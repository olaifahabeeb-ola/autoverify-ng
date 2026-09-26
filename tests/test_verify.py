"""
Tests for the core scan/verify logic in build_and_persist_scan_result().

The TestManualEntryNoPhoto class is a REGRESSION SUITE for a real bug we
shipped and fixed: manual plate entry with no camera photo used to call
recognize_vehicle() anyway, which returned a RANDOM placeholder colour/
make/model when there was no image to look at. That random guess was then
compared against the vehicle's real registered attributes, producing a
false "MISMATCH" alert on a plate nobody had actually looked at (roughly
an 89% false-positive rate, since there are 9 colours in the fallback
palette). These tests make sure that never regresses.
"""

import cv2
import numpy as np
import base64


def _make_plate_image(text):
    """Build a synthetic image containing a rectangle with plate-style text,
    for exercising the real OCR + recognition pipeline end to end."""
    img = np.full((400, 600, 3), 200, dtype=np.uint8)
    cv2.rectangle(img, (150, 150), (450, 230), (255, 255, 255), -1)
    cv2.rectangle(img, (150, 150), (450, 230), (0, 0, 0), 3)
    cv2.putText(img, text, (170, 205), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 3, cv2.LINE_AA)
    ok, buf = cv2.imencode(".png", img)
    return "data:image/png;base64," + base64.b64encode(buf).decode()


class TestManualEntryNoPhoto:
    """Regression tests for the false-mismatch bug (see module docstring)."""

    def test_no_false_mismatch_across_many_runs(self, officer_client):
        """The core regression test: repeat a manual check on a real,
        correctly-registered vehicle many times with no photo captured.
        Before the fix this failed ~89% of the time; it must now never
        report a mismatch, since there is nothing to compare."""
        for _ in range(30):
            resp = officer_client.post(
                "/verify", data={"manual_plate": "ABC-123-XY", "image_data": ""}
            )
            assert b"Mismatch Detected" not in resp.data
            assert b"Mismatch in:" not in resp.data

    def test_shows_plate_checked_badge_not_verified(self, officer_client):
        resp = officer_client.post(
            "/verify", data={"manual_plate": "ABC-123-XY", "image_data": ""}
        )
        assert b"Plate Checked (No Photo)" in resp.data
        # Must not claim full visual "Verified" status without a photo
        assert b">Verified<" not in resp.data

    def test_no_fabricated_vehicle_attributes_shown(self, officer_client):
        resp = officer_client.post(
            "/verify", data={"manual_plate": "ABC-123-XY", "image_data": ""}
        )
        assert b"Not captured" in resp.data or b"No photo on file" in resp.data

    def test_stolen_vehicle_still_flagged_without_photo(self, officer_client, owner_client):
        """The stolen check is a real database lookup, not a visual guess —
        it must still fire correctly even with no photo captured."""
        owner_client.post("/owner/report", data={"report_type": "stolen", "description": "test"})
        resp = officer_client.post(
            "/verify", data={"manual_plate": "ABC-123-XY", "image_data": ""}
        )
        assert b"Stolen Vehicle" in resp.data

    def test_scan_log_records_visually_verified_false(self, officer_client, app):
        officer_client.post("/verify", data={"manual_plate": "ABC-123-XY", "image_data": ""})
        with app.app_context():
            from models import ScanLog
            scan = ScanLog.query.order_by(ScanLog.id.desc()).first()
            assert scan.visually_verified is False
            assert scan.recognized_make is None


class TestManualEntryWithPhoto:
    """When a real photo IS captured alongside manual entry, full visual
    comparison should still run exactly as before."""

    def test_visual_comparison_still_runs(self, officer_client):
        image = _make_plate_image("ABC-123-XY")
        resp = officer_client.post(
            "/verify", data={"manual_plate": "ABC-123-XY", "image_data": image}
        )
        assert b"Not captured" not in resp.data
        assert b"Recognized Vehicle" in resp.data

    def test_scan_log_records_visually_verified_true(self, officer_client, app):
        image = _make_plate_image("ABC-123-XY")
        officer_client.post("/verify", data={"manual_plate": "ABC-123-XY", "image_data": image})
        with app.app_context():
            from models import ScanLog
            scan = ScanLog.query.order_by(ScanLog.id.desc()).first()
            assert scan.visually_verified is True
            assert scan.recognized_make is not None


class TestCameraCapture:
    def test_real_photo_ocr_reads_plate_correctly(self, officer_client):
        image = _make_plate_image("ABC-123-XY")
        resp = officer_client.post("/verify", data={"image_data": image, "gps_lat": "9.05", "gps_lon": "7.49"})
        assert resp.status_code == 200
        assert b"ABC-123-XY" in resp.data

    def test_camera_capture_has_priority_over_manual_plate(self, officer_client):
        image = _make_plate_image("ABC-123-XY")
        resp = officer_client.post(
            "/verify",
            data={"image_data": image, "manual_plate": "ZZZ-999-QQ", "gps_lat": "9.05", "gps_lon": "7.49"},
        )
        assert resp.status_code == 200
        assert b"ABC-123-XY" in resp.data
        assert b"ZZZ-999-QQ" not in resp.data

    def test_unregistered_plate_flagged(self, officer_client):
        image = _make_plate_image("ZZZ-999-QQ")
        resp = officer_client.post("/verify", data={"image_data": image})
        # ZZZ-999-QQ is not seeded, so this should come back unregistered
        assert b"Unregistered" in resp.data or b"UNREGISTERED VEHICLE" in resp.data

    def test_gps_coordinates_stored_and_linked(self, officer_client, app):
        image = _make_plate_image("ABC-123-XY")
        officer_client.post("/verify", data={"image_data": image, "gps_lat": "9.05", "gps_lon": "7.49"})
        with app.app_context():
            from models import ScanLog
            scan = ScanLog.query.order_by(ScanLog.id.desc()).first()
            assert scan.gps_lat == 9.05
            assert scan.gps_lon == 7.49
