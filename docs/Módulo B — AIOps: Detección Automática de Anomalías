
cat > docs/MODULE_B_AWS_ALERTING.md <<'EOF'
# Módulo B. Detección de anomalías y enriquecimiento de alertas en AWS

## 1. Objetivo

Implementar una estrategia inicial de observabilidad y alertamiento para
`data-service`, utilizando servicios nativos de AWS para detectar desviaciones,
correlacionar condiciones de alerta y enriquecer las notificaciones con el
contexto disponible en CloudWatch Logs.

La solución busca complementar las alertas basadas en umbrales estáticos con
detección de anomalías y facilitar el diagnóstico mediante los identificadores
de trazabilidad `trace_id` y `span_id`.

## 2. Alcance y arquitectura implementada

La implementación se realizó en AWS, región `us-east-2`, utilizando los
siguientes componentes:

| Componente | Configuración |
|---|---|
| Amazon CloudWatch Logs | Consulta de registros de la aplicación |
| Métrica personalizada | `DataServiceErrorEvents` |
| Namespace | `Observability/ModuleB` |
| Alarma de latencia | `module-b-data-service-p99-over-slo` |
| Alarma de anomalías | `module-b-data-service-error-anomaly` |
| Alarma compuesta | `module-b-data-service-correlated-alert` |
| Amazon SNS | `observability-module-b-aiops-alerts` |
| AWS Lambda | `module-b-alert-enrichment` |
| Amazon EventBridge | `module-b-correlated-alert-rule` |

La alarma compuesta utiliza una condición AND entre la alarma de anomalías y la
alarma de latencia p99. Cuando ambas se encuentran en estado `ALARM`, la regla
de EventBridge permite activar la Lambda de enriquecimiento.

La Lambda consulta los registros de CloudWatch Logs dentro de una ventana de
cinco minutos y publica una notificación en SNS. El mensaje incluye el estado
de la alarma, la hora del evento, el resultado de la consulta y el contexto
disponible. Si no encuentra una traza coincidente, informa esta condición.

## 3. Configuración de métricas y alarmas

### 3.1. Métrica de eventos de error

Se creó el filtro de métricas `module-b-data-service-errors` sobre el grupo
de logs `/ecs/observability-integrator/otel`.

La métrica resultante es `DataServiceErrorEvents`, en el namespace
`Observability/ModuleB`, con valor de métrica igual a 1 por cada evento
coincidente con el patrón configurado.

Esta métrica representa un conteo de eventos identificados por el filtro.
No equivale a una tasa de errores, una proporción de solicitudes fallidas
ni una medición de solicitudes únicas.

### 3.2. Alarma de latencia p99

Se configuró la alarma `module-b-data-service-p99-over-slo` utilizando
la métrica `TargetResponseTime` de `AWS/ECS`, con estadístico extendido p99
y dimensión `TargetDiscoveryName=data-service`.

La alarma utiliza un periodo de 60 segundos, dos periodos consecutivos para
evaluar el umbral y un límite de 1.000 ms. El estado observado durante las
validaciones fue `OK`.

El objetivo de latencia establecido para este ejercicio es p99 inferior o
igual a 1.000 ms.

### 3.3. Detección de anomalías

Se creó la alarma `module-b-data-service-error-anomaly` utilizando la
expresión `ANOMALY_DETECTION_BAND` sobre `DataServiceErrorEvents`, con una
banda de desviación configurada en 2.

La alarma se configuró con un periodo de 300 segundos, dos puntos para
activar la alarma y tres periodos de evaluación.

Durante la revisión, su estado fue `INSUFFICIENT_DATA`. Por tanto, la
configuración existe, pero no se ha demostrado que el modelo disponga de
suficientes datos para establecer una línea base estable ni que detecte
anomalías de forma efectiva.

### 3.4. Correlación mediante alarma compuesta

Se creó la alarma compuesta `module-b-data-service-correlated-alert`, cuya
condición requiere que se encuentren en estado `ALARM` tanto la alarma de
anomalías como la alarma de latencia p99.

Esta configuración representa la lógica de correlación definida para el
ejercicio. No demuestra por sí sola que una anomalía y una degradación de
latencia hayan coincidido durante un incidente operativo real.

## 4. Notificaciones y enriquecimiento

### 4.1. Amazon SNS

Se creó el tópico `observability-module-b-aiops-alerts` y se confirmó la
suscripción por correo electrónico.

Se realizó una publicación de prueba y se confirmó la recepción del correo.
Esta prueba valida el canal de notificación, pero no demuestra por sí sola
la activación automática a partir de una alarma real.

### 4.2. AWS Lambda y Amazon EventBridge

Se creó la función Lambda `module-b-alert-enrichment`, con runtime Python 3.12
y el rol IAM `module-b-alert-enrichment-role`.

La función procesa los eventos de cambio de estado de la alarma compuesta,
consulta CloudWatch Logs y publica el resultado en SNS.

