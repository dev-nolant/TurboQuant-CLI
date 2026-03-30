from __future__ import annotations

from textual.app import App

from tq.screens.bench import BenchScreen
from tq.screens.dashboard import DashboardScreen
from tq.screens.install import InstallScreen
from tq.screens.models import ModelsScreen
from tq.screens.run import RunScreen


class TQApp(App[None]):
    CSS = """
    Screen {
        layout: vertical;
    }

    Horizontal {
        height: auto;
    }

    Vertical {
        height: 1fr;
    }

    TabbedContent {
        height: 1fr;
    }

    TabPane {
        padding: 1 1;
    }

    VerticalScroll {
        height: 1fr;
    }

    #model-actions, #server-actions, #chat-actions {
        layout: horizontal;
        height: auto;
        margin: 1 0;
    }

    #model-actions Button, #server-actions Button, #chat-actions Button {
        margin-right: 1;
    }

    Input, Select, Checkbox, Button {
        margin: 0 0 1 0;
    }

    TextArea {
        height: 8;
        border: round $accent;
        margin: 1 0;
    }

    #install-log, #bench-log, #run-log, #models-log {
        height: 1fr;
        border: round $accent;
    }

    #hardware-summary, #install-summary, #server-summary,
    #hardware-step, #dependency-step, #status-step, #verify-step, #steps-table,
    #stats, #metrics, #bench-summary, #models-summary, #install-banner,
    #model-summary, #chat-output, #verification-summary, #verify-summary {
        border: round $primary;
        padding: 1 2;
        margin: 1;
    }
    """

    SCREENS = {
        "dashboard": DashboardScreen,
        "install": InstallScreen,
        "models": ModelsScreen,
        "bench": BenchScreen,
        "run": RunScreen,
    }

    def __init__(self, initial_screen: str = "dashboard") -> None:
        super().__init__()
        self.initial_screen = initial_screen

    def on_mount(self) -> None:
        self.push_screen(self.initial_screen)

    def open_screen(self, name: str) -> None:
        current = self.screen
        if current is not None:
            self.pop_screen()
        self.push_screen(name)
