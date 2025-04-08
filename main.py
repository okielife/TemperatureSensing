from time import sleep

# noinspection PyPackageRequirements
import supervisor

from sensing import Sensor

if supervisor.runtime.usb_connected:
    print("Serial USB connected detected, skipping any code, run it manually from IDE")
    while True:
        sleep(1)
else:
    Sensor().run_loop()
