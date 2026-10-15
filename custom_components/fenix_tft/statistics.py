"""Statistics utilities for Fenix TFT integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from pyfenixcontrol import EnergyMetric

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def get_last_statistic_sum(hass: HomeAssistant, statistic_id: str) -> float:
    """
    Get the last cumulative sum from existing statistics.

    Args:
        hass: Home Assistant instance
        statistic_id: The statistic ID to query

    Returns:
        Last cumulative sum value, or 0.0 if no statistics exist

    """

    def _get_last_stat() -> float:
        try:
            last_stats = get_last_statistics(
                hass, 1, statistic_id, convert_units=True, units=set()
            )
            if last_stats.get(statistic_id):
                last_value = last_stats[statistic_id][0].get("sum")
                if last_value is not None:
                    return float(last_value)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Could not get last statistic for %s: %s", statistic_id, err)
        return 0.0

    result = await get_instance(hass).async_add_executor_job(_get_last_stat)
    if result > 0:
        _LOGGER.debug(
            "Retrieved last statistic sum for %s: %.2f",
            statistic_id,
            result,
        )
    else:
        _LOGGER.debug("No existing statistics found for %s", statistic_id)
    return result


async def get_first_statistic_time(
    hass: HomeAssistant, statistic_id: str
) -> datetime | None:
    """
    Get the timestamp of the first (oldest) recorded statistic.

    Uses an optimized binary search approach to avoid expensive full-history scans
    for long-lived installations. Instead of querying from 1970 to now, we start
    with a reasonable recent window (30 days) and progressively expand backwards
    until we find statistics or reach a practical limit.

    Args:
        hass: Home Assistant instance
        statistic_id: The statistic ID to query

    Returns:
        Datetime of the first statistic, or None if no statistics exist

    """

    def _get_first_stat() -> datetime | None:
        try:
            now = dt_util.now()

            # Binary search windows: start with 30 days, then 90, 180, 365,
            # 730, 1825 (5 years). This avoids scanning decades of empty data
            # for new installations
            search_windows_days = [30, 90, 180, 365, 730, 1825]

            for days_back in search_windows_days:
                start_time = now - dt_util.dt.timedelta(days=days_back)

                stats = statistics_during_period(
                    hass,
                    start_time,
                    now,
                    {statistic_id},  # Must be a set, not a list
                    "hour",
                    None,
                    {"sum"},
                )

                if stats.get(statistic_id):
                    first_stat = stats[statistic_id][0]
                    if first_time := first_stat.get("start"):
                        # Convert Unix timestamp to datetime if needed
                        if isinstance(first_time, (int, float)):
                            return dt_util.utc_from_timestamp(first_time)
                        return first_time

        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Could not get first statistic for %s: %s", statistic_id, err)
        return None

    result = await get_instance(hass).async_add_executor_job(_get_first_stat)
    if result:
        _LOGGER.debug(
            "Retrieved first statistic timestamp for %s: %s",
            statistic_id,
            result.isoformat(),
        )
    else:
        _LOGGER.debug(
            "No historical statistics found for %s",
            statistic_id,
        )
    return result


def create_energy_statistic_metadata(
    entity_id: str, entity_name: str
) -> StatisticMetaData:
    """
    Create StatisticMetaData for energy consumption.

    This creates metadata for importing statistics as external statistics,
    not interfering with the main sensor entity. The historical data will appear
    as a separate external statistic (e.g., fenix_tft:sensor.victory_port_x_history)
    that can be used in the Energy Dashboard without requiring an actual entity.

    Args:
        entity_id: Entity ID for the energy sensor (e.g., sensor.victory_port_x)
        entity_name: Human-readable entity name

    Returns:
        StatisticMetaData configured for external statistics

    """
    # Create separate statistic_id for historical data by appending _history
    # Remove the 'sensor.' prefix for cleaner external statistic names
    clean_id = entity_id.replace("sensor.", "")
    history_statistic_id = f"fenix_tft:{clean_id}_history"
    history_entity_name = f"{entity_name} (History)"

    _LOGGER.debug(
        "Created energy statistic metadata: entity_id=%s, statistic_id=%s",
        entity_id,
        history_statistic_id,
    )

    return StatisticMetaData(
        has_mean=False,
        has_sum=True,
        mean_type=StatisticMeanType.NONE,
        name=history_entity_name,
        source="fenix_tft",  # Use integration domain as source for external statistics
        statistic_id=history_statistic_id,  # External statistic ID
        unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        unit_class="energy",
    )


def convert_energy_api_data_to_statistics(
    api_data: list[EnergyMetric], starting_sum: float = 0.0
) -> list[StatisticData]:
    """
    Convert API energy data to StatisticData objects.

    Args:
        api_data: List of energy consumption metrics from API
        starting_sum: Starting cumulative sum value (from existing statistics)

    Returns:
        List of StatisticData objects with cumulative sum

    """
    _LOGGER.debug(
        "Converting %d API data point(s) to statistics: starting_sum=%.2f",
        len(api_data) if api_data else 0,
        starting_sum,
    )

    statistics = []
    cumulative_sum = starting_sum

    for metric in api_data:
        if metric.start is None:
            _LOGGER.warning("Missing startDateOfMetric in energy data: %s", metric.raw)

    # Sort data by timestamp to ensure chronological order (start is UTC)
    for metric in sorted(
        (metric for metric in api_data if metric.start is not None),
        key=lambda metric: metric.start or dt_util.utc_from_timestamp(0),
    ):
        # Energy value (in Wh) for this period; clamp negative values and log
        period_value = metric.value
        if period_value < 0:
            _LOGGER.warning(
                "Received negative energy value %s from API; "
                "clamping to 0.0 for statistics",
                period_value,
            )
            period_value = 0.0

        cumulative_sum += period_value

        _LOGGER.debug(
            "Energy data point: time=%s, period=%s, cumulative=%s",
            metric.start,
            period_value,
            cumulative_sum,
        )

        statistics.append(
            StatisticData(
                start=metric.start,
                state=cumulative_sum,  # State also shows cumulative for energy
                sum=cumulative_sum,  # Cumulative total
            )
        )

    _LOGGER.debug(
        "Converted %d data point(s) to %d statistic(s): final_sum=%.2f",
        len(api_data) if api_data else 0,
        len(statistics),
        cumulative_sum,
    )

    return statistics
