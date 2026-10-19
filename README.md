# observability-integrator

Construimos nuestro laboratorio sobre `observability-end-to-end_v2` para entender qué ocurre con una solicitud. A eso llamamos **observabilidad**.

Implementamos Service A → Service B → data-service → PostgreSQL. Lo validamos localmente y en AWS Ohio, con tres servicios ECS y RDS privado. ECS ejecuta contenedores; RDS administra la base de datos. Conservamos las [evidencias AWS](docs/evidence/integrator/aws/README.md).

OpenTelemetry produce trazas —recorridos de solicitudes—, métricas —conteos y medidas— y logs —eventos—. El Collector las recibe y reenvía. En local usamos Jaeger, Prometheus, Grafana y Loki; en AWS, X-Ray y CloudWatch. Conservamos pruebas Python y k6.

En los resultados, HTTP 201 significa que creamos un registro; HTTP 200, que la consulta terminó correctamente; y HTTP 503, que una dependencia no estaba disponible. La latencia es el tiempo que tarda una respuesta.

Conservamos las rutas y respuestas de Service A. Service B llama mediante HTTPX a `DATA_SERVICE_URL=http://data-service:8002`; solo data-service accede a PostgreSQL. Los tres servicios comparten los modelos de crédito y generan trazas, métricas y logs relacionados entre sí.

Completamos dos experimentos de caos. También configuramos alertamiento AIOps y comprobamos componentes por separado; todavía no demostramos la detección correlacionada de un incidente. En seguridad contamos con registros de red, una alarma disparada y un dashboard. Una configuración, por sí sola, no demuestra un despliegue funcionando.

## Estado de nuestra entrega

| Módulo | Qué comprobamos | Qué falta |
|---|---|---|
| A · Arquitectura | Tres microservicios, RDS y señales relacionadas en AWS. | GCP no implementado; Service Connect no acredita el requisito literal de App Mesh. |
| B · AIOps | Configuración de alarmas y pruebas individuales de SNS y Lambda. | Tasa de errores, línea base + 2σ, correlación real con p99, alerta con trace_id y reducción de ruido. |
| C · Seguridad | Flow Logs, filtro de rechazos, alarma con acción SNS y dashboard en AWS. | Línea base, autenticaciones y CVEs; Inspector y Security Hub reportados como bloqueados por permisos. Sin GCP. |
| D · Caos | Latencia de 200 ms y 10 % de errores internos, recuperación y cálculo del presupuesto de errores. | MTTD de alertamiento no medido; no demostramos la meta de dos minutos. |
| E · Madurez | Borrador con ocho componentes y roadmap de tres meses. | Cotejar la fuente académica, revisar la evaluación y completar informe y demostración. |

En la [evaluación de madurez](docs/EVALUACION_MADUREZ_ROADMAP.md) reunimos las evidencias y los pendientes. Los estados corresponden a los registros conservados, no a una consulta nueva de AWS.

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

- [Guía local e histórica](docs/GUIA_LOCAL.md): referencia del laboratorio anterior.
- [Operación AWS](infra/aws/README.md): despliegue, imágenes, estado, costos y pausa/reactivación.
- [Capturas históricas](docs/evidence/integrator/aws/legacy-aws-captures.md): referencias conservadas tras retirar las dos guías desactualizadas; no son evidencia del integrador.

`scripts/validate_infra.ps1` conserva referencias a GCP, que no incluimos, y no forma parte de la validación local del Módulo A.


## Validación del Módulo A

Para AIOps —detección automática de anomalías— exigimos **tasa de errores > línea base + 2σ Y p99 > umbral del SLO**, del mismo servicio y periodo.

La línea base es el comportamiento habitual; σ mide su variación. p99 es la latencia que no supera el 99 % de las solicitudes; SLO, nuestro objetivo de servicio. El [criterio de medición](infra/aws/metrics-queries.md) detalla los cálculos. Durante estos experimentos no demostramos alertas ni MTTD, el tiempo medio hasta detectar un fallo mediante alertamiento. Las pruebas posteriores de los módulos B y C no cambian ese resultado histórico.

Ejecutamos el [experimento de caos 1: latencia de 200 ms en Service B](docs/CHAOS_EXPERIMENT_1.md) en AWS y lo desactivamos tras la limpieza. En las [evidencias reales y locales](docs/evidence/integrator/aws/chaos/README.md) distinguimos ambos alcances; confirmamos 540 demoras en B y la recuperación, sin errores ni consumo del presupuesto del SLO de trabajo.

En el [experimento 2: errores en data-service](docs/CHAOS_EXPERIMENT_2.md) registramos 50 errores entre 500 intentos internos (10 %). Service Connect los recuperó: las 1350 solicitudes finales de las tres fases devolvieron 200. En el [informe AWS](docs/evidence/integrator/aws/chaos/errors-20261018T153105Z/README.md) distinguimos el SLO del servidor del cliente y conservamos el diagnóstico fallido anterior, las trazas, métricas, logs y comprobaciones de limpieza.

Para pausar o reanudar, conservamos explícitamente las etiquetas actuales descritas en la guía AWS.

Consultamos el [resumen de evidencias locales](docs/evidence/integrator/README.md), con enlaces a pruebas, trazas, métricas y logs.

