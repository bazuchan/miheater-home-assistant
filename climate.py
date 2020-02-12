import logging
import asyncio
import voluptuous as vol
from typing import List, Dict, Optional, Any

from homeassistant.components.climate import (ClimateDevice,
        PLATFORM_SCHEMA, HVAC_MODE_OFF, HVAC_MODE_HEAT)
from homeassistant.components.climate.const import (
    SUPPORT_TARGET_TEMPERATURE)
from homeassistant.const import (
    ATTR_ENTITY_ID, ATTR_TEMPERATURE, CONF_HOST, CONF_NAME,
    CONF_TOKEN, STATE_ON, STATE_OFF, TEMP_CELSIUS)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.exceptions import PlatformNotReady

from .heater import Heater, Brightness, MODEL_HEATER_ZA1, MODEL_HEATER_MA1
from miio.exceptions import DeviceException

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'miheater'
DEFAULT_NAME = 'MiHeater'

DATA_KEY = "climate.miheater"

CONF_MODEL = 'model'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_TOKEN): vol.All(cv.string, vol.Length(min=32, max=32)),
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_MODEL): vol.In(
        [
            MODEL_HEATER_ZA1,
            MODEL_HEATER_MA1,
        ]
    ),
})

TARGET_TEMP_RANGE = {
    MODEL_HEATER_ZA1: (16.0, 32.0),
    MODEL_HEATER_MA1: (20.0, 32.0),
}

ATTR_CHILD_LOCK = 'child_lock'
ATTR_BUZZER = 'buzzer'
ATTR_BRIGHTNESS = 'brightness'
ATTR_DELAY_OFF = 'poweroff_time'

SERVICE_SET_PARAMS = 'set_params'

CLIMATE_SET_PARAMS_SCHEMA = vol.Schema({
        vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Exclusive(ATTR_BRIGHTNESS, "Brightness: bright, dim, off"): vol.All(cv.string, vol.Capitalize, vol.Coerce(Brightness.__getitem__)),
        vol.Exclusive(ATTR_BUZZER, "Buzzer: False, True"): vol.Coerce(vol.Boolean()),
        vol.Exclusive(ATTR_CHILD_LOCK, "Child Lock: False, True"): vol.Coerce(vol.Boolean()),
        vol.Exclusive(ATTR_DELAY_OFF, "Delay off seconds 0-32940"): vol.All(vol.Coerce(int), vol.Clamp(min=0, max=32940)),
})

HEATER_SET_PARAMS_MAP = {
        ATTR_CHILD_LOCK: 'set_child_lock',
        ATTR_BUZZER: 'set_buzzer',
        ATTR_BRIGHTNESS: 'set_brightness',
        ATTR_DELAY_OFF: 'delay_off',
}

