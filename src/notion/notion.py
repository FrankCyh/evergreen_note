"""
Script to create Notion pages from filtered notes and update database with notion_id.
"""

import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import UUID

import psycopg2
import pyperclip
from APIs.notion.notional.blocks import (Block, Heading1, Heading2, Heading3,
                                         Quote, TextBlock)
from APIs.notion.notional.parser import HtmlParser
from APIs.notion.notional.types import URL, MentionPage, Relation
from APIs.notion.page import Page
from APIs.notion.session import session

#os.environ["TEST"] = "True" # not say

# Add project root to path for absolute paths
_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))

# Add APIs directory to path
_apis_path = Path(__file__).parent.parent.parent.parent / "APIs"
sys.path.insert(0, str(_apis_path))


def get_db_connection(
    dbname: str = "evergreen_notes",
    user: str = "postgres",
    password: str = None,
    host: str = "localhost",
    port: int = 5432
) -> psycopg2.extensions.connection:
    """
    Create a connection to the PostgreSQL database.

    Args:
        dbname: Database name
        user: Database user
        password: Database password (if None, will try to get from env or use empty)
        host: Database host
        port: Database port

    Returns:
        psycopg2.extensions.connection: Database connection
    """
    # Try to get password from environment variable if not provided
    if password is None:
        password = os.environ.get('PGPASSWORD', '')

    try:
        conn = psycopg2.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port
        )
        return conn
    except psycopg2.Error as e:
        print(f"Error connecting to database: {e}")
        raise


## Query Utilities
def get_notion_id_fr_page_id(
    conn: psycopg2.extensions.connection,
    page_id: str
) -> Optional[UUID]:
    """
    Get notion_id for a page from the `pages` table.

    Args:
        conn: Database connection
        page_id: Page ID from the database

    Returns:
        UUID: Notion page UUID if exists, None otherwise
    """
    cursor = conn.cursor()

    select_query = """
        SELECT notion_id FROM pages WHERE id = %s
    """

    cursor.execute(select_query, (page_id,))
    result = cursor.fetchone()
    cursor.close()

    if result and result[0]:
        return result[0]
    return None


def get_notion_id_from_href(
    href: str,
    conn: psycopg2.extensions.connection
) -> Optional[UUID]:
    """
    Get notion_id from an href URL by looking up in the database.

    Args:
        href: URL string (e.g., "https://notes.andymatuschak.org/z5E5QawiXCMbtNtupvxeoEX")
        conn: Database connection

    Returns:
        UUID: Notion page UUID if found, None otherwise
    """
    # Extract page ID from URL
    page_id = extract_page_id_from_url(href)

    if not page_id:
        return None

    # Get notion_id from database
    return get_notion_id_fr_page_id(conn, page_id)


def get_page_info_fr_page_id(
    conn: psycopg2.extensions.connection,
    page_id: str
) -> Optional[tuple]:
    """
    Get page information from database.

    Args:
        conn: Database connection
        page_id: Page ID from the database

    Returns:
        tuple: (title, file_location, notion_id) if exists, None otherwise
    """
    cursor = conn.cursor()

    select_query = """
        SELECT title, file_location, notion_id
        FROM pages
        WHERE id = %s
    """

    cursor.execute(select_query, (page_id,))
    result = cursor.fetchone()
    cursor.close()

    if result:
        return result
    return None

def update_notion_id_in_table(
    conn: psycopg2.extensions.connection,
    page_id: str,
    notion_id: UUID
) -> None:
    """
    Update notion_id for a page in the `pages` table.

    Args:
        conn: Database connection
        page_id: Page ID from the database
        notion_id: Notion page UUID
    """
    cursor = conn.cursor()

    update_query = """
        UPDATE pages
        SET notion_id = %s, updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """

    # Convert UUID to string for psycopg2
    cursor.execute(update_query, (str(notion_id), page_id))
    conn.commit()
    cursor.close()


