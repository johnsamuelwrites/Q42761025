import csv
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

MISSING_FILE = Path("../data/missing.csv")
LABELS_FILE = Path("../data/labels.csv")

LANG_COLUMNS = ["en", "fr", "ml", "pa", "hi", "pt", "es", "it", "de", "nl"]

WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY_URL = "https://www.wikidata.org/wiki/Special:EntityData/{}.json"

REQUEST_SLEEP_SECONDS = 0.2  # pause between calls

# Use a UA that follows the Wikimedia policy:
# https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy
USER_AGENT = "labels/0.1 (https://your-site-or-docs.example)"
COMMON_HEADERS = {
    "User-Agent": USER_AGENT,
    "Api-User-Agent": USER_AGENT,
}

# -------------------------------------------------------------------
# HTTP session with retries and backoff
# -------------------------------------------------------------------

def create_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=5,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD", "OPTIONS"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


session = create_session()


def wikidata_get(params, timeout=10):
    time.sleep(REQUEST_SLEEP_SECONDS)
    resp = session.get(WIKIDATA_API_URL, params=params, headers=COMMON_HEADERS, timeout=timeout)
    if resp.status_code == 403:
        raise RuntimeError(
            f"403 Forbidden for Wikidata API. Check User-Agent policy and user agent string: {USER_AGENT}"
        )
    resp.raise_for_status()
    return resp


def fetch_entity_data(qid, timeout=10):
    time.sleep(REQUEST_SLEEP_SECONDS)
    url = WIKIDATA_ENTITY_URL.format(qid)
    resp = session.get(url, headers=COMMON_HEADERS, timeout=timeout)
    if resp.status_code == 403:
        raise RuntimeError(
            f"403 Forbidden for Wikidata EntityData. Check User-Agent policy and user agent string: {USER_AGENT}"
        )
    resp.raise_for_status()
    return resp.json()


# -------------------------------------------------------------------
# CSV helpers
# -------------------------------------------------------------------

def load_existing_labels(labels_path: Path):
    rows = []
    existing_en_labels = set()

    if not labels_path.exists():
        return rows, existing_en_labels

    with labels_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
            en_label = (row.get("en") or "").strip()
            if en_label:
                existing_en_labels.add(en_label.lower())
    return rows, existing_en_labels


def load_missing_concepts(missing_path: Path):
    """
    Returns list of dicts (rows) and list of labels in order.
    """
    rows = []
    labels = []
    if not missing_path.exists():
        return rows, labels

    with missing_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "en" not in (reader.fieldnames or []):
            raise ValueError("missing.csv must have a header with column 'en'")
        for row in reader:
            label = (row.get("en") or "").strip()
            if label:
                rows.append(row)
                labels.append(label)
    return rows, labels


def write_missing_concepts(missing_path: Path, rows):
    """
    Rewrite missing.csv with the subset of rows still unresolved.
    """
    if not rows:
        # Optionally keep an empty file with header
        with missing_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["en"])
            writer.writeheader()
        return

    fieldnames = rows[0].keys()
    with missing_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


# -------------------------------------------------------------------
# Wikidata helpers
# -------------------------------------------------------------------

def search_wikidata(label_en: str, limit: int = 10):
    params = {
        "action": "wbsearchentities",
        "format": "json",
        "language": "en",
        "uselang": "en",
        "search": label_en,
        "limit": limit,
    }
    resp = wikidata_get(params)
    data = resp.json()
    results = data.get("search", [])
    candidates = []
    for r in results:
        candidates.append(
            {
                "id": r.get("id"),
                "label": r.get("label"),
                "description": r.get("description"),
            }
        )
    return candidates


def choose_qid_interactively(label_en: str, candidates):
    print(f"\nAmbiguous label: '{label_en}'")
    if not candidates:
        print("No candidates found. You can still enter a QID manually or press Enter to skip.")
    else:
        print("Candidates:")
        for idx, c in enumerate(candidates, start=1):
            cid = c.get("id") or ""
            clabel = c.get("label") or ""
            cdesc = c.get("description") or ""
            print(f"  {idx}. {cid} | {clabel} | {cdesc}")

    while True:
        user_input = input(
            "Enter QID to use (e.g., Q31), or press Enter if there is no suitable QID: "
        ).strip()
        if not user_input:
            # No QID; concept stays in missing.csv
            return None
        if user_input.startswith("Q") and user_input[1:].isdigit():
            return user_input
        print("Invalid QID format. Please enter something like 'Q31', or just press Enter to leave it unresolved.")


