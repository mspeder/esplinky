"""Sensor platform for the ESPLinky integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, Event # <-- Import Event object
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.const import UnitOfPower, UnitOfEnergy # Example units

from . import DOMAIN, EVENT_NEW_TIC_DATA, CONF_PORT

_LOGGER = logging.getLogger(__name__)

# Dictionary to map Linky label names to Home Assistant sensor properties (units, icons, etc.)
# This mapping is crucial for making the data meaningful in HA.
LINKY_MAPPING = {
    # Consumption (Total Energy)
    "BASE": {"name": "Total Consumption (BASE)", "unit": UnitOfEnergy.WATT_HOUR, "icon": "mdi:counter"},
    "HCHP": {"name": "Consumption (Peak Hours)", "unit": UnitOfEnergy.WATT_HOUR, "icon": "mdi:counter"},
    "HCHC": {"name": "Consumption (Off-Peak Hours)", "unit": UnitOfEnergy.WATT_HOUR, "icon": "mdi:counter"},
    # Instantaneous Power
    "IINST": {"name": "Instantaneous Current (Total)", "unit": "A", "icon": "mdi:flash"},
    "PAPP": {"name": "Apparent Power", "unit": "VA", "icon": "mdi:lightning-bolt"},
    # Tariff Information
    "PTEC": {"name": "Current Tariff Period", "unit": None, "icon": "mdi:cash-multiple"},
    # Other important values (adjust as needed for your specific Linky meter)
    "ADCO": {"name": "Meter Address", "unit": None, "icon": "mdi:identifier"},
    "OPTARIF": {"name": "Tariff Option", "unit": None, "icon": "mdi:tag"},
}

# In-memory store for currently tracked sensors
TRACKED_SENSORS: dict[str, EsplinkySensor] = {}

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    
    # Store the async_add_entities callback for later use when new sensors appear
    hass.data[DOMAIN][config_entry.entry_id] = async_add_entities

    @callback
    def handle_new_data(event: Event) -> None: 
        """Handle new data event fired by the UDP listener."""
        new_sensors: list[EsplinkySensor] = []
        
        # CORRECTED: Access the payload via event.data
        tic_data: dict[str, str] = event.data["data"] 

        for label, value in tic_data.items():
            # Only create sensors for labels we have a mapping for, or if they are PAPP/IINST etc.
            if label not in LINKY_MAPPING:
                # Dynamically add mapping for unknown labels (e.g., custom data)
                LINKY_MAPPING[label] = {"name": label, "unit": None, "icon": "mdi:gauge"}

            # Check if this sensor already exists
            if label not in TRACKED_SENSORS:
                _LOGGER.debug("Creating new sensor for Linky label: %s", label)
                
                # Create the new sensor entity
                sensor = EsplinkySensor(config_entry, label, value)
                TRACKED_SENSORS[label] = sensor
                new_sensors.append(sensor)
            else:
                # Update existing sensor with new value
                TRACKED_SENSORS[label].update_state_value(value)

        # Add any newly created sensors to Home Assistant
        if new_sensors:
            async_add_entities(new_sensors)

    # Subscribe to the event fired by __init__.py when new data arrives
    config_entry.async_on_unload(
        hass.bus.async_listen(EVENT_NEW_TIC_DATA, handle_new_data)
    )


class EsplinkySensor(SensorEntity):
    """Representation of a Linky TIC sensor."""

    def __init__(self, config_entry: ConfigEntry, label: str, initial_value: Any) -> None:
        """Initialize the sensor."""
        self._label = label
        self._attr_name = LINKY_MAPPING[label].get("name", label)
        self._attr_unique_id = f"{config_entry.unique_id}_{label}"
        self._attr_native_value = self._sanitize_value(initial_value)
        self._attr_unit_of_measurement = LINKY_MAPPING[label].get("unit")
        self._attr_icon = LINKY_MAPPING[label].get("icon")
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": f"ESPLinky (Port {config_entry.data.get(CONF_PORT)})", # <-- Updated name
            "model": "Linky TIC Listener",
            "manufacturer": "esplinky",
        }

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self._attr_native_value

    def _sanitize_value(self, value: str) -> StateType:
        """Attempt to convert string value to int/float if possible, otherwise return string."""
        
        # Strip leading/trailing whitespace/control characters first, 
        # as Home Assistant requires a Python int/float for numeric sensors.
        cleaned_value = value.strip()
        
        try:
            # TIC values are often large integers (e.g., Wh)
            return int(cleaned_value)
        except ValueError:
            try:
                # Handle potential float values (less common in standard TIC)
                return float(cleaned_value)
            except ValueError:
                # Return the cleaned string if conversion fails (e.g., PTEC, ADCO, etc.)
                return cleaned_value

    @callback
    def update_state_value(self, new_value: str) -> None:
        """Update the sensor's state value and schedule state refresh."""
        new_sanitized_value = self._sanitize_value(new_value)
        
        # Only update if the value has actually changed
        if new_sanitized_value != self._attr_native_value:
            self._attr_native_value = new_sanitized_value
            self.async_write_ha_state() # Notify HA of the state change
            _LOGGER.debug("Sensor %s updated state to: %s", self._label, new_sanitized_value)
