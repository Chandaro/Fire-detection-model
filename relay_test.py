from machine import Pin
import time
import sys
import select

relay_speed = Pin(16, Pin.OUT)
relay_pump  = Pin(15, Pin.OUT)

relay_speed.on()   # active LOW: HIGH = OFF
relay_pump.on()    # active LOW: HIGH = OFF
print("=== RELAY TEST ===")
print("a = pump ON")
print("s = pump OFF")
print("==================")

def pump_on():
    relay_pump.off()   # active LOW: LOW = trigger ON
    relay_speed.off()
    print("Pump ON")

def pump_off():
    relay_pump.on()    # active LOW: HIGH = OFF
    relay_speed.on()
    print("Pump OFF")

while True:
    if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
        key = sys.stdin.read(1).strip()
        if key == "a":
            pump_on()
        elif key == "s":
            pump_off()
    time.sleep(0.05)
