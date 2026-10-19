# Experimento 2: intento diagnóstico no válido como inyección del 10 %

Necesitábamos inyectar un 10 % de errores en data-service. Este intento **no validó ese objetivo**: recibimos 54/540 errores finales (10 %), pero el servicio produjo 486/972 fallos internos (50 %).

Los reintentos de Service Connect repitieron el mismo fallo. Las tres trazas seleccionadas contienen nueve spans `chaos.error` cada una; un span representa un paso de la solicitud. No confundimos errores finales con intentos internos.

Detuvimos la declaración de éxito, limpiamos los recursos y corregimos el mecanismo antes de repetir. Conservamos abajo el diagnóstico original.

- [Muestras y percentiles del cliente](summary.json), [trazas](xray-traces.json) y [logs correlacionados](correlated-failure-logs.json).
- [Contador de intentos elegibles](eligible-counter-diagnostic.json) y [contador de errores](error-counter-after-recovery.json).
- [Validación fallida](experiment-error.json): la discrepancia nos impidió declarar el éxito; no la ocultamos.
- [Limitación de despliegue](deployment-limitation.json): el healthcheck dependiente de B provocó su reemplazo automático durante el recambio de data-service.
- [Limpieza comprobada](cleanup.json), [servicios finales](final-services.json): tres aplicaciones saludables, gates retirados, cero recursos temporales y plan sin cambios. Sin escrituras de datos.

Corregimos el mecanismo en una etiqueta independiente `chaos-errors-v2`, seleccionando uno de cada diez intentos físicos, incluidos los reintentos. Conservamos los resultados corregidos en [una ejecución separada](../errors-20261018T153105Z/README.md), sin sobrescribir ni ocultar este intento fallido.
