#!/usr/bin/env python
# solidfire_graphite_collector.py
#
# Version 1.0.5
#
# Original authors: Colin Bieberstein, Aaron Patten
# Contributors: Pablo Luis Zorzoli, Davide Obbi, scaleoutSean
#
# Copyright (c) 2020 NetApp, Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import time
import graphyte
from solidfire.factory import ElementFactory
import solidfire.common
import logging


def send_cluster_faults(sfe, prefix):
    """
    send active cluster fault counts by: warning, error, critical
    exclude best practices, and only include current faults
    """
    fault_list = sfe.list_cluster_faults(False, "current").to_json()['faults']
    group = {'critical': 0, 'error': 0, 'warning': 0}
    for d in fault_list:
        if d['severity'] not in group:
            group[d['severity']] = 1
        else:
            group[d['severity']] += 1

    if to_graphite:
        for key in group:
            graphyte.send(prefix + '.fault.' + key, to_num(group[key]))
    else:
        for key in group:
            LOG.warning(prefix + '.fault.' + key + ' ' + str(group[key]))


def send_cluster_stats(sfe, prefix):
    """
    send a subset of GetClusterStats API call results to graphite.
    """
    metrics = ['clientQueueDepth', 'clusterUtilization', 'readOpsLastSample',
               'readBytesLastSample', 'writeOpsLastSample', 'writeBytesLastSample',
               'actualIOPS', 'latencyUSec', 'normalizedIOPS', 'readBytes',
               'readLatencyUSec', 'readOps', 'unalignedReads', 'unalignedWrites',
               'writeLatencyUSec', 'writeOps', 'writeBytes']

    cluster_stats_dict = sfe.get_cluster_stats().to_json()['clusterStats']

    clusterUtilizationDec = float(cluster_stats_dict['clusterUtilization'])
    clusterUtilizationScaled = clusterUtilizationDec

    if to_graphite:
        graphyte.send(prefix + '.clusterUtilizationScaled', to_num(clusterUtilizationScaled))
    else:
        LOG.warning(prefix + '.clusterUtilizationScaled ' + str(clusterUtilizationScaled))

    for key in metrics:
        if to_graphite:
            graphyte.send(prefix + '.' + key, to_num(cluster_stats_dict[key]))
        else:
            LOG.warning(prefix + '.' + key + ' ' + str(cluster_stats_dict[key]))


def send_cluster_capacity(sfe, prefix):
    """
    send a subset of GetClusterCapacity API call results and derived metrics to graphite.
    """
    metrics = ['activeBlockSpace', 'activeSessions', 'averageIOPS',
               'clusterRecentIOSize', 'currentIOPS', 'maxIOPS',
               'maxOverProvisionableSpace', 'maxProvisionedSpace',
               'maxUsedMetadataSpace', 'maxUsedSpace', 'nonZeroBlocks',
               'peakActiveSessions', 'peakIOPS', 'provisionedSpace',
               'snapshotNonZeroBlocks', 'totalOps', 'uniqueBlocks',
               'uniqueBlocksUsedSpace', 'usedMetadataSpace',
               'usedMetadataSpaceInSnapshots', 'usedSpace', 'zeroBlocks']

    result = sfe.get_cluster_capacity().to_json()['clusterCapacity']
    for key in metrics:
        if to_graphite:
            graphyte.send(prefix + '.' + key, to_num(result[key]))
        else:
            LOG.warning(prefix + '.' + key + ' ' + str(result[key]))

    # Calculate & send derived metrics
    non_zero_blocks = to_num(result['nonZeroBlocks'])
    zero_blocks = to_num(result['zeroBlocks'])
    unique_blocks = to_num(result['uniqueBlocks'])
    unique_blocks_used_space = to_num(result['uniqueBlocksUsedSpace'])
    snapshot_non_zero_blocks = to_num(result['snapshotNonZeroBlocks'])

    if non_zero_blocks != 0:
        thin_factor = float((non_zero_blocks + zero_blocks)) / float(non_zero_blocks)
    else:
        thin_factor = 1
    if to_graphite:
        graphyte.send(prefix + '.thin_factor', to_num(thin_factor))
    else:
        LOG.warning(prefix + '.thin_factor ' + str(thin_factor))

    if unique_blocks != 0:
        # cluster with volumes with snapshots can have dedupe ratio < 1
        dedupe_factor = float(non_zero_blocks + snapshot_non_zero_blocks) / float(unique_blocks)
    else:
        dedupe_factor = 1
    if to_graphite:
        graphyte.send(prefix + '.dedupe_factor', to_num(dedupe_factor))
    else:
        LOG.warning(prefix + '.dedupe_factor ' + str(dedupe_factor))
    if unique_blocks_used_space != 0:
        compression_factor = (unique_blocks * 4096.0) / (unique_blocks_used_space * .93)
    else:
        compression_factor = 1
    if to_graphite:
        graphyte.send(prefix + '.compression_factor', to_num(compression_factor))
    else:
        LOG.warning(prefix + '.compression_factor ' + str(compression_factor))

    efficiency_cxd_factor = dedupe_factor * compression_factor
    efficiency_factor = thin_factor * efficiency_cxd_factor
    if to_graphite:
        graphyte.send(prefix + '.efficiency_factor', to_num(efficiency_factor))
        # w/o Thin Provisioning
        graphyte.send(prefix + '.efficiency_cxd_factor', to_num(efficiency_cxd_factor))
    else:
        LOG.warning(prefix + '.efficiency_factor ' + str(efficiency_factor))
        LOG.warning(prefix + '.efficiency_cxd_factor ' + str(efficiency_cxd_factor))


