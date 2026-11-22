#!/usr/bin/env bash
# Run CLIPOS headlessly on a bare Linux CI container.
#
# The container has no desktop libraries (libGL / libEGL / libxkbcommon / libdbus),
# so scripts/build_gl_stubs.py generates no-op stubs and we use Qt's "minimal"
# platform plugin, which needs no display server.
#
#   ./scripts/run_headless.sh python -m clipos
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STUBS="$ROOT/.stublibs"
PY="$ROOT/.venv/bin/python"

if [ ! -x "$PY" ]; then
    PY="$(command -v python3)"
fi

if [ ! -d "$STUBS" ] || [ -z "$(ls -A "$STUBS" 2>/dev/null)" ]; then
    echo "[clipos] building headless GL stubs ..."
    "$PY" "$ROOT/scripts/build_gl_stubs.py" || true
fi

export LD_LIBRARY_PATH="$STUBS:${LD_LIBRARY_PATH:-}"
export QT_QPA_PLATFORM="${CLIPOS_PLATFORM:-vnc}"
export QT_OPENGL=software
export QTWEBENGINE_CHROMIUM_FLAGS="${QTWEBENGINE_CHROMIUM_FLAGS:-} --disable-gpu"
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"

# Point Qt straight at the system font directory: bare containers often have no
# fontconfig cache, which leaves Qt with zero font families.
if [ -d /usr/share/fonts ]; then
    export QT_QPA_FONTDIR=/usr/share/fonts
fi

exec "$PY" "$@"
