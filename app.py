import os
import io
import csv
import re
import base64
import logging
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, Response
)
from werkzeug.utils import secure_filename

from models import db, Vehicle, OwnerReport, Officer, ScanLog, AlertLog, OwnerNotification, BatchUpload
from utils.ocr import read_plate, locate_and_read_plates, is_ocr_available
from utils.recognition import recognize_vehicle, is_classifier_loaded

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
ALERTS_LOG_PATH = os.path.join(BASE_DIR, "alerts.log")
NOTIFICATIONS_LOG_PATH = os.path.join(BASE_DIR, "owner_notifications.log")
DB_PATH = os.path.join(BASE_DIR, "autoverify.db")
MAX_BATCH_IMAGES = 10

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "autoverify-ng-dev-secret-change-in-production")

_db_url = os.environ.get("DATABASE_URL", "")
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = _db_url or ("sqlite:///" + os.path.join(BASE_DIR, "autoverify.db"))

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# ---- Phase 2: simulated alert dispatch settings ----
# By default alerts are logged to the console + alerts.log (fine for a demo).
# To send REAL email alerts, set MAIL_ENABLED=True and fill in real SMTP
# credentials below (or via environment variables), then `pip install Flask-Mail`.
app.config["MAIL_ENABLED"] = False
app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", 587))
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME", "")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD", "")
app.config["ALERT_RECIPIENT"] = os.environ.get("ALERT_RECIPIENT", "control-room@example.com")

db.init_app(app)

mail = None
if app.config["MAIL_ENABLED"]:
    try:
        from flask_mail import Mail
        mail = Mail(app)
    except Exception:
        logging.getLogger("autoverify").warning(
            "Flask-Mail not installed; falling back to console/file alert logging."
        )
        mail = None


def send_alert(alert_type, plate_number, message, scan_log_id=None):
    """
    Phase 2: dispatch a priority alert for a STOLEN or MISMATCH scan result.

    Always logs to the console and to alerts.log on disk — this alone is
    enough for grading/demo purposes as a "simulated" SMS/email alert.
    If MAIL_ENABLED and Flask-Mail + real SMTP credentials are configured,
    also attempts to send a real email to ALERT_RECIPIENT.
    """
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    full_message = f"[{timestamp}] {alert_type.upper()} ALERT — Plate {plate_number}: {message}"

    print(f"\n🚨 {full_message}\n")

    try:
        with open(ALERTS_LOG_PATH, "a") as f:
            f.write(full_message + "\n")
    except Exception as e:
        app.logger.warning("Could not write to alerts.log: %s", e)

    delivered = False
    channel = "console"

    if mail is not None:
        try:
            from flask_mail import Message
            msg = Message(
                subject=f"AutoVerify NG — {alert_type.upper()} ALERT: {plate_number}",
                recipients=[app.config["ALERT_RECIPIENT"]],
                body=full_message,
            )
            mail.send(msg)
            delivered = True
            channel = "email"
        except Exception as e:
            app.logger.warning("Alert email send failed; logged to console/file instead: %s", e)

    alert = AlertLog(
        scan_log_id=scan_log_id,
        alert_type=alert_type,
        plate_number=plate_number,
        message=message,
        channel=channel,
        delivered=delivered,
    )
    db.session.add(alert)
    db.session.commit()


def notify_owner(vehicle, message, scan_log_id=None):
    """
    PHASE 3: Simulate notifying the vehicle owner (SMS/email) when a scan
    detects an active stolen report on their vehicle. Always logs to the
    console and to owner_notifications.log — sufficient for grading/demo
    purposes as a "simulated" notification. Stores an OwnerNotification row
    for audit (visible in the Admin panel).
    """
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    full_message = (
        f"[{timestamp}] OWNER NOTIFICATION — To: {vehicle.owner_name} "
        f"({vehicle.owner_email}, {vehicle.owner_phone}): {message}"
    )

    print(f"\n📩 {full_message}\n")

    try:
        with open(NOTIFICATIONS_LOG_PATH, "a") as f:
            f.write(full_message + "\n")
    except Exception as e:
        app.logger.warning("Could not write to owner_notifications.log: %s", e)

    notification = OwnerNotification(
        vehicle_id=vehicle.id,
        scan_log_id=scan_log_id,
        message=message,
        channel="console",
        delivered=True,  # console/file logging always "delivers" for demo purposes
    )
    db.session.add(notification)
    db.session.commit()
    return notification


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# PHASE 4: Nigerian plate format validation
#
# Nigerian plates follow the same underlying 3-letter / 3-digit / 2-letter
# pattern across states (only the letters/numbers themselves vary by state
# of issue, e.g. Lagos vs Abuja/FCT vs others) — so one regex covers them
# all: AAA-123-AA. We accept the plate with or without dashes/spaces typed
# by the user, and normalise it to the canonical AAA-123-AA form for storage.
NIGERIAN_PLATE_REGEX = re.compile(r"^([A-Z]{3})[\s\-]?(\d{3})[\s\-]?([A-Z]{2})$")

