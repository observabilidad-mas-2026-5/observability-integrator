# Experimentos de caos — estado de evidencia

Comparamos dos fallos controlados con el comportamiento normal y la recuperación. Este índice separa las pruebas AWS de las locales; los informes conservan datos y limpieza.

Seguimos solicitudes con **trazas**, identificamos eventos con **logs** y contamos con **métricas**. Durante estos experimentos no demostramos alertas ni MTTD, el tiempo medio hasta detectar mediante alertamiento.

Posteriormente incorporamos [evidencias de AIOps y seguridad](../README.md#evidencias-posteriores-de-aiops-y-seguridad). No trasladamos sus pruebas de componentes ni la alerta de rechazos de red a los resultados históricos del caos. Para cumplir el objetivo de detección debemos repetir un escenario aprobado con la regla conjunta validada y registrar la notificación real.

## Experimento 2: errores en data-service

En la [ejecución corregida v2](errors-20261018T153105Z/README.md) del 18 de octubre de 2026 medimos **50/500 errores internos (10 %)**. Los reintentos de Service Connect recuperaron las operaciones: obtuvimos 450 respuestas 200 en cada fase de 180 s, a 2,5 RPS.

En X-Ray identificamos el fallo en data-service y la recuperación hacia PostgreSQL dentro de la misma traza; en CloudWatch corroboramos logs y contadores. Distinguimos el consumo cero del SLO del cliente del burn rate 20× del servidor durante la inyección. No medimos MTTD de alertamiento.

Conservamos el [intento v1 inválido](errors-20261018T150233Z/README.md): los reintentos elevaron el fallo interno al 50 %. La ejecución v2 terminó con tres servicios HEALTHY, caos desactivado, cero recursos temporales y Terraform sin cambios.

## Experimento 1: latencia en Service B

Ejecutamos y limpiamos el experimento correctamente el 18 de octubre de 2026. Consultamos el [informe y las evidencias reales](chaos-20261018T141822Z/README.md): 540 solicitudes por fase, cero errores, p99 **72,00 → 276,58 → 84,18 ms**, inyección confirmada en B, trazas completas y tres servicios finales HEALTHY. MTTD de alertamiento no medido. Terraform terminó sin cambios y sin recursos temporales activos.

## Validaciones locales anteriores

Estas pruebas locales usan A/B en FastAPI TestClient y HTTPX MockTransport para simular datos. La espera de 200 ms es real; no usamos RDS, red AWS ni CloudWatch. No las confundimos con la prueba ECS.

La [validación local de fases](local-validation.json) del 18 de octubre de 2026 obtuvo:

| Fase | GET | Errores | p99 descriptivo |
|---|---:|---:|---:|
| Normal | 4 | 0 | 26,32 ms |
| Inyección | 4 | 0 | 214,43 ms |
| Recuperación | 4 | 0 | 19,66 ms |

Duración configurada: 0,7 s por fase, objetivo 5 RPS, cliente secuencial. Es una prueba de mecanismo de muy bajo volumen, no un benchmark ni validación estadística del SLO. Un POST sintético creó el registro simulado; todas las lecturas posteriores se limitaron a ese identificador. Consumo del presupuesto de la muestra: 0 %, SLO de trabajo 99,5 % / 1000 ms.

MTTD no medido: no existe alerta real en esta prueba.

La suite original más las pruebas nuevas pasó: **35 pruebas, 0 fallos, 2 advertencias de deprecación existentes**, en 8,54 s. Ejecutamos la suite con la imagen API existente, repositorio de solo lectura y red deshabilitada.

Comprobamos además aislamiento de contexto, header opt-in, caducidad, exclusión de healthchecks/validaciones 422, errores de transporte, cálculo de estadísticas, modo stdout de solo lectura y span/métricas/contexto de logs de inyección con exportación en memoria. Ver [procedimiento y contrato AIOps](../../../../CHAOS_EXPERIMENT_1.md).

Guardamos cada ejecución en una carpeta nueva: `samples.jsonl`, `summary.json`, spans, logs, métricas, recuperación y limpieza. Para afirmar detección necesitamos una alerta real. No copiamos secretos, estados, planes binarios, SQL parametrizado ni datos personales. `--output-dir -` recupera los registros desde CloudWatch sin escribir en el contenedor.

Nunca copiamos tokens, credenciales, estados Terraform, planes binarios, SQL con parámetros ni datos personales. `--output-dir -` permite recuperar los registros desde CloudWatch sin escribir en el contenedor temporal.
