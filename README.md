# Bandit's Advantage v3

**A modular trading intelligence engine** focused on technical feature computation, scoring (including Bandit's Rocket), and clean exportable outputs.

Current status: **Phase 3 core is functional** — features → scoring (with News Pulse) → postprocess → ScorecardRow → export.

## Quick Start

### 1. Via CLI (recommended for exploration)

```powershell
# Basic Phase 3 run (synthetic data)
python -m src.cli.main

# With export
python -m src.cli.main --export

# Ad-hoc universe
python -m src.cli.main --tickers AAPL,MSFT,NVDA --export

# Real data + dynamic expansion (when Polygon key available)
python -m src.cli.main --data-source polygon --use-dynamic-expansion --export   # fetches + caches real data
# or (after first run)
python -m src.cli.main --data-source polygon_cache --use-dynamic-expansion --export
```

The CLI now produces:
- Clean per-ticker table with `final_rank`, `bandits_rocket`, `abstention_status`, `rocket_zone`, plus Layer 1 `abstention_risk` + `abstention_reason` (all factors, risk ordered)
- Summary statistics (zone distribution, abstention breakdown, top by rocket)
- Compact NewsPulse diagnostics
- Optional scorecard export via `--export`

### 2. Via Python API

```python
from engine.models.core import EngineConfig
from engine.pipeline.run_engine import run_engine
from engine.pipeline.steps.export import export

# Basic run
cfg = EngineConfig(
    data_source="synthetic",
    synthetic_days=200,
    synthetic_seed=42,
)

output = run_engine(cfg)

print(f"Produced {len(output.scorecard_rows)} ScorecardRows")

# Export
result = export(output, config={"output_dir": "Output"})
print(result)  # Shows paths and status
```

### 3. Using the Dry-Run Harness (great for testing)

```powershell
# Ad-hoc mode
python scripts/dry_run_3_tickers.py --tickers AAPL,MSFT,TSLA

# Scheduled mode with dynamic expansion
python scripts/dry_run_3_tickers.py --use-dynamic-expansion --dynamic-top-stocks 50
```

## Key Concepts

### Two-Mode Universe Management

- **Ad-hoc mode**: Pass `tickers=["AAPL", "MSFT"]` directly in `EngineConfig`. Fast targeted runs.
- **Scheduled / Full-run mode**: Load from `core_universe_path` + optional dynamic expansion (top volume stocks + ETFs via Polygon when configured).

See `engine.pipeline.universe.build_universe()` for details.

### Scoring Outputs (Phase 3)

Each `ScorecardRow` includes:
- Core Phase 2 features
- `final_rank`
- `bandits_rocket` (v3.1)
- `abstention_status`
- `rocket_zone` (Positive / Neutral / Negative)
- `abstention_risk` / `abstention_reason` (Layer 1: structured abstention factors + overall risk Low/Med/High)
- Rich `notes` field containing Abstention + Rocket + NewsPulse diagnostics

### Outputs

- **Scorecard.xlsx**: Clean tabular export of `ScorecardRow` data.
- **History_Archive**: Parquet (with CSV fallback) for long-term analytical storage (opt-in).

## Project Structure

```
src/engine/
├── models/           # TickerScore, ScorecardRow, EngineConfig, ExportResult
├── pipeline/
│   ├── run_engine.py
│   ├── steps/
│   │   ├── ingest.py
│   │   ├── features/
│   │   ├── scoring/      # scoring_step, rocket, abstention, NewsPulse, etc.
│   │   ├── postprocess.py
│   │   └── export.py
│   └── universe.py       # build_universe + dynamic expansion
└── io/                   # readers, excel_writer, history_writer

scripts/
├── dry_run_3_tickers.py  # Excellent for testing both universe modes

Docs/                     # Design notes (Postprocess, Export, CLI plans, etc.)
```

## Configuration

Most behavior is controlled through `EngineConfig`:

```python
cfg = EngineConfig(
    data_source="synthetic",           # or "real", "polygon", "polygon_cache"
    tickers=["AAPL", "MSFT"],          # ad-hoc mode (works with any data_source)
    # or
    use_dynamic_expansion=True,
    core_universe_path="data/reference/tickers.csv",
    dynamic_top_stocks=100,
    scoring=ScoringConfig(min_momentum_pulse=2.0),  # nested
)
# For real Polygon data (40+ tickers):
#   1. export POLYGON_API_KEY=...
#   2. cfg = EngineConfig(data_source="polygon", use_dynamic_expansion=True, ...)
#   3. Subsequent runs can use data_source="polygon_cache" (no API calls)
```

## Development Setup

### Prerequisites
- Python 3.10 or newer (3.11+ recommended)
- A terminal with PowerShell or bash

### 1. Install Dependencies

The project currently has no `requirements.txt` or `pyproject.toml`. Install the core packages manually:

```powershell
pip install pandas numpy openpyxl pyarrow pytest
```

**Notes on optional packages:**
- `pyarrow` (preferred) or `fastparquet` — needed for writing the History Archive in Parquet format. If neither is installed, the history writer will automatically fall back to CSV.
- `openpyxl` — required for writing `.xlsx` files.

### 2. Set PYTHONPATH

The source lives under `src/`. You must make it importable:

**PowerShell (Windows):**
```powershell
$env:PYTHONPATH="src"
```

**Bash / zsh:**
```bash
export PYTHONPATH=src
```

You can add this to your shell profile or use a `.env` / virtualenv activation script for convenience.

### 3. Run Tests

```powershell
# All tests
python -m pytest tests/ -q

# Specific modules
python -m pytest tests/test_universe.py -q
python -m pytest tests/test_scoring.py -q
```

### 4. Using the Dry-Run Harness

The dry-run script is the fastest way to exercise both universe modes and the full scoring pipeline during development:

```powershell
# Basic ad-hoc run
python scripts/dry_run_3_tickers.py --tickers AAPL,MSFT,NVDA --no-rocket

# With realized range demo
python scripts/dry_run_3_tickers.py --show-ranges

# Scheduled mode with dynamic expansion (stub)
python scripts/dry_run_3_tickers.py --use-dynamic-expansion --dynamic-top-stocks 50
```

### 5. Running the Full Pipeline via CLI

```powershell
# Basic Phase 3 run
python -m src.cli.main

# With export + summary only
python -m src.cli.main --export --summary-only
```

### 6. Optional: Polygon API Key

For real dynamic universe expansion (top volume stocks/ETFs):

```powershell
$env:POLYGON_API_KEY="your_key_here"
```

Without it, `fetch_dynamic_universe_additions` safely returns an empty list.

### API Keys & External Providers

API keys are loaded automatically from a `.env` file in the project root (via `python-dotenv`).

- **POLYGON_API_KEY**: Used for price data, aggregates, and volume-based dynamic universe expansion.
- **MASSIVE_API_KEY**: Placeholder for future NewsPulse / news & sentiment data (via the `news_provider` field in `EngineConfig`).

Create a `.env` file from `.env.example` and add your keys. The keys are read via `os.getenv()` once `load_dotenv()` has been called (done early in the CLI and main pipeline modules).

### Recommended Daily Workflow

1. Make your change.
2. Run the relevant tests: `python -m pytest tests/ -q`
3. Exercise the change with the dry-run harness (fast feedback on both ad-hoc and dynamic modes).
4. Run a full end-to-end check: `python -m src.cli.main --export --summary-only`
5. Inspect the generated `Output/Scorecard_*.xlsx` (and History file if enabled).

This loop is currently the fastest and most reliable way to develop against the engine.

### Recommended Workflow

1. Make changes.
2. Run `python -m pytest tests/ -q` to verify.
3. Use `python scripts/dry_run_3_tickers.py ...` for fast iteration on specific tickers or modes.
4. Use `python -m src.cli.main --export` for end-to-end validation.
5. Check the generated `Output/Scorecard_*.xlsx` and (if enabled) the history archive.

### Linting / Type Checking (Optional)

The project does not currently enforce a specific linter or type checker. When contributing, consider running at minimum:

```powershell
python -m pyright src/   # or mypy
```

---

This setup keeps the barrier low while the project is still evolving.

## Next Steps / Roadmap

- Improve Excel formatting and add summary sheets
- Flesh out real Polygon dynamic expansion (currently functional via stub)
- Richer History Archive querying
- Full configuration file support (YAML/JSON)
- More comprehensive documentation and examples

## Contributing

This is an active development project. The architecture emphasizes:

- Pure functions where possible
- Clear separation between internal models (`TickerScore`) and export models (`ScorecardRow`)
- Conservative, reviewable evolution of the output contract

Design notes for major components live in the `Docs/` folder.  
A practical usage guide is available at `Docs/USAGE.md`.

---

*Bandit's Advantage v3 — Technical analysis meets clean engineering.*
