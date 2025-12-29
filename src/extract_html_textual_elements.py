#!/usr/bin/env python3
"""
Extract translatable text from HTML files.

This script recursively scans a directory for HTML files and extracts all
translatable text elements (title, content, alt attributes, URLs, directories, filenames)
into CSV files. Short texts go to translations.csv, long texts (100+ chars) go to 
long_translations.csv.
"""

import argparse
import csv
import re
from pathlib import Path
from html.parser import HTMLParser
from typing import Set, List


class TranslationExtractor(HTMLParser):
    """HTML parser that extracts translatable text elements and URL components."""
    
    # Attributes to extract text from
    TRANSLATABLE_ATTRS = {
        'alt', 'title', 'placeholder', 'aria-label', 
        'aria-describedby', 'aria-placeholder', 'data-location', 'data-city'
    }
    
    # Tags to skip entirely
    SKIP_TAGS = {'script', 'style'}
    
    def __init__(self):
        super().__init__()
        self.texts: Set[str] = set()
        self.url_components: Set[str] = set()
        self.current_text: List[str] = []
        self.skip_level = 0
        self.in_title = False
        
    def handle_starttag(self, tag, attrs):
        """Handle opening tags."""
        # Check if we're entering a skip tag
        if tag in self.SKIP_TAGS:
            self.skip_level += 1
            return
            
        if self.skip_level > 0:
            return
            
        # Track title tag
        if tag == 'title':
            self.in_title = True
            
        # Extract translatable attributes
        for attr_name, attr_value in attrs:
            if attr_name in self.TRANSLATABLE_ATTRS and attr_value:
                cleaned = self._clean_text(attr_value)
                if cleaned:
                    self.texts.add(cleaned)
            
            # Extract URL components from href attributes
            if attr_name == 'href' and attr_value and tag == 'a':
                self._extract_url_components(attr_value)
                    
        # Extract meta description
        if tag == 'meta':
            attrs_dict = dict(attrs)
            if attrs_dict.get('name') == 'description' and 'content' in attrs_dict:
                cleaned = self._clean_text(attrs_dict['content'])
                if cleaned:
                    self.texts.add(cleaned)
    
    def handle_endtag(self, tag):
        """Handle closing tags."""
        if tag in self.SKIP_TAGS:
            self.skip_level = max(0, self.skip_level - 1)
            return
            
        if self.skip_level > 0:
            return
            
        if tag == 'title':
            self.in_title = False
            
        # Flush accumulated text when block-level element closes
        if tag in {'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 
                   'li', 'td', 'th', 'blockquote', 'article', 'section',
                   'header', 'footer', 'aside', 'main', 'nav', 'title'}:
            self._flush_current_text()
    
    def handle_data(self, data):
        """Handle text content."""
        if self.skip_level > 0:
            return
            
        # Accumulate text
        if data.strip():
            self.current_text.append(data)
    
    def _flush_current_text(self):
        """Flush accumulated text as a single entry."""
        if self.current_text:
            combined = ' '.join(self.current_text)
            cleaned = self._clean_text(combined)
            if cleaned:
                self.texts.add(cleaned)
            self.current_text = []
    
    def _extract_url_components(self, url: str):
        """Extract translatable components from a URL."""
        # Skip external URLs, mailto, tel, or anchors
        if (url.startswith(('http://', 'https://', 'mailto:', 'tel:', '//', '#')) or
            not url or url.startswith('javascript:')):
            return
        
        # Split URL into path and fragment/query (ignore fragment/query)
        anchor_match = re.match(r'^([^#?]*)([#?].*)$', url)
        if anchor_match:
            path_part = anchor_match.group(1)
        else:
            path_part = url
        
        # Don't extract if it's just an anchor
        if not path_part:
            return
        
        # Split path into components
        parts = path_part.split('/')
        
        for part in parts:
            if not part:  # Empty parts (from leading/trailing slashes)
                continue
            
            # Check if this is a file (has extension)
            if '.' in part:
                # Split filename and extension
                name_parts = part.rsplit('.', 1)
                filename = name_parts[0]
                
                # Extract filename (without extension)
                if filename:
                    self.url_components.add(filename)
            else:
                # Extract directory name
                self.url_components.add(part)
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text)
        # Strip leading/trailing whitespace
        text = text.strip()
        return text
    
    def get_texts(self) -> Set[str]:
        """Get all extracted texts."""
        # Flush any remaining text
        self._flush_current_text()
        return self.texts
    
    def get_url_components(self) -> Set[str]:
        """Get all extracted URL components."""
        return self.url_components


