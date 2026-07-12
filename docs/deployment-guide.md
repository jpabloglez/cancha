# Guía de despliegue

Esta guía describe cómo obtener un dominio y publicar la aplicación en
producción con coste mínimo. Se presentan dos rutas:

- **Opción A — VPS único** (Hetzner + Docker Compose): la más sencilla de
  operar para un desarrollador en solitario. Un solo servidor ejecuta todos
  los servicios tal como están en `docker-compose.yml`. Coste estimado:
  **~4 €/mes** + dominio.
- **Opción B — servicios gestionados gratuitos** (Vercel + Railway): mayor
  complejidad de configuración inicial pero cero coste hasta tráfico
  significativo. Coste estimado: **0 €/mes** para volúmenes bajos.

---

## 1. Dominio

### Registradores recomendados

| Registrador | Por qué usarlo |
|---|---|
| [Porkbun](https://porkbun.com) | Precios al coste, DNS gratuito, UI limpia. `.xyz` desde ~1 $/año el primer año. |
| [Cloudflare Registrar](https://www.cloudflare.com/products/registrar/) | Precio al coste sin margen, CDN y proxy gratuitos integrados. |
| [OVH](https://www.ovhcloud.com/es/domains/) | Opción europea, soporte en español. `.es` desde ~7 €/año. |

### Nombres sugeridos

El TLD `.es` es apropiado dado el foco del proyecto. Alternativas baratas:
`.app`, `.dev`, `.xyz`.

Ejemplos: `basketstats.es`, `cancha-stats.es`, `estadisticasfeb.es`.

### Pasos

1. Comprar el dominio en el registrador elegido.
2. Apuntar los nameservers a Cloudflare (gratuito) para aprovechar el proxy,
   el CDN y los certificados SSL automáticos. Si no se usa Cloudflare se puede
   gestionar el DNS directamente en el registrador.
3. Crear registros DNS según la opción de despliegue elegida (ver §3 y §4).

---

## 2. Trabajos previos al despliegue

### 2.1 Variables de entorno de producción

Crear `backend/.env` para producción a partir de `backend/.env.example`:

```env
DJANGO_SECRET_KEY=<clave aleatoria de 50+ caracteres>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=api.tudominio.es,tudominio.es

DATABASE_URL=postgres://user:pass@host:5432/basketball_stats
REDIS_URL=redis://redis:6379/0

CORS_ALLOWED_ORIGINS=https://tudominio.es

SENTRY_DSN=<opcional>
INGEST_STORE_MEDIA=True
```

Crear `frontend/.env.local` (o variables de entorno en la plataforma):

```env
NEXT_PUBLIC_API_BASE_URL=https://api.tudominio.es/api/v1
API_INTERNAL_BASE_URL=http://backend:8000/api/v1    # solo si frontend está en el mismo Docker network
NEXT_PUBLIC_CONTACT_EMAIL=derechos@tudominio.es
NEXT_PUBLIC_GITHUB_URL=https://github.com/<org>/basquetestads
```

### 2.2 Secreto de Django

Generar una clave segura:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

### 2.3 Migración y datos iniciales

Al arrancar el backend por primera vez en producción:

```bash
# Migraciones
python manage.py migrate

# Sincronizar tareas periódicas en la BD de Celery Beat
python manage.py sync_beat_schedule

# Backfill histórico (5 temporadas FEB + ACB)
python manage.py backfill --seasons 5

# Backfill de jornadas para datos ya ingeridos
python manage.py backfill_rounds
```

### 2.4 Archivos estáticos

```bash
python manage.py collectstatic --noinput
```

---

## 3. Opción A — VPS con Docker Compose (recomendada)

### 3.1 Proveedor: Hetzner Cloud

El servidor **CX22** (2 vCPU, 4 GB RAM, 40 GB SSD, 20 TB tráfico) cuesta
~**3,79 €/mes** en Finlandia o Alemania. Es suficiente para los cinco
contenedores del `docker-compose.yml`.

Alternativa totalmente gratuita: **Oracle Cloud Free Tier** ofrece 4 núcleos
ARM + 24 GB RAM en instancias `A1.Flex`; requiere cuenta con tarjeta de
crédito pero no cobra mientras se mantenga dentro del free tier.

### 3.2 Aprovisionamiento del servidor

```bash
# En el servidor (Ubuntu 22.04 LTS)
apt update && apt upgrade -y
apt install -y docker.io docker-compose-plugin git

# Usuario sin root para Docker
adduser deploy
usermod -aG docker deploy
```

### 3.3 Proxy inverso con Caddy

Caddy gestiona SSL automático vía Let's Encrypt sin configuración adicional.

```bash
apt install -y caddy
```

`/etc/caddy/Caddyfile`:

```
tudominio.es {
    reverse_proxy localhost:3000
}

api.tudominio.es {
    reverse_proxy localhost:8000
    handle_path /media/* {
        root * /srv/basquetestads/backend
        file_server
    }
}
```

```bash
systemctl enable --now caddy
```

### 3.4 Despliegue de la aplicación

```bash
# Como usuario deploy
git clone https://github.com/<org>/basquetestads /srv/basquetestads
cd /srv/basquetestads

# Crear los archivos de entorno
cp backend/.env.example backend/.env   # y editar
cp frontend/.env.local.example frontend/.env.local   # y editar

# Construir y arrancar
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Primera vez: migraciones y datos
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py collectstatic --noinput
docker compose exec backend python manage.py sync_beat_schedule
docker compose exec backend python manage.py backfill --seasons 5
docker compose exec backend python manage.py backfill_rounds
```

#### `docker-compose.prod.yml` (overrides de producción)

Crear este fichero en la raíz del repositorio para sobreescribir los valores
de desarrollo sin tocar `docker-compose.yml`:

```yaml
services:
  backend:
    command: gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2
    volumes: []     # no montar código en prod; usar la imagen construida

  worker:
    volumes: []

  frontend:
    build:
      context: ./frontend
    command: node server.js   # next build && next start
    environment:
      - NODE_ENV=production
    volumes: []
```

> **Nota:** añadir `gunicorn` a `backend/requirements.txt` si aún no está.

### 3.5 DNS (Cloudflare)

| Tipo | Nombre | Valor | Proxy |
|---|---|---|---|
| A | `@` | IP del VPS | ✓ (naranja) |
| A | `api` | IP del VPS | ✓ (naranja) |

### 3.6 Actualizaciones

```bash
cd /srv/basquetestads
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec backend python manage.py migrate
```

---

## 4. Opción B — Servicios gestionados gratuitos

Esta arquitectura divide los componentes entre plataformas:

| Componente | Plataforma | Plan gratuito |
|---|---|---|
| Frontend (Next.js) | [Vercel](https://vercel.com) | Hobby (ilimitado para OSS) |
| Backend (Django + Gunicorn) | [Railway](https://railway.app) | 5 $/mes de crédito |
| Worker + Beat (Celery) | Railway (mismo proyecto) | incluido en el crédito |
| PostgreSQL | Railway | 1 GB incluido |
| Redis | [Upstash](https://upstash.com) | 10 000 comandos/día gratis |

### 4.1 Base de datos — Railway PostgreSQL

1. Crear proyecto en Railway → **New Service → Database → PostgreSQL**.
2. Copiar la variable `DATABASE_URL` que Railway genera.

### 4.2 Redis — Upstash

1. Crear cuenta en Upstash → **Create Database** (región EU West).
2. Copiar la URL de conexión (`rediss://...`).

### 4.3 Backend — Railway

1. **New Service → GitHub Repo** → seleccionar `basquetestads`.
2. Configurar **Root Directory**: `backend`.
3. **Start command**: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2`
4. **Variables de entorno** (pestaña Variables en Railway):
   ```
   DATABASE_URL=<de Railway PostgreSQL>
   REDIS_URL=<de Upstash>
   DJANGO_SECRET_KEY=<generada>
   DJANGO_DEBUG=False
   DJANGO_ALLOWED_HOSTS=<slug>.railway.app,api.tudominio.es
   CORS_ALLOWED_ORIGINS=https://tudominio.es
   ```
5. **Custom domain**: añadir `api.tudominio.es` en Settings → Domains.
6. Tras el primer deploy, ejecutar en la consola Railway:
   ```bash
   python manage.py migrate
   python manage.py collectstatic --noinput
   python manage.py sync_beat_schedule
   python manage.py backfill --seasons 5
   python manage.py backfill_rounds
   ```

### 4.4 Worker Celery — Railway

1. En el mismo proyecto Railway → **New Service → GitHub Repo** →
   mismo repositorio, mismo Root Directory `backend`.
2. **Start command**: `celery -A config worker --beat --loglevel=info`
3. Mismas variables de entorno que el backend.

### 4.5 Frontend — Vercel

1. Importar repositorio en Vercel → **Root Directory**: `frontend`.
2. Framework: **Next.js** (detectado automáticamente).
3. Variables de entorno en Vercel:
   ```
   NEXT_PUBLIC_API_BASE_URL=https://api.tudominio.es/api/v1
   NEXT_PUBLIC_CONTACT_EMAIL=derechos@tudominio.es
   NEXT_PUBLIC_GITHUB_URL=https://github.com/<org>/basquetestads
   ```
   > `API_INTERNAL_BASE_URL` no aplica en Vercel (el SSR llama a la URL pública).
4. **Custom domain**: añadir `tudominio.es` en Settings → Domains de Vercel.

### 4.6 DNS (Cloudflare)

| Tipo | Nombre | Valor | Proxy |
|---|---|---|---|
| CNAME | `@` | `cname.vercel-dns.com` | ✗ (gris, Vercel gestiona SSL) |
| CNAME | `api` | `<slug>.railway.app` | ✓ (naranja) |

### 4.7 Almacenamiento de medios en Opción B

Railway y Vercel no tienen sistema de ficheros persistente. Para logos y fotos:

1. Crear un bucket gratuito en **Cloudflare R2** (10 GB gratis).
2. Instalar `django-storages[s3]` + `boto3`.
3. Configurar `DEFAULT_FILE_STORAGE` en settings con credenciales R2.
4. Añadir variables `AWS_*` al servicio backend en Railway.

---

## 5. CI/CD con GitHub Actions

El repositorio ya tiene path filters en los workflows de CI. Añadir un paso
de despliegue según la opción elegida:

### Opción A (VPS)

```yaml
# .github/workflows/deploy.yml
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: SSH deploy
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: deploy
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd /srv/basquetestads
            git pull
            docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
            docker compose exec -T backend python manage.py migrate
```

### Opción B (Railway + Vercel)

Railway y Vercel despliegan automáticamente en cada push a `main` desde
GitHub. No se necesita workflow adicional para el despliegue.

---

## 6. Checklist pre-lanzamiento

- [ ] `DJANGO_DEBUG=False` en producción
- [ ] `DJANGO_SECRET_KEY` aleatoria y secreta (no en el repositorio)
- [ ] `ALLOWED_HOSTS` y `CORS_ALLOWED_ORIGINS` apuntan al dominio real
- [ ] SSL activo (Caddy/Cloudflare/Vercel lo gestionan automáticamente)
- [ ] Migraciones aplicadas (`migrate`)
- [ ] Estáticos recopilados (`collectstatic`)
- [ ] Tareas Beat sincronizadas (`sync_beat_schedule`)
- [ ] Backfill histórico ejecutado (`backfill --seasons 5`)
- [ ] Jornadas backfilleadas (`backfill_rounds`)
- [ ] Robots.txt correcto (no bloquear el crawl público)
- [ ] Variables de entorno de contacto y GitHub actualizadas en el frontend
- [ ] Comprobar que `/api/v1/leagues/` responde desde el navegador
- [ ] Comprobar que la página de inicio carga datos reales (no el seed)

---

## 7. Costes estimados

| Escenario | Mensual |
|---|---|
| Opción A — Hetzner CX22 + dominio .es | ~5 €/mes |
| Opción A — Oracle Cloud Free + dominio .es | ~1 €/mes (solo dominio) |
| Opción B — Vercel + Railway + Upstash | 0–5 $/mes según uso |
| Almacenamiento medios (Cloudflare R2, <10 GB) | 0 $/mes |

Para un proyecto no comercial de una sola persona, la Opción A en un VPS
Hetzner CX22 es la recomendación principal: Docker Compose ya está
configurado, no hay vendor lock-in, y el coste es predecible.
