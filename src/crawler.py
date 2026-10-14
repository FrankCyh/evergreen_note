import json
import os
import time
from pathlib import Path
from typing import (
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

import requests

from src.webpage import (
    DEFAULT_WEBPAGE_DIR,
    NOTES_BASE_URL,
    create_webpage_html_file,
    find_webpage_file,
    get_note_link_l_from_html,
    get_note_name_from_file,
    get_url_from_page_id,
    get_webpage_file_path,
    get_webpage_html,
)


class NoteCrawler:
    """
    Web crawler for downloading Evergreen Notes using iterative DFS traversal with checkpointing and restore.
    """

    def __init__(
        self,
        base_url: str = NOTES_BASE_URL,
        output_dir: Union[str, Path] = DEFAULT_WEBPAGE_DIR,
        checkpoint_file: Union[str, Path] = "checkpoint.json",
        delay: float = 1.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.output_dir = Path(output_dir)
        self.checkpoint_file = Path(checkpoint_file)
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

        self.stack_l: List[Tuple[str, str]] = []
        self.visited_s: Set[str] = set()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def is_note_downloaded(
        self,
        note_id: str,
        note_name: str = "",
    ) -> bool:
        if note_name and get_webpage_file_path(self.output_dir, note_id, note_name).exists():
            return True
        return find_webpage_file(self.output_dir, note_id) is not None

    def retrieve_note_html(
        self,
        note_id: str,
    ) -> Optional[str]:
        url = get_url_from_page_id(note_id, base_url=self.base_url)
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return response.text

    def create_checkpoint(self) -> None:
        checkpoint_d = {
            "stack": self.stack_l,
            "visited": list(self.visited_s),
        }
        self.checkpoint_file.write_text(
            json.dumps(checkpoint_d, indent=2),
            encoding="utf-8",
        )
        print(f"Checkpoint saved: {len(self.stack_l)} items in stack, {len(self.visited_s)} visited")

    def get_checkpoint(self) -> bool:
        if not self.checkpoint_file.exists():
            return False

        checkpoint_d = json.loads(self.checkpoint_file.read_text(encoding="utf-8"))
        self.stack_l = [(item[0], item[1]) for item in checkpoint_d.get("stack", [])]
        self.visited_s = set(checkpoint_d.get("visited", []))
        print(f"Checkpoint loaded: {len(self.stack_l)} items in stack, {len(self.visited_s)} visited")
        return True

    def crawl(
        self,
        start_note_id: str = "About_these_notes",
        start_note_name: str = "About these notes",
        restore_from_checkpoint: bool = True,
    ) -> None:
        if restore_from_checkpoint and self.get_checkpoint():
            print("Resuming from checkpoint...")
        else:
            print("No checkpoint found, starting fresh...")
            initial_name = start_note_name or get_note_name_from_file(self.output_dir, start_note_id) or start_note_id
            self.stack_l.append((start_note_id, initial_name))

        while self.stack_l:
            note_id, note_name = self.stack_l.pop()
            if note_id in self.visited_s:
                continue

            if self.is_note_downloaded(note_id, note_name):
                print(f"Already downloaded: {note_name} ({note_id})")
                self.visited_s.add(note_id)
                html_content = get_webpage_html(self.output_dir, note_id, note_name)
                if html_content is not None:
                    note_link_l = get_note_link_l_from_html(html_content, current_note_id=note_id)
                    for link_id, link_name in reversed(note_link_l):
                        if link_id not in self.visited_s:
                            self.stack_l.append((link_id, link_name))
                continue

            print(f"Downloading: {note_name} ({note_id})")
            html_content = self.retrieve_note_html(note_id)
            if html_content is None:
                continue

            create_webpage_html_file(self.output_dir, note_id, note_name, html_content)
            print(f"Saved: {note_name} ({note_id})")
            self.visited_s.add(note_id)

            note_link_l = get_note_link_l_from_html(html_content, current_note_id=note_id)
            print(f"  Found {len(note_link_l)} links")
            for link_id, link_name in reversed(note_link_l):
                if link_id not in self.visited_s:
                    self.stack_l.append((link_id, link_name))

            self.create_checkpoint()
            if self.delay > 0:
                time.sleep(self.delay)

        print("Crawling completed!")
        if self.checkpoint_file.exists():
            os.remove(self.checkpoint_file)
            print("Checkpoint file removed.")


def main() -> None:
    crawler = NoteCrawler(
        base_url=NOTES_BASE_URL,
        output_dir=DEFAULT_WEBPAGE_DIR,
        checkpoint_file=DEFAULT_WEBPAGE_DIR.parent / "data" / "crawler_checkpoint.json",
        delay=1.0,
    )
    crawler.crawl(
        start_note_id="About_these_notes",
        start_note_name="About these notes",
        restore_from_checkpoint=True,
    )


if __name__ == "__main__":
    main()