def get_child_pages_w_notion_id(
    conn: psycopg2.extensions.connection,
    parent_id: str
) -> List[UUID]:
    """
    Get child page notion_ids for a parent page from the `page_references` table.

    Args:
        conn: Database connection
        parent_id: Parent page ID from the database

    Returns:
        List[UUID]: List of child page notion_ids that exist
    """
    cursor = conn.cursor()

    select_query = """
        SELECT p.notion_id
        FROM page_references pr
        JOIN pages p ON pr.child_id = p.id
        WHERE pr.parent_id = %s AND p.notion_id IS NOT NULL
    """

    cursor.execute(select_query, (parent_id,))
    results = cursor.fetchall()
    cursor.close()

    # Extract UUIDs from results
    child_notion_ids = [result[0] for result in results if result[0]]
    return child_notion_ids

def get_parent_pages_w_notion_id(
    conn: psycopg2.extensions.connection,
    child_id: str
) -> List[UUID]:
    """
    Get parent page notion_ids for a child page from the `page_references` table.

    Args:
        conn: Database connection
        child_id: Child page ID from the database

    Returns:
        List[UUID]: List of child page notion_ids that exist
    """
    cursor = conn.cursor()

    select_query = """
        SELECT p.notion_id
        FROM page_references pr
        JOIN pages p ON pr.parent_id = p.id
        WHERE pr.child_id = %s AND p.notion_id IS NOT NULL
    """

    cursor.execute(select_query, (child_id,))
    results = cursor.fetchall()
    cursor.close()

    # Extract UUIDs from results
    parent_notion_ids = [result[0] for result in results if result[0]]
    return parent_notion_ids


def get_all_page_w_notion_id(
    conn: psycopg2.extensions.connection
) -> List[tuple]:
    """
    Get all pages that have notion_id defined in the `pages` table.

    Args:
        conn: Database connection

    Returns:
        List[tuple]: List of (page_id, notion_id) tuples
    """
    cursor = conn.cursor()

    select_query = """
        SELECT id, notion_id
        FROM pages
        WHERE notion_id IS NOT NULL
    """

    cursor.execute(select_query)
    results = cursor.fetchall()
    cursor.close()

    return results

## Other Utilities
def extract_page_id_from_url(
    url: str
) -> Optional[str]:
    """
    Extract page ID from notes.andymatuschak.org URL.

    Args:
        url: URL string

    Returns:
        str: Page ID if found, None otherwise
    """
    if not url or "notes.andymatuschak.org" not in url:
        return None

    # Extract the path after the domain
    parsed = urlparse(url)
    path = parsed.path.strip('/')

    # Remove query parameters if any
    if '?' in path:
        path = path.split('?')[0]

    return path if path else None


def get_notion_blocks_fr_html(
    html_content: str,
    conn: psycopg2.extensions.connection
) -> List[Block]:
    """
    Parse HTML content to Notion blocks

    Args:
        html_content: HTML content as string
        conn: Database connection for looking up notion_ids

    Returns:
        List: Processed Notion blocks
    """
    # Replace relative hrefs with full URLs
    # Matches href="/page_id" where page_id can be alphanumeric and underscores
    html_content = re.sub(
        r'href="/([a-zA-Z0-9_]+)"',
        r'href="https://notes.andymatuschak.org/\1"',
        html_content
    )

    # Parse HTML as Notion blocks
    blocks = HtmlParser.parse_html_as_notion_block(html_content)

    # Remove first Heading1 (title)
    blocks = [x for x in blocks if not isinstance(x, Heading1)]

    # Process blocks: convert Quote/Heading2/Heading3 and replace hrefs with MentionPage
    for i, block in enumerate(blocks):
        # Some manual edits
        if isinstance(block, Quote):
            blocks[i] = Quote[block.quote.children[0].rich_text_]
        if isinstance(block, Heading2):
            blocks[i] = Heading1[block("rich_text")]
        if isinstance(block, Heading3):
            blocks[i] = Heading2[block("rich_text")]
        # Replace hrefs with MentionPage if the referenced page exists in Notion
        if isinstance(block, TextBlock):
            for j, text_block in enumerate(block("rich_text")):
                if text_block.href and text_block.href.startswith("https://notes.andymatuschak.org/"):
                    text_block_notion_id = get_notion_id_from_href(text_block.href, conn)
                    if not text_block_notion_id:
                        logging.info(f"Skipping href '{text_block.plain_text}'")
                        pass  # Keep as href if the referenced page is not created in notion database yet
                    else:
                        blocks[i].rich_text_[j] = MentionPage[text_block_notion_id]
                        logging.info(f"Replacing href '{text_block.href}' with mention page '{text_block_notion_id}'")

    return blocks

