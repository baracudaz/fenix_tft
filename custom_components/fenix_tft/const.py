"""Constants for the fenix_tft custom component."""

from collections.abc import Sequence
from typing import Final

DOMAIN: Final[str] = "fenix_tft"
PLATFORMS: Final[Sequence[str]] = ("climate", "sensor")

POLLING_INTERVAL: Final[int] = 300  # Polling interval in seconds
OPTIMISTIC_UPDATE_DURATION: Final[int] = 10  # Optimistic update duration (seconds)

# API endpoints
API_BASE: Final[str] = "https://vs2-fe-apim-prod.azure-api.net"
API_IDENTITY: Final[str] = "https://vs2-fe-identity-prod.azurewebsites.net"

# OAuth2 configuration (PKCE, no client secret needed)
CLIENT_ID: Final[str] = "b1760b2e-69f1-4e89-8233-5840a9accdf8"
REDIRECT_URI: Final[str] = "fenix://callback"
SCOPES: Final[str] = (
    "profile openid offline_access "
    "DataProcessing.Read DataProcessing.Write "
    "Device.Read Device.Write "
    "Installation.Read Installation.Write "
    "IOTManagement.Read IOTManagement.Write "
    "Room.Read Room.Write "
    "TermOfUse.Read TermOfUse.Write"
)

# HTTP codes
HTTP_OK: Final[int] = 200
HTTP_NO_CONTENT: Final[int] = 204
HTTP_REDIRECT: Final[int] = 302

# API timeout configuration
API_TIMEOUT_SECONDS: Final[int] = 10

# Preset mode constants
PRESET_MODE_OFF: Final[int] = 0
PRESET_MODE_HOLIDAYS: Final[int] = 1
PRESET_MODE_PROGRAM: Final[int] = 2
PRESET_MODE_DEFROST: Final[int] = 4
PRESET_MODE_BOOST: Final[int] = 5
PRESET_MODE_MANUAL: Final[int] = 6

# Valid preset mode values (derived from constants)
VALID_PRESET_MODES: Final[set[int]] = {
    PRESET_MODE_OFF,
    PRESET_MODE_HOLIDAYS,
    PRESET_MODE_PROGRAM,
    PRESET_MODE_DEFROST,
    PRESET_MODE_BOOST,
    PRESET_MODE_MANUAL,
}

# Preset mode display names (user-facing)
PRESET_MODE_DISPLAY_NAMES: Final[dict[int, str]] = {
    PRESET_MODE_OFF: "Off",
    PRESET_MODE_HOLIDAYS: "Holidays",
    PRESET_MODE_PROGRAM: "Program",
    PRESET_MODE_DEFROST: "Defrost",
    PRESET_MODE_BOOST: "Boost",
    PRESET_MODE_MANUAL: "Manual",
}

# HVAC action constants
HVAC_ACTION_IDLE: Final[int] = 0
HVAC_ACTION_HEATING: Final[int] = 1
HVAC_ACTION_OFF: Final[int] = 2

# Holiday mode constants (H3 field values)
HOLIDAY_MODE_NONE: Final[int] = 0  # No holiday mode / default
HOLIDAY_MODE_OFF: Final[int] = 1  # Heating off during holiday
HOLIDAY_MODE_REDUCE: Final[int] = 2  # Eco/reduced mode during holiday
HOLIDAY_MODE_DEFROST: Final[int] = 5  # Defrost mode during holiday
HOLIDAY_MODE_SUNDAY: Final[int] = 8  # Sunday schedule during holiday

# Holiday mode names mapping
HOLIDAY_MODE_NAMES: Final[dict[int, str]] = {
    HOLIDAY_MODE_NONE: "none",
    HOLIDAY_MODE_OFF: "off",
    HOLIDAY_MODE_REDUCE: "reduce",
    HOLIDAY_MODE_DEFROST: "defrost",
    HOLIDAY_MODE_SUNDAY: "sunday",
}

# Holiday mode display names (user-facing)
HOLIDAY_MODE_DISPLAY_NAMES: Final[dict[int, str]] = {
    HOLIDAY_MODE_NONE: "None",
    HOLIDAY_MODE_OFF: "Off",
    HOLIDAY_MODE_REDUCE: "Reduce (Eco)",
    HOLIDAY_MODE_DEFROST: "Defrost",
    HOLIDAY_MODE_SUNDAY: "Sunday Schedule",
}

# Valid holiday modes for service (inverted, excluding "none")
# Maps string names to integer codes for API calls
VALID_HOLIDAY_MODES: Final[dict[str, int]] = {
    name: code for code, name in HOLIDAY_MODE_NAMES.items() if code != HOLIDAY_MODE_NONE
}

# Unix epoch date used to indicate no holiday schedule
# Note: This is an invalid date string used as a sentinel value by the API
# It is only compared as a string before parsing, never actually parsed
HOLIDAY_EPOCH_DATE: Final[str] = "00/00/1970 00:00:00"

# Holiday date string format used by API (H1/H2 values)
HOLIDAY_DATE_FORMAT: Final[str] = "%d/%m/%Y %H:%M:%S"

# Exception message for holiday mode lock
HOLIDAY_LOCKED_MSG: Final[str] = "Holiday schedule active; controls locked"

# Delay (seconds) to wait after holiday schedule changes before refresh
HOLIDAY_PROPAGATION_DELAY: Final[int] = 5

# Service names
SERVICE_SET_HOLIDAY_SCHEDULE: Final[str] = "set_holiday_schedule"
SERVICE_CANCEL_HOLIDAY_SCHEDULE: Final[str] = "cancel_holiday_schedule"
SERVICE_IMPORT_HISTORICAL_STATISTICS: Final[str] = "import_historical_statistics"

# Service field names
ATTR_START_DATE: Final[str] = "start_date"
ATTR_END_DATE: Final[str] = "end_date"
ATTR_MODE: Final[str] = "mode"
ATTR_DAYS_BACK: Final[str] = "days_back"
ATTR_ENERGY_ENTITY: Final[str] = "energy_entity"

# Historical data import configuration
API_RATE_LIMIT_DELAY: Final[int] = 1  # Delay in seconds between API calls
