# cv_engine.py
import cv2
import numpy as np
from ultralytics import YOLO

# Load YOLOv8 for edge inference
model = YOLO('yolov8n.pt')

class TrafficAnalyzer:
    @staticmethod
    def run_inference(image, stop_line_ratio=0.8, parking_zone_ratio=0.6):
        """Runs REAL object detection and applies Computer Vision heuristics"""
        results = model(image)[0]
        detections = []
        
        boxes = results.boxes.xyxy.cpu().numpy()
        confs = results.boxes.conf.cpu().numpy()
        classes = results.boxes.cls.cpu().numpy()
        
        for box, conf, cls in zip(boxes, confs, classes):
            class_id = int(cls)
            label = model.names[class_id]
            
            if label in ['car', 'motorcycle', 'bus', 'truck']:
                detections.append({
                    "bbox": [int(x) for x in box],
                    "class": label,
                    "conf": float(conf),
                    "attr": {}
                })
            elif label == 'person':
                # --- REAL CV HELMET DETECTION HEURISTIC ---
                x1, y1, x2, y2 = [int(x) for x in box]
                
                # Crop the top 20% of the person's bounding box (The Head Region)
                head_bottom = y1 + int((y2 - y1) * 0.25)
                head_region = image[y1:head_bottom, x1:x2]
                
                has_helmet = True # Assume helmet is present unless skin is detected
                
                if head_region.size > 0:
                    # Convert to HSV color space for accurate skin tone masking
                    hsv = cv2.cvtColor(head_region, cv2.COLOR_RGB2HSV)
                    
                    # Define lower and upper bounds for human skin tones (works for diverse skin types)
                    lower_skin = np.array([0, 30, 60], dtype=np.uint8)
                    upper_skin = np.array([20, 170, 255], dtype=np.uint8)
                    
                    # Create a mask highlighting skin pixels
                    mask = cv2.inRange(hsv, lower_skin, upper_skin)
                    skin_ratio = cv2.countNonZero(mask) / (head_region.shape[0] * head_region.shape[1] + 1)
                    
                    # If more than 8% of the head region is exposed skin, flag as No Helmet
                    if skin_ratio > 0.08:
                        has_helmet = False
                
                detections.append({
                    "bbox": [x1, y1, x2, y2],
                    "class": "person",
                    "conf": float(conf),
                    "attr": {"helmet": has_helmet}
                })

        # Map 'persons' to 'motorcycles' to classify them as 'riders'
        motorcycles = [d for d in detections if d['class'] == 'motorcycle']
        for d in detections:
            if d['class'] == 'person':
                is_rider = False
                px1, py1, px2, py2 = d['bbox']
                
                for m in motorcycles:
                    mx1, my1, mx2, my2 = m['bbox']
                    # Spatial overlap check: Is the person physically touching the motorcycle?
                    if px1 < mx2 and px2 > mx1 and py1 < my2 and py2 > my1:
                        is_rider = True
                        break
                
                if is_rider:
                    d['class'] = 'rider'
        
        # Dynamic Environmental Context based on UI Sliders
        height, width, _ = image.shape
        context = {
            "stop_line_y": int(height * stop_line_ratio), 
            "no_parking_zone": [int(width * parking_zone_ratio), 0, width, int(height * 0.4)]
        }
        
        return detections, context

    @staticmethod
    def evaluate_violations(detections, context):
        violations = []
        
        motorcycles = [d for d in detections if d['class'] == 'motorcycle']
        riders = [d for d in detections if d['class'] == 'rider']
        cars = [d for d in detections if d['class'] in ['car', 'bus', 'truck']]
        
        # 1. Evaluate Two-Wheeler Infractions
        for bike in motorcycles:
            bx1, by1, bx2, by2 = bike['bbox']
            bike_riders = [r for r in riders if r['bbox'][0] >= bx1 - 40 and r['bbox'][2] <= bx2 + 40]
            
            # Triple Riding
            if len(bike_riders) > 2:
                violations.append({"type": "Triple Riding", "bbox": bike['bbox'], "severity": "Critical"})
                
            # Helmet Compliance
            for rider in bike_riders:
                if not rider['attr'].get('helmet', True):
                    violations.append({"type": "Helmet Non-Compliance", "bbox": rider['bbox'], "severity": "High"})

        # 2. Evaluate Four-Wheeler Infractions
        for car in cars:
            cx1, cy1, cx2, cy2 = car['bbox']
            
            # Stop Line Crossing
            if cy2 > context['stop_line_y']:
                violations.append({"type": "Stop-Line Violation", "bbox": car['bbox'], "severity": "Medium"})
                    
            # Illegal Parking
            px1, py1, px2, py2 = context['no_parking_zone']
            if cx1 >= px1 and cy1 >= py1 and cx2 <= px2 and cy2 <= py2:
                violations.append({"type": "Illegal Parking", "bbox": car['bbox'], "severity": "Low"})

        return violations