import cv2
import math
import numpy as np
from config import (
    HEAD_CROP_RATIO, SKIN_HSV_LOWER, SKIN_HSV_UPPER,
    SKIN_HSV_LOWER2, SKIN_HSV_UPPER2, SKIN_RATIO_THRESHOLD,
    DARK_HAIR_V_MAX, DARK_HAIR_RATIO_THRESH, HELMET_TEXTURE_THRESH,
    MIN_PERSON_HEIGHT_PX,
    TORSO_CROP_Y_START, TORSO_CROP_Y_END, TORSO_CROP_X_INSET,
    DIAGONAL_EDGE_MIN_ANGLE, DIAGONAL_EDGE_MAX_ANGLE, DIAGONAL_DENSITY_THRESH,
    TRAFFIC_LIGHT_CROP_TOP_FRAC,
    RED_HSV1_LOWER, RED_HSV1_UPPER, RED_HSV2_LOWER, RED_HSV2_UPPER, RED_PIXEL_RATIO_THRESH,
    MAX_RIDERS_PER_BIKE, WRONG_SIDE_HOUGH_THRESH, WRONG_SIDE_MIN_LINE_FRAC,
    PHONE_CLASS, PHONE_PERSON_IOU_THRESH, PHONE_VEHICLE_IOU_THRESH,
)


def _bbox_to_xywh(bbox):
    x1, y1, x2, y2 = bbox
    return x1, y1, x2 - x1, y2 - y1


def _no_helmet_score(crop_rgb):
    """
    Returns a score 0.0–1.0 indicating likelihood of NO helmet.
    Combines three independent signals:

    1. Skin pixels (face/neck visible from side/front view)
    2. Dark hair pixels (top of head visible from above — hair, not helmet)
    3. Texture variance (hair/face is textured; helmet surface is smooth)
    """
    total = crop_rgb.shape[0] * crop_rgb.shape[1] + 1
    hsv  = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2HSV)
    gray = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2GRAY)

    # Signal 1 — Skin tone pixels (face visible from side/front)
    m1 = cv2.inRange(hsv,
                     np.array(SKIN_HSV_LOWER,  np.uint8),
                     np.array(SKIN_HSV_UPPER,  np.uint8))
    m2 = cv2.inRange(hsv,
                     np.array(SKIN_HSV_LOWER2, np.uint8),
                     np.array(SKIN_HSV_UPPER2, np.uint8))
    skin_ratio = cv2.countNonZero(cv2.bitwise_or(m1, m2)) / total

    # Signal 2 — Dark hair pixels (head viewed from above/behind)
    # Restrict to brownish/dark-reddish tones (H < 35 or H > 150 in HSV).
    # This excludes green camo helmet patterns (H ≈ 50-90) and blue helmets.
    # Hair is black/dark-brown → H in [0-35] range; V < DARK_HAIR_V_MAX.
    hair_hue_mask  = (hsv[:, :, 0] < 35) | (hsv[:, :, 0] > 150)
    dark_value_mask = hsv[:, :, 2] < DARK_HAIR_V_MAX
    dark_mask  = hair_hue_mask & dark_value_mask
    dark_ratio = float(dark_mask.sum()) / total

    # Signal 3 — Texture variance (hair is high-variance; helmet is smooth)
    lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    high_texture = lap_var > HELMET_TEXTURE_THRESH

    # Scoring — conservative to avoid false positives on patterned helmets
    score = 0.0
    reasons = []

    if skin_ratio > SKIN_RATIO_THRESHOLD:
        # Skin clearly exposed: scale with how much skin
        skin_score = 0.45 + min(0.35, (skin_ratio - SKIN_RATIO_THRESHOLD) * 4)
        score += skin_score
        reasons.append(f"skin={skin_ratio:.2f}")

    if dark_ratio > DARK_HAIR_RATIO_THRESH and high_texture:
        # Dark + very high texture (true hair has Laplacian > 280, camo helmets don't)
        hair_score = 0.35 + min(0.20, (dark_ratio - DARK_HAIR_RATIO_THRESH) * 1.5)
        score += hair_score
        reasons.append(f"hair={dark_ratio:.2f},tex={lap_var:.0f}")

    # Require combined evidence when skin signal is borderline
    if skin_ratio < SKIN_RATIO_THRESHOLD * 1.5 and not (dark_ratio > DARK_HAIR_RATIO_THRESH and high_texture):
        # Only borderline skin, no hair confirmation → reduce confidence
        score *= 0.5

    return min(score, 0.95), reasons


