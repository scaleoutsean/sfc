# Dashboards

- [Dashboards](#dashboards)
  - [Grafana version](#grafana-version)
  - [Grafana Data Source](#grafana-data-source)
  - [Aliasing or replacing Grafana's labels](#aliasing-or-replacing-grafanas-labels)
  - [Overcoming long updates of certain measurements](#overcoming-long-updates-of-certain-measurements)
  - [Measurements](#measurements)
    - [QoS Histograms](#qos-histograms)
  - [Reference InfluxQL queries and dashboard examples SFC](#reference-influxql-queries-and-dashboard-examples-sfc)
    - [Notes](#notes)
    - [Account efficiency (`account_efficiency`)](#account-efficiency-account_efficiency)
    - [Accounts (`accounts`)](#accounts-accounts)
    - [Cluster capacity (`cluster_capacity`)](#cluster-capacity-cluster_capacity)
    - [Cluster faults (`cluster_faults`)](#cluster-faults-cluster_faults)
    - [Cluster performance (`cluster_performance`)](#cluster-performance-cluster_performance)
    - [Cluster version (`cluster_version`)](#cluster-version-cluster_version)
    - [Drive stats (`drive_stats`)](#drive-stats-drive_stats)
    - [Node performance (`node_performance`)](#node-performance-node_performance)
    - [iSCSI connections (`iscsi_sessions`)](#iscsi-connections-iscsi_sessions)
    - [QoS Histograms (`histogram_*`)](#qos-histograms-histogram_)
    - [Snapshots (`snapshots`)](#snapshots-snapshots)
    - [Sync jobs (`sync_jobs`)](#sync-jobs-sync_jobs)
    - [Volume efficiency (`volume_efficiency`)](#volume-efficiency-volume_efficiency)
    - [Volumes (`volumes`)](#volumes-volumes)
    - [Volume performance (`volume_performance`)](#volume-performance-volume_performance)


## Grafana version

Grafana v11.0.0 was used in the development of SFC v2, but SFC has no dependencies or plugins that depend on Grafana 11.

Several recent Grafana major versions support InfluxDB v1 and since SFC doesn't come with dashboards, any recent version ought to work. All it needs is to connect to InfluxDB v1.

If reference dashboard or queries don't work with latest release of grafana, please import the dashboard and try different panel settings or queries. 


## Grafana Data Source

How to create an InfluxDB source in Grafana 11:

- Go to `Sources` > `Add data source`
- Pick `InfluxDB`
- Give the new source a name such as `sfc` (for SolidFire Collector)
- Query language: `InfluxQL` (for InfluxDB v1)
- `HTTP` > `URL`: if InfluxDB is running locally, `http://localhost:8086`, in Docker Compose you may use `http://influxdb:8086`, if elsewhere then `http://some.host.com.org:58086`, etc.
- Scroll all the way to the bottom, click `Save & Test`

You *may* add other complex settings and secure InfluxDB, but SFC is written with the idea that it connects to InfluxDB within same Kubernetes or Docker namespace or same host, so you may need to modify SFC to use HTTP(S) and/or add authentication when connecting InfluxDB. I expect most SFC users will use Docker Compose, Kubernetes or local VM, where HTTP is fine.


## Aliasing or replacing Grafana's labels

Certain parts of Grafana are hard to use.

Personally I find the difficulty of aliasing data in labels the worst. Below in Account Efficiency, there's an example on how to do that. The same general technique works for other metrics below. The Grafana Web site and Community have additional approaches and workarounds.


## Overcoming long updates of certain measurements

As explained elsewhere, SFC uses three schedules for high, medium and low-frequency of data collection. 

- First, the idea is that one is *unlikely* to have high- and low-frequency metrics in the same dashboard, but if they do, then they won't need to zoom to less than 15-60 minute windows
- Second, most users who do need to zoom to 1-15 minute segments will want to do that only for a subset of data and a best practice for this is to not have all panels zoomable to that level

You may consider this approach:

- One frequently-refreshing short-time interval dashboard with volumes, cluster faults, possibly mixed with some other metrics (network, hypervisor) from your environment
- Another dashboard for storage management - 1 hour to 30 day zoom level - to deal with QoS, storage utilization trends, etc.

Of course, nothing prevents you from having everything in one dashboard, but what happens is if you zoom to a 10 minute segment, many panels will have `No data` since SFC sends updates every 15-60 minutes. That's mostly okay since you're not interested in those panels anyway (you wouldn't be zooming if you were), but if you want to prevent that for general users, you can create a dashboard with some limitations

- Go to your SFC dashboard's Settings
- Scroll down to `Time options` > `Auto refresh` and enter a list of higher-duration values such as `30m,1h,2h,4h,8h,12h,1d,7d,28d`
- Just below, optionally enable `Hide time picker` 
- Save your "slow" dashboard using a pre-set time-range set to reasonable value:
  - Select reasonable time range (e.g. 2 days) for your users
  - Click on the little floppy disk icon to save your slow dashboard and select `Save current time range as dashboard default`


## Measurements

This is what's collected by default. Volume properties and statistics are collected frequently (60s by default) while the rest may have medium or low frequency of collection. See the main README.md or the source code for more.

- account_efficiency
- accounts
- cluster_capacity
- cluster_faults
- cluster_performance
- cluster_version
- drive_stats
- iscsi_sessions
- node_performance
- sfc_metrics
- volume_efficiency
- volume_performance
- volumes


### QoS Histograms

QoS histograms are *not* collected by default. You may enable QoS histogram collection with a switch (`sfc.py -h`). 

- histogram_below_min_iops_percentages
- histogram_min_to_max_iops_percentages
- histogram_read_block_sizes
- histogram_target_utilization_percentage
- histogram_throttle_percentages
- histogram_write_block_sizes

These metrics correspond to the names from the SolidFire API, so you can refer to the SolidFire documentation. 

SFC changes names of histogram buckets to be Grafana-friendly, but it's easy to tell which SFC bucket name corresponds to the original bucket name from the original histogram object.


## Reference InfluxQL queries and dashboard examples SFC

### Notes

Some queries here and also in reference [dashboard.json](./dashboard.json) have an unnecessary `alias` in them, as I'm currently experimenting with that feature. That doesn't mean it should be used, or that I recommend it.

Some queries are set to use `last`, others `mean`. In some cases `last` is used because that's what I wanted while working on SFC. For example, in cluster faults I don't want `mean` of 0s (no problem) and 1s (unresolved fault). Where `mean` is used it may be only because that's what Grafana does by default. In other cases maybe I have `last` simply because I wanted to see if the code was working properly, but normally I'd use `mean`. And finally, there may be cases where you'd want something different, so feel free to modify any and all queries to suit your needs.

Reference dashboard contains all queries mentioned below, so you don't need to copy-paste them into Grafana if you import my dashboard and set it to your source. If any of the queries below doesn't work (maybe I made typo while formatting, etc.), you can get it from dashboard.json since that file is dumped from Grafana without any changes.

### Account efficiency (`account_efficiency`)

Storage efficiency is pre-created and we can get account-level storage efficiency (product of compression and deduplication for all volumes owned by a tenant) with this SQL query.

```sql
SELECT mean("storage_efficiency") FROM "account_efficiency" 
  WHERE $timeFilter GROUP BY time($__interval), "name"::tag
```

If you were you select two values - `compression` and `deduplication` - and use Stat, Grafana may show nonsense metric labels.

```sql
SELECT mean("compression"), mean("deduplication") 
  FROM "account_efficiency" 
  WHERE $timeFilter 
  GROUP BY time($__interval), "id"::tag fill(null)
```

- The above will make Stat show junk like `account_efficiency.mean { id: 1 }` above each metric
- What you *want* to see is `1` (i.e. just the account ID)
  - In SQL query area go to `Transform data` tab, add `Rename fields by regex` transformation and then
  - Match: `account_efficiency.mean { id: (.*) }` 
  - Replace with: `Account ID $1`


"Group by" can also use (account) name, in which case the above would still work, just use `{ name: (.*) }` instead of ID-based search in regex transformation.

```sql
SELECT mean("compression"), mean("deduplication") 
  FROM "account_efficiency" 
  WHERE $timeFilter 
  GROUP BY time($__interval), "name"::tag fill(null)
```

![Account storage efficiency](../images/sfc-example-dashboard-01-account-storage-efficiency.png)


### Accounts (`accounts`)

```sql
SELECT mean("volume_count") FROM "accounts" 
  WHERE $timeFilter 
  GROUP BY time($__interval), "name"::tag fill(null)
```

These have just few basic properties of storage accounts (tenants). 

The above example shows volume count by tenant, which may be useful if you are in an environment where volume count or connection count is close to the SolidFire maximums. You may have 10 Kubernetes clusters, for example, where each instance of Trident uses a separate account and has 200-300 volumes.

![Account storage efficiency](../images/sfc-example-dashboard-02-account-volumes-per-tenant.png)

If you want to produce a simple "table"-like list of your accounts, consider using Bar Gauge with this query:

```sql
SELECT last("volume_count") FROM "accounts" 
  WHERE $timeFilter 
  GROUP BY time($__interval), "name"::tag, "id"::tag fill(null) 
  LIMIT 1
```

`LIMIT 1` is the key that makes table show faster.

This screenshot is large, but in my dashboard the panel is very small. When I show (another panel with) accounts as IDs, I can look them up in a smaller panel on the side.

![Account - account ID to name mapping](../images/sfc-example-dashboard-03-account-id-to-name-mapping.png)

### Cluster capacity (`cluster_capacity`)

Almost all useful details from SolidFire's GetClusterCapacity are passed to InfluxDB.

```sql
SELECT mean("active_sessions") FROM "cluster_capacity" 
  WHERE $timeFilter 
  GROUP BY time($__interval) fill(null)
```

![Cluster capacity - recent IO size](../images/sfc-example-dashboard-03-cluster-capacity-recent-io-size.png)


### Cluster faults (`cluster_faults`)

```sql
SELECT mean("warning") FROM "cluster_faults" 
  WHERE $timeFilter 
  GROUP BY time($__interval) fill(null)
```

You may create one panel that gets of those and groups them, or create several panels (one for each level).

```sql
# query A 
SELECT last("warning") AS "alias" FROM "cluster_faults" WHERE $timeFilter GROUP BY time($__interval)
# query B
SELECT last("error") FROM "cluster_faults" WHERE $timeFilter GROUP BY time($__interval)
# query C
SELECT last("critical") FROM "cluster_faults" WHERE $timeFilter GROUP BY time($__interval)
# query D
SELECT last("bestPractices") FROM "cluster_faults" WHERE $timeFilter GROUP BY time($__interval)
```

That should show something like this:

![Cluster faults](../images/sfc-example-dashboard-05-cluster-faults.png)


### Cluster performance (`cluster_performance`)

The SolidFire API method calls these "cluster stats". I call them cluster performance.

```sql
SELECT mean("normalized_iops") FROM "cluster_performance" 
  WHERE $timeFilter 
  GROUP BY time($__interval) fill(null)
```

There's a whole bunch of fields in here and the above shows just one of them `normalized_iops`. The names correspond to the keys from the SolidFire method.

As you can see here, there's nothing going on in my environment and I didn't even change legend, but you get the idea.

![Cluster performance - normalized IOPS](../images/sfc-example-dashboard-06-cluster-performance.png)


### Cluster version (`cluster_version`)

This is a simple one, just to keep an eye on the API and software version and also the cluster name (`PROD`, below). That's important for multi-cluster environments and/or if you collect data from multiple clusters into the same InfluxDB.

```sql
> select * from cluster_version
name: cluster_version
time                 api_version name version
----                 ----------- ---- -------
2024-05-26T10:27:06Z 12.5        PROD 12.5.0.897
```

This I don't visualize, as it's not necessary for people with one cluster (not to mention SolidFire has been end-of-sale'd so it's not like anyone will fall behind when it comes to software updates). The purpose of collecting this measurement is to get the cluster name (`PROD` in my case) which is inserted into other measurements. 

People who have a bunch of clusters and are slow to update may want to gather these, but by now I assume everyone is on latest version because updates are rare.


### Drive stats (`drive_stats`)

I develop SFC on SolidFire Demo VM so I can't produce meaningful drive statistics, but here's what's collected:

```sql
> select * from drive_stats
time                 activeSessions cluster drive_id iosInProgress lifeRemainingPercent powerOnHours
----                 -------------- ------- -------- ------------- -------------------- ------------
2024-05-26T10:27:06Z 3              PROD    1        0             0                    0
2024-05-26T10:27:06Z                PROD    4        0             0                    0
2024-05-26T10:27:06Z                PROD    3        0             0                    0
2024-05-26T10:27:06Z                PROD    2        0             0                    0

```

Active session metric exists on metadata disks, while the other three metrics included apply to all.

One can't get meaningful lifeRemainingPercent and powerOnHours in a VM so I won't share a screenshots. In physical environments these may be useful for long-term maintenance.

Note that lifeRemainingPercent really means (100-lifeRemainingPercent), i.e. it means the opposite from what it says. 15 means 85% remains. I didn't want to transform this value to (100-lifeRemainingPercent) in order to avoid confusion - the figure here is the same (misleading) number that you get from the SolidFire API.


### Node performance (`node_performance`)

You may find these in the API as "node stats".

```sql
SELECT mean("cpu") FROM "node_performance" 
  WHERE $timeFilter 
  GROUP BY time($__interval) fill(null)
```

I guess nodes' stats may be mildly useful if suspecting major imbalance in volumes. The example above shows `cpu` value.

![Node performance - CPU utilization](../images/sfc-example-dashboard-07-node-performance-cpu-utilization.png)

Most of the stuff in the API response isn't useful so in addition to CPU, only two other metrics are collected:
- networkUtilizationCluster
- networkUtilizationStorage

File an issue if you need more and I'll see what I can do. Or submit a pull request.


### iSCSI connections (`iscsi_sessions`)

```sql
SELECT mean("ms_since_last_scsi_command") FROM "iscsi_sessions" 
  WHERE $timeFilter 
  GROUP BY time($__interval) fill(null)
```

This example shows milliseconds since last client's SCSI command, which Windows clients send approximately every 45s-50s. This can be used to find dead clients and unused disks.

![iSCSI connections - time since last SCSI command](../images/sfc-example-dashboard-08-iscsi-connections-seconds-since-last-scsi-command.png)

There are 2-3 other metrics such as session instance and service ID (could be MD service on SolidFire). Generally these aren't that actionable but may be used to visualize client connectivity across cluster nodes.


### QoS Histograms (`histogram_*`)

I've tried hard to find a way to use this information, and haven't been successful so far. Histograms are by default disabled as I'm not certain of their usefulness, but you may enable them from the CLI (`-h`) and try to figure them out (histogram_below_min_iops_percentages and histogram_min_to_max_iops_percentages).

Write block sizes visualized using Time Series:

```sql
SELECT "b_000512_to_004095", "b_004096_to_008191", "b_008192_to_016383", "b_016384_to_032767", "b_032768_to_65535", "b_065536_to_131071", "b_131072_plus" 
  FROM "histogram_write_block_sizes" 
  WHERE ("id"::tag = '134') AND $timeFilter 
  GROUP BY "id"::tag
```

![Volume QoS Histogram - write block size for a volume](../images/sfc-example-dashboard-08-volume-qos-histograms-write-block-sizes.png)

You can't see much unless you hover over the graph and then you'd see data points broken down by request size (0.5 to 4 KiB, 4-8 KiB, etc.). But you can see that one band or bucket (shown in yellow) occupies almost 50% of all IO. That's 4-8 KiB requests, and this client is (an idle) MS SQL Server 2022.

This example is for Heatmap from the same QoS histogram.

```sql
SELECT last("b_01_to_19") 
  AS "alias", last("b_20_to_39") 
  AS "alias", last("b_40_to_59") 
  AS "alias", last("b_60_to_79") 
  AS "alias", last("b_80_to_100") 
  AS "alias" FROM "histogram_below_min_iops_percentages" 
  WHERE ("id"::tag = '134') AND $timeFilter 
  GROUP BY time($__interval)
```

This is why I consider QoS Histograms experimental - until I understand what this below means, I see no point in collecting that data and wasting disk space. Deep-colored vertical orange bars mean most counts were low percentage numbers. But does that mean that most time was spent between Min and Max (histogram_min_to_max_iops_percentages) or that within time spent below Min IOPS, most of it was 01-19% of Min IOPS? I don't know.

![Volume QoS Histogram - write block size for a volume](../images/sfc-example-dashboard-09-volume-qos-histograms-time-below-min-iops.png)

### Snapshots (`snapshots`)

TODO - not yet implemented. 

There are two tasks here, one is plain snapshots (name, ID, retention, etc.) and the other is replicated snapshots, where there's more detail about replication relationship, replication delay, state, etc. 

Pull requests are welcome.

### Sync jobs (`sync_jobs`)

This one is "special". 

First, SFC currently parses only one type of SolidFire sync job, remote sync used for initial replication (and re-sync).

Second, in my observation you can view these only on the cluster where replication is *in*-bound. If you have replication flowing in one direction, I think you can get these details only at the destination.

Below `cluster::tag = 'DR'` is for that. Use the right name of the cluster that is a destination (of volume replication).

```sql
SELECT last("remaining_time") FROM "sync_jobs"
  WHERE ("cluster"::tag = 'DR') AND $timeFilter 
  GROUP BY time($interval), "dst_volume_id"::tag 
  ORDER BY time DESC
```

Third, if network is fast or volumes small, you may rarely see these jobs even though they're gathered every 60 seconds. For example, I paused and resumed replication half a dozen times here and only once did I see it in Grafana.

![Sync jobs](../images/sfc-example-dashboard-16-sync-jobs.png)

Fourth, notice that remaining time may be 0, so Grafana won't show anything (well, showing 0s in this panel may help as long as NaN isn't shown as 0). In any case, this is normal - SolidFire may be comparing changes but not yet copying, so there's no way to give a meaningful time remaining, while the next time SFC checks, the job is done and gone.

```sql
> select * from sync_jobs
name: sync_jobs
time                 blocks_per_sec cluster dst_volume_id elapsed_time pct_complete remaining_time    stage type
----                 -------------- ------- ------------- ------------ ------------ --------------    ----- ----
2024-06-15T14:48:40Z 101968         DR      11            1            31           2.225806451612903 data  remote
2024-06-15T15:13:44Z 20404          DR      10            87           0            0                 data  remote
2024-06-15T15:14:44Z 20404          DR      10            87           0            0                 data  remote
2024-06-15T15:22:44Z 60269          DR      11            6            0            0                 data  remote
```

Fifth, the example above is for "time remaining". You may select other fields which may be more useful to you.

### Volume efficiency (`volume_efficiency`)

Here I simply select all three efficiency-related properties and visualize them using Stat.

```sql
SELECT mean("compression"), mean("deduplication") 
  FROM "volume_efficiency" 
  WHERE $timeFilter 
  GROUP BY time($__interval), "id"::tag fill(null)
```

Volume compression multiplied by volume deduplication give us what's commonly known as "storage efficiency factor". (Most people don't consider Thin Provisioning to be part of this). 

While that can be done in Grafana, this metric is generated by SFC and while not present in the API it is available in this measurement, so if you want to get that without fiddling with Grafana you can query it.

```sql
SELECT mean("storage_efficiency") 
  FROM "volume_efficiency" 
  WHERE $timeFilter 
  GROUP BY time($__interval), "id"::tag fill(null)
```

![Volume storage efficiency - by volume ID](../images/sfc-example-dashboard-11-volume-efficiency-storage-efficiency-by-volume-id.png)

### Volumes (`volumes`)

These container volume properties including volume names. Other metrics may have volume names in them because SFC gets the names this way and inserts them into other measurements.

Here's a less common example - a query for a Stat visualization for QoS policy IDs:

```sql
SELECT mean("qos_policy_id") FROM "volumes" 
  WHERE $timeFilter 
  GROUP BY time($__interval), "name"::tag fill(null)
```

This can be useful if you want to enforce the use of QoS Policy IDs - which is preferable over "custom" settings for each volume, and generally seeing how many volumes use which QoS Policy. It also shows those that don't have it set (`0`), which may be common in containerized environments.

![Volumes - by volume QoS Policy ID](../images/sfc-example-dashboard-12-volume-properties-qos-by-volume-id.png)

Another use case is in multi-cluster scenarios where you may want to apply settings to a volume replica.

Basic volume pairing information is collected as well. By basic I mean that only the first pairing is analyzed, and not all details are included to avoid problems with parsing and typing. Most users don't have more than one pairing per volume and three clusters would be required to try and test, so the number of monitored relationships (which is one) per volume is unlikely to grow.

Field/tag assignment may change if necessary, but at least initially this is one example of how to use it.

```sql
SELECT last("remote_replication_mode") FROM "volumes" 
  WHERE $timeFilter 
  GROUP BY time($__interval), "name"::tag fill(null)
```

![Volumes - by replication mode](../images/sfc-example-dashboard-13-volume-properties-replication-mode.png)

You can try different visualizations, of course. This one shows 6 volumes, although only 3 are being replicated. How's that possible? Well, I started monitoring both sides (two clusters) to view sync job progress, and suddenly I saw six volumes. My query above is not limited to any specific cluster name (tag), so as soon as two sites started sending in data, the panel changed from showing three volumes to showing six. Of course, you can adjust this to filter by site or show each site in a different panel, etc.

![Volumes - by replication mode](../images/sfc-example-dashboard-15-volume-replication-mode-async-snapshotsonly.png)

Replication monitoring is new in SFC v2 and based on feedback the details may be changed. Currently it is limited to the just two clusters, i.e. only the first replication relationship for a volume is captured, parsed and stored. If a volume has more than one pair, SFC will ignore the rest.

If you're interested in these details, see [this](https://scaleoutsean.github.io/2024/06/15/sfc-adds-volume-replication-monitoring.html) for more on the initial implementation and [this](https://scaleoutsean.github.io/2024/06/14/netapp-solidfire-replication-monitoring.html) for API-related background and various considerations. The SolidFire API returns descriptive strings, and SFC stores numbers. For example: Async gets stored as 1, Sync as 2, SnapshotsOnly as 3, in InfluxDB. For replication states, there's a bunch of them, and the up-to-date mapping can be found in the SFC source code. Where 0 values could be confusing as numeric proxies for `null` or `None`, I use `-1`. So if you see `-1` somewhere related to replication, that's usually "not configured" i.e. the volume isn't even paired. Then you can filter out such values (lower than 0) in queries and/or Grafana.

For the monitoring of initial replication sync ("baseline copy") we need to [use `ListSyncJobs`](https://scaleoutsean.github.io/2024/06/14/netapp-solidfire-replication-monitoring.html) which is available in [Sync jobs](#sync-jobs-sync_jobs).

### Volume performance (`volume_performance`)

Volume performance metrics are what you'd expect. The API calls them volume stats.

```sql
SELECT mean("actual_iops") FROM "volume_performance" 
  WHERE ("name"::tag = 'data') AND $timeFilter 
  GROUP BY time($__interval), "name"::tag fill(null)
```

This is like in the SolidFire API response, but with volume names added. Personally I prefer to pick a handful volumes - for which I usually know the ID - and just watch these few in a panel named after my important application.

```sql
SELECT mean("average_io_size"), mean("actual_iops") 
  FROM "volume_performance" 
  WHERE ("id"::tag = '134') AND $timeFilter 
  GROUP BY time($__interval), "name"::tag fill(null)
```

This example shows stats for volume ID 134 (mostly idle, except for when I started the VM and SQL Server came to life).

![Volume performance - average IO size and actual IOPS for volume ID 134](../images/sfc-example-dashboard-10-volume-performance-average-io-size-and-actual-iops.png)

Query I use in a Bar Gauge visualization:

```sql
SELECT mean("burst_io_credit") FROM "volume_performance" 
  WHERE $timeFilter 
  GROUP BY time($__interval), "name"::tag fill(null)
```

It shows how much burst credit each volume has.

![Volume performance - Burst IOPS credit in 4 KiB requests](../images/sfc-example-dashboard-12-volume-performance-burst-iops-by-volume-id.png)

If burst credit is needed by some critical application, it may be wise to tighten MaxIOPS on volumes which don't need a lot of burst credits. That way when a volume does burst, it eliminates the risk of having some random app also burst and take away from what's actually available in terms of burst-able IOPS on the node.

Finally, remember that burst credits on a volume are accumulated when iSCSI client doesn't consume Max IOPS. That is, consuming 900 IOPS on a volume with the QoS set to (50,1000,2000) means in 90 seconds the client will accumulate 90 x (1000-900) = 9,000 Burst IOPS (in 4 KiB requests). 

If a Web server rotates logs when they reach 100 MiB and compresses those by writing them out in 1 MiB requests, 9,000 in 4 KiB may [translate](https://docs.netapp.com/us-en/element-software/concepts/concept_data_manage_volumes_solidfire_quality_of_service.html#qos-performance) to a fraction of that value (let's say 2%, which is 180, enough for 180 x 1MiB requests) which in turn means this burst budget is enough to read a 100 MiB log file (access.log.1) and gzip it to disk as a 35 MB access.log.gz without getting throttled. You can also find appropriate values experimentally by looking at volume utilization percentage or one of the QoS histograms.

Huge burst credit on a volume may mean the volume MaxIOPS setting is too generous. Sometimes that's the idea, but other times that may be wasteful. If there's no problem, there's no need to worry about this, but when it is a problem being able to see this can be helpful.

Volume async replication delay is a property in volume performance measurement. It exists *only* for volumes that are in async replication mode and it's shown only for the source, not the target, volume.

```sql
SELECT last("async_delay") FROM "volume_performance" 
  WHERE ("async_delay"::field > -1) AND $timeFilter 
  GROUP BY time($interval), "name"::tag
```

Stat panels work well for this, but we can also watch async delay over time. 

Where 0 is used (e.g. async delay) is 0 seconds. To avoid confusion with volumes that aren't even a source of replication, all non-replicating volumes get `-1` here, so just eliminate such volumes from panels when working in Grafana.

![Volume async replication delay](../images/sfc-example-dashboard-14-volume-async-replication-delay.png)

Note that replicated snapshots, which are asynchronously replicated as well, are their own "feature" and you can't see snapshot replication delay in volume performance metrics. See [Snapshots](#snapshots-snapshots).

