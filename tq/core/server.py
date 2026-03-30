from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from tq.core.binary_probe import probe_binary, verify_cache_mode
from tq.core.config import AppConfig


@dataclass
class ServerHandle:
    process: asyncio.subprocess.Process | None = None
    logs: list[str] = field(default_factory=list)


class LlamaServerManager:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.handle = ServerHandle()
        self._capture_task: asyncio.Task[None] | None = None

    def build_command(self, *, use_backend_port: bool = False) -> list[str]:
        self.config = AppConfig.load()
        server = self.config.server
        binary = self.config.install.server_binary
        if not binary.exists():
            raise FileNotFoundError(f"llama-server not found at {binary}")
        if not server.model_path:
            raise ValueError("model path is required")
        model = Path(server.model_path).expanduser()
        if not model.exists():
            raise FileNotFoundError(f"model not found at {model}")
        caps = probe_binary(binary)
        if not caps.supports_cache_type_flags:
            raise RuntimeError("llama-server binary lacks --cache-type-k/--cache-type-v flags")
        if not caps.supports_turboquant:
            raise RuntimeError("llama-server binary does not advertise turbo2/turbo3/turbo4 in --help")
        ok, reason = verify_cache_mode(binary, server.cache_type)
        if not ok:
            raise RuntimeError(f"selected cache mode not verified: {reason}")
        port = server.backend_port if use_backend_port else server.port
        cmd = [
            str(binary),
            "-m",
            str(model),
            "-c",
            str(server.context_size),
            "--host",
            server.host,
            "--port",
            str(port),
            "--cache-type-k",
            server.cache_type,
            "--cache-type-v",
            server.cache_type,
            "--metrics",
        ]
        if server.sparse_v and caps.supports_sparse_v:
            cmd.append("--sparse-v")
        self.config.server.last_command = cmd
        self.config.install.help_cache = caps.help_text
        self.config.install.turboquant_verified = True
        self.config.install.sparse_v_verified = caps.supports_sparse_v
        self.config.save()
        return cmd

    async def start(self) -> None:
        cmd = self.build_command(use_backend_port=self.config.install.web_ui_installed)
        self.config.server.detached_log.parent.mkdir(parents=True, exist_ok=True)
        log_fp = open(self.config.server.detached_log, "ab")
        self.handle.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self.config.server.running = True
        self.config.server.pid = self.handle.process.pid
        self.config.server.pid_file.write_text(str(self.handle.process.pid))
        self.config.save()
        self._capture_task = asyncio.create_task(self._capture_logs(log_fp))

    async def _capture_logs(self, log_fp: Any) -> None:
        process = self.handle.process
        try:
            if process is None or process.stdout is None:
                return
            async for raw in process.stdout:
                line = raw.decode(errors="replace").rstrip()
                self.handle.logs.append(line)
                log_fp.write((line + os.linesep).encode())
                log_fp.flush()
            await process.wait()
        finally:
            self.config.server.running = False
            self.config.server.pid = None
            with contextlib.suppress(FileNotFoundError):
                self.config.server.pid_file.unlink()
            self.config.save()
            log_fp.close()

    async def stop(self) -> None:
        process = self.handle.process
        pid = self.config.server.pid
        if process and process.returncode is None:
            process.terminate()
            await process.wait()
        elif pid:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGTERM)
        self.config.server.running = False
        self.config.server.pid = None
        with contextlib.suppress(FileNotFoundError):
            self.config.server.pid_file.unlink()
        self.config.save()

    async def _get(self, path: str) -> tuple[int, str, str]:
        server = AppConfig.load().server
        url = f"http://{server.host}:{server.backend_port if AppConfig.load().install.web_ui_installed else server.port}{path}"
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(url)
            return response.status_code, response.headers.get("content-type", ""), response.text

    async def probe_endpoints(self) -> dict[str, dict[str, str | int | bool]]:
        result: dict[str, dict[str, str | int | bool]] = {}
        for path in ("/health", "/metrics", "/", "/completion", "/v1/completions", "/v1/chat/completions"):
            try:
                if path in {"/completion", "/v1/completions", "/v1/chat/completions"}:
                    result[path] = {"ok": True, "status": 405, "content_type": "probe-skipped", "preview": "POST endpoint assumed"}
                    continue
                status, ctype, text = await self._get(path)
                result[path] = {
                    "ok": True,
                    "status": status,
                    "content_type": ctype,
                    "preview": "\n".join(text.splitlines()[:12])[:1000],
                }
            except Exception as exc:
                result[path] = {"ok": False, "error": str(exc)}
        return result

    async def metrics_text(self) -> str | None:
        server = AppConfig.load().server
        url = f"http://{server.host}:{server.backend_port if AppConfig.load().install.web_ui_installed else server.port}/metrics"
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
            if response.status_code == 503:
                return None
            response.raise_for_status()
            return response.text

    async def stats(self) -> dict[str, Any]:
        stats: dict[str, Any] = {"pid": self.config.server.pid, "running": self.config.server.running}
        stats["probe"] = await self.probe_endpoints()
        stats["command"] = self.config.server.last_command
        stats["turboquant_verified"] = self.config.install.turboquant_verified
        stats["sparse_v_verified"] = self.config.install.sparse_v_verified
        metrics_text = await self.metrics_text()
        if metrics_text is not None:
            stats["metrics_text"] = metrics_text
        return stats
