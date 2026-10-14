import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Optional,
    Tuple,
    Union,
)
from uuid import UUID

import psycopg2
from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import execute_batch

from src.webpage import (
    DEFAULT_REFERENCES_FILE,
    PROJECT_ROOT,
)


DEFAULT_SQL_FILE = Path(__file__).resolve().parent / "create_database.sql"


def get_db_connection(
    dbname: str = "evergreen_notes",
    user: str = "postgres",
    password: Optional[str] = None,
    host: str = "localhost",
    port: int = 5432,
) -> PgConnection:
    if password is None:
        password = os.environ.get("PGPASSWORD", "")

    return psycopg2.connect(
        dbname=dbname,
        user=user,
        password=password,
        host=host,
        port=port,
    )


@contextmanager
def _managed_connection(
    conn: Optional[PgConnection] = None,
) -> Iterator[PgConnection]:
    if conn is not None:
        yield conn
        return

    new_conn = get_db_connection()
    try:
        yield new_conn
    finally:
        new_conn.close()


def create_database_schema(
    conn: Optional[PgConnection] = None,
    sql_file: Union[str, Path] = DEFAULT_SQL_FILE,
) -> None:
    sql_text = Path(sql_file).read_text(encoding="utf-8")
    with _managed_connection(conn) as active_conn:
        with active_conn.cursor() as cursor:
            cursor.execute(sql_text)
        active_conn.commit()


def get_page_data_from_file(
    json_file: Union[str, Path] = DEFAULT_REFERENCES_FILE,
) -> Dict[str, Dict[str, Any]]:
    return json.loads(Path(json_file).read_text(encoding="utf-8"))


def create_pages_in_db(
    page_data_d: Dict[str, Dict[str, Any]],
    conn: Optional[PgConnection] = None,
) -> int:
    """
    Upsert pages in `page_data_d` into the `pages` table while preserving existing `notion_id` values.
    """
    page_row_l = [
        (
            page_id,
            page_info.get("title", ""),
            page_info.get("filename", ""),
            page_info.get("notion_id"),
        )
        for page_id, page_info in page_data_d.items()
    ]

    insert_query = """
        INSERT INTO pages (id, title, file_location, notion_id)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title,
            file_location = EXCLUDED.file_location,
            notion_id = COALESCE(pages.notion_id, EXCLUDED.notion_id),
            updated_at = CURRENT_TIMESTAMP
    """

    with _managed_connection(conn) as active_conn:
        with active_conn.cursor() as cursor:
            execute_batch(cursor, insert_query, page_row_l)
        active_conn.commit()

    return len(page_row_l)


def get_reference_pair_l(
    page_data_d: Dict[str, Dict[str, Any]],
) -> List[Tuple[str, str]]:
    reference_pair_l: List[Tuple[str, str]] = []
    for page_id, page_info in page_data_d.items():
        for child_id in page_info.get("references", []):
            reference_pair_l.append((page_id, child_id))
    return reference_pair_l


def create_references_in_db(
    reference_pair_l: List[Tuple[str, str]],
    conn: Optional[PgConnection] = None,
) -> int:
    insert_query = """
        INSERT INTO page_references (parent_id, child_id)
        VALUES (%s, %s)
        ON CONFLICT (parent_id, child_id) DO NOTHING
    """

    with _managed_connection(conn) as active_conn:
        with active_conn.cursor() as cursor:
            execute_batch(cursor, insert_query, reference_pair_l)
        active_conn.commit()

    return len(reference_pair_l)


def get_database_statistics(
    conn: Optional[PgConnection] = None,
) -> Dict[str, Any]:
    with _managed_connection(conn) as active_conn:
        with active_conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM pages")
            total_pages = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM page_references")
            total_references = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(DISTINCT parent_id) FROM page_references")
            pages_with_children = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(DISTINCT child_id) FROM page_references")
            pages_with_parents = cursor.fetchone()[0]

    avg_references_per_page = total_references / total_pages if total_pages > 0 else 0.0
    return {
        "total_pages": total_pages,
        "total_references": total_references,
        "pages_with_children": pages_with_children,
        "pages_with_parents": pages_with_parents,
        "avg_references_per_page": avg_references_per_page,
    }


