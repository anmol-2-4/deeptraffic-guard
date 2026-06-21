# pipeline_modules.py
import cv2
import numpy as np
import time

class ImageRestorationEngine:
    """Task 1: Handles low-light enhancement and motion de-blurring."""
    @staticmethod
    def enhance(frame, low_light_boost=True, sharpen=True):
        processed = frame.copy()
        if low_light_boost:
            # Convert to YCrCb to equalize brightness channel without ruining colors
            ycrcb = cv2.cvtColor(processed, cv2.COLOR_BGR2YCrCb)
            channels = list(cv2.split(ycrcb))
            channels[0] = cv2.equalizeHist(channels[0])
            ycrcb = cv2.merge(channels)
            processed = cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)
        if sharpen:
            kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
            processed = cv2.filter2D(processed, -1, kernel)
        return processed

class TrafficDetector:
    """Tasks 2 & 4: Simulates object detection model outputs with localized coordinates."""
    @staticmethod
    def detect(frame, conf_threshold=0.5):
        # Format: [x1, y1, x2, y2, class_name, confidence_score]
        # In production, replace this mock data with: model = YOLO('yolov8x.pt'); results = model(frame)
        mock_detections = [
            [150, 350, 450, 750, "motorcycle", 0.92],
            [180, 280, 280, 450, "person", 0.88],  # Rider 1
            [260, 290, 360, 460, "person", 0.84],  # Rider 2
            [320, 300, 420, 470, "person", 0.79],  # Rider 3 (Triple riding!)
            [600, 400, 950, 700, "car", 0.95]
        ]
        return [d for d in mock_detections if d[5] >= conf_threshold]

class ViolationAnalyzer:
    """Task 3: Algorithms evaluating spatial/contextual rule breaches."""
    @staticmethod
    def check_helmet_and_occupancy(detections):
        violations = []
        riders = [d for d in detections if d[4] == "person"]
        motorcycles = [d for d in detections if d[4] == "motorcycle"]
        
        for bike in motorcycles:
            bx1, by1, bx2, by2 = bike[0]:bike[4]
            # Find riders whose bounding boxes overlap with or sit atop the motorcycle region
            bike_riders = []
            for r in riders:
                rx1, ry1, rx2, ry2 = r[0]:r[4]
                # Check spatial intersection
                if rx1 >= bx1 - 50 and rx2 <= bx2 + 50 and ry2 <= by2:
                    bike_riders.append(r)
            
            # 1. Evaluate Triple Riding
            if len(bike_riders) > 2:
                violations.append({
                    "type": "Triple Riding",
                    "confidence": float(np.mean([r[5] for r in bike_riders])),
                    "bbox": bike[0:4]
                })
                
            # 2. Evaluate Helmet Compliance (Simulating a secondary classification head)
            for rider in bike_riders:
                # Mock compliance check: in a real build, pass the head crop to a binary classification model
                if rider[5] < 0.85:  # Simulated trigger for missing helmet
                    violations.append({
                        "type": "Helmet Non-Compliance",
                        "confidence": 0.89,
                        "bbox": rider[0:4]
                    })
        return violations

class LicensePlateOCR:
    """Task 5: Pinpoints number plates and runs OCR character conversion."""
    @staticmethod
    def extract(frame, vehicle_bbox):
        # Simulating plate crop and OCR character reading
        # Real integration: use WPOD-Net or custom YOLO for plate crop, then paddleocr.ocr()
        return {"plate_number": "KA51HG8832", "ocr_confidence": 0.94}