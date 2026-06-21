import numpy as np
import streamlit as st
from ultralytics import YOLO
from config import MODEL_PATH, CONFIDENCE_THRESHOLD, VEHICLE_CLASSES, PERSON_CLASS, RIDER_IOU_THRESH


@st.cache_resource
def _load_model():
    return YOLO(MODEL_PATH)


def _iou_person(person_box, vehicle_box):
    """Intersection area / person area (IoPerson)."""
    px1, py1, px2, py2 = person_box
    vx1, vy1, vx2, vy2 = vehicle_box
    ix1, iy1 = max(px1, vx1), max(py1, vy1)
    ix2, iy2 = min(px2, vx2), min(py2, vy2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    person_area = max(1, (px2 - px1) * (py2 - py1))
    return inter / person_area


def _iou(a, b):
    """Standard IoU between two [x1,y1,x2,y2] boxes."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area_a = (a[2]-a[0]) * (a[3]-a[1])
    area_b = (b[2]-b[0]) * (b[3]-b[1])
    union  = area_a + area_b - inter
    return inter / max(union, 1)


def _nms(detections, iou_thresh=0.70):
    """Remove duplicate detections — keep highest-confidence box for overlapping pairs."""
    detections = sorted(detections, key=lambda d: d["conf"], reverse=True)
    kept = []
    for d in detections:
        if all(_iou(d["bbox"], k["bbox"]) < iou_thresh for k in kept):
            kept.append(d)
    return kept


def run(image_rgb: np.ndarray, conf: float = CONFIDENCE_THRESHOLD) -> list[dict]:
    """
    Returns list of detection dicts: {bbox, class, conf, attrs}
    Persons whose bbox physically intersects a motorcycle bbox by IoPerson >= RIDER_IOU_THRESH
    are relabeled 'rider'. Walking pedestrians near (but not overlapping) a bike score ~0
    IoPerson and are never promoted.
    """
    model = _load_model()
    results = model(image_rgb, conf=conf, verbose=False)[0]

    detections = []
    boxes   = results.boxes.xyxy.cpu().numpy()
    confs   = results.boxes.conf.cpu().numpy()
    classes = results.boxes.cls.cpu().numpy()

    for box, c, cls in zip(boxes, confs, classes):
        label = model.names[int(cls)]
        if label in VEHICLE_CLASSES or label == PERSON_CLASS or label == "traffic light":
            detections.append({
                "bbox":  [int(x) for x in box],
                "class": label,
                "conf":  float(c),
                "attrs": {}
            })

    # Remove overlapping duplicates (same vehicle detected as two classes)
    detections = _nms(detections)

    # Assign riders: only when the person's bbox physically overlaps the motorcycle bbox
    # by at least RIDER_IOU_THRESH fraction of person area.  Walking pedestrians have
    # near-zero overlap with a bike bbox and will never be promoted.
    motorcycles = [d for d in detections if d["class"] == "motorcycle"]
    for d in detections:
        if d["class"] != PERSON_CLASS:
            continue
        px1, py1, px2, py2 = d["bbox"]
        pcx = (px1 + px2) / 2
        for m in motorcycles:
            bx1, by1, bx2, by2 = m["bbox"]
            iop = _iou_person(d["bbox"], m["bbox"])

            # Primary: direct bbox overlap (covers rider legs/torso overlapping bike)
            if iop >= RIDER_IOU_THRESH:
                d["class"] = "rider"
                d["attrs"]["motorcycle_bbox"] = m["bbox"]
                break

            # Secondary: very tight spatial check for riders sitting directly above a bike
            # (person centroid strictly inside bike X bounds, body at bike height, small gap only)
            if (bx1 <= pcx <= bx2                     # centroid within bike width, no padding
                    and py2 >= by1 - 15                # person bottom just above bike top
                    and py1 < by2                      # person top above bike bottom
                    and iop >= 0.05):                  # some minimal physical intersection
                d["class"] = "rider"
                d["attrs"]["motorcycle_bbox"] = m["bbox"]
                break

    return detections
