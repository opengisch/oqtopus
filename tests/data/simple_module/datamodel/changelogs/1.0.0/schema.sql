CREATE SCHEMA IF NOT EXISTS oqtopus_test;

CREATE TABLE oqtopus_test.points (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
