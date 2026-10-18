# AWS temporal — Ohio

El 18 de octubre de 2026 desplegamos nuestra infraestructura en Ohio y validamos el recorrido completo con datos sintéticos. Documentamos las ejecuciones en las [evidencias reales](../../docs/evidence/integrator/aws/README.md). Al finalizar los experimentos retiramos los recursos temporales y comprobamos tres servicios saludables, con RDS activo. Estos recursos generan costos; este estado corresponde a la última verificación documentada, no a una consulta AWS nueva.

## Arquitectura

Nuestra arquitectura es Service A → Service B → data-service → RDS. Tras los experimentos conservamos las etiquetas A/B `chaos-latency-v1`, data-service `chaos-errors-v2` y Collector `traces-v2`, con ambos mecanismos de caos desactivados. La sección de pausa/reactivación contiene el mapa completo vigente. Los ejemplos de publicación inicial y corrección del Collector documentan etapas históricas: no los ejecutamos directamente sobre el estado actual sin incorporar esos overrides y revisar un plan nuevo. La omisión del mapa puede proponer reversiones de imágenes; cualquier cambio adicional bloquea la operación.

Tres servicios ECS Fargate separados: Service A → Service B → data-service → RDS PostgreSQL 16. Cada tarea usa 0,5 vCPU y 1 GiB, con aplicación y Collector; ECS añade el proxy de Service Connect. Total con una tarea por servicio: 1,5 vCPU, 3 GiB y tres IPv4 públicas. La aplicación reserva 128 unidades CPU y 256 MiB; el Collector otras 128 y 256 MiB, dejando capacidad para el proxy. Es una hipótesis de laboratorio que requiere medir memoria, CPU y reinicios al desplegar, no un dimensionamiento productivo.

Región fijada por validación a `us-east-2`. Nombres bajo `observability-integrator`. Sin NAT Gateway, ALB, EFS, Private CA ni endpoints privados facturables. Las tareas tienen salida HTTPS a AWS mediante Internet Gateway; B y data-service no aceptan tráfico público. Las llamadas entre tareas usan direcciones privadas y Service Connect. La API no admite entrada pública salvo que se configure un único `allowed_cidr` IPv4 /32.

Las dos subredes de RDS tienen tabla de rutas propia sin ruta a Internet. RDS no tiene IP pública; 5432 solo permite el Security Group de data-service. PostgreSQL exige TLS mediante `rds.force_ssl=1`. La imagen `infra/images/api-aws.Dockerfile` descarga mediante HTTPS la CA oficial de Ohio, comprueba que sea interpretable y la instala en `/etc/rds/us-east-2-bundle.pem`. data-service usa el hostname de RDS y `verify-full`. Validamos la conexión real a RDS mediante las trazas y lecturas persistidas; no hemos comprobado el rechazo de una CA incorrecta.

Service Connect usa descubrimiento HTTP y proxies, con métricas L7 en CloudWatch `AWS/ECS`. No es AWS App Mesh ni acredita cumplimiento literal de ese requisito: App Mesh se retiró el 30 de septiembre de 2026. Acordar esa diferencia con la rúbrica. No se habilita TLS entre proxies: hacerlo posteriormente requiere evaluar Private CA y sus cargos. La conexión a RDS sí verifica TLS.

La aplicación utiliza el usuario administrador de RDS para conservar la creación automática de tablas del laboratorio. Es una concesión temporal, no mínimo privilegio SQL: antes de uso productivo se necesita usuario de aplicación limitado y migraciones separadas. Solo data-service recibe credenciales. Los roles de ejecución de A/B no pueden leer el secreto; el rol de data-service solo puede leer el secreto administrado por RDS. No se lee su valor desde Terraform ni se publica en outputs. La rotación del secreto requiere renovar la tarea para recibir el nuevo valor. Los roles de tarea exportan telemetría; cada aplicación comparte el rol de su Collector porque ECS asigna el rol a toda la tarea.

## Telemetría y contrato compartido

`collector-aws.Dockerfile` incluye la configuración AWS: trazas mediante `awsxray` a X-Ray, métricas a CloudWatch OTel y logs a CloudWatch Logs mediante OTLP HTTP y SigV4. Conservamos la imagen histórica `initial` con el exporter anterior; ya desplegamos y validamos `traces-v2`. Usa credenciales temporales del rol de tarea, nunca claves estáticas. Los grupos `/ecs/observability-integrator` y `/ecs/observability-integrator/otel` tienen retención de tres días; hay un stream OTLP por servicio. Las salidas JSON de aplicación también se capturan con `awslogs`, por lo que algunos eventos aparecen tanto en runtime como en OTLP: consultar una sola fuente para evitar conteos duplicados.

