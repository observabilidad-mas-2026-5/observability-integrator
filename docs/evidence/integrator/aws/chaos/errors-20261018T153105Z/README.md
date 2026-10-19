# Experimento 2: 10 % de errores en data-service

Necesitábamos inyectar 10 % de errores internos y retirar el fallo sin alterar datos.

El 18 de octubre de 2026 ejecutamos la prueba en nuestra cuenta personal, `us-east-2`. Usamos una tarea Fargate temporal por IP privada de A, sin entrada HTTP pública: 2,5 RPS —solicitudes por segundo— y fases de 180 s. Solo consultamos un registro sintético por GET: **cero escrituras**.

Medimos 50/500 errores internos. Service Connect los recuperó y las respuestas finales fueron 200. Después retiramos el caos y los recursos temporales. No medimos MTTD de alertamiento. El [procedimiento reproducible](../../../../../CHAOS_EXPERIMENT_2.md) conserva los pasos completos.

## Resultados medidos

p50, p95 y p99 son los tiempos que no supera el 50 %, 95 % y 99 % de las solicitudes de cada fase. Usamos milisegundos (ms). Las muestras enlazadas conservan los datos originales.

Calculamos los percentiles end-to-end del cliente mediante nearest-rank, en milisegundos. Conservamos las [muestras](samples.jsonl), el [resumen](summary.json) y los [tiempos de fases](phase-events.json).

| Fase UTC | Solicitudes | HTTP finales | Error final | p50 | p95 | p99 |
|---|---:|---|---:|---:|---:|---:|
| Normal 15:38:10–15:41:10 | 450 | 450 × 200 | 0 % | 18,63 | 47,28 | 87,63 |
| Inyección 15:41:10–15:44:10 | 450 | 450 × 200 | 0 % | 18,42 | 47,79 | 81,39 |
| Recuperación 15:44:10–15:47:10 | 450 | 450 × 200 | 0 % | 18,06 | 33,89 | 69,39 |

Durante la inyección contamos **500 intentos elegibles: 50 errores 503 y 450 éxitos, 10,00 % de fallos internos**. Service Connect reintentó las 50 operaciones afectadas; todas terminaron en 200.

Por eso distinguimos intentos internos y respuestas finales: el cliente no recibió un 10 % de errores. Tampoco contamos los reintentos como solicitudes nuevas del generador. No cambiamos proxies ni AIOps para desactivar esa protección.

## Trazas, logs y métricas

- [CloudWatch: 500 intentos elegibles](eligible-counter.json) y [50 errores](injected-error-counter.json), corroborados con 50 logs `chaos.error.injected`. El contador fue [50 al terminar la inyección](error-counter-after-injection.json) y [50 al terminar la recuperación](error-counter-after-recovery.json): no hubo nuevas inyecciones durante la recuperación.
- [Doce trazas X-Ray](xray-traces.json), tres por grupo: normal, inyección sin fallo, recuperación e inyección con fallo recuperado. [Validación de padres e hijos](trace-chain-validation.json): B desciende de A, data-service de B y PostgreSQL de data-service, con el mismo trace ID en las doce. No extrapolamos esta inspección a todas las trazas.
- Ejemplo recuperado: `1-6ad4e896-9fc9f95b50ed9f75e2200001` contiene un intento data-service HTTP 503 con span ERROR `chaos.error`, luego otro intento HTTP 200 y SQL SELECT. El intento fallido no accede a RDS; el reintento exitoso sí.
- [Logs correlacionados](correlated-failure-logs.json): 50 errores de data-service, 50 `credit.data.success` de B y 50 `credit.remote.success` de A, unidos por trace_id/span_id. La responsabilidad del fallo es data-service aunque A/B terminen exitosamente.
- [Métricas de proceso](memory-metrics.json) consultables en CloudWatch para los tres microservicios. No creamos alarmas ni dashboards.

## SLO y detección

SLO de trabajo end-to-end: **99,5 % de GET finales exitosos y ≤1000 ms**. Las 1350 solicitudes de las fases cumplieron ambas condiciones: cero solicitudes malas, presupuesto de ventana permitido 6,75 y consumo **0 %**. No equivale al presupuesto mensual restante.

SLO de trabajo separado para el servidor durante la inyección: **99,5 % de intentos físicos elegibles sin fallo inyectado**. Con 50/500 fallidos, presupuesto permitido 2,5, consumo de ventana **2000 %**, burn rate **20×**. No mezclamos ese denominador con las 450 operaciones lógicas del cliente. [Cálculo y alcance](server-error-slo.json).

No mezclamos el 10 % interno de data-service con el p99 del cliente. La regla exige errores > línea base + 2σ **Y** p99 > SLO, del mismo servicio y periodo. Los percentiles finales quedaron bajo 1000 ms; no demostramos la alerta.

Observamos el primer fallo real a las **15:41:10,493 UTC** y lo comprobamos operativamente en logs a las **15:41:42,681 UTC**, con una demora de 32,188 s. Mantenemos el **MTTD de alertamiento como no medido**: [no verificamos una alerta real correlacionada](alerts.json). El sondeo del controlador no es una notificación del sistema AIOps.

## Despliegue y limpieza

[Imagen verificada](image-publication.json): `api:chaos-errors-v2`, Linux/amd64, digest `sha256:28ce28d2a411989046aa611bc23a09f8cd9eb89b17a4ce47ed4db739e14a1a21`. `initial` intacta; A/B siguen `chaos-latency-v1`, Collectors `traces-v2`. Pasaron 47 pruebas Python y cinco pruebas Terraform con proveedor simulado, además de fmt/validate.

El [plan de activación](activation-plan-summary.json) solo creó cinco recursos temporales y reemplazó la definición de data-service, actualizando su servicio: **6 altas, 1 cambio, 1 baja**. El [plan de limpieza](cleanup-plan-summary.json) retira el gate y los cinco temporales: **1 alta, 1 cambio, 6 bajas**. No modifica RDS, IAM, AIOps ni reglas internas.

La política de despliegue actual interrumpe brevemente data-service al renovar su tarea. El healthcheck dependiente de B puede provocar su reemplazo automático por ECS; ocurrió antes de medir y esperamos a los tres servicios HEALTHY. No es un cambio Terraform de B ni un efecto de la inyección sobre healthchecks. Documentamos esta limitación para mejorar liveness/readiness por separado.

La [limpieza terminó a las 15:56:18 UTC](cleanup.json): gate retirado (`data_error_expires_at=0`), cliente detenido, cinco recursos temporales eliminados, definición temporal enviada a eliminación y stream temporal retirado después de guardar las evidencias. El plan final devolvió **No changes**. Los [tres servicios quedaron HEALTHY](final-services.json), A/B con `chaos-latency-v1`, data-service con `chaos-errors-v2` y los tres Collectors con `traces-v2`, [sin errores de exportación detectados](final-collector-errors.json).

La [consulta AWS final](final-aws-verification.json) confirma tres tareas activas, ninguna definición temporal activa y ninguna regla de entrada en Service A. Conservamos RDS y sus datos; no ejecutamos un destroy general.

## Intento anterior conservado

La [ejecución v1](../errors-20261018T150233Z/README.md) no fue válida: los reintentos amplificaron los errores hasta 50 % de intentos físicos. Conservamos el fallo, limpiamos AWS y corregimos el calendario por intento en v2 antes de repetir. No sobrescribimos evidencias ni imágenes.
