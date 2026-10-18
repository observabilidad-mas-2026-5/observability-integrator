# Experimento 2 — errores controlados en data-service

En nuestro segundo experimento realizamos 180 s normales, 180 s con un 10 % de fallos y 180 s de recuperación, sin superar 3 RPS. Utilizamos la cuenta personal `observability-integrator`, Ohio. Guardamos las evidencias por ejecución en [aws/chaos](evidence/integrator/aws/chaos/README.md). No modificamos recursos de AIOps o seguridad, RDS ni datos existentes.

## Mecanismo y aislamiento

Implementamos el mecanismo en `app/error_chaos.py` y lo invocamos exclusivamente al consultar `GET /credit-applications/{application_id}`, antes de abrir una conexión SQL. Exigimos simultáneamente `DATA_CHAOS_ENABLED=true`, un `DATA_CHAOS_EXPIRES_AT` futuro dentro de los 30 minutos del arranque y coincidencia exacta con `DATA_CHAOS_APPLICATION_ID`, el UUID de un registro sintético documentado en el experimento 1. Lo mantenemos desactivado por defecto; ningún POST, PUT, listado, healthcheck ni registro distinto es elegible.

A/B ya propagan W3C Trace Context. Para no modificarlos ni redesplegarlos, el cliente marca la fase de inyección en los últimos 32 bits del trace ID: `e220` seguido del ordinal de 16 bits. El resto conserva timestamp y aleatoriedad; el traceparent sigue siendo válido y muestreado. En fases normal/recuperación y en la lectura inicial, el cliente limpia esos bits reservados. El contador protegido por un lock falla en el primer intento físico de cada grupo de diez intentos elegibles, **incluidos los reintentos del proxy**. Es un calendario determinista, no una probabilidad Bernoulli; publicamos la proporción realmente medida. Solo hay un proceso y una tarea data-service en esta prueba; un reinicio invalida la continuidad del contador y debe investigarse.

El marcador no es autenticación. Solo se permite dentro del laboratorio privado, con gate temporal y UUID sintético explícito. No añadimos endpoints administrativos ni privilegios. Un intento fallido devuelve **503** antes de consultar PostgreSQL. Service Connect puede reintentar y recuperar la operación: una misma traza puede contener un intento data-service 503 y otro 200 con SQL SELECT, mientras A/B devuelven 200. No confundimos errores internos con errores finales del cliente. El generador usa **2,5 RPS**, dejando margen para los intentos internos adicionales; no envía ráfagas para recuperar tiempo perdido.

La primera ejecución `chaos-errors-v1` seleccionó por ordinal lógico y los reintentos repitieron el mismo fallo: 486 errores entre 972 intentos físicos (50 %, no el 10 % requerido), aunque el cliente recibió 54/540 errores. Conservamos sus evidencias como diagnóstico fallido, no como validación. `chaos-errors-v2` corrige el calendario por intento físico. Los reintentos son una capacidad de [ECS Service Connect](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-connect-concepts-deploy.html); las multiplicidades concretas se verifican en nuestras trazas, no las asumimos a partir de esa documentación.

## Telemetría y SLO

- Identificador fijo `data-service-errors-10pct-v1`, sin IDs de solicitudes como dimensiones.
- Span `chaos.error` de data-service marcado ERROR, atributos de experimento, tasa 10 y HTTP 503.
- Log ERROR `chaos.error.injected`, con trace_id/span_id. B y A pueden registrar éxito si el proxy recupera el intento; los eventos de dependencia no disponible solo aparecen si agotan los reintentos.
- Contadores OTLP `chaos.error.eligible.requests` y `chaos.injected.errors`, scope `credit-lab.chaos`, recurso `data-service`.
- HTTP servidor y métricas de proceso se conservan; no creamos alarmas ni dashboards.

Reutilizamos las estadísticas nearest-rank p50/p95/p99 y el SLO de trabajo del experimento 1: **99,5 % de GET finales exitosos y ≤1000 ms**. Solicitud mala = código distinto de 200 o duración >1000 ms. Consumo de ventana = `malas / (N × 0,005) × 100`; burn rate = `fracción mala / 0,005`. Separadamente evaluamos un SLO de disponibilidad del servidor: **99,5 % de intentos físicos elegibles sin error inyectado**. Con 10 % de errores internos su burn rate es 20, aunque el SLO del cliente puede quedar intacto gracias a reintentos. Ambos son SLO de trabajo explícitos, no un presupuesto mensual restante. MTTD de alertamiento queda nulo salvo que se verifique una alerta real correlacionada; registrar separadamente inicio de primer fallo y observación operativa de sus logs.