PLATE_FORMAT_EXAMPLES = [
    ("Lagos", "ABC-123-XY"),
    ("Abuja / FCT", "ABJ-123-KJ"),
    ("General pattern", "AAA-123-AA"),
]


def normalize_and_validate_plate(raw_plate):
    """
    PHASE 4: Validates a user-typed plate number against the Nigerian
    3-letter/3-digit/2-letter format (covers Lagos, Abuja/FCT, and other
    states, which all share this structure) and normalises it to
    AAA-123-AA. Returns (normalized_plate, error_message) — exactly one of
    the two will be None.
    """
    if not raw_plate:
        return None, "Plate number is required."

    cleaned = raw_plate.strip().upper()
    match = NIGERIAN_PLATE_REGEX.match(cleaned)

    if not match:
        return None, (
            "Invalid plate format. Nigerian plates follow the pattern "
            "AAA-123-AA (3 letters, 3 numbers, 2 letters) — "
            "e.g. ABC-123-XY (Lagos) or ABJ-123-KJ (Abuja/FCT)."
        )

    letters1, digits, letters2 = match.groups()
    return f"{letters1}-{digits}-{letters2}", None


def owner_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("vehicle_id"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return decorated_get_vehicle(f, *args, **kwargs)
    return decorated


def decorated_get_vehicle(f, *args, **kwargs):
    return f(*args, **kwargs)


def officer_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("officer_id"):
            flash("Officer login required.", "warning")
            return redirect(url_for("officer_login"))
        return f(*args, **kwargs)
    return decorated


def admin_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("officer_id") or not session.get("is_admin"):
            flash("Admin access required.", "danger")
            return redirect(url_for("officer_login"))
        return f(*args, **kwargs)
    return decorated


def save_uploaded_image(file_storage):
    """Save an uploaded photo from a normal <input type=file>. Returns relative path or None."""
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_file(file_storage.filename):
        return None
    filename = secure_filename(file_storage.filename)
    stamped = f"{int(datetime.utcnow().timestamp())}_{filename}"
    full_path = os.path.join(app.config["UPLOAD_FOLDER"], stamped)
    file_storage.save(full_path)
    return f"uploads/{stamped}"


def save_captured_image(data_url, prefix="scan"):
    """Save a base64 dataURL image (from the camera capture) to disk. Returns relative path or None."""
    if not data_url or "," not in data_url:
        return None
    try:
        header, encoded = data_url.split(",", 1)
        binary_data = base64.b64decode(encoded)
    except Exception:
        return None
    stamped = f"{prefix}_{int(datetime.utcnow().timestamp())}.png"
    full_path = os.path.join(app.config["UPLOAD_FOLDER"], stamped)
    with open(full_path, "wb") as f:
        f.write(binary_data)
    return f"uploads/{stamped}"


def build_and_persist_scan_result(plate_number, recognized, officer_id, gps_lat=None, gps_lon=None):
    """
    PHASE 3: Shared vehicle-matching + persistence logic, factored out of
    verify_post() so it can be reused for:
      - single-vehicle camera scans (Phase 2 behaviour)
      - multi-vehicle detection (several plates found in one photo)
      - manual plate entry
      - /batch bulk image processing

    Looks up the plate, compares registered vs. recognized attributes,
    creates the ScanLog row, dispatches a priority alert (STOLEN/MISMATCH),
    and simulates an owner notification for STOLEN detections. Returns a
    result dict ready for template rendering / CSV export.

    IMPORTANT: `recognized["method"]` may be "no_image" — this means no
    actual photo was captured (e.g. manual plate entry with the camera
    never started), so `recognized["make"/"model"/"colour"]` are None
    rather than a real (or even a random placeholder) observation. In that
    case we skip attribute comparison entirely rather than comparing
    against a fabricated guess, which would otherwise risk a false
    MISMATCH alert on a plate that was never actually looked at.
    """
    vehicle = Vehicle.query.filter_by(plate_number=plate_number).first()
    visually_verified = recognized.get("method") != "no_image"

    result = {
        "plate_number": plate_number,
        "recognized_make": recognized["make"],
        "recognized_model": recognized["model"],
        "recognized_colour": recognized["colour"],
        "recognition_method": recognized.get("method"),
        "visually_verified": visually_verified,
        "status": None,        # "stolen" | "mismatch" | "clear" | "unregistered"
        "message": "",
        "notes": [],
        "owner_info": None,
        "registered_vehicle": None,
        "trigger_alert": False,
        "alert_type": None,
    }

    matched = True
    mismatch_detail = None
    report_flag = False
    stolen_flag = False

    if not vehicle:
        result["status"] = "unregistered"
        result["message"] = f"UNREGISTERED VEHICLE — plate {plate_number} was not found in the database."
    else:
        stolen_report = vehicle.active_report("stolen")
        ownership_report = vehicle.active_report("ownership_change")
        written_off_report = vehicle.active_report("written_off")

        if stolen_report:
            stolen_flag = True
            report_flag = True
            result["status"] = "stolen"
            result["message"] = "🚨 STOLEN: This vehicle is reported stolen! Contact control room immediately."
            result["trigger_alert"] = True
            result["alert_type"] = "stolen"

        if not visually_verified:
            # No photo was captured — only the plate/database was checked.
            # Never fabricate a make/model/colour comparison here.
            result["notes"].append(
                "ℹ️ No photo captured — vehicle appearance was not visually verified, "
                "only the plate number was checked against the database."
            )
            if result["status"] is None:
                result["status"] = "clear"
                result["message"] = (
                    "✅ PLATE CHECKED: No active stolen report found for this plate "
                    "(appearance not verified — no photo taken)."
                )
        else:
            mismatches = []
            if recognized["make"].lower() != vehicle.make.lower():
                mismatches.append(f"make (registered: {vehicle.make}, seen: {recognized['make']})")
            if recognized["model"].lower() != vehicle.model.lower():
                mismatches.append(f"model (registered: {vehicle.model}, seen: {recognized['model']})")
            if recognized["colour"].lower() != vehicle.colour.lower():
                mismatches.append(f"colour (registered: {vehicle.colour}, seen: {recognized['colour']})")

            if mismatches:
                matched = False
                mismatch_detail = (
                    f"Plate belongs to a {vehicle.year} {vehicle.make} {vehicle.model} ({vehicle.colour}), "
                    f"but this appears to be a {recognized['make']} {recognized['model']} ({recognized['colour']}). "
                    f"Mismatch in: {', '.join(mismatches)}."
                )
                if result["status"] is None:
                    result["status"] = "mismatch"
                    result["message"] = f"⚠️ MISMATCH: {mismatch_detail}"
                    result["trigger_alert"] = True
                    result["alert_type"] = "mismatch"
                else:
                    result["notes"].append(mismatch_detail)
            else:
                matched = True
                if result["status"] is None:
                    result["status"] = "clear"
                    result["message"] = "✅ CLEAR: Vehicle verified — no issues detected."

        if ownership_report:
            report_flag = True
            result["notes"].append("ℹ️ REPORT ACTIVE: Owner reported ownership change pending.")

        if written_off_report:
            report_flag = True
            result["notes"].append("ℹ️ REPORT ACTIVE: Vehicle has been marked as written off / scrapped by owner.")

        # Registered vehicle photo + details — shown to officers so they can
        # visually compare against the real vehicle in front of them. This
        # matters most for manual/no-photo checks, where no AI comparison
        # runs at all (see build_and_persist_scan_result's no_image branch).
        result["registered_vehicle"] = {
            "make": vehicle.make,
            "model": vehicle.model,
            "year": vehicle.year,
            "colour": vehicle.colour,
            "image_path": vehicle.image_path,
        }

        # Ownership details shown only to authorized officers after successful verification
        result["owner_info"] = {
            "name": vehicle.owner_name,
            "phone": vehicle.owner_phone,
            "email": vehicle.owner_email,
            "address_note": "Full address available in admin records.",
        }

    scan = ScanLog(
        officer_id=officer_id,
        plate_number=plate_number,
        recognized_make=recognized["make"],
        recognized_model=recognized["model"],
        recognized_colour=recognized["colour"],
        matched=matched,
        visually_verified=visually_verified,
        mismatch_detail=mismatch_detail,
        report_flag=report_flag,
        stolen_flag=stolen_flag,
        gps_lat=float(gps_lat) if gps_lat else None,
        gps_lon=float(gps_lon) if gps_lon else None,
    )
    db.session.add(scan)
    db.session.commit()
    result["scan_id"] = scan.id

    if result["trigger_alert"]:
        officer = Officer.query.get(officer_id)
        location_note = ""
        if gps_lat and gps_lon:
            location_note = f" Location: https://maps.google.com/?q={gps_lat},{gps_lon}"
        send_alert(
            alert_type=result["alert_type"],
            plate_number=plate_number,
            message=(
                f"{result['message']} Scanned by Officer {officer.full_name} "
                f"(badge {officer.badge_number}).{location_note}"
            ),
            scan_log_id=scan.id,
        )

    # PHASE 3: simulate an owner notification whenever a stolen vehicle is confirmed
    if stolen_flag and vehicle:
        notify_owner(
            vehicle,
            message=f"Your vehicle with plate {plate_number} was flagged as STOLEN by law enforcement during a scan.",
            scan_log_id=scan.id,
        )
        result["owner_notified"] = True
    else:
        result["owner_notified"] = False

    return result


# ------------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------------

@app.route("/")
def index():
    total_vehicles = Vehicle.query.count()
    today = date.today()

    scans_today = ScanLog.query.filter(
        db.func.date(ScanLog.timestamp) == today
    ).count()

    active_stolen = OwnerReport.query.filter_by(
        report_type="stolen", is_active=True
    ).count()

    mismatches_today = ScanLog.query.filter(
        db.func.date(ScanLog.timestamp) == today,
        ScanLog.matched == False  # noqa: E712
    ).count()

    recent_scans = ScanLog.query.order_by(ScanLog.timestamp.desc()).limit(10).all()

    return render_template(
        "index.html",
        total_vehicles=total_vehicles,
        scans_today=scans_today,
        active_stolen=active_stolen,
        mismatches_today=mismatches_today,
        recent_scans=recent_scans,
    )


@app.route("/api/dashboard-stats")
def api_dashboard_stats():
    """
    PHASE 2: JSON data for the enhanced dashboard charts
    (scans-per-day line chart, verified-vs-mismatch pie chart,
    top-recognized-models bar chart).
    """
    today = date.today()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]  # last 7 days, oldest first

    scans_per_day = []
    for d in days:
        count = ScanLog.query.filter(db.func.date(ScanLog.timestamp) == d).count()
        scans_per_day.append({"date": d.strftime("%a %d"), "count": count})

    verified_count = ScanLog.query.filter_by(matched=True).count()
    mismatch_count = ScanLog.query.filter_by(matched=False).count()
    stolen_count = ScanLog.query.filter_by(stolen_flag=True).count()

    all_scans = ScanLog.query.all()
    model_counts = {}
    for s in all_scans:
        if not s.visually_verified or not s.recognized_make:
            continue
        label = f"{s.recognized_make} {s.recognized_model}".strip()
        if label:
            model_counts[label] = model_counts.get(label, 0) + 1
    top_models = sorted(model_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]

    return jsonify({
        "scans_per_day": scans_per_day,
        "verified_count": verified_count,
        "mismatch_count": mismatch_count,
        "stolen_count": stolen_count,
        "top_models": [{"label": label, "count": count} for label, count in top_models],
    })


