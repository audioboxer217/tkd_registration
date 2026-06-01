"""Unit tests for pure helper functions in models.py."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

base_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(base_path))

os.environ.setdefault("COMPETITION_NAME", "Test Championship")
os.environ.setdefault("CONTACT_EMAIL", "contact@example.com")
os.environ.setdefault("EARLY_REG_DATE", "January 01, 2025")
os.environ.setdefault("REG_CLOSE_DATE", "December 31, 2099")
os.environ.setdefault("STRIPE_API_KEY", "sk_test_placeholder")
os.environ.setdefault("CONFIG_BUCKET", "test-config-bucket")
os.environ.setdefault("PUBLIC_MEDIA_BUCKET", "test-media-bucket")

from app import create_app  # noqa: E402
from models import School, db  # noqa: E402
from models import age_group_for  # noqa: E402

_test_app = create_app(
    test_config={
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
    }
)

with _test_app.app_context():
    db.create_all()


@pytest.mark.parametrize(
    "age, expected",
    [
        # too_young boundary
        (0,   "too_young"),
        (3,   "too_young"),
        # dragon
        (4,   "dragon"),
        (7,   "dragon"),
        # tiger
        (8,   "tiger"),
        (9,   "tiger"),
        # youth
        (10,  "youth"),
        (11,  "youth"),
        # cadet
        (12,  "cadet"),
        (14,  "cadet"),
        # junior
        (15,  "junior"),
        (16,  "junior"),
        # senior boundaries
        (17,  "senior"),
        (32,  "senior"),
        # ultra boundaries
        (33,  "ultra"),
        (99,  "ultra"),
        # too_old (outside map)
        (100, "too_old"),
        (-1,  "too_old"),
        # string input coercion
        ("17", "senior"),
    ],
)
def test_age_group_for(age, expected):
    assert age_group_for(age) == expected


class TestSchoolGetOrCreate:
    def test_empty_name_returns_none(self):
        with _test_app.app_context():
            school, is_new = School.get_or_create(None)
            assert school is None
            assert is_new is False

    def test_blank_name_returns_none(self):
        with _test_app.app_context():
            school, is_new = School.get_or_create("")
            assert school is None
            assert is_new is False

    def test_new_school_created_with_id(self):
        with _test_app.app_context():
            school, is_new = School.get_or_create("BrandNewSchool_unique1")
            assert is_new is True
            assert school is not None
            assert school.name == "BrandNewSchool_unique1"
            assert school.id is not None
            db.session.rollback()

    def test_existing_school_not_duplicated(self):
        with _test_app.app_context():
            original = School(name="ExistingSchool_unique2")
            db.session.add(original)
            db.session.commit()

            school, is_new = School.get_or_create("ExistingSchool_unique2")
            assert is_new is False
            assert school.id == original.id

    def test_savepoint_isolates_session_state_on_integrity_error(self):
        """Verifies that a concurrent-insert IntegrityError only rolls back the
        school insert, not other pending objects already in the session.

        With the old db.session.rollback() approach, 'pending' would be expunged
        from the session entirely. With begin_nested(), it survives and can commit.
        """
        from sqlalchemy import inspect as sa_inspect

        with _test_app.app_context():
            # Pre-commit a school so the duplicate insert triggers IntegrityError
            existing = School(name="ConflictSchool_unique3")
            db.session.add(existing)
            db.session.commit()

            # Add a different pending object to the session BEFORE calling get_or_create
            pending = School(name="PendingSchool_unique3")
            db.session.add(pending)

            # Simulate the race window: the first existence check misses the row
            # (school exists in DB but wasn't visible at query time), so get_or_create
            # tries to insert a duplicate and hits IntegrityError.
            call_count = [0]
            real_query = School.query

            mock_q = MagicMock()

            def mock_filter_by(**kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    # First check: simulate "not found" (the race window)
                    m = MagicMock()
                    m.first.return_value = None
                    return m
                # Subsequent calls (re-query in except block): use the real DB
                return real_query.filter_by(**kwargs)

            mock_q.filter_by.side_effect = mock_filter_by

            with patch.object(School, "query", mock_q):
                returned, is_new = School.get_or_create("ConflictSchool_unique3")

            assert is_new is False
            assert returned is not None
            assert returned.name == "ConflictSchool_unique3"

            # Key invariant: savepoint rollback must not discard other pending objects.
            # flush([school]) scopes the savepoint to only the school insert,
            # so pending is autoflush'd by the re-query AFTER the savepoint, then committed.
            # (With the old db.session.rollback(), pending.id would still be None here.)
            assert not sa_inspect(pending).detached
            assert pending.id is not None  # was autoflush'd into the outer transaction

            db.session.commit()
            assert School.query.filter_by(name="PendingSchool_unique3").first() is not None

            db.session.rollback()
