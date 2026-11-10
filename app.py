import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from datetime import date
from functools import wraps

from flask import (
    Flask, jsonify, redirect, render_template, request,
    send_from_directory, session, url_for
)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'medibridge.db')
SCHEMA_FILE = os.path.join(BASE_DIR, 'schema.sql')
# Outside static/ on purpose: files are only reachable through the access-checked route
UPLOAD_DIR = os.path.join(BASE_DIR, 'private_uploads')

HOSPITALS = ['City Central Hospital', 'Metro Medical Centre']
STATUSES = ['Admit', 'Discharge', 'Transfer']
CONSENT_SCOPES = ['LAB', 'ALL']
REPORT_CATEGORIES = ['LAB', 'DIAGNOSTIC', 'IMAGING', 'PRESCRIPTION', 'SUMMARY']
REQUIRED_PATIENT_FIELDS = [
    'hospital_name', 'patient_id', 'full_name', 'dob', 'gender', 'mobile_number',
    'address', 'hospital_department', 'admission_date', 'admission_time',
    'doctor_name', 'reason', 'patient_status'
]
# extension -> (required file signature, MIME type)
ALLOWED_FILES = {
    'pdf': (b'%PDF', 'application/pdf'),
    'png': (b'\x89PNG', 'image/png'),
    'jpg': (b'\xff\xd8\xff', 'image/jpeg'),
    'jpeg': (b'\xff\xd8\xff', 'image/jpeg'),
}
MIN_PASSWORD_LENGTH = 8

# Secret for hashing Aadhaar numbers. Set MEDIBRIDGE_PEPPER in any real environment.
AADHAAR_PEPPER = os.environ.get('MEDIBRIDGE_PEPPER', 'dev-only-pepper-change-me')

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get('MEDIBRIDGE_SECRET') or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,  # 5 MB upload limit
)


# ---------- Helpers ----------

def is_valid_date(value):
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def age_from_dob(dob_str):
    birth = date.fromisoformat(dob_str)
    today = date.today()
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    conn = get_db()
    with open(SCHEMA_FILE, 'r', encoding='utf-8') as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


def hash_aadhaar(number):
    return hmac.new(AADHAAR_PEPPER.encode(), number.encode(), hashlib.sha256).hexdigest()


def is_valid_aadhaar(number):
    # Demo format check only: 12 digits, first digit 2-9. Not a checksum or UIDAI verification.
    return bool(re.fullmatch(r'[2-9]\d{11}', number or ''))


def mask_aadhaar(last4):
    return f'XXXX XXXX {last4}' if last4 else '—'


def current_hospital():
    return session.get('hospital')


def current_patient():
    return session.get('patient_id')


def login_required(view):
    """Hospital staff only."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_hospital():
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Please log in as hospital staff.'}), 401
            return redirect(url_for('login_page', role='hospital'))
        return view(*args, **kwargs)
    return wrapper


def patient_required(view):
    """Patients only."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_patient():
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Please log in as a patient.'}), 401
            return redirect(url_for('login_page', role='patient'))
        return view(*args, **kwargs)
    return wrapper


def audit(conn, actor, action, patient_id=None, detail=None):
    conn.execute(
        'INSERT INTO audit_log (actor, action, patient_id, detail) VALUES (?, ?, ?, ?)',
        (actor, action, patient_id, detail)
    )


def patient_exists(conn, patient_id):
    return conn.execute(
        'SELECT 1 FROM patients WHERE patient_id = ?', (patient_id,)
    ).fetchone() is not None


def granted_scopes(conn, patient_id, hospital):
    """Scopes the patient has currently approved for this hospital."""
    rows = conn.execute(
        "SELECT scope FROM consents WHERE patient_id = ? AND requesting_hospital = ? "
        "AND status = 'APPROVED'",
        (patient_id, hospital)
    ).fetchall()
    return {r['scope'] for r in rows}


