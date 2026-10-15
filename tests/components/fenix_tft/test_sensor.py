"""Tests for the Fenix TFT sensor platform."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING
from unittest.mock import PropertyMock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers import entity_registry as er
from pyfenixcontrol import FenixControlConnectionError, FenixControlResponseError

from custom_components.fenix_tft import sensor
from custom_components.fenix_tft.const import (
    DOMAIN,
    HOLIDAY_MODE_REDUCE,
    PRESET_MODE_DEFROST,
    PRESET_MODE_OFF,
)

from .conftest import MOCK_DEVICE, MOCK_DEVICE_HOLIDAY, MOCK_DEVICE_ID

if TYPE_CHECKING:
    from collections.abc import Generator

    from homeassistant.core import HomeAssistant

# Sensor key → unique_id suffix (the translation key)
ALL_SENSORS = (
    "daily_energy_consumption",
    "hvac_state",
    "preset_mode",
    "holiday_mode",
    "holiday_schedule_until",
    "holiday_target_temperature",
    "ambient_temperature",
    "target_temperature",
    "temperature_difference",
    "floor_temperature",
    "floor_air_difference",
    "connectivity_status",
)

# Holiday dates from the API are naive local times, so the expected instants
# below depend on the time zone; it is set explicitly by `holiday_time_zone`.
TEST_TIME_ZONE = "US/Pacific"
# MOCK_DEVICE_HOLIDAY ends 10/12/2025 12:00 local time
BEFORE_HOLIDAY_END = "2025-12-05 09:30:00-08:00"  # 5 days 2.5 h left
HOURS_BEFORE_HOLIDAY_END = "2025-12-10 09:30:00-08:00"  # 2.5 h left
MINUTES_BEFORE_HOLIDAY_END = "2025-12-10 11:45:00-08:00"  # 15 min left
AFTER_HOLIDAY_END = "2025-12-11 12:00:00-08:00"


@pytest.fixture(autouse=True)
def enable_all_entities() -> Generator[None]:
    """Enable the sensors that are disabled by default."""
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        new_callable=PropertyMock,
        return_value=True,
    ):
        yield


@pytest.fixture(autouse=True)
async def holiday_time_zone(hass: HomeAssistant) -> None:
    """Pin Home Assistant's time zone that the holiday expectations rely on."""
    await hass.config.async_set_time_zone(TEST_TIME_ZONE)


def _entity_id(hass: HomeAssistant, key: str, device_id: str = MOCK_DEVICE_ID) -> str:
    """Return the entity_id of a sensor by its unique_id."""
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{device_id}_{key}"
    )
    assert entity_id is not None, f"sensor {key} not registered"
    return entity_id


def _state(hass: HomeAssistant, key: str):
    """Return the state object of a sensor."""
    state = hass.states.get(_entity_id(hass, key))
    assert state is not None
    return state


async def _setup(hass, mock_config_entry, mock_client, *devices) -> None:
    """Set up the integration with the given device states."""
    mock_client.get_devices.return_value = list(devices)
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()


async def _refresh(hass, mock_config_entry, mock_client, *devices) -> None:
    """Return new device states on the next poll and refresh."""
    mock_client.get_devices.return_value = list(devices)
    await mock_config_entry.runtime_data["coordinator"].async_refresh()
    await hass.async_block_till_done()


async def test_all_sensors_created(hass, mock_config_entry, mock_client):
    """A device with complete data gets every sensor."""
    await _setup(hass, mock_config_entry, mock_client, MOCK_DEVICE)

    for key in ALL_SENSORS:
        _entity_id(hass, key)


