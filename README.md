# Arete 🤖

[![CI](https://github.com/gregoire-petit1/arete/actions/workflows/ci.yml/badge.svg)](https://github.com/gregoire-petit1/arete/actions/workflows/ci.yml)

> **Arete (ἀρετή)** — an ancient Greek concept meaning _excellence_ or _virtue_,  
> achieved when one fulfills their highest potential through discipline, balance, and mastery.
>
> **Project Arete** embodies this pursuit — an intelligent training assistant that helps you reach your personal best, every day.

## 🚧 Status

Active development — Features Engineering & Metrics API complete.

## Goals

- Personalized workout planner
- Smart memory of previous sessions
- RAG-based recommendations
- AI Agent to orchestrate planning and adaptation
- **Scientific training metrics** (ACWR, CTL/ATL/TSB, TRIMP, 1RM estimation)

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
│   ├── features/        # Feature engineering (workload, cardio, strength, fitness)
│   ├── models/          # ML models (coming soon)
│   ├── rules/           # Business rules (coming soon)
│   └── utils/           # Utility functions
├── tests/               # Test suite
├── data/                # Data files (not in git)
├── notebooks/           # Jupyter notebooks
└── experiments/         # MLflow experiments
```

## Features Engineering Module

The `src/arete/features/` module provides scientific training metrics and intelligent recommendations:

### Workload Metrics (`workload.py`)

- **ACWR** (Acute:Chronic Workload Ratio) with EWMA or rolling window
- **Monotony** (training load variability)
- **Strain** (accumulated fatigue indicator)
- Zone classification: Danger, High Risk, Optimal, Undertrained

### Cardio Metrics (`cardio.py`)

- **TRIMP** (Training Impulse) with gender-specific weighting
- **HR Zones** (5 zones based on % HRmax or HRR)
- **VO2max** estimation (Cooper, Rockport, HR methods)
- **Efficiency Factor** and pace calculations

### Strength Metrics (`strength.py`)

- **1RM Estimation** (7 formulas: Epley, Brzycki, Lombardi, O'Conner, Wathan, Mayhew, Wathen, RPE-based)
- **Strength Zones** (5 zones from Recovery to Max Strength)
- **INOL** (Intensity × Number of Lifts)
- **VBT Zones** (Velocity-Based Training)
- Volume, tonnage, and intensity calculations

### Fitness-Fatigue Model (`fitness.py`)

- **CTL** (Chronic Training Load / Fitness) — 42-day EWMA
- **ATL** (Acute Training Load / Fatigue) — 7-day EWMA
- **TSB** (Training Stress Balance / Form) = CTL − ATL
- **Readiness Score** (0-100 composite)
- Form zones: Exhausted, Fatigued, Neutral, Fresh, Peak

### Recommendations (`recommendations.py`)

- Intelligent training advice in French
- Risk assessment based on ACWR, monotony, strain
- Weekly training plan generation
- Priority-based action items

### Usage Example

```python
from arete.features import (
    compute_workload_metrics,
    calculate_trimp,
    estimate_1rm_epley,
    compute_performance_model,
    generate_recommendations,
)

# Compute workload metrics from last 28 days of training loads
loads = [45, 50, 55, 60, 50, 55, 65]  # sRPE values
metrics = compute_workload_metrics(loads)
print(f"ACWR: {metrics.acwr:.2f} ({metrics.acwr_zone.value})")

# Calculate TRIMP for a cardio session
trimp = calculate_trimp(
    duration_min=60,
    avg_hr=150,
    hr_rest=60,
    hr_max=190,
    gender="male"
)

# Estimate 1RM for strength training
estimated_1rm = estimate_1rm_epley(weight=100, reps=5)
print(f"Estimated 1RM: {estimated_1rm:.1f} kg")

# Compute fitness-fatigue model
tss_history = [50, 60, 70, 55, 80, 65, 75]  # Daily TSS values
model = compute_performance_model(tss_history)
print(f"Form: {model.tsb:.1f} ({model.form_zone.value})")

# Generate recommendations
recommendations = generate_recommendations(
    acwr=1.35,
    acwr_zone=metrics.acwr_zone,
    monotony=1.8,
    monotony_zone=metrics.monotony_zone,
    strain=2500,
    strain_zone=metrics.strain_zone,
    tsb=-15,
    form_zone=model.form_zone,
    sport_type="running",
)
for rec in recommendations:
    print(f"[{rec.priority.value}] {rec.message}")
```

## API Endpoints

The API exposes training metrics via REST endpoints:

### Core Endpoints

| Endpoint      | Method | Description                        |
| ------------- | ------ | ---------------------------------- |
| `/health`     | GET    | Health check                       |
| `/docs`       | GET    | OpenAPI documentation (Swagger UI) |
| `/log/recent` | GET    | Recent training log entries        |

### Metrics Endpoints

| Endpoint                   | Method | Description                                   |
| -------------------------- | ------ | --------------------------------------------- |
| `/metrics/workload`        | GET    | ACWR, Monotony, Strain from training history  |
| `/metrics/fitness`         | GET    | CTL/ATL/TSB (Banister model), readiness score |
| `/metrics/cardio/trimp`    | POST   | Calculate TRIMP for a cardio session          |
| `/metrics/strength/1rm`    | POST   | Estimate 1RM from submaximal lift             |
| `/metrics/strength/inol`   | POST   | Calculate INOL for strength training          |
| `/metrics/recommendations` | GET    | Intelligent training recommendations          |

### Example API Calls

```bash
# Get workload metrics (last 28 days)
curl http://localhost:8000/metrics/workload

# Get fitness metrics (CTL/ATL/TSB)
curl http://localhost:8000/metrics/fitness

# Calculate TRIMP for a session
curl -X POST http://localhost:8000/metrics/cardio/trimp \
  -H "Content-Type: application/json" \
  -d '{"duration_min": 60, "avg_hr": 150, "hr_rest": 60, "hr_max": 190, "gender": "male"}'

# Estimate 1RM
curl -X POST http://localhost:8000/metrics/strength/1rm \
  -H "Content-Type: application/json" \
  -d '{"weight": 100, "reps": 5, "rpe": 8}'

# Get recommendations
curl "http://localhost:8000/metrics/recommendations?sport_type=cardio"
```

## Documentation

The full project documentation and progress log are available on [Notion](https://www.notion.so/Arete-Intelligent-Training-Assistant-28866cec311a80d8828dcf68b45f6193?source=copy_link)
