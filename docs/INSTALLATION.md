# Installation & offline setup

## Installers and release status

Installers are built by `scripts/release-all.sh` and `.github/workflows/release.yml`. The all-target matrix produces:

- **Windows:** NSIS x64 and ARM64 installers
- **macOS:** Intel and Apple Silicon, each as DMG and ZIP
- **Linux x64:** AppImage and Debian package

Each installer contains the React UI, Electron shell, PyInstaller-bundled Python engine, FFmpeg, platform icons and app assets. The Windows ARM64 installer uses the x64 Python engine under Windows' x64 compatibility layer because the currently supported Python dependency set lacks a complete `win_arm64` wheel set. macOS DMGs are read-only and each DMG/ZIP is checked for a runnable, architecture-matched app bundle.

**v6.0.0 is a release candidate under preparation, not a published release.** The latest-release link continues to point to the most recently published installer set until all five platform build jobs are verified and a v6.0.0 GitHub Release is created.

If Finder reports that a disk image is unreadable, verify its checksum against the release's `SHA256SUMS.txt`; if it still will not mount, use the matching macOS ZIP and move `AI Clipper Pro.app` to Applications.

## Data directory

Data lives in `~/.AiFreeClipping/` (`%USERPROFILE%\.AiFreeClipping` on Windows):

```text
downloads/  projects/  clips/  assets/  exports/  cache/  models/  db.sqlite3
```

Set `AIFREECLIP_HOME` to relocate this folder.

## First-run hardware-matched model setup (online once)

On first launch, the app detects system RAM and GPU memory, then offers or automatically starts the recommended offline set:

1. **Whisper Small or Medium** — local transcript features for clip scoring and review context. It is not used to produce subtitles or burned-in text. Medium is selected from 16 GB RAM for stronger multilingual accuracy; Small keeps low-memory systems lighter.
2. **Gemma 3 4B, Gemma 2 7B or Gemma 3 12B** — local clip-title refinement and reranking, sized to available RAM and accelerator. The app downloads and starts Ollama when needed.
3. **YOLOX Nano ONNX** — a compact detector for player/gameplay tracking with ByteTrack.

Open **Local Models** to review recommendations or install models again. SDXL/ComfyUI and Piper remain optional; an existing SDXL checkpoint can be selected from its current folder.

The initial model download needs internet access. Once models are installed, analysis, clipping, editing and rendering can work offline. Optional cloud image generation and stock-media services still need their respective keys and network access. YouTube is supported as a source-download site through yt-dlp; the app has no YouTube channel-upload integration.

## Fully offline machine

1. On a connected machine, run the installer and install the models you need.
2. Copy `~/.AiFreeClipping/` (or at least `cache/`, `models/` and `db.sqlite3`) to the offline machine.
3. Install Ollama locally on the offline machine (offline installer package if available) and keep it running if using Gemma.
4. Leave cloud-image and stock-media keys empty in Settings. YouTube source downloads require an internet connection; imported local media works offline.

## Source install

```bash
npm install
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
# Optional Torch/YOLO vision models for development:
pip install -r backend/requirements-vision.txt
python scripts/generate-icons.py
npm start                            # browser studio (no Electron required)
npm run dev:app                      # Electron window; auto-falls back to browser studio
```

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `AIFREECLIP_HOME` | `~/.AiFreeClipping` | Data location |
| `AIFREECLIP_PORT` | random (Electron) / 8787 (CLI) | Engine port |
| `AIFREECLIP_TOKEN` | generated | Override API token |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `gemma2:7b` | Local LLM |
| `WHISPER_MODEL` | `small` | Whisper model used by analysis |
| `WHISPER_DEVICE`, `WHISPER_COMPUTE` | auto | `cpu`/`cuda`/`mps`, `int8`/`float16` |
| `COMFYUI_URL` | `http://127.0.0.1:8188` | Local image generation |
| `FFMPEG_BINARY`, `FFPROBE_BINARY` | auto | Custom binaries |
| `FORCE_SOFTWARE_ENCODER=1` | unset | Use libx264 even on GPU machines |
| `DISABLE_CLOUD_FEATURES=1` | unset | Force local-only image provider |
