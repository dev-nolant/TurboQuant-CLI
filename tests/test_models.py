from pathlib import Path

from tq.core.models import ModelRegistry, format_size, infer_name


def test_infer_name() -> None:
    assert infer_name(Path('/tmp/foo/bar/model-name.gguf')) == 'model-name'


def test_format_size() -> None:
    assert format_size(1024).endswith('KB')


def test_registry_defaults() -> None:
    registry = ModelRegistry()
    assert registry.models == []
    assert registry.default_model is None
