from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import AsyncIterator

from tq.core.config import AppConfig, BenchReport, BenchResult, model_key
from tq.core.hardware import detect_hardware, make_profile
from tq.core.installer import stream_process


async def run_real_benchmark(config: AppConfig) -> AsyncIterator[str]:
    cli = config.install.cli_binary
    model = Path(config.server.model_path).expanduser()
    if not cli.exists():
        raise FileNotFoundError(f"llama-cli not found at {cli}")
    if not model.exists():
        raise FileNotFoundError(f"model not found at {model}")

    hw = detect_hardware()
    profile = make_profile(hw)
    config.hardware_profile = profile
    config.save()

    results: list[BenchResult] = []
    raw_dir = config.cache_dir() / "bench"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{model_key(model)}.log"
    raw_lines: list[str] = []

    for cache_type, ratio in (("turbo2", 6.4), ("turbo3", 4.9), ("turbo4", 3.8)):
        yield f"running benchmark for {cache_type}"
        prefill_tps, decode_tps, lines = await _measure_cli_run(config, cache_type)
        raw_lines.extend([f"## {cache_type}", *lines, ""])
        if prefill_tps <= 0.0 and decode_tps <= 0.0:
            raise RuntimeError(f"unable to extract real throughput for {cache_type}")
        results.append(
            BenchResult(
                cache_type=cache_type,
                compression_ratio=ratio,
                prefill_tps=prefill_tps,
                decode_tps=decode_tps,
            )
        )
        yield f"{cache_type}: prefill={prefill_tps:.2f} t/s decode={decode_tps:.2f} t/s"

    raw_path.write_text("\n".join(raw_lines))
    report = BenchReport(
        model=str(model),
        arch=profile.arch,
        hardware=profile,
        results=results,
        recommendation=_recommend(results),
        timestamp=datetime.now(UTC).isoformat(),
        raw_log_path=str(raw_path),
    )
    config.last_bench_results[model_key(model)] = report
    config.save()
    yield f"recommendation: {report.recommendation}"
    yield f"raw benchmark log: {raw_path}"


async def _measure_cli_run(config: AppConfig, cache_type: str) -> tuple[float, float, list[str]]:
    cli = config.install.cli_binary
    model = Path(config.server.model_path).expanduser()
    prompt = "Write one sentence about KV cache compression."
    cmd = [
        str(cli),
        "-m",
        str(model),
        "-p",
        prompt,
        "-n",
        "64",
        "-c",
        str(config.server.context_size),
        "--kv-cache-type-k",
        cache_type,
        "--kv-cache-type-v",
        cache_type,
        "-no-cnv",
    ]
    if config.server.sparse_v:
        cmd.append("--sparse-v")

    lines: list[str] = []
    async for line in stream_process(cmd):
        lines.append(line)
    prefill, decode = _extract_tps(lines)
    return prefill, decode, lines



def _extract_tps(lines: list[str]) -> tuple[float, float]:
    prefill = 0.0
    decode = 0.0
    patterns = [
        re.compile(r"prompt eval.*?([0-9]+(?:\.[0-9]+)?)\s*tokens/s", re.IGNORECASE),
        re.compile(r"prompt eval.*?([0-9]+(?:\.[0-9]+)?)\s*t/s", re.IGNORECASE),
        re.compile(r"eval.*?([0-9]+(?:\.[0-9]+)?)\s*tokens/s", re.IGNORECASE),
        re.compile(r"eval.*?([0-9]+(?:\.[0-9]+)?)\s*t/s", re.IGNORECASE),
    ]
    for line in lines:
        if prefill == 0.0 and "prompt eval" in line.lower():
            for pattern in patterns[:2]:
                match = pattern.search(line)
                if match:
                    prefill = float(match.group(1))
                    break
        if " eval" in line.lower() or line.lower().startswith("eval"):
            for pattern in patterns[2:]:
                match = pattern.search(line)
                if match:
                    decode = float(match.group(1))
                    break
    return prefill, decode



def _recommend(results: list[BenchResult]) -> str:
    if not results:
        raise RuntimeError("no benchmark results")
    best = max(results, key=lambda r: (r.compression_ratio * 1000.0) + r.decode_tps)
    return best.cache_type


async def run_command_benchmark(command: list[str], cwd: Path | None = None) -> AsyncIterator[str]:
    async for line in stream_process(command, cwd=cwd):
        yield line
