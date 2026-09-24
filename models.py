from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


def utcnow():
    """Current UTC time as a naive datetime (matches the historical
    datetime.utcnow() behavior, without using the now-deprecated call).
    Kept naive deliberately so it's directly comparable with every
    existing timestamp already stored this way, and with date.today()
    in app.py's analytics date-range filtering."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Vehicle(db.Model):
    __tablename__ = "vehicles"

    id = db.Column(db.Integer, primary_key=True)
    plate_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    owner_name = db.Column(db.String(120), nullable=False)
    owner_phone = db.Column(db.String(30), nullable=False)
    owner_email = db.Column(db.String(120), unique=True, nullable=False)
    owner_password_hash = db.Column(db.String(255), nullable=False)

    make = db.Column(db.String(50), nullable=False)
    model = db.Column(db.String(50), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    colour = db.Column(db.String(30), nullable=False)
    image_path = db.Column(db.String(255), nullable=True)

    registered_at = db.Column(db.DateTime, default=utcnow)

    reports = db.relationship("OwnerReport", backref="vehicle", lazy=True,
                               cascade="all, delete-orphan")

    def set_password(self, raw_password):
        self.owner_password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.owner_password_hash, raw_password)

    def active_report(self, report_type):
        """Return the most recent active report of a given type, if any."""
        for r in sorted(self.reports, key=lambda x: x.created_at, reverse=True):
            if r.is_active and r.report_type == report_type:
                return r
        return None


class OwnerReport(db.Model):
    __tablename__ = "owner_reports"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False)
    report_type = db.Column(db.String(30), nullable=False)  # stolen / ownership_change / written_off
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)  # PHASE 3: for "recovered vehicles" analytics


class Officer(db.Model):
    __tablename__ = "officers"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    badge_number = db.Column(db.String(30), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)


class ScanLog(db.Model):
    __tablename__ = "scan_logs"

    id = db.Column(db.Integer, primary_key=True)
    officer_id = db.Column(db.Integer, db.ForeignKey("officers.id"), nullable=False)
    plate_number = db.Column(db.String(20), nullable=False)
    recognized_make = db.Column(db.String(50), nullable=True)
    recognized_model = db.Column(db.String(50), nullable=True)
    recognized_colour = db.Column(db.String(30), nullable=True)
    matched = db.Column(db.Boolean, default=False)
    visually_verified = db.Column(db.Boolean, default=True)  # False = plate-only check (manual entry, no photo captured)
    mismatch_detail = db.Column(db.Text, nullable=True)
    report_flag = db.Column(db.Boolean, default=False)
    stolen_flag = db.Column(db.Boolean, default=False)
    gps_lat = db.Column(db.Float, nullable=True)
    gps_lon = db.Column(db.Float, nullable=True)
    timestamp = db.Column(db.DateTime, default=utcnow)

    officer = db.relationship("Officer", backref="scans", lazy=True)


class AlertLog(db.Model):
    """
    PHASE 2: Priority alert log — created whenever a scan comes back
    STOLEN or MISMATCH. Represents the "real alert system": a full-screen
    red alert + sound is shown to the officer in the browser, and this row
    is the auditable record of the corresponding simulated email/SMS
    dispatch (see send_alert() in app.py).
    """
    __tablename__ = "alert_logs"

    id = db.Column(db.Integer, primary_key=True)
    scan_log_id = db.Column(db.Integer, db.ForeignKey("scan_logs.id"), nullable=True)
    alert_type = db.Column(db.String(20), nullable=False)  # "stolen" | "mismatch"
    plate_number = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=False)
    channel = db.Column(db.String(20), default="console")  # "console" | "email" | "sms"
    delivered = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    scan_log = db.relationship("ScanLog", backref="alerts", lazy=True)


class OwnerNotification(db.Model):
    """
    PHASE 3: Simulated owner notification log. Created whenever a scan
    detects an active STOLEN report on a vehicle, representing "an SMS/
    email was sent to the owner." Always logged to console + notifications
    are visible in the Admin panel for audit purposes.
    """
    __tablename__ = "owner_notifications"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False)
    scan_log_id = db.Column(db.Integer, db.ForeignKey("scan_logs.id"), nullable=True)
    message = db.Column(db.Text, nullable=False)
    channel = db.Column(db.String(20), default="console")  # "console" | "email" | "sms"
    delivered = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    vehicle = db.relationship("Vehicle", backref="notifications", lazy=True)
    scan_log = db.relationship("ScanLog", backref="owner_notifications", lazy=True)


class BatchUpload(db.Model):
    """
    PHASE 3: Records a batch-processing run (up to 10 images uploaded at
    once at /batch) so officers/admins have an audit trail of bulk scans,
    separate from individual live-camera ScanLog entries.
    """
    __tablename__ = "batch_uploads"

    id = db.Column(db.Integer, primary_key=True)
    officer_id = db.Column(db.Integer, db.ForeignKey("officers.id"), nullable=False)
    image_count = db.Column(db.Integer, default=0)
    stolen_count = db.Column(db.Integer, default=0)
    mismatch_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=utcnow)

    officer = db.relationship("Officer", backref="batch_uploads", lazy=True)