## First Run: Create and upload all webpages
def load_filtered_notes(
    json_file: str
) -> Dict[str, Dict[str, Any]]:
    """
    Load filtered notes from JSON file.

    Args:
        json_file: Path to the JSON file

    Returns:
        Dict[str, Dict[str, Any]]: Filtered notes dictionary
    """
    with open(json_file, 'r', encoding='utf-8') as f:
        return json.load(f)


async def create_all_notion_pages_and_update_db(
    filtered_notes: Dict[str, Dict[str, Any]],
    conn: psycopg2.extensions.connection,
) -> None:
    """
    Create Notion pages for all filtered notes and update database with notion_id.

    Used at the first time to create all pages in Notion. Followed by `upload_all_webpage_to_notion()` to upload content to Notion and establish relationships between pages.

    For later incremental updates, use `upload_new_webpage_to_notion()`.

    Args:
        filtered_notes: Dictionary of filtered notes generated by `filter_notes` in `dfs_filter.py`
            E.g. `filtered_notes`:
            ["z5E5QawiXCMbtNtupvxeoEX": {
                "name": "Evergreen notes",
                "id": "z5E5QawiXCMbtNtupvxeoEX",
                "url": "https://notes.andymatuschak.org/z5E5QawiXCMbtNtupvxeoEX",
                "referenced_ids": ["zKGjQtsTKgscAoq271ZzKqw", ...],
            }, ...]
        conn: Database connection
    """
    total_pages = len(filtered_notes)
    created_count = 0
    skipped_count = 0
    error_count = 0

    print(f"Creating {total_pages} Notion pages...")

    for page_id, page_info in filtered_notes.items():
        try:
            # Check if page already has a notion_id
            existing_notion_id = get_notion_id_fr_page_id(conn, page_id)
            if existing_notion_id:
                print(f"Skipping page {page_id} - already has notion_id: {existing_notion_id}")
                skipped_count += 1
                continue

            title = page_info.get("name", "")
            url = page_info.get("url", "")

            if not title:
                print(f"Warning: Skipping page {page_id} - no name field")
                error_count += 1
                continue

            print(f"Creating page: {title} (ID: {page_id})")

            # Create Notion page
            created_page_obj = await Page.create_empty_page_in_db(
                title=title,
                db_name="Chapter",
                prop_d={"URL": URL[url]},
                do_open_url=False
            )

            # Get the notion_id from the created page
            notion_id = created_page_obj.id

            # Update database with notion_id
            update_notion_id_in_table(conn, page_id, notion_id)

            created_count += 1
            print(f"  ✓ Created Notion page with ID: {notion_id}")

        except Exception as e:
            print(f"  ✗ Error creating page {page_id}: {e}")
            error_count += 1
            continue

    print(f"\n{'='*50}")
    print(f"Summary:")
    print(f"  Total pages: {total_pages}")
    print(f"  Created: {created_count}")
    print(f"  Skipped (already have notion_id): {skipped_count}")
    print(f"  Errors: {error_count}")
    print(f"{'='*50}")


