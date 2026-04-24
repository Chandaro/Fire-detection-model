import cv2
from ultralytics import YOLO
import os
import serial
import serial.tools.list_ports
import time
import threading
import urllib.request
import numpy as np

# ======================
# LOAD YOLO MODEL
# ======================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
model    = YOLO("{}/fire.pt".format(BASE_DIR))
print("YOLO model loaded!")
print("Model classes: {}".format(model.names))

# ======================
# CONFIG
# ======================
ESP32_PORT    = "COM4"
ESPCAM_STREAM = "http://192.168.1.11:81/stream"

# ======================
# CONNECT TO ESP32 VIA SERIAL
# ======================
try:
    esp32 = serial.Serial(ESP32_PORT, 115200, timeout=1)
    time.sleep(2)
    print("ESP32 connected at {}".format(ESP32_PORT))
except Exception as e:
    print("ERROR: Cannot connect to ESP32: {}".format(e))
    print("Close Thonny first!")
    exit()

# ======================
# SERIAL READ THREAD
# prints ESP32 output live
# ======================
def read_serial():
    while True:
        try:
            if esp32.in_waiting:
                line = esp32.readline().decode().strip()
                if line:
                    print("[ESP32] {}".format(line))
        except:
            pass

serial_thread = threading.Thread(target=read_serial, daemon=True)
serial_thread.start()

# ======================
# SEND COMMAND TO ESP32
# ~1ms via serial
# ======================
def send_command(cmd):
    try:
        esp32.write("{}\n".format(cmd).encode())
        print("[PC->ESP32] {}".format(cmd))
    except Exception as e:
        print("[ERROR] Serial failed: {}".format(e))

# ======================
# WAIT FOR ESP32 READY
# ======================
print("Waiting for ESP32 READY signal...")
ready_timeout = time.time() + 30
while time.time() < ready_timeout:
    if esp32.in_waiting:
        line = esp32.readline().decode().strip()
        print("[ESP32] {}".format(line))
        if "READY" in line:
            print("ESP32 is ready!")
            break
    time.sleep(0.1)

# ======================
# MJPEG STREAM READER
# ======================
class MJPEGStream:
    def __init__(self, url):
        self.url     = url
        self.frame   = None
        self.running = True
        self.lock    = threading.Lock()
        self.thread  = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        while self.running:
            try:
                req = urllib.request.Request(
                    self.url,
                    headers={
                        "User-Agent"    : "Mozilla/5.0",
                        "Accept"        : "multipart/x-mixed-replace;boundary=frame",
                        "Cache-Control" : "no-cache",
                        "Connection"    : "keep-alive"
                    }
                )
                response   = urllib.request.urlopen(req, timeout=15)
                bytes_data = b""
                print("Stream connected!")
                while self.running:
                    chunk      = response.read(4096)
                    if not chunk:
                        break
                    bytes_data += chunk
                    start = bytes_data.find(b'\xff\xd8')
                    end   = bytes_data.find(b'\xff\xd9')
                    if start != -1 and end != -1:
                        jpg        = bytes_data[start:end + 2]
                        bytes_data = bytes_data[end + 2:]
                        img_array  = np.frombuffer(jpg, dtype=np.uint8)
                        frame      = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                        if frame is not None:
                            with self.lock:
                                self.frame = frame
            except Exception as e:
                print("Stream error: {} - retrying...".format(e))
                time.sleep(2)

    def read(self):
        with self.lock:
            if self.frame is None:
                return False, None
            return True, self.frame.copy()

    def stop(self):
        self.running = False

# ======================
# OPEN STREAM
# ======================
print("Connecting to ESP-CAM: {}".format(ESPCAM_STREAM))
stream = MJPEGStream(ESPCAM_STREAM)

print("Waiting for first frame...")
got_frame = False
for i in range(40):
    ret, frame = stream.read()
    if ret and frame is not None:
        print("Stream live! {}x{}".format(frame.shape[1], frame.shape[0]))
        got_frame = True
        break
    time.sleep(0.5)
    print("Waiting... {}".format(i + 1))

if not got_frame:
    print("ERROR: Cannot get frame!")
    send_command("CLEAR")
    esp32.close()
    exit()

# ======================
# STATE TRACKING
# ======================
fire_active       = False
last_sent         = 0
SEND_INTERVAL     = 1.0
CONFIRM_FRAMES    = 2
CLEAR_FRAMES      = 5
fire_frame_count  = 0
clear_frame_count = 0

# ======================
# WINDOW SETUP
# ======================
cv2.namedWindow("Fire Detection System", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Fire Detection System", 960, 720)

# ======================
# MAIN DETECTION LOOP
# ======================
print("Fire detection running!")
print("Press Q to quit")

while True:
    ret, frame = stream.read()
    if not ret or frame is None:
        time.sleep(0.05)
        continue

    # resize for better detection
    frame = cv2.resize(frame, (640, 480))

    # ======================
    # YOLO DETECTION
    # ======================
    results       = model(frame, conf=0.4, device="cuda", verbose=False)
    fire_in_frame = False

    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy.tolist()[0])
            label = model.names[int(box.cls)]
            conf  = float(box.conf)

            if label.lower() in ["fire", "flame"]:
                fire_in_frame = True

            color = (0, 0, 255) if label.lower() in ["fire", "flame"] else (0, 165, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame,
                        "{} {:.2f}".format(label, conf),
                        (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    # ======================
    # CONFIRM FIRE / CLEAR
    # ======================
    if fire_in_frame:
        fire_frame_count  += 1
        clear_frame_count  = 0
    else:
        clear_frame_count += 1
        fire_frame_count   = 0

    now = time.time()

    if fire_frame_count >= CONFIRM_FRAMES and not fire_active:
        fire_active = True
        send_command("FIRE")
        last_sent = now
        print(">>> FIRE CONFIRMED!")

    elif fire_active and fire_in_frame:
        if now - last_sent >= SEND_INTERVAL:
            send_command("FIRE")
            last_sent = now

    elif clear_frame_count >= CLEAR_FRAMES and fire_active:
        fire_active = False
        send_command("CLEAR")
        print(">>> Fire cleared!")

    # ======================
    # STATUS DISPLAY
    # ======================
    status_text  = "FIRE DETECTED!" if fire_active else "No Fire - Safe"
    status_color = (0, 0, 255)      if fire_active else (0, 255, 0)

    cv2.rectangle(frame, (0, 0), (frame.shape[1], 95), (0, 0, 0), -1)
    cv2.putText(frame, status_text,
                (10, 55),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, status_color, 3)
    cv2.putText(frame,
                "Fire:{}/{} | Clear:{}/{} | Port:{}".format(
                fire_frame_count, CONFIRM_FRAMES,
                clear_frame_count, CLEAR_FRAMES,
                ESP32_PORT),
                (10, 85),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

    cv2.imshow("Fire Detection System", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        send_command("CLEAR")
        break

# ======================
# CLEANUP
# ======================
send_command("CLEAR")
stream.stop()
cv2.destroyAllWindows()
esp32.close()
print("Shutdown cleanly")