from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

from tq.core.config import AppConfig
from tq.core.server import LlamaServerManager
from tq.core.webui import start_proxy, stop_proxy


class DaemonError(RuntimeError):
    pass



def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False



def status() -> dict[str, object]:
    config = AppConfig.load()
    pid = config.server.pid
    alive = _pid_alive(pid)
    ui_alive = _pid_alive(config.server.ui_pid)
    return {
        "running": alive,
        "ui_running": ui_alive,
        "pid": pid,
        "ui_pid": config.server.ui_pid,
        "url": f"http://{config.server.host}:{config.server.port}",
        "backend_url": f"http://{config.server.host}:{config.server.backend_port}",
        "model": config.server.model_path,
        "cache": config.server.cache_type,
        "ctx": config.server.context_size,
        "log": str(config.server.detached_log),
        "ui_log": str(config.server.ui_log),
        "command": config.server.last_command,
    }



def start(foreground: bool = False) -> dict[str, object]:
    config = AppConfig.load()
    current = status()
    if current["running"]:
        raise DaemonError("daemon already running")
    manager = LlamaServerManager(config)
    refreshed = AppConfig.load()
    cmd = manager.build_command(use_backend_port=refreshed.install.web_ui_installed)
    log_path = config.server.detached_log
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "ab") as log_fp:
        if foreground:
            raise DaemonError("foreground mode should be run directly via printed command")
        process = subprocess.Popen(
            cmd,
            stdout=log_fp,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    config.server.pid = process.pid
    config.server.running = True
    config.server.last_command = cmd
    config.server.pid_file.write_text(str(process.pid))
    config.save()
    if config.install.web_ui_installed:
        start_proxy()
    return status()



def stop() -> dict[str, object]:
    config = AppConfig.load()
    pid = config.server.pid
    if not _pid_alive(pid):
        config.server.running = False
        config.server.pid = None
        config.save()
        stop_proxy()
        return status()
    assert pid is not None
    os.kill(pid, signal.SIGTERM)
    config.server.running = False
    config.server.pid = None
    if config.server.pid_file.exists():
        config.server.pid_file.unlink()
    config.save()
    stop_proxy()
    return status()



def restart() -> dict[str, object]:
    stop()
    return start()



def logs_path() -> Path:
    return AppConfig.load().server.detached_log



def print_foreground_command() -> str:
    config = AppConfig.load()
    manager = LlamaServerManager(config)
    return " ".join(manager.build_command(use_backend_port=config.install.web_ui_installed))
