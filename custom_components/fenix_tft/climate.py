import logging

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

FENIX_TFT_TO_HASS_HVAC_ACTION = {
    1: HVACAction.HEATING,
    2: HVACAction.OFF,
    0: HVACAction.IDLE,
    None: HVACAction.OFF,
}


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]

    entities = [
        FenixTFTClimate(api, dev["id"], coordinator) for dev in coordinator.data
    ]
    async_add_entities(entities)


class FenixTFTClimate(ClimateEntity):
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.AUTO, HVACMode.OFF]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    # _attr_preset_modes = # TODO: Add preset modes

    def __init__(self, api, device_id, coordinator):
        self._api = api
        self._id = device_id
        self._coordinator = coordinator

    @property
    def _device(self):
        return next((d for d in self._coordinator.data if d["id"] == self._id), None)

    @property
    def name(self):
        dev = self._device
        if not dev:
            return "Unknown"
        return f"{dev['name']} ({dev['room']})"

    @property
    def unique_id(self):
        return self._id

    @property
    def current_temperature(self):
        return self._device.get("current_temp")

    @property
    def target_temperature(self):
        return self._device.get("target_temp")

    @property
    def hvac_action(self):
        dev = self._device
        raw_action = dev.get("hvac_action") if dev else None
        return FENIX_TFT_TO_HASS_HVAC_ACTION.get(raw_action, HVACAction.OFF)

    @property
    def hvac_mode(self):
        return HVACMode.HEAT

    async def async_set_temperature(self, **kwargs):
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        await self._api.set_device_temperature(self._id, temp)
        await self._coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode):
        # TODO: Implement hvac mode control if supported
        pass

    async def async_update(self):
        await self._coordinator.async_request_refresh()