def get_page_data_from_db(
    page_id: str,
    conn: Optional[PgConnection] = None,
) -> Optional[Dict[str, Any]]:
    with _managed_connection(conn) as active_conn:
        with active_conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, title, file_location, notion_id, created_at, updated_at
                FROM pages
                WHERE id = %s
                """,
                (page_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None

            return {
                "id": row[0],
                "title": row[1],
                "file_location": row[2],
                "notion_id": str(row[3]) if row[3] else None,
                "created_at": row[4],
                "updated_at": row[5],
            }


def get_notion_id_from_page_id(
    page_id: str,
    conn: Optional[PgConnection] = None,
) -> Optional[str]:
    with _managed_connection(conn) as active_conn:
        with active_conn.cursor() as cursor:
            cursor.execute(
                "SELECT notion_id FROM pages WHERE id = %s",
                (page_id,),
            )
            row = cursor.fetchone()
            if row and row[0] is not None:
                return str(row[0])
            return None


def get_all_page_id_and_notion_id_from_db(
    conn: Optional[PgConnection] = None,
) -> List[Tuple[str, str]]:
    with _managed_connection(conn) as active_conn:
        with active_conn.cursor() as cursor:
            cursor.execute("SELECT id, notion_id FROM pages WHERE notion_id IS NOT NULL")
            return [(row[0], str(row[1])) for row in cursor.fetchall()]


def update_notion_id_in_db(
    page_id: str,
    notion_id: Union[str, UUID],
    conn: Optional[PgConnection] = None,
) -> bool:
    notion_id_str = str(notion_id) if isinstance(notion_id, UUID) else notion_id
    with _managed_connection(conn) as active_conn:
        with active_conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE pages
                SET notion_id = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (notion_id_str, page_id),
            )
            rows_affected = cursor.rowcount
        active_conn.commit()
    return rows_affected > 0


def get_child_page_l_with_notion_id(
    page_id: str,
    conn: Optional[PgConnection] = None,
) -> List[Tuple[str, str, str]]:
    with _managed_connection(conn) as active_conn:
        with active_conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.id, p.title, p.notion_id
                FROM page_references pr
                JOIN pages p ON pr.child_id = p.id
                WHERE pr.parent_id = %s AND p.notion_id IS NOT NULL
                ORDER BY p.id
                """,
                (page_id,),
            )
            return [(row[0], row[1], str(row[2])) for row in cursor.fetchall()]


