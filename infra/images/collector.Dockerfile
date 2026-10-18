FROM otel/opentelemetry-collector-contrib:0.139.0
COPY infra/images/collector.yaml /etc/otelcol/config.yaml
CMD ["--config=/etc/otelcol/config.yaml"]
