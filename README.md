# DeepTraffic-Guard

AI-powered traffic violation detection from camera footage — runs entirely on computer vision and heuristic analysis, no manual zone configuration required.

**Live demo:** [deeptraffic-guard.streamlit.app](https://deeptraffic-guard.streamlit.app)

![Python](https://img.shields.io/badge/python-3.11-blue)
![Streamlit](https://img.shields.io/badge/streamlit-1.30+-FF4B4B)
![YOLOv8](https://img.shields.io/badge/YOLOv8-ultralytics-00FFFF)

## What it does

Upload a traffic camera image or video, and the system automatically:

1. Enhances the image (deblur, low-light correction, shadow normalization)
2. Detects vehicles, pedestrians, riders, and traffic lights with YOLOv8
3. Auto-detects stop lines, no-parking zones, and road signs directly from road markings — no manual calibration
4. Flags violations with bounding boxes, confidence scores, and evidence crops
5. Reads license plates with OCR
6. Logs everything to a searchable analytics dashboard
7. Exports a PDF evidence report

## Violation types detected

| Violation | Method |
|---|---|
| Helmet non-compliance | Skin/hair/texture HSV analysis on rider head crop, with colored-helmet-shell rejection |
| Triple riding | Rider count per motorcycle bounding box |
| Stop-line violation | Vehicle position vs. auto-detected stop line |
| Red-light violation | Traffic light color + stop-line crossing |
| Wrong-side driving | Lane-center estimation via Hough line detection |
| Illegal parking | Vehicle overlap with auto-detected curb-paint zones |
| Seatbelt non-compliance | Diagonal-strap edge density in torso region |
| Phone use while driving/riding | Cell-phone bbox overlap with driver/rider |

## Features

- **Image analysis** — single-frame upload with full violation pipeline and annotated evidence image
- **Video analysis** — frame-sampled video scanning with annotated output video and violation timeline
- **PDF evidence reports** — auto-generated report with annotated frame, violation table, and per-violation evidence pages
- **Analytics dashboard** — violation trends by type/severity/hour, searchable record history, CSV export
- **Zero manual configuration** — stop lines, parking zones, and road signs are detected from the image itself, not assumed or hardcoded

## Tech stack

- **Detection:** YOLOv8n (Ultralytics)
- **Computer vision:** OpenCV (CLAHE, Canny, HoughLinesP, HSV masking, morphological ops)
- **OCR:** EasyOCR for license plates
- **UI:** Streamlit with custom dark-theme CSS
- **Storage:** SQLite with frame-hash deduplication
- **Reports:** fpdf2

## Running locally

```bash
git clone https://github.com/anmol-2-4/deeptraffic-guard.git
cd deeptraffic-guard
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The YOLOv8 model weights download automatically on first run.

## Project structure

```
app.py                 Streamlit UI — image tab, video tab, dashboard tab
detector.py             YOLOv8 inference + rider/vehicle association
violation_engine.py     All 8 violation checks
road_detector.py        Auto-detection of stop lines, parking zones, signs
preprocessor.py         Image enhancement (blur/low-light/shadow correction)
annotator.py            Evidence image rendering with bounding boxes & labels
ocr_engine.py           License plate OCR
report_generator.py     PDF evidence report generation
database.py             SQLite storage and analytics queries
config.py               All tunable thresholds in one place
```

## Performance evaluation

Run `python3 evaluate.py` to reproduce these results. Ground truth was assigned by manually
viewing each image before running the pipeline — every label was hand-verified against actual
image content, not assumed.

**Test set:** 6 real photos (5 sourced from Pexels under their free-use license, 1 real Bengaluru
traffic photo used throughout development) covering Helmet Non-Compliance, Triple Riding,
Red-Light/Stop-Line, and Illegal Parking (zone-absent case) with both positive and negative
examples.

| Violation Type | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|
| Helmet Non-Compliance | 1 | 2 | 0 | 3 | 0.33 | 1.00 | 0.50 |
| Triple Riding | 1 | 0 | 0 | 5 | 1.00 | 1.00 | 1.00 |
| Red-Light Violation | 0 | 0 | 0 | 6 | n/a | n/a | n/a |
| Stop-Line Violation | 0 | 0 | 0 | 6 | n/a | n/a | n/a |
| Illegal Parking | 0 | 0 | 0 | 6 | n/a | n/a | n/a |

**Overall accuracy across covered types: 93.3%**

Not yet evaluated with verified ground truth: Seatbelt Non-Compliance, Wrong-Side Driving,
Phone Use While Riding/Driving — flagged honestly rather than reported with fabricated numbers.

**Computational efficiency:** ~1.2s/image average (single CPU thread, local hardware) — YOLOv8n
inference dominates runtime. Object detection backbone (YOLOv8n) reports 37.3 mAP@0.5:0.95 on
COCO val2017 per Ultralytics' published benchmarks; full task-specific mAP would require a
larger labeled bounding-box dataset than was feasible to hand-annotate here.

**Found and fixed during evaluation:** the rider pipeline (helmet, triple-riding, phone-use
checks) depended entirely on YOLO confidently detecting the motorcycle class — a single
borderline detection would silently skip every downstream rider-based check. Fixing this raised
accuracy on the covered types from 86.7% → 93.3% and Triple Riding recall from 0% → 100%.

## Known limitations

- Helmet/seatbelt detection use HSV/texture heuristics rather than a trained classifier — accuracy depends on lighting and image resolution, especially for small/distant riders
- Wrong-side driving assumes a simple two-lane road with visible lane markings; doesn't generalize to wide multi-lane highways
- Stop-line and parking-zone detection require visible road paint; violations tied to those zones are skipped (not assumed) when no markings are detected
- In cluttered scenes, YOLO can misclassify background mannequins/posters as people, which can be incorrectly linked as a "rider" to a nearby motorcycle
- The head-crop heuristic (top 32% of person bbox) assumes a roughly centered, upright head; it can miss when a rider's head is significantly off-center (e.g. looking back over their shoulder) within an unusually tall bounding box
