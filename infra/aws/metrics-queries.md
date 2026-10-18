# Métricas AWS para Camilo

Preparación, no evidencia de datos AWS. Destino: CloudWatch OpenTelemetry Metrics en Ohio. Las consultas Prometheus del Compose usan nombres traducidos; CloudWatch conserva los nombres OTLP y etiquetas por ámbito. Confirmar los nombres y unidades con una petición real antes de crear alarmas.

El SDK instalado genera `http.server.duration` con unidad milisegundos; atributos `http.status_code` y `http.route`, y recurso `service.name`. Los histogramas permiten obtener cantidad de solicitudes, fracción 5xx y p99 sin introducir trace_id, clientes ni identificadores de crédito como dimensiones. La instrumentación excluye `/health` y `/metrics` de las señales HTTP OTel.

Series iniciales en CloudWatch Query Studio:

```promql
{"http.server.duration", "@resource.service.name"=~"service-a|service-b|data-service"}
```

Solicitudes por segundo (histograma acumulativo):

```promql
sum by ("@resource.service.name") (
  histogram_count(rate({"http.server.duration"}[1m]))
)
```

Fracción de respuestas 5xx por servicio, con cero cuando no existe serie de errores y evitando divisiones por cero:

```promql
(
  sum by ("@resource.service.name") (
    histogram_count(rate({"http.server.duration", "http.status_code"=~"5.."}[1m]))
  )
  or
  0 * sum by ("@resource.service.name") (
    histogram_count(rate({"http.server.duration"}[1m]))
  )
)
/
clamp_min(
  sum by ("@resource.service.name") (
    histogram_count(rate({"http.server.duration"}[1m]))
  ), 0.001
)
```

p99 en segundos:

```promql
histogram_quantile(0.99,
  sum by ("@resource.service.name") (
    rate({"http.server.duration"}[1m])
  )
) / 1000
```

Estas expresiones corresponden a histogramas acumulativos del SDK. Si posteriormente se cambia la temporalidad a delta, revisar las consultas según la documentación; no aplicar `rate` sin comprobar la temporalidad. Son propuestas aún no ejecutadas contra CloudWatch.

Service Connect añade métricas HTTP de solicitudes, respuestas y latencia en `AWS/ECS`, con dimensiones de servicio/descubrimiento. Confirmar ambos saltos por proxy; no confundir estos datos L7 con VPC Flow Logs L3/L4. Los errores HTTP de aplicación y los errores del proxy pueden tener denominadores diferentes.

Logs JSON de runtime: `/ecs/observability-integrator`, filtrando mensajes con `trace_id` y `span_id`. Logs OTLP: `/ecs/observability-integrator/otel`, stream por servicio. Elegir una fuente para contar eventos sin duplicarlos. Buscar la traza en X-Ray por identificador y, si la interfaz lo requiere, convertir el formato W3C a `1-<8 hex>-<24 hex>` sin modificar los bits. Comprobar padres/hijos y spans SQL de data-service después del despliegue.

Antes de alertar: fijar SLO de p99, ventana común, volumen mínimo, tratamiento de ausencia de datos y baseline real. La condición requerida es errores por encima del baseline + 2σ **Y** p99 por encima del SLO. Debe evaluarse sobre el mismo servicio y periodo; no sumar p99 de servicios. Faltan entrenamiento/datos suficientes, reglas y canal de notificaciones. No se crean alarmas ni servicios AIOps en esta etapa.

Referencias: [OTLP endpoints](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-OTLPEndpoint.html), [PromQL e histogramas en CloudWatch](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-PromQL-Querying.html), [métricas ECS y Service Connect](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/available-metrics.html).
