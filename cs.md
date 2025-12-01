# Guide Complet — Projet Arete

## Ordre : Setup → API → Base de Données

**Objectif :** en suivant ce guide pas à pas, vous pouvez reproduire l'intégralité du setup, lancer l'API FastAPI, créer la base DuckDB, ingérer des données et interroger les dernières séances.

## 1) Setup & Environnement

### 1.1. Prérequis

- **macOS Intel** (MacBook Pro 2018, CPU seulement)
- **Terminal** (zsh/bash)
- **Git installé** (facultatif au début)
- **uv** (gestion Python + environnements + dépendances)

**Installer uv :**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Pourquoi uv ?**
uv remplace pip/venv/pip-tools/poetry pour la plupart des cas. C'est rapide, simple et gère Python, les environnements virtuels et les dépendances via `pyproject.toml`.

### 1.2. Créer le projet

```bash
uv init arete && cd arete
```

Ce répertoire contiendra votre code et la configuration du projet.

### 1.3. Configurer pyproject.toml

Remplacez le contenu par ce fichier minimal (adapté à macOS Intel + PyTorch compatible) :

```toml
[project]
name = "arete"
version = "0.1.0"
description = "Assistant d'entraînement — Arete"
readme = "README.md"
requires-python = ">=3.11,<3.12"
dependencies = []

[tool.uv]
# Aide uv à résoudre des roues compatibles macOS Intel (x86_64)
required-environments = ["sys_platform == 'darwin' and platform_machine == 'x86_64'"]
```

**Choix importants :**

- `>=3.11,<3.12` : PyTorch 2.2.x n'est pas compatible Python 3.12 sur macOS Intel
- `required-environments` aide uv à résoudre des roues compatibles x86_64 (Mac Intel)

### 1.4. Pinner Python 3.11

```bash
uv python install 3.11
uv python pin 3.11
```

### 1.5. Installer les dépendances

**Dépendances cœur (API, data, MLOps, etc.) :**

```bash
uv add fastapi "pydantic>=2" uvicorn pytest mypy ruff \
       pandas polars numpy scikit-learn duckdb optuna \
       mlflow typer python-dotenv
```

**PyTorch compatible Mac Intel + Python 3.11 :**

```bash
uv add "torch==2.2.2" "torchvision==0.17.2"
# torchaudio est optionnel ; à installer plus tard si nécessaire :
# uv add "torchaudio==2.2.2"
```

### 1.6. Vérifier l'installation de PyTorch (CPU)

```bash
uv run python - <<'PY'
import sys, torch
print("Python:", sys.version.split()[0])
print("Torch:", torch.__version__)
print("CUDA?", torch.cuda.is_available())
print("MPS?", hasattr(torch.backends, "mps") and torch.backends.mps.is_available())
x = torch.randn(1000, 1000)
print("OK CPU matmul:", (x @ x.T).shape)
PY
```

**Attendu :** Python 3.11.x, Torch 2.2.2, CUDA False, MPS False, et une forme (1000, 1000).

### 1.7. Arborescence recommandée

Créer l'arborescence dès maintenant (depuis la racine du projet) :

```bash
mkdir -p src/arete/{api,dataio,features,models,rules,utils} notebooks experiments tests data
touch src/arete/__init__.py src/arete/api/__init__.py src/arete/dataio/__init__.py
echo -e ".venv/\ndata/\nmlruns/\n.env\n" > .gitignore
```

**Rôle des dossiers :**

- **`src/arete/api/`** : endpoints FastAPI
- **`src/arete/dataio/`** : accès et scripts DB (DuckDB)
- **`src/arete/features/`** : features (charge, ACWR, etc.)
- **`src/arete/models/`** : modèles sklearn / PyTorch
- **`src/arete/rules/`** : règles de planification
- **`notebooks/`** : explorations (Jupyter)
- **`experiments/`** : scripts entraînement, Optuna, MLflow
- **`tests/`** : tests pytest
- **`data/`** : fichiers de données locaux (ignorés par Git)

