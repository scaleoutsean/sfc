#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# sfc.py

###############################################################################
# Synopsis:                                                                   #
# SFC v2 schedules and executes gathering of SolidFire API object properties  #
#  and performance metrics, enriches obtained data and sends it to InfluxDB 3 #
#                                                                             #
# SFC v1 used to be part of NetApp HCI Collector.                             #
#                                                                             #
# Author: @scaleoutSean                                                       #
# https://github.com/scaleoutsean/sfc                                         #
# License: the Apache License Version 2.1                                     #
###############################################################################

# =============== imports =====================================================

import argparse
import aiohttp
import asyncio
from aiohttp import ClientSession, ClientResponseError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import datetime
import distro
from getpass import getpass
import logging
import logging.handlers
from logging.handlers import RotatingFileHandler
from logging.handlers import QueueHandler
import json
import os
import platform
import random
import re
import sys
import warnings
import time
# import urllib.parse
# import uuid
warnings.simplefilter("default")
os.environ["PYTHONWARNINGS"] = "default"

# =============== default vars ================================================

VERSION = '2.1.0'

# Create reporting-only admin user with read-only access to the SolidFire API.
# Modify these five variables to match your environment if you want hardcoded
# values.
# INFLUX_HOST, INFLUX_PORT, INFLUX_DB, INFLUXDB3_AUTH_TOKEN, SF_MVIP, SF_USERNAME, SF_PASSWORD
INFLUX_HOST = '192.168.1.146'
INFLUX_PORT = '8181'  # default port for InfluxDB 3; sfc.py accesses it over HTTPS
INFLUX_DB = 'sfc'
INFLUXDB3_AUTH_TOKEN = 'apiv3_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
SF_MVIP = '192.168.1.34'
SF_USERNAME = 'monitoring'
SF_PASSWORD = 'xxxxxxxxxx'

# TLS certificates for SolidFire API:
# https://docs.aiohttp.org/en/stable/client_advanced.html#example-use-self-signed-certificate
# TLS certificates for InfluxDB 3:
# https://docs.influxdata.com/influxdb3/core/release-notes/#updates-1

# Below this line it's less likely we need to change anything.
# Use startup sfc.py startup arguments (sfc.py -h) to modify main intervals
INT_HI_FREQ = 60
INT_MED_FREQ = 600
INT_LO_FREQ = 3600
INT_EXPERIMENTAL_FREQ = 600

# Check the source code below to see what this does (submits volume metrics in batches)
CHUNK_SIZE = 24

# Global iteration counter
ITERATION = 0

# Global variables - will be initialized based on configuration
SF_JSON_PATH = '/json-rpc/12.5/'  # Default path, may be overridden
SF_URL = f'https://{SF_MVIP}'  # Constructed from SF_MVIP
SF_POST_URL = f'https://{SF_MVIP}/json-rpc/12.5/'  # Default URL
CLUSTER_NAME = 'unknown'  # Will be set after connecting
args = None  # Will be set by argparse

# =============== functions code ==============================================


# SolidFire headers (NO Authorization key!)
sf_headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
# InfluxDB headers (Bearer token)
influx_headers = {'Accept': 'application/json', 'Accept-Encoding': 'deflate, gzip;q=1.0, *;q=0.5',
                  'Content-Type': 'application/json', 'Authorization': 'Bearer ' + INFLUXDB3_AUTH_TOKEN}


async def sf_api_post(session, url, payload, auth):
    """
    Helper for SolidFire API POST requests with debug logging and required auth.
    """
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug(f"[SF DEBUG] POST {url}")
        logging.debug(f"[SF DEBUG] Headers: {sf_headers}")
        logging.debug(f"[SF DEBUG] Payload: {payload}")
    async with session.post(url, data=payload, headers=sf_headers, auth=auth) as response:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug(f"[SF DEBUG] Response status: {response.status}")
            logging.debug(f"[SF DEBUG] Response headers: {response.headers}")
        try:
            response.raise_for_status()
            return await response.json()
        except aiohttp.ContentTypeError as e:
            text = await response.text()
            logging.error(f"[SF DEBUG] ContentTypeError: {e}")
            logging.error(f"[SF DEBUG] Raw response text: {text}")
            raise
        except Exception as e:
            text = await response.text()
            logging.error(f"[SF DEBUG] Exception: {e}")
            logging.error(f"[SF DEBUG] Raw response text: {text}")
            raise


async def volumes(session, auth, **kwargs):
    """
    Extracts useful volume properties including volume name.

    Other SFC functions may use this function to get ID-to-name mapping for volumes.
    """
    time_start = round(time.time(), 3)
    function_name = 'volumes'
    volumes = None  # initialize volumes to None
    # NOTE: the volumeID pair is out of alphanumeric order because it maps to
    # 'id' which *is* in proper order. We have two sets of tags/fields depending if
    # the volume is paired
    tags_non_paired = [
        ('access',
         'access'),
        ('accountID',
         'account_id'),
        ('enable512e',
         'enable_512e'),
        ('volumeID',
         'id'),
        ('name',
         'name'),
        ('scsiNAADeviceID',
         'scsi_naa_dev_id'),
        ('volumeConsistencyGroupUUID',
         'vol_cg_group_id')]
    fields_non_paired = [
        ('blockSize',
         'block_size'),
        ('fifoSize',
         'fifo_size'),
        ('minFifoSize',
         'min_fifo_size'),
        ('qosPolicyID',
         'qos_policy_id'),
        ('totalSize',
         'total_size')]
    tags_paired = [
        ('access',
         'access'),
        ('accountID',
         'account_id'),
        ('clusterPairID',
         'cluster_pair_id'),
        ('enable512e',
         'enable_512e'),
        ('volumeID',
         'id'),
        ('name',
         'name'),
        ('remoteVolumeID',
         'remote_volume_id'),
        ('remoteVolumeName',
         'remote_volume_name'),
        ('scsiNAADeviceID',
         'scsi_naa_dev_id'),
        ('volumeConsistencyGroupUUID',
         'vol_cg_group_id'),
        ('volumePairUUID',
         'volume_pair_uuid')]
    fields_paired = [
        ('blockSize',
         'block_size'),
        ('fifoSize',
         'fifo_size'),
        ('minFifoSize',
         'min_fifo_size'),
        ('qosPolicyID',
         'qos_policy_id'),
        ('remote_replication_mode',
         'remote_replication_mode'),
        ('remote_replication_state',
         'remote_replication_state'),
        ('remote_replication_snap_state',
         'remote_replication_snap_state'),
        ('totalSize',
         'total_size')]
    for t in tags_non_paired:
        if t[0] in (t[0] for t in fields_non_paired) or [tag[0] for tag in tags_non_paired if tags_non_paired.count(
                tag) > 1] or [field[0] for field in fields_non_paired if fields_non_paired.count(field) > 1]:
            logging.critical(
                "Duplicate metrics found in non-paired volume measurements (tags and fields): " +
                t[0])
            exit(200)
    for t in tags_paired:
        if t[0] in (t[0] for t in fields_paired) or [tag[0] for tag in tags_paired if tags_paired.count(
                tag) > 1] or [field[0] for field in fields_paired if fields_paired.count(field) > 1]:
            logging.critical(
                "Duplicate metrics found in paired volume measurements (tags and fields): " +
                t[0])
            exit(200)
    api_payload = "{ \"method\": \"ListVolumes\", \"params\": {\"volumeStatus\": \"active\"} }"
    try:
        r = await sf_api_post(session, SF_POST_URL, api_payload, auth)
        result = r['result']['volumes']
    except Exception as e:
        logging.error('Function volumes: volume information not obtained - returning.')
        logging.error(e)
        return
    if not kwargs:
        volumes = ''
        for volume in result:
            single_volume = "volumes,cluster=" + CLUSTER_NAME + ","
            # NOTE: this needs to be an integer in InfluxDB. None won't work
            if volume['qosPolicyID'] is None:
                volume['qosPolicyID'] = 0
            # NOTE: this section gathers volume pairing information when
            # volumePairs is not empty
            volume_paired = False
            if volume['volumePairs'] != []:
                volume_pairs = volume['volumePairs']
                vp = await extract_volume_pair(volume_pairs)
                if args.loglevel == 'DEBUG':
                    logging.debug(
                        'VP returned from extract_volume_pair: ' + str(vp))
                if vp != {}:
                    try:
                        for k in vp:
                            volume[k] = vp[k]
                        vp = {}
                        volume_paired = True
                        if args.loglevel == 'DEBUG':
                            logging.debug(
                                'Volume pair information obtained, extracted and added to volume ' + str(
                                    volume['volumeID']) + '.')
                    except BaseException:
                        logging.error(
                            'Volume pair information not obtained for volume could not be added to ' + str(
                                volume['volumeID']) + ' key.')
                        return
                else:
                    logging.error('Volume pair information not returned for volume ' +
                                  str(volume['volumeID']) + ' by extract_volume_pair().')
                    return
            else:
                logging.debug(
                    'Volume replication not enabled for volume ' + str(volume['volumeID']) + '.')

            if volume_paired:
                tags = tags_paired
                fields = fields_paired
            else:
                tags = tags_non_paired
                fields = fields_non_paired
            for tag in tags:
                k = tag[0]
                nk = tag[1]
                val = volume[k]
                kv = nk + "=" + str(volume[k])
                if k in [x[0] for x in tags[0:-1]]:
                    single_volume = single_volume + kv + ","
                else:
                    single_volume = single_volume + kv + " "
                if volume_paired:
                    if args.loglevel == 'DEBUG':
                        logging.debug("single_volume tags for volume " +
                                      str(volume['volumeID']) + ": " + str(single_volume))

            # NOTE: this is kind of out of place, but we need to check and add
            # KV if volume has non-empty attributes
            if volume['attributes'] != {}:
                if args.loglevel == 'DEBUG':
                    logging.debug('Volume ' +
                                  str(volume['volumeID']) +
                                  ' has non-empty attributes.')
                try:
                    vol_attr_fields = await extract_trident_volume_attributes(volume['attributes'])
                    if vol_attr_fields != '':
                        single_volume = single_volume + vol_attr_fields + ","
                        if args.loglevel == 'DEBUG':
                            logging.debug(
                                'Volume attributes parsed and added:\n ' +
                                str(vol_attr_fields) +
                                '.')
                    else:
                        logging.info(
                            'Volume ' +
                            str(
                                volume['volumeID']) +
                            ' has no attributes that match Trident attributes currently parsed by SFC. Not adding any attributes to volume fields.')
                except Exception as e:
                    logging.error(
                        'Error while extracting Trident volume attributes: ' + str(e) + '.')
            else:
                if args.loglevel == 'DEBUG':
                    logging.debug('No attributes found for volume ' +
                                  str(volume['volumeID']) + '.')

            for field in fields:
                k = field[0]
                nk = field[1]
                val = volume[k]
                val = str(val) + "i"
                kv = nk + "=" + val
                if k in [x[0] for x in fields[0:-1]]:
                    single_volume = single_volume + kv + ","
                else:
                    single_volume = single_volume + kv + " "
                if volume_paired:
                    if args.loglevel == 'DEBUG':
                        logging.debug("single_volume tags for volume + " +
                                      str(volume['volumeID']) + ": " + str(single_volume))
            volumes = volumes + single_volume + "\n"
        await send_to_influx(volumes)
    elif kwargs.keys() == {'names'} or kwargs.keys() == {'names_dict'}:
        for key in kwargs:
            if key == 'names':
                volumes = []
                for volume in result:
                    volumes.append((volume['volumeID'], volume['name']))
                return volumes
            elif key == 'names_dict':
                volumes_dict = dict(
                    map(lambda x: (x['volumeID'], x['name']), result))
                return volumes_dict
    else:
        logging.error('Invalid argument passed to volumes() function.')
        return False
    time_taken = max(0.0, round(time.time() - time_start, 3))
    if args.loglevel == 'DEBUG':
        logging.debug("Volumes payload:\n " + str(volumes) + ".")
    logging.info('Volumes collected in ' + str(time_taken) + ' seconds.')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return volumes


