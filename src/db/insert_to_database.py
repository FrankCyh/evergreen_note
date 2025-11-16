"""
Script to insert page references data into PostgreSQL database.

Reads from page_references.json and inserts into the PostgreSQL database
with bidirectional relationship tracking.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Set
import psycopg2
from psycopg2.extras import execute_batch
from psycopg2 import sql

# Add project root to path for absolute paths
_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))


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


def load_page_data(
    json_file: str
) -> Dict[str, Dict[str, any]]:
    """
    Load page data from JSON file.

    Args:
        json_file: Path to the JSON file

    Returns:
        Dict[str, Dict[str, any]]: Page data dictionary
    """
    with open(json_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def insert_pages(
    conn: psycopg2.extensions.connection,
    page_data: Dict[str, Dict[str, any]]
) -> None:
    """
    Insert pages into the database.

    Args:
        conn: Database connection
        page_data: Dictionary of page data
    """
    cursor = conn.cursor()
    
    # Prepare page insertions
    pages_to_insert = []
    for page_id, page_info in page_data.items():
        pages_to_insert.append((
            page_id,
            page_info.get('title', ''),
            page_info.get('filename', '')
        ))
    
    # Insert pages using execute_batch for efficiency
    insert_query = """
        INSERT INTO pages (id, title, file_location)
        VALUES (%s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title,
            file_location = EXCLUDED.file_location,
            updated_at = CURRENT_TIMESTAMP
    """
    
    execute_batch(cursor, insert_query, pages_to_insert)
    conn.commit()
    
    print(f"Inserted/updated {len(pages_to_insert)} pages")
    cursor.close()


def build_reference_pairs(
    page_data: Dict[str, Dict[str, any]]
) -> List[tuple]:
    """
    Build list of (parent_id, child_id) tuples from page data.

    Args:
        page_data: Dictionary of page data

    Returns:
        List[tuple]: List of (parent_id, child_id) tuples
    """
    reference_pairs = []
    
    for page_id, page_info in page_data.items():
        references = page_info.get('references', [])
        for child_id in references:
            # Only add if child page exists in our data
            if child_id in page_data:
                reference_pairs.append((page_id, child_id))
            else:
                # Still add it, but note that the child might not exist
                reference_pairs.append((page_id, child_id))
    
    return reference_pairs


def insert_references(
    conn: psycopg2.extensions.connection,
    reference_pairs: List[tuple]
) -> None:
    """
    Insert page references into the database.

    Args:
        conn: Database connection
        reference_pairs: List of (parent_id, child_id) tuples
    """
    cursor = conn.cursor()
    
    # Insert references using execute_batch for efficiency
    insert_query = """
        INSERT INTO page_references (parent_id, child_id)
        VALUES (%s, %s)
        ON CONFLICT (parent_id, child_id) DO NOTHING
    """
    
    execute_batch(cursor, insert_query, reference_pairs)
    conn.commit()
    
    print(f"Inserted {len(reference_pairs)} reference relationships")
    cursor.close()


def get_statistics(
    conn: psycopg2.extensions.connection
) -> Dict[str, any]:
    """
    Get statistics about the database.

    Args:
        conn: Database connection

    Returns:
        Dict[str, any]: Statistics dictionary
    """
    cursor = conn.cursor()
    
    stats = {}
    
    # Total pages
    cursor.execute("SELECT COUNT(*) FROM pages")
    stats['total_pages'] = cursor.fetchone()[0]
    
    # Total references
    cursor.execute("SELECT COUNT(*) FROM page_references")
    stats['total_references'] = cursor.fetchone()[0]
    
    # Pages with outgoing references
    cursor.execute("""
        SELECT COUNT(DISTINCT parent_id) 
        FROM page_references
    """)
    stats['pages_with_children'] = cursor.fetchone()[0]
    
    # Pages with incoming references
    cursor.execute("""
        SELECT COUNT(DISTINCT child_id) 
        FROM page_references
    """)
    stats['pages_with_parents'] = cursor.fetchone()[0]
    
    # Average references per page
    if stats['total_pages'] > 0:
        stats['avg_references_per_page'] = stats['total_references'] / stats['total_pages']
    else:
        stats['avg_references_per_page'] = 0
    
    cursor.close()
    return stats


def main():
    """
    Main function to insert data into PostgreSQL database.
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Insert page references into PostgreSQL database'
    )
    parser.add_argument(
        '--json-file',
        type=str,
        default='src/ref/page_references.json',
        help='Path to the JSON file containing page references (relative to project root or absolute)'
    )
    parser.add_argument(
        '--dbname',
        type=str,
        default='evergreen_notes',
        help='Database name'
    )
    parser.add_argument(
        '--user',
        type=str,
        default='postgres',
        help='Database user'
    )
    parser.add_argument(
        '--password',
        type=str,
        default=None,
        help='Database password (or set PGPASSWORD env var)'
    )
    parser.add_argument(
        '--host',
        type=str,
        default='localhost',
        help='Database host'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=5432,
        help='Database port'
    )
    
    args = parser.parse_args()
    
    # Resolve JSON file path (relative to script location or absolute)
    json_file_path = Path(args.json_file)
    if not json_file_path.is_absolute():
        # If relative, resolve from project root
        json_file_path = _project_root / json_file_path
    
    # Load page data
    print(f"Loading page data from {json_file_path}...")
    page_data = load_page_data(str(json_file_path))
    print(f"Loaded {len(page_data)} pages")
    
    # Connect to database
    print(f"Connecting to database {args.dbname}...")
    conn = get_db_connection(
        dbname=args.dbname,
        user=args.user,
        password=args.password,
        host=args.host,
        port=args.port
    )
    
    try:
        # Insert pages
        print("\nInserting pages...")
        insert_pages(conn, page_data)
        
        # Build and insert references
        print("\nBuilding reference relationships...")
        reference_pairs = build_reference_pairs(page_data)
        print(f"Found {len(reference_pairs)} reference relationships")
        
        print("\nInserting references...")
        insert_references(conn, reference_pairs)
        
        # Get and print statistics
        print("\n" + "="*50)
        print("Database Statistics:")
        print("="*50)
        stats = get_statistics(conn)
        for key, value in stats.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")
        
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()
        print("\nDatabase connection closed.")


if __name__ == '__main__':
    main()

