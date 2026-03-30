from pathlib import Path

from tq.core.webui_server import create_app


def test_create_app() -> None:
    app = create_app(Path('.'), 'http://127.0.0.1:9999')
    assert app is not None
