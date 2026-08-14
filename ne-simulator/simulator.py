import os, time, random, requests
from datetime import datetime, timezone

COLLECTOR = os.environ.get("COLLECTOR_URL", "http://localhost:8000")
FAULT_MODE = os.environ.get("FAULT_MODE")           # isi dengan ne_id untuk mendegradasi NE itu
INTERVAL = int(os.environ.get("INTERVAL_SECONDS", "15"))

NES = [
    "RBS_RIYADH_001",
    "eNodeB_JEDDAH_042",
    "gNodeB_DAMMAM_007",
    "RBS_MAKKAH_015",
    "eNodeB_RIYADH_128",
]
ALARM_TYPES = ["LINK_FAILURE", "CELL_DOWN", "LICENSE_EXPIRY", "TEMPERATURE_HIGH"]
SEVERITIES = ["CRITICAL", "MAJOR", "MINOR", "WARNING"]

def now():
    return datetime.now(timezone.utc).isoformat()

def make_kpi(ne_id):
    degraded = (FAULT_MODE == ne_id)
    if degraded:
        avail = round(random.uniform(85.0, 95.0), 2)
        rrc   = round(random.uniform(70.0, 85.0), 2)
        thr   = round(random.uniform(10.0, 40.0), 2)
    else:
        avail = round(random.uniform(98.5, 100.0), 2)
        rrc   = round(random.uniform(97.0, 99.9), 2)
        thr   = round(random.uniform(80.0, 200.0), 2)
    return {"ne_id": ne_id, "cell_availability": avail, "throughput_mbps": thr,
            "active_users": random.randint(10, 500),
            "rrc_setup_success_rate": rrc, "timestamp": now()}

def make_alarm(ne_id):
    return {"ne_id": ne_id, "severity": random.choice(SEVERITIES),
            "alarm_type": random.choice(ALARM_TYPES), "timestamp": now()}

def main():
    print(f"simulator start -> {COLLECTOR} | FAULT_MODE={FAULT_MODE} | interval={INTERVAL}s")
    while True:
        for ne_id in NES:
            kpi = make_kpi(ne_id)
            try:
                r = requests.post(f"{COLLECTOR}/api/v1/kpi", json=kpi, timeout=5)
                print(f"KPI  {ne_id} avail={kpi['cell_availability']} -> {r.status_code}")
            except requests.RequestException as e:
                print(f"KPI  {ne_id} GAGAL: {e}")
            # ~2% peluang alarm per NE; NE yang di-FAULT_MODE lebih sering
            if random.random() < 0.02 or (FAULT_MODE == ne_id and random.random() < 0.3):
                alarm = make_alarm(ne_id)
                try:
                    r = requests.post(f"{COLLECTOR}/api/v1/alarms", json=alarm, timeout=5)
                    print(f"ALARM {ne_id} {alarm['severity']}/{alarm['alarm_type']} -> {r.status_code}")
                except requests.RequestException as e:
                    print(f"ALARM {ne_id} GAGAL: {e}")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
