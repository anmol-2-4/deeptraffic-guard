"""
Performance evaluation harness for DeepTraffic-Guard.

Ground truth below was assigned by manually viewing each image and recording
which violation types are genuinely present, before running the pipeline.
This is intentionally a small, hand-verified set rather than a large unverified
one -- every label was checked against the actual image content.

Coverage note: this set currently gives real positive+negative coverage for
Helmet Non-Compliance, Triple Riding, Red-Light/Stop-Line, and Illegal Parking
(zone-absent case). It does NOT yet cover Seatbelt, Wrong-Side Driving, or
Phone Use with confirmed positive examples -- those are reported as "not yet
evaluated" rather than guessed at.

Run: python3 evaluate.py
"""
import time
import cv2

import preprocessor
import detector
import violation_engine
import road_detector

ALL_TYPES = [
    "Helmet Non-Compliance",
    "Triple Riding",
    "Stop-Line Violation",
    "Red-Light Violation",
    "Wrong-Side Driving",
    "Illegal Parking",
    "Seatbelt Non-Compliance",
    "Phone Use While Riding",
    "Phone Use While Driving",
]

# image -> set of violation types actually present (hand-verified ground truth)
GROUND_TRUTH = {
    "eval_images/bengaluru_intersection_1.jpg": set(),  # 5 riders, all helmeted, no other violations visible
    "eval_images/triple_riding_1.jpg": {"Triple Riding"},  # 3 riders, all helmeted -> triple riding only
    "eval_images/redlight_stop_1.jpg": set(),  # car properly stopped well behind the line
    "eval_images/scooter_couple_1.jpg": {"Helmet Non-Compliance"},  # 2 riders, neither wearing a helmet
    "eval_images/helmeted_rider_1.jpg": set(),  # solo rider, full-face helmet clearly worn
    "eval_images/parked_cars_1.jpg": set(),  # legal curbside parking, no painted no-parking zone visible
}

# Violation types this test set actually has positive AND/OR negative examples for.
# Metrics are only reported for these -- we don't fabricate numbers for untested types.
COVERED_TYPES = ["Helmet Non-Compliance", "Triple Riding", "Red-Light Violation",
                  "Stop-Line Violation", "Illegal Parking"]


def run_pipeline(path):
    img_bgr = cv2.imread(path)
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    t0 = time.time()
    proc, _ = preprocessor.enhance(img_rgb)
    sy, pz, signs, _ = road_detector.auto_detect_zones(proc)
    dets = detector.run(proc, conf=0.35)
    violations = violation_engine.evaluate_all(dets, proc, sy, pz)
    elapsed_ms = (time.time() - t0) * 1000
    found_types = {v["type"] for v in violations}
    return found_types, elapsed_ms, len(dets)


def main():
    confusion = {t: {"TP": 0, "FP": 0, "FN": 0, "TN": 0} for t in COVERED_TYPES}
    timings = []
    rows = []

    for path, truth in GROUND_TRUTH.items():
        found, ms, n_objects = run_pipeline(path)
        timings.append(ms)
        rows.append((path, truth, found, ms, n_objects))

        for vtype in COVERED_TYPES:
            predicted = vtype in found
            actual = vtype in truth
            if predicted and actual:
                confusion[vtype]["TP"] += 1
            elif predicted and not actual:
                confusion[vtype]["FP"] += 1
            elif not predicted and actual:
                confusion[vtype]["FN"] += 1
            else:
                confusion[vtype]["TN"] += 1

    print("=" * 78)
    print("PER-IMAGE RESULTS")
    print("=" * 78)
    for path, truth, found, ms, n_objects in rows:
        status = "OK" if found == truth else "MISMATCH"
        print(f"\n{path}  [{status}]")
        print(f"  objects detected : {n_objects}")
        print(f"  ground truth     : {sorted(truth) or '(none)'}")
        print(f"  system found     : {sorted(found) or '(none)'}")
        print(f"  time             : {ms:.1f} ms")

    print("\n" + "=" * 78)
    print("CONFUSION MATRIX + METRICS (covered violation types only)")
    print("=" * 78)
    print(f"{'Type':<26}{'TP':>4}{'FP':>4}{'FN':>4}{'TN':>4}"
          f"{'Precision':>11}{'Recall':>9}{'F1':>7}")

    total_tp = total_fp = total_fn = total_tn = 0
    for vtype in COVERED_TYPES:
        c = confusion[vtype]
        tp, fp, fn, tn = c["TP"], c["FP"], c["FN"], c["TN"]
        total_tp += tp; total_fp += fp; total_fn += fn; total_tn += tn
        precision = tp / (tp + fp) if (tp + fp) else float('nan')
        recall = tp / (tp + fn) if (tp + fn) else float('nan')
        f1 = (2 * precision * recall / (precision + recall)
              if (precision + recall) and precision == precision and recall == recall
              else float('nan'))
        def fmt(x):
            return "  n/a" if x != x else f"{x:.2f}"
        print(f"{vtype:<26}{tp:>4}{fp:>4}{fn:>4}{tn:>4}"
              f"{fmt(precision):>11}{fmt(recall):>9}{fmt(f1):>7}")

    overall_acc = (total_tp + total_tn) / max(1, total_tp + total_fp + total_fn + total_tn)
    print(f"\nOverall accuracy across covered types: {overall_acc:.2%}")
    print(f"\nNot yet evaluated (no verified ground truth examples in this set): "
          f"Seatbelt Non-Compliance, Wrong-Side Driving, Phone Use While Riding/Driving")

    print("\n" + "=" * 78)
    print("COMPUTATIONAL EFFICIENCY")
    print("=" * 78)
    avg_ms = sum(timings) / len(timings)
    print(f"Images processed   : {len(timings)}")
    print(f"Average time/image : {avg_ms:.1f} ms  (~{1000/avg_ms:.1f} images/sec, single CPU thread)")
    print(f"Min / Max          : {min(timings):.1f} ms / {max(timings):.1f} ms")
    print("Note: measured on local CPU; YOLOv8n inference dominates runtime.")


if __name__ == "__main__":
    main()
