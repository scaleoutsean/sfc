#!/bin/bash
############################################################################# 
# This script has been soft-deprecated in v0.7                              #
# While it works, it is recommended to:                                     # 
#  - Review and, if necessary, manually edit configuration files            #
#  - Use OS f/w rules to only allow incoming TCP/80 (or TCP/443) and TCP/22 #
#############################################################################

# Check for proper permissions (https://stackoverflow.com/a/21622456)
if (( $EUID != 0 )); then
    echo "Please execute this script as root or use sudo"
    exit 128
fi

####Install HCI Collector####

for i in {16..21} {21..16} {16..21} {21..16} {16..21} {21..16} ; do echo -en "\e[38;5;${i}m#\e[0m" ; done ; echo

# Set some bash colors
Red='\033[0;31m'          # Red
Green='\033[0;32m'        # Green
Yellow='\033[0;33m'       # Yellow
Blue='\033[0;34m'         # Blue
Purple='\033[0;35m'       # Purple
Cyan='\033[0;36m'         # Cyan
White='\033[0;37m'        # White

# Best don't customize this parameter
GRAPHITEVOL="graphite"

# Read in variables

echo "Info needed by this install script:"
echo "1) SolidFire MVIP and credentials"
echo "2) VMware vCenter IP and credentials"
echo "3) One of the IPs of this VM where Grafana Web UI will be accessed"
echo ""
echo "You can use CTRL+C to stop this script and run it again when ready"
echo ""
echo "NOTE: HCICollector will not verify TLS certificates of SolidFire, vCenter and ESXi"
echo ""

echo -e ${Red} "Enter the SolidFire management virtual IP (MVIP):"
read SFMVIP
echo -e ${Red} "Enter the SolidFire username (e.g. 'monitor'):"
read SFUSER
echo -e ${Red} "Enter the password for:" $SFUSER
read -s SFPASSWORD
# We could get this via the API but not everyone has curl or Python installed so we ask
echo -e ${Red} "Enter the Solidfire cluster name (NetApp HCI storage cluster name): "
echo -e ${Red} "If unsure, visit https://${SFMVIP} to take a look (top right corner in Web UI)"
read SFCLUSTER
echo -e ${Yellow} "Enter the initial password to use for the Grafana admin account:"
read -s GPASSWORD
# echo -e ${Yellow} "Do you want to provision sample dashboards ("N" = import or create by yourself):"
# read -e -i 'Y' GPPROVISION || GPPROVISION=Y
echo -e ${Green} "Enter the vCenter DNS hostname or IP (e.g. 'vcsa' or '10.10.10.10'):"
read VCENTERHOSTNAME
# Pre-populate with common username
echo -e ${Green} "Enter the vCenter username (e.g. administrator@vsphere.local):"
read -e -i 'administrator@vsphere.local' VCENTERUSER || VCENTERUSER=administrator@vsphere.local
echo -e ${Green} "Enter the vCenter password:"
read -s VCENTERPASSWORD
echo -e ${Green} "Enter the vCenter DNS domain (e.g. 'vi.company.com' or 'local' if none)"
read VCENTERDOMAIN
echo -e ${Green} "The ESXi hostnames resolve in DNS: yes or no? (e.g. 'no' for IP-based hosts)"
read VCENTERHASDNS
echo -e ${White} "Enter the IP address of this Docker VM (for access to Grafana Web UI):"
read DOCKERIP
echo ""
echo "NOTE: Wrapper script wrapper.sh applies default sfcollector timeouts (10s to connect, 20s to receive API response)"
echo "      If you want to change these timeouts edit wrapper.sh (after this script completes, but before Docker Compose build)"
echo ""
echo "To stop now without having to wipe this folder, press CTRL+C within 5s"
sleep 5
echo -e ${White} "Beginning install..."

