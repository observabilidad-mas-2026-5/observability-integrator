# AWS temporal — Ohio

Estado: configuración preparada y validada localmente; ningún recurso creado. La existencia de archivos Terraform o imágenes locales no demuestra un despliegue.

## Arquitectura

Tres servicios ECS Fargate separados: Service A → Service B → data-service → RDS PostgreSQL 16. Cada tarea usa 0,5 vCPU y 1 GiB, con aplicación y Collector; ECS añade el proxy de Service Connect. Total con una tarea por servicio: 1,5 vCPU, 3 GiB y tres IPv4 públicas. La aplicación reserva 128 unidades CPU y 256 MiB; el Collector otras 128 y 256 MiB, dejando capacidad para el proxy. Es una hipótesis de laboratorio que requiere medir memoria, CPU y reinicios al desplegar, no un dimensionamiento productivo.

Región fijada por validación a `us-east-2`. Nombres bajo `observability-integrator`. Sin NAT Gateway, ALB, EFS, Private CA ni endpoints privados facturables. Las tareas tienen salida HTTPS a AWS mediante Internet Gateway; B y data-service no aceptan tráfico público. Las llamadas entre tareas usan direcciones privadas y Service Connect. La API no admite entrada pública salvo que se configure un único `allowed_cidr` IPv4 /32.

Las dos subredes de RDS tienen tabla de rutas propia sin ruta a Internet. RDS no tiene IP pública; 5432 solo permite el Security Group de data-service. PostgreSQL exige TLS mediante `rds.force_ssl=1`. La imagen `infra/images/api-aws.Dockerfile` descarga mediante HTTPS la CA oficial de Ohio, comprueba que sea interpretable y la instala en `/etc/rds/us-east-2-bundle.pem`. data-service usa el hostname de RDS y `verify-full`. Esto valida la preparación del cliente; falta comprobar una conexión real y rechazo de una CA incorrecta contra RDS.

Service Connect usa descubrimiento HTTP y proxies, con métricas L7 en CloudWatch `AWS/ECS`. No es AWS App Mesh ni acredita cumplimiento literal de ese requisito: App Mesh se retiró el 30 de septiembre de 2026. Acordar esa diferencia con la rúbrica. No se habilita TLS entre proxies: hacerlo posteriormente requiere evaluar Private CA y sus cargos. La conexión a RDS sí verifica TLS.

La aplicación utiliza el usuario administrador de RDS para conservar la creación automática de tablas del laboratorio. Es una concesión temporal, no mínimo privilegio SQL: antes de uso productivo se necesita usuario de aplicación limitado y migraciones separadas. Solo data-service recibe credenciales. Los roles de ejecución de A/B no pueden leer el secreto; el rol de data-service solo puede leer el secreto administrado por RDS. No se lee su valor desde Terraform ni se publica en outputs. La rotación del secreto requiere renovar la tarea para recibir el nuevo valor. Los roles de tarea exportan telemetría; cada aplicación comparte el rol de su Collector porque ECS asigna el rol a toda la tarea.

## Telemetría y contrato para Camilo

`collector-aws.Dockerfile` incluye la configuración AWS con exportación OTLP HTTP y SigV4: trazas al endpoint de X-Ray, métricas a CloudWatch OTel y logs a CloudWatch Logs. Usa credenciales temporales del rol de tarea, nunca claves estáticas. Los grupos `/ecs/observability-integrator` y `/ecs/observability-integrator/otel` tienen retención de tres días; hay un stream OTLP por servicio. Las salidas JSON de aplicación también se capturan con `awslogs`, por lo que algunos eventos aparecen tanto en runtime como en OTLP: consultar una sola fuente para evitar conteos duplicados.

Jaeger, Loki, Grafana y Prometheus del Compose local se conservan. No se despliegan sus contenedores en AWS: allí los destinos son X-Ray y CloudWatch, reduciendo tareas y almacenamiento. Las consultas de Grafana local no se trasladan automáticamente a CloudWatch. Las [consultas de preparación](metrics-queries.md) identifican solicitudes, errores y p99 por servicio; faltan su ejecución real y las alertas que implementará Camilo. No se habilitan Application Signals, Container Insights, enriquecimiento de métricas AWS, Flow Logs ni Security Hub implícitamente.

## Validación sin crear recursos

Desde la raíz:

```powershell
terraform -chdir=infra/aws fmt
terraform -chdir=infra/aws init -backend=false
terraform -chdir=infra/aws validate
terraform -chdir=infra/aws fmt -check
```

La configuración heredada se mantiene en formato `.tf.json`; `fmt` no reformatea JSON. La plantilla `.tfvars.example` no es una entrada automática y los valores predeterminados coinciden con ella. Copiarla a un archivo privado ignorado solo si se necesitan ajustes. No introducir claves, contraseñas o tokens. No hay backend remoto configurado: antes del primer despliegue compartido, acordar un backend cifrado con bloqueo y acceso individual, o un único operador con custodia del estado local. Nunca publicar estado o planes binarios.

