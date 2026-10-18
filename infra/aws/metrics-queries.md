# Métricas AWS y criterio de detección AIOps

Preparamos estas consultas para CloudWatch OpenTelemetry Metrics en Ohio. No las presentamos como consultas HTTP ya validadas ni como alarmas implementadas. En las [evidencias AWS](../../docs/evidence/integrator/aws/chaos/README.md) comprobamos métricas de proceso y contadores de inyección; esa validación no demuestra por sí sola el funcionamiento de los histogramas y expresiones siguientes. Las consultas Prometheus del Compose usan nombres traducidos; CloudWatch conserva los nombres OTLP y etiquetas por ámbito. Antes de crear alarmas, comprobamos nombres, unidades y tipos con datos reales.

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

Estas expresiones corresponden a histogramas acumulativos del SDK. Si posteriormente cambiamos la temporalidad a delta, revisamos las consultas según la documentación; no aplicamos `rate` sin comprobar la temporalidad. Conservamos estas propuestas sin atribuirles una ejecución contra CloudWatch que no esté documentada.

Service Connect añade métricas HTTP de solicitudes, respuestas y latencia en `AWS/ECS`, con dimensiones de servicio/descubrimiento. Confirmar ambos saltos por proxy; no confundir estos datos L7 con VPC Flow Logs L3/L4. Los errores HTTP de aplicación y los errores del proxy pueden tener denominadores diferentes.

Logs JSON de runtime: `/ecs/observability-integrator`, filtrando mensajes con `trace_id` y `span_id`. Logs OTLP: `/ecs/observability-integrator/otel`, stream por servicio. Elegir una fuente para contar eventos sin duplicarlos. Buscar la traza en X-Ray por identificador y, si la interfaz lo requiere, convertir el formato W3C a `1-<8 hex>-<24 hex>` sin modificar los bits. Comprobar padres/hijos y spans SQL de data-service después del despliegue.

## Condición conjunta de AIOps

Definimos la detección como **tasa de errores superior a la línea base + 2σ Y latencia p99 superior al umbral de latencia del SLO**. Ambas condiciones deben cumplirse simultáneamente en el mismo servicio y periodo. Calculamos la línea base y σ a partir de tasas históricas comparables, con la misma unidad y ventana; no comparamos una cantidad absoluta de errores con una tasa. No sumamos percentiles ni combinamos errores de data-service con latencia de A como si fueran una sola señal.

Antes de implementar la regla, necesitamos una línea base suficiente, volumen mínimo, política de ausencia de datos y canal de notificaciones. En las consultas HTTP del servidor consideramos errores las respuestas 5xx; el denominador incluye los intentos atendidos por ese mismo servicio y conjunto de rutas, incluidos sus reintentos. Si medimos el cliente, usamos en cambio sus respuestas finales y el criterio de éxito definido para esa prueba. No sustituimos la condición **Y** por una condición **O** para obtener una alerta. La ausencia de solicitudes no demuestra disponibilidad ni equivale automáticamente a cero errores.

## SLO, presupuesto y alcance de las mediciones

Para los experimentos adoptamos un SLO de trabajo: **99,5 % de GET finales exitosos y con duración ≤1000 ms**. Contamos como mala una solicitud con código distinto de 200 o duración superior a 1000 ms, sin duplicar los fallos. Para N solicitudes, el presupuesto permitido es N × 0,005; el consumo de la ventana es malas / presupuesto permitido × 100 y el burn rate es (malas / N) / 0,005. Con N = 0 no calculamos estas razones. No extrapolamos una muestra de nueve minutos al presupuesto mensual restante.

El p99 es un percentil agregado, no el SLI por solicitud: superar su umbral no equivale matemáticamente a agotar el presupuesto del SLO. Las consultas anteriores expresan p99 en segundos; para compararlas con el umbral de 1000 ms necesitamos la equivalencia de 1 s, sin mezclar unidades.

En el experimento 1 observamos latencia adicional sin errores y sin superar 1000 ms. En el experimento 2 medimos 50/500 intentos internos fallidos en data-service (10 %), pero los reintentos recuperaron las 1350 respuestas finales de las tres fases. El SLO separado del servidor, 99,5 % de intentos elegibles sin error inyectado, tuvo un consumo de ventana de 2000 % y burn rate 20× durante la inyección; el SLO del cliente tuvo consumo cero. No trasladamos esos porcentajes entre denominadores.

No demostramos la activación de la condición conjunta con estos experimentos: los percentiles del cliente quedaron bajo el umbral y no contamos con una validación equivalente de la regla por servicio en CloudWatch. Tampoco demostramos alertas ni notificaciones. Conservamos MTTD de alertamiento como no medido; el tiempo de sondeo de logs solo representa una observación operativa. Una detección individual no constituye un promedio MTTD entre ejecuciones.

Referencias: [OTLP endpoints](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-OTLPEndpoint.html), [PromQL e histogramas en CloudWatch](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-PromQL-Querying.html), [métricas ECS y Service Connect](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/available-metrics.html).
