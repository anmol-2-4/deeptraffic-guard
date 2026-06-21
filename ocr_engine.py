import os
import re
import cv2
import numpy as np
import streamlit as st

PLATE_REGEX = re.compile(r"[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{4}")


@st.cache_resource
def _load_reader():
    import easyocr
    return easyocr.Reader(["en"], gpu=False)


def _preprocess_plate(crop_rgb):
    gray = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    if gray.shape[1] < 200:
        scale = 200 / gray.shape[1]
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    return binary


def extract_plate(image_rgb: np.ndarray, vehicle_bbox: list) -> dict:
    """
    Returns {"plate": str, "confidence": float}.
    Crops the lower portion of the vehicle bbox, preprocesses, runs EasyOCR.
    """
    try:
        reader = _load_reader()
    except Exception:
        return {"plate": "OCR_UNAVAILABLE", "confidence": 0.0}

    x1, y1, x2, y2 = vehicle_bbox
    # Pad 10% on each side
    w, h = x2 - x1, y2 - y1
    px1 = max(0, x1 - int(w * 0.1))
    px2 = min(image_rgb.shape[1], x2 + int(w * 0.1))

    # Plate is in the lower 25% of the vehicle
    plate_y1 = y2 - int(h * 0.28)
    plate_y2 = y2
    plate_x1 = px1 + int(w * 0.10)
    plate_x2 = px2 - int(w * 0.10)

    crop = image_rgb[plate_y1:plate_y2, plate_x1:plate_x2]
    if crop.size == 0 or crop.shape[0] < 5:
        return {"plate": "UNREADABLE", "confidence": 0.0}

    processed = _preprocess_plate(crop)

    results = reader.readtext(
        processed,
        allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        detail=1,
    )

    if not results:
        return {"plate": "UNREADABLE", "confidence": 0.0}

    text = "".join([r[1] for r in results if r[2] > 0.30]).upper().replace(" ", "")
    conf = float(np.mean([r[2] for r in results if r[2] > 0.30]) or 0.0)

    match = PLATE_REGEX.search(text)
    if match:
        return {"plate": match.group(), "confidence": min(conf, 0.99)}
    return {"plate": text if text else "UNREADABLE", "confidence": conf * 0.7}
