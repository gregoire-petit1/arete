# Arete 🤖

[![CI](https://github.com/gregoire-petit1/arete/actions/workflows/ci.yml/badge.svg)](https://github.com/gregoire-petit1/arete/actions/workflows/ci.yml)

> **Arete (ἀρετή)** — an ancient Greek concept meaning _excellence_ or _virtue_,  
> achieved when one fulfills their highest potential through discipline, balance, and mastery.
>
> **Project Arete** embodies this pursuit — an intelligent training assistant that helps you reach your personal best, every day.

## 🚧 Status

Early development – more coming soon.

## Goals

- Personalized workout planner
- Smart memory of previous sessions
- RAG-based recommendations
- AI Agent to orchestrate planning and adaptation

## Stack

- Python 3.11 (via [uv](https://github.com/astral-sh/uv))
- FastAPI + Pydantic v2
- DuckDB (analytical database)
- Pandas / Polars
- MLflow + Optuna
- PyTorch (CPU)
- LLM/RAG (à venir)

## Getting Started

### Prerequisites

- [uv](https://github.com/astral-sh/uv) (recommended) or Python 3.11+

### Installation

```bash
# Clone the repository
git clone https://github.com/gregoire-petit1/arete.git
cd arete

# Install dependencies with uv
uv sync --dev

# Initialize the database (DuckDB)
uv run python -c "from arete.dataio.init_duckdb import main; main()"

# Ingest sample data (optional)
uv run python -c "from arete.dataio.ingest import ingest_csv; ingest_csv('data/sample_log.csv')"
```

### Running the API

```bash
# Development server with auto-reload
uv run uvicorn arete.api.main:app --reload

# Access API at http://localhost:8000
# OpenAPI docs at http://localhost:8000/docs
```

### Environment Variables

Create a `.env` file (optional):

```bash
ARETE_DB=data/arete.duckdb  # Database path
```

## Development

### Quality Tools

```bash
# Run linter
uv run ruff check src tests

# Auto-fix lint issues
uv run ruff check src tests --fix

# Check formatting
uv run ruff format --check src tests

# Format code
uv run ruff format src tests

# Type checking
PYTHONPATH=src uv run mypy src/arete --ignore-missing-imports

# Run tests
PYTHONPATH=src uv run pytest tests/ -v

# Run tests with coverage
PYTHONPATH=src uv run pytest tests/ -v --cov=src/arete --cov-report=term-missing
```

### Project Structure

```
arete/
├── src/arete/           # Main source code
│   ├── api/             # FastAPI routes and main app
│   ├── dataio/          # Database and data ingestion
│   ├── features/        # Feature engineering (coming soon)
│   ├── models/          # ML models (coming soon)
│   ├── rules/           # Business rules (coming soon)
│   └── utils/           # Utility functions
├── tests/               # Test suite
├── data/                # Data files (not in git)
├── notebooks/           # Jupyter notebooks
└── experiments/         # MLflow experiments
```

## Documentation

The full project documentation and progress log are available on [Notion](https://www.notion.so/Arete-Intelligent-Training-Assistant-28866cec311a80d8828dcf68b45f6193?source=copy_link)
