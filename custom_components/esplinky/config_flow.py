"""Config flow for the ESPLinky integration."""

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from . import DOMAIN, DEFAULT_PORT

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
    }
)

class EsplinkyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ESPLinky."""

    VERSION = 1
    # Setting unique_id ensures only one instance can be configured
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        
        # Check if already configured
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
            
        errors: dict[str, str] = {}
        
        if user_input is not None:
            # We don't need to validate the port, cv.port handles it.
            # We just need to ensure the user isn't configuring multiple times.
            
            # Create a fixed unique ID, as there should only be one UDP listener
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(title="ESPLinky", data=user_input)
            
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
