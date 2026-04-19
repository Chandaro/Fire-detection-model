# 🔥 YOLO Fire Detection — ESP32-CAM + YOLOv10

<div align="center">

![Fire Detection Banner](https://img.shields.io/badge/AI-YOLOv10-red?style=for-the-badge&logo=pytorch)
![Python](https://img.shields.io/badge/Python-3.8+-blue?style=for-the-badge&logo=python)
![OpenCV](https://img.shields.io/badge/OpenCV-4.x-green?style=for-the-badge&logo=opencv)
![IoT](https://img.shields.io/badge/Hardware-ESP32--CAM-orange?style=for-the-badge&logo=espressif)
![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)

**Real-time fire detection powered by a custom-trained YOLOv10 model streamed live from an ESP32-CAM over Wi-Fi.**

</div>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [How It Works](#-how-it-works)
- [Project Structure](#-project-structure)
- [Hardware — ESP32-CAM Setup](#-hardware--esp32-cam-setup)
- [Software Setup](#-software-setup)
- [Running the Project](#-running-the-project)
- [Script Comparison](#-script-comparison-mainpy-vs-newpy)
- [Configuration](#-configuration)
- [Troubleshooting](#-troubleshooting)

---

## 🌐 Overview

This project combines **IoT hardware** (ESP32-CAM) with **AI-powered computer vision** (YOLOv10) to build a real-time fire detection system. The ESP32-CAM captures live video and streams it over a local Wi-Fi network via an HTTP MJPEG server. A Python client on your PC connects to that stream, runs each frame through a custom-trained `fire.pt` model, and draws bounding boxes around any detected fire in real time.

### Key Features

| Feature | Details |
|---|---|
| Real-time inference | Frame-by-frame fire detection from live camera stream |
| Custom YOLO model | `fire.pt` — trained specifically for fire/flame recognition |
| ESP32-CAM integration | Wireless camera server streamed over local Wi-Fi |
| Dual inference modes | CPU mode (stable) & GPU/CUDA mode (fast) |
| Bounding box overlay | Red boxes + green labels drawn directly onto frames |
| Auto-reconnect | `main.py` automatically retries on stream disconnection |

---

## ⚙️ How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                        SYSTEM FLOW                              │
│                                                                 │
│  ┌──────────────┐      HTTP MJPEG       ┌─────────────────────┐ │
│  │  ESP32-CAM   │ ──── Stream ────────▶ │   Python Client     │ │
│  │              │  192.168.1.11:81      │                     │ │
│  │  OV2640      │    /stream endpoint   │  urllib / OpenCV    │ │
│  │  Camera      │                       │        │            │ │
│  │  Module      │                       │        ▼            │ │
│  └──────────────┘                       │   YOLOv10 (fire.pt) │ │
│                                         │        │            │ │
│                                         │        ▼            │ │
│                                         │  Bounding Boxes     │ │
│                                         │  on Live Frame      │ │
│                                         │        │            │ │
│                                         │        ▼            │ │
│                                         │  cv2.imshow()       │ │
│                                         │  Display Window     │ │
│                                         └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Detection Pipeline (step by step)

1. **ESP32-CAM** captures frames and broadcasts an MJPEG stream on `http://<IP>:81/stream`
2. Python opens the HTTP stream using `urllib.request.urlopen`
3. Raw bytes are scanned for JPEG markers (`0xFF 0xD8` = start, `0xFF 0xD9` = end)
4. Each complete JPEG frame is decoded into a NumPy array via `cv2.imdecode`
5. The frame is passed to the YOLOv10 model (`fire.pt`) for inference
6. For every detected fire bounding box, a **red rectangle** and a **green label** are drawn
7. The annotated frame is displayed in a live OpenCV window

---

## 📁 Project Structure

```
YOLO fire detection/
│
├── main.py          # Primary script — manual MJPEG parsing, CPU inference, auto-reconnect
├── new.py           # Alternate script — OpenCV VideoCapture stream, GPU (CUDA) inference
├── fire.pt          # Custom-trained YOLOv10 weights for fire detection
└── requires.txt     # Python dependency list
```

---

## 🛠 Hardware — ESP32-CAM Setup

### What You Need

- **ESP32-CAM module** (AI-Thinker variant recommended)
- **FTDI USB-to-Serial adapter** (for flashing firmware)
- Jumper wires
- 5V power supply (the ESP32-CAM needs stable 5V — USB is usually fine)

### Wiring for Flashing

```
FTDI Adapter     ESP32-CAM
─────────────    ──────────────
GND          ──▶ GND
5V           ──▶ 5V
TX           ──▶ U0R (GPIO3 / RX)
RX           ──▶ U0T (GPIO1 / TX)
GND          ──▶ IO0  ← SHORT this to GND to enter flash mode!
```

> **Important:** The `IO0` pin must be pulled LOW (connected to GND) **before** powering up to enter bootloader/flash mode. After flashing, remove the IO0–GND jumper and reset the board.

### Flashing the Camera Server Firmware

The ESP32-CAM needs to run an HTTP camera server sketch. Use the **Arduino IDE** or **esptool**:

#### Using Arduino IDE

1. Install **ESP32 board support** via Board Manager:  
   `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
2. Open **File → Examples → ESP32 → Camera → CameraWebServer**
3. In the sketch, set your Wi-Fi credentials:
   ```cpp
   const char* ssid     = "YOUR_WIFI_SSID";
   const char* password = "YOUR_WIFI_PASSWORD";
   ```
4. Select the correct camera model (AI-Thinker):
   ```cpp
   #define CAMERA_MODEL_AI_THINKER
   ```
5. Select board: **AI Thinker ESP32-CAM**, port: your COM port
6. Click **Upload** (make sure IO0 is pulled to GND)
7. After upload: remove IO0–GND jumper, press **Reset**

#### Using esptool (CLI)

`esptool` is included in `requires.txt` for flashing via terminal:

```bash
esptool.py --chip esp32 --port COM3 --baud 460800 write_flash -z 0x1000 firmware.bin
```

### Finding the ESP32-CAM IP Address

After booting, the ESP32-CAM connects to Wi-Fi and prints its IP to Serial (115200 baud). Open **Serial Monitor** in Arduino IDE to find it, e.g.:

```
WiFi connected
Camera Ready! Use 'http://192.168.1.11' to connect
Stream available at: http://192.168.1.11:81/stream
```

> The default stream endpoint used in this project is `http://192.168.1.11:81/stream`

---

## 💻 Software Setup

### Prerequisites

- Python 3.8 or higher
- pip
- (Optional) NVIDIA GPU + CUDA drivers for GPU-accelerated inference

### Install Dependencies

```bash
pip install -r requires.txt
```

**`requires.txt` contents:**

| Package | Purpose |
|---|---|
| `opencv-python` | Frame decoding, drawing, display window |
| `ultralytics` | YOLOv10 inference engine |
| `esptool` | ESP32-CAM firmware flashing utility |
| `git+https://github.com/THU-MIG/yolov10.git` | YOLOv10 model architecture |

---

## ▶️ Running the Project

### Step 1 — Update the Stream URL

Edit the `url` variable in either script to match your ESP32-CAM's IP address:

**[main.py](main.py) — line 12:**
```python
url = "http://192.168.1.11:81/stream"   # ← change IP here
```

**[new.py](new.py) — line 7:**
```python
cap = cv2.VideoCapture("http://192.168.1.11:81/stream")  # ← change IP here
```

### Step 2 — Run a Script

**CPU mode (recommended for stability):**
```bash
python main.py
```

**GPU/CUDA mode (faster, requires NVIDIA GPU):**
```bash
python new.py
```

### Step 3 — View the Stream

A window titled **"ESP32-CAM Stream"** (or **"Fire Detection"**) will open showing the live camera feed with fire bounding boxes overlaid.

**To quit:** press `Q` in the video window.

---

## 🔀 Script Comparison: `main.py` vs `new.py`

| Feature | [main.py](main.py) | [new.py](new.py) |
|---|---|---|
| **Stream method** | Manual MJPEG byte parsing via `urllib` | `cv2.VideoCapture` (OpenCV built-in) |
| **Inference device** | CPU (`device="cpu"`) | CUDA/GPU (`device="cuda"`) |
| **Confidence threshold** | `0.8` (high precision) | `0.5` (higher recall) |
| **Auto-reconnect** | Yes — catches exceptions, sleeps 1s, retries | No — exits on stream failure |
| **Reliability** | High — handles unstable streams | Simpler — best for stable connections |
| **Speed** | Moderate (CPU-bound) | Fast (GPU-accelerated) |

**When to use which:**
- Use `main.py` if your Wi-Fi connection to the ESP32-CAM is unstable or for general use.
- Use `new.py` if you have a GPU and a stable network connection for maximum speed.

---

## ⚙️ Configuration

### Confidence Threshold

Controls how certain the model must be before drawing a detection box.

```python
# In main.py
results = model(img, conf=0.8, device="cpu")   # 80% confidence required

# In new.py
results = model(frame, conf=0.5, device="cuda") # 50% confidence required
```

- **Higher value** (e.g. `0.9`) → fewer false positives, may miss small fires
- **Lower value** (e.g. `0.4`) → detects more, may include false positives

### Model Path

The model is loaded using an absolute path derived from the script's location:

```python
model = YOLO(f"{os.path.dirname(os.path.abspath(__file__))}/fire.pt")
```

This ensures the script works regardless of which directory you run it from.

---

## 🔧 Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| `HTTP Error: 404` | Wrong stream URL path | Try `/` or `:80` instead of `:81/stream` |
| `Error: timed out` | ESP32-CAM not on network | Check Wi-Fi credentials, reboot ESP32-CAM |
| `Failed to get frame` | Stream URL unreachable | Verify IP in Serial Monitor output |
| Black/frozen window | JPEG decode failure | Check ESP32-CAM power supply (needs stable 5V) |
| `CUDA not available` | No GPU or no CUDA drivers | Use `main.py` (CPU mode) instead |
| Model not found | Wrong path or missing file | Ensure `fire.pt` is in the same folder as the script |
| Slow inference | CPU bottleneck | Use `new.py` with a CUDA-capable GPU |

---

## 📌 Notes

- The `fire.pt` model is a **custom-trained YOLOv10 model** — it is not a general-purpose YOLO model. It has been specifically trained to detect **fire and flames**.
- The ESP32-CAM's stream runs on **port 81** by default in the CameraWebServer example (the web UI is on port 80).
- The MJPEG stream is parsed manually in `main.py` by looking for JPEG byte markers, which is more robust than relying on OpenCV's built-in stream decoder for ESP32-CAM streams.

---

<div align="center">

Built with Python · OpenCV · YOLOv10 · ESP32-CAM

</div>