def check_helmet(detections, image_rgb):
    """
    Helmet non-compliance: three-signal CV analysis on the rider's head region.

    Signals: skin tone pixels (face visible), dark hair pixels (top-of-head
    view), and Laplacian texture variance (hair is rough; helmet is smooth).
    Any one signal above threshold triggers a violation; combined signals
    raise confidence.
    """
    violations = []
    riders = [d for d in detections if d["class"] == "rider"]
    for r in riders:
        x1, y1, x2, y2 = r["bbox"]
        person_h = y2 - y1

        # Head crop: top HEAD_CROP_RATIO of person bbox
        head_bot = y1 + int(person_h * HEAD_CROP_RATIO)
        crop = image_rgb[y1:head_bot, x1:x2]

        if crop.size == 0 or crop.shape[0] < 4 or crop.shape[1] < 4:
            continue

        score, reasons = _no_helmet_score(crop)

        # Very small persons get capped confidence (analysis is unreliable)
        if person_h < MIN_PERSON_HEIGHT_PX:
            score = min(score, 0.45)

        if score >= 0.28:
            violations.append({
                "type": "Helmet Non-Compliance",
                "severity": "High",
                "bbox": r["bbox"],
                "vehicle_class": "motorcycle",
                "confidence": score,
                "license_plate": "N/A",
                "_debug": reasons,
            })
    return violations


def check_triple_riding(detections):
    """
    Triple riding: more than MAX_RIDERS_PER_BIKE persons assigned to one motorcycle.
    """
    violations = []
    motorcycles = [d for d in detections if d["class"] == "motorcycle"]
    for bike in motorcycles:
        bx1, by1, bx2, by2 = bike["bbox"]
        bike_riders = [
            d for d in detections
            if d["class"] == "rider"
            and d["attrs"].get("motorcycle_bbox") == bike["bbox"]
        ]
        # Fallback: spatial proximity if attrs weren't set
        if not bike_riders:
            bike_riders = [
                d for d in detections
                if d["class"] == "rider"
                and d["bbox"][0] >= bx1 - 40 and d["bbox"][2] <= bx2 + 40
            ]
        if len(bike_riders) > MAX_RIDERS_PER_BIKE:
            violations.append({
                "type": "Triple Riding",
                "severity": "Critical",
                "bbox": bike["bbox"],
                "vehicle_class": "motorcycle",
                "confidence": 0.92,
                "license_plate": "N/A",
            })
    return violations


def check_stop_line(detections, stop_line_y, image_rgb):
    """
    Stop-line violation: vehicle bottom edge (y2) crosses the detected stop line.
    Skipped entirely if no stop line was detected in the image.
    """
    if stop_line_y is None:
        return []
    violations = []
    vehicle_classes = {"car", "motorcycle", "bus", "truck"}
    for d in detections:
        if d["class"] not in vehicle_classes:
            continue
        _, _, _, y2 = d["bbox"]
        if y2 > stop_line_y:
            violations.append({
                "type": "Stop-Line Violation",
                "severity": "Medium",
                "bbox": d["bbox"],
                "vehicle_class": d["class"],
                "confidence": 0.85,
                "license_plate": "N/A",
            })
    return violations


def _is_red_light(image_rgb, tl_bbox):
    """Returns True if the traffic light bbox shows a red signal."""
    x1, y1, x2, y2 = tl_bbox
    crop_bot = y1 + int((y2 - y1) * TRAFFIC_LIGHT_CROP_TOP_FRAC)
    crop = image_rgb[y1:crop_bot, x1:x2]
    if crop.size == 0:
        return False
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    m1 = cv2.inRange(hsv, np.array(RED_HSV1_LOWER, np.uint8), np.array(RED_HSV1_UPPER, np.uint8))
    m2 = cv2.inRange(hsv, np.array(RED_HSV2_LOWER, np.uint8), np.array(RED_HSV2_UPPER, np.uint8))
    combined = cv2.bitwise_or(m1, m2)
    ratio = cv2.countNonZero(combined) / (crop.shape[0] * crop.shape[1] + 1)
    return ratio > RED_PIXEL_RATIO_THRESH


