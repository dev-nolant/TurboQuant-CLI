from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Header, Input, Label, Log, Select, Static, TabbedContent, TabPane, TextArea

from tq.core.chat import completion
from tq.core.config import AppConfig
from tq.core.metrics import parse_prometheus_text, summarize_metrics
from tq.core.models import default_model, list_models, set_default_model
from tq.core.server import LlamaServerManager


class RunScreen(Screen[None]):
    BINDINGS = [("q", "app.open_screen('dashboard')", "Dashboard")]

    def compose(self) -> ComposeResult:
        config = AppConfig.load()
        models = list_models()
        current = default_model()
        options = [(model.name, model.path) for model in models] or [("<none>", "")]
        selected = current.path if current else (config.server.model_path if config.server.model_path else options[0][1])
        yield Header(show_clock=True)
        with TabbedContent(initial="model-tab"):
            with TabPane("Model", id="model-tab"):
                with VerticalScroll():
                    yield Label("Registered model")
                    yield Select(options, value=selected, id="model-select")
                    yield Label("Manual model path")
                    yield Input(value=config.server.model_path, id="model-path")
                    with Container(id="model-actions"):
                        yield Button("Use selected model", id="use-selected")
                        yield Button("Open models screen", id="open-models")
                    yield Static(id="model-summary")
            with TabPane("Server", id="server-tab"):
                with VerticalScroll():
                    yield Label("Host")
                    yield Input(value=config.server.host, placeholder="Host", id="host")
                    yield Label("Port")
                    yield Input(value=str(config.server.port), placeholder="Port", id="port")
                    yield Label("Context size")
                    yield Input(value=str(config.server.context_size), placeholder="Context size", id="context-size")
                    yield Label("Cache type")
                    yield Select(
                        [("turbo2", "turbo2"), ("turbo3", "turbo3"), ("turbo4", "turbo4")],
                        value=config.server.cache_type,
                        id="cache-type",
                    )
                    yield Checkbox("Enable Sparse-V", value=config.server.sparse_v, id="sparse-v")
                    with Container(id="server-actions"):
                        yield Button("Start server", id="start", variant="success")
                        yield Button("Stop server", id="stop", variant="warning")
                        yield Button("Refresh probes", id="refresh")
                    yield Static("Server status: idle", id="server-summary")
                    yield Static(id="verification-summary")
            with TabPane("Chat", id="chat-tab"):
                with VerticalScroll():
                    yield Static("Server chat output will appear here.", id="chat-output")
                    yield Label("Preset")
                    yield Select([("balanced", "balanced"), ("deterministic", "deterministic"), ("creative", "creative")], value=config.generation.preset, id="preset")
                    yield Label("Temperature")
                    yield Input(value=str(config.generation.temperature), id="temperature")
                    yield Label("Top-p")
                    yield Input(value=str(config.generation.top_p), id="top-p")
                    yield Label("Max tokens")
                    yield Input(value=str(config.generation.max_tokens), id="max-tokens")
                    yield TextArea("", id="chat-input")
                    with Container(id="chat-actions"):
                        yield Button("Send prompt", id="send-prompt", variant="primary")
                        yield Button("Clear chat", id="clear-chat")
            with TabPane("Stats", id="stats-tab"):
                with VerticalScroll():
                    yield Static("Stats: idle", id="stats")
                    yield Static("Metrics: idle", id="metrics")
                    yield Log(id="run-log")
        yield Footer()

    def on_mount(self) -> None:
        self.manager = LlamaServerManager(AppConfig.load())
        self._last_log_line = ""
        self.render_model_summary()
        self.render_verification_summary()
        asyncio.create_task(self.poll_stats())

    def render_model_summary(self) -> None:
        current = default_model()
        lines = []
        if current:
            lines.extend([
                f"default: {current.name}",
                f"path: {current.path}",
                f"size: {current.size_bytes} bytes",
            ])
        else:
            lines.append("No models registered. Use tq models or tq model add/scan/download.")
        self.query_one("#model-summary", Static).update("\n".join(lines))

    def render_verification_summary(self) -> None:
        config = AppConfig.load()
        lines = [
            f"turboquant verified: {config.install.turboquant_verified}",
            f"sparse-v verified: {config.install.sparse_v_verified}",
            f"detected chat endpoint: {config.server.detected_endpoint}",
            f"active cache type: {config.server.cache_type}",
        ]
        if config.server.last_command:
            lines.append("launch command:")
            lines.append(" ".join(config.server.last_command))
        self.query_one("#verification-summary", Static).update("\n".join(lines))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        log = self.query_one("#run-log", Log)
        if event.button.id == "use-selected":
            try:
                selected = self.query_one("#model-select", Select).value
                if selected:
                    set_default_model(str(selected))
                    self.query_one("#model-path", Input).value = str(selected)
                    self.manager.config = AppConfig.load()
                    self.render_model_summary()
                    self.render_verification_summary()
                    log.write_line(f"selected model: {selected}")
            except Exception as exc:
                log.write_line(f"ERROR: {exc}")
        elif event.button.id == "open-models":
            self.app.open_screen("models")
        elif event.button.id == "start":
            try:
                self._apply_form()
                self.manager.config = AppConfig.load()
                await self.manager.start()
                self.query_one("#server-summary", Static).update("Server status: started")
                self.render_verification_summary()
                log.write_line("llama-server started")
            except Exception as exc:
                log.write_line(f"ERROR: {exc}")
                self.query_one("#server-summary", Static).update(f"Server status: error: {exc}")
        elif event.button.id == "stop":
            await self.manager.stop()
            self.query_one("#server-summary", Static).update("Server status: stopped")
            log.write_line("llama-server stopped")
        elif event.button.id == "refresh":
            await self._refresh_stats()
        elif event.button.id == "send-prompt":
            await self._send_prompt()
        elif event.button.id == "clear-chat":
            self.query_one("#chat-output", Static).update("")
            self.query_one("#chat-input", TextArea).text = ""

    def _apply_form(self) -> None:
        config = AppConfig.load()
        selected = self.query_one("#model-select", Select).value
        manual_path = self.query_one("#model-path", Input).value.strip()
        config.server.model_path = manual_path or str(selected)
        config.server.host = self.query_one("#host", Input).value.strip() or config.server.host
        config.server.context_size = int(self.query_one("#context-size", Input).value.strip())
        config.server.port = int(self.query_one("#port", Input).value.strip())
        config.server.cache_type = self.query_one("#cache-type", Select).value
        config.server.sparse_v = self.query_one("#sparse-v", Checkbox).value
        config.generation.preset = self.query_one("#preset", Select).value
        config.generation.temperature = float(self.query_one("#temperature", Input).value.strip())
        config.generation.top_p = float(self.query_one("#top-p", Input).value.strip())
        config.generation.max_tokens = int(self.query_one("#max-tokens", Input).value.strip())
        if config.generation.preset == "deterministic":
            config.generation.temperature = 0.2
            config.generation.top_p = 0.9
        elif config.generation.preset == "creative":
            config.generation.temperature = 0.9
            config.generation.top_p = 0.95
        config.save()

    async def _send_prompt(self) -> None:
        output = self.query_one("#chat-output", Static)
        log = self.query_one("#run-log", Log)
        prompt = self.query_one("#chat-input", TextArea).text.strip()
        if not prompt:
            return
        try:
            self._apply_form()
            self.manager.config = AppConfig.load()
            response = await completion(self.manager.config, prompt)
            output.update(f"You:\n{prompt}\n\nModel:\n{response}")
            self.render_verification_summary()
        except Exception as exc:
            log.write_line(f"chat failed: {exc}")

    async def _refresh_stats(self) -> None:
        stats_widget = self.query_one("#stats", Static)
        metrics_widget = self.query_one("#metrics", Static)
        log = self.query_one("#run-log", Log)
        try:
            self.manager.config = AppConfig.load()
            stats = await self.manager.stats()
            probe = stats.get("probe", {})
            lines = ["Endpoint probes"]
            for path, info in probe.items():
                if info.get("ok"):
                    lines.append(f"{path} -> {info.get('status')} {info.get('content_type')}")
                else:
                    lines.append(f"{path} -> ERROR {info.get('error')}")
            if stats.get("command"):
                lines.append("")
                lines.append("Launch command:")
                lines.append(" ".join(stats["command"]))
            lines.append("")
            lines.append(f"TurboQuant verified: {stats.get('turboquant_verified')}")
            lines.append(f"Sparse-V verified: {stats.get('sparse_v_verified')}")
            stats_widget.update("\n".join(lines))
            metrics_text = stats.get("metrics_text")
            if isinstance(metrics_text, str):
                snapshot = parse_prometheus_text(metrics_text)
                summary = summarize_metrics(snapshot)
                if summary:
                    metrics_widget.update(
                        "Metrics:\n" + "\n".join(f"{k}: {v}" for k, v in summary.items())
                    )
                else:
                    metrics_widget.update("Metrics:\nNo recognized metrics found.")
            else:
                metrics_widget.update("Metrics:\ncurrently unavailable (common during startup/idle)")
            if self.manager.handle.logs:
                last = self.manager.handle.logs[-1]
                if last != self._last_log_line:
                    self._last_log_line = last
                    log.write_line(last)
        except Exception as exc:
            log.write_line(f"stats poll failed: {exc}")

    async def poll_stats(self) -> None:
        while True:
            await asyncio.sleep(2)
            if not AppConfig.load().server.running:
                continue
            await self._refresh_stats()
