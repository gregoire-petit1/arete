---
type: operations
title: Operations & Deployment
description: Deployment pipeline, monitoring, scaling, and maintenance procedures for the Arete application.
tags: [operations, deployment, monitoring, scaling]
verified:
  - by: openwiki/0.7.1
    at: 2026-10-09T21:28:29.291Z
sources:
  - id: openwiki-source-b79fbbd921df689b4bbdc82f
    resource: repo://docker-compose.yml
  - id: openwiki-source-012f2c78e3b1446dfc35803f
    resource: repo://Makefile
  - id: openwiki-source-3ea4ae9b4b98a62545a81494
    resource: repo://src/arete/api/main.py
  - id: openwiki-source-b465357f807c83adb7d1fddf
    resource: repo://src/arete/config.py
  - id: openwiki-source-ee03fa6c6caf83a873632b50
    resource: repo://src/arete/scheduler.py
generated: { by: "openwiki/0.7.1", at: "2026-10-09T21:28:29.291Z" }
---

## Overview

The Arete application follows a modern deployment pipeline combining local development, containerized production stacks, and automated background jobs. The system is designed for reliability, scalability, and maintainability through clear separation of concerns between the API backend, frontend SPA, and background synchronization services.

## Deployment Pipeline

### Development Setup

Development is initiated with `make dev`, which starts both the API (auto-reload) and frontend (Vite HMR) simultaneously:

```bash
make dev
```

This launches:
- **Backend API** on port 8000 (uvicorn) with hot reload
- **Frontend** on port 5173 (Vite) with Hot Module Replacement

Both services are coordinated by the `make` utility which manages dependencies and environment setup.

### Containerized Production Deployment

The `make docker` target builds and deploys a production-like stack using Docker Compose:

```bash
make docker
```

This creates two containers:
- **Backend** (`arete-backend`) on port 8001, running the API with `--reload`
- **Frontend** (`arete-frontend`) on port 3080, serving the React SPA

Key configuration from `docker-compose.yml`:
- Backend exposes port 8000 internally, mapped to 8001 externally
- Frontend serves on port 3080, proxying API requests to the backend
- Shared data volume at `./data:/app/data` ensures consistency between containers
- Health checks ensure the backend is responsive before considering the stack healthy

### Service Dependencies

- **Backend** (`arete-backend`): Handles HTTP API requests, Garmin/Strava sync orchestration, and daily scheduling
- **Frontend** (`arete-frontend`): Provides the React-based user interface with real-time workout data
- **Database**: DuckDB (local or MotherDuck remote) stores session data, plans, and coaching artifacts
- **Observability**: Metrics, logging, and health endpoints for monitoring

## System Architecture

