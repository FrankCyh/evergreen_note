# Evergreen Notes Project

A comprehensive toolkit for downloading, analyzing, and managing evergreen notes from web sources. This project provides tools for crawling note websites, extracting relationships between notes, filtering notes based on relevance, and storing the data in a PostgreSQL database for advanced querying.

## Overview

This project is designed to work with evergreen note systems (like Andy Matuschak's working notes). It provides a complete pipeline from downloading notes to analyzing their relationships and storing them in a structured database.

## Features

- **Web Crawling**: Download notes from websites with DFS traversal, checkpointing, and resume capability
- **Reference Extraction**: Extract and map relationships between notes from HTML files
- **Note Filtering**: Interactive DFS-based filtering to select relevant notes
- **Database Storage**: Store notes and their relationships in PostgreSQL with bidirectional relationship tracking
- **Query Tools**: SQL views and queries for analyzing note connections

## Project Structure

```
evergreen_note/
├── src/
│   ├── crawler/          # Web crawler for downloading notes
│   │   └── web_crawler.py
│   ├── ref/              # Reference extraction tools
│   │   ├── extract_references.py
│   │   └── page_references.json
│   ├── filter/           # Note filtering tools
│   │   ├── dfs_filter.py
│   │   ├── filtered_notes.json
│   │   └── filtered_notes_checkpoint.json
│   ├── db/               # Database tools
│   │   ├── insert_to_database.py
│   │   ├── create_database.sql
│   │   └── DATABASE_SETUP.md
│   └── util/             # Shared utilities
│       └── note_utils.py
├── webpage/              # Downloaded HTML files
├── requirements.txt
└── README.md
```

## Installation

1. Clone the repository
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set up PostgreSQL database (see [Database Setup](#database-setup))

## Usage

### 1. Crawl Notes

Download notes from a website starting from a seed page:

```bash
python src/crawler/web_crawler.py
```

The crawler will:
- Start from a seed note (default: "About these notes")
- Follow all note references using DFS traversal
- Save HTML files to the `webpage/` directory
- Support checkpointing for resuming interrupted downloads

### 2. Extract References

Extract relationships between notes from downloaded HTML files:

```bash
python src/ref/extract_references.py
```

This will:
- Parse all HTML files in `webpage/`
- Extract page IDs and titles
- Find all internal links within MarkdownContainer divs
- Generate `src/ref/page_references.json` with the relationship data

### 3. Filter Notes

Interactively filter notes using DFS traversal:

```bash
python src/filter/dfs_filter.py
```

The filter allows you to:
- Traverse notes starting from a seed page
- Interactively decide which notes to keep
- Build a filtered subset of notes
- Save results to `src/filter/filtered_notes.json`

### 4. Store in Database

Insert the reference data into PostgreSQL:

```bash
python src/db/insert_to_database.py
```

This will:
- Read `src/ref/page_references.json`
- Create/update pages in the database
- Store bidirectional relationships
- Provide statistics about the database

## Database Setup

### Prerequisites

- PostgreSQL installed and running
- Python dependencies installed

### Step 1: Create Database

```bash
createdb -U postgres evergreen_notes
```

### Step 2: Create Schema

```bash
psql -U postgres -d evergreen_notes -f src/db/create_database.sql
```

### Step 3: Insert Data

```bash
python src/db/insert_to_database.py
```

For detailed database setup instructions, see [src/db/DATABASE_SETUP.md](src/db/DATABASE_SETUP.md).

## Database Schema

### Tables

- **pages**: Stores page metadata (id, title, file_location)
- **page_references**: Stores bidirectional relationships (parent_id, child_id)

### Views

- **page_children**: Shows pages referenced by each page
- **page_parents**: Shows pages that reference each page
- **page_relationships**: Combined view with both children and parents

### Example Queries

```sql
-- Get all pages referenced by a specific page
SELECT * FROM page_children WHERE page_id = 'zGfjkW1ociSmSUCLcpbhKjf';

-- Get all pages that reference a specific page
SELECT * FROM page_parents WHERE page_id = 'zGfjkW1ociSmSUCLcpbhKjf';

-- Find pages with most references
SELECT 
    page_id,
    page_title,
    array_length(children_ids, 1) AS num_children,
    array_length(parent_ids, 1) AS num_parents
FROM page_relationships
ORDER BY num_children DESC
LIMIT 10;
```

## Configuration

### Crawler Configuration

Edit `src/crawler/web_crawler.py` to change:
- `BASE_URL`: Target website URL
- `OUTPUT_DIR`: Directory for downloaded HTML files
- `CHECKPOINT_FILE`: Location for checkpoint file
- `DELAY`: Delay between requests (seconds)

### Filter Configuration

Edit `src/filter/dfs_filter.py` to change:
- `BASE_URL`: Base URL for building stacked URLs
- `WEBPAGE_DIR`: Directory containing HTML files
- `OUTPUT_FILE`: Output file for filtered notes
- `START_NOTE_ID`: Starting note ID for filtering

### Database Configuration

Use command-line arguments or environment variables:

```bash
python src/db/insert_to_database.py \
    --dbname evergreen_notes \
    --user postgres \
    --host localhost \
    --port 5432 \
    --json-file src/ref/page_references.json
```

Or set `PGPASSWORD` environment variable:

```bash
export PGPASSWORD=your_password
python src/db/insert_to_database.py
```

## Utilities

The `src/util/note_utils.py` module provides shared utilities:

- `sanitize_filename()`: Clean filenames for filesystem safety
- `get_file_path()`: Generate file paths for notes
- `extract_note_links()`: Extract note links from HTML content
- `get_note_name_from_file()`: Get note name from filename
- `read_note_from_file()`: Read note HTML from file
- `find_note_file()`: Find note file by ID

## Workflow Example

1. **Download notes**:
   ```bash
   python src/crawler/web_crawler.py
   ```

2. **Extract relationships**:
   ```bash
   python src/ref/extract_references.py
   ```

3. **Filter notes** (optional):
   ```bash
   python src/filter/dfs_filter.py
   ```

4. **Store in database**:
   ```bash
   python src/db/insert_to_database.py
   ```

5. **Query the database**:
   ```bash
   psql -U postgres -d evergreen_notes
   ```

## Dependencies

- `requests`: HTTP library for web crawling
- `beautifulsoup4`: HTML parsing
- `psycopg2-binary`: PostgreSQL database adapter

## Notes

- The `webpage/` directory contains all downloaded HTML files
- All scripts can be run from the project root
- File paths are resolved relative to the project root
- Checkpoint files allow resuming interrupted operations

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]

