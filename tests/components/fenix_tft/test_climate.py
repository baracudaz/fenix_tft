"""Tests for the Fenix TFT climate entity."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.fenix_tft.const import (
    PRESET_MODE_MANUAL,
    PRESET_MODE_OFF,
    PRESET_MODE_PROGRAM,
    TEMP_MAX,
    TEMP_MIN,
)

from .conftest import MOCK_DEVICE_HOLIDAY, MOCK_DEVICE_ID


def _get_climate_entity_id(hass):
    """Get the climate entity ID for our mock device (installation + room name)."""
    # Entity ID is generated from device name: "{installation} {room}"
    # With MOCK_DEVICE: "Home Living Room" → "climate.home_living_room"
    states = hass.states.async_all("climate")
    assert states, "No climate entities found"
    return states[0].entity_id


async def test_climate_entity_created(hass, setup_integration):
    """Test that the climate entity is created after integration setup."""
    states = hass.states.async_all("climate")
    assert len(states) == 1


async def test_climate_initial_state(hass, setup_integration):
    """Test the climate entity's initial state matches mock device data."""
    entity_id = _get_climate_entity_id(hass)
    state = hass.states.get(entity_id)

    assert state is not None
    assert state.state == HVACMode.HEAT  # PRESET_MODE_MANUAL → HVAC HEAT
    assert float(state.attributes["current_temperature"]) == pytest.approx(19.2)
    assert float(state.attributes["temperature"]) == pytest.approx(22.5)
    # MANUAL mode does not map to a HA preset; preset_mode is None for HVAC modes
    assert state.attributes["preset_mode"] is None


async def test_climate_min_max_temp(hass, setup_integration):
    """Test min/max temperature attributes match constants."""
    entity_id = _get_climate_entity_id(hass)
    state = hass.states.get(entity_id)

    assert float(state.attributes["min_temp"]) == TEMP_MIN
    assert float(state.attributes["max_temp"]) == TEMP_MAX
    assert float(state.attributes["target_temp_step"]) == 0.5


async def test_set_temperature_calls_api(hass, setup_integration, mock_api):
    """Test that setting temperature calls the API."""
    entity_id = _get_climate_entity_id(hass)

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": entity_id, ATTR_TEMPERATURE: 21.0},
        blocking=True,
    )

    mock_api.set_device_temperature.assert_called_once_with(MOCK_DEVICE_ID, 21.0)


async def test_set_temperature_below_min_raises(hass, setup_integration):
    """Test that setting temperature below TEMP_MIN raises ServiceValidationError."""
    entity_id = _get_climate_entity_id(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": entity_id, ATTR_TEMPERATURE: TEMP_MIN - 1},
            blocking=True,
        )


async def test_set_temperature_above_max_raises(hass, setup_integration):
    """Test that setting temperature above TEMP_MAX raises ServiceValidationError."""
    entity_id = _get_climate_entity_id(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": entity_id, ATTR_TEMPERATURE: TEMP_MAX + 1},
            blocking=True,
        )


async def test_set_temperature_holiday_locked(hass, mock_config_entry, mock_api):
    """Test that setting temperature is blocked when holiday mode is active."""
    mock_api.fetch_devices_with_energy_data.return_value = [MOCK_DEVICE_HOLIDAY]
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.fenix_tft.FenixTFTApi", return_value=mock_api):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _get_climate_entity_id(hass)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": entity_id, ATTR_TEMPERATURE: 21.0},
            blocking=True,
        )

    mock_api.set_device_temperature.assert_not_called()


async def test_set_hvac_mode_off(hass, setup_integration, mock_api):
    """Test HVAC mode OFF calls set_device_preset_mode with PRESET_MODE_OFF."""
    entity_id = _get_climate_entity_id(hass)

    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": entity_id, "hvac_mode": HVACMode.OFF},
        blocking=True,
    )

    mock_api.set_device_preset_mode.assert_called_once_with(
        MOCK_DEVICE_ID, PRESET_MODE_OFF
    )


async def test_set_hvac_mode_heat(hass, setup_integration, mock_api):
    """Test HVAC mode HEAT calls set_device_preset_mode with PRESET_MODE_MANUAL."""
    entity_id = _get_climate_entity_id(hass)

    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": entity_id, "hvac_mode": HVACMode.HEAT},
        blocking=True,
    )

    mock_api.set_device_preset_mode.assert_called_once_with(
        MOCK_DEVICE_ID, PRESET_MODE_MANUAL
    )


async def test_set_preset_mode(hass, setup_integration, mock_api):
    """Test that setting a preset mode calls the API with the correct int code."""
    entity_id = _get_climate_entity_id(hass)

    await hass.services.async_call(
        "climate",
        "set_preset_mode",
        {"entity_id": entity_id, "preset_mode": "program"},
        blocking=True,
    )

    mock_api.set_device_preset_mode.assert_called_once_with(
        MOCK_DEVICE_ID, PRESET_MODE_PROGRAM
    )


async def test_set_preset_mode_holiday_locked(hass, mock_config_entry, mock_api):
    """Test that changing preset mode is blocked when holiday mode is active."""
    mock_api.fetch_devices_with_energy_data.return_value = [MOCK_DEVICE_HOLIDAY]
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.fenix_tft.FenixTFTApi", return_value=mock_api):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _get_climate_entity_id(hass)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "climate",
            "set_preset_mode",
            {"entity_id": entity_id, "preset_mode": "manual"},
            blocking=True,
        )

    mock_api.set_device_preset_mode.assert_not_called()
