import asyncio
import logging
import re
from pathlib import Path
from typing import (
     Any,
    Dict,
    List,
    Optional,
    Union,
)
from uuid import UUID

from psycopg2.extensions import connection as PgConnection

from APIs.notion.local_page import LocalPage
from APIs.notion.notional.blocks import (
    Block,
    Heading1,
    Heading2,
    Heading3,
    Quote,
    TextBlock,
    WithChildrenMixin,
)
from APIs.notion.notional.parser import HtmlParser
from APIs.notion.notional.types import (
    MentionPage,
    Relation,
    UploadFile,
    URL,
)
from APIs.notion.page import Page
from APIs.notion.session import session

from src.db import (
    get_all_page_id_and_notion_id_from_db,
    get_child_page_l_with_notion_id,
    get_db_connection,
    get_notion_id_from_page_id,
    get_page_data_from_db,
    get_parent_page_l_with_notion_id,
    update_notion_id_in_db,
)
from src.webpage import (
    DEFAULT_WEBPAGE_DIR,
    NOTES_BASE_URL,
    get_page_id_from_url,
    get_url_from_page_id,
)


EVERGREEN_BOOK_ID = UUID("2ad024dc-88c4-8195-a7b8-dfdec7a6a8df")


def get_all_block_l_recursively(
    block_l: List[Block],
) -> List[Block]:
    """
    Collect all blocks in `block_l` and any nested `children` blocks in depth-first order.
    """
    all_block_l: List[Block] = []
    for block in block_l:
        if isinstance(block, WithChildrenMixin):
            all_block_l.extend(block.get_flattened_block_l())
        else:
            all_block_l.append(block)
    return all_block_l


def get_notion_blocks_from_html(
    html_content: str,
    conn: Optional[PgConnection] = None,
    page_id_to_notion_id_d: Optional[Dict[str, Optional[str]]] = None,
) -> List[Block]:
    """
    Parse Evergreen Note HTML into Notion blocks, normalize headings and quotes, and replace links to known Notion pages with `MentionPage`.
    """
    html_content = re.sub(
        r'href="/([a-zA-Z0-9_-]+)"',
        f'href="{NOTES_BASE_URL}/\\1"',
        html_content,
    )

    block_l = HtmlParser.parse_html_as_notion_block(html_content)
    block_l = [x for x in block_l if not isinstance(x, Heading1)]

    for i, block in enumerate(block_l):
        if isinstance(block, Quote) and block.quote.children:
            block_l[i] = Quote[block.quote.children[0].rich_text_]
        elif isinstance(block, Heading2):
            block_l[i] = Heading1[block("rich_text")]
        elif isinstance(block, Heading3):
            block_l[i] = Heading2[block("rich_text")]

    note_url_prefix = f"{NOTES_BASE_URL}/"
    for block in get_all_block_l_recursively(block_l):
        if isinstance(block, TextBlock):
            for j, text_block in enumerate(block("rich_text")):
                if text_block.href and text_block.href.startswith(note_url_prefix):
                    ref_page_id = get_page_id_from_url(text_block.href)
                    if page_id_to_notion_id_d is not None:
                        ref_notion_id = page_id_to_notion_id_d.get(ref_page_id)
                    else:
                        ref_notion_id = get_notion_id_from_page_id(ref_page_id, conn=conn)

                    if not ref_notion_id:
                        logging.info(f"Skipping href '{text_block.plain_text}'")
                    else:
                        block.rich_text_[j] = MentionPage[UUID(str(ref_notion_id))]
                        logging.info(f"Replacing href '{text_block.href}' with mention page '{ref_notion_id}'")

    return block_l


async def create_all_notion_pages_and_update_db(
    filtered_note_d: Dict[str, Dict[str, Any]],
    conn: Optional[PgConnection] = None,
) -> None:
    """
    Create empty Notion pages in the `Chapter` database for all filtered notes and store their `notion_id` in PostgreSQL.
    """
    for page_id, page_info in filtered_note_d.items():
        existing_notion_id = get_notion_id_from_page_id(page_id, conn=conn)
        if existing_notion_id:
            continue

        title = page_info.get("name", "")
        url = page_info.get("url", "") or get_url_from_page_id(page_id)
        if not title:
            continue

        created_page_obj = await Page.create_empty_page_in_database(
            title=title,
            database_name="Chapter",
            prop_d={"URL": URL[url]},
            do_open_url=False,
        )
        update_notion_id_in_db(page_id, created_page_obj.id, conn=conn)


async def upload_all_webpage_to_notion(
    webpage_dir: Union[str, Path] = DEFAULT_WEBPAGE_DIR,
) -> None:
    """
    Upload parsed Notion blocks for all pages in PostgreSQL that have a `notion_id` and no existing content.
    """
    conn = get_db_connection()
    try:
        page_with_notion_id_l = get_all_page_id_and_notion_id_from_db(conn=conn)
        for page_id, notion_id_str in page_with_notion_id_l:
            page_data_d = get_page_data_from_db(page_id, conn=conn)
            if not page_data_d or not page_data_d["file_location"]:
                continue

            file_path = Path(webpage_dir) / page_data_d["file_location"]
            if not file_path.exists():
                continue

            html_content = file_path.read_text(encoding="utf-8")
            block_l = get_notion_blocks_from_html(html_content, conn=conn)

            page_obj = await session.pages.retrieve(UUID(notion_id_str))
            if len(page_obj._child_l) > 1:
                continue

            page_obj._child_l = block_l
            await page_obj.update_page()
    finally:
        conn.close()


