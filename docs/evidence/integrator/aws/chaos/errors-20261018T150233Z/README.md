# Experimento 2: intento diagnóstico no válido como inyección del 10 %

Conservamos esta ejecución como diagnóstico, pero **no la presentamos como validación del objetivo del experimento 2**. Recibimos 54 errores entre 540 solicitudes del cliente durante la fase de inyección (10 %), pero los reintentos de Service Connect amplificaron los fallos del mismo trace ID: data-service recibió 972 intentos elegibles y emitió 486 errores (50 %). En las tres trazas fallidas seleccionadas identificamos nueve spans `chaos.error` por traza. No confundimos el porcentaje del cliente con el del servidor.

- [Muestras y percentiles del cliente](summary.json), [trazas](xray-traces.json) y [logs correlacionados](correlated-failure-logs.json).
- [Contador de intentos elegibles](eligible-counter-diagnostic.json) y [contador de errores](error-counter-after-recovery.json).
- [Validación fallida](experiment-error.json): la discrepancia nos impidió declarar el éxito; no la ocultamos.
- [Limitación de despliegue](deployment-limitation.json): el healthcheck dependiente de B provocó su reemplazo automático durante el recambio de data-service.
- [Limpieza comprobada](cleanup.json), [servicios finales](final-services.json): tres aplicaciones saludables, gates retirados, cero recursos temporales y plan sin cambios. Sin escrituras de datos.

Corregimos el mecanismo en una etiqueta independiente `chaos-errors-v2`, seleccionando uno de cada diez intentos físicos, incluidos los reintentos. Conservamos las evidencias de la repetición en otra carpeta, sin sobrescribir esta ejecución.
