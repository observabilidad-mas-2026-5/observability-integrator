FROM grafana/grafana:11.6.0
COPY infra/images/grafana-datasources.yaml /etc/grafana/provisioning/datasources/lab.yaml
COPY otel/grafana/provisioning/dashboards/lab.yaml /etc/grafana/provisioning/dashboards/lab.yaml
COPY infra/images/dashboard.json /var/lib/grafana/dashboards/credit-lab.json