```powershell
docker compose -f compose.otel.yml run --rm --no-deps -e OTEL_ENABLED=false -e SERVICE_B_URL= -e PYTHONDONTWRITEBYTECODE=1 -v "${PWD}/tests:/app/tests:ro" service-a python -m pytest -q -p no:cacheprovider /app/tests
python scripts/validate_local.py
python scripts/check_dashboard.py
python scripts/validate_reference_runtime.py
python scripts/validate_failure.py
docker compose -f compose.otel.yml run --rm -e VUS=2 -e DURATION=10s k6 run --summary-export=/results/k6-integrator-smoke.json /scripts/load.js
```

Con el validador local comprobamos creación, consulta, listado y actualización de créditos (CRUD), persistencia tras reiniciar data-service y una traza A → B → data-service → SQL. También revisamos las relaciones entre spans —los pasos de una traza—, la ausencia de consultas y parámetros SQL exportados y las tres señales de cada servicio.

Con el validador de fallos detenemos brevemente data-service y Service B por separado. Comprobamos la respuesta 503 y restauramos cada dependencia. Guardamos las evidencias nuevas en `docs/evidence/integrator/`.

data-service reutiliza la instrumentación FastAPI/HTTPX/SQLAlchemy y añade spans `credit.persist` y `credit.status_update`. Los spans SQL conservan atributos de sistema, operación y base de datos; el exportador elimina consultas, parámetros, usuario, cadenas de conexión y detalles de excepciones. No registrar cuerpos HTTP ni datos personales en logs.

## Implementación del Módulo B: alertamiento y AIOps en AWS

Implementamos el Módulo B sobre AWS CloudWatch para complementar la observabilidad del integrador con mecanismos de detección y notificación de eventos relevantes. Configuramos una alarma de latencia p99 para supervisar el cumplimiento del umbral de respuesta, una alarma de detección de anomalías sobre eventos de error y una alarma compuesta que relaciona ambas condiciones para reducir notificaciones aisladas. Integramos Amazon SNS para la entrega de notificaciones y AWS EventBridge con AWS Lambda para procesar los cambios de estado y enriquecer las alertas mediante consultas a los logs del sistema.

Validamos la configuración de los componentes, la publicación de notificaciones SNS y una invocación sintética de Lambda que ejecutó la consulta de logs y publicó el resultado. Estas comprobaciones demuestran el funcionamiento de componentes individuales, pero no equivalen a una detección completa de un incidente operativo real. Durante la revisión de los logs encontramos eventos asociados a los experimentos de caos, pero no coincidencias de errores operativos en la consulta realizada al excluir los eventos inyectados. La alarma de anomalías tampoco llegó a demostrar una detección efectiva durante las pruebas documentadas.

Conservamos esta distinción entre configuración y comportamiento comprobado. El módulo establece la base para correlacionar señales, enriquecer alertas y centralizar notificaciones; queda pendiente demostrar el flujo completo ante una condición operativa real y medir indicadores como el tiempo de detección (MTTD) y la reducción de alertas innecesarias. La configuración, las pruebas realizadas y las evidencias se describen en la [documentación del Módulo B](docs/Modulo-B-AIOps-Deteccion-Automática-de-Anomalías.md), con las capturas correspondientes en [`docs/evidence/integrator/aws/Punto-b/`](docs/evidence/integrator/aws/Punto-b).

## Seguridad de red en AWS

Comprobamos VPC Flow Logs: registros del tráfico permitido y rechazado en nuestra red. Las capturas muestran un filtro de rechazos, la alarma `module-c-vpc-rejected-flows-high`, su acción SNS y el dashboard. Un rechazo no demuestra por sí solo un ataque. Conservamos el alcance y las restricciones en el [Módulo C](docs/ModuloC-Network-and-Security%20-Observability.md) y sus [capturas](docs/evidence/integrator/aws/Punto-C/).

Security Hub e Inspector están reportados como bloqueados por políticas de la organización. No los presentamos como habilitados ni inferimos ausencia de vulnerabilidades. La alerta de red tampoco demuestra detección AIOps ni MTTD de los experimentos de caos.

## Preparación de AWS RDS

data-service admite `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_SSLMODE` y `DATABASE_SSLROOTCERT`. TLS utiliza `verify-full` por defecto fuera del Compose local; montar el certificado CA de RDS y configurar su ruta en `DATABASE_SSLROOTCERT`. `DATABASE_URL` tiene prioridad y debe incluir TLS seguro si se utiliza para RDS. Compose local configura PostgreSQL con TLS desactivado únicamente dentro de la red local de contenedores.

En [Terraform AWS](infra/aws/README.md) configuramos tres servicios ECS, Service Connect y un Collector por tarea. Solo data-service recibe conexión y secreto RDS. TLS cifra la conexión y verifica el certificado.

Tras los experimentos conservamos A/B en `api:chaos-latency-v1`, data-service en `api:chaos-errors-v2` y los Collectors en `collector:traces-v2`. Ambas inyecciones están desactivadas. `api:initial` permanece sin sobrescribir. Exportamos trazas con `awsxray`, sin cambiar el destino regional X-Ray.

La [prueba privada temporal](infra/aws/SYNTHETIC_TEST.md) obtuvo HTTP 201, lectura HTTP 200, traza hasta PostgreSQL y logs correlacionados. Retiramos sus recursos.

Las aplicaciones y RDS seguían activos en la última comprobación y generan costos. Para producción necesitamos usuario SQL limitado y migraciones controladas; por ahora usamos creación automática de tablas y administrador.