**Pourquoi `__init__.py` ?**
Pour que Python reconnaisse ces dossiers comme packages importables (ex : `arete.dataio`).

### 1.8. Variables d'environnement

**Créer `.env` (privé, non versionné) :**

```bash
nano .env
```

**Contenu :**

```env
ARETE_DB=data/arete.duckdb
MLFLOW_TRACKING_URI=./mlruns
```

**Créer `.env.example` (modèle, versionné) :**

```bash
nano .env.example
```

**Contenu :**

```env
ARETE_DB=data/arete.duckdb
MLFLOW_TRACKING_URI=./mlruns
```

**Pourquoi `.env` + `.env.example` ?**

- `.env` contient vos vraies valeurs locales (non poussées sur Git)
- `.env.example` documente les variables attendues pour tout autre poste ou collaborateur

### 1.9. Outils qualité et tests (facultatif mais conseillé)

```bash
uv run ruff check
uv run ruff format
uv run mypy src
uv run pytest -q
```

## 2) API FastAPI

### 2.1. Créer l'API minimale

**Fichier `src/arete/api/main.py` :**

```python
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from arete.dataio.db import connect  # import data (utilisé par /log/recent)

# Charger .env (ARETE_DB, etc.)
load_dotenv()

# App FastAPI
app = FastAPI(title="Arete API", version="0.1.0")

# --------- Schémas ----------
class SessionRequest(BaseModel):
    date: str
    objectif: str
    dispo_min: int
    fatigue: int
    rpe_moy7j: float | None = None

# --------- Endpoints ----------
@app.get("/health")
def health():
    return {"ok": True}

@app.post("/plan/jour")
def plan_jour(req: SessionRequest):
    # stub simple ; sera remplacé par règles + modèles
    return {"seance": "EF 45' + 6x100m", "cible": {"fc": "70-75% FCM", "allure": "Z2"}}

@app.get("/log/recent")
def log_recent(n: int = 5):
    con = connect(read_only=True)
    df = con.execute("""
        SELECT date, sport, type, duree_min, distance_km, rpe
        FROM app.training_log
        ORDER BY date DESC
        LIMIT ?
    """, [n]).fetch_df()
    return {"rows": df.to_dict(orient="records")}
```

**Choix clés :**

- `load_dotenv()` permet de lire `.env` automatiquement
- On sépare la logique data (DB) et l'API. L'API utilise un helper de connexion (`connect`) unique

### 2.2. Lancer l'API

Toujours depuis la racine du projet :

```bash
uv run uvicorn arete.api.main:app --reload --app-dir src
```

- **Swagger UI** : `http://127.0.0.1:8000/docs`
- **Redoc** : `http://127.0.0.1:8000/redoc`
- **Santé** : `http://127.0.0.1:8000/health`

**Tester POST `/plan/jour` (Swagger → Try it out) avec :**

```json
{
  "date": "2025-09-16",
  "objectif": "10k_sub45",
  "dispo_min": 60,
  "fatigue": 3,
  "rpe_moy7j": 5.5
}
```

### 2.3. Alternative pratique (éviter --app-dir src/PYTHONPATH=src)

**Installer le projet en editable (optionnel) :**

```bash
# ajouter le backend de build (une fois)
awk 'BEGIN{print "[build-system]\nrequires=[\"hatchling\"]\nbuild-backend=\"hatchling.build\""}' >> pyproject.toml

# puis :
uv pip install -e .
```

Vous pourrez ensuite utiliser :

```bash
uv run uvicorn arete.api.main:app --reload
```

## 3) Base de Données (DuckDB)

### 3.1. Helper de connexion

**Fichier `src/arete/dataio/db.py` :**