@app.route("/api/hotlist")
@officer_login_required
def api_hotlist():
    """
    PHASE 2: JSON list of currently-active stolen plates, used by
    verify.html to build an offline localStorage cache. If network drops
    mid-shift, the officer can still get a best-effort warning against the
    last-synced hotlist.
    """
    stolen_reports = OwnerReport.query.filter_by(report_type="stolen", is_active=True).all()
    plates = [r.vehicle.plate_number for r in stolen_reports]
    return jsonify({"plates": plates, "synced_at": datetime.utcnow().isoformat()})


# ------------------------------------------------------------------
# Owner: Registration / Login / Logout / Dashboard
# ------------------------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        plate_number = request.form.get("plate_number", "").strip().upper()
        owner_name = request.form.get("owner_name", "").strip()
        owner_phone = request.form.get("owner_phone", "").strip()
        owner_email = request.form.get("owner_email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        make = request.form.get("make", "").strip()
        model = request.form.get("model", "").strip()
        year = request.form.get("year", "").strip()
        colour = request.form.get("colour", "").strip()
        photo = request.files.get("photo")

        if not all([plate_number, owner_name, owner_phone, owner_email,
                    password, make, model, year, colour]):
            flash("Please fill in all required fields.", "danger")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("register"))

        # PHASE 4: Nigerian plate format validation (AAA-123-AA)
        plate_number, plate_error = normalize_and_validate_plate(plate_number)
        if plate_error:
            flash(plate_error, "danger")
            return redirect(url_for("register"))

        # Core rule: one plate -> one owner
        if Vehicle.query.filter_by(plate_number=plate_number).first():
            flash(f"Plate number {plate_number} is already registered. Duplicate registration is not allowed.", "danger")
            return redirect(url_for("register"))

        if Vehicle.query.filter_by(owner_email=owner_email).first():
            flash("An account with this email already exists.", "danger")
            return redirect(url_for("register"))

        try:
            year_int = int(year)
        except ValueError:
            flash("Year must be a number.", "danger")
            return redirect(url_for("register"))

        image_path = save_uploaded_image(photo)

        vehicle = Vehicle(
            plate_number=plate_number,
            owner_name=owner_name,
            owner_phone=owner_phone,
            owner_email=owner_email,
            make=make,
            model=model,
            year=year_int,
            colour=colour,
            image_path=image_path,
        )
        vehicle.set_password(password)

        db.session.add(vehicle)
        db.session.commit()

        flash("Vehicle registered successfully! You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        vehicle = Vehicle.query.filter_by(owner_email=email).first()
        if vehicle and vehicle.check_password(password):
            session["vehicle_id"] = vehicle.id
            flash(f"Welcome back, {vehicle.owner_name}!", "success")
            return redirect(url_for("owner_dashboard"))

        flash("Invalid email or password.", "danger")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("vehicle_id", None)
    session.pop("officer_id", None)
    session.pop("is_admin", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/owner/dashboard")
@owner_login_required
def owner_dashboard():
    vehicle = Vehicle.query.get_or_404(session["vehicle_id"])
    reports = OwnerReport.query.filter_by(vehicle_id=vehicle.id).order_by(
        OwnerReport.created_at.desc()
    ).all()
    return render_template("owner_dashboard.html", vehicle=vehicle, reports=reports)


# ------------------------------------------------------------------
# Owner: Report Filing
# ------------------------------------------------------------------

@app.route("/owner/report", methods=["POST"])
@owner_login_required
def owner_report():
    vehicle = Vehicle.query.get_or_404(session["vehicle_id"])

    report_type = request.form.get("report_type", "")
    description = request.form.get("description", "").strip()

    valid_types = {"stolen", "ownership_change", "written_off"}
    if report_type not in valid_types:
        flash("Invalid report type.", "danger")
        return redirect(url_for("owner_dashboard"))

    report = OwnerReport(
        vehicle_id=vehicle.id,
        report_type=report_type,
        description=description,
        is_active=True,
    )
    db.session.add(report)
    db.session.commit()

    labels = {
        "stolen": "Your vehicle has been reported STOLEN and added to the hotlist.",
        "ownership_change": "Ownership change report filed and pending officer review.",
        "written_off": "Vehicle marked as written off / scrapped.",
    }
    flash(labels[report_type], "success")
    return redirect(url_for("owner_dashboard"))


# ------------------------------------------------------------------
# Officer: Login
# ------------------------------------------------------------------

@app.route("/officer/login", methods=["GET", "POST"])
def officer_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        officer = Officer.query.filter_by(username=username).first()
        if officer and officer.check_password(password):
            session["officer_id"] = officer.id
            session["is_admin"] = officer.is_admin
            flash(f"Welcome, Officer {officer.full_name}.", "success")
            if officer.is_admin:
                return redirect(url_for("admin"))
            return redirect(url_for("verify"))

        flash("Invalid officer credentials.", "danger")
        return redirect(url_for("officer_login"))

    return render_template("officer_login.html")


# ------------------------------------------------------------------
# Officer: Scan & Verification
# ------------------------------------------------------------------

@app.route("/verify", methods=["GET"])
@officer_login_required
def verify():
    return render_template("verify.html")


@app.route("/verify", methods=["POST"])
@officer_login_required
def verify_post():
    image_data_url = request.form.get("image_data") or request.form.get("manual_image_data")
    gps_lat = request.form.get("gps_lat") or request.form.get("manual_gps_lat")
    gps_lon = request.form.get("gps_lon") or request.form.get("manual_gps_lon")
    manual_plate = request.form.get("manual_plate", "").strip().upper()

    # A real captured frame is always a "data:image/..." data URL. Anything
    # else (empty string, missing field) means no photo was actually taken.
    has_real_image = bool(image_data_url) and image_data_url.startswith("data:image")

    save_captured_image(image_data_url)  # stored for audit purposes

    vehicles_results = []

    if manual_plate:
        # Officer typed the plate manually (OCR was unclear, or no camera
        # was used at all). Only run vehicle-attribute recognition if a
        # photo was actually captured — otherwise there is nothing to
        # recognize, and guessing would risk a false MISMATCH alert on a
        # plate nobody actually looked at (see build_and_persist_scan_result).
        if has_real_image:
            recognized = recognize_vehicle(image_data_url)
        else:
            recognized = {"make": None, "model": None, "colour": None, "method": "no_image"}
        vehicles_results.append(
            build_and_persist_scan_result(manual_plate, recognized, session["officer_id"], gps_lat, gps_lon)
        )
    else:
        # PHASE 3: MULTI-VEHICLE DETECTION — find every plate-shaped region
        # in the frame (e.g. a checkpoint photo with several cars) and
        # verify each one independently. Falls back to single-vehicle
        # behaviour automatically if only one plate is found.
        detections = locate_and_read_plates(image_data_url, max_results=MAX_BATCH_IMAGES)
        for det in detections:
            recognized = recognize_vehicle(image_data_url, bbox=det.get("bbox"))
            vehicles_results.append(
                build_and_persist_scan_result(
                    det["plate_number"], recognized, session["officer_id"], gps_lat, gps_lon
                )
            )

    # Overall alert severity across all detected vehicles, for the
    # full-screen overlay + voice alert (stolen takes priority over mismatch)
    overall_alert = None
    for v in vehicles_results:
        if v["alert_type"] == "stolen":
            overall_alert = "stolen"
            break
        if v["alert_type"] == "mismatch" and overall_alert is None:
            overall_alert = "mismatch"

    return render_template(
        "verify.html",
        vehicles=vehicles_results,
        multi_vehicle=len(vehicles_results) > 1,
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        overall_alert=overall_alert,
    )


# ------------------------------------------------------------------
# Hotlist
# ------------------------------------------------------------------

@app.route("/hotlist")
@officer_login_required
def hotlist():
    stolen_reports = (
        OwnerReport.query
        .filter_by(report_type="stolen", is_active=True)
        .order_by(OwnerReport.created_at.desc())
        .all()
    )
    return render_template("hotlist.html", stolen_reports=stolen_reports)


@app.route("/hotlist/resolve/<int:report_id>", methods=["POST"])
@officer_login_required
def hotlist_resolve(report_id):
    report = OwnerReport.query.get_or_404(report_id)
    report.is_active = False
    report.resolved_at = datetime.utcnow()  # PHASE 3: powers the "recovered vehicles" analytics chart
    db.session.commit()
    flash("Report marked as resolved.", "success")
    return redirect(url_for("hotlist"))


# ------------------------------------------------------------------
# Officer view of all owner reports
# ------------------------------------------------------------------

@app.route("/reports")
@officer_login_required
def reports():
    all_reports = OwnerReport.query.order_by(OwnerReport.created_at.desc()).all()
    return render_template("reports.html", reports=all_reports)


# ------------------------------------------------------------------
# Admin Panel
# ------------------------------------------------------------------

@app.route("/admin")
@admin_login_required
def admin():
    officers = Officer.query.order_by(Officer.created_at.desc()).all()
    vehicles = Vehicle.query.order_by(Vehicle.registered_at.desc()).all()
    all_reports = OwnerReport.query.order_by(OwnerReport.created_at.desc()).all()
    scan_logs = ScanLog.query.order_by(ScanLog.timestamp.desc()).limit(50).all()
    owner_notifications = OwnerNotification.query.order_by(OwnerNotification.created_at.desc()).limit(50).all()
    batch_uploads = BatchUpload.query.order_by(BatchUpload.created_at.desc()).limit(50).all()
    return render_template(
        "admin.html",
        officers=officers,
        vehicles=vehicles,
        reports=all_reports,
        scan_logs=scan_logs,
        owner_notifications=owner_notifications,
        batch_uploads=batch_uploads,
    )


@app.route("/admin/officers/create", methods=["POST"])
@admin_login_required
def admin_create_officer():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    full_name = request.form.get("full_name", "").strip()
    badge_number = request.form.get("badge_number", "").strip()
    is_admin = bool(request.form.get("is_admin"))

    if not all([username, password, full_name, badge_number]):
        flash("All officer fields are required.", "danger")
        return redirect(url_for("admin"))

    if Officer.query.filter_by(username=username).first():
        flash("That officer username already exists.", "danger")
        return redirect(url_for("admin"))

    officer = Officer(
        username=username,
        full_name=full_name,
        badge_number=badge_number,
        is_admin=is_admin,
    )
    officer.set_password(password)
    db.session.add(officer)
    db.session.commit()

    flash(f"Officer account created for {full_name}.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/hotlist/add", methods=["POST"])
@admin_login_required
def admin_hotlist_add():
    plate_number = request.form.get("plate_number", "").strip().upper()
    description = request.form.get("description", "").strip()
    redirect_target = "hotlist" if request.form.get("next") == "hotlist" else "admin"

    vehicle = Vehicle.query.filter_by(plate_number=plate_number).first()
    if not vehicle:
        flash(f"No vehicle found with plate {plate_number}.", "danger")
        return redirect(url_for(redirect_target))

    report = OwnerReport(
        vehicle_id=vehicle.id,
        report_type="stolen",
        description=description or "Added manually by admin.",
        is_active=True,
    )
    db.session.add(report)
    db.session.commit()
    flash(f"Plate {plate_number} added to stolen hotlist.", "success")
    return redirect(url_for(redirect_target))


@app.route("/admin/hotlist/remove/<int:report_id>", methods=["POST"])
@admin_login_required
def admin_hotlist_remove(report_id):
    report = OwnerReport.query.get_or_404(report_id)
    report.is_active = False
    report.resolved_at = datetime.utcnow()
    db.session.commit()
    flash("Hotlist entry removed.", "success")
    return redirect(url_for("admin"))


# ------------------------------------------------------------------
# PHASE 3: Batch processing (upload multiple images at once)
# ------------------------------------------------------------------

@app.route("/batch", methods=["GET"])
@officer_login_required
def batch():
    return render_template("batch.html", batch_results=session.get("last_batch_results"))


@app.route("/batch", methods=["POST"])
@officer_login_required
def batch_post():
    files = request.files.getlist("images")[:MAX_BATCH_IMAGES]
    files = [f for f in files if f and f.filename]

    if not files:
        flash("Please choose at least one image to process.", "warning")
        return redirect(url_for("batch"))

    batch_results = []
    stolen_count = 0
    mismatch_count = 0

    for f in files:
        row = {"filename": secure_filename(f.filename)}
        try:
            if not allowed_file(f.filename):
                raise ValueError("Unsupported file type — use JPG, PNG, GIF, or WEBP.")

            image_bytes = f.read()
            if not image_bytes:
                raise ValueError("Empty or unreadable file.")

            plate_number = read_plate(image_bytes)
            recognized = recognize_vehicle(image_bytes)

            single = build_and_persist_scan_result(
                plate_number, recognized, session["officer_id"], gps_lat=None, gps_lon=None
            )

            row.update({
                "plate_number": single["plate_number"],
                "make": single["recognized_make"],
                "model": single["recognized_model"],
                "colour": single["recognized_colour"],
                "status": single["status"],
                "message": single["message"],
                "error": None,
            })

            if single["status"] == "stolen":
                stolen_count += 1
            elif single["status"] == "mismatch":
                mismatch_count += 1

        except Exception as exc:
            # PHASE 3: handle per-image errors gracefully — one bad file
            # shouldn't abort the whole batch.
            row.update({
                "plate_number": None, "make": None, "model": None, "colour": None,
                "status": "error", "message": str(exc), "error": str(exc),
            })

        batch_results.append(row)

    batch_upload = BatchUpload(
        officer_id=session["officer_id"],
        image_count=len(files),
        stolen_count=stolen_count,
        mismatch_count=mismatch_count,
    )
    db.session.add(batch_upload)
    db.session.commit()

    # Stash results in the session (small — just text rows) so the CSV
    # export route can regenerate the file without re-processing images.
    session["last_batch_results"] = batch_results

    flash(f"Processed {len(files)} image(s): {stolen_count} stolen, {mismatch_count} mismatch.", "success")
    return render_template("batch.html", batch_results=batch_results)


@app.route("/batch/export.csv")
@officer_login_required
def batch_export_csv():
    results = session.get("last_batch_results")
    if not results:
        flash("No batch results to export yet — process a batch first.", "warning")
        return redirect(url_for("batch"))

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=["filename", "plate_number", "make", "model", "colour", "status", "message", "error"],
    )
    writer.writeheader()
    for row in results:
        writer.writerow(row)

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=autoverify_batch_results.csv"},
    )


