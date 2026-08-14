from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import itertools
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

app = FastAPI(title="OSS Collector", version="0.1.0")

# --- Penyimpanan di memori (Phase 1). Diganti PostgreSQL di Phase 2. ---
ALARMS = []          # daftar alarm
KPIS = {}            # ne_id -> daftar sampel KPI
_id_seq = itertools.count(1)

# --- Metrik Prometheus ---
ALARMS_TOTAL = Counter("oss_alarms_total", "Total alarm masuk", ["severity", "alarm_type"])
ACTIVE_ALARMS = Gauge("oss_active_alarms", "Alarm aktif (belum di-acknowledge)")
NE_AVAILABILITY = Gauge("oss_ne_availability_percent", "Cell availability per NE", ["ne"])
INGEST_ERRORS = Counter("oss_collector_ingest_errors_total", "Total error saat ingest")

VALID_SEVERITY = {"CRITICAL", "MAJOR", "MINOR", "WARNING"}

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

def _now():
    return datetime.now(timezone.utc).isoformat()

@app.post("/api/v1/alarms", status_code=201)
def ingest_alarm(alarm: Alarm):
    if alarm.severity not in VALID_SEVERITY:
        INGEST_ERRORS.inc()
        raise HTTPException(status_code=422, detail=f"severity tidak valid: {alarm.severity}")
    rec = {
        "id": next(_id_seq),
        "ne_id": alarm.ne_id,
        "severity": alarm.severity,
        "alarm_type": alarm.alarm_type,
        "timestamp": alarm.timestamp or _now(),
        "acknowledged": False,
    }
    ALARMS.append(rec)
    ALARMS_TOTAL.labels(severity=alarm.severity, alarm_type=alarm.alarm_type).inc()
    ACTIVE_ALARMS.set(sum(1 for a in ALARMS if not a["acknowledged"]))
    return rec

@app.get("/api/v1/alarms")
def list_alarms(severity: Optional[str] = Query(None), ne: Optional[str] = Query(None)):
    result = [a for a in ALARMS if not a["acknowledged"]]
    if severity:
        result = [a for a in result if a["severity"] == severity]
    if ne:
        result = [a for a in result if a["ne_id"] == ne]
    return result

@app.post("/api/v1/alarms/{alarm_id}/acknowledge")
def acknowledge(alarm_id: int):
    for a in ALARMS:
        if a["id"] == alarm_id:
            a["acknowledged"] = True
            ACTIVE_ALARMS.set(sum(1 for x in ALARMS if not x["acknowledged"]))
            return {"id": alarm_id, "acknowledged": True}
    raise HTTPException(status_code=404, detail="alarm tidak ditemukan")

@app.post("/api/v1/kpi", status_code=201)
def ingest_kpi(kpi: KPI):
    rec = kpi.model_dump()
    rec["timestamp"] = kpi.timestamp or _now()
    KPIS.setdefault(kpi.ne_id, []).append(rec)
    NE_AVAILABILITY.labels(ne=kpi.ne_id).set(kpi.cell_availability)
    return rec

@app.get("/api/v1/kpi/{ne_id}")
def get_kpi(ne_id: str):
    return KPIS.get(ne_id, [])

@app.get("/health")
def health():
    # Phase 1: belum ada DB. Phase 2 mengganti ini dengan cek koneksi PostgreSQL.
    return {"status": "ok", "db": "in-memory (phase 1)", "alarms_stored": len(ALARMS)}

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)



