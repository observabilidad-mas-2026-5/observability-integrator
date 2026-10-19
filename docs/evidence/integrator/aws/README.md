# Validación real de arquitectura AWS — 18 de octubre de 2026

[Evidencia sanitizada de la solicitud](2026-10-18-synthetic-trace.json).

Necesitábamos seguir una solicitud hasta RDS sin abrir HTTP público. Usamos una tarea Fargate temporal: un contenedor de prueba dentro de nuestra red.

Obtuvimos creación 201, lectura 200 y traza A → B → data-service → PostgreSQL. Retiramos los recursos. Los datos siguientes pertenecen a esa ejecución, no a una consulta nueva.

Los experimentos posteriores, sus imágenes y su limpieza están en el [índice de caos](chaos/README.md). Las alertas y los dashboards no quedan demostrados por esta prueba inicial.

## Evidencias posteriores de AIOps y seguridad

| Frente | Qué conservamos | Alcance y pendiente |
|---|---|---|
| [AIOps](../../../Modulo-B-AIOps-Deteccion-Automática-de-Anomalías.md) | [Ocho capturas](Punto-b/) de alarmas, SNS, Lambda y consultas. | Configuración y pruebas individuales; no acreditamos detección automática correlacionada, alerta con trace_id ni reducción de ruido. |
| [Seguridad](../../../ModuloC-Network-and-Security%20-Observability.md) | [Siete capturas](Punto-C/) de Flow Logs, filtro, alarma, historial, notificación y dashboard. | El historial muestra la acción SNS de una alarma de rechazos. No prueba un ataque ni detección de autenticaciones o CVEs. |

Las capturas complementan los informes; no sustituyen sus límites ni los resultados originales del caos. El módulo B reporta pruebas de SNS y Lambda; la captura de invocación sintética no demuestra por sí sola una activación automática. El módulo C reporta denegaciones por políticas de organización para Inspector y Security Hub, sin capturas específicas de esas denegaciones en este conjunto. No consultamos AWS de nuevo para esta revisión.

## Solicitud privada y limpieza de la arquitectura

Ejecutamos **un POST** desde una tarea Fargate temporal hacia la IP privada de A y obtuvimos HTTP **201**, estado `PENDING`. Añadimos un GET de solo lectura en esa misma tarea para comprobar persistencia: HTTP **200**, mismo identificador y estado. No reintentamos el POST. Conservamos el registro sintético en RDS; no consultamos ni publicamos datos de clientes reales.

X-Ray devolvió la traza `1-6ad47a7f-3cdc5608c1844867c3958ca5`, con la cadena padre-hijo A → HTTPX → B → HTTPX → data-service → `credit.persist` → PostgreSQL `INSERT`. Los tres segmentos servidor indicaron `error=false` y `fault=false`. El JSON conserva los identificadores necesarios para comprobar los enlaces, incluyendo padres derivados del anidamiento real de subsegmentos.

CloudWatch Logs recibió `credit.remote.success`, `credit.data.success` y `credit.persisted` con el mismo trace ID. La consulta CloudWatch PromQL de memoria del proceso devolvió HTTP 200 y series actuales de los tres servicios; esto no acredita todavía dashboards, alertas ni métricas HTTP de extremo a extremo.

La tarea terminó por sí sola con código 0. No se abrió acceso HTTP público; únicamente se permitió TCP 8000 desde el Security Group temporal hacia A. La IPv4 pública de la tarea se usó para salida HTTPS. La preparación y la retirada se controlan mediante `enable_synthetic_test`; ver [procedimiento reproducible](../../../../infra/aws/SYNTHETIC_TEST.md).

Retiramos los recursos con un plan **0 to add, 0 to change, 5 to destroy**, aplicado con **0 added, 0 changed, 5 destroyed**. Solicitamos eliminar la revisión desregistrada y retiramos el stream del cliente después de guardar la evidencia.

Comprobamos que no quedaban Security Groups temporales ni entradas en A. Terraform devolvió **No changes. Your infrastructure matches the configuration.** No ejecutamos `terraform destroy` global.

Durante esta validación, Python del host no pudo recolectar las pruebas por dependencias ausentes. Repetimos la ejecución en la imagen API existente, sin red y con el repositorio de solo lectura: **16 passed**, dos advertencias de deprecación de Starlette/httpx/AnyIO. No modificamos dependencias para ocultarlas. Este conteo corresponde a la etapa inicial, no a la suite ampliada de los experimentos.
