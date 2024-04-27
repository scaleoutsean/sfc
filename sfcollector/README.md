# SolidFire Collector on Kubernetes

See https://scaleoutsean.github.io/2022/05/02/solidfire-collector-in-kubernetes.html for a simple how-to.

- SFC container v0.7.1+ from https://hub.docker.com/repository/docker/scaleoutsean/sfc can work with Dashboards from HCI Collector v0.7+ branch
- SFC v0.7.1+ from Docker Hub only collects SolidFire metrics (not vSphere)
- SFC v0.7.1+ can run in regular Docker environments and send data to Kubernetes-based Graphite, so users who have own (or don't need it) vSphere monitoring can use it instead of the more complicated procedure for HCI Collector

The YAML file is an example Kubenetes Deployment with Graphite and SolidFire. If you run SolidFire in another Deploymment, send data to Graphite container's IPv4 address or resolvable hostname.

## Kubernetes

Use deployment YAML.

## Docker

```sh
docker run -it --name ${CONTAINER_NAME} \
  docker.io/scaleoutsean/sfc:latest \
  -s ${SF_MVIP} \
  -u ${SF_RO_ADMIN} -p ${SF_RO_ADMIN_PASS} \
  -g ${GRAPHITE_HOST}
```
