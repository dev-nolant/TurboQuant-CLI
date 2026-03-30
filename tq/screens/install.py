from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, Log, ProgressBar, Static

from tq.core.config import AppConfig
from tq.core.hardware import dependency_status, detect_hardware, make_profile
from tq.core.installer import (
    build_repo,
    detect_install_status,
    ensure_clone,
    estimate_progress_from_line,
    refresh_install_metadata,
    validate_build,
)


def _status_icon(status: str) -> str:
    return {
        "pending": "…",
        "running": "▶",
        "done": "✓",
        "failed": "✗",
        "skipped": "↷",
    }.get(status, "?")


class InstallScreen(Screen[None]):
    BINDINGS = [("q", "app.open_screen('dashboard')", "Dashboard")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            with Horizontal():
                yield Static(id="hardware-step")
                yield Static(id="dependency-step")
            with Horizontal():
                yield Static(id="status-step")
                yield Static(id="verify-step")
            yield Static("INSTALL STATUS: starting", id="install-banner")
            yield Static(id="steps-table")
            yield Label("Build / validation output")
            yield ProgressBar(total=100, id="install-progress")
            yield Log(id="install-log", highlight=True)
        yield Footer()

    def on_mount(self) -> None:
        self.render_static_info()
        self.render_steps()
        asyncio.create_task(self.run_install_flow())

    def render_static_info(self) -> None:
        config = AppConfig.load()
        hw = detect_hardware()
        profile = make_profile(hw)
        deps = dependency_status()
        status = detect_install_status(config)
        dep_lines = "\n".join(
            f"{'✓' if ok else '✗'} {name}"
            for name, (ok, _hint) in deps.items()
        )
        self.query_one("#hardware-step", Static).update(
            f"Hardware\nchip: {hw.chip}\nbackend: {hw.backend}\nmem: {hw.vram_summary}\nrecommended cache: {profile.recommended_cache_type}\nmax safe ctx: {profile.max_safe_context}"
        )
        self.query_one("#dependency-step", Static).update(f"Dependencies\n{dep_lines}")
        self.query_one("#status-step", Static).update(
            "Current status\n"
            f"repo: {'yes' if status['repo_exists'] else 'no'}\n"
            f"server: {'yes' if status['binary_exists'] else 'no'}\n"
            f"cli: {'yes' if status['cli_exists'] else 'no'}\n"
            f"commit: {status['commit'] or 'unknown'}"
        )
        self.query_one("#verify-step", Static).update(
            "Verification\n"
            f"turboquant: {'verified' if status['turboquant_verified'] else 'not verified'}\n"
            f"sparse-v: {'verified' if status['sparse_v_verified'] else 'not verified'}\n"
            f"binary: {status['binary_path']}"
        )

    def render_steps(self) -> None:
        config = AppConfig.load()
        lines = ["Install steps"]
        for step in config.install.steps:
            lines.append(f"{_status_icon(step.status)} {step.name:<12} {step.status} {step.detail}".rstrip())
        self.query_one("#steps-table", Static).update("\n".join(lines))

    async def run_install_flow(self) -> None:
        config = AppConfig.load()
        config.hardware_profile = make_profile(detect_hardware())
        config.save()

        banner = self.query_one("#install-banner", Static)
        log = self.query_one("#install-log", Log)
        progress = self.query_one("#install-progress", ProgressBar)
        hw = detect_hardware()
        steps = [
            ("clone", ensure_clone(config), 15),
            ("build", build_repo(config, hw), 75),
            ("validate", validate_build(config), 100),
        ]
        current_floor = 0
        for name, step, ceiling in steps:
            banner.update(f"INSTALL STATUS: {name.upper()} RUNNING")
            self.render_steps()
            log.write_line(f"== {name} ==")
            try:
                async for line in step:
                    log.write_line(line)
                    inferred = estimate_progress_from_line(line)
                    if inferred is not None and ceiling > current_floor:
                        mapped = current_floor + int((ceiling - current_floor) * (inferred / 100.0))
                        progress.update(progress=mapped)
                current_floor = ceiling
                progress.update(progress=ceiling)
                self.render_steps()
                self.render_static_info()
            except Exception as exc:
                for step_state in config.install.steps:
                    if step_state.name == name:
                        step_state.status = "failed"
                        step_state.detail = str(exc)
                config.save()
                banner.update(f"INSTALL STATUS: FAILED AT {name.upper()}")
                log.write_line(f"ERROR during {name}: {exc}")
                refresh_install_metadata(config)
                self.render_steps()
                self.render_static_info()
                return

        refresh_install_metadata(config)
        for step in config.install.steps:
            if step.name == "done":
                step.status = "done"
                step.detail = "installation complete"
        config.save()
        banner.update("INSTALL COMPLETE — TurboQuant validation passed")
        log.write_line("Done. Available cache types: turbo2, turbo3, turbo4")
        log.write_line(f"Installed server: {config.install.server_binary}")
        log.write_line(f"Installed cli: {config.install.cli_binary}")
        log.write_line("Suggested next command: tq run")
        self.render_steps()
        self.render_static_info()
        progress.update(progress=100)