La regla de EventBridge `module-b-correlated-alert-rule` está configurada
para reaccionar cuando la alarma compuesta entra en estado `ALARM`.

Durante la configuración se ajustó la política IAM `ModuleBAlertEnrichmentPolicy`
para permitir las operaciones `logs:StartQuery` y `logs:GetQueryResults` sobre
los grupos de logs necesarios, conservando el permiso de publicación sobre
el tópico SNS. La versión predeterminada de la política quedó en `v2`.

### 4.3. Resultado de la prueba sintética

Se invocó la Lambda con un evento sintético que representaba la entrada en
estado `ALARM` de la alarma compuesta.

La ejecución terminó con código HTTP 200 y devolvió:

```json
{
  "status": "published",
  "trace_id_found": false,
  "query_status": "Complete"
}
```

El resultado confirma que la Lambda pudo ejecutar la consulta y publicar la
notificación. No se encontró una traza coincidente en la ventana consultada.

La prueba fue sintética: no debe interpretarse como evidencia de que una
alarma real activó automáticamente toda la cadena de eventos.

## 5. Revisión de los registros y trazabilidad

Se consultó el grupo `/ecs/observability-integrator` para revisar registros
de `data-service` durante un intervalo de 24 horas.

Las consultas identificaron registros con nivel `ERROR`, evento
`chaos.error.injected` y campos `trace_id` y `span_id`.

Una consulta de diagnóstico encontró 538 registros coincidentes con
`data-service` y `trace_id`. Estos resultados correspondían a eventos de caos.
Al excluir `chaos.error.injected`, la consulta de errores operativos devolvió
cero coincidencias en el intervalo consultado.

Este resultado no demuestra que el servicio nunca haya generado errores
operativos; únicamente indica que no se encontraron registros coincidentes
con los filtros utilizados durante ese intervalo.

Por tanto, existe evidencia de que los registros de los eventos de caos
contienen identificadores de trazabilidad, pero no se ha demostrado el
enriquecimiento de una alerta con una traza asociada a un error operativo real.

## 6. Resultados y limitaciones

### Resultados comprobados

- Se configuraron las alarmas de latencia p99, detección de anomalías y
  correlación compuesta.
- Se confirmó la recepción de una notificación de prueba mediante SNS.
- La Lambda ejecutó una consulta de CloudWatch Logs y publicó una notificación.
- Se corrigieron los permisos IAM necesarios para consultar el grupo principal
  de logs y el grupo OTel.
- Se identificaron registros de eventos de caos con `trace_id` y `span_id`.

### Limitaciones pendientes

- La alarma de anomalías permaneció en `INSUFFICIENT_DATA` durante la revisión.
- No se demostró una activación automática de la cadena completa a partir de
  un incidente operativo real.
- No se encontró una traza de error operativo fuera de los eventos de caos
  en las consultas realizadas.
- No se cuantificó la reducción de alertas ruidosas frente a umbrales estáticos.
- No se midieron el MTTD ni la reducción del tiempo de diagnóstico.
- La métrica de eventos de error no debe interpretarse como una tasa real
  de errores ni como una medición de solicitudes fallidas.

## 7. Conclusión

El Módulo B cuenta con una implementación inicial de alertamiento, detección
de anomalías, correlación mediante una alarma compuesta y enriquecimiento
de notificaciones mediante Lambda y SNS.

Las pruebas realizadas demuestran que el canal de notificación funciona y
que la Lambda puede consultar los registros y publicar una alerta sintética.
Sin embargo, la detección efectiva de anomalías y la correlación de una
alerta con un error operativo real y su `trace_id` no quedaron demostradas.

El resultado se considera un avance de implementación con limitaciones
documentadas. No se afirma que la reducción de ruido, la detección de
anomalías en producción ni la correlación operativa real estén validadas.

## 8. Evidencias

Las capturas y resultados asociados a este módulo se almacenan en:

`docs/evidence/integrator/aws/module-b/`

Evidencias recomendadas para conservar:

1. `01-cloudwatch-p99-alarm.png`: configuración de la alarma de latencia p99.
2. `02-cloudwatch-anomaly-alarm.png`: configuración y estado de la alarma de anomalías.
3. `03-cloudwatch-composite-alarm.png`: regla de correlación de la alarma compuesta.
4. `04-sns-confirmation.png`: suscripción confirmada o correo de prueba recibido.
5. `05-eventbridge-lambda.png`: configuración de la regla y función de enriquecimiento.
6. `06-lambda-synthetic-test.png`: ejecución sintética y resultado de publicación.
7. `07-cloudwatch-chaos-traces.png`: registros de caos con `trace_id` y `span_id`.
8. `08-operational-errors-query.png`: consulta que excluye eventos de caos y devuelve
   cero coincidencias.

Las imágenes deben corresponder a resultados reales de la implementación.
No se deben crear capturas simuladas ni presentar una prueba sintética como
si fuera un incidente real.
EOF