async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Perform the setup for Xiaomi heaters."""
    if DATA_KEY not in hass.data:
        hass.data[DATA_KEY] = {}

    host = config.get(CONF_HOST)
    name = config.get(CONF_NAME)
    token = config.get(CONF_TOKEN)
    model = config.get(CONF_MODEL)

    _LOGGER.info("Initializing Xiaomi heaters with host %s (token %s...)", host, token[:5])

    unique_id = None

    try:
        device = Heater(host, token, model = model)
        device_info = await hass.async_add_executor_job(device.info)
        if not model:
           model = device_info.model
        unique_id = "{}-{}".format(model, device_info.mac_address)
        _LOGGER.info("%s %s %s detected",
                     model,
                     device_info.firmware_version,
                     device_info.hardware_version)
        miHeater = MiHeater(device, name, model, unique_id, hass)

    except DeviceException as ex:
        _LOGGER.error("Got exception while setting up device: %s", ex)
        raise PlatformNotReady

    hass.data[DATA_KEY][host] = miHeater
    async_add_entities([miHeater], update_before_add=True)
    _LOGGER.info("Initializing Xiaomi heaters with host %s (token %s...) object", host, token[:5])

    async def async_set_params(service):
        _LOGGER.info("miheater.set_params: %s", str(service.data.items()))
        entity_ids = service.data.get(ATTR_ENTITY_ID)
        params = {key: value for key, value in service.data.items() if key != ATTR_ENTITY_ID}
        mhs = [mh for mh in hass.data[DATA_KEY].values() if mh.entity_id in entity_ids]
        update_tasks = []
        for mh in mhs:
            await mh.async_set_params(params)
            update_tasks.append(mh.async_update_ha_state(True))
        if update_tasks:
            await asyncio.wait(update_tasks)
        _LOGGER.info("miheater.set_params: done")

    hass.services.async_register(DOMAIN, SERVICE_SET_PARAMS, async_set_params, schema=CLIMATE_SET_PARAMS_SCHEMA)
    _LOGGER.info("Initializing Xiaomi heaters with host %s (token %s...) done", host, token[:5])

class MiHeater(ClimateDevice):
    """Representation of a MiHeater device."""

    def __init__(self, device, name, model, unique_id, _hass):
        """Initialize the heater."""
        self._device = device
        self._model = model 
        self._unique_id = unique_id
        self._name = name
        self._available = False
        self._state = None

    @property
    def name(self):
        """Return the name of the device if any."""
        return self._name

    @property
    def unique_id(self):
        """Return an unique ID."""
        return self._unique_id

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        return SUPPORT_TARGET_TEMPERATURE

    @property
    def state_attributes(self) -> Dict[str, Any]:
        """Return the optional state attributes."""
        data = super().state_attributes
        for attr in [ATTR_DELAY_OFF, ATTR_BRIGHTNESS, ATTR_BUZZER, ATTR_CHILD_LOCK]:
            if attr in self._state and self._state[attr] not in ['NULL', None]:
                data[attr] = self._state[attr]
        return data

    @property
    def current_humidity(self) -> Optional[int]:
        """Return the current humidity."""
        if 'relative_humidity' in self._state and self._state['relative_humidity'] not in ['NULL', None]:
            return self._state['relative_humidity']
        return None

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement which this thermostat uses."""
        return TEMP_CELSIUS

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the temperature we try to reach."""
        if 'target_temperature' in self._state and self._state['target_temperature'] not in ['NULL', None]:
            return float(self._state['target_temperature'])
        return None

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the current temperature."""
        if 'temperature' in self._state and self._state['temperature'] not in ['NULL', None]:
            return self._state['temperature']
        return None

    @property
    def target_temperature_step(self) -> Optional[float]:
        """Return the supported step of target temperature."""
        return 1.0

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return TARGET_TEMP_RANGE[self._model][0]

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return TARGET_TEMP_RANGE[self._model][1]

    @property
    def hvac_modes(self) -> List[str]:
        """List of available operation modes."""
        return [HVAC_MODE_OFF, HVAC_MODE_HEAT]

    @property
    def hvac_mode(self) -> str:
        """Return current operation ie. heat, cool, idle."""
        if self._state['power'] == 'on':
            return HVAC_MODE_HEAT
        return HVAC_MODE_OFF

    def set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        self._device.set_target_temperature(temperature)

    def turn_on(self) -> None:
        """Turn MiHeater unit on."""
        self._device.on()

    def turn_off(self) -> None:
        """Turn MiHeater unit off."""
        self._device.off()

    async def async_update(self) -> None:
        """Retrieve latest state."""
        try:
            data = await self.hass.async_add_executor_job(self._device.status)
        except DeviceException as ex:
            self._available = False
            _LOGGER.error("Got exception while fetching the state: %s", ex)
            raise PlatformNotReady
        self._available = True
        self._state = data.__dict__['data']

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set operation mode."""
        if hvac_mode == HVAC_MODE_HEAT:
            await self.async_turn_on()
        elif hvac_mode == HVAC_MODE_OFF:
            await self.async_turn_off()
        else:
            _LOGGER.error("Unrecognized operation mode: %s", hvac_mode)

    async def async_set_params(self, params: dict) -> None:
        """Set heater parameters."""
        for param, func in HEATER_SET_PARAMS_MAP.items():
            if param in params:
                 await self.hass.async_add_executor_job(getattr(self._device, func), params[param])

