"""
ZiGate platform.

For more details about this platform, please refer to the documentation
https://home-assistant.io/components/sensor.zigate/
"""
import logging
import zigate

from homeassistant.exceptions import PlatformNotReady
from homeassistant.components.sensor import ENTITY_ID_FORMAT
from homeassistant.const import (DEVICE_CLASS_HUMIDITY,
                                 DEVICE_CLASS_TEMPERATURE,
                                 DEVICE_CLASS_ILLUMINANCE,
                                 DEVICE_CLASS_PRESSURE,
                                 DEVICE_CLASS_BATTERY,
                                 STATE_UNAVAILABLE)
from homeassistant.helpers.entity import Entity

from .core.const import DATA_ZIGATE_ATTRS, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config, async_add_entities):
    """Set up the ZiGate sensors."""

    myzigate = hass.data[DOMAIN]

    def sync_attributes(**kwargs):
        devs = []
        for device in myzigate.devices:
            ieee = device.ieee or device.addr  # compatibility
            actions = device.available_actions()
            if any(actions.values()):
                continue
            for attribute in device.attributes:
                if attribute['cluster'] < 5:
                    continue
                if 'name' in attribute:
                    key = '{}-{}-{}-{}'.format(ieee,
                                               attribute['endpoint'],
                                               attribute['cluster'],
                                               attribute['attribute'],
                                               )
                    value = attribute.get('value')
                    if value is None:
                        continue
                    if key in hass.data[DATA_ZIGATE_ATTRS]:
                        continue
                    if type(value) not in (bool, dict):
                        _LOGGER.debug(('Creating sensor '
                                       'for device '
                                       '{} {}').format(device,
                                                       attribute))
                        entity = ZiGateSensor(hass, device, attribute)
                        devs.append(entity)
                        hass.data[DATA_ZIGATE_ATTRS][key] = entity

        async_add_entities(devs)

    sync_attributes()
    zigate.dispatcher.connect(sync_attributes,
                              zigate.ZIGATE_ATTRIBUTE_ADDED, weak=False)


class ZiGateSensor(Entity):
    """Representation of a ZiGate sensor."""

    def __init__(self, hass, device, attribute):
        """Initialize the sensor."""
        self.hass = hass
        self._device = device
        self._attribute = attribute
        self._device_class = None
        self._state = attribute.get('value', STATE_UNAVAILABLE)
        name = attribute.get('name')
        ieee = device.ieee or device.addr  # compatibility
        entity_id = 'zigate_{}_{}'.format(ieee,
                                          name)
        self.entity_id = ENTITY_ID_FORMAT.format(entity_id)

        if 'temperature' in name:
            self._device_class = DEVICE_CLASS_TEMPERATURE
        elif 'humidity' in name:
            self._device_class = DEVICE_CLASS_HUMIDITY
        elif 'luminosity' in name:
            self._device_class = DEVICE_CLASS_ILLUMINANCE
        elif 'pressure' in name:
            self._device_class = DEVICE_CLASS_PRESSURE
        elif 'pressure' in name:
            self._device_class = DEVICE_CLASS_BATTERY

    def _handle_event(self, call):
        if (
            self._device.ieee == call.data['ieee']
            and self._attribute['endpoint'] == call.data['endpoint']
            and self._attribute['cluster'] == call.data['cluster']
            and self._attribute['attribute'] == call.data['attribute']
        ):
            _LOGGER.debug("Event received: %s", call.data)
            self._state = call.data['value']
            if not self.hass:
                raise PlatformNotReady
            self.schedule_update_ha_state()

    @property
    def unique_id(self) -> str:
        if self._device.ieee:
            return '{}-{}-{}-{}'.format(self._device.ieee,
                                        self._attribute['endpoint'],
                                        self._attribute['cluster'],
                                        self._attribute['attribute'],
                                        )

    @property
    def should_poll(self):
        """No polling needed for a ZiGate sensor."""
        return False

    @property
    def device_class(self):
        """Return the device class of the sensor."""
        return self._device_class

    @property
    def name(self):
        """Return the name of the sensor."""
        return '{} {}'.format(self._attribute.get('name'),
                              self._device)

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit this state is expressed in."""
        return self._attribute.get('unit')

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        attrs = {
            'addr': self._device.addr,
            'ieee': self._device.ieee,
            'endpoint': '0x{:02x}'.format(self._attribute['endpoint']),
            'cluster': '0x{:04x}'.format(self._attribute['cluster']),
            'attribute': '0x{:04x}'.format(self._attribute['attribute'])
        }
        state = self.state
        if isinstance(self.state, dict):
            attrs.update(state)
        return attrs

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.unique_id), (DOMAIN, self._device.ieee)},
            "manufacturer": self._device.get_value('manufacturer'),
            "model": self._device.get_value('type'),
            "name": str(self._device),
            "via_device": (DOMAIN, self._device.ieee),
        }

    async def async_added_to_hass(self):
        """Connect dispatcher."""
        self.hass.bus.async_listen('zigate.attribute_updated', self._handle_event)
