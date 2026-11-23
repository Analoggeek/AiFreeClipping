#!/usr/bin/env python3
"""Validate macOS wheel architecture and the OAuth imports before freezing."""
from __future__ import annotations

import platform
from pathlib import Path
import subprocess
import sys
import sysconfig


def verify(expected: str) -> None:
    if sys.platform != 'darwin' or platform.machine() != expected:
        raise RuntimeError(f'Expected macOS {expected}, got {sys.platform} {platform.machine()}')
    roots = {Path(sysconfig.get_path(key)).resolve() for key in ('platlib', 'purelib')}
    failures = []
    checked = 0
    for root in sorted(roots):
        for binary in sorted(root.rglob('*')):
            if binary.is_file() and binary.suffix in ('.so', '.dylib'):
                result = subprocess.run(['lipo', str(binary), '-verify_arch', expected],
                                        capture_output=True, text=True)
                checked += 1
                if result.returncode:
                    failures.append(f'{binary}: {result.stderr.strip()}')
    if failures:
        raise RuntimeError('Incompatible wheel binaries:\n' + '\n'.join(failures))
    # Exercise the modules whose architecture mismatch originally broke Intel.
    import cryptography.hazmat.bindings._rust  # noqa: F401
    import google.auth.crypt  # noqa: F401
    import google_auth_oauthlib.flow  # noqa: F401
    import keyring  # noqa: F401
    print(f'Validated {checked} native wheel binaries and OAuth imports for {expected}')


if __name__ == '__main__':
    verify(sys.argv[1])
