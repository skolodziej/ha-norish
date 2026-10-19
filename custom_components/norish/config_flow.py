"""Config flow for Norish."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import probatio
from yarl import URL

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    NorishAuthError,
    NorishClient,
    NorishConnectionError,
    NorishError,
    normalize_url,
)
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_SHOW_STORE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SHOW_STORE,
    DOMAIN,
    LOGGER,
    MIN_SCAN_INTERVAL,
)
from .coordinator import NorishConfigEntry

API_KEY_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

USER_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_URL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
        probatio.Required(CONF_API_KEY): API_KEY_SELECTOR,
    }
)
REAUTH_SCHEMA = probatio.Schema({probatio.Required(CONF_API_KEY): API_KEY_SELECTOR})


class NorishConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Norish."""

    VERSION = 1

    async def _async_validate(self, url: str, api_key: str) -> str | None:
        """Validate the credentials. Return an error key or None."""
        client = NorishClient(async_get_clientsession(self.hass), url, api_key)
        try:
            await client.async_get_groceries()
        except NorishAuthError:
            return "invalid_auth"
        except NorishConnectionError:
            return "cannot_connect"
        except NorishError:
            return "unexpected_response"
        except Exception:  # noqa: BLE001
            LOGGER.exception("Unexpected error while validating Norish")
            return "unknown"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            try:
                url = normalize_url(user_input[CONF_URL])
            except ValueError:
                errors[CONF_URL] = "invalid_url"
            else:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                if not (error := await self._async_validate(url, api_key)):
                    return self.async_create_entry(
                        title=URL(url).host or "Norish",
                        data={CONF_URL: url, CONF_API_KEY: api_key},
                    )
                errors["base"] = error
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, {CONF_URL: (user_input or {}).get(CONF_URL)}
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauth after the API key was rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new API key."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            if not (error := await self._async_validate(entry.data[CONF_URL], api_key)):
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: api_key}
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            description_placeholders={"url": entry.data[CONF_URL]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: NorishConfigEntry) -> NorishOptionsFlow:
        """Return the options flow."""
        return NorishOptionsFlow()


class NorishOptionsFlow(OptionsFlowWithReload):
    """Options for Norish."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_SHOW_STORE: user_input[CONF_SHOW_STORE],
                }
            )
        options = self.config_entry.options
        schema = probatio.Schema(
            {
                probatio.Required(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=3600,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                probatio.Required(
                    CONF_SHOW_STORE,
                    default=options.get(CONF_SHOW_STORE, DEFAULT_SHOW_STORE),
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
