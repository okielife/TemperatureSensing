# This is the main sensor class code for the temperature sensors.

# Relevant files include:
#  CircuitPython Firmware
#     We are currently using 9.2.1.  Might try 10.0 after release.
#  /lib/
#     Get the following packages from the CircuitPython 9.2.1 library:
#        adafruit_onewire/
#        adafruit_connection_manager.mpy
#        adafruit_ds18x20.mpy
#        adafruit_requests.mpy
#  /sensing.py (this file)
#     Actual sensor class with all functionality for reading and reporting temperatures
#     Runs the sensor code on either an infinite loop, resetting the machine hardware each cycle, or a single pass
#     Run this file from a serial connection to do a single pass for debugging
#  /main.py
#     The Pico primary entry point to the sensor operation.  It will instantiate the sensor and start running the loop.
#     If this file detects the controller is connected to the USB runtime, it won't do anything to allow debugging
#  /settings.toml
#     Configuration specific to this controller, including Wi-Fi information and temperature sensor connections

# if something goes wrong with the CIRCUITPY filesystem, just run
# import storage
# storage.erase_filesystem()

# WIRING CONFIGURATION
# Temperature Sensor RED TO Pico 3V3OUT (Extra 3V outputs can be assigned as csv in the EXTRA_HOTS environment variable)
# Temperature Sensor BLACK TO Pico GND
# Temperature Sensor YELLOW TO Pico GPXX where GPXX is defined in the settings.toml file
# Resistor (~4.7k) CONNECTS EACH Temperature Sensor RED AND Temperature Sensor YELLOW

# DIAGNOSTICS
# Upon booting, there will be one brief burst of LEDs
# After this, the LED will follow one of two paths:
#   - It will do a 2-blink before trying to connect to Wi-Fi.  This 2-blink will repeat until successful.
#   - It will do a 3-blink before trying to query current time.  This 3-blink will repeat until successful.
#   - It will do a 4-blink before trying to send temperature reports to the repo
#   - It will do a 5-blink to signal that the operations were complete, and it is about to rest
#   - It will rest for 15 minutes before rebooting, and during this time there will be a very slow blink

# *** Python Standard Library Imports
from binascii import b2a_base64
from json import dumps
from os import getenv
from ssl import SSLContext
from struct import unpack_from
from sys import exit
from time import localtime, sleep, struct_time

# *** CircuitPython Standard Library Imports
try:
    from board_definitions import raspberry_pi_pico_w as board
except ImportError:  # pragma: no cover
    # noinspection PyPackageRequirements
    import board  # import this whole thing so we can search for symbols on it
from microcontroller import Pin, reset
from digitalio import DigitalInOut, Direction
# noinspection PyPackageRequirements
from rtc import RTC
# noinspection PyPackageRequirements
from wifi import radio

# *** CircuitPython Extra Library Imports
from adafruit_connection_manager import get_radio_socketpool, get_radio_ssl_context
try:
    from adafruit_connection_manager import SocketpoolModuleType
except ImportError:
    # Copied this by tracing the definitions of SocketpoolModuleType...it's just a ModuleType I guess?
    import sys
    SocketpoolModuleType = type(sys)
from adafruit_ds18x20 import DS18X20
from adafruit_onewire.bus import OneWireBus
from adafruit_requests import Session


