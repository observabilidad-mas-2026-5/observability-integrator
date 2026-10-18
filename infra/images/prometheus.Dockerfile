FROM prom/prometheus:v3.2.1
COPY infra/images/prometheus.yaml /etc/prometheus/prometheus.yml
CMD ["--config.file=/etc/prometheus/prometheus.yml", "--web.external-url=/prometheus/", "--web.route-prefix=/"]
