"""Config flow for Esplinky integration."""

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, FlowResult
from homeassistant.data_entry_flow import FlowResult

from . import DOMAIN, CONF_PORT, DEFAULT_PORT

# Define the schema for the configuration form
DATA_SCHEMA = vol.Schema({
    vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int)
})

class EsplinkyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Esplinky."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        
        # Check if an entry already exists and prevent multiple instances
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
            
        errors: dict[str, str] = {}
        
        if user_input is not None:
            # Set a unique ID for the single instance of this integration
            await self.async_set_unique_id(DOMAIN)
            
            # Create the configuration entry with the user-provided port
            return self.async_create_entry(title="Esplinky UDP Listener", data=user_input)

        # Show form to configure the port
        return self.async_show_form(
            step_id="user", 
            data_schema=DATA_SCHEMA, 
            errors=errors
        )
