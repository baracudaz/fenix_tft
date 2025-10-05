"""Constants for the fenix_tft custom component."""

DOMAIN = "fenix_tft"
PLATFORMS = ["climate"]
SCAN_INTERVAL = 60  # seconds

# API endpoints
API_BASE = "https://vs2-fe-apim-prod.azure-api.net"
API_IDENTITY = "https://vs2-fe-identity-prod.azurewebsites.net"

# OAuth2 configuration (PKCE, no client secret needed)
CLIENT_ID = "b1760b2e-69f1-4e89-8233-5840a9accdf8"
REDIRECT_URI = "fenix://callback"
SCOPES = (
    "profile openid offline_access "
    "DataProcessing.Read DataProcessing.Write "
    "Device.Read Device.Write "
    "Installation.Read Installation.Write "
    "IOTManagement.Read IOTManagement.Write "
    "Room.Read Room.Write "
    "TermOfUse.Read TermOfUse.Write"
)

# HTTP codes
HTTP_OK = 200
HTTP_REDIRECT = 302

# Valid preset mode values
# 0=off, 1=holidays, 2=program, 4=defrost, 5=boost, 6=manual
VALID_PRESET_MODES = {0, 1, 2, 4, 5, 6}
