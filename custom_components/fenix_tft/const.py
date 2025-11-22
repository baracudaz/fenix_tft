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
HTTP_REDIRECT: Final[int] = 302

# API timeout configuration
API_TIMEOUT_SECONDS: Final[int] = 10

# Valid preset mode values
# 0=off, 1=holidays, 2=program, 4=defrost, 5=boost, 6=manual
VALID_PRESET_MODES: Final[set[int]] = {0, 1, 2, 4, 5, 6}

# Preset mode constants
PRESET_MODE_OFF: Final[int] = 0
PRESET_MODE_MANUAL: Final[int] = 1
PRESET_MODE_PROGRAM: Final[int] = 2

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

# Unix epoch date used to indicate no holiday schedule
HOLIDAY_EPOCH_DATE: Final[str] = "01/01/1970 00:00:00"
