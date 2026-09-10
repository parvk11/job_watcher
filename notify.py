#!/usr/bin/env python3
"""
Send a push notification for postings in new_jobs.json.

Supported backends (auto-detected from environment variables):
  - ntfy.sh   : set NTFY_TOPIC  (free, no account; install the ntfy app and
                subscribe to that topic). Optional NTFY_SERVER (default
                https://ntfy.sh).
  - Pushover  : set PUSHOVER_TOKEN and PUSHOVER_USER.

No-op (exit 0) if there are no new jobs or no backend is configured.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
NEW_JOBS_PATH = HERE / "new_jobs.json"


def send_ntfy(topic: str, title: str, body: str, click: str | None) -> None:
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    headers = {"Title": title, "Tags": "briefcase"}
    if click:
        headers["Click"] = click
    req = urllib.request.Request(
        f"{server}/{topic}", data=body.encode("utf-8"), headers=headers, method="POST"
    )
    urllib.request.urlopen(req, timeout=20).read()


def send_pushover(token: str, user: str, title: str, body: str, url: str | None) -> None:
    payload = {"token": token, "user": user, "title": title, "message": body}
    if url:
        payload["url"] = url
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request("https://api.pushover.net/1/messages.json", data=data)
    urllib.request.urlopen(req, timeout=20).read()


def main() -> int:
    try:
        jobs = json.loads(NEW_JOBS_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        jobs = []
    if not jobs:
        print("notify: nothing new")
        return 0

    n = len(jobs)
    title = f"{n} new MLE/RE internship{'s' if n != 1 else ''}"
    lines = [f"- {j['company']}: {j['title']} [{j.get('location', '')}]\n  {j['url']}" for j in jobs]
    body = "\n".join(lines)
    first_url = jobs[0]["url"]

    ntfy_topic = os.environ.get("NTFY_TOPIC")
    po_token = os.environ.get("PUSHOVER_TOKEN")
    po_user = os.environ.get("PUSHOVER_USER")

    sent = False
    if ntfy_topic:
        send_ntfy(ntfy_topic, title, body, first_url)
        sent = True
    if po_token and po_user:
        send_pushover(po_token, po_user, title, body, first_url)
        sent = True

    if not sent:
        print("notify: no backend configured (set NTFY_TOPIC or PUSHOVER_*)")
        return 0
    print(f"notify: sent {n} job(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
