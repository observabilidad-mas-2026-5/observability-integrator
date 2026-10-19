# Experimento 2 — errores controlados en data-service

Necesitábamos comprobar qué ocurre cuando data-service falla y si podemos identificarlo en las señales del laboratorio. Ejecutamos tres fases de 180 s: normal, 10 % de errores internos y recuperación, sin superar 3 RPS —solicitudes por segundo—.

Usamos la cuenta personal `observability-integrator`, Ohio. Guardamos los resultados en [aws/chaos](evidence/integrator/aws/chaos/README.md). No modificamos AIOps, seguridad, RDS ni los datos existentes.

En la ejecución válida fallaron 50/500 intentos internos. Los reintentos recuperaron las solicitudes y el cliente recibió 200. Conservamos también el intento previo inválido. No demostramos alertas ni MTTD; este documento explica cómo reproducimos y retiramos la inyección.

Las [evidencias posteriores de AIOps y seguridad](evidence/integrator/aws/README.md#evidencias-posteriores-de-aiops-y-seguridad) no demuestran detección de esta inyección. Mantenemos separados el error interno, la respuesta final del cliente y cualquier futura notificación automática.

Un intento interno es una llamada que recibe data-service. Si falla, el proxy —intermediario de red— puede repetirla antes de devolver la respuesta final al cliente. Por eso los dos porcentajes de error pueden ser distintos.

## Mecanismo y aislamiento

Implementamos el mecanismo en `app/error_chaos.py`. Solo se ejecuta al consultar `GET /credit-applications/{application_id}`, antes de abrir una conexión SQL.

Para activarlo exigimos `DATA_CHAOS_ENABLED=true`, un `DATA_CHAOS_EXPIRES_AT` futuro dentro de los 30 minutos del arranque y coincidencia con `DATA_CHAOS_APPLICATION_ID`. Ese UUID identifica el registro sintético creado en el experimento 1. Por defecto está desactivado. Excluimos POST, PUT, listado, healthchecks y cualquier otro registro.

A/B ya propagan W3C Trace Context. Para no modificarlos ni redesplegarlos, el cliente marca la fase de inyección en los últimos 32 bits del trace ID: `e220` seguido del ordinal de 16 bits. El resto conserva timestamp y aleatoriedad; el traceparent sigue siendo válido y muestreado. En fases normal/recuperación y en la lectura inicial, el cliente limpia esos bits reservados.

El contador protegido por un lock falla en el primer intento físico de cada grupo de diez intentos elegibles, **incluidos los reintentos del proxy**. Es un calendario determinista, no una probabilidad Bernoulli; publicamos la proporción realmente medida. Solo hay un proceso y una tarea data-service en esta prueba; un reinicio invalida la continuidad del contador y debe investigarse.

El marcador no es autenticación. Solo se permite dentro del laboratorio privado, con gate temporal y UUID sintético explícito. No añadimos endpoints administrativos ni privilegios. Un intento fallido devuelve **503** antes de consultar PostgreSQL.

Service Connect puede reintentar y recuperar la operación: una misma traza puede contener un intento data-service 503 y otro 200 con SQL SELECT, mientras A/B devuelven 200. No confundimos errores internos con errores finales del cliente. El generador usa **2,5 RPS**, dejando margen para los intentos internos adicionales; no envía ráfagas para recuperar tiempo perdido.

En `chaos-errors-v1` seleccionamos fallos por solicitud lógica. Los reintentos repitieron el fallo: medimos 486 errores entre 972 intentos físicos, **50 %**, aunque el cliente recibió 54/540 errores. Por eso no validamos ese intento como inyección del 10 %.

Corregimos el calendario por intento físico en `chaos-errors-v2`. Conservamos el diagnóstico fallido. [ECS Service Connect](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-connect-concepts-deploy.html) puede reintentar; las cantidades concretas las comprobamos en nuestras trazas, no las deducimos de la documentación.

## Telemetría y SLO

- Identificador fijo `data-service-errors-10pct-v1`, sin IDs de solicitudes como dimensiones.
- Span `chaos.error` de data-service marcado ERROR, atributos de experimento, tasa 10 y HTTP 503.
- Log ERROR `chaos.error.injected`, con trace_id/span_id. B y A pueden registrar éxito si el proxy recupera el intento; los eventos de dependencia no disponible solo aparecen si agotan los reintentos.
- Contadores OTLP `chaos.error.eligible.requests` y `chaos.injected.errors`, scope `credit-lab.chaos`, recurso `data-service`.
- HTTP servidor y métricas de proceso se conservan; no creamos alarmas ni dashboards.

Calculamos p50/p95/p99 con nearest-rank: el valor ordenado de cada percentil. Para el cliente usamos **99,5 % de GET finales exitosos y ≤1000 ms**. Una solicitud mala es no 200 o >1000 ms. El consumo es `malas / (N × 0,005) × 100`; el burn rate, `fracción mala / 0,005`.

Para el servidor usamos **99,5 % de intentos elegibles sin error inyectado**. Con 10 % de fallos internos, el burn rate es 20 aunque los reintentos recuperen al cliente. No es presupuesto mensual. Sin alerta dejamos MTTD nulo y registramos aparte el primer fallo y su comprobación en logs.

Para alertar aplicamos [tasa de errores > línea base + 2σ Y p99 > umbral del SLO](../infra/aws/metrics-queries.md#condición-conjunta-de-aiops), al mismo servicio y periodo. El p99 del cliente quedó bajo el umbral; no demuestra la regla del servidor. No calculamos MTTD sin notificación.

## Ejecución reproducible y planes

La nueva imagen `api:chaos-errors-v2` se publica para Linux/amd64 con el Dockerfile AWS existente. No se sobrescribe `initial` ni se cambian las imágenes A/B (`chaos-latency-v1`) o Collector (`traces-v2`). `api_image_tags` selecciona la nueva etiqueta exclusivamente para data-service. La inyección de latencia en A/B permanece desactivada (`chaos_expires_at=0`).

Después de aprobación y de publicar/verificar la imagen:

```bash
python -u -m scripts.run_aws_error_experiment --execute
```

El controlador verifica la cuenta personal, revisa el plan y solo permite la definición/servicio de data-service y los cinco recursos privados temporales existentes. Armar y desplegar desde la base anterior corresponde a **6 altas, 1 cambio, 1 baja**: cinco recursos temporales más una revisión data-service reemplazada y el puntero de su servicio actualizado.

El tráfico usa `api:initial` como cliente Python, con código comprimido en el override; no necesita rol de aplicación ni secreto de RDS.

El cliente reutiliza por GET el registro sintético cuya creación quedó en la evidencia del experimento 1. **No realiza POST, UPDATE ni DELETE**; la lectura inicial debe devolver 200 y el UUID esperado. Cada fase emite muestras JSONL, códigos HTTP, percentiles y tiempos UTC a CloudWatch.

Se seleccionan trazas normales, exitosas durante caos, fallidas y de recuperación, verificando el servicio responsable. Si no se confirma el fallo en logs dentro de 65 s, se detiene el cliente y se limpia sin ampliar el alcance.

La retirada conserva la nueva imagen de data-service, fija `data_error_expires_at=0`, retira sus tres variables de gate y elimina los cinco recursos temporales: normalmente **1 alta, 1 cambio, 6 bajas**, sin `terraform destroy` general. La limpieza corre en `finally`, conserva las evidencias antes de retirar el stream temporal y exige tres servicios HEALTHY y un plan final sin cambios.

Cualquier cambio ajeno en un plan bloquea la aplicación y debe investigarse.

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

Los despliegues actuales tienen mínimo saludable 0 % y máximo 100 %: renovar data-service implica una interrupción breve. B tiene un healthcheck que depende de `/health` de data-service y ECS puede reemplazar automáticamente B durante ese recambio, aunque el plan no modifique B. Esto ocurrió al armar esta ejecución: `ServiceSchedulerInitiated`, `Task failed container health checks`.

Esperamos la recuperación de los tres servicios antes de medir; los tiempos de despliegue no pertenecen a las fases de tráfico. Durante la inyección los healthchecks no son elegibles y deben permanecer saludables.

Desacoplar liveness/readiness o cambiar la política de rolling deployment sería una mejora separada, no implementada aquí. No alteramos grupos internos, IAM, RDS, AIOps ni seguridad para ocultar esa limitación. La renovación final para desarmar puede producir el mismo efecto y requiere verificar la recuperación completa.
