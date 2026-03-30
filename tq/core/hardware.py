from __future__ import annotations

import platform
import re
import shutil
import subprocess
from dataclasses import dataclass

from tq.core.config import BackendType, CacheType, HardwareProfile


@dataclass(slots=True)
class HardwareInfo:
    system: str
    machine: str
    chip: str
    backend: str
    vram_summary: str
    total_memory_gb: float
    cuda_version: str | None = None



def _run(cmd: list[str]) -> str:
    if not shutil.which(cmd[0]):
        return ""
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
    except Exception:
        return ""



def detect_hardware() -> HardwareInfo:
    system = platform.system()
    machine = platform.machine()
    chip = platform.processor() or machine or "unknown"
    backend = "cpu"
    vram_summary = "unknown"
    total_memory_gb = 0.0
    cuda_version = None

    if system == "Darwin" and machine in {"arm64", "aarch64"}:
        backend = "metal"
        chip = _run(["sysctl", "-n", "machdep.cpu.brand_string"]) or chip
        mem = _run(["sysctl", "-n", "hw.memsize"])
        if mem.isdigit():
            total_memory_gb = int(mem) / (1024**3)
            vram_summary = f"unified {total_memory_gb:.1f} GB"
    elif shutil.which("nvidia-smi"):
        backend = "cuda"
        query = _run([
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader",
        ])
        if query:
            first = query.splitlines()[0]
            parts = [p.strip() for p in first.split(",")]
            if len(parts) >= 3:
                chip = parts[0]
                vram_summary = parts[1]
                cuda_version = parts[2]
                match = re.search(r"([0-9]+(?:\.[0-9]+)?)", parts[1])
                if match:
                    total_memory_gb = float(match.group(1)) / 1024.0 if "MiB" in parts[1] else float(match.group(1))
    elif system == "Linux":
        meminfo = _run(["bash", "-lc", "grep MemTotal /proc/meminfo"])
        match = re.search(r"(\d+)", meminfo)
        if match:
            total_memory_gb = int(match.group(1)) / (1024**2)
            vram_summary = f"system {total_memory_gb:.1f} GB"

    return HardwareInfo(
        system=system,
        machine=machine,
        chip=chip,
        backend=backend,
        vram_summary=vram_summary,
        total_memory_gb=total_memory_gb,
        cuda_version=cuda_version,
    )



def dependency_status() -> dict[str, tuple[bool, str]]:
    deps = {
        "git": "Install git from your system package manager or https://git-scm.com",
        "cmake": "Install CMake from your package manager or https://cmake.org",
        "make": "Install build-essential/Xcode tools, or use ninja",
        "ninja": "Optional but recommended for faster builds",
        "python3": "Install Python 3.11+",
    }
    return {name: (shutil.which(name) is not None, hint) for name, hint in deps.items()}



def build_backend_name(backend: str) -> BackendType:
    if backend == "metal":
        return "metal"
    if backend == "cuda":
        return "cuda"
    return "cpu"



def recommended_cache_type(backend: BackendType, total_memory_gb: float) -> CacheType:
    if backend == "cpu":
        return "turbo4"
    if total_memory_gb >= 24:
        return "turbo2"
    if total_memory_gb >= 12:
        return "turbo3"
    return "turbo4"



def max_safe_context(total_memory_gb: float, backend: BackendType) -> int:
    if backend == "cpu":
        return 8192
    if total_memory_gb >= 24:
        return 131072
    if total_memory_gb >= 12:
        return 65536
    return 32768



def make_profile(info: HardwareInfo) -> HardwareProfile:
    backend = build_backend_name(info.backend)
    return HardwareProfile(
        os=info.system,
        arch=info.machine,
        chip_name=info.chip,
        total_memory_gb=info.total_memory_gb,
        backend=backend,
        cuda_version=info.cuda_version,
        recommended_cache_type=recommended_cache_type(backend, info.total_memory_gb),
        max_safe_context=max_safe_context(info.total_memory_gb, backend),
    )
