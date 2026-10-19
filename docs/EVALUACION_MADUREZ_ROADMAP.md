# Evaluación de madurez y roadmap de tres meses

## 1. Alcance y estado del borrador

Necesitábamos saber qué capacidades demostramos y qué debemos mejorar. Evaluamos nuestra madurez: cuánto de nuestro trabajo es repetible, medible y sostenible.

Usamos las evidencias AWS del **18 de octubre de 2026**, integradas en `main`. No consultamos de nuevo la cuenta ni ejecutamos pruebas. Separamos **resultados comprobados**, **propuestas** y **pendientes**.

Revisamos el README, la [guía local e histórica](GUIA_LOCAL.md), la [guía AWS](../infra/aws/README.md), los experimentos y el archivo local `PLAN_INTEGRADOR.md`. El plan sigue sin cambios y fuera de Git. Sus casillas no son evidencia: las contrastamos con los resultados posteriores.

Comprobamos **Service A → Service B → data-service → Amazon RDS PostgreSQL** sobre ECS Fargate en `us-east-2`, con OpenTelemetry, X-Ray y CloudWatch. ECS ejecuta contenedores; RDS administra la base de datos. OpenTelemetry envía las señales y las consultamos en X-Ray/CloudWatch.

No implementamos GCP. Service Connect comunica los servicios, pero no lo presentamos como cumplimiento literal de App Mesh. Conservamos esa limitación académica en la guía AWS.

## 2. Fuente de los ocho componentes y escala de evaluación

Usamos los ocho componentes de **Observability Foundation** de `Presentacion_Curso_Observabilidad.pdf_compressed.pdf`, **página 40**, proporcionada por la profesora. Conservamos sus nombres en la matriz. No los confundimos con los cinco componentes de SRE Foundation.

Usamos los nombres de la página 40 que compartimos como equipo. El PDF no está en el repositorio y no lo inspeccionamos directamente en esta actualización; debemos cotejar la cita con el original.

No contamos con una rúbrica de niveles por componente. Las interpretaciones y notas siguientes son nuestra **autoevaluación provisional**, no una escala oficial de la presentación.

### Escala de trabajo propuesta, no escala oficial

Para calificar de manera consistente proponemos los siguientes anclajes. Los ajustaremos si la guía académica establece otros criterios; no los presentamos como definiciones oficiales de Observability Foundation. Evaluamos únicamente el alcance demostrado por nuestro laboratorio, no toda la extensión conceptual de cada componente.

| Nivel | Criterio de evaluación que proponemos |
|---|---|
| 1 | Contamos como máximo con preparación conceptual o trabajo ad hoc; no demostramos una capacidad operativa repetible para el componente. |
| 2 | Contamos con una implementación o medición básica, limitada a ejercicios puntuales y con cobertura incompleta. |
| 3 | Definimos un procedimiento reproducible, lo comprobamos en AWS y conservamos evidencia trazable, aunque persisten brechas operativas. |
| 4 | Gestionamos la capacidad con indicadores continuos, responsables grupales, umbrales y validaciones repetidas durante una ventana acordada. |
| 5 | Optimizamos la capacidad con resultados comparativos sostenidos y mejoras verificadas en varios ciclos. |

Calificamos de 1 a 5 según esta escala. Una nota baja indica alcance demostrado limitado, no ausencia de trabajo.

Usamos **NE — no evaluable** para un resultado que no podemos comprobar, no como cero. No calculamos una nota global: el promedio ocultaría diferencias de cobertura.

## 3. Banco de evidencias comprobadas

### E1

Ejecutamos un POST privado con HTTP 201 y un GET con HTTP 200 del mismo registro sintético; observamos los tres servicios y PostgreSQL en X-Ray.

**Evidencia:** [Informe AWS inicial](evidence/integrator/aws/README.md) y [registro sanitizado](evidence/integrator/aws/2026-10-18-synthetic-trace.json).

**Límite:** No acredita alta disponibilidad, recuperación de backups ni un despliegue GCP.

### E2

Correlacionamos logs de A, B y data-service con trace/span IDs y consultamos métricas de proceso de los tres servicios.