# ------------------------------------------------------------------
# PHASE 3: Admin analytics dashboard
# ------------------------------------------------------------------

@app.route("/admin/analytics")
@admin_login_required
def admin_analytics():
    return render_template("analytics.html")


@app.route("/api/analytics-stats")
@admin_login_required
def api_analytics_stats():
    """
    JSON data for the admin analytics charts, with a date-range filter:
      ?range=7            -> last 7 days
      ?range=30            -> last 30 days (default)
      ?range=custom&start=YYYY-MM-DD&end=YYYY-MM-DD
    """
    range_param = request.args.get("range", "30")
    today = date.today()

    if range_param == "custom":
        try:
            start_date = datetime.strptime(request.args.get("start", ""), "%Y-%m-%d").date()
            end_date = datetime.strptime(request.args.get("end", ""), "%Y-%m-%d").date()
        except ValueError:
            start_date, end_date = today - timedelta(days=29), today
    else:
        try:
            num_days = int(range_param)
        except ValueError:
            num_days = 30
        start_date, end_date = today - timedelta(days=num_days - 1), today

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    day_span = (end_date - start_date).days + 1
    days = [start_date + timedelta(days=i) for i in range(day_span)]

    # 1. Daily scans (bar chart)
    daily_scans = []
    for d in days:
        count = ScanLog.query.filter(db.func.date(ScanLog.timestamp) == d).count()
        daily_scans.append({"date": d.strftime("%Y-%m-%d"), "count": count})

    # 2. Mismatches by recognized make (horizontal bar)
    mismatch_scans = ScanLog.query.filter(
        ScanLog.matched == False,  # noqa: E712
        db.func.date(ScanLog.timestamp) >= start_date,
        db.func.date(ScanLog.timestamp) <= end_date,
    ).all()
    make_counts = {}
    for s in mismatch_scans:
        make = s.recognized_make or "Unknown"
        make_counts[make] = make_counts.get(make, 0) + 1
    mismatches_by_make = sorted(
        [{"make": m, "count": c} for m, c in make_counts.items()],
        key=lambda row: row["count"], reverse=True
    )

    # 3. Stolen vehicles recovered over time (resolved stolen reports, line chart)
    recovered_reports = OwnerReport.query.filter(
        OwnerReport.report_type == "stolen",
        OwnerReport.is_active == False,  # noqa: E712
        OwnerReport.resolved_at.isnot(None),
        db.func.date(OwnerReport.resolved_at) >= start_date,
        db.func.date(OwnerReport.resolved_at) <= end_date,
    ).all()
    recovered_by_day = {}
    for r in recovered_reports:
        d = r.resolved_at.date().strftime("%Y-%m-%d")
        recovered_by_day[d] = recovered_by_day.get(d, 0) + 1
    recovered_over_time = [{"date": d.strftime("%Y-%m-%d"), "count": recovered_by_day.get(d.strftime("%Y-%m-%d"), 0)} for d in days]

    # 4. Officer activity / performance (scans, mismatches, stolen recoveries per officer)
    officer_scans = ScanLog.query.filter(
        db.func.date(ScanLog.timestamp) >= start_date,
        db.func.date(ScanLog.timestamp) <= end_date,
    ).all()
    officer_stats = {}
    for s in officer_scans:
        name = s.officer.full_name if s.officer else "Unknown"
        row = officer_stats.setdefault(name, {"officer": name, "total_scans": 0, "mismatches": 0, "stolen_recoveries": 0})
        row["total_scans"] += 1
        if not s.matched:
            row["mismatches"] += 1
        if s.stolen_flag:
            row["stolen_recoveries"] += 1

    officer_performance = sorted(officer_stats.values(), key=lambda row: row["total_scans"], reverse=True)
    officer_activity = [{"officer": row["officer"], "count": row["total_scans"]} for row in officer_performance]

    # PHASE 4: summary stats + recent scans table for the PDF export
    summary = {
        "total_scans": len(officer_scans),
        "total_mismatches": sum(r["mismatches"] for r in officer_performance),
        "total_stolen": sum(r["stolen_recoveries"] for r in officer_performance),
        "total_officers": len(officer_performance),
    }

    recent_scans_qs = ScanLog.query.filter(
        db.func.date(ScanLog.timestamp) >= start_date,
        db.func.date(ScanLog.timestamp) <= end_date,
    ).order_by(ScanLog.timestamp.desc()).limit(20).all()

    recent_scans = [{
        "timestamp": s.timestamp.strftime("%Y-%m-%d %H:%M"),
        "plate_number": s.plate_number,
        "officer": s.officer.full_name if s.officer else "Unknown",
        "status": "stolen" if s.stolen_flag else ("mismatch" if not s.matched else "clear"),
    } for s in recent_scans_qs]

    return jsonify({
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "daily_scans": daily_scans,
        "mismatches_by_make": mismatches_by_make,
        "recovered_over_time": recovered_over_time,
        "officer_activity": officer_activity,
        "officer_performance": officer_performance,
        "summary": summary,
        "recent_scans": recent_scans,
    })


