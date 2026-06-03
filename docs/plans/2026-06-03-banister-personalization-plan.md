# Banister Personalization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fit athlete-specific Banister model coefficients (k1, k2, baseline) from training data using cardiac efficiency as the performance proxy.

**Architecture:** Training script queries daily CTL/ATL + running sessions with HR/speed, fits Ridge regression, stores coefficients in new DB table. `fitness.py` loads personalized coeffs when available and R² > 0.1.

**Tech Stack:** Python, DuckDB, sklearn, ridge regression, MLflow tracking

---

### Task 1: Add banister_coefficients table to DB schema

**Files:**
- Modify: `src/arete/dataio/init_duckdb.py` (add table to DDL + migration for existing DBs)

**DDL:**
```sql
CREATE TABLE IF NOT EXISTS app.banister_coefficients (
    user_id         INTEGER PRIMARY KEY DEFAULT 1,
    k1              FLOAT NOT NULL DEFAULT 1.0,
    k2              FLOAT NOT NULL DEFAULT 2.0,
    baseline        FLOAT NOT NULL DEFAULT 100.0,
    r2              FLOAT,
    n_samples       INTEGER,
    fitted_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Step 1:** Add DDL to the main DDL string (before `user_settings` seed, after `strava_tokens`).

**Step 2:** Add migration in `_run_migrations` for existing DBs that don't have the table yet.

**Step 3:** Run `pytest` to verify nothing broken (0 tests for this yet).

**Step 4:** Commit.
```bash
git add src/arete/dataio/init_duckdb.py
git commit -m "feat: add banister_coefficients table"
```

---

### Task 2: Write tests for Banister coefficient fitting

**Files:**
- Create: `tests/test_banister.py`

**Step 1: Write test_fit_recovers_known_coefficients**

Synthetic data: generate 100 days of random TSS, compute CTL/ATL, generate `efficiency = baseline + k1*CTL - k2*ATL + noise`, then verify fit recovers coefficients within tolerance.

```python
def test_fit_recovers_known_coefficients():
    from arete.features.fitness import calculate_ctl, calculate_atl
    from datetime import date, timedelta
    import numpy as np
    from numpy.typing import NDArray
    
    # Generate synthetic daily TSS
    n_days = 200
    today = date.today()
    dates = [today - timedelta(days=i) for i in range(n_days, 0, -1)]
    rng = np.random.default_rng(42)
    tss_values = rng.exponential(scale=60, size=n_days).tolist()
    daily_tss = [{"date": d, "tss": t} for d, t in zip(dates, tss_values)]
    
    # True coefficients
    true_k1, true_k2, true_baseline = 0.8, 1.5, 60.0
    
    # Compute CTL/ATL for each day
    ctl_vals = [calculate_ctl(daily_tss, d) for d in dates[42:]]
    atl_vals = [calculate_atl(daily_tss, d) for d in dates[42:]]
    
    # Generate efficiency with noise
    eff = np.array([true_baseline + true_k1 * c - true_k2 * a for c, a in zip(ctl_vals, atl_vals)])
    noise = rng.normal(0, 2, size=len(eff))
    y = eff + noise
    
    # Fit
    from sklearn.linear_model import Ridge
    X = np.column_stack([np.ones_like(ctl_vals), ctl_vals, atl_vals])
    model = Ridge(alpha=1.0)
    model.fit(X, y)
    fitted_baseline, fitted_k1, fitted_k2 = model.coef_[0], model.coef_[1], model.coef_[2]  # Wait, Ridge intercept...
    # Actually use fit_intercept=True
    X_no_intercept = np.column_stack([ctl_vals, atl_vals])
    model2 = Ridge(alpha=1.0, fit_intercept=True)
    model2.fit(X_no_intercept, y)
    
    assert abs(model2.coef_[0] - true_k1) < 0.3
    assert abs(model2.coef_[1] - true_k2) < 0.3
    assert abs(model2.intercept_ - true_baseline) < 5.0
```

Run: `pytest tests/test_banister.py::test_fit_recovers_known_coefficients -v`
Expected: PASS

**Step 2: Write test_insufficient_data_returns_none**

```python
def test_insufficient_data_returns_none():
    """Less than 10 samples should return None."""
    from scripts.fit_banister import fit_coefficients
    # Empty data
    result = fit_coefficients([])
    assert result is None
