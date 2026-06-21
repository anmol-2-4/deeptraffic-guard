import cv2
import numpy as np
from config import CLAHE_CLIP_LIMIT, CLAHE_TILE_GRID, BLUR_LAPLACIAN_THRESH, SHADOW_BLUR_KERNEL


def enhance(image_rgb: np.ndarray) -> tuple[np.ndarray, dict]:
    """
    Returns (processed_rgb, diagnostics).
    Input and output are RGB uint8 numpy arrays.
    Three stages applied only when needed.
    """
    img = image_rgb.copy()
    diag = {"was_blurry": False, "was_dark": False, "shadow_corrected": False}

    # Stage 1: Blur detection + adaptive sharpening
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    if lap_var < BLUR_LAPLACIAN_THRESH:
        diag["was_blurry"] = True
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
        img = cv2.filter2D(img, -1, kernel)

    # Stage 2: Low-light CLAHE on L channel of LAB
    lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
    l_channel = lab[:, :, 0]
    if float(l_channel.mean()) < 80:
        diag["was_dark"] = True
        clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=CLAHE_TILE_GRID)
        lab[:, :, 0] = clahe.apply(l_channel)
        img = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)

    # Stage 3: Shadow normalization via illumination division, applied to the V
    # (brightness) channel only. Blending a grayscale map into RGB (the previous
    # approach) desaturates every color by ~40% whenever this stage fires, which
    # corrupts all downstream color-based checks (helmet shell color, red-light
    # detection, sign/parking-zone color masks). Operating on V in HSV corrects
    # uneven brightness while leaving hue/saturation untouched.
    hsv2 = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    v_chan = hsv2[:, :, 2].astype(np.float32)
    k = SHADOW_BLUR_KERNEL
    illum = cv2.GaussianBlur(v_chan, (k, k), 0)
    ratio = v_chan / (illum + 1.0)
    # Check if shadow is significant (std of ratio > 0.05 means uneven illumination)
    if ratio.std() > 0.05:
        diag["shadow_corrected"] = True
        norm_v = cv2.normalize(ratio, None, 0, 255, cv2.NORM_MINMAX)
        blended_v = cv2.addWeighted(v_chan, 0.6, norm_v, 0.4, 0)
        hsv2[:, :, 2] = np.clip(blended_v, 0, 255).astype(np.uint8)
        img = cv2.cvtColor(hsv2, cv2.COLOR_HSV2RGB)

    return img, diag
