# This is the main driver code for the temperature sensors.

# Relevant files include:
#  CircuitPython Firmware
#     We are currently using 9.2.1.  Might try 10.0 after release.
#  /lib/
#     Get the following packages from the CircuitPython 9.2.1 library:
#        adafruit_onewire/
#        adafruit_connection_manager.mpy
#        adafruit_ds18x20.mpy
#        adafruit_requests.mpy
#  /code.py (this file)
#     Runs the sensor code on an infinite loop, resetting the machine hardware each cycle
#     If this file detects the controller is connected to the USB runtime, it won't do anything to allow debugging
#  /settings.toml
#     Configuration specific to this controller, including Wi-Fi information and temperature sensor connections
#  /sensing/sensing.py
#     Actual sensor class with all functionality for reading and reporting temperatures

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

try:
    from board_definitions import raspberry_pi_pico_w as board
except ImportError:
    # noinspection PyPackageRequirements
    import board
from microcontroller import reset
from time import sleep
from digitalio import DigitalInOut, Direction
# noinspection PyPackageRequirements
import supervisor

# Honestly no idea why PyCharm isn't finding the LED attribute on board, it works in sensing.py
# noinspection PyUnresolvedReferences
led = DigitalInOut(board.LED)  # Built-in LED
led.direction = Direction.OUTPUT

if supervisor.runtime.usb_connected:
    print("Serial USB connected detected, skipping any code, run it manually from IDE")
    while True:
        led.value = not led.value  # Toggle LED
        sleep(1)  # Adjust blink speed as needed
else:
    from sensing.sensing import Sensor  # locally, this is inside the sensing package, so nest it
    s = Sensor(led)
    s.run_once()
    if s.success:  # success
        # during this time, we'll steadily blink the light 1s on and 1s off
        data_frequency_minutes = 40
        data_frequency_seconds = data_frequency_minutes * 60
        led.value = False
        for _ in range(data_frequency_seconds // 2):
            led.value = not led.value
            sleep(2)
        led.value = False
    else:  # failure
        # sleep for a bit then reset
        failure_sleep_minutes = 10
        failure_sleep_seconds = failure_sleep_minutes * 60
        led.value = False
        for _ in range(failure_sleep_seconds):
            for _ in range(20):
                led.value = not led.value
                sleep(0.1)
            sleep(1)
        led.value = False

    # regardless of outcome, do a hardware reset to start all over
    reset()
