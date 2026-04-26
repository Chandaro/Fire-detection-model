import cv2, os, time, threading, serial
import urllib.request, numpy as np
from ultralytics import YOLO

# ======================
# CONFIG
# ======================
ESP32_PORT    = "COM4"
ESPCAM_STREAM = "http://192.168.1.11:81/stream"

# servo tracking config
CAM_FOV      = 60   # ESP32-CAM FOV degrees
SERVO_CENTER = 45  # your servo center angle
SERVO_MIN    = 0    # servo left limit
SERVO_MAX    = 90   # servo right limit

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
model    = YOLO("{}/fire.pt".format(BASE_DIR))
print("Model loaded!")

# connect ESP32
try:
    esp32 = serial.Serial(ESP32_PORT, 115200, timeout=1)
    time.sleep(2)
    print("ESP32 connected!")
except Exception as e:
    print("ERROR: {}".format(e)); exit()

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

# wait for READY
print("Waiting for ESP32...")
t = time.time() + 15
while time.time() < t:
    if esp32.in_waiting:
        line = esp32.readline().decode().strip()
        print("[ESP32] {}".format(line))
        if "READY" in line: print("ESP32 Ready!"); break
    time.sleep(0.1)

# WiFi stream
class MJPEGStream:
    def __init__(self, url):
        self.url = url; self.frame = None
        self.running = True; self.lock = threading.Lock()
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
                print("Stream connected!")
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
                            with self.lock: self.frame = frame
            except Exception as e:
                print("Stream error: {}".format(e)); time.sleep(2)

    def read(self):
        with self.lock:
            return (True, self.frame.copy()) if self.frame is not None else (False, None)

    def stop(self): self.running = False

# open stream
print("Connecting to stream...")
stream = MJPEGStream(ESPCAM_STREAM)

got = False
for i in range(40):
    ret, frame = stream.read()
    if ret and frame is not None:
        print("Stream live! {}x{}".format(frame.shape[1], frame.shape[0]))
        got = True; break
    time.sleep(0.5); print("Waiting... {}".format(i+1))

if not got:
    print("ERROR: No frame!"); esp32.close(); exit()

# YOLO thread
latest_frame     = None
detection_result = []
yolo_lock        = threading.Lock()
display_lock     = threading.Lock()

def yolo_thread():
    global detection_result
    while True:
        with yolo_lock:
            if latest_frame is None:
                time.sleep(0.01); continue
            frame_copy = latest_frame.copy()
        results = model(frame_copy, conf=0.4, device="cuda", verbose=False)
        boxes   = []
        for r in results:
            for box in r.boxes:
                x1,y1,x2,y2 = map(int, box.xyxy.tolist()[0])
                label = model.names[int(box.cls)]
                conf  = float(box.conf)
                boxes.append((x1,y1,x2,y2,label,conf))
        with display_lock: detection_result = boxes

threading.Thread(target=yolo_thread, daemon=True).start()

# state
fire_active    = False
last_sent      = 0
SEND_INTERVAL  = 0.3
CONFIRM_FRAMES = 1
CLEAR_FRAMES   = 3
fire_cnt = clear_cnt = 0
servo_angle = SERVO_CENTER

cv2.namedWindow("Object Tracking Test", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Object Tracking Test", 960, 720)
print("Tracking test running! Press Q to quit")
print("Move fire left/right - servo should follow!")

while True:
    ret, frame = stream.read()
    if not ret or frame is None:
        time.sleep(0.01); continue

    frame = cv2.resize(frame, (640, 480))
    small = cv2.resize(frame, (320, 240))
    with yolo_lock: latest_frame = small

    fire_in_frame = False
    with display_lock: boxes = list(detection_result)

    for (x1,y1,x2,y2,label,conf) in boxes:
        x1,y1,x2,y2 = x1*2, y1*2, x2*2, y2*2

        if label.lower() in ["fire","flame"]:
            fire_in_frame  = True
            fire_center_x  = (x1 + x2) // 2

            # object tracking angle calculation
            offset       = fire_center_x - 320
            angle_offset = (offset / 320) * (CAM_FOV / 2)
            servo_angle  = int(SERVO_CENTER - angle_offset)
            servo_angle  = max(SERVO_MIN, min(SERVO_MAX, servo_angle))

            # draw tracking line
            cv2.line(frame,(fire_center_x,0),(fire_center_x,480),(0,0,255),2)
            cv2.putText(frame,"Servo:{}deg".format(servo_angle),
                        (x1,y2+25),cv2.FONT_HERSHEY_SIMPLEX,0.7,(0,0,255),2)

        color = (0,0,255) if label.lower() in ["fire","flame"] else (0,165,255)
        cv2.rectangle(frame,(x1,y1),(x2,y2),color,2)
        cv2.putText(frame,"{} {:.2f}".format(label,conf),
                    (x1,y1-10),cv2.FONT_HERSHEY_SIMPLEX,0.6,color,2)

    if fire_in_frame: fire_cnt += 1; clear_cnt = 0
    else: clear_cnt += 1; fire_cnt = 0

    now = time.time()
    if fire_cnt >= CONFIRM_FRAMES and not fire_active:
        fire_active = True
        send("FIRE:{}".format(servo_angle))
        last_sent = now
        print(">>> Tracking! Servo → {}deg".format(servo_angle))

    elif fire_active and fire_in_frame and now-last_sent >= SEND_INTERVAL:
        send("FIRE:{}".format(servo_angle))
        last_sent = now

    elif clear_cnt >= CLEAR_FRAMES and fire_active:
        fire_active = False
        send("CLEAR")
        print(">>> Lost fire - servo center")

    # display
    txt   = "TRACKING servo:{}deg".format(servo_angle) if fire_active else "No Fire - Show lighter"
    color = (0,0,255) if fire_active else (0,255,0)
    cv2.rectangle(frame,(0,0),(frame.shape[1],95),(0,0,0),-1)
    cv2.putText(frame,txt,(10,40),cv2.FONT_HERSHEY_SIMPLEX,0.9,color,2)
    cv2.putText(frame,"FOV:{}deg | Center:{} | Range:{}-{}".format(
                CAM_FOV,SERVO_CENTER,SERVO_MIN,SERVO_MAX),
                (10,80),cv2.FONT_HERSHEY_SIMPLEX,0.45,(200,200,200),1)

    # center guide line
    cv2.line(frame,(320,0),(320,480),(0,255,0),1)
    cv2.putText(frame,"CENTER",(285,30),cv2.FONT_HERSHEY_SIMPLEX,0.5,(0,255,0),1)

    cv2.imshow("Object Tracking Test", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        send("CLEAR"); break

send("CLEAR"); stream.stop()
cv2.destroyAllWindows(); esp32.close()
print("Done!")