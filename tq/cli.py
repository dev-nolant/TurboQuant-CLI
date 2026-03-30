from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from tq.app import TQApp
from tq.core.binary_probe import probe_binary
from tq.core.daemon import logs_path, print_foreground_command, restart as daemon_restart, start as daemon_start, status as daemon_status, stop as daemon_stop
from tq.core.install_cli import run_install
from tq.core.models import (
    default_model,
    download_model,
    format_size,
    list_models,
    remove_model,
    scan_directory,
    set_default_model,
    upsert_model,
)
from tq.core.webui import disable_webui, enable_webui, open_webui, start_proxy, status as webui_status, stop_proxy

cli = typer.Typer(add_completion=False, no_args_is_help=False)
model_cli = typer.Typer(help="Manage GGUF models")
daemon_cli = typer.Typer(help="Run llama-server in the background")
web_cli = typer.Typer(help="Optional web UI helpers")
cli.add_typer(model_cli, name="model")
cli.add_typer(daemon_cli, name="daemon")
cli.add_typer(web_cli, name="web")


def _run(screen: str | None = None) -> None:
    app = TQApp(initial_screen=screen or "dashboard")
    app.run()


@cli.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        _run()


@cli.command()
def install(with_web_ui: bool = typer.Option(False, "--with-web-ui", help="Install optional llama.ui web frontend")) -> None:
    asyncio.run(run_install(with_web_ui=with_web_ui))


@cli.command()
def bench() -> None:
    _run("bench")


@cli.command()
def run() -> None:
    _run("run")


@cli.command()
def models() -> None:
    _run("models")


@cli.command()
def open() -> None:
    print(open_webui())


@cli.command()
def doctor() -> None:
    from tq.core.config import AppConfig
    from tq.core.hardware import dependency_status, detect_hardware, make_profile
    from tq.core.installer import detect_install_status

    config = AppConfig.load()
    hw = detect_hardware()
    profile = make_profile(hw)
    install = detect_install_status(config)
    current = default_model()
    print(f"hardware: {hw.chip} backend={hw.backend} mem={hw.vram_summary}")
    print(f"recommended cache: {profile.recommended_cache_type} max_ctx={profile.max_safe_context}")
    print(f"repo: {install['repo_exists']} server: {install['binary_exists']} cli: {install['cli_exists']}")
    print(f"turboquant verified: {install['turboquant_verified']}")
    print(f"sparse-v verified: {install['sparse_v_verified']}")
    print(f"web ui installed: {config.install.web_ui_installed}")
    print(f"server path: {install['binary_path']}")
    print(f"cli path: {install['cli_path']}")
    print(f"default model: {current.path if current else 'none'}")
    if install['binary_exists']:
        caps = probe_binary(Path(str(install['binary_path'])))
        print(f"binary cache flags: {caps.supports_cache_type_flags}")
        print(f"binary turboquant: {caps.supports_turboquant}")
        print(f"binary sparse-v: {caps.supports_sparse_v}")
    print("dependencies:")
    for name, (ok, hint) in dependency_status().items():
        print(f"  {'OK' if ok else 'MISSING'} {name}: {hint if not ok else ''}")


@daemon_cli.command("start")
def daemon_start_cmd() -> None:
    info = daemon_start()
    print("started")
    print(f"pid: {info['pid']}")
    print(f"ui_pid: {info['ui_pid']}")
    print(f"url: {info['url']}")
    print(f"backend_url: {info['backend_url']}")
    print(f"model: {info['model']}")
    print(f"cache: {info['cache']}")
    print(f"ctx: {info['ctx']}")
    print(f"log: {info['log']}")
    print(f"ui_log: {info['ui_log']}")


@daemon_cli.command("stop")
def daemon_stop_cmd() -> None:
    info = daemon_stop()
    print("stopped")
    print(f"running: {info['running']}")
    print(f"ui_running: {info['ui_running']}")


@daemon_cli.command("restart")
def daemon_restart_cmd() -> None:
    info = daemon_restart()
    print("restarted")
    print(f"pid: {info['pid']}")
    print(f"ui_pid: {info['ui_pid']}")
    print(f"url: {info['url']}")


@daemon_cli.command("status")
def daemon_status_cmd() -> None:
    info = daemon_status()
    for key in ("running", "ui_running", "pid", "ui_pid", "url", "backend_url", "model", "cache", "ctx", "log", "ui_log"):
        print(f"{key}: {info[key]}")
    if info.get("command"):
        print("command:")
        print(" ".join(info["command"]))


@daemon_cli.command("logs")
def daemon_logs_cmd() -> None:
    print(logs_path())


@daemon_cli.command("foreground-cmd")
def daemon_foreground_cmd() -> None:
    print(print_foreground_command())


@web_cli.command("status")
def web_status_cmd() -> None:
    info = webui_status()
    for key, value in info.items():
        print(f"{key}: {value}")


@web_cli.command("enable")
def web_enable_cmd() -> None:
    config = enable_webui()
    print(f"enabled: {config.install.web_ui_installed}")


@web_cli.command("disable")
def web_disable_cmd() -> None:
    config = disable_webui()
    print(f"enabled: {config.install.web_ui_installed}")


@web_cli.command("start")
def web_start_cmd() -> None:
    info = start_proxy()
    print(f"url: {info['url']}")
    print(f"pid: {info['pid']}")
    print(f"log: {info['log']}")


@web_cli.command("stop")
def web_stop_cmd() -> None:
    stop_proxy()
    print("stopped")


@model_cli.command("list")
def model_list() -> None:
    current = default_model()
    for model in list_models():
        marker = "*" if current and current.path == model.path else " "
        print(f"{marker} {model.name}\t{format_size(model.size_bytes)}\t{model.path}")


@model_cli.command("add")
def model_add(path: str) -> None:
    model = upsert_model(Path(path))
    print(f"added {model.name}: {model.path}")


@model_cli.command("scan")
def model_scan(directory: str) -> None:
    found = scan_directory(Path(directory))
    print(f"registered {len(found)} model(s)")


@model_cli.command("default")
def model_default(name_or_path: str) -> None:
    model = set_default_model(name_or_path)
    print(f"default model: {model.name} -> {model.path}")


@model_cli.command("remove")
def model_remove(name_or_path: str) -> None:
    removed = remove_model(name_or_path)
    print("removed" if removed else "not found")


@model_cli.command("download")
def model_download(url: str, filename: str | None = None) -> None:
    async def _run_download() -> None:
        last_percent = -1
        async for downloaded, total in download_model(url, filename):
            if total:
                percent = int(downloaded * 100 / total)
                if percent != last_percent:
                    print(f"{percent}% {downloaded}/{total}")
                    last_percent = percent
            else:
                print(f"downloaded {downloaded} bytes")
    asyncio.run(_run_download())


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
