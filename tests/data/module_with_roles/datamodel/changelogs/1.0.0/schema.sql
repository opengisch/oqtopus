CREATE SCHEMA IF NOT EXISTS oqtopus_test_roles;

CREATE TABLE oqtopus_test_roles.items (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    value NUMERIC(10,2)
);
