"""Platform for Fenix TFT climate entities."""

import logging
from typing import Any, ClassVar

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

FENIX_TFT_TO_HASS_HVAC_ACTION: dict[int | None, HVACAction] = {
    1: HVACAction.HEATING,
    2: HVACAction.OFF,
    0: HVACAction.IDLE,
    None: HVACAction.OFF,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Any,
) -> None:
    """Set up Fenix TFT climate entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]

    entities = [
        FenixTFTClimate(api, dev["id"], coordinator) for dev in coordinator.data
    ]
    async_add_entities(entities)


class FenixTFTClimate(ClimateEntity):
    """Representation of a Fenix TFT climate entity."""

    _attr_hvac_modes: ClassVar[list[HVACMode]] = [
        HVACMode.HEAT,
        HVACMode.AUTO,
        HVACMode.OFF,
    ]
    _attr_supported_features: ClassVar[int] = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit: ClassVar[str] = UnitOfTemperature.CELSIUS

    def __init__(self, api: Any, device_id: str, coordinator: Any) -> None:
        """Initialize the climate entity."""
        self._api = api
        self._id = device_id
        self._coordinator = coordinator

    @property
    def _device(self) -> dict[str, Any] | None:
        """Return the device dict for this entity."""
        return next((d for d in self._coordinator.data if d["id"] == self._id), None)

    @property
    def name(self) -> str:
        """Return the name of the climate entity."""
        dev = self._device
        if not dev:
            return "Unknown"
        return f"{dev['name']} ({dev['room']})"

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this entity."""
        return self._id

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        dev = self._device
        return dev.get("current_temp") if dev else None

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        dev = self._device
        return dev.get("target_temp") if dev else None

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current HVAC action."""
        dev = self._device
        raw_action = dev.get("hvac_action") if dev else None
        return FENIX_TFT_TO_HASS_HVAC_ACTION.get(raw_action, HVACAction.OFF)

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        return HVACMode.HEAT

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        await self._api.set_device_temperature(self._id, temp)
        await self._coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode (not implemented)."""
        # TODO(baracudaz): Implement hvac mode control if supported. See https://github.com/baracudaz/fenix_tft/issues/1

    async def async_update(self) -> None:
        """Request latest data from coordinator."""
        await self._coordinator.async_request_refresh()