def check_red_light(detections, stop_line_y, image_rgb):
    """
    Red-light violation: vehicle crosses stop line while traffic light is red.
    Skipped if no stop line was detected in the image.
    """
    if stop_line_y is None:
        return []
    violations = []
    traffic_lights = [d for d in detections if d["class"] == "traffic light"]
    red_lights = [tl for tl in traffic_lights if _is_red_light(image_rgb, tl["bbox"])]
    if not red_lights:
        return violations

    vehicle_classes = {"car", "motorcycle", "bus", "truck"}
    for d in detections:
        if d["class"] not in vehicle_classes:
            continue
        _, _, _, y2 = d["bbox"]
        if y2 > stop_line_y:
            violations.append({
                "type": "Red-Light Violation",
                "severity": "Critical",
                "bbox": d["bbox"],
                "vehicle_class": d["class"],
                "confidence": 0.88,
                "license_plate": "N/A",
            })
    return violations


def check_wrong_side(detections, image_rgb):
    """
    Wrong-side driving: vehicle centroid is on the wrong side of detected lane center.
    Uses HoughLinesP on bottom half of frame to find lane markings.
    Limitation: works best on straight roads with visible lane markings.
    """
    violations = []
    h, w = image_rgb.shape[:2]
    roi = image_rgb[h // 2:, :]
    gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    min_len = int(w * WRONG_SIDE_MIN_LINE_FRAC)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, WRONG_SIDE_HOUGH_THRESH,
                             minLineLength=min_len, maxLineGap=15)
    if lines is None:
        return violations

    left_xs, right_xs = [], []
    for line in lines:
        x1l, y1l, x2l, y2l = line[0]
        mx = (x1l + x2l) / 2
        if mx < w / 2:
            left_xs.append(mx)
        else:
            right_xs.append(mx)

    if not left_xs or not right_xs:
        return violations

    lane_center = (np.mean(left_xs) + np.mean(right_xs)) / 2

    vehicle_classes = {"car", "motorcycle", "bus", "truck"}
    for d in detections:
        if d["class"] not in vehicle_classes:
            continue
        x1, _, x2, _ = d["bbox"]
        centroid_x = (x1 + x2) / 2
        # Vehicle on far left of lane center with front-facing aspect ratio
        vw = x2 - x1
        _, vy1, _, vy2 = d["bbox"]
        vh = vy2 - vy1
        aspect = vw / max(vh, 1)
        if centroid_x < lane_center * 0.55 and aspect > 1.1:
            conf = min(0.85, 0.5 + (lane_center - centroid_x) / (w + 1))
            violations.append({
                "type": "Wrong-Side Driving",
                "severity": "Critical",
                "bbox": d["bbox"],
                "vehicle_class": d["class"],
                "confidence": conf,
                "license_plate": "N/A",
            })
    return violations


def check_illegal_parking(detections, parking_zone):
    """
    Illegal parking: vehicle significantly overlaps a detected no-parking zone.
    Skipped if no parking zone was detected in the image.
    """
    if parking_zone is None:
        return []
    violations = []
    pzx1, pzy1, pzx2, pzy2 = parking_zone
    vehicle_classes = {"car", "motorcycle", "bus", "truck"}
    for d in detections:
        if d["class"] not in vehicle_classes:
            continue
        vx1, vy1, vx2, vy2 = d["bbox"]
        ix1, iy1 = max(vx1, pzx1), max(vy1, pzy1)
        ix2, iy2 = min(vx2, pzx2), min(vy2, pzy2)
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        v_area = max(1, (vx2 - vx1) * (vy2 - vy1))
        iov = inter / v_area
        if iov > 0.4:
            violations.append({
                "type": "Illegal Parking",
                "severity": "Low",
                "bbox": d["bbox"],
                "vehicle_class": d["class"],
                "confidence": min(0.9, 0.5 + iov),
                "license_plate": "N/A",
            })
    return violations


