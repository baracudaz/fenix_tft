"""Tests for the Fenix TFT coordinator."""

from __future__ import annotations

import dataclasses
import logging

import pytest
from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import UpdateFailed
from pyfenixcontrol import (
    EnergyPeriod,
    FenixControlAuthError,
    FenixControlConnectionError,
    FenixControlResponseError,
)

from custom_components.fenix_tft.const import (
    DOMAIN,
    HVAC_ACTION_HEATING,
    HVAC_ACTION_IDLE,
    HVAC_ACTION_OFF,
    PRESET_MODE_MANUAL,
    PRESET_MODE_OFF,
    PRESET_MODE_PROGRAM,
)
from custom_components.fenix_tft.coordinator import (
    CONSECUTIVE_FAILURES_BEFORE_ISSUE,
    FenixTFTCoordinator,
)

from .conftest import (
    MOCK_DEVICE,
    MOCK_DEVICE_ID,
    MOCK_INSTALLATION,
    MOCK_INSTALLATION_ID,
    MOCK_ROOM_ID,
)


@pytest.fixture
def coordinator(hass, mock_config_entry, mock_client):
    """Return a FenixTFTCoordinator with a mock client."""
    mock_config_entry.add_to_hass(hass)
    return FenixTFTCoordinator(
        hass=hass,
        client=mock_client,
        config_entry=mock_config_entry,
    )


async def test_coordinator_update_success(coordinator, mock_client):
    """Test a successful data fetch populates coordinator.data."""
    coordinator.data = await coordinator._async_update_data()

    assert list(coordinator.data.devices) == [MOCK_DEVICE_ID]
    device = coordinator.data.devices[MOCK_DEVICE_ID]
    assert device.room_temperature == pytest.approx(19.2)
    assert device.target_temperature == pytest.approx(22.5)
    assert device.floor_temperature == pytest.approx(20.0)
    mock_client.get_devices.assert_awaited_once_with([MOCK_INSTALLATION])


async def test_coordinator_device_name_falls_back_to_room(coordinator, mock_client):
    """Test a thermostat without its own name is named after its room."""
    mock_client.get_devices.return_value = [dataclasses.replace(MOCK_DEVICE, name=None)]

    coordinator.data = await coordinator._async_update_data()

    assert coordinator.data.devices[MOCK_DEVICE_ID].name == "Living Room"


async def test_coordinator_sums_daily_energy(coordinator, mock_client):
    """Test today's energy is the sum of the room's processed hourly values."""
    data = await coordinator._async_update_data()

    assert data.daily_energy[MOCK_DEVICE_ID] == pytest.approx(200.5)
    installation_id, room_id, start, end, period = (
        mock_client.get_room_energy.call_args.args
    )
    assert (installation_id, room_id, period) == (
        MOCK_INSTALLATION_ID,
        MOCK_ROOM_ID,
        EnergyPeriod.HOUR,
    )
    assert start <= end


async def test_coordinator_no_energy_data_is_zero(coordinator, mock_client):
    """Test an empty energy response means nothing consumed yet today."""
    mock_client.get_room_energy.return_value = []

    data = await coordinator._async_update_data()

    assert data.daily_energy[MOCK_DEVICE_ID] == 0.0


async def test_coordinator_energy_error_does_not_fail_update(coordinator, mock_client):
    """Test a failed energy request yields None but keeps the device state."""
    mock_client.get_room_energy.side_effect = FenixControlResponseError("boom", 500)

    data = await coordinator._async_update_data()

    assert data.daily_energy[MOCK_DEVICE_ID] is None
    assert MOCK_DEVICE_ID in data.devices


async def test_coordinator_triggers_installation_update(coordinator, mock_client):
    """Test each installation with devices is asked to report fresh values."""
    await coordinator._async_update_data()

    mock_client.trigger_installation_update.assert_awaited_once_with(
        MOCK_INSTALLATION_ID
    )


async def test_coordinator_trigger_error_does_not_fail_update(coordinator, mock_client):
    """Test the best-effort trigger request never fails the refresh."""
    mock_client.trigger_installation_update.side_effect = FenixControlResponseError(
        "HTTP 500", 500
    )

    data = await coordinator._async_update_data()

    assert MOCK_DEVICE_ID in data.devices


@pytest.mark.parametrize(
    "method", ["get_installations", "trigger_installation_update", "get_room_energy"]
)
async def test_coordinator_auth_error_raises_config_entry_auth_failed(
    coordinator, mock_client, method, caplog
):
    """Test an auth error anywhere in the refresh starts reauthentication."""
    getattr(mock_client, method).side_effect = FenixControlAuthError("Login failed")

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()

    # Logged once as a warning, without a traceback
    records = [r for r in caplog.records if r.name.endswith("fenix_tft.coordinator")]
    assert [r.levelno for r in records if r.levelno > logging.INFO] == [logging.WARNING]
    assert all(r.exc_info is None for r in records)


