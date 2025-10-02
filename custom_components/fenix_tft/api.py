"""API client for Fenix TFT cloud integration."""

import base64
import hashlib
import logging
import secrets
import time
import urllib.parse
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from .const import (
    API_BASE,
    API_IDENTITY,
    CLIENT_ID,
    CLIENT_SECRET,
    HTTP_OK,
    HTTP_REDIRECT,
    LOGIN_URL,
    REDIRECT_URI,
    SCOPES,
    SUBSCRIPTION_KEY,
    TOKEN_URL,
)

_LOGGER = logging.getLogger(__name__)


class FenixTFTApiError(Exception):
    """Exception raised for Fenix TFT API errors."""


def decode_temp_from_entry(entry: dict[str, Any] | None) -> float | None:
    """Decode temperature from API entry (Fahrenheit + divFactor)."""
    if not entry:
        return None
    value = entry.get("value")
    div = entry.get("divFactor", 1)
    if value is None:
        return None
    f_temp = value / div
    return (f_temp - 32.0) * 5.0 / 9.0


def encode_temp_to_entry(temp_c: float, div_factor: int = 10) -> float:
    """Encode Celsius temp into API raw Fahrenheit*divFactor value."""
    f_temp = (temp_c * 9.0 / 5.0) + 32.0
    return round(f_temp * div_factor)


def generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE code verifier and challenge."""
    code_verifier = secrets.token_urlsafe(96)[:128]
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )
    return code_verifier, code_challenge


class FenixTFTApi:
    """Fenix TFT API client."""

    def __init__(
        self, session: aiohttp.ClientSession, username: str, password: str
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._session._default_timeout = aiohttp.ClientTimeout(total=10)
        self._username = username
        self._password = password
        self._access_token = None
        self._refresh_token = None
        self._token_expires = None
        self._sub = None

    def load_from_config(self, config: dict) -> None:
        """Load tokens and sub from config entry."""
        self._access_token = config.get("access_token")
        self._refresh_token = config.get("refresh_token")
        self._token_expires = config.get("token_expires")
        self._sub = config.get("sub")
        _LOGGER.debug("Loaded config: sub=%s", self._sub)

    def _headers(self) -> dict[str, str]:
        """Return headers for API requests."""
        return {
            "Authorization": f"Bearer {self._access_token}",
            "ocp-apim-subscription-key": SUBSCRIPTION_KEY,
            "Accept": "application/json",
        }

    async def _ensure_token(self) -> None:
        """Ensure access token is valid, login if tokens are empty."""
        if not self._access_token or not self._refresh_token:
            _LOGGER.debug("No tokens, initiating login")
            if not await self.login():
                raise FenixTFTApiError("Login failed")
            return

        if self._token_expires and time.time() < self._token_expires - 60:
            return

        _LOGGER.debug("Refreshing access token")
        url = f"{API_IDENTITY}/connect/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": CLIENT_ID,
        }
        async with self._session.post(url, data=data, timeout=10) as resp:
            if resp.status != HTTP_OK:
                _LOGGER.error("Token refresh failed: status=%s", resp.status)
                raise FenixTFTApiError(f"Token refresh failed: {resp.status}")
            tokens = await resp.json()
            if "access_token" not in tokens:
                raise FenixTFTApiError("No access_token in response")
            self._access_token = tokens["access_token"]
            self._refresh_token = tokens.get("refresh_token", self._refresh_token)
            self._token_expires = time.time() + tokens.get("expires_in", 3600)
            _LOGGER.info("Access token refreshed")

    async def login(self) -> bool:
        """Perform OAuth2 login and obtain tokens."""
        _LOGGER.debug("Starting login for %s", self._username)
        code_verifier, code_challenge = generate_pkce_pair()
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        return_url = (
            f"/connect/authorize/callback?client_id={CLIENT_ID}&response_type=code%20id_token"
            f"&scope={urllib.parse.quote(SCOPES)}&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
            f"&nonce={nonce}&code_challenge={code_challenge}&code_challenge_method=S256"
            f"&state={state}&oemclient=fenix"
        )

        login_params = {"ReturnUrl": return_url}
        async with self._session.get(
            LOGIN_URL, params=login_params, timeout=10
        ) as login_page:
            if login_page.status != HTTP_OK:
                _LOGGER.error(
                    "Failed to fetch login page: status=%s", login_page.status
                )
                return False
            soup = BeautifulSoup(await login_page.text(), "html.parser")
            csrf_token = soup.find("input", {"name": "__RequestVerificationToken"})[
                "value"
            ]

        login_data = {
            "ReturnUrl": return_url,
            "Username": self._username,
            "Password": self._password,
            "button": "login",
            "__RequestVerificationToken": csrf_token,
        }
        async with self._session.post(
            LOGIN_URL, data=login_data, allow_redirects=False, timeout=10
        ) as login_response:
            if login_response.status != HTTP_REDIRECT:
                _LOGGER.error(
                    "Login did not redirect: status=%s", login_response.status
                )
                return False
            callback_path = login_response.headers["Location"]

        callback_url = urllib.parse.urljoin(API_IDENTITY, callback_path)
        async with self._session.get(
            callback_url, allow_redirects=False, timeout=10
        ) as callback_response:
            if callback_response.status != HTTP_REDIRECT:
                _LOGGER.error(
                    "Callback did not redirect: status=%s", callback_response.status
                )
                return False
            redirect_url = callback_response.headers["Location"]

        parsed = urllib.parse.urlparse(redirect_url)
        fragment = urllib.parse.parse_qs(parsed.fragment)
        auth_code = fragment.get("code", [None])[0]
        id_token = fragment.get("id_token", [None])[0]
        returned_state = fragment.get("state", [None])[0]
        if returned_state != state or not auth_code or not id_token:
            _LOGGER.error("Invalid redirect: state mismatch or missing code/id_token")
            return False

        token_headers = {
            "Authorization": f"Basic {base64.b64encode(f'{CLIENT_ID}:{CLIENT_SECRET}'.encode()).decode()}",
            "Content-Type": "application/x-www-form-urlencoded",
            "ocp-apim-subscription-key": SUBSCRIPTION_KEY,
        }
        token_data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": code_verifier,
        }
        async with self._session.post(
            TOKEN_URL, headers=token_headers, data=token_data, timeout=10
        ) as token_response:
            if token_response.status != HTTP_OK:
                _LOGGER.error("Token request failed: status=%s", token_response.status)
                return False
            tokens = await token_response.json()
            self._access_token = tokens.get("access_token")
            self._refresh_token = tokens.get("refresh_token")
            self._token_expires = time.time() + tokens.get("expires_in", 3600)

        if not self._access_token or not self._refresh_token:
            _LOGGER.error("Missing access or refresh token")
            return False

        async with self._session.get(
            f"{API_IDENTITY}/connect/userinfo",
            headers={"Authorization": f"Bearer {self._access_token}"},
            timeout=10,
        ) as userinfo_response:
            if userinfo_response.status != HTTP_OK:
                _LOGGER.error(
                    "Failed to fetch userinfo: status=%s", userinfo_response.status
                )
                return False
            data = await userinfo_response.json()
            self._sub = data.get("sub")
            if not self._sub:
                _LOGGER.error("No 'sub' field in userinfo")
                return False

        _LOGGER.info("Login successful, sub=%s", self._sub)
        return True

    async def get_userinfo(self) -> dict[str, Any]:
        """Fetch user info from API."""
        await self._ensure_token()
        url = f"{API_IDENTITY}/connect/userinfo"
        async with self._session.get(
            url, headers={"Authorization": f"Bearer {self._access_token}"}, timeout=10
        ) as resp:
            if resp.status != HTTP_OK:
                _LOGGER.error("Userinfo failed: status=%s", resp.status)
                raise FenixTFTApiError(f"Userinfo failed: {resp.status}")
            data = await resp.json()
            self._sub = data.get("sub")
            if not self._sub:
                raise FenixTFTApiError("No 'sub' field in userinfo")
            return data

    async def get_installations(self) -> list[dict[str, Any]]:
        """Fetch installations for the user."""
        if not self._sub:
            await self.get_userinfo()
        url = f"{API_BASE}/businessmodule/v1/installations/admins/{self._sub}"
        async with self._session.get(url, headers=self._headers()) as resp:
            if resp.status != HTTP_OK:
                _LOGGER.error("Installations request failed: status=%s", resp.status)
                raise FenixTFTApiError(f"Installations failed: {resp.status}")
            return await resp.json()

    async def get_device_properties(self, device_id: str) -> dict[str, Any]:
        """Fetch device properties from API."""
        await self._ensure_token()
        url = f"{API_BASE}/iotmanagement/v1/configuration/{device_id}/{device_id}/v1/content/"
        async with self._session.get(url, headers=self._headers()) as resp:
            if resp.status != HTTP_OK:
                _LOGGER.error(
                    "Failed to fetch device %s properties: status=%s",
                    device_id,
                    resp.status,
                )
                raise FenixTFTApiError(f"Device props failed: {resp.status}")
            return await resp.json()

    async def get_devices(self) -> list[dict[str, Any]]:
        """Fetch all devices for the user."""
        _LOGGER.debug("Fetching devices")
        try:
            installations = await self.get_installations()
            if not installations:
                _LOGGER.warning("No installations found for user %s", self._sub)
        except FenixTFTApiError as err:
            _LOGGER.error("Failed to fetch installations: %s", err)
            return []

        devices = []
        for inst in installations:
            inst_id = inst.get("id")
            rooms = inst.get("rooms", [])
            if not rooms:
                _LOGGER.warning("No rooms in installation %s", inst_id)

            for room in rooms:
                room_name = room.get("Rn", "Unknown")
                room_devices = room.get("devices", [])
                if not room_devices:
                    _LOGGER.warning("No devices in room %s", room_name)

                for dev in room_devices:
                    dev_id = dev.get("Id_deviceId")
                    name = dev.get("Dn", "Fenix TFT")
                    try:
                        props = await self.get_device_properties(dev_id)
                        devices.append(
                            {
                                "id": dev_id,
                                "name": name,
                                "installation_id": inst_id,
                                "room": room_name,
                                "target_temp": decode_temp_from_entry(props.get("Ma")),
                                "current_temp": decode_temp_from_entry(props.get("At")),
                                "hvac_action": props.get("Hs", {}).get("value"),
                                "preset_mode": props.get("Cm", {}).get("value"),
                            }
                        )
                    except FenixTFTApiError as err:
                        _LOGGER.error(
                            "Failed to fetch properties for device %s: %s", dev_id, err
                        )
                        continue

        _LOGGER.debug("Fetched %d devices", len(devices))
        return devices

    async def set_device_temperature(
        self, device_id: str, temp_c: float
    ) -> dict[str, Any]:
        """Set target temperature for a device."""
        await self._ensure_token()
        raw_val = encode_temp_to_entry(temp_c)
        payload = {
            "Id_deviceId": device_id,
            "S1": device_id,
            "configurationVersion": "v1.0",
            "data": [
                {"wattsType": "Dm", "wattsTypeValue": 6},
                {"wattsType": "Ma", "wattsTypeValue": raw_val},
            ],
        }
        url = f"{API_BASE}/iotmanagement/v1/devices/twin/properties/config/replace"
        async with self._session.put(
            url, headers=self._headers(), json=payload
        ) as resp:
            if resp.status != HTTP_OK:
                _LOGGER.error(
                    "Failed to set temperature for %s: status=%s",
                    device_id,
                    resp.status,
                )
                raise FenixTFTApiError(f"Failed to set temp: {resp.status}")
            return await resp.json()

    async def set_device_preset_mode(
        self, device_id: str, preset_mode: int
    ) -> dict[str, Any]:
        """Set preset mode for a device."""
        await self._ensure_token()
        valid_modes = {0, 1, 2, 4, 5, 6}
        if preset_mode not in valid_modes:
            raise FenixTFTApiError(f"Invalid preset mode: {preset_mode}")

        _LOGGER.debug("Setting preset mode %s for device %s", preset_mode, device_id)
        payload = {
            "Id_deviceId": device_id,
            "S1": device_id,
            "configurationVersion": "v1.0",
            "data": [{"wattsType": "Dm", "wattsTypeValue": preset_mode}],
        }
        url = f"{API_BASE}/iotmanagement/v1/devices/twin/properties/config/replace"
        async with self._session.put(
            url, headers=self._headers(), json=payload
        ) as resp:
            if resp.status != HTTP_OK:
                _LOGGER.error(
                    "Failed to set preset mode for %s: status=%s",
                    device_id,
                    resp.status,
                )
                raise FenixTFTApiError(f"Failed to set preset mode: {resp.status}")
            return await resp.json()
