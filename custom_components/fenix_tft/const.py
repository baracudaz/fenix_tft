"""Constants for the fenix_tft custom component."""

from collections.abc import Sequence
from typing import Final

DOMAIN: Final[str] = "fenix_tft"
PLATFORMS: Final[Sequence[str]] = ("climate",)

# Default scan interval (seconds)
SCAN_INTERVAL: Final[int] = 60
# Optimistic update duration (seconds)
OPTIMISTIC_UPDATE_DURATION: Final[int] = 10

# Preset mode constants
PRESET_MODE_OFF: Final[int] = 0
PRESET_MODE_MANUAL: Final[int] = 1
PRESET_MODE_PROGRAM: Final[int] = 2

# HVAC action constants
HVAC_ACTION_IDLE: Final[int] = 0
HVAC_ACTION_HEATING: Final[int] = 1
HVAC_ACTION_OFF: Final[int] = 2

# Adaptive polling configuration (not user-configurable per HA guidelines)
FAST_POLL_SECONDS: Final[int] = 30  # Active heating / startup period
SLOW_POLL_SECONDS: Final[int] = 180  # All devices idle/off
STARTUP_FAST_PERIOD: Final[int] = 300  # Seconds after coordinator init
ERROR_BACKOFF_SECONDS: Final[int] = 300  # Temporary backoff interval after errors

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

# Valid preset mode values
# 0=off, 1=holidays, 2=program, 4=defrost, 5=boost, 6=manual
VALID_PRESET_MODES: Final[set[int]] = {0, 1, 2, 4, 5, 6}
