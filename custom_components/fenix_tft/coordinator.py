"""Coordinator for Fenix TFT integration."""

import asyncio
import dataclasses
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from pyfenixcontrol import (
    Device,
    EnergyMetric,
    EnergyPeriod,
    FenixControlAuthError,
    FenixControlClient,
    FenixControlError,
)

from .const import (
    DOMAIN,
    ENERGY_WINDOW,
    HVAC_ACTION_HEATING,
    HVAC_ACTION_IDLE,
    HVAC_ACTION_OFF,
    MAX_CONCURRENT_ENERGY_REQUESTS,
    OPTIMISTIC_UPDATE_DURATION,
    POLLING_INTERVAL,
    PRESET_MODE_BOOST,
    PRESET_MODE_DEFROST,
    PRESET_MODE_OFF,
)
from .helpers import device_display_name
from .statistics import async_import_recent_energy

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

CONSECUTIVE_FAILURES_BEFORE_ISSUE = 3

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RoomEnergy:
    """Hourly energy buckets of one room."""

    # "<installation> <room>", like the names of the room's thermostats
    name: str
    # Buckets over ENERGY_WINDOW as stamped by the cloud (end of the hour);
    # None if they could not be fetched
    buckets: list[EnergyMetric] | None


@dataclass(slots=True)
class FenixTFTData:
    """Snapshot of all thermostats of the account."""

    devices: dict[str, Device] = field(default_factory=dict)
    # Today's energy consumption per device (Wh); None if it could not be fetched
    daily_energy: dict[str, float | None] = field(default_factory=dict)
    # Hourly energy of each room with thermostats, keyed by room ID
    room_energy: dict[str, RoomEnergy] = field(default_factory=dict)


# Device field holding the setpoint of each mode that has its own one (Ma, df, bo);
# the other modes keep the manual target.
_SETPOINT_FIELDS: dict[int, str] = {
    PRESET_MODE_DEFROST: "defrost_temperature",
    PRESET_MODE_BOOST: "boost_temperature",
}


def _setpoint_field(preset_mode: int) -> str:
    """Return the device field holding the setpoint of ``preset_mode``."""
    return _SETPOINT_FIELDS.get(preset_mode, "target_temperature")


def _with_preset_mode(
    device: Device, preset_mode: int, hvac_state: int | None
) -> Device:
    """
    Return the device in a commanded preset mode.

    The active setpoint (Sp) of another mode would show as the new mode's
    target, so it is unknown until the device reports the new mode.
    """
    if device.preset_mode == preset_mode:
        return dataclasses.replace(
            device, preset_mode=preset_mode, hvac_state=hvac_state
        )
    return dataclasses.replace(
        device,
        preset_mode=preset_mode,
        hvac_state=hvac_state,
        active_target_temperature=None,
    )


def _predict_hvac_action(
    preset_mode: int,
    target_temp: float | None = None,
    current_temp: float | None = None,
) -> int:
    """
    Predict hvac_action based on preset_mode and temperatures.

    - PRESET_MODE_OFF → HVAC_ACTION_OFF
    - Active mode with target > current → HVAC_ACTION_HEATING (device likely heating)
    - Active mode otherwise → HVAC_ACTION_IDLE (safe default)
    """
    if preset_mode == PRESET_MODE_OFF:
        return HVAC_ACTION_OFF
    if (
        target_temp is not None
        and current_temp is not None
        and target_temp > current_temp
    ):
        return HVAC_ACTION_HEATING
    return HVAC_ACTION_IDLE


def _sum_today(buckets: list[EnergyMetric] | None) -> float | None:
    """Return the energy (Wh) of the buckets stamped since local midnight."""
    if buckets is None:
        return None
    midnight = dt_util.start_of_local_day()
    return sum(
        (
            bucket.processed_value
            for bucket in buckets
            if bucket.start is not None and bucket.start >= midnight
        ),
        0.0,
    )


def _room_display_name(room_name: str | None, device: Device) -> str:
    """Return "<installation> <room>", falling back to the thermostat's name."""
    return device_display_name(
        dataclasses.replace(device, name=room_name) if room_name else device
    )


