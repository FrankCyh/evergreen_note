from pathlib import Path
from typing import Dict

from src.dfs_filter import DFSFilter
from src.test_crawler import HTML_BY_ID_D
from src.webpage import create_webpage_html_file


def test_dfs_filter_keep_skip_and_skip_all(
    tmp_path: Path,
) -> None:
    webpage_dir = tmp_path / "webpage"
    for note_id, html in HTML_BY_ID_D.items():
        title = "About these notes" if note_id == "About_these_notes" else f"Note {note_id[5]}"
        create_webpage_html_file(webpage_dir, note_id, title, html)

    choice_by_id_d = {
        "About_these_notes": "",
        "zNoteA111": "",
        "zNoteC333": "n",
        "zNoteB222": "N",
    }

    observed_stacked_name_d: Dict[str, str] = {}

    def prompt_fn(
        note_id: str,
        stacked_name: str,
        stacked_url: str,
    ) -> str:
        observed_stacked_name_d[note_id] = stacked_name
        return choice_by_id_d[note_id]

    output_file = tmp_path / "filtered_notes.json"
    dfs_filter = DFSFilter(
        webpage_dir=webpage_dir,
        output_file=output_file,
        prompt_fn=prompt_fn,
    )
    filtered_d = dfs_filter.filter_notes(
        start_note_id="About_these_notes",
        start_note_name="About these notes",
    )

    assert set(filtered_d.keys()) == {"About_these_notes", "zNoteA111"}
    assert filtered_d["zNoteA111"]["referenced_ids"] == ["zNoteC333"]
    assert observed_stacked_name_d["zNoteC333"] == "1. Note A\n2. Note C"
    assert output_file.exists()
