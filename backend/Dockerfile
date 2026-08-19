# Backend image: Django + DRF + Celery.
# Single-stage build kept intentionally simple for a low-traffic, non-commercial
# deployment. A multi-stage build would reduce the final image size at the cost
# of more complex Playwright/Chromium wiring — a viable next step if image size
# becomes a concern in production.
FROM python:3.12-slim-bookworm

# Avoid writing .pyc files and force unbuffered stdout/stderr for live logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System build dependencies for psycopg and lxml.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Chromium for the Playwright-based ACB connector (JS-rendered source). Pulls
# the browser plus its system libraries. Comment this out if only FEB (httpx)
# ingestion is needed, to keep the image small.
RUN python -m playwright install --with-deps chromium

COPY . .

# Run as a non-root user (defence-in-depth; containers that run as root are a
# security risk if the process is compromised).
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R appuser:appgroup /app/media /app/staticfiles
USER appuser

EXPOSE 8000

# Healthcheck: ping the Django /api/v1/leagues/ endpoint every 30 s. The
# endpoint hits the database so it validates both the app and DB connectivity.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/leagues/')" || exit 1

# Default command is overridden per-service in docker-compose.yml.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
