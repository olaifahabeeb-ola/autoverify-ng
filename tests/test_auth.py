"""
Tests for owner login, officer login, and role-based access control.
"""


class TestOwnerLogin:
    def test_correct_credentials_succeed(self, client):
        resp = client.post(
            "/login",
            data={"email": "chinedu@example.com", "password": "password123"},
            follow_redirects=True,
        )
        assert b"My Vehicle" in resp.data or resp.status_code == 200
        assert b"Invalid email or password" not in resp.data

    def test_wrong_password_rejected(self, client):
        resp = client.post(
            "/login",
            data={"email": "chinedu@example.com", "password": "wrongpassword"},
            follow_redirects=True,
        )
        assert b"Invalid email or password" in resp.data

    def test_unknown_email_rejected(self, client):
        resp = client.post(
            "/login",
            data={"email": "nobody@example.com", "password": "password123"},
            follow_redirects=True,
        )
        assert b"Invalid email or password" in resp.data

    def test_owner_dashboard_requires_login(self, client):
        resp = client.get("/owner/dashboard", follow_redirects=True)
        assert b"Please log in" in resp.data or b"Login" in resp.data

    def test_owner_dashboard_accessible_after_login(self, owner_client):
        resp = owner_client.get("/owner/dashboard")
        assert resp.status_code == 200
        assert b"ABC-123-XY" in resp.data


class TestOfficerLogin:
    def test_correct_credentials_succeed(self, client):
        resp = client.post(
            "/officer/login",
            data={"username": "officer1", "password": "officer123"},
            follow_redirects=True,
        )
        assert b"Invalid officer credentials" not in resp.data

    def test_wrong_password_rejected(self, client):
        resp = client.post(
            "/officer/login",
            data={"username": "officer1", "password": "wrong"},
            follow_redirects=True,
        )
        assert b"Invalid officer credentials" in resp.data

    def test_verify_page_requires_officer_login(self, client):
        resp = client.get("/verify", follow_redirects=True)
        assert b"Officer login required" in resp.data or b"Officer Login" in resp.data


class TestAccessControl:
    """Non-admin officers must not reach admin-only routes."""

    def test_admin_panel_blocked_for_regular_officer(self, officer_client):
        resp = officer_client.get("/admin", follow_redirects=True)
        assert b"Admin access required" in resp.data or b"Officer Login" in resp.data

    def test_admin_analytics_blocked_for_regular_officer(self, officer_client):
        resp = officer_client.get("/admin/analytics", follow_redirects=True)
        assert b"Admin access required" in resp.data or b"Officer Login" in resp.data

    def test_admin_alerts_blocked_for_regular_officer(self, officer_client):
        resp = officer_client.get("/admin/alerts", follow_redirects=True)
        assert b"Admin access required" in resp.data or b"Officer Login" in resp.data

    def test_admin_panel_accessible_for_admin(self, admin_client):
        resp = admin_client.get("/admin")
        assert resp.status_code == 200
        assert b"Admin Panel" in resp.data

    def test_officer_routes_blocked_for_owner(self, owner_client):
        """A logged-in vehicle owner has no officer session and should still be
        redirected away from officer-only routes."""
        resp = owner_client.get("/verify", follow_redirects=True)
        assert b"Officer login required" in resp.data or b"Officer Login" in resp.data

    def test_logout_clears_both_sessions(self, admin_client):
        admin_client.get("/logout")
        resp = admin_client.get("/admin", follow_redirects=True)
        assert b"Admin access required" in resp.data or b"Officer Login" in resp.data