Aplicamos el mismo [criterio AIOps](../infra/aws/metrics-queries.md#condición-conjunta-de-aiops): tasa de errores superior a la línea base + 2σ **Y** latencia p99 superior al umbral del SLO, en el mismo servicio y periodo. Los fallos internos recuperados no son errores finales del cliente. Las muestras del cliente no superaron el umbral de latencia; no las presentamos como prueba de activación de una alarma por servicio ni calculamos un MTTD de alertamiento.

## Ejecución reproducible y planes

La nueva imagen `api:chaos-errors-v2` se publica para Linux/amd64 con el Dockerfile AWS existente. No se sobrescribe `initial` ni se cambian las imágenes A/B (`chaos-latency-v1`) o Collector (`traces-v2`). `api_image_tags` selecciona la nueva etiqueta exclusivamente para data-service. La inyección de latencia en A/B permanece desactivada (`chaos_expires_at=0`).

Después de aprobación y de publicar/verificar la imagen:

```bash
python -u -m scripts.run_aws_error_experiment --execute
```

El controlador verifica la cuenta personal, revisa el plan y solo permite la definición/servicio de data-service y los cinco recursos privados temporales existentes. Armar y desplegar desde la base anterior corresponde a **6 altas, 1 cambio, 1 baja**: cinco recursos temporales más una revisión data-service reemplazada y el puntero de su servicio actualizado. El tráfico usa `api:initial` como cliente Python, con código comprimido en el override; no necesita rol de aplicación ni secreto de RDS.

El cliente reutiliza por GET el registro sintético cuya creación quedó en la evidencia del experimento 1. **No realiza POST, UPDATE ni DELETE**; la lectura inicial debe devolver 200 y el UUID esperado. Cada fase emite muestras JSONL, códigos HTTP, percentiles y tiempos UTC a CloudWatch. Se seleccionan trazas normales, exitosas durante caos, fallidas y de recuperación, verificando el servicio responsable. Si no se confirma el fallo en logs dentro de 65 s, se detiene el cliente y se limpia sin ampliar el alcance.

La retirada conserva la nueva imagen de data-service, fija `data_error_expires_at=0`, retira sus tres variables de gate y elimina los cinco recursos temporales: normalmente **1 alta, 1 cambio, 6 bajas**, sin `terraform destroy` general. La limpieza corre en `finally`, conserva las evidencias antes de retirar el stream temporal y exige tres servicios HEALTHY y un plan final sin cambios. Cualquier cambio ajeno en un plan bloquea la aplicación y debe investigarse.

Para operaciones posteriores conservamos explícitamente:

```text
deploy_services=true
image_tag=initial
collector_image_tag=traces-v2
api_image_tags={"service-a":"chaos-latency-v1","service-b":"chaos-latency-v1","data-service":"chaos-errors-v2"}
chaos_expires_at=0
data_error_expires_at=0
enable_synthetic_test=false
```

## Limitaciones de disponibilidad

Los despliegues actuales tienen mínimo saludable 0 % y máximo 100 %: renovar data-service implica una interrupción breve. B tiene un healthcheck que depende de `/health` de data-service y ECS puede reemplazar automáticamente B durante ese recambio, aunque el plan no modifique B. Esto ocurrió al armar esta ejecución: `ServiceSchedulerInitiated`, `Task failed container health checks`. Esperamos la recuperación de los tres servicios antes de medir; los tiempos de despliegue no pertenecen a las fases de tráfico. Durante la inyección los healthchecks no son elegibles y deben permanecer saludables.

Desacoplar liveness/readiness o cambiar la política de rolling deployment sería una mejora separada, no implementada aquí. No alteramos grupos internos, IAM, RDS, AIOps ni seguridad para ocultar esa limitación. La renovación final para desarmar puede producir el mismo efecto y requiere verificar la recuperación completa.
