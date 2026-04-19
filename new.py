import cv2
from ultralytics import YOLO
import os

model = YOLO(f"{os.path.dirname(os.path.abspath(__file__))}/fire.pt")

cap = cv2.VideoCapture("http://192.168.1.11:81/stream")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to get frame")
        break

    # Fire detection
    results = model(frame, conf=0.5, device="cuda")  # use GPU

    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy.tolist()[0])
            label = model.names[int(box.cls)]

            cv2.rectangle(frame, (x1, y1), (x2, y2), (0,0,255), 2)
            cv2.putText(frame, label, (x1, y1-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,255,0), 2)

    cv2.imshow("Fire Detection", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()