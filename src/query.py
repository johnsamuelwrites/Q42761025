#
# SPDX-FileCopyrightText: 2020 John Samuel <johnsamuelwrites@gmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later
#

import requests


class MediaWiki:
    wikidata_mediawiki_api = "https://www.wikidata.org/w/api.php?format=json"

    @staticmethod
    def request_api(url):
        response = requests.get(url)
        if response.status_code == 200:
            json_response = response.json()
            return json_response
        else:
            return None

    @staticmethod
    def get_labels(identifiers, language):
        labels = dict()
        params = dict()
        params["action"] = "query"
        params["prop"] = "entityterms"
        params["titles"] = "|".join(identifiers)
        params["wbetlanguage"] = language
        params["wbetterms"] = "label"

        url_params = "&".join([key + "=" + params[key] for key in params.keys()])
        url = MediaWiki.wikidata_mediawiki_api + "&" + url_params

        json_response = MediaWiki.request_api(url)
        if json_response is not None:
            pages = json_response["query"]["pages"]
            for key in pages:
                if "entityterms" in pages[key]:
                    labels[pages[key]["title"]] = pages[key]["entityterms"]["label"][0]

        return labels
