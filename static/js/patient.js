const SCOPE_LABEL = { LAB: 'Lab reports only', ALL: 'All records' };
const VIEWS = { records: 'My records', requests: 'Requests', sharing: 'Sharing', account: 'Account' };

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[c]
));

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.menu a[data-view]').forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault();
            showView(link.dataset.view, link);
        });
    });
    document.getElementById('shareForm').addEventListener('submit', shareWith);
    document.getElementById('pwForm').addEventListener('submit', changePassword);

    loadProfile();
    showView('records', document.querySelector('.menu a[data-view="records"]'));
});

function showView(view, link) {
    document.querySelectorAll('.menu a[data-view]').forEach(a => a.classList.toggle('active', a === link));
    Object.keys(VIEWS).forEach(v => {
        document.getElementById('view-' + v).style.display = v === view ? '' : 'none';
    });
    document.getElementById('pageTitle').textContent = VIEWS[view];
    if (view === 'records') loadRecords();
    if (view === 'requests' || view === 'sharing') loadShares();
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
        location.href = '/login?role=patient';
        return null;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        toast(data.error || 'Something went wrong.', 'error');
        return null;
    }
    return data;
}

async function loadProfile() {
    const p = await api('/api/patient/me');
    if (!p) return;
    document.getElementById('profileLine').textContent =
        `${p.full_name} · ${p.patient_id} · ${p.age} yrs · Home: ${p.home_hospital} · Aadhaar ${p.aadhaar_masked}`;
}

async function loadRecords() {
    const reports = await api('/api/patient/reports');
    if (!reports) return;
    const list = document.getElementById('recordList');
    if (!reports.length) {
        list.innerHTML = '<p class="empty-note">No records yet.</p>';
        return;
    }
    list.innerHTML = reports.map(r => `
        <div class="record-card">
            <div>
                <h4>${esc(r.report_type)}</h4>
                <span class="report-meta">${esc(r.hospital_name)} · ${esc(r.report_date)}</span>
            </div>
            <div><span class="pill info">${esc(r.category)}</span></div>
            <div class="record-actions">
                ${r.has_file
                    ? `<a class="btn btn-secondary btn-small" href="/api/files/${r.report_id}?inline=1" target="_blank">View</a>
                       <a class="btn btn-primary btn-small" href="/api/files/${r.report_id}">Download</a>`
                    : '<span class="pill">No file uploaded</span>'}
            </div>
        </div>`).join('');
}

async function loadShares() {
    const shares = await api('/api/patient/shares');
    if (!shares) return;
    renderRequests(shares.filter(s => s.status === 'PENDING'));
    renderGrants(shares);
}

function renderRequests(pending) {
    const box = document.getElementById('requestList');
    if (!pending.length) {
        box.innerHTML = '<div class="card-head"><h3>Requests</h3></div><p class="empty-note">No pending requests.</p>';
        return;
    }
    box.innerHTML = '<div class="card-head"><h3>Requests</h3></div>' + pending.map(s => `
        <div class="report-card" style="margin-bottom:.6rem">
            <div>
                <strong>${esc(s.requesting_hospital)}</strong>
                <div class="report-meta">Asks for: ${esc(SCOPE_LABEL[s.scope] || s.scope)} · ${esc(s.created_at)}</div>
            </div>
            <div class="record-actions">
                <button class="btn btn-primary btn-small" onclick="respond(${s.consent_id}, 'APPROVED')">Approve</button>
                <button class="btn btn-secondary btn-small" onclick="respond(${s.consent_id}, 'DENIED')">Deny</button>
            </div>
        </div>`).join('');
}

function renderGrants(shares) {
    const body = document.getElementById('grantsBody');
    if (!shares.length) {
        body.innerHTML = '<tr><td colspan="5" class="empty-placeholder">You have not shared your records yet.</td></tr>';
        return;
    }
    body.innerHTML = shares.map(s => `
        <tr>
            <td><strong>${esc(s.requesting_hospital)}</strong></td>
            <td><span class="pill info">${esc(SCOPE_LABEL[s.scope] || s.scope)}</span></td>
            <td>${statusPill(s.status)}</td>
            <td class="muted-sm">${esc(s.created_at)}</td>
            <td>${s.status === 'APPROVED'
                ? `<button class="btn btn-secondary btn-small" onclick="revoke(${s.consent_id})">Revoke</button>`
                : ''}</td>
        </tr>`).join('');
}

function statusPill(status) {
    const cls = { APPROVED: 'ok', PENDING: 'warn', DENIED: 'lock', REVOKED: 'lock' }[status] || '';
    return `<span class="pill ${cls}">${esc(status)}</span>`;
}

async function shareWith(e) {
    e.preventDefault();
    const hospital = document.getElementById('shareHospital').value;
    const scope = document.getElementById('shareScope').value;
    const r = await api('/api/patient/shares', { hospital, scope });
    if (r) {
        toast(r.status, 'success');
        loadShares();
    }
}

async function respond(consentId, decision) {
    const r = await api(`/api/patient/requests/${consentId}/respond`, { decision });
    if (r) {
        toast(r.status, 'success');
        loadShares();
    }
}

async function revoke(consentId) {
    const r = await api(`/api/patient/shares/${consentId}/revoke`, {});
    if (r) {
        toast(r.status, 'success');
        loadShares();
    }
}

async function changePassword(e) {
    e.preventDefault();
    const r = await api('/api/patient/password', {
        current: document.getElementById('pwCurrent').value,
        new: document.getElementById('pwNew').value
    });
    if (r) {
        toast(r.status, 'success');
        document.getElementById('pwForm').reset();
    }
}