**Evidencia:** [Logs correlacionados](evidence/integrator/aws/chaos/errors-20261018T153105Z/correlated-failure-logs.json) y [métricas CloudWatch](evidence/integrator/aws/chaos/errors-20261018T153105Z/memory-metrics.json).

**Límite:** No demuestra que las consultas HTTP propuestas, dashboards y alarmas estén validados.

### E3

Verificamos en doce trazas seleccionadas las relaciones A → B → data-service → PostgreSQL, incluidos intentos 503 recuperados.

**Evidencia:** [Spans X-Ray](evidence/integrator/aws/chaos/errors-20261018T153105Z/xray-traces.json) y [validación de relaciones](evidence/integrator/aws/chaos/errors-20261018T153105Z/trace-chain-validation.json).

**Límite:** No es una auditoría exhaustiva de todas las trazas ni una medición de pérdida de telemetría.

### E4

Inyectamos 200 ms en B, con 540 GET por fase y cero errores finales. Observamos p99 de 72,00 → 276,58 → 84,18 ms en normal, caos y recuperación.

**Evidencia:** [Informe del experimento 1](evidence/integrator/aws/chaos/chaos-20261018T141822Z/README.md), [resumen](evidence/integrator/aws/chaos/chaos-20261018T141822Z/summary.json) y [contador de inyección](evidence/integrator/aws/chaos/chaos-20261018T141822Z/cloudwatch-injection-counter.json).

**Límite:** La latencia adicional no superó 1000 ms ni demuestra una alerta AIOps o un MTTD.

### E5

En la repetición válida inyectamos 50 errores en 500 intentos elegibles de data-service: 10 %. Obtuvimos 450 respuestas finales 200 por fase porque Service Connect recuperó los fallos.

**Evidencia:** [Informe del experimento 2](evidence/integrator/aws/chaos/errors-20261018T153105Z/README.md), [resumen](evidence/integrator/aws/chaos/errors-20261018T153105Z/summary.json) y [cálculo del servidor](evidence/integrator/aws/chaos/errors-20261018T153105Z/server-error-slo.json).

**Límite:** No equivale a 10 % de errores finales del cliente ni demuestra degradación simultánea de errores y p99.

### E6

Retiramos los recursos temporales y la inyección; comprobamos tres servicios saludables y un plan final sin cambios.

**Evidencia:** [Limpieza](evidence/integrator/aws/chaos/errors-20261018T153105Z/cleanup.json), [servicios finales](evidence/integrator/aws/chaos/errors-20261018T153105Z/final-services.json) y [verificación AWS](evidence/integrator/aws/chaos/errors-20261018T153105Z/final-aws-verification.json).

**Límite:** El estado es el de la fecha del registro; no garantiza disponibilidad continua ni ausencia de costos posteriores.

### E7

Conservamos un intento inválido: los reintentos amplificaron el fallo hasta 486/972 intentos físicos, 50 %, antes de corregir el calendario.

**Evidencia:** [Diagnóstico fallido](evidence/integrator/aws/chaos/errors-20261018T150233Z/README.md) y [discrepancia de validación](evidence/integrator/aws/chaos/errors-20261018T150233Z/experiment-error.json).

**Límite:** No lo contabilizamos como validación exitosa de una inyección del 10 %.

La configuración ayuda a reproducir el trabajo, pero no prueba que un recurso funcione. La guía AWS documenta RDS privado, TLS —conexión cifrada con certificado verificado— y credenciales desde Secrets Manager.

Las lecturas y trazas prueban conexión real. No probamos el rechazo de una CA incorrecta, la rotación del secreto ni todos los permisos.

### E8 · AIOps: configuración y pruebas de componentes

Incorporamos el [informe del módulo B](Modulo-B-AIOps-Deteccion-Automática-de-Anomalías.md) y sus [ocho capturas](evidence/integrator/aws/Punto-b/). Observamos configuración de alarmas de p99, anomalías y condición Y, además de la integración EventBridge/Lambda. El informe registra pruebas de SNS y Lambda.

**Límite:** El contador de eventos no es una tasa de errores. No demostramos línea base + 2σ de esa tasa, detección conjunta real, alerta con trace_id, reducción de ruido ni MTTD. La captura de invocación de Lambda muestra ejecución sintética, no el flujo automático completo. El texto indica `INSUFFICIENT_DATA` y una captura muestra `OK`: necesitamos fechar ambas observaciones, sin interpretar `OK` como detección efectiva.

