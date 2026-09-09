CREATE SCHEMA oqtopus_test_roles_app;

CREATE VIEW oqtopus_test_roles_app.items_view AS
SELECT id, name, value FROM oqtopus_test_roles.items;
