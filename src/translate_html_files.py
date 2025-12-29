#!/usr/bin/env python3
"""
Replace text in HTML files with translations from CSV files.

This script reads translations from CSV files and replaces text in HTML files
with their translated equivalents, preserving HTML structure.
"""

import argparse
import csv
import re
import shutil
from pathlib import Path
from html.parser import HTMLParser
from typing import Dict, List, Tuple, Optional, Set


class TranslationReplacer(HTMLParser):
    """HTML parser that replaces text with translations."""
    
    # Attributes to translate
    TRANSLATABLE_ATTRS = {
        'alt', 'title', 'placeholder', 'aria-label', 
        'aria-describedby', 'aria-placeholder', 'data-location', 'data-city'
    }
    
    # Tags to skip entirely
    SKIP_TAGS = {'script', 'style'}
    
    def __init__(self, translation_map: Dict[str, str]):
        super().__init__()
        # Store original translation map for exact case-sensitive lookups
        self.translation_map = translation_map
        
        # Create multiple lookup variations for case-insensitive fallback
        self.lookup_variations = {}
        for k, v in translation_map.items():
            # Store all possible variations of the key
            variations = [
                k,  # Original
                self._normalize_separators(k),  # Normalized separators
                re.sub(r'[•\-–—−]', ' ', k),  # All separators as spaces
                re.sub(r'\s*[•\-–—−]\s*', ' • ', k),  # Bullets with spaces
                re.sub(r'\s*[•\-–—−]\s*', ' - ', k),  # Hyphens with spaces
            ]
            
            for variation in variations:
                # Normalize whitespace and store lowercase version for fallback
                normalized = re.sub(r'\s+', ' ', variation).strip().lower()
                # Don't overwrite if we already have this key (prefer first occurrence)
                if normalized not in self.lookup_variations:
                    self.lookup_variations[normalized] = v
        
        self.output = []
        self.skip_level = 0
        self.missing_translations = set()
        
    def handle_starttag(self, tag, attrs):
        """Handle opening tags."""
        # Track skip tags
        if tag in self.SKIP_TAGS:
            self.skip_level += 1
            self.output.append(self.get_starttag_text())
            return
            
        if self.skip_level > 0:
            self.output.append(self.get_starttag_text())
            return
        
        # Translate attributes
        new_attrs = []
        for attr_name, attr_value in attrs:
            if attr_name in self.TRANSLATABLE_ATTRS and attr_value:
                translated = self._translate_text(attr_value)
                new_attrs.append((attr_name, translated))
            elif attr_name == 'href' and tag == 'a':
                # Translate URL paths (but not anchors)
                translated_url = self._translate_url(attr_value)
                new_attrs.append((attr_name, translated_url))
            elif attr_name == 'content' and tag == 'meta':
                # Handle meta description
                meta_dict = dict(attrs)
                if meta_dict.get('name') == 'description':
                    translated = self._translate_text(attr_value)
                    new_attrs.append((attr_name, translated))
                else:
                    new_attrs.append((attr_name, attr_value))
            else:
                new_attrs.append((attr_name, attr_value))
        
        # Reconstruct tag
        if new_attrs:
            attrs_str = ' '.join(f'{name}="{value}"' for name, value in new_attrs)
            self.output.append(f'<{tag} {attrs_str}>')
        else:
            self.output.append(f'<{tag}>')
    
    def handle_endtag(self, tag):
        """Handle closing tags."""
        if tag in self.SKIP_TAGS:
            self.skip_level = max(0, self.skip_level - 1)
        self.output.append(f'</{tag}>')
    
    def handle_startendtag(self, tag, attrs):
        """Handle self-closing tags."""
        if self.skip_level > 0:
            self.output.append(self.get_starttag_text())
            return
            
        # Translate attributes
        new_attrs = []
        for attr_name, attr_value in attrs:
            if attr_name in self.TRANSLATABLE_ATTRS and attr_value:
                translated = self._translate_text(attr_value)
                new_attrs.append((attr_name, translated))
            else:
                new_attrs.append((attr_name, attr_value))
        
        # Reconstruct self-closing tag
        if new_attrs:
            attrs_str = ' '.join(f'{name}="{value}"' for name, value in new_attrs)
            self.output.append(f'<{tag} {attrs_str} />')
        else:
            self.output.append(f'<{tag} />')
    
    def handle_data(self, data):
        """Handle text content."""
        if self.skip_level > 0:
            self.output.append(data)
            return
        
        # Only translate if there's meaningful text
        stripped = data.strip()
        if stripped:
            # Preserve leading/trailing whitespace
            leading_ws = data[:len(data) - len(data.lstrip())]
            trailing_ws = data[len(data.rstrip()):]
            
            translated = self._translate_text(stripped)
            self.output.append(leading_ws + translated + trailing_ws)
        else:
            self.output.append(data)
    
    def handle_comment(self, data):
        """Handle HTML comments."""
        self.output.append(f'<!--{data}-->')
    
    def handle_decl(self, decl):
        """Handle DOCTYPE."""
        self.output.append(f'<!{decl}>')
    
    def handle_pi(self, data):
        """Handle processing instructions."""
        self.output.append(f'<?{data}>')
    
    def _normalize_separators(self, text: str) -> str:
        """Normalize all separator types to standard hyphen with spaces."""
        # Replace bullet, en-dash, em-dash, minus with hyphen
        text = re.sub(r'[•–—−]', '-', text)
        # Normalize spacing around separators
        text = re.sub(r'\s*-\s*', ' - ', text)
        # Collapse multiple spaces
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def _translate_url(self, url: str) -> str:
        """Translate URL path components, preserving anchors and query strings."""
        # Don't translate external URLs, mailto, tel, or anchors
        if (url.startswith(('http://', 'https://', 'mailto:', 'tel:', '//', '#')) or
            not url or url.startswith('javascript:')):
            return url
        
        # Split URL into path and fragment/query
        anchor_match = re.match(r'^([^#?]*)([#?].*)$', url)
        if anchor_match:
            path_part = anchor_match.group(1)
            anchor_part = anchor_match.group(2)
        else:
            path_part = url
            anchor_part = ''
        
        # Don't translate if it's just an anchor
        if not path_part:
            return url
        
        # Split path into components
        parts = path_part.split('/')
        translated_parts = []
        
        for part in parts:
            # Preserve empty parts, '.', and '..' (relative path references)
            if not part or part == '.' or part == '..':
                translated_parts.append(part)
                continue
            
            # Check if this is a file (has extension)
            if '.' in part:
                # Split filename and extension
                name_parts = part.rsplit('.', 1)
                filename = name_parts[0]
                extension = name_parts[1] if len(name_parts) > 1 else ''
                
                # Try to translate the filename (without extension)
                translated_filename = self._translate_text(filename)
                translated_parts.append(f"{translated_filename}.{extension}" if extension else translated_filename)
            else:
                # Translate directory name
                translated_parts.append(self._translate_text(part))
        
        # Reconstruct URL
        translated_path = '/'.join(translated_parts)
        return translated_path + anchor_part
    
    def _translate_text(self, text: str) -> str:
        """Translate a text string using the translation map with multiple normalization attempts."""
        # Normalize the text
        normalized = self._normalize_text(text)
        
        # First, try exact match with original case in translation_map
        if normalized in self.translation_map:
            return self.translation_map[normalized]
        
        # Try case-sensitive variations with normalized separators
        normalized_sep = self._normalize_separators(normalized)
        if normalized_sep != normalized and normalized_sep in self.translation_map:
            return self.translation_map[normalized_sep]
        
        # Fall back to case-insensitive matching
        lookup_key = normalized.lower()
        
        # Try multiple variations (case-insensitive)
        attempts = [
            lookup_key,
            self._normalize_separators(normalized).lower(),
            re.sub(r'\s*[•\-–—−]\s*', ' • ', normalized).lower(),
            re.sub(r'\s*[•\-–—−]\s*', ' - ', normalized).lower(),
            re.sub(r'[•\-–—−]', ' ', normalized).lower(),
        ]
        
        # Normalize whitespace for each attempt
        for attempt in attempts:
            attempt_normalized = re.sub(r'\s+', ' ', attempt).strip()
            if attempt_normalized in self.lookup_variations:
                return self.lookup_variations[attempt_normalized]
        
        # Record missing translation
        self.missing_translations.add(text)
        return text
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text)
        # Strip leading/trailing whitespace
        text = text.strip()
        return text
    
    def get_html(self) -> str:
        """Get the translated HTML."""
        return ''.join(self.output)
    
    def get_missing_translations(self) -> set:
        """Get set of texts that were not found in translation map."""
        return self.missing_translations


