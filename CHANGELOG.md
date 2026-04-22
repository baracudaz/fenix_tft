# Changelog

All notable changes to the Fenix TFT WiFi Home Assistant integration are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.2.1] - 2026-04-22

### Added

- Diagnostic sensors for open-window investigation: `Device status (St)` and `Error codes (Er)`

### Changed

- Device payload now includes raw `St` and `Er` fields (`device_status`, `error_codes`)

### Fixed

- Added missing translations for new diagnostic sensors in all supported locales

---

## [1.2.0] - 2026-03-29

### Added

- **Reconfigure flow**: Update email/password credentials without removing and re-adding the integration
- **Diagnostics panel**: Built-in HA diagnostics page for troubleshooting; sensitive fields (password) are automatically redacted
- **Repair issues**: Automatic repair notification created after 3 consecutive cloud connectivity failures; cleared automatically on recovery
- **Temperature bounds validation**: Set temperature now enforces 5-35 °C range and 0.5 °C step; raises a translatable error if out of range
- **API retry logic**: Transient HTTP 5xx server errors are retried up to 2 times with exponential backoff (1 s, 2 s)
- **Auth error differentiation**: Authentication failures now raise `ConfigEntryAuthFailed`, triggering the reauthentication flow instead of silently failing
- **`async_migrate_entry`**: Migration framework in place for future config entry schema upgrades
- **`async_remove_config_entry_device`**: Prevents removal of devices that are still active in the installation
- **Silver quality scale**: Integration targets and documents HA Silver quality scale compliance (`quality_scale.yaml`)
- **Test infrastructure**: 33 automated tests covering config flow, coordinator, and climate platform
- **Makefile**: Common developer tasks (`make setup`, `make develop`, `make lint`, `make test`, `make test-cov`, `make translations`, `make clean`)

### Changed

- `make setup` now uses `uv sync --all-extras` to install all dependencies (including test extras) into `.venv`
- `scripts/develop` uses `uv run hass` so `hass` is resolved from the virtual environment
- HVAC action prediction improved: uses temperature delta (target vs current) instead of mode alone
- Replaced broad `except Exception` with specific exception types in coordinator
- `AbortFlow` exceptions in config flow steps are no longer silently swallowed

### Fixed

- `reconfigure_successful` abort key was missing from all translation files, causing a raw key to be displayed in the UI
- Config flow `AbortFlow` exceptions (raised by `_abort_if_unique_id_mismatch`, `_abort_if_unique_id_configured`) were incorrectly caught by the broad `except Exception` block

---

## [1.1.3] - 2025-09-24

### Added

- Pre-commit configuration for Ruff linter and formatter

### Fixed

- Handle sporadic API errors and improve date handling in device updates

---

## [1.1.2] - 2025

### Fixed

- Holiday detection improvements
- Dependency and tooling updates

---

## [1.1.1] - 2025

### Fixed

- Holiday mode fix: corrected mode detection logic

---

## [1.1.0] - 2025

### Added

- **Historical energy import**: Import historical energy consumption as external statistics via `fenix_tft.import_historical_statistics` service
- Smart aggregation: hourly (0–7 days), daily (8–90 days), monthly (91+ days)
- Separate external statistic ID to prevent double-counting with live sensor data

---

## [1.0.1] - 2025

### Fixed

- Energy sensor state class changed to `TOTAL_INCREASING` for correct Energy Dashboard integration

---

## [1.0.0] - 2025

### Added

- **Holiday mode**: Set and cancel installation-wide holiday schedules via `fenix_tft.set_holiday_schedule` and `fenix_tft.cancel_holiday_schedule` services
- Holiday mode sensor and holiday end timestamp sensor
- Thermostat controls automatically locked during active holiday periods

---

## [0.9.2] - 2025

### Fixed

- Daily energy consumption calculation fixes

---

## [0.9.1] - 2025

### Fixed

- Energy sensor state class and precision corrections
- Polling interval and local timezone conversion improvements

---

## [0.9.0] - 2025

### Added

- **Daily energy consumption**: New sensor tracking today's energy usage (Wh), integrated with HA Energy Dashboard

---

## [0.8.0] - 2025

### Added

- Additional sensors: ambient temperature, floor temperature, target temperature, temperature difference, floor/air difference, HVAC state, connectivity status

---

## [0.7.0 and earlier]

Initial development: OAuth2 PKCE authentication, climate entity, basic thermostat control (Off/Manual/Program modes), multi-device support.
