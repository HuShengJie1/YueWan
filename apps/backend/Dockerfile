FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Keep dependency installation cached until the lockfile or project metadata changes.
RUN pip install --no-cache-dir uv==0.11.2
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --frozen --no-dev

# Local development can still use filesystem avatar storage; production selects
# the CloudBase adapter. Keep the fallback directory writable for the non-root user.
RUN mkdir -p /app/var/media && chown -R 10001:10001 /app/var

USER 10001:10001

EXPOSE 8000

# Cloud hosting can inject PORT; local runs fall back to the documented port.
CMD ["sh", "-c", "exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
