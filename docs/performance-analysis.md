# Análisis de rendimiento de la API

Medición reproducible con `scripts/api_bench.py` sobre los datos reales de
desarrollo (5.344 partidos, 120.321 líneas de jugador, 263 MB de base de datos),
con gunicorn y `DJANGO_DEBUG=False`, como en producción.

## Método

- `python scripts/api_bench.py endpoints` mide cada grupo de URLs en frío (la
  caché se evita con un parámetro de consulta único) y en caliente.
- `python scripts/api_bench.py load --clients 20 --seconds 30 --cold-ratio 0`
  lanza usuarios virtuales con una mezcla de tráfico de navegación (ligas,
  clasificaciones, equipos, jugadores, líderes, búsqueda). `--cold-ratio 1`
  fuerza todas las peticiones a la ruta sin caché (peor caso, p. ej. justo tras
  una ingesta, que vacía la caché).
- Las URLs se descubren a través de la propia API, así que el script sirve para
  cualquier entorno.

## Resultados (20 clientes concurrentes)

| Configuración | req/s | p50 | p95 |
|---|---:|---:|---:|
| Punto de partida: 2 workers, conexión nueva por petición, pocos endpoints en caché | 63 | 282 ms | 410 ms |
| + conexiones persistentes (`CONN_MAX_AGE=60`) | 141 | 112 ms | 170 ms |
| + 3 workers | 185 | 77 ms | 134 ms |
| + caché en todos los endpoints de lectura con claves acotadas | **334** | **30 ms** | **54 ms** |

Peor caso (todas las peticiones sin caché): de 47 req/s y p95 de 515 ms a
**136 req/s y p95 de 189 ms**.

Latencia secuencial sin caché: `staff` pasa de 29 a 10,5 ms y `leagues` de 22 a
8 ms; el coste de abrir una conexión a Postgres en cada petición era de unos
19 ms, el mayor de los costes fijos.

### Número de workers (con conexiones persistentes, antes de ampliar la caché)

| Workers | req/s |
|---:|---:|
| 1 | 73 |
| 2 | 141 |
| 3 | 185 |
| 4 | 189 |

El rendimiento deja de escalar a partir de 3 (el generador de carga comparte
CPU con el servidor en esta medición). Para un VPS de 2 vCPU se usa 3 workers
(`GUNICORN_WORKERS`).

### Hilos (`gthread`) frente a workers síncronos

Con 3 workers y 2 hilos el rendimiento sube a 369 req/s en caliente, pero la
latencia de cola empeora (p95 72 ms frente a 57 ms y, en frío, 280 ms frente a
185 ms) por el GIL. Se mantienen workers síncronos.

## Cambios aplicados

- `CONN_MAX_AGE=60` con comprobación de salud de la conexión (`DB_CONN_MAX_AGE`).
- `cache_page` en clasificación, rondas, listado de partidos, box score,
  plantilla, cuerpo técnico, estadísticas y últimos partidos del equipo,
  `team-seasons`, estadísticas del jugador, líderes y all-time (TTL de 30 min a
  24 h). La caché se vacía tras cada ingesta. Se dejan sin caché la búsqueda, el
  comparador y el listado de jugadores porque sus claves dependen de texto libre.
- Producción: 3 workers por defecto y Redis con `--maxmemory 256mb` y política
  `volatile-lru`, de modo que la caché (una entrada por URL distinta) no puede
  crecer sin límite y nunca se expulsan las tareas de Celery en cola.
- Tests: la caché se sustituye por una en memoria en cada test (`conftest.py`),
  para que una respuesta cacheada no se filtre entre tests ni entre ejecuciones.

## Limitaciones y pendiente

- Medido en un único equipo (WSL2) con otros contenedores activos y el
  generador de carga en el mismo contenedor: sirven las cifras relativas, no
  las absolutas. Repetir en el VPS real tras el primer despliegue.
- `stats-history` sigue haciendo del orden de 4-5 consultas por temporada
  (28-65 ms en frío); `standings` agrega ~300 partidos en Python (~40 ms en
  frío). Ambos quedan cubiertos por la caché y no justifican reescribirlos aún.
- Sin pruebas con tráfico real ni con más de 20 clientes simultáneos.
