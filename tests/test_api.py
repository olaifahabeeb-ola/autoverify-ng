"""
Tests for the JSON API endpoints (offline hotlist cache, analytics) and
the system health page.
"""


class TestHotlistAPI:
    def test_requires_officer_login(self, client):
        resp = client.get("/api/hotlist")
        assert resp.status_code in (302, 401, 403)

    def test_returns_active_stolen_plates(self, officer_client, owner_client):
        owner_client.post("/owner/report", data={"report_type": "stolen", "description": "test"})
        resp = officer_client.get("/api/hotlist")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "ABC-123-XY" in data["plates"]

    def test_resolved_report_not_in_hotlist_api(self, officer_client, owner_client, app):
        owner_client.post("/owner/report", data={"report_type": "stolen", "description": "test"})
        with app.app_context():
            from models import OwnerReport
            report = OwnerReport.query.filter_by(report_type="stolen", is_active=True).first()
            report_id = report.id
        officer_client.post(f"/hotlist/resolve/{report_id}")

        resp = officer_client.get("/api/hotlist")
        assert "ABC-123-XY" not in resp.get_json()["plates"]


class TestAnalyticsAPI:
    def test_requires_admin(self, officer_client):
        resp = officer_client.get("/api/analytics-stats")
        assert resp.status_code in (302, 401, 403)

    def test_returns_expected_shape(self, admin_client):
        resp = admin_client.get("/api/analytics-stats?range=30")
        assert resp.status_code == 200
        data = resp.get_json()
        for key in ("daily_scans", "mismatches_by_make", "recovered_over_time",
                    "officer_activity", "officer_performance", "summary", "recent_scans"):
            assert key in data

    def test_custom_date_range(self, admin_client):
        resp = admin_client.get("/api/analytics-stats?range=custom&start=2026-01-01&end=2026-01-31")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["start_date"] == "2026-01-01"
        assert data["end_date"] == "2026-01-31"

    def test_officer_performance_counts_scans_correctly(self, admin_client, officer_client):
        officer_client.post("/verify", data={"manual_plate": "ABC-123-XY", "image_data": ""})
        officer_client.post("/verify", data={"manual_plate": "LND-456-KJ", "image_data": ""})

        resp = admin_client.get("/api/analytics-stats?range=30")
        data = resp.get_json()
        musa_row = next(r for r in data["officer_performance"] if r["officer"] == "Officer Musa Bello")
        assert musa_row["total_scans"] == 2


class TestHealthPage:
    def test_requires_officer_login(self, client):
        resp = client.get("/health", follow_redirects=True)
        assert b"Officer login required" in resp.data or b"Officer Login" in resp.data

    def test_loads_for_officer(self, officer_client):
        resp = officer_client.get("/health")
        assert resp.status_code == 200
        assert b"Registered Vehicles" in resp.data

    def test_reflects_vehicle_count(self, officer_client):
        resp = officer_client.get("/health")
        # 2 demo vehicles are seeded
        assert b"2" in resp.data
