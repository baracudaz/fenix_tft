"""Tests for the Fenix TFT coordinator."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.fenix_tft.api import FenixTFTApiError, FenixTFTAuthError
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

from .conftest import MOCK_DEVICE, MOCK_DEVICE_ID


@pytest.fixture
def coordinator(hass, mock_config_entry, mock_api):
    """Return a FenixTFTCoordinator with a mock API."""
    mock_config_entry.add_to_hass(hass)
    return FenixTFTCoordinator(
        hass=hass,
        api=mock_api,
        config_entry=mock_config_entry,
    )


async def test_coordinator_update_success(coordinator, mock_api):
    """Test a successful data fetch populates coordinator.data."""
    coordinator.data = await coordinator._async_update_data()

    assert coordinator.data is not None
    assert len(coordinator.data) == 1
    assert coordinator.data[0]["id"] == MOCK_DEVICE_ID
    assert coordinator.data[0]["current_temp"] == pytest.approx(19.2)
    assert coordinator.data[0]["target_temp"] == pytest.approx(22.5)
    assert coordinator.data[0]["floor_temp"] == pytest.approx(20.0)


async def test_coordinator_update_api_error_raises_update_failed(coordinator, mock_api):
    """Test that an API error raises UpdateFailed."""
    mock_api.fetch_devices_with_energy_data.side_effect = FenixTFTApiError("API down")

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_update_auth_error_raises_config_entry_auth_failed(
    coordinator, mock_api
):
    """Test that a FenixTFTAuthError raises ConfigEntryAuthFailed."""
    mock_api.fetch_devices_with_energy_data.side_effect = FenixTFTAuthError(
        "Login failed"
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_coordinator_creates_repair_issue_after_consecutive_failures(
    hass, coordinator, mock_api
):
    """Test that repeated failures create a repair issue."""
    mock_api.fetch_devices_with_energy_data.side_effect = FenixTFTApiError(
        "connection error"
    )

    for _ in range(CONSECUTIVE_FAILURES_BEFORE_ISSUE):
        try:
            await coordinator._async_update_data()
        except UpdateFailed:
            pass

    issue = ir.async_get(hass).async_get_issue(DOMAIN, "coordinator_unavailable")
    assert issue is not None
    assert issue.severity == ir.IssueSeverity.WARNING


async def test_coordinator_clears_repair_issue_on_success(hass, coordinator, mock_api):
    """Test that a successful fetch after failures clears the repair issue."""
    mock_api.fetch_devices_with_energy_data.side_effect = FenixTFTApiError(
        "connection error"
    )

    # Trigger enough failures to create the repair issue
    for _ in range(CONSECUTIVE_FAILURES_BEFORE_ISSUE):
        try:
            await coordinator._async_update_data()
        except UpdateFailed:
            pass

    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, "coordinator_unavailable")
        is not None
    )

    # Now succeed
    mock_api.fetch_devices_with_energy_data.side_effect = None
    mock_api.fetch_devices_with_energy_data.return_value = [MOCK_DEVICE]
    await coordinator._async_update_data()

    assert ir.async_get(hass).async_get_issue(DOMAIN, "coordinator_unavailable") is None


async def test_coordinator_no_repair_issue_below_threshold(hass, coordinator, mock_api):
    """Test no repair issue is created below the failure threshold."""
    mock_api.fetch_devices_with_energy_data.side_effect = FenixTFTApiError("blip")

    for _ in range(CONSECUTIVE_FAILURES_BEFORE_ISSUE - 1):
        try:
            await coordinator._async_update_data()
        except UpdateFailed:
            pass

    assert ir.async_get(hass).async_get_issue(DOMAIN, "coordinator_unavailable") is None


async def test_optimistic_update_sets_preset_and_hvac_action(coordinator, mock_api):
    """Test that an optimistic update is immediately reflected in coordinator.data."""
    coordinator.data = await coordinator._async_update_data()

    coordinator.update_device_preset_mode(MOCK_DEVICE_ID, PRESET_MODE_OFF)

    device = next(d for d in coordinator.data if d["id"] == MOCK_DEVICE_ID)
    assert device["preset_mode"] == PRESET_MODE_OFF
    assert device["hvac_action"] == HVAC_ACTION_OFF


async def test_optimistic_update_predicts_heating_when_target_above_current(
    coordinator, mock_api
):
    """Test HVAC action is predicted as HEATING when target_temp > current_temp."""
    coordinator.data = await coordinator._async_update_data()

    # MOCK_DEVICE has target=22.5, current=19.2 so target > current → HEATING predicted
    coordinator.update_device_preset_mode(MOCK_DEVICE_ID, PRESET_MODE_MANUAL)

    device = next(d for d in coordinator.data if d["id"] == MOCK_DEVICE_ID)
    assert device["hvac_action"] == HVAC_ACTION_HEATING


async def test_optimistic_update_predicts_idle_when_target_below_current(
    coordinator, mock_api
):
    """Test HVAC action is predicted as IDLE when target_temp <= current_temp."""
    coordinator.data = await coordinator._async_update_data()
    # Adjust temps so target < current
    coordinator.data[0]["target_temp"] = 18.0
    coordinator.data[0]["current_temp"] = 22.0

    coordinator.update_device_preset_mode(MOCK_DEVICE_ID, PRESET_MODE_PROGRAM)

    device = next(d for d in coordinator.data if d["id"] == MOCK_DEVICE_ID)
    assert device["hvac_action"] == HVAC_ACTION_IDLE


async def test_optimistic_update_expires_on_next_refresh(coordinator, mock_api):
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
    await coordinator._async_update_data()
    assert coordinator.pending_optimistic_update_count == 0

    # Data should revert to API values
    device = next(d for d in coordinator.data if d["id"] == MOCK_DEVICE_ID)
    assert device["preset_mode"] == MOCK_DEVICE["preset_mode"]


async def test_coordinator_pending_optimistic_count(coordinator, mock_api):
    """Test the pending_optimistic_update_count property."""
    coordinator.data = await coordinator._async_update_data()
    assert coordinator.pending_optimistic_update_count == 0

    coordinator.update_device_preset_mode(MOCK_DEVICE_ID, PRESET_MODE_MANUAL)
    assert coordinator.pending_optimistic_update_count == 1
