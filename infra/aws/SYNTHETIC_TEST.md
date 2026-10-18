# Solicitud sintética privada, temporal y única

Esta preparación no lanza tareas automáticamente. Usar exclusivamente la cuenta personal `467866783326`, región `us-east-2`. Seguir el procedimiento de credenciales temporales del [README](README.md), sin modificar perfiles laborales ni imprimir credenciales. Todos los comandos de ejecución y retirada siguientes requieren aprobación previa. La ejecución autorizada del 18 de octubre y su retirada están documentadas en las [evidencias reales](../../docs/evidence/integrator/aws/README.md).

## Preparación y revisión

```bash
terraform -chdir=infra/aws fmt
terraform -chdir=infra/aws validate
terraform -chdir=infra/aws plan -input=false \
  -var=deploy_services=true -var=image_tag=initial -var=collector_image_tag=traces-v2 \
  -var=enable_synthetic_test=true -out=.terraform/synthetic-test-review.tfplan
```

Resultado esperado: **5 to add, 0 to change, 0 to destroy**: un Security Group sin entrada, dos reglas de salida (8000 hacia A y 443), una entrada en A exclusivamente desde el grupo temporal y una definición de tarea. Sin cambios en servicios, definiciones de tarea actuales, RDS ni IAM. Si aparece cualquier diferencia adicional, detenerse. Aplicar solamente tras aprobación independiente y revisión del plan vigente.

La salida 443 a `0.0.0.0/0` está limitada por puerto, no por destino: permite ECR, descarga de capas desde S3 y CloudWatch Logs, pero también otros destinos HTTPS. Los Security Groups no filtran por nombre DNS; restringir a endpoints privados requeriría infraestructura adicional facturable. No se crea NAT, balanceador, servicio ECS ni rol IAM. Se reutiliza el rol de ejecución de A (pull ECR y logs); no se asigna rol de tarea, secreto, credencial RDS ni permiso administrativo al contenedor.

## Ejecución única posterior a la aprobación

Git Bash, desde la raíz. Los comandos AWS siempre seleccionan explícitamente el perfil personal. La API `RunTask` no admite Service Connect: se descubre la IP privada vigente de A y se usa directamente. A conserva su proxy para B y B para data-service. No reutilizar una IP después de renovar la tarea de A.

```bash
PROFILE=observability-integrator
REGION=us-east-2
CLUSTER=observability-integrator
ACCOUNT=$(aws sts get-caller-identity --profile "$PROFILE" --region "$REGION" --query Account --output text)
test "$ACCOUNT" = 467866783326 || exit 1

DEFINITION=$(terraform -chdir=infra/aws output -json synthetic_test | python -c 'import json,sys; print(json.load(sys.stdin)["task_definition"])')
GROUP=$(terraform -chdir=infra/aws output -json synthetic_test | python -c 'import json,sys; print(json.load(sys.stdin)["security_group"])')
SUBNET=$(terraform -chdir=infra/aws output -json synthetic_test | python -c 'import json,sys; print(json.load(sys.stdin)["subnet"])')
A_TASK=$(aws ecs list-tasks --profile "$PROFILE" --region "$REGION" --cluster "$CLUSTER" \
  --service-name observability-integrator-service-a --desired-status RUNNING --query 'taskArns[0]' --output text)
A_IP=$(aws ecs describe-tasks --profile "$PROFILE" --region "$REGION" --cluster "$CLUSTER" --tasks "$A_TASK" \
  --query 'tasks[0].attachments[].details[] | [?name==`privateIPv4Address`].value | [0]' --output text)
test -n "$A_IP" && test "$A_IP" != None || exit 1
OVERRIDES=$(python -c 'import json,sys; print(json.dumps({"containerOverrides":[{"name":"synthetic","environment":[{"name":"SERVICE_A_PRIVATE_IP","value":sys.argv[1]}]}]}))' "$A_IP")
RESULT=$(aws ecs run-task --profile "$PROFILE" --region "$REGION" --cluster "$CLUSTER" \
  --launch-type FARGATE --count 1 --task-definition "$DEFINITION" \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$GROUP],assignPublicIp=ENABLED}" \
  --overrides "$OVERRIDES" --output json)
TASK=$(printf '%s' "$RESULT" | python -c 'import json,sys; r=json.load(sys.stdin); assert not r.get("failures"), r.get("failures"); assert len(r.get("tasks",[]))==1; print(r["tasks"][0]["taskArn"])') || exit 1
aws ecs wait tasks-stopped --profile "$PROFILE" --region "$REGION" --cluster "$CLUSTER" --tasks "$TASK"
aws ecs describe-tasks --profile "$PROFILE" --region "$REGION" --cluster "$CLUSTER" --tasks "$TASK" \
  --query 'tasks[].{reason:stoppedReason,containers:containers[].{name:name,exit:exitCode,reason:reason}}'
STREAM="synthetic/synthetic/${TASK##*/}"
aws logs get-log-events --profile "$PROFILE" --region "$REGION" \
  --log-group-name /ecs/observability-integrator --log-stream-name "$STREAM"
```

