FROM nginx:1.28.0-alpine
COPY infra/images/nginx.conf /etc/nginx/conf.d/default.conf
