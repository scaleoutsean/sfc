FROM debian:trixie-slim
LABEL maintainer="@scaleoutSean"

# Set default Versity S3 Gateway version (can be overridden at build time)
ARG VERSITY_VERSION=1.0.14
ENV VERSITY_VERSION=${VERSITY_VERSION}

# Install dependencies for .deb installation and running versitygw
RUN apt-get update && \
    apt-get install -y wget ca-certificates && \
    wget https://github.com/versity/versitygw/releases/download/v${VERSITY_VERSION}/versitygw_${VERSITY_VERSION}_linux_amd64.deb && \
    apt-get install -y ./versitygw_${VERSITY_VERSION}_linux_amd64.deb && \
    rm versitygw_${VERSITY_VERSION}_linux_amd64.deb && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]


