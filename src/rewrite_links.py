#!/usr/bin/env python3
import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, Iterable, Tuple

from bs4 import BeautifulSoup  # pip install beautifulsoup4


def load_labels(labels_path: Path) -> Dict[str, str]:
    """Return mapping: lower(en) -> identifier (QID)."""
    mapping: Dict[str, str] = {}
    with labels_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if "identifier" not in reader.fieldnames or "en" not in reader.fieldnames:
            raise ValueError("labels.csv must contain 'identifier' and 'en' columns")
        for row in reader:
            en = (row.get("en") or "").strip()
            identifier = (row.get("identifier") or "").strip()
            if not en or not identifier:
                continue
            key = en.lower()
            # Last one wins if duplicates; adjust here if you want different policy
            mapping[key] = identifier
    return mapping


def iter_html_files(target_dir: Path, recursive: bool) -> Iterable[Path]:
    if recursive:
        yield from target_dir.rglob("*.html")
    else:
        yield from target_dir.glob("*.html")


def should_skip_href(href: str) -> bool:
    href = href.strip()
    if not href:
        return True
    # external
    if href.startswith(("http://", "https://", "mailto:", "tel:")):
        return True
    # anchors
    if href.startswith("#"):
        return True
    # absolute paths
    if href.startswith("/"):
        return True
    return False


def map_segment(segment: str, labels: Dict[str, str], file_path: Path) -> str:
    """
    Map a single path segment using labels.
    - If segment has an extension, only the base part is used for lookup.
    - If no mapping is found, original segment is returned.
    """
    if not segment or segment in (".", ".."):
        return segment

    # Separate extension if present
    if "." in segment:
        base, ext = segment.rsplit(".", 1)
        base_stripped = base.strip()
        key = base_stripped.lower()
        qid = labels.get(key)
        if qid:
            return f"{qid}.{ext}"
        else:
            # no mapping; report once per occurrence
            print(
                f"[WARN] No mapping for label '{base}' in {file_path} (segment '{segment}')",
                file=sys.stderr,
            )
            return segment
    else:
        base_stripped = segment.strip()
        key = base_stripped.lower()
        qid = labels.get(key)
        if qid:
            return qid
        else:
            print(
                f"[WARN] No mapping for label '{segment}' in {file_path} (segment '{segment}')",
                file=sys.stderr,
            )
            return segment


def rewrite_href(href: str, labels: Dict[str, str], file_path: Path) -> Tuple[str, bool]:
    """
    Rewrite a relative href according to the labels.
    Returns (new_href, changed).
    """
    original = href
    # Preserve any query/fragment; work on path only
    path_part, sep, tail = href.partition("?")
    path_only, frag_sep, fragment = path_part.partition("#")

    segments = path_only.split("/")
    new_segments = [
        map_segment(seg, labels, file_path) for seg in segments
    ]
    new_path = "/".join(new_segments)

    # Reattach fragment and query if present
    rebuilt = new_path
    if fragment:
        rebuilt = f"{rebuilt}#{fragment}"
    if sep:
        rebuilt = f"{rebuilt}?{tail}"

    return rebuilt, (rebuilt != original)


def process_file(
    file_path: Path,
    labels: Dict[str, str],
    dry_run: bool,
) -> int:
    """
    Process a single HTML file.
    Returns number of changed hrefs.
    """
    text = file_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(text, "html.parser")

    changed_count = 0

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if should_skip_href(href):
            continue
        new_href, changed = rewrite_href(href, labels, file_path)
        if changed:
            changed_count += 1
            if dry_run:
                print(f"[DRY-RUN] {file_path}: {href!r} -> {new_href!r}")
            else:
                print(f"[CHANGE] {file_path}: {href!r} -> {new_href!r}")
            a["href"] = new_href

    if not dry_run and changed_count > 0:
        file_path.write_text(str(soup), encoding="utf-8")

    return changed_count


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Replace internal <a href> URLs with Wikidata QIDs using labels.csv"
    )
    parser.add_argument(
        "target_dir",
        type=Path,
        help="Directory containing .html files to process",
    )
    parser.add_argument(
        "--labels",
        required=True,
        type=Path,
        help="Path to labels.csv (UTF-8, with 'identifier' and 'en' columns)",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned changes without modifying any files",
    )

    args = parser.parse_args(argv)

    target_dir: Path = args.target_dir
    labels_path: Path = args.labels
    recursive: bool = args.recursive
    dry_run: bool = args.dry_run

    if not target_dir.is_dir():
        print(f"Error: {target_dir} is not a directory", file=sys.stderr)
        return 1
    if not labels_path.is_file():
        print(f"Error: labels file {labels_path} does not exist", file=sys.stderr)
        return 1

    labels = load_labels(labels_path)
    if not labels:
        print("Warning: labels mapping is empty; nothing will be replaced", file=sys.stderr)

    total_files = 0
    total_changes = 0

    for html_file in iter_html_files(target_dir, recursive):
        total_files += 1
        try:
            total_changes += process_file(html_file, labels, dry_run=dry_run)
        except Exception as e:
            print(f"[ERROR] Failed to process {html_file}: {e}", file=sys.stderr)

    print(
        f"Processed {total_files} .html files, {total_changes} href(s) changed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
