DROP TABLE IF EXISTS audit_log;
DROP TABLE IF EXISTS consents;
DROP TABLE IF EXISTS reports;
DROP TABLE IF EXISTS patient_accounts;
DROP TABLE IF EXISTS patients;
DROP TABLE IF EXISTS hospitals;

CREATE TABLE hospitals (
    hospital_name TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL
);

CREATE TABLE patients (
    patient_id TEXT PRIMARY KEY,
    hospital_name TEXT NOT NULL,           -- home hospital
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
    patient_status TEXT NOT NULL,          -- Admit, Discharge, Transfer
    discharge_date DATE,
    remarks TEXT,
    feedback TEXT,
    aadhaar_hash TEXT UNIQUE,              -- keyed hash of the Aadhaar number, never the raw number
    aadhaar_last4 TEXT,                    -- for masked display only
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Patient login. Created by the home hospital. The patient ID is the username.
CREATE TABLE patient_accounts (
    patient_id TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
);

CREATE TABLE reports (
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    hospital_name TEXT NOT NULL,           -- hospital that created the report
    report_type TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'SUMMARY',  -- LAB, DIAGNOSTIC, IMAGING, PRESCRIPTION, SUMMARY
    report_date DATE NOT NULL,
    status TEXT NOT NULL,                  -- AVAILABLE or LINK REQUIRED
    file_path TEXT,                        -- file name inside private_uploads/ (not a URL)
    file_sha256 TEXT,
    mime_type TEXT,
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
);

CREATE TABLE consents (
    consent_id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    requesting_hospital TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'LAB',     -- LAB = lab reports only, ALL = everything
    status TEXT NOT NULL,                  -- PENDING, APPROVED, DENIED, CANCELLED, REVOKED
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
);

CREATE TABLE audit_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actor TEXT,                            -- hospital:<name> | patient:<id> | NULL
    action TEXT NOT NULL,
    patient_id TEXT,
    detail TEXT
);

CREATE INDEX IF NOT EXISTS idx_reports_patient ON reports(patient_id);
CREATE INDEX IF NOT EXISTS idx_consents_patient ON consents(patient_id);
CREATE INDEX IF NOT EXISTS idx_consents_requester ON consents(requesting_hospital);