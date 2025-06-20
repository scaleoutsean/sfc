# Change Log

- [Change Log](#change-log)
  - [Changes in v2.1.0](#changes-in-v210)
  - [Changes in v2.0.0](#changes-in-v200)
  - [Changes in v0.7.1](#changes-in-v071)
  - [Changes in v0.7](#changes-in-v07)
  - [Changes in v0.6.1](#changes-in-v061)
  - [Changes in .v6](#changes-in-v6)
  - [Changes in .5](#changes-in-5)
  - [Changes in .4](#changes-in-4)
  - [Changes in .3](#changes-in-3)
  - [Changes in .v2](#changes-in-v2)
  - [Changes in .v1](#changes-in-v1)

## Changes in v2.1.0

- Database backend changed to InfluxDB 3 Core (tested with version 3.1 and Grafana v12.0)
- Minor bug fixes and logging improvements
- Minor dependency updates

## Changes in v2.0.0

- SolidFire Collector (technically v1.0.x in HCI Collector 0.7.x) rewritten without SolidFire Python SDK
- Database back-end change from Graphite to InfluxDB OSS v1, and smaller disk space requirements
- Scheduling and performance improvements with non-time-critical metrics collected at lower frequencies. SFC should be able to easily large SolidFire clusters
- VMware collector removed according to the plan (see [here](https://github.com/scaleoutsean/sfc/blob/v0.7.2/docs/FAQ.md#whats-the-roadmap-kenneth)). HCI Compute users can deploy the same or other vSphere collector on their own. The old how-to for IPMI data collection from NetApp HCI nodes is retained and archived in the docs folder of this repository
- Grafana configuration and dashboards also not included, but extensive reference InfluxQL queries and a dashboard created with Grafana 11 are included
- No major changes in collected data, but SFC may not include some minor measurement details that HCI Collector v0.7.1 collects, and may contain some new ones. If something essential is missing, feedback through Issues is welcome.
  - New: basic volume pairing (replication) status and mode monitoring

## Changes in v0.7.1

- Create SolidFire container based on v0.7 for easy deployment and stand-alone SolidFire monitoring with Kubernetes (see ./sfcollector-kubernetes/ directory)
- Update README.md and add an example Deployment YAML file for SolidFire Collector and Graphite/statsd
- SolidFire Collector container published on Docker Hub can be deployed without any configuration wizard

## Changes in v0.7

- Fork upstream hcicollector by jedimt (this release builds upon upstream branch .v7, here renamed to v0.7)
- Remove NetApp Trident-related steps from install script (see the FAQs). HCICollector now by default uses two local Docker volumes: one for GraphiteDB and another for Grafana settings
- Remove the NetApp Technical Report PDF and video demo files from the repo for faster repository cloning. Add video links to YouTube demo videos
- Changes and improvements to documentation as well as online help (links to the SolidFire UI and basic descriptions in various panels)
- Introduce potentially breaking changes in metrics paths and details gathered from SolidFire (see Release Notes v0.7 and FAQs)
- Change storage schemas for GraphiteDB to use less disk space
- Fixes:
  - SFCollector: wrapper script can contain special characters (issue #2). Change Docker base OS to Python 3.8.6 (slim Buster)
  - SFCollector: gather more SolidFire metrics relevant to administrators and operations staff
  - SFCollector: deduplication efficiency formula changed to account for space used for snapshots (issue #3)
  - SFCollector: set SolidFire API call timeout to a lower value than default (issue #6)
  - SFCollector: add the option to validate TLS certificate of SolidFire API endpoint(s)
  - SFCollector: add variable for API response timeout for larger environments (issue #12)
  - SFCollector: upgrade SolidFire SDK for Python  v1.7.0.152, upgrade base image to Python 3.9.2-buster-slim
  - Grafana: configure Legend and Axis Y values in most panels to display 0 decimals (enforce integer values where apppropriate (e.g. byte count) and lower the level of unnecessary detail elsewhere), adjust precision and make other usability improvements
  - Grafana: change deprecated gauge caunters to new gauge counters
  - Grafana: replace deprecated Grafana renderer with new renderer container
  - Grafana: add new panels to existing dashboards, including iSCSI connections, disk wear level, QoS histograms and more
  - Grafana: change some dashboards to make it easier to see key panels without scrolling
  - Update third party container images:
    - graphite-statsd v1.1.7-11: considerably smaller Docker image, and (by upstream) update internal components (`GRAPHITE_LOG_ROTATION: 1` added to container environment variables to retain previous behavior after changes in upstream v1.1.7-9)
    - grafana v6.7.5: v6.7.4 and v6.7.5 fix two security issues (neither of them impacts HCICollector with default settings because they aren't enabled)
    - vsphere-graphite v0.8b: support for vSphere 7.0 (and 7.0U1) API via govmomi 0.23.0 (v7.0 API should work fine on vCenter 7.0U1)
- Known issues:
  - Built-in dashboard links to SolidFire UI work for configurations with single SolidFire storage cluster. HCICollector environments that monitor multiple SolidFire clusters can add a MVIP variable to dashboard and reference it in URLs to modify URLs on the fly
  - Install script configures only one vCenter cluster and only one SolidFire cluster. See the FAQs for workarounds
  - Some visualizations use Beta-release plugins from Grafana which may have issues related to visualization or configuration (editing of panel settings). There are bugs in browsers and Grafana too
  - SolidFire disk drive Wear Level / Life Remaining visualization uses the title like `drive.${disk-id}` although `${disk-id}` would be better. The reason is the Grafana plugin cannot accept numeric titles. If that bothers you try some other Grafana visualization plugin
  - Dashboards and panels may contain hard-coded URLs (e.g. 192.168.1.30) or SolidFire cluster name (e.g. PROD): search-and-replace this link with your own before you import them. HCICollector install script does this for you, but direct import bypasses that step. The proper solution would be to add the MVIP variable to all dashboards and use it in URLs
  - By the nature of how vSphere and SolidFire plugins gather metrics, an object deleted and created with the same name (e.g. a VM, or datastore, or SolidFire volume) may appear in the same long term graph as its ancient namesake. Such objects generally have UUIDs, but VMware and SolidFire don't keep UUID-to-Name mappings for deleted objects. If UUIDs were to be used (which is partially done in Some SolidFire dashboards, that would be correct but present problems for humans who hardly recognize current, let alone historic, UUIDs). This isn't an unsolvable problem but it'd require a fair amount of work to fix. Essentially a DB would have to be built, and another back-end added to Graphite, as far as I can tell. Or cross reference SolidFire API logs against UUIDs.
- Experimental features:
  - Two sample dashboards for hardware monitoring of NetApp H-Series Compute nodes: metrics are not gathered by by default - it requires read-only access to the compute node IPMI interface, manual deployment of collectd VM or container (see the config-examples directory and FAQs) and potentially modifications to the dashboards to make them usable)

## Changes in v0.6.1

- Fix for the bad dedupe factor formula (issue #3) in .v6
- Prior to v0.7, sfcollector used latest version of base OS, so there's a risk to rebuilding containers as base OS updates may break sfcollector
- If you want to try, download branch [v0.6.1](https://github.com/scaleoutsean/hcicollector/tree/v0.6.1) and rebuild, or just apply the [change](https://github.com/jedimt/hcicollector/compare/master...scaleoutsean:v0.6.1) to existing sfcollector/solidfire_graphite_collector.py and rebuild only that container (sfcollector)

## Changes in .v6

- Changed file layout to be more consistent with container names and roles
- Retooled for Grafana 5.0.0
- Dashboards and datasources are now automatically added through the new provisioning functionality in Grafana 5
- Removed the external volume for the Grafana container, only Graphite uses an (optional) external iSCSI volume for persistent data
- Added the ability to poll for active alerts in the "SolidFire Cluster" dashboard.
- Added support for email alerting based on SolidFire events. Note: alerting queries do not support templating variables so if you have multiple clusters you will need to use `*` for the cluster instance instead of the `$Cluster` variable. The net effect of this is that the alert pane will show alerts from ALL clusters instead of an individually selected cluster.
- New detailed install document
- Added a very basic installation script

## Changes in .5

- Extensive dashboard updates. Dashboards now available on [grafana.com](https://grafana.com/dashboards?search=HCI)
- Added additional metrics to collection
- Updated to Trident from NDVP for persistent storage

## Changes in .4

- Added a vSphere collectored based heavily on the work of cblomart's vsphere-graphite collector
- Dashboard updates
- New dashboards for vSphere components

## Changes in .3

- Changed the collector container to Alpine which dramatically cut down container size and build time.
- Other minor changes

## Changes in .v2

- Added "&" in wrapper.sh script to make the collector calls async. Previously the script was waiting for the collector script to finish before continuing the loop. This caused the time between collections to stack which caused holes in the dataset. Now stats should be returned every minute
- Changed graphs to use the summerize function for better accuracy

## Changes in .v1

- Initial release