def send_volume_stats(sfe, prefix):
    """
    Send a subset of ListVolumeStatsByVolume results to graphite.
    Note: Calls ListVolumes to get volume names for use in metric path.
    """
    metrics_list = ['actualIOPS', 'averageIOPSize', 'burstIOPSCredit',
        'clientQueueDepth', 'latencyUSec', 'nonZeroBlocks', 'readBytes',
        'readBytesLastSample', 'readLatencyUSec', 'readOps',
        'readOpsLastSample', 'throttle', 'unalignedReads', 'unalignedWrites',
        'volumeSize', 'volumeUtilization', 'writeBytes', 'writeBytesLastSample',
        'writeLatencyUSec', 'writeOps', 'writeOpsLastSample', 'zeroBlocks']

    volume_list = sfe.list_volumes(include_virtual_volumes=False).to_json()['volumes']
    volinfo_by_id = list_to_dict(volume_list, key="volumeID")

    volstats = sfe.list_volume_stats_by_volume(include_virtual_volumes=False).to_json()['volumeStats']
    for vs_dict in volstats:
        vol_name = volinfo_by_id[vs_dict['volumeID']]['name']
        vol_id = volinfo_by_id[vs_dict['volumeID']]['volumeID']
        vol_accountID = volinfo_by_id[vs_dict['volumeID']]['accountID']
        vol_accountID = volinfo_by_id[vs_dict['volumeID']]['accountID']
        vol_accountName = sfe.get_account_by_id(vol_accountID).to_json()['account']['username']
        for key in metrics_list:
            if to_graphite:
                graphyte.send(prefix + '.accountID.' + str(vol_accountName) +
                              '.volume.' + str(vol_name) + '.' + key, to_num(vs_dict[key]))
                graphyte.send(prefix + '.volumeID.' + str(vol_id) + '.' + key, to_num(vs_dict[key]))
            else:
                LOG.warning(prefix + '.accountID.' + str(vol_accountName) +
                            '.volume.' + str(vol_name) + '.' + key + ' ' + str(vs_dict[key]))
                LOG.warning(prefix + '.volumeID.' + str(vol_accountName) +
                            '.volumeID.' + str(vol_id) + '.' + key + ' ' + str(vs_dict[key]))


def send_volume_histogram_stats(sfe, prefix):
    """
    Send volume QoS histogram stats. Requires API v11 or above
    Note: as of August 2020, this API method is not well documented so
        stuff may not mean what we think it means.
    """
    hmetrics = ['belowMinIopsPercentages', 'minToMaxIopsPercentages',
            'minToMaxIopsPercentages', 'readBlockSizes', 'throttlePercentages',
            'writeBlockSizes']
    qosh = sfe.invoke_sfapi("ListVolumeQoSHistograms", parameters=None)
    for i in range(len(qosh['qosHistograms'])):
        for metric in hmetrics:
            for key, value in (qosh['qosHistograms'][i]['histograms'][metric]).items():
                if to_graphite:
                    graphyte.send(prefix + '.volumeID.' + str(qosh['qosHistograms'][i]['volumeID'])
                        + '.' + metric + '.' + key, int(value))
                else:
                    LOG.warning(prefix + '.volumeID.' + str(qosh['qosHistograms'][i]['volumeID'])
                        + '.' + metric + '.' + key + ' ' + str(value))