class FenixTFTCoordinator(DataUpdateCoordinator[FenixTFTData]):
    """Data update coordinator for Fenix TFT."""

    client: FenixControlClient
    # device_id -> (preset_mode, hvac_action, timestamp, target_temperature or None)
    _optimistic_updates: dict[str, tuple[int, int, float, float | None]]
    _consecutive_failures: int
    _unavailable_logged: bool

    def __init__(
        self,
        hass: HomeAssistant,
        client: FenixControlClient,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the Fenix TFT coordinator with fixed polling interval."""
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=POLLING_INTERVAL),
            config_entry=config_entry,
        )
        self.client = client
        self._optimistic_updates: dict[str, tuple[int, int, float]] = {}
        self._consecutive_failures: int = 0
        self._unavailable_logged: bool = False
        # Energy buckets per room last written as statistics
        self._imported_energy: dict[str, tuple[tuple[Any, float], ...]] = {}

    async def _async_update_data(self) -> FenixTFTData:
        """Fetch data from the FENIX cloud."""
        _LOGGER.debug("Starting coordinator data update")
        try:
            fresh_data = await self._fetch_data()
        except FenixControlAuthError as err:
            _LOGGER.warning("Authentication with the FENIX cloud failed: %s", err)
            raise ConfigEntryAuthFailed(str(err)) from err
        except FenixControlError as err:
            self._handle_update_failure(err)

        _LOGGER.debug(
            "Coordinator data update successful: fetched %d device(s)",
            len(fresh_data.devices),
        )
        self._handle_update_success()
        await self._import_energy_statistics(fresh_data)
        self._apply_optimistic_updates(fresh_data)
        return fresh_data

    async def _fetch_data(self) -> FenixTFTData:
        """Fetch device state, trigger device reports and add room energy."""
        installations = await self.client.get_installations()
        devices = await self.client.get_devices(installations)

        for installation_id in {device.installation_id for device in devices}:
            await self._trigger_installation_update(installation_id)

        # The cloud reports energy per room: fetch each room once
        rooms = {
            (device.installation_id, device.room_id): device
            for device in devices
            if device.installation_id is not None and device.room_id is not None
        }
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_ENERGY_REQUESTS)
        metrics = await asyncio.gather(
            *(self._fetch_room_energy(semaphore, *room) for room in rooms)
        )
        room_energy = {
            room_id: RoomEnergy(
                name=_room_display_name(
                    room_names.get((installation_id, room_id)), device
                ),
                buckets=buckets,
            )
            for ((installation_id, room_id), device), buckets in zip(
                rooms.items(), metrics, strict=True
            )
        }
        return FenixTFTData(
            devices={device.id: device for device in devices},
            daily_energy={
                device.id: _sum_today(
                    room_energy[device.room_id].buckets
                    if device.room_id in room_energy
                    else None
                )
                for device in devices
            },
            room_energy=room_energy,
        )

    async def _trigger_installation_update(self, installation_id: str) -> None:
        """Ask the thermostats of an installation to report fresh values."""
        try:
            await self.client.trigger_installation_update(installation_id)
        except FenixControlAuthError:
            raise
        except FenixControlError as err:
            # Best effort: the backend often answers this with sporadic 5xx
            # responses, and the device state was already fetched.
            _LOGGER.warning(
                "Skipping failed device update trigger for installation %s: %s",
                installation_id,
                err,
            )

    async def _fetch_room_energy(
        self, semaphore: asyncio.Semaphore, installation_id: str, room_id: str
    ) -> list[EnergyMetric] | None:
        """Return the room's hourly energy buckets over the last ENERGY_WINDOW."""
        # The cloud rounds both bounds down to the full hour and leaves out the
        # bucket stamped at the end, so end one hour after the current one: the
        # newest bucket (stamped this hour, covering the hour before) is then
        # returned as soon as it is published.
        hour = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
        start = hour - ENERGY_WINDOW
        end = hour + timedelta(hours=1)
        async with semaphore:
            try:
                return await self.client.get_room_energy(
                    installation_id, room_id, start, end, EnergyPeriod.HOUR
                )
            except FenixControlAuthError:
                raise
            except FenixControlError as err:
                # Don't fail the entire update if energy data fails
                _LOGGER.debug(
                    "Failed to fetch energy data for room %s: %s", room_id, err
                )
                return None

    async def _import_energy_statistics(self, data: FenixTFTData) -> None:
        """Write new or changed hourly energy buckets as external statistics."""
        for room_id, room in data.room_energy.items():
            if not room.buckets:
                continue
            fingerprint = tuple(
                (bucket.start, bucket.processed_value) for bucket in room.buckets
            )
            if self._imported_energy.get(room_id) == fingerprint:
                continue
            try:
                await async_import_recent_energy(
                    self.hass, room_id, room.name, room.buckets
                )
            except Exception:
                _LOGGER.exception(
                    "Failed to import energy statistics for room %s", room_id
                )
                continue
            self._imported_energy[room_id] = fingerprint

    def _handle_update_failure(self, err: FenixControlError) -> None:
        """Handle a failed data update: log, track failures, and raise."""
        self._consecutive_failures += 1
        if not self._unavailable_logged:
            _LOGGER.warning("Fenix TFT cloud API is unavailable: %s", err)
            self._unavailable_logged = True
        else:
            _LOGGER.debug(
                "Coordinator data update failed (consecutive failures: %d): %s",
                self._consecutive_failures,
                err,
            )
        if self._consecutive_failures == CONSECUTIVE_FAILURES_BEFORE_ISSUE:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._unavailable_issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="coordinator_unavailable",
                translation_placeholders={
                    "consecutive_failures": str(CONSECUTIVE_FAILURES_BEFORE_ISSUE),
                },
            )
        msg = f"Error fetching Fenix TFT data: {err}"
        raise UpdateFailed(msg) from err

    def _handle_update_success(self) -> None:
        """Reset failure state and clear any repair issue on a successful update."""
        if self._unavailable_logged:
            _LOGGER.info("Fenix TFT cloud API is back online")
            self._unavailable_logged = False
        ir.async_delete_issue(self.hass, DOMAIN, self._unavailable_issue_id)
        self._consecutive_failures = 0

    @property
    def _unavailable_issue_id(self) -> str:
        """Return the repair issue ID scoped to this coordinator's config entry."""
        return f"coordinator_unavailable_{self.config_entry.entry_id}"

    def _apply_optimistic_updates(self, fresh_data: FenixTFTData) -> None:
        """Overlay in-flight optimistic updates onto freshly fetched device data."""
        current_time: float = self.hass.loop.time()
        expired_updates: list[str] = []

        for device_id, (preset_mode, hvac_action, timestamp, target) in list(
            self._optimistic_updates.items()
        ):
            if current_time - timestamp > OPTIMISTIC_UPDATE_DURATION:
                expired_updates.append(device_id)
                continue
            if (device := fresh_data.devices.get(device_id)) is not None:
                _LOGGER.debug(
                    "Preserving optimistic update for device %s: "
                    "preset_mode=%s, hvac_action=%s",
                    device_id,
                    preset_mode,
                    hvac_action,
                )
                if target is not None:
                    device = dataclasses.replace(
                        device, **{_setpoint_field(preset_mode): target}
                    )
                fresh_data.devices[device_id] = _with_preset_mode(
                    device, preset_mode, hvac_action
                )

        for device_id in expired_updates:
            _LOGGER.debug(
                "Optimistic update expired for device %s, reverting to fresh data",
                device_id,
            )
            del self._optimistic_updates[device_id]

        if expired_updates:
            _LOGGER.debug(
                "Removed %d expired optimistic update(s)", len(expired_updates)
            )

    def update_device_preset_mode(
        self,
        device_id: str,
        preset_mode: int,
        target_temperature: float | None = None,
    ) -> None:
        """
        Optimistically update the preset mode (and its setpoint) in coordinator data.

        ``target_temperature`` is the new setpoint of ``preset_mode``: the manual
        target, or the Defrost or Boost setpoint.
        """
        if not self.data or not self.data.devices:
            _LOGGER.warning(
                "Cannot apply optimistic update for device %s: no coordinator data",
                device_id,
            )
            return

        device = self.data.devices.get(device_id)
        if device is None:
            _LOGGER.warning(
                "Device %s not found in coordinator data for optimistic update",
                device_id,
            )
            return

        field = _setpoint_field(preset_mode)
        if target_temperature is not None:
            device = dataclasses.replace(device, **{field: target_temperature})
        target_temp: float | None = getattr(device, field)
        current_temp = device.room_temperature
        predicted_hvac_action = _predict_hvac_action(
            preset_mode, target_temp, current_temp
        )
        self._optimistic_updates[device_id] = (
            preset_mode,
            predicted_hvac_action,
            self.hass.loop.time(),
            target_temperature,
        )
        self.data.devices[device_id] = _with_preset_mode(
            device, preset_mode, predicted_hvac_action
        )
        _LOGGER.debug(
            "Optimistic update applied for device %s: preset_mode=%s, "
            "predicted_hvac_action=%s (target=%.1f, current=%.1f)",
            device_id,
            preset_mode,
            predicted_hvac_action,
            target_temp if target_temp is not None else float("nan"),
            current_temp if current_temp is not None else float("nan"),
        )

    @property
    def pending_optimistic_update_count(self) -> int:
        """Return the number of devices with pending optimistic updates."""
        return len(self._optimistic_updates)
