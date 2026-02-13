#!/usr/bin/env bash
set -e

# Setup test databases for oqtopus integration tests
# This script creates the PostgreSQL databases and pg_service entries
# needed for running integration tests.
#
# Prerequisites:
#   - PostgreSQL server running locally
#   - A superuser role (default: postgres) that can create databases
#
# Usage:
#   ./scripts/setup_test_db.sh

export PGUSER=${PGUSER:-postgres}

# Determine the pg_service conf file location
if [ -z "$PGSYSCONFDIR" ]; then
    PGSERVICE_FILE="$HOME/.pg_service.conf"
else
    PGSERVICE_FILE="$PGSYSCONFDIR/pg_service.conf"
fi

PG_SERVICE="oqtopus_test"

echo "Adding service ${PG_SERVICE} to ${PGSERVICE_FILE}"

# Check if the service already exists
if grep -q "^\[${PG_SERVICE}\]" "$PGSERVICE_FILE" 2>/dev/null; then
    echo "Service ${PG_SERVICE} already exists in ${PGSERVICE_FILE}, skipping."
else
    printf "\n[${PG_SERVICE}]\nhost=localhost\ndbname=${PG_SERVICE}\nuser=postgres\npassword=postgres\n" >> "$PGSERVICE_FILE"
fi

# Drop and recreate the test database
psql -c "DROP DATABASE IF EXISTS ${PG_SERVICE};" "service=${PG_SERVICE} dbname=postgres" 2>/dev/null || \
    psql -c "DROP DATABASE IF EXISTS ${PG_SERVICE};" "host=localhost dbname=postgres user=postgres password=postgres"

psql -c "CREATE DATABASE ${PG_SERVICE};" "service=${PG_SERVICE} dbname=postgres" 2>/dev/null || \
    psql -c "CREATE DATABASE ${PG_SERVICE};" "host=localhost dbname=postgres user=postgres password=postgres"

echo "Test database '${PG_SERVICE}' created successfully."
