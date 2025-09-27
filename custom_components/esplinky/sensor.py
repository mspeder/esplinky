"""Sensor platform for the ESPLinky integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, Event 
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.const import UnitOfPower, UnitOfEnergy 

from . import DOMAIN, EVENT_NEW_TIC_DATA, CONF_PORT, DEFAULT_PORT # <-- FIX A: Added DEFAULT_PORT

_LOGGER = logging.getLogger(__name__)

# Dictionary to map Linky label names to Home Assistant sensor properties.
# StateClass constants are intentionally replaced with string values for compatibility.
LINKY_MAPPING = {
    # Consumption (Total Energy) - MUST be total_increasing for Energy Dashboard
    # Unit changed to KILO_WATT_HOUR, and conversion logic is added in _sanitize_value
    "BASE": {
        "name": "Total Consumption (BASE)", 
        "unit": UnitOfEnergy.KILO_WATT_HOUR, # <-- CHANGED to kWh
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.ENERGY, 
        "state_class": "total_increasing",
    },
    "HCHP": {
        "name": "Consumption (Peak Hours)", 
        "unit": UnitOfEnergy.KILO_WATT_HOUR, # <-- CHANGED to kWh
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.ENERGY, 
        "state_class": "total_increasing",
    },
    "HCHC": {
        "name": "Consumption (Off-Peak Hours)", 
        "unit": UnitOfEnergy.KILO_WATT_HOUR, # <-- CHANGED to kWh
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.ENERGY, 
        "state_class": "total_increasing",
    },
    # Instantaneous Power (Current reading, not cumulative)
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
    # Tariff Information (String/Text values)
    "PTEC": {"name": "Current Tariff Period", "unit": None, "icon": "mdi:cash-multiple", "device_class": None, "state_class": None},
    "ADCO": {"name": "Meter Address", "unit": None, "icon": "mdi:identifier", "device_class": None, "state_class": None},
    "OPTARIF": {"name": "Tariff Option", "unit": None, "icon": "mdi:tag", "device_class": None, "state_class": None},
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
    # This is a common pattern for integrations that discover entities dynamically.
    hass.data[DOMAIN][config_entry.entry_id] = async_add_entities

    @callback
    def handle_new_data(event: Event) -> None: 
        """Handle new data event fired by the UDP listener."""
        new_sensors: list[EsplinkySensor] = []
        
        # Access the payload via event.data
        tic_data: dict[str, str] = event.data["data"] 

        for label, value in tic_data.items():
            # Dynamically handle unknown labels
            if label not in LINKY_MAPPING:
                _LOGGER.warning("Encountered unknown Linky label: %s. Using default settings.", label)
                # Add the unknown label to the mapping dictionary with basic defaults
                LINKY_MAPPING[label] = {"name": label, "unit": None, "icon": "mdi:gauge", "device_class": None, "state_class": None}

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
        
        # Unique ID uses entry ID and the Linky label
        self._attr_unique_id = f"{config_entry.unique_id}_{label}"
        
        # Set attributes from the mapping dictionary
        self._attr_name = mapping.get("name", label)
        self._attr_unit_of_measurement = mapping.get("unit")
        self._attr_device_class = mapping.get("device_class") 
        self._attr_state_class = mapping.get("state_class")    
        self._attr_icon = mapping.get("icon")
        
        # Apply initial value after sanitization
        self._attr_native_value = self._sanitize_value(initial_value)
        
        # Define Device Info to group all sensors under one virtual device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": f"ESPLinky (Port {config_entry.data.get(CONF_PORT, DEFAULT_PORT)})", # <-- FIX B: Added DEFAULT_PORT as fallback
            "model": "Linky TIC Listener",
            "manufacturer": "esplinky",
        }

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self._attr_native_value

    def _sanitize_value(self, value: str) -> StateType:
        """Attempt to convert string value to int/float if possible, otherwise return string.
        Applies Wh to kWh conversion for energy sensors.
        """
        
        cleaned_value = value.strip()
        
        try:
            # Prioritize integer conversion (common for energy meters)
            numerical_value = int(cleaned_value)
            
            # Energy data from Linky is typically in Wh. If the sensor is one of the energy total
            # labels, and we set the output unit to kWh, perform the conversion.
            if self._label in ["BASE", "HCHP", "HCHC"]:
                if self._attr_unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR:
                    # Conversion from Wh (input) to kWh (output unit)
                    return numerical_value / 1000.0
            
            return numerical_value
            
        except ValueError:
            # Fallback to float conversion if int fails
            try:
                return float(cleaned_value)
            except ValueError:
                # Fallback to string (for tariff/meter info)
                return cleaned_value

    @callback
    def update_state_value(self, new_value: str) -> None:
        """Update the sensor's state value and schedule state refresh."""
        new_sanitized_value = self._sanitize_value(new_value)
        
        # Only update if the value has actually changed to minimize HA writes
        if new_sanitized_value != self._attr_native_value:
            self._attr_native_value = new_sanitized_value
            self.async_write_ha_state() 
            _LOGGER.debug("Sensor %s updated state to: %s", self._label, new_sanitized_value)