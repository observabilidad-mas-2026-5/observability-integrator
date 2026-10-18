# Experimento 1: +200 ms en Service B

Ejecutamos y limpiamos este experimento en AWS el **18 de octubre de 2026**. Documentamos las métricas, trazas y limpieza en el [informe real](evidence/integrator/aws/chaos/chaos-20261018T141822Z/README.md). Conservamos las imágenes ya desplegadas, RDS y los tres servicios. Presentamos por separado las validaciones locales anteriores.

## Mecanismo mínimo y límites

Implementamos la inyección de caos en `app/chaos.py`, que añade una espera fija de 200 ms dentro de `credit.data.request` de B, antes de llamar a data-service. Se ejecuta en el handler síncrono/threadpool, no bloquea el event loop y no requiere privilegios, netem, FIS, nuevas credenciales ni permisos IAM. No altera respuestas, validaciones ni timeouts HTTPX existentes. Los healthchecks y `/metrics` quedan fuera.

Exigimos simultáneamente:

- `CHAOS_ENABLED=true` en A y B; por defecto `false`.
- `CHAOS_EXPIRES_AT` como epoch UTC futuro, no más de 1800 segundos después del arranque del proceso. Si falta, es inválido, está vencido o excede ese límite, no se inyecta.
- Header exacto `x-lab-chaos-experiment: service-b-latency-200ms-v1`. Cualquier otro valor se ignora.

A transmite exclusivamente ese marcador validado a B mediante un ContextVar aislado por solicitud; B aplica la espera. No se transmite a data-service. El cliente solo marca la fase de inyección. No hay endpoint administrativo, estado remoto ni activación automática por importar el módulo. La variable de entorno se fija al desplegar, no cambia entre fases. La caducidad es defensa adicional; la recuperación se logra retirando el header, sin reinicios. Este marcador no es autenticación y solo se admite en el laboratorio privado con datos sintéticos.

## Tráfico y duración

`scripts/chaos_latency.py` crea **un** crédito sintético (POST sin marcador y sin reintentos), después consulta únicamente ese identificador mediante GET durante tres fases. No lista registros de otros clientes ni registra cuerpos de respuestas. Cada solicitud genera un traceparent W3C muestreado nuevo.

Configuramos 180 s normales + 180 s de inyección + 180 s de recuperación, con **3 solicitudes/s** como objetivo y un cliente secuencial. Aproximadamente 540 lecturas por fase, 1620 en total, más la creación. Generamos carga moderada y de mejor esfuerzo: registramos el throughput logrado y no lo presentamos como carga abierta constante; puede haber omisión coordinada si aumentan los tiempos. Configuramos timeout de 5 s, sin reintentos ni redirecciones del cliente. No asumimos un p99 estadísticamente representativo con este volumen.

Ejemplo para una aplicación local ya iniciada con las variables de A/B configuradas explícitamente:

```bash
python scripts/chaos_latency.py --base-url http://127.0.0.1:28000 \
  --phase-seconds 180 --rps 3 --environment local \
  --output-dir docs/evidence/integrator/aws/chaos/local-NUEVA-EJECUCION
```

La plantilla `.env.example` permanece desarmada. Compose no recibe automáticamente variables nuevas de `.env`: para una prueba manual futura habría que pasarlas explícitamente solo a A/B mediante un override local aprobado. Las validaciones de esta entrega no reinician Compose ni usan su PostgreSQL.

## Ejecución posterior en AWS: requiere aprobación separada

Conservamos abajo el procedimiento de la primera ejecución, cuando data-service utilizaba `initial`. Tras el experimento 2 mantenemos data-service en `chaos-errors-v2`: antes de repetir adaptamos el mapa completo del controlador y del plan a las etiquetas vigentes de la [guía AWS](../infra/aws/README.md), sin revertir servicios ajenos. El controlador rechaza cualquier cambio fuera del alcance autorizado.

