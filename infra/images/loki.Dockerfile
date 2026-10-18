FROM grafana/loki:3.4.2
COPY infra/images/loki.yaml /etc/loki/lab.yaml
CMD ["-config.file=/etc/loki/lab.yaml"]
