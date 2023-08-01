#
# SPDX-FileCopyrightText: 2023 John Samuel <johnsamuelwrites@gmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Script to convert text in markdown format to HMTL snippet

import argparse
import markdown

def read_markdown_file(file_path):
    """
    Read the content of a Markdown file.

    Parameters:
        file_path (str): The path to the Markdown file.

    Returns:
        str: The content of the Markdown file as a string.
    """
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()

def markdown_to_html(markdown_text):
    """
    Convert Markdown text to HTML.

    Parameters:
        markdown_text (str): The Markdown text to be converted.

    Returns:
        str: The HTML snippet generated from the Markdown text.
    """
    return markdown.markdown(markdown_text)

def write_html_to_file(html_text, output_file_path):
    """
    Write the HTML content to a file.

    Parameters:
        html_text (str): The HTML content to be written.
        output_file_path (str): The path to the output file.
    """
    with open(output_file_path, 'w', encoding='utf-8') as file:
        file.write(html_text)

def main():
    parser = argparse.ArgumentParser(description='Convert Markdown to HTML')
    parser.add_argument('input_file', help='Path to the input Markdown file')
    parser.add_argument('output_file', help='Path to the output HTML file')
    args = parser.parse_args()

    input_file_path = args.input_file
    output_file_path = args.output_file

    markdown_text = read_markdown_file(input_file_path)
    html_snippet = markdown_to_html(markdown_text)
    write_html_to_file(html_snippet, output_file_path)

if __name__ == "__main__":
    main()

