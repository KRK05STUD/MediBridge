import os
from werkzeug.security import generate_password_hash
from app import DATABASE, init_db, get_db, hash_aadhaar

# Demo logins only. Change or remove before any real use.
HOSPITAL_ACCOUNTS = [
    ('City Central Hospital', 'citycentral', 'city-demo-2026'),
    ('Metro Medical Centre', 'metro', 'metro-demo-2026'),
]

# Fictional Aadhaar-format numbers for demo only
PATIENTS = [
    {
        'hospital_name': 'City Central Hospital', 'patient_id': 'PID-2026-001',
        'full_name': 'Demo Patient A', 'dob': '1968-04-12', 'gender': 'Male',
        'mobile_number': '+91 90000 00001', 'address': 'Demo Street, Demo City',
        'hospital_department': 'Cardiology', 'admission_date': '2026-10-20',
        'admission_time': '09:30', 'doctor_name': 'Dr. Demo Sharma',
        'reason': 'Chest discomfort', 'patient_status': 'Admit',
        'discharge_date': None, 'remarks': 'Monitoring vitals', 'feedback': None,
        'aadhaar': '234567890123',
    },
    {
        'hospital_name': 'Metro Medical Centre', 'patient_id': 'PID-2026-002',
        'full_name': 'Demo Patient B', 'dob': '1991-08-03', 'gender': 'Female',
        'mobile_number': '+91 90000 00002', 'address': 'Sample Colony, Demo City',
        'hospital_department': 'Orthopedic', 'admission_date': '2026-10-02',
        'admission_time': '10:15', 'doctor_name': 'Dr. Demo Rao',
        'reason': 'Fractured wrist', 'patient_status': 'Discharge',
        'discharge_date': '2026-10-06', 'remarks': None, 'feedback': 'Recovering well',
        'aadhaar': '345678901234',
    },
    {
        'hospital_name': 'City Central Hospital', 'patient_id': 'PID-2026-003',
        'full_name': 'Demo Patient C', 'dob': '1955-01-22', 'gender': 'Male',
        'mobile_number': '+91 90000 00003', 'address': 'Test Nagar, Demo City',
        'hospital_department': 'Emergency', 'admission_date': '2026-10-30',
        'admission_time': '18:40', 'doctor_name': 'Dr. Demo Reddy',
        'reason': 'Breathlessness', 'patient_status': 'Transfer',
        'discharge_date': None, 'remarks': 'Transfer requested', 'feedback': None,
        'aadhaar': '456789012345',
    },
]

# patient_id, hospital, report_type, category, date, status
REPORTS = [
    ('PID-2026-001', 'City Central Hospital', 'Blood test report', 'LAB', '2026-09-28', 'AVAILABLE'),
    ('PID-2026-001', 'City Central Hospital', 'Lipid profile', 'LAB', '2026-07-02', 'AVAILABLE'),
    ('PID-2026-001', 'City Central Hospital', 'Consultation summary', 'SUMMARY', '2026-08-14', 'AVAILABLE'),
    ('PID-2026-001', 'Metro Medical Centre', 'Prescription', 'PRESCRIPTION', '2026-10-12', 'LINK REQUIRED'),
    ('PID-2026-002', 'Metro Medical Centre', 'Complete blood count', 'LAB', '2026-10-03', 'AVAILABLE'),
    ('PID-2026-002', 'Metro Medical Centre', 'X-ray report', 'IMAGING', '2026-10-01', 'AVAILABLE'),
    ('PID-2026-002', 'Metro Medical Centre', 'Discharge summary', 'SUMMARY', '2026-10-06', 'AVAILABLE'),
    ('PID-2026-003', 'City Central Hospital', 'ECG report', 'DIAGNOSTIC', '2026-10-30', 'AVAILABLE'),
    ('PID-2026-003', 'City Central Hospital', 'Troponin test', 'LAB', '2026-10-30', 'AVAILABLE'),
]

# patient_id, requesting hospital, scope, status
CONSENTS = [
    ('PID-2026-003', 'Metro Medical Centre', 'LAB', 'APPROVED'),
    ('PID-2026-002', 'City Central Hospital', 'LAB', 'PENDING'),
]


def main():
    if os.path.exists(DATABASE):
        os.remove(DATABASE)
        print('Old database removed.')
    init_db()

    conn = get_db()
    conn.executemany(
        'INSERT INTO hospitals (hospital_name, username, password_hash) VALUES (?, ?, ?)',
        [(name, user, generate_password_hash(pw)) for name, user, pw in HOSPITAL_ACCOUNTS]
    )
    for p in PATIENTS:
        p = dict(p)
        aadhaar = p.pop('aadhaar')
        p['aadhaar_hash'] = hash_aadhaar(aadhaar)
        p['aadhaar_last4'] = aadhaar[-4:]
        cols = ', '.join(p.keys())
        marks = ', '.join('?' for _ in p)
        conn.execute(f'INSERT INTO patients ({cols}) VALUES ({marks})', tuple(p.values()))

    conn.executemany(
        'INSERT INTO reports (patient_id, hospital_name, report_type, category, report_date, status) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        REPORTS
    )
    conn.executemany(
        'INSERT INTO consents (patient_id, requesting_hospital, scope, status) VALUES (?, ?, ?, ?)',
        CONSENTS
    )
    conn.commit()
    conn.close()
    print(f'Database ready: {len(PATIENTS)} patients, {len(REPORTS)} reports, '
          f'{len(HOSPITAL_ACCOUNTS)} hospital logins.')


if __name__ == '__main__':
    main()