def send_drive_stats(sfe, prefix):
    """
    Calculates summary statistics about drives by status and type at both cluster
        and node levels and submits them to graphite.
    Calls ListDrives and ListAllNodes
    """
    # Cluster level status
    drive_list = sfe.list_drives().to_json()['drives']
    for status in ['active', 'available', 'erasing', 'failed', 'removing']:
        value = count_if(drive_list, 'status', status)
        if to_graphite:
            graphyte.send(prefix + '.drives.status.' + status, to_num(value))
        else:
            LOG.warning(prefix + '.drives.status.' + status + ' ' + str(value))
    for dtype in ['volume', 'block', 'unknown']:
        value = count_if(drive_list, 'type', dtype)
        if to_graphite:
            graphyte.send(prefix + '.drives.type.' + dtype, to_num(value))
        else:
            LOG.warning(prefix + '.drives.type.' + dtype + ' ' + str(value))
    # Node level status
    node_list = sfe.list_all_nodes().to_json()['nodes']
    nodeinfo_by_id = list_to_dict(node_list, key="nodeID")
    for node in nodeinfo_by_id:
        node_name = nodeinfo_by_id[node]['name']
        for status in ['active', 'available', 'erasing', 'failed', 'removing']:
            value = count_ifs(drive_list, 'status', status, 'nodeID', node)
            if to_graphite:
                graphyte.send(prefix + '.node.' + node_name + '.drives.status.' + status, to_num(value))
            else:
                LOG.warning(prefix + '.node.' + node_name + '.drives.status.' + status + ' ' + str(value))
        for drive_type in ['volume', 'block', 'unknown']:
            value = count_ifs(drive_list, 'type', drive_type, 'nodeID', node)
            if to_graphite:
                graphyte.send(prefix + '.node.' + node_name + '.drives.type.' + drive_type, to_num(value))
            else:
                LOG.warning(prefix + '.node.' + node_name + '.drives.type.' + drive_type + ' ' + str(value))


def send_ssd_stats(sfe, prefix):
    """
    Send drive wear level from ListDriveStats API method results to graphite.
    We could store them under node name, but that doesn't seem necessary.
    Note: Calls ListDriveStats to get driveID to use in metric path.
    """
    result = sfe.list_drive_stats().to_json()['driveStats']

    for i in range(len(result)):
        driveId = result[i]['driveID']
        lifePct = result[i]['lifeRemainingPercent']
        if 'activeSessions' in result[i].keys():
          sessions = result[i]['activeSessions']
          if to_graphite:
            graphyte.send(prefix + '.drives.' + str(driveId) + '.sessions', int(sessions))
            graphyte.send(prefix + '.drives.' + str(driveId) + '.lifeRemainingPercent', int(lifePct))
          else:
            LOG.warning(prefix + '.drives.' + str(driveId) + '.sessions ' + str(sessions))
            LOG.warning(prefix + '.drives.' + str(driveId) + '.lifeRemainingPercent ' + str(lifePct))
        else:
          if to_graphite:
            graphyte.send(prefix + '.drives.' + str(driveId) + '.lifeRemainingPercent', int(lifePct))
          else:
            LOG.warning(prefix + '.drives.' + str(driveId) + '.lifeRemainingPercent ' + str(lifePct))


def send_elem_version(sfe, prefix):
    """
    Send the highest API version supported by current Element API
    """
    result = sfe.get_cluster_version_info().to_json()
    sf_version = result['clusterAPIVersion']
    if to_graphite:
      graphyte.send(prefix + '.version', float(sf_version))
    else:
      LOG.warning(prefix + '.version ' + str(sf_version))


