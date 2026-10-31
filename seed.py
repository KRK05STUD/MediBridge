import os
from app import DATABASE, init_db, get_db

PATIENTS = [
    {
        'hospital_name': 'City Central Hospital', 'patient_id': 'PID-2026-001',
        'full_name': 'Demo Patient A', 'dob': '1968-04-12', 'gender': 'Male',
        'mobile_number': '+91 90000 00001', 'address': 'Demo Street, Demo City',
        'hospital_department': 'Cardiology', 'admission_date': '2026-10-20',
        'admission_time': '09:30', 'doctor_name': 'Dr. Demo Sharma',
        'reason': 'Chest discomfort', 'patient_status': 'Admit',
        'discharge_date': None, 'remarks': 'Monitoring vitals', 'feedback': None,
    },
    {
        'hospital_name': 'Metro Medical Centre', 'patient_id': 'PID-2026-002',
        'full_name': 'Demo Patient B', 'dob': '1991-08-03', 'gender': 'Female',
        'mobile_number': '+91 90000 00002', 'address': 'Sample Colony, Demo City',
        'hospital_department': 'Orthopedic', 'admission_date': '2026-10-02',
        'admission_time': '10:15', 'doctor_name': 'Dr. Demo Rao',
        'reason': 'Fractured wrist', 'patient_status': 'Discharge',
        'discharge_date': '2026-10-06', 'remarks': None, 'feedback': 'Recovering well',
    },
    {
        'hospital_name': 'City Central Hospital', 'patient_id': 'PID-2026-003',
        'full_name': 'Demo Patient C', 'dob': '1955-01-22', 'gender': 'Male',
        'mobile_number': '+91 90000 00003', 'address': 'Test Nagar, Demo City',
        'hospital_department': 'Emergency', 'admission_date': '2026-10-30',
        'admission_time': '18:40', 'doctor_name': 'Dr. Demo Reddy',
        'reason': 'Breathlessness', 'patient_status': 'Transfer',
        'discharge_date': None, 'remarks': 'Transfer requested', 'feedback': None,
    },
]

REPORTS = [
    ('PID-2026-001', 'City Central Hospital', 'Blood test report', '2026-09-28', 'AVAILABLE'),
    ('PID-2026-001', 'City Central Hospital', 'Consultation summary', '2026-08-14', 'AVAILABLE'),
    ('PID-2026-001', 'Metro Medical Centre', 'Prescription', '2026-10-12', 'LINK REQUIRED'),
    ('PID-2026-002', 'Metro Medical Centre', 'X-ray report', '2026-10-01', 'AVAILABLE'),
    ('PID-2026-002', 'Metro Medical Centre', 'Discharge summary', '2026-10-06', 'AVAILABLE'),
    ('PID-2026-003', 'City Central Hospital', 'ECG report', '2026-10-30', 'AVAILABLE'),
]


def main():
    if os.path.exists(DATABASE):
        os.remove(DATABASE)
        print('Old database removed.')
    init_db()

    conn = get_db()
    for p in PATIENTS:
        cols = ', '.join(p.keys())
        marks = ', '.join('?' for _ in p)
        conn.execute(f'INSERT INTO patients ({cols}) VALUES ({marks})', tuple(p.values()))
    conn.executemany(
        'INSERT INTO reports (patient_id, hospital_name, report_type, report_date, status) '
        'VALUES (?, ?, ?, ?, ?)',
        REPORTS
    )
    conn.commit()
    conn.close()
    print(f'Database ready: {len(PATIENTS)} demo patients, {len(REPORTS)} reports.')


if __name__ == '__main__':
    main()