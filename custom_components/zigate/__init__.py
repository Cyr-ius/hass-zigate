"""
ZiGate component.

For more details about this platform, please refer to the documentation
https://home-assistant.io/components/zigate/
"""
import logging
import voluptuous as vol
import os
import datetime
import zigate

from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.components.group import \
    ENTITY_ID_FORMAT as GROUP_ENTITY_ID_FORMAT
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL
)


from .const import (
    DOMAIN,
    SCAN_INTERVAL,
    PERSISTENT_FILE,
    DATA_ZIGATE_DEVICES,
    DATA_ZIGATE_ATTRS
)
from .core.admin_panel import ZiGateAdminPanel, ZiGateProxy
from .core.dispatcher import ZigateDispatcher
from .core.services import ZigateServices
from .core.entities import ZiGateComponentEntity

_LOGGER = logging.getLogger(__name__)

ENTITY_ID_ALL_ZIGATE = GROUP_ENTITY_ID_FORMAT.format('all_zigate')

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Optional(CONF_PORT): cv.string,
        vol.Optional(CONF_HOST): cv.string,
        vol.Optional('channel'): cv.positive_int,
        vol.Optional('gpio'): cv.boolean,
        vol.Optional('enable_led'): cv.boolean,
        vol.Optional('polling'): cv.boolean,
        vol.Optional(CONF_SCAN_INTERVAL): cv.positive_int,
        vol.Optional('admin_panel'): cv.boolean,
    })
}, extra=vol.ALLOW_EXTRA)

async def async_setup(hass, config):
    """Load configuration for Zigate component."""

    if not hass.config_entries.async_entries(DOMAIN) and DOMAIN in config:
        zigate_config = config[DOMAIN]
        _LOGGER.debug(zigate_config)
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=zigate_config
            )
        )

    return True

async def async_setup_entry(hass, config_entry):
    """Setup zigate platform."""
    port = config_entry.data["port"]
    host = config_entry.data["host"]
    gpio = config_entry.data["gpio"]
    enable_led = config_entry.data["enable_led"]
    polling = config_entry.data["polling"]
    channel = config_entry.data["channel"]
    scan_interval = datetime.timedelta(
        seconds=config[DOMAIN].get(CONF_SCAN_INTERVAL,config_entry.data["scan_interval"])
    )
    admin_panel = config_entry.data["admin_panel"]
    
    persistent_file = os.path.join(hass.config.config_dir, PERSISTENT_FILE)

    _LOGGER.debug('Port : %s', port)
    _LOGGER.debug('Host : %s', host)
    _LOGGER.debug('GPIO : %s', gpio)
    _LOGGER.debug('Led : %s', enable_led)
    _LOGGER.debug('Channel : %s', channel)
    _LOGGER.debug('Scan interval : %s', scan_interval)

    myzigate = zigate.connect(
        port=port, host=host, path=persistent_file, auto_start=False, gpio=gpio)

    if myzigate.ieee is None:
        return False
        
    _LOGGER.debug('ZiGate object created %s', myzigate)
    device_registry = await dr.async_get_registry(hass)
    device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, hass.data[DOMAIN][myzigate.ieee])},
        sw_version=myzigate.get_version_text(),
    )

    hass.data[DOMAIN] = myzigate
    hass.data[DATA_ZIGATE_DEVICES] = {}
    hass.data[DATA_ZIGATE_ATTRS] = {}

    component = EntityComponent(_LOGGER, DOMAIN, hass, scan_interval)
    component.setup(config)
    entity = ZiGateComponentEntity(myzigate)
    hass.data[DATA_ZIGATE_DEVICES]['zigate'] = entity
    component.add_entities([entity])
    ZigateDispatcher(hass, config, component)
    ZigateServices(hass, config, myzigate, component)

    if admin_panel:
        _LOGGER.debug('Start ZiGate Admin Panel on port 9998')
        myzigate.start_adminpanel(prefix='/zigateproxy')

        hass.http.register_view(ZiGateAdminPanel())
        hass.http.register_view(ZiGateProxy())
        custom_panel_config = {
            "name": "zigateadmin",
            "embed_iframe": False,
            "trust_external": False,
            "html_url": "/zigateadmin.html",
        }

        config = {}
        config["_panel_custom"] = custom_panel_config

        hass.components.frontend.async_register_built_in_panel(
            component_name="custom",
            sidebar_title='Zigate Admin',
            sidebar_icon='mdi:zigbee',
            frontend_url_path="zigateadmin",
            config=config,
            require_admin=True,
        )

    return True

async def async_unload_entry(hass, config_entry):
    """Unload a config entry."""

    for component in SUPPORTED_PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_unload(config_entry, component)
        )

    return True
