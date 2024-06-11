# SFC - SolidFire Collector (formerly SolidFire-related component in HCI Collector)

- [SFC - SolidFire Collector (formerly SolidFire-related component in HCI Collector)](#sfc---solidfire-collector-formerly-solidfire-related-component-in-hci-collector)
  - [About project and repository name change (HCI Collector to SFC)](#about-project-and-repository-name-change-hci-collector-to-sfc)
  - [Requirements](#requirements)
  - [Quick start](#quick-start)
    - [CLI](#cli)
    - [Docker and orchestrators](#docker-and-orchestrators)
  - [Alternatives to SFC](#alternatives-to-sfc)
  - [FAQs](#faqs)
  - [Architecture](#architecture)
  - [Security](#security)
    - [How to upload TLS certificate to SolidFire](#how-to-upload-tls-certificate-to-solidfire)
    - [TLS certificates for OS and containers](#tls-certificates-for-os-and-containers)
      - [OS/VM level](#osvm-level)
      - [Containers](#containers)
    - [Create cluster admin with read \& reporting access](#create-cluster-admin-with-read--reporting-access)
  - [Data retention](#data-retention)
  - [Screenshots and demos](#screenshots-and-demos)
  - [Metrics](#metrics)
  - [Dependencies](#dependencies)
  - [History of SFC](#history-of-sfc)
  - [License and Trademarks](#license-and-trademarks)


SFC is a metrics collection script for SolidFire storage systems running Element OS v12.5 or newer v12.


## About project and repository name change (HCI Collector to SFC)

Prior to NetApp's acquisition of SolidFire SolidFire Collector gathered only SolidFire metrics. After that the project was expanded wth 3rd party packages for vSphere monitoring and renamed to HCI Collector. 

With version 2.0.0 SFC returns to its original scope - completely rewritten and with big improvements over SFC from HCI Collector and earlier. [Here](#history-of-sfc) you may view more details about previous versions and contributors.

Latest NetApp HCI-focused version (HCI Collector v0.7.2) - can be found [here](https://github.com/scaleoutsean/sfc/tree/v0.7.2) for those who for some reason need it, but I wouldn't recommend it even to NetApp HCI users: for NetApp HCI I recommend using SFC v2 or one of the alternatives below and addressing vSphere (or KVM, Hyper-V, etc.) separately.


## Requirements

- Environment
  - SolidFire 12+ or equivalent (NetApp HCI, NetApp eSDS)
  - Python 3.10-3.13 with module dependencies installed or a container platform that can run pre-packaged containers
  - InfluxDB OSS v1
  - Grafana 11 (older versions may work as well; SFC v2 has no direct or indirect connection to Grafana)
- New hard requirements for SolidFire environments that did not exist in HCI Collector
  - **Unique** volume names - this is not enforced by SolidFire API since volume IDs are unique by default. Most people don't use duplicate volume names because it's confusing, but if you happen to have duplicate volume names, don't use SFC
  - Volume names must **not be be integers** - volume name should have at last one alphabet character at the beginning
  - SFC no longer attempts to "solve" the problem of accepting invalid **TLS certificates**. If you want to use SFC v2, please deploy a valid certificate to your SolidFire or import your certificate chain to the OS or container SFC is running on. Or you can change the source code to get around the requirement for valid TLS certificates.

The new "hard" requirements was introduced because neither volume IDs nor duplicate alphanumeric names make sense in dashboards that visualize more than a handful of volumes, which means almost 100% of users.

This isn't a new, SFC-only idea. Various SolidFire integrations and automation tools for SolidFire have the same expectation (example: Ansible). If your environment has duplicate volume names, SFC may have errors or behave unpredictably, but you won't "lose SolidFire data" or anything like that; SFC only ever `read`s and `list`s SolidFire API objects. 


## Quick start

- Create a read- and reporting-only admin account on SolidFire (see in [Security](#security) if you don't know how). If using existing InfluxDB, ask for access to a new `sfc` database. By default InfluxDB v1 allows creation of new databases and SFC automatically creates it if it does not exist, so you don't have to do anything in InfluxDB if you deploy your own using default container settings for InfluxDB OSS v1 - just make sure it's running and reachable by SFC
- SFC:
  - Non-containerized: install SFC's dependencies with Python pip (see requirements.txt), make sure TLS certificate on SolidFire is accepted (use curl or something) and run `sfc.py -h`.
  - Containerized: set variables (MVIP, USERNAME, etc.) in YAML or env var or file and deploy. **If your SolidFire does not have a valid TLS certificate**, you will need to copy it into the container to be visible to Python. Refer to generic Python-in-Docker instructions.
- See [dashboards.md](./docs/dashboards.md) about visualization and metrics.


### CLI

```sh
git clone https://github.com/scaleoutsean/sfc
cd sfc
python3 -m pip install -r requirements.txt
# with InfluxDB OSS v1 at 192.168.50.184:32290, database 'sfc' will be automatically created by SFC
python3 ./sfc.py --mvip 192.168.1.30 -u monitor -p ******* -ih 192.168.50.184 -ip 32290 -id sfc
```

If you want something different, try `-h` or hard-code the vars at the top of the script for a test run and try with just `python3 ./sfc.py` (and nothing else).

```sh
$ python ./sfc.py -h
usage: sfc.py [-h] [-m [MVIP]] [-u [USERNAME]] [-p [PASSWORD]] [-ih [INFLUXDB_HOST]] [-ip [INFLUXDB_PORT]] [-id [INFLUXDB_NAME]] [-fh [HI]] [-fm [MED]] [-fl [LO]] [-ex] [-ll [{DEBUG,INFO,WARNING,ERROR,CRITICAL}]] [-lf [LOGFILE]]

Collects SolidFire metrics and sends them to InfluxDB.

options:
  -h, --help            show this help message and exit
  -m [MVIP], --mvip [MVIP]
                        MVIP or FQDN of SolidFire cluster from which metrics should be collected. Default: 192.168.1.30
  -u [USERNAME], --username [USERNAME]
                        username for SolidFire array. Default: monitor
  -p [PASSWORD], --password [PASSWORD]
                        password for admin account on SolidFire cluster. Default: monitor123
  -ih [INFLUXDB_HOST], --influxdb-host [INFLUXDB_HOST]
                        host IP or name of InfluxDB. Default: 192.168.50.184
  -ip [INFLUXDB_PORT], --influxdb-port [INFLUXDB_PORT]
                        port of InfluxDB. Default: 32290
  -id [INFLUXDB_NAME], --influxdb-name [INFLUXDB_NAME]
                        name of InfluxDB database to use. SFC creates it if it does not exist. Default: sfc
  -fh [HI], --frequency-high [HI]
                        high-frequency collection interval in seconds. Default: 60
  -fm [MED], --frequency-med [MED]
                        medium-frequency collection interval in seconds. Default: 600
  -fl [LO], --frequency-low [LO]
                        low-frequency collection interval in seconds. Default: 3600
  -ex, --experimental   use this switch to enable collection of experimental metrics such as volume QoS histograms (interval: 600s, fixed). Default: (disabled, with switch absent)
  -ll [{DEBUG,INFO,WARNING,ERROR,CRITICAL}], --loglevel [{DEBUG,INFO,WARNING,ERROR,CRITICAL}]
                        log level for console output. Default: INFO
  -lf [LOGFILE], --logfile [LOGFILE]
                        log file name. SFC logs only to console by default. Default: None

Author: @scaleoutSean https://github.com/scaleoutsean/sfc License: the BSD License 3.0

```


### Docker and orchestrators

Feel free to build your own with sfc.py in it, or use my Dockerfile from the sfc directory to build your SFC container.

Or you can try this command using pre-built container, but **this will not work** if you don't have a valid TLS certificate on SolidFire MVIP! If you're using internal or self-signed CA, scroll down to Security section for a working recipe.

```sh
docker run --name=sfc docker.io/scaleoutsean/sfc:v2.0.0 --mvip 192.168.1.30 -u monitor -p ********** -ih 192.168.50.184 -ip 32290 -id sfc
```

Why is this so complicated now? 

Because SFC container built by *me* does not have *your* internal certificate or CA chain, so there's no way for me to make this problem go away except by making it possible to accept invalid certificates, which SFC v2 won't do. 


## Alternatives to SFC

- [SolidFire Exporter](https://github.com/mjavier2k/solidfire-exporter/) - Prometheus exporter
  - [Getting started with SolidFire Exporter](https://scaleoutsean.github.io/2021/03/09/get-started-with-solidfire-exporter.html)
- SolidFire syslog forwarding to Elasticsearch or similar platform (detailed [steps](https://scaleoutsean.github.io/2021/10/18/solidfire-syslog-filebeat-logstash-elk-stack.html))
- NetApp Cloud Insights (as-a-service which is free up to 7 day retention and paid above that)


## FAQs

I no longer maintain the SFC FAQs in this repo because I've never heard that anyone has the FAQs for HCI Collector v0.7.

Last version of old FAQs page for the NetApp HCI/vSphere-focused v0.7.x can be found [here](https://github.com/scaleoutsean/sfc/tree/v0.7.2/docs).


## Architecture

![SFC architecture](./images/sfc-architecture.svg)

You may use existing InfluxDB v1 instance or deploy a new one based on standard Docker Compose or Kubernetes templates for InfluxDB v1. SFC uses InfluxDB v1 with default configuration. 

Grafana has to be user-provided and dashboards created once InfluxDB is added as Grafana data source. See [dashboards](./docs/dashboards.md) for help with that.


## Security

- SolidFire TLS certificate
  - As mentioned above, going forward SFC won't assist users in circumventing HTTPS security. SFC may or may not reject invalid TLS certificates, but when it does that would not be considered a bug or issue for SFC to solve. If your SolidFire MVIP uses FQDN and has has a valid TLS certificate, at the very least you can run SFC out of a VM - just import TLS certificates so that Python can find them and that's it. Users of containerized SFC may need to prepare their SolidFire's certificate chain *or* certificate fingerprint of a self-signed SolidFire TLS (including those that use an IP address)
- SolidFire account used by SFC
  - If you want decent account security in SFC, use a dedicated SolidFire admin account with a Reporting-only (Read-only) role. Even the Reporting-only role has access to sensitive information (initiator and target passwords of your storage accounts are, well, read when account properties are queried, for example), but at least it cannot make modifications to SolidFire data (it only can `Get` and `List` API objects) so it can't change passwords to lock you out, or delete something. As a reminder, the sensitive information that read-only admin accounts can read if the password leaks is storage accounts' CHAP secrets, so you still need to guard it carefully
  - Where "sensitive" API methods are used (ListAccounts, for example), SFC removes CHAP credentials from the API response even though they are not used in any way (e.g. they are not sent to metrics database), but that lowers the risk of those secrets ending up in memory/kernel dump files
- SFC configuration file(s)
  - Docker Compose: SFC container configuration files may contain plain text passwords to the SolidFire API (also for the Web UI, since the username/password can be used for that purpose as well). You can consider using ENV variables, but you have to load them from somewhere, so that isn't much better. Still, if you do that, make sure they're not readable by others. If you have a vault service you can configure SFC container to get the password from vault service
  - Kubernetes and Nomad: SFC containers can use Kubernetes secrets or other source if you configure them
- SFC host/VM/container
  - Ensure that only administrator-level staff has access to your SFC host/VM/container namespace because of SFC account security and possibly .env file
  - Create a new user for SFC and limit access to .env and sfc.py to only that account. Better yet, use a vault service or Kubernetes secrets (not ideal, but probably better than plain text passwords in a VM)
  - Because SFC only needs to connect to SolidFire MVIP, host/VM/container can be connected only to SolidFire management network. sfc.py does not provide any external-facing service
- Network
  - SFC only connects to SolidFire to gather metrics which are then sent to InfluxDB. No other connections are required. SFC never attempts to connect to the Internet
- 3rd party containers and packages
  - Upstream containers (SFC base image, InfluxDB) are not audited or regularly checked for vulnerabilities by me. SFC doesn't run any external-facing service and InfluxDB is only accessed by Grafana. But feel free to inspect/update them on your own and use your own Influx and Grafana instances. SFC is built with fairly minimal dependencies, so that users can address vulnerabilities in 3rd party packages on their own

### How to upload TLS certificate to SolidFire

See this post on [how to upload TLS certificate to SolidFire using Postman](https://scaleoutsean.github.io/2020/11/24/scary-bs-postman-ssl-certs.html). The same can be done via the API or from SolidFire PowerShell Tools. It takes 5 minutes!

Optionally use a secure HTTPS reverse proxy with a valid certificate.

With SolidFire's certificate chain on the host available to SFC, even a self-signed TLS certificate can help you avoid MITM attacks.

### TLS certificates for OS and containers

This used to be "solved" by accepting whatever, but in 2024 that's no longer good enough. I don't have *your* valid or invalid certificate, so I can't "solve" it in SFC. 

Python (and by extension, SFC) needs to be able to validate SolidFire's TLS certificate. 

This has nothing to do with SFC, so please figure it out for your OS or container and [this is a great place to start](https://stackoverflow.com/a/39358282). A summary is offered below for your convenience.

#### OS/VM level

Python should reference OS CA locations so if you add certificates so that `openssl` works, Python (and SFC) may too. [(source)](https://stackoverflow.com/a/66258111).

I see this when connecting to SolidFire Demo VM which has a TLS issued by internal CA (i.e. "self-signed") using my development system. The OS has all (CA and SolidFire) certificates imported, so there's no problem when running SFC from the CLI. In the worst case you can take a Linux VM and run sfc.py in it without any special "engineering" efforts.

```sh
$ openssl s_client -connect 192.168.1.30:443 -showcerts < /dev/null
CONNECTED(00000003)
Can't use SSL_get_servername
depth=2 O = DataFabric, CN = DataFabric Root CA
verify return:1
depth=1 O = DataFabric, CN = DataFabric Intermediate CA
verify return:1
depth=0 CN = prod.datafabric.lan
verify return:1
---
Certificate chain
 0 s:CN = prod.datafabric.lan
   i:O = DataFabric, CN = DataFabric Intermediate CA
   a:PKEY: rsaEncryption, 2048 (bit); sigalg: ecdsa-with-SHA256
   v:NotBefore: May  3 15:50:40 2024 GMT; NotAfter: Aug  1 15:51:40 2024 GMT
   ...

```

#### Containers

Validated Docker Compose and Kubernetes recipes are a TODO item, so for now please try these instructions or use a VM. 

How to tell if you have a problem:

```sh
$ docker run --name=sfc docker.io/scaleoutsean/sfc:v2.0.0 --mvip 192.168.1.30 -u monitor -p ********** -ih 192.168.50.184 -ip 32290 -id sfc
Exception: Cannot connect to host 192.168.1.30:443 ssl:True [SSLCertVerificationError: (1, '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1007)')]
```

This means you need to add the CA or the entire chain to *your* container by yourself or mount the OS path where you have it into your container.

One of the ways to solve it is to copy your certificate chain into the container when building it. See sfc/Dockerfile for details. I tested the code without CA chain copied to it (fails, as in the above output) and after (works).

Another way may be to mount a directory with your certificate, but you'd still have to run `update-ca-certificates` inside the container before starting SFC, so it seems like a more complicated approach - you'd have to do it from Python or change entry point to use shell (ash in Alpine Linux), update CA certificates and then run sfc.py. But this seems complicated, so I won't test this approach. 

Enterprise users should be able to get internal recipe and best practices for deploying containers with corporate CA chains - there's no need to reinvent the wheel and SFC doesn't invent or add any special requirements.


### Create cluster admin with read & reporting access

You can do it from the SolidFire UI, PowerShell Tools, Postman, etc. JSON-RPC request for Postman and such:

```json
{
    "method": "AddClusterAdmin",
    "params": {
        "username": "monitor333",
        "password": "**********************************",
        "access": ["read", "reporting" ],      
        "acceptEula": true },
    "id": 1
}
```

This should result in a new admin account created on your SolidFire cluster.

Notes:

- The minimum password length is 8 characters, but you should use a complex password (24+).
- This account does not have to be local to SolidFire - LDAP/ADS is available as well, but I don't have these services so I haven't tried. Please check the documentation for more on that and mind password rotation rules in LDAP/ADS if you use this option


![Reporting-only admin account on SolidFire](./images/solidfire-reporting-read-only-account-in-web-ui.png)


## Data retention

Currently it is set to 31 days because down-sampling hasn't been implemented yet.

SFC v2 aims to save resources. A SolidFire Demo VM (1 node, 4 disks, 32 volumes) made InfluxDB grow by less than 1 MB/day. Physical SolidFire cluster that creates 20 MB/day will still generate only 600 MB per month. Most SFC deployments should not consume more than 1 GB in on-disk space for InfluxDB.

If you need longer retention and don't know how to implement down-sampling in InfluxDB v1, you may simply change it in the code and remove InfluxDB container data (to let SFC re-create the DB with longer retention), just remember that 90 days of 1 minute metrics adds up for InfluxDB, Grafana and your browser. For example, showing a visualization 30 days of all metrics may require the entire database to be read off disk.

HCI Collector used Graphite database in which data down-sampling was trivial. In InfluxDB it sucks for multiple reasons: for example, averaging can easily result in meaningless down-sampled data, and Grafana dashboards can't easily handle down-sampled data either.

If you need longer retention and I may take a look at this again, let me know in Issues. The plan is to start using InfluxDB v3 as soon as it hits public beta - hopefully before end of calendar year 2024 - which should work better given how trivial SFC workload is. 


## Screenshots and demos

SFC v2.0 no longer includes Grafana dashboards, but there's a sample of a dashboard with documented InfluxQL queries.

See [dashboards.md](./docs/dashboards.md) on how to get started. [dashboard.json](./docs/dashboard.json) contains dashboard code for this sample screenshot (it assumes the InfluxDB source in Grafana is named `sfc`).

![Example SFC dashboard](./images/sfc-example.png)


## Metrics

HCI Collector suffered from excessive gathering of metrics in terms of both frequency and scope. That caused a variety of problems, perhaps not easy to notice, but still problems:

- Slow recovery after MVIP failover
- High load on the SolidFire API endpoint
- Fast database growth

SFC attempts to put and end to that and should be able to handle clusters with 1000 volumes or even more.

- Frequent metrics gathering is limited: several metrics are gathered every 60 seconds. Examples:
  - Account properties - these don't change often, but when they do we wish to know
  - Cluster faults - these need to be updated often
  - Volume properties - needed for performance monitoring and storage management purposes
  - Volume performance - performance monitoring is one of top use cases
- Medium and low frequency data: metrics that do not need to be collected every 60 seconds are collected at much higher intervals
  - Everything else including experimental metrics 
  - **NOTE:** when you build dashboards from these measurements, set dashboard time interval to 60 minutes (or longer) and wait, as you may otherwise see "No data" in Grafana until 61 minutes have passed. Or create two tiered dashboard system (see [dashboards.md](./docs/dashboards.md) for details)
- Because of different schedules and tasks, any stuck task (e.g. during MVIP failover) will fail on its own while others may fail or succeed on their own. Before a stuck task would stall all metrics gathering


## Dependencies 

SFC v2.0.0 attempts to minimize the use of external modules. Future v2 releases may take a more relaxed approach than v2.0.0, but the goal is to keep SFC simple, small, fast and secure.

Compared to previous version (HCI Collector v0.7), two top-level external libraries were removed and two added. Two main top-level dependencies are now APScheduler (for smarter scheduling) and aiohttp (the latter includes its own dependencies; you may view them with `pip list`, of course).


## History of SFC

I started contributing in 2019 and took over as the sole maintainer before v0.7.


- I took over before v0.7, released v0.7 and two security and compatibility updates. The main components used in HCI Collector during that time (up to HCI Collector v0.7.2) were as follows:
- [HCI Collector](https://github.com/jedimt/hcicollector/) from the period before I took over expanded scope 
  - [SolidFire SDK for Python](https://solidfire-sdk-python.readthedocs.io/)
  - [docker-graphite-statsd](https://github.com/graphite-project/docker-graphite-statsd) - Graphite and StatsD container by [Graphite](https://graphiteapp.org/). That documentation can be found [here](https://graphite.readthedocs.io/en/latest/releases.html)
  - [vsphere-graphite](https://github.com/cblomart/vsphere-graphite) - VMware vSphere collector for GraphiteDB
  - [Grafana](https://grafana.com)
- SolidFire Graphite Collector before NetApp's acquisition of SolidFire:
  - solidfire-graphite-collector.py - original SolidFire collector script by "cbiebers" (the Github account and repo were deleted at some point so I can't provide the URLs)

See [CHANGELOG.md](./CHANGELOG.md) for more details on HCI Collector and SFC software changes.

I sometimes [blog about SolidFire](http://scaleoutsean.github.io) and maintain curated SolidFire resources such as [Awesome SolidFire](http://github.com/scaleoutsean/awesome-solidfire), where you can find pointers to various SolidFire content and simple Python and PowerShell scripts.


## License and Trademarks

- `sfc.py` and related configuration and deployment files and scripts are licensed under the Apache License, Version 2.0
- External, third party containers, scripts and applications may be licensed under their respective licenses
- NetApp, SolidFire, and the marks listed at www.netapp.com/TM are trademarks of NetApp, Inc. Other marks belong to their respective owners
