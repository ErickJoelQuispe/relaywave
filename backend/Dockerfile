# syntax=docker/dockerfile:1

# ---- Builder stage: resolve and install dependencies with uv ----
FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Copy only the dependency manifests first so this layer stays cached
# across builds whenever app code changes but dependencies don't.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Now copy the application source and install the project itself.
# README.md is required too: pyproject.toml declares it as the package
# readme, and hatchling fails the build without it.
COPY app ./app
COPY README.md ./
RUN uv sync --frozen --no-dev

# ---- Runtime stage: slim image with only the venv + app code ----
FROM python:3.12-slim AS runtime

RUN groupadd --system --gid 999 app \
    && useradd --system --gid 999 --uid 999 --create-home app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv ./.venv
COPY --from=builder --chown=app:app /app/app ./app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
