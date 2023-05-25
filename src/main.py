from query import MediaWiki
from identifier import Identifier
from extract import html_files


def extract_identifiers():
    languages = ["en", "fr", "ml", "pa", "hi", "pt", "es", "it", "de", "nl"]
    for html_file in html_files:
        labels = Identifier.update_labels_for_html_file(html_file, languages)


def update_labels():
    languages = ["en", "fr", "ml", "pa", "hi", "pt", "es", "it", "de", "nl"]
    labels = Identifier.update_labels_for_identifiers(None, languages)


if __name__ == "__main__":
    update_labels()