```python
import os, pathlib
from dotenv import load_dotenv
import duckdb

load_dotenv()

DEFAULT_DB_PATH = pathlib.Path("data/arete.duckdb")

def get_db_path() -> pathlib.Path:
    env_path = os.getenv("ARETE_DB")
    return pathlib.Path(env_path) if env_path else DEFAULT_DB_PATH

def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)  # crée data/ si besoin
    con = duckdb.connect(str(db_path), read_only=read_only)
    con.execute("PRAGMA threads=4;")
    con.execute("PRAGMA temp_directory='data';")
    return con
```

**Choix clés :**

- Accès centralisé à la DB via `connect()`
- `ARETE_DB` configurable dans `.env`
- `PRAGMA` pour fixer les threads et un répertoire temporaire local

### 3.2. Initialisation du schéma et de la table

**Important :** éviter les collisions de noms.
Le fichier s'appelle `arete.duckdb` → DuckDB crée un catalogue `arete`.
Si vous créez un schéma `arete`, DuckDB se plaint d'ambiguïté.
On choisit donc le schéma `app`.

**Fichier `src/arete/dataio/init_duckdb.py` :**

```python
from arete.dataio.db import connect

DDL = """
CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS app.training_log (
    date          DATE,
    sport         VARCHAR,
    type          VARCHAR,
    duree_min     INTEGER,
    distance_km   DOUBLE,
    allure_minkm  DOUBLE,
    avg_hr        INTEGER,
    rpe           DOUBLE,
    sommeil_h     DOUBLE,
    hrv           DOUBLE,
    poids_kg      DOUBLE,
    denivele_m    INTEGER,
    terrain       VARCHAR,
    douleurs      VARCHAR,
    stress        INTEGER,
    notes         VARCHAR,
    course_date   DATE,
    course_type   VARCHAR,
    objectif_tps  VARCHAR
);
"""

def main():
    con = connect(False)
    for stmt in DDL.strip().split(";"):
        s = stmt.strip()
        if s:
            con.execute(s + ";")
    tables = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='app'"
    ).fetchall()
    print("Tables:", tables)

if __name__ == "__main__":
    main()
```

**Créer la table (depuis la racine du projet) :**

```bash
# Si vous n'avez pas installé en editable :
PYTHONPATH=src uv run python -m arete.dataio.init_duckdb

# Si vous avez fait "uv pip install -e .", alors :
# uv run python -m arete.dataio.init_duckdb
```

**Attendu :**

```text
Tables: [('training_log',)]
```

### 3.3. Ingestion d'un CSV dans app.training_log

**Fichier `src/arete/dataio/ingest.py` :**

```python
import pathlib
from arete.dataio.db import connect

COLUMNS = [
    "date","sport","type","duree_min","distance_km","allure_minkm",
    "avg_hr","rpe","sommeil_h","hrv","poids_kg","denivele_m",
    "terrain","douleurs","stress","notes",
    "course_date","course_type","objectif_tps"
]

def duck_type(col: str) -> str:
    if col in {"date","course_date"}: return "DATE"
    if col in {"duree_min","avg_hr","denivele_m","stress"}: return "INTEGER"
    if col in {"distance_km","allure_minkm","rpe","sommeil_h","hrv","poids_kg"}: return "DOUBLE"
    return "VARCHAR"

def ingest_csv(csv_path: str | pathlib.Path) -> int:
    p = pathlib.Path(csv_path)
    if not p.exists():
        raise FileNotFoundError(p)
    con = connect(False)
    cols_select = ", ".join([f"TRY_CAST({c} AS {duck_type(c)}) AS {c}" for c in COLUMNS])
    q = f"""
    INSERT INTO app.training_log
    SELECT {cols_select}
    FROM read_csv_auto('{p.as_posix()}', HEADER=TRUE, SAMPLE_SIZE=-1)
    """
    con.execute(q)
    total = con.execute("SELECT COUNT(*) FROM app.training_log").fetchone()[0]
    print(f"Ingestion OK. Total lignes: {total}")
    return total

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m arete.dataio.ingest <path_csv>")
        raise SystemExit(1)
    ingest_csv(sys.argv[1])
```

