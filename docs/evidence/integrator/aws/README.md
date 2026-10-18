# Validación real de arquitectura AWS — 18 de octubre de 2026

[Evidencia sanitizada de la solicitud](2026-10-18-synthetic-trace.json).

Una tarea Fargate temporal realizó **un POST** a la IP privada de A: HTTP **201**, estado `PENDING`. Se añadió un GET de solo lectura en esa misma tarea para comprobar persistencia: HTTP **200**, mismo identificador y estado. No hubo reintentos del POST. El registro sintético se conserva en RDS; no se consultaron ni publicaron datos de clientes reales.

X-Ray devolvió la traza `1-6ad47a7f-3cdc5608c1844867c3958ca5`, con la cadena padre-hijo A → HTTPX → B → HTTPX → data-service → `credit.persist` → PostgreSQL `INSERT`. Los tres segmentos servidor indicaron `error=false` y `fault=false`. El JSON conserva los identificadores necesarios para comprobar los enlaces, incluyendo padres derivados del anidamiento real de subsegmentos.

CloudWatch Logs recibió `credit.remote.success`, `credit.data.success` y `credit.persisted` con el mismo trace ID. La consulta CloudWatch PromQL de memoria del proceso devolvió HTTP 200 y series actuales de los tres servicios; esto no acredita todavía dashboards, alertas ni métricas HTTP de extremo a extremo.

La tarea terminó por sí sola con código 0. No se abrió acceso HTTP público; únicamente se permitió TCP 8000 desde el Security Group temporal hacia A. La IPv4 pública de la tarea se usó para salida HTTPS. La preparación y la retirada se controlan mediante `enable_synthetic_test`; ver [procedimiento reproducible](../../../../infra/aws/SYNTHETIC_TEST.md).

Retirada comprobada: plan **0 to add, 0 to change, 5 to destroy**, aplicado con **0 added, 0 changed, 5 destroyed**. Se solicitó además eliminar la revisión desregistrada y se eliminó el stream del cliente después de recuperar su evidencia. Consulta posterior: ningún Security Group temporal y ninguna entrada en A. Terraform devolvió **No changes. Your infrastructure matches the configuration.** No se ejecutó `terraform destroy` global.

Pruebas locales: Python del host no pudo recolectar las pruebas por dependencias ausentes. Reejecución en la imagen API existente, sin red y con repositorio de solo lectura: **16 passed**, dos advertencias de deprecación de Starlette/httpx/AnyIO. No se modificaron dependencias para ocultarlas.