def send_acc_eff(sfe, prefix):
    """
    Sends the CxD (no Thin Provisioning) account efficiency for
      all accounts with one or more volumes
    """
    accounts = sfe.list_accounts().to_json()['accounts']
    avw = []
    for x in range(len(accounts)):
        if len(accounts[x]['volumes']) > 0:
            avw.append(accounts[x]['accountID'])

    for acc in avw:
        acc_eff = 0
        acc_eff_info = sfe.get_account_efficiency(acc).to_json()
        acc_eff = round(acc_eff_info['compression'] * acc_eff_info['deduplication'],2)
        if to_graphite:
            graphyte.send(prefix + '.accountID.' + str(acc) + '.accountEfficiency', float(acc_eff))
        else:
            LOG.warning(prefix + '.accountID.' + str(acc) + '.accountEfficiency ' + str(acc_eff))


def send_vol_efficiency(sfe, prefix):
    """
    Send per-volume efficiency info (dedupe & compression aka CxD only)
    Can be used to identify low-efficiency volumes (e.g. < 1.5x)
    """
    results = sfe.list_accounts().to_json()
    for account in results['accounts']:
      av = sfe.list_volumes(accounts=[account['accountID']]).to_json()
      if len(av['volumes']) > 0:
        for volume in av['volumes']:
          vol_eff_d = sfe.get_volume_efficiency(volume['volumeID']).to_json()
          vol_eff = round((vol_eff_d['deduplication'] * vol_eff_d['compression']),2)
          if to_graphite:
            graphyte.send(prefix + '.volumeID.' + str(volume['volumeID']) + '.volumeEfficiency', float(vol_eff))
          else:
            print(prefix + '.volumeID.' + str(volume['volumeID']) + '.volumeEfficiency ' + str(vol_eff))
            LOG.warning(prefix + '.volumeID.' + str(volume['volumeID']) + '.volumeEfficiency ' + str(vol_eff))
      else:
        LOG.warning(prefix + ': account ID ' + str(account['accountID']) + ' has no volumes')


def send_conn_stats(sfe, prefix):
    """
    calculates iSCSI connection stats at both cluster
    and node levels and submits them to Graphite.
    Calls ListConnections
    """
    result = sfe.list_iscsisessions().to_json()['sessions']
    tgts = []
    accts = []
    for i in range(len(result)):
      tgts.append(result[i]['targetIP'].split(':')[0])
      accts.append(result[i]['initiatorIP'].split(':')[0])

    if to_graphite:
        graphyte.send(prefix + '.iscsiActiveSessionCount', len(result))
        graphyte.send(prefix + '.iscsiTargetCount', len(set(tgts)))
    else:
        LOG.warning(prefix + '.iscsiActiveSessionCount ' + str(len(result)))
        LOG.warning(prefix + '.iscsiTargetCount ' + str(len(set(tgts))))


def send_node_stats(sfe, prefix):
    """
    send a subset of ListNodeStats API call results to graphite.
    Note:   Calls ListAllNodes to get node name to use in metric path.
    """
    metrics_list = ['cpu', 'usedMemory', 'networkUtilizationStorage',
                    'networkUtilizationCluster', 'cBytesOut', 'cBytesIn', 'sBytesOut',
                    'sBytesIn', 'mBytesOut', 'mBytesIn', 'readOps', 'writeOps']

    node_list = sfe.list_all_nodes().to_json()['nodes']
    nodeinfo_by_id = list_to_dict(node_list, key="nodeID")

    nodestats = sfe.list_node_stats().to_json()['nodeStats']['nodes']
    for ns_dict in nodestats:
        node_name = nodeinfo_by_id[ns_dict['nodeID']]['name']
        for key in metrics_list:
            if to_graphite:
                graphyte.send(prefix + '.node.' + node_name + '.' + key, to_num(ns_dict[key]))
            else:
                LOG.warning(prefix + '.node.' + node_name + '.' + key + ' ' + str(ns_dict[key]))


def list_to_dict(list_of_dicts, key):
    """
    pivots a list of dicts into a dict of dicts, using key.
    """
    x = dict((child[key], dict(child, index=index)) for (index, child) in \
             enumerate(list_of_dicts))
    return x


def count_if(my_list, key, value):
    """
    return number of records in my_list where key==value pair matches
    """
    counter = (1 for item in my_list if item.get(key) == value)
    return sum(counter)


def count_ifs(my_list, key, value, key2, value2):
    """
    return number of records in my_list where both key==value pairs matches
    ToDo:   convert to grab any number of key=value pairs
    """
    counter = (1 for item in my_list if ((item.get(key) == value) and \
                                         (item.get(key2) == value2)))
    return sum(counter)