async def extract_volume_pair(volume_pairs: list) -> dict:
    """
    Extract information for first volume pairing from volume replication list and return a dict with contents.
    This is a helper function for the volumes() function.

    Currently only the first paired volume (from possible several when paired one-to-many) is processed.
    Additional volumes and values may be added in the future.
    """
    time_start = round(time.time(), 3)
    function_name = 'extract_volume_pair'
    vp = {}
    if volume_pairs == [] or len(volume_pairs) > 1:
        if args.loglevel == 'DEBUG':
            logging.debug('volume_pairs list ' + str(volume_pairs) + '.')
        logging.warning(
            'Volume pairs list is empty or one-to-many detected (not implemented). Returning.')
    else:
        vp_dict = volume_pairs[0]
        for k in vp_dict:
            try:
                # pop from k['clusterPairID']
                if k == 'clusterPairID':
                    vp['clusterPairID'] = vp_dict[k]
                if k == 'remoteVolumeID':
                    vp['remoteVolumeID'] = vp_dict[k]
                if k == 'remoteVolumeName':
                    vp['remoteVolumeName'] = vp_dict[k]
                if k == 'volumePairUUID':
                    vp['volumePairUUID'] = vp_dict[k]
            except KeyError as e:
                logging.warning('KeyError in volume_pair list: ' + str(e))
                return {}
        try:
            # NOTE: this order (Async/Sync/SnapshotsOnly) is based on the SolidFire UI.
            # Numbering starts from 1 as 0 seems suitable for non-paired
            # volumes. Unknown is set to 100 to leave room for existing states
            # not yet here.
            mode_map = [('Async', 1), ('Sync', 2),
                        ('SnapshotsOnly', 3), ('None', 100)]
            mode = vp_dict['remoteReplication']['mode'] if vp_dict['remoteReplication']['mode'] in [
                x[0] for x in mode_map] else 'None'
            vp['remote_replication_mode'] = next(
                (x[1] for x in mode_map if x[0] == mode), None)
            # NOTE: one option is to change these into Pythonic snake case, and deal with it in Grafana
            # and another is to simply use integers for the states and assign 100 to unseen and unknown
            # Source of state keys: NetApp TR-4741 (2020), page 26, and
            # observation on SF Demo VM 12.5
            rep_state_map = [
                ('Active',
                 1),
                ('Idle',
                 2),
                ('PausedDisconnected',
                 3),
                ('PausedManual',
                 4),
                ('PausedDisconnected',
                 5),
                ('PausedManualRemote',
                 6),
                ('ResumingConnected',
                 7),
                ('ResumingDataTransfer',
                 8),
                ('ResumingLocalSync',
                 9),
                ('ResumingRRSync',
                 10),
                ('None',
                 100)]
            rep_state_mode = vp_dict['remoteReplication']['state'] if vp_dict['remoteReplication']['state'] in [
                x[0] for x in rep_state_map] else 'None'
            vp['remote_replication_state'] = next(
                (x[1] for x in rep_state_map if x[0] == rep_state_mode), None)
            snap_state_map = [
                ('Active',
                 1),
                ('Idle',
                 2),
                ('PausedDisconnected',
                 3),
                ('PausedManual',
                 4),
                ('PausedDisconnected',
                 5),
                ('PausedManualRemote',
                 6),
                ('ResumingConnected',
                 7),
                ('ResumingDataTransfer',
                 8),
                ('ResumingLocalSync',
                 9),
                ('ResumingRRSync',
                 10),
                ('None',
                 100)]
            snap_state_mode = vp_dict['remoteReplication']['snapshotReplication']['state'] if vp_dict['remoteReplication']['snapshotReplication']['state'] in [
                x[0] for x in snap_state_map] else 'None'
            vp['remote_replication_snap_state'] = next(
                (x[1] for x in snap_state_map if x[0] == snap_state_mode), None)
        except KeyError as e:
            logging.warning(
                'KeyError while parsing remoteReplication dictionary: ' + str(e))
            return {}
    time_taken = max(0.0, round(time.time() - time_start, 3))
    if args.loglevel == 'DEBUG':
        logging.debug('Volume pair payload: ' + str(vp) + '.')
    logging.info(
        'Volume pair data extracted in ' +
        str(time_taken) +
        ' seconds.')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    if vp:
        return vp
    else:
        logging.warning('Volume pair data not extracted. Returning empty dict.')
        return {}


async def extract_trident_volume_attributes(vol_attr: dict) -> str:
    """
    Extracts volume attributes from the volume dictionary and returns a list of KV strings ready for addition to volume fields.
    """
    volume_attributes = [
        ('docker-name', 'va_docker_name'),
        ('fstype', 'va_fstype'),
        ('provisioning', 'va_provisioning'),
        ('version', 'va_trident_version'),
        ('backendUUID', 'va_trident_backend_uuid'),
        ('platform', 'va_trident_platform'),
        ('platformVersion', 'va_trident_platform_version'),
        ('plugin', 'va_trident_plugin')
    ]
    v_attrs = vol_attr.keys()
    if 'docker-name' in v_attrs and 'fstype' in v_attrs and 'provisioning' in v_attrs and 'trident' in v_attrs:
        v_attrs_dict = {}
        for k in v_attrs:
            for va_pair in volume_attributes:
                if k == va_pair[0]:
                    # NOTE: provisioning seems to be always empty in SF attributes
                    # as Trident seems to be using thin|thick for ONTAP; SF is
                    # always thin-provisioned
                    if k == 'provisioning' and vol_attr[k] == '':
                        v_attrs_dict[va_pair[1]] = 'thin'
                    elif k == 'provisioning' and vol_attr[k] != '':
                        v_attrs_dict[va_pair[1]] = vol_attr[k]
                    else:
                        v_attrs_dict[va_pair[1]] = vol_attr[k]
                elif k == 'trident':
                    trident_dict = json.loads(vol_attr[k])
                    for trident_key in trident_dict.keys():
                        if trident_key == va_pair[0]:
                            v_attrs_dict[va_pair[1]
                                         ] = trident_dict[trident_key]
    else:
        logging.info(
            'Non-Trident attributes found in volume attributes: ' +
            str(vol_attr) +
            '. Skipping.')
        return ''
    if args.loglevel == 'DEBUG':
        logging.debug('Volume attributes extracted: ' + str(v_attrs_dict) + '.')
    return (','.join([f'{k}="{v}"' for k, v in v_attrs_dict.items()]))


async def sync_jobs(session, auth):
    """
    Obtains information about synchronization jobs using ListSyncJobs and sends to InfluxDB.

    Sync jobs are used in SolidFire replication to initially synchronize volume data between paired volumes.
    This function currently only supports 'remote' type sync jobs.
    """
    time_start = round(time.time(), 3)
    function_name = 'sync_jobs'
    api_payload = "{ \"method\": \"ListSyncJobs\" }"
    async with session.post(SF_POST_URL, data=api_payload, auth=auth) as response:
        r = await response.json()
    result = r['result']['syncJobs']
    if args.loglevel == 'DEBUG':
        logging.debug('Sync jobs result: ' + str(result) + '.')
    if result == []:
        logging.info('No sync jobs found. Returning.')
        return
    else:
        # NOTE: there are different kinds of jobs (clone, remote replication, slice synchronization)
        # Each has unique tags and fields
        # See https://docs.netapp.com/us-en/element-software/api/reference_element_api_syncjob.html
        # type: one of clone slice block remote
        tags = [('dstVolumeID', 'dst_volume_id'),
                ('stage', 'stage'), ('type', 'type')]
        fields = [
            ('blocksPerSecond',
             'blocks_per_sec'),
            ('elapsedTime',
             'elapsed_time'),
            ('percentComplete',
             'pct_complete'),
            ('remainingTime',
             'remaining_time')]
        sync_jobs = ''
        for i in result:
            # NOTE: this is a single sync job of 'remote' type. Until we get
            # API examples with real-life data, other types will be discarded
            if i['type'] == 'remote':
                single_sync_job = "sync_jobs,cluster=" + CLUSTER_NAME + ","
                for tag in tags:
                    k = tag[0]
                    nk = tag[1]
                    val = i[k]
                    kv = nk + "=" + str(val)
                    if k in [x[0] for x in tags[0:-1]]:
                        single_sync_job = single_sync_job + kv + ","
                    else:
                        single_sync_job = single_sync_job + kv + " "
                for field in fields:
                    k = field[0]
                    nk = field[1]
                    val = i[k]
                    # NOTE: contrary to the docs, blocks_per_sec seems to be an integer
                    # https://github.com/NetAppDocs/element-software/issues/204
                    if nk in ['blocks_per_sec',
                              'elapsed_time', 'pct_complete']:
                        val = str(val) + "i"
                    elif nk == 'remaining_time':
                        # NOTE: Uhm, yeah. It's possible.
                        if val is None:
                            val = "0"
                    # NOTE: looks like another API documentation bug,
                    # remaining_time is a float
                    else:
                        val = str(val)
                    kv = nk + "=" + val
                    if k in [x[0] for x in fields[0:-1]]:
                        single_sync_job = single_sync_job + kv + ","
                    else:
                        single_sync_job = single_sync_job + kv + " "
                sync_jobs = sync_jobs + single_sync_job + "\n"
            else:
                if args.loglevel == 'DEBUG':
                    logging.debug('Sync job type ' +
                                  str(i['type']) +
                                  ' is not yet supported. You may submit this record to have it considered for inclusion in SFC. Skipping.')
                logging.info('Skipped sync job: ' + str(i))
    await send_to_influx(sync_jobs)
    time_taken = max(0.0, round(time.time() - time_start, 3))
    if args.loglevel == 'DEBUG':
        logging.debug('Sync jobs payload:\n ' + str(sync_jobs) + '.')
    logging.info(
        'Sync jobs obtained and sent in ' +
        str(time_taken) +
        ' seconds.')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return


