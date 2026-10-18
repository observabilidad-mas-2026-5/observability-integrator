# Validación real de arquitectura AWS — 18 de octubre de 2026

[Evidencia sanitizada de la solicitud](2026-10-18-synthetic-trace.json).

Este informe corresponde a la validación inicial de arquitectura. Presentamos los experimentos posteriores, sus etiquetas de imágenes y la limpieza final en el [índice de caos](chaos/README.md). Los estados y conteos siguientes describen aquella ejecución, no una consulta AWS realizada durante esta revisión documental.

Ejecutamos **un POST** desde una tarea Fargate temporal hacia la IP privada de A y obtuvimos HTTP **201**, estado `PENDING`. Añadimos un GET de solo lectura en esa misma tarea para comprobar persistencia: HTTP **200**, mismo identificador y estado. No reintentamos el POST. Conservamos el registro sintético en RDS; no consultamos ni publicamos datos de clientes reales.

X-Ray devolvió la traza `1-6ad47a7f-3cdc5608c1844867c3958ca5`, con la cadena padre-hijo A → HTTPX → B → HTTPX → data-service → `credit.persist` → PostgreSQL `INSERT`. Los tres segmentos servidor indicaron `error=false` y `fault=false`. El JSON conserva los identificadores necesarios para comprobar los enlaces, incluyendo padres derivados del anidamiento real de subsegmentos.

CloudWatch Logs recibió `credit.remote.success`, `credit.data.success` y `credit.persisted` con el mismo trace ID. La consulta CloudWatch PromQL de memoria del proceso devolvió HTTP 200 y series actuales de los tres servicios; esto no acredita todavía dashboards, alertas ni métricas HTTP de extremo a extremo.

La tarea terminó por sí sola con código 0. No se abrió acceso HTTP público; únicamente se permitió TCP 8000 desde el Security Group temporal hacia A. La IPv4 pública de la tarea se usó para salida HTTPS. La preparación y la retirada se controlan mediante `enable_synthetic_test`; ver [procedimiento reproducible](../../../../infra/aws/SYNTHETIC_TEST.md).

Retirada comprobada: plan **0 to add, 0 to change, 5 to destroy**, aplicado con **0 added, 0 changed, 5 destroyed**. Se solicitó además eliminar la revisión desregistrada y se eliminó el stream del cliente después de recuperar su evidencia. Consulta posterior: ningún Security Group temporal y ninguna entrada en A. Terraform devolvió **No changes. Your infrastructure matches the configuration.** No se ejecutó `terraform destroy` global.

Durante esta validación, Python del host no pudo recolectar las pruebas por dependencias ausentes. Repetimos la ejecución en la imagen API existente, sin red y con el repositorio de solo lectura: **16 passed**, dos advertencias de deprecación de Starlette/httpx/AnyIO. No modificamos dependencias para ocultarlas. Este conteo corresponde a la etapa inicial, no a la suite ampliada de los experimentos.
