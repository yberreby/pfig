all: lint format test typecheck

lint:
    uv run ruff check --fix

format:
    uv run ruff format

test:
    uv run -m pytest

typecheck:
    uv run basedpyright

demo figure='lorenz':
    cd demo && uv run pfig generate {{figure}}
