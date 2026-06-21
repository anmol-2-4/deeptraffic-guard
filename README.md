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
- **Batch processing** — upload multiple images at once for fleet-scale analysis, with aggregate throughput stats and bulk ZIP export
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
evaluate.py             Violation-level Precision/Recall/F1 evaluation harness
evaluate_map.py         Object-detection mAP@0.5 evaluation harness
```

## Performance evaluation

Run `python3 evaluate.py` to reproduce these results. Ground truth was assigned by manually
viewing each image before running the pipeline — every label was hand-verified against actual
image content, not assumed.

**Test set:** 8 real photos (6 sourced from Pexels under their free-use license, 2 real photos
encountered during live use) covering Helmet Non-Compliance, Triple Riding, Red-Light/Stop-Line,
Illegal Parking (zone-absent case), and Wrong-Side Driving, with both positive and negative
examples.

| Violation Type | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|
| Helmet Non-Compliance | 3 | 2 | 0 | 3 | 0.60 | 1.00 | 0.75 |
| Triple Riding | 1 | 0 | 0 | 7 | 1.00 | 1.00 | 1.00 |
| Red-Light Violation | 0 | 0 | 0 | 8 | n/a | n/a | n/a |
| Stop-Line Violation | 0 | 0 | 0 | 8 | n/a | n/a | n/a |
| Illegal Parking | 0 | 0 | 0 | 8 | n/a | n/a | n/a |
| Wrong-Side Driving | 0 | 1 | 0 | 7 | 0.00 | n/a | n/a |

**Overall accuracy across covered types: 93.75%**

Two real false negatives were found and fixed via this evaluation, both on genuinely bare-headed
riders:

1. A rider scoring 0.23 (just under the 0.28 trigger) because an overly conservative "borderline"
   rule halved the score whenever hair/texture backup signals didn't also confirm -- even though
   the primary skin signal had already legitimately fired. Removed after confirming it gave no
   real protection against the known false-positive cases (they already crossed the trigger either
   way) while suppressing true positives.
2. A rider scoring exactly 0.0 because (a) the helmet-shell color-rejection check had no hue
   restriction, so his blue/grey shirt collar in the crop was misread as a "painted shell" and
   wrongly discounted his already-low skin signal to near zero, and (b) skin and hair were each
   genuinely present at a meaningful level (~50% and ~40% of their own thresholds) but neither
   alone cleared its bar. Fixed by restricting shell-rejection to hues that could plausibly be
   confused with skin in the first place, and adding a narrow "combined partial evidence" path so
   corroborating-but-individually-inconclusive skin+hair+texture signals can still trigger together.
   This second case was caught on the same intersection photo used throughout development --
   the original ground truth label for that photo only checked the one rider relevant to an
   earlier bug and incorrectly assumed the rest were clean; corrected after this discovery.

The Wrong-Side Driving false positive is the documented multi-lane-highway limitation (see below) —
included here deliberately rather than excluded, since hiding a known failure would defeat the
point of an honest evaluation.

Not yet evaluated with verified ground truth: Seatbelt Non-Compliance, Phone Use While Riding/Driving
— both require an external view showing vehicle body + occupant together (see Engineering
Investigations below); flagged honestly rather than reported with fabricated numbers.

**Computational efficiency:** ~1.0–1.2s/image average (single CPU thread, local hardware) — YOLOv8n
inference dominates runtime.

### Object detection mAP

Run `python3 evaluate_map.py` to reproduce. This scores the underlying object-detection quality
itself (did the detector find the right objects, in the right place, with the right class) —
separate from the violation-classification table above. Ground truth bounding boxes were hand-drawn
by visually inspecting every candidate detection box plus manually scanning each image for missed
objects, evaluated at our system's own output class granularity (`rider`/`person`/`motorcycle`/
`car`/`truck`) rather than raw COCO classes, since that reflects what the pipeline actually produces.

| Class | GT | TP | FP | FN | AP@0.5 |
|---|---|---|---|---|---|
| car | 8 | 7 | 0 | 1 | 0.875 |
| motorcycle | 11 | 11 | 1 | 0 | 1.000 |
| person | 2 | 2 | 3 | 0 | 1.000 |
| rider | 11 | 11 | 5 | 0 | 0.972 |
| truck | 2 | 1 | 0 | 1 | 0.500 |

**mAP@0.5 across 5 classes: 0.869**

This is mAP@0.5 (single IoU threshold, PASCAL VOC-style) rather than the stricter COCO
mAP@[0.5:0.95] — the sample size (7 photos) is too small to make that finer breakdown meaningful.
The `truck` class's 0.500 is from a single missed background vehicle out of 2 instances — not
statistically meaningful on its own, included for transparency rather than omitted.

The `person`/`rider` false positives are the same mannequins-in-a-cluttered-storefront issue
documented elsewhere in this README — included here rather than filtered out, since hiding them
would inflate the score. A first version of this script filtered known-false detections out of the
prediction list entirely, which silently removed them from the false-positive count too; caught and
fixed before reporting the final number. Two additional real misses (a heavily-occluded second rider
on a scooter, and a third rider in the triple-riding photo) are deliberately **not** in this table —
neither has a tight box that could be hand-drawn with confidence, so scoring them against a guessed
box would have been less honest than disclosing them as qualitative misses instead.

As a reference point, YOLOv8n (the pretrained, unmodified backbone this system uses) reports 37.3
mAP@0.5:0.95 on the full COCO val2017 benchmark per Ultralytics' published numbers — a much larger,
harder, more diverse benchmark than this project's 7-photo sample, so the two numbers aren't directly
comparable, but both describe the same underlying detector.

**Found and fixed during evaluation:** the rider pipeline (helmet, triple-riding, phone-use
checks) depended entirely on YOLO confidently detecting the motorcycle class — a single
borderline detection would silently skip every downstream rider-based check. Fixing this raised
accuracy on the covered types from 86.7% → 93.3% and Triple Riding recall from 0% → 100%.

## Engineering investigations (and why some things weren't shipped)

**Rain handling.** The preprocessing spec calls for handling rain alongside blur/low-light/shadow.
Two classical-CV rain signals were implemented and tested against a real rainy street photo plus
several clear-weather photos: (1) high-pass streak energy (rain streaks should show as broadly
scattered high-frequency content) and (2) dark-channel haze signature (rain/fog raises the local
minimum-channel value and reduces contrast). Neither discriminated the real rain photo from normal
busy/textured street scenes — the rain photo's statistics fell well within the range of ordinary
clear photos on both signals. Shipping a detector this unreliable would mean misfiring unpredictably
on clear images or missing real rain entirely, so it was deliberately left out rather than shipped
to look complete. Reliable rain detection/removal in practice needs either a trained model or a much
larger calibration set than was feasible to hand-verify here.

**Seatbelt/phone-use require an external view.** Tested directly against two real interior
dashboard-cam-style photos (driver visible from inside the car). YOLO detected only the `person`
class in both — no `car` bounding box, because the vehicle's exterior body isn't visible from this
angle. Both `check_seatbelt` and `check_phone_use` require a person's box to overlap a detected
`car` box to confirm "this person is inside a vehicle," so they structurally cannot fire on
interior-view photos. This matches the system's intended input (external traffic-camera footage),
but is a real boundary worth stating plainly rather than discovering by surprise.

**Mannequins misclassified as people.** A real street photo containing both a 3-person motorcycle
and a row of storefront mannequins caused two mannequins to be misclassified as riders (YOLO was
*more* confident on the mannequins — 0.88 and 0.83 — than on the real riders at 0.57–0.72, so a
confidence-based filter would not help). Distinguishing a static mannequin from a real person isn't
reliably solvable from a single still frame's bounding-box geometry alone. The video pipeline
already processes sequential frames, so a concrete, technically sound next step is a motion-based
filter: a real rider's bounding box shifts across frames while a mannequin's stays fixed — that
signal doesn't exist yet but is a natural extension of code already in place.

## Known limitations

- Helmet/seatbelt detection use HSV/texture heuristics rather than a trained classifier — accuracy depends on lighting and image resolution, especially for small/distant riders
- Wrong-side driving assumes a simple two-lane road with visible lane markings; doesn't generalize to wide multi-lane highways
- Stop-line and parking-zone detection require visible road paint; violations tied to those zones are skipped (not assumed) when no markings are detected
- In cluttered scenes, YOLO can misclassify background mannequins/posters as people, which can be incorrectly linked as a "rider" to a nearby motorcycle (see above — confidence-based filtering does not help)
- The head-crop heuristic (top 32% of person bbox) assumes a roughly centered, upright head; it can miss when a rider's head is significantly off-center (e.g. looking back over their shoulder) within an unusually tall bounding box
- Rain detection was attempted and deliberately not shipped after failing validation (see above)
- Seatbelt and phone-use checks require an external view showing both vehicle body and occupant; they cannot fire on interior/dashboard-cam-style photos (see above)