### E9 · Seguridad: registros y alerta de red

Incorporamos el [informe del módulo C](ModuloC-Network-and-Security%20-Observability.md) y sus [siete capturas](evidence/integrator/aws/Punto-C/). Observamos Flow Logs activos, registros ACCEPT/REJECT, filtro métrico y dashboard. El historial conserva una transición a ALARM y acción SNS exitosa el 18 de octubre de 2026 a las 22:29:38 UTC; el informe registra recepción del correo.

**Límite:** Una alarma por cantidad de rechazos no identifica por sí sola un ataque. Faltan línea base y fuentes verificadas de autenticaciones y CVEs. Inspector y Security Hub están reportados como bloqueados por políticas de organización; no contamos en estas capturas con sus denegaciones. No demostramos GCP ni MTTD de caos.

## 4. Matriz de madurez de los ocho componentes

Un SLO es un objetivo de servicio; p99 resume la latencia que no supera el 99 % de las solicitudes medidas. Al hablar de SRE y DevOps relacionamos fiabilidad, desarrollo y operación. Estas explicaciones ayudan a leer la matriz, pero no sustituyen los criterios del curso.

Relacionamos los ocho componentes de la página 40 con E1–E9. Una evidencia puede servir para varios componentes, pero no la contamos como implementaciones distintas. Las mejoras son propuestas.

| Componente de Observability Foundation | Calificación | Evidencia y resultado | Limitación | Mejora propuesta |
|---|---:|---|---|---|
| Observability | 3/5 | E1, E3 y E6: seguimos los tres servicios hasta RDS, investigamos fallos y comprobamos recuperación y limpieza. | No demostramos operación continua, alta disponibilidad ni más de una nube. | Medir cobertura y pérdida de señales; repetir el procedimiento de investigación. |
| The Three Pillars | 3/5 | E2 y E3: relacionamos métricas, logs y trazas de solicitudes. | Faltan consultas HTTP completas por servicio y navegación desde una alerta. | Comprobar las tres señales en 3/3 servicios, con unidades y conteos claros y un dashboard verificable. |
| OpenTelemetry | 3/5 | E1–E3 y E5: enviamos señales de aplicaciones y SQL a X-Ray/CloudWatch con el Collector corregido. | No cuantificamos pérdida total, sobrecarga ni fallos prolongados de exportación. | Validar atributos, filtrado de datos sensibles y salud del Collector bajo fallos controlados. |
| Time Travel Topology | 2/5 | E3–E5: reconstruimos solicitudes pasadas y comparamos las fases por sus horas UTC. | Una traza histórica no es un mapa versionado de dependencias. No demostramos cambios de topología entre instantes. | Acordar el alcance académico y comparar dos estados de dependencias fechados, unidos a despliegues y trazas. |
| Network and Security Observability | 2/5 | E1, E6 y E9: acceso privado, Flow Logs, dashboard y alarma de rechazos con acción SNS. | Cobertura puntual y reproducción incompleta; sin línea base ni fuentes verificadas de autenticaciones/CVEs. Security Hub e Inspector reportados como bloqueados. Persisten HIGH y límites de escaneo, rotación y prueba de CA. | Conservar configuración reproducible, validar un evento controlado y completar fuentes y permisos autorizados. |
| AIOps | 2/5 | E4, E5 y E8: mediciones, alarmas configuradas y pruebas individuales de notificación y consulta. | El conteo de eventos no es error rate. Faltan línea base y σ validados, detección conjunta real, trace_id en alerta, reducción de ruido y MTTD. | Validar denominador y ventanas, probar los cuatro casos de la condición Y y medir notificación en ejecuciones comparables. |
| DataOps | 1/5 | E1 y E5: guardamos y leemos datos sintéticos. No lo contamos como un proceso DataOps. | Faltan pipelines —flujos automatizados—, calidad de datos automatizada, linaje —registro de su procedencia— y contratos versionados y recuperación probada. PostgreSQL y data-service no bastan. | Crear un flujo sintético con contrato, controles de calidad y registro de ejecución; probar recuperación en un entorno aislado aprobado. |
| SRE, DevOps and Observability | 2/5 | E4–E7: usamos procedimientos IaC revisados, ejecutamos caos, calculamos SLO/presupuesto y comprobamos recuperación. Conservamos el intento fallido. | No demostramos una política sostenida de presupuesto, guardias, alertamiento, MTTD ni backups recuperables. Hay límites de healthchecks y despliegue. | Revisar SLO periódicamente, validar alertas y runbooks —procedimientos de respuesta—, repetir caos y probar liveness/readiness y recuperación de datos. |

