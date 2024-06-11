FROM python:3.10.14-alpine3.20
LABEL maintainer="@scaleoutSean"
RUN pip install --no-cache-dir --upgrade apscheduler==3.10.4 aiohttp==3.9.5
ENV PATH=/root/.local:$PATH

# Copy your certificate *chain* to the container. You don't need these 2 lines if your SolidFire certificate is valid.
ADD prod.crt /usr/local/share/ca-certificates/prod.crt
RUN chmod 644 /usr/local/share/ca-certificates/prod.crt && update-ca-certificates

COPY sfc.py /sfc.py
ENTRYPOINT [ "python" , "/sfc.py" ]
# docker run --name=sfc sfc:v2.0.0 -h