def load_translations(csv_file: Path, lang_code: str) -> Dict[str, str]:
    """
    Load translations from CSV file.
    Returns dict mapping source text to translated text.
    """
    translations = {}
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            # Check if lang_code column exists
            if lang_code not in reader.fieldnames:
                return translations
            
            if 'en' not in reader.fieldnames:
                print(f"Warning: 'en' column not found in {csv_file}")
                return translations
            
            for row in reader:
                source = row.get('en', '').strip()
                target = row.get(lang_code, '').strip()
                
                # Skip if source and target are identical (not translated)
                if source and target and source != target:
                    translations[source] = target
    
    except FileNotFoundError:
        print(f"Warning: Translation file not found: {csv_file}")
    except Exception as e:
        print(f"Warning: Error reading {csv_file}: {e}")
    
    return translations


def rename_path_components(
    source_dir: Path,
    dest_dir: Path,
    translations: Dict[str, str],
    dry_run: bool = False
) -> Tuple[int, int, int]:
    """
    Rename directories and files according to translations.
    Also translates HTML content and internal links.
    Returns (directories_renamed, files_renamed, html_files_translated).
    """
    dirs_renamed = 0
    files_renamed = 0
    html_translated = 0
    
    # Create destination directory
    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)
    
    # Get all paths and sort by depth (deepest first for directories, but we need files after dirs)
    all_dirs = [p for p in source_dir.rglob('*') if p.is_dir()]
    all_files = [p for p in source_dir.rglob('*') if p.is_file()]
    
    # Sort directories by depth (deepest first)
    all_dirs.sort(key=lambda p: len(p.parts), reverse=True)
    # Sort files by depth (shallowest first, so parent dirs exist)
    all_files.sort(key=lambda p: len(p.parts))
    
    # Process directories first
    for old_path in all_dirs:
        # Calculate relative path from source
        rel_path = old_path.relative_to(source_dir)
        
        # Translate each component of the path
        new_parts = []
        something_translated = False
        
        for part in rel_path.parts:
            # Translate directory name
            if part in translations:
                new_parts.append(translations[part])
                something_translated = True
            else:
                new_parts.append(part)
        
        if something_translated:
            dirs_renamed += 1
        
        # Construct new path
        new_rel_path = Path(*new_parts) if new_parts else Path('.')
        new_path = dest_dir / new_rel_path
        
        if dry_run:
            if something_translated:
                print(f"  Would rename directory: {rel_path} -> {new_rel_path}")
        else:
            # Create directory
            new_path.mkdir(parents=True, exist_ok=True)
    
    # Process files
    for old_path in all_files:
        # Calculate relative path from source
        rel_path = old_path.relative_to(source_dir)
        
        # Translate each component of the path
        new_parts = []
        something_translated = False
        
        for part in rel_path.parts[:-1]:  # All parts except filename
            # Translate directory name
            if part in translations:
                new_parts.append(translations[part])
                something_translated = True
            else:
                new_parts.append(part)
        
        # Handle filename
        filename = rel_path.parts[-1]
        if '.' in filename:
            # Split filename and extension
            name_parts = filename.rsplit('.', 1)
            basename = name_parts[0]
            extension = name_parts[1] if len(name_parts) > 1 else ''
            
            # Try to translate the filename
            if basename in translations:
                translated_filename = translations[basename]
                new_parts.append(f"{translated_filename}.{extension}" if extension else translated_filename)
                something_translated = True
                files_renamed += 1
            else:
                new_parts.append(filename)
        else:
            if filename in translations:
                new_parts.append(translations[filename])
                something_translated = True
                files_renamed += 1
            else:
                new_parts.append(filename)
        
        # Construct new path
        new_rel_path = Path(*new_parts) if new_parts else Path(filename)
        new_path = dest_dir / new_rel_path
        
        if dry_run:
            if something_translated:
                print(f"  Would rename file: {rel_path} -> {new_rel_path}")
            # Also check if HTML file would be translated
            if old_path.suffix.lower() in ['.html', '.htm']:
                print(f"  Would translate HTML content: {rel_path}")
        else:
            # Create parent directories if needed
            new_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if this is an HTML file that needs translation
            if old_path.suffix.lower() in ['.html', '.htm']:
                # Translate HTML content and internal links
                _, missing = translate_html_file(old_path, translations, new_path)
                html_translated += 1
                if missing and len(missing) > 5:  # Only report if many missing
                    print(f"  Note: {len(missing)} untranslated texts in {rel_path}")
            else:
                # Just copy other files
                shutil.copy2(old_path, new_path)
    
    return dirs_renamed, files_renamed, html_translated


