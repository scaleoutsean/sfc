# FAQs

- [FAQs](#faqs)
  - [HLEP!! It doesn't wokr and I needed it to work yesterday](#hlep-it-doesnt-wokr-and-i-needed-it-to-work-yesterday)
  - [Where are the configuration files and what's in them](#where-are-the-configuration-files-and-whats-in-them)
  - [Do passwords really have to be stored unencrypted](#do-passwords-really-have-to-be-stored-unencrypted)
  - [What does the comment about multiple interfaces on HCICollector VM mean?](#what-does-the-comment-about-multiple-interfaces-on-hcicollector-vm-mean)
  - [Where is the SolidFire collector log?](#where-is-the-solidfire-collector-log)
  - [How to recover from a failed run of install script](#how-to-recover-from-a-failed-run-of-install-script)
  - [How to add multiple vCenter and SolidFire clusters?](#how-to-add-multiple-vcenter-and-solidfire-clusters)
  - [How to integrate HCICollector with persistent container storage](#how-to-integrate-hcicollector-with-persistent-container-storage)
  - [How to update HCICollector from an older version](#how-to-update-hcicollector-from-an-older-version)
  - [How to update individual HCICollector container to a newer version](#how-to-update-individual-hcicollector-container-to-a-newer-version)
  - [Add own data feeds and dashboards](#add-own-data-feeds-and-dashboards)
  - [Install a plugin from the Grafana Web site](#install-a-plugin-from-the-grafana-web-site)
  - [Can SolidFire Connector a newer version Grafana](#can-solidfire-connector-a-newer-version-grafana)
  - [How to create SolidFire histograms and other dashboards](#how-to-create-solidfire-histograms-and-other-dashboards)
  - [I imported a sample dashboard and it's not showing anything](#i-imported-a-sample-dashboard-and-its-not-showing-anything)
  - [How to monitor container volumes](#how-to-monitor-container-volumes)
  - [How much disks capacity do I need for HCICollector's Graphite volume?](#how-much-disks-capacity-do-i-need-for-hcicollectors-graphite-volume)
  - [How can I delete old Graphite DB files?](#how-can-i-delete-old-graphite-db-files)
  - [How to add 3rd party feeds and dashboards to HCICollector's Grafana instance](#how-to-add-3rd-party-feeds-and-dashboards-to-hcicollectors-grafana-instance)
  - [How to gather and send SolidFire storage cluster metrics to existing GraphiteDB with a Python script (without running all HCICollector containers) such as NAbox or other?](#how-to-gather-and-send-solidfire-storage-cluster-metrics-to-existing-graphitedb-with-a-python-script-without-running-all-hcicollector-containers-such-as-nabox-or-other)
  - [Use HCICollector without vCenter](#use-hcicollector-without-vcenter)
  - [Use HCICollector with a pre-11.7 version of SolidFire/Element](#use-hcicollector-with-a-pre-117-version-of-solidfireelement)
  - [Reset Grafana password](#reset-grafana-password)
  - [Alternative approaches to telemetry gathering](#alternative-approaches-to-telemetry-gathering)
  - [How to export data from Graphite](#how-to-export-data-from-graphite)
  - [It seems there are dashboard for NetApp HCI Compute node hardware monitoring (IPMI via BMC), but they aren't deployed. What's up with that](#it-seems-there-are-dashboard-for-netapp-hci-compute-node-hardware-monitoring-ipmi-via-bmc-but-they-arent-deployed-whats-up-with-that)
  - [How to gather *hardware* metrics from NetApp HCI Series nodes](#how-to-gather-hardware-metrics-from-netapp-hci-series-nodes)
  - [Can these hardware monitoring dahasboards be used to monitor SolidFire or NetApp HCI storage nodes](#can-these-hardware-monitoring-dahasboards-be-used-to-monitor-solidfire-or-netapp-hci-storage-nodes)
  - [What about H300E, H500E, H700 compute nodes](#what-about-h300e-h500e-h700-compute-nodes)
  - [Why do the two hardware monitoring dashboards for H410C and H615C have different metrics and dashboards](#why-do-the-two-hardware-monitoring-dashboards-for-h410c-and-h615c-have-different-metrics-and-dashboards)
  - [What's the roadmap, Kenneth](#whats-the-roadmap-kenneth)
  - [What is the reason Trident was removed from HCICollector](#what-is-the-reason-trident-was-removed-from-hcicollector)
  - [Can HCICollector collect Trident metrics](#can-hcicollector-collect-trident-metrics)
  - [Is this repo associated with or sponsored by NetApp](#is-this-repo-associated-with-or-sponsored-by-netapp)

## HLEP!! It doesn't wokr and I needed it to work yesterday

If you must have a working solution ASAP, please consider one of the alternatives (see other FAQs for alternatives) while you figure out how to make this thing work. For NetApp Cloud Insights you just need to register at cloud.netapp.com, download and deploy acquisition VM and you'll have something that works well.

But if you still want to try HCICollector, since v0.7 there's really not much that can go wrong so first get familiar with Docker and the HCICollector docs. You may also try the netapp-hci channel in the NetApp Community Slack (join [here](https://netapp.io)) to see if you can find someone who has experience with HCICollector. For help with 3rd party projects, please refer to their documentation & community resources.

## Where are the configuration files and what's in them

Most of these files are created by the installation script. If you change them, you may need to rebuild the containers.

- `docker-compose.yml` - Initial Grafana password (you'll be prompted to change it the first time you log in) 
- `grafana/provisioning/*/*.yml` and `grafana/Dockerfile` - Grafana configuration
- `graphite/carbon.conf` and `graphite/*.conf` - GraphiteDB (service user identity) and StatsD configuration files (including IP address)
- `sfcollector/wrapper.sh` - SolidFire cluster admin account and password. It is created by install script. wrapper.sh periodically executes `solidfire/solidfire_graphite_collector.py` which gathers metrics and events and sends them to Graphite
- `vmwcollector/vsphere-graphite.json` and `vmwcollector/Dockerfile` - VMware vCenter monitoring account and password and container details

## Do passwords really have to be stored unencrypted

For now yes, but your pull request that fixes that would be welcome. The VM is your last line of defense. Protect it.

The entire VM (apart from the Grafana Web UI, of course) should be made off limits to non-administrators. Suggested configuration:

- VM with two interfaces (Management & User Network)
- Management Network: connection to vCenter, SolidFire/Element
  - Graphite (carbon.conf) listening on this network
- User Network: expose Grafana via HTTPS 
  - Firewall that permits access only to port 443 of this interface (or 80, if you don't want to create TLS certificates and register this interface in DNS)

Another thing that should be considered by users of Element OS v12 or newer is to set up a dedicated cluster admin account on SolidFire or NetApp HCI limited to Read & Reporting role (refer to Access Control in the SolidFire User Guide or SolidFire API Reference Guide). Older Element releases require full-featured cluster admin account for Read & Reporting.

The same goes for VMware - vSphere administrator account with limited permissions (read-only) should be used for VMware cluster monitoring. If you don't manage the SolidFire or VMware cluster(s) you want to monitor, you may ask the admin(s) to create a reporting-only admin account for you (for Element v11, if you do not use QoS histograms; for VMware vCenter please refer to the vsphere-graphite and VMware documentation.)

## What does the comment about multiple interfaces on HCICollector VM mean? 

Generally - and considering the nature of this container (passwords in config files, etc.) - it is expected that there be two interfaces:

- Internal, for IT team to access the VM, and for containers to access Managements IPs of vCenter and SolidFire (incoming port 22 (optional), outgoing destination port 443 (required, directly or via trusted proxy))
- External, for users (from IT or elsewhere), to access Graphana Web UI (incoming port 80)

When install script creates config files for you, it sets all services to "external" IP, including but not limited, Graphite (incoming port 8080). To prevent outside users from accessing this VM, either change config files to not expose services on this interface (hard) or add firewall rules to only allow access to port 80 on External IP. Yes, 443 (HTTPS) would be even better, but you'd have to supply TLS certificates Grafana (see `grafana/Dockerfile` and Grafana documentation) and rebuild that container, or add another container, a reverse proxy that would terminate HTTPS and redirect to HTTP (Graphana service port). 

Another point should be made about Grafana accounts. If you don't access Grafana over HTTPS, it may not be a great idea to have any accounts on it because with HTTP passwords are transmitted in clear. You should definitively NOT use your "default" admin password for Grafana! Best practice: read the Grafana manual and rebuild the container to work with HTTPS, and then create appropriate Grafana accounts.

## Where is the SolidFire collector log?

For the container engine and 3rd party containers please see their respective documentation. 

For the container running solidfire_graphite_collector.py (SFCollector) see `sfcollector/solidfire_graphite_collector.py --help`. You can edit wrapper.sh (example below), (re)build the container, start and enter the container to run `tail -f /log.txt`

```shell
/usr/bin/python /solidfire_graphite_collector.py -s 10.10.10.10 -u monitor -p "monitor1234" -g graphite -l log.txt &
```

## How to recover from a failed run of install script

It's just Docker, so use regular Docker (including `docker-compose`) commands to delete the containers, networks, etc. To remove Docker data, look into removing the Docker Graphite and Grafana volumes, too.

## How to add multiple vCenter and SolidFire clusters?

- For vCenter, edit `vmwcollector/vsphere-graphite.json` and rebuild. See upstream documentation.
- For SolidFire, edit `sfcollector/wrapper.sh` to run against additional MVIP's and rebuild. Note that dashboard panel links may need to be modified to use variables, as the way they're currently created is hardcoded based on single storage cluster use case.

## How to integrate HCICollector with persistent container storage

Deploy Docker CE or Kubernetes, deploy a NetApp Trident container (there are two versions - one for Docker and one for Kubernetes) and make sure it works with your backend (ONTAP or SolidFire or whatever you use to store these metrics). Then, instead of creating a local volume for GraphiteDB or any other data you want to persist to external storage, create a Trident volume on external storage (Element OS, ONTAP, etc.) and edit your Docker compose file to make HCICollector store GraphiteDB data on it (in `docker-compose.yaml` generated by installation script find `graphite` (volumes section) and set `external: true`. Then rebuild the Graphite container). You may need to refer to install script from a previous releases of HCICollector and reference various configuration files (mostly for Grafana and Graphite).

If you want to migrate data from a local to an external volume, you could create a new external volume and use a custom container (that mounts the both) and then copy data from old to new volume. Obviously you'd have to do this while GraphiteDB isn't being used, so maybe temporarily modify its Dockerfile and roll back the modification after data has been copied over. Next time the container is started it should be mounting only one (new) Graphite volume on external storage. Create a snapshot before this if you want to protect your data. You'd also have to rebuild the graphite container.

## How to update HCICollector from an older version

I would advise against that because that hasn't been tested and changes may break it (see CHANGELOG for v0.7).

## How to update individual HCICollector container to a newer version

Edit Dockerfile and rebuild the container. You may want to do this if there's a security bug that affects you or you want to add functionality unavailable in current release. 

Using container and config files from newer releases may not work because there are several moving parts.

## Add own data feeds and dashboards

Feel free to do it by yourself. Metrics can be sent to StatsD or directly to Graphite (see `graphite/Dockerfile`). Additional ports may be `EXPOSE`'d if necessary. Dashboards can be imported from the Graphana Web interface. Since v0.7, it is possible to edit (or remove) built-in sample dashboards and import or create your own.

## Install a plugin from the Grafana Web site

Modify the Grafana Dockerfile and rebuild the container. 

## Can SolidFire Connector a newer version Grafana

SolidFire Collector seems to work fine with Grafana 11 Preview (and Grafana and SolidFire work with latest Graphite), so it's likely Grafana 8, 9, 10 and 11 all work.

## How to create SolidFire histograms and other dashboards

See the samples included in HCICollector. 

A separate but related problem is what Grafana function should be used to visualize histogram metrics. Derivative seems to provide better results than perSecond (both of these can be found under panel Transform functions.)

## I imported a sample dashboard and it's not showing anything

First, give it time before you start reinstalling or making changes. I've seen SSDs and ESXi take 70 minutes for all panels to get populated. Other data may start appearing in 5 minutes. As long as one panel works, that's valuable info for troubleshooting, so wait at least 10-15 minutes.

Things that can go wrong:

- Grafana's source DB (instance of GraphiteDB): is Source working? Make sure of the type and name of your Grafana data source (in Grafana settings, make Graphite or Default or whatever is functional)
- Dashboard's source: edit imported Dashboard and in Source pick the correct (Default or Graphite or whatever) Source that contains GraphiteDB data to be visualized
- Dashboard attempts to use wrong MVIP or cluster: delete pre-installed Dashboard, check source code for the dashboard (e.g. by browsing the HCICollector source code on Github) and look for SolidFire MVIP or cluster name. Replace those with your own MVIP or cluster name, copy the file to where other Dashboards are lcoated (`./grafana/...`) and rebuild Grafana container
- Panels: due to changes in metric paths, a dashboard or panel from v0.7 may not work in (say) v0.7.5. Download the file from the right repo branch
- Metric path, URL or cluster name in Dashboard imported using the Grafana UI: things get correctly set up by the HCICollector install script, which uses the SolidFire MVIP you provide to spare you from doing that manually for every Dashboard or Panel. You can correct these details in text editor or Grafana and run a file-wide Search-and-Replace before you Import the dashboard (see other hints on how).
- Pilot error: typos in passwords, accounts, IPs... 

## How to monitor container volumes

One way would be to duplicate existing dashboards and edit their queries to show only volumes owned by the Kubernetes storage provisioning account. NetApp Trident is often deployed to use the storage account name `trident`, but those who use several clusters could use dashboards with Account ID variables and manually added aliases that translate to the Account Name or even the Kubernetes cluster Name.

The hard way would be to send native NetApp Trident performance metrics to Prometheus, add Prometheus to Grafana sources, and create a new dashboard for that source. HCICollector v0.7 and earlier does not use InfluxDB, so you'd have to have InfluxDB for that.

## How much disks capacity do I need for HCICollector's Graphite volume?

As always, "it depends."

Example settings for SolidFire and VMware: 
- 1 minute frequency (retain 2 days)
- 5 minute (8 days)
- 15 minute (30 days)
- 1 hour (1 year)

For standard VM infra environments Graphite probably needs less than 1 GB/day/VM using default settings. Static environments with few VMs may want to keep fine-grained metrics longer. Dynamic DevTest or Kubernetes environments may want the opposite. If you hold Graphite on NetApp E-Series or similar array, you can keep fine-grained metrics and application logs for years. Run your environment for an hour or day, stop HCICollector, and compare Before vs After.

I tried to use various approaches to optimize but the settings can never be good for everyone. Some users may vant faily verbose stats but keep them only for 8 days, others may want coarse stats for months. And the worst of all is that deleted VMs and other objects are retained according to Graphite settings, so even if the VM is created and deleted after 7 days, its data will still be kept for 1 year (with a schema similar to the example above).

Feel free to modify Graphite settings (`graphite/storage-schemas.conf`) to suit your requirements. Check the official Graphite documentation for the details.

## How can I delete old Graphite DB files?

Get into the Graphite container, find and wipe files that haven't been touched for a while. Modify this for your circumstances (source: StackOverflow.com):

`find /opt/graphite/storage/whisper/ -type f -mtime +120 -name \*.wsp -delete; find /opt/graphite/storage/whisper -depth -type d -empty -delete`

## How to add 3rd party feeds and dashboards to HCICollector's Grafana instance

Import them from the Grafana Web UI. 

Also see "Add own data fees and dashboards" above.

## How to gather and send SolidFire storage cluster metrics to existing GraphiteDB with a Python script (without running all HCICollector containers) such as NAbox or other?

Use the `sfcollector` container. Create a `solidfire/wrapper.sh` to run `solidfire/solidfire_graphite_collector.py` and send it to existing StatsD or Graphite.

- Use `solidfire_graphite_collector.py`. Provide your own Graphite server destination with the `--graphite` argument. You may also need to provide a custom `--metricroot` suitable for your environment.
- Alternatively, modify HCICollector to send data to StatsD first. StatsD can send data to built-in GraphiteDB and also to another Graphite (such as your own). Mind the `metricroot` of secondary destination. You may also modify the script to send data to Telegram or other destnation(s).
- Metrics retention periods are set externally in your existing instance of Graphite (see the answer for GraphiteDB disk capacity estimate, above)
- If your existing Grafana setup doesn't use Graphite, you can also deploy the Graphite container from HCICollector and even reuse dashboards included in HCICollector. Then you'd add this Graphite instance as a new data source in Grafana

## Use HCICollector without vCenter

If you don't have a vCenter (you use Hyper-V, for example) or VMware in your environment, you may still use the installation script and then remove the vmwcollector (vsphere-graphite) section (before you run docker-compose).

## Use HCICollector with a pre-11.7 version of SolidFire/Element

Change the Element API version string in sfcollector/solidfire_graphite_collector.py (min `7.0`). Note that SolidFire Python SDK must support that version.

Some sample panels may not be able to work with data gathered from older API (and they can be deleted from affected sample dashboards, if you want to use those that do work.)

## Reset Grafana password

If your username is admin: enter the container, run `apk add sqlite; cd /var/lib/grafana; sqlite3 grafana.db` and set admin password to admin.

```sql
sqlite> update user set password = '59acf18b94d7eb0694c61e60ce44c110c7a683ac6a8f09580d626f90f4a242000746579358d77dd9e570e83fa24faa88a8a6', salt = 'F3FAxVm33R' where login = 'admin';
sqlite> .exit
```

## Alternative approaches to telemetry gathering

Several of the many options:

- Enterprise: please consider either the gratis or paid version of [NetApp Cloud Insights](https://cloud.netapp.com/cloud-insights), a proven, comprehensive, cloud-hosted service for cloud and on-premises environments. The free/lite version can monitor most NetApp storage products including NetApp HCI
- Enterprise: if you own a NetApp HCI or SolidFire ("storage-only") cluster, you can choose to allow NetApp ActiveIQ to gather metrics and send them to ActiveIQ service, but with better trending and alerting. ActiveIQ also has an API and a mobile application which is superior for support-related monitoring (as opposed to gathering and visualization of performance-related metrics.)
- Gratis: [NABox](https://nabox.org) (at some point it may be able to monitor Element storage clusters; until then you may try to integrate the SolidFire Graphite collector script on your own.)
- Gratis: [solidfire-exporter](https://github.com/mjavier2k/solidfire-exporter) - permissively licensed SolidFire metrics exporter to Prometheus
- Gratis: enable and use SNMP v2/v3 on Element software cluster (as well as other monitored components). This can work with any tool which can receive SNMP traps (Zabbix, [Nagios/Icinga](https://github.com/scaleoutsean/nagfire), etc.)

## How to export data from Graphite

- Manual: click at the top of a panel and in drop-down menu select `More` > `Export to CSV`. You can also get the URL for your query or panel and poll it periodically to export/download data.
- Automated: see the [Graphite API docs](https://graphite.readthedocs.io/en/latest/render_api.html). Of course, because we control data as it's being gathered, we can store it in both Graphite and another location and eliminate the need to export it to begin with, but if you want to store just one copy and export a subset later, Graphite API is a convenient way to do that.

## It seems there are dashboard for NetApp HCI Compute node hardware monitoring (IPMI via BMC), but they aren't deployed. What's up with that

Those are a very late addition (in v0.7 beta 2) and not tested nearly enough, but considering the quirky nature of IPMI some users may find them useful. YMMV.

## How to gather *hardware* metrics from NetApp HCI Series nodes

- For storage nodes, it's included in the API (see the repo Awesome SolidFire) and indirectly used by integrated SolidFire platform software (Element OS)
- For compute nodes, HCI Collector v0.7 uses a OS-independent approach, IPMI

**WARNING**: as mentioned elsewhere, Grafana in HCICollector has the ability to configure alerts, but they are not enabled by default. Related to that, some gauges in the hardware monitoring dashboards have visual clues about the status of certain indicators (e.g. hot for overheated System Board). While care has been taken to use conservative values, these do not represent manufacturers' (NetApp, Intel, NVIDIA) recommendations and do not activate alerts or notifications in the Grafana UI. Independently of Grafana, BMC itself can create alerts (`SELEnabled` and `SELSensor` in collectd documentation), but that is not enabled in the example configuration file in this repo.

Please refer to the official sites for information on operating environment and safety, starting with the official NetApp HCI documentation.

IPMI polling may also fail, resulting in one or more dashboards showing outdated information. Please review the thresholds and do not rely on HCICollector for decision making in environments where the malfunctioning of these components could increase the risk of fire hazard, injury, etc.

One way to do it is:

- Use ipmitool to create a new USER type of user for read-only access to IPMI IP's
- Deploy a VM or container with collectd (see a mini how-to in the config-examples directory). This VM or container needs to access IPMI IPs and Graphite (to submit gathered data). Go easy on the IPMI information gathering interval - BMC isn't a Web appliance... Set collectd to gather info every 3-5 minutes
- Metric root for the BMC metrics is `netapp.hci.compute` and depending on how you configure collectd, your metrics can be found under `netapp.hci.compute.h615.$hostname.ipmi.` or similar
- Deploy one or both hardware-monitoring dashboards (for the H410C or H615C), in each dashboard pick the right platform (e.g. H615C) and hostname (e.g. H615T4). If you have multiple systems, you can select All, although in that case you may need to make adjustments to panels. These dashboards were tested with one system per platform, so they probably need to be significantly modified to nicely display multiple systems in a single dashboard

## Can these hardware monitoring dahasboards be used to monitor SolidFire or NetApp HCI storage nodes

Yes, but those nodes already expose system-level warnings, so while gathering BMC metrics from those systems will work, it creates more workload on the storage nodes' BMC without significantly increasing their manageability.

## What about H300E, H500E, H700 compute nodes

Use the instructions for the H410 platform

## Why do the two hardware monitoring dashboards for H410C and H615C have different metrics and dashboards

Because they use different BMCs and different hardware platforms. The collectd IPMI plugin by default gathers "basic" IPMI metrics, so if one wanted to find a non-trivial common set of metrics that would be possible, but it'd also require extra time (get all metrics, figure out which are equivalent, and so on).

Up to four nodes in the H400 Series chassis share (two) chassis fans, so if one were to to show only sensor info common to both platforms, neither H615C fans nor H410 shared chassis fans would be shown.

## What's the roadmap, Kenneth

Don't have it! 

At this time my primary goal is to keep the components up to date and ensure this thing installs and runs.

I've been thinking about changing the back-end to InfluxDB v1 and removing VMware-related code from this repo.

## What is the reason Trident was removed from HCICollector

Because it was confusing to people unfamiliar with Trident, the installation script couldn't handle Trident updates and various other concerns (such as, for example, the fact that more and more NetApp customers use Trident in production so there's a growing risk of unintentional conflict with other users and workloads). Additionally, my primary goal is to make it easier to install and use SolidFire collector in existing monitoring infrastructure rather than create new instances of Grafana and Graphite or introduce additional dependencies.

## Can HCICollector collect Trident metrics

Up to v0.7 it cannot. It could, but that feature would have to be added. It should be relatively simple (scrape Prometheus metrics from Trident container (port 8001), store them in another back-end (not Graphite), and add a dashboard or two).

Prometheus users probably want to use existing Prometheus instances (built into Kubernetes or stand-alone) so I think it should be easier to do this:

- Add a Graphite container to and send sfcollector data to it, and use existing Grafana or other front-end, or
- Use `solidfire-exporter` (not sfcollector) with existing Prometheus, and do not use HCICollector/sfcollector. It may collect slightly different metrics, of course.

Trident's SolidFire metrics are relatively basic as of v21.01, so I'd recommend `solidfire-exporter` to folks who use Kubernetes. The value of Trident metrics isn't in the breadth or depth of SolidFire metrics, but that it makes it possible to monitor only Trident-related SolidFire metrics. 

`sfcollector` can't tell for sure what volumes were created by Trident, although I was able to use regexp in Grafana to create a "poor man's" filter to show only Trident volumes. Those generally have at least two underscores in Volume name. Trident-managed SolidFire volumes have specific metadata tags and are owned by known accounts (those specified in the SolidFire back-end JSON used by Trident), so it is not hard to identify them them in either Grafana (regexp for volume name, or storage account) or sfcollector (pre-process Trident volume metrics before sendign them to Graphite, based on account information and volume metadata).

## Is this repo associated with or sponsored by NetApp

No, it is not.
