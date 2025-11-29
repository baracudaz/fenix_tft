# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Home Assistant custom integration for the FENIX TFT WiFi thermostat. It communicates with the FENIX cloud API (reverse-engineered) to provide climate control, energy monitoring, and holiday scheduling features.

**Key characteristics:**

- Cloud polling integration (no local API available)
- OAuth2 + PKCE authentication with automatic token refresh
- Multi-device/multi-room support through coordinator pattern
- Energy statistics integration with Home Assistant recorder
- Holiday schedule management at installation level

## Development Commands

### Environment Setup

```bash
# Install dependencies
scripts/setup

# Start Home Assistant development server
scripts/develop
```

### Code Quality

```bash
# Format and lint code (use this after editing code)
uv run ./scripts/lint

# Format code only
ruff format .

# Lint with auto-fix
ruff check . --fix
```

### Translations

```bash
# Update translations after adding new keys to strings.json
./scripts/translations.py
```

### Testing

No automated tests are currently implemented in this integration.

## Architecture

### Entry Point Flow

1. **Config Flow** (`config_flow.py`): Handles OAuth2 authentication with PKCE flow
2. **Setup** (`__init__.py`): Creates API client and coordinator, registers services
3. **Coordinator** (`coordinator.py`): Polls API every 5 minutes, manages optimistic updates
4. **Platforms**: Climate entities (`climate.py`) and sensors (`sensor.py`)

### Core Components

**API Client** (`api.py`):

- Implements OAuth2 PKCE authentication flow
- Manages token refresh automatically
- Provides methods for device data, energy statistics, holiday schedules
- Temperature encoding/decoding (API uses Fahrenheit with divFactor)

**Coordinator** (`coordinator.py`):

- Fixed 5-minute polling interval (cloud service, not user-configurable)
- Implements optimistic updates for preset mode changes (10-second duration)
- Predicts HVAC action based on preset mode during optimistic window
- Single source of truth for all device data

**Entity Base** (`entity.py`):

- Base class for all entities with common device info setup
- Extracts and formats device metadata from coordinator data

**Statistics Module** (`statistics.py`):

- Handles historical energy data import as external statistics
- Smart aggregation: hourly (0-7 days), daily (8-90 days), monthly (90+ days)
- Prevents double-counting by using separate statistic IDs for historical imports
- Aligns with Home Assistant's hourly statistic buckets

### Device Data Structure

Coordinator data is a list of device dictionaries with structure:

```python
{
    "id": str,                    # Unique device ID
    "name": str,                  # Device/room name
    "installation_id": str,       # Installation (home) ID
    "installation": str,          # Installation name
    "room_id": str,              # Room ID
    "preset_mode": int,          # Current mode (off/manual/program)
    "hvac_action": int,          # Heating state (off/idle/heating)
    "target_temp": float,        # Target temperature (Celsius)
    "room_temp": float,          # Room temperature (Celsius)
    "floor_temp": float | None,  # Floor temperature (Celsius)
    "daily_energy": float,       # Today's energy consumption (Wh)
    "holiday_mode": int,         # Active holiday mode code
    "holiday_start": str,        # Holiday start date string
    "holiday_end": str,          # Holiday end date string
    # ... additional fields
}
```

### Holiday Mode Behavior

**Important:** Holiday schedules apply to entire installations (all thermostats in a home), not individual devices. During active holidays, thermostat controls are locked to prevent conflicts.

Holiday mode codes (const.py):

- `0`: None (default)
- `1`: Off (heating disabled)
- `2`: Reduce (eco mode)
- `5`: Defrost (frost protection)
- `8`: Sunday (use Sunday schedule)

### Service Architecture

Services are registered in `async_setup()` (not per config entry):

- `fenix_tft.set_holiday_schedule`: Sets installation-wide holiday
- `fenix_tft.cancel_holiday_schedule`: Cancels active holiday
- `fenix_tft.import_historical_statistics`: Imports historical energy data

All services:

1. Validate config entry is loaded
2. Extract installation/device context via registries
3. Call API with proper error handling
4. Wait for backend propagation (5 seconds for holidays)
5. Refresh coordinator to reflect changes

### Energy Statistics Import

The historical import service (`import_historical_statistics`) uses a sophisticated strategy:

