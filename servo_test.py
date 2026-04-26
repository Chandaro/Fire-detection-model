from machine import Pin, PWM
import time

servo = PWM(Pin(13), freq=50)

def set_angle(angle):
    angle = max(0, min(180, angle))
    duty  = int(26 + (angle / 180) * 102)
    servo.duty(duty)
    print("Angle: {}  ->  Duty: {}".format(angle, duty))

# test angles on startup
print("=== SERVO TEST ===")
print("Testing 0, 45, 90, 135, 180 ...")

for a in [0, 45, 90, 135, 180]:
    set_angle(a)
    time.sleep(1.5)

print("Done. Now call set_angle(X) in REPL to test your angle.")
print("Example: set_angle(45)")
