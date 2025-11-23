"""Statistics utilities for Fenix TFT integration."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

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

from .const import DOMAIN

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
            "Found existing cumulative sum for %s: %s",
            statistic_id,
            result,
        )
    return result


async def get_first_statistic_time(
    hass: HomeAssistant, statistic_id: str
) -> datetime | None:
    """
    Get the timestamp of the first (oldest) recorded statistic.

    Args:
        hass: Home Assistant instance
        statistic_id: The statistic ID to query

    Returns:
        Datetime of the first statistic, or None if no statistics exist

    """

    def _get_first_stat() -> datetime | None:
        try:
            # Get the first statistic by querying from epoch
            start_time = datetime(1970, 1, 1, tzinfo=dt_util.UTC)
            end_time = dt_util.now()

            stats = statistics_during_period(
                hass,
                start_time,
                end_time,
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
            "Found first statistic for %s at %s",
            statistic_id,
            result,
        )
    return result


def create_energy_statistic_metadata(
    entity_id: str, entity_name: str
) -> StatisticMetaData:
    """
    Create StatisticMetaData for energy consumption.

    Args:
        entity_id: Entity ID for the energy sensor
        entity_name: Human-readable entity name

    Returns:
        StatisticMetaData configured for energy statistics

    """
    # For external statistics, use domain:unique_id format
    # Extract the unique part from entity_id (after the domain.)
    entity_unique_part = entity_id.split(".", 1)[1] if "." in entity_id else entity_id
    return StatisticMetaData(
        has_mean=False,
        has_sum=True,
        mean_type=StatisticMeanType.NONE,
        name=f"{entity_name} History",
        source=DOMAIN,
        statistic_id=f"{DOMAIN}:{entity_unique_part}_imported",
        unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        unit_class="energy",
    )


def convert_energy_api_data_to_statistics(
    api_data: list[dict[str, Any]], starting_sum: float = 0.0
) -> list[StatisticData]:
    """
    Convert API energy data to StatisticData objects.

    Args:
        api_data: List of energy consumption metrics from API
        starting_sum: Starting cumulative sum value (from existing statistics)

    Returns:
        List of StatisticData objects with cumulative sum

    """
    statistics = []
    cumulative_sum = starting_sum

    # Sort data by timestamp to ensure chronological order
    sorted_data = sorted(
        api_data,
        key=lambda x: x.get("startDateOfMetric", ""),
    )

    for item in sorted_data:
        if not isinstance(item, dict):
            continue

        # Parse start date
        start_date_str = item.get("startDateOfMetric")
        if not start_date_str:
            _LOGGER.warning("Missing startDateOfMetric in energy data: %s", item)
            continue

        try:
            # Parse ISO format date string and ensure UTC timezone
            start_dt = dt_util.parse_datetime(start_date_str)
            if start_dt is None:
                _LOGGER.warning("Failed to parse date: %s", start_date_str)
                continue

            # Ensure UTC timezone
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=dt_util.UTC)
            else:
                start_dt = start_dt.astimezone(dt_util.UTC)

            # Get energy value (in Wh) for this period
            period_value = item.get("sum", 0)

            # Add to cumulative sum (use absolute value to ensure positive)
            cumulative_sum += abs(period_value)

            _LOGGER.debug(
                "Energy data point: time=%s, period=%s, cumulative=%s",
                start_dt,
                period_value,
                cumulative_sum,
            )

            statistics.append(
                StatisticData(
                    start=start_dt,
                    state=cumulative_sum,  # State also shows cumulative for energy
                    sum=cumulative_sum,  # Cumulative total
                )
            )
        except (ValueError, TypeError) as err:
            _LOGGER.warning("Error processing energy data item %s: %s", item, err)
            continue

    return statistics
