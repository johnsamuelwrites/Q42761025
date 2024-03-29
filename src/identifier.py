#
# SPDX-FileCopyrightText: 2022 John Samuel <johnsamuelwrites@gmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later
#

from bs4 import BeautifulSoup
import re
import math
import pandas as pd
from query import MediaWiki


class HTMLTextAnalysis:
    @staticmethod
    def extract_identifiers(filepath):
        identifiers = []
        with open(filepath, "r") as inputfile:
            content = inputfile.read()
            parsed_html = BeautifulSoup(content, features="html.parser")

            if parsed_html.body is not None:
                text = parsed_html.body.get_text()
                identifiers = re.findall(r"Q\d+", text)
        return identifiers


class Identifier:
    identifiers_file = "../data/labels.csv"

    @staticmethod
    def get_existing_identifiers():
        df = pd.read_csv(
            Identifier.identifiers_file,
            dtype={
                "identifier": str,
                "en": str,
                "fr": str,
                "ml": str,
                "pa": str,
                "hi": str,
                "pt": str,
                "es": str,
                "it": str,
                "de": str,
                "nl": str,
            },
        )
        return df

    @staticmethod
    def extract_identifiers_from_html_file(filepath):
        identifiers = HTMLTextAnalysis.extract_identifiers(filepath)
        return identifiers

    @staticmethod
    def update_labels_for_identifiers(identifiers=None, languages=None):
        # Get existing labels
        labels_df = Identifier.get_existing_identifiers()

        # Check if labels already exist
        for language in languages:
            missing_labels_for_identifiers = []

            if identifiers is not None:
                for identifier in identifiers:
                    if identifier in labels_df["identifier"].values:
                        value = labels_df.loc[labels_df["identifier"] == identifier][
                            language
                        ].values[0]
                        if value != "":
                            continue

                    # Label is missing for the given language. Add to the list of identifiers missing labels
                    missing_labels_for_identifiers.append(identifier)
            else:
                for identifier in labels_df["identifier"].values:
                    if identifier in labels_df["identifier"].values:
                        value = labels_df.loc[labels_df["identifier"] == identifier][
                            language
                        ].values[0]
                        if (type(value) == str and value != "") or (
                            type(value) == float and not math.isnan(value)
                        ):
                            continue

                    # Label is missing for the given language. Add to the list of identifiers missing labels
                    missing_labels_for_identifiers.append(identifier)

            for i in range(0, len(missing_labels_for_identifiers), 50):
                sublist = missing_labels_for_identifiers[i : i + 50]
                missing_labels = MediaWiki.get_labels(sublist, language)

                # Update the labels data frame
                for key, value in missing_labels.items():
                    if key in labels_df["identifier"].values:
                        labels_df.loc[labels_df["identifier"] == key, language] = value
                    else:
                        row = {"identifier": key, language: value}
                        new_row_df = pd.DataFrame([row])
                        labels_df = pd.concat(
                            [labels_df, new_row_df], axis=0, ignore_index=True
                        )

        print(labels_df)
        labels_df.to_csv(Identifier.identifiers_file, index=False)

    @staticmethod
    def update_labels_for_html_file(filepath, languages):
        labels = dict()
        identifiers = Identifier.extract_identifiers_from_html_file(filepath)

        Identifier.update_labels_for_identifiers(identifiers, languages)
