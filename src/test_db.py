from typing import Iterator
from uuid import uuid4

import pytest
from psycopg2.extensions import connection as PgConnection

from src.db import (
    create_pages_in_db,
    create_references_in_db,
    get_child_page_l_with_notion_id,
    get_database_statistics,
    get_db_connection,
    get_notion_id_from_page_id,
    get_page_data_from_db,
    get_page_id_from_notion_id,
    get_page_id_from_title,
    get_page_info,
    get_parent_page_l_with_notion_id,
    get_reference_pair_l,
    update_notion_id_in_db,
)


TEST_PARENT_ID = "__test_page_parent__"
TEST_CHILD_ID = "__test_page_child__"


@pytest.fixture
def db_conn() -> Iterator[PgConnection]:
    conn = get_db_connection()
    try:
        yield conn
    finally:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM pages WHERE id IN (%s, %s)",
                (TEST_PARENT_ID, TEST_CHILD_ID),
            )
        conn.commit()
        conn.close()


def test_page_and_reference_crud_in_db(
    db_conn: PgConnection,
) -> None:
    parent_notion_uuid = uuid4()
    child_notion_uuid = uuid4()

    page_data_d = {
        TEST_PARENT_ID: {
            "title": "Test Parent Page Title",
            "filename": "Test Parent Page Title-__test_page_parent__.html",
            "references": [TEST_CHILD_ID],
        },
        TEST_CHILD_ID: {
            "title": "Test Child Page Title",
            "filename": "Test Child Page Title-__test_page_child__.html",
            "references": [],
        },
    }

    inserted_count = create_pages_in_db(page_data_d, conn=db_conn)
    assert inserted_count == 2

    ref_pair_l = get_reference_pair_l(page_data_d)
    assert ref_pair_l == [(TEST_PARENT_ID, TEST_CHILD_ID)]
    create_references_in_db(ref_pair_l, conn=db_conn)

    assert update_notion_id_in_db(TEST_PARENT_ID, parent_notion_uuid, conn=db_conn)
    assert update_notion_id_in_db(TEST_CHILD_ID, child_notion_uuid, conn=db_conn)

    # Re-upserting pages with notion_id=None must preserve the existing notion_id in DB
    create_pages_in_db(page_data_d, conn=db_conn)
    assert get_notion_id_from_page_id(TEST_PARENT_ID, conn=db_conn) == str(parent_notion_uuid)
    assert get_notion_id_from_page_id(TEST_CHILD_ID, conn=db_conn) == str(child_notion_uuid)

    assert get_page_id_from_title("Test Parent Page Title", conn=db_conn) == TEST_PARENT_ID
    assert get_page_id_from_notion_id(parent_notion_uuid, conn=db_conn) == TEST_PARENT_ID

    child_l = get_child_page_l_with_notion_id(TEST_PARENT_ID, conn=db_conn)
    assert child_l == [(TEST_CHILD_ID, "Test Child Page Title", str(child_notion_uuid))]

    parent_l = get_parent_page_l_with_notion_id(TEST_CHILD_ID, conn=db_conn)
    assert parent_l == [(TEST_PARENT_ID, "Test Parent Page Title", str(parent_notion_uuid))]

    info_by_id_d = get_page_info(TEST_PARENT_ID, conn=db_conn, verbose=False)
    assert info_by_id_d is not None
    assert info_by_id_d["notion_id"] == str(parent_notion_uuid)
    assert len(info_by_id_d["children"]) == 1
    assert info_by_id_d["children"][0]["id"] == TEST_CHILD_ID

    info_by_uuid_d = get_page_info(str(child_notion_uuid), conn=db_conn, verbose=False)
    assert info_by_uuid_d is not None
    assert info_by_uuid_d["id"] == TEST_CHILD_ID
    assert len(info_by_uuid_d["parents"]) == 1
    assert info_by_uuid_d["parents"][0]["id"] == TEST_PARENT_ID

    stats_d = get_database_statistics(conn=db_conn)
    assert stats_d["total_pages"] >= 2
    assert stats_d["total_references"] >= 1


def test_existing_target_note_in_db(
    db_conn: PgConnection,
) -> None:
    target_id = "z9vSQjkBVL6dCVC6QhCu4Br"
    page_d = get_page_data_from_db(target_id, conn=db_conn)
    assert page_d is not None
    assert page_d["title"] == "Spaced repetition memory prompts should be concise"
