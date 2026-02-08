"""DataUpdateCoordinator for Seedtime."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SeedtimeApiClient, SeedtimeAuthError, SeedtimeConnectionError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class SeedtimeDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to fetch Seedtime garden data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: SeedtimeApiClient,
        update_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch garden plan data and tasks."""
        try:
            garden_data = await self.client.fetch_garden_data()
            tasks_data = await self.client.fetch_tasks()
        except SeedtimeAuthError as err:
            raise ConfigEntryAuthFailed(
                "Seedtime session expired; reauthentication required"
            ) from err
        except SeedtimeConnectionError as err:
            raise UpdateFailed(f"Error communicating with Seedtime: {err}") from err

        return {
            "user": garden_data.get("user", {}),
            "garden": garden_data.get("garden", {}),
            "tasks_rest": tasks_data if isinstance(tasks_data, dict) else {},
        }
