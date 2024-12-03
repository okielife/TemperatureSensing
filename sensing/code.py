import board
from time import sleep
from digitalio import DigitalInOut, Direction, Pull


if __name__ == "__main__":
    # if GP0 is jumped to ground, we won't do anything, especially not set up the watchdog!
    # Configure GPIO pin with internal pull-up resistor then let GND try to pull it back down
    jumper_pin = DigitalInOut(board.GP0)
    jumper_pin.direction = Direction.INPUT
    jumper_pin.pull = Pull.UP
    jumper_is_active = not jumper_pin.value  # GP0 will go to this false/low state when the jumper IS connected
    if jumper_is_active:
        print("Jumper detected between GP0 and GND, stopping script, run it manually from IDE")
        led = DigitalInOut(board.LED)  # Built-in LED
        led.direction = Direction.OUTPUT
        while True:
            led.value = not led.value  # Toggle LED
            sleep(0.5)  # Adjust blink speed as needed
    else:  # No jumper, just run sensing.main(True) so that it sets up the watchdog to run autonomously
        from sensing import main
        main(set_watchdog=True)
