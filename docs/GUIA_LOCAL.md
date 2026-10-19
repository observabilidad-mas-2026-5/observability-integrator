# Guía local y referencia histórica de OpenTelemetry

## Etapa 0: preservar el proyecto

Necesitábamos ejecutar y observar el recorrido de los créditos sin depender de AWS. En local usamos Service A → Service B → data-service → PostgreSQL, con `compose.otel.yml` y las configuraciones de `otel/`. Conservamos Dockerfile y los contratos públicos de créditos.

A puede trabajar en memoria si SERVICE_B_URL no está definido. En Compose sí configuramos esa variable; solo data-service guarda los datos. La memoria anterior del proceso no migra automáticamente. Para conservarla necesitamos exportar los datos antes de detener la API y reingresarlos mediante POST, que genera nuevos UUID. Los componentes históricos permanecen fuera de Git.

Los ejemplos históricos pertenecen al laboratorio anterior. El ZIP de referencia no es necesario. Para la versión actual seguimos el [README](../README.md), con sus comandos, imágenes y puertos.

Mantenemos los ejemplos históricos sin cambiar sus datos. No los presentamos como resultados actuales.

## Preparación de la entrega

Revisamos el contenido heredado el 13 de octubre de 2026, America/Bogota. El [índice del integrador](evidence/integrator/README.md) identifica la evidencia actual. Conservamos resultados, JSON/CSV, capturas y manifiestos. Los comandos reproducen pruebas; no prueban una ejecución nueva.

Para AWS usamos la [guía vigente](../infra/aws/README.md) y sus [evidencias reales](evidence/integrator/aws/README.md). Las [capturas anteriores](evidence/integrator/aws/legacy-aws-captures.md) son solo referencia histórica. No incluimos sus informes PDF/DOCX en la entrega.

La revisión opcional `scripts/assess_reference_slos.py` utiliza la ruta absoluta del ZIP registrada en el inventario histórico. Esa ruta corresponde al workspace anterior; no es un requisito del arranque local. Conservamos el registro original sin modificarlo.

## Etapas 1 a 3: iniciar, probar y observar

Necesitamos Docker Desktop con Compose, Python 3 para scripts (biblioteca estándar) y PowerShell. El Python host no necesita las dependencias FastAPI; se ejecutan dentro del contenedor. Desde la raíz ejecutamos:

```powershell
docker compose -f compose.otel.yml config --quiet
docker compose -f compose.otel.yml up -d --build --wait
docker compose -f compose.otel.yml ps
python scripts/validate_local.py
```

Las imágenes se descargan y se crean tres volúmenes dedicados para PostgreSQL, Prometheus y Loki. No se usan container_name ni los puertos del monitoreo anterior. `.env.example` permite configurar puertos y credenciales locales; copiarlo a `.env` es opcional. Las contraseñas de ejemplo son exclusivamente locales y el stack publica solo en 127.0.0.1.

### Puertos históricos: no corresponden al integrador actual

