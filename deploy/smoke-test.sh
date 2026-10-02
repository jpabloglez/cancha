#!/usr/bin/env bash
# End-to-end smoke test of the production stack (docker-compose.prod.yml).
#
# Builds and starts every service with throwaway secrets, a temporary Postgres
# directory and plain-HTTP hostnames (no certificates needed), seeds demo data
# and checks the public behaviour through Caddy: frontend SSR, API, CORS, media
# serving, the Celery worker and the Redis cache. Never touches ./data/postgres.
#
# Usage: deploy/smoke-test.sh [--keep]   (--keep leaves the stack running)
set -euo pipefail

cd "$(dirname "$0")/.."
KEEP=0; [ "${1:-}" = "--keep" ] && KEEP=1

HTTP_PORT="${SMOKE_HTTP_PORT:-18080}"
HTTPS_PORT="${SMOKE_HTTPS_PORT:-18443}"
WORK="$(mktemp -d)"
ENV_ROOT="$WORK/root.env"
BACKEND_ENV="$WORK/backend.env"
export COMPOSE_PROJECT_NAME="basquets-smoke"
export POSTGRES_DATA_DIR="$WORK/postgres"
export HTTP_PORT HTTPS_PORT

# Root env: plain-HTTP hostnames so Caddy does not try to obtain certificates.
cat > "$ENV_ROOT" <<ENV
DOMAIN=http://web.localhost
API_DOMAIN=http://api.localhost
POSTGRES_PASSWORD=smoke-password
NEXT_PUBLIC_API_BASE_URL=http://api.localhost:${HTTP_PORT}/api/v1
NEXT_PUBLIC_SITE_URL=http://web.localhost:${HTTP_PORT}
NEXT_PUBLIC_CONTACT_EMAIL=smoke@example.org
NEXT_PUBLIC_GITHUB_URL=https://github.com/jpabloglez/cancha
ENV
cat > "$BACKEND_ENV" <<ENV
DJANGO_SECRET_KEY=smoke-secret-key-not-for-production
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=api.localhost,backend
DATABASE_URL=postgres://basketball_stats:smoke-password@db:5432/basketball_stats
REDIS_URL=redis://redis:6379/0
REDIS_CACHE_URL=redis://redis:6379/1
CORS_ALLOWED_ORIGINS=http://web.localhost:${HTTP_PORT}
INGEST_STORE_MEDIA=False
API_THROTTLE_RATE=20/min
ENV

# docker-compose.prod.yml reads backend/.env.prod; point it at the temp file via
# a temporary copy and restore afterwards.
BACKUP=""
if [ -f backend/.env.prod ]; then BACKUP="$WORK/backend.env.prod.bak"; cp backend/.env.prod "$BACKUP"; fi
cp "$BACKEND_ENV" backend/.env.prod

DC=(docker compose --env-file "$ENV_ROOT" -f docker-compose.prod.yml)

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "--- smoke test FAILED: recent logs ---"
    "${DC[@]}" logs --tail=40 2>&1 || true
  fi
  if [ "$KEEP" -eq 0 ]; then
    "${DC[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
    docker run --rm -v "$WORK:/w" alpine rm -rf /w/postgres >/dev/null 2>&1 || true
  fi
  if [ -n "$BACKUP" ]; then cp "$BACKUP" backend/.env.prod; else rm -f backend/.env.prod; fi
  rm -rf "$WORK" 2>/dev/null || true
  exit "$status"
}
trap cleanup EXIT

PASS=0
check() { # check <description> <command...>
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then PASS=$((PASS+1)); echo "  ok   $desc"
  else echo "  FAIL $desc"; return 1; fi
}
web() { curl -fsS --max-time 20 -H "Host: web.localhost" "http://127.0.0.1:${HTTP_PORT}$1"; }
api() { curl -fsS --max-time 20 -H "Host: api.localhost" "$@"; }
API="http://127.0.0.1:${HTTP_PORT}"

echo "== building and starting the stack"
"${DC[@]}" up -d --build

echo "== waiting for the backend"
for _ in $(seq 1 60); do
  if "${DC[@]}" exec -T backend python -c \
     "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/v1/leagues/')" >/dev/null 2>&1; then
    break
  fi
  sleep 3
done

echo "== migrating and seeding demo data"
"${DC[@]}" exec -T backend python manage.py migrate --noinput >/dev/null
"${DC[@]}" exec -T backend python manage.py seed_demo_data >/dev/null
"${DC[@]}" exec -T backend sh -c 'echo smoke > /app/media/smoke.txt'

