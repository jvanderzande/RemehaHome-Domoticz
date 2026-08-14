# SolarEdge ModbusTCP
#
# Source:  https://github.com/jvanderzande/RemehaHome-Domoticz.git
# Authors:  Nick Baring/GizMoCuz/jvanderzande
# License: MIT

"""
<plugin key="RemehaHome" name="Remeha Home Plugin" author="Nick Baring/GizMoCuz/jvdzande" version="1.5.1" externallink=" https://github.com/jvanderzande/RemehaHome-Domoticz.git">
    <params>
        <param field="Mode1" label="Email" width="200px" required="true"/>
        <param field="Mode2" label="Password" width="200px" password="true" required="true"/>
        <param field="Mode3" label="Poll Interval" width="100px" required="true">
            <options>
                <option label="30 seconds" value="30"/>
                <option label="1 minute" value="60" default="true"/>
                <option label="2 minutes" value="120"/>
                <option label="5 minutes" value="300"/>
            </options>
        </param>
        <param field="Mode4" label="Combined TempSettemp" width="100px" required="true">
            <options>
                <option label="Yes" value="Yes" default="true"/>
                <option label="No" value="No"/>
            </options>
        </param>
    </params>
</plugin>
"""
import Domoticz
import base64
import hashlib
import json
import urllib
import secrets
import requests
import datetime
import calendar
import time
import re