**Créer un CSV d'exemple puis l'ingérer :**

```bash
mkdir -p data
cat > data/sample_log.csv <<'CSV'
date,sport,type,duree_min,distance_km,allure_minkm,avg_hr,rpe,sommeil_h,hrv,poids_kg,denivele_m,terrain,douleurs,stress,notes,course_date,course_type,objectif_tps
2025-09-14,run,EF,45,8,5.6,138,4,7.5,,80,50,route,,3,"ok",2025-11-10,10k,10k_sub45
2025-09-15,run,intervalles,60,10,4.8,158,7,7.0,,79.8,80,piste,genou D léger,4,"8x800m",2025-11-10,10k,10k_sub45
CSV

# Si sans editable :
uv run python -m arete.dataio.ingest data/sample_log.csv
# Si avec editable, idem.
```

**Attendu :**

```text
Ingestion OK. Total lignes: 2
```

### 3.4. Interroger la DB via l'API

L'endpoint `/log/recent` renvoie les N dernières séances.

**Lancer le serveur :**

```bash
uv run uvicorn arete.api.main:app --reload --app-dir src
```

**Appeler :**

```http
GET http://127.0.0.1:8000/log/recent?n=5
```

**Réponse type :**

```json
{
  "rows": [
    {
      "date": "2025-09-15",
      "sport": "run",
      "type": "intervalles",
      "duree_min": 60,
      "distance_km": 10.0,
      "rpe": 7.0
    },
    {
      "date": "2025-09-14",
      "sport": "run",
      "type": "EF",
      "duree_min": 45,
      "distance_km": 8.0,
      "rpe": 4.0
    }
  ]
}
```

### 3.5. Bonnes pratiques & pièges évités

- **Collision de noms DuckDB** : fichier `arete.duckdb` crée un catalogue `arete`. On utilise le schéma `app` pour éviter l'ambiguïté (`arete.arete` autrement)
- **Lancer depuis la racine du projet** : vos chemins (`--app-dir src`, `PYTHONPATH=src`) sont relatifs au répertoire courant
- **`__init__.py` requis** pour que `arete/...` soit importable
- **Mode editable** si vous voulez éviter `--app-dir src` / `PYTHONPATH=src`
- **`.env` privé** (non versionné) vs `.env.example` (modèle versionné)

## 4) Résumé des commandes clés

### Création & config

```bash
uv init arete && cd arete
# éditer pyproject.toml (cf. plus haut)
uv python install 3.11
uv python pin 3.11
```

### Dépendances

```bash
uv add fastapi "pydantic>=2" uvicorn pytest mypy ruff \
       pandas polars numpy scikit-learn duckdb optuna \
       mlflow typer python-dotenv
uv add "torch==2.2.2" "torchvision==0.17.2"
```

### Arbo & fichiers spéciaux

```bash
mkdir -p src/arete/{api,dataio,features,models,rules,utils} notebooks experiments tests data
touch src/arete/__init__.py src/arete/api/__init__.py src/arete/dataio/__init__.py
echo -e ".venv/\ndata/\nmlruns/\n.env\n" > .gitignore
```

### Variables d'environnement

```bash
printf "ARETE_DB=data/arete.duckdb\nMLFLOW_TRACKING_URI=./mlruns\n" > .env
cp .env .env.example
```

### API

```bash
uv run uvicorn arete.api.main:app --reload --app-dir src
# http://127.0.0.1:8000/docs
```

### DB

```bash
# init schéma + table
PYTHONPATH=src uv run python -m arete.dataio.init_duckdb

# ingestion CSV
uv run python -m arete.dataio.ingest data/sample_log.csv
```

### Qualité

```bash
uv run ruff check && uv run ruff format
uv run mypy src
uv run pytest -q
```
