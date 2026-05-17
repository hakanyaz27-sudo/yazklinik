CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  user TEXT,
  action TEXT,
  payload_json TEXT,
  ip TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);

CREATE TABLE IF NOT EXISTS patient_consents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id TEXT NOT NULL,
  consent_type TEXT NOT NULL,
  consent_given INTEGER DEFAULT 0,
  consent_text TEXT,
  given_at TEXT,
  withdrawn_at TEXT,
  signed_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_patient_consents_patient
  ON patient_consents(patient_id);
