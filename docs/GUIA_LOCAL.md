# Laboratorio local de créditos y OpenTelemetry

## Etapa 0: preservar el proyecto

Ejecutamos nuestro laboratorio con `compose.otel.yml` y las configuraciones de `otel/`, conservando Dockerfile y todos los contratos públicos de créditos. La aplicación utiliza memoria cuando SERVICE_B_URL no está definido; el Compose del laboratorio define esa variable y todas las operaciones pasan por HTTP a B y PostgreSQL. El contenido previo del diccionario no migra automáticamente: es memoria del proceso, no una base recuperable. Para migrar datos existentes, los exportamos antes de parar la API antigua y los reingresamos mediante POST; se generan nuevos UUID. Conservamos físicamente los componentes del laboratorio anterior y los excluimos de Git.

Conservamos esta guía del laboratorio OpenTelemetry anterior como referencia local. El inventario del ZIP de la profesora pertenecía a ese laboratorio y no lo incluimos aquí. Para ejecutar el integrador no necesitamos ese ZIP ni herramientas locales del asistente; consultamos primero el [README vigente](../README.md) para la arquitectura de tres servicios y sus puertos.

Conservamos los comandos, puertos, etiquetas de imágenes y conteos de pruebas heredados como referencia histórica, no como resultados actuales del integrador. Para ejecutar nuestra versión vigente utilizamos los comandos y puertos del README; distinguimos estas instrucciones históricas de las evidencias actuales.

## Preparación de la entrega

Revisamos el contenido técnico heredado el 13 de octubre de 2026, America/Bogota. Consultamos el [índice de evidencias del integrador](evidence/integrator/README.md) y conservamos sin cambios los resultados, JSON/CSV, capturas y manifiestos existentes. Presentamos los comandos de validación y benchmark de esta guía como procedimientos de reproducción, no como evidencia de una ejecución actual.

En esta guía conservamos el procedimiento local heredado. Para AWS utilizamos exclusivamente la [guía vigente del integrador](../infra/aws/README.md) y sus [evidencias reales](evidence/integrator/aws/README.md). Conservamos las [capturas históricas anteriores](evidence/integrator/aws/legacy-aws-captures.md) como referencia, no como validación del despliegue actual. No incluimos informes PDF/DOCX del laboratorio anterior en la entrega del integrador.

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

| Herramienta | URL local | Función |
|---|---|---|
| API A | http://localhost:18000/docs | Contratos originales de créditos |
| Jaeger | http://localhost:16686 | Traza A → HTTP → B → PostgreSQL |
| Prometheus | http://localhost:19090 | Scrapes apps, SDK y Collector |
| Grafana | http://localhost:13000 | Dashboard y Explore de Loki |
| OTLP gRPC / HTTP | localhost:14317 / localhost:14318 | Recepción de telemetría |

Grafana: usuario `lab`, contraseña local `local-lab-only` o GRAFANA_PASSWORD. B y PostgreSQL solo son accesibles en la red Compose. La sonda de B consulta SELECT 1. A indica vida del proceso; la disponibilidad de B se verifica con operaciones de negocio y la sonda propia de B.

```powershell
$body = @{customer_name='Synthetic';document_number='TEST';requested_amount=100} | ConvertTo-Json
$credit = Invoke-RestMethod http://localhost:18000/credit-applications -Method Post -ContentType application/json -Body $body
Invoke-RestMethod "http://localhost:18000/credit-applications/$($credit.application_id)"
```

No utilizamos información real de clientes. Los logs propios contienen eventos, nivel, servicio, timestamp, trace_id y span_id en JSON. El SDK exporta los registros por OTLP a Loki vía Collector; no consideramos stdout por sí solo como evidencia de exportación. Los logs de acceso de uvicorn no están convertidos a JSON ni exportados como logs de negocio.

El Collector recibe OTLP en 4317/4318; aplica memory_limiter, resource y batch; exporta trazas OTLP a Jaeger, métricas al endpoint Prometheus 8889 y logs al endpoint OTLP de Loki. Sus métricas internas se publican en 8888.

Las métricas originales /metrics permanecen habilitadas en ambos modos. El SDK aporta duración HTTP y mediciones CPU/memoria por OTLP. No sumamos indiscriminadamente las dos familias de duración/solicitudes: son fuentes alternativas del mismo tráfico. El dashboard utiliza /metrics para conservar cobertura en el modo baseline.

## Correlación y evidencias

`python scripts/validate_local.py` genera un traceparent, comprueba el CRUD, 404, 422, persistencia tras reiniciar B, A/B/SQL en una sola traza, logs de A/B consultados a través del proxy de Grafana, targets de Prometheus y seis paneles provisionados. Guarda trace.json, logs.json, targets.json y validation.json en docs/evidence.