async def test_sensor_values(hass, mock_config_entry, mock_client):
    """Sensor states reflect the device data."""
    await _setup(hass, mock_config_entry, mock_client, MOCK_DEVICE)

    assert float(_state(hass, "daily_energy_consumption").state) == pytest.approx(200.5)
    assert _state(hass, "hvac_state").state == "heating"
    assert _state(hass, "preset_mode").state == "manual"
    assert float(_state(hass, "ambient_temperature").state) == pytest.approx(19.2)
    assert float(_state(hass, "target_temperature").state) == pytest.approx(22.5)
    assert float(_state(hass, "temperature_difference").state) == pytest.approx(3.3)
    assert float(_state(hass, "floor_temperature").state) == pytest.approx(20.0)
    assert float(_state(hass, "floor_air_difference").state) == pytest.approx(0.8)
    assert _state(hass, "connectivity_status").state == "connected"


@pytest.mark.parametrize(
    ("hvac_state", "expected"),
    [(0, "idle"), (1, "heating"), (2, "off"), (99, "off")],
)
async def test_hvac_state_values(
    hass, mock_config_entry, mock_client, hvac_state, expected
):
    """The HVAC state sensor maps the thermostat's heating state."""
    await _setup(
        hass,
        mock_config_entry,
        mock_client,
        dataclasses.replace(MOCK_DEVICE, hvac_state=hvac_state),
    )

    assert _state(hass, "hvac_state").state == expected


@pytest.mark.parametrize(
    ("preset_mode", "expected"),
    [(PRESET_MODE_OFF, "off"), (PRESET_MODE_DEFROST, "defrost"), (3, STATE_UNKNOWN)],
)
async def test_preset_mode_values(
    hass, mock_config_entry, mock_client, preset_mode, expected
):
    """The preset mode sensor maps known modes; unknown ones have no value."""
    await _setup(
        hass,
        mock_config_entry,
        mock_client,
        dataclasses.replace(MOCK_DEVICE, preset_mode=preset_mode),
    )

    assert _state(hass, "preset_mode").state == expected


async def test_sensors_not_created_without_data(hass, mock_config_entry, mock_client):
    """Sensors whose source value is missing at setup are not created."""
    device = dataclasses.replace(
        MOCK_DEVICE,
        hvac_state=None,
        preset_mode=None,
        room_temperature=None,
        target_temperature=None,
        floor_temperature=None,
    )
    await _setup(hass, mock_config_entry, mock_client, device)

    registry = er.async_get(hass)
    missing = {
        "hvac_state",
        "preset_mode",
        "ambient_temperature",
        "target_temperature",
        "temperature_difference",
        "floor_temperature",
        "floor_air_difference",
    }
    for key in missing:
        assert (
            registry.async_get_entity_id("sensor", DOMAIN, f"{MOCK_DEVICE_ID}_{key}")
            is None
        ), key
    # Always created
    for key in set(ALL_SENSORS) - missing:
        _entity_id(hass, key)


async def test_sensors_unavailable_when_value_disappears(
    hass, mock_config_entry, mock_client
):
    """Sensors become unavailable when their source value is no longer reported."""
    await _setup(hass, mock_config_entry, mock_client, MOCK_DEVICE)

    await _refresh(
        hass,
        mock_config_entry,
        mock_client,
        dataclasses.replace(
            MOCK_DEVICE,
            hvac_state=None,
            preset_mode=None,
            room_temperature=None,
            target_temperature=None,
            floor_temperature=None,
        ),
    )

    for key in (
        "hvac_state",
        "preset_mode",
        "target_temperature",
        "temperature_difference",
        "floor_temperature",
        "floor_air_difference",
    ):
        assert _state(hass, key).state == STATE_UNAVAILABLE, key
    # The ambient sensor has no extra availability check; it just has no value
    assert _state(hass, "ambient_temperature").state == STATE_UNKNOWN
    assert _state(hass, "connectivity_status").state == "connected"


async def test_sensors_unavailable_when_device_disappears(
    hass, mock_config_entry, mock_client
):
    """A device removed from the account makes all of its sensors unavailable."""
    await _setup(hass, mock_config_entry, mock_client, MOCK_DEVICE)

    await _refresh(hass, mock_config_entry, mock_client)

    for key in ALL_SENSORS:
        assert _state(hass, key).state == STATE_UNAVAILABLE, key


