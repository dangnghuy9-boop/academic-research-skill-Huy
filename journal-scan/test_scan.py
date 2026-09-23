#!/usr/bin/env python3
"""Offline checks for scan.py. Every record is synthetic: DOIs use Crossref's
10.5555 test prefix and titles start with SYNTHETIC. No network access."""
import json
import sys
import tempfile
from pathlib import Path

from openpyxl import load_workbook

import scan


def rec(doi, title, *, online=None, printed=None, volume=None, issue=None, authors=True, update=False, abstract=None):
    r = {"DOI": doi, "type": "journal-article", "title": [title]}
    if authors:
        r["author"] = [{"given": "Ada", "family": "Example"}, {"given": "Bo", "family": "Sample"}]
    if online:
        r["published-online"] = {"date-parts": [online]}
    if printed:
        r["published-print"] = {"date-parts": [printed]}
    if volume:
        r["volume"], r["issue"] = volume, issue
    if update:
        r["update-to"] = [{"DOI": "10.5555/orig", "type": "correction"}]
    if abstract:
        r["abstract"] = f"<jats:title>Abstract</jats:title><jats:p>{abstract} <i>e</i>-commerce.</jats:p>"
    return r


FIXTURE = {
    "JM": [
        rec("10.5555/JM.2025.001", "SYNTHETIC in-issue 2025 paper", online=[2024, 11, 3], printed=[2025, 3],
            volume="89", issue="2", abstract="Synthetic abstract one."),
        rec("10.5555/jm.2026.002", "SYNTHETIC online-first 2026 paper", online=[2026, 8, 21],
            abstract="Synthetic abstract two."),
        rec("10.5555/jm.2024.003", "SYNTHETIC 2024 issue paper", online=[2024, 1, 5], printed=[2024, 7],
            volume="88", issue="4"),
        rec("10.5555/jm.2024.004", "SYNTHETIC stale online-first", online=[2024, 12, 30]),
        rec("10.5555/jm.2025.005", "Erratum to SYNTHETIC paper", online=[2025, 5, 1]),
        rec("10.5555/jm.2025.006", "SYNTHETIC correction notice", online=[2025, 5, 2], update=True),
    ],
    "JMR": [
        rec("10.5555/jmr.2025.001", "Issue Information", online=[2025, 2, 1], printed=[2025, 2],
            volume="62", issue="1", authors=False),
        rec("10.5555/jmr.2025.002", "SYNTHETIC unresolvable DOI paper", online=[2025, 6, 1]),
        rec("10.5555/jmr.2025.003", "SYNTHETIC doi.org outage paper", online=[2025, 6, 2]),
    ],
    "JCP": [
        rec("10.5555/jcpy.2025.001", "Commentary on SYNTHETIC target article", online=[2025, 4, 1],
            abstract="Synthetic commentary."),
        rec("10.5555/jcpy.2025.002", "SYNTHETIC no-abstract paper", online=[2025, 9, 9]),
    ],
}


def fake_get_json(url, data=None, **_):
    if url.startswith("https://doi.org/api/handles/"):
        doi = url.split("/api/handles/")[1].split("?")[0]
        if doi.endswith("jmr.2025.002"):
            raise scan.NotFound(url)
        if doi.endswith("jmr.2025.003"):
            raise TimeoutError("simulated outage")
        host = "myscp.onlinelibrary.wiley.com" if "jcpy" in doi else "journals.sagepub.com"
        return {"responseCode": 1, "values": [{"type": "URL", "data": {"value": f"https://{host}/doi/{doi}"}}]}
    if url.startswith("https://api.openalex.org/"):
        return {"results": [
            {"doi": "https://doi.org/10.5555/jm.2026.002", "abstract_inverted_index": None,
             "open_access": {"is_oa": True, "oa_status": "hybrid", "oa_url": "https://example.org/x.pdf"}},
            {"doi": "https://doi.org/10.5555/jm.2025.001", "abstract_inverted_index": {"ignored": [0]},
             "open_access": {"is_oa": False, "oa_status": "closed", "oa_url": None}},
        ]}
    if url.startswith("https://api.semanticscholar.org/"):
        return [None for _ in data["ids"]]
    raise AssertionError(f"unexpected URL {url}")


def expect_exit(fn, needle):
    try:
        fn()
    except SystemExit as e:
        assert needle in str(e), f"exit message {e!r} lacks {needle!r}"
        return
    raise AssertionError(f"expected SystemExit containing {needle!r}")


