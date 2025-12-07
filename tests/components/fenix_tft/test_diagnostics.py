"""Test Fenix TFT diagnostics."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant

from custom_components.fenix_tft.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test diagnostics data."""
    # Call diagnostics function directly
    data = await async_get_config_entry_diagnostics(hass, init_integration)

    # Check that sensitive data is redacted
    assert "email" not in str(data).lower() or "**REDACTED**" in str(data)
    assert "password" not in str(data).lower() or "**REDACTED**" in str(data)

    # Check that useful diagnostic info is present
    assert "devices" in data
    assert "coordinator" in data
    assert "entry" in data
    assert "api" in data

    # Verify structure
    assert isinstance(data["devices"], list)
    assert len(data["devices"]) == 2  # Two devices in fixture
