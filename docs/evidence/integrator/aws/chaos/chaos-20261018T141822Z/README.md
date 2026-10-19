# Experimento AWS real: 200 ms en Service B

Necesitábamos medir el efecto de añadir 200 ms a B. Realizamos `chaos-20261018T141822Z` el 18 de octubre de 2026, región `us-east-2`, perfil `observability-integrator`.

Reutilizamos las imágenes: no reconstruimos ni publicamos ninguna. Observamos más latencia, sin errores finales, y recuperamos el comportamiento normal. Todos los tiempos siguientes son UTC. No medimos MTTD de alertamiento.

## Resultado medido

p50, p95 y p99 son los tiempos que no supera el 50 %, 95 % y 99 % de las solicitudes de cada fase. Usamos milisegundos (ms). Las muestras enlazadas conservan los datos originales.

Realizamos un POST sintético que devolvió **HTTP 201**; después ejecutamos **1620 GET**, limitados al identificador recién creado, sin errores. No utilizamos datos personales. Conservamos el registro sintético en RDS y no modificamos su infraestructura.

| Fase | Inicio → fin UTC | GET / duración | RPS real | p50 | p95 | p99 | Errores |
|---|---|---|---:|---:|---:|---:|---:|
| Normal | 14:24:26.311621 → 14:27:26.311936 | 540 / 180,000315 s | 2,999995 | 18,37 ms | 42,87 ms | 72,00 ms | 0 |
| Inyección | 14:27:26.312505 → 14:30:26.312654 | 540 / 180,000149 s | 2,999998 | 219,79 ms | 249,71 ms | 276,58 ms | 0 |
| Recuperación | 14:30:26.313214 → 14:33:26.313327 | 540 / 180,000113 s | 2,999998 | 18,86 ms | 46,55 ms | 84,18 ms | 0 |

Fuente: [muestras individuales](samples.jsonl), [resumen original](summary.json), [eventos de fases](client-phase-events.json) y [POST 201](setup.json). Percentiles nearest-rank descriptivos por fase; no son una prueba estadística de un SLO mensual. Cliente secuencial con pacing sin ráfagas de compensación. Máximos medidos: 162,37 / 322,98 / 153,95 ms respectivamente.

La inyección elevó el p50 en **201,42 ms** y el p99 en **204,58 ms** respecto al baseline. El p99 de recuperación quedó 12,18 ms por encima del baseline, dentro de la tolerancia descriptiva de 20 ms acordada para esta prueba. Ver [comparación](recovery-comparison.json).

## Trazas, métricas y logs

- [Diez trazas seleccionadas](xray-selected-traces.json): POST inicial más primera/intermedia/última lectura de cada fase. Todas contienen A → B → data-service → PostgreSQL en un mismo trace ID, con relaciones padre-hijo explícitas o derivadas del anidamiento X-Ray. Los spans SQL conservan operación y sistema, no parámetros ni sentencias con datos.
- Las tres trazas de inyección contienen `chaos.latency` **solo en Service B**, con duraciones **201,07 / 201,08 / 201,15 ms**. No aparece ese span en las muestras normal o recuperación.
- CloudWatch respondió HTTP 200 a las consultas del contador: **540** al terminar la inyección y **540** después de recuperación, sin incremento adicional. Ver [contador tras inyección](cloudwatch-counter-after-injection.json) y [tras recuperación](cloudwatch-counter-after-recovery.json).
- [Logs de B](injection-logs.json): **540** eventos `chaos.latency.started` y **540** `chaos.latency.injected`, con trace/span IDs. Los [logs del POST](setup-correlated-logs.json) correlacionan `credit.remote.success`, `credit.data.success` y `credit.persisted` en los tres servicios.
- La [consulta de memoria](cloudwatch-memory.json) devolvió series de los tres servicios en la ventana de la prueba. En los [Collectors finales](final-collector-errors.json) no encontramos errores de exportación en los registros revisados. No creamos ni modificamos dashboards, alarmas, AIOps o recursos de seguridad.

## SLO y detección

SLO de trabajo: **99,5 % de GET exitosos y ≤1000 ms**, en la ventana de este experimento. Hubo **0 solicitudes malas de 1620**: éxito observado 100 %, presupuesto permitido `1620 × 0,005 = 8,1` solicitudes, consumo **0 %**, burn rate **0**. Cada fase tuvo presupuesto permitido 2,7 y consumo cero. No extrapolamos este resultado al presupuesto restante mensual.

La demora fue real, pero no violó el umbral de 1 s ni produjo errores; esto no demuestra un fallo de las alertas.

La demora sola no prueba una alerta. Aplicamos el [criterio conjunto](../../../../../../infra/aws/metrics-queries.md#condición-conjunta-de-aiops): errores > línea base + 2σ **Y** p99 > SLO, en el mismo servicio y periodo.

Inicio real del fallo, según el primer log de B: **14:27:26.317000 UTC**. Primera verificación automática del controlador: **14:27:55.898983 UTC** (29,58 s después), registrada en [run.json](run.json). Esta demora corresponde al sondeo y consulta de logs, **no es MTTD de alertamiento**.

La [observación de alarmas](alert-observation.json) no encontró alarmas métricas cuya configuración contuviera el nombre del integrador; no verificamos ninguna notificación correlacionada. **MTTD de alertamiento: no medido (`null`)**. No inferimos que no existan otras alarmas en la cuenta ni modificamos el trabajo del equipo de AIOps y seguridad.

## Recuperación y limpieza verificadas

- Recuperación sin marcador desde 14:30:26 UTC, sin nuevos incrementos del contador ni spans de demora en las trazas seleccionadas.
- [Plan de activación](activation-plan-summary.json): dos revisiones A/B, dos actualizaciones de sus servicios y cinco altas temporales; imágenes, RDS, IAM y recursos ajenos permanecieron intactos.
- [Plan de retirada](cleanup-plan-summary.json): eliminamos los cinco recursos temporales y renovamos exclusivamente A/B para retirar las variables de caos. No ejecutamos `terraform destroy` general.
- [Limpieza](cleanup.json) terminada a las **14:41:59 UTC**: `chaos_expires_at=0`, sin grupo temporal ni entrada en A; Terraform devolvió **No changes** usando las mismas etiquetas y overrides. La revisión temporal fue desregistrada y se solicitó su eliminación; el stream del cliente se retiró después de guardar evidencia. ECS puede retener historial de tareas detenidas sin cómputo activo.
- [Estado final](final-services.json): A y B en `api:chaos-latency-v1`, data-service en `api:initial`; los tres HEALTHY, 1/1, despliegues COMPLETED. Collectors en `traces-v2`, cero errores detectados. RDS y servicios permanecen activos y generan costos.

Procedimiento de reproducción: `python scripts/run_aws_latency_experiment.py --execute`, desde la raíz. Ese comando realiza cambios reales y requiere aprobación para cada nueva ejecución; sin `--execute` se niega a operar. Comprueba identidad y planes, limita los cambios al experimento, utiliza una tarea idempotente y ejecuta limpieza en `finally`. Los planes binarios permanecen bajo `.terraform/`, excluidos de Git; las evidencias solo incluyen campos seleccionados sin credenciales.

Conservamos ese comando como procedimiento histórico de la primera ejecución. Tras el experimento 2, su controlador todavía selecciona `initial` para data-service por omisión; rechaza el cambio adicional al revisar el plan. Antes de repetir necesitamos adaptar los overrides a las etiquetas vigentes, sin modificar servicios ajenos. Esta revisión documental no realiza esa adaptación ni ejecuta el experimento.