def main():
    scan.fetch_crossref = lambda j: FIXTURE[j["key"]]
    scan.get_json = fake_get_json
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        (data / "annotations").mkdir()
        run = lambda *a: scan.main(["--data", tmp, *a])  # noqa: E731

        run("fetch")
        items = {c["doi"]: c for c in json.loads((data / "candidates.json").read_text())["items"]}
        assert "10.5555/jm.2025.001" in items, "2024 online-first printed in a 2025 issue must be in window"
        assert items["10.5555/jm.2025.001"]["year_issue"] == "2025, Vol. 89, Issue 2"
        assert items["10.5555/jm.2025.001"]["crossref_abstract"] == "Synthetic abstract one. e-commerce."
        assert items["10.5555/jm.2026.002"]["year_issue"] == "Online first"
        assert "10.5555/jm.2024.003" not in items, "2024 issue must be out of window"
        assert "10.5555/jm.2024.004" not in items, "2024 online-first must be out of window"
        assert items["10.5555/jm.2025.005"]["exclude_reason"] == "correction/retraction notice"
        assert items["10.5555/jm.2025.006"]["exclude_reason"] == "correction/retraction notice"
        assert items["10.5555/jmr.2025.001"]["exclude_reason"] == "front/back matter"
        assert items["10.5555/jcpy.2025.001"]["flags"] == ["commentary"]
        assert items["10.5555/jcpy.2025.001"]["exclude_reason"] is None, "commentaries are decided by reading"

        run("verify")
        v = {c["doi"]: c for c in json.loads((data / "verified.json").read_text())["items"]}
        assert v["10.5555/jm.2025.001"]["verified"] is True
        assert v["10.5555/jmr.2025.002"]["verified"] is False
        assert v["10.5555/jmr.2025.003"]["verified"] is None
        assert "verify_note" not in v["10.5555/jcpy.2025.002"], "wiley host must match JCP"

        run("enrich")
        e = {c["doi"]: c for c in json.loads((data / "enriched.json").read_text())["items"]}
        assert e["10.5555/jm.2025.001"]["abstract_source"] == "Crossref (publisher deposit)"
        assert e["10.5555/jm.2026.002"]["is_oa"] is True
        assert e["10.5555/jcpy.2025.002"]["abstract"] is None
        assert e["10.5555/jcpy.2025.002"]["is_oa"] is None

        def ann(tag, kind="research"):
            return {"type": kind, "finding": "SYNTHETIC finding.", "method": "SYNTHETIC method", "tag": tag,
                    "future": "not available"}

        out = str(data / "out.xlsx")
        expect_exit(lambda: run("build", "--out", out), "have no annotation yet")

        (data / "annotations" / "b1.json").write_text(json.dumps({
            "10.5555/jm.2025.001": ann("Pricing"),
            "10.5555/jm.2026.002": ann("AI"),
            "10.5555/jcpy.2025.001": ann("Pricing", "commentary"),
            "10.5555/jcpy.2025.002": ann("AI"),
        }))
        (data / "annotations" / "b2.json").write_text(json.dumps({"10.5555/jmr.2025.002": ann("AI")}))
        expect_exit(lambda: run("build", "--out", out), "typo or invented")

        (data / "annotations" / "b2.json").write_text(json.dumps({"10.5555/jm.2025.001": ann("AI")}))
        expect_exit(lambda: run("build", "--out", out), "annotated twice")

        (data / "annotations" / "b2.json").unlink()
        (data / "annotations" / "b1.json").write_text(json.dumps({
            "10.5555/jm.2025.001": ann("Consumer price fairness"),
            "10.5555/jm.2026.002": ann("AI"),
            "10.5555/jcpy.2025.001": ann("Pricing", "commentary"),
            "10.5555/jcpy.2025.002": ann("AI"),
        }))
        expect_exit(lambda: run("build", "--out", out), "longer than two words")

        (data / "annotations" / "b1.json").write_text(json.dumps({
            "10.5555/jm.2025.001": ann("Pricing"),
            "10.5555/jm.2026.002": ann("AI"),
            "10.5555/jcpy.2025.001": ann("Pricing", "commentary"),
            "10.5555/jcpy.2025.002": ann("AI"),
        }))
        run("build", "--out", out)

        wb = load_workbook(out)
        assert wb.sheetnames == ["Papers", "Topic counts", "Limited access", "Excluded", "About"]
        papers = wb["Papers"]
        assert [c.value for c in papers[1]] == scan.HEADERS
        dois = [r[4].value for r in papers.iter_rows(min_row=2)]
        assert dois == ["https://doi.org/10.5555/jm.2025.001", "https://doi.org/10.5555/jm.2026.002",
                        "https://doi.org/10.5555/jcpy.2025.002"], dois
        assert all(r[9].value is None for r in papers.iter_rows(min_row=2)), "Interested? must stay blank"
        assert papers["E2"].hyperlink.target == "https://doi.org/10.5555/jm.2025.001"
        excluded = {r[3].value: r[4].value for r in wb["Excluded"].iter_rows(min_row=2)}
        assert excluded["https://doi.org/10.5555/jcpy.2025.001"] == "commentary"
        assert excluded["https://doi.org/10.5555/jmr.2025.001"] == "front/back matter"
        limited = {r[3].value: (r[4].value, r[6].value) for r in wb["Limited access"].iter_rows(min_row=2)}
        assert limited["https://doi.org/10.5555/jmr.2025.002"] == ("No", "doi.org: DOI not registered")
        assert limited["https://doi.org/10.5555/jmr.2025.003"][0] == "No"
        assert "main finding is not available" in limited["https://doi.org/10.5555/jcpy.2025.002"][1]
        assert limited["https://doi.org/10.5555/jm.2025.001"] == ("Yes", "full text is subscription-only")
        assert "https://doi.org/10.5555/jm.2026.002" not in limited, "open-access papers are not limited"
        print(f"all checks passed; workbook at {out}")
        if len(sys.argv) > 1:
            Path(sys.argv[1]).write_bytes(Path(out).read_bytes())


if __name__ == "__main__":
    sys.exit(main())