class Sensor:
    """
    The main Sensor class that captures all operations around setting up network connections,
    instantiating the temperature probes, managing the LED, sending data to GitHub, etc.
    Attributes:
        test_mode (bool): Set to true before calling the run functions to enable test mode
        verbose (bool): Default True, set to False before calling the run functions to hush the output
        success (bool): After running, this flag holds whether the operation was successful
    """

    def __init__(self):
        # noinspection PyUnresolvedReferences
        self.led = DigitalInOut(board.LED)  # Built-in LED
        self.led.direction = Direction.OUTPUT
        self.clock = RTC()
        self.clock.datetime = struct_time((1900, 1, 1, 12, 0, 0, 0, 0, -1))
        self.set_extra_hot_ports()
        self.test_mode = False
        self.verbose = True
        self.success = False

    def print(self, message: str) -> None:
        """
        A print wrapper function that formats the output in a structured way with an optional timestamp
        :param message: The message to be printed
        :return: None
        """
        t = self.clock.datetime
        current = f"{t.tm_year}-{t.tm_mon:02d}-{t.tm_mday:02d}-{t.tm_hour:02d}-{t.tm_min:02d}-{t.tm_sec:02d}"
        if t.tm_year < 2000:
            current = "*******************"
        if self.verbose:
            print(f"{current} : {message}")

    def flash_led(self, num_times: int) -> None:
        """
        A utility function to blink the LED a specific number of times
        :param num_times: The number of times to blink the LED
        :return: None
        """
        self.led.value = False
        for i in range(num_times * 2):
            sleep(0.2)
            self.led.value = not self.led.value
        self.led.value = False
        sleep(1)

    @staticmethod
    def init_connection_variables() -> [SocketpoolModuleType, Session]:
        """
        This function initializes the Wi-Fi on the board, and sets up a https request session for subsequent HTTP calls.
        :return: A tuple containing a Socket Pool and a Session.
        """
        # I thought about doing this in the constructor, but that would make it harder to test because we'd have to
        # mock all this stuff before calling the constructor.  I think I'll leave it as-is.
        pool: SocketpoolModuleType = get_radio_socketpool(radio)
        ssl_context: SSLContext = get_radio_ssl_context(radio)
        requests: Session = Session(pool, ssl_context)
        return pool, requests

    def connect_to_wifi(self) -> None:
        """
        This function attempts to connect to known Wi-Fi networks as specified by the WIFI environment variable.
        Note that this function will continue forever attempting to connect as this may happen from time to time.
        :raises RuntimeError: If WIFI environment variable is not set.
        :return: None
        """
        if radio.ipv4_address:
            return
        self.led.value = False
        wifi_string = getenv("WIFI")
        if not wifi_string:
            raise RuntimeError("WIFI environment variable not set")
        all_wifi_data = wifi_string.strip().split(';')
        while True:
            self.flash_led(2)
            for wifi_data in all_wifi_data:
                name, ssid, pw = [x.strip() for x in wifi_data.split(',')]
                self.print(f"Attempting to connect to {name} wifi {ssid} : {pw}")
                try:
                    radio.connect(ssid, pw)
                    self.print(f"Connected to {name} wifi!")
                    return
                except ConnectionError:
                    continue
            self.print("Still no IP address, sleeping 2 seconds and we'll check again")
            sleep(2)

    @staticmethod
    def github_token(requests: Session) -> str:
        """
        Retrieves a decoded GitHub token from a specific URL where it is "hidden".
        :param requests: The https requests session
        :raises RuntimeError: If TOKEN_URL environment variable is not set
        :return: A string GitHub token, probably like "ghp-abc123..."
        """
        github_token_url = getenv('TOKEN_URL')
        if not github_token_url:
            raise RuntimeError("TOKEN_URL environment variable not set")
        response = requests.get(github_token_url)
        content = response.content.decode('utf-8')
        github_token = ''.join(reversed(content.replace('\n', '')))
        return github_token

    @staticmethod
    def set_extra_hot_ports() -> None:
        """
        Sets up extra ports as high line voltage to allow for easily connecting multiple temperature probes. The
        extra pins should be specified in the EXTRA_HOTS environment variable.
        :return: None
        """
        extra_hots_string = getenv("EXTRA_HOTS")
        if extra_hots_string:
            for extra_hot in extra_hots_string.split(","):
                pin = getattr(board, extra_hot)
                p = DigitalInOut(pin)
                p.switch_to_output(value=True)

    def set_clock_to_cst(self, pool: SocketpoolModuleType) -> None:
        """
        Sets the built-in clock to Central Standard Time using the Adafruit NTP pool and NTP protocol.  Only
        accurate down to the second or so, but that's plenty close for our temperature reporting.
        :param pool: The socket pool that was instantiated using init_connection_variables
        :return:None
        """
        while True:
            try:
                packet = bytearray(48)
                packet[0] = 0b00100011  # LI=0, VN=4, Mode=3 (client)
                addr = pool.getaddrinfo("0.adafruit.pool.ntp.org", 123)[0][4]
                with pool.socket(pool.AF_INET, pool.SOCK_DGRAM) as sock:
                    sock.settimeout(5)
                    sock.sendto(packet, addr)
                    sock.recv_into(packet)
                transmit_ts = unpack_from("!I", packet, offset=40)[0]
                utc_time = transmit_ts - 2208988800  # convert NTP time to Unix time
                cst_offset = -5 * 60 * 60  # ignores DST I think
                time_int = utc_time + cst_offset
                self.clock.datetime = localtime(time_int)
                self.print(f"Pico time set to CST: {self.clock.datetime}")
                return
            except Exception as e:  # pragma: no cover
                # I tried _really_ hard to get this exception.  It's difficult because of the way I am using mock
                # classes, so it's tough to override things later.  Probably worth revisiting later
                self.print(f"Encountered an error trying to set time, will try again: {e}")

    def get_gpio_port_instance(self, port_name: str) -> Pin:
        """
        Gets a Pin instance for a given port name
        :param port_name: The name of a port as found in the board code, like "GP1", "GP2"
        :raises RuntimeError: If the port name cannot be retrieved from the board module.
        :return: A microcontroller Pin instance for that port.
        """
        self.print(f"Attempting to look up pin `{port_name}` in the board module")
        try:
            pin = getattr(board, port_name)
            self.print("Found it!  Moving on")
            return pin
        except AttributeError:
            available_pins = [x for x in dir(board) if not x.startswith('__')]
            raise RuntimeError(f"Could not find port name!  Available names in board are: {available_pins}") from None

    def get_all_sensors_from_env(self) -> dict[str, DS18X20]:
        """
        Gets all sensors to be monitored, as defined in the SENSORS environment variable.
        :raises RuntimeError: If the SENSORS environment variable is not set, or if a sensor cannot be constructed.
        :return: A dictionary of {sensor ID string : DS18X80 probe instance}
        """
        sensors = {}
        self.print("Attempting to get all sensors from env")
        sensors_string = getenv("SENSORS")
        if not sensors_string:
            raise RuntimeError("Environment variable 'SENSORS' not set")
        sensors_data = sensors_string.strip().split(";")
        for sensor_data in sensors_data:
            sensor_id, gpio_port_name = [x.strip() for x in sensor_data.split(',')]
            self.print(f"Parsed: ID: {sensor_id}; Looking up the port as {gpio_port_name}")
            port_var = self.get_gpio_port_instance(gpio_port_name)
            self.print(f"Got a port name as: {sensor_id}, constructing sensor object")
            if self.test_mode:  # pragma: no cover
                # not planning on testing this little test mode class
                class DummySensor:
                    temperature = -10.0
                sensors[sensor_id] = DummySensor()
            else:
                bus = OneWireBus(port_var)
                connected_sensors = bus.scan()
                if len(connected_sensors) > 0:
                    # The adafruit_ds18x20.py file has a type hint of `int` for the second arg, but it's definitely
                    # a OneWireAddress.  I've opened an issue to address it, but for now just ignore the type issue.
                    # https://github.com/adafruit/Adafruit_CircuitPython_DS18X20/issues/33
                    # noinspection PyTypeChecker
                    sensor = DS18X20(bus, connected_sensors[0])
                    self.print(f"Successfully constructed sensor {sensor_id} on port {port_var}")
                    sensors[sensor_id] = sensor
                else:
                    raise RuntimeError(f"Could not construct sensor {sensor_id} on port {port_var}")
        self.print(f"All sensors found: {[x for x in sensors]}")
        return sensors

    def warm_up_temperature_sensors(self, sensors: dict[str, DS18X20]) -> None:
        """
        This function loops over the provided sensor dictionary, calling temperature on each to "warm" them up.  When
        you first call .temperature on them, they can report bad values, so this gets that out of the way.
        :param sensors: The dictionary of sensors, as retrieved from get_all_sensors_from_env()
        :return: None
        """
        for sensor_id, sensor_instance in sensors.items():
            _ = sensor_instance.temperature  # call it once and give it a second to warm it up
            sleep(1)
            self.print(f"Sensor ID {sensor_id} New Temperature = {sensor_instance.temperature}")

    def report_single_sensor(self, requests: Session, sensor_id: str, sensor: DS18X20, token: str) -> bool:
        """
        Reads the current temperature, builds an HTTPS PUT request, and reports this sensor to GitHub
        :param requests: The HTTPS requests instance
        :param sensor_id: The ID of the sensor, such as "Pantry East"
        :param sensor: The associated DS18X20 sensor instance
        :param token: The string GitHub token which write access to the TempSensors repository.
        :return: A boolean, true if successful, false otherwise.
        """
        t = self.clock.datetime
        current = f"{t.tm_year}-{t.tm_mon:02d}-{t.tm_mday:02d}-{t.tm_hour:02d}-{t.tm_min:02d}-{t.tm_sec:02d}"
        file_content = f"""---
sensor_id: {sensor_id}
temperature: {sensor.temperature}
measurement_time: {current}
---
{{}}
        """
        file_name = f"{current}_{sensor_id}.html"
        file_path = f"_posts/{sensor_id}/{file_name}"
        url = f"https://api.github.com/repos/okielife/TempSensors/contents/{file_path}"
        headers = {'Accept': 'application/vnd.github + json', 'Authorization': f'Token {token}'}
        encoded_content = b2a_base64(file_content.encode()).decode()
        data = {'message': f"Updating {file_path}", 'content': encoded_content}
        try:
            response = requests.put(url, headers=headers, data=dumps(data))
        except (RuntimeError, OSError) as e:
            self.print(f"Could not send request, reason={e}, skipping this report, checks will continue")
            return False
        if response.status_code in (200, 201):
            self.print("PUT Complete: File created/updated successfully.")
            return True
        else:
            self.print(f"PUT Error: {response.text}")
            return False

    def report_all_sensors(self, requests: Session, sensors: dict[str, DS18X20]) -> None:
        """
        This function loops over the provided sensor dictionary and reports each one of them to GitHub
        :param requests: The HTTPS requests instance
        :param sensors: The dictionary of sensors, as retrieved from get_all_sensors_from_env()
        :raises RuntimeError: If any of the sensors fail to report
        :return: None
        """
        self.flash_led(4)
        token = self.github_token(requests)
        complete_success = True
        for sensor_id, sensor_instance in sensors.items():
            success = self.report_single_sensor(requests, sensor_id, sensor_instance, token)
            if not success:
                complete_success = False
        self.flash_led(5)
        if not complete_success:
            raise RuntimeError("Could not complete all sensor reporting")

    def run_once(self):
        """
        Run one sweep of the temperature sensing process, including setting up the network, reading temp, and reporting.
        :return: None, just check self.success for the result
        """
        try:
            pool, requests = self.init_connection_variables()
            self.connect_to_wifi()
            self.set_clock_to_cst(pool)
            sensors = self.get_all_sensors_from_env()
            self.warm_up_temperature_sensors(sensors)
            self.report_all_sensors(requests, sensors)
            self.success = True
        # not covering all of these exceptions in unit test coverage, each function is tested separately
        except KeyboardInterrupt:  # pragma: no cover
            self.print("Encountered keyboard interrupt, exiting")
        except RuntimeError as e:  # most issues are propagated through RuntimeErrors
            self.print(f"Runtime error in run() function, reason: {e}")
        except Exception as e:  # pragma: no cover
            self.print(f"Unexpected error in run() function, reason: {e}")

    def run_loop(self):
        """
        So this function calls run_once to perform a single full sweep of the sensing process.  However, with this
        entry point, it will then sleep for a while (40 minutes if it was successful, 10 minutes if it wasn't), and then
        BOOM hardware resets the whole microcontroller.  The idea is that this function should be called by the
        microcontroller's automatic entry point, so that it will immediately be called right back again.  This avoids
        having to enable hardware watchdogs, and also avoids memory issues if a loop continues for so long and there
        is any miniscule memory leak or issue.
        :return: None, just check self.success for the result
        """
        self.run_once()
        if self.success:  # success
            # during this time, we'll steadily blink the light 1s on and 1s off
            data_frequency_minutes = 40
            data_frequency_seconds = data_frequency_minutes * 60
            self.led.value = False
            for _ in range(data_frequency_seconds):
                self.led.value = not self.led.value
                sleep(2)
            self.led.value = False
        else:  # failure
            # sleep for a bit then reset
            failure_sleep_minutes = 10
            failure_sleep_seconds = failure_sleep_minutes * 60
            self.led.value = False
            for _ in range(failure_sleep_seconds):
                for _ in range(20):
                    self.led.value = not self.led.value
                    sleep(0.1)
                sleep(1)
            self.led.value = False
        # regardless of outcome, do a hardware reset to start all over
        reset()


if __name__ == "__main__":  # pragma: no cover
    s = Sensor()
    s.run_once()
    exit(0 if s.success else 1)
