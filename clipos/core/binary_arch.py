"""Reading the architecture out of a binary file.

A binary that is built for the wrong architecture is worse than no binary
at all: it does not run, or it runs slowly through Rosetta, and nothing
in the application says why.  These helpers read the architecture out of
the file itself, so that the build can check what it downloaded and the
application can check what it is running.

Three formats are understood: Mach-O (macOS), ELF (Linux) and PE
(Windows).
"""
from __future__ import annotations

import struct
from pathlib import Path

# The architecture each platform key has to end up with.
EXPECTED_ARCH = {
    "linux-x64": "x86_64",
    "linux-ia32": "i386",
    "darwin-x64": "x86_64",
    "darwin-arm64": "arm64",
    "win32-x64": "x86_64",
    "win32-ia32": "i386",
}

_MACH_CPU_TYPES = {
    7: "i386",
    0x01000007: "x86_64",
    12: "arm",
    0x0100000C: "arm64",
}

_ELF_MACHINES = {3: "i386", 62: "x86_64", 40: "arm", 183: "arm64"}

_PE_MACHINES = {0x014C: "i386", 0x8664: "x86_64", 0xAA64: "arm64"}


def _macho_arch(path: Path) -> str | None:
    """The architecture of a Mach-O file, or None if it is not a Mach-O."""
    try:
        data = path.read_bytes()[:64]
    except OSError:
        return None
    if len(data) < 8:
        return None
    little = struct.unpack("<I", data[:4])[0]
    big = struct.unpack(">I", data[:4])[0]
    magic = little if little in (0xFEEDFACE, 0xFEEDFACF) else big
    if magic in (0xFEEDFACE, 0xFEEDFACF):
        cpu, = struct.unpack("<i", data[4:8])
        return _MACH_CPU_TYPES.get(cpu, f"cpu{cpu}")
    if magic in (0xCAFEBABE, 0xBEBAFECA):
        # A fat binary holds several architectures.  The fat header and
        # its entries are always big endian, whichever way round the
        # magic was stored.
        count = struct.unpack(">I", data[4:8])[0]
        found = []
        for index in range(count):
            offset = 8 + index * 20
            cpu, = struct.unpack(">i", data[offset:offset + 4])
            found.append(_MACH_CPU_TYPES.get(cpu, f"cpu{cpu}"))
        return "|".join(found)
    return None


def _elf_arch(path: Path) -> str | None:
    """The architecture of an ELF file, or None if it is not an ELF."""
    try:
        data = path.read_bytes()[:20]
    except OSError:
        return None
    if len(data) < 20 or data[:4] != b"\x7fELF":
        return None
    little = data[5] == 1
    order = "<" if little else ">"
    machine, = struct.unpack(order + "H", data[18:20])
    return _ELF_MACHINES.get(machine, f"machine{machine}")


def _pe_arch(path: Path) -> str | None:
    """The architecture of a Windows executable, or None."""
    try:
        data = path.read_bytes()[:1024]
    except OSError:
        return None
    if len(data) < 64 or data[:2] != b"MZ":
        return None
    offset = struct.unpack("<I", data[0x3C:0x40])[0]
    if offset + 6 > len(data) or data[offset:offset + 2] != b"PE":
        return None
    machine, = struct.unpack("<H", data[offset + 4:offset + 6])
    return _PE_MACHINES.get(machine, f"machine{machine}")


def binary_arch(path: Path | str) -> str | None:
    """The architecture of a binary, whichever format it is in.

    A fat binary reports several architectures, separated by a vertical
    bar, so that a check can ask whether one of them is the wanted one.
    """
    path = Path(path)
    for probe in (_macho_arch, _elf_arch, _pe_arch):
        found = probe(path)
        if found:
            return found
    return None


def check_arch(path: Path | str, key: str) -> None:
    """Make sure a binary really is the architecture it is filed under.

    A mismatch is not a warning: an Intel binary in the Apple Silicon
    folder runs through Rosetta, or not at all, and nothing in the
    application says why.
    """
    path = Path(path)
    expected = EXPECTED_ARCH.get(key)
    if not expected:
        return
    found = binary_arch(path)
    if found is None:
        # The architecture could not be read.  That is not proof of a
        # problem, so the file is kept.
        print(f"  [warn] the architecture of {path.name} could not be read")
        return
    if expected in found.split("|"):
        print(f"  [ok  ] {path.name} is {found}")
        return
    raise SystemExit(
        f"{path} is a {found} binary but it is filed as {expected}. "
        f"The package it came from is wrong; refusing to ship it."
    )


def running_architecture() -> str:
    """The architecture of the machine the code is running on."""
    import platform
    import sys

    machine = platform.machine().lower()
    if sys.platform == "win32":
        return "x86_64" if machine in ("amd64", "x86_64") else "i386"
    if sys.platform == "darwin":
        return "arm64" if machine in ("arm64", "aarch64") else "x86_64"
    return "x86_64" if machine in ("amd64", "x86_64") else "i386"


def can_run(path: Path | str | None) -> bool:
    """Whether a binary can run on this machine.

    A machine that can run both kinds of binary -- Apple Silicon with
    Rosetta installed -- counts as a match, because the binary will run.
    """
    if not path:
        return True
    found = binary_arch(path)
    if found is None:
        # The architecture could not be read; that is not proof of a
        # problem.
        return True
    wanted = running_architecture()
    if wanted in found.split("|"):
        return True
    if wanted == "arm64" and "x86_64" in found.split("|"):
        return True
    return False
