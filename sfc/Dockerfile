# Set default Python version (can be overridden at build time)
ARG PYTHON_VERSION=3.15.0a7-alpine3.22
ARG PYTHON_DIGEST=sha256:91f42f75ba6a04f0ae571a1010e0dfca3ac79d7d41ee0e366a7f8ab6dc55faad
ARG APSCHEDULER_VERSION=3.11.2
ARG AIOHTTP_VERSION=3.13.5

FROM docker.io/python:${PYTHON_VERSION}@${PYTHON_DIGEST} AS builder
# https://hub.docker.com/layers/library/python/3.12.11-alpine3.22/images/sha256-c7faa49938b528b23f0d3f900d6c3e11e16ded420852d327f58267547d26f915

# Re-declare args after FROM so they are available during this stage.
ARG APSCHEDULER_VERSION
ARG AIOHTTP_VERSION

# Create a non-root user and group
RUN addgroup -S sfcgroup && adduser -S sfcuser -G sfcgroup

# Builder-only toolchain for native wheel compilation.
RUN apk add --no-cache build-base libffi-dev python3-dev cmake c-ares-dev

USER sfcuser
WORKDIR /home/sfcuser

# Install Python packages to user site for sfcuser
RUN pip install --user --no-cache-dir --upgrade apscheduler==${APSCHEDULER_VERSION} aiohttp[speedups]==${AIOHTTP_VERSION}

FROM docker.io/python:${PYTHON_VERSION}@${PYTHON_DIGEST}

LABEL maintainer="@scaleoutSean"

# Runtime-only packages (no compiler toolchain)
RUN apk add --no-cache ca-certificates libffi

# Copy CA certificates and install them to Alpine certificate store
# The certificates will be copied from the build context
COPY certs/ /usr/local/share/ca-certificates/
RUN update-ca-certificates

# Create a non-root user and group
RUN addgroup -S sfcgroup && adduser -S sfcuser -G sfcgroup

# Copy only installed Python packages from builder stage
COPY --from=builder --chown=sfcuser:sfcgroup /home/sfcuser/.local /home/sfcuser/.local

USER sfcuser
WORKDIR /home/sfcuser

# Copy sfc.py to the non-root user's home directory
COPY --chown=sfcuser:sfcgroup sfc.py /home/sfcuser/sfc.py

# Set PATH to include sfcuser's local bin
ENV PATH=/home/sfcuser/.local/bin:$PATH

ENTRYPOINT [ "python" , "/home/sfcuser/sfc.py" ]

# Alternative Alpine approaches: https://stackoverflow.com/questions/67231714/how-to-add-trusted-root-ca-to-docker-alpine
# ADD my-cert.pem /usr/local/share/ca-certificates/my-cert.crt
# RUN cat /usr/local/share/ca-certificates/my-cert.crt >> /etc/ssl/certs/ca-certificates.crt 

# How to run SFC from your Docker container: 
# docker run --name=sfc sfc:v2.2.0 -h