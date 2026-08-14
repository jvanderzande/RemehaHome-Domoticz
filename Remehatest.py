#!/usr/bin/env python3
"""Manual test runner for the active Remeha Home plugin implementation.

python Remehatest.py --email your@email.com --password yourpassword --action login
python Remehatest.py --email your@email.com --password yourpassword --action update
python Remehatest.py --email your@email.com --password yourpassword --action set-temp 16.0
-or-
set REMEHA_EMAIL=your@email.com
set REMEHA_PASSWORD=yourpassword
python Remehatest.py --action login

This script intentionally imports the live code from plugin.py so it does not drift
from the production implementation when the plugin changes.
"""

from __future__ import annotations

import argparse
import os
import sys
import types
import datetime
from pathlib import Path

WORKDIR = Path(__file__).resolve().parent
if str(WORKDIR) not in sys.path:
    sys.path.insert(0, str(WORKDIR))

# Stub the minimal Domoticz runtime required to load the real plugin code.
Domoticz = types.ModuleType("Domoticz")
Domoticz.Parameters = {
    "Mode1": "dummy-email",
    "Mode2": "dummy-password",
    "Mode3": "60",
    "Mode4": "Yes",
    "DomoticzVersion": "manual-test",
}
Domoticz.Log = lambda *args, **kwargs: print(*args)
Domoticz.Error = lambda *args, **kwargs: print("[ERROR]", *args)
Domoticz.Status = lambda *args, **kwargs: print("[STATUS]", *args)
Domoticz.Heartbeat = lambda *args, **kwargs: None
Domoticz.Debug = lambda *args, **kwargs: print("[DEBUG]", *args)
Domoticz.Debugging = 0


class FakeDevice:
    """Very small Domoticz-like device implementation used by the live plugin."""

    def __init__(self, Name, Unit, Type=None, Subtype=None, TypeName=None, Used=1, Switchtype=None, Image=None, Options=None, **kwargs):
        self.Name = Name
        self.Unit = Unit
        self.Type = Type
        self.SubType = Subtype
        self.TypeName = TypeName
        self.Used = Used
        self.Switchtype = Switchtype
        self.Image = Image
        self.Options = Options or {}
        self.nValue = 0
        self.sValue = ""

    def Create(self):
        # Domoticz stores devices in a module-global Devices dict. Mirror that here.

        if not hasattr(plugin, "Devices"):
            plugin.Devices = {}
        plugin.Devices[self.Unit] = self
        plugin.__dict__["Devices"] = plugin.Devices
        return self

    def Update(self, nValue=None, sValue=None, Name=None, Used=None, Type=None, Subtype=None, Options=None, **kwargs):
        if nValue is not None:
            self.nValue = nValue
        if sValue is not None:
            self.sValue = str(sValue)
        if Name is not None:
            self.Name = Name
        if Used is not None:
            self.Used = Used
        if Type is not None:
            self.Type = Type
        if Subtype is not None:
            self.SubType = Subtype
        if Options is not None:
            self.Options = Options
        if not hasattr(plugin, "Devices"):
            plugin.Devices = {}
        plugin.Devices[self.Unit] = self
        plugin.__dict__["Devices"] = plugin.Devices
        return self

    def Delete(self):
        if hasattr(plugin, "Devices"):
            plugin.Devices.pop(self.Unit, None)
            plugin.__dict__["Devices"] = plugin.Devices
        return True


Domoticz.Device = FakeDevice
sys.modules.setdefault("Domoticz", Domoticz)

import plugin

# Domoticz plugin code expects a module-level Devices registry and Parameters values.
plugin.Parameters = Domoticz.Parameters
plugin.Devices = {}
plugin.__dict__["Devices"] = plugin.Devices
Devices = plugin.Devices


