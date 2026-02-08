"""Seedtime Garden Planner integration for Home Assistant."""

from __future__ import annotations

import logging
from pathlib import Path

import aiohttp

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .api import SeedtimeApiClient
from .const import (
    CONF_EMAIL,
    CONF_ENABLE_CALENDAR,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_ENABLE_CALENDAR,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import SeedtimeDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Seedtime integration (YAML not supported)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Seedtime from a config entry."""
    # Create a dedicated aiohttp session for cookie isolation
    session = aiohttp.ClientSession()

    client = SeedtimeApiClient(
        session=session,
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
    )

    # Authenticate before creating coordinator
    try:
        await client.authenticate()
    except Exception:
        await session.close()
        raise

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = SeedtimeDataUpdateCoordinator(
        hass, client, update_interval=scan_interval
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Store session reference for cleanup
    entry.runtime_data = {"session": session}

    # Register static path for custom Lovelace card
    www_path = Path(__file__).parent / "www"
    if www_path.is_dir():
        try:
            await hass.http.async_register_static_paths(
                [StaticPathConfig("/seedtime", str(www_path), False)]
            )
        except Exception:  # noqa: BLE001
            # Path may already be registered from a previous load
            _LOGGER.debug("Static path /seedtime already registered")

    # Forward to platforms
    platforms = ["image"]
    if entry.options.get(CONF_ENABLE_CALENDAR, DEFAULT_ENABLE_CALENDAR):
        platforms.append("calendar")

    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    # Listen for options changes
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Seedtime config entry."""
    platforms = ["image"]
    if entry.options.get(CONF_ENABLE_CALENDAR, DEFAULT_ENABLE_CALENDAR):
        platforms.append("calendar")

    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

        # Close the dedicated aiohttp session
        runtime = getattr(entry, "runtime_data", None)
        if runtime and isinstance(runtime, dict):
            session = runtime.get("session")
            if session and not session.closed:
                await session.close()

    return unload_ok


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload entry to apply changes."""
    await hass.config_entries.async_reload(entry.entry_id)
