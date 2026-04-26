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
# CONFIG
# ======================
GAS_THRESHOLD = 3200

# Servo calibration (verified with servo_test.py):
#   0 deg  = duty 26  (full left)
#   45 deg = duty 51  (center)  <-- confirmed true center
#   90 deg = duty 77  (full right)
SERVO_CENTER = 45   # duty 51 — do not change

current_state   = ""
fire_detected   = False
was_suppressing = False
fire_angle      = SERVO_CENTER

# ======================
# SERVO
# (defined before boot so boot can call it)
# ======================
def set_servo_angle(angle):
    angle = max(0, min(90, angle))          # clamp to 0-90 range
    duty  = int(26 + (angle / 180) * 102)  # verified formula
    servo.duty(duty)

# ======================
# BOOT — everything off, servo to center
# ======================
green.off()
yellow.off()
red.off()
buzzer.off()
relay_speed.off()
relay_pump.off()
set_servo_angle(SERVO_CENTER)   # duty 51 = 45 deg = center
print("BOOT_OK")

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
# ======================
def read_command():
    global fire_detected, fire_angle
    try:
        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            command = sys.stdin.readline().strip()
            if command.startswith("FIRE"):
                fire_detected = True
                if ":" in command:
                    fire_angle = int(command.split(":")[1])
                print("CMD: FIRE angle={}".format(fire_angle))
            elif command == "CLEAR":
                fire_detected = False
                fire_angle    = SERVO_CENTER
                print("CMD: CLEAR")
    except:
        pass

# ======================
# SAFE MODE — servo returns to center (45 deg)
# ======================
def safe_mode():
    green.on()
    yellow.off()
    red.off()
    buzzer.off()
    pump_off()
    set_servo_angle(SERVO_CENTER)
    set_lcd("safe", "SYSTEM SAFE", "No Fire/Gas")

# ======================
# SMOKE MODE — servo stays at center (45 deg)
# ======================
def smoke_mode():
    green.off()
    yellow.on()
    red.off()
    set_lcd("smoke", "SMOKE DETECTED", "WARNING")
    buzzer.on()
    time.sleep(0.1)
    buzzer.off()
    set_servo_angle(SERVO_CENTER)
    pump_on()

# ======================
# FIRE MODE — servo tracks camera angle
# ======================
def fire_mode(angle=SERVO_CENTER):
    green.off()
    yellow.off()
    red.on()
    buzzer.on()
    set_servo_angle(angle)
    set_lcd("fire", "FIRE DETECTED", "DANGER!")
    pump_on()

# ======================
# STOP SUPPRESSION — servo back to center (45 deg)
# ======================
def stop_suppression():
    global was_suppressing
    pump_off()
    set_servo_angle(SERVO_CENTER)
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
    read_command()
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
    read_command()

    gas_value = mq5.read()
    print("GAS:{}|FIRE:{}|ANGLE:{}".format(gas_value, fire_detected, fire_angle))

    if fire_detected:
        was_suppressing = True
        fire_mode(angle=fire_angle)

    elif gas_value >= GAS_THRESHOLD:
        was_suppressing = True
        smoke_mode()

    else:
        if was_suppressing:
            stop_suppression()
        safe_mode()

    time.sleep(0.3)
