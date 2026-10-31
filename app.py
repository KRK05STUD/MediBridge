import os
import sqlite3
from flask import Flask, render_template, jsonify, request
from datetime import date

def is_valid_date(value):
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'medibridge.db')
SCHEMA_FILE = os.path.join(BASE_DIR, 'schema.sql')

HOSPITALS = ['City Central Hospital', 'Metro Medical Centre']
STATUSES = ['Admit', 'Discharge', 'Transfer']
REQUIRED_PATIENT_FIELDS = [
    'hospital_name', 'patient_id', 'full_name', 'dob', 'gender', 'mobile_number',
    'address', 'hospital_department', 'admission_date', 'admission_time',
    'doctor_name', 'reason', 'patient_status'
]

app = Flask(__name__)


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    """Creates all tables from schema.sql (empty)."""
    conn = get_db()
    with open(SCHEMA_FILE, 'r', encoding='utf-8') as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


def patient_exists(conn, patient_id):
    return conn.execute(
        'SELECT 1 FROM patients WHERE patient_id = ?', (patient_id,)
    ).fetchone() is not None


def has_approved_consent(conn, patient_id, hospital):
    return conn.execute(
        "SELECT 1 FROM consents WHERE patient_id = ? AND requesting_hospital = ? "
        "AND status = 'APPROVED' LIMIT 1",
        (patient_id, hospital)
    ).fetchone() is not None


# ---------- Pages ----------

@app.route('/')
def index():
    return render_template('index.html', hospitals=HOSPITALS, statuses=STATUSES)


@app.route('/patient/<patient_id>')
def patient_page(patient_id):
    return render_template('timeline.html', patient_id=patient_id, hospitals=HOSPITALS)


# ---------- Patients ----------

@app.route('/api/patients', methods=['GET'])
def get_patients():
    conn = get_db()
    rows = conn.execute('SELECT * FROM patients ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/patients/<patient_id>', methods=['GET'])
