"""Tests for fenix_tft __init__ hooks (migrate entry, remove device)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import UnitOfEnergy
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from custom_components import fenix_tft
from custom_components.fenix_tft import (
    async_migrate_entry,
    async_remove_config_entry_device,
)
from custom_components.fenix_tft.const import DOMAIN

from .conftest import MOCK_DEVICE_ID


def _get_energy_entity_id(hass) -> str:
    """Return the Fenix daily energy sensor entity id."""
    for state in hass.states.async_all("sensor"):
        if state.entity_id.endswith("daily_energy_consumption"):
            return state.entity_id

    msg = "No Fenix daily energy sensor found"
    raise AssertionError(msg)


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


async def test_import_historical_statistics_rebases_future_sums(
    hass, setup_integration, mock_api
):
    """Prepending older history should rebase later cumulative statistics."""
    mock_api.subscription_id = "subscription-123"
    energy_entity_id = _get_energy_entity_id(hass)
    import_end = dt_util.parse_datetime("2025-03-01T00:00:00+00:00")
    assert import_end is not None
    import_start = dt_util.parse_datetime("2025-02-01T00:00:00+00:00")
    assert import_start is not None
    recorder = MagicMock()

    with (
        patch(
            "custom_components.fenix_tft.get_first_statistic_time",
            return_value=import_end,
        ),
        patch(
            "custom_components.fenix_tft._calculate_import_date_range",
            return_value=(import_start, import_end, 28),
        ),
        patch(
            "custom_components.fenix_tft._fetch_historical_energy_data",
            return_value=[
                {"startDateOfMetric": "2025-02-01T00:00:00+00:00", "sum": 10.0},
                {"startDateOfMetric": "2025-02-02T00:00:00+00:00", "sum": 5.0},
            ],
        ) as fetch_history,
        patch("custom_components.fenix_tft.async_add_external_statistics"),
        patch("custom_components.fenix_tft.get_instance", return_value=recorder),
    ):
        await hass.services.async_call(
            DOMAIN,
            "import_historical_statistics",
            {
                "energy_entity": energy_entity_id,
                "days_back": 30,
            },
            blocking=True,
        )

    assert fetch_history.await_args.args[6] == 28
    recorder.async_adjust_statistics.assert_called_once_with(
        "fenix_tft:home_living_room_daily_energy_consumption_history",
        import_end,
        15.0,
        UnitOfEnergy.WATT_HOUR,
    )


async def test_import_historical_statistics_without_existing_stats_skips_rebase(
    hass, setup_integration, mock_api
):
    """Initial history imports should not shift future sums when none exist."""
    mock_api.subscription_id = "subscription-123"
    energy_entity_id = _get_energy_entity_id(hass)
    import_end = dt_util.parse_datetime("2025-03-01T00:00:00+00:00")
    assert import_end is not None
    import_start = dt_util.parse_datetime("2025-02-01T00:00:00+00:00")
    assert import_start is not None
    recorder = MagicMock()

    with (
        patch(
            "custom_components.fenix_tft.get_first_statistic_time",
            return_value=None,
        ),
        patch(
            "custom_components.fenix_tft._calculate_import_end_date",
            return_value=import_end,
        ),
        patch(
            "custom_components.fenix_tft._calculate_import_date_range",
            return_value=(import_start, import_end, 28),
        ),
        patch(
            "custom_components.fenix_tft._fetch_historical_energy_data",
            return_value=[
                {"startDateOfMetric": "2025-02-01T00:00:00+00:00", "sum": 10.0},
            ],
        ) as fetch_history,
        patch("custom_components.fenix_tft.async_add_external_statistics"),
        patch("custom_components.fenix_tft.get_instance", return_value=recorder),
    ):
        await hass.services.async_call(
            DOMAIN,
            "import_historical_statistics",
            {
                "energy_entity": energy_entity_id,
                "days_back": 30,
            },
            blocking=True,
        )

    assert fetch_history.await_args.args[6] == 28
    recorder.async_adjust_statistics.assert_not_called()


async def test_import_historical_statistics_import_all_uses_yearly_batches(
    hass, setup_integration, mock_api
):
    """Import-all should walk backwards in yearly batches and rebase older prepends."""
    mock_api.subscription_id = "subscription-123"
    energy_entity_id = _get_energy_entity_id(hass)
    full_history_end = dt_util.parse_datetime("2026-01-01T00:00:00+00:00")
    assert full_history_end is not None
    full_history_start = dt_util.parse_datetime("2024-01-01T00:00:00+00:00")
    assert full_history_start is not None
    recorder = MagicMock()

    with (
        patch(
            "custom_components.fenix_tft.get_first_statistic_time",
            return_value=None,
        ),
        patch(
            "custom_components.fenix_tft._calculate_import_end_date",
            return_value=full_history_end,
        ),
        patch(
            "custom_components.fenix_tft.FULL_HISTORY_EARLIEST_DATE",
            full_history_start,
        ),
        patch(
            "custom_components.fenix_tft._fetch_historical_energy_data",
            side_effect=[
                [
                    {
                        "startDateOfMetric": "2025-01-01T00:00:00+00:00",
                        "sum": 20.0,
                    },
                    {
                        "startDateOfMetric": "2025-02-01T00:00:00+00:00",
                        "sum": 30.0,
                    },
                ],
                [
                    {
                        "startDateOfMetric": "2024-02-01T00:00:00+00:00",
                        "sum": 8.0,
                    }
                ],
                [],
            ],
        ) as fetch_history,
        patch("custom_components.fenix_tft.async_add_external_statistics") as add_stats,
        patch("custom_components.fenix_tft.get_instance", return_value=recorder),
    ):
        await hass.services.async_call(
            DOMAIN,
            "import_historical_statistics",
            {
                "energy_entity": energy_entity_id,
                "import_all_history": True,
            },
            blocking=True,
        )

    assert fetch_history.call_count == 3
    assert add_stats.call_count == 2
    recorder.async_adjust_statistics.assert_called_once_with(
        "fenix_tft:home_living_room_daily_energy_consumption_history",
        dt_util.parse_datetime("2025-01-01T00:00:00+00:00"),
        8.0,
        UnitOfEnergy.WATT_HOUR,
    )


async def test_fetch_historical_energy_data_uses_yearly_aggregation_for_old_ranges():
    """Very old full-history batches should skip directly to yearly requests."""
    api = AsyncMock()
    api.get_room_historical_energy.return_value = []

    start_date = dt_util.parse_datetime("2000-05-15T00:00:00+00:00")
    end_date = dt_util.parse_datetime("2001-05-15T00:00:00+00:00")
    reference_end_date = dt_util.parse_datetime("2026-05-10T00:00:00+00:00")
    assert start_date is not None
    assert end_date is not None
    assert reference_end_date is not None

    with patch("custom_components.fenix_tft.asyncio.sleep", return_value=None):
        result = await fenix_tft._fetch_historical_energy_data(
            api,
            "installation-id",
            "room-id",
            "subscription-id",
            start_date,
            end_date,
            365,
            "Bedroom",
            aggregation_reference_end_date=reference_end_date,
        )

    assert result == []
    api.get_room_historical_energy.assert_awaited_once_with(
        "installation-id",
        "room-id",
        "subscription-id",
        start_date,
        end_date,
        "Year",
    )


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
