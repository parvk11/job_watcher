# job_watcher

Watches Greenhouse / Lever / Ashby job boards for AI companies and alerts when
a **MLE / Research-Engineer internship** opens.

Runs as a **GitHub Actions** cron job (every 2 hours) — nothing needs to stay on.

## How it works

| File | Purpose |
|---|---|
| `companies.json` | Companies + their ATS board slugs (edit to add/remove) |
| `check_jobs.py` | Fetch → filter to intern + ML/AI titles → diff vs `state.json` |
| `notify.py` | Optional push to ntfy.sh / Pushover |
| `.github/workflows/watch.yml` | The scheduled runner |
| `state.json` | Every matching posting ever seen (committed by CI, so dedup persists) |

Each run:
1. Polls every board, keeps intern roles whose **title** matches ML/AI/research/
   agent keywords and isn't a recruiter/PM/hardware/etc. role.
2. Diffs against `state.json`; anything new goes to `new_jobs.json` / `new_jobs.md`.
3. If there are new roles → opens a GitHub issue assigned to you (→ GitHub
   mobile push + email) and, if secrets are set, fires an ntfy/Pushover push.
4. Commits the updated `state.json` back to the repo.

If more than half the boards fail to fetch, the run aborts without touching
state (so a transient outage can't trigger a re-alert storm) and the Action
shows as failed.

## Notifications

- **Zero setup:** GitHub issues. Install the GitHub mobile app and enable
  notifications, or watch the repo — you'll get pinged on assignment.
- **Real push (optional):** add a repo secret `NTFY_TOPIC` (Settings → Secrets
  and variables → Actions). Install the [ntfy](https://ntfy.sh) app, subscribe
  to that topic. Or set `PUSHOVER_TOKEN` + `PUSHOVER_USER`.

## Run it manually

Actions tab → **intern-watch** → **Run workflow**. Or locally:

```bash
python3 check_jobs.py
```

Standard library only, Python 3.10+.

## Tuning

Edit `TITLE_POS_RE` / `TITLE_NEG_RE` in `check_jobs.py`. Keyword matching is
title-only on purpose — job descriptions say "AI" everywhere.

## Adding companies

Add `{ "name": ..., "ats": "greenhouse|lever|ashby", "slug": ... }` to
`companies.json`. Slug comes from the board URL
(`job-boards.greenhouse.io/<slug>`, `jobs.lever.co/<slug>`,
`jobs.ashbyhq.com/<slug>`). Custom boards (DeepMind, Meta, Mistral, Hugging
Face) aren't supported — see `_unresolved` in `companies.json`.
