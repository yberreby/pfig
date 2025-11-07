# pfig Demo

## Usage

```bash
uv run run.py list
uv run run.py generate bifurcation
uv run run.py render bifurcation
uv run run.py compute lorenz
uv run run.py clean --skip-confirm
```

## Structure

Each figure is a separate module with compute(), serialize(), deserialize(), plot() functions.
