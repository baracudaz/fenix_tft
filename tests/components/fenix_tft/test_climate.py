"""Test the Fenix TFT climate platform."""

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    ATTR_TEMPERATURE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


async def test_climate_entity_created(
    hass: HomeAssistant, init_integration, entity_registry: er.EntityRegistry
) -> None:
    """Test that climate entities are created."""
    entries = er.async_entries_for_config_entry(
        entity_registry, init_integration.entry_id
    )

    climate_entries = [e for e in entries if e.domain == CLIMATE_DOMAIN]
    assert len(climate_entries) == 2

    # Check entity IDs match our real fixtures
    entity_ids = {e.entity_id for e in climate_entries}
    assert "climate.test_installation_test_device_1" in entity_ids
    assert "climate.test_installation_test_device_2" in entity_ids


async def test_climate_entity_attributes(hass: HomeAssistant, init_integration) -> None:
    """Test climate entity attributes."""
    state = hass.states.get("climate.test_installation_test_device_1")

    assert state is not None
    assert state.state == HVACMode.HEAT
    assert state.attributes["temperature"] == 21.0
    assert state.attributes["current_temperature"] == 20.4
    assert state.attributes["min_temp"] == 7.0
    assert state.attributes["max_temp"] == 35.0


async def test_set_temperature(
    hass: HomeAssistant, init_integration, mock_fenix_api
) -> None:
    """Test setting temperature."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {
            ATTR_ENTITY_ID: "climate.test_installation_test_device_1",
            ATTR_TEMPERATURE: 22.0,
        },
        blocking=True,
    )

    # Verify API was called with correct temperature
    mock_fenix_api.set_device_temperature.assert_called_once_with("TESTDEV0001", 22.0)


async def test_set_hvac_mode(
    hass: HomeAssistant, init_integration, mock_fenix_api
) -> None:
    """Test setting HVAC mode."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {
            ATTR_ENTITY_ID: "climate.test_installation_test_device_1",
            ATTR_HVAC_MODE: HVACMode.OFF,
        },
        blocking=True,
    )

    # Verify API was called with correct preset mode (OFF = preset_mode 0)
    mock_fenix_api.set_device_preset_mode.assert_called_once_with("TESTDEV0001", 0)


async def test_set_preset_mode(
    hass: HomeAssistant, init_integration, mock_fenix_api
) -> None:
    """Test setting preset mode."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {
            ATTR_ENTITY_ID: "climate.test_installation_test_device_1",
            ATTR_PRESET_MODE: "boost",
        },
        blocking=True,
    )

    # Verify API was called with correct preset mode (boost = preset_mode 5)
    mock_fenix_api.set_device_preset_mode.assert_called_once_with("TESTDEV0001", 5)


async def test_holiday_mode_locks_controls(
    hass: HomeAssistant, init_integration
) -> None:
    """Test climate entity when NOT in holiday mode."""
    state = hass.states.get("climate.test_installation_test_device_1")

    # Device is NOT in holiday mode in our fixture (preset_mode=6 is manual)
    assert state is not None
    assert state.attributes["preset_mode"] is None  # Not in holiday preset
