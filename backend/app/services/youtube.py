"""Optional YouTube Data API v3 publishing with user-owned OAuth credentials."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from ..config import HOME, env
from ..db import db

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN = HOME / "youtube_token.json"


def _secret_path() -> Path:
    configured = db.get_setting("youtube_client_secret", env("YOUTUBE_CLIENT_SECRET"))
    return Path(configured).expanduser() if configured else HOME / "client_secret.json"


def available() -> bool:
    try:
        import googleapiclient.discovery  # type: ignore
        import google_auth_oauthlib.flow  # type: ignore

        return True
    except ImportError:
        return False


def status() -> dict[str, Any]:
    return {
        "available": available(),
        "authorized": TOKEN.exists(),
        "clientSecretConfigured": _secret_path().exists(),
        "clientSecretPath": str(_secret_path()),
        "note": "Unaudited OAuth apps upload as private until Google reviews the app.",
    }


async def authorize() -> dict[str, Any]:
    if not available():
        raise RuntimeError("Install youtube extras: pip install -r backend/requirements-youtube.txt")
    if not _secret_path().exists():
        raise RuntimeError(f"Place your OAuth client_secret.json at {_secret_path()} or set it in Settings.")
    from google.auth.transport.requests import Request  # type: ignore
    from google.oauth2.credentials import Credentials  # type: ignore
    from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore

    def work():
        creds = None
        if TOKEN.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(_secret_path()), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
        return {"authorized": True}

    return await asyncio.to_thread(work)


async def upload(
    path: str,
    title: str,
    description: str,
    tags: list[str],
    privacy: str,
    publish_at: str | None = None,
    made_for_kids: bool = False,
) -> dict[str, Any]:
    if not status()["authorized"]:
        raise RuntimeError("Connect your YouTube channel from the Publish page first.")
    from google.oauth2.credentials import Credentials  # type: ignore
    from googleapiclient.discovery import build  # type: ignore
    from googleapiclient.http import MediaFileUpload  # type: ignore

    def work():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
        youtube = build("youtube", "v3", credentials=creds)
        body: dict[str, Any] = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags[:20],
                "categoryId": "28",
            },
            "status": {
                "privacyStatus": "private" if publish_at else privacy,
                "selfDeclaredMadeForKids": made_for_kids,
            },
        }
        if publish_at:
            body["status"]["publishAt"] = publish_at
        media = MediaFileUpload(path, mimetype="video/mp4", chunksize=-1, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        retries = 0
        while response is None:
            try:
                _chunk, response = request.next_chunk()
            except Exception:
                retries += 1
                if retries > 5:
                    raise
                import time

                time.sleep(2**retries)
        return {"videoId": response.get("id"), "url": f"https://youtu.be/{response.get('id')}", "title": title}

    return await asyncio.to_thread(work)
