# Arete — Journal & Troubleshooting

Notes pédagogiques sur ce qui a été fait, commandes utilisées, et solutions aux problèmes rencontrés. Objectif : servir de mémo pour reproduire et dépanner rapidement.

## 1. Environnement & uv
- **Cible** : Python 3.11 avec uv, venv local `.venv`.
- **Installer/pinner Python 3.11** :
  ```bash
  uv python install 3.11
  uv python pin 3.11
  uv python list  # vérifier le default
  ```
- **Créer le venv avec la bonne syntaxe** (`--path` n’existe pas) :
  ```bash
  uv venv --python 3.11 --seed .venv
  source .venv/bin/activate
  ```
- **Symptôme** : warning `VIRTUAL_ENV=.../.venv ne correspond pas...` → venv pointant sur un autre dossier.  
  **Fix** : `deactivate`, supprimer l’ancien venv si besoin (`rm -rf /Users/.../arete/.venv`), recréer le venv au bon chemin (`uv venv --python 3.11 --seed .venv`).
- **Commande invalide** : `uv python --version` n’existe pas. Utiliser `python -V` ou `uv run python -V`.

## 2. Structure du projet
- Structure : `src/arete/...` (API, dataio).  
- `.env` et `.env.example` définissent `ARETE_DB` et `MLFLOW_TRACKING_URI`.

## 3. Base DuckDB
- **Helper** : `arete.dataio.db.connect()` centralise la connexion et crée `data/arete.duckdb` si besoin.
- **DDL** : `arete.dataio.init_duckdb` crée :
  - `app.training_log`
  - `app.sessions`
  - `app.users`
  - `app.objectives`
  - `app.personal_records`
- **Commande d’init** :
  ```bash
  PYTHONPATH=src uv run python -m arete.dataio.init_duckdb
  ```
- **Problème rencontré** : DuckDB 1.4.2 ne supporte pas `PRIMARY KEY` ni `IDENTITY`.  
  **Fix** : retirer les contraintes et générer les IDs côté applicatif (`COALESCE(MAX(id),0)+1` dans le dépôt).

### Ingestion
- **Script** : `arete.dataio.ingest` ingère un CSV dans `app.training_log`.
  ```bash
  PYTHONPATH=src uv run python -m arete.dataio.ingest data/sample_log.csv
  ```
- **Symptôme** : doublons si ingestion répétée.  
  **Reset rapide** : `rm data/arete.duckdb` puis ré-exécuter init + ingestion, ou `DELETE FROM app.training_log;`.

## 4. API FastAPI
- **Endpoints exposés** :
  - `/health`
  - `/plan/jour` (stub)
  - `/log/recent` (lit `training_log`)
  - CRUD DuckDB : `/plan/day`, `/sessions`, `/user`, `/objectives`, `/records`
- **Lancement** :
  ```bash
  uv run uvicorn arete.api.main:app --reload --app-dir src
  ```
- **404 sur /** : attendu, pas de route racine ; utiliser `/docs` ou `/health`.

## 5. Couche dépôt (DuckDB)
- Fichier : `src/arete/dataio/repository.py`.  
- Rôle : CRUD sessions/user/objectives/records, génération d’ID appli, mapping dict pour l’API.
- Schémas Pydantic : `src/arete/api/routes.py` (types `date`, `Field` bornés, `Literal` pour `sex`).

## 6. Commandes utiles (récap)
- Init DB : `PYTHONPATH=src uv run python -m arete.dataio.init_duckdb`
- Ingestion sample : `PYTHONPATH=src uv run python -m arete.dataio.ingest data/sample_log.csv`
- Lancer API : `uv run uvicorn arete.api.main:app --reload --app-dir src`
- Vérifier comptages :
  ```bash
  PYTHONPATH=src uv run python - <<'PY'
  from arete.dataio.db import connect
  con = connect(True)
  print("training_log", con.execute("SELECT COUNT(*) FROM app.training_log").fetchone())
  print("sessions", con.execute("SELECT COUNT(*) FROM app.sessions").fetchone())
  PY
  ```

## 7. Points de vigilance
- IDs gérés côté app (pas de PK/identity DuckDB 1.4.2) → éviter les écritures concurrentes.
- Toujours utiliser `PYTHONPATH=src` tant que le projet n’est pas installé en editable.  
- Ingestion : purger avant de ré-ingérer pour éviter les doublons dans `training_log`.

