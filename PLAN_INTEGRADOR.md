# Plan de trabajo — Laboratorio integrador de observabilidad

**Materia:** Observabilidad en Ambientes Productivos MAS 2026-5\
**Enfoque acordado:** AWS (GCP no se desplegará en esta etapa).\
**Repositorio propuesto:** `observabilidad-mas-2026-5/observability-integrator`\
**Base:** implementación anterior de OpenTelemetry, sin alterar el repositorio ya entregado.

> **Importante:** Los módulos A y C exigen evidencia en ambas nubes para la máxima calificación. Con AWS solamente, dejar explícita esa limitación. Una configuración sin despliegue y sin comprobación no equivale a implementación funcional.

## Fase 0 — Organización y colaboración (primero)

- [x] Crear la organización GitHub `observabilidad-mas-2026-5` (si el nombre está disponible), con plan Free.
- [x] Invitar a Camilo como miembro de la organización; comprobar que dispone de permisos para crear ramas y hacer push al repositorio.
- [x] Crear el repositorio público `observability-integrator` dentro de esa organización.
- [x] Copiar **solo los archivos útiles** del laboratorio anterior (no copiar `.git/`, `.env`, secretos, credenciales, estados de Terraform ni cachés); dejar intacto el repositorio original.
- [ ] Crear `.gitignore` apropiado y revisar que no se publiquen claves AWS, tokens, contraseñas ni archivos `.tfstate`.
- [ ] Publicar la base en `main` con README que explique qué funciona y qué está pendiente.
- [ ] Definir ramas: `feature/arquitectura-data-service` (tú), `feature/aiops-seguridad` (Camilo); integrar mediante Pull Requests.
- [ ] Camilo hace `git clone` del repositorio **principal**, sin fork, crea su rama y confirma que puede hacer push a esa rama.
- [ ] Guardar este checklist en `docs/PLAN_INTEGRADOR.md` y actualizarlo entre los dos.

## Fase 1 — Tu entrega de hoy: base para Camilo (Módulo A)

- [ ] Levantar el proyecto base con Docker Compose y confirmar que Service A, Service B, PostgreSQL, Collector, Jaeger, Prometheus y Grafana siguen funcionando.
- [ ] Definir el contrato de `data-service`: rutas, respuestas, errores de prueba y llamadas desde Service B.
- [ ] Crear `data-service` e incorporarlo a Docker Compose; probar el recorrido Service A → Service B → data-service.
- [ ] Instrumentar `data-service` con trazas, métricas y logs mediante OTel SDK, y spans de BD acordes con las convenciones semánticas de OpenTelemetry.
- [ ] Comprobar en Jaeger las trazas entre los tres servicios y la operación de base de datos; validar logs correlacionados y métricas disponibles.
- [ ] Identificar y documentar métricas concretas para AIOps: tasa de errores, latencia p99, etiquetas por servicio y modo de consultar un `trace_id` fallido.
- [ ] Preparar **mecanismos desactivados por defecto** para introducir 200 ms de latencia en Service B y 10 % de errores en `data-service` (sin ejecutar todavía la prueba final).
- [ ] Documentar endpoints, comandos de arranque, consultas de métricas y pruebas en README o `docs/GUIA_INTEGRADOR.md`.
- [ ] Guardar evidencias locales reales en una carpeta separada (`docs/evidence/integrador/local/`).
- [ ] Publicar tu rama, abrir PR hacia `main`, revisar y fusionar cuando las comprobaciones pasen; avisar a Camilo que la base está lista.

## Fase 2 — Tu continuación: AWS y Chaos (Módulos A y D)

- [ ] Revisar acceso a la cuenta AWS, región elegida, permisos, presupuesto y recursos existentes; no asumir que ECR implica ECS desplegado.
- [ ] Revisar infraestructura IaC y decidir la arquitectura mínima viable en AWS (ECS, red/VPC, RDS PostgreSQL, Collector y destino de telemetría).
- [ ] Verificar costos estimados, configurar avisos de presupuesto y plan de eliminación **antes** de crear recursos facturables.
- [ ] Crear/configurar RDS de prueba y probar conexión segura desde `data-service` (credenciales fuera de Git y acceso de red mínimo).
- [ ] Desplegar los servicios necesarios en AWS y comprobar que `data-service` realmente consulta RDS.
- [ ] Instrumentación cloud: comprobar trazas, métricas y logs reales del recorrido de tres servicios; conservar las evidencias.
- [ ] Evaluar/implementar observabilidad de red L7 / alternativa vigente a App Mesh; explicar las diferencias respecto al service mesh exigido si no se implementa uno real.
- [ ] **Después de que Camilo entregue las alertas:** ejecutar el experimento de +200 ms en Service B.
- [ ] Ejecutar el experimento de 10 % de errores en `data-service`.
- [ ] En cada experimento registrar inicio, primera alerta, MTTD, comportamiento de p99, errores, SLO y consumo del error budget; comprobar si MTTD ≤ 2 min.
- [ ] Restaurar el funcionamiento normal y documentar los resultados, incluidas las limitaciones.
- [ ] Eliminar recursos temporales de AWS tras registrar las evidencias y verificar que no queden recursos facturables sin necesidad.