async def volume_performance(session, auth, **kwargs):
    """
    Extract volume stats for additional processing and sends to InfluxDB.

    Uses volumes() function to get ID-to-name mapping for volumes.
    """
    time_start = round(time.time(), 3)
    function_name = 'volume_performance'
    try:
        all_volumes = await volumes(session, auth, names=True)
        isinstance(all_volumes, list)
        if args.loglevel == 'DEBUG':
            logging.debug('Volume information obtained and is a list of ' +
                          str(len(all_volumes)) + ' elements.')
    except Exception as e:
        logging.error(
            'Volume information not obtained or malformed. Returning.')
        logging.error(e)
        return
    fields = [('actualIOPS', 'actual_iops'),
              ('averageIOPSize', 'average_io_size'),
              ('asyncDelay', 'async_delay'),
              ('burstIOPSCredit', 'burst_io_credit'),
              ('clientQueueDepth', 'client_queue_depth'),
              ('latencyUSec', 'latency_usec'),
              ('nonZeroBlocks', 'non_zero_blocks'),
              ('normalizedIOPS', 'normalized_iops'),
              ('readBytes', 'read_bytes'),
              ('readBytesLastSample', 'read_bytes_last_sample'),
              ('readLatencyUSec', 'read_latency_usec'),
              ('readOpsLastSample', 'read_ops_last_sample'),
              ('throttle', 'throttle'),
              ('volumeSize', 'volume_size'),
              ('volumeUtilization', 'volume_utilization'),
              ('writeBytes', 'write_bytes'),
              ('writeBytesLastSample', 'write_bytes_last_sample'),
              ('writeLatencyUSec', 'write_latency_usec'),
              ('writeOpsLastSample', 'write_ops_last_sample'),
              ('zeroBlocks', 'zero_blocks')
              ]
    if len(all_volumes) > CHUNK_SIZE:
        if args.loglevel == 'DEBUG':
            logging.debug('Splitting volumes list with length ' +
                          str(len(all_volumes)) + ' using chunk size ' + str(CHUNK_SIZE) + '.')
        volume_lists = await _split_list(all_volumes)
    else:
        volume_lists = []
        volume_lists.append(all_volumes)

    volumes_performance = ''
    b = 0
    for volume_batch in volume_lists:
        if args.loglevel == 'DEBUG':
            logging.info('Processing volume batch ' + str(b) + ' with ' +
                         str(len(volume_batch)) + ' volumes.')
        volume_batch_ids = [x[0] for x in volume_batch]
        if args.loglevel == 'DEBUG':
            logging.info("Volume batch IDs:\n" + str(volume_batch_ids) + ".")
        api_payload = "{ \"method\": \"ListVolumeStats\", \"params\": { \"volumeIDs\": " + \
            str(volume_batch_ids) + "}}"
        async with session.post(SF_POST_URL, data=api_payload, auth=auth) as response:
            r = await response.json()
        result = r['result']['volumeStats']
        # NOTE: we need to convert the asyncDelay from null to integer or parse the string to seconds:int
        # NOTE: asyncDelay is a string like "00:00:01.123456" (1.1s)
        async_delay_pattern = re.compile('\\d{2}:\\d{2}:\\d{2}.\\d{5}')
        for volume in result:
            if volume['asyncDelay'] is not None:
                try:
                    if async_delay_pattern.match(volume['asyncDelay']):
                        async_delay_tp = datetime.datetime.strptime(
                            volume['asyncDelay'], "%H:%M:%S.%f")
                        volume['asyncDelay'] = async_delay_tp.hour * 3600 + \
                            async_delay_tp.minute * 60 + async_delay_tp.second
                except TypeError as e:
                    logging.error(
                        'Failed to convert asyncDelay text string to seconds (int) for volume ' +
                        str(
                            volume['volumeID']) +
                        '. Problem string: ' +
                        str(
                            volume['asyncDelay']) +
                        '. Setting to -1 to surface in Grafana. Error: ' +
                        str(e) +
                        '.')
                    volume['asyncDelay'] = int(-1)
            else:
                if args.loglevel == 'DEBUG':
                    logging.debug(
                        'Volume has null asyncDelay. Setting it to -1 for volume ' + str(volume['volumeID']) + '.')
                volume['asyncDelay'] = -1
            if args.loglevel == 'DEBUG':
                logging.debug('Processed volume ' +
                              str(volume['volumeID']) +
                              '. Data: ' +
                              str(volume) +
                              '.')
        volume_performance = ''
        for volume in result:
            volume_line = ''
            for v in volume_batch:
                if v[0] == volume['volumeID']:
                    volume_name = v[1]
                    kv_list = ''
                    for field in fields:
                        k = field[0]
                        nk = field[1]
                        val = volume[k]
                        if isinstance(
                                val, float) or k == 'throttle' or k == 'volumeUtilization':
                            val = str(val)
                        else:
                            val = str(val) + "i"
                        if k in [x[0] for x in fields[0:-1]]:
                            kv = nk + "=" + val + ","
                        else:
                            kv = nk + "=" + val + " "
                        kv_list = kv_list + kv
                    volume_line = "volume_performance,cluster=" + CLUSTER_NAME + ",id=" + \
                        str(volume['volumeID']) + ",name=" + \
                        volume_name + " " + kv_list
            # NOTE: timestamp for the record
            ts = str(int(round(time.time(), 0)))
            volume_performance = volume_performance + volume_line + ts + "\n"
        b = b + 1
        volumes_performance = volumes_performance + volume_performance
    await send_to_influx(volumes_performance)
    time_taken = max(0.0, round(time.time() - time_start, 3))
    if args.loglevel == 'DEBUG':
        logging.debug(
            "Volume performance payload:\n" +
            str(volumes_performance))
    logging.info('Volume performance collected in ' +
                 str(time_taken) + ' seconds')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return


async def accounts(session, auth):
    """
    Call SolidFire GetClusterAccounts, extract data from response and send to InfluxDB.
    """
    time_start = round(time.time(), 3)
    function_name = 'accounts'
    accounts = ''
    api_payload = "{ \"method\": \"ListAccounts\" }"
    async with session.post(SF_POST_URL, data=api_payload, auth=auth) as response:
        r = await response.json()
    for account in r['result']['accounts']:
        if (account['enableChap']):
            try:
                # NOTE: remove CHAP secrets
                account.pop('initiatorSecret')
                account.pop('targetSecret')
            except KeyError:
                # NOTE: if they don't exist, we don't need to remove them
                logging.warning(
                    "Did not find account (CHAP) secrets to remove from API response" + str(account['accountID']))
        if len(account['volumes']) > 0:
            volume_count = str(len(account['volumes']))
        else:
            volume_count = "0"
        if account['status'] == "active":
            account_active = "1"
        else:
            account_active = "0"
        accounts = accounts + "accounts,cluster=" + CLUSTER_NAME + ",id=" + str(account['accountID']) + ",name=" + str(
            account['username']) + " " + "active=" + account_active + "i" + ",volume_count=" + volume_count + "i" + "\n"
    await send_to_influx(accounts)
    time_taken = max(0.0, round(time.time() - time_start, 3))
    if args.loglevel == 'DEBUG':
        logging.debug("Account (tenants) list payload: " + str(accounts))
    logging.info('Tenant accounts gathered in ' +
                 str(time_taken) + ' seconds.')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return accounts


async def account_efficiency(session, auth):
    """
    Process account efficiency response from ListAccounts, GetAccountEfficiency and submit to InfluxDB.
    """
    function_name = 'account_efficiency'
    time_start = round(time.time(), 3)
    account_efficiency = '#account_efficiency\n'
    api_payload = "{ \"method\": \"ListAccounts\", \"params\": {}}"
    async with session.post(SF_POST_URL, data=api_payload, auth=auth) as response:
        if response.status != 200:
            text = await response.text()
            logging.error(f"Failed to get accounts. Status: {response.status}, Response: {text}")
            return
        try:
            r = await response.json()
        except Exception as e:
            text = await response.text()
            logging.error(f"Failed to parse JSON. Response text: {text}")
            return
        account_id_name_list = []
        try:
            for account in r['result']['accounts']:
                account_id_name_list.append(
                    (account['accountID'], account['username']))
        except KeyError:
            # NOTE: we can't continue without account IDs. Log and return.
            logging.error(
                'Account information not obtained - deallocating response and returning.')
            return
        finally:
            del r
    for account in account_id_name_list:
        api_payload = "{ \"method\": \"GetAccountEfficiency\", \"params\": { \"accountID\": " + \
            str(account[0]) + " }}"
        async with session.post(SF_POST_URL, data=api_payload, auth=auth) as response:
            r = await response.json()
        compression = round(r['result']['compression'], 2)
        deduplication = round(r['result']['deduplication'], 2)
        thin_provisioning = round(r['result']['thinProvisioning'], 2)
        storage_efficiency = round((compression * deduplication), 2)
        account_id_efficiency = "account_efficiency,cluster=" + CLUSTER_NAME + ",id=" + str(account[0]) + ",name=" + str(account[1]) + " " + "compression=" + str(
            compression) + ",deduplication=" + str(deduplication) + ",storage_efficiency=" + str(storage_efficiency) + ",thin_provisioning=" + str(thin_provisioning) + "\n"
        account_efficiency = account_efficiency + account_id_efficiency
    time_taken = max(0.0, round(time.time() - time_start, 3))
    logging.info('Account efficiency collected in ' +
                 str(time_taken) + ' seconds.')
    if args.loglevel == 'DEBUG':
        logging.debug(
            "Account efficiency payload:\n" +
            str(account_efficiency))
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    await send_to_influx(account_efficiency)
    return


async def volume_efficiency(session, auth):
    """
    Use ListVolumes, GetVolumeEfficiency to gather volume efficiency and submit to InfluxDB.
    """
    function_name = 'volume_efficiency'
    volume_efficiency = "#volume_efficiency\n"
    time_start = round(time.time(), 3)
    api_payload = "{ \"method\": \"ListVolumes\", \"params\": {}}"
    async with session.post(SF_POST_URL, data=api_payload, auth=auth) as response:
        r = await response.json()
        volume_id_name_list = []
        for volume in r['result']['volumes']:
            volume_id_name_list.append((volume['volumeID'], volume['name']))
    short_lists = await _split_list(volume_id_name_list)
    for short_list in short_lists:
        for volume in short_list:
            api_payload = "{ \"method\": \"GetVolumeEfficiency\", \"params\": { \"volumeID\": " + \
                str(volume[0]) + " }}"
            async with session.post(SF_POST_URL, data=api_payload, auth=auth) as response:
                r = await response.json()
                compression = round(r['result']['compression'], 2)
                deduplication = round(r['result']['deduplication'], 2)
                storage_efficiency = round(
                    r['result']['deduplication'] * r['result']['compression'], 2)
                thin_provisioning = round(r['result']['thinProvisioning'], 2)
                volume_id_efficiency = "volume_efficiency,cluster=" + CLUSTER_NAME + ",id=" + str(volume[0]) + ",name=" + str(volume[1]) + " " + "compression=" + str(
                    compression) + ",deduplication=" + str(deduplication) + ",storage_efficiency=" + str(storage_efficiency) + ",thin_provisioning=" + str(thin_provisioning) + "\n"
                volume_efficiency = volume_efficiency + volume_id_efficiency
                await send_to_influx(volume_efficiency)

    time_taken = max(0.0, round(time.time() - time_start, 3))
    if args.loglevel == 'DEBUG':
        logging.debug("Volume efficiency payload: " + str(volume_efficiency))
    logging.info('Volume efficiency collected in ' +
                 str(time_taken) + ' seconds.')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return


async def cluster_faults(session, auth):
    """
    Use GetClusterFaults to extract cluster faults and return for sending to InfluxDB.
    """
    time_start = round(time.time(), 3)
    function_name = 'cluster_faults'
    api_payload = "{ \"method\": \"ListClusterFaults\" }"
    async with session.post(SF_POST_URL, data=api_payload, auth=auth) as response:
        r = await response.json()
    group = {'bestPractices': 0, 'error': 0, 'critical': 0, 'warning': 0}
    for fault in r['result']['faults']:
        if fault['severity'] in group and fault['resolved'] is False:
            group[fault['severity']] += 1
    if group['critical'] > 0 or group['error'] > 0 or group['warning'] > 0 or group['bestPractices'] > 0:
        faults_total = str(
            group['critical'] + group['error'] + group['warning'] + group['bestPractices'])
        cluster_faults = "cluster_faults,cluster=" + CLUSTER_NAME + ",total=" + faults_total + " " + "critical=" + str(group['critical']) + "i" + ",error=" + str(
            group['error']) + "i" + ",warning=" + str(group['warning']) + "i" + ",bestPractices=" + str(group['bestPractices']) + "i" + "\n"
    else:
        cluster_faults = "cluster_faults,cluster=" + CLUSTER_NAME + \
            ",total=0 critical=0i,error=0i,warning=0i,bestPractices=0i" + "\n"
    time_taken = max(0.0, round(time.time() - time_start, 3))
    await send_to_influx(cluster_faults)
    logging.info('Cluster faults gathered in ' + str(time_taken) + ' seconds.')
    if args.loglevel == 'DEBUG':
        logging.debug("Cluster faults payload: " + str(cluster_faults))
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return cluster_faults


