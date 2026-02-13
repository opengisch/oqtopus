"""Pytest configuration and fixtures for oqtopus integration tests.

This module provides shared fixtures for integration tests that require a
PostgreSQL database. The test infrastructure follows the same patterns as
the pum library's test suite.

Prerequisites:
    - A running PostgreSQL server
    - A pg_service entry named 'oqtopus_test' (see scripts/setup_test_db.sh)
"""

import logging
from pathlib import Path
from unittest.mock import patch

import psycopg
import pytest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PG_SERVICE = "oqtopus_test"
TEST_DATA_DIR = Path(__file__).parent / "data"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pg_service_available(service: str) -> bool:
    """Check whether a pg_service connection can be established."""
    try:
        with psycopg.connect(f"service={service}") as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def pg_service():
    """Return the pg_service name used for integration tests."""
    if not _pg_service_available(PG_SERVICE):
        pytest.skip(f"PostgreSQL service '{PG_SERVICE}' is not available")
    return PG_SERVICE


@pytest.fixture(scope="session")
def test_data_dir():
    """Return the path to the test data directory."""
    return TEST_DATA_DIR


# ---------------------------------------------------------------------------
# Function-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def clean_db(pg_service):
    """Ensure a clean database state before and after each test.

    Drops all oqtopus test schemas and the pum_migrations table.
    """
    _clean_database(pg_service)
    yield
    _clean_database(pg_service)


@pytest.fixture(autouse=True)
def _no_blocking_dialogs():
    """Prevent modal dialogs from blocking tests.

    CriticalMessageBox.exec() and QMessageBox.information() will raise
    immediately instead of opening a window that waits for user input.
    """

    def _raise_on_critical_exec(self):
        raise AssertionError(f"Unexpected CriticalMessageBox: {self.text()}")

    with (
        patch(
            "oqtopus.utils.qt_utils.CriticalMessageBox.exec",
            _raise_on_critical_exec,
        ),
        patch(
            "oqtopus.gui.module_widget.QMessageBox.information",
            return_value=None,
        ),
    ):
        yield


def _clean_database(service: str):
    """Drop all test schemas and migration tables."""
    with psycopg.connect(f"service={service}") as conn:
        cur = conn.cursor()
        # Drop test schemas
        cur.execute(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name LIKE 'oqtopus_test%'"
        )
        schemas = [row[0] for row in cur.fetchall()]
        for schema in schemas:
            cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')

        # Drop pum migration table
        cur.execute("DROP TABLE IF EXISTS public.pum_migrations CASCADE;")

        # Drop test roles
        for role in ("oqtopus_test_viewer", "oqtopus_test_editor"):
            cur.execute(f"DROP ROLE IF EXISTS {role};")

        conn.commit()