# Docker compose configuration
echo "Creating the docker-compose.yml file"
cat << EOF > ./docker-compose.yml
version: "2"
services:
  graphite:
    build: ./graphite
    container_name: graphite-v0.7
    restart: always
    ports:
        - "8080:80"
        - "8125:8125/udp"
        - "8126:8126"
        - "2003:2003"
        - "2004:2004"
    volumes: 
        - ${GRAPHITEVOL}:/opt/graphite/storage/whisper
    networks:
        - net_hcicollector
    environment:
        GRAPHITE_LOG_ROTATION: 1

  grafana:
    build: ./grafana
    container_name: grafana-v0.7
    volumes:
        - grafana:/var/lib/grafana
        - ./grafana/provisioning/:/etc/grafana/provisioning/
    restart: always
    ports:
        - "80:3000"
    networks:
        - net_hcicollector
    environment:
        #Set password for Grafana web interface
        GF_SECURITY_ADMIN_PASSWORD: ${GPASSWORD} 
        #Optional SMTP configuration for alert queries
        # GF_SMTP_ENABLED: true
        # GF_SMTP_HOST: smtp.gmail.com:465
        # GF_SMTP_USER: <email address>
        # GF_SMTP_PASSWORD: <email password>
        # GF_SMTP_SKIP_VERIFY: true
        GF_RENDERING_SERVER_URL: http://renderer:8081/render
        GF_RENDERING_CALLBACK_URL: http://grafana:3000/
        GF_LOG_FILTERS: rendering:debug

  renderer:
    image: grafana/grafana-image-renderer:latest
    container_name: renderer-v0.7
    ports:
      - 8081
    environment:
      ENABLE_METRICS: 'true'
      # GF_RENDERER_PLUGIN_GRPC_PORT: 50059
      GF_RENDERER_PLUGIN_IGNORE_HTTPS_ERRORS: 'true'
      # GF_RENDERER_PLUGIN_VERBOSE_LOGGING: 'false'
      # GF_RENDERER_PLUGIN_TZ: Europe/London

  sfcollector:
    build: ./sfcollector
    container_name: sfcollector-v0.7
    restart: always
    networks:
        - net_hcicollector

  vmwcollector:
    build: ./vmwcollector
    container_name: vmwcollector-v0.7
    restart: always
    networks:
        - net_hcicollector
    depends_on:
        - graphite

networks:
  net_hcicollector:
    driver: bridge

volumes:
  ${GRAPHITEVOL}:
    external: false
  grafana:
    external: false
EOF
chmod 740 docker-compose.yml

# Wrapper script for the SolidFire collector
echo "Creating the SolidFire collector wrapper.sh script"
cat << EOF > ./sfcollector/wrapper.sh
#!/usr/bin/env sh
while true
do
/usr/bin/env python3 /solidfire_graphite_collector.py -s $SFMVIP -u $SFUSER -p "$SFPASSWORD" -g "graphite" -o 10 -a 20 &
sleep 60
done
EOF
chmod 740 ./sfcollector/wrapper.sh

# Create the storage-schemas.conf file for Graphite
echo "Creating the storage-schemas.conf file"
cat << EOF > ./graphite/storage-schemas.conf
[stats]
pattern = ^stats\.*$
retentions = 5s:1d,1m:7d

[netapp]
pattern = ^netapp\.*
retentions = 1m:7d,5m:28d,10m:1y

[vsphere]
pattern = ^vsphere\.*
retentions = 1m:7d,5m:28d,10m:1y

[carbon]
pattern = ^carbon\.*$
retentions = 5s:1d,1m:7d

[statsd_internal_counts]
pattern = ^stats_counts\.statsd.*$
retentions = 5s:1d,1m:7d

[statsd_internal]
pattern = ^statsd\..*$
retentions = 5s:1d,1m:7d

[statsd]
pattern = ^stats_counts\..*$
retentions = 5s:1d,1m:28d,1h:2y

[statsd_gauges_internal]
pattern = ^stats\.gauges\.statsd\..*$
retentions = 5s:1d,1m:7d

[statsd_gauges]
pattern = ^stats\.gauges\..*$
retentions = 5s:1d,1m:28d,1h:2y

[catchall]
pattern = ^.*
retentions = 1m:5d,10m:28d
EOF

# Create the vsphere-graphite.json file for the vSphere-Graphite collector
echo "Creating the vsphere-graphite.json file"
if [ $VCENTERHASDNS == 'no' ]
then
    VCENTERIPBASED='true'
else
    VCENTERIPBASED='false'
fi