# ------------------------------------------------------------------
# PHASE 4: Simulated SMS/alert log
# ------------------------------------------------------------------

@app.route("/admin/alerts")
@admin_login_required
def admin_alerts():
    """
    PHASE 4: Shows the full history of simulated priority alerts
    (STOLEN/MISMATCH) dispatched by send_alert() — useful for demoing
    "here's the alert history" during defense.
    """
    alerts = AlertLog.query.order_by(AlertLog.created_at.desc()).limit(200).all()
    return render_template(
        "alerts.html",
        alerts=alerts,
        alert_recipient=app.config.get("ALERT_RECIPIENT", "control-room@autoverify.local"),
    )


# ------------------------------------------------------------------
# PHASE 3: System health page
# ------------------------------------------------------------------

@app.route("/health")
@officer_login_required
def health():
    db_size_bytes = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    last_scan = ScanLog.query.order_by(ScanLog.timestamp.desc()).first()

    health_data = {
        "ocr_available": is_ocr_available(),
        "classifier_loaded": is_classifier_loaded(),
        "db_size_kb": round(db_size_bytes / 1024, 1),
        "vehicle_count": Vehicle.query.count(),
        "officer_count": Officer.query.count(),
        "scan_count": ScanLog.query.count(),
        "active_stolen_count": OwnerReport.query.filter_by(report_type="stolen", is_active=True).count(),
        "last_scan_at": last_scan.timestamp if last_scan else None,
        "last_scan_plate": last_scan.plate_number if last_scan else None,
    }
    return render_template("health.html", health=health_data)


