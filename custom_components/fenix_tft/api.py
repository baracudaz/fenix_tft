import logging
import aiohttp

_LOGGER = logging.getLogger(__name__)

API_IDENTITY = "https://vs2-fe-identity-prod.azurewebsites.net"
API_BASE = "https://vs2-fe-apim-prod.azure-api.net"
SUBSCRIPTION_KEY = "e14bfd9fa2b3477e874895cb3babe608"


def decode_temp(value: int) -> float:
    return (value - 320) / 18.0


def encode_temp(temp_c: float) -> int:
    return int(round(temp_c * 18.0 + 320))


class FenixTFTApi:
    def __init__(
        self, session: aiohttp.ClientSession, access_token: str, refresh_token: str
    ):
        self._session = session
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._sub = None  # user id (fetched from userinfo)

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._access_token}",
            "ocp-apim-subscription-key": SUBSCRIPTION_KEY,
            "Accept": "application/json",
        }

    async def get_userinfo(self):
        """Fetch user profile to obtain `sub` (user ID)."""
        url = f"{API_IDENTITY}/connect/userinfo"
        async with self._session.get(
            url, headers={"Authorization": f"Bearer {self._access_token}"}
        ) as resp:
            data = await resp.json()
            _LOGGER.debug("Userinfo response: %s", data)
            self._sub = data.get("sub")
            return data

    async def get_installations(self):
        """Fetch installations for the logged-in user (requires sub)."""
        if not self._sub:
            await self.get_userinfo()
        url = f"{API_BASE}/businessmodule/v1/installations/admins/{self._sub}"
        async with self._session.get(url, headers=self._headers()) as resp:
            data = await resp.json()
            _LOGGER.debug("Installations response: %s", data)
            return data

    async def get_devices(self):
        """Flatten all devices across all installations/rooms."""
        installations = await self.get_installations()
        devices = []

        for inst in installations:
            inst_id = inst.get("id")
            rooms = inst.get("rooms", [])
            for room in rooms:
                for dev in room.get("devices", []):
                    dev_id = dev.get("Id_deviceId")
                    name = dev.get("Dn", "Fenix TFT")
                    devices.append(
                        {
                            "id": dev_id,
                            "name": name,
                            "installation_id": inst_id,
                            "room": room.get("Rn"),
                            "target_temp": None,  # will be fetched separately if needed
                        }
                    )
        return devices

    async def set_device_temperature(self, device_id: str, temp_c: float):
        """Send new target temperature."""
        raw_val = encode_temp(temp_c)
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
        _LOGGER.debug(
            "Setting temperature %s °C (raw=%s) for device %s",
            temp_c,
            raw_val,
            device_id,
        )

        async with self._session.put(
            url, headers=self._headers(), json=payload
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                _LOGGER.error(
                    "Failed to set temperature for %s: %s %s",
                    device_id,
                    resp.status,
                    text,
                )
                raise Exception(f"Failed to set temp: {resp.status}")
            data = await resp.json()
            _LOGGER.debug("Set temp response: %s", data)
            return data