1. **Separate statistic ID**: Creates external statistic `fenix_tft:{entity}_history` to avoid interfering with main sensor
2. **Smart backfilling**: Detects existing data and imports older data to fill gaps
3. **Dynamic aggregation**:
   - Recent 7 days: hourly data for detail
   - 8-90 days: daily aggregation
   - 91+ days: monthly aggregation
4. **Midnight boundaries**: Aligns imports to day boundaries to prevent overlap with current sensor data
5. **Chunked fetching**: Fetches in chunks with rate limiting (1-second delays)

## Home Assistant Integration Guidelines

This integration follows Home Assistant's Integration Quality Scale. See `.github/copilot-instructions.md` for comprehensive guidelines on:

- Code quality standards (Python 3.13+, type hints, Ruff/PyLint)
- Async programming patterns
- Entity development (unique IDs, naming, availability)
- Config flow implementation
- Error handling and logging
- Testing requirements
- Documentation standards

**Key requirements for this integration:**

- Use `ConfigEntry.runtime_data` for non-persistent data storage
- Pass `config_entry` to coordinator initialization
- All external I/O must be async
- Use `DataUpdateCoordinator` pattern for efficient polling
- Implement proper error handling with typed exceptions
- Never expose sensitive data in diagnostics/logs

## API Specifics

### Authentication

- OAuth2 Authorization Code flow with PKCE
- No client secret (public mobile app credentials)
- Token refresh handled automatically by API client
- Stores access_token, refresh_token, subscription_id in config entry

### Rate Limiting

- Cloud polling: 300-second intervals (5 minutes)
- Historical imports: 1-second delays between API calls
- Max 5 concurrent energy data requests

### Temperature Handling

API returns temperatures as `{"value": int, "divFactor": int}` in Fahrenheit:

- Decode: `(value / divFactor - 32) * 5/9` → Celsius
- Encode: `((celsius * 9/5) + 32) * divFactor` → API value

### Holiday Dates

API uses format `"01/01/1970 00:00:00"` for epoch (no holiday).
Active holidays use `"dd/mm/yyyy HH:MM:SS"` format.

## File Organization

```bash
custom_components/fenix_tft/
├── __init__.py          # Setup, services, entry point
├── api.py              # API client with OAuth2 PKCE
├── climate.py          # Climate platform (thermostats)
├── config_flow.py      # OAuth2 configuration flow
├── const.py            # Constants and configuration
├── coordinator.py      # Data update coordinator
├── entity.py           # Base entity class
├── helpers.py          # Utility functions
├── manifest.json       # Integration metadata
├── sensor.py           # Sensor platform
├── statistics.py       # Historical energy import logic
├── strings.json        # Translations
└── translations/       # Additional language files
```

## Common Patterns

### Adding a New Sensor

1. Define entity description in `sensor.py` sensor descriptions tuple
2. Add translation key to `strings.json` if needed
3. Ensure data is available in coordinator device dictionary
4. Use `value_fn` lambda for any data transformation

### Modifying API Calls

1. Add/modify method in `FenixTFTApi` class
2. Handle authentication errors → trigger reauth flow
3. Raise `FenixTFTApiError` for API failures
4. Log at appropriate level (debug for requests, info for important operations)

### Service Development

1. Define schema in `__init__.py` using voluptuous
2. Register in `async_setup()` (not `async_setup_entry()`)
3. Validate config entry state before processing
4. Use translation keys for all user-facing errors
5. Add service definition to `services.yaml`

## Important Notes

- **Never make polling intervals user-configurable** - integration determines optimal intervals
- **Holiday schedules are installation-wide** - affect all thermostats in the home
- **Temperature precision**: API supports 0.1°C precision via divFactor
- **Optimistic updates**: Climate entities show immediate feedback for 10 seconds
- **Energy data timing**: Daily energy resets at midnight in user's local timezone
- **Statistics imports**: Always use external statistics for historical data to prevent double-counting

## Debugging

Enable debug logging in Home Assistant `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.fenix_tft: debug
```

Common issues:

- **Authentication failures**: Check OAuth2 flow, tokens in config entry
- **No energy data**: Verify subscription_id is present, check API endpoint response
- **Holiday controls locked**: Active holiday schedule prevents manual changes
- **Statistics not appearing**: Check external statistic ID format, verify recorder integration
