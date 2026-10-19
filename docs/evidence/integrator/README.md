# Validación local del Módulo A

Necesitábamos comprobar que el tercer servicio no rompiera la API de créditos. En esta etapa validamos Service A → Service B → data-service → PostgreSQL en Docker Compose local.

Obtuvimos los resultados listados abajo: pruebas, operaciones de crédito y señales de los tres servicios. No ejecutamos Terraform ni desplegamos AWS durante esta etapa. Los resultados posteriores están en [AWS](aws/README.md) y [caos](aws/chaos/README.md), con sus propios conteos y fechas.

- [pytest.txt](pytest.txt): 16 pruebas aprobadas, incluidas las 10 existentes y nuevas pruebas de delegación B → data-service y filtrado de spans SQL. Dos advertencias de obsolescencia de Starlette/AnyIO.
- [validation.json](validation.json): 22 comprobaciones aprobadas de CRUD, 404, 422, persistencia tras reiniciar data-service, relaciones entre spans, métricas y logs de los tres servicios.
- [trace.json](trace.json): traza `ff49725ffe1d4584b007b85a492fad59`, con relaciones padre-hijo entre servicios y spans PostgreSQL de data-service. Atributos `db.system.name=postgresql` y `db.operation.name`; sin consultas ni parámetros SQL exportados.
- [logs.json](logs.json) y [correlation-runtime.json](reference/correlation-runtime.json): logs de los tres servicios correlacionados mediante trace_id y span_id; configuración efectiva de navegación Jaeger/Loki y código de la imagen comprobados.
- [targets.json](targets.json) y [metrics.json](metrics.json): targets HTTP y métricas de aplicación de los tres servicios.
- [dashboard-queries.json](dashboard-queries.json): 21 consultas de dashboard y métricas OTLP aprobadas.
- [failure.json](failure.json): 503 verificado con data-service detenido y con Service B detenido; ambas dependencias restauradas.
- [k6-integrator-smoke.json](k6-integrator-smoke.json): dos usuarios, duración configurada de 10 segundos, 54 solicitudes y comprobaciones aprobadas, cero fallos HTTP. Esta prueba corta no demuestra un SLO de producción.

Incidencia de ejecución: PowerShell interpretó inicialmente un mensaje informativo de Docker en stderr como error y detuvo el comando que capturaba pytest. La repetición completó las 16 pruebas; no hubo fallos de pruebas en la ejecución completada.

En esta etapa no ejecutamos el benchmark largo, capturas del navegador ni el bundle de imágenes cloud. RDS, su TLS y Secrets Manager quedaron pendientes entonces; la [etapa AWS](aws/README.md) documenta la conexión posterior.

Siguen sin demostrarse el rechazo de una CA incorrecta y la rotación de credenciales. Conservamos las evidencias anteriores sin cambios.
