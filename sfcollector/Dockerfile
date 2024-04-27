#  
# Apache 2.0 License
# @scaleoutSean
# 
# Based on SolidFire Collector script from HCI Collector v0.7.1:
# https://github.com/scaleoutsean/hcicollector/tree/v0.7/sfcollector
# Can use non-vSphere dashboards from the same release:
# https://github.com/scaleoutsean/hcicollector/tree/v0.7/grafana/dashboards
# Run this container with -h to get help for arguments, or see the HCI Collector v0.7 documentation

FROM python:3.9.19-slim-bullseye
LABEL maintainer="@scaleoutSean"
RUN python -m pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir --upgrade solidfire-sdk-python==12.3.0.203 requests graphyte==1.7.1
ENV PATH=/root/.local:$PATH
COPY solidfire_graphite_collector.py /solidfire_graphite_collector.py
RUN chmod +x /solidfire_graphite_collector.py
ENTRYPOINT [ "python" , "/solidfire_graphite_collector.py" ]
