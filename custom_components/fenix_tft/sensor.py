"""Platform for Fenix TFT sensor entities."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfTemperature
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util

from .const import (
    HOLIDAY_MODE_DISPLAY_NAMES,
    HOLIDAY_MODE_NONE,
    HVAC_ACTION_HEATING,
    HVAC_ACTION_IDLE,
    PRESET_MODE_DISPLAY_NAMES,
    PRESET_MODE_HOLIDAYS,
)
from .entity import FenixTFTEntity
from .helpers import parse_holiday_end

if TYPE_CHECKING:
    from datetime import datetime

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import FenixTFTConfigEntry
    from .coordinator import FenixTFTCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    _: HomeAssistant,
    entry: FenixTFTConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Fenix TFT sensor entities from a config entry."""
    data = entry.runtime_data
    coordinator = data["coordinator"]

    entities = []

    # Create sensors for each device in specific order
    for dev in coordinator.data:
        device_id = dev["id"]

        # Regular sensors (in display order)
        # 1. Daily Energy Consumption (Enabled)
        if dev.get("room_id") is not None and dev.get("installation_id") is not None:
            entities.append(FenixEnergyConsumptionSensor(coordinator, device_id))

        # 2. HVAC state (Enabled)
        if dev.get("hvac_action") is not None:
            entities.append(FenixHvacStateSensor(coordinator, device_id))

        # 3. Preset mode (Enabled)
        if dev.get("preset_mode") is not None:
            entities.append(FenixPresetModeSensor(coordinator, device_id))

        # 4-6. Holiday sensors (Disabled)
        entities.extend(
            (
                FenixHolidayModeSensor(coordinator, device_id),
                FenixHolidayUntilSensor(coordinator, device_id),
                FenixHolidayTargetTempSensor(coordinator, device_id),
            )
        )

        # 7. Ambient temperature (Disabled)
        if dev.get("current_temp") is not None:
            entities.append(FenixAmbientTempSensor(coordinator, device_id))

        # 8. Target temperature (Disabled)
        if dev.get("target_temp") is not None:
            entities.append(FenixTargetTempSensor(coordinator, device_id))

        # 9. Temperature difference (Disabled)
        if dev.get("target_temp") is not None and dev.get("current_temp") is not None:
            entities.append(FenixTempDifferenceSensor(coordinator, device_id))

        # 10. Floor temperature (Disabled)
        if dev.get("floor_temp") is not None:
            entities.append(FenixFloorTempSensor(coordinator, device_id))

        # 11. Floor-air difference (Disabled)
        if dev.get("floor_temp") is not None and dev.get("current_temp") is not None:
            entities.append(FenixFloorAirDifferenceSensor(coordinator, device_id))

        # Diagnostic sensors
        entities.append(FenixConnectivitySensor(coordinator, device_id))

    if entities:
        async_add_entities(entities)


class FenixFloorTempSensor(FenixTFTEntity, SensorEntity):
    """Representation of a Fenix TFT floor temperature sensor."""

    _attr_translation_key = "floor_temperature"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: FenixTFTCoordinator, device_id: str) -> None:
        """Initialize a Fenix TFT floor temperature sensor."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_floor_temperature"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Requires coordinator connection and device data with floor_temp
        dev = self._device
        return (
            super().available and dev is not None and dev.get("floor_temp") is not None
        )

    @property
    def native_value(self) -> float | None:
        """Return the current floor temperature."""
        dev = self._device
        return dev.get("floor_temp") if dev else None


class FenixAmbientTempSensor(FenixTFTEntity, SensorEntity):
    """Representation of a Fenix TFT ambient/air temperature sensor."""

    _attr_translation_key = "ambient_temperature"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: FenixTFTCoordinator, device_id: str) -> None:
        """Initialize a Fenix TFT ambient temperature sensor."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_ambient_temperature"

    @property
    def native_value(self) -> float | None:
        """Return the current ambient/air temperature."""
        dev = self._device
        return dev.get("current_temp") if dev else None


