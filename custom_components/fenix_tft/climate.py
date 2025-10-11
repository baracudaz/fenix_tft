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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

FENIX_TFT_TO_HASS_HVAC_ACTION: dict[int | None, HVACAction] = {
    1: HVACAction.HEATING,
    2: HVACAction.OFF,
    0: HVACAction.IDLE,
    None: HVACAction.OFF,
}

# HVAC mode mappings (basic operational modes)
HVAC_MODE_MAP: dict[int, str] = {
    0: "off",
    1: "holidays",
    2: "auto",
    6: "manual",
}
HVAC_MODE_INVERTED: dict[str, int] = {v: k for k, v in HVAC_MODE_MAP.items()}

# Preset mode mappings (special operational modes)
PRESET_MAP: dict[int, str] = {
    2: "program",
    4: "defrost",
    5: "boost",
}
PRESET_INVERTED: dict[str, int] = {v: k for k, v in PRESET_MAP.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Any,
) -> None:
    """Set up Fenix TFT climate entities from a config entry."""
    data = entry.runtime_data  # Use runtime_data, not hass.data
    coordinator = data["coordinator"]
    api = data["api"]

    entities = [
        FenixTFTClimate(api, dev["id"], coordinator) for dev in coordinator.data
    ]
    async_add_entities(entities)


class FenixTFTClimate(CoordinatorEntity, ClimateEntity):
    """Representation of a Fenix TFT climate entity."""

    _attr_hvac_modes: ClassVar[list[HVACMode]] = [
        HVACMode.HEAT,
        HVACMode.AUTO,
        HVACMode.OFF,
    ]
    _attr_preset_modes: ClassVar[list[str]] = [
        "program",
        "defrost",
        "boost",
    ]
    _attr_temperature_unit: ClassVar[str] = UnitOfTemperature.CELSIUS
    _attr_has_entity_name: bool = True
    _attr_translation_key: str = "thermostat"

    def __init__(self, api: Any, device_id: str, coordinator: Any) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._api: Any = api
        self._id: str = device_id
        self._attr_unique_id: str = device_id

        dev: dict[str, Any] | None = next(
            (d for d in coordinator.data if d["id"] == device_id), None
        )
        self._attr_device_info: DeviceInfo = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=dev["name"] if dev else None,
            manufacturer="Fenix",
            model="TFT WiFi Thermostat",
        )

    @property
    def _device(self) -> dict[str, Any] | None:
        """Return the device dict for this entity."""
        return next((d for d in self.coordinator.data if d["id"] == self._id), None)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self._device is not None

    def _get_preset_mode(self) -> str | None:
        """Get the current preset mode string from device data."""
        dev = self._device
        if not dev:
            return None
        raw_preset = dev.get("preset_mode")
        if raw_preset is None:
            return None
        return PRESET_MAP.get(raw_preset)

    @property
    def name(self) -> str | None:
        """Return the name of the climate entity."""
        dev = self._device
        return dev.get("name") if dev else None

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
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        preset = self._get_preset_mode()
        return preset if preset in self._attr_preset_modes else None

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the list of supported features based on current mode."""
        dev = self._device
        raw_preset = dev.get("preset_mode") if dev else None
        hvac_mode_str = (
            HVAC_MODE_MAP.get(raw_preset) if raw_preset is not None else None
        )
        if hvac_mode_str == "manual":
            return (
                ClimateEntityFeature.TARGET_TEMPERATURE
                | ClimateEntityFeature.PRESET_MODE
            )
        return ClimateEntityFeature.PRESET_MODE

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        dev = self._device
        raw_preset = dev.get("preset_mode") if dev else None
        hvac_mode_str = (
            HVAC_MODE_MAP.get(raw_preset) if raw_preset is not None else None
        )
        _LOGGER.debug(
            "Device %s preset mode: %s (%s)", self._id, raw_preset, hvac_mode_str
        )
        if hvac_mode_str == "off":
            return HVACMode.OFF
        if hvac_mode_str == "manual":
            return HVACMode.HEAT
        return HVACMode.AUTO

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temp: float | None = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        await self._api.set_device_temperature(self._id, temp)
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode by mapping to appropriate preset mode."""
        _LOGGER.debug("Setting HVAC mode to %s for device %s", hvac_mode, self._id)
        if hvac_mode == HVACMode.OFF:
            preset_value = HVAC_MODE_INVERTED["off"]
        elif hvac_mode == HVACMode.AUTO:
            preset_value = HVAC_MODE_INVERTED["auto"]
        elif hvac_mode == HVACMode.HEAT:
            preset_value = HVAC_MODE_INVERTED["manual"]
        else:
            _LOGGER.warning("Unsupported HVAC mode: %s", hvac_mode)
            return
        try:
            await self._api.set_device_preset_mode(self._id, preset_value)
        except Exception as err:
            _LOGGER.exception("Failed to set HVAC mode for device %s", self._id)
            raise
        self.coordinator.update_device_preset_mode(self._id, preset_value)
        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if preset_mode not in self._attr_preset_modes:
            _LOGGER.warning("Unsupported preset mode: %s", preset_mode)
            return
        preset_value = PRESET_INVERTED[preset_mode]
        _LOGGER.debug(
            "Setting preset mode to %s (%s) for device %s",
            preset_mode,
            preset_value,
            self._id,
        )
        try:
            await self._api.set_device_preset_mode(self._id, preset_value)
        except Exception as err:
            _LOGGER.exception(
                "Failed to set preset mode %s (%s) for device %s",
                preset_mode,
                preset_value,
                self._id,
            )
            raise
        self.coordinator.update_device_preset_mode(self._id, preset_value)
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Request latest data from coordinator."""
        await self.coordinator.async_request_refresh()
