"""Helper functions for Fenix TFT integration (holiday parsing & state)."""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.util import dt as dt_util

from .const import (
    HOLIDAY_DATE_FORMAT,
    HOLIDAY_EPOCH_DATE,
)

_LOGGER = logging.getLogger(__name__)


def parse_holiday_end(end_str: str | None) -> datetime | None:
    """
    Parse holiday end date string into timezone-aware datetime.

    Returns None if date is missing, epoch placeholder, or cannot be parsed.
    Note: We only parse the end date (H2) as the start date (H1) is unreliable
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
