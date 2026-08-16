import os
from contextlib import contextmanager, asynccontextmanager
from typing import Optional, List

import psycopg
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://oss:oss_secret@localhost:5432/ossdb"
)

ALARMS_TOTAL = Counter("oss_alarms_total", "Total alarm masuk", ["severity", "alarm_type"])
ACTIVE_ALARMS = Gauge("oss_active_alarms", "Alarm aktif (belum di-acknowledge)")
NE_AVAILABILITY = Gauge("oss_ne_availability_percent", "Cell availability per NE", ["ne"])
INGEST_ERRORS = Counter("oss_collector_ingest_errors_total", "Total error saat ingest")

VALID_SEVERITY = {"CRITICAL", "MAJOR", "MINOR", "WARNING"}

@contextmanager
def db():
    conn = psycopg.connect(DATABASE_URL, autocommit=True, connect_timeout=5)
    try:
        yield conn
    finally:
        conn.close()

def refresh_active_alarms():
    with db() as conn:
        n = conn.execute(
            "SELECT count(*) FROM alarms WHERE acknowledged = false AND cleared_at IS NULL"
        ).fetchone()[0]
        ACTIVE_ALARMS.set(n)

@asynccontextmanager
async def lifespan(app):
    try:
        refresh_active_alarms()
    except Exception:
        pass
    yield

app = FastAPI(title="OSS Collector", version="0.3.0", lifespan=lifespan)

class Alarm(BaseModel):
    ne_id: str
    severity: str
    alarm_type: str
    timestamp: Optional[str] = None

class KPI(BaseModel):
    ne_id: str
    cell_availability: float
    throughput_mbps: float
    active_users: int
    rrc_setup_success_rate: float
    timestamp: Optional[str] = None

@app.post("/api/v1/alarms", status_code=201)
def ingest_alarm(a: Alarm):
    if a.severity not in VALID_SEVERITY:
        INGEST_ERRORS.inc()
        raise HTTPException(422, f"severity tidak valid: {a.severity}")
    try:
        with db() as conn:
            row = conn.execute(
                "INSERT INTO alarms (ne_id, severity, alarm_type) "
                "VALUES (%s,%s,%s) RETURNING alarm_id, raised_at",
                (a.ne_id, a.severity, a.alarm_type),
            ).fetchone()
    except psycopg.errors.ForeignKeyViolation:
        INGEST_ERRORS.inc()
        raise HTTPException(409, f"NE tidak dikenal: {a.ne_id}")
    ALARMS_TOTAL.labels(severity=a.severity, alarm_type=a.alarm_type).inc()
    refresh_active_alarms()
    return {"alarm_id": row[0], "raised_at": row[1].isoformat(), "ne_id": a.ne_id}

@app.get("/api/v1/alarms")
def list_alarms(severity: Optional[str] = Query(None), ne: Optional[str] = Query(None)):
    sql = ("SELECT alarm_id, ne_id, severity, alarm_type, raised_at, acknowledged "
           "FROM alarms WHERE acknowledged = false AND cleared_at IS NULL")
    params: List = []
    if severity:
        sql += " AND severity = %s"; params.append(severity)
    if ne:
        sql += " AND ne_id = %s"; params.append(ne)
    sql += " ORDER BY raised_at DESC"
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [{"alarm_id": r[0], "ne_id": r[1], "severity": r[2],
             "alarm_type": r[3], "raised_at": r[4].isoformat(), "acknowledged": r[5]}
            for r in rows]

@app.post("/api/v1/alarms/{alarm_id}/acknowledge")
def acknowledge(alarm_id: int):
    with db() as conn:
        row = conn.execute(
            "UPDATE alarms SET acknowledged = true WHERE alarm_id = %s RETURNING alarm_id",
            (alarm_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "alarm tidak ditemukan")
    refresh_active_alarms()
    return {"alarm_id": alarm_id, "acknowledged": True}

@app.post("/api/v1/kpi", status_code=201)
def ingest_kpi(k: KPI):
    try:
        with db() as conn:
            row = conn.execute(
                "INSERT INTO kpi_samples (ne_id, availability, throughput, active_users, rrc_success) "
                "VALUES (%s,%s,%s,%s,%s) RETURNING sample_id, collected_at",
                (k.ne_id, k.cell_availability, k.throughput_mbps, k.active_users, k.rrc_setup_success_rate),
            ).fetchone()
    except psycopg.errors.ForeignKeyViolation:
        INGEST_ERRORS.inc()
        raise HTTPException(409, f"NE tidak dikenal: {k.ne_id}")
    NE_AVAILABILITY.labels(ne=k.ne_id).set(k.cell_availability)
    return {"sample_id": row[0], "collected_at": row[1].isoformat(), "ne_id": k.ne_id}

@app.get("/api/v1/kpi/{ne_id}")
def get_kpi(ne_id: str, limit: int = 100):
    with db() as conn:
        rows = conn.execute(
            "SELECT collected_at, availability, throughput, active_users, rrc_success "
            "FROM kpi_samples WHERE ne_id = %s ORDER BY collected_at DESC LIMIT %s",
            (ne_id, limit),
        ).fetchall()
    return [{"collected_at": r[0].isoformat(),
             "availability": float(r[1]) if r[1] is not None else None,
             "throughput": float(r[2]) if r[2] is not None else None,
             "active_users": r[3],
             "rrc_success": float(r[4]) if r[4] is not None else None} for r in rows]

@app.get("/health")
def health():
    try:
        with db() as conn:
            conn.execute("SELECT 1")
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "degraded", "db": "unreachable", "error": str(e)})
    return {"status": "ok", "db": "connected"}

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
