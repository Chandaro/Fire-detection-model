import cv2
import urllib.request
import numpy as np
import time
from ultralytics import YOLO as YOLOv10
import os

# Mô hình yolov10 phát hiện lửa
model = YOLOv10(f"{os.path.dirname(os.path.abspath(__file__))}/fire.pt")

# Địa chỉ IP của ESP32-CAM
url = "http://192.168.1.11:81/stream"


# Đọc và hiển thị hình ảnh từ ESP32-CAM
def stream_video(url):
    bytes_stream = b""

    while True:
        try:
            with urllib.request.urlopen(url, timeout=10) as stream:
                while True:
                    bytes_stream += stream.read(1024)
                    a = bytes_stream.find(b"\xff\xd8")  # Start of JPEG
                    b = bytes_stream.find(b"\xff\xd9")  # End of JPEG

                    if a != -1 and b != -1:
                        jpg = bytes_stream[a : b + 2]
                        bytes_stream = bytes_stream[b + 2 :]

                        img_np = np.frombuffer(jpg, dtype=np.uint8)
                        img = cv2.imdecode(img_np, cv2.IMREAD_COLOR)

                        if img is not None:
                            # Fire detection
                            results = model(img, conf=0.8, device="cpu")
                            # Draw bounding boxes
                            for result in results:
                                boxes = result.boxes
                                for box in boxes:
                                    x1, y1, x2, y2 = box.xyxy.tolist()[0]
                                    c = box.cls
                                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                                    label = model.names[int(c)]
                                    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)
                                    cv2.putText(
                                        img,
                                        label,
                                        (x1, y1 - 10),
                                        cv2.FONT_HERSHEY_SIMPLEX,
                                        0.9,
                                        (0, 255, 0),
                                        2,
                                    )

                            cv2.imshow("ESP32-CAM Stream", img)

                        if cv2.waitKey(1) & 0xFF == ord("q"):
                            cv2.destroyAllWindows()
                            return
        except urllib.error.HTTPError as e:
            print(f"HTTP Error: {e.code} - {e.reason}")
            time.sleep(1)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)


if __name__ == "__main__":
    stream_video(url)