echo "== checks"
LEAGUE_JSON="$(api "$API/api/v1/leagues/")"
LEAGUE_SLUG="$(echo "$LEAGUE_JSON" | python3 -c 'import sys,json;print(json.load(sys.stdin)["results"][0]["slug"])')"
LEAGUE_NAME="$(echo "$LEAGUE_JSON" | python3 -c 'import sys,json;print(json.load(sys.stdin)["results"][0]["name"])')"
TEAM_SLUG="$(api "$API/api/v1/teams/?limit=1" | python3 -c 'import sys,json;print(json.load(sys.stdin)["results"][0]["slug"])')"

check "API lists leagues through Caddy" api "$API/api/v1/leagues/"
check "API team staff endpoint responds" api "$API/api/v1/teams/${TEAM_SLUG}/staff/"
check "Unknown team returns 404" bash -c "[ \"\$(curl -s -o /dev/null -w '%{http_code}' -H 'Host: api.localhost' $API/api/v1/teams/does-not-exist/)\" = 404 ]"
check "CORS allows the frontend origin" bash -c "curl -sI -H 'Host: api.localhost' -H 'Origin: http://web.localhost:${HTTP_PORT}' $API/api/v1/leagues/ | grep -qi '^access-control-allow-origin: http://web.localhost:${HTTP_PORT}'"
check "CORS rejects other origins" bash -c "! curl -sI -H 'Host: api.localhost' -H 'Origin: http://evil.example' $API/api/v1/leagues/ | grep -qi '^access-control-allow-origin'"
check "Caddy serves /media/ from the shared volume" bash -c "curl -fsS -H 'Host: api.localhost' $API/media/smoke.txt | grep -q smoke"
check "Frontend home renders" bash -c "curl -fsS -H 'Host: web.localhost' $API/ | grep -q 'Basket Stats'"
check "Frontend league page renders league data via the internal API URL" bash -c "curl -fsS -H 'Host: web.localhost' $API/ligas/${LEAGUE_SLUG} | grep -qF '${LEAGUE_NAME}'"
check "Frontend team page renders" bash -c "curl -fsS -H 'Host: web.localhost' $API/equipos/${TEAM_SLUG} | grep -q 'Plantilla'"
check "robots.txt points at the site URL" bash -c "curl -fsS -H 'Host: web.localhost' $API/robots.txt | grep -q 'http://web.localhost:${HTTP_PORT}/sitemap.xml'"
check "Celery worker answers ping" "${DC[@]}" exec -T worker celery -A config inspect ping
check "Worker reports healthy" bash -c "
  for _ in \$(seq 1 20); do
    [ \"\$(docker inspect -f '{{.State.Health.Status}}' ${COMPOSE_PROJECT_NAME}-worker-1)\" = healthy ] && exit 0
    sleep 5
  done; exit 1"
check "API cache lives in Redis db 1, Celery in db 0" bash -c "
  [ \"\$(${DC[*]} exec -T redis redis-cli -n 1 dbsize | tr -d '\\r')\" -gt 0 ]"
check "Redis is memory-capped with volatile-lru eviction" bash -c "
  ${DC[*]} exec -T redis redis-cli config get maxmemory-policy | grep -q volatile-lru"
check "No dev ports are published (only Caddy)" bash -c "
  [ \"\$(docker ps --filter label=com.docker.compose.project=${COMPOSE_PROJECT_NAME} --format '{{.Ports}}' | grep -c '0.0.0.0:\\(5432\\|6379\\|8000\\|3000\\)')\" = 0 ]"

# Last on purpose: once the limit trips, this client IP is throttled for a minute.
check "Public API rate limit answers 429 through Caddy" bash -c "
  for i in \$(seq 1 40); do
    curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: api.localhost' \"$API/api/v1/players/?limit=1&_t=\$i\"
  done | grep -q 429"
check "Frontend pages still render while the public IP is throttled (internal calls exempt)" bash -c "curl -fsS -H 'Host: web.localhost' $API/equipos/${TEAM_SLUG}?x=throttle | grep -q 'Plantilla'"

check "Backup restores into a scratch database with identical row counts" \
  env DC="${DC[*]}" BACKUP_DIR="$WORK/backups" ./scripts/db_verify_backup.sh

echo "== smoke test passed (${PASS} checks)"