1. A/B ya utilizan la etiqueta API inmutable `chaos-latency-v1` y el Collector permanece `traces-v2`; no repetir la construcción ni publicación para nuevas corridas sin cambios de código. Nunca sobrescribir `initial`.
2. Utilizamos `api_image_tags={"service-a":"chaos-latency-v1","service-b":"chaos-latency-v1"}` y `chaos_expires_at=<epoch UTC futuro>`, manteniendo `image_tag=initial` y `collector_image_tag=traces-v2`. El Terraform preparado cambia solo las aplicaciones A/B; data-service hereda `initial` y los Collectors no cambian. Los valores por defecto (`{}` y `0`) conservan exactamente las definiciones anteriores. Preparar y revisar el plan real siguiendo la [guía AWS vigente](../infra/aws/README.md#publicación-y-activación-posterior-del-experimento-de-latencia); no modificamos recursos ajenos al experimento.
3. Fijamos caducidad UTC con margen para despliegue y 9 minutos de prueba, dentro de los 30 minutos máximos. Esperar HEALTHY antes del baseline; no contar reinicios ni calentamiento como inyección. Confirmar en la fase marcada que la caducidad no venció.
4. Reutilizamos los cinco recursos opcionales de [la prueba privada](../infra/aws/SYNTHETIC_TEST.md): `enable_synthetic_test=true`, A/B/data-service activos, sin ingreso público. La regla TCP 8000 entre grupos basta; la tarea usa la IP privada vigente de A, no el alias de Service Connect. El rol de ejecución existente permite ECR y logs; no hace falta rol de aplicación ni credenciales RDS para el generador.
5. Reutilizamos `api:initial` como cliente Python: enviar el contenido del script como override de comando `python -c`, con los argumentos del ejemplo y `--environment aws --output-dir -`. Este modo emite muestras y resumen a stdout/CloudWatch y funciona con raíz de solo lectura. Si el JSON de overrides excede el límite de ECS (8192 caracteres), comprimir el código con zlib/base64 y usar un bootstrap estándar Python; no incluir secretos. Revisar el override antes de lanzar, no sustituir accidentalmente el comando por el POST único de la definición original.
6. Recuperamos muestras JSONL y `chaos.summary` del stream temporal antes de retirarlo; consultar X-Ray y logs OTLP por los trace IDs de las muestras. Guardar evidencia sanitizada con fechas nuevas bajo `docs/evidence/integrator/aws/chaos/`. Una ejecución sin spans/logs de inyección se clasifica **no inyectada**, aunque el script termine sin errores.

La ejecución real utilizó planes revisados limitados al armado/desarmado de A/B y cinco recursos temporales, con limpieza completa; los detalles están en la evidencia enlazada. Cada repetición requiere aprobación independiente. La tarea y sus IPv4 generan cargos; no se necesitan NAT, ALB ni acceso público. Ventana operativa: **20–30 minutos**, incluyendo despliegue, 9 minutos de tráfico, exportación asíncrona y limpieza; entrenamiento de AIOps queda fuera.

## Medición, SLO y contrato compartido

Identificador fijo: **`service-b-latency-200ms-v1`**. Servicios: `service-a`, `service-b`, `data-service`; ruta normalizada `/credit-applications/{application_id}`. No usamos IDs de crédito, trace IDs ni marcas horarias como dimensiones de métricas. Definimos este contrato común para integrar posteriormente la detección AIOps, sin atribuirle alarmas reales ni una integración ya comprobada.

| Señal | Medida / nombre |
|---|---|
| Latencia cliente | p99 por fase, nearest-rank sobre `duration_ms`, incluye fallos/timeout; anotar volumen y duración real |
| HTTP servidor | `http.server.duration`, milisegundos, `http.route`, `http.status_code`, recurso `service.name`; confirmar esquema real CloudWatch antes de alarmar |
| Inyección | span hijo `chaos.latency`, atributos `chaos.experiment` fijo y `chaos.delay_ms=200` |
| Métricas nuevas | `chaos.injected.requests` (contador), `chaos.injected.delay` (histograma, ms nominales solicitados), scope `credit-lab.chaos`, recurso B |
| Logs | `chaos.latency.started` y `chaos.latency.injected` en B con trace_id/span_id; conservar logs existentes |
| Errores cliente | respuestas distintas de HTTP 200 o fallo de transporte / intentos GET; separado del porcentaje servidor 5xx |

Para una validación de alertamiento por servicio necesitamos comparar p99 de A y B por separado, con ventanas de 60 s y las fases completas, excluyendo healthchecks. No damos esa comparación por realizada con los percentiles end-to-end del cliente. Tampoco sumamos percentiles ni confundimos el histograma nominal de demora con la latencia real. Las consultas propuestas están en [metrics-queries.md](../infra/aws/metrics-queries.md); su validación requiere confirmar nombres, unidades y tipos de histogramas en AWS. En este experimento no modificamos dashboards, alarmas ni recursos de seguridad/AIOps.

SLO de trabajo configurable (no acuerdo productivo): **99,5 % de solicitudes GET exitosas y ≤1000 ms**. Solicitud mala = no 200 **o** duración >1000 ms, sin contar dos veces. Para N intentos: presupuesto permitido `N × (1−0,995)`; consumo de la ventana `malas / permitido × 100`; burn rate `fracción_mala / (1−0,995)`. No redondear el presupuesto hacia arriba ni declararlo presupuesto mensual restante. Para el mensual hacen falta volumen y errores de toda esa ventana. Un p99 por encima de 1 s es una condición de alarma, no una definición equivalente al SLI por solicitud.

**200 ms pueden elevar la latencia sin superar el umbral de 1 s ni aumentar los errores**: un consumo de presupuesto de cero es un resultado válido. Nuestro criterio AIOps exige una tasa de errores superior a la línea base + 2σ **Y** una latencia p99 superior al umbral del SLO, para el mismo servicio y periodo. En este experimento no demostramos la activación de esa condición conjunta ni una alerta real. No reducimos el SLO retroactivamente ni creamos fallos artificiales para obtener MTTD. Detallamos unidades, denominadores y limitaciones en el [criterio compartido](../infra/aws/metrics-queries.md#condición-conjunta-de-aiops).

Calculamos el tiempo hasta detección de una ejecución como `timestamp de primera alerta real − inicio confirmado de inyección`, usando UTC del span `chaos.latency` o log `chaos.latency.started` y la marca de evaluación/notificación acordada. Si no observamos una alerta, registramos **no detectado/censurado hasta fin de ventana**, no cero. Para estimar MTTD como promedio necesitamos varias ejecuciones con un criterio de detección consistente. El generador deja `mttd_seconds=null`: no sustituye la medición de una notificación real por una inferencia a partir de p99.

## Recuperación y retirada

La fase recovery deja de enviar el marcador: comprobar ausencia de nuevos spans/logs de inyección y contador sin incremento, errores de vuelta al baseline y p99 próximo al baseline (tolerancia inicial descriptiva `max(20 ms, 20 % del baseline)`; repetir bajo condiciones comparables antes de concluir). El script conserva las métricas por fase pero no declara recuperación por sí solo. Si la prueba termina antes, ninguna otra solicitud sin marcador recibe demora; la caducidad impide nuevas inyecciones después del límite, y no cancela una espera de 200 ms ya iniciada.

Después de guardar evidencia, esperar que termine o detener exclusivamente la tarea generadora, retirar los cinco recursos temporales con el procedimiento Terraform revisado y conservar `deploy_services=true` y el Collector. Retirar `CHAOS_ENABLED`/ponerlo a false y caducidad 0 en A/B en una renovación posterior aprobada, o volver a las imágenes anteriores; revisar antes el plan exacto. No destruimos RDS, los servicios ni recursos del equipo de AIOps y seguridad. El único registro sintético permanece en PostgreSQL; no hay endpoint DELETE y su borrado requiere otra aprobación.