Conservamos Jaeger, Loki, Grafana y Prometheus en Compose local; no desplegamos sus contenedores en AWS. Allí utilizamos X-Ray y CloudWatch para reducir tareas y almacenamiento. Las consultas de Grafana local no se trasladan automáticamente a CloudWatch. En las [consultas de preparación](metrics-queries.md) distinguimos las expresiones HTTP propuestas de los contadores y métricas de proceso comprobados durante el caos. Mantenemos el criterio conjunto de tasa de errores superior a la línea base + 2σ **Y** p99 superior al umbral del SLO, para el mismo servicio y periodo, sin afirmar que las alertas estén implementadas. Esta infraestructura no habilita implícitamente Application Signals, Container Insights, enriquecimiento de métricas AWS, Flow Logs ni Security Hub.

## Validación sin crear recursos

Desde la raíz:

```powershell
terraform -chdir=infra/aws fmt
terraform -chdir=infra/aws init -backend=false
terraform -chdir=infra/aws validate
terraform -chdir=infra/aws fmt -check
```

La configuración heredada se mantiene en formato `.tf.json`; `fmt` no reformatea JSON. La plantilla `.tfvars.example` no es una entrada automática y los valores predeterminados coinciden con ella. Copiarla a un archivo privado ignorado solo si se necesitan ajustes. No introducimos claves, contraseñas o tokens. Nunca publicamos estado o planes binarios.

## Backend S3 compartido y perfil exclusivo

El backend usa el bucket existente `observabilidad-mas-2026-5-tfstate-aws`, key `integrator/terraform.tfstate`, región `us-east-2`, `encrypt=true` y `use_lockfile=true`. No administra ni recrea el bucket. El backend y el proveedor no fijan un perfil: reciben las credenciales temporales exportadas exclusivamente desde `observability-integrator` a la terminal actual; no alteramos `default`. Cada integrante utiliza su propia identidad autorizada, sin compartir credenciales. No combinar `AWS_PROFILE` con credenciales exportadas en estas ejecuciones.

En la revisión del bucket confirmamos los cuatro controles de bloqueo de acceso público activos, versionado `Enabled`, cifrado predeterminado `AES256` y ubicación `us-east-2`. Es una comprobación de configuración del bucket, no una prueba de escritura o de bloqueo concurrente. Mantener el bucket fuera del ciclo de eliminación de la infraestructura del laboratorio.

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

La API de Free Tier puede no estar disponible en la versión instalada del CLI o no aplicar al tipo de cuenta; en ese caso revisamos Billing/Free Tier y Credits con permisos individuales. No asumimos crédito ni elegibilidad. Conservamos el [resumen histórico de preparación](../../docs/evidence/integrator/aws-preflight/summary.json), que registró un fallo de autenticación anterior al despliegue. Ese resultado no describe la sesión ni la infraestructura posteriores; tampoco demuestra créditos disponibles.

## Publicación posterior de imágenes y arranque

Secuencia de referencia para un despliegue nuevo; las operaciones de publicación y aplicación siempre requieren aprobación. La cuenta actual ya está desplegada: no repetir esta inicialización ni desactivar los servicios existentes.

1. Resolvemos autenticación, región, cuotas, créditos, presupuesto y custodia del estado. Revisar el plan real; no aplicar este laboratorio sobre un estado del proyecto anterior.
2. Primera aplicación de Terraform con `deploy_services=false`: crea infraestructura y repositorios, pero los tres servicios ECS tienen cero tareas. **RDS y Secrets Manager ya generan cargos**, aunque no haya tareas. Service Connect queda registrado antes de iniciar clientes.
3. Obtenemos las URLs de los dos repositorios mediante `terraform output -json ecr_urls`. Construir dos imágenes `linux/amd64`: API con `infra/images/api-aws.Dockerfile` y Collector con `infra/images/collector-aws.Dockerfile`.
4. Autenticamos Docker con `aws ecr get-login-password --profile observability-integrator --region us-east-2` canalizado directamente a `docker login --password-stdin`; nunca imprimir ni guardar el token. Etiquetar y publicar ambas imágenes con la misma etiqueta de versión inmutable y revisar el escaneo. No reutilizar una etiqueta existente.
5. Revisamos un nuevo plan con el `image_tag` publicado y `deploy_services=true`, luego obtener aprobación antes de activar las tres tareas. Empezar después de registrar todos los endpoints de Service Connect evita clientes con descubrimiento incompleto. Ante futuros endpoints nuevos se requiere renovar los clientes.
6. Para las pruebas actuales utilizamos la tarea privada temporal, sin abrir entrada pública. Conservamos `allowed_cidr` sin habilitar acceso HTTP externo. Un eventual `/32` del operador sería una alternativa distinta que requeriría revisión de seguridad; no forma parte de las ejecuciones documentadas. Producción requiere un diseño de acceso autenticado y cifrado.
7. Comprobar CRUD, TLS RDS, persistencia, trazas de tres servicios y SQL, logs correlacionados, métricas L7 y métricas OTLP. Los scripts locales no validan automáticamente AWS.

