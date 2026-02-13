ALTER TABLE oqtopus_test.points ADD COLUMN geom TEXT;

CREATE TABLE oqtopus_test.categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

ALTER TABLE oqtopus_test.points ADD COLUMN category_id INTEGER REFERENCES oqtopus_test.categories(id);
