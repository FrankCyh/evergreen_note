import os
import json
import re
from typing import (
    List,
    Tuple,
    Optional,
)
from bs4 import BeautifulSoup


def sanitize_filename(
    name: str,
) -> str:
    """
    Sanitize a filename by removing invalid characters.

    Args:
        name: Original filename

    Returns:
        str: Sanitized filename safe for filesystem
    """
    # Remove or replace invalid filename characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip(' .')
    # Limit length
    if len(sanitized) > 200:
        sanitized = sanitized[:200]
    return sanitized


def get_file_path(
    output_dir: str,
    note_id: str,
    note_name: str,
) -> str:
    """
    Get the file path for a note.

    Args:
        output_dir: Directory where notes are stored
        note_id: Note ID (e.g., "z5E5QawiXCMbtNtupvxeoEX")
        note_name: Note name (e.g., "Evergreen notes")

    Returns:
        str: File path for the note
    """
    sanitized_name = sanitize_filename(note_name)
    filename = f"{sanitized_name}-{note_id}.html"
    return os.path.join(output_dir, filename)


def extract_note_links(
    html_content: str,
    current_note_id: Optional[str] = None,
) -> List[Tuple[str, str]]:
    """
    Extract note links from HTML content.

    Args:
        html_content: HTML content of the page
        current_note_id: Optional note ID of the current note to filter out self-references

    Returns:
        List[Tuple[str, str]]: List of (note_id, note_name) tuples
    """
    soup = BeautifulSoup(html_content, "html.parser")
    note_links: List[Tuple[str, str]] = []

    # Find all anchor tags with href starting with "/"
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        # Check if it's a note link (starts with / and contains alphanumeric ID)
        if href.startswith("/") and len(href) > 1:
            # Extract note ID from href (remove leading /)
            note_id = href.lstrip("/")
            # Skip if it's not a valid note ID format (should be alphanumeric)
            if not re.match(r'^[a-zA-Z0-9_-]+$', note_id):
                continue
            
            # Skip self-references
            if current_note_id and note_id == current_note_id:
                continue

            # Try to get note name from span or text content
            note_name = ""
            span = link.find("span")
            if span:
                note_name = span.get_text(strip=True)
            else:
                note_name = link.get_text(strip=True)

            # If no name found, use the ID
            if not note_name:
                note_name = note_id

            note_links.append((note_id, note_name))

    # Also try to extract from JSON script tag (more reliable)
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if script_tag:
        try:
            data = json.loads(script_tag.string)
            # Navigate through the JSON structure to find linkedNoteSlugs
            if "props" in data:
                page_props = data["props"].get("pageProps", {})
                initial_cache = page_props.get("initialNoteCache", {})
                for note_key, note_data in initial_cache.items():
                    # Only extract links from the current note if current_note_id is provided
                    if current_note_id and note_key != current_note_id:
                        continue
                    
                    note_info = note_data.get("data", {})
                    linked_slugs = note_info.get("linkedNoteSlugs", [])
                    title = note_info.get("title", note_key)

                    # For each linked slug, try to find the name in the HTML
                    for slug in linked_slugs:
                        # Skip self-references
                        if current_note_id and slug == current_note_id:
                            continue
                        
                        # Try to find the link with this slug
                        link_tag = soup.find("a", href=f"/{slug}")
                        if link_tag:
                            span = link_tag.find("span")
                            if span:
                                note_name = span.get_text(strip=True)
                            else:
                                note_name = link_tag.get_text(strip=True)
                            if not note_name:
                                note_name = slug
                        else:
                            note_name = slug

                        # Add to note_links if not already present
                        if (slug, note_name) not in note_links:
                            note_links.append((slug, note_name))
        except (json.JSONDecodeError, KeyError):
            pass

    return note_links


def get_note_name_from_file(
    output_dir: str,
    note_id: str,
) -> Optional[str]:
    """
    Try to get note name from an already downloaded file.

    Args:
        output_dir: Directory where notes are stored
        note_id: Note ID

    Returns:
        Optional[str]: Note name if found, None otherwise
    """
    # Search for files ending with the note_id
    if not os.path.exists(output_dir):
        return None
    
    for filename in os.listdir(output_dir):
        if filename.endswith(f"-{note_id}.html"):
            # Extract name from filename
            name_part = filename[:-len(f"-{note_id}.html")]
            return name_part
    return None


def read_note_from_file(
    output_dir: str,
    note_id: str,
    note_name: str,
) -> Optional[str]:
    """
    Read a note's HTML content from a file.

    Args:
        output_dir: Directory where notes are stored
        note_id: Note ID
        note_name: Note name

    Returns:
        Optional[str]: HTML content if file exists, None otherwise
    """
    file_path = get_file_path(output_dir, note_id, note_name)
    if not os.path.exists(file_path):
        return None
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except IOError:
        return None


def find_note_file(
    output_dir: str,
    note_id: str,
) -> Optional[Tuple[str, str]]:
    """
    Find a note file by ID and return both the file path and note name.

    Args:
        output_dir: Directory where notes are stored
        note_id: Note ID to find

    Returns:
        Optional[Tuple[str, str]]: (file_path, note_name) if found, None otherwise
    """
    if not os.path.exists(output_dir):
        return None
    
    for filename in os.listdir(output_dir):
        if filename.endswith(f"-{note_id}.html"):
            file_path = os.path.join(output_dir, filename)
            # Extract name from filename
            name_part = filename[:-len(f"-{note_id}.html")]
            return (file_path, name_part)
    return None

