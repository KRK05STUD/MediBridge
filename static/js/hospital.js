const state = { patientId: null, number: null };

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[c]
));

const initials = name => name.split(' ').filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('');

document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('aadhaar');
    input.addEventListener('input', () => {
        const digits = input.value.replace(/\D/g, '').slice(0, 12);
        input.value = digits.replace(/(\d{4})(?=\d)/g, '$1 ');
    });

    document.getElementById('lookupForm').addEventListener('submit', onLookup);

    document.querySelectorAll('.menu a[data-view]').forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault();
            showView(link.dataset.view, link);
        });
    });

    showView('find', document.querySelector('.menu a[data-view="find"]'));
});

function showView(view, link) {
    document.querySelectorAll('.menu a[data-view]').forEach(a => a.classList.toggle('active', a === link));
    document.getElementById('viewFind').style.display = view === 'find' ? '' : 'none';
    document.getElementById('viewPermissions').style.display = view === 'permissions' ? '' : 'none';
    document.getElementById('pageTitle').textContent = view === 'find' ? 'Find patient' : 'Permissions';
    if (view === 'permissions') loadPermissions();
}

function toast(message, type = 'info') {
    let stack = document.querySelector('.toast-stack');
    if (!stack) {
        stack = document.createElement('div');
        stack.className = 'toast-stack';
        document.body.appendChild(stack);
    }
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = message;
    stack.appendChild(el);
    setTimeout(() => el.remove(), 3500);
}

// Single place for API calls: handles login expiry and shows errors
async function api(url, body) {
    const opts = body === undefined
        ? {}
        : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
    let res;
    try {
        res = await fetch(url, opts);
    } catch (err) {
        toast('Could not reach the server.', 'error');
        return null;
    }
    if (res.status === 401) {
        location.href = '/login';
        return null;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        toast(data.error || 'Something went wrong.', 'error');
        return null;
    }
    return data;
}

async function onLookup(e) {
    e.preventDefault();
    const number = document.getElementById('aadhaar').value.replace(/\s/g, '');
    if (!/^[2-9]\d{11}$/.test(number)) {
        toast('Enter a valid 12-digit Aadhaar number.', 'error');
        return;
    }
    state.number = number;
    const data = await api('/api/hospital/lookup', { aadhaar: number });
    if (data) renderPatient(data);
}

function renderPatient(d) {
    state.patientId = d.patient_id;
    const approved = d.granted_scopes.includes('LAB') || d.granted_scopes.includes('ALL');
    const pending = d.access && d.access.status === 'PENDING';

    let accessPill, action;
    if (d.is_home_hospital) {
        accessPill = '<span class="pill info">Registered at your hospital</span>';
        action = '<button class="btn btn-primary" onclick="loadReports()">View lab reports</button>';
    } else if (approved) {
        accessPill = '<span class="pill ok">Lab access approved</span>';
        action = '<button class="btn btn-primary" onclick="loadReports()">View lab reports</button>';
    } else if (pending) {
        accessPill = '<span class="pill warn">Request pending</span>';
        action = '<span class="muted-sm">Waiting for the patient to approve.</span>';
    } else {
        accessPill = '<span class="pill">No access</span>';
        action = '<button class="btn btn-primary" onclick="requestLab()">Request lab reports</button>';
    }

    document.getElementById('patientResult').innerHTML = `
        <div class="card result-card">
            <div class="person">
                <div class="avatar lg" style="background:linear-gradient(135deg,#0ea5e9,#6366f1)">${esc(initials(d.full_name))}</div>
                <div>
                    <h2>${esc(d.full_name)}</h2>
                    <span class="muted-sm">${esc(d.patient_id)} · ${d.age} yrs · ${esc(d.gender)}</span>
                </div>
            </div>
            <div class="result-grid">
                <div><span class="kpi-label">Aadhaar</span><div>${esc(d.aadhaar_masked)}</div></div>
                <div><span class="kpi-label">Home hospital</span><div>${esc(d.home_hospital)}</div></div>
                <div><span class="kpi-label">Your access</span><div>${accessPill}</div></div>
            </div>
            <div class="row-actions">${action}</div>
        </div>
        <div id="reportsBox"></div>`;
    document.getElementById('reportsBox').innerHTML = '';
}

async function requestLab() {
    const r = await api('/api/hospital/requests', { patient_id: state.patientId, scope: 'LAB' });
    if (!r) return;
    toast(r.status, 'success');
    const d = await api('/api/hospital/lookup', { aadhaar: state.number });
    if (d) renderPatient(d);
}

async function loadReports() {
    const box = document.getElementById('reportsBox');
    box.innerHTML = '<div class="card"><div class="skeleton"></div><div class="skeleton" style="width:70%"></div></div>';
    const data = await api(`/api/hospital/patients/${encodeURIComponent(state.patientId)}/reports?category=LAB`);
    if (!data) { box.innerHTML = ''; return; }

    const rows = data.reports.map(r => `
        <div class="report-card">
            <div>
                <strong>${esc(r.report_type)}</strong>
                <div class="report-meta">${esc(r.hospital_name)} · ${esc(r.report_date)}</div>
            </div>
            <span class="pill info">${esc(r.category)}</span>
        </div>`).join('');

    const hiddenNote = data.hidden_count ? ` · ${data.hidden_count} hidden by consent` : '';
    box.innerHTML = `
        <section class="card" style="margin-top:1.25rem">
            <div class="card-head">
                <h3>Lab reports</h3>
                <span class="muted-sm">${data.reports.length} shown${hiddenNote}</span>
            </div>
            ${rows || '<p class="empty-note">No lab reports available to you.</p>'}
        </section>`;
}

async function loadPermissions() {
    const rows = await api('/api/hospital/permissions');
    if (!rows) return;
    const body = document.getElementById('permBody');
    if (!rows.length) {
        body.innerHTML = '<tr><td colspan="6" class="empty-placeholder">No requests yet. Look up a patient to request lab reports.</td></tr>';
        return;
    }
    body.innerHTML = rows.map(r => `
        <tr>
            <td>
                <strong>${esc(r.full_name)}</strong><br>
                <span class="muted-sm">${esc(r.patient_id)} · ${esc(r.home_hospital)}</span>
            </td>
            <td class="muted-sm">${esc(r.aadhaar_masked)}</td>
            <td><span class="pill info">${esc(r.scope)}</span></td>
            <td>${statusPill(r.status)}</td>
            <td class="muted-sm">${esc(r.created_at)}</td>
            <td>${r.status === 'PENDING'
                ? `<button class="btn btn-secondary btn-small" onclick="cancelRequest(${r.consent_id})">Cancel</button>`
                : ''}</td>
        </tr>`).join('');
}

function statusPill(status) {
    const cls = { APPROVED: 'ok', PENDING: 'warn', DENIED: 'lock' }[status] || '';
    return `<span class="pill ${cls}">${esc(status)}</span>`;
}

async function cancelRequest(consentId) {
    const r = await api(`/api/hospital/requests/${consentId}/cancel`, {});
    if (r) {
        toast('Request cancelled.', 'success');
        loadPermissions();
    }
}