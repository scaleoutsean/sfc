FROM debian:bookworm-slim
LABEL maintainer="@scaleoutSean"

# Set default InfluxDB3 version (can be overridden at build time)
ARG INFLUXDB3_BUILD_VERSION=3.3.0
ENV INFLUXDB3_BUILD_VERSION=${INFLUXDB3_BUILD_VERSION}

# Install dependencies for InfluxDB3 and plugin processing
RUN apt-get update && \
    apt-get install -y wget ca-certificates curl tar netcat-openbsd python3 python3-yaml && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy CA cert to container
COPY ./ca.crt /home/influxdb3/certs/ca.crt 
RUN chmod 774 /home/influxdb3/certs/ca.crt

# Create influx user and home directory
RUN useradd -m -d /home/influx -s /bin/bash influx

# Set working directory
WORKDIR /home/influx

# =====================================================
# InfluxDB3 Core Installation
# =====================================================
RUN mkdir -p /home/influx/.influxdb && \
    cd /home/influx/.influxdb && \
    echo "Downloading InfluxDB3 Core ${INFLUXDB3_BUILD_VERSION}..." && \
    curl -sSL "https://dl.influxdata.com/influxdb/releases/influxdb3-core-${INFLUXDB3_BUILD_VERSION}_linux_amd64.tar.gz" -O && \
    curl -sSL "https://dl.influxdata.com/influxdb/releases/influxdb3-core-${INFLUXDB3_BUILD_VERSION}_linux_amd64.tar.gz.sha256" -O && \
    sha256sum -c "influxdb3-core-${INFLUXDB3_BUILD_VERSION}_linux_amd64.tar.gz.sha256" && \
    tar -xf "influxdb3-core-${INFLUXDB3_BUILD_VERSION}_linux_amd64.tar.gz" --strip-components=1 -C /home/influx/.influxdb && \
    ls -l /home/influx/.influxdb && \
    rm "influxdb3-core-${INFLUXDB3_BUILD_VERSION}_linux_amd64.tar.gz"* && \
    echo "InfluxDB3 Core installed successfully"

# Add InfluxDB to PATH for all users
ENV PATH="$PATH:/home/influx/.influxdb"

# =====================================================
# Embedded Plugin Architecture - "Stored Procedures"  
# =====================================================
# Use InfluxDB's bundled Python to create plugin virtual environment
# This makes plugins available as stored procedures within InfluxDB

RUN mkdir -p /tmp/plugins/official /tmp/plugins/sfc && \
    cd /tmp/plugins && \
    echo "Setting up Python virtual environment using InfluxDB's bundled Python..." && \
    /home/influx/.influxdb/python/bin/python3 -m venv .venv && \
    echo "Installing Python dependencies for plugins..." && \
    /tmp/plugins/.venv/bin/pip install requests toml schedule numpy pandas && \
    cd /tmp/plugins/official && \
    echo "Downloading official InfluxDB3 plugins..." && \
    curl -sSL "https://raw.githubusercontent.com/influxdata/influxdb3_plugins/main/influxdata/downsampler/downsampler.py" -o downsampler.py 2>/dev/null || \
    curl -sSL "https://raw.githubusercontent.com/influxdata/downsampler/main/downsampler.py" -o downsampler.py 2>/dev/null || \
    echo "WARNING: Could not download official downsampler plugin" && \
    echo "Official plugins download attempt completed"

# Create plugin manifest for SFC-specific intelligence
RUN echo "# SFC Embedded Plugin Manifest" > /tmp/plugins/PLUGINS.md && \
    echo "## Official InfluxDB3 Plugins (Embedded)" >> /tmp/plugins/PLUGINS.md && \
    echo "- downsampler.py: Intelligent data aggregation with field-type awareness" >> /tmp/plugins/PLUGINS.md && \
    echo "- Custom SFC configurations embedded as stored procedures" >> /tmp/plugins/PLUGINS.md && \
    echo "" >> /tmp/plugins/PLUGINS.md && \
    echo "## Usage as Stored Procedures" >> /tmp/plugins/PLUGINS.md && \
    echo "- No external orchestration required" >> /tmp/plugins/PLUGINS.md && \
    echo "- Plugins execute within InfluxDB processing engine" >> /tmp/plugins/PLUGINS.md && \
    echo "- SFC-specific configurations available via triggers" >> /tmp/plugins/PLUGINS.md && \
    echo "Plugin manifest created"

# Create a simple SFC-specific plugin that enhances the official downsampler
RUN echo '#!/usr/bin/env python3' > /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '"""' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo 'SFC Intelligent Downsampler Plugin' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo 'Embedded stored procedure for SolidFire Collector data management' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo 'Uses InfluxDB3 processing engine for intelligent downsampling' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '"""' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo 'def process_scheduled_call(influxdb3_local, call_time, args):' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '    """Main entry point for scheduled downsampling trigger"""' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '    from datetime import datetime, timedelta' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '    ' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '    # Parse arguments' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '    source_table = args.get("source_measurement", "volume_performance")' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '    target_table = args.get("target_measurement", "volume_performance_5m_auto")' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '    window_period = args.get("window_period", "5m")' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '    older_than = args.get("older_than", "7d")' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '    ' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '    # Build downsampling query' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '    query = f"""' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '    INSERT INTO {target_table}' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '    SELECT' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '        cluster, id, name,' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '        avg(read_latency_usec) as read_latency_usec,' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '        avg(write_latency_usec) as write_latency_usec,' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '        avg(latency_usec) as latency_usec,' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '        sum(read_ops_last_sample) as read_ops_last_sample,' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '        sum(write_ops_last_sample) as write_ops_last_sample,' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '        avg(actual_iops) as actual_iops,' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '        avg(volume_utilization) as volume_utilization,' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '        window_start as time' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '    FROM (SELECT *, date_bin(interval \"{window_period}\", time) as window_start FROM {source_table}' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '          WHERE time < now() - interval \"{older_than}\")' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '    GROUP BY cluster, id, name, window_start' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '    """' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '    ' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '    # Execute the query' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '    try:' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '        result = influxdb3_local.execute_query(query)' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '        return f"SFC downsampling completed: {len(result)} rows processed"' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '    except Exception as e:' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo '        return f"SFC downsampling error: {str(e)}"' >> /tmp/plugins/sfc_intelligent_downsampler.py && \
    chmod +r /tmp/plugins/sfc_intelligent_downsampler.py && \
    echo "SFC intelligent plugin created"

# Display embedded plugin summary
RUN echo "=== SFC InfluxDB3 Embedded Plugin Summary ===" && \
    echo "Plugin directory: /tmp/plugins" && \
    ls -la /tmp/plugins/ && \
    echo "Official plugins:" && \
    ls -la /tmp/plugins/official/ 2>/dev/null || echo "Official plugins directory not found" && \
    echo "SFC plugins:" && \
    ls -la /tmp/plugins/sfc/ 2>/dev/null || echo "SFC plugins directory not found" && \
    echo "Embedded plugin architecture ready"

# Copy downsampling configuration
COPY downsampling-config.yaml /tmp/plugins/downsampling-config.yaml

COPY influxdb3-entrypoint.sh /home/influx/influxdb3-entrypoint.sh
RUN chmod +x /home/influx/influxdb3-entrypoint.sh

USER influx

EXPOSE 8181