class ManualRemehaTestRunner:
    """Thin wrapper around the live plugin API class for ad-hoc testing."""

    def __init__(self, email: str, password: str):
        plugin.Parameters["Mode1"] = email
        plugin.Parameters["Mode2"] = password
        plugin.Parameters["Mode3"] = plugin.Parameters.get("Mode3", "60")
        plugin.Parameters["Mode4"] = plugin.Parameters.get("Mode4", "Yes")

        self.api = plugin.RemehaHomeAPI()
        self.api.email = email
        self.api.password = password
        self.api.readOptions()
        self.api.createDevices()

        # Initialize the plugin and load cached tokens
        self.api.onStart()

    def try_cached_token(self):
        """Try to use a cached token if available and valid."""
        if self.api.APItokeninfo.access_token:
            if self.api.check_token_validity(self.api.APItokeninfo.access_token) == "valid":
                print(f"Token loaded from cache file, expires at: {datetime.datetime.fromtimestamp(self.api.APItokeninfo.expires_on)} ({self.api.APItokeninfo.expires_on})")
                return self.api.APItokeninfo.access_token
            else:
                print("Cached token is expired, attempting to refresh...")
                if self.api._refresh_access_token():
                    print("Token refreshed successfully")
                    return self.api.APItokeninfo.access_token
        return None

    def login(self):
        """Attempt login with cached token or full authentication."""
        # Try to use cached token first
        token = self.try_cached_token()
        if token:
            return token

        # If no valid cached token, do full authentication
        print("No valid cached token, performing full authentication...")
        result = self.api._perform_authentication()
        if result is None:
            print("Authentication failed.")
            return None
        token = result.get("access_token")
        print(f"Access token acquired: {token[:20]}..." if token else "No access token returned.")
        return token

    def update(self, access_token: str):

        self.api.update_devices(access_token)

    def set_temperature(self, access_token: str, room_temperature_setpoint: float = 20.0):
        self.api.set_temperature(access_token, room_temperature_setpoint)

    def daily_energy(self, access_token: str):
        self.api.getDailyEnergyConsumption(access_token)

    def cleanup(self):
        self.api.cleanup()


def run_manual_test(email: str, password: str, action: str = "login", temperature: float = 20.0) -> int:
    runner = ManualRemehaTestRunner(email, password)
    try:
        global Devices
        token = runner.login()
        if token is None:
            return 1

        if action in {"update", "all"}:
            print("Updating devices...")
            runner.update(token)
            print("Retrieving daily energy consumption...")
            runner.daily_energy(token)
            print("Devices info retrieved for Domoticz:")
            for unit, device in plugin.Devices.items():
                print({
                    unit: {
                        "Name": device.Name,
                        "Type": device.Type,
                        "sValue": device.sValue,
                        "nValue": device.nValue,
                    }
                })

        if action in {"set-temp", "all"}:
            target_temperature = float(temperature)
            print(f"Setting room temperature to {target_temperature}C")
            runner.update(token)
            runner.set_temperature(token, room_temperature_setpoint=target_temperature)

        if action == "login":
            print("Login succeeded. No extra action requested.")
        return 0
    finally:
        runner.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the active Remeha Home plugin logic without starting the Domoticz runtime."
    )
    parser.add_argument("--email", default=os.getenv("REMEHA_EMAIL"), help="Remeha login email")
    parser.add_argument("--password", default=os.getenv("REMEHA_PASSWORD"), help="Remeha password")
    parser.add_argument(
        "--action",
        choices=["login", "update", "set-temp", "all"],
        default="login",
        help="Which plugin method to exercise after login",
    )
    parser.add_argument(
        "temperature",
        nargs="?",
        type=float,
        default=16.0,
        help="Target room temperature for --action set-temp",
    )
    args = parser.parse_args()

    if not args.email or not args.password:
        parser.error("Provide --email/--password or set REMEHA_EMAIL/REMEHA_PASSWORD.")

    return run_manual_test(args.email, args.password, args.action, args.temperature)


if __name__ == "__main__":
    raise SystemExit(main())
