const DEPARTMENTS = ['General Admission', 'Cardiology', 'Orthopedic', 'Emergency'];
const HOSPITALS = ['City Central Hospital', 'Metro Medical Centre'];
const AVATAR_COLORS = ['#0ea5e9', '#6366f1', '#ea580c', '#16a34a', '#db2777', '#7c3aed'];

let allPatients = [];
let activeFilter = 'All';
let charts = { dept: null, status: null, hospital: null };

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('patientForm').addEventListener('submit', handleFormSubmit);
    document.getElementById('patient_status').addEventListener('change', e => toggleDischargeField(e.target.value));
    document.getElementById('searchInput').addEventListener('input', renderTable);
    document.getElementById('filters').addEventListener('click', onFilterClick);
    document.getElementById('themeBtn').addEventListener('click', toggleTheme);
    document.querySelectorAll('.menu a[data-view]').forEach(link => link.addEventListener('click', onNavClick));
    document.addEventListener('keydown', onKeydown);

    syncThemeIcon();
    setupClock();
    toggleDischargeField(document.getElementById('patient_status').value);
    fetchPatientData();
});

/* ================= Helpers ================= */
function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function calculateAge(dobString) {
    const birth = new Date(dobString);
    const now = new Date();
    let age = now.getFullYear() - birth.getFullYear();
    const m = now.getMonth() - birth.getMonth();
    if (m < 0 || (m === 0 && now.getDate() < birth.getDate())) age--;
    return age >= 0 ? age : 0;
}

function initials(name) {
    return name.split(' ').filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('');
}