def get_parent_page_l_with_notion_id(
    page_id: str,
    conn: Optional[PgConnection] = None,
) -> List[Tuple[str, str, str]]:
    with _managed_connection(conn) as active_conn:
        with active_conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.id, p.title, p.notion_id
                FROM page_references pr
                JOIN pages p ON pr.parent_id = p.id
                WHERE pr.child_id = %s AND p.notion_id IS NOT NULL
                ORDER BY p.id
                """,
                (page_id,),
            )
            return [(row[0], row[1], str(row[2])) for row in cursor.fetchall()]


def get_page_id_from_title(
    title: str,
    conn: Optional[PgConnection] = None,
) -> Optional[str]:
    with _managed_connection(conn) as active_conn:
        with active_conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM pages WHERE title = %s",
                (title,),
            )
            row = cursor.fetchone()
            return row[0] if row else None


def get_page_id_from_notion_id(
    notion_id: Union[str, UUID],
    conn: Optional[PgConnection] = None,
) -> Optional[str]:
    notion_id_str = str(notion_id) if isinstance(notion_id, UUID) else notion_id
    with _managed_connection(conn) as active_conn:
        with active_conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM pages WHERE notion_id = %s",
                (notion_id_str,),
            )
            row = cursor.fetchone()
            return row[0] if row else None


def get_page_info(
    identifier: str,
    conn: Optional[PgConnection] = None,
    verbose: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Resolve `identifier` by page ID, Notion UUID, or exact title and return its database record along with all child and parent pages.
    """
    with _managed_connection(conn) as active_conn:
        page_data_d = get_page_data_from_db(identifier, conn=active_conn)

        if page_data_d is None:
            try:
                UUID(identifier)
                page_id = get_page_id_from_notion_id(identifier, conn=active_conn)
                if page_id:
                    page_data_d = get_page_data_from_db(page_id, conn=active_conn)
            except ValueError:
                pass

        if page_data_d is None:
            page_id = get_page_id_from_title(identifier, conn=active_conn)
            if page_id:
                page_data_d = get_page_data_from_db(page_id, conn=active_conn)

        if page_data_d is None:
            if verbose:
                print(f"Page not found for identifier: {identifier}")
            return None

        page_id = page_data_d["id"]
        with active_conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.id, p.title, p.notion_id
                FROM page_references pr
                JOIN pages p ON pr.child_id = p.id
                WHERE pr.parent_id = %s
                ORDER BY p.id
                """,
                (page_id,),
            )
            children_l = [
                {
                    "id": row[0],
                    "title": row[1],
                    "notion_id": str(row[2]) if row[2] else None,
                }
                for row in cursor.fetchall()
            ]

            cursor.execute(
                """
                SELECT p.id, p.title, p.notion_id
                FROM page_references pr
                JOIN pages p ON pr.parent_id = p.id
                WHERE pr.child_id = %s
                ORDER BY p.id
                """,
                (page_id,),
            )
            parents_l = [
                {
                    "id": row[0],
                    "title": row[1],
                    "notion_id": str(row[2]) if row[2] else None,
                }
                for row in cursor.fetchall()
            ]

    result_d = {
        **page_data_d,
        "children": children_l,
        "parents": parents_l,
    }

    if verbose:
        print("=" * 80)
        print(f"Page Information: {page_data_d['title']}")
        print("=" * 80)
        print(f"ID:            {page_data_d['id']}")
        print(f"Title:         {page_data_d['title']}")
        print(f"File Location: {page_data_d['file_location']}")
        print(f"Notion ID:     {page_data_d['notion_id'] or 'None'}")
        print(f"\nChildren ({len(children_l)}):")
        for child in children_l:
            print(f"  - [{child['id']}] {child['title']} (Notion ID: {child['notion_id'] or 'None'})")
        print(f"\nParents ({len(parents_l)}):")
        for parent in parents_l:
            print(f"  - [{parent['id']}] {parent['title']} (Notion ID: {parent['notion_id'] or 'None'})")
        print("=" * 80)

    return result_d


def main() -> None:
    parser = argparse.ArgumentParser(description="Insert page references into PostgreSQL database")
    parser.add_argument(
        "--json-file",
        type=str,
        default=str(DEFAULT_REFERENCES_FILE),
        help="Path to the JSON file containing page references",
    )
    parser.add_argument("--dbname", type=str, default="evergreen_notes", help="Database name")
    parser.add_argument("--user", type=str, default="postgres", help="Database user")
    parser.add_argument("--password", type=str, default=None, help="Database password")
    parser.add_argument("--host", type=str, default="localhost", help="Database host")
    parser.add_argument("--port", type=int, default=5432, help="Database port")
    args = parser.parse_args()

    json_file_path = Path(args.json_file)
    if not json_file_path.is_absolute():
        json_file_path = PROJECT_ROOT / json_file_path

    page_data_d = get_page_data_from_file(json_file_path)
    conn = get_db_connection(
        dbname=args.dbname,
        user=args.user,
        password=args.password,
        host=args.host,
        port=args.port,
    )

    try:
        inserted_pages = create_pages_in_db(page_data_d, conn=conn)
        print(f"Inserted/updated {inserted_pages} pages")

        reference_pair_l = get_reference_pair_l(page_data_d)
        inserted_refs = create_references_in_db(reference_pair_l, conn=conn)
        print(f"Inserted {inserted_refs} reference relationships")

        stats_d = get_database_statistics(conn=conn)
        for key, value in stats_d.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
