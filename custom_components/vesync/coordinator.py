"""Class to manage VeSync data updates."""

import asyncio
from datetime import timedelta
import logging
import time
from typing import override

from pyvesync import VeSync
from pyvesync.utils.errors import VeSyncError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .common import is_dual_air_fryer
from .const import (
    FRYER_ACTIVE_MAX_SECONDS,
    FRYER_ACTIVE_STATUSES,
    UPDATE_INTERVAL,
    UPDATE_INTERVAL_ENERGY,
    UPDATE_INTERVAL_FRYER_ACTIVE,
)

_LOGGER = logging.getLogger(__name__)

type VesyncConfigEntry = ConfigEntry[VeSyncDataCoordinator]


class VeSyncDataCoordinator(DataUpdateCoordinator[None]):
    """Class representing data coordinator for VeSync devices."""

    config_entry: VesyncConfigEntry
    update_time: float | None = None
    _last_full_update: float = 0.0
    _fryer_active_since: float | None = None

    def __init__(
        self, hass: HomeAssistant, config_entry: VesyncConfigEntry, manager: VeSync
    ) -> None:
        """Initialize."""
        self.manager = manager

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="VeSyncDataCoordinator",
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

    def should_update_energy(self) -> bool:
        """Test if specified update interval has been exceeded."""
        if self.update_time is None:
            return True

        return time.time() - self.update_time >= UPDATE_INTERVAL_ENERGY

    def _fryers(self) -> list:
        """Return the dual-basket air fryers."""
        return [dev for dev in self.manager.devices if is_dual_air_fryer(dev)]

    def _fryer_active(self) -> bool:
        """Test if a fryer basket is cooking.

        Falls back to the normal interval after FRYER_ACTIVE_MAX_SECONDS as a safety
        net, so a status that never clears does not poll quickly all day.
        """
        active = any(
            chamber.cook_status.lower() in FRYER_ACTIVE_STATUSES
            for dev in self._fryers()
            for chamber in dev.state.chambers.values()
        )
        if not active:
            self._fryer_active_since = None
            return False
        if self._fryer_active_since is None:
            self._fryer_active_since = time.monotonic()
        return time.monotonic() - self._fryer_active_since < FRYER_ACTIVE_MAX_SECONDS

    @override
    async def _async_update_data(self) -> None:
        """Fetch data from API endpoint."""
        try:
            fast = self.update_interval == timedelta(
                seconds=UPDATE_INTERVAL_FRYER_ACTIVE
            )
            if fast and time.monotonic() - self._last_full_update < UPDATE_INTERVAL:
                # Between full updates only the fryer needs the short interval.
                await asyncio.gather(*(dev.update() for dev in self._fryers()))
            else:
                await self.manager.update_all_devices()
                self._last_full_update = time.monotonic()

            if self.should_update_energy():
                self.update_time = time.time()
                for outlet in self.manager.devices.outlets:
                    await outlet.update_energy()
        except VeSyncError as err:
            raise UpdateFailed(f"The service is unavailable: {err}") from err
        finally:
            self.update_interval = timedelta(
                seconds=UPDATE_INTERVAL_FRYER_ACTIVE
                if self._fryer_active()
                else UPDATE_INTERVAL
            )
