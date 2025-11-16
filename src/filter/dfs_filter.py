import os
import sys
import json
from pathlib import Path
from typing import (
    List,
    Dict,
    Tuple,
    Optional,
    Union,
)

# Add project root to path for imports
_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root / "src"))

from util.note_utils import (
    extract_note_links,
    read_note_from_file,
    find_note_file,
    get_note_name_from_file,
)


def build_stacked_url(
    base_url: str,
    note_path: List[str],
) -> str:
    """
    Build a stacked URL from a list of note IDs.

    Args:
        base_url: Base URL (e.g., "https://notes.andymatuschak.org/About_these_notes")
        note_path: List of note IDs in the path

    Returns:
        str: Stacked URL with query parameters
    """
    if not note_path:
        return base_url
    
    query_params = "&".join([f"stackedNotes={note_id}" for note_id in note_path])
    return f"{base_url}?{query_params}"


def build_stacked_name(
    webpage_dir: str,
    note_path: List[str],
    current_note_id: str,
    current_note_name: str,
) -> str:
    """
    Build a stacked name from a list of note IDs in the format "name_1 → name_2 → name_3".

    Args:
        webpage_dir: Directory containing downloaded HTML files
        note_path: List of note IDs in the path
        current_note_id: Current note ID
        current_note_name: Current note name

    Returns:
        str: Stacked name with arrow separators
    """
    name_l: List[str] = []
    
    # Get names for each note ID in the path
    for note_id in note_path:
        note_name = get_note_name_from_file(webpage_dir, note_id)
        if note_name:
            name_l.append(note_name)
        else:
            name_l.append(note_id)
    
    # Add current note name
    name_l.append(current_note_name)
    
    # Join with arrow separator
    return "\n".join([f"{i+1}. {name}" for i, name in enumerate(name_l)])


