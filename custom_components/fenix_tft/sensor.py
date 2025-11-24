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
    HOLIDAY_EPOCH_DATE,
    HOLIDAY_MODE_DISPLAY_NAMES,
    HOLIDAY_MODE_NAMES,
    HOLIDAY_MODE_NONE,
    HVAC_ACTION_HEATING,
    HVAC_ACTION_IDLE,
)
from .entity import FenixTFTEntity
from .helpers import is_holiday_active, parse_holiday_window

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

    # Create sensors for each device
    for dev in coordinator.data:
        device_id = dev["id"]

        # Create floor temperature sensor if floor_temp data is available
        if dev.get("floor_temp") is not None:
            entities.append(FenixFloorTempSensor(coordinator, device_id))

        # Create ambient temperature sensor if current_temp data is available
        if dev.get("current_temp") is not None:
            entities.append(FenixAmbientTempSensor(coordinator, device_id))

        # Create target temperature sensor if target_temp data is available
        if dev.get("target_temp") is not None:
            entities.append(FenixTargetTempSensor(coordinator, device_id))

        # Create temperature difference sensor if both temps are available
        if dev.get("target_temp") is not None and dev.get("current_temp") is not None:
            entities.append(FenixTempDifferenceSensor(coordinator, device_id))

        # Create floor-air difference sensor if both temps are available
        if dev.get("floor_temp") is not None and dev.get("current_temp") is not None:
            entities.append(FenixFloorAirDifferenceSensor(coordinator, device_id))

        # Create HVAC state sensor if hvac_action data is available
        if dev.get("hvac_action") is not None:
            entities.append(FenixHvacStateSensor(coordinator, device_id))

        # Create connectivity sensor (always available)
        entities.append(FenixConnectivitySensor(coordinator, device_id))

        # Create energy consumption sensor if room_id and installation_id are available
        if dev.get("room_id") is not None and dev.get("installation_id") is not None:
            entities.append(FenixEnergyConsumptionSensor(coordinator, device_id))

        # Create holiday sensors (always available)
        entities.extend(
            (
                FenixHolidayModeSensor(coordinator, device_id),
                FenixHolidayUntilSensor(coordinator, device_id),
            )
        )

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
    _attr_entity_category = EntityCategory.DIAGNOSTIC
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
    _attr_entity_category = EntityCategory.DIAGNOSTIC
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
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
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


class FenixFloorAirDifferenceSensor(FenixTFTEntity, SensorEntity):
    """Representation of a Fenix TFT floor-air temperature difference sensor."""

    _attr_translation_key = "floor_air_difference"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
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
        """Return the holiday schedule mode."""
        dev = self._device
        if not dev:
            return HOLIDAY_MODE_DISPLAY_NAMES.get(HOLIDAY_MODE_NONE, "None")

        holiday_start = dev.get("holiday_start")
        holiday_end = dev.get("holiday_end")
        holiday_mode = dev.get("holiday_mode", HOLIDAY_MODE_NONE)

        # No holiday if mode is 0 or dates are epoch
        if (
            holiday_mode == HOLIDAY_MODE_NONE
            or HOLIDAY_EPOCH_DATE in (holiday_start, holiday_end)
            or not holiday_start
            or not holiday_end
        ):
            return HOLIDAY_MODE_DISPLAY_NAMES.get(HOLIDAY_MODE_NONE, "None")

        # Return the user-facing holiday mode display name
        return HOLIDAY_MODE_DISPLAY_NAMES.get(holiday_mode, "None")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        dev = self._device
        if not dev:
            return {}

        holiday_start = dev.get("holiday_start")
        holiday_end = dev.get("holiday_end")
        holiday_mode = dev.get("holiday_mode", HOLIDAY_MODE_NONE)

        # Active state and time remaining
        is_active = is_holiday_active(holiday_mode, holiday_start, holiday_end)
        time_remaining = None
        if is_active:
            _start_dt, end_dt = parse_holiday_window(holiday_start, holiday_end)
            if end_dt:
                now = dt_util.now()
                remaining = end_dt - now
                days = remaining.days
                hours, remainder = divmod(remaining.seconds, 3600)
                minutes = remainder // 60
                if days > 0:
                    time_remaining = f"{days}d {hours}h {minutes}m"
                elif hours > 0:
                    time_remaining = f"{hours}h {minutes}m"
                else:
                    time_remaining = f"{minutes}m"

        return {
            "start_time": holiday_start,
            "end_time": holiday_end,
            "mode_code": holiday_mode,
            "mode_internal": HOLIDAY_MODE_NAMES.get(holiday_mode, "none"),
            "mode_display": HOLIDAY_MODE_DISPLAY_NAMES.get(holiday_mode, "None"),
            "is_active": is_active,
            "time_remaining": time_remaining,
        }


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
        """Return the holiday end datetime."""
        dev = self._device
        if not dev:
            return None

        holiday_start = dev.get("holiday_start")
        holiday_end = dev.get("holiday_end")
        holiday_mode = dev.get("holiday_mode", HOLIDAY_MODE_NONE)

        # No holiday if mode is 0 or date is epoch
        if (
            holiday_mode == HOLIDAY_MODE_NONE
            or holiday_end == HOLIDAY_EPOCH_DATE
            or not holiday_end
        ):
            return None

        _start_dt, end_dt = parse_holiday_window(holiday_start, holiday_end)
        return end_dt

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        dev = self._device
        if not dev:
            return {}

        holiday_start = dev.get("holiday_start")
        holiday_mode = dev.get("holiday_mode", HOLIDAY_MODE_NONE)

        return {
            "start_time": holiday_start,
            "mode": HOLIDAY_MODE_DISPLAY_NAMES.get(holiday_mode, "None"),
            "mode_code": holiday_mode,
            "mode_internal": HOLIDAY_MODE_NAMES.get(holiday_mode, "none"),
        }
