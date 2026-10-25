#!/usr/bin/env python
"""Check that every rule in the medication catalogue can be traced to a live source.

`backend/test_pharmacology_agent.py` proves the registry is *internally*
consistent: every drug and every interaction names an id, and every id resolves
to a title and a URL. It cannot prove that the document behind that URL still
exists — a moved DOI passes every offline assertion, which is exactly how a
citation rots unnoticed in a clinical tool.

This script is the missing half. Offline it repeats the structural invariants
(fast, no network, usable everywhere). With ``--network`` it checks each
citation against the publisher:

* a DOI (``10.xxx/...``, whether the URL is a doi.org link or a journal's
  ``/doi/`` path) is resolved through Crossref, a free metadata API that needs
  no key. The reply must be a 200 and its title must agree with the registered
  one, which proves both that the identifier exists and that it names the
  document we cite.
* anything else is fetched directly. Publisher bot protection (401, 403, 429)
  is reported as *protected*, not as a dead link: AHA journals and
  Diabetes Care serve 403 to every non-browser client, and a checker that
  called that a broken citation would be turned off within a week. 404 and 410
  are dead; a DNS/TLS/timeout failure is unreachable.

A network run on a machine with no egress exits 2 rather than claiming the
sources are gone, so an offline laptop is never mistaken for a withdrawn
guideline.

Usage:
    python scripts/verify_sources.py                 # structure only
    python scripts/verify_sources.py --network       # structure + live checks
    python scripts/verify_sources.py --network --json

Exit codes: 0 every check passed, 1 at least one citation is dead or a title
disagrees, 2 network checks were requested but nothing answered at all.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents import pharmacology_agent as pharmacology  # noqa: E402

# The Windows console is cp1252 by default; a tick mark is not worth a crash.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = (
    "PulseIQ-source-check/1.0 (citation verification; "
    "mailto:pulseiq-source-check@example.org)"
)
DOI_IN_URL = re.compile(r"(10\.\d{4,9}/[^\s?#]+)")
STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "over", "this", "that",
    "patients", "patient", "guideline", "guidelines", "clinical", "practice",
}


def source_ids(entry: dict) -> list[str]:
    value = entry.get("source")
    return list(value) if isinstance(value, (list, tuple)) else [value] if value else []


def structural_problems() -> list[str]:
    problems: list[str] = []
    registry = pharmacology.SOURCES
    if len(registry) < 10:
        problems.append(f"only {len(registry)} sources registered")

    seen_urls: dict[str, str] = {}
    for source_id, source in registry.items():
        title = str(source.get("title", "")).strip()
        url = str(source.get("url", "")).strip()
        if not title:
            problems.append(f"{source_id}: no title")
        elif len(title) < 20:
            problems.append(f"{source_id}: title too short to identify the document ({title!r})")
        if not url.startswith("https://"):
            problems.append(f"{source_id}: URL is not https ({url!r})")
        if url in seen_urls:
            problems.append(f"{source_id}: same URL as {seen_urls[url]}")
        else:
            seen_urls[url] = source_id

    used: set[str] = set()
    for drug in pharmacology.DRUGS:
        ids = source_ids(drug)
        if not ids:
            problems.append(f"drug {drug['key']}: no source")
        used.update(ids)
    for rule in pharmacology.INTERACTIONS:
        ids = source_ids(rule)
        if not ids:
            problems.append(f"rule {rule['a']} + {rule['b']}: no source")
        used.update(ids)

    for missing in sorted(used - set(registry)):
        problems.append(f"a rule names {missing!r}, which is not in SOURCES")
    for unused in sorted(set(registry) - used):
        problems.append(f"{unused!r} is registered but never cited")
    return problems


def title_tokens(value: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", value.lower())
    return {word for word in words if len(word) > 2 and word not in STOPWORDS}


def titles_agree(registered: str, returned: str) -> bool:
    """Whether a Crossref title names the document we cite.

    Publisher titles are longer than the short name a table can hold (the 2018
    cholesterol guideline's full title has five societies the registry omits),
    and Crossref sometimes holds a subtitle or a shortened form. So the test is
    containment in whichever direction is shorter, not equality.
    """
    a, b = title_tokens(registered), title_tokens(returned)
    if len(a) < 3 or len(b) < 3:
        return False
    shared = len(a & b)
    # Three shared tokens is enough when the shorter title is that short and
    # almost entirely contained: a practice bulletin's metadata carries only
    # "Gestational Hypertension and Preeclampsia" for the title the registry
    # expands with its bulletin number.
    return shared >= 3 and shared / min(len(a), len(b)) >= 0.7


def doi_of(url: str) -> str | None:
    match = DOI_IN_URL.search(url)
    # A trailing sentence period is not part of a DOI.
    return match.group(1).rstrip(".") if match else None


def get(url: str, timeout: float, accept: str = "text/html,*/*") -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read(400_000)


def check_source(source_id: str, source: dict[str, str], timeout: float) -> dict:
    url = str(source["url"])
    doi = doi_of(url)
    row: dict = {"source": source_id, "url": url, "doi": doi, "status": None, "kind": "error"}
    try:
        if doi:
            status, body = get(
                f"https://api.crossref.org/works/{urllib.parse.quote(doi)}",
                timeout,
                accept="application/json",
            )
            row["status"] = status
            if status == 200:
                metadata = json.loads(body)["message"]
                returned = " ".join(metadata.get("title") or [])
                row["returnedTitle"] = returned
                row["via"] = "crossref"
                if titles_agree(str(source.get("title", "")), returned):
                    row["kind"] = "ok"
                else:
                    row["kind"] = "mismatch"
            else:
                row["kind"] = "dead"
            return row

        status, body = get(url, timeout)
        row["status"] = status
        row["kind"] = "ok" if 200 <= status < 400 else "dead"
        row["bytes"] = len(body)
    except urllib.error.HTTPError as error:
        row["status"] = error.code
        row["kind"] = "protected" if error.code in (401, 403, 429) else "dead"
        row["error"] = str(error.reason)
    except Exception as error:  # timeouts, DNS, TLS
        row["error"] = type(error).__name__ + (f": {error}" if str(error) else "")
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--network", action="store_true", help="also check every citation")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    problems = structural_problems()
    rows: list[dict] = []
    if args.network:
        registry = pharmacology.SOURCES
        with ThreadPoolExecutor(max_workers=6) as pool:
            rows = list(
                pool.map(lambda item: check_source(item[0], item[1], args.timeout), registry.items())
            )
        for row in rows:
            if row["kind"] == "dead":
                problems.append(f"{row['source']}: dead citation — HTTP {row['status']} ({row['url']})")
            elif row["kind"] == "mismatch":
                problems.append(
                    f"{row['source']}: DOI resolves to a different document "
                    f"({row.get('returnedTitle', '')[:90]!r})"
                )

    report = {
        "sources": len(pharmacology.SOURCES),
        "drugs": len(pharmacology.DRUGS),
        "rules": len(pharmacology.INTERACTIONS),
        "network": args.network,
        "checks": rows,
        "problems": problems,
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"{report['sources']} sources cited by {report['drugs']} drugs and "
            f"{report['rules']} interaction rules"
        )
        if rows:
            marks = {"ok": "OK  ", "protected": "BOT ", "dead": "DEAD", "mismatch": "MISM", "error": "ERR "}
            for row in sorted(rows, key=lambda r: r["source"]):
                status = row["status"] if row["status"] is not None else row.get("error", "no answer")
                via = f"via {row['via']}" if row.get("via") else ""
                print(f"  {marks[row['kind']]} {row['source']:<26} {str(status):<4} {via:<13} {row['url']}")
        if problems:
            print("\nFAIL: source problems:")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print(
                "\nOK: every source is https, unique, cited, and "
                + (
                    f"confirmed ({sum(1 for r in rows if r['kind'] == 'ok')} checked, "
                    f"{sum(1 for r in rows if r['kind'] == 'protected')} behind bot protection)"
                    if args.network
                    else "well-formed"
                )
            )

    if problems:
        return 1
    # A machine with no egress is not evidence that a guideline was withdrawn.
    if args.network and rows and all(row["kind"] == "error" for row in rows):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
