from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from tq.core.config import AppConfig
from tq.core.hardware import detect_hardware, make_profile
from tq.core.installer import detect_install_status
from tq.core.models import default_model, format_size, list_models


class DashboardScreen(Screen[None]):
    BINDINGS = [
        ("i", "app.open_screen('install')", "Install"),
        ("m", "app.open_screen('models')", "Models"),
        ("b", "app.open_screen('bench')", "Bench"),
        ("r", "app.open_screen('run')", "Run"),
        ("d", "action_refresh", "Refresh"),
        ("q", "app.quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical():
                yield Static(id="hardware-summary")
            with Vertical():
                yield Static(id="install-summary")
            with Vertical():
                yield Static(id="server-summary")
        with Horizontal():
            with Vertical():
                yield Static(id="models-summary")
            with Vertical():
                yield Static(id="verify-summary")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_panels()

    def action_refresh(self) -> None:
        self.refresh_panels()

    def refresh_panels(self) -> None:
        config = AppConfig.load()
        hw = detect_hardware()
        profile = make_profile(hw)
        install = detect_install_status(config)
        models = list_models()
        current_model = default_model()

        self.query_one("#hardware-summary", Static).update(
            f"Hardware\nchip: {hw.chip}\nbackend: {hw.backend}\nos: {hw.system}/{hw.machine}\nmem: {hw.vram_summary}\nrecommended cache: {profile.recommended_cache_type}\nmax safe ctx: {profile.max_safe_context}"
        )
        self.query_one("#install-summary", Static).update(
            "Install\n"
            f"repo: {'yes' if install['repo_exists'] else 'no'}\n"
            f"server: {'yes' if install['binary_exists'] else 'no'}\n"
            f"cli: {'yes' if install['cli_exists'] else 'no'}\n"
            f"commit: {install['commit'] or 'unknown'}\n"
            f"path: {install['binary_path']}"
        )
        self.query_one("#server-summary", Static).update(
            "Server\n"
            f"running: {config.server.running}\n"
            f"pid: {config.server.pid}\n"
            f"host: {config.server.host}:{config.server.port}\n"
            f"cache: {config.server.cache_type}\n"
            f"model: {config.server.model_path or 'unset'}\n"
            "keys: [i] install  [m] models  [b] bench  [r] run"
        )
        model_lines = [f"Models: {len(models)} registered"]
        if current_model:
            model_lines.append(f"default: {current_model.name} ({format_size(current_model.size_bytes)})")
        else:
            model_lines.append("default: none")
        for model in models[:5]:
            model_lines.append(f"- {model.name} | {format_size(model.size_bytes)}")
        self.query_one("#models-summary", Static).update("\n".join(model_lines))
        self.query_one("#verify-summary", Static).update(
            "Verification\n"
            f"turboquant: {'verified' if install['turboquant_verified'] else 'not verified'}\n"
            f"sparse-v: {'verified' if install['sparse_v_verified'] else 'not verified'}\n"
            f"chat endpoint: {config.server.detected_endpoint}"
        )
