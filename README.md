# opendatabs/common

Shared Python utilities and code for ETL pipelines and data projects under the [OpenDataBS](https://github.com/opendatabs) umbrella.

This package is not published on PyPI and is intended to be installed directly from GitHub.

## Installation

You can install this package using either `pip` or [`uv`](https://github.com/astral-sh/uv).

### Install with `uv`

```bash
uv add "git+https://github.com/opendatabs/common"
```

You can also install a specific tag, commit, or branch:

```bash
# Install from a specific tag
uv add "git+https://github.com/opendatabs/common@v0.1.0"

# Install from a specific commit
uv add "git+https://github.com/opendatabs/common@<commit-sha>"

# Install from a branch (e.g., main)
uv add "git+https://github.com/opendatabs/common@main"
```

### Install with `pip`

```bash
pip install "git+https://github.com/opendatabs/common"
```

As with `uv`, you can install a specific reference:

```bash
# From a tag
pip install "git+https://github.com/opendatabs/common@v0.1.0"

# From a commit
pip install "git+https://github.com/opendatabs/common@<commit-sha>"

# From a branch
pip install "git+https://github.com/opendatabs/common@main"
```

## Development

To work on this package locally:

```bash
git clone https://github.com/opendatabs/common.git
uv sync
source .venv/bin/activate
```

## License

This project is licensed under the MIT License.

