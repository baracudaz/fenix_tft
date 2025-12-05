"""Helper functions for Fenix TFT integration (holiday parsing & state)."""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.util import dt as dt_util

from .const import (
    HOLIDAY_DATE_FORMAT,
    HOLIDAY_EPOCH_DATE,
    PRESET_MODE_HOLIDAYS,
)

_LOGGER = logging.getLogger(__name__)


def parse_holiday_end(end_str: str | None) -> datetime | None:
    """
    Parse holiday end date string into timezone-aware datetime.

    Args:
        end_str: Holiday end date string in format DD/MM/YYYY HH:MM:SS

    Returns:
        Timezone-aware datetime if valid, None otherwise

    Note:
        We only parse the end date (H2) as the start date (H1) is unreliable
        and gets updated dynamically by the Fenix API.

    """
    if not end_str or end_str == HOLIDAY_EPOCH_DATE:
        return None

    tz = dt_util.get_default_time_zone()
    try:
        return datetime.strptime(end_str, HOLIDAY_DATE_FORMAT).replace(tzinfo=tz)
    except (ValueError, TypeError) as err:
        _LOGGER.debug("Failed to parse holiday end date (%s): %s", end_str, err)
        return None


def is_holiday_active(
    preset_mode: int,
    end_str: str | None,
    now: datetime | None = None,
) -> bool:
    """
    Determine if a holiday schedule is currently active.

    Uses preset_mode (Cm field) and end date (H2) for validation.
    The start date (H1) is not used as it's unreliable and updated
    dynamically by the API.

    Conditions:
    - preset_mode == PRESET_MODE_HOLIDAYS (Cm=1)
    - end date exists and parses successfully
    - current time <= end date (haven't passed the end yet)
    """
    if preset_mode != PRESET_MODE_HOLIDAYS:
        return False

    if not (end_dt := parse_holiday_end(end_str)):
        return False

    return (now or dt_util.now()) <= end_dt
