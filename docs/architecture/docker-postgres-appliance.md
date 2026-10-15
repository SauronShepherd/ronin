# Ronin appliance: PostgreSQL local y ejecución aislada

## Objetivo

El perfil appliance de Ronin ejecuta la plataforma en Docker, conserva su estado en un PostgreSQL local y lanza cada trabajo pesado en contenedores aislados. Ronin Pro podrá añadir plugins comerciales sobre los mismos contratos, pero no forma parte de esta imagen ni de este compose.

## Topología

```text
cliente
  |
  v
ronin-server  --->  postgres (volumen ronin-postgres)
  |
  +------------->  runner-broker  ---> Docker Engine (único acceso al socket)
                                      |
                                      +--> workers/studios efímeros
```

- `postgres` tiene el volumen persistente `ronin-postgres` y, opcionalmente, publica PostgreSQL sólo en `127.0.0.1` para herramientas locales y backups; nunca en interfaces no locales.
- `server` y `worker` reciben `RONIN_STORAGE_BACKEND=postgres` y el DSN interno del servicio.
- `runner-broker` es el único servicio que recibe `/var/run/docker.sock`; ni el servidor ni los workers tienen autoridad directa para crear contenedores.
- Los workers usan el broker para descubrir una imagen inmutable y ejecutar notebooks o studios con límites de CPU, memoria, tiempo y red.
- Las imágenes de studios no se incluyen dentro de la imagen base de Ronin: se descargan o construyen según el catálogo de runtimes y se ejecutan bajo demanda.

## Persistencia y migraciones

PostgreSQL es el backend explícito del perfil appliance. El arranque debe fallar si falta `RONIN_POSTGRES_DSN`; nunca se degrada silenciosamente a SQLite. SQLite permanece disponible únicamente cuando el usuario ejecuta Ronin directamente para desarrollo local o tests.

La migración es idempotente y se ejecuta desde los adaptadores PostgreSQL antes de atender tráfico. El volumen debe respaldarse como dato de usuario. El DSN y la contraseña se configuran mediante variables de entorno; no se escriben en el repositorio.

El estado durable que debe converger a PostgreSQL incluye jobs, runs, eventos, resultados de celdas, evidencias, auditoría, workspaces, proyectos, entornos, conexiones y catálogo. Los artefactos binarios son una preocupación separada: el perfil local usa un volumen/directorio de artefactos; Ronin Pro podrá sustituirlo por object storage mediante un plugin.

## Contratos de extensión

Los plugins de Ronin sólo dependen de puertos (`JobReadPort`, metadata, auditoría, artifacts, runtime catalog) y no de PostgreSQL directamente. Esto permite que Ronin Pro reemplace adaptadores o añada multi-tenant, cloud y gobierno sin bifurcar el núcleo. Un plugin de studio aporta, como mínimo, su descriptor/runtime y puede añadir UI, rutas REST y workers mediante los contratos del host.

## Operación local

```powershell
Copy-Item .env.example .env
# Edit .env and replace all change-me-* values.
docker compose up -d
docker compose ps
docker compose logs -f server
```

La imagen queda autocontenida en cuanto a servicios y red, pero los secretos y
los modelos son configuración del usuario y por eso no se incluyen en Git.
`.env.example` permite validar la topología sin inventar credenciales reales.

La parada conserva PostgreSQL y los artefactos:

```powershell
docker compose down
```

Backup lógico del PostgreSQL del appliance:

```powershell
python tools/ronin_postgres_backup.py --backup ./.ronin/backups/ronin.dump
```

Restaurar reemplaza datos existentes y exige confirmación explícita:

```powershell
python tools/ronin_postgres_backup.py --restore ./.ronin/backups/ronin.dump --force
```

La eliminación explícita de datos requiere retirar los volúmenes de Compose y debe considerarse una operación destructiva:

```powershell
docker compose down -v
```

## Estado de implementación

Implementado en esta fase:

- servicio PostgreSQL 16 Alpine con healthcheck y volumen persistente;
- DSN compartido por Compose y selección explícita de backend en server/worker;
- worker capaz de consumir el puerto PostgreSQL de jobs;
- workflows, schedules y bundles portables persistidos mediante adaptador PostgreSQL;
- labs, pipelines y ejecuciones del ML Studio persistidos mediante adaptador PostgreSQL;
- experimentos, runs, modelos registrados y evaluaciones ML persistidos mediante adaptador PostgreSQL;
- validación fail-closed de backend y DSN;
- autoridad Docker confinada al runner-broker;
- pruebas de topología y configuración.

La cualificación local del appliance queda completada: la imagen se construye, PostgreSQL, server, runner-broker y worker arrancan con Compose, el server responde `200 {"status":"ready"}`, los adaptadores PostgreSQL se inicializan correctamente y la cualificación Docker real pasa tanto para ejecución como para recuperación tras `SIGKILL`. El journey v0.1 completo también queda verificado contra la imagen inmutable construida localmente. La cualificación CI con PostgreSQL/Docker real y la ejecución de studios que requieran imágenes externas siguen siendo gates de infraestructura separados.

La misma cualificación Docker se puede repetir localmente con:

```powershell
./tools/run_docker_qualification.ps1
```

El workflow equivalente está en `.github/workflows/docker-qualification.yml` y
ejecuta PostgreSQL real, la suite de storage y los escenarios Docker con una
imagen identificada por digest.