class DFSFilter:
    """
    Depth-first search filter for notes with interactive filtering.

    Traverses notes starting from a seed page, following all note references.
    Uses DFS traversal and interactive filtering to decide which notes to keep.
    """

    def __init__(
        self,
        base_url: str,
        webpage_dir: str,
        output_file: str = "filtered_notes.json",
    ):
        """
        Initialize the filter.

        Args:
            base_url: Base URL of the notes website (e.g., "https://notes.andymatuschak.org/About_these_notes")
            webpage_dir: Directory containing downloaded HTML files
            output_file: Path to JSON file for saving filtered notes
        """
        self.base_url = base_url.rstrip("/")
        self.webpage_dir = webpage_dir
        self.output_file = output_file
        
        # Track filtered notes: {note_id: {name, id, url, referenced_ids}}
        self.filtered_notes: Dict[str, Dict[str, any]] = {}
        
        # Track visited note IDs to avoid duplicates
        self.visited: set = set()
        
        # Checkpoint file path
        self.checkpoint_file = output_file.replace(".json", "_checkpoint.json")
        
        # Track checkpoint save count for less verbose output
        self.checkpoint_save_count = 0

    def _ask_user_to_keep(
        self,
        note_id: str,
        stacked_name: str,
        stacked_url: str,
    ) -> str:
        """
        Ask user if they want to keep this note.

        Args:
            note_id: Note ID
            note_name: Note name
            stacked_name: Stacked name for the note (e.g., "name_1 → name_2")

        Returns:
            str: "Yes" if user wants to keep, "No" if skip, "Skip_all" if skip all at this level
        """
        print(f"\n🔗: {stacked_url}")
        print(f"\n{stacked_name}")
        user_input = input("Keep? (y/n/N)").strip()
        
        if user_input == "":
            return "Yes"
        elif user_input == "n":
            return "No"
        elif user_input == "N":
            return "Skip_all"
        else:
            # Default to Yes for any other input
            return "Yes"

    def _process_note(
        self,
        note_id: str,
        note_name: str,
        note_path: List[str],
    ) -> Union[List[Tuple[str, str]], str]:
        """
        Process a note: read it, filter it, and extract referenced notes.

        Args:
            note_id: Note ID to process
            note_name: Note name
            note_path: List of note IDs in the path to this note (for stacked URL)

        Returns:
            Union[List[Tuple[str, str]], str]: List of (referenced_note_id, referenced_note_name) tuples, or "Skip_all" string
        """
        # Build stacked URL
        stacked_url = build_stacked_url(self.base_url, note_path + [note_id])
        
        # Read note content first to get accurate note name
        html_content = read_note_from_file(self.webpage_dir, note_id, note_name)
        if html_content is None:
            # Try to find the file by ID only
            result = find_note_file(self.webpage_dir, note_id)
            if result:
                file_path, actual_name = result
                with open(file_path, "r", encoding="utf-8") as f:
                    html_content = f.read()
                note_name = actual_name
            else:
                print(f"Warning: Could not find file for note {note_id}")
                # Build stacked name
                stacked_name = build_stacked_name(
                    self.webpage_dir,
                    note_path,
                    note_id,
                    note_name,
                )
                # Still ask user even if file not found
                user_choice = self._ask_user_to_keep(note_id, stacked_name, stacked_url)
                if user_choice == "Yes":
                    self.filtered_notes[note_id] = {
                        "name": note_name,
                        "id": note_id,
                        "url": stacked_url,
                        "referenced_ids": [],
                    }
                    print(f"✓ Kept {len(self.filtered_notes)}: {note_name} ({note_id}) - no file found, no references")
                    return []
                elif user_choice == "Skip_all":
                    print(f"✗ Skipped all at this level: {note_name} ({note_id})")
                    return "Skip_all"
                else:
                    print(f"✗ Skipped: {note_name} ({note_id})")
                    return []
        
        # Build stacked name
        stacked_name = build_stacked_name(
            self.webpage_dir,
            note_path,
            note_id,
            note_name,
        )
        
        # Ask user if they want to keep this note
        user_choice = self._ask_user_to_keep(note_id, stacked_name, stacked_url)
        
        # Extract referenced notes (filter out self-references)
        referenced_notes = extract_note_links(html_content, current_note_id=note_id)
        
        if user_choice == "Yes":
            # Save note information
            self.filtered_notes[note_id] = {
                "name": note_name,
                "id": note_id,
                "url": stacked_url,
                "referenced_ids": [ref_id for ref_id, _ in referenced_notes],
            }
            print(f"✓ Kept {len(self.filtered_notes)}: {note_name} ({note_id})")
            return referenced_notes
        elif user_choice == "Skip_all":
            print(f"✗ Skipped all at this level: {note_name} ({note_id})")
            return "Skip_all"
        else:
            print(f"✗ Skipped: {note_name} ({note_id})")
            return []

    def _save_filtered_notes(self) -> None:
        """
        Save filtered notes to JSON file.
        """
        try:
            with open(self.output_file, "w", encoding="utf-8") as f:
                json.dump(self.filtered_notes, f, indent=2)
        except IOError as e:
            print(f"Error saving filtered notes: {e}")

    def save_checkpoint(
        self,
        stack: List[Tuple[str, str, List[str]]],
        verbose: bool = False,
    ) -> None:
        """
        Save checkpoint with current state.

        Args:
            stack: Current DFS stack state
            verbose: If True, print checkpoint save message
        """
        try:
            checkpoint_data = {
                "filtered_notes": self.filtered_notes,
                "visited": list(self.visited),
                "stack": stack,
            }
            with open(self.checkpoint_file, "w", encoding="utf-8") as f:
                json.dump(checkpoint_data, f, indent=2)
            self.checkpoint_save_count += 1
            if verbose or self.checkpoint_save_count % 10 == 0:
                print(f"Checkpoint saved to {self.checkpoint_file} (save #{self.checkpoint_save_count})")
        except IOError as e:
            print(f"Error saving checkpoint: {e}")

    def load_checkpoint(
        self,
    ) -> Optional[List[Tuple[str, str, List[str]]]]:
        """
        Load checkpoint and restore state.

        Returns:
            Optional[List[Tuple[str, str, List[str]]]]: Restored stack if checkpoint exists, None otherwise
        """
        if not os.path.exists(self.checkpoint_file):
            return None
        
        try:
            with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                checkpoint_data = json.load(f)
            
            self.filtered_notes = checkpoint_data.get("filtered_notes", {})
            self.visited = set(checkpoint_data.get("visited", []))
            stack = checkpoint_data.get("stack", [])
            
            # Convert stack back to tuples
            restored_stack: List[Tuple[str, str, List[str]]] = [
                (item[0], item[1], item[2]) for item in stack
            ]
            
            print(f"Checkpoint loaded from {self.checkpoint_file}")
            print(f"  - Filtered notes: {len(self.filtered_notes)}")
            print(f"  - Visited notes: {len(self.visited)}")
            print(f"  - Stack size: {len(restored_stack)}")
            
            return restored_stack
        except (IOError, json.JSONDecodeError, KeyError) as e:
            print(f"Error loading checkpoint: {e}")
            return None

    def filter_notes(
        self,
        start_note_id: str,
        start_note_name: str = "",
    ) -> None:
        """
        Start filtering notes using iterative DFS.

        Args:
            start_note_id: Starting note ID
            start_note_name: Starting note name (optional)
        """
        # Get note name if not provided
        if not start_note_name:
            start_note_name = get_note_name_from_file(self.webpage_dir, start_note_id)
            if not start_note_name:
                start_note_name = start_note_id
        
        # Stack for iterative DFS: list of (note_id, note_name, note_path) tuples
        # note_path is the list of note IDs from root to current note
        stack: List[Tuple[str, str, List[str]]] = []
        
        # Try to load checkpoint first
        restored_stack = self.load_checkpoint()
        if restored_stack is not None:
            stack = restored_stack
        else:
            # Initialize with starting note
            stack.append((start_note_id, start_note_name, []))
        
        # Main filtering loop
        while stack:
            # Pop from stack (DFS: LIFO)
            note_id, note_name, note_path = stack.pop()
            
            # Skip if already visited
            if note_id in self.visited:
                continue
            
            # Mark as visited
            self.visited.add(note_id)
            
            # Process the note
            result = self._process_note(note_id, note_name, note_path)
            
            # Handle Skip_all case
            if result == "Skip_all":
                # Get current level (length of note_path)
                current_level = len(note_path)
                # Remove all items from stack at the same level
                stack = [
                    (nid, nname, npath)
                    for nid, nname, npath in stack
                    if len(npath) != current_level
                ]
                print(f"  → Removed all notes at level {current_level}, jumping back to previous level")
                # Save progress
                self._save_filtered_notes()
                self.save_checkpoint(stack, verbose=True)
                continue
            
            # result should be a list of referenced notes
            referenced_notes = result
            
            # If note was kept, add referenced notes to stack
            if note_id in self.filtered_notes:
                # Build new path including current note
                if note_id != "About_these_notes":
                    new_path = note_path + [note_id]
                else:
                    new_path = note_path
                
                # Add unvisited referenced notes to stack (in reverse order for DFS)
                for ref_id, ref_name in reversed(referenced_notes):
                    if ref_id not in self.visited:
                        # Get actual note name if available
                        actual_name = get_note_name_from_file(self.webpage_dir, ref_id)
                        if actual_name:
                            ref_name = actual_name
                        stack.append((ref_id, ref_name, new_path))
            
            # Save progress periodically
            self._save_filtered_notes()
            self.save_checkpoint(stack)
        
        print("\nFiltering completed!")
        self._save_filtered_notes()


def main():
    """
    Main function to run the filter.
    """
    # Configuration
    BASE_URL = "https://notes.andymatuschak.org/About_these_notes"
    WEBPAGE_DIR = str(_project_root / "webpage")
    OUTPUT_FILE = str(Path(__file__).parent / "filtered_notes.json")
    START_NOTE_ID = "About_these_notes"
    START_NOTE_NAME = "About these notes"
    
    # Create filter
    filter_tool = DFSFilter(
        base_url=BASE_URL,
        webpage_dir=WEBPAGE_DIR,
        output_file=OUTPUT_FILE,
    )
    
    # Start filtering
    filter_tool.filter_notes(
        start_note_id=START_NOTE_ID,
        start_note_name=START_NOTE_NAME,
    )


if __name__ == "__main__":
    main()

