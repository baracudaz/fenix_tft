"""Tests for fenix_tft __init__ hooks (migrate entry, remove device)."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.helpers import device_registry as dr

from custom_components.fenix_tft import (
    async_migrate_entry,
    async_remove_config_entry_device,
)
from custom_components.fenix_tft.const import DOMAIN

from .conftest import MOCK_DEVICE_ID


async def test_async_migrate_entry_current_version(hass, mock_config_entry, mock_api):
    """Return True when the config entry is already at the current version."""
    mock_config_entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, mock_config_entry)

    assert result is True


async def test_async_migrate_entry_future_version(hass, mock_api):
    """Return False for an unknown future version that cannot be migrated."""
    from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from .conftest import MOCK_PASSWORD, MOCK_USERNAME

    future_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: MOCK_PASSWORD},
        unique_id=MOCK_USERNAME,
        version=999,
        minor_version=1,
    )
    future_entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, future_entry)

    assert result is False


async def test_async_remove_config_entry_device_active_device(
    hass, mock_config_entry, setup_integration
):
    """Return False when the device is still present in coordinator data."""
    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get_device(
        identifiers={(DOMAIN, MOCK_DEVICE_ID)}
    )
    assert device_entry is not None

    result = await async_remove_config_entry_device(
        hass, mock_config_entry, device_entry
    )

    assert result is False


async def test_async_remove_config_entry_device_stale_device(
    hass, mock_config_entry, mock_api
):
    """Return True when the device is no longer in coordinator data."""
    mock_api.fetch_devices_with_energy_data.return_value = []
    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.fenix_tft.FenixTFTApi", return_value=mock_api):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    device_registry = dr.async_get(hass)
    # Manually register a stale device not present in coordinator data
    device_entry = device_registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={(DOMAIN, "STALE_DEVICE_ID")},
        name="Stale Device",
    )

    result = await async_remove_config_entry_device(
        hass, mock_config_entry, device_entry
    )

    assert result is True


async def test_async_remove_config_entry_device_no_runtime_data(
    hass, mock_config_entry, mock_api
):
    """Return True (allow removal) when runtime_data is not populated."""
    mock_config_entry.add_to_hass(hass)
    # Do not set up the integration — runtime_data will be absent

    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={(DOMAIN, MOCK_DEVICE_ID)},
        name="Test Device",
    )

    result = await async_remove_config_entry_device(
        hass, mock_config_entry, device_entry
    )

    assert result is True
