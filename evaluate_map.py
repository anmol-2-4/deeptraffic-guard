"""
Object-detection mAP@0.5 evaluation for DeepTraffic-Guard's detector module.

This is separate from evaluate.py (which scores violation-level classification).
This script scores the underlying detection quality itself: did the detector find
the right objects, in the right place, with the right class label.

Ground truth bounding boxes below were hand-drawn by visually inspecting every
candidate detection box AND manually scanning each image for missed objects --
not copied from the model's own output. Where the model produced a duplicate or
badly-merged box covering two real objects, that is recorded as a methodology
note rather than silently treated as correct. Evaluated at the SAME class
granularity our system actually outputs (e.g. 'rider', not raw COCO 'person'),
since that reflects what the pipeline produces, not just the base YOLO model.

Run: python3 evaluate_map.py
"""
import cv2
import numpy as np
import detector
import preprocessor

# Each entry: image path -> list of (class, [x1,y1,x2,y2])
GROUND_TRUTH = {
    "eval_images/bengaluru_intersection_1.jpg": [
        ("rider", [1, 442, 250, 995]), ("rider", [295, 372, 569, 1060]),
        ("rider", [941, 452, 1136, 766]), ("rider", [590, 446, 758, 762]),
        ("rider", [1219, 437, 1299, 612]),
        ("motorcycle", [198, 618, 577, 1085]), ("motorcycle", [941, 544, 1143, 831]),
        ("motorcycle", [595, 562, 748, 826]), ("motorcycle", [0, 647, 226, 1085]),
        ("motorcycle", [1224, 498, 1294, 620]),
        ("truck", [0, 277, 250, 641]),
        ("car", [532, 426, 829, 697]),
        ("truck", [1300, 420, 1448, 550]),  # background van, missed by detector (FN)
    ],
    "eval_images/triple_riding_1.jpg": [
        ("rider", [1550, 1217, 2956, 3609]),   # front rider, tan jacket -- matched by box 1
        ("rider", [2689, 1016, 4260, 3623]),   # back rider, maroon helmet -- matched by box 0
        # NOTE: a third rider (middle, face mask) is visibly present but heavily occluded between
        # the other two -- no confident tight box can be hand-drawn for them, so they are excluded
        # from quantitative ground truth rather than scored against a guessed box. Documented as a
        # qualitative miss instead (see methodology notes below).
        ("motorcycle", [638, 1595, 1407, 2229]),    # red parked scooter -- matched by box 10
        ("motorcycle", [1264, 1729, 4400, 3640]),   # the 3-rider motorcycle -- matched by box 11/12 (duplicate)
    ],
    "eval_images/scooter_couple_1.jpg": [
        ("rider", [3119, 2607, 3908, 3482]),   # front person on scooter -- matched
        # NOTE: a second person is visible riding behind the front one but is heavily occluded/
        # overlapping -- same as the triple_riding case, excluded from quantitative ground truth
        # rather than scored against a guessed box (see methodology notes below).
        ("motorcycle", [3216, 2944, 3665, 3652]),
    ],
    "eval_images/redlight_stop_1.jpg": [
        ("car", [1036, 2723, 1675, 3021]),
    ],
    "eval_images/parked_cars_1.jpg": [
        ("person", [1708, 2360, 1836, 2731]), ("person", [1832, 2314, 1982, 2734]),
        ("car", [29, 2567, 1132, 3601]), ("car", [830, 2307, 1284, 2815]),
        ("car", [679, 2424, 1241, 2995]),
        ("car", [1480, 2300, 1850, 2700]),  # dark SUV near the gate, missed by detector (FN)
    ],
    "eval_images/helmeted_rider_1.jpg": [
        ("rider", [1163, 1369, 2702, 4273]),
        ("motorcycle", [518, 2950, 2727, 4757]),
    ],
    "eval_images/bareheaded_rider_1.jpg": [
        ("rider", [229, 38, 421, 319]), ("rider", [29, 91, 124, 255]),
        ("motorcycle", [139, 148, 492, 369]), ("motorcycle", [32, 176, 103, 308]),
        ("car", [445, 46, 647, 319]), ("car", [570, 0, 786, 432]),
    ],
}

def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area_a = max(1, (a[2] - a[0]) * (a[3] - a[1]))
    area_b = max(1, (b[2] - b[0]) * (b[3] - b[1]))
    return inter / (area_a + area_b - inter)


