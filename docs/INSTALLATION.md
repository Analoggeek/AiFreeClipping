# Installation & offline setup

## Installers

Installers are produced by `scripts/release-all.sh` / `release.yml` and contain:

- the React UI + Electron shell,
- a PyInstaller bundle of the Python engine (Python runtime + FastAPI + yt-dlp + AI client code),
- an FFmpeg binary bundled next to the engine,
- platform icons and assets.

| OS / arch | Artifact | Notes |
|---|---|---|
| Windows x64 / ARM64 | `.exe` (NSIS) | Per-user install by default; SmartScreen warning until signed |
| macOS Intel (x64) | `.dmg` | Right-click → Open if unsigned |
| macOS Apple Silicon (arm64) | `.dmg` | Native ARM build, no Rosetta needed |
| Linux x64 | `.AppImage`, `.deb` | AppImage needs `chmod +x`; deb installs via `sudo apt install ./…` |

Data lives in `~/.AiFreeClipping/` (`%USERPROFILE%\.AiFreeClipping` on Windows):

```
downloads/  projects/  clips/  assets/  exports/  cache/  models/  db.sqlite3
```

Set `AIFREECLIP_HOME` to relocate this folder.

## First-run model pack (online once)

Open **Local Models** in the app and install, in order:

1. **Whisper Small** — captions + transcript-driven scoring. Use Medium/Large v3 for multilingual accuracy.
2. **Gemma 2 7B** via Ollama — titles/hashtags/reranking. On 8 GB machines choose Gemma 3 4B.
3. **YOLO11 Nano or YOLOX Nano** — player/gameplay activity with ByteTrack.
4. **SDXL checkpoint** (optional) — place `sd_xl_base_1.0.safetensors` in `~/.AiFreeClipping/models/checkpoints`, run ComfyUI on port 8188.
5. **Piper voice** (optional) — offline narration.

Ollama must be installed and running for Gemma. The Model page's install button calls Ollama's `POST /api/pull`; once pulled, no further network access is needed.

## Fully offline machine

1. On a connected machine, run the installer and install all models above.
2. Copy `~/.AiFreeClipping/` (or at least `cache/`, `models/`, `db.sqlite3`) to the offline machine.
3. Install Ollama locally on the offline machine (offline installer package if available) and keep it running.
4. Leave Gemini/Pexels/Pixabay/YouTube fields empty in Settings; all other features work offline.

## Source install

```bash
npm install
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
# Optional Torch/YOLO vision models for development:
pip install -r backend/requirements-vision.txt
# Optional YouTube publishing:
pip install -r backend/requirements-youtube.txt
python scripts/generate-icons.py
npm start                            # browser studio (no Electron required)
npm run dev:app                      # Electron window; auto-falls back to browser studio
```

Environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `AIFREECLIP_HOME` | `~/.AiFreeClipping` | Data location |
| `AIFREECLIP_PORT` | random (Electron) / 8787 (CLI) | Engine port |
| `AIFREECLIP_TOKEN` | generated | Override API token |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `gemma2:7b` | Local LLM |
| `WHISPER_MODEL` | `small` | Whisper size |
| `WHISPER_DEVICE`, `WHISPER_COMPUTE` | auto | `cpu`/`cuda`/`mps`, `int8`/`float16` |
| `COMFYUI_URL` | `http://127.0.0.1:8188` | Local image generation |
| `FFMPEG_BINARY`, `FFPROBE_BINARY` | auto | Custom binaries |
| `FORCE_SOFTWARE_ENCODER=1` | unset | Use libx264 even on GPU machines |
| `DISABLE_CLOUD_FEATURES=1` | unset | Force local-only image provider |

## Publishing setup (optional)

Create a Google Cloud project, enable **YouTube Data API v3**, create an **OAuth client (Desktop app)** credential, download `client_secret.json` into `~/.AiFreeClipping/`, then click **Connect channel** in the Publish page. New/unaudited OAuth apps upload as private videos; Google reviews can lift that restriction.