<!-- openwiki: broken internal link [/openwiki/architecture.md] link "/openwiki/architecture.md" is root-absolute, which no real consumer resolves against the repository root (not a coding agent reading the page, not GitHub's Markdown renderer, not a local viewer); use a path relative to this file instead. Fix the href or restore the target, then delete this comment. -->
See [Architecture](/openwiki/architecture.md) for a high-level overview of the system design, including:
- Coaching stack with one owner per behavior
- Agent runtime with middleware pipeline
- Service layer reusing domain modules
- Daily sync entrypoints for Garmin/Strava data ingestion

Core components:
- **Coaching**: Responsible for profile assembly, briefing generation, and feedback
- **Agents**: Modular agent framework built with LangChain, supporting chat, briefing, feedback, and review profiles
- **Services**: Domain-specific services (garmin, strava, strength, features)
- **Observability**: Provider usage tracking and model-boundary timing

## Configuration Management

Configuration is centralized in `src/arete/config.py` and follows these principles:

### Source of Truth
- All configuration is read from environment variables via `os.getenv()`
- `.env` files are loaded via `python-dotenv` for local development
- Explicit defaults are provided for every configuration property

### Key Properties

| Property | Description | Default |
|----------|-------------|---------|
| `ARETE_DB` | Database target (local DuckDB or MotherDuck URI) | `data/arete.duckdb` |
| `ARETE_AUTO_SYNC_HOUR` | Hour for daily Garmin/Strava sync | `None` (disabled) |
| `FRONTEND_URL` | Browser origin for OAuth callbacks | `http://localhost:3080` |
| `LLM_PROVIDER` | LLM provider (ollama, openrouter, github) | `ollama` |
| `LLM_CONTEXT_TOKENS` | Context window size (min 8192) | `65536` |
| `ARETE_LOG_LEVEL` | Logging level | `INFO` |

### Validation
Some properties include runtime validation:
- `LLM_CONTEXT_TOKENS` must be ≥ 8192
- `ARETE_AUTO_SYNC_HOUR` must be 0–23
- `auto_sync_hour` raises `ValueError` if out of range

### Database Adaptation
- Local DB: data resides in `data/` directory
- Remote DB (MotherDuck): data lives in `/tmp/arete-data` on the server
- `data_dir` adapts based on database mode

## Background Jobs & Scheduling

### Daily Sync

The `scheduler.py` module orchestrates daily synchronization of Garmin and Strava data:

1. **Garmin Sync** (`daily_sync()`):
   - Checks if the scheduled hour has arrived
   - Fetches activities via `GarminClient`
   - Syncs fitness data to the database
   - Handles token management and error resilience

2. **Strava Sync** (`strava`):
   - Imports workout sessions via Strava API
   - Tracks imported count in the status report

3. **Briefing Generation** (`write_daily_briefing()`):
   - Generates coach briefings after sync completes
   - Triggered by the scheduler before daily briefing

4. **Weekly Review** (`write_weekly_review()`):
   - Runs on Mondays to summarize the past week
   - Sent as a notification to the planning page

### Auto-Sync

When `ARETE_AUTO_SYNC_HOUR` is set (e.g., `9`), the system performs Garmin/Strava syncs automatically at the specified hour. This is controlled by the `arete-daily-sync` task in `docker-compose.yml`.

## Scaling & Performance

### Horizontal Scaling

- **API Layer**: Single-process FastAPI app with async I/O; suitable for moderate concurrent users
- **Frontend**: Stateless React SPA; scales horizontally behind a reverse proxy
- **Background Workers**: Scheduler runs as a single asyncio task; for higher throughput, consider sharding the sync workload

### Resource Considerations

- **Memory**: The agent runtime maintains conversation state and tool contexts; monitor memory usage
- **CPU**: Model inference dominates CPU load; consider GPU acceleration for larger models
- **Database**: DuckDB is optimized for analytical queries; ensure adequate disk I/O

## Monitoring & Observability

### Health Checks

- **API Health** (`/health`): Confirms DuckDB connectivity and schema version
- **Sync Status** (`/sync/status`): Reports last run time and per-source outcomes
- **Metrics**: Exposed via FastAPI endpoints; integrated with LangSmith for tracing

### Logging

Logging is configured in `src/arete/config.py` with level from `ARETE_LOG_LEVEL` (default: INFO). All major operations are logged:
- Sync status transitions
- Agent invocations and tool calls
- Error conditions and exceptions

### Tracing

LangSmith integration enables distributed tracing for the shared coaching agent, capturing:
- Model calls and their latency
- Tool executions and durations
- Cross-service request flows

## Maintenance Procedures

### Regular Tasks

1. **Database Backups**
   - Schedule periodic snapshots of the DuckDB database
   - Verify backup integrity before deployments

2. **Container Hygiene**
   - Remove unused images and volumes periodically
   - Update base images (Python, Node) to address security patches

3. **Configuration Rotation**
   - Rotate secrets (OLLAMA_BASE_URL, CRON_SECRET, WEB_PUSH_* keys) regularly
   - Audit environment variables for unnecessary permissions

4. **Monitoring Alerts**
   - Alert on prolonged sync failures
   - Monitor API error rates and response times
   - Watch for memory leaks in long-running processes

### Incident Response

- **Sync Failure**: Check Garmin/Strava API connectivity; verify tokens and permissions
- **Performance Degradation**: Profile the scheduler; consider increasing `TICK_SECONDS` or batching
- **Data Loss**: Ensure `ARETE_AUTO_SYNC_HOUR` is correctly set; verify database durability

## Summary

The Arete platform combines a robust deployment pipeline with a well-defined operating model. Development leverages `make dev` for rapid iteration, while production uses Docker Compose for reproducible environments. The system's modular architecture (architecture.md) and centralized configuration (configuration.md) enable safe evolution and operational control.

Key operational touchpoints:
- **Deploy**: `make docker` for production, `make dev` for development
- **Monitor**: `/health`, `/sync/status`, and LangSmith tracing
- **Maintain**: Regular config audits, database backups, and container hygiene
- **Scale**: Horizontal scaling of frontend; potential sharding for background sync
