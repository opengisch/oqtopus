CREATE SCHEMA IF NOT EXISTS oqtopus_test_app;

CREATE OR REPLACE VIEW oqtopus_test_app.points_view AS
SELECT id, name, description, created_at
FROM oqtopus_test.points;
