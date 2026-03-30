from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Log, Static

from tq.core.benchmarker import run_real_benchmark
from tq.core.config import AppConfig, model_key


class BenchScreen(Screen[None]):
    BINDINGS = [("q", "app.open_screen('dashboard')", "Dashboard")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            yield Static("Latest report: none", id="bench-summary")
            yield Log(id="bench-log")
        yield Footer()

    def on_mount(self) -> None:
        self.render_last_report()
        asyncio.create_task(self.run_bench())

    def render_last_report(self) -> None:
        config = AppConfig.load()
        key = model_key(config.server.model_path) if config.server.model_path else None
        report = config.last_bench_results.get(key) if key else None
        if report is None:
            self.query_one("#bench-summary", Static).update("Latest report: none")
            return
        lines = [
            f"Latest report: {report.timestamp}",
            f"recommended: {report.recommendation}",
            f"raw log: {report.raw_log_path or 'none'}",
        ]
        for result in report.results:
            lines.append(
                f"{result.cache_type}: {result.compression_ratio}x prefill={result.prefill_tps:.2f} decode={result.decode_tps:.2f}"
            )
        self.query_one("#bench-summary", Static).update("\n".join(lines))

    async def run_bench(self) -> None:
        log = self.query_one("#bench-log", Log)
        try:
            async for line in run_real_benchmark(AppConfig.load()):
                log.write_line(line)
            self.render_last_report()
        except Exception as exc:
            log.write_line(f"ERROR: {exc}")
            log.write_line("No synthetic stats are shown. Benchmark failed because real measurements were unavailable.")
