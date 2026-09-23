"""Step 2: normalize Crossref records, add OpenAlex abstracts/OA status, verify DOIs at doi.org.

Output: data/papers.json — one record per in-window item, with `include` + `exclude_reason`.
"""
import html, re, time
from concurrent.futures import ThreadPoolExecutor
from common import JOURNALS, START, TODAY, RAW, DATA, get_json, date_str, dump, load

# Titles that mark non-research front/back matter. Matched case-insensitively at the start
# of the title (or as the whole title) so research papers that merely contain a word survive.
NON_RESEARCH = re.compile(
    r"^(erratum|errata|corrigendum|correction( to)?|retraction|retracted|expression of concern|"
    r"editorial|editor'?s? (note|introduction|comment)|from the editors?|issue information|"
    r"in this issue|call for papers|reviewer(s)? (acknowledg|thank)|thank you to (our )?reviewers|"
    r"acknowledg(e)?ment of reviewers|in memoriam|obituary|announcement|masthead|"
    r"editorial board|table of contents|index to volume|author index|commentary|rejoinder|"
    r"a (brief )?commentary|reply to|response to)", re.I)
COMMENTARY_ANYWHERE = re.compile(r"\b(commentary on|a response to|rejoinder to|reply to)\b", re.I)


def clean_jats(s):
    if not s:
        return None
    s = re.sub(r"<jats:title>.*?</jats:title>", " ", s, flags=re.S)   # drop "Abstract" heading
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(re.sub(r"\s+", " ", s)).strip()
    return s or None


def inverted_to_text(inv):
    if not inv:
        return None
    pos = [(i, w) for w, idx in inv.items() for i in idx]
    return " ".join(w for _, w in sorted(pos)) or None


def authors_str(auth):
    names = []
    for a in auth or []:
        n = " ".join(x for x in (a.get("given"), a.get("family")) if x) or a.get("name")
        if n:
            names.append(n.strip())
    return "; ".join(names)


def normalize(key, it):
    title = " ".join(it.get("title") or []).strip()
    sub = " ".join(it.get("subtitle") or []).strip()
    if sub and sub.lower() not in title.lower():
        title = f"{title}: {sub}"
    title = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"\s+", " ", title)))
    online, prnt = date_str(it.get("published-online")), date_str(it.get("published-print"))
    issued = date_str(it.get("issued")) or date_str(it.get("published"))
    issue, vol = it.get("issue"), it.get("volume")
    in_issue = bool(issue and vol)
    # Window rule: in if either the online date or the issue/print date falls in [START, TODAY].
    dates = [d for d in (online, prnt) if d] or [issued]
    in_window = any(d and START <= d <= TODAY for d in dates)
    if in_issue:
        yr = (prnt or issued or online or "")[:4]
        yi = f"{yr}, Vol. {vol}, Issue {issue}"
    else:
        yi = f"Online first ({online or issued})"
    return {
        "doi": it["DOI"].lower(), "journal_key": key, "journal": JOURNALS[key]["name"],
        "title": title, "authors": authors_str(it.get("author")), "n_authors": len(it.get("author") or []),
        "online_date": online, "print_date": prnt, "issued": issued, "volume": vol, "issue": issue,
        "in_issue": in_issue, "year_issue": yi, "page": it.get("page"),
        "abstract_crossref": clean_jats(it.get("abstract")),
        "license": [l.get("URL") for l in it.get("license") or []],
        "update_to": it.get("update-to"), "in_window": in_window,
    }


def classify(p):
    t = p["title"]
    if not p["in_window"]:
        return False, "outside Jan-2025..today window"
    if not t:
        return False, "no title"
    if NON_RESEARCH.search(t) or COMMENTARY_ANYWHERE.search(t):
        return False, "non-research item (editorial/erratum/commentary/front matter)"
    if p["update_to"]:
        return False, "correction/retraction notice (Crossref update-to)"
    if p["n_authors"] == 0:
        return False, "no authors listed (likely front matter)"
    return True, None


def openalex(dois):
    out = {}
    for i in range(0, len(dois), 50):
        chunk = dois[i:i + 50]
        res = get_json("https://api.openalex.org/works",
                       params={"filter": "doi:" + "|".join(chunk), "per-page": 50,
                               "select": "doi,type,abstract_inverted_index,open_access,best_oa_location,"
                                         "primary_location,publication_date"})
        for w in res.get("results", []):
            d = (w.get("doi") or "").replace("https://doi.org/", "").lower()
            out[d] = w
        time.sleep(0.2)
    return out


def verify_doi(doi):
    """doi.org Handle API: responseCode 1 == DOI registered; also capture the URL it resolves to."""
    try:
        r = get_json(f"https://doi.org/api/handles/{doi}", params={"type": "URL"}, tries=4, timeout=30)
        url = next((v["data"]["value"] for v in r.get("values", []) if v.get("type") == "URL"), None)
        return doi, r.get("responseCode") == 1 and bool(url), url
    except Exception as e:  # recorded, never assumed valid
        return doi, False, f"ERROR: {e}"


if __name__ == "__main__":
    papers = []
    for key in JOURNALS:
        for it in load(RAW / f"crossref_{key}.json", []):
            p = normalize(key, it)
            p["include"], p["exclude_reason"] = classify(p)
            papers.append(p)
    inc = [p for p in papers if p["include"]]
    print(f"normalized {len(papers)}; provisionally included {len(inc)}")

    oa = openalex([p["doi"] for p in inc])
    for p in inc:
        w = oa.get(p["doi"], {})
        p["abstract_openalex"] = inverted_to_text(w.get("abstract_inverted_index"))
        o = w.get("open_access") or {}
        best = w.get("best_oa_location") or {}
        p["is_oa"], p["oa_status"] = o.get("is_oa"), o.get("oa_status")
        p["oa_url"] = best.get("pdf_url") or best.get("landing_page_url") or o.get("oa_url")
        p["openalex_type"] = w.get("type")
        p["abstract"] = p["abstract_crossref"] or p["abstract_openalex"]
        p["abstract_source"] = ("crossref" if p["abstract_crossref"] else
                                "openalex" if p["abstract_openalex"] else None)
    print(f"openalex matched {sum(1 for p in inc if p['doi'] in oa)}/{len(inc)}; "
          f"abstracts: {sum(1 for p in inc if p['abstract'])}/{len(inc)}; OA: {sum(1 for p in inc if p.get('is_oa'))}")

    with ThreadPoolExecutor(8) as ex:
        res = {d: (ok, url) for d, ok, url in ex.map(verify_doi, [p["doi"] for p in inc])}
    for p in inc:
        p["doi_ok"], p["doi_target"] = res[p["doi"]]
        if not p["doi_ok"]:
            p["include"], p["exclude_reason"] = False, f"DOI did not verify at doi.org ({p['doi_target']})"
    print(f"doi.org verified: {sum(1 for p in inc if p['doi_ok'])}/{len(inc)}")
    dump(papers, DATA / "papers.json")
