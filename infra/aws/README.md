# AWS temporal — Ohio

Estado al 18 de octubre de 2026: infraestructura desplegada en Ohio, tres servicios activos y recorrido completo validado con datos sintéticos. Consultar las [evidencias reales](../../docs/evidence/integrator/aws/README.md). Los recursos temporales de prueba se retiraron; RDS y los tres servicios se conservan activos y generan costos.

## Arquitectura

Tres servicios ECS Fargate separados: Service A → Service B → data-service → RDS PostgreSQL 16. Cada tarea usa 0,5 vCPU y 1 GiB, con aplicación y Collector; ECS añade el proxy de Service Connect. Total con una tarea por servicio: 1,5 vCPU, 3 GiB y tres IPv4 públicas. La aplicación reserva 128 unidades CPU y 256 MiB; el Collector otras 128 y 256 MiB, dejando capacidad para el proxy. Es una hipótesis de laboratorio que requiere medir memoria, CPU y reinicios al desplegar, no un dimensionamiento productivo.

Región fijada por validación a `us-east-2`. Nombres bajo `observability-integrator`. Sin NAT Gateway, ALB, EFS, Private CA ni endpoints privados facturables. Las tareas tienen salida HTTPS a AWS mediante Internet Gateway; B y data-service no aceptan tráfico público. Las llamadas entre tareas usan direcciones privadas y Service Connect. La API no admite entrada pública salvo que se configure un único `allowed_cidr` IPv4 /32.

Las dos subredes de RDS tienen tabla de rutas propia sin ruta a Internet. RDS no tiene IP pública; 5432 solo permite el Security Group de data-service. PostgreSQL exige TLS mediante `rds.force_ssl=1`. La imagen `infra/images/api-aws.Dockerfile` descarga mediante HTTPS la CA oficial de Ohio, comprueba que sea interpretable y la instala en `/etc/rds/us-east-2-bundle.pem`. data-service usa el hostname de RDS y `verify-full`. Esto valida la preparación del cliente; falta comprobar una conexión real y rechazo de una CA incorrecta contra RDS.

Service Connect usa descubrimiento HTTP y proxies, con métricas L7 en CloudWatch `AWS/ECS`. No es AWS App Mesh ni acredita cumplimiento literal de ese requisito: App Mesh se retiró el 30 de septiembre de 2026. Acordar esa diferencia con la rúbrica. No se habilita TLS entre proxies: hacerlo posteriormente requiere evaluar Private CA y sus cargos. La conexión a RDS sí verifica TLS.

La aplicación utiliza el usuario administrador de RDS para conservar la creación automática de tablas del laboratorio. Es una concesión temporal, no mínimo privilegio SQL: antes de uso productivo se necesita usuario de aplicación limitado y migraciones separadas. Solo data-service recibe credenciales. Los roles de ejecución de A/B no pueden leer el secreto; el rol de data-service solo puede leer el secreto administrado por RDS. No se lee su valor desde Terraform ni se publica en outputs. La rotación del secreto requiere renovar la tarea para recibir el nuevo valor. Los roles de tarea exportan telemetría; cada aplicación comparte el rol de su Collector porque ECS asigna el rol a toda la tarea.

## Telemetría y contrato para Camilo

`collector-aws.Dockerfile` incluye la configuración AWS: trazas mediante `awsxray` a X-Ray, métricas a CloudWatch OTel y logs a CloudWatch Logs mediante OTLP HTTP y SigV4. La imagen publicada `initial` conserva el exporter anterior hasta un despliegue aprobado de `traces-v2`. Usa credenciales temporales del rol de tarea, nunca claves estáticas. Los grupos `/ecs/observability-integrator` y `/ecs/observability-integrator/otel` tienen retención de tres días; hay un stream OTLP por servicio. Las salidas JSON de aplicación también se capturan con `awslogs`, por lo que algunos eventos aparecen tanto en runtime como en OTLP: consultar una sola fuente para evitar conteos duplicados.

