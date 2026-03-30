from tq.core.webui import webui_dir


def test_webui_dir_name() -> None:
    assert 'llama-ui' in str(webui_dir())
