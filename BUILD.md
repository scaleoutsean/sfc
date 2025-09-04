# Docker build args configuration

This document explains how the SFC project uses environment variables and Docker build arguments for version management.

## Environment variables (.env)

The `.env` file contains both runtime and build-time configuration:

### Build-time versions (used as `ARG`s in Dockerfiles)

- `VERSITY_S3GW_VERSION=1.0.14` - Versity S3 Gateway version
- `INFLUXDB3_BUILD_VERSION=3.3.0` - InfluxDB3 Core binary version for download
- `PYTHON_VERSION=3.12.11-alpine3.22` - Python base image version
- `PYTHON_DIGEST=sha256:...` - Python image digest for extra security

### Runtime versions (used in docker-compose services)

- `INFLUXDB3_VERSION=3-core` - InfluxDB3 image tag
- `GRAFANA_VERSION=latest` - Grafana image tag

## How It Works

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
