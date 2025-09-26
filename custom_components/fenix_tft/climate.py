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

# HVAC mode mappings (basic operational modes)
HVAC_MODE_MAP = {
    0: "off",
    1: "manual",
    2: "auto",
}
HVAC_MODE_INVERTED = {v: k for k, v in HVAC_MODE_MAP.items()}

# Preset mode mappings (special operational modes)
PRESET_MAP = {
    2: "program",
    4: "defrost",
    5: "boost",
}
PRESET_INVERTED = {v: k for k, v in PRESET_MAP.items()}


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
    _attr_preset_modes: ClassVar[list[str]] = [
        "program",
        "defrost",
        "boost",
    ]
    _attr_temperature_unit: ClassVar[str] = UnitOfTemperature.CELSIUS
    _attr_has_entity_name: bool = True

    def __init__(self, api: Any, device_id: str, coordinator: Any) -> None:
        """Initialize the climate entity."""
        self._api = api
        self._id = device_id
        self._coordinator = coordinator
        self._attr_hvac_mode = HVACMode.HEAT

    @property
    def _device(self) -> dict[str, Any] | None:
        """Return the device dict for this entity."""
        return next((d for d in self._coordinator.data if d["id"] == self._id), None)

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
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        preset = self._get_preset_mode()
        # Return None if preset is not in our supported list
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
            # Manual mode - full temperature and preset control
            return (
                ClimateEntityFeature.TARGET_TEMPERATURE
                | ClimateEntityFeature.PRESET_MODE
            )
        # Automatic operation (or unknown)- temperature control disabled
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

        # Default for program or unknown modes
        return HVACMode.AUTO

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        await self._api.set_device_temperature(self._id, temp)
        await self._coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode by mapping to appropriate preset mode."""
        _LOGGER.debug("Setting HVAC mode to %s for device %s", hvac_mode, self._id)

        # Map HVAC modes to preset mode values
        if hvac_mode == HVACMode.OFF:
            preset_value = HVAC_MODE_INVERTED["off"]  # 0
        elif hvac_mode == HVACMode.AUTO:
            preset_value = HVAC_MODE_INVERTED["auto"]  # 2
        elif hvac_mode == HVACMode.HEAT:
            preset_value = HVAC_MODE_INVERTED["manual"]  # 1
        else:
            _LOGGER.warning("Unsupported HVAC mode: %s", hvac_mode)
            return

        try:
            await self._api.set_device_preset_mode(self._id, preset_value)
            _LOGGER.debug(
                "Successfully set preset mode to %s for device %s",
                preset_value,
                self._id,
            )

            # Optimistically update coordinator data for immediate UI response
            self._coordinator.update_device_preset_mode(self._id, preset_value)

            # Force immediate state update
            self.async_write_ha_state()

            # Note: Coordinator will automatically refresh in the background
            # and preserve our optimistic update for 10 seconds

        except Exception:
            _LOGGER.exception("Failed to set HVAC mode for device %s", self._id)
            raise

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
            _LOGGER.debug(
                "Successfully set preset mode to %s (%s) for device %s",
                preset_mode,
                preset_value,
                self._id,
            )

            # Optimistically update coordinator data for immediate UI response
            self._coordinator.update_device_preset_mode(self._id, preset_value)

            # Force immediate state update
            self.async_write_ha_state()

            # Note: Coordinator will automatically refresh in the background
            # and preserve our optimistic update for 10 seconds

        except Exception:
            _LOGGER.exception(
                "Failed to set preset mode %s (%s) for device %s",
                preset_mode,
                preset_value,
                self._id,
            )
            raise

    async def async_update(self) -> None:
        """Request latest data from coordinator."""
        await self._coordinator.async_request_refresh()
