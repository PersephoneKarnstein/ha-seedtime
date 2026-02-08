"""Config flow for Seedtime integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .api import SeedtimeApiClient, SeedtimeAuthError, SeedtimeConnectionError
from .const import (
    CONF_EMAIL,
    CONF_ENABLE_CALENDAR,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_ENABLE_CALENDAR,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class SeedtimeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Seedtime."""

    VERSION = 1

    def __init__(self) -> None:
        self._reauth_entry: ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SeedtimeOptionsFlow:
        """Get the options flow handler."""
        return SeedtimeOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: email + password."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL].strip().lower()
            password = user_input[CONF_PASSWORD]

            # Check if already configured
            await self.async_set_unique_id(email)
            self._abort_if_unique_id_configured()

            # Validate credentials
            session = aiohttp.ClientSession()
            try:
                client = SeedtimeApiClient(session, email, password)
                await client.validate_credentials()
            except SeedtimeAuthError:
                errors["base"] = "invalid_auth"
            except SeedtimeConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during Seedtime login")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Seedtime ({email})",
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                    },
                    options={
                        CONF_ENABLE_CALENDAR: DEFAULT_ENABLE_CALENDAR,
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                    },
                )
            finally:
                await session.close()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauth triggered by expired session."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauth confirmation step."""
        errors: dict[str, str] = {}
        assert self._reauth_entry is not None
        existing_email = self._reauth_entry.data[CONF_EMAIL]

        if user_input is not None:
            password = user_input[CONF_PASSWORD]

            session = aiohttp.ClientSession()
            try:
                client = SeedtimeApiClient(session, existing_email, password)
                await client.validate_credentials()
            except SeedtimeAuthError:
                errors["base"] = "invalid_auth"
            except SeedtimeConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during Seedtime reauth")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={
                        CONF_EMAIL: existing_email,
                        CONF_PASSWORD: password,
                    },
                )
                await self.hass.config_entries.async_reload(
                    self._reauth_entry.entry_id
                )
                return self.async_abort(reason="reauth_successful")
            finally:
                await session.close()

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
            description_placeholders={"email": existing_email},
        )


class SeedtimeOptionsFlow(OptionsFlow):
    """Handle options for Seedtime."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_ENABLE_CALENDAR,
                        default=current.get(
                            CONF_ENABLE_CALENDAR, DEFAULT_ENABLE_CALENDAR
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=current.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                }
            ),
        )
