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
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\.venv\Scripts\Activate.ps1
# On macOS/Linux:
source .venv/bin/activate

# Install
pip install -e .

# Optional: Install in development mode
pip install -e .[dev]
```

## Usage

This tool uses a three-step workflow with a local SQLite database as the source of truth:

1. **Import** — Parse your Kindle `My Clippings.txt` and store highlights in a local database
2. **Generate** — Use an LLM to convert highlights into Anki card content (stored locally)
3. **Sync** — Push generated cards to Anki via [AnkiConnect](https://ankiweb.net/shared/info/2055492159)

### Prerequisites

- Set your OpenAI API key: `export OPENAI_API_KEY=sk-...`
- For syncing: Install [AnkiConnect](https://ankiweb.net/shared/info/2055492159) in Anki and keep Anki running

### Step 1: Import Clippings

Import highlights from your Kindle's `My Clippings.txt` file:

```bash
anki-cards-from-kindle-highlights import --clippings-file "/path/to/My Clippings.txt"
```

This parses the file and stores highlights in a local SQLite database. Duplicates are automatically skipped.

### Step 2: Generate Card Content

Generate Anki card content for unprocessed highlights using an LLM:

```bash
anki-cards-from-kindle-highlights generate
```

You'll be prompted to select which books to process. The LLM analyzes each highlight and creates appropriate card content based on learning patterns (distinctions, mental models, frameworks, definitions, etc.).

Options:
- `--model gpt-4o` — Choose the OpenAI model (default: `gpt-4o-2024-08-06`)
- `--max-generations 10` — Limit processing for testing
- `--parallel-requests 20` — Number of concurrent API requests (default: 10)

### Step 2 (Alternative): Batch Mode

For large numbers of highlights, use OpenAI's Batch API for 50% cost savings:

```bash
# Create a batch job
anki-cards-from-kindle-highlights generate-batch
```

This uploads your highlights to OpenAI for asynchronous processing (up to 24 hours). After the batch completes, load the results:

```bash
# Check status and load results
anki-cards-from-kindle-highlights generate-batch --load-batch-id batch_abc123
```

If the batch is still processing, you'll be prompted to wait. Once complete, results are stored in the database just like the regular `generate` command.

### Step 3: Sync to Anki

Push all generated (but unsynced) cards to Anki:

```bash
anki-cards-from-kindle-highlights sync-to-anki
```

This creates a "Kindle Highlights" deck and custom note types automatically (if they don't yet exist). Cards are marked as synced in the database to prevent duplicates.

### Other Commands

```bash
# Export the database to CSV for inspection
anki-cards-from-kindle-highlights dump --output cards.csv
anki-cards-from-kindle-highlights dump --output cards.csv --only-generated

# Reset all LLM-generated content (to re-generate with a different model/prompt)
anki-cards-from-kindle-highlights reset-generations

# Mark all cards as unsynced (to re-sync to Anki)
anki-cards-from-kindle-highlights set-unsynced

# Show version
anki-cards-from-kindle-highlights --version
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
