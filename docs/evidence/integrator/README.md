# Validación local del Módulo A

Alcance: Service A → Service B → data-service → PostgreSQL en Docker Compose local. No se ejecutó Terraform ni se desplegaron recursos AWS.

- [pytest.txt](pytest.txt): 16 pruebas aprobadas, incluidas las 10 existentes y nuevas pruebas de delegación B → data-service y filtrado de spans SQL. Dos advertencias de obsolescencia de Starlette/AnyIO.
- [validation.json](validation.json): 22 comprobaciones aprobadas de CRUD, 404, 422, persistencia tras reiniciar data-service, relaciones entre spans, métricas y logs de los tres servicios.
- [trace.json](trace.json): traza `ff49725ffe1d4584b007b85a492fad59`, con relaciones padre-hijo entre servicios y spans PostgreSQL de data-service. Atributos `db.system.name=postgresql` y `db.operation.name`; sin consultas ni parámetros SQL exportados.
- [logs.json](logs.json) y [correlation-runtime.json](reference/correlation-runtime.json): logs de los tres servicios correlacionados mediante trace_id y span_id; configuración efectiva de navegación Jaeger/Loki y código de la imagen comprobados.
- [targets.json](targets.json) y [metrics.json](metrics.json): targets HTTP y métricas de aplicación de los tres servicios.
- [dashboard-queries.json](dashboard-queries.json): 21 consultas de dashboard y métricas OTLP aprobadas.
- [failure.json](failure.json): 503 verificado con data-service detenido y con Service B detenido; ambas dependencias restauradas.
- [k6-integrator-smoke.json](k6-integrator-smoke.json): dos usuarios, duración configurada de 10 segundos, 54 solicitudes y comprobaciones aprobadas, cero fallos HTTP. Esta prueba corta no demuestra un SLO de producción.

Incidencia de ejecución: PowerShell interpretó inicialmente un mensaje informativo de Docker en stderr como error y detuvo el comando que capturaba pytest. La repetición completó las 16 pruebas; no hubo fallos de pruebas en la ejecución completada.

No se ejecutaron el benchmark largo, capturas del navegador ni el bundle auxiliar de imágenes cloud. La conectividad RDS, TLS contra RDS y Secrets Manager quedan pendientes de una fase AWS. Las evidencias anteriores fuera de esta carpeta se conservan intactas.
