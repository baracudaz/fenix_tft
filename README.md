![GitHub release (latest SemVer including pre-releases)](https://img.shields.io/github/v/release/baracudaz/fenix_tft?include_prereleases)
 [![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

# FENIX TFT WiFi Home Assistant Integration

This is a custom Home Assistant integration for the [FENIX TFT WiFi thermostat](https://www.fenixgroup.cz/en/products/thermostat-fenix-tft-wifi).

**🏠 Smart Thermostat Control** **⚡ Energy Monitoring** **🌡️ Multi-Sensor Support** **📊 Energy Dashboard**

## Screenshots

Here is the thermostat integration in action.

<p float="left">
  <img src="artifacts/screenshots/thermostat-manual.png" width="32%" />
  <img src="artifacts/screenshots/thermostat-auto.png" width="32%" />
  <img src="artifacts/screenshots/thermostat-off.png" width="32%" />
</p>

## Project status

- **Reverse engineered API**: This integration is based on reverse engineering the FENIX cloud API. It is a work in progress and intended as a fun project for developers and advanced users.
- **Not officially supported**: This is not an official FENIX Group product and is not affiliated with them.

## Features

### ✅ Current Features

- **Climate Control**: Temperature control, heating modes (Off/Manual/Program), real-time monitoring
- **Energy Monitoring**: Daily consumption tracking with Home Assistant Energy Dashboard integration
- **Multi-Sensor Support**: Room/floor temperatures, HVAC status, connectivity monitoring
- **Multi-Device**: Supports multiple thermostats across different rooms

### 🚧 Planned & Ideas

- **Smart Scheduling**: Holiday mode, full scheduling system, calendar integration
- **Enhanced Diagnostics**: Additional device sensors and operational data

### 💡 Contributing

Help wanted with testing, translations, documentation, and feature requests!

## Getting started

### Login credentials

To use this integration, you only need your **FENIX account email and password**.  

### Installation

#### Manual installation

1. Clone this repository into your Home Assistant `custom_components` folder:

    ```bash
    git clone https://github.com/baracudaz/fenix_tft.git custom_components/fenix_tft
    ```

2. Restart Home Assistant.
3. Add the integration via the Home Assistant and provide your **email** and **password**.

#### Installation via HACS

1. Open [HACS](https://www.hacs.xyz) in your Home Assistant instance.
2. Go to "Integrations" and click the three dots in the top right, then select "Custom repositories".
3. Add `https://github.com/baracudaz/fenix_tft` as a custom repository and select "Integration" as the category.
4. Install the integration from HACS.
5. Restart Home Assistant.
6. Add the integration via the Home Assistant and provide your **email** and **password**.

### Configuration

- During setup, you will be prompted for your **email** and **password** used in the FENIX Control app.
- The integration will take care of acquiring and refreshing tokens automatically in the background.

## Inspiration

This project was inspired by:

- [Watts Vision for Home Assistant](https://github.com/pwesters/watts_vision)
- [homebridge-fenix-tft-wifi](https://github.com/tomas-kulhanek/homebridge-fenix-tft-wifi)

## Product information

- [FENIX TFT WiFi Thermostat product page](https://www.fenixgroup.cz/en/products/thermostat-fenix-tft-wifi)
- [FENIX Control app on Apple App Store](https://apps.apple.com/ch/app/fenix-control/id1474206689?l=en-GB)
- [FENIX Control app on Google Play](https://play.google.com/store/apps/details?id=com.Fenix.TftWifi.Mobile)

---

Feel free to contribute, open issues, or share feedback as you explore and extend this integration!