def can_see(report, viewer, scopes):
    """The access rule. viewer=None means the patient's own view."""
    if not viewer:
        return True
    if report['hospital_name'] == viewer:
        return True
    if 'ALL' in scopes:
        return True
    return report['category'] == 'LAB' and 'LAB' in scopes


def patient_out(row):
    data = dict(row)
    data.pop('aadhaar_hash', None)
    return data


def report_out(row):
    """Report for the browser: never includes the stored file name."""
    data = dict(row)
    data['has_file'] = bool(data.pop('file_path', None))
    data.pop('file_sha256', None)
    data.pop('mime_type', None)
    return data


# ---------- Pages ----------

@app.route('/')
@login_required
def index():
    return render_template('index.html', hospitals=HOSPITALS, statuses=STATUSES)


@app.route('/login')
def login_page():
    if current_hospital():
        return redirect(url_for('index'))
    if current_patient():
        return redirect(url_for('patient_page'))
    role = request.args.get('role', 'hospital')
    return render_template('login.html', role=role if role in ('hospital', 'patient') else 'hospital')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))


@app.route('/hospital')
@login_required
def hospital_portal():
    return render_template('hospital.html', hospital=current_hospital())


@app.route('/my')
@patient_required
def patient_page():
    return render_template('patient.html', hospitals=HOSPITALS)


@app.route('/patient/<patient_id>')
def old_timeline(patient_id):
    # The old public timeline is retired. Send each user to their own area.
    if current_hospital():
        return redirect(url_for('hospital_portal'))
    if current_patient():
        return redirect(url_for('patient_page'))
    return redirect(url_for('login_page', role='patient'))


# ---------- Logins ----------

@app.route('/api/auth/hospital/login', methods=['POST'])
def api_hospital_login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip().lower()
    password = data.get('password') or ''
    conn = get_db()
    row = conn.execute(
        'SELECT hospital_name, password_hash FROM hospitals WHERE username = ?', (username,)
    ).fetchone()
    if row and check_password_hash(row['password_hash'], password):
        session.clear()
        session['hospital'] = row['hospital_name']
        audit(conn, f"hospital:{row['hospital_name']}", 'LOGIN')
        conn.commit()
        conn.close()
        return jsonify({'hospital': row['hospital_name']})
    audit(conn, None, 'LOGIN_FAILED', None, f'hospital username: {username}')
    conn.commit()
    conn.close()
    return jsonify({'error': 'Invalid username or password.'}), 401


@app.route('/api/auth/patient/login', methods=['POST'])
def api_patient_login():
    data = request.get_json(silent=True) or {}
    pid = (data.get('patient_id') or '').strip()
    password = data.get('password') or ''
    conn = get_db()
    row = conn.execute(
        'SELECT password_hash FROM patient_accounts WHERE patient_id = ?', (pid,)
    ).fetchone()
    if row and check_password_hash(row['password_hash'], password):
        session.clear()
        session['patient_id'] = pid
        audit(conn, f'patient:{pid}', 'LOGIN', pid)
        conn.commit()
        conn.close()
        return jsonify({'patient_id': pid})
    audit(conn, None, 'LOGIN_FAILED', pid, 'patient')
    conn.commit()
    conn.close()
    return jsonify({'error': 'Invalid Patient ID or password.'}), 401


# ---------- Hospital: patients and reports ----------

