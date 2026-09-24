"""
Tests for owner report filing and the stolen vehicle hotlist workflow.
"""


class TestOwnerReports:
    def test_owner_can_file_stolen_report(self, owner_client):
        resp = owner_client.post(
            "/owner/report",
            data={"report_type": "stolen", "description": "Taken overnight"},
            follow_redirects=True,
        )
        assert b"STOLEN" in resp.data

    def test_stolen_report_appears_on_hotlist(self, owner_client, officer_client):
        owner_client.post("/owner/report", data={"report_type": "stolen", "description": "test"})
        resp = officer_client.get("/hotlist")
        assert b"ABC-123-XY" in resp.data

    def test_non_owner_cannot_file_report_without_login(self, client):
        resp = client.post(
            "/owner/report",
            data={"report_type": "stolen", "description": "x"},
            follow_redirects=True,
        )
        assert b"Please log in" in resp.data or b"Login" in resp.data

    def test_invalid_report_type_rejected(self, owner_client):
        resp = owner_client.post(
            "/owner/report",
            data={"report_type": "not_a_real_type", "description": "x"},
            follow_redirects=True,
        )
        assert b"Invalid report type" in resp.data

    def test_ownership_change_report_does_not_add_to_hotlist(self, owner_client, officer_client):
        owner_client.post(
            "/owner/report",
            data={"report_type": "ownership_change", "description": "selling car"},
        )
        resp = officer_client.get("/hotlist")
        assert b"No active stolen reports" in resp.data


class TestHotlist:
    def test_hotlist_requires_officer_login(self, client):
        resp = client.get("/hotlist", follow_redirects=True)
        assert b"Officer login required" in resp.data or b"Officer Login" in resp.data

    def test_resolve_removes_from_active_hotlist(self, owner_client, officer_client, app):
        owner_client.post("/owner/report", data={"report_type": "stolen", "description": "test"})

        with app.app_context():
            from models import OwnerReport
            report = OwnerReport.query.filter_by(report_type="stolen", is_active=True).first()
            report_id = report.id

        officer_client.post(f"/hotlist/resolve/{report_id}", follow_redirects=True)

        resp = officer_client.get("/hotlist")
        assert b"No active stolen reports" in resp.data

    def test_resolve_sets_resolved_at_timestamp(self, owner_client, officer_client, app):
        owner_client.post("/owner/report", data={"report_type": "stolen", "description": "test"})

        with app.app_context():
            from models import OwnerReport
            report = OwnerReport.query.filter_by(report_type="stolen", is_active=True).first()
            report_id = report.id

        officer_client.post(f"/hotlist/resolve/{report_id}")

        with app.app_context():
            from models import OwnerReport, db
            resolved = db.session.get(OwnerReport, report_id)
            assert resolved.is_active is False
            assert resolved.resolved_at is not None

    def test_admin_can_manually_add_to_hotlist(self, admin_client):
        resp = admin_client.post(
            "/admin/hotlist/add",
            data={"plate_number": "LND-456-KJ", "description": "Reported by police"},
            follow_redirects=True,
        )
        assert b"added to stolen hotlist" in resp.data

    def test_admin_add_unknown_plate_fails_gracefully(self, admin_client):
        resp = admin_client.post(
            "/admin/hotlist/add",
            data={"plate_number": "XXX-000-ZZ", "description": "nope"},
            follow_redirects=True,
        )
        assert b"No vehicle found" in resp.data
