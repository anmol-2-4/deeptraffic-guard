"""
Detects stop lines and no-parking zones from the image itself.
If nothing is found, returns None — no assumptions, no fake defaults.
"""
import math
import cv2
import numpy as np


# ─── Stop Line ───────────────────────────────────────────────────────────────

def _white_mask(gray):
    """Isolate bright road-marking white. Uses adaptive threshold to handle glare."""
    # Hard threshold for very bright white
    _, t1 = cv2.threshold(gray, 210, 255, cv2.THRESH_BINARY)
    # Adaptive for slightly dimmer white in shadows
    t2 = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                cv2.THRESH_BINARY, 31, -20)
    return cv2.bitwise_and(t1, t2)


def detect_stop_line(image_rgb):
    """
    Returns (stop_line_y_px, was_detected) or (None, False).

    Method: row-based white-pixel density scan.
    A painted stop line produces a dense band of white pixels spanning most
    of the road width. We look for horizontal rows where ≥28% of pixels are
    white, then cluster them into thick bands (real lines are 5-30px thick).

    Confirmed by a secondary HoughLinesP check to reject noise.
    Returns None if no credible stop line is found.
    """
    h, w = image_rgb.shape[:2]

    # Only search lower 65% of frame — stop lines are on the road, not sky
    roi_start = int(h * 0.35)
    roi = image_rgb[roi_start:, :]
    roi_h = roi.shape[0]

    gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    white = _white_mask(blur)

    # ── Method 1: row density scan ──────────────────────────────────────────
    row_density = np.sum(white > 0, axis=1) / w  # fraction of white per row

    DENSITY_THRESH = 0.28   # ≥28% of row must be white
    MIN_BAND_ROWS  = 2      # line must be at least 2 px thick

    candidate_rows = np.where(row_density >= DENSITY_THRESH)[0]
    if len(candidate_rows) < MIN_BAND_ROWS:
        return None, False

    # Cluster consecutive rows
    clusters = []
    run = [candidate_rows[0]]
    for r in candidate_rows[1:]:
        if r - run[-1] <= 4:
            run.append(r)
        else:
            clusters.append(run)
            run = [r]
    clusters.append(run)

    valid = [c for c in clusters if len(c) >= MIN_BAND_ROWS]
    if not valid:
        return None, False

    # Pick highest-density cluster (most white per row on average)
    best = max(valid, key=lambda c: np.mean(row_density[c]))
    center_y_roi = int(np.mean(best))
    center_y = center_y_roi + roi_start

    # ── Method 2: Hough confirmation ────────────────────────────────────────
    # Verify with HoughLinesP — must find at least one near-horizontal line
    # within ±30px of the density peak
    edges = cv2.Canny(white, 50, 150)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180,
        threshold=max(30, int(w * 0.12)),
        minLineLength=int(w * 0.18),
        maxLineGap=30,
    )

    confirmed = False
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = abs(math.degrees(math.atan2(y2 - y1, (x2 - x1) + 1e-6)))
            mid_y  = (y1 + y2) / 2
            if (angle <= 15 or angle >= 165) and abs(mid_y - center_y_roi) <= 30:
                confirmed = True
                break

    # Accept density peak even without Hough if the band is wide (≥5 rows)
    if not confirmed and len(best) < 5:
        return None, False

    return center_y, True


# ─── Parking Zone ─────────────────────────────────────────────────────────────

