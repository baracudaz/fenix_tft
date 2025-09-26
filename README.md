# FENIX TFT WiFi Home Assistant Integration

This is a custom Home Assistant integration for the [FENIX TFT WiFi thermostat](https://www.fenixgroup.cz/en/products/thermostat-fenix-tft-wifi).

## Project status

- **Reverse engineered API**: This integration is based on reverse engineering the FENIX cloud API. It is a work in progress and intended as a fun project for developers and advanced users.
- **Not officially supported**: This is not an official FENIX Group product and is not affiliated with them.

## Getting started

### How to acquire tokens

To use this integration, you need your FENIX cloud API `access_token` and `refresh_token`.
Tokens are necessary because user login and password APIs have not been implemented yet.

#### Fenix tokens

You must use a proxy tool like Proxyman on your mobile device and capture traffic to the host `https://vs2-fe-identity-prod.azurewebsites.net/`.

Steps:
1. Set Proxyman to catch all traffic.
2. Enable SSL Proxying for the domain `https://vs2-fe-identity-prod.azurewebsites.net/`.
3. Open the [FENIX Control application](https://apps.apple.com/ch/app/fenix-control/id1474206689?l=en-GB) on your mobile.
4. Log in using your credentials.
5. In Proxyman, look for a POST request to `https://vs2-fe-identity-prod.azurewebsites.net/connect/token`.
6. The response to this request contains both `access_token` and `refresh_token`.

**Note:**
- The token is only valid for 24 hours.
- The integration automatically renews the token so that it is not invalidated.
- The renewed token, including the refresh token, is then stored.

### Installation

#### Manual installation

1. Clone this repository into your Home Assistant `custom_components` folder:
    ```bash
    git clone https://github.com/baracudaz/fenix_tft.git custom_components/fenix_tft
    ```
2. Restart Home Assistant.
3. Add the integration via the Home Assistant UI and provide your tokens.

#### Installation via HACS

1. Open HACS in your Home Assistant instance.
2. Go to "Integrations" and click the three dots in the top right, then select "Custom repositories".
3. Add `https://github.com/baracudaz/fenix_tft` as a custom repository and select "Integration" as the category.
4. Install the integration from HACS.
5. Restart Home Assistant.
6. Add the integration via the Home Assistant UI and provide your tokens.

### Configuration

- During setup, you will be prompted for your `access_token` and `refresh_token`.
- These tokens are required for cloud API access.

## Inspiration

- This project was inspired by [homebridge-fenix-tft-wifi](https://github.com/tomas-kulhanek/homebridge-fenix-tft-wifi).

## Product information

- [FENIX TFT WiFi Thermostat product page](https://www.fenixgroup.cz/en/products/thermostat-fenix-tft-wifi)
- [FENIX Control app on Google Play](https://play.google.com/store/apps/details?id=cz.fenixgroup.tftwifi)

---

Feel free to contribute, open issues, or share feedback as you explore and extend this integration!
