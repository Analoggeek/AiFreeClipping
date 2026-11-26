#!/usr/bin/env bash
# AI Clipper Pro — one command to build every offline installer.
#   bash scripts/release-all.sh                 # build installers for THIS machine
#   bash scripts/release-all.sh 1.0.1 --all     # all platforms via GitHub Actions
#   bash scripts/release-all.sh 1.0.1 --all --publish  # also create a GitHub Release
set -euo pipefail

cd "$(dirname "$0")/.."

VERSION="$(node -p "require('./package.json').version")"
MODE="local"
SKIP_BACKEND=0
PUBLISH=0
ARGS=()

for arg in "$@"; do
  case "$arg" in
    --all|--ci) MODE="ci" ;;
    --skip-backend) SKIP_BACKEND=1 ;;
    --publish) PUBLISH=1 ;;
    -h|--help)
      echo "Usage: bash scripts/release-all.sh [version] [--all] [--publish] [--skip-backend]"
      echo "  --all      dispatch the GitHub Actions matrix (Windows x64/arm64, macOS Intel/Apple Silicon, Linux x64)"
      echo "  --publish  create a GitHub Release with all artifacts and SHA256 checksums"
      exit 0 ;;
    *) ARGS+=("$arg") ;;
  esac
done
if [ "${#ARGS[@]}" -gt 0 ]; then VERSION="${ARGS[0]}"; fi

echo "== AI Clipper Pro release v${VERSION} (${MODE}) =="
for tool in node npm python3; do
  command -v "$tool" >/dev/null || { echo "Missing required tool: $tool" >&2; exit 1; }
done

PYTHON="${PYTHON:-python3}"
if [ -x ".venv/bin/python" ]; then PYTHON=".venv/bin/python"; fi

echo "== 1/6 Checks =="
npm run typecheck
if "$PYTHON" -c "import pytest" 2>/dev/null; then
  PYTHONPATH=backend "$PYTHON" -m pytest backend/tests -q
else
  echo "pytest not installed — skipping Python tests"
fi

echo "== 2/6 Icons =="
"$PYTHON" scripts/generate-icons.py

echo "== 3/6 Web bundle =="
npm run build

echo "== 4/6 Local Python engine =="
if [ "$SKIP_BACKEND" -eq 1 ]; then
  "$PYTHON" scripts/package-backend.py --skip-pyinstaller
else
  "$PYTHON" scripts/package-backend.py
fi

if [ "$MODE" = "ci" ]; then
  echo "== 5/6 Dispatching cross-platform GitHub Actions build =="
  command -v gh >/dev/null || { echo "gh CLI required for --all" >&2; exit 1; }
  gh workflow run release.yml -f version="$VERSION"
  echo "Waiting for the workflow to appear…"
  sleep 8
  RUN_ID="$(gh run list --workflow release.yml --branch main --limit 1 --json databaseId --jq '.[0].databaseId')"
  [ -n "$RUN_ID" ] || { echo "Could not find the dispatched run" >&2; exit 1; }
  echo "Run ID: $RUN_ID — watch with: gh run view $RUN_ID"
  gh run watch "$RUN_ID" --exit-status
  rm -rf release
  mkdir -p release release/.download
  gh run download "$RUN_ID" -D release/.download
  # gh run download creates one subfolder per matrix job; GitHub Releases need flat files.
  find release/.download -type f -exec cp -f {} release/ \;
  rm -rf release/.download
else
  echo "== 5/6 Building installers for this host =="
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) npx electron-builder --win --x64 --arm64 --publish never ;;
    Darwin) npx electron-builder --mac --x64 --arm64 --publish never ;;
    Linux) npx electron-builder --linux --x64 --publish never ;;
    *) echo "Unsupported host; use --all to build via GitHub Actions" >&2; exit 1 ;;
  esac
fi

echo "== 6/6 Checksums and manifest =="
mkdir -p release
MANIFEST="release/manifest.json"
node - "$VERSION" "$MODE" "$MANIFEST" <<'NODE'
const fs = require('fs');
const [version, mode, target] = process.argv.slice(2);
const payload = {
  product: 'AI Clipper Pro',
  author: 'analoggeek',
  version,
  builtAt: new Date().toISOString(),
  buildMode: mode,
  installers: fs.existsSync('release') ? fs.readdirSync('release').filter(f => /\.(exe|dmg|AppImage|deb|zip)$/i.test(f)) : [],
  components: ['Electron 33', 'React 18', 'FastAPI', 'yt-dlp', 'FFmpeg', 'faster-whisper', 'YOLOX/YOLO11 + ByteTrack', 'Ollama Gemma', 'ComfyUI SDXL (optional)', 'Piper TTS (optional)'],
};
fs.writeFileSync(target, JSON.stringify(payload, null, 2) + '\n');
NODE
(cd release && find . -maxdepth 2 -type f \( -name '*.exe' -o -name '*.dmg' -o -name '*.AppImage' -o -name '*.deb' -o -name '*.zip' \) -print0 | sort -z | xargs -0 -r sha256sum > SHA256SUMS.txt)

if [ "$PUBLISH" -eq 1 ]; then
  echo "== Publishing GitHub Release =="
  command -v gh >/dev/null || { echo "gh CLI required for --publish" >&2; exit 1; }
  gh release create "v$VERSION" release/* --generate-notes --title "AI Clipper Pro v$VERSION" || \
    gh release upload "v$VERSION" release/* --clobber
fi

echo "Done. Installers and checksums are in ./release"
ls -lh release | head -30