class FenixTargetTempSensor(FenixTFTEntity, SensorEntity):
    """Representation of a Fenix TFT target temperature sensor."""

    _attr_translation_key = "target_temperature"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: FenixTFTCoordinator, device_id: str) -> None:
        """Initialize a Fenix TFT target temperature sensor."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_target_temperature"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        dev = self._device
        return (
            super().available and dev is not None and dev.get("target_temp") is not None
        )

    @property
    def native_value(self) -> float | None:
        """Return the target temperature."""
        dev = self._device
        return dev.get("target_temp") if dev else None


class FenixTempDifferenceSensor(FenixTFTEntity, SensorEntity):
    """Representation of a Fenix TFT temperature difference sensor."""

    _attr_translation_key = "temperature_difference"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: FenixTFTCoordinator, device_id: str) -> None:
        """Initialize a Fenix TFT temperature difference sensor."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_temperature_difference"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        dev = self._device
        return (
            super().available
            and dev is not None
            and dev.get("target_temp") is not None
            and dev.get("current_temp") is not None
        )

    @property
    def native_value(self) -> float | None:
        """Return the temperature difference (target - current)."""
        dev = self._device
        if not dev:
            return None

        target = dev.get("target_temp")
        current = dev.get("current_temp")

        if target is not None and current is not None:
            return round(target - current, 1)
        return None


class FenixHvacStateSensor(FenixTFTEntity, SensorEntity):
    """Representation of a Fenix TFT HVAC state sensor."""

    _attr_translation_key = "hvac_state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options: ClassVar[list[str]] = ["idle", "heating", "off"]

    def __init__(self, coordinator: FenixTFTCoordinator, device_id: str) -> None:
        """Initialize a Fenix TFT HVAC state sensor."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_hvac_state"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        dev = self._device
        return (
            super().available and dev is not None and dev.get("hvac_action") is not None
        )

    @property
    def native_value(self) -> str | None:
        """Return the HVAC state."""
        dev = self._device
        if not dev:
            return None

        hvac_action = dev.get("hvac_action")

        # Map numeric HVAC action to string state
        if hvac_action == HVAC_ACTION_HEATING:
            return "heating"
        return "idle" if hvac_action == HVAC_ACTION_IDLE else "off"


class FenixPresetModeSensor(FenixTFTEntity, SensorEntity):
    """Representation of a Fenix TFT preset mode sensor."""

    _attr_translation_key = "preset_mode"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options: ClassVar[list[str]] = [
        "off",
        "holidays",
        "program",
        "defrost",
        "boost",
        "manual",
    ]

    def __init__(self, coordinator: FenixTFTCoordinator, device_id: str) -> None:
        """Initialize a Fenix TFT preset mode sensor."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_preset_mode"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        dev = self._device
        return (
            super().available and dev is not None and dev.get("preset_mode") is not None
        )

    @property
    def native_value(self) -> str | None:
        """Return the preset mode."""
        dev = self._device
        if not dev:
            return None

        preset_mode = dev.get("preset_mode")

        # Map numeric preset mode to display name, then to lowercase for enum
        display_name = PRESET_MODE_DISPLAY_NAMES.get(preset_mode)
        return display_name.lower() if display_name else None


class FenixFloorAirDifferenceSensor(FenixTFTEntity, SensorEntity):
    """Representation of a Fenix TFT floor-air temperature difference sensor."""

    _attr_translation_key = "floor_air_difference"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: FenixTFTCoordinator, device_id: str) -> None:
        """Initialize a Fenix TFT floor-air difference sensor."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_floor_air_difference"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        dev = self._device
        return (
            super().available
            and dev is not None
            and dev.get("floor_temp") is not None
            and dev.get("current_temp") is not None
        )

    @property
    def native_value(self) -> float | None:
        """Return the floor-air temperature difference."""
        dev = self._device
        if not dev:
            return None

        floor_temp = dev.get("floor_temp")
        current_temp = dev.get("current_temp")

        if floor_temp is not None and current_temp is not None:
            return round(floor_temp - current_temp, 1)
        return None


class FenixConnectivitySensor(FenixTFTEntity, SensorEntity):
    """Representation of a Fenix TFT connectivity sensor."""

    _attr_translation_key = "connectivity_status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: FenixTFTCoordinator, device_id: str) -> None:
        """Initialize a Fenix TFT connectivity sensor."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_connectivity_status"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available

    @property
    def native_value(self) -> str:
        """Return the connectivity status."""
        dev = self._device

        # If device data is present and coordinator is available, device is connected
        return "connected" if dev is not None and super().available else "disconnected"