@app.route('/api/patients', methods=['GET'])
@login_required
def get_patients():
    conn = get_db()
    rows = conn.execute('SELECT * FROM patients ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([patient_out(r) for r in rows])


@app.route('/api/patients/<patient_id>', methods=['GET'])
@login_required
def get_patient(patient_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM patients WHERE patient_id = ?', (patient_id,)).fetchone()
    conn.close()
    if row is None:
        return jsonify({'error': 'Patient not found'}), 404
    return jsonify(patient_out(row))


@app.route('/api/patients', methods=['POST'])
@login_required
def add_patient():
    hospital = current_hospital()
    data = request.get_json(silent=True) or {}

    missing = [f for f in REQUIRED_PATIENT_FIELDS if not data.get(f)]
    if missing:
        return jsonify({'error': 'Missing fields: ' + ', '.join(missing)}), 400
    if data['hospital_name'] not in HOSPITALS:
        return jsonify({'error': 'Unknown hospital'}), 400
    if data['hospital_name'] != hospital:
        return jsonify({'error': 'You can only register patients at your own hospital.'}), 403
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

    aadhaar = re.sub(r'\s', '', data.get('aadhaar') or '')
    aadhaar_hash = aadhaar_last4 = None
    if aadhaar:
        if not is_valid_aadhaar(aadhaar):
            return jsonify({'error': 'Aadhaar must be 12 digits.'}), 400
        aadhaar_hash = hash_aadhaar(aadhaar)
        aadhaar_last4 = aadhaar[-4:]

    conn = get_db()
    try:
        conn.execute(
            '''INSERT INTO patients (
                hospital_name, patient_id, full_name, dob, gender, mobile_number, address,
                hospital_department, admission_date, admission_time, doctor_name,
                reason, patient_status, discharge_date, remarks, feedback,
                aadhaar_hash, aadhaar_last4
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                data['hospital_name'], data['patient_id'], data['full_name'], data['dob'],
                data['gender'], data['mobile_number'], data['address'],
                data['hospital_department'], data['admission_date'], data['admission_time'],
                data['doctor_name'], data['reason'], data['patient_status'],
                data.get('discharge_date') or None, data.get('remarks'), data.get('feedback'),
                aadhaar_hash, aadhaar_last4
            )
        )
        audit(conn, f'hospital:{hospital}', 'REGISTER_PATIENT', data['patient_id'])
        conn.commit()
        return jsonify({'status': 'Patient saved.'}), 201
    except sqlite3.IntegrityError as e:
        if 'aadhaar_hash' in str(e):
            return jsonify({'error': 'This Aadhaar number is already registered.'}), 400
        return jsonify({'error': f"Patient ID '{data['patient_id']}' already exists."}), 400
    finally:
        conn.close()


@app.route('/api/reports', methods=['GET'])
@login_required
def all_reports():
    conn = get_db()
    rows = conn.execute('''
        SELECT r.report_id, r.patient_id, p.full_name, r.hospital_name,
               r.report_type, r.category, r.report_date, r.status
        FROM reports r
        JOIN patients p ON p.patient_id = r.patient_id
        ORDER BY r.report_date DESC, r.report_id DESC
    ''').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/hospital/patients/<patient_id>/reports', methods=['GET'])
@login_required
def hospital_patient_reports(patient_id):
    hospital = current_hospital()
    category = (request.args.get('category') or '').upper()
    conn = get_db()
    if not patient_exists(conn, patient_id):
        conn.close()
        return jsonify({'error': 'Patient not found'}), 404

    rows = conn.execute(
        'SELECT * FROM reports WHERE patient_id = ? ORDER BY report_date DESC, report_id DESC',
        (patient_id,)
    ).fetchall()
    scopes = granted_scopes(conn, patient_id, hospital)

    visible, hidden = [], 0
    for row in rows:
        item = dict(row)
        if category and item['category'] != category:
            continue
        if can_see(item, hospital, scopes):
            visible.append(report_out(row))
        else:
            hidden += 1

    audit(conn, f'hospital:{hospital}', 'VIEW_REPORTS', patient_id,
          f'{len(visible)} shown, {hidden} hidden, filter={category or "ALL"}')
    conn.commit()
    conn.close()
    return jsonify({'reports': visible, 'hidden_count': hidden})


@app.route('/api/hospital/patients/<patient_id>/reports', methods=['POST'])
@login_required
def upload_report(patient_id):
    hospital = current_hospital()
    upload = request.files.get('file')
    report_type = (request.form.get('report_type') or '').strip()
    category = (request.form.get('category') or '').upper()
    report_date = (request.form.get('report_date') or '').strip()

    if upload is None or not upload.filename:
        return jsonify({'error': 'Choose a file to upload.'}), 400
    if not report_type or category not in REPORT_CATEGORIES or not is_valid_date(report_date):
        return jsonify({'error': 'Report name, category and date are required.'}), 400

    ext = upload.filename.rsplit('.', 1)[-1].lower() if '.' in upload.filename else ''
    if ext not in ALLOWED_FILES:
        return jsonify({'error': 'Only PDF, PNG and JPG files are allowed.'}), 400
    content = upload.read()
    signature, mime = ALLOWED_FILES[ext]
    if not content.startswith(signature):
        return jsonify({'error': 'The file content does not match its extension.'}), 400

    conn = get_db()
    try:
        row = conn.execute(
            'SELECT hospital_name FROM patients WHERE patient_id = ?', (patient_id,)
        ).fetchone()
        if row is None:
            return jsonify({'error': 'Patient not found'}), 404
        if row['hospital_name'] != hospital:
            return jsonify({'error': 'Only the home hospital can upload reports for this patient.'}), 403

        os.makedirs(UPLOAD_DIR, exist_ok=True)
        stored = f'{secrets.token_hex(16)}.{ext}'
        with open(os.path.join(UPLOAD_DIR, stored), 'wb') as f:
            f.write(content)

        cur = conn.execute(
            "INSERT INTO reports (patient_id, hospital_name, report_type, category, report_date, "
            "status, file_path, file_sha256, mime_type) "
            "VALUES (?, ?, ?, ?, ?, 'AVAILABLE', ?, ?, ?)",
            (patient_id, hospital, report_type, category, report_date,
             stored, hashlib.sha256(content).hexdigest(), mime)
        )
        audit(conn, f'hospital:{hospital}', 'UPLOAD_REPORT', patient_id, str(cur.lastrowid))
        conn.commit()
        return jsonify({'report_id': cur.lastrowid, 'status': 'Report uploaded.'}), 201
    finally:
        conn.close()


@app.route('/api/hospital/patients/<patient_id>/account', methods=['POST'])
@login_required
def create_patient_account(patient_id):
    hospital = current_hospital()
    password = (request.get_json(silent=True) or {}).get('password') or ''
    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({'error': f'Password must be at least {MIN_PASSWORD_LENGTH} characters.'}), 400

    conn = get_db()
    try:
        row = conn.execute(
            'SELECT hospital_name FROM patients WHERE patient_id = ?', (patient_id,)
        ).fetchone()
        if row is None:
            return jsonify({'error': 'Patient not found'}), 404
        if row['hospital_name'] != hospital:
            return jsonify({'error': 'Only the home hospital can create a login for this patient.'}), 403
        exists = conn.execute(
            'SELECT 1 FROM patient_accounts WHERE patient_id = ?', (patient_id,)
        ).fetchone()
        if exists:
            return jsonify({'error': 'This patient already has a login.'}), 400

        conn.execute(
            'INSERT INTO patient_accounts (patient_id, password_hash) VALUES (?, ?)',
            (patient_id, generate_password_hash(password))
        )
        audit(conn, f'hospital:{hospital}', 'CREATE_PATIENT_LOGIN', patient_id)
        conn.commit()
        return jsonify({'status': f'Patient login created. Patient ID: {patient_id}'}), 201
    finally:
        conn.close()


# ---------- Hospital: Aadhaar lookup, requests, permissions ----------

@app.route('/api/hospital/lookup', methods=['POST'])
@login_required
def hospital_lookup():
    hospital = current_hospital()
    data = request.get_json(silent=True) or {}
    number = re.sub(r'\s', '', data.get('aadhaar') or '')
    if not is_valid_aadhaar(number):
        return jsonify({'error': 'Enter a valid 12-digit Aadhaar number.'}), 400

    conn = get_db()
    row = conn.execute(
        'SELECT * FROM patients WHERE aadhaar_hash = ?', (hash_aadhaar(number),)
    ).fetchone()
    if row is None:
        audit(conn, f'hospital:{hospital}', 'LOOKUP_NOT_FOUND')
        conn.commit()
        conn.close()
        return jsonify({'error': 'No patient found for this Aadhaar number.'}), 404

    pid = row['patient_id']
    latest = conn.execute(
        'SELECT consent_id, scope, status FROM consents '
        'WHERE patient_id = ? AND requesting_hospital = ? ORDER BY consent_id DESC LIMIT 1',
        (pid, hospital)
    ).fetchone()
    scopes = granted_scopes(conn, pid, hospital)
    has_account = conn.execute(
        'SELECT 1 FROM patient_accounts WHERE patient_id = ?', (pid,)
    ).fetchone() is not None
    audit(conn, f'hospital:{hospital}', 'LOOKUP', pid)
    conn.commit()
    conn.close()

    return jsonify({
        'patient_id': pid,
        'full_name': row['full_name'],
        'age': age_from_dob(row['dob']),
        'gender': row['gender'],
        'home_hospital': row['hospital_name'],
        'is_home_hospital': row['hospital_name'] == hospital,
        'has_account': has_account,
        'aadhaar_masked': mask_aadhaar(row['aadhaar_last4']),
        'access': dict(latest) if latest else None,
        'granted_scopes': sorted(scopes),
    })


@app.route('/api/hospital/requests', methods=['POST'])
@login_required
def hospital_request():
    hospital = current_hospital()
    data = request.get_json(silent=True) or {}
    pid = (data.get('patient_id') or '').strip()
    scope = (data.get('scope') or 'LAB').upper()
    if scope not in CONSENT_SCOPES:
        return jsonify({'error': 'Invalid scope.'}), 400

    conn = get_db()
    try:
        row = conn.execute(
            'SELECT hospital_name FROM patients WHERE patient_id = ?', (pid,)
        ).fetchone()
        if row is None:
            return jsonify({'error': 'Patient not found'}), 404
        if row['hospital_name'] == hospital:
            return jsonify({'error': 'This patient is registered at your hospital.'}), 400

        scopes = granted_scopes(conn, pid, hospital)
        if 'ALL' in scopes or scope in scopes:
            return jsonify({'status': 'Access already approved.'}), 200

        pending = conn.execute(
            "SELECT consent_id FROM consents WHERE patient_id = ? AND requesting_hospital = ? "
            "AND scope = ? AND status = 'PENDING'",
            (pid, hospital, scope)
        ).fetchone()
        if pending:
            return jsonify({'status': 'Request already pending.',
                            'consent_id': pending['consent_id']}), 200

        cur = conn.execute(
            "INSERT INTO consents (patient_id, requesting_hospital, scope, status) "
            "VALUES (?, ?, ?, 'PENDING')",
            (pid, hospital, scope)
        )
        audit(conn, f'hospital:{hospital}', 'REQUEST_ACCESS', pid, scope)
        conn.commit()
        return jsonify({'status': 'Request sent to patient.', 'consent_id': cur.lastrowid}), 201
    finally:
        conn.close()


@app.route('/api/hospital/permissions', methods=['GET'])
@login_required
def hospital_permissions():
    hospital = current_hospital()
    conn = get_db()
    rows = conn.execute('''
        SELECT c.consent_id, c.patient_id, c.scope, c.status, c.created_at,
               p.full_name, p.aadhaar_last4, p.hospital_name AS home_hospital
        FROM consents c
        JOIN patients p ON p.patient_id = c.patient_id
        WHERE c.requesting_hospital = ?
        ORDER BY c.consent_id DESC
    ''', (hospital,)).fetchall()
    conn.close()

    out = []
    for r in rows:
        item = dict(r)
        item['aadhaar_masked'] = mask_aadhaar(item.pop('aadhaar_last4'))
        out.append(item)
    return jsonify(out)


@app.route('/api/hospital/requests/<int:consent_id>/cancel', methods=['POST'])
@login_required
def cancel_request(consent_id):
    hospital = current_hospital()
    conn = get_db()
    try:
        cur = conn.execute(
            "UPDATE consents SET status = 'CANCELLED' "
            "WHERE consent_id = ? AND requesting_hospital = ? AND status = 'PENDING'",
            (consent_id, hospital)
        )
        if cur.rowcount == 0:
            return jsonify({'error': 'No pending request of yours with that ID.'}), 404
        audit(conn, f'hospital:{hospital}', 'CANCEL_REQUEST', None, f'consent {consent_id}')
        conn.commit()
        return jsonify({'status': 'Request cancelled.'})
    finally:
        conn.close()


# ---------- Patient area ----------

@app.route('/api/patient/me', methods=['GET'])
@patient_required
def patient_me():
    conn = get_db()
    row = conn.execute(
        'SELECT patient_id, full_name, dob, gender, hospital_name, aadhaar_last4 '
        'FROM patients WHERE patient_id = ?', (current_patient(),)
    ).fetchone()
    conn.close()
    if row is None:
        return jsonify({'error': 'Patient not found'}), 404
    return jsonify({
        'patient_id': row['patient_id'],
        'full_name': row['full_name'],
        'age': age_from_dob(row['dob']),
        'gender': row['gender'],
        'home_hospital': row['hospital_name'],
        'aadhaar_masked': mask_aadhaar(row['aadhaar_last4']),
    })


@app.route('/api/patient/reports', methods=['GET'])
@patient_required
def patient_reports():
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM reports WHERE patient_id = ? ORDER BY report_date DESC, report_id DESC',
        (current_patient(),)
    ).fetchall()
    conn.close()
    return jsonify([report_out(r) for r in rows])


@app.route('/api/patient/shares', methods=['GET'])
@patient_required
def patient_shares():
    conn = get_db()
    rows = conn.execute(
        'SELECT consent_id, requesting_hospital, scope, status, created_at FROM consents '
        'WHERE patient_id = ? ORDER BY consent_id DESC', (current_patient(),)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/patient/shares', methods=['POST'])
@patient_required
def patient_share():
    """Patient shares directly with a hospital. If a matching request is pending, it is approved instead."""
    pid = current_patient()
    data = request.get_json(silent=True) or {}
    hospital = (data.get('hospital') or '').strip()
    scope = (data.get('scope') or 'LAB').upper()
    if hospital not in HOSPITALS:
        return jsonify({'error': 'Choose a valid hospital.'}), 400
    if scope not in CONSENT_SCOPES:
        return jsonify({'error': 'Invalid scope.'}), 400

    conn = get_db()
    try:
        pending = conn.execute(
            "SELECT consent_id FROM consents WHERE patient_id = ? AND requesting_hospital = ? "
            "AND scope = ? AND status = 'PENDING'",
            (pid, hospital, scope)
        ).fetchone()
        if pending:
            conn.execute("UPDATE consents SET status = 'APPROVED' WHERE consent_id = ?",
                         (pending['consent_id'],))
        else:
            conn.execute(
                "INSERT INTO consents (patient_id, requesting_hospital, scope, status) "
                "VALUES (?, ?, ?, 'APPROVED')",
                (pid, hospital, scope)
            )
        audit(conn, f'patient:{pid}', 'SHARE', pid, f'{hospital} ({scope})')
        conn.commit()
        return jsonify({'status': f'Shared with {hospital}.'}), 201
    finally:
        conn.close()


@app.route('/api/patient/requests/<int:consent_id>/respond', methods=['POST'])
@patient_required
def patient_respond(consent_id):
    pid = current_patient()
    decision = (request.get_json(silent=True) or {}).get('decision')
    if decision not in ('APPROVED', 'DENIED'):
        return jsonify({'error': 'decision must be APPROVED or DENIED'}), 400

    conn = get_db()
    try:
        cur = conn.execute(
            "UPDATE consents SET status = ? WHERE consent_id = ? AND patient_id = ? AND status = 'PENDING'",
            (decision, consent_id, pid)
        )
        if cur.rowcount == 0:
            return jsonify({'error': 'No pending request with that ID.'}), 404
        audit(conn, f'patient:{pid}', f'REQUEST_{decision}', pid, f'consent {consent_id}')
        conn.commit()
        return jsonify({'status': f'Request {decision.lower()}.'})
    finally:
        conn.close()


@app.route('/api/patient/shares/<int:consent_id>/revoke', methods=['POST'])
@patient_required
def patient_revoke(consent_id):
    pid = current_patient()
    conn = get_db()
    try:
        cur = conn.execute(
            "UPDATE consents SET status = 'REVOKED' "
            "WHERE consent_id = ? AND patient_id = ? AND status = 'APPROVED'",
            (consent_id, pid)
        )
        if cur.rowcount == 0:
            return jsonify({'error': 'No active sharing with that ID.'}), 404
        audit(conn, f'patient:{pid}', 'REVOKE', pid, f'consent {consent_id}')
        conn.commit()
        return jsonify({'status': 'Access revoked.'})
    finally:
        conn.close()


@app.route('/api/patient/password', methods=['POST'])
@patient_required
def patient_change_password():
    pid = current_patient()
    data = request.get_json(silent=True) or {}
    current = data.get('current') or ''
    new = data.get('new') or ''
    if len(new) < MIN_PASSWORD_LENGTH:
        return jsonify({'error': f'New password must be at least {MIN_PASSWORD_LENGTH} characters.'}), 400

    conn = get_db()
    try:
        row = conn.execute(
            'SELECT password_hash FROM patient_accounts WHERE patient_id = ?', (pid,)
        ).fetchone()
        if row is None or not check_password_hash(row['password_hash'], current):
            return jsonify({'error': 'Current password is incorrect.'}), 401
        conn.execute('UPDATE patient_accounts SET password_hash = ? WHERE patient_id = ?',
                     (generate_password_hash(new), pid))
        audit(conn, f'patient:{pid}', 'CHANGE_PASSWORD', pid)
        conn.commit()
        return jsonify({'status': 'Password changed.'})
    finally:
        conn.close()


# ---------- Files (access-checked) ----------

@app.route('/api/files/<int:report_id>')
def download_report(report_id):
    inline = request.args.get('inline') == '1'
    patient = current_patient()
    hospital = current_hospital()

    conn = get_db()
    row = conn.execute('SELECT * FROM reports WHERE report_id = ?', (report_id,)).fetchone()
    if row is None or not row['file_path']:
        conn.close()
        return jsonify({'error': 'File not found.'}), 404
    report = dict(row)

    actor = None
    if patient and patient == report['patient_id']:
        actor = f'patient:{patient}'
    elif hospital and can_see(report, hospital, granted_scopes(conn, report['patient_id'], hospital)):
        actor = f'hospital:{hospital}'

    if actor is None:
        conn.close()
        return jsonify({'error': 'You do not have access to this file.'}), 403

    audit(conn, actor, 'VIEW_FILE' if inline else 'DOWNLOAD_FILE', report['patient_id'], str(report_id))
    conn.commit()
    conn.close()

    ext = os.path.splitext(report['file_path'])[1]
    download_name = re.sub(r'[^A-Za-z0-9_-]+', '_', report['report_type']).strip('_') + ext
    return send_from_directory(
        UPLOAD_DIR, report['file_path'],
        mimetype=report['mime_type'],
        as_attachment=not inline,
        download_name=download_name,
    )


if __name__ == '__main__':
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    if not os.path.exists(DATABASE):
        init_db()
        print('Created an empty medibridge.db. Run "python seed.py" to load demo data.')
    app.run(debug=False)