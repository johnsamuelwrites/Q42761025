#!/usr/bin/env python3
import argparse
import csv
import re
from pathlib import Path
from typing import Dict, Tuple, Iterable, Set

LABELS_PATH = Path("../data/labels.csv")
CONCEPTS_PATH = Path("../data/concepts.csv")
MISSING_PATH = Path("../data/missing.csv")

QID_RE = re.compile(r"^Q[1-9][0-9]*$")

LangRow = Dict[str, str]
LabelMaps = Tuple[Dict[str, LangRow], Dict[str, LangRow]]  # (by_id, by_en)


def load_csv_as_maps(path: Path) -> LabelMaps:
    """
    Load a CSV (identifier,en,fr,...) into:
      - by_id:  identifier -> full row
      - by_en:  normalized en label -> full row

    Normalization: strip and casefold for lookups.
    """
    by_id: Dict[str, LangRow] = {}
    by_en: Dict[str, LangRow] = {}

    if not path.is_file():
        return by_id, by_en

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = [h.strip() for h in reader.fieldnames] if reader.fieldnames else []
        reader.fieldnames = fieldnames

        for row in reader:
            norm_row = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
            identifier = norm_row.get("identifier", "")
            en_label = norm_row.get("en", "")

            if identifier:
                by_id[identifier] = norm_row

            if en_label:
                key = en_label.casefold()
                by_en.setdefault(key, norm_row)

    return by_id, by_en


def load_all_maps() -> Tuple[LabelMaps, LabelMaps]:
    # Keep the (by_id, by_en) ordering intact for both files
    labels_maps: LabelMaps = load_csv_as_maps(LABELS_PATH)
    concepts_maps: LabelMaps = load_csv_as_maps(CONCEPTS_PATH)
    return labels_maps, concepts_maps


def iter_html_files(root: Path, recursive: bool) -> Iterable[Path]:
    if recursive:
        yield from root.rglob("*.html")
    else:
        yield from root.glob("*.html")


def iter_dirs_bottom_up(root: Path, recursive: bool) -> Iterable[Path]:
    """
    Yield directories bottom-up (deepest first), respecting `recursive`.
    If recursive is False, only yield the root itself (if it is a directory).
    """
    if not recursive:
        if root.is_dir():
            yield root
        return

    dirs = [p for p in root.rglob("*") if p.is_dir()]
    if root.is_dir():
        dirs.append(root)
    dirs.sort(key=lambda p: len(p.parts), reverse=True)
    for d in dirs:
        yield d


def load_existing_missing() -> Set[str]:
    """
    Load existing 'en' concepts from missing.csv as normalized (strip+casefold) strings.
    """
    existing: Set[str] = set()
    if not MISSING_PATH.is_file():
        return existing

    with MISSING_PATH.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "en" not in [h.strip() for h in reader.fieldnames]:
            return existing
        for row in reader:
            val = (row.get("en") or "").strip()
            if val:
                existing.add(val.casefold())
    return existing


def add_missing_concept(concept: str, existing: Set[str]) -> None:
    """
    Add a non-Q concept to missing.csv if it's not already present.
    QIDs are never added.
    """
    concept_stripped = concept.strip()
    if not concept_stripped:
        return

    # Do not add QIDs
    if QID_RE.match(concept_stripped):
        # Just ignore silently; this situation may occur on future runs
        return

    key = concept_stripped.casefold()
    if key in existing:
        return

    MISSING_PATH.parent.mkdir(parents=True, exist_ok=True)
    new_file = not MISSING_PATH.exists()

    with MISSING_PATH.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["en"])
        writer.writerow([concept_stripped])

    existing.add(key)


def handle_non_wikidata_for_path(
    path: Path,
    lang: str,
    labels_id: Dict[str, LangRow],
    concepts_id: Dict[str, LangRow],
) -> Tuple[bool, str]:
    """
    Common logic for non-wikidata:
    - For files: path.stem is the identifier.
    - For dirs: path.name is the identifier.

    Returns (ok_to_rename, new_name_or_label).
    """
    name = path.name
    if path.is_file():
        name = path.stem

    identifier = name

    row = labels_id.get(identifier) or concepts_id.get(identifier)
    if row is None:
        print(f"[MISSING ID] {identifier} not found in labels.csv or concepts.csv (path: {path})")
        return False, ""

    label = row.get(lang, "") or ""
    label = label.strip()
    if not label:
        print(
            f"[MISSING LABEL] Identifier {identifier} has no '{lang}' label; skipping path: {path}"
        )
        return False, ""

    return True, label