class FenixEnergyConsumptionSensor(FenixTFTEntity, SensorEntity):
    """Representation of a Fenix TFT daily energy consumption sensor."""

    _attr_translation_key = "daily_energy_consumption"
    _attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: FenixTFTCoordinator, device_id: str) -> None:
        """Initialize a Fenix TFT energy consumption sensor."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_daily_energy_consumption"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        dev = self._device
        return (
            super().available
            and dev is not None
            and dev.get("room_id") is not None
            and dev.get("installation_id") is not None
        )

    @property
    def native_value(self) -> float | None:
        """Return the daily energy consumption."""
        dev = self._device
        return dev.get("daily_energy_consumption") if dev else None


class FenixHolidayModeSensor(FenixTFTEntity, SensorEntity):
    """Representation of a Fenix TFT holiday mode sensor."""

    _attr_translation_key = "holiday_mode"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: FenixTFTCoordinator, device_id: str) -> None:
        """Initialize a Fenix TFT holiday mode sensor."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_holiday_mode"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self._device is not None

    @property
    def native_value(self) -> str:
        """Return the currently active holiday mode.
        
        This uses H4 (active_holiday_mode) which is the real-time indicator
        of whether a holiday is actively being applied to the device.
        """
        dev = self._device
        none_display = HOLIDAY_MODE_DISPLAY_NAMES.get(HOLIDAY_MODE_NONE, "None")

        if not dev:
            return none_display

        # API field mapping:
        # active_holiday_mode = H4 field (PRIMARY indicator)
        #   (0=None/not active, 1=Off, 2=Reduce/Eco, 5=Defrost, 8=Sunday)
        # preset_mode = Cm field
        #   (0=Off, 1=Holidays, 2=Program, 4=Defrost, 5=Boost, 6=Manual)
        # holiday_mode = H3[0] field (configured mode, not necessarily active)
        #   (0=None, 1=Off, 2=Reduce/Eco, 5=Defrost, 8=Sunday)
        # hvac_action = Hs field - dual purpose:
        #   - Normal mode: heating status (0=idle, 1=heating, 2=off)
        #   - Holiday mode (Cm=1): holiday mode type
        #     (1=Off, 2=Reduce, 5=Defrost, 8=Sunday)
        # Note: H1 (holiday_start) is unreliable - updated dynamically by API
        active_holiday_mode = dev.get("active_holiday_mode")
        holiday_end = dev.get("holiday_end")
        preset_mode = dev.get("preset_mode")

        _LOGGER.debug(
            "Holiday mode sensor %s: active_holiday_mode=%s, preset_mode=%s, "
            "holiday_end=%s",
            self._device_id,
            active_holiday_mode,
            preset_mode,
            holiday_end,
        )

        # Validate holiday mode is actually active (H4 != 0)
        if not active_holiday_mode or active_holiday_mode == HOLIDAY_MODE_NONE:
            _LOGGER.debug(
                "Device %s has no active holiday: active_holiday_mode=%s",
                self._device_id,
                active_holiday_mode,
            )
            return none_display

        # Check if holiday end date is valid
        end_dt = parse_holiday_end(holiday_end)
        if not end_dt or dt_util.now() > end_dt:
            _LOGGER.debug(
                "Device %s holiday schedule invalid or expired: end=%s",
                self._device_id,
                holiday_end,
            )
            return none_display

        # Return the active mode from H4
        mode_name = HOLIDAY_MODE_DISPLAY_NAMES.get(
            active_holiday_mode, f"Unknown ({active_holiday_mode})"
        )
        _LOGGER.debug(
            "Device %s has active holiday mode: %s (%s)",
            self._device_id,
            mode_name,
            active_holiday_mode,
        )
        return mode_name

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        dev = self._device
        if not dev:
            return {}

        active_holiday_mode = dev.get("active_holiday_mode")
        holiday_end = dev.get("holiday_end")
        holiday_target_temp = dev.get("holiday_target_temp")

        # Check if holiday is currently active based on active_holiday_mode (H4)
        # and end date
        is_active = False
        time_remaining = None

        if (
            active_holiday_mode
            and active_holiday_mode != HOLIDAY_MODE_NONE
            and (end_dt := parse_holiday_end(holiday_end))
        ):
            now = dt_util.now()
            is_active = now <= end_dt

            if is_active:
                remaining = end_dt - now
                days = remaining.days
                hours, remainder = divmod(remaining.seconds, 3600)
                minutes = remainder // 60

                if days > 0:
                    time_remaining = f"{days}d {hours}h"
                elif hours > 0:
                    time_remaining = f"{hours}h {minutes}m"
                else:
                    time_remaining = f"{minutes}m"

        attributes = {
            "is_active": is_active,
            "time_remaining": time_remaining,
        }

        # Add holiday target temperature when in holiday mode
        if is_active and holiday_target_temp is not None:
            attributes["target_temperature"] = holiday_target_temp

        return attributes


