# Wikibase export queries

These read-only queries export the local Wikibase into versioned offline build
inputs. They are split into small result sets because hosted query services may
impose time and row limits.

| Query | Suggested output |
| --- | --- |
| `all-multilingual-labels.rq` | `data/labels-wikibase.csv` |
| `abstract-content-items.rq` | `data/abstract-content-items.csv` |
| `abstract-content-values.rq` | `data/abstract-content-values.csv` |
| `abstract-composition.rq` | `data/abstract-composition.csv` |
| `abstract-constructors.rq` | `data/abstract-constructors.csv` |
| `abstract-schema.rq` | `data/abstract-schema.csv` |
| `q3062-pilot-graph.rq` | `data/q3062-pilot-graph.csv` |
| `travel-abstract-pages.rq` | `data/travel-abstract-pages.csv` |

The checked-in CSV files, not the live endpoint, are consumed by site builds.
Network refresh is an explicit CI synchronization step.

Run a refresh locally with:

```bash
python src/export_sparql_queries.py
```

The scheduled GitHub Actions workflow performs the same export and commits only
changed CSV files. Downloads are validated before any existing dataset is
replaced, so a failed endpoint request cannot erase the offline cache.

Current local schema: P8 instance of; P12 abstract page; P21 part of; P38
localized path segment; P39 localized relative path; P40 monolingual content;
P41 constructor function; P42 sequence ordinal; Q3017 language-independent
page; Q3185 content component; Q3834 abstract function; Q3835 abstract
paragraph; Q3836 abstract sentence.
