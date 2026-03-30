from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Log, ProgressBar, Static

from tq.core.models import (
    default_model,
    download_model,
    format_size,
    list_models,
    scan_directory,
    set_default_model,
)


class ModelsScreen(Screen[None]):
    BINDINGS = [("q", "app.open_screen('dashboard')", "Dashboard")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            yield Static(id="models-summary")
            yield Label("Scan directory")
            with Horizontal():
                yield Input(placeholder="/path/to/models", id="scan-dir")
                yield Button("Scan", id="scan")
            yield Label("Download model URL")
            with Horizontal():
                yield Input(placeholder="https://.../model.gguf", id="download-url")
                yield Button("Download", id="download")
            yield ProgressBar(total=100, id="download-progress")
            yield Label("Set default model by name or path")
            with Horizontal():
                yield Input(placeholder="model name or full path", id="default-model")
                yield Button("Set default", id="set-default")
            yield Log(id="models-log")
        yield Footer()

    def on_mount(self) -> None:
        self.render_models()

    def render_models(self) -> None:
        models = list_models()
        current = default_model()
        lines = [f"default: {current.name if current else 'none'}"]
        if not models:
            lines.append("no models registered")
            lines.append("use Scan, Download, or tq model add")
        else:
            for model in models:
                marker = "*" if current and current.path == model.path else "-"
                lines.append(f"{marker} {model.name} | {format_size(model.size_bytes)} | {model.path}")
        self.query_one("#models-summary", Static).update("\n".join(lines))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        log = self.query_one("#models-log", Log)
        if event.button.id == "scan":
            directory = self.query_one("#scan-dir", Input).value.strip()
            if not directory:
                log.write_line("scan path required")
                return
            try:
                found = scan_directory(Path(directory))
                log.write_line(f"registered {len(found)} model(s)")
                self.render_models()
            except Exception as exc:
                log.write_line(f"ERROR: {exc}")
        elif event.button.id == "set-default":
            name = self.query_one("#default-model", Input).value.strip()
            try:
                model = set_default_model(name)
                log.write_line(f"default model set to {model.name}")
                self.render_models()
            except Exception as exc:
                log.write_line(f"ERROR: {exc}")
        elif event.button.id == "download":
            url = self.query_one("#download-url", Input).value.strip()
            asyncio.create_task(self._download(url))

    async def _download(self, url: str) -> None:
        log = self.query_one("#models-log", Log)
        progress = self.query_one("#download-progress", ProgressBar)
        if not url:
            log.write_line("download url required")
            return
        try:
            async for downloaded, total in download_model(url):
                if total:
                    percent = int(downloaded * 100 / total)
                    progress.update(progress=percent)
                log.clear()
                if total:
                    log.write_line(f"downloading... {downloaded}/{total} bytes")
                else:
                    log.write_line(f"downloading... {downloaded} bytes")
            progress.update(progress=100)
            log.write_line("download complete")
            self.render_models()
        except Exception as exc:
            log.write_line(f"ERROR: {exc}")