class FenixHolidayUntilSensor(FenixTFTEntity, SensorEntity):
    """Representation of a Fenix TFT holiday schedule until sensor."""

    _attr_translation_key = "holiday_schedule_until"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: FenixTFTCoordinator, device_id: str) -> None:
        """Initialize a Fenix TFT holiday schedule until sensor."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_holiday_schedule_until"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self._device is not None

    @property
    def native_value(self) -> datetime | None:
        """Return the holiday end datetime if actively in holiday mode.
        
        Uses H4 (active_holiday_mode) to check if holiday is truly active,
        not just configured.
        """
        dev = self._device
        if not dev:
            return None

        active_holiday_mode = dev.get("active_holiday_mode")
        holiday_end = dev.get("holiday_end")

        _LOGGER.debug(
            "Holiday until sensor %s: active_holiday_mode=%s, end=%s",
            self._device_id,
            active_holiday_mode,
            holiday_end,
        )

        # Check if holiday mode is actually active (H4 != 0)
        if not active_holiday_mode or active_holiday_mode == HOLIDAY_MODE_NONE:
            _LOGGER.debug(
                "Device %s has no active holiday: active_holiday_mode=%s",
                self._device_id,
                active_holiday_mode,
            )
            return None

        # Parse and return end date
        end_dt = parse_holiday_end(holiday_end)
        if not end_dt:
            _LOGGER.debug("Device %s has no valid holiday end date", self._device_id)
            return None

        _LOGGER.debug("Device %s holiday ends: %s", self._device_id, end_dt)
        return end_dt

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        dev = self._device
        if not dev:
            return {}

        active_holiday_mode = dev.get("active_holiday_mode")
        holiday_end = dev.get("holiday_end")

        # Only show mode if holiday is currently active (H4 != 0)
        if not active_holiday_mode or active_holiday_mode == HOLIDAY_MODE_NONE:
            return {}

        # Check if holiday has expired
        end_dt = parse_holiday_end(holiday_end)
        if not end_dt or dt_util.now() > end_dt:
            return {}

        # Return the active mode from H4
        mode_display = HOLIDAY_MODE_DISPLAY_NAMES.get(
            active_holiday_mode, f"Unknown ({active_holiday_mode})"
        )

        return {"mode": mode_display}


class FenixHolidayTargetTempSensor(FenixTFTEntity, SensorEntity):
    """Representation of a Fenix TFT holiday target temperature sensor."""

    _attr_translation_key = "holiday_target_temperature"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: FenixTFTCoordinator, device_id: str) -> None:
        """Initialize a Fenix TFT holiday target temperature sensor."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_holiday_target_temperature"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self._device is not None

    @property
    def native_value(self) -> float | None:
        """Return the holiday target temperature if actively in holiday mode.
        
        Uses H4 (active_holiday_mode) to check if holiday is truly active.
        """
        dev = self._device
        if not dev:
            return None

        active_holiday_mode = dev.get("active_holiday_mode")
        holiday_target_temp = dev.get("holiday_target_temp")

        # Only show value when holiday is actually active (H4 != 0)
        return (
            None
            if not active_holiday_mode or active_holiday_mode == HOLIDAY_MODE_NONE
            else holiday_target_temp
        )
