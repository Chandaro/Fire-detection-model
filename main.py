from machine import Pin, ADC, PWM, SoftI2C
import time
import sys
import select
from machine_i2c_lcd import I2cLcd

# ======================
# HARDWARE SETUP
# ======================
green = Pin(18, Pin.OUT)
yellow = Pin(2, Pin.OUT)
red = Pin(23, Pin.OUT)
buzzer = Pin(4, Pin.OUT)

relay_speed = Pin(15, Pin.OUT)
relay_pump  = Pin(16, Pin.OUT)

mq5 = ADC(Pin(33))
mq5.atten(ADC.ATTN_11DB)
mq5.width(ADC.WIDTH_12BIT)

servo = PWM(Pin(13), freq=50)

i2c = SoftI2C(sda=Pin(21), scl=Pin(22), freq=400000)
lcd = I2cLcd(i2c, 0x27, 2, 16)

# ======================
# FORCE EVERYTHING OFF AT BOOT
# ======================
green.off()
yellow.off()
red.off()
buzzer.off()
relay_speed.off()
relay_pump.off()
servo.duty(40)
print("BOOT_OK")

# ======================
# CONFIG
# ======================
GAS_THRESHOLD   = 3200
current_state   = ""
fire_detected   = False
was_suppressing = False
servo_aligned   = False

# ======================
# PUMP HELPERS
# ======================
def pump_on():
    relay_speed.on()
    time.sleep(0.1)
    relay_pump.on()
    print("Pump ON")

def pump_off():
    relay_pump.off()
    time.sleep(0.1)
    relay_speed.off()
    print("Pump OFF")

# ======================
# SERVO HELPER
# ======================
def set_servo_angle(angle):
    angle = max(0, min(180, angle))
    duty  = int(26 + (angle / 180) * 102)
    servo.duty(duty)

# ======================
# LCD UPDATE
# ======================
def set_lcd(state, line1, line2=""):
    global current_state
    if state != current_state:
        lcd.clear()
        lcd.putstr(line1)
        lcd.move_to(0, 1)
        lcd.putstr(line2)
        current_state = state

# ======================
# READ SERIAL COMMAND
# non-blocking
# ======================
def read_command():
    global fire_detected
    try:
        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            command = sys.stdin.readline().strip()
            if command == "FIRE":
                fire_detected = True
                print("CMD: FIRE received")
            elif command == "CLEAR":
                fire_detected = False
                print("CMD: CLEAR received")
    except:
        pass

# ======================
# SAFE MODE
# ======================
def safe_mode():
    global servo_aligned
    green.on()
    yellow.off()
    red.off()
    buzzer.off()
    pump_off()
    if servo_aligned:
        set_servo_angle(0)
        servo_aligned = False
    set_lcd("safe", "SYSTEM SAFE", "No Fire/Gas")

# ======================
# SMOKE MODE
# ======================
def smoke_mode():
    global servo_aligned
    green.off()
    yellow.on()
    red.off()
    set_lcd("smoke", "SMOKE DETECTED", "WARNING")
    buzzer.on()
    time.sleep(0.1)
    buzzer.off()
    if not servo_aligned:
        set_servo_angle(90)
        servo_aligned = True
    pump_on()

# ======================
# FIRE MODE
# ======================
def fire_mode():
    global servo_aligned
    green.off()
    yellow.off()
    red.on()
    buzzer.on()
    set_lcd("fire", "FIRE DETECTED", "DANGER!")
    if not servo_aligned:
        set_servo_angle(90)
        servo_aligned = True
    pump_on()

# ======================
# STOP SUPPRESSION
# ======================
def stop_suppression():
    global servo_aligned, was_suppressing
    pump_off()
    set_servo_angle(0)
    servo_aligned   = False
    was_suppressing = False
    print("Suppression stopped")

# ======================
# WARM UP SENSOR
# ======================
print("Warming up MQ-5...")
lcd.clear()
lcd.putstr("Warming up...")
lcd.move_to(0, 1)
lcd.putstr("Please wait...")

for i in range(10):
    read_command()   # check serial during warmup
    time.sleep(1)
    print("Warm up: {}/10".format(i + 1))

print("READY")
lcd.clear()
lcd.putstr("System Ready!")
time.sleep(1)

# ======================
# MAIN LOOP
# ======================
while True:
    # always read serial first
    read_command()

    gas_value = mq5.read()
    print("GAS:{}|FIRE:{}".format(gas_value, fire_detected))

    # ======================
    # PRIORITY SYSTEM
    # ======================
    if fire_detected:
        was_suppressing = True
        fire_mode()

    elif gas_value >= GAS_THRESHOLD:
        was_suppressing = True
        smoke_mode()

    else:
        if was_suppressing:
            stop_suppression()
        safe_mode()

    time.sleep(0.3)