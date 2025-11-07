# pfig (**p**aper **fig**ures)

This is a small, opinionated library to facilitate the disciplined development and export of publication-ready figures using `matplotlib`, with a `tyro`-based CLI.

**Disclaimer**: I am writing this for my own use; for now, expect API breakage with no support commitment.

## End-to-end demo

```bash
git clone https://github.com/yberreby/pfig.git
cd pfig/demo
uv run pfig generate lorenz
```

## Features

- **Decoupled computation and rendering.**
  - Code that _prepares a figure's data_ is kept distinct from _code that turns this data into beautiful visuals_.
  - This is especially useful when a figure's code is computation-heavy. Don't rerun expensive data processing if you're just tweaking the style!
- **Rich metadata support.**
  - In user code, keep track of the parameters used to produce a figure in a disciplined manner.
  - Automatically benefit from tracking of additional metadata: git commit, export datetime, hostname...
- **Full history tracking.**
  - Don't accidentally overwrite valuable data.
  - Each figure export results in the creation of a separate directory.
- **Validation and safety.**
  - Directory names use readable formats without shell-problematic characters.
  - Automatic validation ensures directory names match their metadata contents.

## Usage

### As a dependency

1. Install pfig:
```bash
uv add pfig
```

2. Create a `figures.py` or `figures/` module in your project with a `FIGURES` list:

```python
# figures.py
from pfig import PFigure, ComputeResult, PlotResult
import matplotlib.pyplot as plt

def my_compute() -> ComputeResult:
    data = {"x": [1, 2, 3], "y": [1, 4, 9]}
    return ComputeResult(data=data, metadata={})

def my_serialize(data, output_dir):
    # Save data to output_dir
    pass

def my_deserialize(data_dir):
    # Load data from data_dir
    return data

def my_plot(data, compute_metadata) -> PlotResult:
    fig, ax = plt.subplots()
    ax.plot(data["x"], data["y"])
    return PlotResult(figure=fig, metadata={})

my_figure = PFigure(
    name="my_figure",
    compute=my_compute,
    serialize=my_serialize,
    deserialize=my_deserialize,
    plot=my_plot,
)

FIGURES = [my_figure]
```

3. Use the CLI:
```bash
uv run pfig list           # List available figures
uv run pfig generate my_figure  # Compute and render
uv run pfig compute my_figure   # Just compute
uv run pfig render my_figure    # Just render
```

### Complete example

See `./demo/` for a complete working example with multiple figures.

## Development commands

```bash
# format
uv run ruff format
# lint
uv run ruff check --fix
# type check
uv run basedpyright
# test
uv run pytest
# all of the above
uv run just
# generate demo figure (defaults to lorenz)
uv run just demo
uv run just demo bifurcation
```
