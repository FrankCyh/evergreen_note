import json
from pathlib import Path

from src.webpage import (
    DEFAULT_WEBPAGE_DIR,
    NOTES_BASE_URL,
    create_reference_database,
    create_webpage_html_file,
    find_webpage_file,
    get_main_content_html,
    get_note_link_l_from_html,
    get_note_name_from_file,
    get_page_id_from_html,
    get_page_id_from_url,
    get_reference_id_s_from_html,
    get_stacked_name,
    get_stacked_url,
    get_title_and_html_from_page_id,
    get_title_from_html,
    get_url_from_page_id,
    get_webpage_html,
)


def test_url_and_page_id_conversion() -> None:
    page_id = "z9vSQjkBVL6dCVC6QhCu4Br"
    assert get_url_from_page_id(page_id) == f"{NOTES_BASE_URL}/{page_id}"
    assert get_page_id_from_url(f"{NOTES_BASE_URL}/{page_id}") == page_id
    assert get_page_id_from_url(f"/{page_id}") == page_id
    assert get_page_id_from_url(page_id) == page_id

    stacked_url = get_stacked_url(
        f"{NOTES_BASE_URL}/About_these_notes",
        ["zFirstNote123", page_id],
    )
    assert stacked_url == f"{NOTES_BASE_URL}/About_these_notes?stackedNotes=zFirstNote123&stackedNotes={page_id}"
    assert get_page_id_from_url(stacked_url) == page_id


def test_get_page_id_and_title_from_html() -> None:
    next_data_d = {
        "query": {"note": "zTestNoteId123"},
    }
    html = (
        f"<html><head><title>Sample Note | Andy Matuschak's Evergreen Notes</title></head>"
        f"<body><script id='__NEXT_DATA__'>{json.dumps(next_data_d)}</script></body></html>"
    )
    assert get_page_id_from_html(html, "Fallback-zFallback999.html") == "zTestNoteId123"
    assert get_title_from_html(html) == "Sample Note"

    fallback_html = "<html><head></head><body>No title</body></html>"
    assert get_page_id_from_html(fallback_html, "My Note Title-zFallback999.html") == "zFallback999"
    assert get_title_from_html(fallback_html, fallback="Fallback Title") == "Fallback Title"


def test_get_main_content_html_strips_header_and_backlinks() -> None:
    raw_html = """
    <html>
      <body>
        <div class="NoteContents">
          <div class="jsx-1017266111 MarkdownContainer">
            <h1>Note Heading</h1>
            <p>Body with <a href="/zChildPage123"><span>linked note</span></a>.</p>
            <hr/>
            <div class="Backlinks">
              <a href="/zBacklinkPage456">Backlink</a>
            </div>
          </div>
        </div>
      </body>
    </html>
    """
    main_html = get_main_content_html(raw_html)
    assert "<h1>" not in main_html
    assert "<hr" not in main_html
    assert "zBacklinkPage456" not in main_html
    assert f'href="{NOTES_BASE_URL}/zChildPage123"' in main_html
    assert ">linked note</a>" in main_html


def test_extract_links_and_references() -> None:
    next_data_d = {
        "props": {
            "pageProps": {
                "initialNoteCache": {
                    "zCurrentNote": {
                        "data": {
                            "linkedNoteSlugs": ["zChildOne111", "zChildTwo222", "zCurrentNote"],
                        },
                    },
                },
            },
        },
    }
    html = f"""
    <html>
      <body>
        <div class="MarkdownContainer">
          <a href="/zChildOne111"><span>Child One</span></a>
          <a href="/zCurrentNote"><span>Self Link</span></a>
          <a href="https://example.com">External</a>
        </div>
        <script id="__NEXT_DATA__">{json.dumps(next_data_d)}</script>
      </body>
    </html>
    """
    link_l = get_note_link_l_from_html(html, current_note_id="zCurrentNote")
    assert link_l == [
        ("zChildOne111", "Child One"),
        ("zChildTwo222", "zChildTwo222"),
    ]

    ref_s = get_reference_id_s_from_html(html, current_note_id="zCurrentNote")
    assert ref_s == {"zChildOne111"}


def test_local_webpage_file_operations_and_reference_db(
    tmp_path: Path,
) -> None:
    html_a = """
    <html>
      <head><title>Alpha Note</title></head>
      <body>
        <div class="MarkdownContainer">
          <p><a href="/zBetaNote222"><span>Beta Note</span></a></p>
        </div>
      </body>
    </html>
    """
    html_b = """
    <html>
      <head><title>Beta Note</title></head>
      <body>
        <div class="MarkdownContainer">
          <p>Leaf content.</p>
        </div>
      </body>
    </html>
    """
    create_webpage_html_file(tmp_path, "zAlphaNote111", "Alpha Note", html_a)
    create_webpage_html_file(tmp_path, "zBetaNote222", "Beta Note", html_b)

    found_a = find_webpage_file(tmp_path, "zAlphaNote111")
    assert found_a is not None
    assert found_a[1] == "Alpha Note"
    assert get_note_name_from_file(tmp_path, "zAlphaNote111") == "Alpha Note"
    assert get_webpage_html(tmp_path, "zAlphaNote111") == html_a

    stacked_name = get_stacked_name(tmp_path, ["zAlphaNote111"], "Beta Note")
    assert stacked_name == "1. Alpha Note\n2. Beta Note"

    output_json = tmp_path / "refs.json"
    db_d = create_reference_database(webpage_dir=tmp_path, output_file=output_json)
    assert output_json.exists()
    assert db_d["zAlphaNote111"]["title"] == "Alpha Note"
    assert db_d["zAlphaNote111"]["references"] == ["zBetaNote222"]
    assert db_d["zBetaNote222"]["references"] == []


def test_real_webpage_lookup() -> None:
    title, html = get_title_and_html_from_page_id(
        "z9vSQjkBVL6dCVC6QhCu4Br",
        webpage_dir=DEFAULT_WEBPAGE_DIR,
    )
    assert title == "Spaced repetition memory prompts should be concise"
    main_html = get_main_content_html(html)
    assert "Spaced repetition memory system" in main_html
