# Implementación inicial de observabilidad en AWS

## 1. Objetivo

Documentar los avances de la implementación inicial de la arquitectura de observabilidad en AWS, incluyendo la preparación de los repositorios de imágenes, la publicación de contenedores, la configuración de CloudWatch Logs y la ejecución de pruebas automatizadas de la aplicación.

Esta fase busca establecer una base para integrar OpenTelemetry con los servicios de monitoreo de AWS y preparar la validación del flujo de telemetría de extremo a extremo.

## 2. Recursos configurados

La implementación se realizó en la región **Ohio (`us-east-2`)**.

| Servicio | Recurso | Estado |
|---|---|---|
| Amazon ECR | `otel-credit-lab/api` | Imagen publicada |
| Amazon ECR | `otel-credit-lab/collector` | Imagen publicada |
| Amazon ECR | `otel-credit-lab/prometheus` | Repositorio creado |
| Amazon ECR | `otel-credit-lab/grafana` | Repositorio creado |
| Amazon ECR | `otel-credit-lab/loki` | Repositorio creado |
| Amazon ECR | `otel-credit-lab/gateway` | Repositorio creado |
| CloudWatch Logs | `/ecs/otel-credit-lab/otel-logs` | Grupo creado |
| CloudWatch Logs | Flujo `otel` | Flujo creado |

<img width="948" height="464" alt="image" src="https://github.com/user-attachments/assets/fd4a877f-4583-49e1-a6b9-c67a74f40cb7" />


Los seis repositorios privados de Amazon ECR permiten organizar las imágenes de los componentes de la arquitectura. Durante esta fase se construyeron y publicaron las imágenes de la API y del colector de OpenTelemetry.

El grupo de CloudWatch Logs se configuró con una retención de siete días. La creación del grupo y del flujo `otel` prepara el destino para los registros, pero no confirma por sí sola que se estén recibiendo eventos.

## 3. Construcción y publicación de imágenes

### 3.1. API

Se construyó la imagen de la aplicación a partir del `Dockerfile` del proyecto. La imagen incluye las dependencias definidas en `requirements.txt`, el código de la aplicación y el comando de inicio mediante Uvicorn en el puerto `8000`.

**Repositorio:**

`otel-credit-lab/api`

**Etiqueta publicada:** `aws`

La publicación se verificó mediante una consulta a Amazon ECR, que confirmó la existencia de la imagen, su etiqueta y su digest SHA-256.

**Evidencia:**  <img width="920" height="371" alt="image" src="https://github.com/user-attachments/assets/2dc46895-973a-4d4c-ae60-d8327bddfd13" />


### 3.2. Colector de OpenTelemetry

Se construyó la imagen del colector utilizando OpenTelemetry Collector Contrib versión `0.139.0`. Se empleó un Dockerfile específico para AWS, que incorpora el archivo `collector-aws.yaml` como configuración de inicio.

La configuración contempla:

- Recepción de telemetría mediante OTLP sobre gRPC en el puerto `4317`.
- Recepción de telemetría mediante OTLP sobre HTTP en el puerto `4318`.
- Limitación del uso de memoria y agrupación de datos mediante procesadores.
- Enriquecimiento de atributos de los recursos.
- Exportación prevista de trazas a AWS X-Ray.
- Exportación prevista de métricas a Amazon CloudWatch.
- Exportación prevista de registros a CloudWatch Logs.
- Uso de autenticación SigV4 para las solicitudes dirigidas a los servicios de AWS.

La imagen se publicó en el repositorio `otel-credit-lab/collector`, con la etiqueta `aws`. La publicación fue confirmada mediante la consulta del digest SHA-256 en ECR.

La configuración fue revisada y su sintaxis YAML fue validada. Sin embargo, la prueba de inicio del colector realizada fuera de ECS no pudo completarse porque el contenedor de prueba no disponía de credenciales de AWS para los autenticadores SigV4. Por tanto, la configuración de exportación todavía requiere una validación funcional en el entorno de ejecución previsto.

**Evidencia:** <img width="941" height="340" alt="image" src="https://github.com/user-attachments/assets/9d72dd93-b67b-405c-b246-0cfff7ee42cf" />


## 4. Preparación de CloudWatch Logs

Se creó el grupo de registros:

<img width="938" height="349" alt="image" src="https://github.com/user-attachments/assets/cad2657d-2bb0-46c5-ab9c-b6631d76eebc" />


Se configuró una retención de siete días y se creó el flujo de registros `otel`.

Estos recursos preparan el destino para los registros exportados por el colector. Durante la validación inicial no se confirmó la recepción de eventos generados por la aplicación.

**Evidencias:**

<img width="934" height="423" alt="image" src="https://github.com/user-attachments/assets/e00e625e-fa98-41d9-b2f3-5ae305d9848e" />
<img width="929" height="411" alt="image" src="https://github.com/user-attachments/assets/32daa704-a5d3-4905-9da3-851cbdc037c6" />



## 5. Pruebas automatizadas de la aplicación

Las pruebas se ejecutaron en CloudShell utilizando `pytest`. Para completar la ejecución fue necesario instalar en el entorno temporal algunas dependencias que no estaban disponibles inicialmente, entre ellas FastAPI, HTTPX, `psutil`, `prometheus-client`, SQLAlchemy y los paquetes de instrumentación y exportación de OpenTelemetry.

El resultado final de la ejecución de las pruebas ubicadas en `tests/` fue:

- **Pruebas aprobadas:** 10.
- **Advertencias:** 1.
- **Tiempo de ejecución:** aproximadamente 0,75 segundos.

La advertencia correspondió a una deprecación relacionada con el uso de HTTPX en `Starlette TestClient`. Esta advertencia no impidió que las diez pruebas seleccionadas finalizaran correctamente.

La ejecución se realizó sobre el código descargado en CloudShell. La instalación temporal de dependencias no implica que se hayan modificado las dependencias del repositorio.

**Evidencia:** <img width="940" height="469" alt="image" src="https://github.com/user-attachments/assets/2033c6c1-ce6e-478e-9d74-d7169e538a5c" />


## 6. Validación de telemetría en AWS

Se consultó CloudWatch Metrics para buscar métricas relacionadas con `credit-lab`. La consulta no mostró métricas personalizadas de la aplicación; únicamente apareció un resultado asociado al uso de AWS.

No se confirmó la recepción de trazas en AWS X-Ray. La frase final de la documentación original estaba incompleta y no permite precisar una causa adicional. Esta comprobación se mantiene como pendiente.

No hay evidencia suficiente de la aplicación ni del Collector funcionando en ECS Fargate. Las imágenes publicadas, los repositorios y el grupo de registros no equivalen a un despliegue validado.

## 7. Material de entrega

- [Informe técnico PDF](INFORME_LAB_OTEL.pdf).
- [Informe editable DOCX](INFORME_LAB_OTEL.docx).
- [Evidencias locales](evidence/README.md).
- [Configuración AWS del Collector, preparada sin validación funcional remota](../infra/images/collector-aws.yaml).

Las siete capturas anteriores conservan exactamente sus enlaces y atributos originales. En este documento reunimos nuestros avances; durante su revisión editorial no ejecutamos recursos ni pruebas en AWS.
