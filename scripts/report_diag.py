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

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    }

    # Comment on the pull request the run belongs to, when there is one.
    number = os.environ.get("PR_NUMBER", "").strip()
    if not number:
        number = _pull_request_number(repo, headers)
    if number:
        url = f"https://api.github.com/repos/{repo}/issues/{number}/comments"
        if _post(url, headers, {"body": body}):
            print(f"[diag] posted the diagnostics on #{number}")
            return True

    # Otherwise open an issue, which is visible to everyone with access.
    url = f"https://api.github.com/repos/{repo}/issues"
    title = os.environ.get("DIAG_TITLE", "CLIPOS build failure")
    if _post(url, headers, {"title": title, "body": body}):
        print("[diag] opened an issue with the diagnostics")
        return True
    return False


def _pull_request_number(repo: str, headers: dict) -> str:
    """The number of the pull request the current run belongs to."""
    run_id = os.environ.get("GITHUB_RUN_ID")
    if not run_id:
        return ""
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=60
        ) as response:
            data = json.load(response)
    except (urllib.error.URLError, OSError):
        return ""
    for pull in data.get("pull_requests", []) or []:
        number = pull.get("number")
        if number:
            return str(number)
    return ""


def _post(url: str, headers: dict, payload: dict) -> bool:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response.read()
        return True
    except (urllib.error.URLError, OSError) as exc:
        print(f"[diag] could not post to {url}: {exc}")
        return False


def collect() -> str:
    parts: list[str] = ["### CLIPOS build failure\n"]
    build = ROOT / "build"
    if build.is_dir():
        listing = sorted(p.name for p in build.iterdir())
        parts.append(f"The build directory contains: {', '.join(listing)}\n")
    for name in ("build-error.log", "pyinstaller.log", "step-failure.txt",
                 "pip-install.log"):
        path = build / name
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            # The build error log holds one section per failed back-end.
            # Keeping only the tail threw the first one away, which is
            # where the real reason usually is, so the whole thing is kept
            # when it fits and trimmed from the middle when it does not.
            parts.append(f"#### {name}\n\n```\n{_trim(text)}\n```\n")
    for pattern in ("*.iss", "*.nsi"):
        for path in build.glob(pattern):
            parts.append(f"#### {path.name}\n\n```\n"
                         f"{path.read_text(encoding='utf-8', errors='replace')[:3000]}\n```\n")
    return "\n".join(parts)


def _trim(text: str, limit: int = 24000) -> str:
    """Keep a log readable without losing the beginning of it.

    A failure report that starts halfway through the log is worse than
    useless, so the middle is dropped rather than the start.
    """
    if len(text) <= limit:
        return text
    head = limit // 2
    tail = limit - head
    return (
        text[:head]
        + f"\n\n... {len(text) - limit} characters in the middle were left out ...\n\n"
        + text[-tail:]
    )


def main() -> int:
    body = collect()
    print(body[:2000])

    # The commit status is the broadest channel available: it works with the
    # least permissions and the text shows up on the commit itself.
    if post_status(body):
        print("[diag] posted the diagnostics as a commit status")
        return 0
    if post_comment(body):
        print("[diag] posted the diagnostics as a comment")
        return 0

    # Nothing worked.  The diagnostics are still worth keeping, so they are
    # written next to the build where the artifact step will pick them up.
    try:
        (ROOT / "build" / "failure-report.md").write_text(body, encoding="utf-8")
        print("[diag] wrote build/failure-report.md")
    except OSError:
        pass
    print("[diag] WARNING: could not report the failure through the API")
    return 0


def post_status(body: str) -> bool:
    """Attach the diagnostics to the commit as a status."""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    sha = os.environ.get("GITHUB_SHA")
    if not token or not repo or not sha:
        return False

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    }
    url = f"https://api.github.com/repos/{repo}/statuses/{sha}"
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    payload = {
        "state": "failure",
        "context": "clipos-build",
        "description": "CLIPOS build failed — see the run log",
        "target_url": f"https://github.com/{repo}/actions/runs/{run_id}",
    }
    return _post(url, headers, payload)


if __name__ == "__main__":
    raise SystemExit(main())
