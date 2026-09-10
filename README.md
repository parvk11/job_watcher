# intern-watcher

Polls Greenhouse / Lever / Ashby job boards for a list of AI companies and
alerts on **newly opened MLE / Research-Engineer internships**.

## Files

| File | Purpose |
|---|---|
| `companies.json` | Companies + their ATS board slugs (edit to add/remove) |
| `check_jobs.py` | Fetch, filter to intern + ML/AI titles, diff vs `state.json` |
| `notify.py` | Push `new_jobs.json` to ntfy.sh or Pushover |
| `state.json` | Every matching posting ever seen (committed, so it persists) |
| `new_jobs.json` | Postings first seen on the most recent run |

## Run locally

```bash
python3 check_jobs.py        # writes state.json + new_jobs.json, prints summary
NTFY_TOPIC=my-secret-topic python3 notify.py
```

Nothing to install — standard library only, Python 3.10+.

## Filtering

- **Internship**: title matches `intern(ship)` and not `internal`/`international`.
- **Role**: title matches ML/AI/research/agent/engineer keywords
  (`TITLE_POS_RE` in `check_jobs.py`) and not a non-IC keyword like
  recruiter / PM / hardware / marketing (`TITLE_NEG_RE`).
- Keyword matching is **title-only** on purpose — descriptions mention "AI"
  everywhere.

Tune the two regexes in `check_jobs.py` to taste.

## Scheduled cloud agent

A Claude Code routine runs `check_jobs.py` then `notify.py` on a cron schedule,
and commits the updated `state.json` back to this repo so dedup survives across
runs. See `routine_prompt.md` for the exact agent prompt.

## Adding companies

Add `{ "name": ..., "ats": "greenhouse|lever|ashby", "slug": ... }` to
`companies.json`. Find the slug from the company's job board URL, e.g.
`job-boards.greenhouse.io/<slug>`, `jobs.lever.co/<slug>`,
`jobs.ashbyhq.com/<slug>`.

Custom boards not on these three ATSes (DeepMind, Meta, Mistral, Hugging Face)
are not supported yet — see `_unresolved` in `companies.json`.
