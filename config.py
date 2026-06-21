MODEL_PATH = "yolov8n.pt"

CLAHE_CLIP_LIMIT      = 2.0
CLAHE_TILE_GRID       = (8, 8)
BLUR_LAPLACIAN_THRESH = 80.0
SHADOW_BLUR_KERNEL    = 51

CONFIDENCE_THRESHOLD = 0.35

HEAD_CROP_RATIO      = 0.32           # top 32% = head region only, avoids neck/chin
SKIN_HSV_LOWER       = [0,  25,  50]  # skin tones: reasonably tight to avoid chin/neck noise
SKIN_HSV_UPPER       = [22, 175, 255]
SKIN_HSV_LOWER2      = [0,  15,  45]
SKIN_HSV_UPPER2      = [15, 200, 200]
SKIN_RATIO_THRESHOLD = 0.14           # >14% face skin clearly exposed = no helmet
DARK_HAIR_V_MAX      = 80             # V < 80 = dark (hair or helmet)
DARK_HAIR_RATIO_THRESH = 0.30         # >30% dark pixels required (avoid partial shadows)
HELMET_TEXTURE_THRESH  = 280.0        # high variance = genuine hair texture (not helmet pattern)
MIN_PERSON_HEIGHT_PX   = 20

RIDER_IOU_THRESH     = 0.15   # intersection/person_area; walkers near bikes score ~0, actual riders score 0.15+

TORSO_CROP_Y_START       = 0.20
TORSO_CROP_Y_END         = 0.55
TORSO_CROP_X_INSET       = 0.15
DIAGONAL_EDGE_MIN_ANGLE  = 20
DIAGONAL_EDGE_MAX_ANGLE  = 70
DIAGONAL_DENSITY_THRESH  = 0.04

TRAFFIC_LIGHT_CROP_TOP_FRAC = 0.35
RED_HSV1_LOWER = [0,   100, 100]
RED_HSV1_UPPER = [10,  255, 255]
RED_HSV2_LOWER = [160, 100, 100]
RED_HSV2_UPPER = [180, 255, 255]
RED_PIXEL_RATIO_THRESH = 0.15

STOP_LINE_Y_RATIO    = 0.85
PARKING_ZONE_X_RATIO = 0.65
PARKING_ZONE_Y_RATIO = 0.40
MAX_RIDERS_PER_BIKE  = 2

WRONG_SIDE_HOUGH_THRESH    = 50
WRONG_SIDE_MIN_LINE_FRAC   = 0.10
WRONG_SIDE_CENTROID_THRESH = 0.45

DB_PATH      = "violations.db"
EVIDENCE_DIR = "evidence"

VEHICLE_CLASSES     = {"car", "motorcycle", "bus", "truck", "bicycle"}
PERSON_CLASS        = "person"
TRAFFIC_LIGHT_CLASS = "traffic light"
