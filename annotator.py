import os
import cv2
import time
import numpy as np
from config import EVIDENCE_DIR

SEVERITY_COLORS = {
    "Critical": (220, 38,  38),
    "High":     (234, 88,  12),
    "Medium":   (234, 179, 8),
    "Low":      (37,  99,  235),
}
SEVERITY_BADGE = {"Critical": "CRIT", "High": "HIGH", "Medium": "MED", "Low": "LOW"}


def _overlay_rect(img, x1, y1, x2, y2, color, alpha=0.3):
    ov = img.copy()
    cv2.rectangle(ov, (x1, y1), (x2, y2), color, -1)
    cv2.addWeighted(ov, alpha, img, 1 - alpha, 0, img)


def _label(img, text, x, y, fg=(255, 255, 255), bg=(0, 0, 0), scale=0.52, thickness=1):
    font = cv2.FONT_HERSHEY_DUPLEX
    (tw, th), bl = cv2.getTextSize(text, font, scale, thickness)
    h_img = img.shape[0]
    y = max(th + 6, min(h_img - bl - 2, y))
    cv2.rectangle(img, (x - 2, y - th - 4), (x + tw + 4, y + bl + 1), bg, -1)
    cv2.putText(img, text, (x, y), font, scale, fg, thickness, cv2.LINE_AA)


def render(image_rgb, violations, detections,
           stop_line_y,   # int or None
           parking_zone,  # [x1,y1,x2,y2] or None
           camera_node="CAM-NODE-01",
           signs=None) -> tuple[np.ndarray, list]:
    """
    Returns (annotated_rgb, evidence_paths).
    stop_line_y and parking_zone are only drawn if not None (i.e., actually detected).
    """
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    img = image_rgb.copy()
    h, w = img.shape[:2]

    # ── Parking zone — only if detected ──────────────────────────────────────
    if parking_zone is not None:
        pzx1, pzy1, pzx2, pzy2 = parking_zone
        _overlay_rect(img, pzx1, pzy1, pzx2, pzy2, (255, 100, 0), alpha=0.18)
        cv2.rectangle(img, (pzx1, pzy1), (pzx2, pzy2), (255, 120, 0), 2)
        _label(img, "NO PARKING ZONE", pzx1 + 5, pzy1 + 22,
               (255, 255, 255), (200, 80, 0))

    # ── Road signs ────────────────────────────────────────────────────────────
    if signs:
        for s in signs:
            sx1, sy1, sx2, sy2 = s["bbox"]
            sc = (255, 70, 70) if s["color"] == "red" else (70, 130, 255)
            cv2.rectangle(img, (sx1, sy1), (sx2, sy2), sc, 2)
            _label(img, s["text_hint"], sx1, max(16, sy1 - 4),
                   (255, 255, 255), sc, scale=0.40)

    # ── Stop line — only if detected ──────────────────────────────────────────
    if stop_line_y is not None:
        cv2.line(img, (0, stop_line_y), (w, stop_line_y), (0, 240, 160), 3)
        _label(img, "STOP LINE", 10, stop_line_y - 8, (0, 0, 0), (0, 210, 140))

    # ── Normal detections (green, thin) ──────────────────────────────────────
    violation_bboxes = {tuple(v["bbox"]) for v in violations}
    for d in detections:
        if tuple(d["bbox"]) in violation_bboxes:
            continue
        x1, y1, x2, y2 = d["bbox"]
        cv2.rectangle(img, (x1, y1), (x2, y2), (80, 200, 120), 1)
        _label(img, d["class"], x1, max(14, y1 - 3),
               (180, 255, 200), (20, 60, 30), scale=0.38)

    # ── Violations ────────────────────────────────────────────────────────────
    evidence_paths = []
    ts = time.strftime("%Y%m%d_%H%M%S")
    used_label_rects = []  # track drawn label areas to avoid overlap

    def _find_label_y(x1, x2, preferred_y, label_h=18):
        """Nudge label down if it would overlap an already-drawn label."""
        y = preferred_y
        for _ in range(8):  # up to 8 nudges
            overlap = any(
                rx1 < x2 and rx2 > x1 and ry1 < y + label_h and ry2 > y - label_h
                for rx1, ry1, rx2, ry2 in used_label_rects
            )
            if not overlap:
                break
            y += label_h + 2
        used_label_rects.append((x1, y - label_h, x2, y + 4))
        return min(h - 4, y)

    for i, v in enumerate(violations):
        x1, y1, x2, y2 = v["bbox"]
        sev   = v.get("severity", "Medium")
        color = SEVERITY_COLORS.get(sev, (180, 180, 180))
        badge = SEVERITY_BADGE.get(sev, sev)
        conf  = int(v.get("confidence", 0) * 100)
        plate = v.get("license_plate", "")
        font  = cv2.FONT_HERSHEY_DUPLEX

        # Box
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 3)

        # Label above box — place at y1-18, nudge if crowded
        preferred_y = max(20, y1 - 18)
        label_y = _find_label_y(x1, x2, preferred_y)

        # Measure texts
        vtype_short = v['type'][:22]  # truncate long names
        (tw, th), _ = cv2.getTextSize(vtype_short, font, 0.52, 1)
        (bw_px, _), _ = cv2.getTextSize(badge, font, 0.44, 1)

        # Draw type pill (full width of box if possible)
        label_bg_x2 = min(w - 1, x1 + tw + bw_px + 24)
        cv2.rectangle(img, (x1, label_y - th - 4), (label_bg_x2, label_y + 3), color, -1)
        cv2.putText(img, vtype_short, (x1 + 4, label_y), font, 0.52,
                    (255, 255, 255), 1, cv2.LINE_AA)
        # Badge right-aligned inside the pill
        badge_x = max(x1 + tw + 10, label_bg_x2 - bw_px - 6)
        cv2.putText(img, badge, (badge_x, label_y), font, 0.44,
                    (255, 255, 230), 1, cv2.LINE_AA)

        # Confidence tag below box (small, dark bg)
        info = f"Conf:{conf}%"
        if plate and plate not in ("N/A", "UNREADABLE", "OCR_UNAVAILABLE", ""):
            info += f"  {plate}"
        _label(img, info, x1, min(h - 4, y2 + 14),
               (200, 200, 200), (25, 25, 25), scale=0.40)

        # Evidence crop
        pad = 20
        ev_crop = image_rgb[
            max(0, y1 - pad): min(h, y2 + pad),
            max(0, x1 - pad): min(w, x2 + pad),
        ]
        vt_safe = v["type"].replace(" ", "_").replace("-", "_")
        ep = os.path.join(EVIDENCE_DIR, f"{ts}_{i}_{vt_safe}.png")
        cv2.imwrite(ep, cv2.cvtColor(ev_crop, cv2.COLOR_RGB2BGR))
        evidence_paths.append(ep)

    # ── Top banner ────────────────────────────────────────────────────────────
    _overlay_rect(img, 0, 0, w, 40, (0, 0, 0), alpha=0.70)
    summary = (
        f"  {camera_node}   "
        f"{time.strftime('%Y-%m-%d  %H:%M:%S')}   "
        f"Objects: {len(detections)}   "
        f"Violations: {len(violations)}"
    )
    cv2.putText(img, summary, (8, 27), cv2.FONT_HERSHEY_DUPLEX,
                0.56, (200, 220, 255), 1, cv2.LINE_AA)

    return img, evidence_paths
