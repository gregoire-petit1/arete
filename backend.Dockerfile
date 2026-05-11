FROM python:3.11-slim AS base

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files first (cache layer)
COPY pyproject.toml uv.lock README.md ./

# Install production dependencies only
RUN uv sync --frozen --no-dev --no-install-project

# Copy source code
COPY src/ src/

# Install the project itself
RUN uv sync --frozen --no-dev

# Create data directory
RUN mkdir -p data

# Expose API port
EXPOSE 8000

# Run with uvicorn
CMD ["uv", "run", "uvicorn", "arete.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
