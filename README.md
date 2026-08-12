# Remeha Home Plugin for Domoticz

## Overview
This Domoticz Python plugin integrates with the Remeha Home API, providing real-time information about your heating system. It creates Domoticz devices for temperature, pressure, setpoint and fireplacemode control.

## Credits
This plugin is based on the Remeha Home Python library by Michiel Visser, available at [GitHub - Remeha Home Library](https://github.com/msvisser/remeha_home).
It was further developed by Tuk90, GizMoCuz. jvanderzande added the T6 Thermostat option and added some code to avoid hardware failures due to slow responses from the Remeha website.

## Installation
1. Clone this repository into the Domoticz plugins folder using the following command: git clone https://github.com/jvanderzande/RemehaHome-Domoticz.git
2. Restart the Domoticz service.
3. Go to the Domoticz web interface, navigate to "Hardware," and add a new hardware device with type "Remeha Home Plugin."

## Plugin Parameters
- **Email:** Your Remeha Home account email.
- **Password:** Your Remeha Home account password.
- **Poll Interval:** Poll Interval (default 30 seconds). If you choose an amount higher than 30 seconds then set the value of Data Timeout to a higher value to prevent your logs from being flooded with 'timeout' error messages.
- **Combined TempSettemp:** 
  - **Yes** means you will get the new Thermostat6 device which combines the temperature and SetTemp into one device.
  - **No** means you will get 2 separate devices: Thermostat and Temperature device.

## Devices
The plugin creates the following devices in Domoticz:
1. Room Temperature
2. Outdoor Temperature
3. Water Pressure
4. Setpoint
5. Domestic Hot Water Temperature
6. Energy Consumption
7. Energy Delivered
8. gasCalorificValue
9. zoneMode
10. waterPressureToLow (alarm)
11. Status
12. seasonalEfficiency (only for air heatpumps)
13. FireplaceMode

## Usage
The plugin fetches data from the Remeha Home API and updates the corresponding Domoticz devices. The room temperature can be set using the "Setpoint" device, it will set the zoneMode to TemporaryOverride except when the zoneMode is set to Manual. The zoneMode can be used to set the zoneMode to the following modes: Scheduling, Manual, TemporaryOverride, FrostProtection

## Support
For any issues or questions, please open an issue on the [GitHub repository](https://github.com/jvanderzande/RemehaHome-Domoticz).