function avatarColor(seed) {
    let h = 0;
    for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

function avatarHtml(p, large = false) {
    return `<div class="avatar ${large ? 'lg' : ''}" style="background:linear-gradient(135deg, ${avatarColor(p.patient_id)}, ${avatarColor(p.full_name)})">${escapeHtml(initials(p.full_name))}</div>`;
}

function animateNumber(el, to) {
    const from = parseInt(el.textContent, 10) || 0;
    const start = performance.now();
    const duration = 700;
    const step = now => {
        const progress = Math.min((now - start) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(from + (to - from) * eased);
        if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
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

/* ================= Theme, clock, keyboard ================= */
function syncThemeIcon() {
    document.getElementById('themeBtn').textContent =
        document.documentElement.dataset.theme === 'dark' ? '☀️' : '🌙';
}

function toggleTheme() {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('mb-theme', next);
    syncThemeIcon();
    if (allPatients.length) renderCharts(allPatients); // redraw charts in the new palette
}

function setupClock() {
    const el = document.getElementById('clock');
    const tick = () => {
        el.textContent = new Date().toLocaleString('en-IN', {
            weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
        });
    };
    tick();
    setInterval(tick, 30000);
}

function onKeydown(e) {
    const modal = document.getElementById('patientModal');
    if (e.key === 'Escape') {
        if (modal.classList.contains('active')) toggleModal(false);
        return;
    }
    if (e.target.matches('input, select, textarea') || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === '/') { e.preventDefault(); document.getElementById('searchInput').focus(); }
    if (e.key.toLowerCase() === 'n') toggleModal(true);
}

/* ================= Navigation ================= */
function onNavClick(e) {
    e.preventDefault();
    const link = e.currentTarget;
    document.querySelectorAll('.menu a').forEach(a => a.classList.toggle('active', a === link));
    showView(link.dataset.view);
    if (link.dataset.scroll) {
        document.getElementById(link.dataset.scroll).scrollIntoView({ behavior: 'smooth' });
    }
}

function showView(view) {
    document.querySelectorAll('.dash').forEach(el => el.style.display = view === 'dashboard' ? '' : 'none');
    document.getElementById('reportsView').style.display = view === 'reports' ? 'block' : 'none';
    if (view === 'reports') loadReports();
}

function onFilterClick(e) {
    const chip = e.target.closest('.chip');
    if (!chip) return;
    document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    activeFilter = chip.dataset.filter;
    renderTable();
}

/* ================= Modal ================= */
function toggleModal(show) {
    const modal = document.getElementById('patientModal');
    modal.classList.toggle('active', show);
    if (show) {
        toggleDischargeField(document.getElementById('patient_status').value);
        setTimeout(() => document.getElementById('hospital_name').focus(), 50);
    } else {
        document.getElementById('patientForm').reset();
        toggleDischargeField(document.getElementById('patient_status').value);
    }
}

function toggleDischargeField(status) {
    const group = document.getElementById('discharge_date_group');
    const input = document.getElementById('discharge_date');
    const isDischarge = status === 'Discharge';
    group.style.opacity = isDischarge ? '1' : '0.35';
    input.disabled = !isDischarge;
    input.required = isDischarge;
    if (!isDischarge) input.value = '';
}

/* ================= Data ================= */
async function fetchPatientData() {
    try {
        const res = await fetch('/api/patients');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        allPatients = await res.json();
        updateMetrics(allPatients);
        renderActivity(allPatients);
        renderCharts(allPatients);
        renderTable();
    } catch (err) {
        console.error('Could not load patients:', err);
        toast('Could not load patients. Is the server running?', 'error');
    }
}

function updateMetrics(patients) {
    const count = s => patients.filter(p => p.patient_status === s).length;
    animateNumber(document.getElementById('m-total'), patients.length);
    animateNumber(document.getElementById('m-admit'), count('Admit'));
    animateNumber(document.getElementById('m-discharge'), count('Discharge'));
    animateNumber(document.getElementById('m-transfer'), count('Transfer'));
}

/* ================= Registry table ================= */
function renderTable() {
    const tbody = document.getElementById('patient-table-body');
    const query = document.getElementById('searchInput').value.trim().toLowerCase();

    const rows = allPatients.filter(p => {
        const matchesFilter = activeFilter === 'All' || p.patient_status === activeFilter;
        const haystack = `${p.full_name} ${p.patient_id} ${p.hospital_name}`.toLowerCase();
        return matchesFilter && (!query || haystack.includes(query));
    });

    if (rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="empty-placeholder">No patients match this view.</td></tr>`;
        return;
    }

    tbody.innerHTML = rows.map(p => `
        <tr>
            <td>
                <div class="person">
                    ${avatarHtml(p)}
                    <div>
                        <strong>${escapeHtml(p.full_name)}</strong><br>
                        <span class="muted-sm">${escapeHtml(p.patient_id)} · ${calculateAge(p.dob)} yrs · ${escapeHtml(p.gender)}</span>
                    </div>
                </div>
            </td>
            <td>
                ${escapeHtml(p.hospital_name)}<br>
                <span class="muted-sm">${escapeHtml(p.hospital_department)} · 🩺 ${escapeHtml(p.doctor_name)}</span>
            </td>
            <td><span class="muted-sm">📅 ${escapeHtml(p.admission_date)} · ${escapeHtml(p.admission_time)}</span></td>
            <td><span class="badge ${escapeHtml(p.patient_status.toLowerCase())}">${escapeHtml(p.patient_status)}</span></td>
            <td><span class="muted-sm">${p.discharge_date ? escapeHtml(p.discharge_date) : '—'}</span></td>
            <td><a class="view-link" href="/patient/${encodeURIComponent(p.patient_id)}">View timeline →</a></td>
        </tr>`).join('');
}

/* ================= Activity ================= */
function renderActivity(patients) {
    const list = document.getElementById('activityList');
    const recent = patients.slice(0, 5);
    if (!recent.length) {
        list.innerHTML = '<p class="empty-note">No admissions yet.</p>';
        return;
    }
    const dotColor = s => s === 'Discharge' ? 'var(--discharge)' : s === 'Transfer' ? 'var(--transfer)' : 'var(--admit)';
    list.innerHTML = recent.map(p => `
        <div class="activity-item">
            <span class="dot" style="background:${dotColor(p.patient_status)}"></span>
            <div class="main">
                <strong>${escapeHtml(p.full_name)}</strong> · ${escapeHtml(p.reason)}
                <small>${escapeHtml(p.hospital_name)} · ${escapeHtml(p.admission_date)}</small>
            </div>
            ${avatarHtml(p)}
        </div>`).join('');
}

/* ================= Charts ================= */
function gradientFor(canvas, from, to) {
    const ctx = canvas.getContext('2d');
    const g = ctx.createLinearGradient(0, 0, 0, canvas.height || 300);
    g.addColorStop(0, from);
    g.addColorStop(1, to);
    return g;
}

function renderCharts(patients) {
    if (typeof Chart === 'undefined') {
        console.warn('Chart.js not loaded. Check your internet connection.');
        return;
    }
    const muted = cssVar('--muted');
    const grid = cssVar('--border');
    Chart.defaults.color = muted;
    Chart.defaults.font.family = 'Inter, system-ui, sans-serif';
    Chart.defaults.font.size = 12;

    const deptCounts = DEPARTMENTS.map(d => patients.filter(p => p.hospital_department === d).length);
    const statusCounts = ['Admit', 'Discharge', 'Transfer'].map(s => patients.filter(p => p.patient_status === s).length);
    const hospitalCounts = HOSPITALS.map(h => patients.filter(p => p.hospital_name === h).length);

    Object.values(charts).forEach(c => c && c.destroy());

    const deptCanvas = document.getElementById('deptChart');
    charts.dept = new Chart(deptCanvas, {
        type: 'bar',
        data: {
            labels: DEPARTMENTS,
            datasets: [{
                label: 'Patients',
                data: deptCounts,
                backgroundColor: gradientFor(deptCanvas, '#38bdf8', '#6366f1'),
                hoverBackgroundColor: gradientFor(deptCanvas, '#7dd3fc', '#818cf8'),
                borderRadius: 10,
                maxBarThickness: 56
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 900, easing: 'easeOutQuart' },
            plugins: {
                legend: { display: false },
                tooltip: { backgroundColor: cssVar('--surface-solid'), titleColor: cssVar('--text'), bodyColor: cssVar('--text'), borderColor: grid, borderWidth: 1, padding: 10, cornerRadius: 10 }
            },
            scales: {
                y: { beginAtZero: true, ticks: { stepSize: 1 }, grid: { color: grid }, border: { display: false } },
                x: { grid: { display: false }, border: { display: false } }
            }
        }
    });

    charts.status = new Chart(document.getElementById('statusChart'), {
        type: 'doughnut',
        data: {
            labels: ['Admitted', 'Discharged', 'Transferred'],
            datasets: [{
                data: statusCounts,
                backgroundColor: ['#2563eb', '#16a34a', '#ea580c'],
                borderColor: cssVar('--surface-solid'),
                borderWidth: 4,
                hoverOffset: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            animation: { animateRotate: true, duration: 900 },
            plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, pointStyle: 'circle', padding: 16 } } }
        }
    });

    const hospitalCanvas = document.getElementById('hospitalChart');
    charts.hospital = new Chart(hospitalCanvas, {
        type: 'bar',
        data: {
            labels: HOSPITALS,
            datasets: [{
                label: 'Patients',
                data: hospitalCounts,
                backgroundColor: [gradientFor(hospitalCanvas, '#818cf8', '#6366f1'), gradientFor(hospitalCanvas, '#38bdf8', '#0ea5e9')],
                borderRadius: 10,
                maxBarThickness: 30
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 900, easing: 'easeOutQuart' },
            plugins: { legend: { display: false } },
            scales: {
                x: { beginAtZero: true, ticks: { stepSize: 1 }, grid: { color: grid }, border: { display: false } },
                y: { grid: { display: false }, border: { display: false } }
            }
        }
    });
}

/* ================= Reports view ================= */
async function loadReports() {
    const tbody = document.getElementById('reports-body');
    tbody.innerHTML = `<tr><td colspan="5"><div class="skeleton"></div><div class="skeleton" style="width:70%"></div></td></tr>`;
    try {
        const res = await fetch('/api/reports');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const reports = await res.json();
        tbody.innerHTML = reports.length ? reports.map(r => `
            <tr>
                <td>
                    <div class="person">
                        ${avatarHtml({ patient_id: r.patient_id, full_name: r.full_name }, false)}
                        <div><strong>${escapeHtml(r.full_name)}</strong><br>
                        <span class="muted-sm">${escapeHtml(r.patient_id)}</span></div>
                    </div>
                </td>
                <td>${escapeHtml(r.report_type)}</td>
                <td>${escapeHtml(r.hospital_name)}</td>
                <td><span class="muted-sm">${escapeHtml(r.report_date)}</span></td>
                <td><span class="pill ${r.status === 'AVAILABLE' ? 'ok' : 'warn'}">${escapeHtml(r.status)}</span></td>
            </tr>`).join('')
            : `<tr><td colspan="5" class="empty-placeholder">No reports yet.</td></tr>`;
    } catch (err) {
        console.error(err);
        tbody.innerHTML = `<tr><td colspan="5" class="empty-placeholder">Could not load reports.</td></tr>`;
    }
}

/* ================= Export ================= */
function exportCsv() {
    if (!allPatients.length) { toast('No patients to export yet', 'error'); return; }
    const rows = [['patient_id', 'full_name', 'hospital', 'department', 'status', 'admission_date']];
    allPatients.forEach(p => rows.push([
        p.patient_id, p.full_name, p.hospital_name, p.hospital_department, p.patient_status, p.admission_date
    ]));
    const csv = rows.map(r => r.map(v => `"${String(v ?? '').replace(/"/g, '""')}"`).join(',')).join('\n');
    const a = document.createElement('a');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    a.href = url;
    a.download = 'medibridge-patients.csv';
    a.click();
    URL.revokeObjectURL(url);
    toast('CSV exported', 'success');
}

/* ================= Registration form ================= */
async function handleFormSubmit(event) {
    event.preventDefault();
    const v = id => document.getElementById(id).value.trim();

    const payload = {
        hospital_name: v('hospital_name'),
        patient_id: v('patient_id'),
        full_name: v('full_name'),
        dob: v('dob'),
        gender: v('gender'),
        mobile_number: v('mobile_number'),
        address: v('address'),
        hospital_department: v('hospital_department'),
        doctor_name: v('doctor_name'),
        admission_date: v('admission_date'),
        admission_time: v('admission_time'),
        reason: v('reason'),
        patient_status: v('patient_status'),
        discharge_date: v('discharge_date') || null,
        remarks: v('remarks') || null,
        feedback: v('feedback') || null
    };

    try {
        const res = await fetch('/api/patients', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await res.json();
        if (res.ok) {
            toggleModal(false);
            toast('Patient saved', 'success');
            fetchPatientData();
        } else {
            toast(result.error || 'Could not save the patient.', 'error');
        }
    } catch (err) {
        console.error(err);
        toast('Could not reach the server. Is it running?', 'error');
    }
}