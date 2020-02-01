"""
ZiGate platform.

For more details about this platform, please refer to the documentation
https://home-assistant.io/components/switch.zigate/
"""
import logging
import zigate

from homeassistant.exceptions import PlatformNotReady
from homeassistant.components.switch import SwitchDevice, ENTITY_ID_FORMAT

from .core.const import DATA_ZIGATE_ATTRS, DOMAIN as DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config, async_add_entities):
    """Set up the ZiGate sensors."""

    myzigate = hass.data[DOMAIN]

    def sync_attributes():
        devs = []
        for device in myzigate.devices:
            ieee = device.ieee or device.addr  # compatibility
            actions = device.available_actions()
            if not any(actions.values()):
                continue
            for endpoint, action_type in actions.items():
                if [zigate.ACTIONS_ONOFF] == action_type:
                    key = '{}-{}-{}'.format(ieee, 'switch', endpoint)
                    if key in hass.data[DATA_ZIGATE_ATTRS]:
                        continue
                    _LOGGER.debug(F"Creating switch for device {device} {endpoint}")
                    entity = ZiGateSwitch(hass, device, endpoint)
                    devs.append(entity)
                    hass.data[DATA_ZIGATE_ATTRS][key] = entity

        async_add_entities(devs)
    sync_attributes()
    zigate.dispatcher.connect(
        sync_attributes, zigate.ZIGATE_ATTRIBUTE_ADDED, weak=False
    )


class ZiGateSwitch(SwitchDevice):
    """Representation of a ZiGate switch."""

    def __init__(self, hass, device, endpoint):
        """Initialize the ZiGate switch."""
        self.hass = hass
        self._device = device
        self._endpoint = endpoint
        self._is_on = False
        a = self._device.get_attribute(endpoint, 6, 0)
        if a:
            self._is_on = a.get('value', False)
        ieee = device.ieee or device.addr  # compatibility
        entity_id = 'zigate_{}_{}'.format(ieee,
                                          endpoint)
        self.entity_id = ENTITY_ID_FORMAT.format(entity_id)

    def _handle_event(self, call):
        if (
            self._device.ieee == call.data['ieee']
            and self._endpoint == call.data['endpoint']
        ):
            _LOGGER.debug("Event received: %s", call.data)
            if call.data['cluster'] == 6 and call.data['attribute'] == 0:
                self._is_on = call.data['value']
            if not self.hass:
                raise PlatformNotReady
            self.schedule_update_ha_state()

    @property
    def unique_id(self) -> str:
        if self._device.ieee:
            return '{}-{}-{}'.format(
                self._device.ieee, 'switch', self._endpoint)

    @property
    def should_poll(self):
        """No polling needed for a ZiGate switch."""
        return False

    def update(self):
        self._device.refresh_device()

    @property
    def name(self):
        """Return the name of the device if any."""
        return '{} {}'.format(self._device,
                              self._endpoint)

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._is_on

    def turn_on(self, **kwargs):
        """Turn the switch on."""
        self._is_on = True
        self.schedule_update_ha_state()
        self.hass.data[DOMAIN].action_onoff(
            self._device.addr, self._endpoint, 1)

    def turn_off(self, **kwargs):
        """Turn the device off."""
        self._is_on = False
        self.schedule_update_ha_state()
        self.hass.data[DOMAIN].action_onoff(
            self._device.addr, self._endpoint, 0)

    def toggle(self, **kwargs):
        """Toggle the device"""
        self._is_on = not self._is_on
        self.schedule_update_ha_state()
        self.hass.data[DOMAIN].action_onoff(
            self._device.addr, self._endpoint, 2)

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return {
            'addr': self._device.addr,
            'ieee': self._device.ieee,
            'endpoint': '0x{:02x}'.format(self._endpoint),
        }

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.unique_id), (DOMAIN, self._device.ieee)},
            "manufacturer": self._device.get_value('manufacturer'),
            "model": self._device.get_value('type'),
            "name": str(self._device),
            "via_device": (DOMAIN, self._device.ieee),
        }

#     @property
#     def assumed_state(self)->bool:
#         return self._device.assumed_state

    async def async_added_to_hass(self):
        """Connect dispatcher."""
        self.hass.bus.async_listen('zigate.attribute_updated', self._handle_event)
