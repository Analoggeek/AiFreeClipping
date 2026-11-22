#!/usr/bin/env python3
"""Post the build diagnostics to the pull request or an issue.

The CI logs and the artifacts live on a storage host that is not always
reachable, so a build failure writes its explanation here instead.  The
comment shows up in the repository and can be read from anywhere.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def post_comment(body: str) -> bool:
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("[diag] no GITHUB_TOKEN or GITHUB_REPOSITORY; skipping")
        return False

    # Prefer commenting on the run itself; fall back to an issue.
    run_id = os.environ.get("GITHUB_RUN_ID")
    endpoint = None
    if run_id:
        endpoint = (
            f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs"
        )
    if not endpoint:
        return False

    request = urllib.request.Request(
        endpoint, headers={"Authorization": f"Bearer {token}",
                           "Accept": "application/vnd.github+json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.load(response)
    except (urllib.error.URLError, OSError) as exc:
        print(f"[diag] could not reach the API: {exc}")
        return False

    jobs = data.get("jobs", [])
    failed = [j for j in jobs if j.get("conclusion") == "failure"]
    if not failed:
        return False

    for job in failed:
        url = (f"https://api.github.com/repos/{repo}/issues/"
               f"{job['id']}/comments")
        payload = json.dumps({"body": body}).encode("utf-8")
        request = urllib.request.Request(
            url, data=payload, method="POST",
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/vnd.github+json",
                     "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                response.read()
            print(f"[diag] posted the diagnostics for job {job['id']}")
            return True
        except (urllib.error.URLError, OSError) as exc:
            print(f"[diag] could not post the comment: {exc}")
    return False


def collect() -> str:
    parts: list[str] = ["### CLIPOS build failure\n"]
    build = ROOT / "build"
    if build.is_dir():
        listing = sorted(p.name for p in build.iterdir())
        parts.append(f"The build directory contains: {', '.join(listing)}\n")
    for name in ("build-error.log", "pyinstaller.log"):
        path = build / name
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            tail = text[-3000:]
            parts.append(f"#### {name}\n\n```\n{tail}\n```\n")
    for pattern in ("*.iss", "*.nsi"):
        for path in build.glob(pattern):
            parts.append(f"#### {path.name}\n\n```\n"
                         f"{path.read_text(encoding='utf-8', errors='replace')[:3000]}\n```\n")
    return "\n".join(parts)


def main() -> int:
    body = collect()
    print(body[:2000])
    if post_comment(body):
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