No asignamos 4 o 5: no demostramos operación continua ni mejoras sostenidas. Ajustamos AIOps de 1 a 2 por la implementación y las pruebas individuales de E8, no por una correlación validada. Conservamos red/seguridad en 2: E9 amplía su evidencia, pero no cierra la cobertura ni la reproducción. DataOps permanece en 1.

## 5. Interpretación de SLO, burn rate y detección

Adoptamos para los ejercicios un SLO de trabajo de **99,5 % de GET finales exitosos y con duración ≤1000 ms**. Contamos como mala una solicitud con código distinto de 200 o duración superior a 1000 ms, sin contarla dos veces.

Para N > 0 calculamos presupuesto permitido = N × 0,005, consumo de ventana = malas / presupuesto permitido × 100 y burn rate = (malas / N) / 0,005. No redondeamos el presupuesto permitido ni lo presentamos como presupuesto mensual restante.

- En el experimento 1 observamos cero solicitudes malas de 1620 GET: presupuesto permitido 8,1 y consumo cero.
- En el experimento 2 observamos cero solicitudes malas de 1350 GET finales: presupuesto permitido 6,75 y consumo cero.
- Para el servidor durante la inyección del experimento 2 usamos otro SLO de trabajo: 99,5 % de intentos físicos elegibles sin error inyectado. Con 50/500 fallos, el presupuesto permitido fue 2,5, el consumo de esa ventana 2000 % y el burn rate 20×. No usamos ese denominador para evaluar las respuestas finales del cliente.

Para AIOps mantenemos la condición **tasa de errores > línea base + 2σ Y p99 > umbral de latencia del SLO**, en el mismo servicio y periodo. No sumamos percentiles ni combinamos errores internos de data-service con p99 de A como si fueran la misma serie. El p99 agregado no sustituye el SLI por solicitud; en particular, comparamos unidades coherentes, 1000 ms = 1 s.

TTD es el tiempo hasta detectar un fallo en una ejecución. MTTD es el promedio de varias detecciones comparables mediante alertas. No lo calculamos a partir de observaciones manuales de logs.

Los experimentos no demuestran una alerta que cumpla ambos términos. Los percentiles del cliente quedaron bajo el umbral, y todavía necesitamos validar las series HTTP y la regla por servicio. Mantenemos el **MTTD de alertamiento como no medido**.

Los tiempos de comprobación operativa mediante logs no son tiempos de notificación; si no observamos una alerta real, registramos el caso como no detectado hasta el cierre de la ventana, no como cero segundos. Detallamos el contrato en [métricas y criterio AIOps](../infra/aws/metrics-queries.md).

## 6. Roadmap propuesto: tres meses desde su aprobación

Proponemos tres meses de trabajo desde su aprobación. Organizamos las semanas como equipo: **P0** bloquea la evaluación; **P1** valida la operación; **P2** consolida mejoras. Compartimos la responsabilidad entre plataforma, AIOps, seguridad y datos.

Las metas siguientes no son resultados actuales. Antes de desplegar, activar servicios de pago o ejecutar más caos, revisamos costos y alcance y obtenemos aprobación.

Trabajamos en sesiones acotadas, guardamos evidencias y retiramos los recursos temporales. No dejamos el laboratorio encendido todo el trimestre por defecto.

### Mes 1: comprobar fuentes y señales

#### Mes 1, semanas 1–2 · P0

