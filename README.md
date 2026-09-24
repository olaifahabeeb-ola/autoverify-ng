# AutoVerify NG

**A Vehicle Plate-to-Identity Verification System with Citizen Reporting**
HND Final Year Project — **Phase 4** (final polish for defense)

[![Tests](https://github.com/<your-username>/<repo-name>/actions/workflows/tests.yml/badge.svg)](https://github.com/<your-username>/<repo-name>/actions/workflows/tests.yml)

*(Replace `<your-username>/<repo-name>` above with your actual GitHub path
once pushed — see DEPLOY.md — and the badge will show live pass/fail
status. GitHub Actions runs the full test suite automatically on every
push.)*

---

## 0. UI Redesign (Post-Phase 4)

The entire frontend was redesigned for a clean, professional, "modern SaaS"
look: a calm green/white palette (replacing the earlier dark navy/red
theme), soft-colored status badges, rounded cards with subtle shadows, a
white top navbar, and a public landing page hero. No functionality
changed — every route, feature, and business rule from Phases 1-4 works
exactly as before.

As part of this pass, **Bootstrap, Font Awesome, and Chart.js are now
vendored locally** under `static/vendor/` instead of loaded from a CDN —
the app no longer needs internet access to render its styling/icons/
charts, which matters for a field tool that may run on a laptop with
unreliable connectivity. If you ever want to update these libraries,
replace the files under `static/vendor/<library>/` with newer versions.

---

## 1. What's New in Phase 4

- **Nigerian plate format validation**: registration now validates and
  normalises plate numbers against the `AAA-123-AA` pattern (3 letters,
  3 digits, 2 letters) shared by Lagos, Abuja/FCT, and other states —
  typos/wrong formats are rejected with a clear message and example
  formats, and accepted plates are auto-normalised (dashes/case).
- **Officer performance tracking**: the Analytics page now includes a
  table (Officer Name, Total Scans, Mismatches Found, Stolen Recoveries)
  alongside the officer-activity chart, both respecting the date filter.
- **Analytics PDF export, extended**: the analytics page now also shows
  summary stat cards and a recent-scans table so the printed/exported PDF
  is a complete one-page report, not just charts.
- **Simulated alert log page** (`/admin/alerts`): a dedicated table of
  every dispatched STOLEN/MISMATCH alert (Date, Plate, Alert Type,
  Recipient, Status) — a clean "here's the alert history" view for demos.
- **Landing page**: logged-out visitors now see a proper hero section
  (name, tagline, key features) with Register/Owner Login/Officer Login
  quick links, followed by the same live public stats as before — no
  login required to see system activity.

*(Note: a dark mode toggle was originally added here, then removed in
the later UI redesign in favor of a single clean light theme — see
section 0.)*

Phases 1-3 (registration, owner reports, real OCR/recognition, GPS
tagging, full-screen + voice alerts, multi-vehicle detection, batch
processing, admin analytics, offline hotlist cache, mobile-responsive
design) are unchanged and still fully working.

---

## 2. Requirements (unchanged from Phase 2)

- Python 3.10+ (built and tested on Python 3.12)
- pip
- **Tesseract OCR** system binary (for real plate reading — see below)
- ~1 GB free disk space (TensorFlow + OpenCV are the biggest dependencies)
- Works fine on a standard laptop CPU — **no GPU required** anywhere in
  this project.

### Installing Tesseract (system binary, not a Python package)

| OS | Command |
|---|---|
| Ubuntu/Debian | `sudo apt-get install tesseract-ocr` |
| macOS | `brew install tesseract` |
| Windows | Installer at https://github.com/UB-Mannheim/tesseract/wiki |

If Tesseract isn't installed, the app still runs — `utils/ocr.py` detects
this, logs a clear warning, and falls back to demo plate values so you can
keep developing/demoing without it.

---

## 3. Setup Instructions

### Quick start (recommended)
```bash
cd autoverify
./run_all.sh          # Linux/macOS
run_all.bat           # Windows (double-click or run from Command Prompt)
```
Both scripts create a virtual environment, install `requirements.txt`, warn
you if Tesseract isn't found, and start the server.

### Manual setup
```bash
cd autoverify
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

The app starts on **http://localhost:5000**. On first run it automatically
creates `autoverify.db` and seeds two demo officer accounts and two demo
vehicles (see below). To reset all data, stop the server and delete
`autoverify.db`, then restart.

> **Camera note:** `getUserMedia` requires a "secure context." On
> `localhost` this works over plain HTTP. If you deploy to a real server,
> you'll need HTTPS for the camera to work in the browser.

> **First install note:** the first run of `pip install -r requirements.txt`
> downloads TensorFlow and OpenCV (a few hundred MB total) — this can take
> a few minutes depending on your connection.

### Deploying so you can test on your phone

If you want a public HTTPS URL to test the camera/GPS features on an
actual phone (instead of only `localhost` on your laptop), see
**[`DEPLOY.md`](DEPLOY.md)** for a full step-by-step guide to deploying on
Render. A `Dockerfile` is already included in this project for exactly
this purpose (it installs the Tesseract system binary reliably during the
build).

---

## 4. Demo Accounts (seeded automatically)

| Role              | Username / Email             | Password      |
|-------------------|-------------------------------|---------------|
| Admin officer      | `admin`                       | `admin123`    |
| Field officer       | `officer1`                    | `officer123`  |
| Vehicle owner 1     | `chinedu@example.com`         | `password123` |
| Vehicle owner 2     | `amaka@example.com`           | `password123` |

Demo owner 1's plate is `ABC-123-XY` (Toyota Camry, white).
Demo owner 2's plate is `LND-456-KJ` (Honda Accord, black).

### Suggested test walkthrough
1. Log in as owner `chinedu@example.com` → **My Vehicle** → file a
   **Stolen** report on `ABC-123-XY`.
2. Log out, log in as `officer1` → **Scan Vehicle**.
3. Print or display an image of the plate text `ABC-123-XY` (or use the
   manual-entry fallback under "Plate not reading clearly?") and capture
   it. You should see a full-screen red **STOLEN** alert with sound.
4. Try a plate that isn't registered to see the **UNREGISTERED** state, or
   watch for **MISMATCH** if the (still-placeholder, until trained —
   see section 5) make/model recognition disagrees with what's registered.
5. Check the **Dashboard** for the live charts and quick-action buttons,
   and **Hotlist** to resolve the stolen report.
6. Turn off your Wi-Fi mid-session on the Scan Vehicle page to see the
   offline-cache banner and manual-entry offline check in action.
7. Display an image with **two plate texts side by side** (e.g.
   `ABC-123-XY` and `LND-456-KJ` in one photo) and capture it — you should
   see both vehicles detected and verified independently as a scrollable
   list of result cards, with a spoken voice warning for any STOLEN/
   MISMATCH result.
8. Go to **Batch Scan**, upload 2-3 vehicle photos at once, review the
   results table, and click **Export as CSV**.
9. Log in as `admin` → **Analytics** → try the 7-day/30-day/custom date
   filters, then **Export as PDF** (opens the browser print dialog — choose
   "Save as PDF").
10. Visit **Health** to see OCR/classifier status, database size, and scan
    counts — useful to confirm what's "real" vs. "placeholder" at a glance.
11. Try registering a vehicle with an obviously invalid plate like
    `AB-12-XYZ` to see the format-validation error, then register with a
    valid one typed without dashes (e.g. `abj123kj`) to see it
    auto-normalise to `ABJ-123-KJ`.
12. Visit **Analytics** → scroll down to see the new **Officer
    Performance** and **Recent Scans** tables, which are included in the
    PDF export alongside the charts.
13. Visit **Alert Log** (admin) to see every STOLEN/MISMATCH alert ever
    dispatched, in one clean table.
14. Log out completely and revisit `/` to see the **landing page** hero
    section with live public stats — no login required.

---

## 5. Real AI Components

### 5.1 Plate OCR — `utils/ocr.py` (real, works out of the box)

Pipeline: decode image → grayscale → bilateral filter → Canny edges →
contour search for plate-shaped rectangles (aspect ratio ~2:1–6:1) → Otsu
threshold on the best candidate crop → Tesseract OCR restricted to
`A-Z0-9-` → regex-normalise to `AAA-999-AA`. Falls back to OCR on the
whole frame if no plate-shaped contour is found, and to a demo plate value
if Tesseract itself isn't installed or nothing confident is found (so the
app keeps working end-to-end during setup/demos).

`locate_and_read_plates()` (Phase 3) runs the same pipeline but keeps
**every** plate-shaped contour found instead of just the best one, powering
multi-vehicle detection.

### 5.2 Vehicle colour — `utils/recognition.py::detect_colour()` (real, works out of the box)

OpenCV k-means clustering on the centre 60% of the frame (to avoid
road/sky background), mapped to the nearest named colour in a small
palette. No training needed.

### 5.3 Make/model recognition — MobileNetV2 transfer learning (needs your photos to be fully "real")

There's no public, ready-made "Nigerian common cars" classifier, so make/
model recognition needs to be fine-tuned on labelled photos of the actual
cars you care about. This repo ships the complete training pipeline:

1. Add photos under `training_data/`, one folder per class, named
   `Make_Model`:
   ```
   training_data/
     Toyota_Camry/     20-50+ photos
     Honda_Accord/      20-50+ photos
     Lexus_RX350/       20-50+ photos
   ```
2. Run:
   ```bash
   python utils/train_classifier.py
   ```
   This fine-tunes a frozen MobileNetV2 backbone (ImageNet weights) with a
   small trainable head — fast enough on a laptop CPU — and saves
   `models_ml/vehicle_classifier.h5` + `models_ml/class_labels.json`.
3. Restart the Flask app. `utils/recognition.py` automatically detects and
   loads the trained model — no code changes needed.

**Until you train it**, make/model predictions fall back to the Phase-1
placeholder values (clearly logged, and shown as "Placeholder (no trained
model yet)" on the scan result page) — colour detection keeps working for
real regardless, and the whole app keeps functioning end-to-end for demos.

---

## 6. Real Alert System

When a scan comes back **STOLEN** or **MISMATCH**:
- The browser shows a full-screen, flashing red/orange overlay with a
  synthesized siren sound (`static/sounds/alert.wav`) and a vibration
  pattern on supported phones. The officer taps "Acknowledge" to dismiss it.
- The backend calls `send_alert()` in `app.py`, which **always** logs a
  clearly formatted priority alert to the console and to `alerts.log` —
  this alone satisfies "a real alert was dispatched" for grading/demo
  purposes.
- If you set `app.config["MAIL_ENABLED"] = True` in `app.py` and install
  `Flask-Mail` with real SMTP credentials (`MAIL_SERVER`, `MAIL_USERNAME`,
  `MAIL_PASSWORD`, `ALERT_RECIPIENT` — configurable via environment
  variables), it also sends a real email per alert.
- Every alert is stored in the `AlertLog` table (`models.py`) with the
  plate, message, channel used, and whether it was actually delivered.

---

## 7. Multi-Vehicle Detection

`utils/ocr.py::locate_and_read_plates()` finds every plate-shaped contour
in a frame (not just the best one), and for each detected plate,
`utils/recognition.py::recognize_vehicle(..., bbox=...)` expands that
plate's bounding box outward to approximate the surrounding vehicle body
before running colour/make/model recognition — a simplified "region
proposal" approach using classic CV rather than a full object-detection
model (e.g. YOLO), which keeps the whole pipeline laptop/CPU-friendly.
Each detected vehicle gets its own `ScanLog` row, alert check, and result
card. A single-plate photo still works exactly as in Phase 2 (falls back
to one result automatically).

## 8. Voice Alerts

`templates/verify.html` uses the browser's built-in **Web Speech API**
(`SpeechSynthesisUtterance`) — no extra libraries — to speak a warning
whenever a scan result includes a STOLEN or MISMATCH vehicle, e.g. *"Warning!
Stolen vehicle detected."* This fires alongside the full-screen alert
overlay and only for alert-worthy results (not for CLEAR/UNREGISTERED).
Voice alerts require a browser with Web Speech API support (all modern
desktop and mobile browsers) and silently do nothing otherwise.

## 9. Batch Processing

`/batch` accepts up to 10 images per upload (`MAX_BATCH_IMAGES` in
`app.py`). Each image runs through the same real OCR + recognition +
database-matching pipeline as a live scan (one primary plate per image),
results render as a table, and a `BatchUpload` row is saved for audit.
Errors on individual files (corrupt image, wrong file type) are caught
per-file so one bad upload doesn't abort the whole batch — they show up
as an `ERROR` row with the failure reason. Click **Export as CSV** to
download the results table.

## 10. Admin Analytics Dashboard

`/admin/analytics` (admin-only) renders four Chart.js charts backed by
`GET /api/analytics-stats?range=...`:
- **Daily scans** — bar chart over the selected range
- **Mismatches by vehicle make** — horizontal bar, grouped by the
  recognized make on mismatched scans
- **Stolen vehicles recovered** — line chart of `OwnerReport` rows
  resolved (`resolved_at` set) per day
- **Officer activity** — scans grouped by officer

Below the charts, two tables complete the report:
- **Officer Performance** — Officer Name, Total Scans, Mismatches Found,
  Stolen Recoveries, all respecting the same date filter.
- **Recent Scans** — the latest 20 scans in the selected range (time,
  plate, officer, status).

Plus four summary stat cards (Total Scans, Mismatches, Stolen Confirmed,
Active Officers) at the top.

Supports `?range=7`, `?range=30` (default), or `?range=custom&start=YYYY-MM-DD&end=YYYY-MM-DD`.
**Export as PDF** uses the browser's native print dialog (`window.print()`)
with dedicated print CSS (`@media print` in `style.css`) that hides the
nav/footer/filter controls and switches to a light, printer-friendly
theme — the summary cards, all four charts, and both tables print as one
clean report, with no extra PDF library needed.

## 11. Simulated Owner Notification

Whenever `build_and_persist_scan_result()` in `app.py` confirms an active
**stolen** report on a scanned vehicle, `notify_owner()` simulates sending
the owner an SMS/email: logs a clear message to the console and to
`owner_notifications.log`, and stores an `OwnerNotification` row (visible
in the Admin panel's "Owner Notifications" table). The scan result page
shows a confirmation line ("Owner notified...") so the officer knows it
happened.

## 12. System Health Page

`/health` shows, at a glance:
- Whether real OCR (Tesseract) is loaded vs. falling back to placeholder plates
- Whether a trained MobileNetV2 classifier is loaded vs. falling back to placeholder make/model
- Database file size, registered vehicle/officer/scan counts, active stolen
  report count, and the timestamp + plate of the most recent scan

Useful for confirming setup during grading/demos without digging through logs.

---

## 13. Nigerian Plate Format Validation

`app.py::normalize_and_validate_plate()` checks every registration against
the shared Nigerian plate structure — **3 letters, 3 digits, 2 letters**
(`AAA-123-AA`) — which covers Lagos (e.g. `ABC-123-XY`), Abuja/FCT (e.g.
`ABJ-123-KJ`), and other states, since they all follow this same pattern
(only the specific letter/number combination varies by state of issue).
The function accepts the plate with or without dashes/spaces and any
letter case, then normalises it to the canonical `AAA-123-AA` form before
storage. Invalid formats (wrong letter/digit counts, missing segments,
etc.) are rejected with a clear error message and example formats. The
registration form's `pattern` attribute and helper text mirror the same
rule for instant client-side feedback.

## 14. Visual Theme

The interface uses a single, deliberately light theme — clean white
navbar, soft light-gray page background, white cards with subtle
shadows, and a calm green (`#2e7d32`) as the primary accent color. An
earlier dark navy/red theme with a light/dark toggle was replaced with
this single theme for a more professional, approachable look; there is
no dark mode. All colors are defined as CSS custom properties at the top
of `static/css/style.css` (`--av-primary`, `--av-bg`, `--av-text`, etc.)
if you want to adjust the palette.

## 15. Simulated Alert Log Page

`/admin/alerts` lists every `AlertLog` row (every STOLEN/MISMATCH alert
ever dispatched by `send_alert()`), with Date, Plate, Alert Type,
Recipient (the configured `ALERT_RECIPIENT` if email is enabled, otherwise
"Control Room (console dispatch)"), and Status (Delivered / Logged +
channel). Useful as a clean, dedicated view for a "here's the alert
history" moment during defense, separate from the Admin panel's broader
audit tables.

## 16. Landing Page

Logged-out visitors now see a hero section at the top of `/` — app name,
tagline, four key-feature callouts (real OCR, instant stolen alerts, GPS
tagging, citizen reporting), and quick links to Register Vehicle, Owner
Login, and Officer Login — followed by the same live public stats
(registered vehicles, scans today, active stolen reports, mismatches
today) and charts as before, with **no login required** to see system
activity. Logged-in officers see the familiar Control Room Dashboard
header and quick-action buttons instead of the hero.

---

## 17. Offline Hotlist Cache (Phase 2, still active)

`templates/verify.html` fetches `GET /api/hotlist` on page load and
whenever the browser regains connectivity, storing the list of active
stolen plates in `localStorage`. If `navigator.onLine` is `false` when an
officer submits a manually-typed plate, the app checks it against this
cached list client-side and raises an immediate offline warning — full
OCR + database verification still happens automatically once the
connection returns.

---

## 18. Automated Testing

A `pytest` suite (`tests/`) covers the core business logic with 63 tests
across 5 files, run against an isolated temporary SQLite database (never
your real `autoverify.db`) that's reset and reseeded before every test:

- **`test_plate_validation.py`** — Nigerian plate format normalisation/
  rejection, duplicate plate and email rejection, password confirmation.
- **`test_auth.py`** — owner/officer login success and failure, and
  role-based access control (a non-admin officer cannot reach `/admin`,
  `/admin/analytics`, or `/admin/alerts`; an owner session can't reach
  officer-only routes).
- **`test_verify.py`** — the core scan/verify logic, including a full
  **regression suite for a real bug we shipped and fixed**: manual plate
  entry with no photo captured used to call the recognition pipeline
  anyway, which returned a *random* placeholder colour/make/model that
  then got compared against the real registered vehicle — producing a
  false "MISMATCH" alert roughly 89% of the time on a plate nobody had
  actually looked at. `test_no_false_mismatch_across_many_runs` repeats
  that exact scenario 30 times and asserts it never happens again; several
  other tests confirm the STOLEN check still correctly fires with no
  photo (it's a real database lookup, not a visual guess), and that real
  camera/photo-based comparison is untouched.
- **`test_reports_and_hotlist.py`** — owner report filing, hotlist
  add/resolve, `resolved_at` timestamp tracking.
- **`test_api.py`** — the `/api/hotlist` and `/api/analytics-stats` JSON
  endpoints and the `/health` diagnostics page.

### Running the tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -v
```

With a coverage report (matches what CI runs):
```bash
pytest tests/ -v --cov=. --cov-report=term-missing --cov-config=.coveragerc
```

Current coverage is roughly 74% of `app.py`/`models.py`/`utils/` combined
(mostly untested: the `utils/train_classifier.py` standalone training
script, and a few defensive error-handling branches for things like a
corrupted upload).

### Continuous Integration

`.github/workflows/tests.yml` runs the full suite automatically on every
push and pull request (installing Tesseract OCR first, since real OCR
tests depend on it), so a broken change is caught before it reaches a
demo or Render deploy — not discovered live in front of a panel.

---

## 19. Project Structure

```
autoverify/
├── app.py                     # Flask app: all routes + /api/* JSON endpoints
├── models.py                  # Vehicle, OwnerReport, Officer, ScanLog, AlertLog,
│                               # OwnerNotification, BatchUpload
├── requirements.txt
├── requirements-dev.txt        # pytest + pytest-cov, for testing only
├── pytest.ini                  # pytest configuration
├── .coveragerc                  # coverage.py configuration
├── run_all.sh / run_all.bat   # one-command local setup + launch
├── Dockerfile                  # for Render (or any Docker host) deployment
├── .dockerignore
├── .gitignore
├── .github/workflows/tests.yml  # CI — runs the full test suite on every push
├── DEPLOY.md                    # step-by-step Render deployment guide
├── autoverify.db               # created automatically on first run
├── alerts.log                  # created automatically — priority alert audit trail
├── owner_notifications.log     # created automatically — owner notification audit trail
├── tests/                       # pytest suite — see section 18
│   ├── conftest.py               # isolated test DB + role-based client fixtures
│   ├── test_plate_validation.py
│   ├── test_auth.py
│   ├── test_verify.py            # includes the false-mismatch regression suite
│   ├── test_reports_and_hotlist.py
│   └── test_api.py
├── models_ml/                  # trained classifier lives here once you train it
│   ├── vehicle_classifier.h5   # (created by utils/train_classifier.py)
│   └── class_labels.json
├── training_data/               # add your own labelled photos here (see section 5.3)
├── static/
│   ├── uploads/                 # vehicle photos + scan captures
│   ├── sounds/alert.wav          # synthesized siren for the full-screen alert
│   ├── vendor/                    # self-hosted Bootstrap, Font Awesome, Chart.js (no CDN needed)
│   └── css/style.css             # clean green/white theme + mobile responsive + print rules
├── templates/
│   ├── base.html                  # clean white navbar, no dark mode
│   ├── index.html                 # public landing hero + dashboard stats
│   ├── register.html              # PHASE 4: Nigerian plate format hint/validation
│   ├── login.html
│   ├── owner_dashboard.html
│   ├── officer_login.html
│   ├── verify.html                 # camera scan + multi-vehicle cards + voice/full-screen alerts
│   ├── batch.html                  # bulk image upload + CSV export
│   ├── analytics.html              # charts + officer performance + recent scans + PDF export
│   ├── health.html                 # system health/diagnostics page
│   ├── alerts.html                 # PHASE 4: simulated alert history log
│   ├── hotlist.html
│   ├── reports.html
│   └── admin.html                  # includes owner-notification + batch-upload audit tables
└── utils/
    ├── ocr.py                     # real OCR (OpenCV + Tesseract) + multi-plate detection
    ├── recognition.py             # real colour detection + MobileNetV2 classifier + bbox cropping
    └── train_classifier.py        # fine-tuning script for make/model recognition
```

---

## 20. Core Business Rules Implemented

- One plate → one owner. Duplicate plate registration is rejected at `/register`.
- Plate numbers must match the Nigerian `AAA-123-AA` format (3 letters, 3
  digits, 2 letters) — invalid formats are rejected at registration, and
  valid ones are normalised (case, dashes) before storage.
- Owner reports can only be filed by the authenticated registered owner.
- Filing a "Stolen" report immediately adds the plate to the active hotlist.
- Officers cannot self-register — accounts are admin-created only.
- Every officer scan is logged (officer ID, plate, recognized attributes,
  match result, GPS if available, timestamp) for audit purposes.
- STOLEN/MISMATCH results always generate an `AlertLog` entry.

---

## 21. Known Limitations

- Make/model recognition requires you to supply and train on your own
  labelled photos (section 5.3) to move beyond placeholder values — this
  is a hard requirement of any specific-vehicle classifier, not something
  a generic pretrained model can do out of the box.
- OCR accuracy on real-world photos depends heavily on lighting, angle,
  and plate condition — this is inherent to any OCR system, not unique to
  this project. Manual plate entry is provided as a fallback.
- Multi-vehicle detection uses a classic-CV "plate-shaped contour" search
  rather than a trained object-detection model — it works well for clearly
  separated plates but can miss vehicles at extreme angles or very small
  in-frame, and can occasionally pick up non-plate rectangles as false
  positives. A YOLO-style detector would be a natural upgrade path.
- Batch processing runs synchronously per request — 10 large images can
  take a several seconds; there's no true live progress bar (would need
  WebSockets/SSE), just an in-page "processing" indicator.
- Voice alerts depend on the browser's Web Speech API and installed system
  voices — quality/availability varies by OS and browser.
- The Nigerian plate format validation covers the standard 3-letter/
  3-digit/2-letter structure shared across states; it doesn't check that a
  specific letter combination is actually assigned to a real state code —
  that would require a maintained lookup table, which is out of scope for
  a school project demo.
- Session-based auth only (no password reset / email verification flow yet).
- SQLite is fine for a school project demo; production would want
  PostgreSQL/MySQL + proper secret management (the `SECRET_KEY` in `app.py`
  is a dev placeholder — change it before any real deployment).
- No CSRF tokens yet — consider adding `Flask-WTF` in a later phase.
- The offline hotlist cache is a best-effort client-side convenience, not
  a substitute for real connectivity — full verification (OCR + DB lookup)
  still requires the officer's device to reach the Flask server.
