from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import webbrowser
from pathlib import Path

from tq.core.config import AppConfig

LLAMA_UI_REPO = "https://github.com/olegshulyakov/llama.ui.git"


class WebUIError(RuntimeError):
    pass



def webui_dir() -> Path:
    path = AppConfig.cache_dir() / "webui" / "llama-ui"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path



def _sync_install_state() -> AppConfig:
    config = AppConfig.load()
    built = (webui_dir() / "dist").exists()
    config.install.web_ui_installed = built
    config.save()
    return config



def _write_runtime_env(target: Path) -> None:
    config = AppConfig.load()
    api_base = f"http://{config.server.host}:{config.server.backend_port}"
    env_file = target / ".env.local"
    env_file.write_text(f"VITE_API_BASE={api_base}\nVITE_BASE_URL={api_base}\n")



def enable_webui() -> AppConfig:
    config = _sync_install_state()
    if not config.install.web_ui_installed:
        raise WebUIError("web ui not installed")
    return config



def disable_webui() -> AppConfig:
    config = AppConfig.load()
    config.install.web_ui_installed = False
    config.save()
    return config



def install_llama_ui() -> Path:
    target = webui_dir()
    if target.exists() and (target / ".git").exists():
        subprocess.check_call(["git", "-C", str(target), "pull", "--ff-only"])
    else:
        if target.exists():
            shutil.rmtree(target)
        subprocess.check_call(["git", "clone", LLAMA_UI_REPO, str(target)])
    if not shutil.which("npm"):
        raise WebUIError("npm is required to build llama.ui")
    _write_runtime_env(target)
    subprocess.check_call(["npm", "ci"], cwd=target)
    subprocess.check_call(["npm", "run", "build"], cwd=target)
    _sync_install_state()
    return target



def status() -> dict[str, object]:
    config = _sync_install_state()
    target = webui_dir()
    built = (target / "dist").exists()
    return {
        "installed": target.exists(),
        "built": built,
        "path": str(target),
        "enabled": config.install.web_ui_installed,
    }



def open_webui() -> str:
    config = AppConfig.load()
    url = f"http://{config.server.host}:{config.server.port}"
    webbrowser.open(url)
    return url



def start_proxy() -> dict[str, object]:
    config = _sync_install_state()
    if not config.install.web_ui_installed:
        raise WebUIError("web ui not installed; run tq install --with-web-ui")
    target = webui_dir() / "dist"
    if not target.exists():
        raise WebUIError("llama.ui dist not built")
    log_path = config.server.ui_log
    log_path.parent.mkdir(parents=True, exist_ok=True)
    api_base = f"http://{config.server.host}:{config.server.backend_port}"
    cmd = [
        sys.executable,
        "-m",
        "tq.core.webui_server",
        "--host",
        config.server.host,
        "--port",
        str(config.server.port),
        "--static-dir",
        str(target),
        "--api-base",
        api_base,
    ]
    with open(log_path, "ab") as log_fp:
        process = subprocess.Popen(cmd, stdout=log_fp, stderr=subprocess.STDOUT, start_new_session=True)
    config.server.ui_pid = process.pid
    config.server.ui_pid_file.write_text(str(process.pid))
    config.save()
    return {"pid": process.pid, "url": f"http://{config.server.host}:{config.server.port}", "log": str(log_path)}



def stop_proxy() -> None:
    config = AppConfig.load()
    pid = config.server.ui_pid
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    config.server.ui_pid = None
    if config.server.ui_pid_file.exists():
        config.server.ui_pid_file.unlink()
    config.save()
