import json
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

from src.webpage import (
    DEFAULT_WEBPAGE_DIR,
    NOTES_BASE_URL,
    PROJECT_ROOT,
    find_webpage_file,
    get_note_link_l_from_html,
    get_note_name_from_file,
    get_stacked_name,
    get_stacked_url,
    get_url_from_page_id,
    get_webpage_html,
)


DEFAULT_FILTERED_NOTES_FILE = PROJECT_ROOT / "data" / "filtered_notes.json"


class DFSFilter:
    """
    Interactive depth-first search filter for curating Evergreen Notes.
    """

    def __init__(
        self,
        base_url: str = f"{NOTES_BASE_URL}/About_these_notes",
        webpage_dir: Union[str, Path] = DEFAULT_WEBPAGE_DIR,
        output_file: Union[str, Path] = DEFAULT_FILTERED_NOTES_FILE,
        prompt_fn: Optional[Callable[[str, str, str], str]] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.webpage_dir = Path(webpage_dir)
        self.output_file = Path(output_file)
        self.prompt_fn = prompt_fn

        self.filtered_note_d: Dict[str, Dict[str, Any]] = {}
        self.visited_s: Set[str] = set()
        self.checkpoint_file = Path(str(self.output_file).replace(".json", "_checkpoint.json"))
        self.checkpoint_save_count = 0

    def _ask_user_to_keep(
        self,
        note_id: str,
        stacked_name: str,
        stacked_url: str,
    ) -> str:
        if self.prompt_fn is not None:
            user_input = self.prompt_fn(note_id, stacked_name, stacked_url).strip()
        else:
            print(f"\n🔗: {stacked_url}")
            print(f"\n{stacked_name}")
            user_input = input("Keep? (y/n/N)").strip()

        if user_input == "n":
            return "No"
        if user_input == "N":
            return "Skip_all"
        return "Yes"

    def _process_note(
        self,
        note_id: str,
        note_name: str,
        note_path_l: List[str],
    ) -> Union[List[Tuple[str, str]], str]:
        stacked_url = get_stacked_url(self.base_url, note_path_l + [note_id])

        html_content = get_webpage_html(self.webpage_dir, note_id, note_name)
        if html_content is None:
            found = find_webpage_file(self.webpage_dir, note_id)
            if found is not None:
                file_path, actual_name = found
                html_content = file_path.read_text(encoding="utf-8")
                note_name = actual_name
            else:
                print(f"Warning: Could not find file for note {note_id}")
                stacked_name = get_stacked_name(self.webpage_dir, note_path_l, note_name)
                user_choice = self._ask_user_to_keep(note_id, stacked_name, stacked_url)
                if user_choice == "Yes":
                    self.filtered_note_d[note_id] = {
                        "name": note_name,
                        "id": note_id,
                        "url": get_url_from_page_id(note_id),
                        "referenced_ids": [],
                    }
                    print(f"✓ Kept {len(self.filtered_note_d)}: {note_name} ({note_id}) - no file found, no references")
                    return []
                if user_choice == "Skip_all":
                    print(f"✗ Skipped all at this level: {note_name} ({note_id})")
                    return "Skip_all"
                print(f"✗ Skipped: {note_name} ({note_id})")
                return []

        stacked_name = get_stacked_name(self.webpage_dir, note_path_l, note_name)
        user_choice = self._ask_user_to_keep(note_id, stacked_name, stacked_url)
        referenced_note_l = get_note_link_l_from_html(html_content, current_note_id=note_id)

        if user_choice == "Yes":
            self.filtered_note_d[note_id] = {
                "name": note_name,
                "id": note_id,
                "url": stacked_url,
                "referenced_ids": [ref_id for ref_id, _ in referenced_note_l],
            }
            print(f"✓ Kept {len(self.filtered_note_d)}: {note_name} ({note_id})")
            return referenced_note_l
        if user_choice == "Skip_all":
            print(f"✗ Skipped all at this level: {note_name} ({note_id})")
            return "Skip_all"

        print(f"✗ Skipped: {note_name} ({note_id})")
        return []

    def create_filtered_notes_file(self) -> None:
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        self.output_file.write_text(
            json.dumps(self.filtered_note_d, indent=2),
            encoding="utf-8",
        )

    def create_checkpoint(
        self,
        stack_l: List[Tuple[str, str, List[str]]],
        verbose: bool = False,
    ) -> None:
        checkpoint_d = {
            "filtered_notes": self.filtered_note_d,
            "visited": list(self.visited_s),
            "stack": stack_l,
        }
        self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_file.write_text(
            json.dumps(checkpoint_d, indent=2),
            encoding="utf-8",
        )
        self.checkpoint_save_count += 1
        if verbose or self.checkpoint_save_count % 10 == 0:
            print(f"Checkpoint saved to {self.checkpoint_file} (save #{self.checkpoint_save_count})")

    def get_checkpoint(self) -> Optional[List[Tuple[str, str, List[str]]]]:
        if not self.checkpoint_file.exists():
            return None

        checkpoint_d = json.loads(self.checkpoint_file.read_text(encoding="utf-8"))
        self.filtered_note_d = checkpoint_d.get("filtered_notes", {})
        self.visited_s = set(checkpoint_d.get("visited", []))
        stack_l = checkpoint_d.get("stack", [])
        restored_stack_l: List[Tuple[str, str, List[str]]] = [
            (item[0], item[1], list(item[2])) for item in stack_l
        ]
        return restored_stack_l

    def filter_notes(
        self,
        start_note_id: str = "About_these_notes",
        start_note_name: str = "",
    ) -> Dict[str, Dict[str, Any]]:
        if not start_note_name:
            start_note_name = get_note_name_from_file(self.webpage_dir, start_note_id) or start_note_id

        restored_stack_l = self.get_checkpoint()
        if restored_stack_l is not None:
            stack_l = restored_stack_l
        else:
            stack_l = [(start_note_id, start_note_name, [])]

        while stack_l:
            note_id, note_name, note_path_l = stack_l.pop()
            if note_id in self.visited_s:
                continue

            self.visited_s.add(note_id)
            result = self._process_note(note_id, note_name, note_path_l)

            if result == "Skip_all":
                current_level = len(note_path_l)
                stack_l = [
                    (nid, nname, npath)
                    for nid, nname, npath in stack_l
                    if len(npath) != current_level
                ]
                self.create_filtered_notes_file()
                self.create_checkpoint(stack_l, verbose=True)
                continue

            referenced_note_l = result
            if note_id in self.filtered_note_d:
                new_path_l = note_path_l + [note_id] if note_id != "About_these_notes" else note_path_l
                for ref_id, ref_name in reversed(referenced_note_l):
                    if ref_id not in self.visited_s:
                        actual_name = get_note_name_from_file(self.webpage_dir, ref_id)
                        if actual_name:
                            ref_name = actual_name
                        stack_l.append((ref_id, ref_name, new_path_l))

            self.create_filtered_notes_file()
            self.create_checkpoint(stack_l)

        self.create_filtered_notes_file()
        return self.filtered_note_d


def main() -> None:
    filter_tool = DFSFilter(
        base_url=f"{NOTES_BASE_URL}/About_these_notes",
        webpage_dir=DEFAULT_WEBPAGE_DIR,
        output_file=DEFAULT_FILTERED_NOTES_FILE,
    )
    filter_tool.filter_notes(
        start_note_id="About_these_notes",
        start_note_name="About these notes",
    )


if __name__ == "__main__":
    main()
