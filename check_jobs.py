#!/usr/bin/env python3
"""
Intern-role watcher for MLE / Research Engineer internships.

Polls Greenhouse / Lever / Ashby public job boards for a configured list of
companies, keeps only postings that look like internships AND match ML/AI
keywords, and diffs the result against a saved state file so that each run
reports only *newly seen* postings.

Outputs:
  - state.json      : {job_key: {first_seen, title, company, url}}  (persisted)
  - new_jobs.json   : list of postings first seen on THIS run          (overwritten)
  - stdout          : human-readable summary

Exit code 0 always (so a scheduler doesn't treat "no new jobs" as failure).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import urllib.request
from pathlib import Path
from urllib.error import HTTPError, URLError

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "companies.json"
STATE_PATH = HERE / "state.json"
NEW_JOBS_PATH = HERE / "new_jobs.json"

USER_AGENT = "intern-watcher/1.0 (+personal job alert script)"
TIMEOUT = 30

# --- matching rules -------------------------------------------------------

# Internship, but not "internal" / "international".
INTERN_RE = re.compile(r"\bintern(ship)?s?\b", re.I)
INTERN_NEG_RE = re.compile(r"\b(internal|international|internally)\b", re.I)

# Keyword match is done on the TITLE ONLY. Job-description bodies at AI labs
# mention "AI" / "ML" in boilerplate on nearly every posting, so matching the
# body produces mostly false positives.
TITLE_POS_RE = re.compile(
    r"\b("
    r"machine learning|ml|mle|ai|artificial intelligence|deep learning|"
    r"llm|llms|nlp|natural language|computer vision|cv|perception|"
    r"reinforcement learning|rl|rlhf|research|applied scien|"
    r"foundation model|robot learning|generative|multimodal|diffusion|"
    r"agent|agents|agentic|data scien|software engineer\w*|"
    r"ml engineer\w*|engineer\w*|scientist"
    r")\b",
    re.I,
)

# Roles that are internships *at* these companies but not MLE/RE-type IC roles.
TITLE_NEG_RE = re.compile(
    r"\b("
    r"recruit\w*|sourcer|coordinator|specialist|"
    r"program manager|product manager|product management|tpm|"
    r"marketing|sales|account|business development|bd|gtm|revenue|"
    r"operations|people|hr|talent|design(er)?|ux|ui|content|"
    r"electrical|firmware|hardware|mechanical|power systems|thermal|"
    r"optical|manufacturing|supply chain|technician|"
    r"accounting|finance|legal|communications|policy|comms|"
    r"video|artist|animation|social media|community"
    r")\b",
    re.I,
)


def looks_like_intern(title: str, body: str) -> bool:
    hay_title = title or ""
    if INTERN_RE.search(hay_title) and not INTERN_NEG_RE.search(hay_title):
        return True
    # Some boards bury "Internship" in an employment-type field folded into body.
    if INTERN_RE.search(body or "") and not INTERN_NEG_RE.search(title or ""):
        # require the word intern to be reasonably prominent, not a stray mention
        return len(re.findall(INTERN_RE, body or "")) >= 1 and (
            "intern" in hay_title.lower() or "student" in (body or "").lower()[:2000]
        )
    return False


def matches_keywords(title: str, body: str) -> bool:
    if TITLE_NEG_RE.search(title or ""):
        return False
    return bool(TITLE_POS_RE.search(title or ""))


# --- fetching -----------------------------------------------------------------

def _get(url: str) -> dict | list:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_greenhouse(slug: str) -> list[dict]:
    data = _get(
        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    )
    out = []
    for j in data.get("jobs", []):
        out.append(
            {
                "id": str(j.get("id")),
                "title": j.get("title", ""),
                "location": (j.get("location") or {}).get("name", ""),
                "url": j.get("absolute_url", ""),
                "body": _strip_html(j.get("content", "") or ""),
                "updated": j.get("updated_at", ""),
            }
        )
    return out


def fetch_lever(slug: str) -> list[dict]:
    data = _get(f"https://api.lever.co/v0/postings/{slug}?mode=json&limit=500")
    out = []
    for j in data if isinstance(data, list) else []:
        cats = j.get("categories", {}) or {}
        out.append(
            {
                "id": str(j.get("id")),
                "title": j.get("text", ""),
                "location": cats.get("location", "") or "",
                "url": j.get("hostedUrl", "") or j.get("applyUrl", ""),
                "body": _strip_html(j.get("descriptionPlain", "") or j.get("description", "") or "")
                + " "
                + str(cats.get("commitment", "")),
                "updated": str(j.get("createdAt", "")),
            }
        )
    return out


def fetch_ashby(slug: str) -> list[dict]:
    data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=false")
    out = []
    for j in data.get("jobs", []):
        out.append(
            {
                "id": str(j.get("id")),
                "title": j.get("title", ""),
                "location": j.get("location", "")
                or (j.get("address", {}) or {}).get("postalAddress", {}).get("addressLocality", ""),
                "url": j.get("jobUrl", "") or j.get("applyUrl", ""),
                "body": (j.get("descriptionPlain", "") or "")
                + " "
                + str(j.get("employmentType", "")),
                "updated": j.get("publishedAt", ""),
            }
        )
    return out


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
}


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&[a-z]+;", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# --- main -------------------------------------------------------------------

def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def main() -> int:
    cfg = load_json(CONFIG_PATH, {})
    companies = cfg.get("companies", [])
    state: dict = load_json(STATE_PATH, {})

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    all_matches: list[dict] = []
    errors: list[str] = []

    for c in companies:
        name, ats, slug = c["name"], c["ats"], c["slug"]
        fetcher = FETCHERS.get(ats)
        if not fetcher:
            errors.append(f"{name}: unknown ats {ats}")
            continue
        try:
            postings = fetcher(slug)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as e:
            errors.append(f"{name} ({ats}/{slug}): {e}")
            continue

        for p in postings:
            title, body = p["title"], p.get("body", "")
            if not looks_like_intern(title, body):
                continue
            if not matches_keywords(title, body):
                continue
            key = f"{ats}:{slug}:{p['id']}"
            all_matches.append(
                {
                    "key": key,
                    "company": name,
                    "title": title,
                    "location": p.get("location", ""),
                    "url": p["url"],
                }
            )

    # Safety: if a large fraction of boards failed, this run has no reliable
    # signal. Don't touch state (pruning would wipe it and cause a re-alert
    # storm next run) and exit non-zero so the scheduler surfaces it.
    if companies and len(errors) >= max(3, len(companies) // 2):
        NEW_JOBS_PATH.write_text("[]")
        (HERE / "new_jobs.md").write_text("")
        print(f"[{now}] ABORT: {len(errors)}/{len(companies)} board fetches failed")
        for e in errors:
            print(f"    ! {e}")
        return 1

    # diff against state
    new_jobs = []
    for m in all_matches:
        if m["key"] not in state:
            state[m["key"]] = {
                "first_seen": now,
                "company": m["company"],
                "title": m["title"],
                "url": m["url"],
            }
            new_jobs.append(m)

    # prune state entries that are no longer live (posting closed) so a
    # re-opened role later counts as new again
    live_keys = {m["key"] for m in all_matches}
    for k in list(state):
        if k not in live_keys:
            del state[k]

    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))
    NEW_JOBS_PATH.write_text(json.dumps(new_jobs, indent=2))

    # markdown block for notifications / GitHub issues
    if new_jobs:
        md = [f"**{len(new_jobs)} new MLE/RE internship(s)**", ""]
        for m in new_jobs:
            loc = f" — {m['location']}" if m.get("location") else ""
            md.append(f"- **{m['company']}**: {m['title']}{loc}")
            md.append(f"  {m['url']}")
        (HERE / "new_jobs.md").write_text("\n".join(md) + "\n")
    else:
        (HERE / "new_jobs.md").write_text("")

    # summary
    print(f"[{now}] checked {len(companies)} companies")
    print(f"  matching intern roles currently live: {len(all_matches)}")
    print(f"  NEW since last run: {len(new_jobs)}")
    for m in new_jobs:
        print(f"    + {m['company']}: {m['title']}  [{m['location']}]")
        print(f"      {m['url']}")
    if errors:
        print("  errors:")
        for e in errors:
            print(f"    ! {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