class RemehaHomeAPI:
    def __init__(self):
        # Initialize a session for making HTTP requests
        self._session = requests.Session()
        self.email = ""
        self.password = ""
        self.domoticzbuild = 0
        self.usecombined = False
        self.poll_interval = 0
        self.LastWebUpdate = None


    def _request_with_retry(self, method, url, max_retries=3, timeout=5, **kwargs):
        """Helper method to make requests with retry logic and 5 second timeout."""
        for attempt in range(max_retries):
            try:
                if method.lower() == 'get':
                    response = self._session.get(url, timeout=timeout, **kwargs)
                elif method.lower() == 'post':
                    response = self._session.post(url, timeout=timeout, **kwargs)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                return response
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    raise
                Domoticz.Debug(f"Retry attempt {attempt + 1}/{max_retries} for {method.upper()} {url}: {e}")
        return None

    @staticmethod
    def _format_exception(exc):
        reason = getattr(exc, 'reason', None)
        if reason is None and getattr(exc, 'args', None):
            reason = exc.args[0] if len(exc.args) == 1 else exc.args
        if reason is None:
            reason = str(exc)
        return f"{type(exc).__name__}: {reason}"

    def onStart(self):

        # Read options from Domoticz GUI
        self.readOptions()

        # Called when the plugin is started
        if self.usecombined:
           Domoticz.Status("Remeha Home Plugin started with combined temp-settemp. Domoticz version: " + Parameters["DomoticzVersion"])
        else:
           Domoticz.Status("Remeha Home Plugin started with separate temp-settemp. Domoticz version: " + Parameters["DomoticzVersion"])

        # Check if there are no existing devices
        self.createDevices()

        # Set the poll interval to 5 seconds and test for the set real update time in onheartbeat() to allow for longer than 30 seconds
        Domoticz.Heartbeat(5)
        Domoticz.Log(f"Poll Interval: {self.poll_interval}")

    def onStop(self):
        # Called when the plugin is stopped
        Domoticz.Log("Remeha Home Plugin stopped.")

    def readOptions(self):
        # Read options from Domoticz GUI

        if Parameters["Mode1"]:
            self.email = Parameters["Mode1"]
        if "Mode2" in Parameters and Parameters["Mode2"]:
            self.password = Parameters["Mode2"]
        else:
            Domoticz.Error("Password not configured in the Domoticz plugin configuration.")
        self.poll_interval = int(Parameters["Mode3"])
        if self.poll_interval < 30:
            self.poll_interval = 30
        if self.poll_interval > 300:
            self.poll_interval = 300

        self.usecombined = (Parameters["Mode4"] == "Yes")

    def createDevices(self):
        # Declare Devices variable
        global Devices

        # Create devices for temperature, pressure, and setpoint
        # Use Combined device when supported and requested in the hardware page
        if (self.usecombined):
            OrgTempsValue="18.0"
            OrgSetTempName = "roomTempsetPoint"
            OrgSetTempsValue = "15.0"
            OrgSetTempnValue = 0
            # Delete old Temp device as that has to become the Combined SetTemp Device
            if 1 in Devices and Devices[1].Type != 73 :
                # retrieve current (4) - SetTemp device info
                OrgSetTempName = Devices[4].Name
                OrgSetTempsValue= Devices[4].sValue
                OrgSetTempnValue= Devices[4].nValue
                # retrieve current (1) - Temp device info
                OrgTempsValue= Devices[1].sValue
                # Delete old (1) - Temp device to trigger the below device creation
                Domoticz.Log(f"Deleted old Temp device: \"{Devices[1].Name}\" Type={Devices[1].Type}, SubType={Devices[1].SubType}")
                Devices[1].Delete()

                # Disable&Rename old SetTemp device
                newname = "OLD_"+OrgSetTempName
                if 4 in Devices and Devices[4].Type != 73:
                    Devices[4].Update(
                        nValue=Devices[4].nValue,
                        sValue=Devices[4].sValue,
                        Name=newname,
                        Used=0
                    )
                    Domoticz.Log(f"Renamed & Disabled Old SetTemp device to: \"{Devices[4].Name}\"")

            if 1 not in Devices:
                Domoticz.Device(Name=OrgSetTempName, Unit=1, Type=73, Subtype=0, Used=1).Create()
                Devices[1].Update(
                    nValue=OrgSetTempnValue,
                    sValue=OrgTempsValue + ";" + OrgSetTempsValue,
                    Name=OrgSetTempName,
                    Used=1
                )
                Domoticz.Log(f"Created combined device: {Devices[1].Name} Type={Devices[1].Type}, SubType={Devices[1].SubType}")
        else:
            if 1 in Devices and Devices[1].Type == 73 :
                Domoticz.Log(f"Deleted Combined SetTemp device: \"{Devices[1].Name}\"")
                Devices[1].Delete();
                newname = "roomTempsetPoint"
                if 4 in Devices:
                    # remove added "OLD_" prefix and enable previous define SetTemp device
                    newname = Devices[4].Name.replace("OLD_","")
                if 4 in Devices:
                    Devices[4].Update(
                        nValue=Devices[4].nValue,
                        sValue=Devices[4].sValue,
                        Name=newname,
                        Used=1
                    )
                    Domoticz.Log(f"Renamed Old SetTemp device back to: \"{Devices[4].Name}\"")

            # Use separate Thermostat devices for SetTemp and temperature
            if 1 not in Devices:
                Domoticz.Device(Name="roomTemperature", Unit=1, TypeName="Temperature", Used=1).Create()
                Domoticz.Log(f"Created separate Temp device: {Devices[1].Name}")
            if 4 not in Devices:
                Domoticz.Device(Name="setPoint", Unit=4, TypeName="Setpoint", Used=1).Create()
                Domoticz.Log(f"Created separate SetTemp device: {Devices[4].Name}")

        # other devices
        if 2 not in Devices:
            Domoticz.Device(Name="outdoorTemperature", Unit=2, TypeName="Temperature", Used=1).Create()
        if 3 not in Devices:
            Domoticz.Device(Name="waterPressure", Unit=3, TypeName="Pressure", Used=1).Create()
        if 5 not in Devices:
            Domoticz.Device(Name="dhwTemperature", Unit=5, TypeName="Temperature", Used=1).Create()
        if 6 not in Devices:
            Domoticz.Device(Name="EnergyConsumption", Unit=6, Type=243, TypeName="Kwh", Subtype=29, Used=1).Create()
        if 7 not in Devices:
            Domoticz.Device(Name="gasCalorificValue", Unit=7, Type=243, Subtype=31, Used=1).Create()
        if 8 not in Devices:
            Domoticz.Device(Name="zoneMode", Unit=8, TypeName="Selector Switch", Image=15, Options={"LevelNames":"Scheduling|Manual|TemporaryOverride|FrostProtection", "LevelOffHidden": "false", "SelectorStyle": "1"}, Used=1).Create()
        if 9 not in Devices:
            Domoticz.Device(Name="waterPressureToLow", Unit=9, TypeName="Switch", Switchtype=0, Image=13, Used=1).Create()
        if 10 not in Devices:
            Domoticz.Device(Name="EnergyDelivered", Unit=10, Type=243, TypeName="Kwh", Subtype=29, Switchtype=4, Used=1).Create()
        if 11 not in Devices:
            Domoticz.Device(Name="Status", Unit=11, TypeName="Text", Image=15, Used=1).Create()
        if 12 not in Devices:
            Domoticz.Device(Name="seasonalEfficiency", Unit=12, Type=243, Subtype=31, Used=1).Create()
        if 13 not in Devices:
            Domoticz.Device(Name="firePlaceModeActive", Unit=13, TypeName="Switch", Switchtype=0, Image=10, Used=1).Create()



    def resolve_external_data(self):
        # Logic for resolving external data (OAuth2 flow)
        random_state = secrets.token_urlsafe()
        code_challenge = secrets.token_urlsafe(64)
        code_challenge_sha256 = (
            base64.urlsafe_b64encode(
                hashlib.sha256(code_challenge.encode("ascii")).digest()
            )
            .decode("ascii")
            .rstrip("=")
        )

        try:
            response = self._request_with_retry(
                "get",
                "https://remehalogin.bdrthermea.net/bdrb2cprod.onmicrosoft.com/oauth2/v2.0/authorize",
                params={
                    "response_type": "code",
                    "client_id": "6ce007c6-0628-419e-88f4-bee2e6418eec",
                    "redirect_uri": "com.b2c.remehaapp://login-callback",
                    "scope": "openid https://bdrb2cprod.onmicrosoft.com/iotdevice/user_impersonation offline_access",
                    "state": random_state,
                    "code_challenge": code_challenge_sha256,
                    "code_challenge_method": "S256",
                    "p": "B2C_1A_RPSignUpSignInNewRoomV3.1",
                    "brand": "remeha",
                    "lang": "en",
                    "nonce": "defaultNonce",
                    "prompt": "login",
                    "signUp": "False",
                },
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            reason = getattr(e, 'reason', e)
            Domoticz.Error(f"Authorize error: {type(e).__name__}: {reason}")
            return None
        except Exception as e:
            Domoticz.Error(f"Unexpected error during GET request: {self._format_exception(e)}")
            return None

        if response.status_code != 200:
            Domoticz.Error(f"Error received from server (authorize): {response.status_code}")
            return None

        request_id = response.headers["x-request-id"]
        state_properties_json = f'{{"TID":"{request_id}"}}'.encode("ascii")
        state_properties = (
            base64.urlsafe_b64encode(state_properties_json)
            .decode("ascii")
            .rstrip("=")
        )

        csrf_token = next(
            cookie.value
            for cookie in self._session.cookies
            if (
                cookie.name == "x-ms-cpim-csrf"
                and cookie.domain == ".remehalogin.bdrthermea.net"
            )
        )

        try:
            response = self._request_with_retry(
                "post",
                "https://remehalogin.bdrthermea.net/bdrb2cprod.onmicrosoft.com/B2C_1A_RPSignUpSignInNewRoomv3.1/SelfAsserted",
                params={
                    "tx": "StateProperties=" + state_properties,
                    "p": "B2C_1A_RPSignUpSignInNewRoomv3.1",
                },
                headers={"x-csrf-token": csrf_token},
                data={
                    "request_type": "RESPONSE",
                    "signInName": self.email,
                    "password": self.password,
                },
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            reason = getattr(e, 'reason', e)
            Domoticz.Error(f"Error during GET request for SelfAsserted: {type(e).__name__}: {reason}")
            return None
        except Exception as e:
            Domoticz.Error(f"Unexpected error during GET request: {self._format_exception(e)}")
            return None

        if response.status_code != 200:
            Domoticz.Error(f"Error received from server (signin_1): {response.status_code}")
            return None

        response_json = json.loads(response.text)

        try:
            response = self._request_with_retry(
                "get",
                "https://remehalogin.bdrthermea.net/bdrb2cprod.onmicrosoft.com/B2C_1A_RPSignUpSignInNewRoomv3.1/api/CombinedSigninAndSignup/confirmed",
                params={
                    "rememberMe": "false",
                    "csrf_token": csrf_token,
                    "tx": "StateProperties=" + state_properties,
                    "p": "B2C_1A_RPSignUpSignInNewRoomv3.1",
                },
                allow_redirects=False,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            reason = getattr(e, 'reason', e)
            Domoticz.Error(f"Error during GET request for CombinedSigninAndSignup: {type(e).__name__}: {reason}")
            return None
        except Exception as e:
            Domoticz.Error(f"Unexpected error during GET request: {self._format_exception(e)}")
            return None

        if response.status_code >= 400:
            Domoticz.Error(f"Error received from server (signin_2): {response.status_code}")
            return None

        parsed_callback_url = urllib.parse.urlparse(response.headers["location"])
        if parsed_callback_url is None:
            Domoticz.Error("Invalid response, check authorization")
            return None
        query_string_dict = urllib.parse.parse_qs(parsed_callback_url.query)
        if "code" not in query_string_dict:
            Domoticz.Error("Invalid response, check authorization")
            return None
        authorization_code = query_string_dict["code"]

        grant_params = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": "com.b2c.remehaapp://login-callback",
            "code_verifier": code_challenge,
            "client_id": "6ce007c6-0628-419e-88f4-bee2e6418eec",
        }
        return self._request_new_token(grant_params)

    def _request_new_token(self, grant_params):
        # Logic for requesting a new access token
        try:
            response = self._request_with_retry(
                "post",
                "https://remehalogin.bdrthermea.net/bdrb2cprod.onmicrosoft.com/oauth2/v2.0/token?p=B2C_1A_RPSignUpSignInNewRoomV3.1",
                data=grant_params,
                allow_redirects=True,
            )
            if response.status_code != 200:
                response_json = response.json()
                Domoticz.Log(
                    "OAuth2 token request returned '400 Bad Request': %s",
                    response_json["error_description"],
                )
            response.raise_for_status()
            response_json = response.json()
        except requests.exceptions.RequestException as e:
            reason = getattr(e, 'reason', e)
            Domoticz.Error(f"new access token error: {type(e).__name__}: {reason}")
            return None
        except Exception as e:
            Domoticz.Error(f"new access token error: {self._format_exception(e)}")

        return response_json

    def cleanup(self):
        # Cleanup session resources
        self._session.close()

    def update_devices(self, access_token):
        # Update Domoticz devices with data from Remeha Home
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Ocp-Apim-Subscription-Key": "df605c5470d846fc91e848b1cc653ddf",
        }

        global appliance_id
        global climate_zone_id
        global firePlaceModeActive
        global value_firePlaceModeActive


        # Initialize global variables if not already set
        appliance_id = globals().get('appliance_id', None)
        climate_zone_id = globals().get('climate_zone_id', None)
        firePlaceModeActive = globals().get('firePlaceModeActive', None)
        value_firePlaceModeActive = globals().get('value_firePlaceModeActive', None)

        #Domoticz.Log("Getting device states...")
        try:
            response = self._request_with_retry(
                "get",
                "https://api.bdrthermea.net/Mobile/api/homes/dashboard", headers=headers
            )

            response.raise_for_status()

            if response.status_code != 200:
                Domoticz.Error(f"Error getting device states: {response.status_code}")
                return None

            response_json = response.json()

            # declaring value_dhwTemperature to not break if the value is not present.
            value_dhwTemperature = None


            # Update Domoticz devices here based on the response_json
            value_room_temperature = response_json["appliances"][0]["climateZones"][0]["roomTemperature"]
            if response_json["appliances"][0]["capabilityOutdoorTemperature"] is True:
                if response_json["appliances"][0]["outdoorTemperatureInformation"]["outdoorTemperatureSource"] == 'Wired':
                    value_outdoor_temperature = response_json["appliances"][0]["outdoorTemperatureInformation"]["applianceOutdoorTemperature"]
                    #Domoticz.Error(f"Device outdoor temp expected: {value_outdoor_temperature}")
                else :
                    value_outdoor_temperature = response_json["appliances"][0]["outdoorTemperatureInformation"]["cloudOutdoorTemperature"]
                    #Domoticz.Error(f"Internet temp expected : {value_outdoor_temperature}")

            value_water_pressure = response_json["appliances"][0]["waterPressure"]
            value_setpoint = response_json["appliances"][0]["climateZones"][0]["setPoint"]
            value_gascalorificvalue = response_json["appliances"][0]["gasCalorificValue"]
            value_zoneMode = response_json["appliances"][0]["climateZones"][0]["zoneMode"]
            value_waterPressureOK = response_json["appliances"][0]["waterPressureOK"]
            value_status = response_json["appliances"][0]["climateZones"][0]["activeComfortDemand"]

            # set globals
            if climate_zone_id is None:
                climate_zone_id = response_json["appliances"][0]["climateZones"][0]["climateZoneId"]
            if appliance_id is None:
                appliance_id = response_json["appliances"][0]["applianceId"]

            try:
                value_dhwTemperature = response_json["appliances"][0]["hotWaterZones"][0]["dhwTemperature"]
            except:
                pass

            if (self.usecombined and Devices[1].Type == 73):
                Devices[1].Update(nValue=0, sValue=str(value_room_temperature) + ";" + str(value_setpoint))
            else:
                Devices[1].Update(nValue=0, sValue=str(value_room_temperature))
                Devices[4].Update(nValue=0, sValue=str(value_setpoint))

            #if str(Devices[2].sValue) != str(value_outdoor_temperature):
            if response_json["appliances"][0]["capabilityOutdoorTemperature"] is True:
                Devices[2].Update(nValue=0, sValue=str(value_outdoor_temperature))
            #if str(Devices[3].sValue) != str(value_water_pressure):
            Devices[3].Update(nValue=0, sValue=str(value_water_pressure))
            #if str(Devices[5].sValue) != str(value_dhwTemperature):
            if value_dhwTemperature is not None:
                Devices[5].Update(nValue=0, sValue=str(value_dhwTemperature))
            #if str(Devices[7].sValue) != str(value_gascalorificvalue):
            Devices[7].Update(nValue=0, sValue=str(value_gascalorificvalue), Options={"Custom": "1;kWh/m³"})
            #if str(Devices[8].sValue) != str(value_zoneMode):
            if value_zoneMode == "Scheduling":
                Devices[8].Update(nValue=1, sValue="0")
            elif value_zoneMode == "Manual":
                Devices[8].Update(nValue=10, sValue="10")
            elif value_zoneMode == "TemporaryOverride":
                Devices[8].Update(nValue=20, sValue="20")
            elif value_zoneMode == "FrostProtection":
                Devices[8].Update(nValue=0, sValue="30")
            #if str(Devices[9].sValue) != str(value_gascalorificvalue):
            if value_waterPressureOK == True:
                Devices[9].Update(nValue=0, sValue="Off")
            else:
                Devices[9].Update(nValue=1, sValue="On")
            Devices[11].Update(nValue=0, sValue=str(value_status))
            if response_json["appliances"][0]["climateZones"][0]["capabilityFirePlaceMode"] is True:
                value_firePlaceModeActive = response_json["appliances"][0]["climateZones"][0]["firePlaceModeActive"]
                if value_firePlaceModeActive == True:
                    Devices[13].Update(nValue=1, sValue="On")
                if value_firePlaceModeActive == False:
                    Devices[13].Update(nValue=0, sValue="Off")
            else:
                Devices[13].Update(nValue=0, sValue="Off")

        except requests.exceptions.RequestException as e:
            reason = getattr(e, 'reason', e)
            Domoticz.Error(f"Error during GET request for dashboard: {type(e).__name__}: {reason}")
            return None

        except Exception as e:
            Domoticz.Error(f"Error making GET request: {self._format_exception(e)}")

    def set_temperature(self, access_token, room_temperature_setpoint):
        # Set temperature in the external system using a POST request
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Ocp-Apim-Subscription-Key': 'df605c5470d846fc91e848b1cc653ddf'
        }

        try:
            json_data = {'roomTemperatureSetPoint': room_temperature_setpoint}
            if Devices[8].sValue == "10": #If zonemode is manual then adjust the manual temp
                response = self._request_with_retry(
                    "post",
                    f'https://api.bdrthermea.net/Mobile/api/climate-zones/{climate_zone_id}/modes/manual',
                    headers=headers,
                    json=json_data,
                    )
            else: # zonemode is not manual then temporary override
                response = self._request_with_retry(
                    "post",
                    f'https://api.bdrthermea.net/Mobile/api/climate-zones/{climate_zone_id}/modes/temporary-override',
                    headers=headers,
                    json=json_data,
                    )
            response.raise_for_status()
            Domoticz.Log(f"Temperature set successfully to {room_temperature_setpoint}")
        except Exception as e:
            Domoticz.Error(f"Error making POST request: {self._format_exception(e)}")

    def getDailyEnergyConsumption(self, access_token):
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Ocp-Apim-Subscription-Key': 'df605c5470d846fc91e848b1cc653ddf'
            }
        Domoticz.Log("Daily energy consumption updated")

        current_year = datetime.datetime.now().year

        # Step 1: Get all results of the previous years until the last day of the previous year
        last_day_of_last_year = datetime.datetime(current_year - 1, 12, 31)
        yearly_url = f"https://api.bdrthermea.net/Mobile/api/appliances/{appliance_id}/energyconsumption/yearly?startDate=1900-01-01T00:00:00.000Z&endDate={last_day_of_last_year.strftime('%Y-%m-%dT00:00:00.000Z')}"

        # Initialize so a failed GET below cannot cause an UnboundLocalError later on
        total_heating_energy_consumed_yearly = None
        total_heating_energy_delivered_yearly = None
        total_heating_energy_consumed_monthly = None
        total_heating_energy_delivered_monthly = None

        try:
            yearly_response = self._request_with_retry(
                "get",
                yearly_url,
                headers=headers
            )
            yearly_response.raise_for_status()
            yearly_data = yearly_response.json()

            # Extract "heatingEnergyConsumed" from each row in the yearly response body
            heating_energy_consumed_values_yearly = [entry["heatingEnergyConsumed"] for entry in yearly_data["data"]]
            # Energy generated
            heating_energy_delivered_values_yearly = [entry["heatingEnergyDelivered"] for entry in yearly_data["data"]]

            # Calculate total heating energy consumed for yearly data
            total_heating_energy_consumed_yearly = sum(heating_energy_consumed_values_yearly)
            # Energy generated
            total_heating_energy_delivered_yearly = sum(heating_energy_delivered_values_yearly)
        except Exception as e:
            Domoticz.Error(f"Energy consumption: yearly GET failed: {self._format_exception(e)}")

        # Step 2: Get all results of the previous months excluding the current month
        current_month = datetime.datetime.now().month

        # Get the last day of the current month
        last_day_of_current_month = calendar.monthrange(current_year, current_month)[1]

        # Create a datetime object for the last day of the current month
        end_of_current_month = datetime.datetime(current_year, current_month, last_day_of_current_month)

        try:
            monthly_url = f"https://api.bdrthermea.net/Mobile/api/appliances/{appliance_id}/energyconsumption/monthly?startDate={datetime.datetime.now().year}-01-01T00:00:00.000Z&endDate={end_of_current_month.strftime('%Y-%m-%dT00:00:00.000Z')}"
            #print(monthly_url)
            monthly_response = self._request_with_retry(
                "get",
                monthly_url,
                headers=headers
            )
            monthly_response.raise_for_status()
            monthly_data = monthly_response.json()

            # Extract "heatingEnergyConsumed" from each row in the monthly response body
            heating_energy_consumed_values_monthly = [entry["heatingEnergyConsumed"] for entry in monthly_data["data"]]
            # Energy generated
            heating_energy_delivered_values_monthly = [entry["heatingEnergyDelivered"] for entry in monthly_data["data"]]

            # Calculate total heating energy consumed for monthly data
            total_heating_energy_consumed_monthly = sum(heating_energy_consumed_values_monthly)
            # Energy delivered
            total_heating_energy_delivered_monthly = sum(heating_energy_delivered_values_monthly)
        except Exception as e:
            Domoticz.Error(f"Energy consumption: monthly GET failed: {self._format_exception(e)}")

        # If either the yearly or the monthly retrieval failed, skip this cycle
        # (the counters will simply update again at the next full hour)
        if None in (total_heating_energy_consumed_yearly, total_heating_energy_delivered_yearly,
                    total_heating_energy_consumed_monthly, total_heating_energy_delivered_monthly):
            Domoticz.Error("Energy consumption: yearly/monthly data unavailable, skipping counter update this cycle")
            return

         # Combine the totals consumed
        total_heating_energy_consumed = (
        total_heating_energy_consumed_yearly +
        total_heating_energy_consumed_monthly
        )
        # Generated
        total_heating_energy_delivered = (
        total_heating_energy_delivered_yearly +
        total_heating_energy_delivered_monthly
        )

        total_heating_energy_consumed = total_heating_energy_consumed * 1000
        total_heating_energy_delivered = total_heating_energy_delivered * 1000


        # Get the start and end date for today
        today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = datetime.datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)

        # Format the start and end dates in the required format
        today_string = today_start.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        end_of_today_string = today_end.strftime('%Y-%m-%dT%H:%M:%S.999Z')

        try:
            response = self._request_with_retry(
                "get",
                f'https://api.bdrthermea.net/Mobile/api/appliances/{appliance_id}/energyconsumption/daily?startDate={today_string}&endDate={end_of_today_string}',
                headers=headers
            )
            response.raise_for_status()
            response_json = response.json()

            EnergyToday = response_json["data"][0]["heatingEnergyConsumed"]

            EnergyDeliveredToday = response_json["data"][0]["heatingEnergyDelivered"]

            # Initialize the variable to 1, default value if producerType is not "HeatPumpAirSource"
            value_seasonalEfficiency = 1

            # Iterate over the producers to find the matching producerType
            for producer in response_json['data'][0]['producerPerformanceStatistics']['producers']:
                if producer['producerType'] == "HeatPumpAirSource":
                    value_seasonalEfficiency = producer['seasonalEfficiency']
                    break  # Exit loop once the producer is found

            EnergyToday = EnergyToday * 1000
            EnergyDeliveredToday = EnergyDeliveredToday * 1000

            # Split the string based on the semicolon
            split_values = (Devices[6].sValue).split(";")
            # Check the value before the semicolon against another string
            DomoticzCurrentConsume = split_values[0]

            if datetime.datetime.now().hour not in (0, 1, 2):
                #if str(DomoticzCurrentConsume) != str(EnergyToday):
                Devices[6].Update(nValue=0, sValue=str(EnergyToday) + ";" + str(total_heating_energy_consumed))
                Devices[10].Update(nValue=0, sValue=str(EnergyDeliveredToday) + ";" + str(total_heating_energy_delivered))
                Devices[12].Update(nValue=0, sValue=str(value_seasonalEfficiency), Options={"Custom": "1;SCOP"})
        except Exception as e:
            Domoticz.Error(f"Energy consumption: daily GET failed: {self._format_exception(e)}")


    def check_token_validity(self,acces_token):
        try:
            # Extracting the payload part of the token
            payload = acces_token.split('.')[1]
            # Decoding the payload from base64
            decoded_payload = base64.b64decode(payload + '===').decode('utf-8')
            # Converting the decoded payload to a dictionary
            payload_dict = eval(decoded_payload)

            # Extracting the expiration timestamp
            expiration_timestamp = payload_dict.get('exp')
            if expiration_timestamp:
                #added 5 seconds to be certain that if the token expires in a few seconds a new one is fetched
                current_timestamp = datetime.datetime.now().timestamp() + 5
                if current_timestamp < expiration_timestamp:
                    return "valid"
                else:
                    Domoticz.Log("Token check: Token is invalid, getting new token.....")
                    return "invalid"
            else:
                Domoticz.Log("Token check: Token is invalid, getting new token.....")
                return "invalid"  # If expiration timestamp is not present, consider it invalid
        except Exception as e:
            print("Error:", self._format_exception(e))
        return "invalid"

    def zonemode(self, access_token, level):
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Ocp-Apim-Subscription-Key': 'df605c5470d846fc91e848b1cc653ddf'
            }
        try:
            if level == 0: # Scheduling mode
                json_data = {"heatingProgramId": 1}
                response = self._request_with_retry(
                    "post",
                    f'https://api.bdrthermea.net/Mobile/api/climate-zones/{climate_zone_id}/modes/schedule',
                    headers=headers,
                    json=json_data
                    )
                response.raise_for_status()
                Domoticz.Log("Zonemode succesfully set to Scheduling")
            elif level == 10: # Manual mode
                room_temperature_setpoint = float(Devices[4].sValue)
                json_data = {"roomTemperatureSetPoint": room_temperature_setpoint}
                response = self._request_with_retry(
                    "post",
                    f'https://api.bdrthermea.net/Mobile/api/climate-zones/{climate_zone_id}/modes/manual',
                    headers=headers,
                    json=json_data
                    )
                response.raise_for_status()
                Domoticz.Log("Zonemode succesfully set to Manual")
            elif level == 20: # TemporaryOverride mode
                room_temperature_setpoint = float(Devices[4].sValue)
                json_data = {'roomTemperatureSetPoint': room_temperature_setpoint}
                response = self._request_with_retry(
                    "post",
                    f'https://api.bdrthermea.net/Mobile/api/climate-zones/{climate_zone_id}/modes/temporary-override',
                    headers=headers,
                    json=json_data,
                    )
                response.raise_for_status()
                Domoticz.Log("Zonemode succesfully set to TemporaryOverride")
            elif level == 30: # FrostProtection mode
                response = self._request_with_retry(
                    "post",
                    f'https://api.bdrthermea.net/Mobile/api/climate-zones/{climate_zone_id}/modes/anti-frost',
                    headers=headers,
                    )
                response.raise_for_status()
                Domoticz.Log("Zonemode succesfully set to FrostProtection")

        except Exception as e:
                print("Error:", self._format_exception(e))
                return "invalid"

    def fireplacemode(self, access_token, fireplacemode):
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Ocp-Apim-Subscription-Key': 'df605c5470d846fc91e848b1cc653ddf'
            }
        try:
            if str(value_firePlaceModeActive) == "True": # Fireplace mode currently on
                json_data = {"fireplaceModeActive": False}
                response = requests.post(
                    f'https://api.bdrthermea.net/Mobile/api/climate-zones/{climate_zone_id}/modes/fireplacemode',
                    headers=headers,
                    json=json_data
                    )
                response.raise_for_status()
                Devices[13].Update(nValue=0, sValue="Off")
                Domoticz.Log("Fireplace Mode succesfully set to false")
            elif str(value_firePlaceModeActive) == "False": # Fireplace mode currently off
                json_data = {"fireplaceModeActive": True}
                response = requests.post(
                    f'https://api.bdrthermea.net/Mobile/api/climate-zones/{climate_zone_id}/modes/fireplacemode',
                    headers=headers,
                    json=json_data
                    )
                response.raise_for_status()
                Devices[13].Update(nValue=1, sValue="On")
                Domoticz.Log("Fireplace Mode succesfully set to true")

        except Exception as e:
            print("Error:", self._format_exception(e))
            return "invalid"

    def onheartbeat(self):
        # Check update interval ourselves to avoid error for heartbeat longer than 30 seconds cause hardware errors in domoticz
        if self.LastWebUpdate is not None and (datetime.datetime.now() - self.LastWebUpdate).total_seconds() < self.poll_interval:
            return
        self.LastWebUpdate = datetime.datetime.now()
        Domoticz.Log("Remeha Home plugin heartbeat")
        current_time_minutes = time.localtime().tm_min
        # current_time_seconds = time.localtime().tm_sec

        # Check if the access token exists in the instance variable self and if it's valid
        access_token = getattr(self, 'access_token', None)
        if access_token and self.check_token_validity(access_token) == "valid":
            try:
                self.update_devices(access_token)
                # Check if the current time in minutes is 5, then get the daily energy consumption
                # The API seems to be only updated once an hour so no use to run it more often.
            except Exception as e:
                Domoticz.Error(f"6.Error making POST request: {self._format_exception(e)}")
        else:
            # Access token is expired or doesn't exist in the session, get a new one
            result = self.resolve_external_data()
            if result is not None:
                try:
                    access_token = result.get("access_token")
                    # Save the access token to the session
                    self.access_token = access_token
                    self.update_devices(access_token)
                    # Check if the current time in minutes is 5, then get the daily energy consumption
                    # The API seems to be only updated once an hour so no use to run it more often.
                except Exception as e:
                    Domoticz.Error(f"7.Error making POST request: {self._format_exception(e)}")

        # Do an hourly check for energy consumption between 5 - 15 past the hour depending on the update freq
        seclastupdate = 0
        try:
            lastupdate = Devices[6].LastUpdate
            seclastupdate = time.time() - time.mktime(time.strptime(lastupdate, "%Y-%m-%d %H:%M:%S"))
        except:
            seclastupdate = 99999
        Domoticz.Debug(f"seclastupdate:{seclastupdate:.0f}")
        if seclastupdate > 720 and current_time_minutes < 15 and current_time_minutes > 4:
            self.getDailyEnergyConsumption(access_token)

        self.cleanup()

    def oncommand(self, unit, command, level, hue):
        # Command handling function
        access_token = getattr(self, 'access_token', None)
        if access_token and self.check_token_validity(access_token) == "valid":
            try:
                if unit == 1: # New combined setpoint device
                    if command == 'Set Level':
                        room_temperature_setpoint = float(level)
                        self.set_temperature(access_token, room_temperature_setpoint)
                elif unit == 4:  # setpoint device
                    if command == 'Set Level':
                        room_temperature_setpoint = float(level)
                        self.set_temperature(access_token, room_temperature_setpoint)
                elif unit == 8: # zonemode device
                    self.zonemode(access_token, level)
                elif unit == 13: # fireplace mode
                    self.fireplacemode(access_token, level)
            except Exception as e:
                Domoticz.Error(f"8.Error making POST request: {self._format_exception(e)}")
        else:
             # Access token is expired or doesn't exist in the session, get a new one
            result = self.resolve_external_data()
            if result is not None:
                try:
                    access_token = result.get("access_token")
                    # Save the access token to the session
                    self.access_token = access_token
                    if unit == 4:  # setpoint device
                        if command == 'Set Level':
                            room_temperature_setpoint = float(level)
                            self.set_temperature(access_token, room_temperature_setpoint)
                except Exception as e:
                    Domoticz.Error(f"9.Error making POST request: {e}")
        self.cleanup()

# Create an instance of the RemehaHomeAPI class
_plugin = RemehaHomeAPI()

def onStart():
    _plugin.onStart()

def onStop():
    _plugin.onStop()

def onHeartbeat():
    _plugin.onheartbeat()

def onCommand(unit, command, level, hue):
    _plugin.oncommand(unit, command, level, hue)

def onConfigurationChanged():
    _plugin.readOptions()