async def upload_all_webpage_to_notion() -> None:
    """
    Upload webpages to Notion by reading local HTML files and parsing them.

    Used at the first time to upload all webpages to Notion. For later incremental updates, use `upload_new_webpage_to_notion()`.

    For pages with notion_id defined, reads the HTML file, parses it as Notion blocks,
    and uploads to Notion. Replaces href links to notes.andymatuschak.org with
    page mentions if the target page exists in Notion.
    """
    # Connect to database
    conn = get_db_connection()

    try:
        # Get all pages with notion_id
        pages_w_notion_id = get_all_page_w_notion_id(conn)
        total_pages = len(pages_w_notion_id)

        print(f"Found {total_pages} pages with notion_id")
        print("Uploading webpages to Notion...")

        uploaded_count = 0
        skipped_count = 0
        error_count = 0

        for page_id, notion_id in pages_w_notion_id:
            try:
                # Get page info (file_location)
                page_info = get_page_info_fr_page_id(conn, page_id)

                if not page_info:
                    print(f"Warning: No page info found for {page_id}")
                    skipped_count += 1
                    continue

                _, file_location, _ = page_info

                if not file_location:
                    print(f"Warning: No file_location for {page_id}")
                    skipped_count += 1
                    continue

                # Resolve file path
                file_path = Path(file_location)
                if not file_path.is_absolute():
                    file_path = _project_root / "webpage" / file_path

                if not file_path.exists():
                    print(f"Warning: File not found: {file_path}")
                    skipped_count += 1
                    continue

                print(f"Uploading page {page_id} (file: {file_location})")

                # Read HTML file
                with open(file_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()

                # Parse HTML as Notion blocks
                blocks = get_notion_blocks_fr_html(html_content, conn)

                # Retrieve the page from Notion
                page_obj = await session.pages.retrieve(notion_id)

                # If page already has children, skip
                if len(page_obj._child_l) > 1:
                    print(f"Warning: Page '{page_id}' already has children, skipping")
                    continue

                # Set _child_l with parsed blocks
                page_obj._child_l = blocks

                # Call update_page to append children
                await page_obj.update_page()

                uploaded_count += 1
                print(f"  ✓ Uploaded {len(blocks)} blocks")

            except Exception as e:
                print(f"  ✗ Error uploading page {page_id}: {e}")
                error_count += 1
                continue

        print(f"\n{'='*50}")
        print(f"Summary:")
        print(f"  Total pages with notion_id: {total_pages}")
        print(f"  Uploaded: {uploaded_count}")
        print(f"  Skipped: {skipped_count}")
        print(f"  Errors: {error_count}")
        print(f"{'='*50}")

    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()
        print("\nDatabase connection closed.")

## Incremental Updates: Upload new webpages
async def replace_href_w_mention_page_in_notion_page(
    page_id: str,
    href_id: str,
    page_mention_id: str,
) -> None:
    """
    Replace `href_id` with mention page `page_mention_id` in a Notion page `page_id`.
    """
    assert re.match(r'^[a-zA-Z0-9_]+$', href_id)

    page_obj = await Page.retrieve(page_id)
    block_l = page_obj.content

    for block in block_l:
        if isinstance(block, TextBlock):
            for j, text_block in enumerate(block("rich_text")):
                if text_block.href and text_block.href == f"https://notes.andymatuschak.org/{href_id}":
                    # Replace text block with MentionPage object
                    block.rich_text_[j] = MentionPage[page_mention_id]
                    await session.blocks.update(block)


async def upload_new_webpage_to_notion(
    page_id: str,
) -> None:
    """
    Upload a new page to Notion with proper database synchronization.

    All page data must already exist in database. The function:
    1. Validates that page exists and doesn't have notion_id
    2. Creates Notion page
    3. Updates notion_id in database
    4. Uploads HTML content with href→MentionPage conversion (only for pages with notion_id)
    5. Updates "📖 Related" property

    Args:
        page_id: Page ID to upload (e.g., "z4geAr5cERWdJPrdhU5gy3N")
    """
    # Connect to database
    conn = get_db_connection()

    try:
        print(f"\nProcessing page: {page_id}")

        #$ Phase 1: Validate and get page info from database
        page_info = get_page_info_fr_page_id(conn, page_id)

        if not page_info:
            raise ValueError(f"Page {page_id} not found in database")

        title, file_location, existing_notion_id = page_info

        if existing_notion_id:
            raise ValueError(f"Page {page_id} already has notion_id: {existing_notion_id}. This function is for new pages only.")

        if not file_location:
            raise ValueError(f"Page {page_id} has no file_location in database")

        print(f"  Title: {title}")
        #$ Phase 2: Find HTML file
        file_path = Path(file_location)
        if not file_path.is_absolute():
            file_path = _project_root / "webpage" / file_path

        if not file_path.exists():
            raise FileNotFoundError(f"HTML file not found: {file_path}")

        print(f"  File location: {file_location}")

        #$ Phase 3: Create Notion page
        print(f"  Creating Notion page...")
        url = f"https://notes.andymatuschak.org/{page_id}"

        created_page_obj = await Page.create_empty_page_in_db(
            title=title,
            db_name="Chapter",
            prop_d={"URL": URL[url]},
            do_open_url=True
        )


        notion_id = created_page_obj.id
        update_notion_id_in_table(conn, page_id, notion_id)
        print(f"  ✓ Created Notion page: {notion_id}")
        confirm = input("Initialized the page with the evergreen chapter template? (y/N): ").strip().lower()
        while confirm != "y":
            confirm = input("Initialized the page with the evergreen chapter template? (y/N): ").strip().lower()

        #$ Phase 4: Upload content to Notion
        # Read HTML file
        with open(file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # Parse HTML as Notion blocks (replaces hrefs with MentionPage for pages with notion_id)
        blocks = get_notion_blocks_fr_html(html_content, conn)

        # Set _child_l with parsed blocks
        created_page_obj._child_l = blocks
        print(f"  Appending {len(blocks)} blocks to the page...")

        #$ Phase 5: Update "📖 Related" property
        # Get child and parent pages with notion_id
        child_notion_ids = get_child_pages_w_notion_id(conn, page_id)
        parent_notion_ids = get_parent_pages_w_notion_id(conn, page_id)
        unique_related_ids = list(set(child_notion_ids + parent_notion_ids))

        if unique_related_ids:
            # Update "📖 Related" for the new page
            created_page_obj._update_d["📖 Related"] = Relation[unique_related_ids]
            print(f"  Updating the \"📖 Related\" property of the new page with {len(unique_related_ids)} related pages...")

        await created_page_obj.process_update()
        print(f"  ✓ Updated the page\n\n")

        # Print parent page URLs for manual update
        if parent_notion_ids:
            print(f"  Parent pages:")
            for parent_notion_id in parent_notion_ids:
                parent_url = f"https://notion.so/{parent_notion_id.replace('-', '')}"
                print(f"    - {parent_url}")
                await replace_href_w_mention_page_in_notion_page(
                    parent_notion_id,
                    page_id,
                    str(created_page_obj.id),
                )

        print(f"  ✓ Successfully processed page {page_id}")

    except Exception as e:
        print(f"  ✗ Error processing page {page_id}: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    async def upload_pages():
        page_urls = [
            "https://notes.andymatuschak.org/zTpJdbe6ub7uhBFLuHkFsrT",
        ]
        for url in page_urls:
            page_id = extract_page_id_from_url(url)
            if page_id:
                await upload_new_webpage_to_notion(page_id)

    asyncio.run(upload_pages())

    #asyncio.run(replace_href_w_mention_page_in_notion_page(
    #    "2d2024dc-88c4-8158-bef8-ebd75b39be5e",
    #    "z26C6ing3sqiZMHRVFuT6xn",
    #    "2d2024dc-88c4-8127-8e44-f32aadbdb116",
    #))

    pass
