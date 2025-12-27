# anki-cards-from-kindle-highlights

Generate Anki cards from Kindle highlights using LLMs.

## Installation

```bash
# Clone the repository
git clone https://github.com/fabiansvara/anki-cards-from-kindle-highlights.git
cd anki-cards-from-kindle-highlights

# Create a virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install in development mode with dev dependencies
pip install -e ".[dev]"
```

## Usage

```bash
anki-cards-from-kindle-highlights --help
```

## Development

### Setup

```bash
pip install -e ".[dev]"
pre-commit install
```

### Commands

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov

# Lint and format
ruff check .
ruff format .

# Type check
mypy src
```

## License

GPL-3.0 - see [LICENSE](LICENSE).
