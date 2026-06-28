# Backend image: Django + DRF + Celery.
# Kept intentionally simple for a low-traffic, non-commercial deployment.
FROM python:3.12-slim

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

EXPOSE 8000

# Default command is overridden per-service in docker-compose.yml.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
