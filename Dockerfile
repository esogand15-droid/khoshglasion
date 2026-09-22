FROM python:3.11-slim

WORKDIR /app

# Create non-root user and data dir for SQLite persistence
RUN useradd -m -u 1000 appuser && mkdir -p /app/data && chown -R appuser:appuser /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/dist/ ./frontend/dist/
COPY alembic.ini ./alembic.ini
COPY alembic/ ./alembic/
COPY pyproject.toml ./

RUN mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH=/app
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:' + __import__('os').environ.get('PORT','8080') + '/health', timeout=3)"

CMD ["sh", "-c", "mkdir -p /app/data && alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