async def volume_qos_histograms(session, auth):
    """
    Get ListVolumeQoSHistograms results, extract, transform and send to InfluxDB.
    """
    # NOTE: https://docs.influxdata.com/influxdb/v1/query_language/functions/#histogram
    # NOTE: It is resource-intensive so delay it a bit to avoid executing concurrently with other functions
    sleep_delay = random.randint(5, 10)
    await asyncio.sleep(sleep_delay)
    time_start = round(time.time(), 3)
    function_name = 'volume_qos_histograms'
    if not args.experimental:
        logging.warning('QoS histograms are not enabled. Returning...')
        return
    volumes_dict = None
    try:
        volumes_dict = await volumes(session, auth, names_dict=True)
        isinstance(volumes, dict)
        if args.loglevel == 'DEBUG':
            logging.debug('ID-volume KV pairs obtained from volumes: ' +
                          str(len(volumes_dict)) + ' pairs.')
    except Exception as e:
        logging.error(
            'Volume information not returned by volumes function or response malformed:' + str(volumes_dict))
        logging.error(e)
        return
    api_payload = "{ \"method\": \"ListVolumeQoSHistograms\" }"
    async with session.post(SF_POST_URL, data=api_payload, auth=auth) as response:
        r = await response.json()
        result = r['result']['qosHistograms']
    qosh_list = await _split_list(result)
    for qosh_batch in qosh_list:
        for hg in qosh_batch:
            vol_id_name = (hg['volumeID'], volumes_dict[hg['volumeID']])
            await qos_histogram_processor(hg, vin=vol_id_name)
    time_taken = max(0.0, round(time.time() - time_start, 3))
    logging.info('Volume QoS histograms collected in ' +
                 str(time_taken) + ' seconds.')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    await send_to_influx("sfc_metrics,cluster=" + CLUSTER_NAME + ",function=volume_qos_histograms" + " " + "time_taken=" + str(time_taken) + "\n")
    return


async def qos_histogram_processor(hg, **kwargs):
    """
    Process QoS histogram output from volume_qos_histograms function and send to InfluxDB.
    """
    # histogram_types = ['belowMinIopsPercentages', 'minToMaxIopsPercentages', 'readBlockSizes', 'targetUtilizationPercentages', 'throttlePercentages', 'writeBlockSizes']
    histogram_types = [('belowMinIopsPercentages', 'below_min_iops_percentages'),
                       ('minToMaxIopsPercentages', 'min_to_max_iops_percentages'),
                       ('readBlockSizes', 'read_block_sizes'),
                       ('targetUtilizationPercentages',
                        'target_utilization_percentage'),
                       ('throttlePercentages', 'throttle_percentages'),
                       ('writeBlockSizes', 'write_block_sizes')
                       ]
    belowMinIopsPercentages = [('Bucket1To19', 'b_01_to_19'),
                               ('Bucket20To39', 'b_20_to_39'),
                               ('Bucket40To59', 'b_40_to_59'),
                               ('Bucket60To79', 'b_60_to_79'),
                               ('Bucket80To100', 'b_80_to_100')
                               ]
    minToMaxIopsPercentages = [('Bucket1To19', 'b_001_to_019'),
                               ('Bucket20To39', 'b_020_to_039'),
                               ('Bucket40To59', 'b_040_to_059'),
                               ('Bucket60To79', 'b_060_to_079'),
                               ('Bucket80To100', 'b_080_to_100'),
                               ('Bucket101Plus', 'b_101_plus')
                               ]
    readBlockSizes = [('Bucket512To4095', 'b_000512_to_004095'),
                      ('Bucket4096To8191', 'b_004096_to_008191'),
                      ('Bucket8192To16383', 'b_008192_to_016383'),
                      ('Bucket16384To32767', 'b_016384_to_032767'),
                      ('Bucket32768To65535', 'b_032768_to_65535'),
                      ('Bucket65536To131071', 'b_065536_to_131071'),
                      ('Bucket131072Plus', 'b_131072_plus')
                      ]
    targetUtilizationPercentages = [('Bucket0', 'b_000'),
                                    ('Bucket1To19', 'b_001_to_019'),
                                    ('Bucket20To39', 'b_020_to_039'),
                                    ('Bucket40To59', 'b_040_to_059'),
                                    ('Bucket60To79', 'b_060_079'),
                                    ('Bucket80To100', 'b_080_to_100'),
                                    ('Bucket101Plus', 'b_101_plus')
                                    ]
    throttlePercentages = [('Bucket0', 'b_00'),
                           ('Bucket1To19', 'b_00_to_19'),
                           ('Bucket20To39', 'b_20_to_30'),
                           ('Bucket40To59', 'b_40_to_59'),
                           ('Bucket60To79', 'b_60_to_79'),
                           ('Bucket80To100', 'b_80_to_100')
                           ]
    writeBlockSizes = [('Bucket512To4095', 'b_000512_to_004095'),
                       ('Bucket4096To8191', 'b_004096_to_008191'),
                       ('Bucket8192To16383', 'b_008192_to_016383'),
                       ('Bucket16384To32767', 'b_016384_to_032767'),
                       ('Bucket32768To65535', 'b_032768_to_65535'),
                       ('Bucket65536To131071', 'b_065536_to_131071'),
                       ('Bucket131072Plus', 'b_131072_plus')
                       ]
    hg_names = (belowMinIopsPercentages, minToMaxIopsPercentages, readBlockSizes,
                targetUtilizationPercentages, throttlePercentages, writeBlockSizes)
    vol_id_name = kwargs['vin']
    n = 0
    volume_payload = ''
    volume_kvs_string = ''
    for bucket_tuple, histogram_type in zip(hg_names, hg['histograms']):
        volume_kvs_string = "histogram_" + \
            histogram_types[n][1] + ",cluster=" + \
            CLUSTER_NAME + ",name=" + vol_id_name[1] + " "
        kv_pair = ''
        for orig_bucket_name, sfc_bucket_name in bucket_tuple:
            kv_pair = kv_pair + sfc_bucket_name + '=' + \
                str(hg['histograms'][histogram_type]
                    [orig_bucket_name]) + 'i' + ','
        volume_kvs_string = volume_kvs_string + kv_pair + \
            'id=' + str(vol_id_name[0]) + 'i' + '\n'
        volume_kvs_string = volume_kvs_string[:-1]
        if args.loglevel == 'DEBUG':
            logging.debug("QoS histogram records (n=" + str(n) + ") for volume " +
                          str(vol_id_name[0]) + ":\n" + str(volume_kvs_string))
        volume_payload = volume_payload + volume_kvs_string + "\n"
        n = n + 1
    await send_to_influx(volume_payload)
    logging.debug("Sent QoS histogram records for volume " +
                  str(vol_id_name[0]) + ". Data:\n" + str(volume_kvs_string))
    return


async def node_performance(session, auth):
    """
    Use GetClusterStats to extract node stats and return for sending to InfluxDB.
    """
    time_start = round(time.time(), 3)
    function_name = 'node_performance'
    api_payload = "{ \"method\": \"ListNodeStats\" }"
    async with session.post(SF_POST_URL, data=api_payload, auth=auth) as response:
        r = await response.json()
    result = r['result']['nodeStats']['nodes']
    metrics = [("cpu", "cpu"), ("networkUtilizationCluster", "network_utilization_cluster"),
               ("networkUtilizationStorage", "network_utilization_storage")]
    load_histogram_metrics = [
        ("Bucket0",
         "bucket_00_00"),
        ("Bucket1To19",
         "bucket_01_to_19"),
        ("Bucket20To39",
         "bucket_20_to_39"),
        ("Bucket40To59",
            "bucket_40_to_59"),
        ("Bucket60To79",
         "bucket_60_to_79"),
        ("Bucket80To100",
         "bucket_80_to_100")]
    node_performance = ''
    for node in result:
        metric_details = ''
        for key in load_histogram_metrics:
            key_string = key[1]
            val = node['ssLoadHistogram'][key[0]]
            if isinstance(val, int):
                str_val = str(val) + "i"
            else:
                str_val = str(val)
            metric_detail = key_string + "=" + str_val + ","
        record = len(metrics)
        n = 0
        for key in metrics:
            key_string = key[1]
            val = node[key[0]]
            if isinstance(val, int):
                str_val = str(val) + "i"
            else:
                pass
            if n < (record - 1):
                metric_detail = key_string + "=" + str_val + ","
            else:
                metric_detail = key_string + "=" + str_val
            n += 1
            metric_details = metric_details + metric_detail
        node_performance = node_performance + \
            ("node_performance,cluster=" + CLUSTER_NAME + ",id=" +
             str(node['nodeID']) + " " + metric_details + "\n")
    await send_to_influx(node_performance)
    time_taken = max(0.0, round(time.time() - time_start, 3))
    if args.loglevel == 'DEBUG':
        logging.debug("Node stats: " + str(node_performance))
    logging.info('Node stats collected in ' + str(time_taken) + ' seconds.')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return


async def iscsi_sessions(session, auth):
    """
    Use GetIscsiSessions to extract iSCSI sessions info and send to InfluxDB.
    When there are no iSCSI sessions, sends an empty payload to InfluxDB and iscsi_sessions table
      does not get created.
    """
    function_name = 'iscsi_sessions'
    time_start = round(time.time(), 3)
    api_payload = "{ \"method\": \"ListISCSISessions\" }"
    async with session.post(SF_POST_URL, data=api_payload, auth=auth) as response:
        r = await response.json()
    result = r['result']['sessions']
    fields = [
        ("accountID", "account_id"),
        ("accountName", "account_name"),
        ("initiatorIP", "initiator_ip"),
        ("initiatorName", "initiator_name"),
        ("initiatorSessionID", "initiator_session_id"),
        ("nodeID", "node_id"),
        ("targetIP", "target_ip"),
        ("targetName", "target_name"),
        ("virtualNetworkID", "virtual_network_id"),
        ("volumeID", "volume_id")
    ]
    metrics = [
        ("msSinceLastIscsiPDU", "ms_since_last_iscsi_pdu"),
        ("msSinceLastScsiCommand", "ms_since_last_scsi_command"),
        ("serviceID", "service_id"),
        ("sessionID", "session_id"),
        ("volumeInstance", "volume_instance")
    ]
    iscsi_session_number = len(result)
    if result != []:
        iscsi_sessions = ''
        for session in result:
            metric_details = ''
            record = len(metrics)
            field_details = ''
            field_detail = ''
            if session['initiator'] is None:
                session['initiator'] = {'alias': 'None', 'initiatorID': 'None'}
            field_details = "initiator_alias=" + \
                session['initiator']['alias'] + "," + "initiator_id=" + \
                str(session['initiator']['initiatorID']) + ","
            if session['authentication']['authMethod'] is None:
                session['authentication']['authMethod'] = "None"
            if session['authentication']['chapAlgorithm'] == "null":
                session['authentication']['chapAlgorithm'] = "None"
            if session['authentication']['chapUsername'] == "null":
                session['authentication']['chapUsername'] = "None"
            field_details = field_details + "auth_method=" + str(session['authentication']['authMethod']) + "," + "chap_algorithm=" + str(
                session['authentication']['chapAlgorithm']) + "," + "chap_username=" + str(session['authentication']['chapUsername']) + ","
            if session['accountName'] is None or len(
                    session['accountName']) == 0:
                session['accountName'] = "None"
            f = 0
            record_fields = len(fields)
            for key in fields:
                key_string = key[1]
                val = session[key[0]]
                str_val = str(val)
                if f < (record_fields - 1):
                    if str_val is not None:
                        field_detail = key_string + "=" + str_val + ","
                    else:
                        field_detail = key_string + "=" + "None" + ","
                else:
                    if str_val is not None:
                        field_detail = key_string + "=" + str_val
                    else:
                        field_detail = key_string + "=" + "None"
                field_details = field_details + field_detail
                f += 1
            m = 0
            metric_detail = ''
            for key in metrics:
                key_string = key[1]
                val = session[key[0]]
                str_val = None  # Ensure str_val is always defined
                if isinstance(val, str):
                    str_val = val
                elif isinstance(val, int):
                    str_val = str(val) + "i"
                else:
                    str_val = "None"
                if m < (record - 1):
                    if str_val is not None:
                        metric_detail = key_string + "=" + str_val + ","
                else:
                    if str_val is not None:
                        metric_detail = key_string + "=" + str_val
                metric_details = metric_details + metric_detail
                m += 1
            iscsi_sessions = iscsi_sessions + \
                ("iscsi_sessions,cluster=" + CLUSTER_NAME + "," +
                 field_details + " " + metric_details + "\n")
        if args.loglevel == 'DEBUG':
            logging.debug("iSCSI sessions payload: " + str(iscsi_sessions))
        time_taken = max(0.0, round(time.time() - time_start, 3))
        logging.info('iSCSI sessions collected. Sending to InfluxDB information about ' + str(iscsi_session_number) +
                     ' sessions from one or more clients. Time taken: ' + str(time_taken) + ' seconds.')
        await send_to_influx(iscsi_sessions)
    else:
        logging.info(
            'iSCSI sessions collected. It appears there are no iSCSI connections. No payload to send to InfluxDB.')
        time_taken = max(0.0, round(time.time() - time_start, 3))
        await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return


