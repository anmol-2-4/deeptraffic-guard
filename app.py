import io
import os
import cv2
import time
import hashlib
import tempfile
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image

import preprocessor
import detector
import violation_engine
import annotator
import database
import road_detector
from ocr_engine import extract_plate
from report_generator import build_pdf
from config import CONFIDENCE_THRESHOLD

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DeepTraffic-Guard",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded",
)
database.init_db()

if "video_results" not in st.session_state:
    st.session_state.video_results = None

# ── Theme constants ───────────────────────────────────────────────────────────
BG       = "#0b0f1a"
SURFACE  = "#111827"
SURFACE2 = "#1a2235"
BORDER   = "#1e2d47"
TEXT      = "#e2e8f0"
MUTED     = "#64748b"
SUBTLE    = "#334155"

SEV_COLOR = {
    "Critical": "#ef4444",
    "High":     "#f97316",
    "Medium":   "#eab308",
    "Low":      "#3b82f6",
}
SEV_BG = {
    "Critical": "#1c0a0a",
    "High":     "#1c0f05",
    "Medium":   "#1a1803",
    "Low":      "#070e1f",
}

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
/* ── Reset & base ── */
html, body, [data-testid="stAppViewContainer"] {{
    background: {BG};
    font-family: 'Inter', 'Segoe UI', sans-serif;
}}
[data-testid="stSidebar"] {{
    background: {SURFACE};
    border-right: 1px solid {BORDER};
}}
[data-testid="stSidebarContent"] {{ padding: 1.5rem 1.2rem; }}

/* ── Typography ── */
h1,h2,h3,h4 {{ color: {TEXT} !important; font-weight: 600; letter-spacing: -0.02em; }}
p, li, span  {{ color: {MUTED}; }}
.stMarkdown  {{ color: {MUTED}; }}
label, .stRadio label {{ color: {MUTED} !important; font-size: 0.82rem; }}

/* ── Sidebar title ── */
.sidebar-title {{
    font-size: 1.05rem;
    font-weight: 700;
    color: {TEXT};
    letter-spacing: -0.01em;
    margin-bottom: 2px;
}}
.sidebar-sub {{
    font-size: 0.74rem;
    color: {SUBTLE};
    margin-bottom: 1rem;
}}

/* ── Tab bar ── */
[data-testid="stTabs"] [role="tablist"] {{
    background: {SURFACE};
    border-radius: 10px;
    padding: 4px;
    gap: 4px;
    border: 1px solid {BORDER};
}}
[data-testid="stTabs"] [role="tab"] {{
    border-radius: 7px;
    padding: 8px 20px;
    font-size: 0.83rem;
    font-weight: 500;
    color: {MUTED};
    border: none;
    background: transparent;
}}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{
    background: {SURFACE2};
    color: {TEXT};
    box-shadow: 0 1px 3px rgba(0,0,0,0.4);
}}

/* ── Cards ── */
.card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 20px 22px;
}}
.card-sm {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 10px;
}}

/* ── KPI cards ── */
.kpi-grid {{ display:grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-bottom: 20px; }}
.kpi {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 18px 20px;
    text-align: center;
}}
.kpi-val  {{ font-size: 2rem; font-weight: 700; color: {TEXT}; line-height: 1; }}
.kpi-lbl  {{ font-size: 0.70rem; text-transform: uppercase; letter-spacing: 0.08em; color: {MUTED}; margin-top: 6px; }}
.kpi-sub  {{ font-size: 0.68rem; color: {SUBTLE}; margin-top: 3px; }}

