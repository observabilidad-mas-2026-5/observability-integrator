# observability-integrator

Construimos nuestro laboratorio integrador sobre `observability-end-to-end_v2`. Implementamos el recorrido Service A → Service B → data-service → PostgreSQL, con Collector, Jaeger, Prometheus, Grafana, Loki, pruebas Python y k6. También lo desplegamos y validamos en AWS Ohio con tres servicios ECS, RDS privado, X-Ray y CloudWatch; documentamos los resultados en las [evidencias reales de AWS](docs/evidence/integrator/aws/README.md).

Conservamos la API pública de Service A. Service B delega mediante HTTPX a `DATA_SERVICE_URL=http://data-service:8002`; solo data-service accede a PostgreSQL. Los tres servicios comparten los modelos de crédito y exportan trazas, métricas y logs correlacionados. Completamos los dos experimentos de caos descritos abajo; mantenemos AIOps y seguridad como líneas de trabajo del equipo, sin atribuirles validaciones en esta entrega. Conservamos nuestro plan localmente en `PLAN_INTEGRADOR.md`, fuera del seguimiento de Git. Distinguimos la configuración Terraform de los despliegues comprobados mediante evidencias AWS.

## Ejecución local

Con Docker y Docker Compose disponibles, ejecutamos desde la raíz:

```powershell
docker compose -f compose.otel.yml config --quiet
docker compose -f compose.otel.yml up -d --build
docker compose -f compose.otel.yml ps
```

Podemos arrancar con los valores predeterminados sin crear un `.env`. En `.env.example` documentamos las variables disponibles e incluimos únicamente contraseñas de ejemplo para uso local. No publicamos credenciales reales.

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

Consultamos la guía [local e histórica](docs/GUIA_LOCAL.md) y la [operación AWS vigente](infra/aws/README.md), que reúne despliegue, imágenes, estado compartido, costos y pausa/reactivación de ECS. Retiramos las guías históricas de AWS/costos por describir la arquitectura anterior; conservamos sus [capturas](docs/evidence/integrator/aws/legacy-aws-captures.md), sin presentarlas como evidencia del integrador. `scripts/validate_infra.ps1` conserva referencias a GCP, que no incluimos en este repositorio, y no forma parte de la validación local del Módulo A.

## Validación del Módulo A

Para AIOps mantenemos la condición conjunta de **tasa de errores superior a la línea base + 2σ Y latencia p99 superior al umbral del SLO**, en el mismo servicio y periodo. Distinguimos el SLO de trabajo por solicitud del percentil usado en la alerta. En el [criterio de medición](infra/aws/metrics-queries.md) explicamos denominadores, presupuesto de errores y burn rate; no atribuimos a los experimentos alertas o MTTD que no demostramos.

Ejecutamos el [experimento de caos 1: latencia de 200 ms en Service B](docs/CHAOS_EXPERIMENT_1.md) en AWS y lo desactivamos tras la limpieza. En las [evidencias reales y locales](docs/evidence/integrator/aws/chaos/README.md) distinguimos ambos alcances; confirmamos 540 demoras en B y la recuperación, sin errores ni consumo del presupuesto del SLO de trabajo.

En el [experimento 2: errores en data-service](docs/CHAOS_EXPERIMENT_2.md) registramos 50 errores entre 500 intentos internos (10 %). Service Connect los recuperó: las 1350 solicitudes finales de las tres fases devolvieron 200. En el [informe AWS](docs/evidence/integrator/aws/chaos/errors-20261018T153105Z/README.md) distinguimos el SLO del servidor del cliente y conservamos el diagnóstico fallido anterior, las trazas, métricas, logs y comprobaciones de limpieza. Para pausar o reanudar, conservamos explícitamente las etiquetas actuales descritas en la guía AWS.

Consultamos el [resumen de evidencias locales](docs/evidence/integrator/README.md), con enlaces a pruebas, trazas, métricas y logs.

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

Con nuestra [infraestructura AWS con Terraform](infra/aws/README.md) asignamos la conexión y el secreto RDS únicamente a data-service, con TLS verificable. Ejecutamos tres servicios ECS con Service Connect, un Collector por tarea y exportación a X-Ray/CloudWatch. Tras los experimentos conservamos A/B en `api:chaos-latency-v1`, data-service en `api:chaos-errors-v2` y los Collectors en `collector:traces-v2`, con ambas inyecciones desactivadas. Mantenemos `api:initial` sin sobrescribir; utilizamos el exporter `awsxray`, sin modificar el destino regional X-Ray. En la [prueba privada temporal](infra/aws/SYNTHETIC_TEST.md) confirmamos HTTP 201, lectura persistida HTTP 200, la traza A → B → data-service → PostgreSQL y logs correlacionados de los tres servicios. Retiramos sus recursos temporales; conservamos las aplicaciones y RDS activos, por lo que generan costos. Aceptamos la creación automática de tablas y el usuario administrador solo como concesiones del laboratorio; para un despliegue productivo necesitamos un usuario limitado y migraciones controladas.