def detect_parking_zone(image_rgb):
    """
    Returns ([x1, y1, x2, y2], was_detected) or (None, False).

    Detects yellow or red CURB paint — horizontal strips at the very bottom
    of the frame hugging the road edge near the camera.

    Key constraints to avoid false positives from car bodies / road markings:
    - Only searches the bottom 18% of the frame (curbs are closest to camera)
    - Requires elongated horizontal strips (width/height > 4)
    - Requires the strip to span >20% of frame width (short dabs are noise)
    """
    h, w = image_rgb.shape[:2]
    hsv = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2HSV)

    # Yellow curb — tighter saturation floor (80) to skip pale car bodies
    yellow = cv2.inRange(hsv, np.array([15, 80, 80]), np.array([40, 255, 255]))
    # Red curb (two HSV ranges)
    red1 = cv2.inRange(hsv, np.array([0,  110, 80]),  np.array([10, 255, 255]))
    red2 = cv2.inRange(hsv, np.array([158, 110, 80]), np.array([180, 255, 255]))
    combined = cv2.bitwise_or(yellow, cv2.bitwise_or(red1, red2))

    # Only search the bottom 18% of frame — real curbs are near the camera lens
    curb_roi_start = int(h * 0.82)
    mask = np.zeros_like(combined)
    mask[curb_roi_start:, :] = 255
    combined = cv2.bitwise_and(combined, mask)

    # Morphology to connect broken horizontal strips
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3))
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    valid = []
    for c in contours:
        if cv2.contourArea(c) < 200:
            continue
        bx, by, bw, bh = cv2.boundingRect(c)
        aspect = bw / max(bh, 1)
        # Must be a wide horizontal strip AND span at least 20% of frame width
        if aspect > 4.0 and bw > w * 0.20:
            valid.append(c)

    if not valid:
        return None, False

    all_pts = np.vstack(valid)
    bx, by, bw, bh = cv2.boundingRect(all_pts)
    # Extend the zone upward to cover the full restricted area on the road edge
    zone = [bx, max(0, curb_roi_start - int(h * 0.15)),
            min(w, bx + bw), min(h, by + bh)]
    return zone, True


# ─── Road Signs ───────────────────────────────────────────────────────────────

def detect_road_signs(image_rgb):
    """
    Detect road sign regions by color and shape.
    Returns list of {bbox, color, text_hint}.
    """
    h, w = image_rgb.shape[:2]
    hsv = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2HSV)
    signs = []

    # Signs are only in the upper 55% of the frame — not in the road/vehicle area
    sign_roi_end = int(h * 0.55)

    candidates = [
        (cv2.bitwise_or(
            cv2.inRange(hsv, np.array([0, 140, 80]),  np.array([10, 255, 255])),
            cv2.inRange(hsv, np.array([158, 140, 80]), np.array([180, 255, 255]))
         ), "red", "STOP/NO ENTRY"),
        (cv2.inRange(hsv, np.array([100, 110, 80]), np.array([130, 255, 255])),
         "blue", "INFO SIGN"),
    ]

    for mask, color, hint in candidates:
        # Only look in the upper portion where road signs physically exist
        roi_mask = np.zeros_like(mask)
        roi_mask[:sign_roi_end, :] = 255
        mask = cv2.bitwise_and(mask, roi_mask)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (4, 4))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            area = cv2.contourArea(c)
            # Signs: not too small (noise) and not too large (building facades)
            if area < 600 or area > w * h * 0.025:
                continue
            bx, by, bw, bh = cv2.boundingRect(c)
            aspect = bw / max(bh, 1)
            # Compact shape: signs are roughly square to moderately wide
            if 0.40 <= aspect <= 2.2:
                signs.append({"bbox": [bx, by, bx + bw, by + bh],
                               "color": color, "text_hint": hint})
    return signs


# ─── Master ──────────────────────────────────────────────────────────────────

def auto_detect_zones(image_rgb):
    """
    Returns:
      stop_line_y   — int pixel y-coordinate, or None if not found
      parking_zone  — [x1,y1,x2,y2], or None if not found
      signs         — list[dict]
      meta          — detection flags
    """
    stop_y,    stop_found  = detect_stop_line(image_rgb)
    park_zone, park_found  = detect_parking_zone(image_rgb)
    signs                  = detect_road_signs(image_rgb)

    return stop_y, park_zone, signs, {
        "stop_line_detected":    stop_found,
        "parking_zone_detected": park_found,
        "signs_detected":        len(signs),
    }