def compute_ap(matches, n_gt):
    """matches: list of (confidence, is_tp) sorted by confidence descending."""
    if n_gt == 0:
        return None
    tp_cum, fp_cum = 0, 0
    precisions, recalls = [], []
    for _, is_tp in matches:
        if is_tp:
            tp_cum += 1
        else:
            fp_cum += 1
        precisions.append(tp_cum / (tp_cum + fp_cum))
        recalls.append(tp_cum / n_gt)
    # Precision envelope (monotonically decreasing from the right), VOC2012-style AP
    precisions = np.array([0.0] + precisions + [0.0])
    recalls = np.array([0.0] + recalls + [recalls[-1] if recalls else 0.0])
    for i in range(len(precisions) - 2, -1, -1):
        precisions[i] = max(precisions[i], precisions[i + 1])
    ap = 0.0
    for i in range(1, len(recalls)):
        ap += (recalls[i] - recalls[i - 1]) * precisions[i]
    return ap


def main():
    IOU_THRESH = 0.5
    per_class = {}  # class -> list of (confidence, is_tp), plus n_gt counter

    for path, gt_list in GROUND_TRUTH.items():
        img_bgr = cv2.imread(path)
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        proc, _ = preprocessor.enhance(img_rgb)
        preds = detector.run(proc, conf=0.35)

        gt_by_class = {}
        for cls, box in gt_list:
            gt_by_class.setdefault(cls, []).append({"box": box, "matched": False})

        preds_sorted = sorted(preds, key=lambda p: p["conf"], reverse=True)
        for p in preds_sorted:
            cls, box, conf = p["class"], p["bbox"], p["conf"]
            per_class.setdefault(cls, {"matches": [], "n_gt": 0})
            candidates = gt_by_class.get(cls, [])
            best_iou, best_gt = 0.0, None
            for g in candidates:
                if g["matched"]:
                    continue
                cur_iou = iou(box, g["box"])
                if cur_iou > best_iou:
                    best_iou, best_gt = cur_iou, g
            if best_iou >= IOU_THRESH and best_gt is not None:
                best_gt["matched"] = True
                per_class[cls]["matches"].append((conf, True))
            else:
                per_class[cls]["matches"].append((conf, False))

        for cls, glist in gt_by_class.items():
            per_class.setdefault(cls, {"matches": [], "n_gt": 0})
            per_class[cls]["n_gt"] += len(glist)

    print("=" * 70)
    print(f"OBJECT DETECTION mAP@{IOU_THRESH} (our system's output classes)")
    print("=" * 70)
    print(f"{'Class':<14}{'GT':>5}{'TP':>5}{'FP':>5}{'FN':>5}{'AP':>8}")

    aps = []
    for cls in sorted(per_class):
        data = per_class[cls]
        matches = sorted(data["matches"], key=lambda m: -m[0])
        n_gt = data["n_gt"]
        tp = sum(1 for _, is_tp in matches if is_tp)
        fp = sum(1 for _, is_tp in matches if not is_tp)
        fn = n_gt - tp
        ap = compute_ap(matches, n_gt)
        aps.append(ap if ap is not None else 0.0)
        ap_str = f"{ap:.3f}" if ap is not None else "n/a"
        print(f"{cls:<14}{n_gt:>5}{tp:>5}{fp:>5}{fn:>5}{ap_str:>8}")

    mAP = sum(aps) / len(aps) if aps else 0.0
    print(f"\nmAP@{IOU_THRESH} across {len(per_class)} classes: {mAP:.3f}")
    print(f"\nMethodology notes:")
    print(f"- Ground truth hand-drawn from visual inspection of {len(GROUND_TRUTH)} real photos,")
    print(f"  evaluated at our system's output class granularity (rider/person/motorcycle/car/truck).")
    print(f"- Known false detections (mannequins, duplicate/merged boxes) are NOT excluded --")
    print(f"  they go through the same matching as every other prediction and count as FP")
    print(f"  whenever they fail to land on a real ground-truth box, same as a real system would see.")
    print(f"- This is mAP@0.5 (single IoU threshold, PASCAL VOC-style), not the stricter COCO")
    print(f"  mAP@[0.5:0.95] -- the sample size here is too small to make that finer breakdown meaningful.")
    print(f"- 2 additional misses are NOT in the table above: a heavily-occluded second person on a")
    print(f"  scooter, and a heavily-occluded third rider in the triple-riding photo. Both are real,")
    print(f"  visible people the detector missed, but neither has a tight box that could be hand-drawn")
    print(f"  with confidence, so they're disclosed here rather than scored against a guessed box.")


if __name__ == "__main__":
    main()
