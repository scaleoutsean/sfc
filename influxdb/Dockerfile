FROM debian:bookworm-slim
LABEL maintainer="@scaleoutSean"

# Install dependencies for .deb installation and running versitygw
RUN apt-get update && \
    apt-get install -y wget ca-certificates curl tar netcat-openbsd && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy CA cert to OS trust store and update
# THIS WORKS
# COPY ./ca.crt /usr/local/share/ca-certificates/s3-ca.crt
# RUN update-ca-certificates
# THIS IS EXPERIMENTAL
COPY ./ca.crt /home/influxdb3/certs/ca.crt 
RUN chmod 774 /home/influxdb3/certs/ca.crt

# Create influx user and home directory
RUN useradd -m -d /home/influx -s /bin/bash influx

# Set working directory
WORKDIR /home/influx

# Download and install InfluxDB3 Core
RUN mkdir -p /home/influx/.influxdb && \
    cd /home/influx/.influxdb && \
    curl -sSL 'https://dl.influxdata.com/influxdb/releases/influxdb3-core-3.3.0_linux_amd64.tar.gz' -O && \
    curl -sSL 'https://dl.influxdata.com/influxdb/releases/influxdb3-core-3.3.0_linux_amd64.tar.gz.sha256' -O && \
    sha256sum -c influxdb3-core-3.3.0_linux_amd64.tar.gz.sha256 && \
    tar -xf influxdb3-core-3.3.0_linux_amd64.tar.gz --strip-components=1 -C /home/influx/.influxdb && \
    ls -l /home/influx/.influxdb && \
    rm influxdb3-core-3.3.0_linux_amd64.tar.gz*

# Add InfluxDB to PATH for all users
ENV PATH="$PATH:/home/influx/.influxdb"

COPY influxdb3-entrypoint.sh /home/influx/influxdb3-entrypoint.sh
COPY influxdb3-init-entrypoint.sh /home/influx/influxdb3-init-entrypoint.sh
RUN chmod +x /home/influx/influxdb3-entrypoint.sh && \
    chmod +x /home/influx/influxdb3-init-entrypoint.sh

USER influx

EXPOSE 8181