def to_num(metric):
    """
    convert string to number (int or float)
    """
    x = 0
    try:
        x = float(metric)
    except ValueError:
        try:
            x = float(metric)
        except ValueError:
            x = float('NaN')
    finally:
        return x


# Parse commandline arguments
parser = argparse.ArgumentParser()
parser.add_argument('-s', '--solidfire',
                    help='MVIP or FQDN of SolidFire cluster from which metrics should be collected')
parser.add_argument('-u', '--username', default='admin',
                    help='username for SolidFire array. Default: admin (NOTE: consider using a dedicated reporting admin account)')
parser.add_argument('-p', '--password', default='password',
                    help='password for admin account on SolidFire cluster. Default: password')
parser.add_argument('-o', '--timeout', type=int, default=10,
                    help='timeout for SolidFire Collector to connect to SolidFire API. Default: 10 (seconds)')
parser.add_argument('-a', '--apitimeout', type=int, default=20,
                    help='timeout for SolidFire Collector to get response from the SolidFire API endpoint. Default: 20 (seconds)')
parser.add_argument('-c', '--validatecert', default=False,
                    help='Validate SF TLS certificate. Default: False (allow self-signed). For "True", --solidfire must use FQDN')
parser.add_argument('-g', '--graphite', default='localhost',
                    help='hostname of Graphite server to send to. Default: localhost. (NOTE: "debug" sends metrics to logfile)')
parser.add_argument('-t', '--port', type=int, default=2003,
                    help='port to send message to. Default: 2003. if the --graphite is set to debug, can be omitted')
parser.add_argument('-v', '--version', default="11.0",
                    help='Element API version. Default: 11.0. Version must be supported by SolidFire Python SDK in sfcollector')
parser.add_argument('-m', '--metricroot', default='netapp.solidfire.cluster',
                    help='Graphite metric root for sfcollector. Default: netapp.solidfire.cluster')
parser.add_argument('-l', '--logfile', 
                    help='logfile. Default: none. Required if Graphite hostname is "debug" and metrics sent to logfile')
args = parser.parse_args()

to_graphite = True
# Logger module configuration
LOG = logging.getLogger('solidfire_graphite_collector.py')
if args.logfile:
    logging.basicConfig(filename=args.logfile, level=logging.DEBUG, format='%(asctime)s %(message)s')
    LOG.warning("Starting Collector script as a daemon. No console output possible.")
else:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')

# Initialize graphyte sender
if args.graphite == "debug":
    LOG.warning("Starting collector in debug mode. All the metrics will be shipped to logfile")
    to_graphite = False
else:
    graphyte.init(args.graphite, port=args.port, prefix=args.metricroot)

LOG.info("Metrics Collection for array: {0}".format(args.solidfire))
try:
    sfe = ElementFactory.create(args.solidfire, args.username, args.password, args.version, verify_ssl=args.validatecert, print_ascii_art=False)
    # There are two kinds of timeouts (one is for individual API requests)
    # https://github.com/solidfire/solidfire-sdk-python/pull/39/files
    sfe.timeout(args.apitimeout)
    sfe.connect_timeout(args.timeout)
except solidfire.common.ApiServerError as e:
    LOG.warning("ApiServerError: {0}".format(str(e)))
    sfe = None
except Exception as e:
    LOG.warning("General Exception: {0}".format(str(e)))
    sfe = None

try:
    cluster_name = sfe.get_cluster_info().to_json()['clusterInfo']['name']
    send_cluster_faults(sfe, cluster_name)
    send_cluster_stats(sfe, cluster_name)
    send_cluster_capacity(sfe, cluster_name)
    send_volume_stats(sfe, cluster_name)
    send_volume_histogram_stats(sfe, cluster_name)
    send_drive_stats(sfe, cluster_name)
    send_ssd_stats(sfe, cluster_name)
    send_acc_eff(sfe, cluster_name)
    send_elem_version(sfe, cluster_name)
    send_vol_efficiency(sfe, cluster_name)
    send_node_stats(sfe, cluster_name)
    send_conn_stats(sfe, cluster_name)
except solidfire.common.ApiServerError as e:
    LOG.warning("ApiServerError: {0}".format(str(e)))
except Exception as e:
    LOG.warning("General Exception: {0}".format(str(e)))
    sfe = None
