-- Create database for evergreen notes page relationships
-- Run this as a PostgreSQL superuser (e.g., postgres user)

-- Create database (uncomment if you need to create it)
-- CREATE DATABASE evergreen_notes;

-- Connect to the database
-- \c evergreen_notes;

-- Create pages table to store page metadata
CREATE TABLE IF NOT EXISTS pages (
    id VARCHAR(255) PRIMARY KEY,
    title TEXT NOT NULL,
    file_location TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create page_references table to store bidirectional relationships
-- parent_id references the page that contains the link
-- child_id references the page that is linked to
CREATE TABLE IF NOT EXISTS page_references (
    id SERIAL PRIMARY KEY,
    parent_id VARCHAR(255) NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    child_id VARCHAR(255) NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(parent_id, child_id)
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_page_references_parent ON page_references(parent_id);
CREATE INDEX IF NOT EXISTS idx_page_references_child ON page_references(child_id);
CREATE INDEX IF NOT EXISTS idx_pages_title ON pages(title);

-- Create a view to easily query children (pages referenced by a page)
CREATE OR REPLACE VIEW page_children AS
SELECT 
    p.id AS page_id,
    p.title AS page_title,
    p.file_location AS page_file_location,
    ARRAY_AGG(pr.child_id ORDER BY pr.child_id) AS children_ids,
    ARRAY_AGG(pc.title ORDER BY pr.child_id) AS children_titles
FROM pages p
LEFT JOIN page_references pr ON p.id = pr.parent_id
LEFT JOIN pages pc ON pr.child_id = pc.id
GROUP BY p.id, p.title, p.file_location;

-- Create a view to easily query parents (pages that reference a page)
CREATE OR REPLACE VIEW page_parents AS
SELECT 
    p.id AS page_id,
    p.title AS page_title,
    p.file_location AS page_file_location,
    ARRAY_AGG(pr.parent_id ORDER BY pr.parent_id) AS parent_ids,
    ARRAY_AGG(pp.title ORDER BY pr.parent_id) AS parent_titles
FROM pages p
LEFT JOIN page_references pr ON p.id = pr.child_id
LEFT JOIN pages pp ON pr.parent_id = pp.id
GROUP BY p.id, p.title, p.file_location;

-- Create a combined view with both children and parents
CREATE OR REPLACE VIEW page_relationships AS
SELECT 
    p.id AS page_id,
    p.title AS page_title,
    p.file_location AS page_file_location,
    COALESCE(pc.children_ids, ARRAY[]::VARCHAR[]) AS children_ids,
    COALESCE(pc.children_titles, ARRAY[]::TEXT[]) AS children_titles,
    COALESCE(pp.parent_ids, ARRAY[]::VARCHAR[]) AS parent_ids,
    COALESCE(pp.parent_titles, ARRAY[]::TEXT[]) AS parent_titles
FROM pages p
LEFT JOIN page_children pc ON p.id = pc.page_id
LEFT JOIN page_parents pp ON p.id = pp.page_id;

