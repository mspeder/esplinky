"""Sensor platform for Esplinky."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, EVENT_NEW_TIC_DATA
import logging

_LOGGER = logging.getLogger(__name__)

# Map common TIC labels to HA sensor properties (units, icons, etc.)
TIC_LABEL_MAP = {
    # Energy indices (Wh/A)
    "BASE": {"name": "Index Base", "unit": "Wh", "icon": "mdi:counter", "device_class": "energy"},
    "HCHC": {"name": "Index Heures Creuses", "unit": "Wh", "icon": "mdi:counter", "device_class": "energy"},
    "HCHP": {"name": "Index Heures Pleines", "unit": "Wh", "icon": "mdi:counter", "device_class": "energy"},
    "EASF01": {"name": "Energie Active F1", "unit": "Wh", "icon": "mdi:counter", "device_class": "energy"},
    "EASF02": {"name": "Energie Active F2", "unit": "Wh", "icon": "mdi:counter", "device_class": "energy"},
    
    # Instantaneous values (W/A)
    "IINST": {"name": "Intensité Instantanée", "unit": "A", "icon": "mdi:current-ac"},
    "PAPP": {"name": "Puissance Apparente", "unit": "VA", "icon": "mdi:flash", "device_class": "apparent_power"},
    
    # Misc
    "ADCO": {"name": "Adresse Compteur", "unit": None, "icon": "mdi:tag-multiple", "category": EntityCategory.DIAGNOSTIC},
    "IMAX": {"name": "Intensité Max Appelée", "unit": "A", "icon": "mdi:current-ac", "category": EntityCategory.DIAGNOSTIC},
    "HHPHC": {"name": "Horaire Heures Pleines/Creuses", "unit": None, "icon": "mdi:clock-outline", "category": EntityCategory.DIAGNOSTIC},
    "MOTDETAT": {"name": "Mot d'État", "unit": None, "icon": "mdi:information-outline", "category": EntityCategory.DIAGNOSTIC},
    "ISOUSC": {"name": "Intensité Souscrite", "unit": "A", "icon": "mdi:current-ac", "category": EntityCategory.DIAGNOSTIC},
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Esplinky sensor platform."""
    
    # Store dynamic entities for creation later
    # We delay entity creation until the first data packet arrives to know all labels
    hass.data[DOMAIN]["pending_entities"] = []
    
    @callback
    def _handle_new_data(event):
        """Handle the event fired by the UDP listener when new data is available."""
        tic_data = event.data.get("data", {})
        
        new_entities = []
        
        # Check if we have received data for the first time
        if not hass.data[DOMAIN].get("initial_entities_added"):
            _LOGGER.debug("First data received. Creating dynamic sensors.")
            
            # Create a sensor for every unique label found in the data
            for label, value in tic_data.items():
                if label not in hass.data[DOMAIN]["pending_entities"]:
                    entity = EsplinkySensor(config_entry, label, value)
                    new_entities.append(entity)
                    hass.data[DOMAIN]["pending_entities"].append(label) # Mark as pending/added

            if new_entities:
                async_add_entities(new_entities)
                hass.data[DOMAIN]["initial_entities_added"] = True

        # Update all existing sensors
        for entity in hass.data[DOMAIN].get("pending_entities", []):
            hass.bus.async_fire(f"{DOMAIN}_update_{entity}", {"value": tic_data.get(entity)})

    # Subscribe to the HA event fired by the UDP listener
    config_entry.async_on_unload(
        hass.bus.async_listen(EVENT_NEW_TIC_DATA, _handle_new_data)
    )


class EsplinkySensor(SensorEntity):
    """Representation of a Linky TIC sensor."""

    def __init__(self, config_entry: ConfigEntry, label: str, initial_value: Any) -> None:
        """Initialize the sensor."""
        self._config_entry = config_entry
        self._label = label
        self._attr_native_value = initial_value
        self._attr_unique_id = f"{config_entry.unique_id}_{label}"
        
        # Get metadata from the label map, or use default if not found
        metadata = TIC_LABEL_MAP.get(label, {})
        
        # Set attributes based on metadata
        self._attr_name = metadata.get("name", label.replace('_', ' ').title())
        self._attr_native_unit_of_measurement = metadata.get("unit")
        self._attr_icon = metadata.get("icon", "mdi:meter-electric")
        self._attr_device_class = metadata.get("device_class")
        self._attr_entity_category = metadata.get("category")
        
        # Use the config entry ID as part of the device identifier
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": "Esplinky UDP",
            "manufacturer": "esplinky",
            "model": "Linky TIC Historic",
        }
        
    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added to HA."""
        
        @callback
        def _update_state_from_event(event):
            """Update the sensor state from the received event data."""
            new_value = event.data.get("value")
            if new_value is not None and new_value != self._attr_native_value:
                self._attr_native_value = new_value
                self.async_write_ha_state()

        # Listen to a specific update event for this sensor's label
        self.async_on_remove(
            self.hass.bus.async_listen(f"{DOMAIN}_update_{self._label}", _update_state_from_event)
        )
        
    @property
    def should_poll(self) -> bool:
        """Data is pushed, so no need to poll."""
        return False