# ------------------------------------------------------------------
# DB init / seed helpers
# ------------------------------------------------------------------

def seed_demo_data():
    """Seed a demo admin officer and a couple of demo vehicles for grading/testing."""
    if not Officer.query.filter_by(username="admin").first():
        admin_officer = Officer(
            username="admin",
            full_name="System Administrator",
            badge_number="ADM-001",
            is_admin=True,
        )
        admin_officer.set_password("admin123")
        db.session.add(admin_officer)

    if not Officer.query.filter_by(username="officer1").first():
        officer = Officer(
            username="officer1",
            full_name="Officer Musa Bello",
            badge_number="OFC-1042",
            is_admin=False,
        )
        officer.set_password("officer123")
        db.session.add(officer)

    if not Vehicle.query.filter_by(plate_number="ABC-123-XY").first():
        v1 = Vehicle(
            plate_number="ABC-123-XY",
            owner_name="Chinedu Okafor",
            owner_phone="08012345678",
            owner_email="chinedu@example.com",
            make="Toyota",
            model="Camry",
            year=2019,
            colour="white",
        )
        v1.set_password("password123")
        db.session.add(v1)

    if not Vehicle.query.filter_by(plate_number="LND-456-KJ").first():
        v2 = Vehicle(
            plate_number="LND-456-KJ",
            owner_name="Amaka Nwosu",
            owner_phone="08087654321",
            owner_email="amaka@example.com",
            make="Honda",
            model="Accord",
            year=2021,
            colour="black",
        )
        v2.set_password("password123")
        db.session.add(v2)

    db.session.commit()


with app.app_context():
    db.create_all()
    seed_demo_data()


if __name__ == "__main__":
    # Render (and most PaaS hosts) inject a PORT env var — bind to it.
    # In production, Render runs this via Gunicorn instead (see Dockerfile),
    # so this block is really only used for local `python app.py` runs.
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug_mode, host="0.0.0.0", port=port)
