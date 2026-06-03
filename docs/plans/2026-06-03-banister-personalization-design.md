# Personalized Banister Model Coefficients

## Motivation

The current Banister impulse-response model uses hardcoded coefficients:

```
performance = baseline + 1.0 · CTL − 2.0 · ATL
```

These defaults assume a generic athlete. By fitting `k1` and `k2` to the user's actual
training data, we get more accurate fatigue/fitness tracking, better TSB/form estimates,
and a foundation for downstream ML models (performance prediction, readiness).

## Design

### Target variable

**Primary**: Cardiac efficiency (`avg_heartrate / avg_speed_kmh`) — objective,
available on every run with HR data. Lower = more efficient.

**Secondary (validation only)**: RPE (1–10) — subjective, but captures perceived
effort better on hilly/mountain runs where HR is mechanically elevated.

### Model

Simple linear regression with L2 regularization (Ridge):

```
efficiency(t) = baseline + k1 · CTL(t) − k2 · ATL(t)
```

Constraints: `k1 ≥ 0`, `k2 ≥ 0` — clamped post-fit.

### Data pipeline

1. Query daily CTL/ATL (from `app.daily_metrics` or computed on-the-fly via
   the same EWMA logic in `fitness.py`)
2. Join with all running sessions that have both `avg_heartrate` and `avg_speed_mps`
3. Filter out: strength sessions, walks, rest days, sessions without HR
4. Fit Ridge regression with leave-one-out CV
5. Report: `k1`, `k2`, `baseline`, `R²`, `n_samples`, `fitted_at`

### Storage

New table `app.banister_coefficients`:

| Column | Type | Description |
|--------|------|-------------|
| `user_id` | INTEGER | FK to users |
| `k1` | FLOAT | Fitness coefficient |
| `k2` | FLOAT | Fatigue coefficient |
| `baseline` | FLOAT | Baseline efficiency |
| `r2` | FLOAT | Fit quality |
| `n_samples` | INTEGER | Data points used |
| `fitted_at` | TIMESTAMP | Last fit time |

### Integration

`fitness.py` `compute_readiness()` checks for personalized coefficients.
If available and `r2 > 0.1`, uses them for the Banister model (CTL/ATL/TSB
remain unchanged; only the performance equation uses fitted values).
Otherwise falls back to defaults `(k1=1.0, k2=2.0)`.

### CLI

```bash
# Fit + store, log to MLflow
uv run python scripts/fit_banister.py

# Dry-run: show coefficients without storing
uv run python scripts/fit_banister.py --dry-run

# Force refit with specific data range
uv run python scripts/fit_banister.py --start 2025-01-01 --end 2026-06-03
```

### Error handling / Edge cases

| Case | Handling |
|------|----------|
| < 10 runs with HR data | Skip, print "not enough data" |
| k1 < 0 or k2 < 0 | Clamp to 0 (no negative fatigue effect) |
| R² ≤ 0 | Don't store, fallback to defaults |
| No efficiency on a day | Excluded from fit (not imputed) |
| MLflow unavailable | Coefficients still stored in DB, warn |

### Future work (not implemented now)

- Use RPE directly in loss function (multi-objective)
- Time-varying coefficients (e.g., k1 increases with training age)
- Hierarchical Bayesian model pooling across athletes
- Predict race-day performance (TMB) using personalized model

## Files changed

- `scripts/fit_banister.py` — new training script
- `src/arete/features/fitness.py` — load personalized coefficients
- `src/arete/dataio/schema.py` — add `banister_coefficients` table

## Testing

- Unit test: `test_fit_banister.py` with synthetic data (known k1, k2)
- Integration test: script runs end-to-end with real DB
- Validation: R² > 0 expected (even weak) on real data
