"""Constants for the fenix_tft custom component."""

from typing import Final, Sequence, Set

DOMAIN: Final[str] = "fenix_tft"
PLATFORMS: Final[Sequence[str]] = ("climate",)
SCAN_INTERVAL: Final[int] = 60  # seconds

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
VALID_PRESET_MODES: Final[Set[int]] = {0, 1, 2, 4, 5, 6}