## Fase 3 — Camilo: AIOps (Módulo B)

- [ ] Clonar `main` actualizado y trabajar en `feature/aiops-seguridad`, sin fork.
- [ ] Revisar métricas reales de error rate y p99 de `data-service` y los otros servicios.
- [ ] Implementar detección de anomalías en AWS con un servicio o mecanismo disponible y explicar su correspondencia con la guía (no asumir que DevOps Guru está disponible).
- [ ] Implementar la correlación `error_rate > baseline + 2σ` **Y** `latency_p99 > SLO_threshold`, con evidencia de ambos términos.
- [ ] Enriquecer o vincular la alerta con el `trace_id` de una petición fallida y comprobar que se puede investigar.
- [ ] Comparar alertas estáticas frente a las nuevas reglas; medir alertas generadas, ruido y reducción con datos, no solo una meta estimada.
- [ ] Entregar reglas/configuraciones reproducibles y evidencias para que tú puedas hacer los experimentos de caos.

## Fase 4 — Camilo: red y seguridad (Módulo C)

- [ ] Habilitar VPC Flow Logs en AWS sobre la red efectivamente usada; verificar registros reales.
- [ ] Crear al menos una detección/alerta de tráfico anómalo basada en datos observados o simulados de forma controlada.
- [ ] Evaluar la habilitación de AWS Security Hub y sus posibles cargos; habilitarlo solo con aprobación y presupuesto claro.
- [ ] Construir dashboard de señales de seguridad: autenticaciones fallidas, tráfico norte-sur/este-oeste y CVEs activos, distinguiendo datos disponibles de paneles aún sin fuente real.
- [ ] Guardar capturas de logs, reglas, alertas y dashboard; registrar lo que no se pudo habilitar.
- [ ] Crear PR de su rama y fusionar después de la revisión.

## Fase 5 — Ambos: madurez y entrega (Módulo E)

- [ ] Identificar los **8 dominios** del Observability Foundation Blueprint tal como figuran en el material de la profesora (no inventarlos).
- [ ] Asignar nivel de madurez 1–5 por dominio y justificarlo con evidencias reales del proyecto.
- [ ] Definir roadmap de mejora de **3 meses**, con tareas, responsables, prioridades y resultados verificables.
- [ ] Organizar el README principal: qué se implementó, cómo ejecutarlo, evidencias locales, evidencias AWS y limitaciones (GCP no ejecutado).
- [ ] Preparar informe y demostración técnica según la guía completa, revisando allí el formato y extensión exactos antes de cerrar la entrega.
- [ ] Verificar links, capturas, reproducibilidad, resultados y que no se afirme como desplegado algo solo configurado.
- [ ] Preparar una demostración de los servicios, las señales y al menos un escenario con alerta; revisar si la rúbrica exige demostración en vivo.
- [ ] Validar que no queden secretos en Git y que los recursos temporales de nube estén apagados/eliminados.

## Criterios y riesgos de la rúbrica

| Módulo | Puntaje máximo | Responsable principal | Riesgo |
|---|---:|---|---|
| A. Arquitectura observable completa | 1,25 | Tú | Máximo exige tres servicios, service mesh y correlación en AWS **y** GCP. |
| B. AIOps y correlación | 1,00 | Camilo | Requiere detección funcional y evidencia cuantitativa, no solo configuración. |
| C. Red y seguridad | 1,00 | Camilo | Máximo exige observabilidad de ambas nubes; solo AWS es alcance parcial. |
| D. Chaos y MTTD | 1,00 | Tú | Dos experimentos, MTTD ≤ 2 min y análisis de SLO/error budget. |
| E. Madurez y presentación | 0,75 | Ambos | Ocho dominios, roadmap verificable y demostración. |

**Orden de integración:** base de tres servicios → métricas y alertas AIOps → experimentos de caos → evidencias cloud y seguridad → evaluación de madurez → entrega.
