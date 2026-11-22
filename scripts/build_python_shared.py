#!/usr/bin/env python3
"""Build a Python shared library so PyInstaller can freeze CLIPOS.

Some Linux distributions ship Python without the ``libpython3.x.so`` file that
PyInstaller's bootloader links against.  On Debian and Ubuntu that happens
when the ``libpython3.x`` package is not installed; the ``libpython3.x-minimal``
and ``libpython3.x-stdlib`` packages alone are not enough.

This script builds the missing shared library from the matching CPython
source and prints the ``LD_LIBRARY_PATH`` needed to use it.

Usage::

    python scripts/build_python_shared.py            # build and install locally
    python scripts/build_python_shared.py --version 3.11.2
    python scripts/build_python_shared.py --prefix /opt/python-shared

The build needs a C compiler and ``make``.  It does not need root: everything
is installed under the chosen prefix.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> None:
    printable = " ".join(str(c) for c in cmd)
    print(f"  $ {printable}")
    subprocess.run([str(c) for c in cmd], cwd=cwd, check=True, env=env)


def fetch_source(version: str, dest: Path) -> Path:
    """Download the CPython source tarball from GitHub."""
    url = f"https://codeload.github.com/python/cpython/tar.gz/refs/tags/v{version}"
    tarball = dest / f"Python-{version}.tar.gz"
    print(f"[python-shared] downloading {url}")
    with urllib.request.urlopen(url, timeout=300) as response:
        tarball.write_bytes(response.read())
    print(f"[python-shared] extracting to {dest}")
    with tarfile.open(tarball) as tf:
        tf.extractall(dest)
    # GitHub names the directory "cpython-<version>".
    for pattern in (f"cpython-{version}*", f"python-{version}*"):
        match = next(dest.glob(pattern), None)
        if match is not None:
            return match
    raise SystemExit(f"could not find the extracted source in {dest}")


def find_zlib_headers() -> Path | None:
    """Locate zlib.h, which the zlib core module needs.

    Minimal containers often ship the zlib runtime but not its development
    headers.  Node.js bundles a copy of them, which is a reliable fallback.
    """
    candidates = [
        Path("/usr/include"),
        Path("/usr/local/include"),
        Path("/usr/local/include/node"),
        Path("/opt/homebrew/include"),
    ]
    for folder in candidates:
        if (folder / "zlib.h").exists():
            return folder
    return None


def enable_core_modules(source: Path, zlib_include: Path | None) -> None:
    """Build the core modules into the interpreter, as Debian does.

    Debian compiles ``_struct``, ``zlib`` and friends into the interpreter
    itself instead of shipping them as separate extension modules.  PyInstaller
    relies on that layout, so the same modules are enabled here.
    """
    setup = source / "Modules" / "Setup"
    if not setup.exists():
        return
    core = {
        "_asyncio", "_bisect", "_blake2", "_collections", "_contextvars",
        "_csv", "_datetime", "_elementtree", "_functools", "_heapq", "_imp",
        "_io", "_json", "_locale", "_lsprof", "_md5", "_opcode", "_operator",
        "_pickle", "_posixsubprocess", "_queue", "_random", "_sha1", "_sha256",
        "_sha3", "_sha512", "_socket", "_sre", "_stat", "_statistics", "_string",
        "_struct", "_symtable", "_thread", "_tokenize", "_tracemalloc", "_typing",
        "_warnings", "_weakref", "_zoneinfo", "array", "atexit", "audioop",
        "binascii", "cmath", "errno", "fcntl", "grp", "marshal", "math", "mmap",
        "posix", "pwd", "pyexpat", "select", "spwd", "sys", "syslog", "time",
        "unicodedata", "zlib",
    }
    lines, changed = [], 0
    for line in setup.read_text(encoding="utf-8").splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("#") and len(stripped) > 1:
            parts = stripped[1:].split()
            if parts and parts[0] in core:
                line = line.replace("#" + parts[0], parts[0], 1)
                changed += 1
        lines.append(line)

    text = "".join(lines)
    if zlib_include is not None:
        # Point the linker at a directory holding a "libz.so" symlink.
        libdir = zlib_include / "lib"
        libdir.mkdir(exist_ok=True)
        for runtime in ("/lib/x86_64-linux-gnu/libz.so.1",
                        "/usr/lib/x86_64-linux-gnu/libz.so.1",
                        "/usr/lib/libz.so.1"):
            if Path(runtime).exists():
                link = libdir / "libz.so"
                if not link.exists():
                    link.symlink_to(runtime)
                break
        text = text.replace(
            "zlib  zlibmodule.c -lz\n",
            f"zlib  zlibmodule.c -I{zlib_include} -L{libdir} -lz\n",
        )
    # Use the expat sources bundled with CPython instead of the system
    # library, because the system expat headers are often absent too.
    if (source / "Modules" / "expat" / "xmlparse.c").exists():
        text = text.replace(
            "pyexpat pyexpat.c\n",
            "pyexpat pyexpat.c expat/xmlparse.c expat/xmlrole.c "
            "expat/xmltok.c expat/xmltok_impl.c expat/xmltok_ns.c\n",
        )
    setup.write_text(text, encoding="utf-8")
    print(f"[python-shared] enabled {changed} core modules")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="3.11.2",
                    help="CPython version to build (must match the interpreter "
                         "that runs PyInstaller)")
    ap.add_argument("--prefix", default="",
                    help="install prefix (default: a temporary directory)")
    ap.add_argument("--keep", action="store_true",
                    help="keep the build directory")
    args = ap.parse_args()

    for tool in ("gcc", "make"):
        if not shutil.which(tool):
            print(f"error: {tool} is required to build CPython")
            return 2

    workdir = Path(tempfile.mkdtemp(prefix="clipos-python-"))
    prefix = Path(args.prefix) if args.prefix else workdir / "install"
    prefix.mkdir(parents=True, exist_ok=True)

    try:
        source = fetch_source(args.version, workdir)
        print(f"[python-shared] configuring in {source}")
        run(["./configure", f"--prefix={prefix}", "--enable-shared",
             "--with-ensurepip=no", "--without-doc-strings"], cwd=source)

        zlib_include = find_zlib_headers()
        if zlib_include is None:
            print("error: zlib.h was not found.  Install the zlib development "
                  "headers (Debian/Ubuntu: zlib1g-dev, Fedora/RHEL: zlib-devel) "
                  "and try again.")
            return 2
        print(f"[python-shared] using zlib headers from {zlib_include}")
        enable_core_modules(source, zlib_include)

        print("[python-shared] building (this takes a few minutes) ...")
        jobs = str(os.cpu_count() or 2)
        run(["make", f"-j{jobs}"], cwd=source)
        run(["make", "install"], cwd=source)

        libdir = prefix / "lib"
        # The shared object is named after the ABI version ("3.11"), not the
        # full release ("3.11.2").
        major_minor = ".".join(args.version.split(".")[:2])
        candidates = sorted(libdir.glob(f"libpython{major_minor}.so*"))
        if not candidates:
            print(f"error: no libpython{major_minor}.so was produced in {libdir}")
            return 1
        so = candidates[0]
        print(f"\n[python-shared] built {so}")
        print(f"\nRun the build with:\n"
              f"  LD_LIBRARY_PATH={libdir} python scripts/build.py <target>\n")
        return 0
    finally:
        if not args.keep and not args.prefix:
            shutil.rmtree(workdir, ignore_errors=True)
        elif args.keep:
            print(f"[python-shared] build directory kept at {workdir}")


if __name__ == "__main__":
    sys.exit(main())