def check_seatbelt(detections, image_rgb):
    """
    Seatbelt non-compliance: detect absence of diagonal strap in driver torso region.
    Looks for diagonal edge density in the torso crop; low density => no seatbelt visible.
    Confidence is capped at 0.60 due to heuristic limitations.
    """
    violations = []
    cars = [d for d in detections if d["class"] == "car"]
    persons = [d for d in detections if d["class"] == "person"]

    for car in cars:
        cx1, cy1, cx2, cy2 = car["bbox"]
        # Find persons inside the car bbox
        occupants = [
            p for p in persons
            if p["bbox"][0] >= cx1 and p["bbox"][2] <= cx2
            and p["bbox"][1] >= cy1 and p["bbox"][3] <= cy2
        ]
        for occ in occupants:
            px1, py1, px2, py2 = occ["bbox"]
            ph = py2 - py1
            pw = px2 - px1
            ty1 = py1 + int(ph * TORSO_CROP_Y_START)
            ty2 = py1 + int(ph * TORSO_CROP_Y_END)
            tx1 = px1 + int(pw * TORSO_CROP_X_INSET)
            tx2 = px2 - int(pw * TORSO_CROP_X_INSET)
            crop = image_rgb[ty1:ty2, tx1:tx2]
            if crop.shape[0] < 10 or crop.shape[1] < 10:
                continue
            gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 20,
                                    minLineLength=int(crop.shape[0] * 0.2), maxLineGap=5)
            diagonal_len = 0
            if lines is not None:
                for line in lines:
                    x1l, y1l, x2l, y2l = line[0]
                    angle = abs(math.degrees(math.atan2(y2l - y1l, x2l - x1l + 1e-6)))
                    if DIAGONAL_EDGE_MIN_ANGLE <= angle <= DIAGONAL_EDGE_MAX_ANGLE:
                        diagonal_len += math.hypot(x2l - x1l, y2l - y1l)
                    elif 110 <= angle <= 160:
                        diagonal_len += math.hypot(x2l - x1l, y2l - y1l)
            torso_area = max(1, crop.shape[0] * crop.shape[1])
            density = diagonal_len / torso_area
            if density < DIAGONAL_DENSITY_THRESH:
                violations.append({
                    "type": "Seatbelt Non-Compliance",
                    "severity": "High",
                    "bbox": occ["bbox"],
                    "vehicle_class": "car",
                    "confidence": min(0.60, 0.35 + (DIAGONAL_DENSITY_THRESH - density) * 5),
                    "license_plate": "N/A",
                })
    return violations


def _iou_fraction(a, b):
    """Intersection / area_of_a."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area_a = max(1, (a[2] - a[0]) * (a[3] - a[1]))
    return inter / area_a


def check_phone_use(detections):
    """
    Phone use while driving/riding.

    Triggers when a detected 'cell phone' bbox overlaps:
      • a rider  (motorcycle phone use), OR
      • a person whose bbox is inside a car/bus/truck bbox (driver phone use).
    """
    violations = []
    phones   = [d for d in detections if d["class"] == PHONE_CLASS]
    riders   = [d for d in detections if d["class"] == "rider"]
    persons  = [d for d in detections if d["class"] == "person"]
    vehicles = [d for d in detections if d["class"] in {"car", "bus", "truck"}]

    flagged_phones = set()

    for pi, phone in enumerate(phones):
        # Case 1: phone overlaps a motorcycle rider
        for r in riders:
            if _iou_fraction(phone["bbox"], r["bbox"]) >= PHONE_PERSON_IOU_THRESH:
                violations.append({
                    "type":          "Phone Use While Riding",
                    "severity":      "Critical",
                    "bbox":          r["bbox"],
                    "vehicle_class": "motorcycle",
                    "confidence":    0.82,
                    "license_plate": "N/A",
                })
                flagged_phones.add(pi)
                break

        if pi in flagged_phones:
            continue

        # Case 2: phone overlaps a person who is inside a car/bus/truck
        for person in persons:
            if _iou_fraction(phone["bbox"], person["bbox"]) < PHONE_PERSON_IOU_THRESH:
                continue
            for veh in vehicles:
                if _iou_fraction(person["bbox"], veh["bbox"]) >= PHONE_VEHICLE_IOU_THRESH:
                    violations.append({
                        "type":          "Phone Use While Driving",
                        "severity":      "Critical",
                        "bbox":          veh["bbox"],
                        "vehicle_class": veh["class"],
                        "confidence":    0.80,
                        "license_plate": "N/A",
                    })
                    flagged_phones.add(pi)
                    break
            if pi in flagged_phones:
                break

    return violations


def evaluate_all(detections, image_rgb, stop_line_y, parking_zone):
    """Run all violation checkers and return deduplicated list."""
    violations = []
    violations += check_helmet(detections, image_rgb)
    violations += check_triple_riding(detections)
    violations += check_stop_line(detections, stop_line_y, image_rgb)
    violations += check_red_light(detections, stop_line_y, image_rgb)
    violations += check_wrong_side(detections, image_rgb)
    violations += check_illegal_parking(detections, parking_zone)
    violations += check_seatbelt(detections, image_rgb)
    violations += check_phone_use(detections)

    # Deduplicate by type + bbox proximity
    seen = set()
    unique = []
    for v in violations:
        key = (v["type"], v["bbox"][0] // 20, v["bbox"][1] // 20)
        if key not in seen:
            seen.add(key)
            unique.append(v)
    return unique
