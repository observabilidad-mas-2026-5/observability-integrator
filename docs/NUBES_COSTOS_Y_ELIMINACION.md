# AWS ECS Fargate y Google Cloud Run: preparación sin despliegue

Estado actualizado al 15 de octubre de 2026: este documento describe la propuesta Terraform y el bundle preparados y validados localmente. Por separado, la [implementación inicial AWS](IMPLEMENTACION_INICIAL_AWS.md) documenta seis repositorios ECR creados, imágenes de API y Collector publicadas y CloudWatch Logs preparado en `us-east-2`, con siete días de retención. No se confirmó un despliegue en ECS ni el flujo de las tres señales. GCP no se desplegó. Las estimaciones históricas siguientes no son una cotización actual ni evidencia de recursos activos; las cuentas y créditos no se consultaron durante esta revisión.

## Diseño y límites

A y B son procesos FastAPI independientes que se comunican por HTTP, junto con Collector, Jaeger, Prometheus, Loki, Grafana y gateway Nginx. Para una demostración breve se empaquetan en una tarea ECS o una instancia Cloud Run, compartiendo loopback. Esto conserva trazas HTTP/W3C y separa contenedores, pero no permite escalar/reiniciar microservicios de forma independiente. Confirmar con la profesora si exige servicios de plataforma separados. PostgreSQL se externaliza a RDS/Cloud SQL y no depende del disco efímero del contenedor.

Las configuraciones cloud están horneadas en imágenes derivadas, evitando bind mounts locales. Las interfaces se exponen por gateway en /grafana/, /jaeger/, /prometheus/ y la API en /. OTLP y DB no se publican por el gateway. En Cloud Run todo el ingreso requiere IAM; en AWS el security group solo permite el CIDR de la estudiante. AWS usa HTTP en el puerto 8080, adecuado solo para una prueba controlada con datos sintéticos: no se han preparado dominio, certificado ni ALB HTTPS.

La telemetría cloud es efímera: trazas en memoria y datos Loki/Prometheus/Grafana en disco del contenedor. Exportar evidencias antes de terminar la sesión. No es una configuración de producción ni prueba de retención durable de señales.

## Servicios previstos por la propuesta Terraform

| AWS | Cantidad/configuración | Costos posibles |
|---|---|---|
| ECS cluster y service Fargate | 1 tarea, 2 vCPU / 4 GiB, 8 contenedores | CPU y memoria por tiempo activo |
| VPC, 3 subnets, rutas, Internet Gateway y SG | 1 subnet pública ECS, 2 privadas RDS | IPv4 pública y transferencia; sin NAT ni ALB |
| RDS PostgreSQL 16 | db.t4g.micro, single-AZ, 20 GiB gp3 | Instancia, disco, posible CPU burst; no asumir free tier |
| ECR | 6 repositorios de imágenes | Almacenamiento, transferencias |
| CloudWatch Logs | Propuesta Terraform: 1 grupo, retención 3 días; fase inicial AWS documentada por separado: grupo y flujo `otel`, retención 7 días | Ingesta y almacenamiento |
| IAM | roles execution/task y política limitada | Sin tarifa directa por roles |
| Secrets Manager | secreto maestro RDS administrado; Grafana externo | Almacenamiento de secretos y lecturas |

| Google Cloud | Cantidad/configuración | Costos posibles |
|---|---|---|
| Cloud Run | 1 servicio, mínimo=1/máximo=1; 8 contenedores × 1 vCPU; 4 GiB total; CPU siempre asignada | Facturación por instancia aun sin peticiones |
| Cloud SQL PostgreSQL 16 | db-f1-micro, single-zone, 10 GiB SSD | CPU compartida, disco y red |
| Artifact Registry | 1 repositorio Docker | Almacenamiento y transferencias |
| Secret Manager | 2 secretos: DB/Grafana | Versiones y accesos |
| Cloud Logging | stdout de contenedores | Ingesta y retención según cuotas |
| IAM/service account y APIs | Cloud SQL client, secrets scoped, run.invoker al usuario | Roles sin costo directo; APIs habilitadas no implican uso gratuito |