La tarea usa 0,25 vCPU/512 MiB, IPv4 pública solo para salida y ninguna entrada. Hay cargos breves Fargate (mínimo facturable Linux de un minuto), IPv4 y logs. No hay reinicio automático por un servicio ECS. El cliente realiza un único POST, sin reintentos ni redirecciones; registra `traceparent`, `trace_id`, `xray_trace_id`, hora UTC, código HTTP y `application_id`. Exigir salida 0 y HTTP 201/PENDING. Si falla o expira, no reintentar automáticamente: el registro podría haberse persistido antes del fallo de respuesta. La tarea deja un registro sintético en RDS; no existe endpoint DELETE y esta preparación no borra datos.

El operador necesita `ecs:RegisterTaskDefinition`, `ecs:RunTask`, `ecs:DescribeTasks`, `ecs:ListTasks`, `ecs:StopTask`, `ecs:DeregisterTaskDefinition`, `ecs:DeleteTaskDefinitions`, lectura de logs y `iam:PassRole` limitado al rol de ejecución de A. Terraform necesita administrar el grupo y las tres reglas temporales. No se otorgan estos permisos al contenedor.

El comando incluye además un GET de solo lectura del identificador recién creado y exige HTTP 200 con el mismo ID y estado `PENDING`. No repite el POST. La validación real inicial utilizó este GET mediante un override del comando; queda incorporado aquí para que las siguientes ejecuciones sean reproducibles.

## Evidencia de las tres señales

Después de esperar la entrega asíncrona, copiar `xray_trace_id` desde el evento `synthetic.request`:

```bash
aws xray batch-get-traces --profile "$PROFILE" --region "$REGION" --trace-ids "$XRAY_TRACE_ID"
aws logs filter-log-events --profile "$PROFILE" --region "$REGION" \
  --log-group-name /ecs/observability-integrator/otel --filter-pattern "\"$TRACE_ID\""
```

Definir previamente `XRAY_TRACE_ID` con formato `1-xxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxx` y `TRACE_ID` con sus 32 dígitos hexadecimales, ambos tomados del cliente. En X-Ray, inspeccionar segmentos y subsegmentos recursivamente: mismo `trace_id`, atribución `otel.resource.service.name` a A/B/data-service, relaciones `parent_id`/`id` y span PostgreSQL con `db.system.name=postgresql` y `db.operation.name=INSERT`. El padre externo del span servidor de A corresponde al ID enviado en `traceparent`; el cliente no exporta un span propio. No confundir nombres de segmentos con identidad del servicio.

Buscar `credit.remote.success` (A), `credit.data.success` (B), `credit.persisted` (data-service), todos con el mismo trace ID y span IDs correspondientes. Verificar también métricas recientes de los tres servicios en CloudWatch OTel y HTTP en los destinos donde estén configuradas; no asumir que las métricas Prometheus locales aparecen automáticamente en OTLP. Guardar evidencia sanitizada en `docs/evidence/integrator/`, sin estados, planes binarios ni credenciales.

## Retirada completa de los recursos temporales

Guardar evidencia y comprobar primero que la tarea esté STOPPED. Si quedó colgada, detener únicamente el ARN guardado en `TASK`, nunca servicios del laboratorio. No deshabilitar la preparación hasta que termine la prueba.

```bash
# Solo si fuera necesario y con aprobación:
# aws ecs stop-task --profile "$PROFILE" --region "$REGION" --cluster "$CLUSTER" --task "$TASK" --reason synthetic-test-cleanup
terraform -chdir=infra/aws plan -input=false \
  -var=deploy_services=true -var=image_tag=initial -var=collector_image_tag=traces-v2 \
  -var=enable_synthetic_test=false -out=.terraform/synthetic-test-cleanup.tfplan
```

Resultado esperado tras haber creado los recursos: **0 to add, 0 to change, 5 to destroy**. Revisar y aplicar únicamente tras aprobación separada; no utilizar `terraform destroy` global ni `-target`. Se eliminan el grupo y sus reglas, incluida la entrada temporal en A, y se desregistra la definición de tarea. Las tres aplicaciones siguen activas con sus imágenes actuales.

Terraform desregistra la revisión de tarea; si se requiere eliminar además la revisión INACTIVE, usar después `aws ecs delete-task-definitions --profile "$PROFILE" --region "$REGION" --task-definitions "$DEFINITION"`, solo cuando no tenga tareas en ejecución. Después de guardar las evidencias, eliminar exclusivamente el stream temporal con `aws logs delete-log-stream --profile "$PROFILE" --region "$REGION" --log-group-name /ecs/observability-integrator --log-stream-name "$STREAM"`. No eliminar grupos compartidos ni los streams de aplicaciones. ECS puede conservar temporalmente historial de tareas detenidas; no son tareas activas ni cargos de cómputo. No borrar el registro sintético de RDS sin aprobación independiente.
