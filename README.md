# tq

`tq` is a CLI-first workflow tool for building, validating, and running TurboQuant-enabled `llama.cpp` locally.

## Getting started

Install from source:

```bash
pip install .
```

Then:

```bash
tq install
tq doctor
tq model download 'https://example.com/model.gguf'
tq daemon start
tq daemon status
tq open
```

If you want the optional replacement web UI:

```bash
tq install --with-web-ui
```

## Commands

### Install and health

```bash
tq install
tq install --with-web-ui
tq doctor
```

### Model management

```bash
tq model list
tq model add /path/to/model.gguf
tq model scan ~/models
tq model default my-model
tq model download 'https://example.com/model.gguf'
tq model remove my-model
```

### Daemon management

```bash
tq daemon start
tq daemon stop
tq daemon restart
tq daemon status
tq daemon logs
tq daemon foreground-cmd
tq open
```

### Web UI helpers

```bash
tq web status
tq web enable
tq web disable
tq web start
tq web stop
```

### TUI

```bash
tq
tq run
tq models
tq bench
```

## Special thanks

`tq` builds on top of upstream work from the following projects:

- `llama.cpp`: <https://github.com/ggml-org/llama.cpp>
- `llama-cpp-turboquant`: <https://github.com/TheTom/llama-cpp-turboquant>
- `turboquant_plus`: <https://github.com/TheTom/turboquant_plus>
- `llama.ui`: <https://github.com/olegshulyakov/llama.ui>

## Development

See [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

MIT
