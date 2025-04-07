# CircuitPython library imports
try:
    from board_definitions import raspberry_pi_pico_w as board
except ImportError:  # pragma: no cover
    # noinspection PyPackageRequirements
    import board  # import this whole thing so we can search for symbols on it
from binascii import b2a_base64
from digitalio import DigitalInOut
from json import dumps
from os import getenv
# noinspection PyPackageRequirements
from rtc import RTC
from ssl import SSLContext
from struct import unpack_from
from sys import exit
from time import localtime, sleep
# noinspection PyPackageRequirements
from wifi import radio

# Adafruit library imports
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

    def __init__(self, _led: DigitalInOut):
        self.led = _led
        self.set_extra_hot_ports()
        self.test_mode = False
        self.verbose = True
        self.success = False

    def run_once(self):
        try:
            clock = RTC()
            pool, requests = self.init_connection_variables()
            self.connect_to_wifi()
            self.set_clock_to_cst(pool, clock)
            sensors = self.get_all_sensors_from_env(clock)
            self.warm_up_temperature_sensors(sensors, clock)
            self.report_all_sensors(requests, clock, sensors)
            self.success = True
        # not covering all of these exceptions in unit test coverage, each function is tested separately
        except KeyboardInterrupt:  # pragma: no cover
            self.print("Encountered keyboard interrupt, exiting")
        except ConnectionError as e:  # pragma: no cover
            self.print(f"Could not find network with that SSID or failed to connect: {e}")
        except Exception as e:
            self.print(f"Unexpected error in run() function, reason: {e}")

    def print(self, message: str, clock: RTC = None) -> None:
        if clock:
            t = clock.datetime
            current = f"{t.tm_year}-{t.tm_mon:02d}-{t.tm_mday:02d}-{t.tm_hour:02d}-{t.tm_min:02d}-{t.tm_sec:02d}"
        else:
            current = "*******************"
        if self.verbose:
            print(f"{current} : {message}")

    def flash_led(self, num_times: int) -> None:
        self.led.value = False
        for i in range(num_times * 2):
            sleep(0.2)
            self.led.value = not self.led.value
        self.led.value = False
        sleep(1)

    @staticmethod
    def init_connection_variables() -> [SocketpoolModuleType, Session]:
        # Initialize Wi-Fi, Socket Pool, Request Session
        pool: SocketpoolModuleType = get_radio_socketpool(radio)
        ssl_context: SSLContext = get_radio_ssl_context(radio)
        requests: Session = Session(pool, ssl_context)
        return pool, requests

    def connect_to_wifi(self) -> None:
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
        github_token_url = getenv('TOKEN_URL')
        if not github_token_url:
            raise RuntimeError("TOKEN_URL environment variable not set")
        response = requests.get(github_token_url)
        content = response.content.decode('utf-8')
        github_token = ''.join(reversed(content.replace('\n', '')))
        return github_token

    @staticmethod
    def set_extra_hot_ports() -> None:
        """Set up any extra ports to output high for easier wiring"""
        extra_hots_string = getenv("EXTRA_HOTS")
        if extra_hots_string:
            for extra_hot in extra_hots_string.split(","):
                pin = getattr(board, extra_hot)
                p = DigitalInOut(pin)
                p.switch_to_output(value=True)

    def set_clock_to_cst(self, pool: SocketpoolModuleType, clock: RTC) -> None:
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
                clock.datetime = localtime(time_int)
                self.print(f"Pico time set to CST: {clock.datetime}", clock)
                return
            except Exception as e:  # pragma: no cover
                # I tried _really_ hard to get this exception.  It's difficult because of the way I am using mock
                # classes, so it's tough to override things later.  Probably worth revisiting later
                self.print(f"Encountered an error trying to set time, will try again: {e}", clock)

    def get_gpio_port_instance(self, clock: RTC, port_name: str):  # should be returning a Pin
        self.print(f"Attempting to look up pin `{port_name}` in the board module", clock)
        try:
            pin = getattr(board, port_name)
            self.print("Found it!  Moving on", clock)
            return pin
        except AttributeError:
            available_pins = [x for x in dir(board) if not x.startswith('__')]
            self.print(f"Could not find port name!  Available names in board are: {available_pins}", clock)
            raise

    def get_all_sensors_from_env(self, clock: RTC) -> dict[str, DS18X20]:
        sensors = {}
        self.print("Attempting to get all sensors from env", clock)
        sensors_string = getenv("SENSORS")
        if not sensors_string:
            raise RuntimeError("Environment variable 'SENSORS' not set")
        sensors_data = sensors_string.strip().split(";")
        for sensor_data in sensors_data:
            sensor_id, gpio_port_name = [x.strip() for x in sensor_data.split(',')]
            self.print(f"Parsed: ID: {sensor_id}; Looking up the port as {gpio_port_name}", clock)
            port_var = self.get_gpio_port_instance(clock, gpio_port_name)
            self.print(f"Got a port name as: {sensor_id}, constructing sensor object", clock)
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
                    self.print(f"Successfully constructed sensor {sensor_id} on port {port_var}", clock)
                    sensors[sensor_id] = sensor
                else:
                    raise RuntimeError(f"Could not construct sensor {sensor_id} on port {port_var}", clock)
        self.print(f"All sensors found: {[x for x in sensors]}", clock)
        return sensors

    def warm_up_temperature_sensors(self, sensors: dict[str, DS18X20], clock) -> None:
        for sensor_id, sensor_instance in sensors.items():
            _ = sensor_instance.temperature  # call it once and give it a second to warm it up
            sleep(1)
            self.print(f"Sensor ID {sensor_id} New Temperature = {sensor_instance.temperature}", clock)

    def report_single_sensor(self, clock: RTC, requests: Session, sensor_id: str, sensor: DS18X20, token: str) -> bool:
        t = clock.datetime
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
            self.print(f"Could not send request, reason={e}, skipping this report, checks will continue", clock)
            return False
        if response.status_code in (200, 201):
            self.print("PUT Complete: File created/updated successfully.", clock)
            return True
        else:
            self.print(f"PUT Error: {response.text}", clock)
            return False

    def report_all_sensors(self, requests: Session, clock: RTC, sensors: dict[str, DS18X20]) -> bool:
        self.flash_led(4)
        token = self.github_token(requests)
        complete_success = True
        for sensor_id, sensor_instance in sensors.items():
            success = self.report_single_sensor(clock, requests, sensor_id, sensor_instance, token)
            if not success:
                complete_success = False
        self.flash_led(5)
        return complete_success


if __name__ == "__main__":  # pragma: no cover
    # noinspection PyUnresolvedReferences
    led = DigitalInOut(board.LED)  # Built-in LED
    led.switch_to_output(value=True)
    s = Sensor(led)
    s.run_once()
    exit(0 if s.success else 1)