La siguiente tabla documenta el laboratorio anterior. Para nuestra ejecución actual utilizamos los puertos del [README vigente](../README.md#ejecución-local), sin reutilizar los puertos históricos.

| Herramienta | URL local | Función |
|---|---|---|
| API A | http://localhost:18000/docs | Contratos originales de créditos |
| Jaeger | http://localhost:16686 | Traza A → HTTP → B → PostgreSQL |
| Prometheus | http://localhost:19090 | Scrapes apps, SDK y Collector |
| Grafana | http://localhost:13000 | Dashboard y Explore de Loki |
| OTLP gRPC / HTTP | localhost:14317 / localhost:14318 | Recepción de telemetría |

En el laboratorio anterior utilizábamos Grafana con usuario `lab`, contraseña local `local-lab-only` o GRAFANA_PASSWORD. En nuestra arquitectura actual B delega su sonda en data-service, que ejecuta SELECT 1; A comprueba la vida de su proceso. Validamos la disponibilidad de negocio con las operaciones completas, no solo con esas sondas.

Conservamos debajo el ejemplo HTTP histórico, cuyos puertos no corresponden a la ejecución actual.

```powershell
$body = @{customer_name='Synthetic';document_number='TEST';requested_amount=100} | ConvertTo-Json
$credit = Invoke-RestMethod http://localhost:18000/credit-applications -Method Post -ContentType application/json -Body $body
Invoke-RestMethod "http://localhost:18000/credit-applications/$($credit.application_id)"
```

No utilizamos información real de clientes. Los logs propios contienen eventos, nivel, servicio, timestamp, trace_id y span_id en JSON. El SDK exporta los registros por OTLP a Loki vía Collector; no consideramos stdout por sí solo como evidencia de exportación. Los logs de acceso de uvicorn no están convertidos a JSON ni exportados como logs de negocio.

El Collector recibe OTLP en 4317/4318; aplica memory_limiter, resource y batch; exporta trazas OTLP a Jaeger, métricas al endpoint Prometheus 8889 y logs al endpoint OTLP de Loki. Sus métricas internas se publican en 8888.

Las métricas originales /metrics permanecen habilitadas en ambos modos. El SDK aporta duración HTTP y mediciones CPU/memoria por OTLP. No sumamos indiscriminadamente las dos familias de duración/solicitudes: son fuentes alternativas del mismo tráfico. El dashboard utiliza /metrics para conservar cobertura en el modo baseline.

## Correlación y evidencias

En la versión actual, `python scripts/validate_local.py` genera un traceparent y comprueba CRUD, 404, 422, persistencia tras reiniciar data-service, relaciones A/B/data-service/SQL, logs de los tres servicios, targets de Prometheus y paneles provisionados. Conservamos los resultados históricos trace.json, logs.json, targets.json y validation.json en docs/evidence como referencia; las [evidencias del integrador](evidence/integrator/README.md) identifican las ejecuciones vigentes.

Conservamos la siguiente consulta histórica de Grafana Explore para A/B. Para observar el recorrido actual completo incluimos también data-service en el filtro de servicios, sin interpretar esta consulta parcial como evidencia de las tres aplicaciones.

```logql
{service_name=~"service-a|service-b"} | trace_id="TRACE_ID_DE_VALIDATION_JSON"
```

Relacionamos los eventos mediante trace_id, el identificador de la traza, y span_id, el identificador de cada paso. En Loki los guardamos como metadatos, no como etiquetas indexadas: así evitamos crear una serie distinta por solicitud. El campo trace_id enlaza con Jaeger.

Para comparar métricas usamos service_name/instance y la misma ventana de tiempo. No afirmamos que cada muestra agregada tenga trace_id. Hay configuración de exemplars —enlaces desde una medida a una traza—, pero no verificamos su recepción ni navegación visual.

La base heredada tenía seis paneles: latencia p95/p99, errores 5xx, tráfico, disponibilidad de scrape y proporción de éxito, CPU de A/B y fallos del Collector. El integrador tiene su [validación de dashboard](evidence/integrator/dashboard-queries.json).

Contamos éxito como ausencia de 5xx; 404/422 controlados no indican indisponibilidad. `up` mide el acceso de Prometheus al endpoint, no el servicio completo. El dashboard estima percentiles por buckets; k6 usa sus observaciones. Cero tráfico o un panel del Collector en cero no prueban disponibilidad ni exportación.

## Etapa 4: carga y recursos

```powershell
python scripts/benchmark.py
```

Documentamos este benchmark como procedimiento de la base heredada, no como resultado actual: tarda más de diez minutos, con 20 segundos de warm-up y cinco minutos con 50 VUs por modo, primero sin SDK y luego con SDK. Reinicia A/B al cambiar OTEL_ENABLED, sin cambiar límites ni volumen.

Reutiliza el mismo crédito sintético para GET y PUT y evita datos nuevos por iteración. Antes de aplicarlo a los tres servicios debemos revisar su cobertura de data-service; no lo ejecutamos como parte de esta revisión documental.

Cada aplicación tiene límite de 1 CPU y 512 MiB; el Collector tiene igual límite. El Collector permanece activo en baseline y no recibe OTLP nuevo de aplicaciones. Las dependencias SDK permanecen instaladas/importadas: se mide instrumentación y exportación activa, no el costo de instalación de paquetes. Prometheus, Grafana, PostgreSQL, Jaeger y Loki siguen encendidos en ambos modos.

El benchmark produce without-otel.json, with-otel.json, logs de k6, CSV de recursos y benchmark.json. Comparamos promedios por servicio y sumamos A/B. Docker stats expresa CPU como porcentaje de un core y memoria del contenedor; no la confundimos con RSS, la memoria del proceso.

Calculamos el overhead —costo adicional de instrumentar— como (con-sin)/sin×100. Expresamos la memoria adicional en MiB. Una sola pareja de ejecuciones en orden fijo no permite conclusiones estadísticas ni atribuir toda la diferencia a OpenTelemetry. Para el informe recomendamos repeticiones con orden alternado.

Para las validaciones actuales utilizamos `python scripts/validate_failure.py`, con aprobación operativa en un entorno compartido. El script detiene por separado data-service y B, comprueba 503 en A y restaura las dependencias mediante finally. No elimina datos.

## Pruebas unitarias en Docker

```powershell
$testsPath = Join-Path (Get-Location) 'tests'
docker run --rm --mount "type=bind,source=$testsPath,target=/tests,readonly" -e PYTHONDONTWRITEBYTECODE=1 otel-credit-api:local python -m pytest /tests -q -p no:cacheprovider
```

El ejemplo Docker anterior pertenece a la base histórica de diez pruebas: ocho previas y dos adicionales para HTTP remoto y 503. No utilizamos ese conteo para describir la suite actual: en la validación posterior a los experimentos registramos 47 pruebas Python aprobadas. Las pruebas con memoria o mocks no sustituyen la integración real PostgreSQL/W3C.

Conservamos las advertencias de deprecación de TestClient.

## Detención y recuperación

```powershell
docker compose -f compose.otel.yml stop
# Para volver a iniciar:
docker compose -f compose.otel.yml up -d --wait
```

No ejecutamos down -v ni prune sin autorización: eliminan datos o recursos ajenos. `stop` conserva los volúmenes. Jaeger usa memoria: sus trazas se pierden al reiniciar Jaeger; guardamos las evidencias JSON antes. PostgreSQL sí conserva créditos; Loki/Prometheus usan volúmenes. Ante fallos revisamos `docker compose -f compose.otel.yml logs --tail 50 SERVICE` y comprobamos la disponibilidad de los puertos configurados.

La latencia del dashboard usa http_request_duration_highr_seconds_bucket (todas las rutas, incluidas sondas y scrapes), cuyos buckets permiten observar latencias superiores a un segundo. La familia agrupada por handler tiene buckets más gruesos y se conserva para compatibilidad; no se usa para p99 del panel. GET/PUT de negocio es el workload exclusivo de k6.