async def cluster_performance(session, auth):
    """
    Use GetClusterStats to extract cluster stats and send to InfluxDB.
    """
    function_name = 'cluster_performance'
    time_start = round(time.time(), 3)
    api_payload = "{ \"method\": \"GetClusterStats\" }"
    async with session.post(SF_POST_URL, data=api_payload, auth=auth) as response:
        r = await response.json()
    result = r['result']['clusterStats']
    metrics = [("actualIOPS", "actual_iops"),
               ("averageIOPSize", "average_iops"),
               ("clientQueueDepth", "client_queue_depth"),
               ("clusterUtilization", "cluster_utilization"),
               ("latencyUSec", "latency_usec"),
               ("normalizedIOPS", "normalized_iops"),
               ("readBytesLastSample", "read_bytes_last_sample"),
               ("readLatencyUSec", "read_latency_usec"),
               ("readOpsLastSample", "read_ops_last_sample"),
               ("writeLatencyUSec", "write_latency_usec"),
               ("writeBytesLastSample", "write_bytes_last_sample"),
               ("writeOpsLastSample", "write_ops_last_sample")
               ]
    metric_details = ''
    record = len(metrics)
    n = 0
    for key in metrics:
        key_string = key[1]
        val = result[key[0]]
        if isinstance(val, int):
            str_val = str(val) + "i"
        elif isinstance(val, float) or key[0] == "clusterUtilization":
            str_val = str(round(val, 2))
        else:
            str_val = str(val) + "i"
        if n < (record - 1):
            metric_detail = key_string + "=" + str_val + ","
        else:
            metric_detail = key_string + "=" + str_val
        n += 1
        metric_details = metric_details + metric_detail
    cluster_performance = ("cluster_performance,name=" +
                           CLUSTER_NAME + " " + metric_details + "\n")
    time_taken = max(0.0, round(time.time() - time_start, 3))
    logging.info('Cluster performance collected in ' +
                 str(time_taken) + ' seconds.')
    if args.loglevel == 'DEBUG':
        logging.debug("Cluster performance payload: " +
                      str(cluster_performance))
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    await send_to_influx(cluster_performance)
    return


async def cluster_capacity(session, auth):
    """
    Get GetClusterCapacity results, send a subset to InfluxDB.
    Creates several derived metrics that are not part of the API response.
    """
    function_name = 'cluster_capacity'
    time_start = round(time.time(), 3)
    api_payload = "{ \"method\": \"GetClusterCapacity\" }"
    async with session.post(SF_POST_URL, data=api_payload, auth=auth) as response:
        r = await response.json()
        result = r['result']['clusterCapacity']
        cluster_capacity = ""
        # NOTE: CLUSTER_NAME is a tag, everything else is field data
        # NOTE: thinFactor and storageEfficiency here are SFC-derived metrics
        # and NOT part of SolidFire's GetClusterCapacity API response
        fields = [('activeBlockSpace', 'active_block_space'),
                  ('activeSessions', 'active_sessions'),
                  ('averageIOPS', 'average_iops'),
                  ('clusterRecentIOSize', 'cluster_recent_io_size'),
                  ('compressionFactor', 'compressioN_factor'),
                  ('currentIOPS', 'current_iops'),
                  ('dedupeFactor', 'dedupe_factor'),
                  ('storageEfficiency', 'storage_efficiency'),
                  ('maxIOPS', 'max_iops'),
                  ('maxOverProvisionableSpace', 'max_overprovisionable_space'),
                  ('maxProvisionedSpace', 'max_provisioned_space'),
                  ('maxUsedMetadataSpace', 'max_used_metadata_space'),
                  ('maxUsedSpace', 'max_used_space'),
                  ('nonZeroBlocks', 'non_zero_blocks'),
                  ('peakActiveSessions', 'peak_active_sessions'),
                  ('peakIOPS', 'peak_iops'),
                  ('provisionedSpace', 'provisioned_space'),
                  ('snapshotNonZeroBlocks', 'snapshot_non_zero_blocks'),
                  ('thinFactor', 'thin_factor'),
                  ('totalOps', 'total_ops'),
                  ('uniqueBlocks', 'unique_blocks'),
                  ('uniqueBlocksUsedSpace', 'unique_block_space'),
                  ('usedMetadataSpace', 'used_block_space'),
                  ('usedMetadataSpaceInSnapshots',
                   'used_metadata_space_in_snapshots'),
                  ('usedSpace', 'used_space'),
                  ('zeroBlocks', 'zero_blocks')
                  ]
        metric_details = 'cluster_capacity,name=' + CLUSTER_NAME + ' '
        # NOTE: Thin SFC-derived metric is the ratio of non-zero blocks to the
        # total number of blocks.
        if result['nonZeroBlocks'] != 0:
            result['thinFactor'] = round(
                ((result['nonZeroBlocks'] + result['zeroBlocks']) / result['nonZeroBlocks']), 2)
        else:
            result['thinFactor'] = 1
        if result['uniqueBlocks'] != 0:
            # NOTE: SolidFire clusters with almost empty volumes that have
            # non-empty snapshots can have dedupe ratio < 1. This avoids
            # getting an impossible ratio (< 1).
            result['dedupeFactor'] = round(float(
                result['nonZeroBlocks'] + result['snapshotNonZeroBlocks']) / float(result['uniqueBlocks']), 2)
        else:
            result['dedupeFactor'] = 1
        if result['uniqueBlocksUsedSpace'] != 0:
            # NOTE: 0.93x because GC reserve capacity (7%) is normally empty so
            # not actually compressed
            result['compressionFactor'] = round(
                (result['uniqueBlocks'] * 4096.0) / (result['uniqueBlocksUsedSpace'] * .93), 2)
        else:
            result['compressionFactor'] = 1
        # NOTE: Derived key and not part of the API response. Most users
        # consider the product of compression and dedupe factors to be "storage
        # efficiency", so we calculate it here to eliminate the need to do it
        # in DB or dashboards
        result['storageEfficiency'] = round(
            result['dedupeFactor'] * result['compressionFactor'], 2)
        record = len(fields)
        r = 0
        for item in fields:
            key = item[1]
            val = result[item[0]]
            if isinstance(val, int):
                str_val = str(val) + "i"
            else:
                str_val = str(val)
            if r < (record - 1):
                metric_detail = key + "=" + str_val + ","
            else:
                metric_detail = key + "=" + str_val
            r += 1
            metric_details = metric_details + metric_detail
        cluster_capacity = cluster_capacity + metric_details + "\n"
        if args.loglevel == 'DEBUG':
            logging.debug("Cluster capacity payload: " + str(cluster_capacity))
        logging.info(
            'Cluster capacity names collected. Sending to InfluxDB next.')
        await send_to_influx(cluster_capacity)
    time_taken = max(0.0, round(time.time() - time_start, 3))
    logging.info('Cluster capacity collected in ' +
                 str(time_taken) + ' seconds.')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return


async def cluster_version(session, auth):
    """
    Use GetClusterVersionInfo to get cluster version details and send to InfluxDB.
    """
    function_name = 'cluster_version'
    time_start = round(time.time(), 3)
    api_payload = "{ \"method\": \"GetClusterVersionInfo\" }"
    async with session.post(SF_URL + SF_JSON_PATH, data=api_payload, auth=auth) as response:
        r = await response.json(content_type=None)
        result = r['result']
        api_version = str(result['clusterAPIVersion'])
        version = str(result['clusterVersion'])
        payload = ("cluster_version,name=" + CLUSTER_NAME + ",version=" +
                   str(version) + " " + "api_version=" + str(api_version) + "\n")
    await send_to_influx(payload)
    time_taken = max(0.0, round(time.time() - time_start, 3))
    if args.loglevel == 'DEBUG':
        logging.debug("Cluster version payload: " + str(payload))
        logging.debug('Cluster version info collected in ' +
                      str(time_taken) + ' seconds.')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return


async def drive_stats(session, auth):
    """
    Use ListDriveStats and send selected parts of response to InfluxDB.
    """
    function_name = 'drive_stats'
    time_start = round(time.time(), 3)
    api_payload = "{ \"method\": \"ListDriveStats\" }"
    async with session.post(SF_POST_URL, data=api_payload, auth=auth) as response:
        r = await response.json()
        result = r['result']['driveStats']
        payload = "# DriveStats\n"
        for drive in result:
            drive_id = str(drive['driveID'])
            pop_list = ['driveID', 'failedDieCount', 'lifetimeReadBytes',
                        'lifetimeWriteBytes', 'procTimestamp', 'readBytes',
                        'readMsec', 'readOps', 'readSectors', 'reads',
                        'readsCombined', 'reallocatedSectors', 'reserveCapacityPercent',
                        'sectorSize', 'timestamp', 'totalCapacity',
                        'uncorrectableErrors', 'usedCapacity', 'usedMemory',
                        'writeBytes', 'writeMsec', 'writeOps', 'writeSectors',
                        'writes', 'writesCombined'
                        ]
            for key in pop_list:
                drive.pop(key)
            metric_details = ''
            record = len(drive)
            n = 0
            for key in drive:
                val = drive[key]
                if isinstance(val, int):
                    str_val = str(val) + "i"
                else:
                    str_val = str(val)
                if n < (record - 1):
                    metric_detail = key + "=" + str_val + ","
                else:
                    metric_detail = key + "=" + str_val
                n += 1
                metric_details = metric_details + metric_detail
            payload = payload + ("drive_stats,cluster=" + CLUSTER_NAME +
                                 ",id=" + drive_id + " " + metric_details + "\n")
        if args.loglevel == 'DEBUG':
            logging.debug("Drive stats: " + str(payload))
        await send_to_influx(payload)
    time_taken = max(0.0, round(time.time() - time_start, 3))
    if args.loglevel == 'DEBUG':
        logging.debug(
            'Drive stats collected in ' +
            str(time_taken) +
            ' seconds.')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return


