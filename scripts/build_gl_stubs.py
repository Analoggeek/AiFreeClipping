#!/usr/bin/env python3
"""Build stub shared libraries so PySide6 can run headlessly on bare Linux CI.

Qt's platform plugins link against system libraries (libGL, libEGL, libxkbcommon,
libdbus-1) that a normal desktop OS provides.  On a bare container they are
missing and PySide6 cannot even be imported.

Instead of hard-coding symbol lists, this script reads the *undefined* symbols
that the Qt libraries actually need and generates stubs for exactly those.

This is a DEVELOPMENT / CI convenience only.  Real macOS and Windows builds use
the libraries shipped by the operating system.

    python scripts/build_gl_stubs.py
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUB_DIR = Path(os.environ.get("CLIPOS_STUB_LIBS", ROOT / ".stublibs"))

# Which stub library satisfies which "needed by" library
TARGETS = {
    "libGL.so.1": ["libQt6Gui.so", "libQt6Widgets.so", "libQt6OpenGLWidgets.so"],
    "libEGL.so.1": ["libQt6Gui.so", "libQt6Widgets.so"],
    "libxkbcommon.so.0": ["libQt6Gui.so", "libQt6Widgets.so"],
    "libdbus-1.so.3": ["libQt6DBus.so"],
}

VERSION_TAGS = {
    "libdbus-1.so.3": "LIBDBUS_1_3",
    "libxkbcommon.so.0": "V_0.5.0",
}

# Symbol-family prefixes for the unversioned libraries.  A stub may only export
# symbols from its own family, otherwise the loader sees two libraries claiming
# the same symbol.
PREFIX_MAP = {
    "libGL.so.1": ("gl",),
    "libEGL.so.1": ("egl",),
    "libxkbcommon.so.0": ("xkb",),
}

# Symbols that must not be stubbed (they are provided by the linker / libc)
SKIP_PREFIXES = ("_", "__")

# Per-library symbol hints.  When a stub library has a hint list, only symbols
# from that list are exported -- this prevents one stub from claiming another
# library's symbols (which makes the dynamic loader abort).
SYMBOL_HINTS: dict[str, set[str]] = {
    "libGL.so.1": {
        "glGetString", "glGetError", "glClear", "glClearColor", "glViewport",
        "glEnable", "glDisable", "glBlendFunc", "glBlendEquation",
        "glDrawArrays", "glDrawElements", "glDrawBuffer",
        "glGenBuffers", "glBindBuffer", "glBufferData", "glBufferSubData",
        "glDeleteBuffers", "glGenVertexArrays", "glBindVertexArray",
        "glDeleteVertexArrays", "glEnableVertexAttribArray",
        "glDisableVertexAttribArray", "glVertexAttribPointer",
        "glCreateShader", "glShaderSource", "glCompileShader", "glGetShaderiv",
        "glGetShaderInfoLog", "glCreateProgram", "glAttachShader",
        "glLinkProgram", "glGetProgramiv", "glGetProgramInfoLog", "glUseProgram",
        "glDeleteShader", "glDeleteProgram", "glGetUniformLocation",
        "glUniform1i", "glUniform1f", "glUniform2f", "glUniform3f", "glUniform4f",
        "glUniformMatrix3fv", "glUniformMatrix4fv", "glGetAttribLocation",
        "glPixelStorei", "glReadPixels", "glFlush", "glFinish",
        "glGetIntegerv", "glGetFloatv", "glDepthFunc", "glCullFace",
        "glTexImage2D", "glTexParameteri", "glTexParameterfv",
        "glActiveTexture", "glGenTextures", "glBindTexture", "glDeleteTextures",
        "glScissor", "glLineWidth", "glPolygonOffset", "glStencilFunc",
        "glStencilOp", "glClearStencil", "glColorMask", "glDepthMask",
        "glAlphaFunc", "glSampleCoverage", "glTexParameteri",
        "glGetAttribLocation", "glVertexAttribDivisor",
        "glDrawElementsInstanced", "glDrawArraysInstanced",
    },
    "libEGL.so.1": {
        "eglGetDisplay", "eglInitialize", "eglTerminate", "eglChooseConfig",
        "eglGetConfigAttrib", "eglCreateContext", "eglDestroyContext",
        "eglMakeCurrent", "eglSwapBuffers", "eglGetError", "eglGetCurrentContext",
        "eglGetCurrentDisplay", "eglGetCurrentSurface", "eglCreateWindowSurface",
        "eglDestroySurface", "eglQuerySurface", "eglSwapInterval",
        "eglGetProcAddress", "eglBindAPI", "eglQueryAPI", "eglGetDisplayDriverName",
        "eglGetPlatformDisplay", "eglQueryDevices", "eglQueryDeviceString",
        "eglCreatePlatformWindowSurface", "eglCreatePlatformPixmapSurface",
        "eglQueryContext", "eglWaitClient", "eglWaitGL", "eglWaitNative",
    },
    "libxkbcommon.so.0": {
        "xkb_context_new", "xkb_context_unref", "xkb_context_parse",
        "xkb_context_parse_file", "xkb_context_sanitize",
        "xkb_keymap_new_from_names", "xkb_keymap_new_from_string",
        "xkb_keymap_new_from_file", "xkb_keymap_free",
        "xkb_keymap_key_by_name", "xkb_keymap_key_get_syms",
        "xkb_state_new", "xkb_state_unref", "xkb_state_update_key",
        "xkb_state_update_mask", "xkb_state_key_get_syms",
        "xkb_state_key_get_utf8", "xkb_state_get_layout",
        "xkb_state_get_led_mask", "xkb_state_update_led",
        "xkb_compose_table_new_from_buffer", "xkb_compose_table_free",
        "xkb_compose_table_new_from_locale", "xkb_compose_state_new",
        "xkb_compose_state_unref", "xkb_compose_state_get_utf8",
        "xkb_keymap_get_ascii", "xkb_keymap_mod_get_index",
        "xkb_keymap_key_get_mods_for_level", "xkb_state_serialize",
        "xkb_keymap_num_levels_for_key", "xkb_context_set_log_level",
        "xkb_context_set_log_verbosity", "xkb_context_get_log_verbosity",
    },
}


def _pyside_lib_dir() -> Path | None:
    try:
        import PySide6  # noqa: F401

        base = Path(PySide6.__file__).parent
        for cand in (base / "Qt" / "lib", base / "QtCore"):
            if cand.exists():
                return cand
    except Exception:
        pass
    return None


def _resolve_lib(lib_dir: Path, lib_name: str) -> Path | None:
    """Find a library by name, tolerating the .so.N versioning suffix."""
    direct = lib_dir / lib_name
    if direct.exists():
        return direct
    stem = lib_name.split(".so")[0]
    for cand in sorted(lib_dir.glob(f"{stem}.so*")):
        if cand.exists():
            return cand
    return None


def undefined_symbols(lib_dir: Path, lib_name: str) -> list[str]:
    """Symbols that ``lib_name`` imports but does not define."""
    return [s for s, _ in undefined_symbols_with_versions(lib_dir, lib_name)]


def undefined_symbols_with_versions(
    lib_dir: Path, lib_name: str
) -> list[tuple[str, str]]:
    """Imported symbols paired with the version tag they are requested under."""
    lib = _resolve_lib(lib_dir, lib_name)
    if not lib:
        return []
    try:
        out = subprocess.run(["nm", "-D", "--undefined-only", str(lib)],
                             capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            return []
    except Exception:
        return []
    syms: list[tuple[str, str]] = []
    for line in out.stdout.splitlines():
        parts = line.split()
        if not parts or parts[0] not in ("U", "w"):
            continue
        raw = parts[-1]
        sym, _, ver = raw.partition("@")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", sym):
            continue
        if sym.startswith(SKIP_PREFIXES):
            continue
        syms.append((sym, ver))
    return syms


def defined_symbols(lib_dir: Path, lib_name: str) -> set[str]:
    lib = _resolve_lib(lib_dir, lib_name)
    if not lib:
        return set()
    try:
        out = subprocess.run(["nm", "-D", "--defined-only", str(lib)],
                             capture_output=True, text=True, timeout=120)
    except Exception:
        return set()
    syms = set()
    for line in out.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] not in ("U", "w"):
            syms.add(parts[-1])
    return syms


def make_c_source(symbols: list[str], version_tag: str = "") -> str:
    unique: list[str] = []
    seen: set[str] = set()
    for s in symbols:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    lines = ["/* Auto-generated stub library for headless CI. */"]
    # The helper symbols must stay hidden: if two stub libraries export the same
    # helper name, the dynamic loader reports an inconsistency.
    lines += [
        f'static long clipos_stub_{i}(void) {{ return 0; }}' for i in range(len(unique))
    ]
    lines.append("")
    for i, s in enumerate(unique):
        lines.append(
            f'__attribute__((visibility("default"))) long {s}(void) '
            f'{{ return clipos_stub_{i}(); }}'
        )
    if version_tag:
        # Bind each exported symbol to the version node the consumer asks for.
        # Without this the loader only sees the symbol in the BASE node and
        # reports "undefined symbol: X, version TAG".
        lines.append("")
        for s in unique:
            lines.append(f'__asm__(".symver {s},{s}@{version_tag}");')
    return "\n".join(lines) + "\n"


def make_version_script(name: str, symbols: list[str]) -> str:
    """Linker version script defining the version node referenced by .symver."""
    tag = VERSION_TAGS.get(name)
    if not tag:
        return ""
    unique: list[str] = []
    seen: set[str] = set()
    for sym in symbols:
        if sym not in seen:
            seen.add(sym)
            unique.append(sym)
    # Exactly one named node.  Adding a second node makes glibc >= 2.36 abort
    # with "Inconsistency detected" because the base node then carries the
    # library filename.
    lines = [f"{tag} {{", "  global:"]
    lines += [f"    {sym};" for sym in unique]
    lines += ["};", ""]
    return "\n".join(lines)


def build_stub(name: str, symbols: list[str]) -> Path | None:
    target = STUB_DIR / name
    if not symbols:
        return None
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "stub.c"
        tag = VERSION_TAGS.get(name, "")
        src.write_text(make_c_source(symbols, tag))
        out = Path(td) / name
        cmd = ["gcc", "-shared", "-fPIC", "-O0", "-w", "-o", str(out), str(src)]
        # Set an explicit SONAME so the loader maps the object under exactly one
        # name.  Without it, ld.so may see the same object under two names and
        # abort with "Inconsistency detected".
        cmd += ["-Wl,-soname," + name]
        ver = make_version_script(name, symbols)
        if ver:
            vfile = Path(td) / "stub.map"
            vfile.write_text(ver)
            cmd += ["-Wl,--version-script", str(vfile)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"  [skip] {name}: {proc.stderr.strip()[:200]}")
            return None
        STUB_DIR.mkdir(parents=True, exist_ok=True)
        target.write_bytes(out.read_bytes())
        target.chmod(0o755)
        stem = name.split(".so")[0]
        # A library that carries symbol versions must NOT also exist under the
        # unversioned name -- ld.so maps the object twice under different names
        # and aborts with "Inconsistency detected".
        if name not in VERSION_TAGS:
            (STUB_DIR / f"{stem}.so").write_bytes(target.read_bytes())
            (STUB_DIR / f"{stem}.so").chmod(0o755)
        else:
            stale = STUB_DIR / f"{stem}.so"
            if stale.exists():
                stale.unlink()
    return target


def main() -> int:
    if not shutil.which("gcc") or not shutil.which("nm"):
        print("gcc and binutils (nm) are required to build the stubs")
        return 1

    lib_dir = _pyside_lib_dir()
    if not lib_dir:
        print("PySide6 not installed")
        return 1

    STUB_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Qt libs: {lib_dir}")

    # Build the prefix-specific libraries first so the catch-all (dbus) stub can
    # be built from whatever is still unclaimed.
    order = ["libGL.so.1", "libEGL.so.1", "libxkbcommon.so.0", "libdbus-1.so.3"]
    claimed: set[str] = set()

    for stub_name in order:
        consumers = TARGETS.get(stub_name, [])
        tag = VERSION_TAGS.get(stub_name, "")

        needed: set[str] = set()
        prefixes = PREFIX_MAP.get(stub_name)
        for consumer in consumers:
            for sym, ver in undefined_symbols_with_versions(lib_dir, consumer):
                if tag:
                    # Versioned library: only symbols requested under its tag.
                    if ver != tag:
                        continue
                else:
                    # Unversioned library: only untagged symbols belong to it.
                    # Tagged symbols come from libc or another versioned lib.
                    if ver:
                        continue
                    # Untagged stubs must still be restricted to their own
                    # symbol family, otherwise one stub claims another's symbols.
                    if prefixes and not sym.startswith(prefixes):
                        continue
                needed.add(sym)

        # Remove symbols already defined by other Qt libs (avoid duplicate defs)
        for other in lib_dir.glob("*.so*"):
            if other.name.startswith("libQt6"):
                needed -= defined_symbols(lib_dir, other.name)
        # Remove symbols another stub already provides
        needed -= claimed

        syms = sorted(needed)
        if not syms:
            print(f"  [ok] {stub_name}: nothing to stub")
            continue
        p = build_stub(stub_name, syms)
        if p:
            claimed |= set(syms)
            print(f"  [ok] {stub_name}: {len(syms)} symbols")
        else:
            print(f"  [FAIL] {stub_name}")

    print(f"\nStub libraries in {STUB_DIR}")
    print("Run with:  LD_LIBRARY_PATH=" + str(STUB_DIR) + " QT_QPA_PLATFORM=offscreen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
