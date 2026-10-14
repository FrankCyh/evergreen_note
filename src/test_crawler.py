from pathlib import Path
from typing import (
    Dict,
    List,
    Optional,
)

from src.crawler import NoteCrawler


HTML_BY_ID_D: Dict[str, str] = {
    "About_these_notes": """
    <html>
      <head><title>About these notes</title></head>
      <body>
        <div class="MarkdownContainer">
          <a href="/zNoteA111"><span>Note A</span></a>
          <a href="/zNoteB222"><span>Note B</span></a>
        </div>
      </body>
    </html>
    """,
    "zNoteA111": """
    <html>
      <head><title>Note A</title></head>
      <body>
        <div class="MarkdownContainer">
          <a href="/zNoteC333"><span>Note C</span></a>
        </div>
      </body>
    </html>
    """,
    "zNoteB222": """
    <html>
      <head><title>Note B</title></head>
      <body>
        <div class="MarkdownContainer">
          <p>No outgoing links</p>
        </div>
      </body>
    </html>
    """,
    "zNoteC333": """
    <html>
      <head><title>Note C</title></head>
      <body>
        <div class="MarkdownContainer">
          <a href="/About_these_notes"><span>Cycle back to root</span></a>
        </div>
      </body>
    </html>
    """,
}


def test_note_crawler_dfs_and_checkpoint(
    tmp_path: Path,
) -> None:
    webpage_dir = tmp_path / "webpage"
    checkpoint_file = tmp_path / "checkpoint.json"

    crawler = NoteCrawler(
        output_dir=webpage_dir,
        checkpoint_file=checkpoint_file,
        delay=0.0,
    )

    downloaded_order_l: List[str] = []

    def fake_retrieve(
        note_id: str,
    ) -> Optional[str]:
        downloaded_order_l.append(note_id)
        return HTML_BY_ID_D.get(note_id)

    crawler.retrieve_note_html = fake_retrieve  # type: ignore[method-assign]
    crawler.crawl(
        start_note_id="About_these_notes",
        start_note_name="About these notes",
        restore_from_checkpoint=False,
    )

    assert downloaded_order_l == ["About_these_notes", "zNoteA111", "zNoteC333", "zNoteB222"]
    assert not checkpoint_file.exists()
    for note_id in HTML_BY_ID_D:
        assert crawler.is_note_downloaded(note_id)
