# Dockerfile for Grafana container
#
# https://hub.docker.com/r/grafana/grafana/tags
FROM grafana/grafana:8.3.5
ENV GF_SECURITY_DISABLE_GRAVATAR=true
ENV GF_SERVER_PROTOCOL=http
ENV GF_SERVER_HTTP_PORT=3000

ENV GF_INSTALL_PLUGINS="yesoreyeram-boomtable-panel, btplc-trend-box-panel, grafana-clock-panel, farski-blendstat-panel, vonage-status-panel, grafana-piechart-panel"

# For HTTPS, change server protocol to HTTPS and ensure required certs are available
# COPY certs/ /etc/ssl/certs/
# ENV GF_SERVER_CERT_FILE = 
# ENV GF_SERVER_CERT_KEY = 

RUN mkdir -p /var/lib/grafana/dashboards
COPY dashboards /var/lib/grafana/dashboards/
