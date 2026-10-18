# observability-integrator

Laboratorio integrador basado en `observability-end-to-end_v2`. Conserva Service A, Service B, PostgreSQL y la instrumentación OpenTelemetry, junto con Collector, Jaeger, Prometheus, Grafana, Loki, pruebas Python, k6 y la configuración Terraform para AWS.

La ampliación prevista incluye `data-service`, AIOps, seguridad y experimentos de caos. Estas capacidades están pendientes; el plan se conserva en [PLAN_INTEGRADOR.md](PLAN_INTEGRADOR.md). La configuración Terraform no implica que existan recursos desplegados en AWS.

## Ejecución local

Con Docker y Docker Compose disponibles, ejecutar desde la raíz:

```powershell
docker compose -f compose.otel.yml config --quiet
docker compose -f compose.otel.yml up -d --build
docker compose -f compose.otel.yml ps
```

Los valores predeterminados permiten arrancar sin crear un `.env`. `.env.example` documenta las variables disponibles y contiene únicamente contraseñas de ejemplo para uso local. No publicar credenciales reales.

| Acceso | Puerto anterior | Puerto del integrador |
|---|---:|---:|
| API /docs | 18000 | 28000 |
| Grafana | 13000 | 23000 |
| Jaeger | 16686 | 26686 |
| Prometheus | 19090 | 29090 |
| OTLP gRPC | 14317 | 24317 |
| OTLP HTTP | 14318 | 24318 |

Todos los puertos publicados están limitados a `127.0.0.1`. Por ejemplo, la API está en http://127.0.0.1:28000/docs y Grafana en http://127.0.0.1:23000. Las variables de entorno o un `.env` pueden sobrescribir estos puertos; evitar valores del laboratorio anterior si ambos se ejecutan simultáneamente.

Compose usa el proyecto `observability-integrator` y la imagen de aplicación `observability-integrator-api:local`, compartida por Service A y Service B. Los contenedores, la red y los volúmenes administrados por Compose quedan separados por el nombre del proyecto. Los puertos internos, DNS de servicios y destinos OpenTelemetry se conservan.

Para ejecutar la carga k6 con el laboratorio iniciado:

```powershell
docker compose -f compose.otel.yml run --rm k6
```

Los scripts k6 se conservan en `otel/k6/`; los resultados nuevos se guardan en `docs/evidence/`. No se importaron evidencias históricas.

Para detener el laboratorio conservando sus volúmenes:

```powershell
docker compose -f compose.otel.yml down
```

## Documentación y pendientes

Se conservan las guías [local](docs/GUIA_LOCAL.md), [AWS](docs/IMPLEMENTACION_INICIAL_AWS.md) y [costos y eliminación](docs/NUBES_COSTOS_Y_ELIMINACION.md). Estas guías y algunos scripts de validación conservan referencias a puertos, imágenes y evidencias del laboratorio anterior; deben adaptarse antes de utilizarlos con el integrador. `scripts/validate_infra.ps1` también conserva referencias a GCP, que no se incluyó en este repositorio.

La validación de configuración de Compose no comprueba el funcionamiento de servicios ni un despliegue AWS. La incorporación de `data-service` y las validaciones funcionales del integrador quedan pendientes.
