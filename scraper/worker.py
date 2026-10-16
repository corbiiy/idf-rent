"""Long-running crawler for Railway (or any always-on host).

Every CRAWL_INTERVAL seconds: crawl, post new matches to Discord, and at most every
PUSH_INTERVAL seconds commit data/listings.json to the `data` branch of the GitHub
repository (the site on GitHub Pages reads that file straight from
raw.githubusercontent.com). Data goes to its own branch so that the commits never
trigger a Railway redeploy, which watches `main`.

Environment:
  GITHUB_TOKEN         fine-grained token, Contents: read and write on the repo (required unless DRY_RUN)
  GITHUB_REPO          owner/name            (default corbiiy/idf-rent)
  GITHUB_BRANCH        branch for data commits (default data; created from main if missing)
  DISCORD_WEBHOOK_URL  webhook               (optional; matches are logged otherwise)
  CRAWL_INTERVAL       seconds between crawls (default 300)
  PUSH_INTERVAL        min seconds between GitHub commits (default 900)
  CRAWL_PAGES          list pages per department and source (default 1)
  CYCLE_BUDGET         seconds after which no further source is started in a cycle (default 240)
  DEPARTMENTS          comma list            (default all 8 IDF)
  SOURCES              comma list            (default all)
  DRY_RUN              "1": never push to GitHub
  ONCE                 "1": run a single cycle and exit (used for smoke tests)
"""
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone

import requests

from . import store
from .github import GitHubFile
from .http import PoliteSession
from .model import IDF_DEPARTMENTS
from .notify import notify_new
from .run import run_cycle
from .sources import SOURCES

log = logging.getLogger("worker")


def env_list(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    interval = int(os.environ.get("CRAWL_INTERVAL", "300"))
    push_interval = int(os.environ.get("PUSH_INTERVAL", "900"))
    pages = int(os.environ.get("CRAWL_PAGES", "1"))
    budget = float(os.environ.get("CYCLE_BUDGET", "240"))
    departments = env_list("DEPARTMENTS", ",".join(IDF_DEPARTMENTS))
    sources = env_list("SOURCES", ",".join(SOURCES))
    dry_run = os.environ.get("DRY_RUN") == "1"
    once = os.environ.get("ONCE") == "1"
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO", "corbiiy/idf-rent")
    branch = os.environ.get("GITHUB_BRANCH", "data")

    gh = None
    if token:
        gh = GitHubFile(token, repo, branch, "data/listings.json")
    elif not dry_run:
        log.error("GITHUB_TOKEN is not set (set DRY_RUN=1 to run without pushing)")
        return 2

    # Start from the copy in the repository so a redeploy never forgets what was already seen.
    if gh is not None:
        try:
            if not dry_run:
                gh.ensure_branch("main")
            content = gh.download()
            if content:
                store.DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
                store.DATA_FILE.write_bytes(content)
                log.info("synced data/listings.json from %s@%s (%d bytes)", repo, branch, len(content))
        except requests.RequestException as exc:
            log.warning("could not sync from GitHub, using local copy: %s", exc)

    stored = store.load()
    status = store.load_status()
    labels = {s: m.LABEL for s, m in SOURCES.items()}
    session = PoliteSession()
    last_push: float | None = None  # None: push right after the first cycle
    dirty = False

    while True:
        started = time.monotonic()
        try:
            stored, new, status = run_cycle(stored, session, departments, sources, pages=pages,
                                            status=status, budget=budget)
            store.save(stored, status=status)
            dirty = True
            summary = ", ".join(f"{s}={st.get('count', 0)}{'!' if st.get('last_error') else ''}" for s, st in status.items())
            log.info("cycle: %s; new=%d total=%d; next push in %ds", summary, len(new), len(stored),
                     0 if last_push is None else max(0, int(push_interval - (time.monotonic() - last_push))))
            if new:
                notify_new(new, labels)
        except Exception as exc:
            log.exception("cycle failed: %s", exc)

        due = last_push is None or time.monotonic() - last_push >= push_interval
        if dirty and gh is not None and not dry_run and due:
            try:
                stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
                sha = gh.upload(store.DATA_FILE.read_bytes(), f"data: crawl {stamp} (railway)")
                log.info("pushed data/listings.json as %s", sha[:7])
                last_push = time.monotonic()
                dirty = False
            except requests.RequestException as exc:
                detail = ""
                if exc.response is not None:
                    detail = " " + exc.response.text.strip()[:200]
                    if exc.response.status_code in (401, 403, 404):
                        detail += " (check GITHUB_TOKEN: fine-grained token, repository idf-rent, Contents: read and write)"
                log.warning("push failed, will retry next cycle: %s%s", exc, detail)

        if once:
            return 0
        elapsed = time.monotonic() - started
        time.sleep(max(30.0, interval - elapsed))


if __name__ == "__main__":
    sys.exit(main())