async def test_sensors_unavailable_when_cloud_unreachable(
    hass, mock_config_entry, mock_client
):
    """A failed poll makes the sensors unavailable; the next success restores them."""
    await _setup(hass, mock_config_entry, mock_client, MOCK_DEVICE)

    mock_client.get_installations.side_effect = FenixControlConnectionError("down")
    await mock_config_entry.runtime_data["coordinator"].async_refresh()
    await hass.async_block_till_done()

    for key in ALL_SENSORS:
        assert _state(hass, key).state == STATE_UNAVAILABLE, key

    mock_client.get_installations.side_effect = None
    await _refresh(hass, mock_config_entry, mock_client, MOCK_DEVICE)

    assert _state(hass, "connectivity_status").state == "connected"
    assert float(_state(hass, "floor_temperature").state) == pytest.approx(20.0)


async def test_daily_energy_none_when_fetch_fails(hass, mock_config_entry, mock_client):
    """A failed energy request leaves the sensor available without a value."""
    mock_client.get_room_energy.side_effect = FenixControlResponseError("boom", 500)
    await _setup(hass, mock_config_entry, mock_client, MOCK_DEVICE)

    assert _state(hass, "daily_energy_consumption").state == STATE_UNKNOWN


async def test_daily_energy_zero_without_buckets(hass, mock_config_entry, mock_client):
    """No energy buckets yet today means 0 Wh."""
    mock_client.get_room_energy.return_value = []
    await _setup(hass, mock_config_entry, mock_client, MOCK_DEVICE)

    assert float(_state(hass, "daily_energy_consumption").state) == 0.0


async def test_holiday_sensors_without_holiday(hass, mock_config_entry, mock_client):
    """With no active holiday the holiday sensors report nothing."""
    await _setup(hass, mock_config_entry, mock_client, MOCK_DEVICE)

    holiday_mode = _state(hass, "holiday_mode")
    assert holiday_mode.state == "None"
    assert holiday_mode.attributes["is_active"] is False
    assert holiday_mode.attributes["time_remaining"] is None
    assert "target_temperature" not in holiday_mode.attributes

    until = _state(hass, "holiday_schedule_until")
    assert until.state == STATE_UNKNOWN
    assert "mode" not in until.attributes

    assert _state(hass, "holiday_target_temperature").state == STATE_UNKNOWN


@pytest.mark.parametrize(
    ("now", "time_remaining"),
    [
        (BEFORE_HOLIDAY_END, "5d 2h"),
        (HOURS_BEFORE_HOLIDAY_END, "2h 30m"),
        (MINUTES_BEFORE_HOLIDAY_END, "15m"),
    ],
)
async def test_holiday_sensors_active_holiday(  # noqa: PLR0913, PLR0917
    hass, mock_config_entry, mock_client, freezer, now, time_remaining
):
    """An active holiday shows its mode, end, remaining time and target."""
    freezer.move_to(now)
    await _setup(hass, mock_config_entry, mock_client, MOCK_DEVICE_HOLIDAY)

    holiday_mode = _state(hass, "holiday_mode")
    assert holiday_mode.state == "Reduce (Eco)"
    assert holiday_mode.attributes["is_active"] is True
    assert holiday_mode.attributes["time_remaining"] == time_remaining
    assert holiday_mode.attributes["target_temperature"] == pytest.approx(22.5)

    until = _state(hass, "holiday_schedule_until")
    assert until.state == "2025-12-10T20:00:00+00:00"
    assert until.attributes["mode"] == "Reduce (Eco)"

    assert float(_state(hass, "holiday_target_temperature").state) == pytest.approx(
        22.5
    )


async def test_holiday_sensors_expired_holiday(
    hass, mock_config_entry, mock_client, freezer
):
    """After the end date the holiday no longer counts as active."""
    freezer.move_to(AFTER_HOLIDAY_END)
    await _setup(hass, mock_config_entry, mock_client, MOCK_DEVICE_HOLIDAY)

    holiday_mode = _state(hass, "holiday_mode")
    assert holiday_mode.state == "None"
    assert holiday_mode.attributes["is_active"] is False
    assert holiday_mode.attributes["time_remaining"] is None

    until = _state(hass, "holiday_schedule_until")
    # The end date is still shown, but without an active mode
    assert until.state == "2025-12-10T20:00:00+00:00"
    assert "mode" not in until.attributes


