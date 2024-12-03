# Python standard library imports
import board  # import this whole thing so we can search for symbols on it
from board import LED
from binascii import b2a_base64
from digitalio import DigitalInOut
from gc import collect
from json import dumps
from microcontroller import watchdog
from os import getenv
from rtc import RTC
from socketpool import SocketPool
from ssl import create_default_context
from time import localtime, sleep, struct_time, mktime
from wifi import radio
from watchdog import WatchDogMode

# Adafruit library imports
from adafruit_ds18x20 import DS18X20
from adafruit_onewire.bus import OneWireBus
from adafruit_requests import Session

# if something goes wrong with the CIRCUITPY filesystem, just run
# import storage
# storage.erase_filesystem()


# WIRING CONFIGURATION
# Temperature Sensor RED TO Pico 3V3OUT
# Temperature Sensor BLACK TO Pico GND
# Temperature Sensor YELLOW TO Pico GPXX where GPXX is defined in the settings.toml file
# Resistor (~4.7k) CONNECTS EACH Temperature Sensor RED AND Temperature Sensor YELLOW
# When plugging this into the computer for development or debugging, you'll want to use a jumper to cross
#  GP0 with GND.  This will skip running the program automatically to avoid behavioral issues.

# BOOT PROCESS
# Upon plugging in, Pico firmware will try to auto-connect to Wi-Fi
# This script then starts calling run() in an infinite loop with a broad exception handler that restarts run()
# Inside run(), there are some one-time calls to ensure wi-fi is connected,
#  set the clock, and initialize the sensors
# Once one-time initialization is done, another infinite loop starts monitoring temps and sending commits to GH
# The Wi-Fi connection is checked each iteration to ensure the device is still active

# DIAGNOSTICS
# Upon booting, the script will turn on the board LED as a health signal
# While Wi-Fi is connecting, the LED will flash in steady pulses of 3
# Once Wi-Fi is connected, it will attempt to access the internet, and it will flash quickly during this
# Once both are connected, it will stay on steady.


TEST_MODE = False


def my_print(clock: RTC, message: str, verbose: bool = True) -> None:
    t = clock.datetime
    current = f"{t.tm_year}-{t.tm_mon:02d}-{t.tm_mday:02d}-{t.tm_hour:02d}-{t.tm_min:02d}-{t.tm_sec:02d}"
    if verbose:
        print(f"{current} : {message}")


def my_sleep(num_seconds: int) -> None:
    for _ in range(num_seconds):
        feed_dog()
        sleep(1)


def feed_dog() -> None:
    try:
        watchdog.feed()
    except ValueError:
        pass  # just let errors happen, keep trying


def flash_led(led_object: DigitalInOut, num_times: int, flash_interval_seconds: float) -> None:
    for i in range(num_times * 2):
        feed_dog()
        sleep(flash_interval_seconds / 2)
        led_object.value = not led_object.value


def connect_to_wifi(status_led: DigitalInOut) -> None:
    if radio.ipv4_address:
        print("******************* : Trying to connect to wifi, but radio already HAS an IP address, carrying on")
        return
    status_led.value = False
    print("******************* : Radio does NOT have an IP address, attempting to connect")
    while True:
        flash_led(status_led, 3, 0.5)
        status_led.value = False
        ssid = getenv("WIFI_SSID")
        pw = getenv("WIFI_PASSWORD")
        print(f"******************* : Attempting to connect to wifi {ssid} : {pw}")
        radio.connect(getenv("WIFI_SSID"), getenv("WIFI_PASSWORD"))
        feed_dog()
        if radio.ipv4_address:
            status_led.value = True
            return
        else:
            print("******************* : Still no IP address, sleeping 2 seconds and we'll check again")
            status_led.value = False
            my_sleep(2)


def disconnect_from_wifi(status_led: DigitalInOut) -> None:
    if not radio.ipv4_address:
        print("******************* : Trying to disconnect to wifi, but IP address is already invalid, carrying on")
        feed_dog()
        return
    status_led.value = False
    print("******************* : Attempting to disable WiFi radio")
    radio.enabled = False
    my_sleep(2)


def set_time_to_unix_time(clock: RTC, https: Session, status_led: DigitalInOut) -> None:
    print("******************* : Attempting to set time")
    connect_to_wifi(status_led)
    feed_dog()
    time_url = "http://worldtimeapi.org/api/timezone/America/Chicago"  # use http to avoid cert issues when setting time
    while True:
        try:
            time_response = https.get(time_url)
            feed_dog()
            break
        except (RuntimeError, OSError):
            my_print(clock, "Could not send request, sleeping 5 seconds and retrying")
            flash_led(status_led, 10, 0.1)
            my_sleep(5)
    data = time_response.json()
    print(f"******************* : Got a timestamp from the worldtimeapi server: {data['datetime']}")
    my_time = data['unixtime'] + data['raw_offset']  # + data['dst_offset']  # current local time ignoring DST for now
    clock.datetime = struct_time(localtime(my_time))
    my_print(clock, f"Pico time set to UTC: {clock.datetime}")
    feed_dog()
    disconnect_from_wifi(status_led)
    feed_dog()


def get_gpio_port_instance(clock: RTC, port_name: str):  # should be returning a Pin
    my_print(clock, f"Attempting to look up pin `{port_name}` in the board module")
    try:
        pin = getattr(board, port_name)
        my_print(clock, "Found it!  Moving on")
        return pin
    except AttributeError:
        available_pins = [x for x in dir(board) if not x.startswith('__')]
        my_print(clock, f"Could not find port name!  Available names in board are: {available_pins}")
        raise


