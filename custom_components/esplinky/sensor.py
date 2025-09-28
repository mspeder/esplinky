"""Sensor platform for the ESPLinky integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass 
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, Event 
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import DOMAIN, EVENT_NEW_TIC_DATA, CONF_PORT

_LOGGER = logging.getLogger(__name__)

# Dictionary to map Linky label names to Home Assistant sensor properties (units, icons, etc.)
LINKY_MAPPING = {
    # Consumption (Total Energy) - Configured for Energy Dashboard
    "BASE": {
        "name": "Total Consumption (BASE)", 
        "unit": "Wh",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.ENERGY, 
        "state_class": "total_increasing", 
    },
    "HCHP": {
        "name": "Consumption (Peak Hours)", 
        "unit": "Wh",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.ENERGY, 
        "state_class": "total_increasing", 
    },
    "HCHC": {
        "name": "Consumption (Off-Peak Hours)", 
        "unit": "Wh",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.ENERGY, 
        "state_class": "total_increasing", 
    },
    # Instantaneous Power and Current
    "IINST": {
        "name": "Instantaneous Current (Total)", 
        "unit": "A",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.CURRENT, 
        "state_class": "measurement", 
    },
    "PAPP": {
        "name": "Apparent Power", 
        "unit": "VA",
        "icon": "mdi:lightning-bolt",
        "device_class": SensorDeviceClass.APPARENT_POWER, 
        "state_class": "measurement", 
    },
    # Tariff and Configuration Information
    "PTEC": {
        "name": "Current Tariff Period", 
        "unit": None, 
        "icon": "mdi:cash-multiple", 
        "device_class": None, 
        "state_class": None
    },
    "ADCO": {
        "name": "Meter Address", 
        "unit": None, 
        "icon": "mdi:identifier", 
        "device_class": None, 
        "state_class": None
    },
    "OPTARIF": {
        "name": "Tariff Option", 
        "unit": None, 
        "icon": "mdi:tag", 
        "device_class": None, 
        "state_class": None
    },
    # Current-related sensors
    "ISOUSC": {
        "name": "Subscribed Current", 
        "unit": "A",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.CURRENT, 
        "state_class": None,
    },
    "IMAX": {
        "name": "Max Current Called", 
        "unit": "A",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.CURRENT, 
        "state_class": "measurement", 
    },
    # Additional sensors
    "HHPHC": {
        "name": "Hour/Day Code", 
        "unit": None, 
        "icon": "mdi:clock-outline", 
        "device_class": None, 
        "state_class": None,
    },
    "MOTDETAT": {
        "name": "Meter Status", 
        "unit": None, 
        "icon": "mdi:alert-circle-outline", 
        "device_class": None, 
        "state_class": None,
    },
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
        
        # Access the payload via event.data
        tic_data: dict[str, str] = event.data["data"] 

        for label, value in tic_data.items():
            # Dynamically handle truly unknown labels 
            if label not in LINKY_MAPPING:
                _LOGGER.warning("Encountered unknown Linky label: %s. Using default settings.", label)
                # Ensure unknown labels are added to the mapping before sensor creation
                LINKY_MAPPING[label] = {
                    "name": label, 
                    "unit": None, 
                    "icon": "mdi:gauge", 
                    "device_class": None, 
                    "state_class": None
                }

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
            # Check if the async_add_entities callback is still the same object before calling
            if hass.data[DOMAIN].get(config_entry.entry_id) is async_add_entities:
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
        mapping = LINKY_MAPPING[label]
        
        self._attr_name = mapping["name"]
        self._attr_unique_id = f"{config_entry.unique_id}_{label}"
        self._attr_native_value = self._sanitize_value(initial_value)
        
        # Apply the required attributes - ensure units are properly set
        unit = mapping["unit"]
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = mapping["device_class"] 
        self._attr_state_class = mapping["state_class"]   
        self._attr_icon = mapping["icon"]
        
        # Debug logging to verify units are set correctly
        _LOGGER.debug("Creating sensor %s with unit: %s, device_class: %s", 
                     label, unit, mapping["device_class"])
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": f"ESPLinky (Port {config_entry.data.get(CONF_PORT)})", 
            "model": "Linky TIC Listener",
            "manufacturer": "esplinky",
        }

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self._attr_native_value

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement."""
        return self._attr_native_unit_of_measurement

    def _sanitize_value(self, value: str) -> StateType:
        """Attempt to convert string value to int/float if possible, otherwise return string."""
        
        cleaned_value = value.strip()
        
        try:
            # TIC energy values are typically large integers
            return int(cleaned_value)
        except ValueError:
            try:
                # Handle potential float values
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
            self.async_write_ha_state() 
            _LOGGER.debug("Sensor %s updated state to: %s", self._label, new_sanitized_value)