DROP TABLE IF EXISTS consents;
DROP TABLE IF EXISTS reports;
DROP TABLE IF EXISTS patients;

CREATE TABLE patients (
    patient_id TEXT PRIMARY KEY,
    hospital_name TEXT NOT NULL,
    full_name TEXT NOT NULL,
    dob DATE NOT NULL,
    gender TEXT NOT NULL,
    mobile_number TEXT NOT NULL,
    address TEXT NOT NULL,
    hospital_department TEXT NOT NULL,
    admission_date DATE NOT NULL,
    admission_time TIME NOT NULL,
    doctor_name TEXT NOT NULL,
    reason TEXT NOT NULL,
    patient_status TEXT NOT NULL,      -- Admit, Discharge, Transfer
    discharge_date DATE,
    remarks TEXT,
    feedback TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE reports (
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    hospital_name TEXT NOT NULL,       -- hospital that created the report
    report_type TEXT NOT NULL,
    report_date DATE NOT NULL,
    status TEXT NOT NULL,              -- AVAILABLE or LINK REQUIRED
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
);

CREATE TABLE consents (
    consent_id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    requesting_hospital TEXT NOT NULL,
    status TEXT NOT NULL,              -- PENDING, APPROVED, DENIED
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
);

CREATE INDEX IF NOT EXISTS idx_reports_patient ON reports(patient_id);
CREATE INDEX IF NOT EXISTS idx_consents_patient ON consents(patient_id);