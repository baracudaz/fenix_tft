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

    def _headers(self) -> dict[str, str]:
        """Return headers for API requests."""
        return {
            "Authorization": f"Bearer {self._access_token}",
            "ocp-apim-subscription-key": SUBSCRIPTION_KEY,
            "Accept": "application/json",
        }

    async def _ensure_token(self) -> None:
        """Ensure access token is valid, login if tokens are empty."""
        _LOGGER.debug(
            "Ensuring access token is valid, current expiry: %s, access_token: %s, refresh_token: %s",
            self._token_expires,
            self._access_token,
            self._refresh_token,
        )

        # If no tokens, attempt login
        if not self._access_token or not self._refresh_token:
            _LOGGER.debug("No access or refresh token, initiating login")
            if not await self.login():
                _LOGGER.error("Login failed, cannot obtain tokens")
                raise FenixTFTApiError("Login failed during token initialization")
            return

        # If token is still valid, return
        if self._token_expires and time.time() < self._token_expires - 60:
            _LOGGER.debug("Access token is still valid")
            return

        # Refresh token
        _LOGGER.debug(
            "Access token expired or near expiry, refreshing with refresh_token: %s",
            self._refresh_token,
        )
        url = f"{API_IDENTITY}/connect/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": CLIENT_ID,
        }
        try:
            async with self._session.post(url, data=data, timeout=10) as resp:
                text = await resp.text()
                _LOGGER.debug(
                    "Token refresh request: status=%s, response=%s", resp.status, text
                )
                if resp.status != HTTP_OK:
                    _LOGGER.error(
                        "Token refresh failed: status=%s, response=%s",
                        resp.status,
                        text,
                    )
                    raise FenixTFTApiError(
                        f"Token refresh failed: {resp.status} {text}"
                    )
                tokens = await resp.json()
                _LOGGER.debug("Token refresh response: %s", tokens)
                if "access_token" not in tokens:
                    _LOGGER.error("No access_token in token refresh response")
                    raise FenixTFTApiError("No access_token in response")
                self._access_token = tokens["access_token"]
                self._refresh_token = tokens.get("refresh_token", self._refresh_token)
                self._token_expires = time.time() + tokens.get("expires_in", 3600)
                _LOGGER.info(
                    "Access token refreshed, valid until %s", self._token_expires
                )
        except aiohttp.ClientConnectorDNSError as err:
            _LOGGER.error("DNS resolution failed for token refresh %s: %s", url, err)
            raise FenixTFTApiError(f"DNS error: {err}") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("HTTP error during token refresh: %s", err)
            raise FenixTFTApiError(f"HTTP error: {err}") from err
        except asyncio.TimeoutError:
            _LOGGER.error("Token refresh request timed out")
            raise FenixTFTApiError("Token refresh timed out")
        except Exception as err:
            _LOGGER.error("Unexpected error during token refresh: %s", err)
            raise FenixTFTApiError(f"Unexpected error: {err}") from err

    async def login(self) -> bool:
        """Perform OAuth2 login and obtain tokens."""
        _LOGGER.debug("Starting login process for username: %s", self._username)

        # Step 1: Generate PKCE pair and state
        code_verifier, code_challenge = generate_pkce_pair()
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        _LOGGER.debug(
            "Generated PKCE: code_verifier=%s, code_challenge=%s, state=%s, nonce=%s",
            code_verifier,
            code_challenge,
            state,
            nonce,
        )

        # Step 2: Construct ReturnUrl
        return_url = (
            f"/connect/authorize/callback?client_id={CLIENT_ID}&response_type=code%20id_token"
            f"&scope={urllib.parse.quote(SCOPES)}&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
            f"&nonce={nonce}&code_challenge={code_challenge}&code_challenge_method=S256"
            f"&state={state}&oemclient=fenix"
        )
        _LOGGER.debug("Constructed ReturnUrl: %s", return_url)

        # Step 3: Fetch login page to extract CSRF token
        login_params = {"ReturnUrl": return_url}
        try:
            async with self._session.get(
                LOGIN_URL, params=login_params, timeout=10
            ) as login_page:
                _LOGGER.debug("Login page request: status=%s", login_page.status)
                if login_page.status != HTTP_OK:
                    _LOGGER.error(
                        "Failed to fetch login page: status=%s, response=%s",
                        login_page.status,
                        await login_page.text(),
                    )
                    return False
                soup = BeautifulSoup(await login_page.text(), "html.parser")
                csrf_token = soup.find("input", {"name": "__RequestVerificationToken"})[
                    "value"
                ]
                _LOGGER.debug("Extracted CSRF token: %s", csrf_token)
        except Exception as err:
            _LOGGER.error("Error fetching login page: %s", err)
            return False

        # Step 4: Submit login form
        login_data = {
            "ReturnUrl": return_url,
            "Username": self._username,
            "Password": self._password,
            "button": "login",
            "__RequestVerificationToken": csrf_token,
        }
        try:
            async with self._session.post(
                LOGIN_URL, data=login_data, allow_redirects=False, timeout=10
            ) as login_response:
                _LOGGER.debug("Login form submission: status=%s", login_response.status)
                if login_response.status != HTTP_REDIRECT:
                    _LOGGER.error(
                        "Login did not redirect: status=%s, response=%s",
                        login_response.status,
                        await login_response.text(),
                    )
                    return False
                callback_path = login_response.headers["Location"]
                _LOGGER.debug("Login redirect to: %s", callback_path)
        except Exception as err:
            _LOGGER.error("Error submitting login form: %s", err)
            return False

        # Step 5: Follow redirect to get authorization code
        callback_url = urllib.parse.urljoin(API_IDENTITY, callback_path)
        try:
            async with self._session.get(
                callback_url, allow_redirects=False, timeout=10
            ) as callback_response:
                _LOGGER.debug("Callback request: status=%s", callback_response.status)
                if callback_response.status != HTTP_REDIRECT:
                    _LOGGER.error(
                        "Callback did not redirect: status=%s, response=%s",
                        callback_response.status,
                        await callback_response.text(),
                    )
                    return False
                redirect_url = callback_response.headers["Location"]
                _LOGGER.debug("Callback redirect to: %s", redirect_url)
        except Exception as err:
            _LOGGER.error("Error following callback redirect: %s", err)
            return False

        # Step 6: Parse the redirect URI
        parsed = urllib.parse.urlparse(redirect_url)
        fragment = urllib.parse.parse_qs(parsed.fragment)
        auth_code = fragment.get("code", [None])[0]
        id_token = fragment.get("id_token", [None])[0]
        returned_state = fragment.get("state", [None])[0]
        _LOGGER.debug(
            "Parsed redirect: auth_code=%s, id_token=%s, state=%s",
            auth_code,
            id_token,
            returned_state,
        )
        if returned_state != state:
            _LOGGER.error(
                "State mismatch in OAuth2 flow: expected=%s, received=%s",
                state,
                returned_state,
            )
            return False
        if not auth_code or not id_token:
            _LOGGER.error("Authorization code or ID token missing")
            return False

        # Step 7: Exchange authorization code for access token
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
        try:
            async with self._session.post(
                TOKEN_URL, headers=token_headers, data=token_data, timeout=10
            ) as token_response:
                _LOGGER.debug("Token request: status=%s", token_response.status)
                if token_response.status != HTTP_OK:
                    _LOGGER.error(
                        "Token request failed: status=%s, response=%s",
                        token_response.status,
                        await token_response.text(),
                    )
                    return False
                tokens = await token_response.json()
                _LOGGER.debug("Token response: %s", tokens)
                self._access_token = tokens.get("access_token")
                self._refresh_token = tokens.get("refresh_token")
                self._token_expires = time.time() + tokens.get("expires_in", 3600)
                _LOGGER.debug(
                    "Tokens obtained: access_token=%s, refresh_token=%s, expires=%s",
                    self._access_token,
                    self._refresh_token,
                    self._token_expires,
                )
        except Exception as err:
            _LOGGER.error("Error exchanging authorization code: %s", err)
            return False

        if not self._access_token or not self._refresh_token:
            _LOGGER.error("Access token or refresh token missing in response")
            return False

        # Step 8: Fetch userinfo to set self._sub
        try:
            async with self._session.get(
                f"{API_IDENTITY}/connect/userinfo",
                headers={"Authorization": f"Bearer {self._access_token}"},
                timeout=10,
            ) as userinfo_response:
                _LOGGER.debug("Userinfo request: status=%s", userinfo_response.status)
                if userinfo_response.status != HTTP_OK:
                    _LOGGER.error(
                        "Failed to fetch userinfo: status=%s, response=%s",
                        userinfo_response.status,
                        await userinfo_response.text(),
                    )
                    return False
                data = await userinfo_response.json()
                self._sub = data.get("sub")
                _LOGGER.debug("Userinfo fetched, sub: %s", self._sub)
                if not self._sub:
                    _LOGGER.error("No 'sub' field in userinfo response")
                    return False
        except Exception as err:
            _LOGGER.error("Error fetching userinfo during login: %s", err)
            return False

        _LOGGER.debug("Login successful, tokens and sub obtained: sub=%s", self._sub)
        return True

    async def get_userinfo(self) -> dict[str, Any]:
        """Fetch user info from API."""
        await self._ensure_token()
        url = f"{API_IDENTITY}/connect/userinfo"
        try:
            async with self._session.get(
                url,
                headers={"Authorization": f"Bearer {self._access_token}"},
                timeout=10,
            ) as resp:
                _LOGGER.debug(
                    "Userinfo request: status=%s, response=%s",
                    resp.status,
                    await resp.text(),
                )
                if resp.status != HTTP_OK:
                    _LOGGER.error(
                        "Userinfo failed: status=%s, response=%s",
                        resp.status,
                        await resp.text(),
                    )
                    raise FenixTFTApiError(f"Userinfo failed: {resp.status}")
                data = await resp.json()
                self._sub = data.get("sub")
                if not self._sub:
                    _LOGGER.error("No 'sub' field in userinfo response")
                    raise FenixTFTApiError("No 'sub' field in userinfo response")
                _LOGGER.debug("Userinfo response: %s", data)
                return data
        except aiohttp.ClientConnectorDNSError as err:
            _LOGGER.error("DNS resolution failed for userinfo %s: %s", url, err)
            raise FenixTFTApiError(f"DNS error: {err}") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("HTTP error during userinfo: %s", err)
            raise FenixTFTApiError(f"HTTP error: {err}") from err
        except asyncio.TimeoutError:
            _LOGGER.error("Userinfo request timed out")
            raise FenixTFTApiError("Userinfo request timed out")
        except Exception as err:
            _LOGGER.error("Unexpected error during userinfo: %s", err)
            raise FenixTFTApiError(f"Unexpected error: {err}") from err

    async def get_installations(self) -> list[dict[str, Any]]:
        """Fetch installations for the user."""
        _LOGGER.debug("Fetching installations for user %s", self._sub)
        if not self._sub:
            await self.get_userinfo()
        url = f"{API_BASE}/businessmodule/v1/installations/admins/{self._sub}"
        try:
            async with self._session.get(url, headers=self._headers()) as resp:
                _LOGGER.debug(
                    "Installations request: status=%s, response=%s",
                    resp.status,
                    await resp.text(),
                )
                if resp.status != HTTP_OK:
                    _LOGGER.error(
                        "Installations request failed: status=%s, response=%s",
                        resp.status,
                        await resp.text(),
                    )
                    raise FenixTFTApiError(f"Installations failed: {resp.status}")
                data = await resp.json()
                _LOGGER.debug("Installations response: %s", data)
                return data
        except aiohttp.ClientConnectorDNSError as err:
            _LOGGER.error("DNS resolution failed for installations %s: %s", url, err)
            raise FenixTFTApiError(f"DNS error: {err}") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("HTTP error fetching installations: %s", err)
            raise FenixTFTApiError(f"HTTP error: {err}") from err
        except asyncio.TimeoutError:
            _LOGGER.error("Installations request timed out")
            raise FenixTFTApiError("Installations request timed out")
        except Exception as err:
            _LOGGER.error("Unexpected error fetching installations: %s", err)
            raise FenixTFTApiError(f"Unexpected error: {err}") from err

    async def get_device_properties(self, device_id: str) -> dict[str, Any]:
        """Fetch device properties from API."""
        await self._ensure_token()
        url = f"{API_BASE}/iotmanagement/v1/configuration/{device_id}/{device_id}/v1/content/"
        try:
            async with self._session.get(url, headers=self._headers()) as resp:
                _LOGGER.debug(
                    "Device %s properties request: status=%s, response=%s",
                    device_id,
                    resp.status,
                    await resp.text(),
                )
                if resp.status != HTTP_OK:
                    _LOGGER.error(
                        "Failed to fetch device properties %s: status=%s, response=%s",
                        device_id,
                        resp.status,
                        await resp.text(),
                    )
                    raise FenixTFTApiError(f"Device props failed: {resp.status}")
                data = await resp.json()
                _LOGGER.debug("Device %s properties: %s", device_id, data)
                return data
        except aiohttp.ClientConnectorDNSError as err:
            _LOGGER.error(
                "DNS resolution failed for device properties %s: %s", url, err
            )
            raise FenixTFTApiError(f"DNS error: {err}") from err
        except aiohttp.ClientError as err:
            _LOGGER.error(
                "HTTP error fetching device properties %s: %s", device_id, err
            )
            raise FenixTFTApiError(f"HTTP error: {err}") from err
        except asyncio.TimeoutError:
            _LOGGER.error(
                "Device properties request timed out for device %s", device_id
            )
            raise FenixTFTApiError("Device properties request timed out")
        except Exception as err:
            _LOGGER.error(
                "Unexpected error fetching device properties %s: %s", device_id, err
            )
            raise FenixTFTApiError(f"Unexpected error: {err}") from err

    async def get_devices(self) -> list[dict[str, Any]]:
        """Fetch all devices for the user."""
        _LOGGER.debug("Fetching devices for user")
        try:
            installations = await self.get_installations()
            _LOGGER.debug("Fetched installations: %s", installations)
            if not installations:
                _LOGGER.warning("No installations found for user %s", self._sub)
        except FenixTFTApiError as err:
            _LOGGER.error("Failed to fetch installations: %s", err)
            return []

        devices = []
        for inst in installations:
            inst_id = inst.get("id")
            rooms = inst.get("rooms", [])
            _LOGGER.debug(
                "Processing installation %s with %d rooms", inst_id, len(rooms)
            )
            if not rooms:
                _LOGGER.warning("No rooms found in installation %s", inst_id)

            for room in rooms:
                room_name = room.get("Rn", "Unknown")
                room_devices = room.get("devices", [])
                _LOGGER.debug(
                    "Processing room %s with %d devices", room_name, len(room_devices)
                )
                if not room_devices:
                    _LOGGER.warning("No devices found in room %s", room_name)

                for dev in room_devices:
                    dev_id = dev.get("Id_deviceId")
                    name = dev.get("Dn", "Fenix TFT")
                    _LOGGER.debug(
                        "Fetching properties for device %s (%s)", dev_id, name
                    )

                    target_temp = None
                    current_temp = None
                    hvac_action = None
                    preset_mode = None
                    try:
                        props = await self.get_device_properties(dev_id)
                        _LOGGER.debug("Device %s properties: %s", dev_id, props)
                        target_temp = decode_temp_from_entry(props.get("Ma"))
                        current_temp = decode_temp_from_entry(props.get("At"))
                        hvac_action = props.get("Hs", {}).get("value")
                        preset_mode = props.get("Cm", {}).get("value")
                    except FenixTFTApiError as err:
                        _LOGGER.error(
                            "Failed to fetch properties for device %s: %s", dev_id, err
                        )
                        continue

                    devices.append(
                        {
                            "id": dev_id,
                            "name": name,
                            "installation_id": inst_id,
                            "room": room_name,
                            "target_temp": target_temp,
                            "current_temp": current_temp,
                            "hvac_action": hvac_action,
                            "preset_mode": preset_mode,
                        }
                    )
                    _LOGGER.debug("Added device %s to devices list", dev_id)

        _LOGGER.debug("Total devices fetched: %d", len(devices))
        return devices
