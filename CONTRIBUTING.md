# Contributing

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
pip install pytest build
pytest -q
python -m build
```

## Guidelines

- Keep CLI behavior deterministic and script-friendly.
- Prefer verification over assumption when dealing with llama.cpp/TurboQuant capabilities.
- Do not invent benchmark or runtime stats.
- Keep dependencies lightweight unless they materially improve usability.
