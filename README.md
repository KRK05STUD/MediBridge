# MediBridge

MediBridge is a patient-centred prototype for finding and sharing medical reports across participating healthcare providers. Patients see one clear timeline of their reports. A receiving hospital can request access, and the reports stay locked until the patient approves the request.

> **Demo data only.** All patients, reports and doctors in this project are fictional. MediBridge is not connected to any real hospital, health system or patient record.

Built for the Hack for Social Cause track (Healthcare and Wellbeing) under VBYLD 2027.

---

## The problem

When a patient moves between hospitals, their history often gets lost. Reports are spread across labs, paper files and different portals. Patients and staff spend time searching for old results, a new clinician may not see relevant history in time, and some tests are repeated because the earlier result could not be found.

MediBridge is a prototype of one part of the solution: a patient-owned view of available reports, with consent-based sharing between hospitals.

## What it does

**Staff dashboard** (`/`)
- Metric cards for total, admitted, discharged and transferred patients, with animated counters.
- Charts for department load, status mix and hospital split.
- Recent admissions list.
- Searchable patient registry with status filters.
- Reports view listing report metadata across all hospitals.
- Registration form for new admissions.
- CSV export of the patient list.
- Dark and light themes, remembered in the browser.

**Patient timeline** (`/patient/<patient_id>`)
- Reports sorted by date, each marked Available, Link required or Locked.
- A "View as" selector that simulates the patient or a receiving hospital.
- Access requests from a hospital, which the patient can approve or deny.
- A consent history showing who asked, when, and the outcome.
- English and Telugu labels, switchable with one button.

**Consent rule**
A hospital only sees another hospital's reports after the patient approves its request. Until then, those reports show as locked.

## Tech stack

- **Backend:** Python, Flask
- **Database:** SQLite (a single file, `medibridge.db`)
- **Frontend:** HTML, CSS, vanilla JavaScript
- **Charts:** Chart.js (loaded from a CDN)
- **Fonts:** Inter (Google Fonts)

## Requirements

- Python 3.12 (recommended). Newer pre-release Python versions, such as 3.15, may fail to import Flask's dependencies.
- An internet connection for the charts and fonts. The app still runs without one, but the charts will not draw.
- Windows, macOS or Linux.

## Setup and run

Run these from the project folder.

**1. Create and activate a virtual environment**

Windows (PowerShell):
```
py -3.12 -m venv .venv
.venv\Scripts\activate
```

macOS or Linux:
```
python3.12 -m venv .venv
source .venv/bin/activate
```

**2. Install the dependencies**
```
python -m pip install -r requirements.txt
```

**3. Create the database with demo data**
```
python seed.py
```
This deletes any existing `medibridge.db` and loads three fictional patients and six reports. Run it again any time you want a clean demo.

**4. Start the app**
```
python app.py
```
Open **http://127.0.0.1:5000** in your browser. Press `Ctrl+C` in the terminal to stop the server.

On later runs, you only need to activate the environment (step 1) and run `python app.py`.

## Using the demo

1. **Dashboard:** check the counters, charts and registry. Try the search box, the status chips, the 🌙 theme button and the ⬇ CSV export.
2. **Keyboard shortcuts:** press `/` to search, `N` to add a patient, and `Esc` to close the form.
3. **Add a patient:** click **+ New Patient**, fill in the form and save. Use a new ID such as `PID-2026-010`.
4. **Open a timeline:** click **View timeline →** for Demo Patient A (`PID-2026-001`).
5. **Request access:** change **View as** to *Metro Medical Centre*. Some reports now show as locked, and the **Request access** button appears. Click it.
6. **Approve:** change **View as** back to *Patient (own record)*. Click **Approve** in the pending box.
7. **Check:** switch **View as** to *Metro Medical Centre* again. The reports from City Central Hospital are now visible, and the history shows *Approved*.
8. **Language:** click **తెలుగు** to switch the timeline labels to Telugu.

## Project structure

```
MediBridge/
├── app.py              Flask server, routes and database helpers
├── schema.sql          Table definitions and indexes
├── seed.py             Rebuilds the database with fictional demo data
├── requirements.txt    Python dependencies (Flask)
├── templates/
│   ├── index.html      Staff dashboard
│   └── timeline.html   Patient timeline and consent view
├── static/
│   ├── css/style.css   Styling, themes and layout
│   └── js/dashboard.js Dashboard logic, charts and form handling
├── LICENSE             MIT licence
├── .gitignore          Keeps .venv, the database and caches out of Git
└── README.md
```

## API reference

All endpoints return JSON.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/patients` | List all patients, newest first |
| POST | `/api/patients` | Register a new patient |
| GET | `/api/patients/<patient_id>` | Get one patient |
| GET | `/api/patients/<patient_id>/reports?viewer=<hospital>` | List reports. Pass a hospital name to apply the consent rule; leave it empty for the patient's own view |
| GET | `/api/patients/<patient_id>/consents` | Consent history for a patient |
| POST | `/api/consents` | A hospital requests access. Body: `patient_id`, `requesting_hospital` |
| POST | `/api/consents/<id>/respond` | Approve or deny a request. Body: `decision` = `APPROVED` or `DENIED` |
| GET | `/api/reports` | Report metadata across all patients (no file contents) |

Patient registration validates required fields, the hospital and status values, date formats, and that a discharge date is not before the admission date.

## Database

Three tables are defined in `schema.sql`:

- `patients`: one row per patient, including hospital, department, admission details and status.
- `reports`: report metadata linked to a patient, with the hospital that created it and an availability status.
- `consents`: access requests and their outcome (`PENDING`, `APPROVED`, `DENIED`).

Foreign keys are enforced, and indexes are created on the patient ID columns of `reports` and `consents`.

To inspect the data, install [DB Browser for SQLite](https://sqlitebrowser.org/) and open `medibridge.db`.

## Security and privacy: current limitations

This is a prototype built for a hackathon demo. It is not ready for real patient data, and the following are **not implemented**:

- **No login or authentication.** Anyone can open the dashboard and the API.
- **"View as" is a demo switch.** The role is chosen in the browser, so the server cannot verify who is asking.
- **Consent approval is not authenticated.** Any client can call the approve endpoint.
- **No encryption** at rest or in transit beyond what the browser provides when served over HTTPS.
- **No audit log** of who viewed or changed a record.
- **No real integration** with hospital systems.
- **Development server only.** Flask's built-in server is not designed for production traffic.

A real deployment would need patient and staff authentication with server-side authorisation on every request, encryption, audit logging, security testing, and compliance with applicable health-data rules.

## Notes

- The charts and fonts load from the internet. Without a connection, the page still works, but the charts stay blank.
- The Telugu labels were written as a prototype and should be checked by a native speaker before wider use. Hospital and doctor names stay in English.
- Report files are not uploaded in this version. Reports are metadata entries used to demonstrate the timeline and consent flow.

## Roadmap

- Authentication for patients and hospital staff, with role-based access enforced on the server.
- Secure report upload and storage, with encryption.
- Audit log of every access and approval.
- Pagination for large patient lists.
- Integration with compatible hospital record systems under the right permissions.
- Usability testing with patients and clinicians.

## Licence

Released under the MIT Licence. See [LICENSE](LICENSE).

