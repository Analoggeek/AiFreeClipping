#!/usr/bin/env bash
# AI Clipper Pro — one command to build every offline installer.
#   bash scripts/release-all.sh                      # build installers for THIS machine
#   bash scripts/release-all.sh 6.0.2 --all           # build the complete cross-platform matrix (no release)
#   bash scripts/release-all.sh 6.0.2 --all --publish # build and publish all supported installers
set -euo pipefail

cd "$(dirname "$0")/.."

VERSION="$(node -p "require('./package.json').version")"
CURRENT_BRANCH="$(git branch --show-current)"
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
      echo "  --all      dispatch the full GitHub Actions matrix (Windows x64/arm64, macOS Intel/Apple Silicon, Linux x64)"
      echo "  --publish  publish a local host build; combine with --all to publish the full matrix after checks pass"
      exit 0 ;;
    *) ARGS+=("$arg") ;;
  esac
done
if [ "${#ARGS[@]}" -gt 0 ]; then VERSION="${ARGS[0]}"; fi

echo "== AI Clipper Pro release v${VERSION} (${MODE}) =="
if [ "$MODE" = "ci" ]; then
  [ -n "$CURRENT_BRANCH" ] || { echo "Cannot dispatch a release from a detached HEAD" >&2; exit 1; }
  if [ -n "$(git status --porcelain)" ]; then
    echo "Commit the current changes before dispatching; GitHub Actions builds the pushed branch, not this working tree." >&2
    exit 1
  fi
  LOCAL_SHA="$(git rev-parse HEAD)"
  REMOTE_SHA="$(git ls-remote --heads origin "refs/heads/$CURRENT_BRANCH" | awk 'NR == 1 { print $1 }')"
  if [ -z "$REMOTE_SHA" ] || [ "$LOCAL_SHA" != "$REMOTE_SHA" ]; then
    echo "Push $CURRENT_BRANCH at $LOCAL_SHA to origin before dispatching the all-target build." >&2
    exit 1
  fi
fi
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

if [ "$MODE" = "ci" ]; then
  echo "== 4/6 Local Python engine =="
  echo "Skipped — each GitHub Actions matrix job packages its engine bundle."
else
  echo "== 4/6 Local Python engine =="
  if [ "$SKIP_BACKEND" -eq 1 ]; then
    "$PYTHON" scripts/package-backend.py --skip-pyinstaller
  else
    "$PYTHON" scripts/package-backend.py
  fi
fi

if [ "$MODE" = "ci" ]; then
  echo "== 5/6 Dispatching cross-platform GitHub Actions build =="
  command -v gh >/dev/null || { echo "gh CLI required for --all" >&2; exit 1; }
  [ -n "$CURRENT_BRANCH" ] || { echo "Cannot dispatch a release from a detached HEAD" >&2; exit 1; }
  BUILD_ONLY=true
  if [ "$PUBLISH" -eq 1 ]; then BUILD_ONLY=false; fi
  HEAD_SHA="$(git rev-parse HEAD)"
  PREVIOUS_RUN_ID="$(gh run list --workflow release.yml --branch "$CURRENT_BRANCH" --limit 1 --json databaseId --jq '.[0].databaseId')"
  gh workflow run release.yml --ref "$CURRENT_BRANCH" -f version="$VERSION" -f build_only="$BUILD_ONLY"
  echo "Waiting for the new workflow run to appear…"
  RUN_ID=""
  for attempt in {1..30}; do
    RUN_INFO="$(gh run list --workflow release.yml --branch "$CURRENT_BRANCH" --limit 1 --json databaseId,headSha,event --jq '.[0] | [.databaseId, .headSha, .event] | @tsv')"
    IFS=$'\t' read -r CANDIDATE_ID CANDIDATE_SHA CANDIDATE_EVENT <<< "$RUN_INFO"
    if [ -n "$CANDIDATE_ID" ] && [ "$CANDIDATE_ID" != "null" ] \
      && [ "$CANDIDATE_ID" != "$PREVIOUS_RUN_ID" ] \
      && [ "$CANDIDATE_SHA" = "$HEAD_SHA" ] && [ "$CANDIDATE_EVENT" = "workflow_dispatch" ]; then
      RUN_ID="$CANDIDATE_ID"
      break
    fi
    sleep 2
  done
  [ -n "$RUN_ID" ] || { echo "Could not find a new workflow_dispatch run for $HEAD_SHA" >&2; exit 1; }
  echo "Run ID: $RUN_ID — watch with: gh run view $RUN_ID"
  gh run watch "$RUN_ID" --exit-status
  rm -rf release
  mkdir -p release release/.download
  gh run download "$RUN_ID" -D release/.download
  # gh run download creates one subfolder per matrix job; GitHub Releases need flat files.
  find release/.download -type f -exec cp -f {} release/ \;
  rm -rf release/.download
  expected=(
    "AI-Clipper-Pro-${VERSION}-Windows-x64.exe"
    "AI-Clipper-Pro-${VERSION}-Windows-arm64.exe"
    "AI-Clipper-Pro-${VERSION}-macOS-x64.dmg"
    "AI-Clipper-Pro-${VERSION}-macOS-x64.zip"
    "AI-Clipper-Pro-${VERSION}-macOS-arm64.dmg"
    "AI-Clipper-Pro-${VERSION}-macOS-arm64.zip"
    "AI-Clipper-Pro-${VERSION}-Linux-x86_64.AppImage"
    "AI-Clipper-Pro-${VERSION}-Linux-amd64.deb"
  )
  for file in "${expected[@]}"; do
    [ -s "release/$file" ] || { echo "Missing all-target artifact: $file" >&2; exit 1; }
  done
  actual="$(find release -maxdepth 1 -type f \
    \( -name '*.exe' -o -name '*.dmg' -o -name '*.zip' -o -name '*.AppImage' -o -name '*.deb' \) | wc -l | tr -d '[:space:]')"
  [ "$actual" = "${#expected[@]}" ] || { echo "Expected ${#expected[@]} installers, found $actual" >&2; exit 1; }
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
  components: ['Electron 45', 'React 18', 'FastAPI', 'yt-dlp', 'FFmpeg', 'faster-whisper', 'YOLOX/YOLO11 + ByteTrack', 'Ollama Gemma', 'ComfyUI SDXL (optional)', 'Piper TTS (optional)'],
};
fs.writeFileSync(target, JSON.stringify(payload, null, 2) + '\n');
NODE
(cd release && find . -maxdepth 2 -type f \( -name '*.exe' -o -name '*.dmg' -o -name '*.AppImage' -o -name '*.deb' -o -name '*.zip' \) -print0 | sort -z | xargs -0 -r sha256sum > SHA256SUMS.txt)

if [ "$PUBLISH" -eq 1 ]; then
  command -v gh >/dev/null || { echo "gh CLI required for --publish" >&2; exit 1; }
  if [ "$MODE" = "ci" ]; then
    echo "== Verifying the GitHub Actions release =="
    # The all-platform workflow publishes once its matrix build and asset checks pass.
    gh release view "v$VERSION" --json tagName,url
  else
    echo "== Publishing GitHub Release =="
    gh release create "v$VERSION" release/* --target "$(git rev-parse HEAD)" --generate-notes --title "AI Clipper Pro v$VERSION" || \
      gh release upload "v$VERSION" release/* --clobber
  fi
fi

echo "Done. Installers and checksums are in ./release"
ls -lh release | head -30