En Grafana Explore seleccionamos Loki y consultamos:

```logql
{service_name=~"service-a|service-b"} | trace_id="TRACE_ID_DE_VALIDATION_JSON"
```

El campo estructurado trace_id tiene enlace interno a Jaeger. Los logs OTLP almacenan trace_id/span_id como metadatos estructurados; no son etiquetas indexadas, para evitar cardinalidad alta. Para correlacionar temporalmente las métricas utilizamos service_name/instance y una ventana de tiempo; no afirmamos que cada muestra agregada tenga trace_id. Hay configuración para exemplars, pero no dimos por verificadas su recepción y navegación visual.

Los seis paneles son: latencia p95/p99, errores 5xx, tráfico, disponibilidad de scrape y proporción de éxito, CPU de A/B y fallos de exportación del Collector. El éxito se define como ausencia de 5xx, por lo que los 404/422 controlados no representan indisponibilidad. `up` indica disponibilidad de scrape, no un SLI end-to-end. Las latencias del dashboard son estimaciones por buckets; k6 calcula el p99 de sus observaciones. Cero solicitudes no demuestra disponibilidad de negocio. Las métricas de errores del Collector solo aparecen tras eventos en algunas versiones; el panel usa cero como valor inicial.

## Etapa 4: carga y recursos

```powershell
python scripts/benchmark.py
```

Este comando tarda más de diez minutos: 20 segundos de warm-up y cinco minutos con 50 VUs por modo, primero sin SDK y luego con SDK. Reinicia A/B al cambiar OTEL_ENABLED, sin cambiar límites ni volumen. Reutiliza el mismo crédito sintético para GET y PUT y evita listas crecientes o datos nuevos por iteración. Las peticiones se etiquetan read/update para no crear series por UUID.

Cada aplicación tiene límite de 1 CPU y 512 MiB; el Collector tiene igual límite. El Collector permanece activo en baseline y no recibe OTLP nuevo de aplicaciones. Las dependencias SDK permanecen instaladas/importadas: se mide instrumentación y exportación activa, no el costo de instalación de paquetes. Prometheus, Grafana, PostgreSQL, Jaeger y Loki siguen encendidos en ambos modos.

Recopilamos como resultados: without-otel.json, with-otel.json, logs de k6, CSV de recursos y benchmark.json. Docker stats expresa CPU en porcentaje de un core y memoria de contenedor; para la comparación utilizamos promedios por servicio, sumados para A/B. Calculamos el overhead como (con-sin)/sin×100 y expresamos la memoria adicional en MiB. No confundimos RSS del proceso con la memoria del contenedor. La pareja única tiene orden fijo: no permite conclusiones estadísticas ni atribución causal exacta. Para el informe final recomendamos repetir con orden alternado.

Podemos reproducir la falla controlada con `python scripts/validate_failure.py`: para B, necesitamos aprobación operativa si lo ejecutamos en un entorno compartido. El script detiene solo B de nuestro laboratorio, comprueba 503 en A y restaura B mediante finally. No elimina datos.

## Pruebas unitarias en Docker

```powershell
$testsPath = Join-Path (Get-Location) 'tests'
docker run --rm --mount "type=bind,source=$testsPath,target=/tests,readonly" -e PYTHONDONTWRITEBYTECODE=1 otel-credit-api:local python -m pytest /tests -q -p no:cacheprovider
```

Diez pruebas: ocho previas y dos adicionales para HTTP remoto y 503. La suite usa memoria/mock; PostgreSQL y W3C se validan mediante integración real. Las advertencias de deprecación de TestClient no bloquean los contratos actuales.

## Detención y recuperación

```powershell
docker compose -f compose.otel.yml stop
# Para volver a iniciar:
docker compose -f compose.otel.yml up -d --wait
```

No ejecutamos down -v ni prune sin autorización: eliminan datos o recursos ajenos. `stop` conserva los volúmenes. Jaeger usa memoria: sus trazas se pierden al reiniciar Jaeger; guardamos las evidencias JSON antes. PostgreSQL sí conserva créditos; Loki/Prometheus usan volúmenes. Ante fallos revisamos `docker compose -f compose.otel.yml logs --tail 50 SERVICE` y comprobamos la disponibilidad de los puertos configurados.

La latencia del dashboard usa http_request_duration_highr_seconds_bucket (todas las rutas, incluidas sondas y scrapes), cuyos buckets permiten observar latencias superiores a un segundo. La familia agrupada por handler tiene buckets más gruesos y se conserva para compatibilidad; no se usa para p99 del panel. GET/PUT de negocio es el workload exclusivo de k6.