cat << EOF > ./vmwcollector/vsphere-graphite.json
{
  "Domain": ".$VCENTERDOMAIN",
  "Interval": 60,
  "FlushSize": 100,
  "ReplacePoint": $VCENTERIPBASED,
  "VCenters": [
    { "Username": "$VCENTERUSER", "Password": "$VCENTERPASSWORD", "Hostname": "$VCENTERHOSTNAME" }
  ],
  "Backend": {
    "Type": "graphite",
    "Hostname": "graphite",
    "Port": 2003
  },
  "Metrics": [
    {
      "ObjectType": [ "VirtualMachine", "HostSystem" ],
      "Definition": [
        { "Metric": "cpu.usage.average", "Instances": "" },
        { "Metric": "cpu.usage.maximum", "Instances": "" },
        { "Metric": "cpu.usagemhz.average", "Instances": "" },
        { "Metric": "cpu.usagemhz.maximum", "Instances": "" },
        { "Metric": "cpu.totalCapacity.average", "Instances": "" },
        { "Metric": "cpu.ready.summation", "Instances": "" },
        { "Metric": "mem.usage.average", "Instances": "" },
        { "Metric": "mem.usage.maximum", "Instances": "" },
        { "Metric": "mem.consumed.average", "Instances": "" },
        { "Metric": "mem.consumed.maximum", "Instances": "" },
        { "Metric": "mem.active.average", "Instances": "" },
        { "Metric": "mem.active.maximum", "Instances": "" },
        { "Metric": "mem.vmmemctl.average", "Instances": "" },
        { "Metric": "mem.vmmemctl.maximum", "Instances": "" },
        { "Metric": "disk.commandsAveraged.average", "Instances": "*" },
        { "Metric": "mem.totalCapacity.average", "Instances": "" }
      ]
    },
    {
      "ObjectType": [ "VirtualMachine" ],
      "Definition": [
        { "Metric": "virtualDisk.totalWriteLatency.average", "Instances": "*" },
        { "Metric": "virtualDisk.totalReadLatency.average", "Instances": "*" },
        { "Metric": "virtualDisk.numberReadAveraged.average", "Instances": "*" },
        { "Metric": "virtualDisk.numberWriteAveraged.average", "Instances": "*" },
        { "Metric": "cpu.ready.summation", "Instance": ""}
      ]
    },
    {
      "ObjectType": [ "HostSystem" ],
      "Definition": [
        { "Metric": "disk.maxTotalLatency.latest", "Instances": "" },
        { "Metric": "disk.numberReadAveraged.average", "Instances": "*" },
        { "Metric": "disk.numberWriteAveraged.average", "Instances": "*" },
        { "Metric": "disk.deviceLatency.average", "Instances": "*" },
        { "Metric": "disk.deviceReadLatency.average", "Instances": "*" },
        { "Metric": "disk.deviceWriteLatency.average", "Instances": "*" },
        { "Metric": "disk.kernelLatency.average", "Instances": "*" },
        { "Metric": "disk.queueLatency.average", "Instances": "*" },
        { "Metric": "datastore.datastoreIops.average", "Instances": "*" },
        { "Metric": "datastore.datastoreMaxQueueDepth.latest", "Instances": "*" },
        { "Metric": "datastore.datastoreReadBytes.latest", "Instances": "*" },
        { "Metric": "datastore.datastoreReadIops.latest", "Instances": "*" },
        { "Metric": "datastore.datastoreWriteBytes.latest", "Instances": "*" },
        { "Metric": "datastore.datastoreWriteIops.latest", "Instances": "*" },
        { "Metric": "datastore.numberReadAveraged.average", "Instances": "*" },
        { "Metric": "datastore.numberWriteAveraged.average", "Instances": "*" },
        { "Metric": "datastore.read.average", "Instances": "*" },
        { "Metric": "datastore.totalReadLatency.average", "Instances": "*" },
        { "Metric": "datastore.totalWriteLatency.average", "Instances": "*" },
        { "Metric": "datastore.write.average", "Instances": "*" },
        { "Metric": "mem.state.latest", "Instances": "" },
        { "Metric": "cpu.ready.summation", "Instance": ""},
        { "Metric": "cpu.usagemhz.average", "Instance": ""},
        { "Metric": "cpu.usage.average", "Instance": ""}
      ]
    }
  ]
}
EOF
# This below won't work
# sudo chmod 740 ./vmwcollector/vsphere-graphite.json

# Create the datasource.yml file for the dashboards
# If you customized GRAPHITEVOL (which you shouldn't have), also modify `name` in:
# ./grafana/provisioning/datasources/dashboards/datasource.yml
# Change GraphiteDB IP in Grafana
sed -i "s#url: http://DOCKERIP:8080#url: http://${DOCKERIP}:8080#g" ./grafana/provisioning/datasources/datasource.yml

# Modify any hard-coded SolidFire MVIP (SFMVIP) and cluster name in sample dashboards
sed -i "s#192\.168\.1\.30#$SFMVIP#g" grafana/dashboards/*.json
sed -i "s#PROD#$SFCLUSTER#g" grafana/dashboards/*.json
# Work around Grafana issue # 10786
sed -i "s#\${DS_GRAPHITE}#graphite#g" grafana/dashboards/*.json
sed -i 's#\"DS_GRAPHITE\"#"graphite"#g' grafana/dashboards/*.json

echo "Script complete. Use 'sudo docker-compose up' to start the containers the first time"
echo ""
echo "Before you run docker-compose, you may want to consider adding a few firewall rules to allow remote access only to Grafana Web UI."
echo "-----"
echo "NOTE: It may take up to 15 minutes for all metrics to appear in Grafana dashboards (assuming everything is working)"
sleep 2