/* ── Violation cards ── */
.v-card {{
    border-radius: 10px;
    padding: 13px 15px;
    margin-bottom: 8px;
    border-left: 3px solid;
    transition: opacity 0.2s;
}}
.v-header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:5px; }}
.v-type   {{ font-size: 0.88rem; font-weight: 600; color: {TEXT}; }}
.v-badge  {{ font-size: 0.65rem; font-weight: 700; padding: 2px 9px; border-radius: 20px; letter-spacing: 0.05em; }}
.v-meta   {{ font-size: 0.74rem; color: {MUTED}; margin-top: 4px; }}
.v-plate  {{ font-family: 'Courier New', monospace; background: #0f172a; border: 1px solid {BORDER};
             padding: 1px 7px; border-radius: 4px; color: #38bdf8; font-size: 0.76rem; }}

/* ── Alert/clear banners ── */
.banner {{
    border-radius: 10px;
    padding: 11px 15px;
    font-size: 0.88rem;
    font-weight: 600;
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
}}
.banner-red   {{ background: #1a0808; border: 1px solid #ef4444; color: #fca5a5; }}
.banner-green {{ background: #071510; border: 1px solid #22c55e; color: #86efac; }}
.banner-blue  {{ background: #070e1f; border: 1px solid #3b82f6; color: #93c5fd; }}

/* ── Section label ── */
.section-lbl {{
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: {SUBTLE};
    border-bottom: 1px solid {BORDER};
    padding-bottom: 6px;
    margin: 16px 0 12px;
}}

/* ── Detection zone chips ── */
.chip {{
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 11px;
    border-radius: 20px;
    font-size: 0.73rem;
    font-weight: 500;
    margin: 3px 3px 3px 0;
}}
.chip-green  {{ background: #052e16; color: #86efac; border: 1px solid #166534; }}
.chip-grey   {{ background: #1c1917; color: #78716c; border: 1px solid #292524; }}
.chip-blue   {{ background: #071527; color: #7dd3fc; border: 1px solid #1d4ed8; }}

/* ── Upload area ── */
[data-testid="stFileUploadDropzone"] {{
    background: {SURFACE};
    border: 2px dashed {BORDER};
    border-radius: 14px;
    color: {MUTED};
}}

/* ── Streamlit widget overrides ── */
div[data-testid="stSlider"] label {{ font-size: 0.80rem; color: {MUTED}; }}
div[data-testid="stCheckbox"] label {{ font-size: 0.80rem; }}
[data-testid="stMetric"] {{ background:{SURFACE}; border-radius:10px; padding:12px 16px; border:1px solid {BORDER}; }}
[data-testid="stMetricValue"] {{ color: {TEXT} !important; }}
.stProgress > div > div {{ background: #3b82f6; border-radius: 4px; }}
.stButton > button {{ border-radius: 8px; font-weight: 600; font-size: 0.84rem; border: none; }}
.stButton > button[kind="primary"] {{ background: #1d4ed8; color: #fff; }}
.stButton > button[kind="primary"]:hover {{ background: #2563eb; }}
.stDownloadButton > button {{ border-radius: 8px; font-weight: 600; font-size: 0.84rem; }}
[data-testid="stDataFrame"] {{ border: 1px solid {BORDER}; border-radius: 10px; overflow: hidden; }}

/* ── Scrollbar ── */
::-webkit-scrollbar {{ width: 5px; }}
::-webkit-scrollbar-track {{ background: {SURFACE}; }}
::-webkit-scrollbar-thumb {{ background: {SUBTLE}; border-radius: 3px; }}

/* ── Divider ── */
hr {{ border-color: {BORDER} !important; margin: 12px 0; }}
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def kpi(value, label, sub="", cols=None):
    html = f"""
    <div class="kpi">
      <div class="kpi-val">{value}</div>
      <div class="kpi-lbl">{label}</div>
      {"<div class='kpi-sub'>" + sub + "</div>" if sub else ""}
    </div>"""
    if cols:
        cols.markdown(html, unsafe_allow_html=True)
    else:
        st.markdown(html, unsafe_allow_html=True)


def violation_card(v, ev_path=None):
    sev    = v.get("severity", "Medium")
    color  = SEV_COLOR.get(sev, "#94a3b8")
    bg     = SEV_BG.get(sev, SURFACE)
    icon   = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🔵"}.get(sev, "⚪")
    conf   = int(v.get("confidence", 0) * 100)
    plate  = v.get("license_plate", "")
    vclass = v.get("vehicle_class", "").upper()

    plate_html = ""
    if plate and plate not in ("N/A", "UNREADABLE", "OCR_UNAVAILABLE", ""):
        plate_html = f'&nbsp;·&nbsp; <span class="v-plate">{plate}</span>'

    st.markdown(f"""
    <div class="v-card" style="background:{bg}; border-color:{color};">
      <div class="v-header">
        <span class="v-type">{icon} &nbsp;{v['type']}</span>
        <span class="v-badge" style="background:{color}; color:#fff;">{sev.upper()}</span>
      </div>
      <div class="v-meta">{vclass}{plate_html} &nbsp;·&nbsp; Confidence: {conf}%</div>
    </div>
    """, unsafe_allow_html=True)

    if ev_path:
        try:
            st.image(ev_path, use_container_width=True)
        except Exception:
            pass


def banner(msg, kind="red"):
    icon = {"red": "⚠", "green": "✓", "blue": "ℹ"}.get(kind, "ℹ")
    st.markdown(
        f'<div class="banner banner-{kind}"><span>{icon}</span>{msg}</div>',
        unsafe_allow_html=True,
    )


def chip(text, kind="grey"):
    return f'<span class="chip chip-{kind}">{text}</span>'


def _overlaps_vehicle(sign_bbox, dets, iou_thresh=0.25):
    sx1, sy1, sx2, sy2 = sign_bbox
    for d in dets:
        if d["class"] not in {"car", "motorcycle", "bus", "truck", "rider"}:
            continue
        vx1, vy1, vx2, vy2 = d["bbox"]
        ix1, iy1 = max(sx1, vx1), max(sy1, vy1)
        ix2, iy2 = min(sx2, vx2), min(sy2, vy2)
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        s_area = max(1, (sx2 - sx1) * (sy2 - sy1))
        if inter / s_area > iou_thresh:
            return True
    return False


def save_all(violations, frame_hash, ts, ev_paths, location):
    for i, v in enumerate(violations):
        database.insert_violation({
            "timestamp":      ts,
            "violation_type": v["type"],
            "severity":       v["severity"],
            "vehicle_class":  v.get("vehicle_class", ""),
            "license_plate":  v.get("license_plate", "N/A"),
            "confidence":     v.get("confidence", 0.0),
            "image_path":     ev_paths[i] if i < len(ev_paths) else "",
            "location":       location,
            "frame_hash":     frame_hash,
            "raw_detection":  {"bbox": v["bbox"]},
        })


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="sidebar-title">🚦 DeepTraffic-Guard</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-sub">AI Traffic Enforcement System</div>', unsafe_allow_html=True)
    st.divider()

    st.markdown('<div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.1em;color:#475569;margin-bottom:8px">Camera</div>', unsafe_allow_html=True)
    camera_node = st.text_input("Node ID",   value="BLR-CAM-NODE-01", label_visibility="collapsed")
    location    = st.text_input("Location",  value="MG Road, Bengaluru", label_visibility="collapsed")
    st.divider()

    st.markdown('<div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.1em;color:#475569;margin-bottom:8px">Detection</div>', unsafe_allow_html=True)
    conf_thresh    = st.slider("Confidence", 0.10, 1.0, CONFIDENCE_THRESHOLD, 0.05,
                               label_visibility="visible")
    run_preprocess = st.toggle("Auto image enhancement", value=True)


# ── Main tabs ─────────────────────────────────────────────────────────────────
tab_analyze, tab_video, tab_dash = st.tabs(["  Analyze Image  ", "  Analyze Video  ", "  Dashboard  "])


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 1 — Analyze
# ══════════════════════════════════════════════════════════════════════════════
def _render_analyze_tab():
    st.markdown(f"""
    <div style="margin-bottom:20px">
      <h2 style="margin:0;padding:0">Traffic Violation Analyzer</h2>
      <span style="font-size:0.78rem;color:{SUBTLE};">{camera_node} &nbsp;·&nbsp; {location}</span>
    </div>
    """, unsafe_allow_html=True)

    uploaded_files = st.file_uploader(
        "Upload traffic camera image(s)",
        type=["jpg", "jpeg", "png"],
        label_visibility="collapsed",
        accept_multiple_files=True,
        help="Upload multiple images at once for batch processing across a camera fleet.",
    )

    if not uploaded_files:
        st.markdown(f"""
        <div style="text-align:center; padding:70px 20px; background:{SURFACE};
                    border:1px dashed {BORDER}; border-radius:14px; margin-top:10px;">
          <div style="font-size:2.8rem">📷</div>
          <div style="font-size:1rem; color:#475569; margin-top:12px;">Drop one or more traffic camera images to begin</div>
          <div style="font-size:0.78rem; color:{SUBTLE}; margin-top:6px;">JPG · JPEG · PNG &nbsp;·&nbsp; multiple files supported for batch analysis</div>
        </div>
        """, unsafe_allow_html=True)
        return

    # ── Batch mode: 2+ images uploaded ───────────────────────────────────────────
    if len(uploaded_files) > 1:
        st.markdown(f"""
        <div style="margin-bottom:14px">
          <h3 style="margin:0;padding:0;font-size:1.1rem;">Batch Analysis &nbsp;·&nbsp; {len(uploaded_files)} images</h3>
          <span style="font-size:0.78rem;color:{SUBTLE};">Simulates fleet-scale processing across multiple camera frames</span>
        </div>
        """, unsafe_allow_html=True)

        bbar = st.progress(0, "Starting batch...")
        batch_t0 = time.time()
        batch_results = []

        for i, f in enumerate(uploaded_files):
            f_bytes = f.getvalue()
            f_hash = hashlib.md5(f_bytes).hexdigest()
            f_img = np.array(Image.open(io.BytesIO(f_bytes)).convert("RGB"))

            img_t0 = time.time()
            f_proc, f_diag = (preprocessor.enhance(f_img) if run_preprocess else (f_img.copy(), {}))
            f_sy, f_pz, f_signs, f_zmeta = road_detector.auto_detect_zones(f_proc)
            f_dets = detector.run(f_proc, conf=conf_thresh)
            f_signs = [s for s in f_signs if not _overlaps_vehicle(s["bbox"], f_dets)]
            f_viols = violation_engine.evaluate_all(f_dets, f_proc, f_sy, f_pz)
            f_ann, f_ev_paths = annotator.render(f_proc, f_viols, f_dets, f_sy, f_pz, camera_node, f_signs)
            img_ms = (time.time() - img_t0) * 1000

            batch_results.append({
                "name": f.name, "hash": f_hash, "annotated": f_ann,
                "detections": f_dets, "violations": f_viols, "ev_paths": f_ev_paths,
                "ms": img_ms,
            })
            bbar.progress((i + 1) / len(uploaded_files), f"Processed {i+1}/{len(uploaded_files)} — {f.name}")

        batch_elapsed = time.time() - batch_t0
        bbar.empty()

        total_objects = sum(len(r["detections"]) for r in batch_results)
        total_viols = sum(len(r["violations"]) for r in batch_results)
        throughput = len(batch_results) / batch_elapsed if batch_elapsed > 0 else 0

        k1, k2, k3, k4 = st.columns(4)
        kpi(len(batch_results), "Images Processed", cols=k1)
        kpi(total_objects, "Total Objects", cols=k2)
        kpi(total_viols, "Total Violations", cols=k3)
        kpi(f"{throughput:.2f}/s", "Throughput", sub=f"{batch_elapsed:.1f}s total", cols=k4)

        st.markdown("<br>", unsafe_allow_html=True)
        if total_viols:
            banner(f"{total_viols} violation(s) found across {len(batch_results)} images", "red")
        else:
            banner("No violations detected across this batch", "green")

        st.markdown('<div class="section-lbl">PER-IMAGE RESULTS</div>', unsafe_allow_html=True)
        for r in batch_results:
            with st.expander(f"{'⚠' if r['violations'] else '✓'}  {r['name']}  —  "
                              f"{len(r['violations'])} violation(s)  ·  {r['ms']:.0f}ms"):
                ec1, ec2 = st.columns([3, 2])
                ec1.image(r["annotated"], use_container_width=True)
                with ec2:
                    if not r["violations"]:
                        st.caption("No violations found.")
                    for v in r["violations"]:
                        violation_card(v)

        # Bulk export: ZIP of all annotated images
        import zipfile
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for r in batch_results:
                img_buf = io.BytesIO()
                Image.fromarray(r["annotated"]).save(img_buf, format="PNG")
                zf.writestr(f"{r['hash'][:8]}_{r['name']}.png", img_buf.getvalue())

        st.markdown('<div class="section-lbl">EXPORT</div>', unsafe_allow_html=True)
        dl1, dl2 = st.columns(2)
        dl1.download_button(
            "⬇  Download All Annotated Images (ZIP)",
            data=zip_buf.getvalue(),
            file_name="batch_evidence.zip",
            mime="application/zip",
            use_container_width=True,
        )
        if total_viols and dl2.button("💾  Save All Violations to Database", type="primary", use_container_width=True):
            ts_batch = time.strftime("%Y-%m-%d %H:%M:%S")
            saved = 0
            for r in batch_results:
                if r["violations"]:
                    save_all(r["violations"], r["hash"], ts_batch, r["ev_paths"], location)
                    saved += len(r["violations"])
            st.toast(f"Saved {saved} violation(s) across {len(batch_results)} images.")

        return

    # ── Single-image mode ─────────────────────────────────────────────────────────
    uploaded = uploaded_files[0]
    img_bytes  = uploaded.getvalue()
    frame_hash = hashlib.md5(img_bytes).hexdigest()
    pil_img    = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    img_rgb    = np.array(pil_img)

    # ── Run pipeline ──────────────────────────────────────────────────────────
    bar = st.progress(0)

    bar.progress(5,  "Enhancing image...")
    proc_rgb, diag = (preprocessor.enhance(img_rgb) if run_preprocess
                      else (img_rgb.copy(), {}))

    bar.progress(25, "Detecting stop lines & parking zones...")
    stop_y, park_zone, signs, zmeta = road_detector.auto_detect_zones(proc_rgb)

    bar.progress(45, "Running object detection...")
    t0 = time.time()
    detections = detector.run(proc_rgb, conf=conf_thresh)

    signs = [s for s in signs if not _overlaps_vehicle(s["bbox"], detections)]
    zmeta["signs_detected"] = len(signs)

    bar.progress(62, "Reading license plates...")
    for d in detections:
        if d["class"] in {"car", "motorcycle", "bus", "truck"}:
            d["attrs"]["plate"] = extract_plate(proc_rgb, d["bbox"])

    bar.progress(75, "Evaluating violations...")
    violations = violation_engine.evaluate_all(
        detections, proc_rgb, stop_y, park_zone
    )

    # Attach best nearby plate to each violation
    for v in violations:
        vx1 = v["bbox"][0]
        best_plate, best_conf = "N/A", 0.0
        for d in detections:
            if d["class"] in {"car", "motorcycle", "bus", "truck"}:
                pi = d["attrs"].get("plate", {})
                if pi.get("confidence", 0) > best_conf and abs(d["bbox"][0] - vx1) < 120:
                    best_plate = pi.get("plate", "N/A")
                    best_conf  = pi.get("confidence", 0)
        v["license_plate"] = best_plate

    elapsed_ms = int((time.time() - t0) * 1000)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")

    bar.progress(90, "Rendering evidence...")
    annotated, ev_paths = annotator.render(
        proc_rgb, violations, detections,
        stop_y, park_zone, camera_node, signs,
    )
    bar.progress(100, "Done")
    time.sleep(0.2)
    bar.empty()

    # ── Layout ────────────────────────────────────────────────────────────────
    left, right = st.columns([3, 2], gap="large")

    with left:
        # Zone detection chips
        chips_html = ""
        if zmeta["stop_line_detected"]:
            chips_html += chip("🛑 Stop line detected", "green")
        else:
            chips_html += chip("🛑 No stop line found in image", "grey")

        if zmeta["parking_zone_detected"]:
            chips_html += chip("🚫 Parking zone detected", "green")
        else:
            chips_html += chip("🚫 No parking markings found", "grey")

        if zmeta["signs_detected"]:
            chips_html += chip(f"🪧 {zmeta['signs_detected']} road sign(s)", "blue")

        st.markdown(chips_html + "<br>", unsafe_allow_html=True)
        st.image(annotated, use_container_width=True)

        col_dl, col_pdf = st.columns([1, 1])
        buf = io.BytesIO()
        Image.fromarray(annotated).save(buf, format="PNG")
        col_dl.download_button(
            "⬇  Download Evidence",
            data=buf.getvalue(),
            file_name=f"evidence_{frame_hash[:8]}.png",
            mime="image/png",
            use_container_width=True,
        )
        if violations:
            pdf_bytes = build_pdf(violations, annotated, camera_node, location, ts, ev_paths)
            col_pdf.download_button(
                "📄  Export PDF Report",
                data=pdf_bytes,
                file_name=f"report_{frame_hash[:8]}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

        if run_preprocess and any(diag.values()):
            with st.expander("Image enhancement details"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Blur",     "Fixed"  if diag.get("was_blurry")        else "—")
                c2.metric("Low Light","Fixed"  if diag.get("was_dark")           else "—")
                c3.metric("Shadow",   "Fixed"  if diag.get("shadow_corrected")   else "—")
                oc, ec = st.columns(2)
                oc.image(img_rgb,  caption="Original",  use_container_width=True)
                ec.image(proc_rgb, caption="Enhanced",  use_container_width=True)

    with right:
        # Stats row
        s1, s2, s3 = st.columns(3)
        kpi(len(detections), "Objects",    cols=s1)
        kpi(len(violations), "Violations", cols=s2)
        kpi(f"{elapsed_ms}ms", "Time",     cols=s3)

        st.markdown("<br>", unsafe_allow_html=True)

        # Status banner
        if not violations:
            banner("No violations detected in this frame", "green")
        else:
            crit = sum(1 for v in violations if v["severity"] == "Critical")
            high = sum(1 for v in violations if v["severity"] == "High")
            parts = [f"{len(violations)} violation(s) detected"]
            if crit: parts.append(f"{crit} Critical")
            if high: parts.append(f"{high} High")
            banner(" · ".join(parts), "red")

        st.markdown('<div class="section-lbl">VIOLATIONS</div>', unsafe_allow_html=True)

        if not violations:
            st.markdown(f"""
            <div style="text-align:center; padding:30px 0; color:{SUBTLE}; font-size:0.84rem;">
              No violations found.<br>
              <span style="font-size:0.75rem; color:#1e2d47;">Try an image with traffic activity.</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            for i, v in enumerate(violations):
                violation_card(v, ev_paths[i] if i < len(ev_paths) else None)

        st.divider()

        if database.dedup_check(frame_hash):
            banner("This frame was already saved to the database.", "blue")

        if violations:
            if st.button("💾  Save All Violations", type="primary", use_container_width=True):
                save_all(violations, frame_hash, ts, ev_paths, location)
                st.toast(f"Saved {len(violations)} violation(s).")

        with st.expander("JSON payload"):
            st.json({
                "timestamp":   ts,
                "camera_node": camera_node,
                "location":    location,
                "zones_detected": {
                    "stop_line":    stop_y,
                    "parking_zone": park_zone,
                },
                "violations": [{
                    "type":          v["type"],
                    "severity":      v["severity"],
                    "vehicle_class": v.get("vehicle_class"),
                    "license_plate": v.get("license_plate"),
                    "confidence":    round(v.get("confidence", 0), 3),
                    "bbox":          v["bbox"],
                } for v in violations],
            })


with tab_analyze:
    _render_analyze_tab()


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 2 — Video Analyzer
# ══════════════════════════════════════════════════════════════════════════════
with tab_video:
    st.markdown(f"""
    <div style="margin-bottom:20px">
      <h2 style="margin:0;padding:0">Video Violation Scanner</h2>
      <span style="font-size:0.78rem;color:{SUBTLE};">{camera_node} &nbsp;·&nbsp; {location}</span>
    </div>
    """, unsafe_allow_html=True)

    uploaded_vid = st.file_uploader(
        "Upload traffic video",
        type=["mp4", "avi", "mov", "mkv"],
        key="video_upload",
        label_visibility="collapsed",
    )

    if not uploaded_vid:
        st.markdown(f"""
        <div style="text-align:center; padding:70px 20px; background:{SURFACE};
                    border:1px dashed {BORDER}; border-radius:14px; margin-top:10px;">
          <div style="font-size:2.8rem">🎥</div>
          <div style="font-size:1rem; color:#475569; margin-top:12px;">
            Drop a traffic video to scan for violations</div>
          <div style="font-size:0.78rem; color:{SUBTLE}; margin-top:6px;">
            MP4 · AVI · MOV · MKV &nbsp;·&nbsp; Max 50 MB</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        vid_bytes = uploaded_vid.read()
        if len(vid_bytes) > 50 * 1024 * 1024:
            banner("Video exceeds 50 MB — please upload a shorter clip.", "red")
        else:
            vleft, vright = st.columns([3, 2], gap="large")

            with vleft:
                st.video(vid_bytes)

            with vright:
                sample_n = st.slider("Process every N frames", 1, 15, 5,
                                     help="Higher = faster but fewer frames checked")
                st.markdown("<br>", unsafe_allow_html=True)

                if st.button("▶  Analyze Video", type="primary", use_container_width=True):
                    st.session_state.video_results = None

                    tmp_in = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
                    tmp_in.write(vid_bytes)
                    tmp_in.close()
                    tmp_out = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
                    tmp_out.close()
                    out_path = tmp_out.name

                    try:
                        cap     = cv2.VideoCapture(tmp_in.name)
                        total   = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
                        fps_v   = cap.get(cv2.CAP_PROP_FPS) or 25
                        fw      = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        fh_v    = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        fourcc  = cv2.VideoWriter_fourcc(*'mp4v')
                        writer  = cv2.VideoWriter(out_path, fourcc, fps_v, (fw, fh_v))

                        vbar       = st.progress(0, "Analyzing…")
                        all_viols  = []
                        key_frames = []
                        last_ann   = None
                        fidx       = 0

                        while True:
                            ret, frame = cap.read()
                            if not ret:
                                break
                            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                            if fidx % sample_n == 0:
                                proc, _ = (preprocessor.enhance(frame_rgb)
                                           if run_preprocess else (frame_rgb.copy(), {}))
                                sy, pz, sg, _ = road_detector.auto_detect_zones(proc)
                                dets  = detector.run(proc, conf=conf_thresh)
                                sg    = [s for s in sg if not _overlaps_vehicle(s["bbox"], dets)]
                                viols = violation_engine.evaluate_all(dets, proc, sy, pz)
                                ann, _ = annotator.render(proc, viols, dets, sy, pz, camera_node, sg)
                                all_viols.extend(viols)
                                if viols and len(key_frames) < 6:
                                    key_frames.append((ann.copy(), list(viols)))
                                last_ann = ann

                            out_frame = last_ann if last_ann is not None else frame_rgb
                            writer.write(cv2.cvtColor(out_frame, cv2.COLOR_RGB2BGR))
                            fidx += 1
                            if fidx % 15 == 0:
                                vbar.progress(min(fidx / total, 1.0),
                                              f"Frame {fidx} / {total}")

                        cap.release()
                        writer.release()
                        vbar.progress(1.0, "Done ✓")

                        with open(out_path, 'rb') as f:
                            vid_out_bytes = f.read()

                        v_ts = time.strftime("%Y-%m-%d %H:%M:%S")
                        st.session_state.video_results = {
                            "violations":  all_viols,
                            "video_bytes": vid_out_bytes,
                            "key_frames":  key_frames,
                            "stats":       {"processed": max(1, (fidx + sample_n - 1) // sample_n),
                                            "total": total},
                            "ts":          v_ts,
                        }
                    finally:
                        try:
                            os.unlink(tmp_in.name)
                        except Exception:
                            pass
                        try:
                            os.unlink(out_path)
                        except Exception:
                            pass

                # ── Results ───────────────────────────────────────────────────
                res = st.session_state.video_results
                if res:
                    all_viols = res["violations"]
                    vk1, vk2, vk3 = st.columns(3)
                    kpi(res["stats"]["total"],     "Total Frames", cols=vk1)
                    kpi(res["stats"]["processed"], "Analyzed",     cols=vk2)
                    kpi(len(all_viols),            "Violations",   cols=vk3)
                    st.markdown("<br>", unsafe_allow_html=True)

                    if all_viols:
                        banner(f"{len(all_viols)} violation(s) detected across video", "red")
                        st.markdown('<div class="section-lbl">BY TYPE</div>',
                                    unsafe_allow_html=True)
                        by_type = {}
                        for v in all_viols:
                            by_type[v["type"]] = by_type.get(v["type"], 0) + 1
                        for vtype, cnt in sorted(by_type.items(), key=lambda x: -x[1]):
                            sev   = next((v["severity"] for v in all_viols
                                          if v["type"] == vtype), "Medium")
                            color = SEV_COLOR.get(sev, "#94a3b8")
                            bg    = SEV_BG.get(sev, SURFACE)
                            st.markdown(f"""
                            <div class="v-card" style="background:{bg};border-color:{color};">
                              <div class="v-header">
                                <span class="v-type">{vtype}</span>
                                <span class="v-badge" style="background:{color};color:#fff;"
                                >{cnt}×</span>
                              </div>
                            </div>""", unsafe_allow_html=True)
                    else:
                        banner("No violations detected in this video", "green")

                    st.markdown('<div class="section-lbl">EXPORTS</div>',
                                unsafe_allow_html=True)
                    ex1, ex2 = st.columns(2)
                    ex1.download_button(
                        "⬇  Annotated Video",
                        data=res["video_bytes"],
                        file_name="annotated_video.mp4",
                        mime="video/mp4",
                        use_container_width=True,
                    )
                    if res["key_frames"] and all_viols:
                        ann_img, _ = res["key_frames"][-1]
                        pdf_bytes  = build_pdf(
                            all_viols, ann_img, camera_node, location,
                            res["ts"], [], frame_stats=res["stats"],
                        )
                        ex2.download_button(
                            "📄  PDF Report",
                            data=pdf_bytes,
                            file_name="video_report.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                        )

            # ── Key frames ────────────────────────────────────────────────────
            res = st.session_state.video_results
            if res and res["key_frames"]:
                st.markdown('<div class="section-lbl">KEY VIOLATION FRAMES</div>',
                            unsafe_allow_html=True)
                kf_list = res["key_frames"][:3]
                kf_cols = st.columns(len(kf_list))
                for i, (kf_img, kf_viols) in enumerate(kf_list):
                    with kf_cols[i]:
                        st.image(kf_img, use_container_width=True)
                        for kv in kf_viols[:2]:
                            sev   = kv.get("severity", "Medium")
                            color = SEV_COLOR.get(sev, "#94a3b8")
                            st.markdown(
                                f'<div style="font-size:0.74rem;color:{color};">'
                                f'⚠ {kv["type"]}</div>',
                                unsafe_allow_html=True,
                            )


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 3 — Dashboard
# ══════════════════════════════════════════════════════════════════════════════
with tab_dash:
    st.markdown(f"""
    <div style="margin-bottom:20px">
      <h2 style="margin:0;padding:0">Analytics Dashboard</h2>
      <span style="font-size:0.78rem;color:{SUBTLE};">Violation statistics and searchable records</span>
    </div>
    """, unsafe_allow_html=True)

    stats = database.get_summary_stats()
    most_common = max(stats["by_type"], key=stats["by_type"].get) if stats["by_type"] else "—"

    # KPI row
    k1, k2, k3, k4, k5 = st.columns(5)
    kpi(stats["total"],                          "Total",      cols=k1)
    kpi(stats["today"],                          "Today",      cols=k2)
    kpi(stats["by_severity"].get("Critical", 0), "Critical",   cols=k3)
    kpi(stats["by_severity"].get("High", 0),     "High",       cols=k4)
    kpi(most_common.split()[0] if most_common != "—" else "—",
        "Top Violation", sub=most_common if most_common != "—" else "", cols=k5)

    st.markdown("<br>", unsafe_allow_html=True)

    if stats["total"] == 0:
        st.markdown(f"""
        <div style="text-align:center; padding:60px 0; background:{SURFACE};
                    border:1px solid {BORDER}; border-radius:12px;">
          <div style="font-size:2.5rem">📊</div>
          <div style="color:#475569; margin-top:10px; font-size:0.92rem;">No violations recorded yet</div>
          <div style="color:{SUBTLE}; font-size:0.78rem; margin-top:6px;">
            Analyze images in the Analyze tab and save violations to see statistics here.
          </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        import altair as alt

        CHART_BG = SURFACE

        def _dark_chart(chart):
            return (chart
                    .configure_view(stroke=None, fill=CHART_BG)
                    .configure_axis(
                        labelColor=MUTED, titleColor=MUTED,
                        gridColor="#1a2235", domainColor=BORDER, tickColor=BORDER,
                        labelFontSize=11, titleFontSize=11,
                    )
                    .configure_legend(
                        labelColor=MUTED, titleColor=MUTED,
                        strokeColor=BORDER, fillColor=SURFACE,
                        labelFontSize=11,
                    ))

        cc1, cc2, cc3 = st.columns(3)

        with cc1:
            st.markdown('<div class="section-lbl">BY TYPE</div>', unsafe_allow_html=True)
            type_df = (pd.DataFrame(list(stats["by_type"].items()), columns=["Type", "Count"])
                       .sort_values("Count"))
            bar = alt.Chart(type_df).mark_bar(
                cornerRadiusTopRight=4, cornerRadiusBottomRight=4
            ).encode(
                x=alt.X("Count:Q", axis=alt.Axis(grid=True)),
                y=alt.Y("Type:N",  sort="-x", axis=alt.Axis(labelLimit=140)),
                color=alt.Color("Type:N", legend=None,
                                scale=alt.Scale(scheme="tableau10")),
                tooltip=["Type", "Count"],
            ).properties(height=260, background=CHART_BG)
            st.altair_chart(_dark_chart(bar), use_container_width=True)

        with cc2:
            st.markdown('<div class="section-lbl">BY SEVERITY</div>', unsafe_allow_html=True)
            sev_df = pd.DataFrame(list(stats["by_severity"].items()), columns=["Severity", "Count"])
            pie = alt.Chart(sev_df).mark_arc(innerRadius=50, outerRadius=95).encode(
                theta=alt.Theta("Count:Q"),
                color=alt.Color("Severity:N", scale=alt.Scale(
                    domain=["Critical", "High", "Medium", "Low"],
                    range=["#ef4444", "#f97316", "#eab308", "#3b82f6"],
                )),
                tooltip=["Severity", "Count"],
            ).properties(height=260, background=CHART_BG)
            st.altair_chart(_dark_chart(pie), use_container_width=True)

        with cc3:
            st.markdown('<div class="section-lbl">HOURLY TREND</div>', unsafe_allow_html=True)
            if stats["by_hour"]:
                hour_df = (pd.DataFrame(list(stats["by_hour"].items()), columns=["Hour", "Count"])
                           .sort_values("Hour"))
                area = alt.Chart(hour_df).mark_area(
                    line={"color": "#3b82f6", "strokeWidth": 2},
                    color=alt.Gradient(
                        gradient="linear",
                        stops=[alt.GradientStop(color="#1d4ed880", offset=0),
                               alt.GradientStop(color="#0b0f1a00", offset=1)],
                        x1=1, x2=1, y1=1, y2=0,
                    ),
                ).encode(
                    x=alt.X("Hour:N", title="Hour of Day"),
                    y=alt.Y("Count:Q", title="Violations"),
                    tooltip=["Hour", "Count"],
                ).properties(height=260, background=CHART_BG)
                st.altair_chart(_dark_chart(area), use_container_width=True)

    # ── Records ───────────────────────────────────────────────────────────────
    st.divider()
    st.markdown('<div class="section-lbl">RECORDS</div>', unsafe_allow_html=True)

    all_types = ["All"] + sorted(stats["by_type"].keys())
    fc1, fc2, fc3, fc4, fc5 = st.columns([2, 1, 1, 1, 1])
    type_f  = fc1.selectbox("Type",     all_types,
                             label_visibility="collapsed", placeholder="All types")
    sev_f   = fc2.selectbox("Severity", ["All", "Critical", "High", "Medium", "Low"],
                             label_visibility="collapsed")
    date_f  = fc3.date_input("From", value=None, label_visibility="collapsed")
    date_t  = fc4.date_input("To",   value=None, label_visibility="collapsed")
    plate_f = fc5.text_input("Plate", placeholder="Search plate...",
                              label_visibility="collapsed")

    df = database.get_violations(
        violation_type=type_f,
        severity=sev_f,
        date_from=str(date_f) if date_f else None,
        date_to=str(date_t)   if date_t else None,
        plate_search=plate_f  or None,
    )

    if df.empty:
        st.markdown(f'<div style="color:{SUBTLE}; font-size:0.84rem; padding:16px 0;">No records match the filters.</div>',
                    unsafe_allow_html=True)
    else:
        st.dataframe(
            df[["id", "timestamp", "violation_type", "severity",
                "vehicle_class", "license_plate", "confidence", "location"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "confidence": st.column_config.ProgressColumn(
                    "Confidence", min_value=0, max_value=1, format="%.0%%"
                ),
            },
        )
        st.download_button(
            "⬇  Export CSV",
            data=df.to_csv(index=False).encode(),
            file_name="violations_export.csv",
            mime="text/csv",
        )
