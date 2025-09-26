import logging
import time

import aiohttp

_LOGGER = logging.getLogger(__name__)

API_IDENTITY = "https://vs2-fe-identity-prod.azurewebsites.net"
API_BASE = "https://vs2-fe-apim-prod.azure-api.net"
SUBSCRIPTION_KEY = "e14bfd9fa2b3477e874895cb3babe608"


def decode_temp_from_entry(entry: dict | None) -> float | None:
    """Decode temperature from API entry (Fahrenheit + divFactor)."""
    if not entry:
        return None
    value = entry.get("value")
    div = entry.get("divFactor", 1)
    if value is None:
        return None
    f_temp = value / div
    return (f_temp - 32.0) * 5.0 / 9.0


def encode_temp_to_entry(temp_c: float, div_factor: int = 10) -> int:
    """Encode Celsius temp into API raw Fahrenheit*divFactor value."""
    f_temp = (temp_c * 9.0 / 5.0) + 32.0
    return int(round(f_temp * div_factor))


class FenixTFTApi:
    def __init__(
        self, session: aiohttp.ClientSession, access_token: str, refresh_token: str
    ):
        self._session = session
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._token_expires = time.time() + 3600  # assume 1h lifetime
        self._sub = None  # user id (from /userinfo)

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._access_token}",
            "ocp-apim-subscription-key": SUBSCRIPTION_KEY,
            "Accept": "application/json",
        }

    async def _ensure_token(self):
        """Refresh token if expired."""
        if time.time() < self._token_expires - 60:
            return

        url = f"{API_IDENTITY}/connect/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": "b1760b2e-69f1-4e89-8233-5840a9accdf8",
        }
        async with self._session.post(url, data=data) as resp:
            if resp.status != 200:
                text = await resp.text()
                _LOGGER.error("Token refresh failed: %s %s", resp.status, text)
                raise Exception(f"Token refresh failed {resp.status}")
            tokens = await resp.json()
            self._access_token = tokens["access_token"]
            self._refresh_token = tokens.get("refresh_token", self._refresh_token)
            self._token_expires = time.time() + tokens.get("expires_in", 3600)
            _LOGGER.info("Access token refreshed, valid until %s", self._token_expires)

    async def get_userinfo(self):
        await self._ensure_token()
        url = f"{API_IDENTITY}/connect/userinfo"
        async with self._session.get(
            url, headers={"Authorization": f"Bearer {self._access_token}"}
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                _LOGGER.error("Userinfo failed: %s %s", resp.status, text)
                raise Exception(f"Userinfo failed {resp.status}")
            data = await resp.json()
            _LOGGER.debug("Userinfo response: %s", data)
            self._sub = data.get("sub")
            return data

    async def get_installations(self):
        await self._ensure_token()
        if not self._sub:
            await self.get_userinfo()
        url = f"{API_BASE}/businessmodule/v1/installations/admins/{self._sub}"
        async with self._session.get(url, headers=self._headers()) as resp:
            data = await resp.json()
            _LOGGER.debug("Installations response: %s", data)
            return data

    async def get_device_properties(self, device_id: str):
        await self._ensure_token()
        url = f"{API_BASE}/iotmanagement/v1/configuration/{device_id}/{device_id}/v1/content/"
        async with self._session.get(url, headers=self._headers()) as resp:
            if resp.status != 200:
                text = await resp.text()
                _LOGGER.error(
                    "Failed to fetch device properties %s: %s %s",
                    device_id,
                    resp.status,
                    text,
                )
                raise Exception(f"Device props failed {resp.status}")
            data = await resp.json()
            _LOGGER.debug("Device %s properties: %s", device_id, data)
            return data

    async def get_devices(self):
        installations = await self.get_installations()
        devices = []
        for inst in installations:
            inst_id = inst.get("id")
            rooms = inst.get("rooms", [])
            for room in rooms:
                for dev in room.get("devices", []):
                    dev_id = dev.get("Id_deviceId")
                    name = dev.get("Dn", "Fenix TFT")

                    target_temp = None
                    current_temp = None
                    hvac_action = None
                    try:
                        props = await self.get_device_properties(dev_id)
                        target_temp = decode_temp_from_entry(props.get("Ma"))
                        current_temp = decode_temp_from_entry(props.get("At"))
                        hvac_action = props.get("Hs", {}).get("value")
                    except Exception as e:
                        _LOGGER.warning("Could not decode temp for %s: %s", dev_id, e)

                    devices.append(
                        {
                            "id": dev_id,
                            "name": name,
                            "installation_id": inst_id,
                            "room": room.get("Rn"),
                            "target_temp": target_temp,
                            "current_temp": current_temp,
                            "hvac_action": hvac_action,
                        }
                    )
        return devices

    async def set_device_temperature(self, device_id: str, temp_c: float):
        await self._ensure_token()
        raw_val = encode_temp_to_entry(temp_c, div_factor=10)
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
            if resp.status != 200:
                text = await resp.text()
                _LOGGER.error("Failed to set temperature: %s %s", resp.status, text)
                raise Exception(f"Failed to set temp {resp.status}")
            return await resp.json()
