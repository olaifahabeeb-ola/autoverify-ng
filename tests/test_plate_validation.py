"""
Tests for Nigerian plate format validation (Phase 4) and the core
"one plate -> one owner" business rule.
"""

import pytest

from app import normalize_and_validate_plate


class TestPlateNormalization:
    """Unit tests for the validator itself — no HTTP involved."""

    @pytest.mark.parametrize("raw,expected", [
        ("ABC-123-XY", "ABC-123-XY"),
        ("abc-123-xy", "ABC-123-XY"),          # lowercase normalises to uppercase
        ("ABC123XY", "ABC-123-XY"),             # no separators
        ("ABJ 123 KJ", "ABJ-123-KJ"),           # spaces instead of dashes
        ("  abc-123-xy  ", "ABC-123-XY"),       # surrounding whitespace trimmed
    ])
    def test_valid_formats_normalize_correctly(self, raw, expected):
        plate, error = normalize_and_validate_plate(raw)
        assert error is None
        assert plate == expected

    @pytest.mark.parametrize("raw", [
        "AB-123-XY",        # only 2 letters in first group
        "ABCD-123-XY",      # 4 letters in first group
        "ABC-12-XY",        # only 2 digits
        "ABC-1234-XY",      # 4 digits
        "ABC-123-X",        # only 1 letter in last group
        "ABC-123-XYZ",      # 3 letters in last group
        "12C-123-XY",       # digit where a letter should be
        "ABC-12A-XY",       # letter where a digit should be
    ])
    def test_invalid_formats_rejected(self, raw):
        plate, error = normalize_and_validate_plate(raw)
        assert plate is None
        assert error is not None
        assert "AAA-123-AA" in error  # error message names the expected pattern

    def test_empty_plate_rejected_with_required_message(self):
        plate, error = normalize_and_validate_plate("")
        assert plate is None
        assert "required" in error.lower()


class TestRegistrationPlateRules:
    """Integration tests through the actual /register route."""

    VALID_REGISTRATION = {
        "owner_name": "New Owner",
        "owner_phone": "08000000099",
        "owner_email": "newowner@example.com",
        "password": "pass1234",
        "confirm_password": "pass1234",
        "make": "Kia",
        "model": "Rio",
        "year": "2021",
        "colour": "white",
    }

    def test_invalid_plate_format_is_rejected(self, client):
        data = {**self.VALID_REGISTRATION, "plate_number": "AB-12-XYZ"}
        resp = client.post("/register", data=data, follow_redirects=True)
        assert b"Invalid plate format" in resp.data

    def test_valid_plate_is_accepted_and_normalized(self, client):
        data = {**self.VALID_REGISTRATION, "plate_number": "kan123qw"}
        resp = client.post("/register", data=data, follow_redirects=True)
        assert b"Invalid plate format" not in resp.data

        with client.application.app_context():
            from models import Vehicle
            vehicle = Vehicle.query.filter_by(owner_email="newowner@example.com").first()
            assert vehicle is not None
            assert vehicle.plate_number == "KAN-123-QW"

    def test_duplicate_plate_is_rejected(self, client):
        """Core rule: one plate -> one owner. ABC-123-XY is already seeded."""
        data = {**self.VALID_REGISTRATION, "plate_number": "ABC-123-XY"}
        resp = client.post("/register", data=data, follow_redirects=True)
        assert b"already registered" in resp.data

        with client.application.app_context():
            from models import Vehicle
            # still only one vehicle with this plate
            assert Vehicle.query.filter_by(plate_number="ABC-123-XY").count() == 1

    def test_duplicate_email_is_rejected(self, client):
        data = {
            **self.VALID_REGISTRATION,
            "plate_number": "NEW-111-ZZ",
            "owner_email": "chinedu@example.com",  # already seeded
        }
        resp = client.post("/register", data=data, follow_redirects=True)
        assert b"already exists" in resp.data

    def test_mismatched_passwords_rejected(self, client):
        data = {**self.VALID_REGISTRATION, "plate_number": "NEW-222-ZZ", "confirm_password": "different"}
        resp = client.post("/register", data=data, follow_redirects=True)
        assert b"do not match" in resp.data
