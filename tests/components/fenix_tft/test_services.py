"""Test Fenix TFT services."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fenix_tft.const import ATTR_DAYS_BACK, ATTR_ENERGY_ENTITY
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError


async def test_set_holiday_schedule(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_fenix_api: MagicMock,
) -> None:
    """Test setting holiday schedule."""
    await hass.services.async_call(
        "fenix_tft",
        "set_holiday_schedule",
        {
            "entity_id": "climate.victory_port_spalna",
            "start_date": "2025-12-10",
            "end_date": "2025-12-20",
            "mode": "reduce",
        },
        blocking=True,
    )

    # Verify API was called
    mock_fenix_api.set_holiday_schedule.assert_called_once()


async def test_set_holiday_schedule_invalid_dates(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_fenix_api: MagicMock,
) -> None:
    """Test setting holiday schedule with invalid dates."""
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "fenix_tft",
            "set_holiday_schedule",
            {
                "entity_id": "climate.victory_port_spalna",
                "start_date": "2025-12-20",
                "end_date": "2025-12-10",  # End before start
                "mode": "reduce",
            },
            blocking=True,
        )


async def test_cancel_holiday_schedule(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_fenix_api: MagicMock,
) -> None:
    """Test canceling holiday schedule."""
    await hass.services.async_call(
        "fenix_tft",
        "cancel_holiday_schedule",
        {
            "entity_id": "climate.victory_port_spalna",
        },
        blocking=True,
    )

    # Verify API was called
    mock_fenix_api.cancel_holiday_schedule.assert_called_once()


async def test_import_historical_statistics(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_fenix_api: MagicMock,
) -> None:
    """Test importing historical statistics."""
    from unittest.mock import patch

    # Mock the statistics helper to avoid needing recorder setup
    with (
        patch(
            "custom_components.fenix_tft.get_first_statistic_time",
            return_value=None,
        ),
        patch(
            "custom_components.fenix_tft.get_last_statistic_sum",
            return_value=0.0,
        ),
        patch(
            "custom_components.fenix_tft.async_add_external_statistics",
        ),
    ):
        # Mock historical energy data as async API response
        mock_fenix_api.get_room_historical_energy = AsyncMock(
            return_value=[
                {
                    "startDateOfMetric": "2024-01-01T00:00:00+00:00",
                    "sum": 1.5,
                }
            ]
        )

        await hass.services.async_call(
            "fenix_tft",
            "import_historical_statistics",
            {
                ATTR_ENERGY_ENTITY: "sensor.victory_port_spalna_daily_energy_consumption",
                ATTR_DAYS_BACK: 7,
            },
            blocking=True,
        )

        # Verify API was called to fetch energy data
        mock_fenix_api.get_room_historical_energy.assert_called()