def translate_html_file(
    html_path: Path,
    translation_map: Dict[str, str],
    output_path: Optional[Path] = None
) -> Tuple[int, set]:
    """
    Translate an HTML file using the translation map.
    Returns (number of replacements, set of missing translations).
    """
    try:
        with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {html_path}: {e}")
        return 0, set()
    
    # Parse and translate
    parser = TranslationReplacer(translation_map)
    parser.feed(content)
    translated_html = parser.get_html()
    missing = parser.get_missing_translations()
    
    # Write output
    out_path = output_path if output_path else html_path
    try:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(translated_html)
    except Exception as e:
        print(f"Error writing {out_path}: {e}")
        return 0, missing
    
    # Count actual replacements
    replacements = len([k for k in translation_map.keys() if k in content])
    
    return replacements, missing


def find_html_files(directory: Path, recursive: bool = True) -> List[Path]:
    """Find all HTML files in directory."""
    if recursive:
        return list(directory.rglob('*.html')) + list(directory.rglob('*.htm'))
    else:
        return list(directory.glob('*.html')) + list(directory.glob('*.htm'))


def rename_mode(args):
    """Rename directories and files according to translations."""
    print(f"Renaming directories and files for language: {args.lang}")
    
    # Load all translations
    translations_file = args.translations_dir / f'translations_{args.lang}.csv'
    long_translations_file = args.translations_dir / f'long_translations_{args.lang}.csv'
    
    if not translations_file.exists():
        translations_file = args.translations_dir / 'translations.csv'
    if not long_translations_file.exists():
        long_translations_file = args.translations_dir / 'long_translations.csv'
    
    translations = load_translations(translations_file, args.lang)
    long_translations = load_translations(long_translations_file, args.lang)
    
    # Merge translation maps
    all_translations = {**translations, **long_translations}
    
    if not all_translations:
        print(f"Error: No translations found for language '{args.lang}'")
        print(f"Expected files:")
        print(f"  - {translations_file}")
        print(f"  - {long_translations_file}")
        return 1
    
    print(f"Loaded {len(all_translations)} translation(s)")
    
    # Determine output directory
    if not args.output_dir:
        print("Error: --output-dir is required for rename mode")
        return 1
    
    # Check if dry run
    if args.dry_run:
        print("\n=== DRY RUN MODE - No changes will be made ===\n")
    
    # Perform renaming
    print(f"\nRenaming from {args.directory} to {args.output_dir}...")
    
    dirs_renamed, files_renamed, html_translated = rename_path_components(
        args.directory,
        args.output_dir,
        all_translations,
        dry_run=args.dry_run
    )
    
    # Summary
    print(f"\n{'='*60}")
    if args.dry_run:
        print("Dry run complete! (no changes made)")
        print(f"Would rename {dirs_renamed} director{'y' if dirs_renamed == 1 else 'ies'}")
        print(f"Would rename {files_renamed} file(s)")
        print(f"Would translate {html_translated} HTML file(s)")
    else:
        print("Renaming complete!")
        print(f"Renamed {dirs_renamed} director{'y' if dirs_renamed == 1 else 'ies'}")
        print(f"Renamed {files_renamed} file(s)")
        print(f"Translated {html_translated} HTML file(s)")
        print(f"Output saved to: {args.output_dir}")
    
    return 0


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Replace text in HTML files with translations from CSV files.'
    )
    parser.add_argument(
        'directory',
        type=Path,
        help='Input directory containing HTML files'
    )
    parser.add_argument(
        '--lang',
        required=True,
        help='Target language code (e.g., fr, nl, de)'
    )
    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        default=False,
        help='Recursively scan subdirectories'
    )
    parser.add_argument(
        '--translations-dir',
        type=Path,
        default=Path('.'),
        help='Directory containing translation CSV files (default: current directory)'
    )
    parser.add_argument(
        '-o', '--output-dir',
        type=Path,
        default=None,
        help='Output directory for translated files (default: overwrite originals)'
    )
    parser.add_argument(
        '--rename',
        action='store_true',
        default=False,
        help='Rename directories and files according to translations (requires --output-dir)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=False,
        help='Show what would be renamed without making changes (use with --rename)'
    )
    
    args = parser.parse_args()
    
    # Validate input directory
    if not args.directory.exists():
        print(f"Error: Directory '{args.directory}' does not exist.")
        return 1
    
    if not args.directory.is_dir():
        print(f"Error: '{args.directory}' is not a directory.")
        return 1
    
    # Rename mode
    if args.rename:
        return rename_mode(args)
    
    # Translation mode (default)
    print(f"Loading translations for language: {args.lang}")
    
    # Try language-specific files first (e.g., translations_fr.csv)
    translations_file = args.translations_dir / f'translations_{args.lang}.csv'
    long_translations_file = args.translations_dir / f'long_translations_{args.lang}.csv'
    
    # If language-specific files don't exist, try base files with language column
    if not translations_file.exists():
        translations_file = args.translations_dir / 'translations.csv'
    if not long_translations_file.exists():
        long_translations_file = args.translations_dir / 'long_translations.csv'
    
    translations = load_translations(translations_file, args.lang)
    long_translations = load_translations(long_translations_file, args.lang)
    
    # Merge translation maps
    all_translations = {**translations, **long_translations}
    
    if not all_translations:
        print(f"Error: No translations found for language '{args.lang}'")
        print(f"Expected files:")
        print(f"  - {translations_file}")
        print(f"  - {long_translations_file}")
        print(f"Make sure they contain an '{args.lang}' column.")
        return 1
    
    print(f"Loaded {len(all_translations)} translation(s)")
    
    # Find HTML files
    print(f"\nScanning for HTML files in {args.directory}{'...' if args.recursive else ''}")
    html_files = find_html_files(args.directory, args.recursive)
    
    if not html_files:
        print("No HTML files found.")
        return 0
    
    print(f"Found {len(html_files)} HTML file(s)")
    
    # Create output directory if needed
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Translate files
    total_replacements = 0
    all_missing = set()
    
    for html_file in html_files:
        print(f"\nProcessing: {html_file}")
        
        # Determine output path
        if args.output_dir:
            rel_path = html_file.relative_to(args.directory)
            output_path = args.output_dir / rel_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            output_path = html_file
        
        replacements, missing = translate_html_file(
            html_file,
            all_translations,
            output_path
        )
        
        total_replacements += replacements
        all_missing.update(missing)
        
        if output_path != html_file:
            print(f"  → Saved to: {output_path}")
        else:
            print(f"  → Updated in place")
        
        if missing:
            print(f"  → {len(missing)} text(s) not found in translations (left as-is)")
    
    # Summary
    print(f"\n{'='*60}")
    print(f"Translation complete!")
    print(f"Total files processed: {len(html_files)}")
    print(f"Total translations applied: {total_replacements}")
    
    if all_missing:
        print(f"\n{len(all_missing)} unique text(s) not found in translation files:")
        for text in sorted(all_missing)[:10]:  # Show first 10
            print(f"  - {text[:80]}{'...' if len(text) > 80 else ''}")
        if len(all_missing) > 10:
            print(f"  ... and {len(all_missing) - 10} more")
    
    return 0


if __name__ == '__main__':
    exit(main())