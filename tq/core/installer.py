from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
from pathlib import Path
from typing import AsyncIterator

from tq.core.binary_probe import probe_binary
from tq.core.config import AppConfig, InstallStepStatus
from tq.core.hardware import HardwareInfo

REPO_URL = "https://github.com/TheTom/llama-cpp-turboquant"
REPO_BRANCH = "feature/turboquant-kv-cache"
VALIDATION_REPO = "https://github.com/TheTom/turboquant_plus"


async def stream_process(command: list[str], cwd: Path | None = None) -> AsyncIterator[str]:
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert process.stdout is not None
    async for raw in process.stdout:
        yield raw.decode(errors="replace").rstrip()
    code = await process.wait()
    if code != 0:
        raise RuntimeError(f"command failed ({code}): {' '.join(command)}")



def _git(args: list[str], cwd: Path) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.STDOUT).strip()
    except Exception:
        return ""



def _set_step(config: AppConfig, name: str, status: InstallStepStatus, detail: str = "") -> None:
    for step in config.install.steps:
        if step.name == name:
            step.status = status
            step.detail = detail
            config.save()
            return



def _binary_candidates(install_path: Path) -> list[Path]:
    return [
        install_path / "build" / "bin" / "llama-server",
        install_path / "build" / "bin" / "llama-server.exe",
        install_path / "build" / "bin" / "server",
    ]



def refresh_install_metadata(config: AppConfig) -> None:
    install = config.install
    for candidate in _binary_candidates(install.install_path):
        if candidate.exists():
            install.binary_dir = candidate.parent
            install.binary_name = candidate.name
            break
    cli_candidate = install.binary_dir / install.cli_name
    if not cli_candidate.exists():
        alt = install.binary_dir / ("llama-cli.exe" if install.binary_name.endswith(".exe") else "llama-cli")
        if alt.exists():
            install.cli_name = alt.name
    if install.install_path.exists():
        commit = _git(["rev-parse", "--short", "HEAD"], cwd=install.install_path)
        install.last_commit = commit or install.last_commit
    if install.server_binary.exists():
        caps = probe_binary(install.server_binary)
        install.help_cache = caps.help_text
        install.turboquant_verified = caps.supports_turboquant and caps.supports_cache_type_flags
        install.sparse_v_verified = caps.supports_sparse_v
    config.save()



def detect_install_status(config: AppConfig) -> dict[str, str | bool | None]:
    refresh_install_metadata(config)
    install = config.install
    return {
        "repo_exists": (install.install_path / ".git").exists(),
        "binary_exists": install.server_binary.exists(),
        "cli_exists": install.cli_binary.exists(),
        "repo_dir": str(install.install_path),
        "binary_path": str(install.server_binary),
        "cli_path": str(install.cli_binary),
        "commit": install.last_commit,
        "source": install.source,
        "turboquant_verified": install.turboquant_verified,
        "sparse_v_verified": install.sparse_v_verified,
    }


async def ensure_clone(config: AppConfig) -> AsyncIterator[str]:
    repo_dir = config.install.install_path
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    if (repo_dir / ".git").exists():
        _set_step(config, "clone", "skipped", "repository already present")
        yield f"✓ repo already present: {repo_dir}"
        refresh_install_metadata(config)
        return
    _set_step(config, "clone", "running", "cloning llama.cpp turboquant fork")
    async for line in stream_process(["git", "clone", "--branch", REPO_BRANCH, REPO_URL, str(repo_dir)]):
        yield line
    _set_step(config, "clone", "done", f"cloned into {repo_dir}")
    refresh_install_metadata(config)



def cmake_configure_command(info: HardwareInfo) -> list[str]:
    flags = ["cmake", "-B", "build", "-DCMAKE_BUILD_TYPE=Release"]
    if info.backend == "metal":
        flags.append("-DGGML_METAL=ON")
    elif info.backend == "cuda":
        flags.append("-DGGML_CUDA=ON")
    return flags


async def build_repo(config: AppConfig, info: HardwareInfo) -> AsyncIterator[str]:
    repo_dir = config.install.install_path
    if config.install.server_binary.exists() and config.install.cli_binary.exists():
        caps = probe_binary(config.install.server_binary)
        if caps.supports_turboquant and caps.supports_cache_type_flags:
            _set_step(config, "build", "skipped", "validated TurboQuant-capable binaries already exist")
            yield f"✓ binaries already exist: {config.install.server_binary}"
            refresh_install_metadata(config)
            return
        yield "existing binaries found but TurboQuant support is not proven; rebuilding"
    _set_step(config, "build", "running", f"building for backend={info.backend}")
    async for line in stream_process(cmake_configure_command(info), cwd=repo_dir):
        yield line
    build_tool = ["cmake", "--build", "build", "-j"]
    async for line in stream_process(build_tool, cwd=repo_dir):
        yield line
    config.install.source = "built"
    config.install.binary_dir = repo_dir / "build" / "bin"
    refresh_install_metadata(config)
    caps = probe_binary(config.install.server_binary)
    if not caps.supports_cache_type_flags:
        _set_step(config, "build", "failed", "llama-server missing --cache-type-k/--cache-type-v flags")
        raise RuntimeError("built llama-server is missing cache type flags")
    if not caps.supports_turboquant:
        _set_step(config, "build", "failed", "llama-server help does not expose turbo2/turbo3/turbo4")
        raise RuntimeError("built llama-server does not expose turboquant cache types in --help")
    config.install.help_cache = caps.help_text
    config.install.turboquant_verified = True
    config.install.sparse_v_verified = caps.supports_sparse_v
    detail = "TurboQuant support verified"
    if caps.supports_sparse_v:
        detail += "; sparse-v detected"
    _set_step(config, "build", "done", detail)
    config.save()


async def validate_build(config: AppConfig) -> AsyncIterator[str]:
    validation_dir = config.install.validation_repo
    if not validation_dir.exists():
        async for line in stream_process(["git", "clone", VALIDATION_REPO, str(validation_dir)]):
            yield line
    _set_step(config, "validate", "running", "running turboquant_plus pytest suite")
    python = shutil.which("python3") or shutil.which("python") or "python3"
    async for line in stream_process([python, "-m", "pip", "install", "-e", ".", "pytest"], cwd=validation_dir):
        yield line
    async for line in stream_process([python, "-m", "pytest"], cwd=validation_dir):
        yield line
    _set_step(config, "validate", "done", "validation passed")



def estimate_progress_from_line(line: str) -> int | None:
    match = re.search(r"\[(\d+)%\]", line)
    if match:
        return int(match.group(1))
    return None