Jaeger, Loki, Grafana y Prometheus del Compose local se conservan. No se despliegan sus contenedores en AWS: allí los destinos son X-Ray y CloudWatch, reduciendo tareas y almacenamiento. Las consultas de Grafana local no se trasladan automáticamente a CloudWatch. Las [consultas de preparación](metrics-queries.md) identifican solicitudes, errores y p99 por servicio; faltan su ejecución real y las alertas que implementará Camilo. No se habilitan Application Signals, Container Insights, enriquecimiento de métricas AWS, Flow Logs ni Security Hub implícitamente.

## Validación sin crear recursos

Desde la raíz:

```powershell
terraform -chdir=infra/aws fmt
terraform -chdir=infra/aws init -backend=false
terraform -chdir=infra/aws validate
terraform -chdir=infra/aws fmt -check
```

La configuración heredada se mantiene en formato `.tf.json`; `fmt` no reformatea JSON. La plantilla `.tfvars.example` no es una entrada automática y los valores predeterminados coinciden con ella. Copiarla a un archivo privado ignorado solo si se necesitan ajustes. No introducir claves, contraseñas o tokens. Nunca publicar estado o planes binarios.

## Backend S3 compartido y perfil exclusivo

El backend usa el bucket existente `observabilidad-mas-2026-5-tfstate-aws`, key `integrator/terraform.tfstate`, región `us-east-2`, `encrypt=true` y `use_lockfile=true`. No administra ni recrea el bucket. El backend y el proveedor no fijan un perfil: reciben las credenciales temporales exportadas exclusivamente desde `observability-integrator` a la terminal actual; no se altera `default`. Cada integrante utiliza su propia identidad autorizada, sin compartir credenciales. No combinar `AWS_PROFILE` con credenciales exportadas en estas ejecuciones.

La revisión del bucket confirmó los cuatro controles de bloqueo de acceso público activos, versionado `Enabled`, cifrado predeterminado `AES256` y ubicación `us-east-2`. Es una comprobación de configuración del bucket, no una prueba de escritura o de bloqueo concurrente. Mantener el bucket fuera del ciclo de eliminación de la infraestructura del laboratorio.

Desde la raíz, con Terraform 1.10 o superior y el perfil autenticado:

```powershell
aws sts get-caller-identity --profile observability-integrator --region us-east-2 --query 'Account!=`null`' --output json
terraform -chdir=infra/aws init -reconfigure -input=false
terraform -chdir=infra/aws validate
```

`init -backend=false` sirve para validación estática sin inicializar S3. `init -reconfigure` selecciona el backend compartido sin migrar automáticamente un estado local. Si alguien tiene infraestructura ya administrada por un estado local, detenerse y coordinar una migración revisada antes de continuar; no ignorar ni sobreescribir ese estado. Utilizar el workspace `default` para que todos trabajen sobre la key indicada. No crear workspaces separados ni copiar estados de otros laboratorios. Revisar siempre el plan antes de aplicar y no deshabilitar el bloqueo.

El problema inicial de compatibilidad de `aws login` con Terraform 1.12.2 se resolvió exportando credenciales temporales del perfil personal al proceso de Terraform, sin imprimirlas ni modificar perfiles. El backend compartido está inicializado y se utilizó para los despliegues y la limpieza. En Git Bash, usar el bloque de exportación de la sección Collector antes de ejecutar Terraform; no activar `set -x`, no guardar la salida de credenciales y cerrar la terminal al terminar. Las consultas AWS CLI mantienen `--profile observability-integrator --region us-east-2` explícitos.

Permisos mínimos del operador sobre este backend:

- `s3:ListBucket` en `arn:aws:s3:::observabilidad-mas-2026-5-tfstate-aws`, restringido al prefijo `integrator/` según las operaciones necesarias.
- `s3:GetObject` y `s3:PutObject` en `arn:aws:s3:::observabilidad-mas-2026-5-tfstate-aws/integrator/terraform.tfstate`.
- `s3:GetObject`, `s3:PutObject` y `s3:DeleteObject` en `arn:aws:s3:::observabilidad-mas-2026-5-tfstate-aws/integrator/terraform.tfstate.tflock`.

