CREATE TABLE IF NOT EXISTS network_elements (
  ne_id       VARCHAR(64) PRIMARY KEY,
  ne_type     VARCHAR(32) NOT NULL,
  region      VARCHAR(64),
  technology  VARCHAR(16)
);

CREATE TABLE IF NOT EXISTS alarms (
  alarm_id     BIGSERIAL PRIMARY KEY,
  ne_id        VARCHAR(64) REFERENCES network_elements(ne_id),
  severity     VARCHAR(16) NOT NULL,
  alarm_type   VARCHAR(64) NOT NULL,
  raised_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  cleared_at   TIMESTAMPTZ,
  acknowledged BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS kpi_samples (
  sample_id    BIGSERIAL PRIMARY KEY,
  ne_id        VARCHAR(64) REFERENCES network_elements(ne_id),
  collected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  availability NUMERIC(5,2),
  throughput   NUMERIC(10,2),
  active_users INTEGER,
  rrc_success  NUMERIC(5,2)
);

-- WAJIB: isi NE dulu. Tabel alarms & kpi_samples punya foreign key ke sini,
-- jadi tanpa baris ini, semua INSERT alarm/KPI akan DITOLAK.
INSERT INTO network_elements (ne_id, ne_type, region, technology) VALUES
  ('RBS_RIYADH_001',   'RBS',    'Riyadh', '3G'),
  ('eNodeB_JEDDAH_042','eNodeB', 'Jeddah', 'LTE'),
  ('gNodeB_DAMMAM_007','gNodeB', 'Dammam', 'NR'),
  ('RBS_MAKKAH_015',   'RBS',    'Makkah', '3G'),
  ('eNodeB_RIYADH_128','eNodeB', 'Riyadh', 'LTE')
ON CONFLICT (ne_id) DO NOTHING;