def get_patient(patient_id):
    conn = get_db()
    row = conn.execute(
        'SELECT * FROM patients WHERE patient_id = ?', (patient_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return jsonify({'error': 'Patient not found'}), 404
    return jsonify(dict(row))


@app.route('/api/patients', methods=['POST'])
def add_patient():
    data = request.get_json(silent=True) or {}

    missing = [f for f in REQUIRED_PATIENT_FIELDS if not data.get(f)]
    if missing:
        return jsonify({'error': 'Missing fields: ' + ', '.join(missing)}), 400
    if data['hospital_name'] not in HOSPITALS:
        return jsonify({'error': 'Unknown hospital'}), 400
    if data['patient_status'] not in STATUSES:
        return jsonify({'error': 'Invalid patient status'}), 400
    if data['patient_status'] == 'Discharge' and not data.get('discharge_date'):
        return jsonify({'error': 'Discharge date is required for Discharge status'}), 400
    if not (is_valid_date(data['dob']) and is_valid_date(data['admission_date'])):
        return jsonify({'error': 'Dates must be in YYYY-MM-DD format'}), 400
    if data.get('discharge_date') and not is_valid_date(data['discharge_date']):
        return jsonify({'error': 'Discharge date is invalid'}), 400
    if data.get('discharge_date') and data['discharge_date'] < data['admission_date']:
        return jsonify({'error': 'Discharge date cannot be before admission date'}), 400

    conn = get_db()
    try:
        conn.execute(
            '''INSERT INTO patients (
                hospital_name, patient_id, full_name, dob, gender, mobile_number, address,
                hospital_department, admission_date, admission_time, doctor_name,
                reason, patient_status, discharge_date, remarks, feedback
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                data['hospital_name'], data['patient_id'], data['full_name'], data['dob'],
                data['gender'], data['mobile_number'], data['address'],
                data['hospital_department'], data['admission_date'], data['admission_time'],
                data['doctor_name'], data['reason'], data['patient_status'],
                data.get('discharge_date') or None, data.get('remarks'), data.get('feedback')
            )
        )
        conn.commit()
        return jsonify({'status': 'Patient saved.'}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error': f"Patient ID '{data['patient_id']}' already exists."}), 400
    finally:
        conn.close()


# ---------- Reports ----------

@app.route('/api/patients/<patient_id>/reports', methods=['GET'])
def get_reports(patient_id):
    # viewer = hospital name viewing the record; empty = the patient viewing their own record
    viewer = request.args.get('viewer', '').strip()
    conn = get_db()
    if not patient_exists(conn, patient_id):
        conn.close()
        return jsonify({'error': 'Patient not found'}), 404

    rows = conn.execute(
        'SELECT * FROM reports WHERE patient_id = ? ORDER BY report_date DESC, report_id DESC',
        (patient_id,)
    ).fetchall()
    approved = bool(viewer) and has_approved_consent(conn, patient_id, viewer)
    conn.close()

    reports = []
    for row in rows:
        item = dict(row)
        # A hospital only sees another hospital's reports after the patient approves
        if viewer and item['hospital_name'] != viewer and not approved:
            item['report_type'] = 'Hidden until patient approves'
            item['status'] = 'LOCKED'
        reports.append(item)
    return jsonify(reports)


# ---------- Consents ----------

@app.route('/api/patients/<patient_id>/consents', methods=['GET'])
def get_consents(patient_id):
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM consents WHERE patient_id = ? ORDER BY consent_id DESC', (patient_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/consents', methods=['POST'])
def request_consent():
    data = request.get_json(silent=True) or {}
    patient_id = (data.get('patient_id') or '').strip()
    hospital = (data.get('requesting_hospital') or '').strip()
    if not patient_id or hospital not in HOSPITALS:
        return jsonify({'error': 'patient_id and a valid requesting_hospital are required'}), 400

    conn = get_db()
    try:
        if not patient_exists(conn, patient_id):
            return jsonify({'error': 'Patient not found'}), 404
        pending = conn.execute(
            "SELECT consent_id FROM consents WHERE patient_id = ? "
            "AND requesting_hospital = ? AND status = 'PENDING'",
            (patient_id, hospital)
        ).fetchone()
        if pending:
            return jsonify({'status': 'Request already pending.'}), 200
        cur = conn.execute(
            "INSERT INTO consents (patient_id, requesting_hospital, status) "
            "VALUES (?, ?, 'PENDING')",
            (patient_id, hospital)
        )
        conn.commit()
        return jsonify({'status': 'Request sent to patient.', 'consent_id': cur.lastrowid}), 201
    finally:
        conn.close()


@app.route('/api/consents/<int:consent_id>/respond', methods=['POST'])
def respond_consent(consent_id):
    data = request.get_json(silent=True) or {}
    decision = data.get('decision')
    if decision not in ('APPROVED', 'DENIED'):
        return jsonify({'error': 'decision must be APPROVED or DENIED'}), 400

    conn = get_db()
    try:
        cur = conn.execute(
            "UPDATE consents SET status = ? WHERE consent_id = ? AND status = 'PENDING'",
            (decision, consent_id)
        )
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({'error': 'No pending request with that ID.'}), 404
        return jsonify({'status': f'Request {decision.lower()}.'})
    finally:
        conn.close()

@app.route('/api/reports', methods=['GET'])
def all_reports():
    """Report metadata for the staff Reports view. File contents are not included."""
    conn = get_db()
    rows = conn.execute('''
        SELECT r.report_id, r.patient_id, p.full_name, r.hospital_name,
               r.report_type, r.report_date, r.status
        FROM reports r
        JOIN patients p ON p.patient_id = r.patient_id
        ORDER BY r.report_date DESC, r.report_id DESC
    ''').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        init_db()
        print('Created an empty medibridge.db. Run "python seed.py" to load demo data.')
    app.run(debug=False)