# Evergreen Notes Project

A comprehensive toolkit for downloading, analyzing, and managing [evergreen notes](https://notes.andymatuschak.org/Evergreen_notes) from web sources. This project provides tools for crawling note websites, extracting relationships between notes, filtering notes based on relevance, and storing the data in a PostgreSQL database for advanced querying.

## Overview

This project is designed to work with evergreen note systems (like Andy Matuschak's working notes). It provides a complete pipeline from downloading notes to analyzing their relationships and storing them in a structured database.

## Features

- **Web Crawling**: Download notes from websites with DFS traversal, checkpointing, and resume capability
- **Reference Extraction**: Extract and map relationships between notes from HTML files
- **Note Filtering**: Interactive DFS-based filtering to select relevant notes
- **Database Storage**: Store notes and their relationships in PostgreSQL with bidirectional relationship tracking
- **Notion Integration**: Create Notion pages from filtered notes, upload HTML content, and maintain bidirectional links
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
│   ├── notion/           # Notion integration tools
│   │   └── notion.py
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
- Create all pages in the database
- Store bidirectional relationships
- Provide statistics about the database

### 5. Upload to Notion

The Notion integration allows you to create Notion pages from your filtered notes and maintain consistency with the database.

#### First-Time Setup: Create All Pages

For the first time, create all Notion pages from filtered notes:

```python
# Load filtered notes
filtered_notes = load_filtered_notes("src/filter/filtered_notes.json")

# Connect to database
conn = get_db_connection()

# Create all Notion pages and update database with notion_id
asyncio.run(create_all_notion_pages_and_update_db(filtered_notes, conn))

conn.close()
```

This will:
- Create empty Notion pages for all filtered notes
- Update the `pages` table with `notion_id` for each created page
- Skip pages that already have a `notion_id`

#### First-Time Setup: Upload All Content

After creating all pages, upload HTML content to Notion:

```python
asyncio.run(upload_all_webpage_to_notion())
```

This will:
- Read HTML files for all pages with `notion_id`
- Parse HTML content into Notion blocks
- Convert href links to `notes.andymatuschak.org` into MentionPage references (if target page exists in Notion)
- Upload content to Notion pages

#### Incremental Updates: Upload New Pages

For adding new pages incrementally:

```python
# Upload a single new page
page_id = "z5E5QawiXCMbtNtupvxeoEX"
asyncio.run(upload_new_webpage_to_notion(page_id))
```

This function:
1. Validates that the page exists in the database and doesn't have a `notion_id`
2. Creates a new Notion page
3. Updates `notion_id` in the database (all other fields already exist in the database from step 4)
4. Uploads HTML content with href→MentionPage conversion
5. Updates the "📖 Related" property based on `page_references` table
6. Updates parent pages to replace href links with MentionPage references

## Database Setup

See [src/db/DATABASE_SETUP.md](src/db/DATABASE_SETUP.md).

## Database Schema

### Tables

- **pages**: Stores page metadata (id, title, file_location, notion_id)
  - `notion_id`: UUID of the corresponding Notion page (NULL if not yet created in Notion)
- **page_references**: Stores bidirectional relationships (parent_id, child_id)

### Views

- **page_children**: Shows pages referenced by each page
- **page_parents**: Shows pages that reference each page
- **page_relationships**: Combined view with both children and parents

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

5. **Upload to Notion** (optional):
   ```python
   filtered_notes = load_filtered_notes("src/filter/filtered_notes.json")
   conn = get_db_connection()
   asyncio.run(create_all_notion_pages_and_update_db(filtered_notes, conn))
   conn.close()
   
   # Then upload content
   asyncio.run(upload_all_webpage_to_notion())
   
   # For incremental updates:
   # asyncio.run(upload_new_webpage_to_notion("page_id"))
   ```

## Notion Integration Details

### Database Consistency

The Notion integration maintains consistency with the PostgreSQL database:

- **Pages Table**: The `notion_id` column stores the Notion page UUID for each page
- **Page References**: The `page_references` table is used to:
  - Populate the "📖 Related" property in Notion pages
  - Determine which href links should be converted to MentionPage references
- **Bidirectional Updates**: When uploading a new page:
  - The new page's "📖 Related" property includes both child and parent pages
  - Parent pages are automatically updated to replace href links with MentionPage references

### Link Conversion

The integration automatically converts links:
- **Href Links** → **MentionPage References**: Links to `notes.andymatuschak.org` are converted to Notion page mentions if the target page exists in Notion (has a `notion_id` in the database)
- **Unconverted Links**: Links to pages not yet in Notion remain as href links

### Workflow Modes

1. **First-Time Setup**: Use `create_all_notion_pages_and_update_db()` followed by `upload_all_webpage_to_notion()` to create all pages at once
2. **Incremental Updates**: Use `upload_new_webpage_to_notion(page_id)` to add individual new pages while maintaining all relationships

## Notes

- The `webpage/` directory contains all downloaded HTML files
- All scripts can be run from the project root
- File paths are resolved relative to the project root
- Checkpoint files allow resuming interrupted operations
- Notion pages must be created in the database before uploading content

