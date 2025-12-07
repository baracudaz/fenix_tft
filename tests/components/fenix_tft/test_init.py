"""Test the Fenix TFT integration initialization."""

from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.fenix_tft.api import FenixTFTAuthenticationError


async def test_setup_entry_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_fenix_api: MagicMock,
) -> None:
    """Test successful setup of config entry."""
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state == ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data is not None
    # runtime_data can be either a dict or typed object depending on HA version
    if hasattr(mock_config_entry.runtime_data, "api"):
        assert mock_config_entry.runtime_data.api is mock_fenix_api
    else:
        assert mock_config_entry.runtime_data["api"] is mock_fenix_api


async def test_setup_entry_authentication_failed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_fenix_api: MagicMock,
) -> None:
    """Test setup retries on authentication error.

    When coordinator first_refresh fails with UpdateFailed (wrapping auth error),
    Home Assistant treats it as a transient error and schedules retry.
    """
    mock_config_entry.add_to_hass(hass)
    mock_fenix_api.fetch_devices_with_energy_data.side_effect = (
        FenixTFTAuthenticationError("Auth failed")
    )

    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state == ConfigEntryState.SETUP_RETRY


async def test_unload_entry(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test unloading a config entry."""
    assert init_integration.state == ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert init_integration.state == ConfigEntryState.NOT_LOADED


async def test_reload_entry(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_fenix_api: MagicMock,
) -> None:
    """Test reloading a config entry."""
    assert init_integration.state == ConfigEntryState.LOADED

    assert await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert init_integration.state == ConfigEntryState.LOADED