El operador de Terraform necesita permisos de creación sobre los tipos del inventario y `iam:PassRole` limitado a los roles ECS del integrador. La primera utilización de ECS puede requerir `iam:CreateServiceLinkedRole` para su rol de servicio. El publicador de imágenes necesita permisos de push solo en los dos repositorios y `ecr:GetAuthorizationToken`. Cada integrante debe recibir acceso individual por Identity Center/roles temporales, consultas de logs, métricas y trazas, y permisos acotados para sus alertas y tareas de seguridad; no claves compartidas ni acceso al valor del secreto de BD.

## Corrección de trazas: Collector `traces-v2`

La configuración corregida usa `awsxray` de Contrib 0.139.0 para convertir spans y enviarlos mediante `PutTraceSegments` a Ohio. Conserva el destino regional `XRay`; no necesita habilitar CloudWatch Logs como destino de segmentos. Las pipelines OTLP de métricas y logs y sus extensiones SigV4 no cambian. Los roles de tarea existentes permiten `xray:PutTraceSegments` y `xray:PutTelemetryRecords`. La imagen base y el Dockerfile no requieren cambios.

`collector_image_tag` permite versionar solo el Collector. Su valor predeterminado `null` hereda `image_tag`, conservando el comportamiento anterior; `image_tag=initial` y `collector_image_tag=traces-v2` mantienen la API intacta. `deploy_services` sigue siendo `false` por defecto: omitirlo en un plan posterior puede proponer detener los servicios. Mantener `deploy_services=true` mientras deban permanecer activos.

Conservamos la siguiente secuencia de Git Bash como referencia de la corrección ya desplegada. Las operaciones de publicación y despliegue requieren una revisión independiente; no repetimos un push de etiquetas inmutables ni aplicamos sus planes históricos sobre las imágenes actuales.

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

No publicamos planes binarios ni salidas completas de estado. Un plan puede generarse antes de publicar una imagen, pero no comprueba su existencia en ECR: verificamos la etiqueta, arquitectura `linux/amd64` y escaneo por separado. En la corrección histórica del Collector revisamos tres reemplazos de definiciones y tres actualizaciones de servicios, con `desired_count=1` y API `initial`. Ese alcance no es el esperado para un plan actual con las imágenes de caos: conservamos los overrides vigentes y detenemos cualquier cambio de red, IAM, RDS, destino regional o imágenes ajenas.

Los servicios actuales usan mínimo saludable 0 % y máximo 100 %: renovar la definición detiene la tarea anterior antes de iniciar la nueva, con interrupción temporal y posibles errores 503 entre dependencias. No hay garantía de cero downtime con una tarea por servicio. Conservamos esos porcentajes como limitación del despliegue. El plan también muestra normalización de listas vacías y omisión de `hostPort`, cuyo valor predeterminado en `awsvpc` es el puerto del contenedor; no cambia los puertos efectivos.

Después de un despliegue aprobado: esperar los tres servicios estables y aplicaciones saludables; confirmar digest del Collector y ausencia de errores 400 o `AccessDenied`. Generar tráfico sintético mediante un acceso privado autorizado, sin abrir Security Groups, y consultar X-Ray para comprobar A → B → data-service → PostgreSQL, un mismo trace ID y relaciones padre-hijo. Verificar además métricas de los tres servicios en CloudWatch y logs correlacionados en `/ecs/observability-integrator/otel`. Los spans ya descartados no se recuperan. Guardar evidencias nuevas sin datos sensibles en `docs/evidence/integrator/`.

## Publicación y activación posterior del experimento de latencia

