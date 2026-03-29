"""
Shared fixtures for Fenix TFT tests.

Mock data is anonymized from real API captures in artifacts/api-captures/.
Original data: installation 3E76B4F7126D, device 30C6F7E491A0 (Obývačka/Living Room).
Temperatures decoded from API format: At=665/10=66.5°F→19.2°C, Ma=725/10=72.5°F→22.5°C,
bo=680/10=68.0°F→20.0°C.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fenix_tft.const import DOMAIN, PRESET_MODE_MANUAL

MOCK_USERNAME = "user@example.com"
MOCK_PASSWORD = "test_password_123"
MOCK_INSTALLATION_ID = "AABB1122CCDD"
MOCK_DEVICE_ID = "AA11BB22CC00"
MOCK_DEVICE_ID_2 = "AA11BB22CC01"
MOCK_ROOM_ID = "aaaabbbb-cccc-dddd-eeee-111122223333"

# Coordinator-format device dict (post-API-processing), based on real capture data.
MOCK_DEVICE = {
    "id": MOCK_DEVICE_ID,
    "name": "Living Room",
    "software": "v01.06.01",
    "type": "P07542",
    "installation": "Home",
    "installation_id": MOCK_INSTALLATION_ID,
    "room_id": MOCK_ROOM_ID,
    "target_temp": 22.5,  # Ma: 725/10=72.5°F → 22.5°C
    "current_temp": 19.2,  # At: 665/10=66.5°F → 19.2°C
    "floor_temp": 20.0,  # bo: 680/10=68.0°F → 20.0°C
    "hvac_action": 1,  # Hs: heating status
    "preset_mode": PRESET_MODE_MANUAL,  # Cm: 6
    "holiday_start": "01/01/1970 00:00:00",
    "holiday_end": "01/01/1970 00:00:00",
    "holiday_mode": 0,
    "active_holiday_mode": 0,  # H4: no active holiday
    "holiday_target_temp": 22.5,
}

MOCK_DEVICE_HOLIDAY = {
    **MOCK_DEVICE,
    "active_holiday_mode": 2,  # H4: Reduce/Eco mode active
    "holiday_start": "01/12/2025 12:00:00",
    "holiday_end": "10/12/2025 12:00:00",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Auto-enable custom integrations for all tests in this module."""
    return enable_custom_integrations


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mock config entry for Fenix TFT."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: MOCK_PASSWORD},
        unique_id=MOCK_USERNAME,
        title=MOCK_USERNAME,
        version=1,
        minor_version=1,
    )


@pytest.fixture
def mock_api() -> AsyncMock:
    """Return a mock FenixTFTApi instance."""
    mock = AsyncMock()
    mock.login.return_value = True
    mock.fetch_devices_with_energy_data.return_value = [MOCK_DEVICE]
    mock.set_device_temperature.return_value = None
    mock.set_device_preset_mode.return_value = None
    mock.set_holiday_schedule.return_value = None
    mock.cancel_holiday_schedule.return_value = None
    return mock


@pytest.fixture
async def setup_integration(hass, mock_config_entry, mock_api):
    """Set up the Fenix TFT integration with a mock API."""
    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.fenix_tft.FenixTFTApi", return_value=mock_api):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    return mock_config_entry
