import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from . import linky_parser # Import the TIC parsing utility

_LOGGER = logging.getLogger(__name__)

DOMAIN = "esplinky"
PLATFORMS = ["sensor"]

CONF_PORT = "port"
DEFAULT_PORT = 8095
EVENT_NEW_TIC_DATA = f"{DOMAIN}_new_data"

class EsplinkyUDPProtocol(asyncio.DatagramProtocol):
    """Protocol for receiving UDP datagrams."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the protocol."""
        self.hass = hass
        self.transport = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        """Called when a connection is made (socket is bound)."""
        _LOGGER.debug("UDP Listener connection established")
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        """Called when a datagram is received."""
        _LOGGER.debug("Datagram received from %s:%s - length %d", addr[0], addr[1], len(data))
        
        # 1. Parse the raw frame
        tic_data = linky_parser.parse_tic_frame(data)

        if tic_data:
            _LOGGER.info("Successfully parsed and validated %d Linky values. Firing HA event.", len(tic_data))
            
            # 2. Fire HA event with the validated data
            # Sensors will subscribe to this event to update their state
            self.hass.bus.fire(EVENT_NEW_TIC_DATA, {"data": tic_data})
        else:
            _LOGGER.warning("Received TIC frame contained no valid data or was empty.")

    def connection_lost(self, exc: Exception | None) -> None:
        """Called when the connection is lost."""
        _LOGGER.warning("UDP Listener connection lost: %s", exc)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Esplinky from a config entry."""
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    
    # Store the component setup in the hass data store
    hass.data.setdefault(DOMAIN, {})
    
    # Start the UDP Listener
    try:
        # Create a UDP endpoint bound to all interfaces (0.0.0.0)
        transport, protocol = await hass.loop.create_datagram_endpoint(
            lambda: EsplinkyUDPProtocol(hass),
            local_addr=('0.0.0.0', port)
        )
        hass.data[DOMAIN]["transport"] = transport
        _LOGGER.info("Started UDP listener on port %d for Esplinky data.", port)
        
    except OSError as err:
        _LOGGER.error("Failed to bind UDP socket on port %d: %s", port, err)
        raise ConfigEntryNotReady(f"Failed to bind UDP socket on port {port}") from err
        
    # Set up the sensor platform
    await hass.config_entries.async_forward_entry_setup(entry, "sensor")

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload the sensor platform
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    
    # Close the UDP transport
    transport = hass.data[DOMAIN].pop("transport", None)
    if transport:
        transport.close()
        _LOGGER.info("Closed UDP listener.")

    # Clean up the domain data
    if not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)

    return unload_ok

# Dummy Config Flow (required because config_flow: true in manifest)
# This allows the user to configure the port via the HA UI.

from homeassistant.config_entries import ConfigFlow
from homeassistant.data_entry_flow import FlowResult
import voluptuous as vol

DATA_SCHEMA = vol.Schema({
    vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int)
})

class EsplinkyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Esplinky."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Check for duplicates
            await self.async_set_unique_id(DOMAIN)
            self.hass.async_set_config_entry_flow_manager(DOMAIN, self)
            
            # Create the configuration entry
            return self.async_create_entry(title="Esplinky UDP Listener", data=user_input)

        # Show form
        return self.async_show_form(
            step_id="user", 
            data_schema=DATA_SCHEMA, 
            errors=errors
        )

