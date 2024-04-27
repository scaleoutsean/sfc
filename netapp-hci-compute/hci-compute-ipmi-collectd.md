# Gathering NetApp H-Series BMC Metrics with collectd 

As tested with:

- Ubuntu 20.04
- collectd 5.9.0 (5.9.2.g-1ubuntu5)

Save your collectd config file somewherewhere (e.g. /etc/collectd.conf), make sure collectd service is stopped, and then start it with:
```
sudo /usr/sbin/collectd -C /etc/collectd.conf -f
```

Minutes later the metrics should appear in the right dashboard (H400C or H615C). If not, troubleshoot IPMI access, IPMI login, firewall access to Graphite (HCICollector port 2003), Graphite, Grafana.... 

If this minimalistic approach works, you can include the plugin-related info in main collectd.conf, start collectd without `-f` and after that works fine, enable collectd service and run it in background.

We should probably also monitor the monitor, that is enable gathering of collectd metrics and watch it from Graphana to make sure that service is up and IPMI data is being fetched and sent in.


## References and Tips

- On Debian and Ubuntu, it is probably easiest to install collectd with apt, avoid installing recommended packages, and choose None when asked about Apache or Lighttpd integration
- Getting started with collectd: https://collectd.org/wiki/index.php/First_steps

## Minimal /etc/collectd.conf

- I haven't tried to monitor more than one system of the same platform (H400 or H615C) at the same time using from single collectd instance using different `<Instance>` [blocks](https://collectd.org/documentation/manpages/collectd.conf.5.shtml#plugin_ipmi); if that cannot be done effectively, consider using a separate collectd container for each IPMI/BMC host you have
- H400 Series chasis are shared among several nodes; if you have multiple systems that share the same chassis, there is no reason to have a panel for chassis or PSU for each of those nodes. Therefore, if you use Instance blocks in the IPMI plugin, you could use this approach:
  - Instance Ch1 - shared IPMI metrics (e.g. chassis PSU1, PSU2)
  - Instance Ch2 - shared metrics
  - Instance Ch1Cn1 - compute node-level metrics (e.g. system Temperature sensors for Compute Node in Chassis 1, Slot 1)
  - Instance Ch2Cn1 - compute node-level metrics (Compute Node from Chassis 2, Slot 1 ('A'))
  - [Optional] Instance Ch1Sn2 - storage node metrics from Chassis 1, Slot 2 ('B')
  - [Optional] Instance Ch2Sn2 - storage node metrics from Chassis 2, Slot 2 ('B')
  - If chassis-level and system-level metrics are gathered separately, we have to edit paths to appropriate panels in sample dashboards

```
# Set your FQDN/IP/hostname here
Hostname    "h410c21"
# Hostname    "h615ct4"
# Note that the IPMI plugin uses `Instance` blocks to identify IPMI endpoints (see above)
# Above "global" hostname is used only in the IPMI plugin doesn't have it set

# We need at least these two plugins

LoadPlugin ipmi
LoadPlugin write_graphite

# Plugin config

<Plugin ipmi>
  # Use <Instance> blocks for multiple IPMI endpoints
  #
  # This is the IPMI (BMC) IP of H410 or H615C IPMI interface (BMC)
  Address  "10.1.1.1"
  # Create a USER-type IPMI account for this - do not use admin/root!
  Username "monitor"
  Password "m0n1tor"
  Host "ch1cn2"
  #AuthType "md5"
  # In order to call out sensors, you must know their exact names
  # If you don't call out any, a "basic" set of metrics will be captured
  # Best to not call out any, make sure it works first, then get fancy later
  # Sensor "Fan_SYS0_0"
  # Sensor "Temp_GPU1"
  # IgnoreSelected false
  NotifySensorAdd false
  NotifySensorRemove true
  NotifySensorNotPresent false
  NotifyIPMIConnectionState true
  SELEnabled false
  # SELSensor "another_one"
  # SELIgnoreSelected false
  SELClearEvent false
</Plugin>

# If you want to send metrics elsewhere (syslogd, etc.), use a different plugin
# This one sends metrics to Graphite using HCICollector configuration

<Plugin write_graphite>
  <Node "my-hcicollector">
    # Your HCICollector (or Graphite) IP 
    Host "10.10.10.10"
    # HCICollector's firewall rules must allow access to port 2003 to collectd host/IP
    # Other clients should not be allowed to access Graphite (see the README and FAQs.)
    Port "2003"
    Protocol "tcp"
    ReconnectInterval 30
    LogSendErrors true
    # Sample dashbards are based on these paths
    # NOTE:
    # Enable only one per instance of collectd
    # H300E, H500E, H700E can all use H400 path
    # Prefix "netapp.hci.compute.h400."
    # Prefix "netapp.hci.compute.h615."
    StoreRates true
    AlwaysAppendDS false
    EscapeCharacter "_"
    SeparateInstances false
    PreserveSeparator false
    DropDuplicateFields false
    ReverseHost false
  </Node>
</Plugin>

```
