FROM python:3.12.11-alpine3.22@sha256:c610e4a94a0e8b888b4b225bfc0e6b59dee607b1e61fb63ff3926083ff617216
# https://hub.docker.com/layers/library/python/3.12.11-alpine3.22/images/sha256-c7faa49938b528b23f0d3f900d6c3e11e16ded420852d327f58267547d26f915

LABEL maintainer="@scaleoutSean"

# Create a non-root user and group
RUN addgroup -S sfcgroup && adduser -S sfcuser -G sfcgroup

USER sfcuser
WORKDIR /home/sfcuser

# Install Python packages to user site for sfcuser
RUN pip install --user --no-cache-dir --upgrade apscheduler==3.11 aiohttp[speedups]==3.12.13

# Copy your certificate *chain* to the container. You don't need these 2 lines if your SolidFire certificate can be validated without CA import.
ADD prod.crt /usr/local/share/ca-certificates/prod.crt
RUN chmod 644 /usr/local/share/ca-certificates/prod.crt && update-ca-certificates

# Copy sfc.py to the non-root user's home directory
COPY sfc.py /home/sfcuser/sfc.py
RUN chown -R sfcuser:sfcgroup /home/sfcuser

# Set PATH to include sfcuser's local bin
ENV PATH=/home/sfcuser/.local/bin:$PATH

ENTRYPOINT [ "python" , "/home/sfcuser/sfc.py" ]

# Alternative Alpine approaches: https://stackoverflow.com/questions/67231714/how-to-add-trusted-root-ca-to-docker-alpine
# ADD my-cert.pem /usr/local/share/ca-certificates/my-cert.crt
# RUN cat /usr/local/share/ca-certificates/my-cert.crt >> /etc/ssl/certs/ca-certificates.crt 

# How to run SFC from your Docker container: 
# docker run --name=sfc sfc:v2.1.0 -h