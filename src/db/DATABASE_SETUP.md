# Database Setup Guide

This guide explains how to set up the PostgreSQL database for tracking page relationships.

## Prerequisites

1. PostgreSQL installed and running
2. Python dependencies installed: `pip install -r requirements.txt`

## Step 1: Create the Database

### Option A: Using psql command line

```bash
# Connect to PostgreSQL as superuser
psql -U postgres

# Create the database
CREATE DATABASE evergreen_notes;

# Exit psql
\q
```

### Option B: Using createdb command

```bash
createdb -U postgres evergreen_notes
```

## Step 2: Create Tables and Schema

Run the SQL script to create tables, indexes, and views:

```bash
cd src/db
psql -U postgres -d evergreen_notes -f create_database.sql
```

Or from the project root:

```bash
psql -U postgres -d evergreen_notes -f src/db/create_database.sql
```

Or if you need to provide a password:

```bash
PGPASSWORD=your_password psql -U postgres -d evergreen_notes -f src/db/create_database.sql
```

## Step 3: Insert Data

Run the Python script to insert data from `page_references.json`:

```bash
cd src/db
python insert_to_database.py
```

Or from the project root:

```bash
python src/db/insert_to_database.py
```

### With custom database settings:

```bash
python src/db/insert_to_database.py \
    --dbname evergreen_notes \
    --user postgres \
    --host localhost \
    --port 5432
```

## Database Schema

### Tables

1. **pages**: Stores page metadata
   - `id` (VARCHAR, PRIMARY KEY): Page ID
   - `title` (TEXT): Page title
   - `file_location` (TEXT): HTML filename
   - `created_at` (TIMESTAMP): Creation timestamp
   - `updated_at` (TIMESTAMP): Last update timestamp

2. **page_references**: Stores bidirectional relationships
   - `id` (SERIAL, PRIMARY KEY): Auto-incrementing ID
   - `parent_id` (VARCHAR): Page that contains the reference (foreign key)
   - `child_id` (VARCHAR): Page that is referenced (foreign key)
   - `created_at` (TIMESTAMP): Creation timestamp
   - UNIQUE constraint on (parent_id, child_id)

### Views

1. **page_children**: Shows pages referenced by each page
   - `page_id`: The page ID
   - `page_title`: The page title
   - `page_file_location`: The file location
   - `children_ids`: Array of referenced page IDs
   - `children_titles`: Array of referenced page titles

2. **page_parents**: Shows pages that reference each page
   - `page_id`: The page ID
   - `page_title`: The page title
   - `page_file_location`: The file location
   - `parent_ids`: Array of page IDs that reference this page
   - `parent_titles`: Array of titles of pages that reference this page

3. **page_relationships**: Combined view with both children and parents
   - All fields from both `page_children` and `page_parents`

## Example Queries

### Get all children (pages referenced by a page):

```sql
SELECT * FROM page_children WHERE page_id = 'zGfjkW1ociSmSUCLcpbhKjf';
```

### Get all parents (pages that reference a page):

```sql
SELECT * FROM page_parents WHERE page_id = 'zGfjkW1ociSmSUCLcpbhKjf';
```

### Get complete relationship information:

```sql
SELECT * FROM page_relationships WHERE page_id = 'zGfjkW1ociSmSUCLcpbhKjf';
```

### Find pages with most references:

```sql
SELECT 
    page_id,
    page_title,
    array_length(children_ids, 1) AS num_children,
    array_length(parent_ids, 1) AS num_parents
FROM page_relationships
ORDER BY num_children DESC
LIMIT 10;
```

### Find orphaned pages (pages with no references):

```sql
SELECT id, title 
FROM pages 
WHERE id NOT IN (SELECT DISTINCT parent_id FROM page_references)
  AND id NOT IN (SELECT DISTINCT child_id FROM page_references);
```

## Troubleshooting

### Connection Issues

If you get connection errors, check:
1. PostgreSQL is running: `pg_isready`
2. Database exists: `psql -U postgres -l | grep evergreen_notes`
3. User permissions: Ensure your user has CREATE and INSERT privileges

### Permission Issues

If you get permission errors, you may need to grant privileges:

```sql
GRANT ALL PRIVILEGES ON DATABASE evergreen_notes TO your_username;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_username;
```

