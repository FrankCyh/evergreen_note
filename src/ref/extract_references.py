"""
Script to extract page references from HTML files in the webpage directory.

For each HTML file, finds all links to other pages within the MarkdownContainer
div and creates a database mapping each page to the pages it references.
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, List, Set
from bs4 import BeautifulSoup


def extract_page_id_from_html(
    html_content: str,
    filename: str
) -> str:
    """
    Extract the page ID from the HTML content or filename.
    
    First tries to extract from the JSON data in the script tag,
    then falls back to filename extraction.
    
    Args:
        html_content: The HTML content as a string
        filename: The HTML filename (fallback)
        
    Returns:
        str: The page ID (slug), stripped of whitespace
    """
    # Try to extract from JSON data first
    soup = BeautifulSoup(html_content, 'html.parser')
    script_tag = soup.find('script', id='__NEXT_DATA__')
    
    if script_tag and script_tag.string:
        try:
            data = json.loads(script_tag.string)
            # Try to get from query.note
            if 'query' in data:
                page_id = data['query'].get('note')
                if page_id:
                    return page_id.strip()
            
            # Try to get from initialNoteCache keys
            props = data.get('props', {})
            page_props = props.get('pageProps', {})
            initial_cache = page_props.get('initialNoteCache', {})
            
            if initial_cache:
                # Get the first (and usually only) key
                page_id = list(initial_cache.keys())[0]
                if page_id:
                    return page_id.strip()
        except (json.JSONDecodeError, KeyError, AttributeError):
            pass
    
    # Fallback to filename extraction
    name_wo_ext = filename.replace('.html', '')
    
    # Find the last dash before the end
    last_dash_idx = name_wo_ext.rfind('-')
    
    if last_dash_idx != -1:
        # Extract the part after the last dash
        page_id = name_wo_ext[last_dash_idx + 1:]
        return page_id.strip()
    else:
        # No dash found, return the whole name
        return name_wo_ext.strip()


def extract_references_from_html(
    html_content: str
) -> Set[str]:
    """
    Extract all page references from the HTML content.
    
    Finds all <a href="/..."> links within <div class="MarkdownContainer">.
    The href should start with "/" and contain a page ID.
    
    Args:
        html_content: The HTML content as a string
        
    Returns:
        Set[str]: Set of referenced page IDs
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find the MarkdownContainer div
    markdown_container = soup.find('div', class_='MarkdownContainer')
    
    if not markdown_container:
        return set()
    
    # Find all <a> tags within the MarkdownContainer
    links = markdown_container.find_all('a', href=True)
    
    referenced_pages: Set[str] = set()
    
    for link in links:
        href = link.get('href', '')
        
        # Check if href starts with "/" (internal page reference)
        if href.startswith('/'):
            # Remove the leading "/" to get the page ID
            page_id = href[1:]
            
            # Only add if it looks like a valid page ID
            # (starts with 'z' and has alphanumeric characters)
            if page_id and re.match(r'^z[a-zA-Z0-9]+$', page_id):
                referenced_pages.add(page_id)
    
    return referenced_pages


def build_reference_database(
    webpage_dir: str
) -> Dict[str, Dict[str, any]]:
    """
    Build a database of page references from all HTML files.
    
    Args:
        webpage_dir: Path to the directory containing HTML files
        
    Returns:
        Dict[str, Dict[str, any]]: Database mapping page IDs to their metadata
        and references. Format:
        {
            "page_id": {
                "filename": "filename.html",
                "title": "Page Title",
                "references": ["ref_id1", "ref_id2", ...]
            },
            ...
        }
    """
    webpage_path = Path(webpage_dir)
    
    if not webpage_path.exists():
        raise ValueError(f"Directory {webpage_dir} does not exist")
    
    database: Dict[str, Dict[str, any]] = {}
    
    # Get all HTML files
    html_files = list(webpage_path.glob('*.html'))

    print(f"Processing {len(html_files)} HTML files...")
    
    for html_file in html_files:
        try:
            # Read HTML content
            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Extract page ID from HTML (or filename as fallback)
            page_id = extract_page_id_from_html(html_content, html_file.name)
            
            # Skip if page_id is empty
            if not page_id:
                print(f"Warning: Could not extract page ID from {html_file.name}")
                continue
            
            # Extract title from HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            title_tag = soup.find('title')
            title = title_tag.get_text() if title_tag else html_file.stem
            
            # Extract references
            references = extract_references_from_html(html_content)
            
            # Store in database
            database[page_id] = {
                "filename": html_file.name,
                "title": title,
                "references": sorted(list(references))  # Sort for consistency
            }
            
        except Exception as e:
            print(f"Error processing {html_file.name}: {e}")
            continue
    
    return database


def main():
    """
    Main function to extract references and save to JSON.
    """
    # Get paths relative to project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent
    webpage_dir = project_root / 'webpage'
    
    # Build the database
    database = build_reference_database(str(webpage_dir))
    
    # Save to JSON file in the ref directory
    output_file = script_dir / 'page_references.json'
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(database, f, indent=2, ensure_ascii=False)
    
    # Print summary statistics
    total_pages = len(database)
    pages_w_references = sum(1 for page_data in database.values() 
                            if page_data['references'])
    total_references = sum(len(page_data['references']) 
                          for page_data in database.values())
    
    print(f"\nSummary:")
    print(f"  Total pages: {total_pages}")
    print(f"  Pages with references: {pages_w_references}")
    print(f"  Total references: {total_references}")
    print(f"  Average references per page: {total_references / total_pages:.2f}")
    print(f"\nDatabase saved to: {output_file}")


if __name__ == '__main__':
    main()

