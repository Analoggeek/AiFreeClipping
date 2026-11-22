"""Opt-in release checks. Never modifies project data or executes remote code."""
import platform
import re
import requests

RELEASE_API = "https://api.github.com/repos/Analoggeek/AiFreeClipping/releases/latest"


def version_tuple(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value or "")
    if not match:
        raise ValueError("Unsupported release version")
    return tuple(map(int, match.groups()))


def check_update(current):
    response = requests.get(RELEASE_API, timeout=20, headers={"Accept": "application/vnd.github+json"})
    response.raise_for_status()
    release = response.json()
    if release.get("draft") or release.get("prerelease"):
        return None
    if version_tuple(release.get("tag_name")) <= version_tuple(current):
        return None
    system, machine = platform.system(), platform.machine().lower()
    assets = release.get("assets", [])
    for asset in assets:
        name = asset.get("name", "").lower()
        match = (system == "Windows" and name.endswith("setup.exe")) or (
            system == "Darwin" and name.endswith(".dmg") and
            (("intel" in name) == (machine in ("x86_64", "amd64")))) or (
            system == "Linux" and name.endswith(".deb") and machine in ("x86_64", "amd64"))
        url = asset.get("browser_download_url", "")
        if match and url.startswith("https://github.com/Analoggeek/AiFreeClipping/releases/download/"):
            return {"version": release["tag_name"], "url": url, "name": asset["name"]}
    raise ValueError("Release found, but no compatible installer is published for this device")
