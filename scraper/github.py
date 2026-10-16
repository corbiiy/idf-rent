"""Read and write data/listings.json in the GitHub repository through the REST API.

Uses the Git Data API (blob -> tree -> commit -> ref) so there is no size limit worry
and no local git checkout needed. Requires a fine-grained token with Contents: read/write.
"""
from __future__ import annotations

import base64
import logging

import requests

log = logging.getLogger(__name__)

API = "https://api.github.com"


class GitHubFile:
    def __init__(self, token: str, repo: str, branch: str, path: str):
        self.repo, self.branch, self.path = repo, branch, path
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "idf-rent worker",
        })

    def _get(self, url: str, **kw) -> dict:
        r = self.s.get(url, timeout=60, **kw)
        r.raise_for_status()
        return r.json()

    def _post(self, url: str, payload: dict) -> dict:
        r = self.s.post(url, json=payload, timeout=120)
        r.raise_for_status()
        return r.json()

    def download(self) -> bytes | None:
        """Current content of the file on the branch, or None if it does not exist."""
        r = self.s.get(f"{API}/repos/{self.repo}/contents/{self.path}", params={"ref": self.branch},
                       headers={"Accept": "application/vnd.github.raw+json"}, timeout=120)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.content

    def head(self) -> str:
        return self._get(f"{API}/repos/{self.repo}/git/ref/heads/{self.branch}")["object"]["sha"]

    def upload(self, content: bytes, message: str) -> str:
        """Commit `content` at self.path on top of the branch head. Returns the new commit sha.
        Raises requests.HTTPError (422) if the branch moved between head() and the ref update."""
        base = self.repo
        head = self.head()
        base_tree = self._get(f"{API}/repos/{base}/git/commits/{head}")["tree"]["sha"]
        blob = self._post(f"{API}/repos/{base}/git/blobs",
                          {"content": base64.b64encode(content).decode(), "encoding": "base64"})["sha"]
        tree = self._post(f"{API}/repos/{base}/git/trees",
                          {"base_tree": base_tree, "tree": [{"path": self.path, "mode": "100644", "type": "blob", "sha": blob}]})["sha"]
        commit = self._post(f"{API}/repos/{base}/git/commits",
                            {"message": message, "tree": tree, "parents": [head]})["sha"]
        r = self.s.patch(f"{API}/repos/{base}/git/refs/heads/{self.branch}", json={"sha": commit, "force": False}, timeout=60)
        r.raise_for_status()
        return commit
