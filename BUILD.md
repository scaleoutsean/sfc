# Docker build args configuration

- [Docker build args configuration](#docker-build-args-configuration)
  - [Environment variables (`.env`)](#environment-variables-env)
    - [Build-time versions (used as `ARG`s in Dockerfiles)](#build-time-versions-used-as-args-in-dockerfiles)
    - [Runtime versions (used in docker-compose services)](#runtime-versions-used-in-docker-compose-services)
  - [How it works](#how-it-works)
    - [1. Dockerfile `ARG`s](#1-dockerfile-args)
    - [2. Docker compose build args](#2-docker-compose-build-args)
    - [3. Additional instances](#3-additional-instances)
  - [Smart down-sampling (v2.1.1)](#smart-down-sampling-v211)
    - [Features](#features)
    - [Configuration](#configuration)
    - [Customization](#customization)
    - [Monitoring](#monitoring)
    - [3. Usage](#3-usage)


This document explains how the SFC project uses environment variables and Docker build arguments for version management.

## Environment variables (`.env`)

The `.env` file contains both runtime and build-time configuration.

Copy `.env.example` to `.env` and edit it. You mostly need to only change the credentials and SolidFire MVIP.

### Build-time versions (used as `ARG`s in Dockerfiles)

- `INFLUXDB3_BUILD_VERSION=3.3.0` - InfluxDB3 Core binary version for download
- `VERSITY_S3GW_VERSION=1.0.14` - Versity S3 Gateway version (leave as is if you don't use S3 tiering)
- `PYTHON_VERSION=3.12.11-alpine3.22` - Python base image version
- `PYTHON_DIGEST=sha256:...` - Python image digest for extra security

### Runtime versions (used in docker-compose services)

- `INFLUXDB3_VERSION=3-core` - InfluxDB3 image tag
- `GRAFANA_VERSION=latest` - Grafana image tag (if set, use 12.2 or newer due to TLS CA bug in previous versions)

## How it works

### 1. Dockerfile `ARG`s

Each Dockerfile declares `ARG` variables with defaults:

```dockerfile
# s3/Dockerfile
ARG VERSITY_S3GW_VERSION=1.0.14

# influxdb/Dockerfile  
ARG INFLUXDB3_BUILD_VERSION=3.3.0

# sfc/Dockerfile
ARG PYTHON_VERSION=3.12.11-alpine3.22
ARG PYTHON_DIGEST=sha256:...
```

### 2. Docker compose build args

The `docker-compose.yaml` passes `.env` variables as build arguments:

```yaml
services:
  s3:
    build:
      args:
        VERSITY_S3GW_VERSION: ${VERSITY_S3GW_VERSION}
        
  influxdb:
    build:
      args:
        INFLUXDB3_BUILD_VERSION: ${INFLUXDB3_BUILD_VERSION}
        
  sfc:
    build:
      args:
        PYTHON_VERSION: ${PYTHON_VERSION}
        PYTHON_DIGEST: ${PYTHON_DIGEST}
```

### 3. Additional instances

Additional instances of SFC Collector that use existing InfluxDB should be deployed manually, as everything else is already in place.

If you need to deploy multiple collectors in Docker Compose or Kubernetes, you may either add additional `sfc` services (e.g. `sfc-PROD`) or stand up stand-alone Docker Compose with only SFC collectors.

Multiple collectors can use own databases on the same InfluxDB servers ('sfc-PROD', 'sfc-DR'), or share the same database (e.g. 'sfc') and use cluster name tags to query own measurements. InfluDB administrator may create one shared user token, or (better) multiple user tokens. Use InfluxDB Explorer or InfluxDB CLI in the `utils` container to do that.

Note that if you don't have InfluxDB administrator key and use user or "named" key, you may need the administrator to create a database for you. SFC tries to create the specified database, but if token permissions aren't sufficient then it will fail to do that.

## Smart down-sampling (v2.1.1)

SFC v2.1.1 includes an embedded smart data lifecycle management system using the official InfluxDB3 down-sampling plugin. This "stored procedures" architecture provides zero-dependency down-sampling with production defaults.

### Features

- Embedded plugin architecture: Official InfluxDB down-sampler embedded during container build
- Production defaults: pre-configured for the critical table, `volume_performance` (adjust parameters if necessary)
- Zero external dependencies: plugin runs locally using InfluxDB's bundled Python environment
- Automatic table creation: target tables (e.g. `volume_performance_5m_auto`) created automatically
- Transparent dashboard integration: reference dashboard provided to handle multiple resolutions seamlessly

### Configuration

Current active configuration (hardcoded in `influxdb3-entrypoint.sh`):

- Three down-sampling schedules for key measurement built-in: `volume_performance` data older than 14 days down-sampled to 5-minute intervals (DS01), >30d->1h (DS02), >60d->1d (DS03)
- Run schedule: Every 10 minutes for DS01, hourly for DS02, and daily for DS03
- Target: `volume_performance` DS01 schedule creates `volume_performance_5m_auto`, DS02 uses that to create `volume_performance_1h_auto`, and DS03 uses DS02's table to create `volume_performance_1d_auto`
- Aggregations: Operations (sum), Latency (avg), Utilization (avg)

### Customization

To modify down-sampling behavior (i.e. change schedules or add down-sampling for other measurements):

1. Edit `influxdb/influxdb3-entrypoint.sh`
2. Find `setup_downsampling_triggers()` function
3. Modify the trigger parameters:
   - Change threshold (and `target_measurement` name for easier orientation)
   - Adjust interval
   - Add additional layers/measurements
4. Rebuild: `docker-compose down && docker-compose up -d --build influxdb`
5. Adjust dashboards by following `dashboard-sql-downsampling.json` (for InfluxDB's SQL query language)

Reference configuration and field mappings are documented in `influxdb/downsampling-config.yaml`.

### Monitoring

You maybe be able to use InfluxDB Explorer (in admin mode, which is the default for SFC) for some of this.

```bash
# Check target table creation
docker-compose exec influxdb influxdb3 -t your_token -c "SHOW TABLES"

# Verify data down-sampling (use the correct target measurement name)
docker-compose exec influxdb influxdb3 -t your_token -c "SELECT COUNT(*) FROM volume_performance_5m_auto"
```

### 3. Usage

To build with custom versions:

```bash
# Option 1: Edit .env file
vim .env

# Option 2: Override at build time
PYTHON_VERSION=3.12.12-alpine3.22 docker-compose build sfc

# Option 3: Environment override
export INFLUXDB3_BUILD_VERSION=3.4.0
docker-compose build influxdb
```