- **Acción conjunta:** Cotejar el esquema de la página 40 con el PDF original; acordar nuestra escala y revisar la correspondencia E1–E9 de los ocho componentes.
- **Resultado esperado:** Consolidar la fuente y los criterios de la autoevaluación sin confundirlos con una escala oficial.
- **Cómo lo comprobaremos:** 8/8 componentes con nombre cotejado, referencia, criterio y nota justificada; cero nombres inferidos y cero criterios atribuidos a la profesora sin fuente.

#### Mes 1, semanas 1–3 · P0

- **Acción conjunta:** Completar la revisión de E8/E9 con exportaciones reproducibles y fechas; resolver diferencias entre capturas y texto y clasificar cada resultado como comprobado, configurado o pendiente.
- **Resultado esperado:** Compartir un inventario verificable, sin asumir que una configuración prueba funcionalidad.
- **Cómo lo comprobaremos:** 100 % de las afirmaciones de esos frentes con enlace a evidencia o marca pendiente, fecha y alcance; cero alertas declaradas solo por existir una regla.

#### Mes 1, semanas 2–4 · P1

- **Acción conjunta:** Validar las consultas HTTP por servicio y su correspondencia con tráfico sintético; acordar unidad, ruta, temporalidad y denominador.
- **Resultado esperado:** Disponer de solicitudes, errores y p99 utilizables para detectar e investigar.
- **Cómo lo comprobaremos:** Cobertura de las tres medidas en 3/3 servicios durante ventanas documentadas; conteos contrastados con el generador y reintentos; diferencias explicadas.

#### Mes 1, semanas 3–4 · P1

- **Acción conjunta:** Revisar el estado de vulnerabilidades y controles de acceso, los ejemplos de overrides y los límites de despliegue.
- **Resultado esperado:** Preparar pruebas repetibles sin revertir imágenes ni ocultar riesgos.
- **Cómo lo comprobaremos:** 100 % de los hallazgos HIGH previamente registrados con estado verificable de corrección o aceptación temporal; limitación de escaneo del Collector explícita; cero cambios ajenos en cada plan aprobado.

### Mes 2: validar detección y seguridad

#### Mes 2, semanas 5–6 · P0

- **Acción conjunta:** Construir una línea base comparable y validar la condición conjunta AIOps con casos separados y combinados.
- **Resultado esperado:** Demostrar la lógica Y, sin bajar el SLO para provocar una alerta.
- **Cómo lo comprobaremos:** Al menos 30 ventanas comparables de 1 min distribuidas en sesiones aprobadas, como punto de partida a revisar por representatividad; cuatro casos documentados: ninguno, solo errores, solo p99 y ambos. Solo el último debe activar la regla conjunta.

#### Mes 2, semanas 6–8 · P1

- **Acción conjunta:** Validar notificación e investigación desde una alerta real; aprobar un escenario adicional que cumpla ambos términos si los anteriores no lo hacen.
- **Resultado esperado:** Medir tiempo hasta detección y correlación con trazas sin sustituirla por sondeo manual.
- **Cómo lo comprobaremos:** Al menos tres ejecuciones comparables con inicio del fallo y recepción de alerta en UTC; meta inicial ≤120 s por ejecución, pendiente de demostrar. Reportamos cada TTD y su promedio solo si corresponde; conservamos también los casos sin detección.

#### Mes 2, semanas 5–8 · P1

- **Acción conjunta:** Partir de Flow Logs, la alarma y el dashboard observados en E9; validar un evento controlado contra una línea base y completar las fuentes de autenticaciones y CVEs. Revisar las restricciones de Inspector/Security Hub con autorización y costos aprobados.
- **Resultado esperado:** Tener señales reales de seguridad y distinguir fuentes disponibles de paneles propuestos.
- **Cómo lo comprobaremos:** Un evento de red controlado con registro y detección correlacionados; cada panel con consulta y fuente verificable o etiqueta pendiente. Security Hub queda NE si no se habilita o no se verifica; no inventamos hallazgos para llenar el dashboard.

### Mes 3: repetir y consolidar

#### Mes 3, semanas 9–10 · P1

- **Acción conjunta:** Repetir los dos experimentos con los overrides vigentes y evaluar por separado los efectos de reintentos, despliegue y recuperación.
- **Resultado esperado:** Fortalecer la reproducibilidad sin borrar el intento fallido inicial.
- **Cómo lo comprobaremos:** Al menos tres repeticiones válidas por mecanismo, incluyendo las existentes solo si son comparables; registro de solicitudes, percentiles, errores internos/finales y limpieza en cada una; cero inyecciones residuales.

