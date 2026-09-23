# Journal scan: JM, JMR, JCP (2025 onward)

Lists every research article in *Journal of Marketing*, *Journal of Marketing
Research* and *Journal of Consumer Psychology* published from 1 January 2025,
including online-first papers. Output is `journal_scan.xlsx`, with one row per
paper.

```bash
python3 scan.py fetch               # Crossref records -> data/candidates.json
python3 scan.py verify              # doi.org check    -> data/verified.json
python3 scan.py enrich --fulltext   # abstracts + OA   -> data/enriched.json
python3 scan.py worklist --batch 25 # papers still needing annotation
python3 scan.py build               # annotations/*.json -> journal_scan.xlsx
python3 test_scan.py                # offline self-test (synthetic records only)
```

`data/annotations/*.json` holds the hand-written columns, keyed by DOI:
`{"<doi>": {"type": "research", "finding": "...", "method": "...", "tag": "...", "future": "..."}}`.
`type` is one of `research`, `review`, `commentary`, `rejoinder`, `editorial` or `other`.
Only `research` and `review` rows reach the Papers sheet.

**Network.** `api.crossref.org` and `doi.org` are required. `api.openalex.org` and
`api.semanticscholar.org` add abstracts and open-access status.

**Recalculation.** Recalculating the workbook's formulas needs LibreOffice Calc
(`apt-get install libreoffice-calc`).
