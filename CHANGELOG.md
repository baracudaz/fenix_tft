# Changelog

All notable changes to the Fenix TFT WiFi Home Assistant integration are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

**Breaking:** automations, conditions and dashboards that check for the preset `home` or `away` need updating to `program` / `defrost` (see Changed).

### Changed

- **Presets are named after the thermostat modes, as in the core FENIX Control integration:** Program is `program` (was `home`) and Defrost is `defrost` (was `away`); Boost stays `boost`. The labels shown in Home Assistant (Program, Defrost, Boost and their translations) don't change. This follows the review of the core integration: presets don't have to use Home Assistant's standard names. `climate.set_preset_mode` still accepts the former names `home`, `away`, `eco` and `comfort` ([#235](https://github.com/baracudaz/fenix_tft/pull/235)).

### Fixed

- The climate entity shows the HVAC action (heating / idle) during a holiday again. It was hidden on the assumption that the thermostat reports the holiday mode in its heating state then; a test on a TFT Wi-Fi RF and a WiFi Box showed that the heating state stays correct. The off mode shows "Off" even when the thermostat sends no heating state ([#236](https://github.com/baracudaz/fenix_tft/pull/236)).
- A WiFi Box in a holiday that turns the heating off shows the HVAC mode "Off" instead of "Auto", like the TFT thermostats. During a holiday the climate entity shows "Auto", or "Off" if the holiday turns the heating off, whatever mode the device itself reports ([#236](https://github.com/baracudaz/fenix_tft/pull/236)).
- The *Holiday mode* sensor and the `mode` attribute of the *Holiday until* sensor show what the holiday actually does (Off, Reduce, Defrost or Sunday schedule). They read a property that is the same for every active holiday, so they showed "Reduce (Eco)" whatever was chosen ([#236](https://github.com/baracudaz/fenix_tft/pull/236)).

---

## [1.7.3] - 2026-11-10

### Fixed

- `climate.set_temperature` with a temperature and an HVAC mode now works while the thermostat is off (for example `hvac_mode: heat` turns it on with that target); before, Home Assistant rejected the call. The HVAC mode given with a temperature is now applied in the other modes too; it used to be ignored. A temperature without an HVAC mode is still rejected while the thermostat is off, so it can't switch the heating on by itself ([#232](https://github.com/baracudaz/fenix_tft/pull/232)).

---

## [1.7.2] - 2026-11-10

### Fixed

- WiFi Box: no floor temperature sensors any more. The box sends a floor temperature value, but the cloud provider confirmed it means nothing there (no floor probe). Raw error values (0x7FFF) no longer show up as absurd temperatures. Both via pyfenixcontrol 0.5.1 ([#230](https://github.com/baracudaz/fenix_tft/pull/230)). Existing WiFi Box floor sensors stay as unavailable entities and can be deleted.

---

## [1.7.1] - 2026-11-10

### Fixed

- Setting a target temperature in Fahrenheit no longer fails with "not a valid step": the converted value is rounded to the thermostat's 0.5 °C step ([#225](https://github.com/baracudaz/fenix_tft/pull/225)).
- With Fahrenheit, the thermostat card now steps the target by 1 °F; a 0.5 °F step was rounded back to the same 0.5 °C target, so the buttons seemed to do nothing ([#228](https://github.com/baracudaz/fenix_tft/pull/228)).

### Changed

- README: the energy sensors are calculated by the cloud from the relay's on-time and the heating power set on the thermostat, with how to set it and what this means with HDO ([#224](https://github.com/baracudaz/fenix_tft/pull/224)).

---

## [1.7.0] - 2026-11-09

### Changed

- Requires Home Assistant 2026.11 or newer. The thermostat uses the climate entity's new `native_*` temperature members; the old names logged deprecation warnings since 2026.11 and stop working in 2027.11 ([#222](https://github.com/baracudaz/fenix_tft/pull/222)).
- README: installation count badge from Home Assistant analytics; obsolete badges removed ([#208](https://github.com/baracudaz/fenix_tft/pull/208)).

---

## [1.6.3] - 2026-11-09

### Changed

- README: installation via the Marketplace built into Home Assistant 2026.11 and newer; HACS instructions kept for 2026.10 and older ([#206](https://github.com/baracudaz/fenix_tft/pull/206)).
- README: the integration is now developed in cooperation with FENIX (technical support, documentation, test devices) and is coming to Home Assistant as FENIX Control; the "reverse engineered, not affiliated" notes are gone ([#206](https://github.com/baracudaz/fenix_tft/pull/206)).

---

## [1.6.2] - 2026-11-09

### Fixed

- A mode or temperature change no longer reverts to the old value when a slow poll that started before the change finishes more than 10 seconds after it ([#204](https://github.com/baracudaz/fenix_tft/pull/204)).

### Changed

- README: energy is calculated from the heating time and the heater power set on the thermostat, not measured; why it can differ from the electricity meter (heater power setting, HDO tariffs, [#179](https://github.com/baracudaz/fenix_tft/issues/179); [#202](https://github.com/baracudaz/fenix_tft/pull/202)).
- README: where to set the heater power on the thermostat ([#203](https://github.com/baracudaz/fenix_tft/pull/203)).

---

## [1.6.1] - 2026-11-09

### Fixed

- After switching the preset to Program, the thermostat briefly showed the previous mode's temperature (for example Defrost's 7 °C) as the Program target until the next update. It now shows no target until the thermostat reports the program's temperature ([#200](https://github.com/baracudaz/fenix_tft/pull/200)).

### Changed

- pyfenixcontrol 0.5.0: naming a thermostat that reports no name after its room now happens in the library (same result as 1.4.1).

---

## [1.6.0] - 2026-11-08

### Added

- The thermostat shows a target temperature outside manual mode too, instead of none ([#186](https://github.com/baracudaz/fenix_tft/issues/186)):
  - Program: the temperature the program currently regulates to (for example 20 °C). Changing it switches the thermostat to manual (Heat) with that temperature.
  - Defrost and Boost: their own setpoints (for example Defrost 7 °C, Boost 24 °C, as on the thermostat's display), right after switching the mode. Changing the target sets that setpoint and keeps the thermostat in Defrost or Boost ([#197](https://github.com/baracudaz/fenix_tft/issues/197)).
- The temperature range follows what each thermostat accepts in the current mode, for example 2–15 °C for Defrost on TFT thermostats and 10–30 °C on the WiFi Box ([#187](https://github.com/baracudaz/fenix_tft/issues/187)). Before, it was always 5–35 °C.
- pyfenixcontrol 0.4.0.

### Changed

- The presets are labelled with FENIX's names, as in the FENIX Control app and on the preset mode sensor: `home` is "Program", `away` "Defrost" and `boost` "Boost", with the app's icons (clock, snowflake, flame). Czech, German and French use the mode names of the thermostat's menu from its manual: Defrost is "Ochrana proti zamrznutí" / "Frostschutz" / "Hors gel", Boost "Časovač" / "Timer" / "Dérogation temporaire" (Czech also "Dovolená" for holiday). The preset keys are unchanged, so automations keep working.

---

## [1.5.1] - 2026-11-08

### Fixed

- A thermostat that has reached its target temperature shows the HVAC action "Idle" instead of "Off". TFT thermostats report the same value for "not heating" and "off", so the action and the *HVAC state* sensor now show "Off" only when the thermostat's mode is off. The climate entity reports no action when the thermostat doesn't send its heating state or a holiday is active (the thermostat then reports the holiday mode in that field) ([#184](https://github.com/baracudaz/fenix_tft/issues/184))

### Changed

- The device model shows the product name of the thermostat (TFT Wi-Fi, TFT Wi-Fi RF or WiFi Box) instead of "TFT WiFi Thermostat" for every device, and the type code (for example P07542) as the model ID instead of the hardware version, as in the core integration. Unknown device types show only the type code. pyfenixcontrol 0.2.0 ([#185](https://github.com/baracudaz/fenix_tft/issues/185))
- Documentation: TFT thermostats round holiday start and end down to the full hour (README and the holiday service fields); new "Known limitations" section in the README: floor temperature, open-window detection, floor limit and Professional Mode aren't reported by the cloud ([#188](https://github.com/baracudaz/fenix_tft/issues/188))

---

## [1.5.0] - 2026-11-08

**Breaking:** automations, conditions and dashboards that check for the preset `eco` or `comfort` need updating to `away` / `boost` (see Changed). The floor sensors are no longer created (see Fixed).

### Fixed

- **The floor temperature sensor showed the thermostat's Boost setpoint, not the floor temperature.** The library read the wrong cloud property (checked on a thermostat: Boost setting 24.0 °C, floor probe 23.1 °C, sensor 24.0 °C). It now reads the floor temperature, but the cloud doesn't report one for TFT Wi-Fi thermostats, even with a floor probe connected. So the *Floor temperature* and *Floor-air difference* sensors are no longer created: after updating, Home Assistant lists the existing ones as no longer provided, and you can delete them. If the cloud starts reporting the floor temperature, they come back the next time the integration loads (restart or reload). pyfenixcontrol 0.1.1 ([#183](https://github.com/baracudaz/fenix_tft/issues/183))

### Changed

- **Presets use Home Assistant's standard names, as in the core FENIX Control integration:** Program is `home` ("Home"), Defrost is `away` ("Away", was `eco` "Eco 15°C") and Boost is `boost` ("Boost", was `comfort` "Comfort 23°C"). The old labels showed fixed temperatures, but the Defrost and Boost setpoints are set on each thermostat (Defrost is 7 °C by default), so they were often wrong. Labels are now translated by Home Assistant in every language. `climate.set_preset_mode` still accepts `eco`, `comfort`, `defrost` and `program`, so service calls keep working. **Update automations, conditions and dashboards that check for the preset `eco` or `comfort`.** The preset mode sensor keeps its states; its `defrost` and `boost` states are now labelled "Defrost" and "Boost" ([#178](https://github.com/baracudaz/fenix_tft/issues/178))
- Development only: tests run on Home Assistant 2026.11.0 with Home Assistant's own test package `pytest-homeassistant`, which replaces the retired `pytest-homeassistant-custom-component`; the Docker dev image is on 2026.11.0 ([#180](https://github.com/baracudaz/fenix_tft/pull/180))

## [1.4.1] - 2026-10-22

### Fixed

- A thermostat that reports no name of its own (seen on a thermostat after its firmware update to v01.09.03) is now named after its room, as in the FENIX app, instead of `<installation> Unnamed Device`. Entity IDs don't change; the device name is updated the next time the integration loads, unless you renamed the device ([#159](https://github.com/baracudaz/fenix_tft/pull/159))

### Changed

- Development only: the Home Assistant version for tests and `make install` now comes from the exact `pytest-homeassistant-custom-component` pin (2026.10.2), so Dependabot updates no longer fail on a separate `homeassistant` pin; the Docker dev image is on 2026.10.2 and updated by Dependabot ([#160](https://github.com/baracudaz/fenix_tft/pull/160))
- Tests for the sensor platform and the config flow error paths ([#152](https://github.com/baracudaz/fenix_tft/pull/152), [#153](https://github.com/baracudaz/fenix_tft/pull/153))

---

## [1.4.0] - 2026-10-15

### Changed

- The cloud API client moved into the standalone library [`pyfenixcontrol`](https://github.com/baracudaz/pyfenixcontrol); `api.py` and the `beautifulsoup4` dependency are gone. Entities, unique IDs, services and the `fenix_tft` domain are unchanged
- Each config entry now uses its own HTTP session, so login cookies of one account can't affect another
- An authentication failure during polling is logged as a warning instead of an error with a traceback; Home Assistant asks for reauthentication as before
- Config flow no longer logs failed logins as errors or logs the account e-mail; expected failures (wrong password, cloud unreachable) are logged at debug level only, since the form already shows them
- When the installation list can't be fetched, the entities now become unavailable until the next successful refresh. Previously the update succeeded with no devices

### Added

- Config flow shows "Failed to connect to the FENIX cloud" instead of "Unexpected exception" when the cloud is unreachable

### Fixed

- Diagnostics now include today's energy consumption (the field was always empty)
- Failed thermostat commands (temperature, HVAC mode, preset) now show a translated error instead of a raw exception
- An expired login during a holiday service or the historical import now starts reauthentication; the import no longer continues and reports success with gaps

---

## [1.3.8] - 2026-10-04

### Fixed

- Removed `aiohttp` from the manifest `requirements`. Hassfest now rejects custom integrations that list it, since it is a dependency of Home Assistant itself; this had been failing validation since 2026-10-01. No runtime change, as Home Assistant already provides `aiohttp` ([#142](https://github.com/baracudaz/fenix_tft/pull/142))

### Changed

- Bumped `homeassistant` to `2026.9.4` in `requirements.txt` and `docker-compose.yml` to match the version required by `pytest-homeassistant-custom-component` 0.13.367 ([#141](https://github.com/baracudaz/fenix_tft/pull/141))
- Bumped `ruff` from `0.16.7` to `0.16.9` ([#137](https://github.com/baracudaz/fenix_tft/pull/137), [#139](https://github.com/baracudaz/fenix_tft/pull/139))
- Bumped the pinned `home-assistant/actions/hassfest` GitHub Action ([#140](https://github.com/baracudaz/fenix_tft/pull/140))
- Updated `CLAUDE.md` to document the existing pytest suite (`make test`) instead of stating that no tests exist

---

## [1.3.7] - 2026-09-16

### Fixed

- The `coordinator_unavailable` repair issue no longer gets stuck open forever after a Home Assistant restart. It was only cleared when the coordinator's in-memory consecutive-failure counter had crossed the creation threshold, but that counter resets on every restart, so a coordinator that recovered across a restart could never clear its own issue again ([#134](https://github.com/baracudaz/fenix_tft/issues/134))
- The repair issue is now tracked per config entry instead of a single shared ID, so with multiple Fenix accounts configured, a healthy account's coordinator no longer clears the issue for a different account whose coordinator is still failing

### Changed

- Bumped `homeassistant` to `2026.9.2` in `requirements.txt` and `docker-compose.yml` to match the version required by `pytest-homeassistant-custom-component` 0.13.365
- Bumped `ruff` from `0.16.6` to `0.16.7`

---

## [1.3.6] - 2026-09-12

### Fixed

- HTTP 401 responses from the cloud API now trigger an automatic token refresh, falling back to a full re-login with the stored credentials, and only surface a Home Assistant reauthentication request if both fail. Previously a 401 was treated as a generic non-retriable error and the same invalid token was retried on every 5-minute polling cycle indefinitely, leaving all entities `unavailable` until the config entry was manually reloaded ([#129](https://github.com/baracudaz/fenix_tft/issues/129))
- `get_installations()` now refreshes the access token on every poll instead of only on the very first call, closing a gap where an expiring token was never proactively renewed once the subscription ID was cached

### Changed

- Bumped the pinned `home-assistant/actions/hassfest` CI action to its latest commit

---

## [1.3.5] - 2026-09-08

### Fixed

- Bumped `homeassistant` to `2026.9.1` in `requirements.txt` and `docker-compose.yml`: `pytest-homeassistant-custom-component` hard-pins a matching `homeassistant`/`pytest` version, and the previous `2026.8.2`/`pytest>=9.1.1` pins here had become mutually unresolvable, breaking `make install`/CI
- Updated `tests/components/fenix_tft/test_init.py` to use `device_registry.async_get_device_by_identifier`, replacing the now-deprecated `async_get_device`

---

## [1.3.3] - 2026-08-21

### Changed

- Bumped Home Assistant and all Python dependencies to `homeassistant==2026.8.2`, which now requires Python 3.14
- Removed `uv` as the package manager; local development now uses a plain `.venv` created with `python -m venv` and `pip`
- Deleted `scripts/setup`, `scripts/develop`, and `scripts/lint`; their logic now lives directly in the `Makefile` (`make install`, `make develop`, `make lint`, etc.)
- Added `docker-compose.yml` and `make docker-up`/`docker-down`/`docker-logs` targets as an alternative way to run a full Home Assistant dev instance in a container, pinned to the `2026.8.2` image; it shares the same `config/` directory as `make develop` so both dev paths use one Home Assistant state (no separate `.data/`)
- Trimmed the `Makefile` to a lean, focused set of targets (`install`, `develop`, `lint`, `test`, `translations`, `docker-up`/`docker-down`/`docker-logs`/`docker-restart`, `clean`)
- Added `requirements-test.txt` and `pytest.ini` (tracked) so test/dev-only dependencies and pytest configuration no longer depend on a local, untracked `pyproject.toml`
- Raised the minimum supported Home Assistant version in `hacs.json` from `2024.1.0` to `2025.1.0`, reflecting the versions actually exercised by dev/CI

---

## [1.3.2] - 2026-08-21

### Fixed

- GET requests (installations, device properties, userinfo, energy consumption) now retry transient 5xx gateway errors with exponential backoff, matching the retry behavior already used for PUT requests. Previously a single transient 502/503 from the cloud API's gateway could drop a device from a polling cycle until the next 5-minute update.

---

## [1.3.1] - 2026-08-20

### Fixed

- Declared `CONFIG_SCHEMA` (config-entry-only) to resolve a Home Assistant hassfest validation warning; the integration has no YAML setup, only the config flow

---

## [1.3.0] - 2026-05-10

### Added

- Full-history energy statistics import via `fenix_tft.import_historical_statistics` with the new `import_all_history` option
- Yearly batching for very old history ranges so long backfills can progress efficiently

### Changed

- `days_back` is now optional with a default of 30 days for targeted historical backfills
- Updated service descriptions, README documentation, and localized translations for the new full-history import flow

### Fixed

- Historical backfills now rebase later external statistic sums when prepending older data, keeping cumulative totals continuous
- Historical import notifications now better reflect imported ranges, batch progress, and up-to-date cases

---

## [1.2.2] - 2026-05-09

### Changed

- Updated climate preset presentation in Auto mode to use clearer names and icons:
  - `program` is shown as **Program** with a home icon
  - `defrost` behavior is shown as **Eco 15°C** with a leaf icon
  - `boost` behavior is shown as **Comfort 23°C** with a comfort icon
- Updated localized translations (EN/DE/FR/CS/SK) for climate preset labels and sensor preset labels to match the new naming

### Fixed

- Fixed preset picker icon behavior in Home Assistant by mapping exposed climate preset keys to icon-aware semantic values (`home`, `eco`, `comfort`)
- Kept backward compatibility for service calls by accepting legacy preset aliases (`program`, `defrost`, `boost`)

---

## [1.2.1] - 2026-04-28

### Changed

- Clarified the custom integration translation workflow in the README: `translations/en.json` is the English runtime source, and `make translations` validates other locale files against it

### Fixed

- Clarified installation instructions to avoid confusion between HACS custom repositories and Home Assistant's Add-on Store
- Updated wording to match Home Assistant UI labels and corrected the repository error phrasing to "not a valid add-on repository"

---

## [1.2.0] - 2026-03-29

### Added

- **Reconfigure flow**: Update email/password credentials without removing and re-adding the integration
- **Diagnostics panel**: Built-in HA diagnostics page for troubleshooting; sensitive fields (password) are automatically redacted
- **Repair issues**: Automatic repair notification created after 3 consecutive cloud connectivity failures; cleared automatically on recovery
- **Temperature bounds validation**: Set temperature now enforces 5–35 °C range and 0.5 °C step; raises a translatable error if out of range
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
