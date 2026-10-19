# Métricas AWS y criterio de detección AIOps

Necesitábamos medir solicitudes, errores y latencia por servicio para preparar AIOps, la detección automática de anomalías. Conservamos estas consultas para CloudWatch OpenTelemetry Metrics en Ohio.

En las [evidencias AWS](../../docs/evidence/integrator/aws/chaos/README.md) comprobamos métricas de proceso y contadores de inyección. No comprobamos todavía los histogramas HTTP ni todas las expresiones siguientes. Posteriormente documentamos alarmas en el módulo B; no demostramos su detección conjunta ante un incidente real.

Los histogramas agrupan mediciones y permiten estimar percentiles. Prometheus local traduce nombres; CloudWatch conserva nombres OTLP y etiquetas por ámbito. Antes de crear alarmas comprobamos nombres, unidades y tipos reales.

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

## Configuración posterior y brecha de validación

En el [Módulo B](../../docs/Modulo-B-AIOps-Deteccion-Automática-de-Anomalías.md) configuramos `DataServiceErrorEvents`, una alarma de anomalías, otra de p99 y una compuesta con condición Y. Probamos SNS y una invocación sintética de Lambda. No demostramos una alerta automática con la traza de un error operativo real.

`DataServiceErrorEvents` cuenta eventos de logs: no es una tasa de solicitudes fallidas. Necesitamos un denominador de solicitudes del mismo servicio y rutas, sin duplicar fuentes. La banda de anomalías de amplitud 2 no demuestra por sí sola la condición exacta línea base + 2σ de esa tasa.

La configuración documenta p99 de Service Connect en milisegundos, umbral 1000 y periodos de 60 s; la alarma de anomalías usa periodos de 300 s. Antes de declarar cumplimiento debemos comprobar ventanas comparables, el sentido del comparador de anomalías y los casos de prueba. La condición Y entre estados de alarmas no basta para demostrar mediciones simultáneas. Las capturas de configuración tampoco prueban un MTTD ≤120 s.

## Condición conjunta de AIOps

Buscamos detectar una degradación cuando se cumplen **dos condiciones a la vez**:

- La tasa de errores supera la línea base + 2σ. La línea base es el comportamiento habitual; σ, su desviación estándar, indica cuánto varía.
- La latencia p99 supera el umbral del SLO. p99 es el valor que no supera el 99 % de las solicitudes medidas; SLO es nuestro objetivo de servicio.

Aplicamos la condición **Y**, no **O**, al mismo servicio y periodo. Calculamos línea base y σ con tasas históricas comparables, en la misma unidad y ventana. No comparamos cantidades absolutas con tasas ni mezclamos errores de data-service con latencia de A.

Antes de implementar la regla, necesitamos una línea base suficiente, volumen mínimo, política de ausencia de datos y canal de notificaciones. En las consultas HTTP del servidor consideramos errores las respuestas 5xx; el denominador incluye los intentos atendidos por ese mismo servicio y conjunto de rutas, incluidos sus reintentos.

Si medimos el cliente, usamos en cambio sus respuestas finales y el criterio de éxito definido para esa prueba. No sustituimos la condición **Y** por una condición **O** para obtener una alerta. La ausencia de solicitudes no demuestra disponibilidad ni equivale automáticamente a cero errores.

## SLO, presupuesto y alcance de las mediciones

Para los experimentos adoptamos un SLO de trabajo: **99,5 % de GET finales exitosos y con duración ≤1000 ms**. Contamos como mala una solicitud con código distinto de 200 o duración superior a 1000 ms, sin duplicar los fallos.

Para N solicitudes, el presupuesto permitido es N × 0,005; el consumo de la ventana es malas / presupuesto permitido × 100 y el burn rate es (malas / N) / 0,005. Con N = 0 no calculamos estas razones. No extrapolamos una muestra de nueve minutos al presupuesto mensual restante.

El p99 es un percentil agregado, no el SLI por solicitud: superar su umbral no equivale matemáticamente a agotar el presupuesto del SLO. Las consultas anteriores expresan p99 en segundos; para compararlas con el umbral de 1000 ms necesitamos la equivalencia de 1 s, sin mezclar unidades.

En el experimento 1 observamos latencia adicional sin errores y sin superar 1000 ms. En el experimento 2 medimos 50/500 intentos internos fallidos en data-service (10 %), pero los reintentos recuperaron las 1350 respuestas finales de las tres fases.

El SLO separado del servidor, 99,5 % de intentos elegibles sin error inyectado, tuvo un consumo de ventana de 2000 % y burn rate 20× durante la inyección; el SLO del cliente tuvo consumo cero. No trasladamos esos porcentajes entre denominadores.

No demostramos la activación de la condición conjunta con estos experimentos: los percentiles del cliente quedaron bajo el umbral y no contamos con una validación equivalente de la regla por servicio en CloudWatch. Las pruebas posteriores de SNS/Lambda y la alerta de red no acreditan una notificación de esos fallos. Conservamos MTTD de alertamiento como no medido; el tiempo de sondeo de logs solo representa una observación operativa.

Una detección individual no constituye un promedio MTTD entre ejecuciones.

Referencias: [OTLP endpoints](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-OTLPEndpoint.html), [PromQL e histogramas en CloudWatch](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-PromQL-Querying.html), [métricas ECS y Service Connect](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/available-metrics.html).