#### Mes 3, semanas 9–11 · P1

- **Acción conjunta:** Revisar recuperación de datos, privilegios SQL y dependencia de healthchecks; ejecutar solo mejoras y pruebas aprobadas.
- **Resultado esperado:** Reducir las concesiones del laboratorio sin comprometer RDS ni datos existentes.
- **Cómo lo comprobaremos:** Una prueba de recuperación en un entorno aislado aprobado, con RTO/RPO observados, no supuestos; verificación del usuario SQL limitado y de liveness/readiness si implementamos esos cambios. Sin ejecución, mantenemos los puntos pendientes.

#### Mes 3, semanas 9–11 · P2

- **Acción conjunta:** Preparar un ejercicio acotado de DataOps y otro de reconstrucción de topología temporal, con datos sintéticos y alcance acordado.
- **Resultado esperado:** Obtener evidencia específica para dos componentes que hoy tienen cobertura limitada.
- **Cómo lo comprobaremos:** Un contrato de datos versionado con al menos tres comprobaciones de calidad y registro de ejecución; dos estados de dependencias fechados y una comparación documentada, sin declarar linaje o topología completos si no los implementamos.

#### Mes 3, semanas 11–12 · P2

- **Acción conjunta:** Revaluar los ocho componentes, comparar los resultados con la línea inicial y preparar una demostración reproducible.
- **Resultado esperado:** Entregar un informe sustentado y un cierre operativo claro.
- **Cómo lo comprobaremos:** 8/8 componentes con estado y evidencia; cada cambio de nota justificado; enlaces internos válidos, sin secretos ni planes/estados publicados; cero recursos temporales activos tras la demostración. Documentamos por separado costos persistentes y alcance AWS.

No subimos notas solo porque pasen tres meses. Las cambiamos cuando tenemos evidencia nueva; dejamos pendiente lo que no pudimos ejecutar o validar. Revisamos todos los resultados como equipo. Añadir GCP requiere otro acuerdo de alcance, costos y criterios académicos.

## 7. Información que necesitamos completar como equipo

Para cerrar el informe revisamos juntos los pendientes de AIOps y seguridad:

1. El cotejo del esquema de la página 40 con el PDF original y la confirmación de cualquier rúbrica adicional de madurez y del alcance exigido de nube y service mesh. Los nombres de los ocho componentes ya están identificados; nuestra escala sigue siendo una propuesta del equipo.
2. Las configuraciones reproducibles de las reglas AIOps, consultas ejecutadas, ventanas de línea base, σ y tratamiento de ausencia de datos. Necesitamos evidencia de ambos términos y de los cuatro casos lógicos, no solo un gráfico de latencia.
3. Los registros de evaluación y notificación de alertas, con zona horaria y vínculo a una traza investigable. Sin notificación real mantenemos MTTD como no medido. El objetivo de ≤2 min del Plan es una meta, no un resultado alcanzado.
4. Las exportaciones reproducibles de Flow Logs, dashboard y alerta ya observados; una línea base que permita interpretar los rechazos y las fuentes pendientes de autenticaciones/CVEs. Necesitamos conservar el diagnóstico de permisos de Inspector/Security Hub y evaluar alternativas autorizadas, sin suponer que están habilitados.
5. La revisión de vulnerabilidades con paquete, versión, severidad y corrección disponible cuando exista un informe verificable. Conservamos los HIGH conocidos y la limitación de escaneo; no suponemos que una etiqueta nueva los resuelve.
6. La comparación entre alertas estáticas y detección propuesta, si contamos con ella: misma carga, ventana y definición de ruido. Sin ambos conjuntos de datos no calculamos reducción de alertas ni porcentajes de mejora.
7. El acuerdo de prioridades, sesiones de prueba y presupuesto del trimestre. Revisamos juntos los cambios antes de desplegarlos y conservamos las evidencias de recuperación y limpieza.

Conservamos este documento como **borrador de evaluación y propuesta de mejora**. No es una certificación, una implementación multicloud ni una demostración de AIOps y seguridad completos.
