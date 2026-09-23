# JM / JMR / JCP article scan (Jan 2025 → today)

Pipeline behind `marketing-journals-2025.xlsx`. Needs network access to
`api.crossref.org`, `api.openalex.org` and `doi.org`.

1. `python fetch_crossref.py` — every Crossref `journal-article` record for the three
   journals (print + online ISSNs), unioning the pub / print / online date filters from 2025-01-01.
2. `python enrich.py` — normalizes records, drops non-research items (editorials, errata,
   commentaries, front matter), adds OpenAlex abstracts and open-access status, and checks every
   DOI against the doi.org Handle API. A paper whose DOI does not verify is excluded.
3. `data/summaries.json` — per-DOI finding / method / topic tag / future directions, written from
   each paper's abstract (and open-access full text where available).
4. `python build_xlsx.py marketing-journals-2025.xlsx` — builds the workbook.
