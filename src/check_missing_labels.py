#!/usr/bin/env python3
import argparse
import csv
import sys
from pathlib import Path
from typing import Set, Tuple


def load_labels(labels_path: Path, lang: str) -> Tuple[Set[str], Set[str]]:
    """
    Load labels.csv and return:
      - a set of non-empty keys for the given language (normalized to lowercase)
      - a set of identifiers (row numbers as strings) where the language cell is empty
    """
    if not labels_path.is_file():
        sys.exit(f"labels.csv not found at: {labels_path}")

    lang_lower = lang.lower()
    keys: Set[str] = set()
    empty_rows: Set[str] = set()

    with labels_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # Normalize headers to allow minor mistakes in case and surrounding spaces
        fieldname_map = {name.strip().lower(): name for name in reader.fieldnames or []}

        if lang_lower not in fieldname_map:
            sys.exit(f"Language column '{lang}' not found in labels.csv")

        lang_col = fieldname_map[lang_lower]

        for idx, row in enumerate(reader, start=2):  # start=2 (header is line 1)
            raw_value = row.get(lang_col, "")
            value = (raw_value or "").strip()
            if not value:
                # Use row number as identifier when reporting empty labels
                empty_rows.add(str(idx))
            else:
                keys.add(value.lower())

    return keys, empty_rows


def iter_html_files(root: Path, recursive: bool):
    """Yield Path objects for .html files under root, optionally recursively."""
    if recursive:
        pattern = "**/*.html"
        yield from root.glob(pattern)
    else:
        yield from root.glob("*.html")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check that each .html file under a directory has a corresponding "
            "entry in labels.csv for a given language, and report empty labels."
        )
    )
    parser.add_argument(
        "directory",
        help="Directory containing .html files to check",
    )
    parser.add_argument(
        "language",
        help="Language code to check (e.g. en, fr, nl, de)",
    )
    parser.add_argument(
        "labels",
        help="Path to labels.csv",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursively scan subdirectories for .html files",
    )

    args = parser.parse_args(argv)

    root = Path(args.directory)
    if not root.is_dir():
        sys.exit(f"Not a directory: {root}")

    labels_path = Path(args.labels)

    # Load labels and collect empty rows for the given language
    known_keys, empty_rows = load_labels(labels_path, args.language)

    missing_files = []
    for path in iter_html_files(root, args.recursive):
        if not path.is_file():
            continue
        stem = path.stem  # filename without extension
        if stem.lower() not in known_keys:
            missing_files.append(stem)

    # Reporting
    had_errors = False

    if missing_files:
        had_errors = True
        print("Missing in CSV (no matching key for these .html files):")
        for name in sorted(set(missing_files)):
            print(name)

    if empty_rows:
        had_errors = True
        print("\nEmpty labels in CSV for language "
              f"'{args.language}' (row numbers):")
        for row_id in sorted(empty_rows, key=int):
            print(row_id)

    if not had_errors:
        print("All .html files have entries in labels.csv and no empty labels for this language.")

    return 1 if had_errors else 0


if __name__ == "__main__":
    sys.exit(main())
