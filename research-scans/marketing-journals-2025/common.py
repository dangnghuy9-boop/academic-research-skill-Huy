"""Shared config + HTTP helpers for the JM / JMR / JCP scan."""
import json, time, pathlib, requests
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent
RAW, DATA = ROOT / "raw", ROOT / "data"
START = "2025-01-01"
TODAY = date.today().isoformat()
UA = "ars-journal-scan/1.0 (python-requests; academic literature scan)"

JOURNALS = {
    "JM":  {"name": "Journal of Marketing",           "issns": ["0022-2429", "1547-7185"]},
    "JMR": {"name": "Journal of Marketing Research",  "issns": ["0022-2437", "1547-7193"]},
    "JCP": {"name": "Journal of Consumer Psychology", "issns": ["1057-7408", "1532-7663"]},
}

_session = requests.Session()
_session.headers["User-Agent"] = UA


def get_json(url, params=None, tries=5, timeout=60):
    """GET with exponential backoff; returns parsed JSON or raises the last error."""
    err = None
    for i in range(tries):
        try:
            r = _session.get(url, params=params, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code} for {r.url}")
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            err = e
            time.sleep(2 ** i)
    raise err


def date_str(parts_obj):
    """Crossref {'date-parts': [[y, m, d]]} -> 'YYYY-MM-DD' (missing parts padded with 01)."""
    if not parts_obj:
        return None
    p = (parts_obj.get("date-parts") or [[None]])[0]
    if not p or p[0] is None:
        return None
    y, m, d = (list(p) + [1, 1])[:3]
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def dump(obj, path):
    pathlib.Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1))


def load(path, default=None):
    p = pathlib.Path(path)
    return json.loads(p.read_text()) if p.exists() else default
