import copy
import json
import os
import re
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)
from urllib.parse import (
    parse_qs,
    urlparse,
)

from bs4 import BeautifulSoup


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WEBPAGE_DIR = PROJECT_ROOT / "webpage"
DEFAULT_REFERENCES_FILE = PROJECT_ROOT / "data" / "page_references.json"
NOTES_BASE_URL = "https://notes.andymatuschak.org"

TITLE_SUFFIX_T = (
    " | Andy Matuschak's Evergreen Notes",
    " - Andy Matuschak's Notes",
    " — Andy Matuschak's Notes",
)


def get_url_from_page_id(
    page_id: str,
    base_url: str = NOTES_BASE_URL,
) -> str:
    return f"{base_url.rstrip('/')}/{page_id}"


def get_page_id_from_url(
    url: str,
) -> str:
    """
    Extract the Evergreen Note page ID from a URL or return a bare page ID unchanged.

    Handles full URLs, relative paths, and stacked URLs (`?stackedNotes=<id>`).
    """
    parsed = urlparse(url)
    query_d = parse_qs(parsed.query)
    if "stackedNotes" in query_d and query_d["stackedNotes"]:
        return query_d["stackedNotes"][-1].strip()

    path = parsed.path.strip("/")
    if "/" in path:
        return path.split("/")[-1].strip()
    if path:
        return path.strip()
    return url.strip()


def get_stacked_url(
    base_url: str,
    note_path_l: List[str],
) -> str:
    if not note_path_l:
        return base_url

    query_params = "&".join([f"stackedNotes={note_id}" for note_id in note_path_l])
    return f"{base_url}?{query_params}"


def sanitize_filename(
    name: str,
) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", name)
    sanitized = sanitized.strip(" .")
    if len(sanitized) > 200:
        sanitized = sanitized[:200]
    return sanitized


def get_webpage_file_path(
    webpage_dir: Union[str, Path],
    page_id: str,
    page_name: str,
) -> Path:
    sanitized_name = sanitize_filename(page_name)
    return Path(webpage_dir) / f"{sanitized_name}-{page_id}.html"


def find_webpage_file(
    webpage_dir: Union[str, Path],
    page_id: str,
) -> Optional[Tuple[Path, str]]:
    """
    Locate a downloaded HTML file in `webpage_dir` matching `*-{page_id}.html` or `{page_id}.html`.

    Returns:
        Optional[Tuple[Path, str]]: `(file_path, page_name)` if found, `None` otherwise
    """
    dir_path = Path(webpage_dir)
    if not dir_path.exists():
        return None

    suffix = f"-{page_id}.html"
    exact_name = f"{page_id}.html"
    for filename in sorted(os.listdir(dir_path)):
        if filename.endswith(suffix):
            name_part = filename[:-len(suffix)]
            return (dir_path / filename, name_part)
        if filename == exact_name:
            return (dir_path / filename, page_id)
    return None


def get_note_name_from_file(
    webpage_dir: Union[str, Path],
    page_id: str,
) -> Optional[str]:
    found = find_webpage_file(webpage_dir, page_id)
    if found is None:
        return None
    return found[1]


def get_stacked_name(
    webpage_dir: Union[str, Path],
    note_path_l: List[str],
    current_note_name: str,
) -> str:
    name_l: List[str] = []
    for note_id in note_path_l:
        note_name = get_note_name_from_file(webpage_dir, note_id)
        name_l.append(note_name if note_name else note_id)
    name_l.append(current_note_name)
    return "\n".join([f"{i + 1}. {name}" for i, name in enumerate(name_l)])


def get_webpage_html(
    webpage_dir: Union[str, Path],
    page_id: str,
    page_name: Optional[str] = None,
) -> Optional[str]:
    if page_name:
        candidate = get_webpage_file_path(webpage_dir, page_id, page_name)
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")

    found = find_webpage_file(webpage_dir, page_id)
    if found is None:
        return None
    return found[0].read_text(encoding="utf-8")