@pytest.mark.parametrize(
    "error",
    [FenixControlConnectionError("down"), FenixControlResponseError("HTTP 503", 503)],
)
async def test_coordinator_update_api_error_raises_update_failed(
    coordinator, mock_client, error
):
    """Test that connection and response errors raise UpdateFailed."""
    mock_client.get_devices.side_effect = error

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_creates_repair_issue_after_consecutive_failures(
    hass, coordinator, mock_client
):
    """Test that repeated failures create a repair issue."""
    mock_client.get_installations.side_effect = FenixControlConnectionError(
        "connection error"
    )

    for _ in range(CONSECUTIVE_FAILURES_BEFORE_ISSUE):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, coordinator._unavailable_issue_id
    )
    assert issue is not None
    assert issue.severity == ir.IssueSeverity.WARNING


async def test_coordinator_clears_repair_issue_on_success(
    hass, coordinator, mock_client
):
    """Test that a successful fetch after failures clears the repair issue."""
    mock_client.get_installations.side_effect = FenixControlConnectionError(
        "connection error"
    )

    # Trigger enough failures to create the repair issue
    for _ in range(CONSECUTIVE_FAILURES_BEFORE_ISSUE):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, coordinator._unavailable_issue_id)
        is not None
    )

    # Now succeed
    mock_client.get_installations.side_effect = None
    await coordinator._async_update_data()

    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, coordinator._unavailable_issue_id)
        is None
    )


async def test_coordinator_no_repair_issue_below_threshold(
    hass, coordinator, mock_client
):
    """Test no repair issue is created below the failure threshold."""
    mock_client.get_installations.side_effect = FenixControlConnectionError("blip")

    for _ in range(CONSECUTIVE_FAILURES_BEFORE_ISSUE - 1):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, coordinator._unavailable_issue_id)
        is None
    )


async def test_optimistic_update_sets_preset_and_hvac_action(coordinator):
    """Test that an optimistic update is immediately reflected in coordinator.data."""
    coordinator.data = await coordinator._async_update_data()

    coordinator.update_device_preset_mode(MOCK_DEVICE_ID, PRESET_MODE_OFF)

    device = coordinator.data.devices[MOCK_DEVICE_ID]
    assert device.preset_mode == PRESET_MODE_OFF
    assert device.hvac_state == HVAC_ACTION_OFF


async def test_optimistic_update_predicts_heating_when_target_above_current(
    coordinator,
):
    """Test HVAC action is predicted as HEATING when target > current temp."""
    coordinator.data = await coordinator._async_update_data()

    # MOCK_DEVICE has target=22.5, current=19.2 so target > current → HEATING predicted
    coordinator.update_device_preset_mode(MOCK_DEVICE_ID, PRESET_MODE_MANUAL)

    assert coordinator.data.devices[MOCK_DEVICE_ID].hvac_state == HVAC_ACTION_HEATING


async def test_optimistic_update_predicts_idle_when_target_below_current(
    coordinator, mock_client
):
    """Test HVAC action is predicted as IDLE when target <= current temp."""
    mock_client.get_devices.return_value = [
        dataclasses.replace(MOCK_DEVICE, target_temperature=18.0, room_temperature=22.0)
    ]
    coordinator.data = await coordinator._async_update_data()

    coordinator.update_device_preset_mode(MOCK_DEVICE_ID, PRESET_MODE_PROGRAM)

    assert coordinator.data.devices[MOCK_DEVICE_ID].hvac_state == HVAC_ACTION_IDLE


async def test_optimistic_update_survives_refresh(coordinator):
    """Test a pending optimistic update is overlaid on freshly fetched data."""
    coordinator.data = await coordinator._async_update_data()
    coordinator.update_device_preset_mode(MOCK_DEVICE_ID, PRESET_MODE_OFF)

    coordinator.data = await coordinator._async_update_data()

    assert coordinator.data.devices[MOCK_DEVICE_ID].preset_mode == PRESET_MODE_OFF
    assert coordinator.pending_optimistic_update_count == 1


async def test_optimistic_update_expires_on_next_refresh(coordinator):
    """Test that an optimistic update is overwritten after it expires."""
    coordinator.data = await coordinator._async_update_data()

    coordinator.update_device_preset_mode(MOCK_DEVICE_ID, PRESET_MODE_OFF)
    assert coordinator.pending_optimistic_update_count == 1

    # Simulate expiry by backdating the timestamp
    device_id, (preset, hvac, _timestamp) = next(
        iter(coordinator._optimistic_updates.items())
    )
    coordinator._optimistic_updates[device_id] = (preset, hvac, 0.0)

    # Second refresh should clear the expired optimistic update
    coordinator.data = await coordinator._async_update_data()
    assert coordinator.pending_optimistic_update_count == 0

    # Data should revert to API values
    assert (
        coordinator.data.devices[MOCK_DEVICE_ID].preset_mode == MOCK_DEVICE.preset_mode
    )


async def test_optimistic_update_unknown_device_is_ignored(coordinator):
    """Test an optimistic update for an unknown device changes nothing."""
    coordinator.data = await coordinator._async_update_data()

    coordinator.update_device_preset_mode("UNKNOWN", PRESET_MODE_OFF)

    assert coordinator.pending_optimistic_update_count == 0


async def test_coordinator_pending_optimistic_count(coordinator):
    """Test the pending_optimistic_update_count property."""
    coordinator.data = await coordinator._async_update_data()
    assert coordinator.pending_optimistic_update_count == 0

    coordinator.update_device_preset_mode(MOCK_DEVICE_ID, PRESET_MODE_MANUAL)
    assert coordinator.pending_optimistic_update_count == 1