Cloud Run necesita CPU activa para exportación/scraping en segundo plano. Mantener minimum instances=1 evita que desaparezca la telemetría al quedar sin tráfico, pero genera costo continuo. Los 8 vCPU son la suma de los recursos declarados por contenedor; AWS comparte 2 vCPU entre todo el bundle. Esas condiciones no son comparables para benchmarks entre nubes.

## Estimación orientativa al 12 de octubre de 2026

USD sin impuestos, descuentos, créditos, transferencia ni servicios auxiliares. Ejemplo región us-east-1 y us-central1, según tarifas publicadas consultadas:

- AWS Fargate: 2×0.000011244×3600 + 4×0.000001235×3600 = **US$0.0987/h**; dos horas ≈US$0.20; 730 horas ≈US$72.08 solo cómputo. IPv4 pública añade aproximadamente US$0.005/h, según precio publicado, sin contar RDS y auxiliares. [Fargate](https://aws.amazon.com/fargate/pricing/), [VPC IPv4](https://aws.amazon.com/vpc/pricing/).
- Cloud Run con facturación por instancia: (8×0.000018 + 4×0.000002)×3600 = **US$0.5472/h**; dos horas ≈US$1.09; 730 horas ≈US$399.46 solo cómputo. [Cloud Run](https://cloud.google.com/run/pricing).
- RDS y Cloud SQL son cargos adicionales continuos: confirmar la cotización regional y el tamaño elegido antes de aprobar. Reservar margen para disco mínimo, secretos, registries, logs y salida de datos. No se obtuvo una cotización completa autenticada. [RDS PostgreSQL](https://aws.amazon.com/rds/postgresql/pricing/), [Cloud SQL](https://cloud.google.com/sql/pricing).

No se promete costo total ni cobertura de la cuenta gratuita. Antes de desplegar, presentar un plan con cuenta/proyecto, región, recursos, duración máxima y presupuesto explícito. Reducir el bundle o migrar observabilidad a un backend externo requeriría revisar la rúbrica y el costo de ese backend.

## Validación permitida sin recursos

```powershell
powershell -NoProfile -File scripts/validate_infra.ps1
```

Terraform 1.13.3 en Docker descarga providers, ejecuta init -backend=false y validate. No autentica cuentas ni crea recursos. main.tf.json es formato Terraform JSON válido, no pseudocódigo. Se conservan .terraform.lock.hcl para fijar providers. Validate confirma esquema y expresiones, no disponibilidad regional, cuotas, permisos ni arranque real en las nubes.

## Procedimiento de referencia para completar despliegues, sujeto a aprobación

1. Confirmar proyecto/cuenta, región, límites de presupuesto, duración y CIDR. Revisar si el empaquetado de A/B satisface la guía original.
2. Autenticar con identidad del usuario sin introducir llaves en el repositorio. Copiar terraform.tfvars.example a terraform.tfvars y ajustar referencias. Los valores de ejemplo no son desplegables.
3. Revisar los repositorios e imágenes ya documentados en AWS antes de cualquier bootstrap adicional. Para GCP, aprobar registries/APIs, construir imágenes y publicar con tags inmutables. Un terraform apply -target para bootstrap es excepcional: revisar el plan completo de nuevo después, sin tratar el primer resultado como despliegue final.
4. AWS exige un secreto externo para Grafana: crearlo o elegir uno con permiso explícito. El rol ECS puede leer ese ARN y el secreto maestro RDS. Si hay KMS personalizado añadir permisos mínimos específicos; no están incluidos.
5. GCP requiere APIs habilitadas, Cloud SQL socket en /cloudsql y permisos Cloud SQL client/Secret accessor. Los secretos generados también aparecen en el estado Terraform: proteger y no compartir tfstate. IAM run.invoker se otorga solo a invoker_member.
6. Construir API con Dockerfile y las otras imágenes con `docker build -f infra/images/NAME.Dockerfile -t REGISTRY/NAME:REVISION .`. No ejecutar push antes de autorización, porque escribe en una cuenta remota.
7. Ejecutar terraform plan, revisar cambios y estimación, y solicitar aprobación del plan final antes de apply. No se incluirán apply automáticos en CI.
8. Probar health/CRUD, OTLP en cada cloud, trace_id y logs, capturar evidencias. En AWS obtener la IPv4 de la ENI de la tarea; en GCP usar identidad IAM y gcloud run services proxy para navegar sin publicar allUsers. No confiar en una URL declarada como evidencia de arranque.

## Cómo eliminar al terminar (no ejecutado)

Primero exportar evidencias y decidir si se necesita un backup de créditos. Ambos IaC declaran DB sin protección de borrado y sin backups automáticos para un laboratorio corto: destroy elimina créditos. No aplicar esos defaults a datos reales.

AWS:

- Revisar `terraform plan -destroy` en infra/aws y aprobar la eliminación.
- ECS service/tarea deben parar primero. Un destroy autorizado elimina task definition, ECS cluster/service, RDS, subnet group, SG/VPC/rutas/IGW, logs y roles.
- ECR tiene force_delete=false: repositorios con imágenes bloquean destroy. Tras autorización, borrar solo imágenes de los seis repositorios creados por este laboratorio; después repetir destroy. No eliminar repositorios ajenos.
- El secreto Grafana externo no lo administra este estado: conservarlo si era preexistente; eliminarlo por separado solo si se creó exclusivamente para este laboratorio y con aprobación. Revisar el secreto maestro RDS y su eliminación administrada por RDS.
- Verificar RDS, tareas, IPv4/ENI, ECR, Logs, Secrets y posibles snapshots residuales. Detener ECS solo no deja la cuenta sin cargos de RDS.

GCP:

- Revisar `terraform plan -destroy` en infra/gcp y aprobarlo. Exportar cualquier crédito necesario antes de eliminar Cloud SQL.
- Un destroy autorizado elimina Cloud Run, Cloud SQL, sus DB/usuario, secretos/versiones, IAM específico, cuenta de servicio y Artifact Registry.
- Si hay políticas o imágenes que impiden borrar el registry, limpiar exclusivamente este repositorio con autorización y repetir destroy.
- Las APIs quedan habilitadas por disable_on_destroy=false: no se deshabilitan servicios compartidos. El proyecto existente tampoco se elimina. Revisar Cloud Logging, backups/snapshots y otros recursos creados manualmente.
- Verificar la consola de facturación tras propagarse los cargos. Reducir min instances a cero no elimina Cloud SQL ni los discos/registries.

Esta guía documenta un procedimiento de referencia; no prueba su ejecución. Los avances parciales AWS se registran en IMPLEMENTACION_INICIAL_AWS.md. Esta actualización no ejecutó pasos cloud.

## Prueba adicional local de imágenes cloud

`python scripts/validate_cloud_bundle.py` construyó las cinco imágenes derivadas y ejecutó los ocho contenedores con red compartida en Docker local. Probó CRUD, traza A/B, targets y dashboard por gateway; guardó cloud-image-builds.json y cloud-bundle-local.json. Los contenedores desechables se detuvieron automáticamente al terminar. Esto no es un despliegue en AWS/GCP. Se separaron los puertos OTLP de Jaeger (14317/14318) de los del Collector (4317/4318) para evitar colisión de sockets al compartir namespace.

El bundle Cloud Run declara 8 vCPU y 4 GiB (512 MiB por contenedor) para respetar el mínimo de memoria asociado a 8 vCPU. [Restricciones oficiales de CPU/memoria](https://docs.cloud.google.com/run/docs/configuring/services/cpu). La región, cuotas y validación remota todavía deben verificarse después de autorización.
