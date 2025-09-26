# FENIX TFT WiFi Home Assistant Integration

This is a custom Home Assistant integration for the [FENIX TFT WiFi thermostat](https://www.fenixgroup.cz/en/products/thermostat-fenix-tft-wifi).

## Project status

- **Reverse engineered API**: This integration is based on reverse engineering the FENIX cloud API. It is a work in progress and intended as a fun project for developers and advanced users.
- **Not officially supported**: This is not an official FENIX Group product and is not affiliated with them.

## Getting started

### How to acquire tokens

To use this integration, you need your FENIX cloud API `access_token` and `refresh_token`.
You can obtain these by logging into the official FENIX mobile app and extracting tokens from network traffic (for example, using browser developer tools or a proxy tool like mitmproxy or Charles Proxy).

### Installation

1. Clone this repository into your Home Assistant `custom_components` folder:
    ```bash
    git clone https://github.com/baracudaz/fenix_tft.git custom_components/fenix_tft
    ```
2. Restart Home Assistant.
3. Add the integration via the Home Assistant UI and provide your tokens.

### Configuration

- During setup, you will be prompted for your `access_token` and `refresh_token`.
- These tokens are required for cloud API access.

## Inspiration

- This project was inspired by [homebridge-fenix-tft-wifi](https://github.com/tomas-kulhanek/homebridge-fenix-tft-wifi).

## Product information

- [FENIX TFT WiFi Thermostat product page](https://www.fenixgroup.cz/en/products/thermostat-fenix-tft-wifi)

---

Feel free to contribute, open issues, or share feedback as you explore and extend this integration!
