import os
import json
import sqlite3
import hashlib
import pandas as pd
from config import DB_PATH, EVIDENCE_DIR


def init_db():
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS violations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT NOT NULL,
            violation_type  TEXT NOT NULL,
            severity        TEXT NOT NULL,
            vehicle_class   TEXT,
            license_plate   TEXT,
            confidence      REAL,
            image_path      TEXT,
            location        TEXT DEFAULT 'CAM-NODE-01',
            frame_hash      TEXT,
            raw_detection   TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts   ON violations(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON violations(violation_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sev  ON violations(severity)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_plate ON violations(license_plate)")
    conn.commit()
    conn.close()


def compute_hash(image_bytes: bytes) -> str:
    return hashlib.md5(image_bytes).hexdigest()


def dedup_check(frame_hash: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT 1 FROM violations WHERE frame_hash=? LIMIT 1", (frame_hash,))
    exists = cur.fetchone() is not None
    conn.close()
    return exists


def insert_violation(record: dict):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO violations
            (timestamp, violation_type, severity, vehicle_class, license_plate,
             confidence, image_path, location, frame_hash, raw_detection)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record.get("timestamp"),
        record.get("violation_type"),
        record.get("severity"),
        record.get("vehicle_class"),
        record.get("license_plate"),
        record.get("confidence"),
        record.get("image_path"),
        record.get("location", "CAM-NODE-01"),
        record.get("frame_hash"),
        json.dumps(record.get("raw_detection", {})),
    ))
    conn.commit()
    conn.close()


def get_violations(violation_type=None, severity=None,
                   date_from=None, date_to=None, plate_search=None) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT * FROM violations WHERE 1=1"
    params = []
    if violation_type and violation_type != "All":
        query += " AND violation_type=?"
        params.append(violation_type)
    if severity and severity != "All":
        query += " AND severity=?"
        params.append(severity)
    if date_from:
        query += " AND timestamp >= ?"
        params.append(str(date_from))
    if date_to:
        query += " AND timestamp <= ?"
        params.append(str(date_to) + " 23:59:59")
    if plate_search:
        query += " AND license_plate LIKE ?"
        params.append(f"%{plate_search.upper()}%")
    query += " ORDER BY timestamp DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def get_summary_stats() -> dict:
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM violations").fetchone()[0]
    today = conn.execute(
        "SELECT COUNT(*) FROM violations WHERE date(timestamp) = date('now')"
    ).fetchone()[0]

    by_type = {}
    for row in conn.execute("SELECT violation_type, COUNT(*) FROM violations GROUP BY violation_type"):
        by_type[row[0]] = row[1]

    by_severity = {}
    for row in conn.execute("SELECT severity, COUNT(*) FROM violations GROUP BY severity"):
        by_severity[row[0]] = row[1]

    by_hour = {}
    for row in conn.execute(
        "SELECT strftime('%H', timestamp) as hr, COUNT(*) FROM violations GROUP BY hr ORDER BY hr"
    ):
        by_hour[row[0]] = row[1]

    conn.close()
    return {
        "total": total,
        "today": today,
        "by_type": by_type,
        "by_severity": by_severity,
        "by_hour": by_hour,
    }