def create_webpage_html_file(
    webpage_dir: Union[str, Path],
    page_id: str,
    page_name: str,
    html_content: str,
) -> Path:
    file_path = get_webpage_file_path(webpage_dir, page_id, page_name)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(html_content, encoding="utf-8")
    return file_path


def get_page_id_from_html(
    html_content: str,
    filename: str = "",
) -> str:
    """
    Extract the page ID from `<script id="__NEXT_DATA__">` or fall back to the filename suffix after the last `-`.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")

    if script_tag and script_tag.string:
        try:
            data = json.loads(script_tag.string)
            if "query" in data:
                page_id = data["query"].get("note")
                if page_id:
                    return page_id.strip()

            initial_cache = data.get("props", {}).get("pageProps", {}).get("initialNoteCache", {})
            if initial_cache:
                page_id = list(initial_cache.keys())[0]
                if page_id:
                    return page_id.strip()
        except (json.JSONDecodeError, KeyError, AttributeError):
            pass

    name_without_ext = filename[:-5] if filename.endswith(".html") else filename
    last_dash_idx = name_without_ext.rfind("-")
    if last_dash_idx != -1:
        return name_without_ext[last_dash_idx + 1:].strip()
    return name_without_ext.strip()


def get_title_from_html(
    html_content: str,
    fallback: str = "",
) -> str:
    soup = BeautifulSoup(html_content, "html.parser")
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text().strip()
        for suffix in TITLE_SUFFIX_T:
            if title.endswith(suffix):
                title = title[:-len(suffix)].strip()
        if title:
            return title
    return fallback


def get_title_and_html_from_page_id(
    page_id: str,
    webpage_dir: Union[str, Path] = DEFAULT_WEBPAGE_DIR,
    file_location: Optional[str] = None,
) -> Tuple[str, str]:
    dir_path = Path(webpage_dir)
    html_path: Optional[Path] = None

    if file_location:
        candidate = dir_path / file_location
        if candidate.exists():
            html_path = candidate

    if html_path is None:
        found = find_webpage_file(dir_path, page_id)
        assert found is not None, f"No HTML file found for page_id: {page_id}"
        html_path = found[0]

    html_content = html_path.read_text(encoding="utf-8")
    title = get_title_from_html(html_content, fallback=html_path.stem)
    return title, html_content


def get_main_content_html(
    html_content: str,
    base_url: str = NOTES_BASE_URL,
) -> str:
    """
    Extract the main note content HTML before `<hr>` (excluding backlinks and footer), remove `<h1>`, and normalize internal links to absolute URLs.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    main_container = None
    for div in soup.find_all("div", class_=lambda x: x and "jsx-1017266111" in x):
        parent = div.find_parent("div", class_=lambda x: x and "NoteContents" in " ".join(x if isinstance(x, list) else [x]))
        if parent:
            main_container = div
            break

    if not main_container:
        main_container = soup.find("div", class_="MarkdownContainer")

    assert main_container is not None, "Could not find main content container in HTML"

    content_copy = copy.copy(main_container)

    hr_tag = content_copy.find("hr")
    if hr_tag:
        elements_to_remove_l = []
        current = hr_tag
        while current:
            elements_to_remove_l.append(current)
            current = current.find_next_sibling()
        for elem in elements_to_remove_l:
            elem.decompose()

    for h1 in content_copy.find_all("h1"):
        h1.decompose()

    normalized_base = base_url.rstrip("/")
    for link in content_copy.find_all("a", href=True):
        href = link["href"]
        if href.startswith("/"):
            link["href"] = f"{normalized_base}{href}"
        span = link.find("span")
        if span:
            link.string = span.get_text()

    return str(content_copy)