async def schedules(session, auth):
    """
    Use ListSchedules to get snapshot schedules and sends a subset of each to InfluxDB.

    There are different types of schedules. schedules() parses only 'snapshot' type of schedule. If there's none, the measurement will be empty.
    """
    function_name = 'schedules'
    sleep_delay = random.randint(5, 10)
    await asyncio.sleep(sleep_delay)
    time_start = round(time.time(), 3)
    api_payload = "{ \"method\": \"ListSchedules\" }"
    async with session.post(SF_POST_URL, data=api_payload, auth=auth) as response:
        r = await response.json()
        if args.loglevel == 'DEBUG':
            logging.debug("Schedules response:\n" + str(r))
    result = r['result']['schedules']
    if args.loglevel == 'DEBUG':
        logging.debug("Processing schedules:\n" + str(result))

    payload = ''
    payload_header = "schedules,cluster=" + CLUSTER_NAME + ","
    for schedule in result:
        if schedule['scheduleType'] == 'Snapshot':
            # NOTE: `volumeID` appears if for single-volume snapshot schedules while `volumes` appears in multi-volume (group) snapshot schedules!
            # NOTE: Because of that 'volumeID' and 'volumes' are dropped and
            # `volume_count` is used instead
            schedule_fields = [('scheduleID', 'schedule_id')]
            schedule_tags = [
                ('enableRemoteReplication',
                 'enable_remote_replication'),
                ('enableSerialCreation',
                 'enable_serial_creation'),
                ('hasError',
                 'has_error'),
                ('lastRunStatus',
                 'last_run_status'),
                ('scheduleName',
                 'schedule_name'),
                ('name',
                 'snapshot_name'),
                ('paused',
                 'paused'),
                ('recurring',
                 'recurring'),
                ('runNextInterval',
                 'run_next_interval'),
                ('scheduleType',
                 'schedule_type'),
                ('volume_count',
                 'volume_count')]
            if 'scheduleInfo' in schedule:
                for k in ['enableRemoteReplication', 'enableSerialCreation']:
                    if k in schedule['scheduleInfo']:
                        if schedule['scheduleInfo'][k]:
                            schedule['scheduleInfo'][k] = 1
                        else:
                            # NOTE: set to 0 if not True to avoid having to
                            # check for None
                            schedule['scheduleInfo'][k] = 0
                    else:
                        # NOTE: pop the key from schedule_tags and
                        # schedule_fields as we don't need it
                        for l in [schedule_tags, schedule_fields]:
                            p = next(
                                (i for i, t in enumerate(l) if t[0] == k), None)
                            if p is not None:
                                l.pop(p)
                    # NOTE: deal with `volumes` vs `volumeID` stuff
                    if 'volumes' in schedule['scheduleInfo'] or 'volumeID' in schedule['scheduleInfo']:
                        if 'volumes' in schedule['scheduleInfo']:
                            # NOTE: volumes aren't kept because there may be
                            # hundreds in this list
                            schedule['volume_count'] = len(
                                schedule['scheduleInfo']['volumes'])
                            schedule['scheduleInfo'].pop('volumes')
                        elif 'volumeID' in schedule['scheduleInfo']:
                            schedule['volume_count'] = 1
                            schedule['scheduleInfo'].pop('volumeID')
            for key in ['lastRunStatus']:
                if key in schedule:
                    if schedule[key] == 'Success':
                        schedule[key] = 1
                    else:
                        schedule[key] = 0
                else:
                    if args.loglevel == 'DEBUG':
                        logging.debug(
                            "Key >> " + str(key) + " << not in schedule keys")
            for key in ['hasError', 'paused', 'recurring', 'runNextInterval']:
                if schedule[key]:
                    schedule[key] = 1
                else:
                    schedule[key] = 0
            # NOTE: process tags
            tags = ''
            for tag in schedule_tags[0:-1]:
                tag_key = tag[1]
                if tag[0] in schedule:
                    tag_val = schedule[tag[0]]
                tags = tags + tag_key + "=" + str(tag_val) + ","
            for tag in schedule_tags[-1:]:
                tag_key = tag[1]
                tag_val = schedule[tag[0]]
                tags = tags + tag_key + "=" + str(tag_val) + ""
            fields = ' '
            for field in schedule_fields:
                field_val = None  # Ensure field_val is always initialized
                if field[0] in schedule:
                    field_val = schedule[field[0]]
                    if isinstance(field_val, str):
                        field_val = "\"" + str(field_val) + "\""
                elif 'scheduleInfo' in schedule and schedule['scheduleInfo'] is not None and schedule['scheduleInfo'] != {}:
                    try:
                        if field[0] in schedule['scheduleInfo'].keys():
                            field_val = schedule['scheduleInfo'][field[0]]
                            if isinstance(field_val, str):
                                field_val = "\"" + str(field_val) + "\""
                        else:
                            if field[0] == 'name' and 'name' not in schedule['scheduleInfo']:
                                schedule['scheduleInfo']['name'] = "auto-by-SolidFire"
                                field_val = schedule['scheduleInfo']['name']
                                if isinstance(field_val, str):
                                    field_val = "\"" + str(field_val) + "\""
                    except BaseException:
                        field_val = None
                else:
                    if args.loglevel == 'DEBUG':
                        logging.debug("Field not in schedule or scheduleINFO: " +
                                      str(field[0]) + " is type: " + str(type(field_val)))
                    field_val = None
                if next((i for i, t in enumerate(schedule_fields)
                        if t[0] == field[0]), None) == len(schedule_fields) - 1:
                    fields = fields + field[1] + "=" + str(field_val) + " "
                else:
                    fields = fields + field[1] + "=" + str(field_val) + ","
            snapshot_payload = payload_header + tags + fields + "\n"
            payload = payload + snapshot_payload
        else:
            logging.info("Unsupported schedule type observed.")

    time_taken = max(0.0, round(time.time() - time_start, 3))
    if args.loglevel == 'DEBUG':
        logging.debug("Schedules:\n" + str(payload))
        logging.debug('Schedules collected in ' +
                      str(time_taken) + ' seconds.')
    # If there are no schedules, payload will be empty and no data will be sent to InfluxDB
    if payload != '':
        await send_to_influx(payload)
    else:
        logging.info(
            'Schedules collected. It appears there are no snapshot schedules. No payload to send to InfluxDB.')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return


async def snapshot_groups(session, auth):
    """
    Use ListGroupSnapshots to get information about group snapshots and send a subset of each to InfluxDB.

    If there are no group snapshots, the payload will be empty and no data will be sent to InfluxDB.
    """
    function_name = 'snapshot_groups'
    sleep_delay = random.randint(5, 10)
    await asyncio.sleep(sleep_delay)
    time_start = round(time.time(), 3)
    api_payload = "{ \"method\": \"ListGroupSnapshots\" }"
    async with session.post(SF_POST_URL, data=api_payload, auth=auth) as response:
        r = await response.json()
        if args.loglevel == 'DEBUG':
            logging.debug("Group snapshots response:\n" + str(r))
    result = r['result']['groupSnapshots']
    if args.loglevel == 'DEBUG':
        logging.debug("Processing group snapshots:\n" + str(result))
    snap_tags = [
        ('createTime',
         'create_time'),
        ('enableRemoteReplication',
         'enable_remote_replication'),
        ('expirationTime',
         'expiration_time'),
        ('groupSnapshotID',
         'grp_snapshot_id'),
        ('name',
         'grp_snapshot_name'),
        ('remoteStatus',
         'remote_grp_status'),
        ('status',
         'status')]
    snap_fields = [('groupSnapshotID', 'grp_snapshot_id'),
                   ('members', 'members')]
    snap_pop = ['attributes']
    result = sorted(result, key=lambda k: k['groupSnapshotID'])
    payload = ''
    payload_header = "snapshot_groups,cluster=" + CLUSTER_NAME + ","
    for snapshot in result:
        # NOTE: process time values to save disk space
        snap_epoch_sec = (0, 0)  # Ensure snap_epoch_sec is always defined
        try:
            if isinstance(snapshot['members'],
                          list) and snapshot['members'] != []:
                if snapshot['members'][0]['expirationTime'] == 'fifo':
                    # NOTE: If expirationTime is 'fifo', set it to 0, it's
                    # technically equivalent - if no newer snapshots come,
                    # existing will stay around
                    snap_epoch_sec = await time_diff_epoch(snapshot['createTime'], snapshot['createTime'])
                elif snapshot['members'][0]['expirationTime'] is None:
                    # Note: treat this as 'never' and set it to 31 Dec 2037
                    snap_epoch_sec = await time_diff_epoch(snapshot['createTime'], '0')
                else:
                    snap_epoch_sec = await time_diff_epoch(snapshot['createTime'], snapshot['members'][0]['expirationTime'])
                if isinstance(snap_epoch_sec[0], int) and isinstance(
                        snap_epoch_sec[1], int):
                    snapshot['createTime'] = snap_epoch_sec[0]
                    snapshot['members'][0]['expirationTime'] = snap_epoch_sec[1]
                else:
                    snapshot['createTime'] = snap_epoch_sec[0]
            else:
                if args.loglevel == 'DEBUG':
                    logging.debug(
                        "No snapshot[members] or snapshot[members][0] is None")
        except Exception as e:
            logging.error("Error in time_diff_epoch function: " +
                          str(e) +
                          " for snapshot: " +
                          str(snapshot['groupSnapshotID']))
            snapshot['createTime'] = 0
            snapshot['expirationTime'] = 0
        for s in snap_pop:
            if s in snapshot:
                snapshot.pop(s)
        if not snapshot['enableRemoteReplication']:
            snapshot['enableRemoteReplication'] = 0
        else:
            snapshot['enableRemoteReplication'] = 1
        if snapshot['status'] == 'done':
            snapshot['status'] = 1
        else:
            # NOTE: Else map to 0, although there may be "Syncing" and more
            snapshot['status'] = 0
        if 'remoteStatuses' in snapshot:
            if snapshot['remoteStatuses'] != [
            ] and snapshot['remoteStatuses'][0] is not None:
                if snapshot['remoteStatuses'][0]['remoteStatus'] == 'Present':
                    snapshot['remoteStatus'] = 1
                else:
                    # NOTE: Else 0, although there may be intermediate states
                    if args.loglevel == 'DEBUG':
                        logging.debug("Remote status is NOT Present: " +
                                      str(snapshot['remoteStatus']) +
                                      " so setting it to 0.")
                    snapshot['remoteStatus'] = 0
        tags = ''
        for tag in snap_tags:
            tag_key = tag[1]
            if tag[0] in snapshot:
                if snapshot[tag[0]] is None:
                    tag_val = 0
                else:
                    tag_val = snapshot[tag[0]]
            elif tag[0] == 'expirationTime':
                tag_val = snap_epoch_sec[1]
            elif 'remoteStatuses' in snapshot:
                if isinstance(snapshot['remoteStatuses'], list) and snapshot['remoteStatuses'] != [
                ] and snapshot['remoteStatuses'][0] is not None:
                    try:
                        if tag[0] in snapshot['remoteStatuses'][0].keys():
                            tag_val = snapshot['remoteStatuses'][0][tag[0]]
                        else:
                            tag_val = "0"
                    except BaseException:
                        logging.debug(
                            "Tag " + str(
                                tag[0]) + " does NOT exist in snapshot or snapshot-remoteStatuses: ",
                            snapshot['remoteStatuses'][0].keys())
                        tag_val = "0"
                else:
                    tag_val = "0"
            else:
                if args.loglevel == 'DEBUG':
                    logging.debug("Tag  " +
                                  str(tag[0]) +
                                  " does NOT exist in schedule or scheduleInfo: " +
                                  str(tag[0]))
                tag_val = "0"
            if tag == snap_tags[-1]:
                tags = tags + tag_key + "=" + str(tag_val) + ""
            else:
                tags = tags + tag_key + "=" + str(tag_val) + ","
        fields = ' '
        for field in snap_fields:
            field_val = 0
            if field[0] in snapshot:  # if scheduleInfo does not exist, use the schedule object
                if snapshot[field[0]] is None:
                    field_val = 0
                elif isinstance(snapshot[field[0]], list) and snapshot[field[0]] != []:
                    field_val = len(snapshot[field[0]])
                else:
                    field_val = snapshot[field[0]]
            elif 'remoteStatuses' in snapshot:
                if snapshot['remoteStatuses'] != [] and snapshot['remoteStatuses'][0] is not None:
                    try:
                        if field[0] in snapshot['remoteStatuses'][0].keys():
                            field_val = snapshot['remoteStatuses'][0][field[0]]
                    except BaseException:
                        field_val = "0"
            # else: field_val remains as initialized above
            field_key = field[1]
            if isinstance(field_val, str):
                field_val = "\"" + str(field_val) + "\""
            elif isinstance(field_val, int):
                field_val = str(field_val) + "i"
            if field == snap_fields[-1]:
                fields = fields + field_key + "=" + field_val + ""
            else:
                fields = fields + field_key + "=" + field_val + ","
        snapshot_payload = payload_header + tags + fields + "\n"
        payload = payload + snapshot_payload

    time_taken = max(0.0, round(time.time() - time_start, 3))
    logging.info('Snapshots collected in ' + str(time_taken) + ' seconds.')
    if args.loglevel == 'DEBUG':
        logging.debug("Snapshots:\n" + str(payload))
    if payload != '':
        await send_to_influx(payload)
    else:
        logging.info(
            'Snapshots collected. It appears there are no group snapshots. No payload to send to InfluxDB.')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return


