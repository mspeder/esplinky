"""The ESPLinky integration."""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_call_later

from .linky_parser import parse_tic_frame

_LOGGER = logging.getLogger(__name__)

DOMAIN = "esplinky"
EVENT_NEW_TIC_DATA = f"{DOMAIN}_new_data"
PLATFORMS: list[str] = ["sensor"]

# Default UDP port for Linky data
DEFAULT_PORT = 8095

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ESPLinky from a config entry."""
    
    # Store configuration data (listener instance) in hass.data
    hass.data.setdefault(DOMAIN, {})

    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    
    listener = EsplinkyListener(hass, entry, port)
    
    try:
        await listener.async_start()
    except OSError as err:
        _LOGGER.error("Failed to bind UDP socket on port %s: %s", port, err)
        raise ConfigEntryNotReady(f"Failed to start UDP listener on port {port}") from err

    hass.data[DOMAIN][entry.entry_id] = listener
    
    # Forward the setup to the sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok and entry.entry_id in hass.data[DOMAIN]:
        listener: EsplinkyListener = hass.data[DOMAIN].pop(entry.entry_id)
        await listener.async_stop()
    
    return unload_ok

class EsplinkyListener:
    """Handles the UDP socket listening and data processing."""
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, port: int) -> None:
        """Initialize the UDP listener."""
        self.hass = hass
        self.entry = entry
        self.port = port
        self._transport = None
        
        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"ESPLinky (Port {port})", # <-- Updated name
            model="Linky TIC Listener",
            manufacturer="esplinky",
        )

    async def async_start(self) -> None:
        """Start the UDP listener socket."""
        loop = asyncio.get_event_loop()
        # Bind to 0.0.0.0 (all interfaces)
        self._transport, protocol = await loop.create_datagram_endpoint(
            lambda: LinkyUDPProtocol(self.hass),
            local_addr=('0.0.0.0', self.port)
        )
        _LOGGER.info("UDP listener started on port %s", self.port)

    async def async_stop(self) -> None:
        """Stop the UDP listener socket."""
        if self._transport:
            self._transport.close()
            _LOGGER.info("UDP listener stopped on port %s", self.port)

class LinkyUDPProtocol(asyncio.DatagramProtocol):
    """Protocol to handle incoming UDP packets."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the protocol."""
        self.hass = hass

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """Called when connection is made."""
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        """Handle incoming UDP datagrams."""
        ip, port = addr
        _LOGGER.debug("Received datagram from %s:%s. Length: %d", ip, port, len(data))
        
        # Process the raw TIC frame
        tic_data = parse_tic_frame(data)
        
        if tic_data:
            _LOGGER.info("Successfully parsed and validated %d Linky values. Firing HA event.", len(tic_data))
            
            # Fire a Home Assistant event with the validated data
            self.hass.bus.fire(EVENT_NEW_TIC_DATA, {"data": tic_data})
        else:
            _LOGGER.warning("Received UDP packet but could not extract any valid Linky data. Checksum errors or incorrect format.")

    def error_received(self, exc: Exception) -> None:
        """Handle error receiving datagram."""
        _LOGGER.error("UDP Error received: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        """Called when connection is lost or closed."""
        _LOGGER.warning("UDP listener connection lost: %s", exc)