def get_all_sensors_from_env(clock: RTC) -> dict:
    class DummySensor:
        temperature = -10.0

    sensors = {}
    my_print(clock, "Attempting to get all sensors from env")
    for i in range(10):
        sensor_variable_name = f"SENSOR_{i:02}"
        tentative_sensor_and_io_port = getenv(sensor_variable_name)
        if not tentative_sensor_and_io_port:
            continue
        my_print(clock, f"Found variable {sensor_variable_name} in env, parsing!")
        sensor_id, gpio_port_name = tentative_sensor_and_io_port.split(':')
        my_print(clock, f"Parsed: ID: {sensor_id}; Looking up the port as {gpio_port_name}")
        port_var = get_gpio_port_instance(clock, gpio_port_name)
        my_print(clock, f"Got a port name as: {sensor_id}, constructing sensor object")
        if TEST_MODE:
            sensors[sensor_id] = DummySensor()
        else:
            bus = OneWireBus(port_var)
            connected_sensors = bus.scan()
            sensor = DS18X20(bus, connected_sensors[0]) if len(connected_sensors) > 0 else None
            if sensor:
                my_print(clock, f"Successfully constructed sensor {sensor_id} on port {port_var}")
                sensors[sensor_id] = sensor
            else:
                # my_print(clock, "Constructing dummy sensor")
                # sensors[sensor_id] = DummySensor(20.0)
                my_print(clock, f"Could not construct sensor {sensor_id} on port {port_var}; skipping")
        feed_dog()
    return sensors


def report_single_sensor(clock, https, sensor_id, sensor_instance, github_token) -> None:
    t = clock.datetime
    current = f"{t.tm_year}-{t.tm_mon:02d}-{t.tm_mday:02d}-{t.tm_hour:02d}-{t.tm_min:02d}-{t.tm_sec:02d}"
    file_content = f"""---
sensor_id: {sensor_id}
temperature: {sensor_instance.temperature}
measurement_time: {current}
---
{{}}
    """
    file_name = f"{current}_{sensor_id}.html"
    file_path = f"_posts/{sensor_id}/{file_name}"
    url = f"https://api.github.com/repos/okielife/TempSensors/contents/{file_path}"
    headers = {'Accept': 'application/vnd.github + json', 'Authorization': f'Token {github_token}'}
    encoded_content = b2a_base64(file_content.encode()).decode()
    data = {'message': f"Updating {file_path}", 'content': encoded_content}
    try:
        response = https.put(url, headers=headers, data=dumps(data))
    except (RuntimeError, OSError):
        my_print(clock, "Could not send request, skipping this report, checks will continue")
        return
    if response.status_code in (200, 201):
        my_print(clock, "PUT Complete: File created/updated successfully.")
    else:
        my_print(clock, f"PUT Error: {response.text}")
    feed_dog()


def run(status_led: DigitalInOut) -> None:
    # Convert to seconds for calculations
    commit_interval_minutes = 15
    sensing_interval_seconds = 30
    commit_interval_seconds = commit_interval_minutes * 60

    # setup the Pico clock early so we can use it in debug messages
    clock = RTC()

    # set up connection variables
    pool = SocketPool(radio)
    https = Session(pool, create_default_context())  # the pool argument is fine, not sure why it's confused in PyCharm

    # set the time for sensor reporting, this will connect to wifi as needed
    set_time_to_unix_time(clock, https, status_led)

    # Local project settings - must be set in settings.toml or ENV
    github_token_url = getenv('TOKEN_URL')
    response = https.get(github_token_url)
    content = response.content.decode('utf-8')
    github_token = ''.join(reversed(content.replace('\n', '')))
    sensors = get_all_sensors_from_env(clock)
    sensor_ids = [x for x in sensors]  # list the dict keys
    my_print(clock, f"All sensors found: {sensor_ids}")

    # set the to-do time stamps so that they will run the first time
    next_commit_time = mktime(clock.datetime) - commit_interval_seconds

    while True:

        # get the current time for checking what we need to do
        current_time_in_seconds = mktime(clock.datetime)
        feed_dog()

        # sense temperatures (update screen here if it is connected)
        for sensor_id, sensor_instance in sensors.items():
            my_print(clock, f"Sensor ID {sensor_id} New Temperature = {sensor_instance.temperature}")
            feed_dog()

        # if the current time has reached the next commit time, we need to commit!
        if current_time_in_seconds >= next_commit_time:
            # connect back up to wifi
            connect_to_wifi(status_led)
            feed_dog()

            my_print(clock, "Commit time has been reached, attempting to commit")
            for sensor_id, sensor_instance in sensors.items():
                report_single_sensor(clock, https, sensor_id, sensor_instance, github_token)
                feed_dog()
            next_commit_time = current_time_in_seconds + commit_interval_seconds
            feed_dog()

            # disconnect from wifi here
            disconnect_from_wifi(status_led)
            feed_dog()
        else:
            my_print(clock, "Commit time NOT reached, skipping the commit")

        # clean up memory usage, verified heap memory leaks, so this is important!
        collect()
        my_sleep(sensing_interval_seconds)


def main(set_watchdog: bool):
    if set_watchdog:
        # ask the watchdog to reset the board if not fed for a specified number of seconds
        watchdog.timeout = 8
        watchdog.mode = WatchDogMode.RESET
    feed_dog()
    # set up status LED as an output initially ON
    _status_led = DigitalInOut(LED)
    _status_led.switch_to_output(value=True)
    while True:
        feed_dog()
        try:
            run(_status_led)
        except KeyboardInterrupt:
            print("Encountered keyboard interrupt, letting the watchdog sleep and exiting")
            watchdog.mode = None
            break
        except Exception as e:
            print(f"Unexpected error in run() function, retrying, reason: {e}")
            continue


if __name__ == "__main__":
    main(False)  # if we are running this file from and IDE, call main with False to avoid setting up the watchgod