```

Run: `pytest tests/test_banister.py::test_insufficient_data_returns_none -v`
Expected: FAIL (fit_coefficients not imported)

**Step 3: Commit**
```bash
git add tests/test_banister.py
git commit -m "test: Banister coefficient fitting tests"
```

---

### Task 3: Implement fit_banister.py script

**Files:**
- Create: `scripts/fit_banister.py`

**Key logic:**
```python
def fit_coefficients(sessions: list[dict]) -> dict | None:
    """Fit Banister coefficients from session data.
    
    Args:
        sessions: list of dicts with 'date', 'avg_hr', 'avg_speed_mps', 'ctl', 'atl'
    
    Returns:
        dict with k1, k2, baseline, r2, n_samples, or None if insufficient data
    """
    if len(sessions) < 10:
        return None
    
    X = np.column_stack([s['ctl'] for s in sessions], [s['atl'] for s in sessions])
    y = np.array([s['avg_hr'] / s['avg_speed_mps'] / 3.6 for s in sessions])
    # ^ convert speed from m/s to km/h
    
    model = Ridge(alpha=1.0, fit_intercept=True, positive=False)  # allow any signs, clamp after
    model.fit(X, y)
    
    k1, k2 = model.coef_
    baseline = model.intercept_
    r2 = model.score(X, y)
    
    # Clamp
    k1 = max(0, k1)
    k2 = max(0, k2)
    
    return {
        'k1': round(k1, 4),
        'k2': round(k2, 4),
        'baseline': round(baseline, 2),
        'r2': round(r2, 4),
        'n_samples': len(sessions),
    }
```

**Data query flow:**
1. Connect to DB
2. Query `actual_sessions` for runs with `avg_hr IS NOT NULL AND avg_speed_mps IS NOT NULL AND date >= ?`
3. For each session date, compute daily TSS (from all sessions that day) → then compute CTL/ATL for that date
4. Fit coefficients
5. Store in `banister_coefficients` (UPSERT)
6. Optionally log to MLflow

**Script entry point:**
```python
def main(dry_run: bool = False, start_date: str | None = None, end_date: str | None = None):
    ...
```

**Step 1:** Run `pytest tests/test_banister.py::test_insufficient_data_returns_none` → verify PASS

**Step 2:** Run all tests → `pytest tests/test_banister.py -v`

**Step 3:** Commit
```bash
git add scripts/fit_banister.py
git commit -m "feat: Banister coefficient fitting script"
```

---

### Task 4: Update fitness.py to load personalized coefficients

**Files:**
- Modify: `src/arete/features/fitness.py`

**Changes:**
1. Add `load_banister_coefficients(user_id: int = 1) -> dict | None` function
2. Modify `predict_performance()` (or its callers) to check for personalization
3. When computing `PerformanceModel`, use personalized coefficients if available and R² > 0.1

**Important:** The current model already accepts k1/k2/baseline as params with defaults. The change is to load them from DB at compute time.

```python
def load_banister_coefficients(user_id: int = 1) -> dict | None:
    """Load personalized Banister coefficients from DB."""
    from arete.dataio.db import connect
    con = connect()
    try:
        row = con.execute(
            "SELECT k1, k2, baseline, r2 FROM app.banister_coefficients WHERE user_id = ?",
            [user_id]
        ).fetchone()
        if row and row[3] and row[3] > 0.1:
            return {"k1": row[0], "k2": row[1], "baseline": row[2], "r2": row[3]}
        return None
    finally:
        con.close()
```

**Integration in `compute_performance_model`:**
```python
def compute_performance_model(...) -> PerformanceModel:
    metrics = calculate_fitness_metrics(tss_values, target_date)
    ramp_rate = calculate_ramp_rate(tss_values, target_date)
    
    # Check for personalized coefficients
    coeffs = load_banister_coefficients()
    if coeffs:
        predicted_perf = predict_performance(
            metrics.ctl, metrics.atl,
            k1=coeffs["k1"], k2=coeffs["k2"], baseline=coeffs["baseline"]
        )
    else:
        predicted_perf = predict_performance(metrics.ctl, metrics.atl)
    ...
```

**Step 1:** Run tests: `pytest tests/ -v`
Expected: all pass (including existing analytics tests)

**Step 2:** Commit
```bash
git add src/arete/features/fitness.py
git commit -m "feat: load personalized Banister coefficients from DB"
```

---

### Task 5: Update test with integration-level test

**Files:**
- Modify: `tests/test_banister.py`

**Step 1:** Add a test that exercises the full script end-to-end using the DB
```python
def test_fit_via_script():
    """Run fit_banister.py --dry-run, verify it doesn't crash."""
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "scripts/fit_banister.py", "--dry-run"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
```

**Step 2:** Run `pytest tests/test_banister.py -v` → PASS

**Step 3:** Commit
```bash
git add tests/test_banister.py
git commit -m "test: add integration test for fit_banister script"
```

---

### Task 6: Build Docker, run on real data, verify

**Step 1:** Build backend
```bash
docker compose build backend
docker compose up -d
```

**Step 2:** Run fit on real data
```bash
docker exec arete-backend uv run python scripts/fit_banister.py
```

**Step 3:** Verify coefficients stored
```bash
docker exec arete-backend uv run python -c "
from arete.dataio.db import connect
con = connect()
row = con.execute('SELECT * FROM app.banister_coefficients').fetchone()
print(row)
"
```

**Step 4:** Verify frontend still works (curl http://localhost:3080)

**Step 5:** Push and commit if desired