async def test_holiday_sensors_active_without_end_date(
    hass, mock_config_entry, mock_client
):
    """An active holiday mode without a valid end date is not shown as active."""
    device = dataclasses.replace(MOCK_DEVICE_HOLIDAY, holiday_end="00/00/1970 00:00:00")
    await _setup(hass, mock_config_entry, mock_client, device)

    assert _state(hass, "holiday_mode").state == "None"
    assert _state(hass, "holiday_schedule_until").state == STATE_UNKNOWN
    assert "mode" not in _state(hass, "holiday_schedule_until").attributes
    # The holiday target follows the active mode (H4) only
    assert float(_state(hass, "holiday_target_temperature").state) == pytest.approx(
        22.5
    )


async def test_holiday_mode_unknown_code(hass, mock_config_entry, mock_client, freezer):
    """An unknown active holiday code is shown with its number."""
    freezer.move_to(BEFORE_HOLIDAY_END)
    device = dataclasses.replace(MOCK_DEVICE_HOLIDAY, active_holiday_mode=7)
    await _setup(hass, mock_config_entry, mock_client, device)

    assert _state(hass, "holiday_mode").state == "Unknown (7)"
    assert _state(hass, "holiday_schedule_until").attributes["mode"] == "Unknown (7)"


async def test_holiday_mode_without_holiday_target(
    hass, mock_config_entry, mock_client, freezer
):
    """An active holiday without a holiday target omits that attribute."""
    freezer.move_to(BEFORE_HOLIDAY_END)
    device = dataclasses.replace(
        MOCK_DEVICE_HOLIDAY,
        active_holiday_mode=HOLIDAY_MODE_REDUCE,
        holiday_target_temperature=None,
    )
    await _setup(hass, mock_config_entry, mock_client, device)

    attributes = _state(hass, "holiday_mode").attributes
    assert attributes["is_active"] is True
    assert "target_temperature" not in attributes


@pytest.mark.parametrize(
    "sensor_class",
    [
        sensor.FenixFloorTempSensor,
        sensor.FenixAmbientTempSensor,
        sensor.FenixTargetTempSensor,
        sensor.FenixTempDifferenceSensor,
        sensor.FenixHvacStateSensor,
        sensor.FenixPresetModeSensor,
        sensor.FenixFloorAirDifferenceSensor,
        sensor.FenixEnergyConsumptionSensor,
        sensor.FenixHolidayUntilSensor,
        sensor.FenixHolidayTargetTempSensor,
    ],
)
async def test_sensor_without_device_has_no_value(
    hass, setup_integration, sensor_class
):
    """A sensor whose device is not in the coordinator data has no value."""
    coordinator = setup_integration.runtime_data["coordinator"]
    entity = sensor_class(coordinator, "UNKNOWN_DEVICE")

    assert entity.available is False
    assert entity.native_value is None


async def test_holiday_and_connectivity_without_device(hass, setup_integration):
    """Holiday and connectivity sensors fall back without a device."""
    coordinator = setup_integration.runtime_data["coordinator"]

    holiday_mode = sensor.FenixHolidayModeSensor(coordinator, "UNKNOWN_DEVICE")
    assert holiday_mode.available is False
    assert holiday_mode.native_value == "None"
    assert holiday_mode.extra_state_attributes == {}

    until = sensor.FenixHolidayUntilSensor(coordinator, "UNKNOWN_DEVICE")
    assert until.extra_state_attributes == {}

    connectivity = sensor.FenixConnectivitySensor(coordinator, "UNKNOWN_DEVICE")
    assert connectivity.available is False
    assert connectivity.native_value == "disconnected"