def fetch_labels_for_qid(qid: str, languages):
    try:
        data = fetch_entity_data(qid)
    except Exception as e:
        print(f"Error fetching entity data for {qid}: {e}")
        return {lang: "" for lang in languages}

    entities = data.get("entities", {})
    entity_data = entities.get(qid, {})
    labels = entity_data.get("labels", {})

    result = {}
    for lang in languages:
        label_obj = labels.get(lang)
        result[lang] = label_obj.get("value") if label_obj else ""
    return result


# -------------------------------------------------------------------
# Main logic
# -------------------------------------------------------------------

def main():
    existing_rows, existing_en_labels = load_existing_labels(LABELS_FILE)
    missing_rows, missing_labels = load_missing_concepts(MISSING_FILE)

    print(f"Loaded {len(existing_rows)} existing rows from {LABELS_FILE}")
    print(f"Loaded {len(missing_labels)} missing concepts from {MISSING_FILE}")

    new_rows = []
    unresolved_missing_rows = []

    for row, label_en in zip(missing_rows, missing_labels):
        if label_en.lower() in existing_en_labels:
            print(f"Skipping '{label_en}' (already present in labels.csv)")
            # Already resolved, do not keep it in missing.csv
            continue

        print(f"\nProcessing '{label_en}'...")

        try:
            candidates = search_wikidata(label_en)
        except Exception as e:
            print(f"Error searching Wikidata for '{label_en}': {e}")
            # Keep unresolved
            unresolved_missing_rows.append(row)
            continue

        if not candidates:
            qid = choose_qid_interactively(label_en, candidates)
        elif len(candidates) == 1:
            print("Found one candidate:")
            c = candidates[0]
            print(f"  {c['id']} | {c.get('label') or ''} | {c.get('description') or ''}")
            confirm = input(
                "Use this QID? [Y/n] (or type a different QID, or press Enter if there is no suitable QID): "
            ).strip()
            if not confirm or confirm.lower() == "y":
                qid = c["id"]
            elif confirm.startswith("Q") and confirm[1:].isdigit():
                qid = confirm
            else:
                qid = choose_qid_interactively(label_en, candidates)
        else:
            qid = choose_qid_interactively(label_en, candidates)

        if not qid:
            print(f"No QID selected for '{label_en}'. Keeping it in missing.csv.")
            unresolved_missing_rows.append(row)
            continue

        print(f"Using QID {qid} for '{label_en}'")

        labels = fetch_labels_for_qid(qid, LANG_COLUMNS)

        if not labels.get("en"):
            labels["en"] = label_en

        out_row = {"identifier": qid}
        for lang in LANG_COLUMNS:
            out_row[lang] = labels.get(lang, "")

        new_rows.append(out_row)
        existing_en_labels.add(labels["en"].lower())
        print(f"Prepared new row for '{label_en}' -> {qid}")
        # Do NOT add this row to unresolved_missing_rows: it is now resolved

    # Append new rows to labels.csv
    if new_rows:
        fieldnames = ["identifier"] + LANG_COLUMNS

        if LABELS_FILE.exists():
            with LABELS_FILE.open("r", encoding="utf-8") as f:
                reader = csv.reader(f)
                existing_header = next(reader, None)

            if existing_header is None:
                mode = "w"
                write_header = True
            else:
                mode = "a"
                write_header = False
        else:
            mode = "w"
            write_header = True

        with LABELS_FILE.open(mode, encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            for row in new_rows:
                for field in fieldnames:
                    row.setdefault(field, "")
                writer.writerow(row)

        print(f"Appended {len(new_rows)} new rows to {LABELS_FILE}")
    else:
        print("No new rows to append to labels.csv")

    # Rewrite missing.csv with only unresolved concepts
    write_missing_concepts(MISSING_FILE, unresolved_missing_rows)
    print(f"Updated {MISSING_FILE} with {len(unresolved_missing_rows)} unresolved concepts")


if __name__ == "__main__":
    main()
