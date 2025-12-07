"""Test the Fenix TFT sensor platform."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


async def test_sensor_entities_created(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that sensor entities are created."""
    entries = er.async_entries_for_config_entry(
        entity_registry, init_integration.entry_id
    )

    sensor_entries = [e for e in entries if e.domain == "sensor"]

    # Should have energy consumption sensors for each device
    assert len(sensor_entries) >= 2


async def test_energy_consumption_sensor(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test energy consumption sensor."""
    await hass.async_block_till_done()
    entries = er.async_entries_for_config_entry(
        entity_registry, init_integration.entry_id
    )
    sensor_entries = [e for e in entries if e.domain == "sensor"]
    energy_sensor_entry = next(
        (
            e
            for e in sensor_entries
            if e.unique_id == "30C6F7E493C4_daily_energy_consumption"
        ),
        None,
    )

    assert energy_sensor_entry is not None, (
        "Energy consumption sensor not found in registry"
    )
    state = hass.states.get(energy_sensor_entry.entity_id)

    assert state is not None
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfEnergy.WATT_HOUR
    assert "state_class" in state.attributes