No se necesita DynamoDB para este bloqueo nativo S3. No otorgar borrado del estado como parte del permiso normal de bloqueo. Los permisos para inspeccionar las protecciones del bucket son adicionales y no se incorporan a los roles de las aplicaciones. El cifrado AES256 usa SSE-S3, sin una clave KMS del cliente. Proteger también los permisos de lectura: el estado puede contener información sensible aunque esté cifrado. Referencia: [backend S3 de Terraform](https://developer.hashicorp.com/terraform/language/backend/s3).

No guardar claves en Terraform, `-backend-config`, variables versionadas ni comandos. No configurar perfiles laborales ni usar `aws configure` sin `--profile observability-integrator`. No sobrescribir archivos completos de configuración AWS ni definir credenciales globales para este laboratorio.

Con un perfil autenticado y con permisos de lectura, comprobar identidad sin imprimirla y consultar plan/créditos:

```powershell
aws sts get-caller-identity --profile observability-integrator --region us-east-2 --query 'Account!=`null`' --output json
aws freetier get-account-plan-state --profile observability-integrator --region us-east-2 --query '{type:accountPlanType,status:accountPlanStatus,credits:accountPlanRemainingCredits,expires:accountPlanExpirationDate}' --output json
terraform -chdir=infra/aws plan -input=false
```

La API de Free Tier puede no estar disponible en la versión instalada del CLI o no aplicar al tipo de cuenta; en ese caso revisar Billing/Free Tier y Credits en la consola con permisos individuales. No asumir crédito ni elegibilidad. El resumen de esta preparación se guarda en [summary.json](../../docs/evidence/integrator/aws-preflight/summary.json), sin credenciales ni plan ficticio.

## Publicación posterior de imágenes y arranque

Secuencia de referencia para un despliegue nuevo; las operaciones de publicación y aplicación siempre requieren aprobación. La cuenta actual ya está desplegada: no repetir esta inicialización ni desactivar los servicios existentes.

1. Resolver autenticación, región, cuotas, créditos, presupuesto y custodia del estado. Revisar el plan real; no aplicar este laboratorio sobre un estado del proyecto anterior.
2. Primera aplicación de Terraform con `deploy_services=false`: crea infraestructura y repositorios, pero los tres servicios ECS tienen cero tareas. **RDS y Secrets Manager ya generan cargos**, aunque no haya tareas. Service Connect queda registrado antes de iniciar clientes.
3. Obtener las URLs de los dos repositorios mediante `terraform output -json ecr_urls`. Construir dos imágenes `linux/amd64`: API con `infra/images/api-aws.Dockerfile` y Collector con `infra/images/collector-aws.Dockerfile`.
4. Autenticar Docker con `aws ecr get-login-password --profile observability-integrator --region us-east-2` canalizado directamente a `docker login --password-stdin`; nunca imprimir ni guardar el token. Etiquetar y publicar ambas imágenes con la misma etiqueta de versión inmutable y revisar el escaneo. No reutilizar una etiqueta existente.
5. Revisar un nuevo plan con el `image_tag` publicado y `deploy_services=true`, luego obtener aprobación antes de activar las tres tareas. Empezar después de registrar todos los endpoints de Service Connect evita clientes con descubrimiento incompleto. Ante futuros endpoints nuevos se requiere renovar los clientes.
6. Solo si se aprueba, configurar el `/32` del operador para solicitudes HTTP sintéticas al puerto 8000 de Service A. No enviar credenciales ni información personal por ese HTTP. No hay hostname estable ni TLS de entrada: producción requiere otro diseño de acceso aprobado.
7. Comprobar CRUD, TLS RDS, persistencia, trazas de tres servicios y SQL, logs correlacionados, métricas L7 y métricas OTLP. Los scripts locales no validan automáticamente AWS.

El operador de Terraform necesita permisos de creación sobre los tipos del inventario y `iam:PassRole` limitado a los roles ECS del integrador. La primera utilización de ECS puede requerir `iam:CreateServiceLinkedRole` para su rol de servicio. El publicador de imágenes necesita permisos de push solo en los dos repositorios y `ecr:GetAuthorizationToken`. Camilo debe recibir acceso individual por Identity Center/roles temporales, consultas de logs, métricas y trazas, y permisos acotados para sus alertas y tareas de seguridad; no claves compartidas ni acceso al valor del secreto de BD.

## Corrección de trazas: Collector `traces-v2`

La configuración corregida usa `awsxray` de Contrib 0.139.0 para convertir spans y enviarlos mediante `PutTraceSegments` a Ohio. Conserva el destino regional `XRay`; no necesita habilitar CloudWatch Logs como destino de segmentos. Las pipelines OTLP de métricas y logs y sus extensiones SigV4 no cambian. Los roles de tarea existentes permiten `xray:PutTraceSegments` y `xray:PutTelemetryRecords`. La imagen base y el Dockerfile no requieren cambios.

`collector_image_tag` permite versionar solo el Collector. Su valor predeterminado `null` hereda `image_tag`, conservando el comportamiento anterior; `image_tag=initial` y `collector_image_tag=traces-v2` mantienen la API intacta. `deploy_services` sigue siendo `false` por defecto: omitirlo en un plan posterior puede proponer detener los servicios. Mantener `deploy_services=true` mientras deban permanecer activos.

Secuencia desde Git Bash, en la raíz del repositorio; publicación y despliegue requieren aprobación independiente y **no forman parte de esta preparación**:

```bash
export AWS_REGION=us-east-2
export AWS_DEFAULT_REGION=us-east-2
# Exportar solo credenciales temporales del perfil personal a esta terminal.
# No ejecutar con depuración de shell (set -x) ni imprimir variables de autenticación.
eval "$(aws configure export-credentials --profile observability-integrator --format env)"
unset AWS_PROFILE AWS_DEFAULT_PROFILE
aws sts get-caller-identity --region us-east-2 --query Account --output text
# Detenerse si la cuenta no es 467866783326.

REGISTRY=467866783326.dkr.ecr.us-east-2.amazonaws.com
docker build --platform linux/amd64 -f infra/images/collector-aws.Dockerfile \
  -t "$REGISTRY/observability-integrator/collector:traces-v2" .
docker run --rm --network none -e AWS_REGION=us-east-2 \
  -e AWS_ACCESS_KEY_ID=LOCAL_VALIDATION_ONLY -e AWS_SECRET_ACCESS_KEY=LOCAL_VALIDATION_ONLY \
  -e AWS_EC2_METADATA_DISABLED=true -e AWS_EC2_METADATA_SERVICE_ENDPOINT=http://127.0.0.1:9 \
  -e OTEL_LOG_GROUP=/ecs/observability-integrator/otel -e OTEL_LOG_STREAM=service-a \
  "$REGISTRY/observability-integrator/collector:traces-v2" validate --config=/etc/otelcol/config.yaml

# Usar exclusivamente la configuración temporal Docker del laboratorio,
# sin imprimir su contenido ni alterar el administrador de credenciales global.
# Si requiere renovar autenticación, hacerlo sin mostrar el token y sin helper defectuoso.
docker --config "$HOME/.docker-ecr-lab" push "$REGISTRY/observability-integrator/collector:traces-v2"
aws ecr describe-images --profile observability-integrator --region us-east-2 \
  --repository-name observability-integrator/collector --image-ids imageTag=traces-v2 \
  --query 'imageDetails[].{digest:imageDigest,tags:imageTags}'

terraform -chdir=infra/aws fmt
terraform -chdir=infra/aws validate
terraform -chdir=infra/aws plan -input=false -var=deploy_services=true \
  -var=image_tag=initial -var=collector_image_tag=traces-v2 \
  -out=.terraform/traces-v2-review.tfplan
```

Las credenciales ficticias `LOCAL_VALIDATION_ONLY` solo permiten validar las extensiones SigV4 dentro del contenedor sin red; no autentican contra AWS y nunca deben configurarse en ECS. La redirección local de metadatos evita esperas de autodetección de EC2 durante esa validación; tampoco debe trasladarse a ECS.

No publicar planes binarios ni salidas completas de estado. El plan puede generarse antes de publicar la imagen, pero no comprueba que esa etiqueta exista en ECR. Antes de cualquier aplicación, confirmar imagen y arquitectura `linux/amd64`, escaneo y plan actualizado. Revisar únicamente tres reemplazos de definiciones de tarea y tres actualizaciones de servicios; no aprobar cambios de red, IAM, RDS ni destino regional. ECS debe conservar `desired_count=1` y la API `initial`.

Los servicios actuales usan mínimo saludable 0 % y máximo 100 %: renovar la definición detiene la tarea anterior antes de iniciar la nueva, con interrupción temporal y posibles errores 503 entre dependencias. No hay garantía de cero downtime con una tarea por servicio. No se modifican esos porcentajes en esta corrección. El plan también muestra normalización de listas vacías y omisión de `hostPort`, cuyo valor predeterminado en `awsvpc` es el puerto del contenedor; no cambia los puertos efectivos.

Después de un despliegue aprobado: esperar los tres servicios estables y aplicaciones saludables; confirmar digest del Collector y ausencia de errores 400 o `AccessDenied`. Generar tráfico sintético mediante un acceso privado autorizado, sin abrir Security Groups, y consultar X-Ray para comprobar A → B → data-service → PostgreSQL, un mismo trace ID y relaciones padre-hijo. Verificar además métricas de los tres servicios en CloudWatch y logs correlacionados en `/ecs/observability-integrator/otel`. Los spans ya descartados no se recuperan. Guardar evidencias nuevas sin datos sensibles en `docs/evidence/integrator/`.

## Prueba sintética privada

La [guía de prueba temporal](SYNTHETIC_TEST.md) prepara una tarea de una sola solicitud sin acceso HTTP público. `enable_synthetic_test=false` por defecto no crea recursos; habilitarlo requiere revisar cinco altas y aprobar su aplicación por separado. Mantener explícitamente `deploy_services=true`, `image_tag=initial` y `collector_image_tag=traces-v2` tanto al preparar como al retirar la prueba.

## Costos y retirada

El inventario estático prevé 55 recursos Terraform con la API cerrada; 56 si se configura el `/32`. No es un plan contra AWS. Incluye un RDS Single-AZ `db.t4g.micro`, 20 GiB gp3, dos repositorios, seis roles, siete políticas inline, tres servicios y tres definiciones de tarea. RDS administra además un secreto y ECS crea objetos de descubrimiento/roles vinculados al servicio que no son recursos independientes en ese conteo.

Los cargos potenciales son Fargate, tres IPv4 cuando corran las tareas, RDS/almacenamiento, secreto administrado, ECR, CloudWatch (ingesta, consultas, métricas, logs y métricas L7), X-Ray y transferencia. No se incluye presupuesto gratuito ni crédito como descuento garantizado. Consultar la calculadora para Ohio y fijar duración aprobada antes del apply; AWS Budgets no es un corte automático del gasto. No se activan servicios de seguridad de pago ni NAT/ALB.

Programar pruebas en una ventana corta, exportar evidencias sin secretos y coordinar la retirada con Camilo. Cero tareas solo detiene el cómputo ECS; no elimina RDS ni almacenamiento. Detener RDS tampoco elimina su almacenamiento y no es una estrategia permanente. La configuración actual de laboratorio tiene backups deshabilitados, sin protección de borrado y sin snapshot final: aprobar esa pérdida de datos antes de aplicar. ECR tiene `force_delete=false`, por lo que habrá que retirar explícitamente las imágenes antes de eliminar sus repositorios. Revisar también secretos, logs retenidos, imágenes, descubrimiento y roles después de una futura eliminación autorizada. No se ejecutó ningún comando de creación o eliminación de recursos.
