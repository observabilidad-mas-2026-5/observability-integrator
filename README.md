# observability-integrator

Laboratorio integrador basado en `observability-end-to-end_v2`. Implementa el recorrido Service A → Service B → data-service → PostgreSQL, con Collector, Jaeger, Prometheus, Grafana, Loki, pruebas Python y k6. La configuración Terraform de AWS se prepara para Ohio con los tres servicios ECS, RDS privado y destinos AWS de telemetría; todavía no se ha desplegado.

Service A conserva su API pública. Service B delega mediante HTTPX a `DATA_SERVICE_URL=http://data-service:8002`; solo data-service accede a PostgreSQL. Los tres servicios comparten los modelos de crédito y exportan trazas, métricas y logs correlacionados. AIOps, seguridad y experimentos de caos quedan pendientes; el plan de trabajo se conserva localmente en `PLAN_INTEGRADOR.md`, fuera del seguimiento de Git. La configuración Terraform no implica que existan recursos desplegados en AWS.

## Ejecución local

Con Docker y Docker Compose disponibles, ejecutar desde la raíz:

```powershell
docker compose -f compose.otel.yml config --quiet
docker compose -f compose.otel.yml up -d --build
docker compose -f compose.otel.yml ps
```

Los valores predeterminados permiten arrancar sin crear un `.env`. `.env.example` documenta las variables disponibles y contiene únicamente contraseñas de ejemplo para uso local. No publicar credenciales reales.

| Acceso | Puerto anterior | Puerto del integrador |
|---|---:|---:|
| API /docs | 18000 | 28000 |
| Grafana | 13000 | 23000 |
| Jaeger | 16686 | 26686 |
| Prometheus | 19090 | 29090 |
| OTLP gRPC | 14317 | 24317 |
| OTLP HTTP | 14318 | 24318 |

Todos los puertos publicados están limitados a `127.0.0.1`. Por ejemplo, la API está en http://127.0.0.1:28000/docs y Grafana en http://127.0.0.1:23000. Las variables de entorno o un `.env` pueden sobrescribir estos puertos; evitar valores del laboratorio anterior si ambos se ejecutan simultáneamente.

Compose usa el proyecto `observability-integrator` y la imagen de aplicación `observability-integrator-api:local`, compartida por Service A, Service B y data-service. Los contenedores, la red y los volúmenes administrados por Compose quedan separados por el nombre del proyecto. Los puertos internos, DNS de servicios y destinos OpenTelemetry se conservan.

Para ejecutar la carga k6 con el laboratorio iniciado:

```powershell
docker compose -f compose.otel.yml run --rm k6
```

Los scripts k6 se conservan en `otel/k6/`; los resultados nuevos se guardan en `docs/evidence/integrator/`. Las evidencias de la base inicial se conservan intactas.

Para detener el laboratorio conservando sus volúmenes:

```powershell
docker compose -f compose.otel.yml down
```

## Documentación y pendientes

Se conservan las guías [local](docs/GUIA_LOCAL.md), [AWS](docs/IMPLEMENTACION_INICIAL_AWS.md) y [costos y eliminación](docs/NUBES_COSTOS_Y_ELIMINACION.md). Las guías describen el laboratorio anterior; este README documenta el recorrido de tres servicios. `scripts/validate_infra.ps1` conserva referencias a GCP, que no se incluyó en este repositorio, y no forma parte de la validación local del Módulo A.

## Validación del Módulo A

Consulta el [resumen de evidencias locales](docs/evidence/integrator/README.md), con enlaces a pruebas, trazas, métricas y logs.

```powershell
docker compose -f compose.otel.yml run --rm --no-deps -e OTEL_ENABLED=false -e SERVICE_B_URL= -e PYTHONDONTWRITEBYTECODE=1 -v "${PWD}/tests:/app/tests:ro" service-a python -m pytest -q -p no:cacheprovider /app/tests
python scripts/validate_local.py
python scripts/check_dashboard.py
python scripts/validate_reference_runtime.py
python scripts/validate_failure.py
docker compose -f compose.otel.yml run --rm -e VUS=2 -e DURATION=10s k6 run --summary-export=/results/k6-integrator-smoke.json /scripts/load.js
```

El validador local comprueba CRUD, persistencia tras reiniciar data-service, una traza compartida y relaciones padre-hijo A → B → data-service → SQL, ausencia de consultas y parámetros SQL exportados, métricas y logs de los tres servicios. El validador de fallos detiene brevemente data-service y Service B por separado, comprueba 503 y restaura cada dependencia. Las evidencias nuevas se guardan bajo `docs/evidence/integrator/`.

data-service reutiliza la instrumentación FastAPI/HTTPX/SQLAlchemy y añade spans `credit.persist` y `credit.status_update`. Los spans SQL conservan atributos de sistema, operación y base de datos; el exportador elimina consultas, parámetros, usuario, cadenas de conexión y detalles de excepciones. No registrar cuerpos HTTP ni datos personales en logs.

## Preparación de AWS RDS

data-service admite `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_SSLMODE` y `DATABASE_SSLROOTCERT`. TLS utiliza `verify-full` por defecto fuera del Compose local; montar el certificado CA de RDS y configurar su ruta en `DATABASE_SSLROOTCERT`. `DATABASE_URL` tiene prioridad y debe incluir TLS seguro si se utiliza para RDS. Compose local configura PostgreSQL con TLS desactivado únicamente dentro de la red local de contenedores.

La [preparación AWS con Terraform](infra/aws/README.md) asigna la conexión y el secreto RDS únicamente a data-service, con TLS verificable. Define tres servicios ECS con Service Connect, un Collector por tarea y exportación a X-Ray/CloudWatch. No se crearon recursos ni se publicaron imágenes en ECR. Las validaciones estáticas no equivalen a una conexión RDS ni a telemetría AWS comprobadas. La creación automática de tablas y el usuario administrador son concesiones del laboratorio; un despliegue productivo requiere usuario limitado y migraciones controladas.