async def list_database():
    """
    Call InfluxDB /api/v3/configure/database and return the list of existing databases.
    """
    url = f'https://{INFLUX_HOST}:{INFLUX_PORT}/api/v3/configure/database?format=json'
    headers = {
        'Authorization': f'Bearer {INFLUXDB3_AUTH_TOKEN}',
        'Content-Type': 'application/json'
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as r:
            if r.status == 200:
                data = await r.json()
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug(f"List of databases: {data}")
                dbs = [list(db.values())[0] for db in data]
                return dbs
            else:
                text = await r.text()
                logging.error(f"Failed to list databases. Status: {r.status}, Response: {text}")
                return []


async def create_database_v3(INFLUX_DB):
    """
    Create InfluxDB 3 database using the /api/v3/configure/database endpoint and verify creation.
    """
    url = f'https://{INFLUX_HOST}:{INFLUX_PORT}/api/v3/configure/database'
    headers = {
        'Authorization': f'Bearer {INFLUXDB3_AUTH_TOKEN}',
        'Content-Type': 'application/json'
    }
    payload = {"db": INFLUX_DB}
    dbs = await list_database()
    if INFLUX_DB in dbs:
        logging.info(f"Database '{INFLUX_DB}' exists in InfluxDB. Skipping creation of new database.")
        return
    else:
        logging.error(f"Database '{INFLUX_DB}' not found after creation attempt.")
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as r:
            if r.status == 200:
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug(
                        msg=f"Database '{INFLUX_DB}' created or already exists (HTTP 200). Checking existence...")
                return
            else:
                text = await r.text()
                logging.error(f"Failed to create database '{INFLUX_DB}'. Status: {r.status}, Response: {text}")
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug(f"Database creation error: {text}")
    return


async def send_to_influx(payload):
    """
    Send received payload to InfluxDB 3 over HTTPS.
    """
    original_lines = payload.splitlines()
    payload_lines = len(original_lines)
    if args.loglevel == 'DEBUG':
        logging.debug('send_to_influx() received payload data with ' + str(payload_lines) + ' lines.')
    # If "measurement" is '' or null, we cannot send data to InfluxDB, so error out, print payload, and return False
    # Extract measurement name from the first line
    first_line = payload.splitlines()[0] if payload else ''
    measurement = first_line.split(",", 1)[0] if first_line else ''
    if measurement is None or measurement == '':
        logging.error('Measurement is empty or null. Cannot send data to InfluxDB.')
        logging.error('Payload:\n' + str(payload))
        return False
    # If payload is 0 lines, we cannot send data to InfluxDB, so error out, print payload, and return False
    if payload is None or payload == '' or payload.count('\n') == 0:
        logging.error('Payload is empty or has no lines. Cannot send data to InfluxDB.')
        logging.error('Payload:\n' + str(payload))
        return False
    # Strip trailing space from any misformatted lines, if any
    stripped_lines = [line.rstrip() for line in original_lines]
    payload_stripped = '\n'.join(stripped_lines)
    # Ensure no lines were removed - compare line count before and after stripping
    if len(original_lines) != len(stripped_lines):
        logging.error('We have fewer lines after stripping trailing spaces. This may indicate mishandling.')
        logging.error('Original payload had ' + str(len(original_lines)) + ' lines.')
        logging.error('Stripped payload has ' + str(len(stripped_lines)) + ' lines.')
        logging.error('Payload with stripped lines:\n' + payload_stripped)
        return False
    # Optionally, diff the payloads and log if there are changes
    if args.loglevel == 'DEBUG' and payload != payload_stripped:
        import difflib
        diff = list(difflib.unified_diff(
            payload.splitlines(),
            payload_stripped.splitlines(),
            fromfile='original',
            tofile='stripped',
            lineterm=''
        ))
        if diff:
            logging.debug('Diff between original and stripped payload:\n' + '\n'.join(diff))
        else:
            logging.debug('No differences found between original and stripped payload.')
    payload = payload_stripped
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(enable_cleanup_closed=True)) as session:
        if INFLUXDB3_AUTH_TOKEN is None or INFLUXDB3_AUTH_TOKEN == '':
            logging.error('INFLUXDB3_AUTH_TOKEN is not set. Cannot send data to InfluxDB.')
            return False
        if INFLUX_DB is None or INFLUX_DB == '':
            logging.error('INFLUX_DB is not set. Cannot send data to InfluxDB.')
            return False
        urlPostEndpoint = f"https://{INFLUX_HOST}:{INFLUX_PORT}/api/v3/write_lp?db={INFLUX_DB}&precision=second"
        headers = {
            "Authorization": f"Bearer {INFLUXDB3_AUTH_TOKEN}",
            "Content-Type": "text/plain; charset=utf-8"
        }
        async with session.post(url=urlPostEndpoint, data=payload, headers=headers) as db_session:
            resp = db_session.status
        await session.close()
    if resp != 204:
        logging.error('Failed to send metrics to InfluxDB. Measurement: ' +
                      measurement + ', response code: ' + str(resp))
        logging.error('Payload:\n' + str(payload))
        return False
    else:
        # Do not log successful sends unless in DEBUG mode
        if args.loglevel == 'DEBUG':
            logging.debug('send_to_influx() for ' +
                          measurement + ': response code: 204')
        return True


async def _split_list(long_list: list) -> list:
    """
    Splits a long list into a list of shorter lists.
    """
    list_length = len(long_list)
    if list_length <= CHUNK_SIZE:
        logging.info('List not long enough to split')
        return long_list
    else:
        shorter_lists = [long_list[i:i + CHUNK_SIZE]
                         for i in range(0, len(long_list), CHUNK_SIZE)]
        logging.info('Split ' + str(len(long_list)) +
                     ' long list using chunk size ' + str(CHUNK_SIZE))
        if args.loglevel == 'DEBUG':
            logging.debug('Lists created: ' +
                          str(len(shorter_lists)) +
                          ' . List printout:\n' +
                          str(shorter_lists) +
                          '.')
        return shorter_lists


async def _send_function_stat(cluster_name, function, time_taken):
    """
    Send SFC function execution metrics to InfluxDB.
    """
    try:
        await send_to_influx("sfc_metrics,cluster=" + cluster_name + ",function=" + function + " " + "time_taken=" + str(time_taken) + "\n")
    except BaseException:
        logging.error("Failed to send function stats to InfluxDB.")
    return


async def time_diff_epoch(t1: str, t2: str) -> tuple:
    """
    Calculate the difference between two timestamps in seconds and return a tuple with the first time and time delta in seconds.

    Example: T1 is the start time and T2 is the end time. The function returns T1 in seconds since epoch and T2 as integer delta vs. T2.
    t1 and t2 are ISO 8601-formatted strings. The primary use case is to calculate the time difference between the snapshot creation time and expiration time so that we can tell how recent t1 is and how long before t2 expires.
    If t2 is `null` (never), the function returns 2145844799 (end of Dec 31, 2037) as the expiration time.
    """
    create_time = t1
    expiration_time = t2
    try:
        if t2 == '0':
            dt_e = datetime.datetime(2037, 12, 31, 11, 59, 59)
        else:
            dt_e = datetime.datetime.strptime(
                expiration_time, "%Y-%m-%dT%H:%M:%SZ")
        dt_c = datetime.datetime.strptime(create_time, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        logging.error(
            "Error parsing the timestamps: " +
            str(create_time) +
            " and " +
            str(expiration_time) +
            ". Exiting.")
        exit(400)
    try:
        create_time_epoch = int(dt_c.timestamp())
        ce_epoch = (create_time_epoch, int((dt_e - dt_c).total_seconds()))
    except ValueError:
        logging.error(
            "Error parsing the timestamps: " +
            str(create_time) +
            " and " +
            str(expiration_time) +
            ". Exiting.")
        exit(400)
    if args.loglevel == 'DEBUG':
        logging.debug("==> Time difference in seconds: " + str(ce_epoch) + ".")
    return ce_epoch


async def run_sf_task(task_func, session, auth):
    """
    Helper to run a SolidFire task with error handling for aiohttp and general exceptions.
    """
    try:
        await task_func(session, auth)
    except aiohttp.ContentTypeError as e:
        logging.error(f"ContentTypeError in {task_func.__name__}: {e}")
    except aiohttp.ClientResponseError as e:
        logging.error(f"ClientResponseError in {task_func.__name__}: {e}")
    except Exception as e:
        logging.error(f"Unhandled exception in {task_func.__name__}: {e}")


async def hi_freq_tasks(auth):
    """
    Run high-frequency (1-5 minute interval) tasks for time-sensitive metrics.

    May call some non-time-sensitive functions if their output is essential for gathering time-sensitive metrics.
    """
    time_start = round(time.time(), 3)
    global ITERATION
    ITERATION += 1
    logging.info(
        "==> ITERATION " +
        str(ITERATION) +
        " of high-frequency tasks.")
    session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(
        enable_cleanup_closed=True), headers=sf_headers)
    task_list = [cluster_faults, cluster_performance,
                 node_performance, volume_performance, sync_jobs]
    logging.info('High-frequency tasks: ' + str(len(task_list)))
    bg_tasks = set()
    for t in task_list:
        task = asyncio.create_task(run_sf_task(t, session, auth))
        bg_tasks.add(task)
        task.add_done_callback(bg_tasks.discard)
    await asyncio.gather(*bg_tasks)
    await session.close()
    time_end = round(time.time(), 3)
    time_taken = max(0.0, round(time.time() - time_start, 3))
    logging.info('Completed combined high-frequency collection. Sending to InfluxDB next. Time taken: ' +
                 str(time_taken) + ' seconds.')
    return


async def med_freq_tasks(auth):
    """
    Run medium-frequency (5-30 min interval) tasks for less time-sensitive operation data.
    """
    time_start = round(time.time(), 3)
    session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(
        enable_cleanup_closed=True, timeout_ceil_threshold=15), headers=sf_headers)
    task_list = [accounts, cluster_capacity, iscsi_sessions, volumes]
    logging.info('Medium-frequency tasks: ' + str(len(task_list)))
    bg_tasks = set()
    for t in task_list:
        task = asyncio.create_task(run_sf_task(t, session, auth))
        bg_tasks.add(task)
        task.add_done_callback(bg_tasks.discard)
    await asyncio.gather(*bg_tasks)
    await session.close()
    time_end = round(time.time(), 3)
    time_taken = max(0.0, round(time.time() - time_start, 3))
    logging.info('Completed medium-frequency collection and closed aiohttp session. Time taken: ' +
                 str(time_taken) + ' seconds.')
    return


