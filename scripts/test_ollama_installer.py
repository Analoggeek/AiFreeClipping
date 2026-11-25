"""Actual OS installation acceptance on disposable, explicitly approved CI runners.

Only CI supplies unattended Inno flags; the application's installer remains the
normal interactive OS flow after its explicit confirmation dialog. This script
is NOT evidence that a human approved a physical desktop permission dialog.
"""

import json
import os
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from clipos.core import ollama_install

    report = {
        "os": platform.system(),
        "architecture": platform.machine(),
        "interactive_permission_dialog": "not exercised by headless CI",
    }
    before = ollama_install.find_binary()
    report["already_installed"] = str(before) if before else None
    original = ollama_install.subprocess.Popen
    launched = []

    def execute(args, *positional, **kwargs):
        if isinstance(args, list) and args and Path(args[0]).name == "OllamaSetup.exe":
            if os.environ.get("GITHUB_ACTIONS") != "true":
                raise RuntimeError(
                    "Headless Windows installer flags are restricted to disposable GitHub CI"
                )
            launched.append("Authenticode + official SHA256 verified Windows installer")
            args = [
                *args,
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/CURRENTUSER",
                "/NORESTART",
            ]
        return original(args, *positional, **kwargs)

    ollama_install.subprocess.Popen = execute
    try:
        report["api"] = ollama_install.install(consent=True)
        report["binary_after"] = str(ollama_install.find_binary())
        report["windows_installer_executed"] = bool(launched)
        report["fresh_install_verified"] = before is None and bool(
            ollama_install.find_binary()
        )
        if not report["binary_after"]:
            raise RuntimeError("No installed executable after lifecycle completion")
        report["status"] = "ok"
    except Exception as exc:
        report["status"] = "error"
        report["error"] = str(exc)
    finally:
        ollama_install.subprocess.Popen = original
        Path("ollama-install-acceptance.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
