#!/usr/bin/env bash
# Isolate Intel wheels from the ARM framework site-packages on macOS runners.
set -euo pipefail
base="$(command -v python)"
arch -x86_64 "$base" -c 'import platform; assert platform.machine() == "x86_64"'
arch -x86_64 "$base" -m venv .venv-intel
wrapper="$PWD/.venv-intel/run-python"
cat > "$wrapper" <<EOF
#!/usr/bin/env bash
exec arch -x86_64 "$PWD/.venv-intel/bin/python" "\$@"
EOF
chmod +x "$wrapper"
"$wrapper" -m pip install --upgrade pip
"$wrapper" scripts/install_deps.py --build --tracking --diarization
"$wrapper" -c 'import platform, sys, PIL, PyInstaller; assert platform.machine() == "x86_64"; assert sys.prefix != sys.base_prefix; print("Isolated Intel Python:", sys.prefix, PIL.__file__)'
# Fail early on an incompatible transitive dependency, before freezing either
# an unusable OAuth implementation or an incorrectly labelled Intel bundle.
mkdir -p build
"$wrapper" scripts/verify_python_arch.py x86_64 2>&1 | tee -a build/build-error.log
if [[ -n "${GITHUB_ENV:-}" ]]; then
  echo "CLIPOS_INTEL_PYTHON=$wrapper" >> "$GITHUB_ENV"
fi