El mapa de A/B mostrado en esta sección corresponde al primer experimento, cuando data-service heredaba `initial`. No sustituye el mapa completo vigente de pausa/reactivación. El controlador histórico de latencia rechaza el cambio adicional de data-service; antes de repetir necesitamos adaptar sus overrides. No modificamos ese código en esta revisión documental.

**Procedimiento reproducible; ejecución real completada y limpiada el 18 de octubre.** Las [instrucciones completas](../../docs/CHAOS_EXPERIMENT_1.md) y el [informe AWS](../../docs/evidence/integrator/aws/chaos/chaos-20261018T141822Z/README.md) definen tráfico, resultados, SLO y recuperación. A/B permanecen en `chaos-latency-v1` pero con `chaos_expires_at=0`, sin infraestructura temporal. Cada nueva corrida requiere aprobación; no repetir publicaciones de imágenes ya verificadas. Retiramos las dos guías históricas por describir otra arquitectura. Conservamos sus [siete capturas](../../docs/evidence/integrator/aws/legacy-aws-captures.md) como referencia; utilizamos este README como fuente operativa vigente.

`api_image_tags` permite seleccionar etiquetas por aplicación sin alterar el resto. Por defecto `{}` hereda `image_tag`, y `chaos_expires_at=0` no añade variables de caos. Un deadline positivo añade `CHAOS_ENABLED=true` y `CHAOS_EXPIRES_AT` **solo en A/B**. La aplicación exige además el marcador de cada solicitud y caduca en un máximo de 30 minutos desde el arranque del proceso. No hay inyección por el mero cambio de imagen.

Git Bash, raíz del repositorio, después de aprobación para construir/publicar. Autenticar exclusivamente el perfil personal; para Terraform exportar sus credenciales temporales mediante el procedimiento de esta guía. No activar depuración de shell ni imprimir tokens:

```bash
ACCOUNT=$(aws sts get-caller-identity --profile observability-integrator --region us-east-2 --query Account --output text)
test "$ACCOUNT" = 467866783326 || exit 1
REGISTRY=467866783326.dkr.ecr.us-east-2.amazonaws.com
API_IMAGE="$REGISTRY/observability-integrator/api:chaos-latency-v1"
aws ecr describe-images --profile observability-integrator --region us-east-2 \
  --repository-name observability-integrator/api --image-ids imageTag=chaos-latency-v1
```

Continuar únicamente si la consulta autenticada confirma que la etiqueta no existe (`ImageNotFoundException`). Si ya existe, elegir otra etiqueta nueva y actualizar el mapa del plan; no sobrescribirla. Si falla autenticación/permisos, detenerse, no interpretar ese error como etiqueta disponible. ECR mantiene etiquetas inmutables y `api:initial` se conserva.

```bash
docker build --platform linux/amd64 -f infra/images/api-aws.Dockerfile -t "$API_IMAGE" .
docker image inspect "$API_IMAGE" --format '{{.Os}}/{{.Architecture}}'
# Exigir linux/amd64 antes de publicar.
aws ecr get-login-password --profile observability-integrator --region us-east-2 | \
  docker --config "$HOME/.docker-ecr-lab" login --username AWS --password-stdin "$REGISTRY"
docker --config "$HOME/.docker-ecr-lab" push "$API_IMAGE"
aws ecr describe-images --profile observability-integrator --region us-east-2 \
  --repository-name observability-integrator/api --image-ids imageTag=chaos-latency-v1 \
  --query 'imageDetails[].{digest:imageDigest,tags:imageTags}'
```

Usar exclusivamente el directorio Docker temporal ya preparado sin credential helper defectuoso. Revisar el escaneo de la etiqueta nueva y el digest; no asumir que los hallazgos HIGH conocidos de la imagen anterior se corrigieron. No volver a construir ni publicar el Collector.

Con credenciales temporales personales en la terminal actual, generar el plan justo antes de la ventana de prueba:

```bash
EXPIRES=$(python -c 'import time; print(int(time.time()) + 20*60)')
terraform -chdir=infra/aws plan -input=false \
  -var=deploy_services=true -var=image_tag=initial -var=collector_image_tag=traces-v2 \
  '-var=api_image_tags={"service-a":"chaos-latency-v1","service-b":"chaos-latency-v1"}' \
  -var="chaos_expires_at=$EXPIRES" -var=enable_synthetic_test=false \
  -out=.terraform/chaos-latency-reviewed.tfplan
```

