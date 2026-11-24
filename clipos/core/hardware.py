"""Hardware detection and encoder selection.

Detects CPU cores, RAM, GPU (NVIDIA / Apple Silicon / Intel iGPU) and picks the best
available FFmpeg encoder.  Never assumes a dedicated GPU exists -- CPU encoding is a
fully supported path.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .ffmpeg import list_encoders
from .logging_setup import get_logger

log = get_logger(__name__)


@dataclass
class GPUInfo:
    name: str = ""
    vendor: str = ""          # nvidia | apple | intel | amd | unknown
    vram_mb: int = 0
    driver: str = ""
    cuda_available: bool = False
    metal_available: bool = False
    qsv_available: bool = False
    count: int = 0

    @property
    def label(self) -> str:
        if not self.name:
            return "No dedicated GPU"
        vram = f" · {self.vram_mb} MB VRAM" if self.vram_mb else ""
        return f"{self.name}{vram}"


@dataclass
class HardwareProfile:
    os_name: str = ""
    os_version: str = ""
    arch: str = ""
    cpu_name: str = ""
    cpu_cores: int = 0
    cpu_threads: int = 0
    ram_total_mb: int = 0
    ram_available_mb: int = 0
    gpu: GPUInfo = field(default_factory=GPUInfo)
    ffmpeg_encoders: dict = field(default_factory=dict)
    torch_available: bool = False
    torch_cuda: bool = False
    torch_mps: bool = False

    @property
    def recommended_threads(self) -> int:
        # Leave headroom for playback, Qt and the OS. FFmpeg filters and speech
        # inference each own worker pools; using all logical CPUs causes stutter.
        logical = max(1, self.cpu_threads)
        budget = min(8, max(1, logical - max(1, logical // 4)))
        if 0 < self.ram_total_mb <= 8192:
            budget = min(budget, 4)
        return budget

    @property
    def is_apple_silicon(self) -> bool:
        return self.gpu.vendor == "apple" or (
            self.os_name == "macOS" and self.arch in ("arm64", "aarch64")
        )

    def to_dict(self) -> dict:
        return {
            "os_name": self.os_name,
            "os_version": self.os_version,
            "arch": self.arch,
            "cpu_name": self.cpu_name,
            "cpu_cores": self.cpu_cores,
            "cpu_threads": self.cpu_threads,
            "ram_total_mb": self.ram_total_mb,
            "ram_available_mb": self.ram_available_mb,
            "gpu": {
                "name": self.gpu.name,
                "vendor": self.gpu.vendor,
                "vram_mb": self.gpu.vram_mb,
                "cuda_available": self.gpu.cuda_available,
                "metal_available": self.gpu.metal_available,
                "qsv_available": self.gpu.qsv_available,
                "count": self.gpu.count,
            },
            "ffmpeg_encoders": self.ffmpeg_encoders,
            "torch_available": self.torch_available,
            "torch_cuda": self.torch_cuda,
            "torch_mps": self.torch_mps,
        }


def _run(cmd: list[str], timeout: int = 15) -> str:
    try:
        flags = 0x08000000 if sys.platform == "win32" else 0
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, creationflags=flags
        )
        return (proc.stdout or "") + (proc.stderr or "")
    except Exception:
        return ""


def _cpu_name() -> str:
    system = platform.system()
    if system == "Darwin":
        out = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        if out.strip():
            return out.strip()
    if system == "Windows":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except (ImportError, OSError):
            pass
    try:
        with open("/proc/cpuinfo") as fh:
            for line in fh:
                if "model name" in line:
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine() or "Unknown CPU"


def _ram_info() -> tuple[int, int]:
    # Live available memory (particularly important on unified-memory Macs).
    try:
        import psutil
        mem = psutil.virtual_memory()
        return mem.total // (1024 * 1024), mem.available // (1024 * 1024)
    except (ImportError, OSError):
        pass
    system = platform.system()
    if system == "Windows":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return stat.ullTotalPhys // (1024 * 1024), stat.ullAvailPhys // (1024 * 1024)
        except Exception:
            pass
    if system == "Darwin":
        out = _run(["sysctl", "-n", "hw.memsize"])
        total = int(out.strip()) // (1024 * 1024) if out.strip().isdigit() else 0
        return total, total
    total = avail = 0
    try:
        info = {}
        with open("/proc/meminfo") as fh:
            for line in fh:
                k, _, v = line.partition(":")
                info[k] = v.strip()
        total = int(info.get("MemTotal", "0 kB").split()[0]) // 1024
        avail = int(info.get("MemAvailable", info.get("MemFree", "0 kB")).split()[0]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return total, avail


def _detect_nvidia() -> GPUInfo:
    gpu = GPUInfo(vendor="nvidia")
    smi = shutil.which("nvidia-smi")
    if not smi:
        # Windows fallback
        smi = shutil.which("nvidia-smi.exe")
    if not smi:
        for cand in (
            r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
            "/usr/bin/nvidia-smi",
            "/usr/local/bin/nvidia-smi",
        ):
            if Path(cand).exists():
                smi = cand
                break
    if not smi:
        return gpu
    out = _run([
        smi, "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ], timeout=20)
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    if not lines:
        return gpu
    gpu.count = len(lines)
    parts = [p.strip() for p in lines[0].split(",")]
    gpu.name = parts[0] if parts else "NVIDIA GPU"
    try:
        gpu.vram_mb = int(float(parts[1])) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        pass
    gpu.driver = parts[2] if len(parts) > 2 else ""
    gpu.cuda_available = True
    return gpu


def _detect_apple() -> GPUInfo:
    gpu = GPUInfo()
    if platform.system() != "Darwin":
        return gpu
    brand = platform.machine()
    if brand not in ("arm64", "aarch64"):
        # Intel Macs may have Intel/AMD graphics, not an Apple Silicon GPU.
        return gpu
    gpu.vendor = "apple"
    names = {"arm64": "Apple Silicon (Apple GPU)", "aarch64": "Apple Silicon (Apple GPU)"}
    gpu.name = names.get(brand, "Apple GPU")
    gpu.metal_available = True
    gpu.count = 1
    try:
        out = _run(["system_profiler", "SPDisplaysDataType"], timeout=25)
        m = re.search(r"VRAM[^:]*:\s*(\d+)\s*MB", out)
        if m:
            gpu.vram_mb = int(m.group(1))
    except Exception:
        pass
    return gpu


def _detect_intel() -> GPUInfo:
    gpu = GPUInfo(vendor="intel")
    if platform.system() == "Linux":
        out = _run(["lspci"])
        for line in out.splitlines():
            if "VGA" in line and ("Intel" in line or "HD Graphics" in line or "UHD" in line):
                gpu.name = line.split(":", 2)[-1].strip()
                gpu.count = 1
                break
    elif platform.system() == "Windows":
        out = _run(["wmic", "path", "win32_VideoController", "get", "name"])
        for line in out.splitlines():
            if "Intel" in line and line.strip():
                gpu.name = line.strip()
                gpu.count = 1
                break
    if gpu.name:
        gpu.qsv_available = True
    return gpu


def _detect_gpu() -> GPUInfo:
    if platform.system() == "Darwin":
        return _detect_apple()
    nvidia = _detect_nvidia()
    if nvidia.name:
        return nvidia
    intel = _detect_intel()
    if intel.name:
        return intel
    if platform.system() == "Linux":
        out = _run(["lspci"])
        for line in out.splitlines():
            if "VGA" in line and ("AMD" in line or "Radeon" in line):
                return GPUInfo(name=line.split(":", 2)[-1].strip(), vendor="amd", count=1)
    return GPUInfo()


def _detect_torch() -> tuple[bool, bool, bool]:
    try:
        import torch  # type: ignore

        cuda = bool(torch.cuda.is_available())
        mps = bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
        return True, cuda, mps
    except Exception:
        return False, False, False


@lru_cache(maxsize=1)
def detect_hardware() -> HardwareProfile:
    """Full hardware probe. Cached for the process lifetime."""
    system = platform.system()
    os_names = {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}
    prof = HardwareProfile(
        os_name=os_names.get(system, system),
        os_version=platform.release(),
        arch=platform.machine(),
        cpu_name=_cpu_name(),
        cpu_cores=os.cpu_count() or 1,
        cpu_threads=os.cpu_count() or 1,
    )
    try:
        import psutil
        prof.cpu_cores = psutil.cpu_count(logical=False) or prof.cpu_threads
    except (ImportError, OSError):
        pass
    total, avail = _ram_info()
    prof.ram_total_mb = total
    prof.ram_available_mb = avail
    prof.gpu = _detect_gpu()
    prof.ffmpeg_encoders = list_encoders()
    prof.torch_available, prof.torch_cuda, prof.torch_mps = _detect_torch()
    log.info(
        "hardware: %s %s | %d threads | %dMB RAM | GPU=%s",
        prof.os_name, prof.arch, prof.cpu_threads, prof.ram_total_mb, prof.gpu.label,
    )
    return prof


# --------------------------------------------------------------------------------------
# Encoder selection
# --------------------------------------------------------------------------------------


@dataclass
class EncoderChoice:
    video_encoder: str = "libx264"
    audio_encoder: str = "aac"
    hw_accel: str = "none"          # none | nvenc | qsv | videotoolbox
    extra_args: list = field(default_factory=list)
    description: str = "CPU (software) encoding"

    @property
    def is_hardware(self) -> bool:
        return self.hw_accel != "none"


def choose_encoder(preference: str = "auto", codec: str = "h264",
                   low_memory: bool = False) -> EncoderChoice:
    """Pick the best available encoder.

    ``preference`` is one of: auto, cpu, nvidia, intel, apple, nvenc, qsv, videotoolbox.
    Falls back to CPU whenever the requested accelerator is unavailable -- we never
    hand ffmpeg an encoder it does not have.
    """
    prof = detect_hardware()
    enc = prof.ffmpeg_encoders or {}
    want_hevc = codec.lower() in ("h265", "hevc")
    base_cpu = "libx265" if want_hevc else "libx264"

    def cpu_choice() -> EncoderChoice:
        extra = []
        if low_memory:
            extra += ["-threads", str(max(1, prof.cpu_cores // 2))]
        return EncoderChoice(
            video_encoder=base_cpu, audio_encoder="aac", hw_accel="none",
            extra_args=extra,
            description=f"CPU {base_cpu} ({prof.cpu_threads} threads)",
        )

    if preference in ("cpu", "none"):
        return cpu_choice()

    # NVENC
    nvenc_name = "hevc_nvenc" if want_hevc else "h264_nvenc"
    if preference in ("auto", "nvidia", "nvenc", "gpu"):
        if enc.get(nvenc_name) and prof.gpu.cuda_available:
            return EncoderChoice(
                video_encoder=nvenc_name, audio_encoder="aac", hw_accel="nvenc",
                extra_args=["-preset", "p4" if want_hevc else "p5", "-tune", "hq"],
                description=f"NVIDIA NVENC ({prof.gpu.name})",
            )

    # Apple VideoToolbox
    vt_name = "hevc_videotoolbox" if want_hevc else "h264_videotoolbox"
    if preference in ("auto", "apple", "videotoolbox", "gpu"):
        if platform.system() == "Darwin" and enc.get(vt_name):
            return EncoderChoice(
                video_encoder=vt_name, audio_encoder="aac", hw_accel="videotoolbox",
                extra_args=["-b:v", "10M", "-allow_sw", "1"],
                description="Apple VideoToolbox (hardware)",
            )

    # Intel QSV
    qsv_name = "hevc_qsv" if want_hevc else "h264_qsv"
    if preference in ("auto", "intel", "qsv", "gpu"):
        if enc.get(qsv_name) and prof.gpu.qsv_available:
            return EncoderChoice(
                video_encoder=qsv_name, audio_encoder="aac", hw_accel="qsv",
                extra_args=["-preset", "medium", "-look_ahead", "0"],
                description=f"Intel Quick Sync ({prof.gpu.name})",
            )

    return cpu_choice()


def memory_pressure() -> float:
    """Fraction of RAM in use (0..1)."""
    total, available = _ram_info()
    if total <= 0:
        return 0.0
    return max(0.0, min(1.0, (total - available) / total))


def suggest_worker_threads(requested: int = 0) -> int:
    prof = detect_hardware()
    if requested and requested > 0:
        return max(1, min(requested, prof.cpu_threads))
    budget = prof.recommended_threads
    if memory_pressure() >= .85:
        budget = min(budget, 2)
    return budget
