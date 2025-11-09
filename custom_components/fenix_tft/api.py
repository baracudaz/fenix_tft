"""API client for Fenix TFT cloud integration."""

import base64
import hashlib
import logging
import secrets
import time
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from .const import (
    API_BASE,
    API_IDENTITY,
    API_TIMEOUT_SECONDS,
    CLIENT_ID,
    HTTP_OK,
    HTTP_REDIRECT,
    REDIRECT_URI,
    SCOPES,
    VALID_PRESET_MODES,
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
    """Generate PKCE code verifier and challenge for OAuth2 security."""
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
        self._username = username
        self._password = password
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expires: float | None = None
        self._sub: str | None = None
        self._login_in_progress = False

    def _headers(self) -> dict[str, str]:
        """Return standard headers with bearer token."""
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }

    async def _ensure_token(self) -> None:
        """Ensure access token is valid, or refresh/login as needed."""
        if self._login_in_progress:
            _LOGGER.debug("Login already in progress, skipping nested attempt")
            return

        if not self._access_token or not self._refresh_token:
            _LOGGER.debug("No tokens, initiating login")
            self._login_in_progress = True
            try:
                success = await self.login()
                if not success:
                    msg = "Login failed"
                    raise FenixTFTApiError(msg)
            finally:
                self._login_in_progress = False
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
        async with self._session.post(
            url, data=data, timeout=API_TIMEOUT_SECONDS
        ) as resp:
            if resp.status != HTTP_OK:
                msg = f"Token refresh failed: {resp.status}"
                _LOGGER.error(msg)
                raise FenixTFTApiError(msg)
            tokens = await resp.json()
            if "access_token" not in tokens:
                msg = "No access_token in response"
                raise FenixTFTApiError(msg)
            self._access_token = tokens["access_token"]
            self._refresh_token = tokens.get("refresh_token", self._refresh_token)
            self._token_expires = time.time() + tokens.get("expires_in", 3600)
            _LOGGER.info("Access token refreshed")

    async def _start_authorization(
        self,
    ) -> tuple[str | None, str | None, str | None, str | None]:
        """Start authorization request and get login URL."""
        code_verifier, code_challenge = generate_pkce_pair()
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        auth_params = {
            "client_id": CLIENT_ID,
            "response_type": "code id_token",
            "scope": SCOPES,
            "redirect_uri": REDIRECT_URI,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
            "oemclient": "fenix",
        }
        auth_url = (
            f"{API_IDENTITY}/connect/authorize?{urllib.parse.urlencode(auth_params)}"
        )

        async with self._session.get(
            auth_url, allow_redirects=False, timeout=API_TIMEOUT_SECONDS
        ) as resp:
            login_path = resp.headers.get("Location")
            if resp.status != HTTP_REDIRECT or not login_path:
                _LOGGER.error(
                    "Authorization failed: status=%s, location=%s",
                    resp.status,
                    login_path,
                )
                return None, None, None, None
            login_url = urllib.parse.urljoin(API_IDENTITY, login_path)
        return login_url, code_verifier, state, nonce

    async def _fetch_login_page(self, login_url: str) -> tuple[str | None, str | None]:
        """Fetch login page and extract CSRF token and ReturnUrl."""
        if not login_url.startswith("http"):
            _LOGGER.debug(
                "Login URL is non-HTTP (%s), skipping login page fetch", login_url
            )
            return None, None

        async with self._session.get(
            login_url, timeout=API_TIMEOUT_SECONDS
        ) as login_page:
            if login_page.status != HTTP_OK:
                _LOGGER.error(
                    "Failed to fetch login page: status=%s", login_page.status
                )
                return None, None

            soup = BeautifulSoup(await login_page.text(), "html.parser")
            csrf_input = soup.find("input", {"name": "__RequestVerificationToken"})
            return_url_input = soup.find("input", {"name": "ReturnUrl"})

            if not (
                csrf_input
                and csrf_input.get("value")
                and return_url_input
                and return_url_input.get("value")
            ):
                _LOGGER.debug(
                    "No CSRF token/ReturnUrl found - possibly cached session redirect"
                )
                return None, None

            return csrf_input["value"], return_url_input["value"]

    async def _submit_login_form(
        self, login_url: str, return_url: str, csrf_token: str
    ) -> str | None:
        """Submit login form and get callback URL."""
        login_data = {
            "ReturnUrl": return_url,
            "Username": self._username,
            "Password": self._password,
            "button": "login",
            "__RequestVerificationToken": csrf_token,
        }
        async with self._session.post(
            login_url,
            data=login_data,
            allow_redirects=False,
            timeout=API_TIMEOUT_SECONDS,
        ) as resp:
            callback_path = resp.headers.get("Location")
            if resp.status != HTTP_REDIRECT or not callback_path:
                _LOGGER.error(
                    "Login failed: status=%s, location=%s", resp.status, callback_path
                )
                return None
            return urllib.parse.urljoin(API_IDENTITY, callback_path)

    async def _handle_callback(
        self, callback_url: str, state: str
    ) -> tuple[str | None, str | None]:
        """Handle callback redirect and extract auth code and ID token."""
        if callback_url.startswith("fenix://"):
            parsed = urllib.parse.urlparse(callback_url)
        else:
            async with self._session.get(
                callback_url,
                allow_redirects=False,
                timeout=API_TIMEOUT_SECONDS,
            ) as resp:
                redirect_url = resp.headers.get("Location", callback_url)
                parsed = urllib.parse.urlparse(redirect_url)

        fragment = urllib.parse.parse_qs(parsed.fragment)
        auth_code = fragment.get("code", [None])[0]
        id_token = fragment.get("id_token", [None])[0]
        returned_state = fragment.get("state", [None])[0]

        if not (returned_state == state and auth_code and id_token):
            _LOGGER.error(
                "Invalid redirect: state mismatch=%s, code=%s, id_token=%s",
                returned_state != state,
                auth_code is None,
                id_token is None,
            )
            return None, None

        return auth_code, id_token

    async def _exchange_tokens(self, auth_code: str, code_verifier: str) -> bool:
        """Exchange authorization code for access and refresh tokens."""
        token_headers = {"Content-Type": "application/x-www-form-urlencoded"}
        token_data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": code_verifier,
            "client_id": CLIENT_ID,
        }
        async with self._session.post(
            f"{API_IDENTITY}/connect/token",
            headers=token_headers,
            data=token_data,
            timeout=API_TIMEOUT_SECONDS,
        ) as resp:
            if resp.status != HTTP_OK:
                msg = f"Token request failed: {resp.status}"
                raise FenixTFTApiError(msg)
            tokens = await resp.json()
            self._access_token = tokens.get("access_token")
            self._refresh_token = tokens.get("refresh_token")
            if not (self._access_token and self._refresh_token):
                msg = "Missing access or refresh token"
                raise FenixTFTApiError(msg)
            self._token_expires = time.time() + tokens.get("expires_in", 3600)
        return True

    async def login(self) -> bool:
        """Perform OAuth2 login and obtain tokens."""
        _LOGGER.debug("Starting login for %s", self._username)
        success = False
        try:
            login_url, code_verifier, state, nonce = await self._start_authorization()
            if not all([login_url, code_verifier, state, nonce]):
                return False

            csrf_token, return_url = await self._fetch_login_page(login_url)

            if not csrf_token and not return_url and login_url.startswith("fenix://"):
                _LOGGER.debug("Detected direct fenix:// callback after cached session")
                callback_url = login_url
            else:
                callback_url = await self._submit_login_form(
                    login_url, return_url, csrf_token
                )
                if not callback_url:
                    return False

            auth_code, id_token = await self._handle_callback(callback_url, state)
            if not (auth_code and id_token):
                return False

            success = await self._exchange_tokens(auth_code, code_verifier)
            if success:
                _LOGGER.info("Login successful")
        except (aiohttp.ClientError, FenixTFTApiError, ValueError, KeyError):
            _LOGGER.exception("Login failed with exception")
            success = False
        return success

    async def get_userinfo(self) -> dict[str, Any]:
        """Retrieve user info from identity endpoint."""
        await self._ensure_token()
        url = f"{API_IDENTITY}/connect/userinfo"
        async with self._session.get(
            url, headers=self._headers(), timeout=API_TIMEOUT_SECONDS
        ) as resp:
            if resp.status != HTTP_OK:
                msg = f"Userinfo failed: {resp.status}"
                raise FenixTFTApiError(msg)
            data = await resp.json()
            self._sub = data.get("sub")
            if not self._sub:
                msg = "No 'sub' field in userinfo"
                raise FenixTFTApiError(msg)
            _LOGGER.debug("Retrieved user sub: %s", self._sub)
            return data

    async def get_installations(self) -> list[dict[str, Any]]:
        """Return all installations associated with the user."""
        if not self._sub:
            await self.get_userinfo()
        url = f"{API_BASE}/businessmodule/v1/installations/admins/{self._sub}"
        async with self._session.get(url, headers=self._headers()) as resp:
            if resp.status != HTTP_OK:
                msg = f"Installations failed: {resp.status}"
                raise FenixTFTApiError(msg)
            return await resp.json()

    async def get_device_properties(self, device_id: str) -> dict[str, Any]:
        """Fetch device properties from configuration endpoint."""
        await self._ensure_token()
        url = (
            f"{API_BASE}/iotmanagement/v1/configuration/"
            f"{device_id}/{device_id}/v1/content/"
        )
        async with self._session.get(url, headers=self._headers()) as resp:
            if resp.status != HTTP_OK:
                msg = f"Device props failed: {resp.status}"
                raise FenixTFTApiError(msg)
            return await resp.json()

    async def get_devices(self) -> list[dict[str, Any]]:
        """Retrieve all devices with their current state."""
        _LOGGER.debug("Fetching devices")
        try:
            installations = await self.get_installations()
        except FenixTFTApiError:
            _LOGGER.exception("Failed to fetch installations")
            return []

        devices = []
        for inst in installations:
            inst_name = inst.get("Il", "Fenix TFT")
            inst_id = inst.get("id")  # Get installation ID
            _LOGGER.debug("Processing installation: %s", inst_name)
            for room in inst.get("rooms", []):
                room_id = room.get("Zn")  # Get room ID (Zn field)
                for dev in room.get("devices", []):
                    dev_id = dev.get("Id_deviceId")
                    try:
                        props = await self.get_device_properties(dev_id)
                        device_data = {
                            "id": dev_id,
                            "name": props.get("Rn", {}).get("value", "Unnamed Device"),
                            "software": props.get("Sv", {}).get("value"),
                            "type": props.get("Ty", {}).get("value"),
                            "installation": inst_name,
                            "installation_id": inst_id,
                            "room_id": room_id,
                            "target_temp": decode_temp_from_entry(props.get("Ma")),
                            "current_temp": decode_temp_from_entry(props.get("At")),
                            "floor_temp": decode_temp_from_entry(props.get("bo")),
                            "hvac_action": props.get("Hs", {}).get("value"),
                            "preset_mode": props.get("Cm", {}).get("value"),
                        }
                        devices.append(device_data)
                    except FenixTFTApiError:
                        _LOGGER.exception(
                            "Failed to fetch properties for device %s", dev_id
                        )
                        continue

        # Update all devices after fetching
        await self.update_all_devices(devices)

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
                msg = f"Failed to set temp: {resp.status}"
                raise FenixTFTApiError(msg)
            return await resp.json()

    async def set_device_preset_mode(
        self, device_id: str, preset_mode: int
    ) -> dict[str, Any]:
        """Set device preset mode (comfort, eco, etc.)."""
        await self._ensure_token()
        if preset_mode not in VALID_PRESET_MODES:
            msg = f"Invalid preset mode: {preset_mode}"
            raise FenixTFTApiError(msg)

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
                msg = f"Failed to set preset mode: {resp.status}"
                raise FenixTFTApiError(msg)
            return await resp.json()

    async def update_all_devices(self, devices: list[dict[str, Any]]) -> None:
        """Update all devices by triggering updates for each installation."""
        _LOGGER.debug("Updating all devices")
        # Trigger updates for each unique installation
        installation_ids = {
            device.get("installation_id")
            for device in devices
            if device.get("installation_id")
        }
        for installation_id in installation_ids:
            await self.trigger_device_updates(installation_id)

    async def trigger_device_updates(self, installation_id: str) -> dict[str, Any]:
        """Trigger device updates for a specific installation."""
        await self._ensure_token()
        payload = {
            "A1": self._sub,
            "In": installation_id,
        }
        url = f"{API_BASE}/iotmanagement/v1/devices/userconnected"

        _LOGGER.debug("Triggering device updates for installation: %s", installation_id)
        async with self._session.put(
            url, headers=self._headers(), json=payload
        ) as resp:
            if resp.status != HTTP_OK:
                msg = f"Failed to trigger device updates: {resp.status}"
                raise FenixTFTApiError(msg)
            return await resp.json()

    async def get_room_energy_consumption(
        self,
        installation_id: str,
        room_id: str,
        device_id: str,
        days: int = 1,
    ) -> list[dict[str, Any]]:
        """Get energy consumption data for a specific room/device."""
        await self._ensure_token()

        # Calculate date range (last N days)
        end_date = datetime.now(tz=UTC)
        start_date = end_date - timedelta(days=days)

        # Format dates as required by API
        start_str = start_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        end_str = end_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        url = (
            f"{API_BASE}/DataProcessing/v1/metricsAggregat/consommation/room/"
            f"{installation_id}/{room_id}/{device_id}/Day/Wc/{start_str}/{end_str}"
        )

        _LOGGER.debug(
            "Fetching energy consumption for room %s, device %s", room_id, device_id
        )

        async with self._session.get(url, headers=self._headers()) as resp:
            if resp.status != HTTP_OK:
                msg = f"Failed to get energy consumption: {resp.status}"
                raise FenixTFTApiError(msg)
            return await resp.json()

    async def fetch_devices_with_energy_data(self) -> list[dict[str, Any]]:
        """Retrieve all devices with their current state and energy consumption data."""
        devices = await self.get_devices()

        # Add energy consumption data to devices that have required IDs
        for device in devices:
            room_id = device.get("room_id")
            installation_id = device.get("installation_id")
            device_id = device.get("id")

            if room_id and installation_id and device_id:
                try:
                    energy_data = await self.get_room_energy_consumption(
                        installation_id, room_id, device_id
                    )

                    # Process the energy data - use processedDataWithAggregator
                    if energy_data and isinstance(energy_data, list):
                        total_consumption = 0
                        for item in energy_data:
                            if isinstance(item, dict):
                                consumption_value = item.get(
                                    "processedDataWithAggregator", 0
                                )
                                total_consumption += consumption_value
                        device["daily_energy_consumption"] = total_consumption
                    else:
                        device["daily_energy_consumption"] = 0
                except FenixTFTApiError as err:
                    _LOGGER.debug(
                        "Failed to fetch energy data for device %s: %s", device_id, err
                    )
                    # Don't fail the entire update if energy data fails
                    device["daily_energy_consumption"] = None
            else:
                # Device missing required IDs for energy consumption
                device["daily_energy_consumption"] = None

        return devices