Desde la base actual, el plan esperado es **2 to add, 2 to change, 2 to destroy**: nuevas revisiones de definiciones A/B y actualización de sus dos servicios. El contenido debe limitarse a imagen de A/B y dos variables de caos; Collector `traces-v2`, data-service `initial`, desired_count=1, RDS, SG, IAM y backend quedan intactos. Las normalizaciones equivalentes de JSON del proveedor deben distinguirse de cambios efectivos. Si aparece cualquier otra diferencia, detenerse. El plan no demuestra que la imagen exista ni que la inyección funcione. No reutilizar un plan cuyo deadline haya vencido. Aplicar únicamente tras aprobación independiente; los porcentajes de despliegue actuales implican interrupción breve al renovar A/B.

Después de HEALTHY, preparar los cinco recursos sintéticos con otro plan, conservando **el mismo mapa, etiquetas y deadline**, cambiando solo `enable_synthetic_test=true`; exigir cinco altas sin otras diferencias. Ejecutar el generador privado durante 9 minutos como indica la guía del experimento, comprobar spans/logs de inyección y guardar evidencias antes de retirar su stream. Retirar los recursos con el mismo mapa y `enable_synthetic_test=false`, exigiendo únicamente cinco eliminaciones.

La recuperación inmediata es dejar de enviar el header; después desarmar permanentemente con `chaos_expires_at=0`, conservando el mapa y todas las etiquetas, en un plan revisado que solo retire las variables de A/B. Para volver a `initial`, limpiar además `api_image_tags={}` mediante otra revisión aprobada. No dejar que un comando de pausa/reactivación omita esos overrides mientras se usen: podría provocar una reversión de imágenes inesperada.