def get_note_link_l_from_html(
    html_content: str,
    current_note_id: Optional[str] = None,
) -> List[Tuple[str, str]]:
    """
    Extract `(note_id, note_name)` pairs from internal `<a href="/...">` tags and `<script id="__NEXT_DATA__">`.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    note_link_l: List[Tuple[str, str]] = []
    seen_id_s: Set[str] = set()

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if href.startswith("/") and len(href) > 1:
            note_id = href.lstrip("/")
            if not re.match(r"^[a-zA-Z0-9_-]+$", note_id):
                continue
            if current_note_id and note_id == current_note_id:
                continue
            if note_id in seen_id_s:
                continue

            span = link.find("span")
            note_name = span.get_text(strip=True) if span else link.get_text(strip=True)
            if not note_name:
                note_name = note_id

            note_link_l.append((note_id, note_name))
            seen_id_s.add(note_id)

    script_tag = soup.find("script", id="__NEXT_DATA__")
    if script_tag and script_tag.string:
        try:
            data = json.loads(script_tag.string)
            initial_cache = data.get("props", {}).get("pageProps", {}).get("initialNoteCache", {})
            for note_key, note_data in initial_cache.items():
                if current_note_id and note_key != current_note_id:
                    continue

                linked_slug_l = note_data.get("data", {}).get("linkedNoteSlugs", [])
                for slug in linked_slug_l:
                    if current_note_id and slug == current_note_id:
                        continue
                    if slug in seen_id_s:
                        continue

                    link_tag = soup.find("a", href=f"/{slug}")
                    if link_tag:
                        span = link_tag.find("span")
                        note_name = span.get_text(strip=True) if span else link_tag.get_text(strip=True)
                        if not note_name:
                            note_name = slug
                    else:
                        note_name = slug

                    note_link_l.append((slug, note_name))
                    seen_id_s.add(slug)
        except (json.JSONDecodeError, KeyError, AttributeError):
            pass

    return note_link_l


def get_reference_id_s_from_html(
    html_content: str,
    current_note_id: Optional[str] = None,
) -> Set[str]:
    """
    Extract referenced `z...` page IDs from `<a href="/...">` inside `<div class="MarkdownContainer">`.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    markdown_container = soup.find("div", class_="MarkdownContainer")
    if not markdown_container:
        return set()

    referenced_page_s: Set[str] = set()
    for link in markdown_container.find_all("a", href=True):
        href = link.get("href", "")
        if href.startswith("/"):
            page_id = href[1:]
            if page_id and re.match(r"^z[a-zA-Z0-9]+$", page_id):
                if current_note_id and page_id == current_note_id:
                    continue
                referenced_page_s.add(page_id)

    return referenced_page_s


def create_reference_database(
    webpage_dir: Union[str, Path] = DEFAULT_WEBPAGE_DIR,
    output_file: Optional[Union[str, Path]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Scan all HTML files in `webpage_dir` and build a mapping from `page_id` to `filename`, `title`, and sorted `references`.
    """
    webpage_path = Path(webpage_dir)
    assert webpage_path.exists(), f"Directory {webpage_dir} does not exist"

    database_d: Dict[str, Dict[str, Any]] = {}
    html_file_l = sorted(webpage_path.glob("*.html"))

    for html_file in html_file_l:
        html_content = html_file.read_text(encoding="utf-8")
        page_id = get_page_id_from_html(html_content, html_file.name)
        if not page_id:
            continue

        title = get_title_from_html(html_content, fallback=html_file.stem)
        reference_s = get_reference_id_s_from_html(html_content)

        database_d[page_id] = {
            "filename": html_file.name,
            "title": title,
            "references": sorted(list(reference_s)),
        }

    if output_file is not None:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(database_d, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return database_d


def main() -> None:
    database_d = create_reference_database(
        webpage_dir=DEFAULT_WEBPAGE_DIR,
        output_file=DEFAULT_REFERENCES_FILE,
    )
    total_pages = len(database_d)
    pages_with_references = sum(1 for page_data in database_d.values() if page_data["references"])
    total_references = sum(len(page_data["references"]) for page_data in database_d.values())
    avg_references = total_references / total_pages if total_pages > 0 else 0.0

    print("Summary:")
    print(f"  Total pages: {total_pages}")
    print(f"  Pages with references: {pages_with_references}")
    print(f"  Total references: {total_references}")
    print(f"  Average references per page: {avg_references:.2f}")
    print(f"Database saved to: {DEFAULT_REFERENCES_FILE}")


if __name__ == "__main__":
    main()
