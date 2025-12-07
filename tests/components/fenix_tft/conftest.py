"""Fixtures for Fenix TFT integration tests."""

import json
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fenix_tft.const import DOMAIN

from . import MOCK_CONFIG


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return the default mocked config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test Installation",
        data=MOCK_CONFIG,
        unique_id=MOCK_CONFIG["username"],
    )


@pytest.fixture
def mock_fenix_api() -> Generator[MagicMock, None, None]:
    """Mock FenixTFTApi."""
    # Load fixture data
    fixtures_path = Path(__file__).parent / "fixtures"

    def load_json_with_comments(file_path: Path) -> list | dict:
        """Load JSON file, stripping // comments."""
        with open(file_path) as f:
            # Strip lines starting with //
            content = "\n".join(line for line in f if not line.strip().startswith("//"))
            return json.loads(content)

    devices_data = load_json_with_comments(fixtures_path / "devices.json")
    installations_data = load_json_with_comments(fixtures_path / "installations.json")
    energy_data = load_json_with_comments(fixtures_path / "energy_consumption.json")

    # Create mock instance
    mock_api = MagicMock()

    # Mock API methods
    mock_api.login = AsyncMock(return_value=True)
    mock_api.authenticate = AsyncMock()
    mock_api.subscription_id = "3E76B4F7126D"
    mock_api.get_installations = AsyncMock(return_value=installations_data)
    mock_api.get_all_devices = AsyncMock(return_value=devices_data)
    mock_api.fetch_devices_with_energy_data = AsyncMock(return_value=devices_data)
    mock_api.update_device = AsyncMock()
    mock_api.trigger_device_updates = AsyncMock()
    mock_api.get_energy_consumption = AsyncMock(return_value=energy_data)
    mock_api.set_holiday_schedule = AsyncMock()
    mock_api.cancel_holiday_schedule = AsyncMock()
    mock_api.set_device_temperature = AsyncMock()
    mock_api.set_device_preset_mode = AsyncMock()

    # Patch the API class to return our mock instance
    with patch("custom_components.fenix_tft.FenixTFTApi", return_value=mock_api):
        yield mock_api


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_fenix_api: MagicMock,
) -> MockConfigEntry:
    """Set up the Fenix TFT integration for testing."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Ensure setup succeeded
    assert result is True

    return mock_config_entry