async def lo_freq_tasks(auth):
    """
    Run low-frequency (0.5-3 hour interval) tasks for non-time-sensitive metrics and events.
    """
    time_start = round(time.time(), 3)
    session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(
        enable_cleanup_closed=True, timeout_ceil_threshold=30), headers=sf_headers)
    task_list = [account_efficiency, cluster_version,
                 drive_stats, schedules, volume_efficiency]
    logging.info('Low-frequency tasks: ' + str(len(task_list)))
    bg_tasks = set()
    for t in task_list:
        task = asyncio.create_task(run_sf_task(t, session, auth))
        bg_tasks.add(task)
        task.add_done_callback(bg_tasks.discard)
    await asyncio.gather(*bg_tasks)
    await session.close()
    time_end = round(time.time(), 3)
    time_taken = max(0.0, round(time.time() - time_start, 3))
    logging.info('Completed low-frequency collection and closed aiohttp session. Time taken: ' +
                 str(time_taken) + ' seconds.')
    return


async def experimental(auth):
    """
    Runs one or more medium-frequency and experimental collector tasks.
    """
    time_start = round(time.time(), 3)
    session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(
        enable_cleanup_closed=True, timeout_ceil_threshold=20), headers=sf_headers)
    task_list = [schedules, snapshot_groups, volume_qos_histograms]
    logging.info('Experimental tasks: ' + str(len(task_list)))
    bg_tasks = set()
    for t in task_list:
        task = asyncio.create_task(t(session, auth))
        bg_tasks.add(task)
        task.add_done_callback(bg_tasks.discard)
    await asyncio.gather(*bg_tasks)
    await session.close()
    time_end = round(time.time(), 3)
    time_taken = max(0.0, round(time.time() - time_start, 3))
    logging.info('Completed combined experimental collection. Sending to InfluxDB next. Time taken: ' +
                 str(time_taken) + ' seconds.')
    return


async def get_cluster_name(auth):
    """
    Get cluster name from SolidFire cluster.
    """
    time_start = round(time.time(), 3)
    url = SF_URL + SF_JSON_PATH + '?method=GetClusterInfo'
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=True, force_close=True, enable_cleanup_closed=True), headers=sf_headers, auth=auth) as session:
        async with session.get(url, allow_redirects=True) as resp:
            if resp.status != 200:
                text = await resp.text()
                logging.error(f"Failed to get cluster info. Status: {resp.status}, Response: {text}")
                raise RuntimeError(f"Failed to get cluster info. Status: {resp.status}")
            try:
                result = await resp.json(content_type=None)
            except Exception:
                text = await resp.text()
                logging.error(f"Failed to decode JSON: {text}")
                raise
    cluster_name = result['result']['clusterInfo']['name']
    time_end = round(time.time(), 3)
    time_taken = round(time_end - time_start, 3)
    logging.info(
        'Obtained SolidFire cluster name for tagging of SolidFire metrics: ' +
        str(cluster_name) +
        '. Time taken: ' +
        str(time_taken) +
        ' seconds.')
    return cluster_name


async def main():
    global ITERATION, CLUSTER_NAME, SF_URL, SF_JSON_PATH, SF_POST_URL, args
    ITERATION = 0
    # Prepare SolidFire auth
    auth = aiohttp.BasicAuth(args.username, args.password)
    CLUSTER_NAME = await get_cluster_name(auth)
    # Ensure InfluxDB database exists or create it
    await create_database_v3(INFLUX_DB)
    # Example: schedule hi/med/lo freq tasks with auth
    scheduler = AsyncIOScheduler(misfire_grace_time=10)
    scheduler.add_job(hi_freq_tasks, 'interval', seconds=INT_HI_FREQ, max_instances=1, args=[auth])
    scheduler.add_job(med_freq_tasks, 'interval', seconds=INT_MED_FREQ, max_instances=1, args=[auth])
    scheduler.add_job(lo_freq_tasks, 'interval', seconds=INT_LO_FREQ, max_instances=1, args=[auth])
    scheduler.start()
    while True:
        await asyncio.sleep(3600)


async def run_all_sf_tasks(auth):
    """
    Create dedicated session for SolidFire API calls with correct auth and headers, and run all SF tasks.
    """
    async with aiohttp.ClientSession(auth=auth, headers=sf_headers) as session:
        task_list = [
            cluster_faults,
            cluster_performance,
            node_performance,
            volume_performance,
            sync_jobs,
            accounts,
            account_efficiency,
            volume_efficiency,
            cluster_capacity,
            cluster_version,
            drive_stats,
            schedules,
            snapshot_groups,
            volumes]
        bg_tasks = set()
        for t in task_list:
            task = asyncio.create_task(run_sf_task(t, session, auth))
            bg_tasks.add(task)
            task.add_done_callback(bg_tasks.discard)
        await asyncio.gather(*bg_tasks)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog="sfc.py",
        description="Collects SolidFire metrics and sends them to InfluxDB.",
        epilog="Author: @scaleoutSean\nhttps://github.com/scaleoutsean/sfc\nLicense: the Apache License 2.0"
    )
    parser.add_argument('-m', '--mvip', nargs='?', const=1, type=str, default='', required=False,
                        help='MVIP or FQDN of SolidFire cluster from which metrics should be collected.')
    parser.add_argument(
        '-u',
        '--username',
        type=str,
        required=False,
        default=os.environ.get(
            'SF_USERNAME',
            ''),
        help='username for SolidFire array. Default: SF_USERNAME')
    parser.add_argument(
        '-p',
        '--password',
        type=str,
        required=False,
        default=os.environ.get(
            'SF_PASSWORD',
            ''),
        help='password for admin account on SolidFire cluster. Default: SF_PASSWORD or, if empty, prompt to provide it.')
    parser.add_argument('-ih', '--influxdb-host', nargs='?', const=1, type=str,
                        default=os.environ.get('INFLUX_HOST', INFLUX_HOST),
                        required=False, help='host IP or name of InfluxDB. Default: ' + INFLUX_HOST)
    parser.add_argument('-ip', '--influxdb-port', nargs='?', const=1, type=int,
                        default=os.environ.get('INFLUX_PORT', INFLUX_PORT),
                        required=False, help='HTTPS port of InfluxDB. Default: ' + INFLUX_PORT)
    parser.add_argument(
        '-id',
        '--influxdb-name',
        nargs='?',
        const=1,
        type=str,
        default=os.environ.get(
            'INFLUX_DB',
            INFLUX_DB),
        required=False,
        help='name of InfluxDB database to use. SFC creates it if it does not exist. Default: ' +
        INFLUX_DB)
    parser.add_argument(
        '-fh',
        '--frequency-high',
        nargs='?',
        const=1,
        type=str,
        default=os.environ.get(
            'INT_HI_FREQ',
            INT_HI_FREQ),
        required=False,
        metavar='HI',
        choices=[
            '60',
            '120',
            '180',
            '300'],
        help='high-frequency collection interval in seconds. Default: ' +
        str(INT_HI_FREQ))
    parser.add_argument(
        '-fm',
        '--frequency-med',
        nargs='?',
        const=1,
        type=str,
        default=os.environ.get(
            'INT_MED_FREQ',
            INT_MED_FREQ),
        required=False,
        metavar='MED',
        choices=[
            "300",
            "600",
            "900"],
        help='medium-frequency collection interval in seconds. Default: ' +
        str(INT_MED_FREQ))
    parser.add_argument(
        '-fl',
        '--frequency-low',
        nargs='?',
        const=1,
        type=str,
        default=os.environ.get(
            'INT_LO_FREQ',
            INT_LO_FREQ),
        required=False,
        metavar='LO',
        choices=[
            "1800",
            "3600",
            "7200",
            "10800"],
        help='low-frequency collection interval in seconds. Default: ' +
        str(INT_LO_FREQ))
    parser.add_argument(
        '-ex',
        '--experimental',
        action='store_true',
        required=False,
        help='use this switch to enable collection of experimental metrics such as volume QoS histograms (interval: 600s, fixed). Default: (disabled, with switch absent)')
    parser.add_argument('-ll', '--loglevel', nargs='?', const=1, type=str, default='INFO', required=False, choices=(
        'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'), help='log level for console output. Default: INFO')
    parser.add_argument('-lf', '--logfile', nargs='?', const=1, type=str, default=None,
                        required=False, help='log file name. SFC logs only to console by default. Default: None')
    parser.add_argument(
        '-c',
        '--ca-chain',
        nargs='?',
        const=1,
        type=str,
        default=None,
        required=False,
        help='Optional filename with your (full) CA chain to be copied to the Ubuntu/Debian/Alpine OS certificate store. Users of other systems may import manually. Default: None')
    parser.add_argument('-v', '--version', action='store_true', required=False,
                        help='Show program version and exit.')
    args = parser.parse_args()

    if args.version:
        print("SFC Version: " + VERSION)
        sys.exit(0)

    FORMAT = '%(asctime)-15s - %(levelname)s - %(funcName)s - %(lineno)d - %(message)s'
    if args.logfile:
        logging.basicConfig(filename=args.logfile, level=args.loglevel,
                            format=FORMAT, datefmt='%Y-%m-%dT%H:%M:%SZ')
        handler = RotatingFileHandler(
            args.logfile,
            mode='a',
            maxBytes=10000000,
            backupCount=1,
            encoding=None,
            delay=True)
        handler.setFormatter(logging.Formatter(FORMAT, datefmt='%Y-%m-%dT%H:%M:%SZ'))
        logging.getLogger().addHandler(handler)
        logging.info('Logging to file: ' + args.logfile)
    else:
        logging.basicConfig(level=args.loglevel, format=FORMAT,
                            datefmt='%Y-%m-%dT%H:%M:%SZ')
    logging.getLogger("asyncio").setLevel(level=args.loglevel)
    logging.getLogger('apscheduler').setLevel(level=args.loglevel)
    logging.getLogger('aiohttp').setLevel(level=args.loglevel)

    if args.username == '' or args.username is None:
        args.username = getpass("Enter the username for SolidFire cluster: ")

    if args.password == '' or args.password is None:
        args.password = getpass(
            "Enter the password for SolidFire cluster (not logged): ")

    if args.frequency_high is None:
        args.frequency_high = INT_HI_FREQ
    else:
        INT_HI_FREQ = int(args.frequency_high)
    if args.frequency_med is None:
        args.frequency_med = INT_MED_FREQ
    else:
        INT_MED_FREQ = int(args.frequency_med)
    if args.frequency_low is None:
        args.frequency_low = INT_LO_FREQ
    else:
        INT_LO_FREQ = int(args.frequency_low)
    logging.info(
        'Hi/med/lo frequency intervals: ' +
        str(INT_HI_FREQ) +
        '/' +
        str(INT_MED_FREQ) +
        '/' +
        str(INT_LO_FREQ) +
        ' seconds.')

    if args.experimental:
        logging.warning('Experimental collectors enabled.')
    else:
        logging.info('Experimental collectors disabled (recommended default)')

    if args.ca_chain is not None and platform.system() == 'Linux' and (distro.id() in ['ubuntu', 'debian', 'alpine']):
        if os.path.exists(args.c):
            logging.info('Copying CA chain to OS certificate store.')
            os.system(
                'sudo cp ' +
                args.ca_chain +
                ' /usr/local/share/ca-certificates/')
            # chmod 644 is required for the file to be picked up by
            # update-ca-certificates
            os.system(
                'sudo chmod 644 /usr/local/share/ca-certificates/' +
                os.path.basename(
                    args.ca_chain))
            os.system('sudo update-ca-certificates')
            logging.info('OS certificate store refreshed.')
        else:
            logging.error('CA chain file not found. Exiting.')
            sys.exit(1)

    # The below works for SolidFire 12.5, 12.7 or a higher v12
    SF_JSON_PATH = '/json-rpc/12.5/'
    SF_URL = 'https://' + SF_MVIP
    SF_POST_URL = SF_URL + SF_JSON_PATH

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        logging.info("Exception: %s", str(e))
