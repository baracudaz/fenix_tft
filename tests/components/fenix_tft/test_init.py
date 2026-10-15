"""Tests for fenix_tft __init__ hooks (migrate entry, remove device)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD, UnitOfEnergy
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
from pyfenixcontrol import (
    EnergyMetric,
    EnergyPeriod,
    FenixControlAuthError,
    FenixControlConnectionError,
    HolidayMode,
)

from custom_components import fenix_tft
from custom_components.fenix_tft import (
    async_migrate_entry,
    async_remove_config_entry_device,
)
from custom_components.fenix_tft.const import DOMAIN
from custom_components.fenix_tft.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import MOCK_DEVICE_ID, MOCK_INSTALLATION_ID


def _metric(start: str, value: float) -> EnergyMetric:
    """Return an energy bucket as parsed by pyfenixcontrol."""
    return EnergyMetric.from_api({"startDateOfMetric": start, "sum": value})


def _get_energy_entity_id(hass) -> str:
    """Return the Fenix daily energy sensor entity id."""
    for state in hass.states.async_all("sensor"):
        if state.entity_id.endswith("daily_energy_consumption"):
            return state.entity_id

    msg = "No Fenix daily energy sensor found"
    raise AssertionError(msg)


async def test_async_migrate_entry_current_version(
    hass, mock_config_entry, mock_client
):
    """Return True when the config entry is already at the current version."""
    mock_config_entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, mock_config_entry)

    assert result is True


async def test_async_migrate_entry_future_version(hass, mock_client):
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
    device_entry = device_registry.async_get_device_by_identifier(
        (DOMAIN, MOCK_DEVICE_ID), mock_config_entry.entry_id
    )
    assert device_entry is not None

    result = await async_remove_config_entry_device(
        hass, mock_config_entry, device_entry
    )

    assert result is False


async def test_async_remove_config_entry_device_stale_device(
    hass, mock_config_entry, mock_client
):
    """Return True when the device is no longer in coordinator data."""
    mock_client.get_devices.return_value = []
    mock_config_entry.add_to_hass(hass)
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
    hass, setup_integration, mock_client
):
    """Prepending older history should rebase later cumulative statistics."""
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
                _metric("2025-02-01T00:00:00+00:00", 10.0),
                _metric("2025-02-02T00:00:00+00:00", 5.0),
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

    assert fetch_history.await_args.args[5] == 28
    recorder.async_adjust_statistics.assert_called_once_with(
        "fenix_tft:home_living_room_daily_energy_consumption_history",
        import_end,
        15.0,
        UnitOfEnergy.WATT_HOUR,
    )


async def test_import_historical_statistics_without_existing_stats_skips_rebase(
    hass, setup_integration, mock_client
):
    """Initial history imports should not shift future sums when none exist."""
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
                _metric("2025-02-01T00:00:00+00:00", 10.0),
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

    assert fetch_history.await_args.args[5] == 28
    recorder.async_adjust_statistics.assert_not_called()


async def test_import_historical_statistics_import_all_uses_yearly_batches(
    hass, setup_integration, mock_client
):
    """Import-all should walk backwards in yearly batches and rebase older prepends."""
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
                    _metric("2025-01-01T00:00:00+00:00", 20.0),
                    _metric("2025-02-01T00:00:00+00:00", 30.0),
                ],
                [_metric("2024-02-01T00:00:00+00:00", 8.0)],
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
    api.get_room_energy.return_value = []

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
            start_date,
            end_date,
            365,
            "Bedroom",
            aggregation_reference_end_date=reference_end_date,
        )

    assert result == []
    api.get_room_energy.assert_awaited_once_with(
        "installation-id",
        "room-id",
        start_date,
        end_date,
        EnergyPeriod.YEAR,
    )


async def test_async_remove_config_entry_device_no_runtime_data(
    hass, mock_config_entry, mock_client
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


def _get_climate_entity_id(hass) -> str:
    """Return the Fenix climate entity id."""
    return hass.states.async_entity_ids("climate")[0]


async def test_set_holiday_schedule_calls_client(hass, setup_integration, mock_client):
    """The set_holiday_schedule service passes local datetimes and mode on."""
    with patch("custom_components.fenix_tft.asyncio.sleep", return_value=None):
        await hass.services.async_call(
            DOMAIN,
            "set_holiday_schedule",
            {
                "entity_id": _get_climate_entity_id(hass),
                "start_date": "2026-12-20 08:00:00",
                "end_date": "2026-12-27 18:00:00",
                "mode": "reduce",
            },
            blocking=True,
        )

    installation_id, start, end, mode = mock_client.set_holiday_schedule.call_args.args
    assert installation_id == MOCK_INSTALLATION_ID
    assert (start.day, start.hour, end.day, end.hour) == (20, 8, 27, 18)
    assert mode is HolidayMode.REDUCE


async def test_cancel_holiday_schedule_calls_client(
    hass, setup_integration, mock_client
):
    """The cancel_holiday_schedule service cancels the device's installation."""
    with patch("custom_components.fenix_tft.asyncio.sleep", return_value=None):
        await hass.services.async_call(
            DOMAIN,
            "cancel_holiday_schedule",
            {"entity_id": _get_climate_entity_id(hass)},
            blocking=True,
        )

    mock_client.cancel_holiday_schedule.assert_awaited_once_with(MOCK_INSTALLATION_ID)


