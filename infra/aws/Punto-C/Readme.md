# Module C — artefactos de código y validación

Artefactos para describir y validar la configuración ya existente. No ejecutar despliegues como parte de esta entrega.

## Recursos referenciados
- Región: `us-east-2`
- VPC: `vpc-051c9d747227ae6ab`
- VPC Flow Log: `fl-0e0e19a230315a65d`
- Log group: `/aws/vpc/observability-integrator/flow-logs`
- Metric filter: `ModuleC-RejectedFlowRecords`
- Métrica: `ObservabilityIntegrator/Security` / `RejectedFlowRecords`
- Alarma: `module-c-vpc-rejected-flows-high`
- Dashboard: `module-c-security-observability`
- SNS existente reutilizado: `observability-module-b-aiops-alerts`

## Uso (solo lectura)
```bash
bash scripts/aws/module-c/validate.sh
LOOKBACK_MINUTES=60 bash scripts/aws/module-c/query-rejected-flows.sh
```
El segundo script imprime un Query ID para consultar los resultados.

## Límites
- Los scripts consultan; no cambian recursos.
- Los JSON documentan la configuración conocida. No ejecutarlos con comandos `put-*` ni aplicar Terraform.
- Security Hub e Inspector no se incluyen como recursos desplegables: el acceso estaba bloqueado por SCP.
- `REJECT` indica tráfico rechazado, no necesariamente un ataque.
- No se reportan métricas de autenticación ni CVE sin fuentes verificadas.