def handle_non_wikidata_file(
    path: Path,
    lang: str,
    labels_id: Dict[str, LangRow],
    concepts_id: Dict[str, LangRow],
    dry_run: bool,
) -> None:
    # Future-run rule: if filename stem is not a QID, it is already translated
    stem = path.stem
    if not QID_RE.match(stem):
        # Considered already translated; skip silently
        return

    ok, label = handle_non_wikidata_for_path(path, lang, labels_id, concepts_id)
    if not ok:
        return

    new_name = f"{label}.html"
    new_path = path.with_name(new_name)

    if new_path == path:
        return

    if new_path.exists():
        print(f"[SKIP COLLISION] Target file already exists: {new_path} (from {path})")
        return

    print(f"[RENAME FILE] {path} -> {new_path}")
    if not dry_run:
        path.rename(new_path)


def handle_non_wikidata_dir(
    path: Path,
    lang: str,
    labels_id: Dict[str, LangRow],
    concepts_id: Dict[str, LangRow],
    dry_run: bool,
) -> None:
    # Future-run rule: if directory name is not a QID, it is already translated
    dir_name = path.name
    if not QID_RE.match(dir_name):
        return

    ok, label = handle_non_wikidata_for_path(path, lang, labels_id, concepts_id)
    if not ok:
        return

    new_path = path.with_name(label)

    if new_path == path:
        return

    if new_path.exists():
        print(f"[SKIP DIR COLLISION] Target directory already exists: {new_path} (from {path})")
        return

    print(f"[RENAME DIR] {path} -> {new_path}")
    if not dry_run:
        path.rename(new_path)


def handle_wikidata_file(
    path: Path,
    labels_en: Dict[str, LangRow],
    concepts_en: Dict[str, LangRow],
    dry_run: bool,
    missing_existing: Set[str],
) -> None:
    concept = path.stem
    concept_norm = concept.strip().casefold()

    row = labels_en.get(concept_norm) or concepts_en.get(concept_norm)
    if row is None:
        print(f"[MISSING CONCEPT] '{concept}' not found in labels/concepts; adding to missing.csv")
        add_missing_concept(concept, missing_existing)
        return

    identifier = row.get("identifier", "").strip()
    if not identifier:
        print(
            f"[INVALID ROW] Concept '{concept}' found but row has no identifier; file: {path}"
        )
        return

    new_name = f"{identifier}.html"
    new_path = path.with_name(new_name)

    if new_path == path:
        return

    if new_path.exists():
        print(f"[SKIP COLLISION] Target file already exists: {new_path} (from {path})")
        return

    print(f"[RENAME FILE] {path} -> {new_path}")
    if not dry_run:
        path.rename(new_path)


def handle_wikidata_dir(
    path: Path,
    labels_en: Dict[str, LangRow],
    concepts_en: Dict[str, LangRow],
    dry_run: bool,
    missing_existing: Set[str],
) -> None:
    concept = path.name
    concept_norm = concept.strip().casefold()

    row = labels_en.get(concept_norm) or concepts_en.get(concept_norm)
    if row is None:
        print(f"[MISSING CONCEPT] '{concept}' not found in labels/concepts; adding to missing.csv")
        add_missing_concept(concept, missing_existing)
        return

    identifier = row.get("identifier", "").strip()
    if not identifier:
        print(
            f"[INVALID ROW] Concept '{concept}' found but row has no identifier; dir: {path}"
        )
        return

    new_path = path.with_name(identifier)

    if new_path == path:
        return

    if new_path.exists():
        print(f"[SKIP DIR COLLISION] Target directory already exists: {new_path} (from {path})")
        return

    print(f"[RENAME DIR] {path} -> {new_path}")
    if not dry_run:
        path.rename(new_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rename HTML files and/or directories using labels.csv / concepts.csv."
    )
    parser.add_argument(
        "--dir",
        required=True,
        type=Path,
        help="Root directory containing HTML files and/or directories.",
    )
    parser.add_argument(
        "--lang",
        required=True,
        help="Language code (e.g. en, fr, nl, wikidata).",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print planned renames, do not change files/directories.",
    )
    parser.add_argument(
        "--rename-dirs",
        action="store_true",
        help="Also rename directories according to the same rules.",
    )

    args = parser.parse_args()
    root: Path = args.dir
    lang: str = args.lang
    recursive: bool = args.recursive
    dry_run: bool = args.dry_run
    rename_dirs: bool = args.rename_dirs

    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Directory does not exist or is not a directory: {root}")

    (labels_by_id, labels_by_en), (concepts_by_id, concepts_by_en) = load_all_maps()
    missing_existing = load_existing_missing()

    # 1) Files first
    for html_file in iter_html_files(root, recursive):
        if lang == "wikidata":
            handle_wikidata_file(html_file, labels_by_en, concepts_by_en, dry_run, missing_existing)
        else:
            handle_non_wikidata_file(html_file, lang, labels_by_id, concepts_by_id, dry_run)

    # 2) Directories bottom-up (optional)
    if rename_dirs:
        for d in iter_dirs_bottom_up(root, recursive):
            if lang == "wikidata":
                handle_wikidata_dir(d, labels_by_en, concepts_by_en, dry_run, missing_existing)
            else:
                handle_non_wikidata_dir(d, lang, labels_by_id, concepts_by_id, dry_run)


if __name__ == "__main__":
    main()
