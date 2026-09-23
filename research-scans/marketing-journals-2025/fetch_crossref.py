"""Step 1: enumerate every Crossref journal-article record for the three journals.

Three date filters are unioned so nothing slips through:
  from-pub-date        earliest of print/online  (catches online-first)
  from-print-pub-date  issue date                (catches late-2024 online / 2025 issue papers)
  from-online-pub-date online date
"""
import sys
from common import JOURNALS, START, RAW, get_json, dump

FIELDS = ("DOI,title,subtitle,author,container-title,ISSN,published-print,published-online,"
          "issued,published,volume,issue,page,type,abstract,subject,license,link,update-to,relation,"
          "created,article-number")

def pull(issn, date_filter):
    items, cursor = [], "*"
    while True:
        msg = get_json(f"https://api.crossref.org/journals/{issn}/works",
                       params={"filter": f"{date_filter}:{START},type:journal-article",
                               "rows": 200, "cursor": cursor, "select": FIELDS})["message"]
        batch = msg.get("items", [])
        items += batch
        if not batch or len(batch) < 200:
            return items, msg.get("total-results")
        cursor = msg["next-cursor"]

if __name__ == "__main__":
    for key, j in JOURNALS.items():
        by_doi, report = {}, []
        for issn in j["issns"]:
            for f in ("from-pub-date", "from-print-pub-date", "from-online-pub-date"):
                items, total = pull(issn, f)
                report.append(f"{issn} {f}: {len(items)} (total-results={total})")
                for it in items:
                    by_doi.setdefault(it["DOI"].lower(), it)
        dump(list(by_doi.values()), RAW / f"crossref_{key}.json")
        print(f"[{key}] {len(by_doi)} unique DOIs")
        for line in report:
            print("   ", line)
    sys.exit(0)
