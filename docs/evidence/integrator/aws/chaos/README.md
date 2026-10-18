# Experimentos de caos — estado de evidencia

## Experimento 2: errores en data-service

La [ejecución corregida v2](errors-20261018T153105Z/README.md) del 18 de octubre de 2026 midió **50/500 errores internos (10 %)**. Los reintentos de Service Connect recuperaron las operaciones: 450 respuestas 200 en cada una de las tres fases de 180 s, a 2,5 RPS. X-Ray identifica el fallo en data-service y la recuperación hacia PostgreSQL en la misma traza; CloudWatch confirma logs y contadores. SLO del cliente sin consumo; SLO del servidor durante inyección con burn rate 20×. MTTD de alertamiento no medido.

Conservamos el [intento v1](errors-20261018T150233Z/README.md) como diagnóstico **no válido**: seleccionaba por solicitud lógica y los reintentos amplificaron los fallos hasta el 50 % de intentos físicos. No confundimos sus resultados con la validación v2. La limpieza v2 terminó con tres servicios HEALTHY, gate desactivado, cero recursos temporales activos y Terraform sin cambios.

## Ejecución real AWS

Ejecutamos y limpiamos el experimento correctamente el 18 de octubre de 2026. Consultamos el [informe y las evidencias reales](chaos-20261018T141822Z/README.md): 540 solicitudes por fase, cero errores, p99 **72,00 → 276,58 → 84,18 ms**, inyección confirmada en B, trazas completas y tres servicios finales HEALTHY. MTTD de alertamiento no medido. Terraform terminó sin cambios y sin recursos temporales activos.

## Validaciones locales anteriores

Las siguientes validaciones son locales y usan A/B reales en FastAPI TestClient con HTTPX MockTransport para la dependencia de datos; no usan RDS, red AWS ni exportación CloudWatch real. La espera de 200 ms sí es real. No confundimos estas mediciones con el resultado ECS anterior.

La [validación local de fases](local-validation.json) del 18 de octubre de 2026 obtuvo:

| Fase | GET | Errores | p99 descriptivo |
|---|---:|---:|---:|
| Normal | 4 | 0 | 26,32 ms |
| Inyección | 4 | 0 | 214,43 ms |
| Recuperación | 4 | 0 | 19,66 ms |

Duración configurada: 0,7 s por fase, objetivo 5 RPS, cliente secuencial. Es una prueba de mecanismo de muy bajo volumen, no un benchmark ni validación estadística del SLO. Un POST sintético creó el registro simulado; todas las lecturas posteriores se limitaron a ese identificador. Consumo del presupuesto de la muestra: 0 %, SLO de trabajo 99,5 % / 1000 ms. MTTD no medido: no existe alerta real en esta prueba.

La suite original más las pruebas nuevas pasó: **35 pruebas, 0 fallos, 2 advertencias de deprecación existentes**, en 8,54 s. Ejecutamos la suite con la imagen API existente, repositorio de solo lectura y red deshabilitada. Comprobamos además aislamiento de contexto, header opt-in, caducidad, exclusión de healthchecks/validaciones 422, errores de transporte, cálculo de estadísticas, modo stdout de solo lectura y span/métricas/contexto de logs de inyección con exportación en memoria. Ver [procedimiento y contrato AIOps](../../../../CHAOS_EXPERIMENT_1.md).

En una ejecución AWS aprobada, crear una carpeta nueva por fecha/ejecución y conservar `samples.jsonl`, `summary.json`, extractos sanitizados de spans y logs, consultas de métricas, evidencia de la alerta del equipo de AIOps (o ausencia de detección) y la comprobación de recuperación/limpieza. Nunca copiamos tokens, credenciales, estados Terraform, planes binarios, SQL con parámetros ni datos personales. `--output-dir -` permite recuperar los registros desde CloudWatch sin escribir en el contenedor temporal.