def extract_from_html_file(file_path: Path) -> tuple[Set[str], Set[str]]:
    """
    Extract translatable texts and URL components from a single HTML file.
    Returns (texts, url_components).
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        parser = TranslationExtractor()
        parser.feed(content)
        return parser.get_texts(), parser.get_url_components()
    except Exception as e:
        print(f"Warning: Could not process {file_path}: {e}")
        return set(), set()


def find_html_files(directory: Path, recursive: bool = True) -> List[Path]:
    """Find all HTML files in directory."""
    if recursive:
        return list(directory.rglob('*.html')) + list(directory.rglob('*.htm'))
    else:
        return list(directory.glob('*.html')) + list(directory.glob('*.htm'))


def extract_filesystem_components(directory: Path, recursive: bool = True) -> Set[str]:
    """Extract directory and file names from the filesystem."""
    components = set()
    
    if recursive:
        items = directory.rglob('*')
    else:
        items = directory.glob('*')
    
    for item in items:
        if item.is_dir():
            # Add directory name
            components.add(item.name)
        elif item.is_file() and item.suffix in ['.html', '.htm']:
            # Add filename without extension
            components.add(item.stem)
    
    return components


def write_csv_file(file_path: Path, texts: List[str], append: bool = False, 
                   languages: List[str] = None):
    """Write texts to CSV file with language columns."""
    if languages is None:
        languages = ['fr', 'de', 'nl', 'es', 'it']
    
    # Check if file exists and read existing entries for append mode
    existing_entries = set()
    if append and file_path.exists():
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    en_value = row.get('en', '').strip()
                    if en_value:
                        existing_entries.add(en_value)
        except Exception as e:
            print(f"Warning: Could not read existing file {file_path}: {e}")
    
    # Filter out existing entries if appending
    if append and existing_entries:
        new_texts = [t for t in texts if t not in existing_entries]
        if not new_texts:
            return 0
        texts = new_texts
    
    # Write to CSV
    mode = 'a' if (append and file_path.exists()) else 'w'
    with open(file_path, mode, encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        
        # Write header only if creating new file
        if mode == 'w':
            writer.writerow(['en'] + languages)
        
        # Write each text with empty columns for translations
        for text in texts:
            writer.writerow([text] + [''] * len(languages))
    
    return len(texts)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Extract translatable text and URL components from HTML files into CSV files.'
    )
    parser.add_argument(
        'directory',
        type=Path,
        help='Input directory containing HTML files'
    )
    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        default=False,
        help='Recursively scan subdirectories'
    )
    parser.add_argument(
        '--threshold',
        type=int,
        default=100,
        help='Character threshold for long translations (default: 100)'
    )
    parser.add_argument(
        '-o', '--output-dir',
        type=Path,
        default=Path('.'),
        help='Output directory for CSV files (default: current directory)'
    )
    parser.add_argument(
        '--append',
        action='store_true',
        default=False,
        help='Append to existing CSV files instead of overwriting'
    )
    parser.add_argument(
        '--languages',
        nargs='+',
        default=['fr', 'de', 'nl', 'es', 'it'],
        help='Language columns to create (default: fr de nl es it)'
    )
    parser.add_argument(
        '--skip-urls',
        action='store_true',
        default=False,
        help='Skip extraction of URL components'
    )
    parser.add_argument(
        '--skip-filesystem',
        action='store_true',
        default=False,
        help='Skip extraction of filesystem directory/file names'
    )
    
    args = parser.parse_args()
    
    # Validate input directory
    if not args.directory.exists():
        print(f"Error: Directory '{args.directory}' does not exist.")
        return 1
    
    if not args.directory.is_dir():
        print(f"Error: '{args.directory}' is not a directory.")
        return 1
    
    # Find HTML files
    print(f"Scanning for HTML files in {args.directory}{'...' if args.recursive else ''}")
    html_files = find_html_files(args.directory, args.recursive)
    
    if not html_files:
        print("No HTML files found.")
        return 0
    
    print(f"Found {len(html_files)} HTML file(s)")
    
    # Extract all texts and URL components
    all_texts: Set[str] = set()
    all_url_components: Set[str] = set()
    
    for html_file in html_files:
        print(f"Processing: {html_file}")
        texts, url_components = extract_from_html_file(html_file)
        all_texts.update(texts)
        if not args.skip_urls:
            all_url_components.update(url_components)
    
    # Extract filesystem components if not skipped
    if not args.skip_filesystem:
        print("\nExtracting directory and file names from filesystem...")
        filesystem_components = extract_filesystem_components(args.directory, args.recursive)
        all_url_components.update(filesystem_components)
        print(f"Found {len(filesystem_components)} filesystem component(s)")
    
    # Combine text content and URL components
    # URL components are typically short, so add them to the short texts
    combined_short_items = all_url_components.copy()
    
    # Separate short and long texts from content
    short_texts = [t for t in all_texts if len(t) < args.threshold]
    long_texts = [t for t in all_texts if len(t) >= args.threshold]
    
    # Add short text content to combined items
    combined_short_items.update(short_texts)
    
    # Sort everything
    sorted_short = sorted(combined_short_items)
    sorted_long = sorted(long_texts)
    
    # Create output directory if needed
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Check for existing files and prompt user
    translations_file = args.output_dir / 'translations.csv'
    long_translations_file = args.output_dir / 'long_translations.csv'
    
    if not args.append and (translations_file.exists() or long_translations_file.exists()):
        print("\nWarning: Output files already exist:")
        if translations_file.exists():
            print(f"  - {translations_file}")
        if long_translations_file.exists():
            print(f"  - {long_translations_file}")
        
        response = input("Do you want to (o)verwrite, (a)ppend, or (c)ancel? [o/a/c]: ").strip().lower()
        
        if response == 'c':
            print("Extraction cancelled.")
            return 0
        elif response == 'a':
            args.append = True
        elif response != 'o':
            print("Invalid choice. Extraction cancelled.")
            return 0
    
    # Write short translations (including URL components)
    count_short = write_csv_file(translations_file, sorted_short, 
                                  args.append, args.languages)
    
    if args.append and count_short > 0:
        print(f"\nAppended {count_short} new entr{'y' if count_short == 1 else 'ies'} to {translations_file}")
    else:
        print(f"\nWrote {len(sorted_short)} entr{'y' if len(sorted_short) == 1 else 'ies'} to {translations_file}")
    
    # Write long translations
    count_long = write_csv_file(long_translations_file, sorted_long, 
                                args.append, args.languages)
    
    if args.append and count_long > 0:
        print(f"Appended {count_long} new entr{'y' if count_long == 1 else 'ies'} to {long_translations_file}")
    else:
        print(f"Wrote {len(sorted_long)} entr{'y' if len(sorted_long) == 1 else 'ies'} to {long_translations_file}")
    
    # Summary
    print(f"\n{'='*60}")
    print(f"Extraction summary:")
    print(f"  Text content extracted: {len(all_texts)}")
    if not args.skip_urls:
        print(f"  URL components from HTML: {len(all_url_components - (filesystem_components if not args.skip_filesystem else set()))}")
    if not args.skip_filesystem:
        print(f"  Filesystem components: {len(filesystem_components)}")
    print(f"  Short items (< {args.threshold} chars): {len(sorted_short)}")
    print(f"  Long items (>= {args.threshold} chars): {len(sorted_long)}")
    print(f"  Total unique items: {len(sorted_short) + len(sorted_long)}")
    
    return 0


if __name__ == '__main__':
    exit(main())