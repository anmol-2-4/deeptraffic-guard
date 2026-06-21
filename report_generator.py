import os
import tempfile
import numpy as np
from PIL import Image


def build_pdf(violations, annotated_img, camera_node, location, ts,
              ev_paths, frame_stats=None):
    """Returns PDF as bytes. frame_stats: optional dict with 'processed'/'total' keys."""
    from fpdf import FPDF, XPos, YPos

    SEV_RGB = {
        "Critical": (220,  38,  38),
        "High":     (234,  88,  12),
        "Medium":   (202, 138,   4),
        "Low":      ( 37,  99, 235),
    }

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header bar
    pdf.set_fill_color(15, 23, 42)
    pdf.rect(0, 0, 210, 30, 'F')
    pdf.set_font('Helvetica', 'B', 14)
    pdf.set_text_color(226, 232, 240)
    pdf.set_xy(10, 9)
    pdf.cell(0, 10, 'DeepTraffic-Guard: Violation Evidence Report')
    pdf.ln(34)

    # Meta table
    meta = [
        ('Camera Node', camera_node),
        ('Location',    location),
        ('Timestamp',   ts),
        ('Violations',  str(len(violations))),
    ]
    if frame_stats:
        meta += [
            ('Frames Processed', str(frame_stats.get('processed', '-'))),
            ('Total Frames',     str(frame_stats.get('total',     '-'))),
        ]
    for label, val in meta:
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_text_color(80, 80, 100)
        pdf.cell(44, 6, label + ':', new_x=XPos.RIGHT, new_y=YPos.LAST)
        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(20, 20, 20)
        pdf.cell(0,  6, val, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    # Annotated image
    tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
    try:
        Image.fromarray(annotated_img).save(tmp.name, quality=88)
        tmp.close()
        pdf.image(tmp.name, x=15, w=180)
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
    pdf.ln(5)

    # Violations table
    if violations:
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(0, 8, 'Detected Violations', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        cols = [8, 66, 24, 22, 38, 32]
        hdrs = ['#', 'Violation Type', 'Severity', 'Confidence', 'License Plate', 'Vehicle']
        pdf.set_fill_color(241, 245, 249)
        pdf.set_font('Helvetica', 'B', 8)
        pdf.set_text_color(60, 60, 90)
        for c, h in zip(cols, hdrs):
            pdf.cell(c, 7, h, border='B', fill=True)
        pdf.ln()

        pdf.set_font('Helvetica', '', 8)
        for i, v in enumerate(violations):
            sev   = v.get('severity', 'Medium')
            r, g, b = SEV_RGB.get(sev, (100, 100, 100))
            plate = v.get('license_plate') or 'N/A'
            if plate in ('UNREADABLE', 'OCR_UNAVAILABLE'):
                plate = 'N/A'
            conf  = str(int(v.get('confidence', 0) * 100)) + '%'
            vc    = (v.get('vehicle_class') or '').title()
            fill  = (i % 2 == 0)
            fc    = (250, 250, 252) if fill else (255, 255, 255)
            pdf.set_fill_color(*fc)
            pdf.set_text_color(30, 30, 30)
            pdf.cell(cols[0], 6, str(i + 1),     fill=fill)
            pdf.cell(cols[1], 6, v['type'][:42],  fill=fill)
            pdf.set_text_color(r, g, b)
            pdf.cell(cols[2], 6, sev,             fill=fill)
            pdf.set_text_color(30, 30, 30)
            pdf.cell(cols[3], 6, conf,            fill=fill)
            pdf.cell(cols[4], 6, plate,           fill=fill)
            pdf.cell(cols[5], 6, vc,              fill=fill)
            pdf.ln()

    # Evidence pages
    for i, ep in enumerate(ev_paths):
        if not (ep and os.path.exists(ep)):
            continue
        pdf.add_page()
        v   = violations[i] if i < len(violations) else {}
        sev = v.get('severity', 'Medium')
        r, g, b = SEV_RGB.get(sev, (60, 60, 60))
        pdf.set_fill_color(r, g, b)
        pdf.rect(0, 0, 210, 18, 'F')
        pdf.set_font('Helvetica', 'B', 12)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(10, 5)
        pdf.cell(0, 8, 'Evidence #' + str(i + 1) + ': ' + v.get('type', 'Violation'))
        pdf.ln(22)
        plate = v.get('license_plate') or 'N/A'
        if plate in ('UNREADABLE', 'OCR_UNAVAILABLE'):
            plate = 'N/A'
        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(80, 80, 80)
        info = ('Severity: ' + sev + '   |   Confidence: ' +
                str(int(v.get('confidence', 0) * 100)) + '%   |   Plate: ' + plate)
        pdf.cell(0, 6, info, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(3)
        pdf.image(ep, x=30, w=150)

    return bytes(pdf.output())
