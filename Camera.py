import cv2, os, time, threading, serial
import urllib.request, numpy as np
from ultralytics import YOLO

# ======================
# CONFIG
# ======================
ESP32_PORT    = "COM4"
ESPCAM_STREAM = "http://192.168.1.11:81/stream"
BAUD_ESP32    = 115200

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
model    = YOLO("{}/fire.pt".format(BASE_DIR))
print("Model loaded! Classes: {}".format(model.names))

# ======================
# CONNECT ESP32
# ======================
try:
    esp32 = serial.Serial(ESP32_PORT, BAUD_ESP32, timeout=1)
    time.sleep(2)
    print("ESP32 connected at {}".format(ESP32_PORT))
except Exception as e:
    print("ERROR: {} - Close Thonny first!".format(e))
    exit()

def read_serial():
    while True:
        try:
            if esp32.in_waiting:
                line = esp32.readline().decode().strip()
                if line: print("[ESP32] {}".format(line))
        except: pass

threading.Thread(target=read_serial, daemon=True).start()

def send(cmd):
    try:
        esp32.write("{}\n".format(cmd).encode())
        print("[PC->ESP32] {}".format(cmd))
    except Exception as e:
        print("[ERROR] {}".format(e))

# wait for ESP32
print("Waiting for ESP32...")
t = time.time() + 30
while time.time() < t:
    if esp32.in_waiting:
        line = esp32.readline().decode().strip()
        print("[ESP32] {}".format(line))
        if "READY" in line: print("ESP32 Ready!"); break
    time.sleep(0.1)

# ======================
# WIFI STREAM
# always keeps LATEST frame only
# no buffer buildup!
# ======================
class MJPEGStream:
    def __init__(self, url):
        self.url     = url
        self.frame   = None
        self.running = True
        self.lock    = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        while self.running:
            try:
                req = urllib.request.Request(self.url, headers={
                    "User-Agent"    : "Mozilla/5.0",
                    "Accept"        : "multipart/x-mixed-replace;boundary=frame",
                    "Cache-Control" : "no-cache",
                    "Connection"    : "keep-alive"
                })
                res = urllib.request.urlopen(req, timeout=15)
                buf = b""
                print("WiFi stream connected!")
                while self.running:
                    buf += res.read(4096)
                    a = buf.find(b'\xff\xd8')
                    b = buf.find(b'\xff\xd9')
                    if a != -1 and b != -1:
                        frame = cv2.imdecode(
                            np.frombuffer(buf[a:b+2], dtype=np.uint8),
                            cv2.IMREAD_COLOR)
                        buf = buf[b+2:]
                        if frame is not None:
                            with self.lock:
                                self.frame = frame  # always replace with latest
            except Exception as e:
                print("Stream error: {} - retrying...".format(e))
                time.sleep(2)

    def read(self):
        with self.lock:
            return (True, self.frame.copy()) if self.frame is not None else (False, None)

    def stop(self): self.running = False

# open stream
print("Connecting to ESP-CAM: {}".format(ESPCAM_STREAM))
stream = MJPEGStream(ESPCAM_STREAM)

print("Waiting for first frame...")
got = False
for i in range(40):
    ret, frame = stream.read()
    if ret and frame is not None:
        print("Stream live! {}x{}".format(frame.shape[1], frame.shape[0]))
        got = True; break
    time.sleep(0.5); print("Waiting... {}".format(i+1))

if not got:
    print("ERROR: No frame!"); send("CLEAR"); esp32.close(); exit()

# ======================
# YOLO THREAD
# runs detection separately from display
# display never waits for YOLO!
# ======================
latest_frame      = None
detection_result  = []
yolo_lock         = threading.Lock()
display_lock      = threading.Lock()

def yolo_thread():
    global detection_result
    while True:
        with yolo_lock:
            if latest_frame is None:
                time.sleep(0.01)
                continue
            frame_copy = latest_frame.copy()

        # run YOLO on copy
        results = model(frame_copy, conf=0.4, device="cuda", verbose=False)
        boxes   = []
        for r in results:
            for box in r.boxes:
                x1,y1,x2,y2 = map(int, box.xyxy.tolist()[0])
                label = model.names[int(box.cls)]
                conf  = float(box.conf)
                boxes.append((x1,y1,x2,y2,label,conf))

        with display_lock:
            detection_result = boxes

threading.Thread(target=yolo_thread, daemon=True).start()

# ======================
# STATE
# ======================
fire_active    = False
last_sent      = 0
SEND_INTERVAL  = 1.0
CONFIRM_FRAMES = 1
CLEAR_FRAMES   = 3
fire_cnt = clear_cnt = 0

cv2.namedWindow("Fire Detection", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Fire Detection", 960, 720)
print("Running! Press Q to quit")

# ======================
# MAIN LOOP - display only
# never blocked by YOLO!
# ======================
while True:
    ret, frame = stream.read()
    if not ret or frame is None:
        time.sleep(0.01)
        continue

    # resize for display
    frame = cv2.resize(frame, (640, 480))

    # update frame for YOLO thread
    small = cv2.resize(frame, (320, 240))
    with yolo_lock:
        latest_frame = small

    # draw detections from YOLO thread
    fire_in_frame = False
    with display_lock:
        boxes = list(detection_result)

    for (x1,y1,x2,y2,label,conf) in boxes:
        # scale boxes from 320x240 back to 640x480
        x1,y1,x2,y2 = x1*2, y1*2, x2*2, y2*2
        if label.lower() in ["fire","flame"]:
            fire_in_frame = True
        color = (0,0,255) if label.lower() in ["fire","flame"] else (0,165,255)
        cv2.rectangle(frame,(x1,y1),(x2,y2),color,2)
        cv2.putText(frame,"{} {:.2f}".format(label,conf),
                    (x1,y1-10),cv2.FONT_HERSHEY_SIMPLEX,0.6,color,2)

    # fire logic
    if fire_in_frame: fire_cnt += 1; clear_cnt = 0
    else: clear_cnt += 1; fire_cnt = 0

    now = time.time()
    if fire_cnt >= CONFIRM_FRAMES and not fire_active:
        fire_active = True; send("FIRE"); last_sent = now
        print(">>> FIRE CONFIRMED!")
    elif fire_active and fire_in_frame and now-last_sent >= SEND_INTERVAL:
        send("FIRE"); last_sent = now
    elif clear_cnt >= CLEAR_FRAMES and fire_active:
        fire_active = False; send("CLEAR")
        print(">>> Fire cleared!")

    # display
    txt   = "FIRE DETECTED!" if fire_active else "No Fire - Safe"
    color = (0,0,255) if fire_active else (0,255,0)
    cv2.rectangle(frame,(0,0),(frame.shape[1],95),(0,0,0),-1)
    cv2.putText(frame,txt,(10,55),cv2.FONT_HERSHEY_SIMPLEX,1.5,color,3)
    cv2.putText(frame,"Fire:{}/{} | Clear:{}/{} | {}".format(
                fire_cnt,CONFIRM_FRAMES,clear_cnt,CLEAR_FRAMES,ESP32_PORT),
                (10,85),cv2.FONT_HERSHEY_SIMPLEX,0.45,(200,200,200),1)

    cv2.imshow("Fire Detection", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        send("CLEAR"); break

send("CLEAR"); stream.stop()
cv2.destroyAllWindows(); esp32.close()
print("Shutdown cleanly")