Con un perfil autenticado y con permisos de lectura, comprobar identidad sin imprimirla y consultar plan/créditos:

```powershell
aws sts get-caller-identity --region us-east-2 --query 'Account!=`null`' --output json
aws freetier get-account-plan-state --region us-east-2 --query '{type:accountPlanType,status:accountPlanStatus,credits:accountPlanRemainingCredits,expires:accountPlanExpirationDate}' --output json
terraform -chdir=infra/aws plan -input=false
```

La API de Free Tier puede no estar disponible en la versión instalada del CLI o no aplicar al tipo de cuenta; en ese caso revisar Billing/Free Tier y Credits en la consola con permisos individuales. No asumir crédito ni elegibilidad. El resumen de esta preparación se guarda en [summary.json](../../docs/evidence/integrator/aws-preflight/summary.json), sin credenciales ni plan ficticio.

## Publicación posterior de imágenes y arranque

No se ejecutó ninguna publicación ni apply. Secuencia que requiere aprobación:

1. Resolver autenticación, región, cuotas, créditos, presupuesto y custodia del estado. Revisar el plan real; no aplicar este laboratorio sobre un estado del proyecto anterior.
2. Primera aplicación de Terraform con `deploy_services=false`: crea infraestructura y repositorios, pero los tres servicios ECS tienen cero tareas. **RDS y Secrets Manager ya generan cargos**, aunque no haya tareas. Service Connect queda registrado antes de iniciar clientes.
3. Obtener las URLs de los dos repositorios mediante `terraform output -json ecr_urls`. Construir dos imágenes `linux/amd64`: API con `infra/images/api-aws.Dockerfile` y Collector con `infra/images/collector-aws.Dockerfile`.
4. Autenticar Docker con `aws ecr get-login-password --region us-east-2` canalizado directamente a `docker login --password-stdin`; nunca imprimir ni guardar el token. Etiquetar y publicar ambas imágenes con la misma etiqueta de versión inmutable y revisar el escaneo. No reutilizar una etiqueta existente.
5. Revisar un nuevo plan con el `image_tag` publicado y `deploy_services=true`, luego obtener aprobación antes de activar las tres tareas. Empezar después de registrar todos los endpoints de Service Connect evita clientes con descubrimiento incompleto. Ante futuros endpoints nuevos se requiere renovar los clientes.
6. Solo si se aprueba, configurar el `/32` del operador para solicitudes HTTP sintéticas al puerto 8000 de Service A. No enviar credenciales ni información personal por ese HTTP. No hay hostname estable ni TLS de entrada: producción requiere otro diseño de acceso aprobado.
7. Comprobar CRUD, TLS RDS, persistencia, trazas de tres servicios y SQL, logs correlacionados, métricas L7 y métricas OTLP. Los scripts locales no validan automáticamente AWS.

El operador de Terraform necesita permisos de creación sobre los tipos del inventario y `iam:PassRole` limitado a los roles ECS del integrador. La primera utilización de ECS puede requerir `iam:CreateServiceLinkedRole` para su rol de servicio. El publicador de imágenes necesita permisos de push solo en los dos repositorios y `ecr:GetAuthorizationToken`. Camilo debe recibir acceso individual por Identity Center/roles temporales, consultas de logs, métricas y trazas, y permisos acotados para sus alertas y tareas de seguridad; no claves compartidas ni acceso al valor del secreto de BD.

## Costos y retirada

El inventario estático prevé 55 recursos Terraform con la API cerrada; 56 si se configura el `/32`. No es un plan contra AWS. Incluye un RDS Single-AZ `db.t4g.micro`, 20 GiB gp3, dos repositorios, seis roles, siete políticas inline, tres servicios y tres definiciones de tarea. RDS administra además un secreto y ECS crea objetos de descubrimiento/roles vinculados al servicio que no son recursos independientes en ese conteo.

Los cargos potenciales son Fargate, tres IPv4 cuando corran las tareas, RDS/almacenamiento, secreto administrado, ECR, CloudWatch (ingesta, consultas, métricas, logs y métricas L7), X-Ray y transferencia. No se incluye presupuesto gratuito ni crédito como descuento garantizado. Consultar la calculadora para Ohio y fijar duración aprobada antes del apply; AWS Budgets no es un corte automático del gasto. No se activan servicios de seguridad de pago ni NAT/ALB.

Programar pruebas en una ventana corta, exportar evidencias sin secretos y coordinar la retirada con Camilo. Cero tareas solo detiene el cómputo ECS; no elimina RDS ni almacenamiento. Detener RDS tampoco elimina su almacenamiento y no es una estrategia permanente. La configuración actual de laboratorio tiene backups deshabilitados, sin protección de borrado y sin snapshot final: aprobar esa pérdida de datos antes de aplicar. ECR tiene `force_delete=false`, por lo que habrá que retirar explícitamente las imágenes antes de eliminar sus repositorios. Revisar también secretos, logs retenidos, imágenes, descubrimiento y roles después de una futura eliminación autorizada. No se ejecutó ningún comando de creación o eliminación de recursos.
