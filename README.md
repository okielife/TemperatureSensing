# Temperature Sensor Development Repository

This repository holds code and resources for our temperature sensor management.

## Current Requirements / Dependencies

- Hardware
  - This is currently targeting Raspberry Pico W (Version 1 - RP2040)
    - I use a WH: https://www.amazon.com/Pico-Raspberry-Pre-Soldered-Dual-core-Processor/dp/B0BK9W4H2Q/
    - I also use a breakout board with screw terminals to avoid soldering: https://www.amazon.com/dp/B0BHZSYTD8/
  - I use a "one-wire" temperature sensor like this: https://www.amazon.com/gp/product/B09NVFJYPS/
- Firmware
  - The most reliable OS I have found is Circuit Python, specifically version 8.2.6
    - UF2 can be downloaded here: https://adafruit-circuit-python.s3.amazonaws.com/bin/raspberry_pi_pico_w/en_US/adafruit-circuitpython-raspberry_pi_pico_w-en_US-8.2.6.uf2
    - And the associated CircuitPython 8.x libraries can be downloaded here: https://github.com/adafruit/Adafruit_CircuitPython_Bundle/releases/download/20241203/adafruit-circuitpython-bundle-8.x-mpy-20241203.zip
    - After flashing the UF2 onto the board, you'll need to copy a few files into the CIRCUITPY/lib folder:
      - `adafruit_onewire/`
      - `adafruit_ds18x20.mpy`
      - `adafruit_requests.mpy`
- Software
  - The actual running code is what is found on this repo, specifically these files:
    - `code.py` which always runs when the board boots up
    - `sensing.py` which includes the actual operational code for sensing temperature and reporting it
    - `settings.toml` which includes the config for this particular temperature sensor board

## Wiring/Build

The wiring for the board right now only includes the temperature sensor, and it's super simple to connect:
 - Temperature Sensor RED TO Pico 3V3OUT
 - Temperature Sensor BLACK TO Pico GND
 - Temperature Sensor YELLOW TO Pico GPXX
   - The GPXX will be defined in the settings.toml file
 - Resistor (~4.7k) CONNECTS EACH Temperature Sensor RED AND Temperature Sensor YELLOW

As mentioned below in the debugging section of this readme, you can jump GP0 and GND to put the board into debug mode.
This wouldn't be used for normal operations, however.

## Software Development / Testing

The code is written in Python, and I intend to cover as much of the code as possible with unit tests.
This is made difficult because it's difficult to actually run CircuitPython in a dev/test environment.
The requirements for the project include stubs for the CircuitPython libraries, but they are empty.

## Overall Workflow

Controller boots, temperature is sensed, data is committed to GitHub, our dashboard updates at: https://okielife.github.io/TempSensors/

### Tags and Releases

I will try to produce tags that link to a specific combination of hardware, firmware, and possibly software.
The first will be something like PicoW1_CircuitPython826

I would love to eventually add this to PyPi.
Someone could buy a board, pip install a specific named version, and get the files copied over to the board.
This may be a stretch...but maybe not.
A custom command in the setup.py attached to the project could take an argument.
Based on this, it would simply grab the right CircuitPython, extract it, grab libraries and code, and drop it on the board.
The only thing that would be needed set up would be the stuff that goes in the settings.toml file.

## Debugging

### Data Cord Check

It's silly, but happens more often than I'd like to admit.
When connecting this up to the computer, it may act like it's broken, simply because it's a power-only micro USB cord.
Double check this before assuming the board is dead.

### Debug Mode

When the Pico boots up, it automatically runs any code in code.py (or main.py).
By default, the code.py file in this project will instantiate sensors and begin running.
During development or debugging, it is helpful to avoid having this happen.
If a jumper wire is placed between terminals GP0 and ground, it will alert the Pico to stop early.
This allows you to plug in the board and run scripts without conflicting with the auto-running code.

> [!TIP]
> In debug mode, the LED will flash steadily.  If the board doesn't run and you notice this flash, check if it's jumped!

### Storage Cleanup

If something goes awry with the storage on the board, corrupted in any way, you can try to clean it up with some Python

```python
import storage
storage.erase_filesystem()
```