async def test_holiday_service_maps_library_error(hass, setup_integration, mock_client):
    """A library error surfaces as HomeAssistantError."""
    mock_client.cancel_holiday_schedule.side_effect = FenixControlConnectionError("x")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "cancel_holiday_schedule",
            {"entity_id": _get_climate_entity_id(hass)},
            blocking=True,
        )


async def test_daily_energy_sensor_state(hass, setup_integration):
    """The daily energy sensor shows today's summed consumption."""
    state = hass.states.get(_get_energy_entity_id(hass))

    assert state is not None
    assert float(state.state) == pytest.approx(200.5)


async def test_diagnostics(hass, setup_integration):
    """Diagnostics list the devices and redact the credentials."""
    diag = await async_get_config_entry_diagnostics(hass, setup_integration)

    assert diag["entry"][CONF_PASSWORD] == "**REDACTED**"
    assert diag["coordinator"]["device_count"] == 1
    device = diag["devices"][0]
    assert device["id"] == MOCK_DEVICE_ID
    assert device["current_temp"] == pytest.approx(19.2)
    assert device["daily_energy"] == pytest.approx(200.5)


def _reauth_flows(hass) -> list:
    """Return reauth flows in progress for the integration."""
    return [
        flow
        for flow in hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        if flow["context"]["source"] == "reauth"
    ]


async def test_holiday_service_auth_error_starts_reauth(
    hass, setup_integration, mock_client
):
    """An auth error in a holiday service asks the user to reauthenticate."""
    mock_client.cancel_holiday_schedule.side_effect = FenixControlAuthError("expired")

    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            "cancel_holiday_schedule",
            {"entity_id": _get_climate_entity_id(hass)},
            blocking=True,
        )
    await hass.async_block_till_done()

    assert exc_info.value.translation_key == "auth_failed"
    assert len(_reauth_flows(hass)) == 1


async def test_fetch_historical_energy_data_propagates_auth_error():
    """An auth error stops the chunk loop instead of being counted as a gap."""
    client = AsyncMock()
    client.get_room_energy.side_effect = FenixControlAuthError("expired")
    end_date = dt_util.parse_datetime("2026-05-10T00:00:00+00:00")
    assert end_date is not None

    with (
        patch("custom_components.fenix_tft.asyncio.sleep", return_value=None),
        pytest.raises(FenixControlAuthError),
    ):
        await fenix_tft._fetch_historical_energy_data(
            client,
            "installation-id",
            "room-id",
            end_date - dt_util.dt.timedelta(days=60),
            end_date,
            60,
            "Bedroom",
        )

    client.get_room_energy.assert_awaited_once()


async def test_import_historical_statistics_auth_error_starts_reauth(
    hass, setup_integration, mock_client
):
    """The import service reports an auth failure and starts reauthentication."""
    mock_client.get_room_energy.side_effect = FenixControlAuthError("expired")

    with (
        patch(
            "custom_components.fenix_tft.get_first_statistic_time",
            return_value=None,
        ),
        patch("custom_components.fenix_tft.asyncio.sleep", return_value=None),
        pytest.raises(HomeAssistantError) as exc_info,
    ):
        await hass.services.async_call(
            DOMAIN,
            "import_historical_statistics",
            {"energy_entity": _get_energy_entity_id(hass), "days_back": 7},
            blocking=True,
        )
    await hass.async_block_till_done()

    assert exc_info.value.translation_key == "auth_failed"
    assert len(_reauth_flows(hass)) == 1
