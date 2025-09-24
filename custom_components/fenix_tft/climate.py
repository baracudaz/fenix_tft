import logging
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE

from .const import DOMAIN
from .api import decode_temp

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    api = hass.data[DOMAIN][entry.entry_id]["api"]

    devices = await api.get_devices()
    entities = [FenixTFTClimate(api, dev) for dev in devices]

    async_add_entities(entities)


class FenixTFTClimate(ClimateEntity):
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, api, device):
        self._api = api
        self._device = device
        self._attr_name = f"{device['name']} ({device['room']})"
        self._attr_unique_id = device["id"]
        self._attr_target_temperature = device.get("target_temp")
        self._attr_hvac_mode = HVACMode.HEAT

    async def async_set_temperature(self, **kwargs):
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        await self._api.set_device_temperature(self._device["id"], temp)
        self._attr_target_temperature = temp
        self.async_write_ha_state()

    async def async_update(self):
        """Poll the device for updated target temperature."""
        try:
            props = await self._api.get_device_properties(self._device["id"])
            raw_val = props["Ma"]["value"]  # Raw target temp
            self._attr_target_temperature = decode_temp(raw_val)
            _LOGGER.debug(
                "Decoding target temp for device %s, temp: %f",
                self._device["id"],
                self._attr_target_temperature,
            )

        except Exception as e:
            _LOGGER.warning("Failed to refresh device %s: %s", self._device["id"], e)
