import logging
import voluptuous as vol
from typing import List, Optional

from homeassistant.components.climate import (ClimateDevice,
        PLATFORM_SCHEMA, HVAC_MODE_OFF, HVAC_MODE_HEAT)
from homeassistant.components.climate.const import (
    SUPPORT_TARGET_TEMPERATURE)
from homeassistant.const import (
    ATTR_TEMPERATURE, CONF_HOST, CONF_NAME, CONF_TOKEN,
    STATE_ON, STATE_OFF, TEMP_CELSIUS)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.exceptions import PlatformNotReady

from .heater import Heater, Brightness, MODEL_HEATER_ZA1, MODEL_HEATER_MA1
from miio.exceptions import DeviceException

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'miheater'
DEFAULT_NAME = 'MiHeater'
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

async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Perform the setup for Xiaomi heaters."""
    host = config.get(CONF_HOST)
    name = config.get(CONF_NAME)
    token = config.get(CONF_TOKEN)
    model = config.get(CONF_MODEL)

    _LOGGER.info("Initializing Xiaomi heaters with host %s (token %s...)", host, token[:5])

    unique_id = None

    try:
        #device = Heater(host, token, model = model)

        #device_info = await hass.async_add_executor_job(device.info)
        #if not model:
        #   model = device_info.model
        #unique_id = "{}-{}".format(model, device_info.mac_address)
        #_LOGGER.info("%s %s %s detected",
        #             model,
        #             device_info.firmware_version,
        #             device_info.hardware_version)
        #miHeater = MiHeater(device, name, model, unique_id, hass)
        miHeater = MiHeater([host,token,name], name, MODEL_HEATER_ZA1, 'bla-bla-heater', hass)

    except DeviceException as ex:
        _LOGGER.error("Got exception while setting up device: %s", ex)
        raise PlatformNotReady

    async_add_entities([miHeater], update_before_add=True)
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
            #data = await self.hass.async_add_executor_job(self._device.status)
            data = {'power': 'on', 'target_temperature': 21.1, 'temperature': 15.2}
        except DeviceException as ex:
            self._available = False
            _LOGGER.error("Got exception while fetching the state: %s", ex)
            raise PlatformNotReady
        self._available = True
        self._state = data

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set operation mode."""
        if hvac_mode == HVAC_MODE_HEAT:
            await self.async_turn_on()
        elif hvac_mode == HVAC_MODE_OFF:
            await self.async_turn_off()
        else:
            _LOGGER.error("Unrecognized operation mode: %s", hvac_mode)

