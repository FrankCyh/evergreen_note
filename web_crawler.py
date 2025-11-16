import os
import json
import time
from typing import (
    List,
    Dict,
    Tuple,
    Optional,
)
from urllib.parse import urljoin
import requests
from note_utils import (
    get_file_path,
    extract_note_links,
    get_note_name_from_file,
)


class NoteCrawler:
    """
    Web crawler for downloading notes with DFS traversal, checkpointing, and restore.

    Crawls notes starting from a seed page, following all note references.
    Uses iterative DFS to avoid recursion limits.
    Saves checkpoints to allow resuming after interruptions.
    """

    def __init__(
        self,
        base_url: str,
        output_dir: str,
        checkpoint_file: str = "checkpoint.json",
        delay: float = 1.0,
    ):
        """
        Initialize the crawler.

        Args:
            base_url: Base URL of the notes website (e.g., "https://notes.andymatuschak.org")
            output_dir: Directory to save downloaded notes
            checkpoint_file: Path to checkpoint file for saving/restoring state
            delay: Delay between requests in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.output_dir = output_dir
        self.checkpoint_file = checkpoint_file
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

        # Stack for iterative DFS: list of (note_id, note_name) tuples
        self.stack: List[Tuple[str, str]] = []
        # Track visited note IDs to avoid duplicates
        self.visited: set = set()

        # Create output directory if it doesn't exist
        os.makedirs(self.output_dir, exist_ok=True)

    def _is_note_downloaded(
        self,
        note_id: str,
        note_name: str,
    ) -> bool:
        """
        Check if a note is already downloaded by checking if file exists.

        Args:
            note_id: Note ID
            note_name: Note name

        Returns:
            bool: True if file exists, False otherwise
        """
        file_path = get_file_path(self.output_dir, note_id, note_name)
        return os.path.exists(file_path)

    def _download_note(
        self,
        note_id: str,
    ) -> Optional[str]:
        """
        Download a note from the website.

        Args:
            note_id: Note ID to download

        Returns:
            Optional[str]: HTML content if successful, None otherwise
        """
        url = urljoin(self.base_url, f"/{note_id}")
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"Error downloading {note_id}: {e}")
            return None

    def _save_note(
        self,
        note_id: str,
        note_name: str,
        html_content: str,
    ) -> bool:
        """
        Save a note to disk.

        Args:
            note_id: Note ID
            note_name: Note name
            html_content: HTML content to save

        Returns:
            bool: True if successful, False otherwise
        """
        file_path = get_file_path(self.output_dir, note_id, note_name)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            return True
        except IOError as e:
            print(f"Error saving {note_id} to {file_path}: {e}")
            return False

    def _save_checkpoint(self) -> None:
        """
        Save current state to checkpoint file.
        """
        checkpoint_data = {
            "stack": self.stack,
            "visited": list(self.visited),
        }
        try:
            with open(self.checkpoint_file, "w", encoding="utf-8") as f:
                json.dump(checkpoint_data, f, indent=2)
            print(f"Checkpoint saved: {len(self.stack)} items in stack, {len(self.visited)} visited")
        except IOError as e:
            print(f"Error saving checkpoint: {e}")

    def _load_checkpoint(self) -> bool:
        """
        Load state from checkpoint file.

        Returns:
            bool: True if checkpoint loaded successfully, False otherwise
        """
        if not os.path.exists(self.checkpoint_file):
            return False

        try:
            with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                checkpoint_data = json.load(f)
            self.stack = [tuple(item) for item in checkpoint_data.get("stack", [])]
            self.visited = set(checkpoint_data.get("visited", []))
            print(f"Checkpoint loaded: {len(self.stack)} items in stack, {len(self.visited)} visited")
            return True
        except (IOError, json.JSONDecodeError, KeyError) as e:
            print(f"Error loading checkpoint: {e}")
            return False


    def crawl(
        self,
        start_note_id: str,
        start_note_name: str = "",
        restore_from_checkpoint: bool = True,
    ) -> None:
        """
        Start crawling notes using iterative DFS.

        Args:
            start_note_id: Starting note ID
            start_note_name: Starting note name (optional)
            restore_from_checkpoint: Whether to restore from checkpoint if available
        """
        # Try to restore from checkpoint
        if restore_from_checkpoint:
            if self._load_checkpoint():
                print("Resuming from checkpoint...")
            else:
                print("No checkpoint found, starting fresh...")
                # Initialize with starting note
                if start_note_name:
                    self.stack.append((start_note_id, start_note_name))
                else:
                    # Try to get name from file if it exists
                    name = get_note_name_from_file(self.output_dir, start_note_id)
                    if not name:
                        name = start_note_id
                    self.stack.append((start_note_id, name))

        # Main crawling loop
        while self.stack:
            # Pop from stack (DFS: LIFO)
            note_id, note_name = self.stack.pop()

            # Skip if already visited
            if note_id in self.visited:
                continue

            # Check if already downloaded
            if self._is_note_downloaded(note_id, note_name):
                print(f"Already downloaded: {note_name} ({note_id})")
                self.visited.add(note_id)
                # Still need to process links from this note
                file_path = get_file_path(self.output_dir, note_id, note_name)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        html_content = f.read()
                    note_links = extract_note_links(html_content, current_note_id=note_id)
                    # Add unvisited links to stack (in reverse order for DFS)
                    for link_id, link_name in reversed(note_links):
                        if link_id not in self.visited:
                            self.stack.append((link_id, link_name))
                except IOError:
                    pass
                continue

            # Download the note
            print(f"Downloading: {note_name} ({note_id})")
            html_content = self._download_note(note_id)
            if html_content is None:
                print(f"Failed to download {note_id}, skipping...")
                continue

            # Save the note
            if self._save_note(note_id, note_name, html_content):
                print(f"Saved: {note_name} ({note_id})")
            else:
                print(f"Failed to save {note_id}, continuing...")

            # Mark as visited
            self.visited.add(note_id)

            # Extract links and add to stack
            note_links = extract_note_links(html_content, current_note_id=note_id)
            print(f"  Found {len(note_links)} links")
            # Add unvisited links to stack (in reverse order for DFS)
            for link_id, link_name in reversed(note_links):
                if link_id not in self.visited:
                    self.stack.append((link_id, link_name))

            # Save checkpoint periodically
            self._save_checkpoint()

            # Delay between requests
            if self.delay > 0:
                time.sleep(self.delay)

        print("Crawling completed!")
        # Clean up checkpoint file
        if os.path.exists(self.checkpoint_file):
            os.remove(self.checkpoint_file)
            print("Checkpoint file removed.")


def main():
    """
    Main function to run the crawler.
    """
    # Configuration
    BASE_URL = "https://notes.andymatuschak.org"
    OUTPUT_DIR = "webpage"
    CHECKPOINT_FILE = "checkpoint.json"
    START_NOTE_ID = "About_these_notes"
    START_NOTE_NAME = "About these notes"
    DELAY = 1.0  # Delay between requests in seconds

    # Create crawler
    crawler = NoteCrawler(
        base_url=BASE_URL,
        output_dir=OUTPUT_DIR,
        checkpoint_file=CHECKPOINT_FILE,
        delay=DELAY,
    )

    # Start crawling
    crawler.crawl(
        start_note_id=START_NOTE_ID,
        start_note_name=START_NOTE_NAME,
        restore_from_checkpoint=True,
    )


if __name__ == "__main__":
    main()