Validación local reproducible: `terraform -chdir=infra/aws fmt -check -recursive`, `terraform -chdir=infra/aws validate` y `terraform -chdir=infra/aws test`. Las cinco pruebas de `tests/chaos.tftest.hcl` usan [proveedor simulado](https://developer.hashicorp.com/terraform/language/tests/mocking) y `command=plan`: no usan el estado compartido ni realizan llamadas AWS, apply o destroy reales. Comprueban valores por defecto idénticos, cambios limitados a A/B, desarme, rechazo de `latest` y aislamiento del gate de errores en data-service. No reemplazan el plan contra la cuenta real.

### Experimento 2: errores en data-service

Consultamos el [procedimiento y aislamiento](../../docs/CHAOS_EXPERIMENT_2.md). `data_error_expires_at=0` desactiva el mecanismo; un valor futuro exige el UUID sintético `data_error_application_id` y habilita solo data-service. El cliente marca únicamente la fase de inyección. `chaos-errors-v2` cuenta intentos físicos, incluidos los reintentos de Service Connect: pueden existir errores 503 internos con respuesta final 200. No modificamos los gates de A/B ni atribuimos al cliente el porcentaje de errores del servidor.

Las operaciones posteriores deben conservar las etiquetas actuales mediante el mapa completo indicado abajo. Las etiquetas históricas `initial` y `chaos-errors-v1` no se sobrescriben. Renovar data-service puede provocar el reemplazo automático de B por su healthcheck dependiente; esperar siempre a que los tres servicios se estabilicen antes de medir.

## Prueba sintética privada

La [guía de prueba temporal](SYNTHETIC_TEST.md) prepara una tarea de una sola solicitud sin acceso HTTP público. `enable_synthetic_test=false` por defecto no crea recursos; habilitarlo requiere revisar cinco altas y aprobar su aplicación por separado. Mantener explícitamente `deploy_services=true`, `image_tag=initial` y `collector_image_tag=traces-v2` tanto al preparar como al retirar la prueba.

## Pausar y reanudar únicamente los microservicios

La pausa conserva servicios, definiciones de tarea, RDS, datos, ECR, logs, redes, secretos y backend S3. Solo cambia `desired_count` de los tres servicios de 1 a 0. No utilizamos `terraform destroy`. La pausa evita el cómputo Fargate de esas tareas y sus IPv4 al liberarse; RDS, almacenamiento, ECR, Secrets Manager y otros consumos de observabilidad pueden seguir generando cargos. Los logs mantienen su política de retención existente, no se conservan indefinidamente por pausar ECS.

Para reanudar desde Git Bash, en la raíz del repositorio, autenticar exclusivamente el perfil personal y exportar sus credenciales temporales sin imprimirlas ni activar `set -x`:

```bash
eval "$(aws configure export-credentials --profile observability-integrator --format env)"
unset AWS_PROFILE AWS_DEFAULT_PROFILE
export AWS_REGION=us-east-2 AWS_DEFAULT_REGION=us-east-2
ACCOUNT=$(aws sts get-caller-identity --profile observability-integrator --region us-east-2 --query Account --output text)
test "$ACCOUNT" = 467866783326 || exit 1
terraform -chdir=infra/aws plan -input=false \
  -var=deploy_services=true -var=image_tag=initial \
  -var=collector_image_tag=traces-v2 -var=enable_synthetic_test=false \
  '-var=api_image_tags={"service-a":"chaos-latency-v1","service-b":"chaos-latency-v1","data-service":"chaos-errors-v2"}' \
  -var=chaos_expires_at=0 -var=data_error_expires_at=0 \
  -out=.terraform/resume-services-reviewed.tfplan
```

Revisamos que el plan proponga exclusivamente **0 to add, 3 to change, 0 to destroy**, con `desired_count: 0 → 1` para A, B y data-service, manteniendo las mismas imágenes y definiciones. Si hay cualquier otro cambio, detenerse. Solo tras revisar y aprobar ese plan:

```bash
terraform -chdir=infra/aws apply -input=false .terraform/resume-services-reviewed.tfplan
aws ecs wait services-stable --profile observability-integrator --region us-east-2 \
  --cluster observability-integrator --services observability-integrator-service-a \
  observability-integrator-service-b observability-integrator-data-service
```

Confirmamos después una tarea RUNNING por servicio, aplicaciones HEALTHY y telemetría reciente. El arranque no ejecuta la prueba sintética ni abre acceso HTTP público. Cerrar la terminal al terminar para descartar las credenciales temporales. Para volver a pausar, generar otro plan con las mismas variables e imágenes, cambiando únicamente `deploy_services=false`, y exigir exactamente tres cambios `1 → 0` antes de aplicarlo. No publicar los planes binarios.

## Riesgos, costos y retirada

### Riesgos de seguridad conocidos

En la evaluación previa de `api:initial` identificamos tres hallazgos HIGH y una limitación de escaneo del Collector. Conservamos esos riesgos: no interpretamos el escaneo fallido como ausencia de vulnerabilidades, ni consideramos las nuevas etiquetas de caos una remediación de dependencias. Esta revisión no realiza un escaneo nuevo ni añade CVE o versiones sin un informe verificable. El uso temporal de datos sintéticos y el acceso privado reducen exposición, pero no eliminan los hallazgos. Antes de otro uso revisamos los resultados ECR disponibles y el alcance de las correcciones necesarias.

Los reintentos pueden ocultar errores internos al cliente. Además, la política de despliegue y el healthcheck dependiente de B pueden producir una interrupción al renovar data-service. Mantenemos esas limitaciones, el usuario SQL administrador y la falta de TLS entre proxies como aspectos pendientes, sin atribuirles una corrección no implementada.

### Costos y retirada

El inventario estático prevé 55 recursos Terraform con la API cerrada; 56 si se configura el `/32`. No es un plan contra AWS. Incluye un RDS Single-AZ `db.t4g.micro`, 20 GiB gp3, dos repositorios, seis roles, siete políticas inline, tres servicios y tres definiciones de tarea. RDS administra además un secreto y ECS crea objetos de descubrimiento/roles vinculados al servicio que no son recursos independientes en ese conteo.

Los cargos potenciales son Fargate, tres IPv4 cuando corran las tareas, RDS/almacenamiento, secreto administrado, ECR, CloudWatch (ingesta, consultas, métricas, logs y métricas L7), X-Ray y transferencia. No consideramos un presupuesto gratuito ni créditos como descuentos garantizados. Consultar la calculadora para Ohio y fijar duración aprobada antes del apply; AWS Budgets no es un corte automático del gasto. No se activan servicios de seguridad de pago ni NAT/ALB.

Programamos las pruebas en una ventana corta, exportamos evidencias sin secretos y coordinamos la retirada como equipo. Cero tareas solo detiene el cómputo ECS; no elimina RDS ni almacenamiento. Detener RDS tampoco elimina su almacenamiento y no es una estrategia permanente. En nuestro laboratorio los backups están deshabilitados, sin protección de borrado ni snapshot final: una futura eliminación requiere aceptar expresamente la pérdida de datos. ECR tiene `force_delete=false`, por lo que debemos retirar las imágenes antes de eliminar sus repositorios. Tras una retirada autorizada revisamos también secretos, logs retenidos, imágenes, descubrimiento y roles. Los procedimientos de esta guía no ejecutan operaciones por sí solos; documentamos las creaciones y retiradas realizadas en las evidencias AWS.
