"""
Shared fixtures for Fenix TFT tests.

Mock data is anonymized from real API captures in artifacts/api-captures/.
Temperatures decoded from API format: At=665/10=66.5°F→19.2°C, Ma=725/10=72.5°F→22.5°C,
bo=680/10=68.0°F→20.0°C.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.util import dt as dt_util
from pyfenixcontrol import Device, EnergyMetric, Installation, Room
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fenix_tft.const import DOMAIN, PRESET_MODE_MANUAL

if TYPE_CHECKING:
    from collections.abc import Generator

MOCK_USERNAME = "user@example.com"
MOCK_PASSWORD = "test_password_123"
MOCK_INSTALLATION_ID = "AABB1122CCDD"
MOCK_DEVICE_ID = "AA11BB22CC00"
MOCK_DEVICE_ID_2 = "AA11BB22CC01"
MOCK_ROOM_ID = "aaaabbbb-cccc-dddd-eeee-111122223333"

MOCK_INSTALLATION = Installation(
    id=MOCK_INSTALLATION_ID,
    name="Home",
    rooms=(Room(id=MOCK_ROOM_ID, name="Living Room", device_ids=(MOCK_DEVICE_ID,)),),
    raw={},
)

# Device state as returned by pyfenixcontrol, based on real capture data.
MOCK_DEVICE = Device(
    id=MOCK_DEVICE_ID,
    name="Living Room",
    installation_id=MOCK_INSTALLATION_ID,
    installation_name="Home",
    room_id=MOCK_ROOM_ID,
    software_version="v01.06.01",
    model="P07542",
    target_temperature=22.5,  # Ma: 725/10=72.5°F → 22.5°C
    room_temperature=19.2,  # At: 665/10=66.5°F → 19.2°C
    floor_temperature=20.0,  # bo: 680/10=68.0°F → 20.0°C
    holiday_target_temperature=22.5,
    preset_mode=PRESET_MODE_MANUAL,  # Cm: 6
    hvac_state=1,  # Hs: heating status
    holiday_start="01/01/1970 00:00:00",
    holiday_end="01/01/1970 00:00:00",
    holiday_mode=0,
    active_holiday_mode=0,  # H4: no active holiday
    raw={},
)

MOCK_DEVICE_HOLIDAY = dataclasses.replace(
    MOCK_DEVICE,
    active_holiday_mode=2,  # H4: Reduce/Eco mode active
    holiday_start="01/12/2025 12:00:00",
    holiday_end="10/12/2025 12:00:00",
)

# Values of the room's hourly energy buckets stamped today (Wh)
MOCK_ENERGY_VALUES = (120.0, 80.5)


def energy_bucket(start: datetime, value: float) -> EnergyMetric:
    """Return an hourly energy bucket stamped at ``start``."""
    return EnergyMetric(start=start, value=value, processed_value=value, raw={})


def mock_energy(*_: object) -> list[EnergyMetric]:
    """Return today's buckets, stamped 01:00 and 02:00 local time."""
    midnight = dt_util.start_of_local_day()
    return [
        energy_bucket(dt_util.as_utc(midnight + timedelta(hours=hour)), value)
        for hour, value in enumerate(MOCK_ENERGY_VALUES, start=1)
    ]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Auto-enable custom integrations for all tests in this module."""
    return enable_custom_integrations


@pytest.fixture(autouse=True)
def mock_import_recent_energy() -> Generator[AsyncMock]:
    """Don't write energy statistics; the recorder is not set up in tests."""
    with patch(
        "custom_components.fenix_tft.coordinator.async_import_recent_energy"
    ) as mock:
        yield mock


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
def mock_client() -> Generator[AsyncMock]:
    """Return a mock FenixControlClient that the integration will use."""
    mock = AsyncMock()
    mock.get_installations.return_value = [MOCK_INSTALLATION]
    mock.get_devices.return_value = [MOCK_DEVICE]
    mock.trigger_installation_update.return_value = None
    mock.get_room_energy.side_effect = mock_energy
    mock.set_target_temperature.return_value = None
    mock.set_preset_mode.return_value = None
    mock.set_holiday_schedule.return_value = None
    mock.cancel_holiday_schedule.return_value = None
    with (
        patch("custom_components.fenix_tft.PasswordAuth"),
        patch("custom_components.fenix_tft.FenixControlClient", return_value=mock),
    ):
        yield mock


@pytest.fixture
async def setup_integration(hass, mock_config_entry, mock_client):
    """Set up the Fenix TFT integration with a mock client."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