async def replace_href_with_mention_page_in_notion_page(
    page_id: Union[str, UUID],
    href_id: str,
    page_mention_id: Union[str, UUID],
) -> int:
    """
    Retrieve Notion page `page_id`, traverse all text blocks (including nested children), replace any link to `href_id` with a `MentionPage` pointing to `page_mention_id`, and return the number of updated blocks.
    """
    assert re.match(r"^[a-zA-Z0-9_-]+$", href_id)
    target_page_uuid = UUID(str(page_id)) if not isinstance(page_id, UUID) else page_id
    mention_uuid = UUID(str(page_mention_id)) if not isinstance(page_mention_id, UUID) else page_mention_id
    target_url = get_url_from_page_id(href_id)

    page_obj = await Page.retrieve(target_page_uuid)
    block_l = page_obj.get_page_flattened_block_l()

    updated_block_count = 0
    for block in block_l:
        if not isinstance(block, TextBlock):
            continue

        block_modified = False
        for j, text_block in enumerate(block("rich_text")):
            if text_block.href and text_block.href == target_url:
                block.rich_text_[j] = MentionPage[mention_uuid]
                block_modified = True

        if block_modified:
            await session.blocks.update(block)
            updated_block_count += 1

    return updated_block_count


async def upload_new_webpage_to_notion(
    url_or_page_id: str,
    webpage_dir: Union[str, Path] = DEFAULT_WEBPAGE_DIR,
    confirm_template: bool = True,
    do_open_url: bool = True,
) -> UUID:
    """
    Upload a new Evergreen Note page to Notion `Chapter` database, update `notion_id` in PostgreSQL, populate `📖 Related`, and replace links to this page with `MentionPage` across all parent Notion pages.
    """
    page_id = get_page_id_from_url(url_or_page_id)
    conn = get_db_connection()

    try:
        print(f"\nProcessing page: {page_id}")

        page_data_d = get_page_data_from_db(page_id, conn=conn)
        if not page_data_d:
            raise ValueError(f"Page {page_id} not found in database")

        title = page_data_d["title"]
        file_location = page_data_d["file_location"]
        existing_notion_id = page_data_d["notion_id"]

        if existing_notion_id:
            raise ValueError(f"Page {page_id} already has notion_id: {existing_notion_id}. This function is for new pages only.")
        if not file_location:
            raise ValueError(f"Page {page_id} has no file_location in database")

        file_path = Path(file_location)
        if not file_path.is_absolute():
            file_path = Path(webpage_dir) / file_path
        if not file_path.exists():
            raise FileNotFoundError(f"HTML file not found: {file_path}")

        print(f"  Title: {title}")
        print(f"  File location: {file_location}")
        print("  Creating Notion page...")

        url = get_url_from_page_id(page_id)
        leaf_icon_path = LocalPage.find_local_file_path_with_name("leaf", file_type="icon")
        icon = await UploadFile.from_local_file(leaf_icon_path, file_name_with_ext="leaf.png") if leaf_icon_path else None
        created_page_obj = await Page.create_empty_page_in_database(
            title=title,
            database_name="Chapter",
            rel_d={"📚 Book": EVERGREEN_BOOK_ID},
            prop_d={"URL": URL[url]},
            icon=icon,
            do_open_url=do_open_url,
        )

        notion_id = created_page_obj.id
        update_notion_id_in_db(page_id, notion_id, conn=conn)
        print(f"  ✓ Created Notion page: {notion_id}")

        if confirm_template:
            confirm = input("Initialized the page with the evergreen chapter template? (y/N): ").strip().lower()
            while confirm != "y":
                confirm = input("Initialized the page with the evergreen chapter template? (y/N): ").strip().lower()

        html_content = file_path.read_text(encoding="utf-8")
        block_l = get_notion_blocks_from_html(html_content, conn=conn)
        created_page_obj._child_l = block_l
        print(f"  Appending {len(block_l)} blocks to the page...")

        child_page_l = get_child_page_l_with_notion_id(page_id, conn=conn)
        parent_page_l = get_parent_page_l_with_notion_id(page_id, conn=conn)
        child_notion_id_l = [UUID(nid) for _, _, nid in child_page_l]
        parent_notion_id_l = [UUID(nid) for _, _, nid in parent_page_l]
        unique_related_id_l = list(dict.fromkeys(child_notion_id_l + parent_notion_id_l))

        if unique_related_id_l:
            created_page_obj._update_d["📖 Related"] = Relation[unique_related_id_l]
            print(f'  Updating the "📖 Related" property of the new page with {len(unique_related_id_l)} related pages...')

        await created_page_obj.process_update()
        print("  ✓ Updated the page\n")

        if parent_notion_id_l:
            print("  Parent pages:")
            for parent_notion_id in parent_notion_id_l:
                parent_url = f"https://notion.so/{str(parent_notion_id).replace('-', '')}"
                print(f"    - {parent_url}")
                await replace_href_with_mention_page_in_notion_page(
                    parent_notion_id,
                    page_id,
                    notion_id,
                )

        print(f"  ✓ Successfully processed page {page_id}")
        return notion_id

    except Exception as e:
        print(f"  ✗ Error processing page {page_id}: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    async def main() -> None:
        page_url_l = [
            "https://notes.andymatuschak.org/z9vSQjkBVL6dCVC6QhCu4Br",
        ]
        for url in page_url_l:
            await upload_new_webpage_to_notion(url)

    asyncio.run(main())
