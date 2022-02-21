#### Home-Assistant custom component for SmartMi Zhimi Heaters.
Supports recent home-assistant versions (0.105.3 currently).

Supported models:
  - zhimi.heater.za1
  - zhimi.elecheater.ma1

Configuration:

add to your configuration.yaml following values:

```climate:
  - platform: miheater
      name: Bedroom Heater
      host: 192.168.0.10
      token: !secret bedroom_heater
      model: zhimi.heater.za1
```
