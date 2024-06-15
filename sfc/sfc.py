#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# sfc.py

###############################################################################
# Synopsis:                                                                   #
# SFC v2 schedules and executes gathering of SolidFire API object properties  #
#  and performance metrics, enriches obtained data and sends it to InfluxDB v1#
#                                                                             #
# SFC v1 used to be part of NetApp HCI Collector.                             #
#                                                                             #
# Author: @scaleoutSean                                                       #
# https://github.com/scaleoutsean/sfc                                         #
# License: the Apache License Version 2.0                                     #
###############################################################################

# =============== imports =====================================================


import argparse
import aiohttp
import asyncio
from aiohttp import ClientSession, ClientResponseError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import datetime
from getpass import getpass
import logging
import logging.handlers
from logging.handlers import RotatingFileHandler
from logging.handlers import QueueHandler
import os
import random
import re
import sys
if not sys.warnoptions:
    import os
    import warnings
import time
warnings.simplefilter("default")
os.environ["PYTHONWARNINGS"] = "default"

# =============== default vars ================================================

# Create reporting-only admin user with read-only access to the SolidFire API.
# Modify these five variables to match your environment if you want hardcoded
# values.

INFLUX_HOST = '192.168.50.184'
INFLUX_PORT = '32290'
INFLUX_DB = 'sfc'
SF_MVIP = '192.168.1.30'
SF_USERNAME = 'monitor'
# SF_PASSWORD = ''


# Use startup sfc.py startup arguments (sfc.py -h) to modify main intervals
INT_HI_FREQ = 60
INT_MED_FREQ = 600
INT_LO_FREQ = 3600
INT_EXPERIMENTAL_FREQ = 600

# Check the source code to see what this does
CHUNK_SIZE = 24
# =============== functions code ==============================================


headers = {'Accept': 'application/json'}
headers['Accept-Encoding'] = 'deflate, gzip;q=1.0, *;q=0.5'
headers['Content-Type'] = 'application/json'


async def volumes(session, **kwargs):
    """
    Extracts useful volume properties including volume name.

    Other SFC functions may use this function to get ID-to-name mapping for volumes.
    """
    time_start = round(time.time(), 3)
    function_name = 'volumes'
    # NOTE: the volumeID pair is out of order because it maps to 'id' which
    # *is* in proper order. We have two sets of tags depending if the volume is
    # paired
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
        async with session.post(SF_POST_URL, data=api_payload) as response:
            r = await response.json()
            result = r['result']['volumes']
    except Exception as e:
        logging.error('Function ' + function_name +
                      ': volume information not obtained - returning.')
        logging.error(e)
        return
    if not kwargs:
        volumes = ''
        for volume in result:
            single_volume = "volumes,cluster=" + CLUSTER_NAME + ","
            # NOTE: this needs to be an integer in InfluxDB, None won't work
            if (volume['qosPolicyID'] is None):
                volume['qosPolicyID'] = 0
            # NOTE: this section gathers volume pairing information when
            # volumePairs is not empty
            volume_paired = False
            if volume['volumePairs'] != []:
                volume_pairs = volume['volumePairs']
                logging.debug(
                    "Volume pairs (volume['volumePairs']) for volume ID: " + str(
                        volume['volumeID']) + ": " + str(volume_pairs))
                logging.debug('Volume replication enabled for volume ' +
                              str(volume['volumeID']) +
                              '. Calling extract_volume_pair().')
                vp = await extract_volume_pair(volume_pairs)
                logging.debug(
                    'VP returned from extract_volume_pair: ' + str(vp))
                if vp != {}:
                    try:
                        for k in vp:
                            volume[k] = vp[k]
                        vp = {}
                        volume_paired = True
                        logging.debug(
                            'Volume pair information obtained, extracted and added to volume ' + str(
                                volume['volumeID']) + '.')
                    except BaseException:
                        logging.error(
                            'Volume pair information not obtained for volume could not be added to ' + str(
                                volume['volumeID']) + ' key.')
                else:
                    logging.error('Volume pair information not returned for volume ' +
                                  str(volume['volumeID']) + ' by extract_volume_pair().')
            else:
                logging.debug(
                    'Volume replication not enabled for volume ' + str(volume['volumeID']) + '.')

            if volume_paired == True:
                tags = tags_paired
                fields = fields_paired
                logging.debug('Volume ' +
                              str(volume['volumeID']) +
                              ' is paired, using paired tags and fields.')
            else:
                tags = tags_non_paired
                fields = fields_non_paired
                logging.debug('Volume ' +
                              str(volume['volumeID']) +
                              ' is not paired, using non-paired tags and fields.')
            for tag in tags:
                k = tag[0]
                nk = tag[1]
                val = volume[k]
                kv = nk + "=" + str(volume[k])
                if k in [x[0] for x in tags[0:-1]]:
                    single_volume = single_volume + kv + ","
                else:
                    single_volume = single_volume + kv + " "
                if volume_paired == True:
                    logging.debug("single_volume tags for volume + " +
                                  str(volume['volumeID']) + ": " + str(single_volume))
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
                if volume_paired == True:
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
    time_taken = (round(time.time(), 3) - time_start)
    if args.loglevel == 'DEBUG':
        logging.debug("Volumes payload:\n " + str(volumes) + ".")
    logging.info('Volumes collected in ' + str(time_taken) + ' seconds.')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return volumes


async def extract_volume_pair(volume_pairs: list) -> dict:
    """
    Extract information for first volume pairing from volume replication list and return a dict with contents.

    This is a helper function for the volumes() function.
    Currently only the first paired volume is processed. Additional volumes and values may be added in the future.
    """
    time_start = round(time.time(), 3)
    function_name = 'extract_volume_pair' 
    vp = {}
    if volume_pairs == [] or len(volume_pairs) > 1:
        logging.debug('volume_pairs list ' + str(volume_pairs) + '.')
        logging.warning(
            'Volume pairs list is empty or has more than one pair, which is currently not implemented. Returning.')
        return {}
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
            # volumes. Unknown is set to 100 to leave room for existing states not yet here.
            
            mode_map = [('Async', 1), ('Sync', 2), ('SnapshotsOnly', 3), ('None', 100)]
            mode = vp_dict['remoteReplication']['mode'] if vp_dict['remoteReplication']['mode'] in [x[0] for x in mode_map] else 'None'
            vp['remote_replication_mode'] = next((x[1] for x in mode_map if x[0] == mode), None)            

            # NOTE: one option is to change these into Pythonic snake case, and deal with it in Grafana
            # and another is to simply use integers for the states and assign 100 to unseen and unknown 
            # Source of state keys: NetApp TR-4741 (2020), page 26, and observation on SF Demo VM 12.5

            rep_state_map = [('Active', 1), ('Idle', 2), ('PausedDisconnected', 3), ('PausedManual', 4), ('PausedDisconnected', 5), ('PausedManualRemote', 6), ('ResumingConnected', 7), ('ResumingDataTransfer', 8), ('ResumingLocalSync', 9), ('ResumingRRSync', 10), ('None', 100)]
            rep_state_mode = vp_dict['remoteReplication']['state'] if vp_dict['remoteReplication']['state'] in [x[0] for x in rep_state_map] else 'None'
            vp['remote_replication_state'] =  next((x[1] for x in rep_state_map if x[0] == rep_state_mode), None)
            
            snap_state_map = [('Active', 1), ('Idle', 2), ('PausedDisconnected', 3), ('PausedManual', 4), ('PausedDisconnected', 5), ('PausedManualRemote', 6), ('ResumingConnected', 7), ('ResumingDataTransfer', 8), ('ResumingLocalSync', 9), ('ResumingRRSync', 10), ('None', 100)]
            snap_state_mode = vp_dict['remoteReplication']['snapshotReplication']['state'] if vp_dict['remoteReplication']['snapshotReplication']['state'] in [x[0] for x in snap_state_map] else 'None'
            vp['remote_replication_snap_state'] = next((x[1] for x in snap_state_map if x[0] == snap_state_mode), None)
                
        except KeyError as e:
            logging.warning(
                'KeyError while parsing remoteReplication dictionary: ' + str(e))
            return {}
    time_taken = (round(time.time(), 3) - time_start)
    if args.loglevel == 'DEBUG':
        logging.debug('Volume pair payload: ' + str(vp) + '.')
    logging.info(
        'Volume pair data extracted in ' +
        str(time_taken) +
        ' seconds.')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return vp

async def sync_jobs(session):
    """
    Obtains information about synchronization jobs using ListSyncJobs and sends to InfluxDB.

    Sync jobs are used in SolidFire replication to initially synchronize volume data between paired volumes.
    This function currently only supports 'remote' type sync jobs.
    """
    time_start = round(time.time(), 3)
    function_name = 'sync_jobs'
    api_payload = "{ \"method\": \"ListSyncJobs\" }"
    async with session.post(SF_POST_URL, data=api_payload) as response:
        r = await response.json()
    result = r['result']['syncJobs']
    if args.loglevel == 'DEBUG':
        logging.debug('Sync jobs result: ' + str(result) + '.')
    if result == []:
        logging.debug('No sync jobs found. Returning.')
        return
    else:
        # NOTE: there are different kinds of jobs (clone, remote replication, slice synchronization)
        # Ech has unique tags and fields
        # See https://docs.netapp.com/us-en/element-software/api/reference_element_api_syncjob.html
        # type: one of clone slice block remote
        tags = [('dstVolumeID', 'dst_volume_id'), ('stage', 'stage'), ('type', 'type')]
        fields = [('blocksPerSecond', 'blocks_per_sec'), ('elapsedTime', 'elapsed_time'), ('percentComplete', 'pct_complete'), ('remainingTime', 'remaining_time')]
        sync_jobs = ''
        for i in result:
            # NOTE: this is a single sync job of 'remote' type. Until we get API examples with real-life data, other types will be discarded
            if i['type'] == 'remote':
                logging.info('Processing remote sync job with ID ' + str(i['dstVolumeID']) + '.')
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
                    # NOTE: https://github.com/NetAppDocs/element-software/issues/204
                    if nk in ['blocks_per_sec', 'elapsed_time', 'pct_complete']: 
                        val = str(val) + "i"
                    elif nk == 'remaining_time':
                        # NOTE: Uhm, yeah. It's possible.                        
                        if val == None:
                            val = "0"
                    # NOTE: looks like an API bug, remaining_time is a float
                    else:    
                        val = str(val) 
                    kv = nk + "=" + val
                    if k in [x[0] for x in fields[0:-1]]:
                        single_sync_job = single_sync_job + kv + ","
                    else:
                        single_sync_job = single_sync_job + kv + " "
                sync_jobs = sync_jobs + single_sync_job + "\n"
            else:
                logging.debug('Sync job type ' + str(i['type']) + ' is not yet supported. You may submit this record to have it considered for inclusion in SFC. Skipping.')
                logging.info('Skipped sync job: ' + str(i))
    await send_to_influx(sync_jobs)
    time_taken = (round(time.time(), 3) - time_start)
    if args.loglevel == 'DEBUG':
        logging.debug('Sync jobs payload:\n' + str(sync_jobs) + '.')
    logging.info(
        'Sync jobs obtained and sent in ' +
        str(time_taken) +
        ' seconds.')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return

async def volume_performance(session, **kwargs):
    """
    Extract volume stats for additional processing and sends to InfluxDB.

    Uses volumes() function to get ID-to-name mapping for volumes.
    """
    time_start = round(time.time(), 3)
    function_name = 'volume_performance'
    try:
        all_volumes = await volumes(session, names=True)
        isinstance(all_volumes, list)
        logging.debug('Volume information obtained and is a list of ' +
                      str(len(all_volumes)) + ' elements.')
    except Exception as e:
        logging.error(
            'Volume information not obtained or malformed. Returning.')
        logging.error(e)
        return
    fields = [('actualIOPS', 'actual_iops'), ('averageIOPSize', 'average_io_size'), ('asyncDelay', 'async_delay'), ('burstIOPSCredit', 'burst_io_credit'), ('clientQueueDepth', 'client_queue_depth'), ('latencyUSec', 'latency_usec'), ('nonZeroBlocks', 'non_zero_blocks'),
              ('normalizedIOPS', 'normalized_iops'), ('readBytes', 'read_bytes'), ('readBytesLastSample', 'read_bytes_last_sample'), ('readLatencyUSec',
                                                                                                                                      'read_latency_usec'), ('readOpsLastSample', 'read_ops_last_sample'), ('throttle', 'throttle'), ('volumeSize', 'volume_size'),
              ('volumeUtilization', 'volume_utilization'), ('writeBytes', 'write_bytes'), ('writeBytesLastSample', 'write_bytes_last_sample'), ('writeLatencyUSec', 'write_latency_usec'), ('writeOpsLastSample', 'write_ops_last_sample'), ('zeroBlocks', 'zero_blocks')]    
    if len(all_volumes) > CHUNK_SIZE:
        logging.info('Splitting volumes list with length ' +
                     str(len(all_volumes)) + ' using chunk size ' + str(CHUNK_SIZE) + '.')
        volume_lists = await _split_list(all_volumes)
    else:
        volume_lists = []
        volume_lists.append(all_volumes)    
    
    volumes_performance = ''
    b = 0
    for volume_batch in volume_lists:
        logging.info('Processing volume batch ' + str(b) + ' with ' +
                     str(len(volume_batch)) + ' volumes.')
        volume_batch_ids = [x[0] for x in volume_batch]
        logging.info("Volume batch IDs:\n" + str(volume_batch_ids) + ".")
        api_payload = "{ \"method\": \"ListVolumeStats\", \"params\": { \"volumeIDs\": " + \
            str(volume_batch_ids) + "}}"
        # logging.debug("API payload for volume stats:\n" + str(api_payload) + ".")
        async with session.post(SF_POST_URL, data=api_payload) as response:
            r = await response.json()
        result = r['result']['volumeStats']
        # NOTE: we need to convert the asyncDelay from null to integer or parse the string to seconds:int
        # NOTE: asyncDelay is a string like "00:00:01.123456" (1.1s)
        async_delay_pattern = re.compile('\d{2}:\d{2}:\d{2}.\d{5}')
        for volume in result:
            # logging.debug('Processing volume ' + str(volume['volumeID']) + '. Data: ' + str(volume) + '.')
            if volume['asyncDelay'] != None:
                # logging.debug('Volume has non-null asyncDelay. Converting to seconds for volume ' + str(volume['volumeID']) + '.')                        
                try: 
                    if async_delay_pattern.match(volume['asyncDelay']):
                        async_delay_tp = datetime.datetime.strptime(volume['asyncDelay'],"%H:%M:%S.%f")
                        volume['asyncDelay'] = async_delay_tp.hour * 3600 + async_delay_tp.minute * 60 + async_delay_tp.second
                        # logging.debug('Converted asyncDelay to seconds for volume ' + str(volume['volumeID']) + ': ' + str(volume['asyncDelay']) + '.')
                except TypeError as e:
                    logging.error('Failed to convert asyncDelay text string to seconds (int) for volume ' + str(volume['volumeID']) + '. Problem string: ' + str(volume['asyncDelay']) + '. Setting to -1 to surface in Grafana. Error: ' + str(e) + '.')
                    volume['asyncDelay'] = int(-1)
            else:
                logging.debug('Volume has null asyncDelay. Setting it to -1 for volume ' + str(volume['volumeID']) + '.')
                volume['asyncDelay'] = -1
            # logging.debug('Processed volume ' + str(volume['volumeID']) + '. Data: ' + str(volume) + '.')
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
            ts = str(int(round(time.time(),0))) # NOTE: timestamp for the record
            volume_performance = volume_performance + volume_line + ts + "\n"
            # logging.debug('Volume performance line for volume ID ' + str(volume['volumeID']) + ':\n' + str(volume_line))
        b = b + 1
        volumes_performance = volumes_performance + volume_performance
        # logging.debug('Volume performance batch for batch item ' + str(b) + ':\n' + str(volume_performance))
    await send_to_influx(volumes_performance)
    time_taken = (round(time.time(), 3) - time_start)
    if args.loglevel == 'DEBUG':
        logging.debug("Volume performance payload:\n" + str(volumes_performance))
    logging.info('Volume performance gathered in ' +
                 str(time_taken) + ' seconds')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return


async def accounts(session):
    """
    Call SolidFire GetClusterAccounts, extract data from response and send to InfluxDB.
    """
    time_start = round(time.time(), 3)
    function_name = 'accounts'
    accounts = ''
    api_payload = "{ \"method\": \"ListAccounts\" }"
    async with session.post(SF_POST_URL, data=api_payload) as response:
        r = await response.json()
    for account in r['result']['accounts']:
        if (account['enableChap'] == True):
            try:
                # NOTE: remove CHAP secrets
                account.pop('initiatorSecret')
                account.pop('targetSecret')
            except KeyError:
                # NOTE: if they don't exist, we don't need to remove them
                logging.warning(
                    "Did not find account (CHAP) secrets to remove from API response" + str(account['accountID']))
                pass
        if len(account['volumes']) > 0:
            volume_count = str(len(account['volumes']))
        else:
            volume_count = "0"
        if account['status'] == "active":
            account_active = "1"
        else:
            account_active = "0"
        accounts = accounts + "accounts,id=" + str(account['accountID']) + ",name=" + str(
            account['username']) + " " + "active=" + account_active + "i" + ",volume_count=" + volume_count + "i" + "\n"
    await send_to_influx(accounts)
    time_taken = (round(time.time(), 3) - time_start)
    if args.loglevel == 'DEBUG':
        logging.debug("Account (tenants) list payload: " + str(accounts))
    logging.info('Tenant accounts gathered in ' +
                 str(time_taken) + ' seconds.')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return accounts


async def account_efficiency(session):
    """
    Process account efficiency response from ListAccounts, GetAccountEfficiency and submit to InfluxDB.
    """
    function_name = 'account_efficiency'
    time_start = round(time.time(), 3)
    account_efficiency = ''
    api_payload = "{ \"method\": \"ListAccounts\", \"params\": {}}"
    async with session.post(SF_POST_URL, data=api_payload) as response:
        r = await response.json()
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
        async with session.post(SF_POST_URL, data=api_payload) as response:
            r = await response.json()
            compression = round(r['result']['compression'], 2)
            deduplication = round(r['result']['deduplication'], 2)
            thin_provisioning = round(r['result']['thinProvisioning'], 2)
            storage_efficiency = round((compression * deduplication), 2)
            account_id_efficiency = "account_efficiency,id=" + str(account[0]) + ",name=" + str(account[1]) + " " + "compression=" + str(
                compression) + ",deduplication=" + str(deduplication) + ",storage_efficiency=" + str(storage_efficiency) + ",thin_provisioning=" + str(thin_provisioning) + "\n"
            account_efficiency = account_efficiency + account_id_efficiency
    time_taken = (round(time.time(), 3) - time_start)
    logging.info('Account efficiency collected in ' +
                 str(time_taken) + ' seconds.')
    if args.loglevel == 'DEBUG':
        logging.debug("Account efficiency payload: " + str(account_efficiency))
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    await send_to_influx(account_efficiency)
    return


async def volume_efficiency(session):
    """
    Use ListVolumes, GetVolumeEfficiency to gather volume efficiency and submit to InfluxDB.
    """
    function_name = 'volume_efficiency'
    time_start = round(time.time(), 3)
    volume_efficiency = ''
    api_payload = "{ \"method\": \"ListVolumes\", \"params\": {}}"
    async with session.post(SF_POST_URL, data=api_payload) as response:
        r = await response.json()
        volume_id_name_list = []
        for volume in r['result']['volumes']:
            volume_id_name_list.append((volume['volumeID'], volume['name']))
    short_lists = await _split_list(volume_id_name_list)
    for short_list in short_lists:
        for volume in short_list:
            api_payload = "{ \"method\": \"GetVolumeEfficiency\", \"params\": { \"volumeID\": " + \
                str(volume[0]) + " }}"
            async with session.post(SF_POST_URL, data=api_payload) as response:
                r = await response.json()
                compression = round(r['result']['compression'], 2)
                deduplication = round(r['result']['deduplication'], 2)
                storage_efficiency = round(
                    r['result']['deduplication'] * r['result']['compression'], 2)
                thin_provisioning = round(r['result']['thinProvisioning'], 2)
                volume_id_efficiency = "volume_efficiency,id=" + str(volume[0]) + ",name=" + str(volume[1]) + " " + "compression=" + str(compression) + ",deduplication=" + str(
                    deduplication) + ",storage_efficiency=" + str(storage_efficiency) + ",thin_provisioning=" + str(thin_provisioning) + "\n"
                volume_efficiency = volume_efficiency + volume_id_efficiency
                await send_to_influx(volume_efficiency)
    if args.loglevel == 'DEBUG':
        logging.debug("Volume efficiency payload: " + str(volume_efficiency))
        logging.info('Volume efficiency collected in ' +
                     str(time_taken) + ' seconds.')
    time_taken = (round(time.time(), 3) - time_start)
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return


async def cluster_faults(session):
    """
    Use GetClusterFaults to extract cluster faults and return for sending to InfluxDB.
    """
    time_start = round(time.time(), 3)
    function_name = 'cluster_faults'
    api_payload = "{ \"method\": \"ListClusterFaults\" }"
    async with session.post(SF_POST_URL, data=api_payload) as response:
        r = await response.json()
    group = {'bestPractices': 0, 'error': 0, 'critical': 0, 'warning': 0}
    for fault in r['result']['faults']:
        if fault['severity'] in group and fault['resolved'] == False:
            group[fault['severity']] += 1
    if group['critical'] > 0 or group['error'] > 0 or group['warning'] > 0 or group['bestPractices'] > 0:
        faults_total = str(
            group['critical'] + group['error'] + group['warning'] + group['bestPractices'])
        cluster_faults = "cluster_faults,total=" + faults_total + " " + "critical=" + str(group['critical']) + "i" + ",error=" + str(
            group['error']) + "i" + ",warning=" + str(group['warning']) + "i" + ",bestPractices=" + str(group['bestPractices']) + "i" + "\n"
    else:
        cluster_faults = "cluster_faults,total=0 critical=0i,error=0i,warning=0i,bestPractices=0i" + "\n"
    time_taken = (round(time.time(), 3) - time_start)
    await send_to_influx(cluster_faults)
    logging.info('Cluster faults gathered in ' + str(time_taken) + ' seconds.')
    if args.loglevel == 'DEBUG':
        logging.debug("Cluster faults payload: " + str(cluster_faults))
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return cluster_faults


async def volume_qos_histograms(session):
    """
    Get ListVolumeQoSHistograms results, extract, transform and send to InfluxDB.
    """
    # NOTE: https://docs.influxdata.com/influxdb/v1/query_language/functions/#histogram
    # NOTE: Delay to avoid executing concurrently with other functions
    sleep_delay = random.randint(5, 10)
    await asyncio.sleep(sleep_delay)
    time_start = round(time.time(), 3)
    function_name = 'volume_qos_histograms'
    if args.experimental == False:
        logging.warning('QoS histograms are not enabled. Returning...')
        return
    try:
        volumes_dict = await volumes(session, names_dict=True)
        isinstance(volumes, dict)
        logging.debug('ID-volume KV pairs obtained from volumes: ' +
                      str(len(volumes_dict)) + ' pairs.')
    except Exception as e:
        logging.error(
            'Volume information not returned by volumes function or response malformed:' + str(volumes_dict))
        logging.error(e)
        return
    api_payload = "{ \"method\": \"ListVolumeQoSHistograms\" }"
    async with session.post(SF_POST_URL, data=api_payload) as response:
        r = await response.json()
        result = r['result']['qosHistograms']
    qosh_list = await _split_list(result)
    for qosh_batch in qosh_list:
        for hg in qosh_batch:
            vol_id_name = (hg['volumeID'], volumes_dict[hg['volumeID']])
            await qos_histogram_processor(hg, vin=vol_id_name)
    logging.info('QoS histograms collected and sent to InfluxDB.')
    time_taken = (round(time.time(), 3) - time_start)
    logging.info('Volume QoS histograms collected in ' +
                 str(time_taken) + ' seconds.')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    await send_to_influx("sfc_metrics,cluster=" + CLUSTER_NAME + ",function=volume_qos_histograms" + " " + "time_taken=" + str(time_taken) + "\n")
    return


async def qos_histogram_processor(hg, **kwargs):
    """
    Processes QoS histogram output from volume_qos_histograms function.
    """
    histogram_types = ['belowMinIopsPercentages', 'minToMaxIopsPercentages', 'readBlockSizes',
                       'targetUtilizationPercentages', 'throttlePercentages', 'writeBlockSizes']
    histogram_types = [('belowMinIopsPercentages', 'below_min_iops_percentages'), ('minToMaxIopsPercentages', 'min_to_max_iops_percentages'), ('readBlockSizes', 'read_block_sizes'),
                       ('targetUtilizationPercentages', 'target_utilization_percentage'), ('throttlePercentages', 'throttle_percentages'), ('writeBlockSizes', 'write_block_sizes')]
    belowMinIopsPercentages = [('Bucket1To19', 'b_01_to_19'), ('Bucket20To39', 'b_20_to_39'), (
        'Bucket40To59', 'b_40_to_59'), ('Bucket60To79', 'b_60_to_79'), ('Bucket80To100', 'b_80_to_100')]
    minToMaxIopsPercentages = [('Bucket1To19', 'b_001_to_019'), ('Bucket20To39', 'b_020_to_039'), ('Bucket40To59', 'b_040_to_059'),
                               ('Bucket60To79', 'b_060_to_079'), ('Bucket80To100', 'b_080_to_100'), ('Bucket101Plus', 'b_101_plus')]
    readBlockSizes = [('Bucket512To4095', 'b_000512_to_004095'), ('Bucket4096To8191', 'b_004096_to_008191'), ('Bucket8192To16383', 'b_008192_to_016383'), ('Bucket16384To32767',
                                                                                                                                                           'b_016384_to_032767'), ('Bucket32768To65535', 'b_032768_to_65535'), ('Bucket65536To131071', 'b_065536_to_131071'), ('Bucket131072Plus', 'b_131072_plus')]
    targetUtilizationPercentages = [('Bucket0', 'b_000'), ('Bucket1To19', 'b_001_to_019'), ('Bucket20To39', 'b_020_to_039'), (
        'Bucket40To59', 'b_040_to_059'), ('Bucket60To79', 'b_060_079'), ('Bucket80To100', 'b_080_to_100'), ('Bucket101Plus', 'b_101_plus')]
    throttlePercentages = [('Bucket0', 'b_00'), ('Bucket1To19', 'b_00_to_19'), ('Bucket20To39', 'b_20_to_30'), (
        'Bucket40To59', 'b_40_to_59'), ('Bucket60To79', 'b_60_to_79'), ('Bucket80To100', 'b_80_to_100')]
    writeBlockSizes = [('Bucket512To4095', 'b_000512_to_004095'), ('Bucket4096To8191', 'b_004096_to_008191'), ('Bucket8192To16383', 'b_008192_to_016383'), ('Bucket16384To32767',
                                                                                                                                                            'b_016384_to_032767'), ('Bucket32768To65535', 'b_032768_to_65535'), ('Bucket65536To131071', 'b_065536_to_131071'), ('Bucket131072Plus', 'b_131072_plus')]
    hg_names = (belowMinIopsPercentages, minToMaxIopsPercentages, readBlockSizes,
                targetUtilizationPercentages, throttlePercentages, writeBlockSizes)
    vol_id_name = kwargs['vin']
    n = 0
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
        await send_to_influx(volume_kvs_string)
        n = n + 1
    return


async def node_performance(session):
    """
    Use GetClusterStats to extract node stats and return for sending to InfluxDB.
    """
    time_start = round(time.time(), 3)
    function_name = 'node_performance'
    api_payload = "{ \"method\": \"ListNodeStats\" }"
    async with session.post(SF_POST_URL, data=api_payload) as response:
        r = await response.json()
    result = r['result']['nodeStats']['nodes']
    metrics = [("cpu", "cpu"), ("networkUtilizationCluster", "network_utilization_cluster"),
               ("networkUtilizationStorage", "network_utilization_storage")]
    load_histogram_metrics = [("Bucket0", "bucket_00_00"), ("Bucket1To19", "bucket_01_to_19"), ("Bucket20To39", "bucket_20_to_39"), (
        "Bucket40To59", "bucket_40_to_59"), ("Bucket60To79", "bucket_60_to_79"), ("Bucket80To100", "bucket_80_to_100")]
    node_performance = ''
    for node in result:
        metric_details = ''
        for key in load_histogram_metrics:
            key_string = key[1]
            val = node['ssLoadHistogram'][key[0]]
            if isinstance(val, int):
                str_val = str(val) + "i"
            else:
                pass
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
    time_taken = (round(time.time(), 3) - time_start)
    if args.loglevel == 'DEBUG':
        logging.debug("Node stats: " + str(node_performance))
    logging.info('Node stats collected in ' + str(time_taken) + ' seconds.')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return


async def iscsi_sessions(session):
    """
    Uses GetIscsiSessions to extract iSCSI sessions and return for sending to InfluxDB.
    """
    function_name = 'iscsi_sessions'
    time_start = round(time.time(), 3)
    api_payload = "{ \"method\": \"ListISCSISessions\" }"
    async with session.post(SF_POST_URL, data=api_payload) as response:
        r = await response.json()
    result = r['result']['sessions']
    fields = [
        ("accountID", "account_id"), ("accountName", "account_name"), ("initiatorIP",
                                                                       "initiator_ip"), ("initiatorName", "initiator_name"), ("initiatorSessionID", "initiator_session_id"),
        ("nodeID", "node_id"), ("targetIP", "target_ip"), ("targetName",
                                                           "target_name"), ("virtualNetworkID", "virtual_network_id"), ("volumeID", "volume_id")
    ]
    metrics = [
        ("msSinceLastIscsiPDU", "ms_since_last_iscsi_pdu"), ("msSinceLastScsiCommand",
                                                             "ms_since_last_scsi_command"),
        ("serviceID", "service_id"), ("sessionID",
                                      "session_id"), ("volumeInstance", "volume_instance")
    ]
    iscsi_session_number = len(result)
    if iscsi_session_number > 0:
        iscsi_sessions = ''
        for session in result:
            metric_details = ''
            record = len(metrics)
            field_details = ''
            field_detail = ''
            field_details = "initiator_alias=" + \
                session['initiator']['alias'] + "," + "initiator_id=" + \
                str(session['initiator']['initiatorID']) + ","
            if session['authentication']['authMethod'] is None:
                session['authentication']['authMethod'] = "None"
            if session['authentication']['chapAlgorithm'] == "null":
                session['authentication']['chapAlgorithm'] = "None"
            if session['authentication']['chapUsername'] == "null":
                session['authentication']['chapUsername'] = "None"
            field_details = field_details + "auth_method=" + session['authentication']['authMethod'] + "," + "chap_algorithm=" + str(
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
                if isinstance(val, str):
                    str_val = val
                elif isinstance(val, int):
                    str_val = str(val) + "i"
                else:
                    pass
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
        time_taken = (round(time.time(), 3) - time_start)
        logging.info('iSCSI sessions collected. Sending to InfluxDB information about ' + str(iscsi_session_number) +
                     ' sessions from one or more clients. Time taken: ' + str(time_taken) + ' seconds.')
        await send_to_influx(iscsi_sessions)
    else:
        logging.info(
            'iSCSI sessions collected, but it appears there are no iSCSI connections. Sending empty payload to InfluxDB.')
        await send_to_influx("# iscsiSessions,cluster=" + CLUSTER_NAME + "\n")
        time_taken = (round(time.time(), 3) - time_start)
        await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return


async def cluster_performance(session):
    """
    Use GetClusterStats to extract cluster stats and return for sending to InfluxDB.
    """
    function_name = 'cluster_performance'
    time_start = round(time.time(), 3)
    api_payload = "{ \"method\": \"GetClusterStats\" }"
    async with session.post(SF_POST_URL, data=api_payload) as response:
        r = await response.json()
    result = r['result']['clusterStats']
    metrics = [("actualIOPS", "actual_iops"), ("averageIOPSize", "average_iops"),
               ("clientQueueDepth", "client_queue_depth"), ("clusterUtilization", "cluster_utilization"), (
                   "latencyUSec", "latency_usec"), ("normalizedIOPS", "normalized_iops"),
               ("readBytesLastSample", "read_bytes_last_sample"), ("readLatencyUSec",
                                                                   "read_latency_usec"), ("readOpsLastSample", "read_ops_last_sample"),
               ("writeLatencyUSec", "write_latency_usec"), ("writeBytesLastSample", "write_bytes_last_sample"), ("writeOpsLastSample", "write_ops_last_sample")]
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
    time_taken = (round(time.time(), 3) - time_start)
    logging.info('Cluster performance collected in ' +
                 str(time_taken) + ' seconds.')
    if args.loglevel == 'DEBUG':
        logging.debug("Cluster performance payload: " +
                      str(cluster_performance))
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    await send_to_influx(cluster_performance)
    return


async def cluster_capacity(session):
    """
    Get GetClusterCapacity results, send subset of response to InfluxDB.
    """
    function_name = 'cluster_capacity'
    time_start = round(time.time(), 3)
    api_payload = "{ \"method\": \"GetClusterCapacity\" }"
    async with session.post(SF_POST_URL, data=api_payload) as response:
        r = await response.json()
        result = r['result']['clusterCapacity']
        cluster_capacity = ""
        # NOTE: CLUSTER_NAME is a tag, everything else is field data
        # NOTE: thinFactor and storageEfficiency here are SFC-derived metrics
        # and NOT part of SolidFire's GetClusterCapacity API response
        fields = [('activeBlockSpace', 'active_block_space'), ('activeSessions', 'active_sessions'), ('averageIOPS', 'average_iops'), ('clusterRecentIOSize', 'cluster_recent_io_size'), ('compressionFactor', 'compressioN_factor'),
                  ('currentIOPS', 'current_iops'), ('dedupeFactor', 'dedupe_factor'), ('storageEfficiency', 'storage_efficiency'), ('maxIOPS',
                                                                                                                                    'max_iops'), ('maxOverProvisionableSpace', 'max_overprovisionable_space'), ('maxProvisionedSpace', 'max_provisioned_space'),
                  ('maxUsedMetadataSpace', 'max_used_metadata_space'), ('maxUsedSpace', 'max_used_space'), ('nonZeroBlocks',
                                                                                                            'non_zero_blocks'), ('peakActiveSessions', 'peak_active_sessions'), ('peakIOPS', 'peak_iops'),
                  ('provisionedSpace', 'provisioned_space'), ('snapshotNonZeroBlocks', 'snapshot_non_zero_blocks'), (
                      'thinFactor', 'thin_factor'), ('totalOps', 'total_ops'), ('uniqueBlocks', 'unique_blocks'),
                  ('uniqueBlocksUsedSpace', 'unique_block_space'), ('usedMetadataSpace', 'used_block_space'), ('usedMetadataSpaceInSnapshots', 'used_metadata_space_in_snapshots'), ('usedSpace', 'used_space'), ('zeroBlocks', 'zero_blocks')]
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
            # not compressed
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
    time_taken = (round(time.time(), 3) - time_start)
    logging.info('Cluster capacity collected in ' +
                 str(time_taken) + ' seconds.')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return


async def cluster_version(session):
    """
    Use GetClusterVersionInfo to get cluster version details.
    """
    function_name = 'cluster_version'
    time_start = round(time.time(), 3)
    api_payload = "{ \"method\": \"GetClusterVersionInfo\" }"
    async with session.post(SF_URL + SF_JSON_PATH, data=api_payload) as response:
        r = await response.json(content_type=None)
        result = r['result']
        api_version = str(result['clusterAPIVersion'])
        version = str(result['clusterVersion'])
        payload = ("cluster_version,name=" + CLUSTER_NAME + ",version=" +
                   str(version) + " " + "api_version=" + str(api_version) + "\n")
    await send_to_influx(payload)
    time_taken = (round(time.time(), 3) - time_start)
    if args.loglevel == 'DEBUG':
        logging.debug("Cluster version payload: " + str(payload))
        logging.debug('Cluster version info collected in ' +
                      str(time_taken) + ' seconds.')
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return


async def drive_stats(session):
    """
    Use ListDriveStats and send selected parts of response to InfluxDB.
    """
    function_name = 'drive_stats'
    time_start = round(time.time(), 3)
    api_payload = "{ \"method\": \"ListDriveStats\" }"
    async with session.post(SF_POST_URL, data=api_payload) as response:
        r = await response.json()
        result = r['result']['driveStats']
        payload = "# DriveStats\n"
        for drive in result:
            drive_id = str(drive['driveID'])
            pop_list = ['driveID', 'failedDieCount', 'lifetimeReadBytes', 'lifetimeWriteBytes', 'procTimestamp', 'readBytes', 'readMsec', 'readOps', 'readSectors', 'reads', 'readsCombined', 'reallocatedSectors',
                        'reserveCapacityPercent', 'sectorSize', 'timestamp', 'totalCapacity', 'uncorrectableErrors', 'usedCapacity', 'usedMemory', 'writeBytes', 'writeMsec', 'writeOps', 'writeSectors', 'writes', 'writesCombined']
            for key in pop_list:
                drive.pop(key)
            metric_details = ''
            record = len(drive)
            n = 0
            for key in drive:
                val = drive[key]
                if isinstance(val, int):
                    str_val = str(val) + "i"
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
            logging.debug('Drive stats collected in ' +
                          str(time_taken) + ' seconds.')
        await send_to_influx(payload)
    time_taken = (round(time.time(), 3) - time_start)
    await _send_function_stat(CLUSTER_NAME, function_name, time_taken)
    return


async def send_to_influx(payload):
    """
    Send received payload to InfluxDB.
    """
    measurement = payload.split(",")[0]    
    logging.debug('send_to_influx() received data for ' + measurement + ': ' +    str(payload.count('\n')) + ' lines.')
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(enable_cleanup_closed=True)) as session:
        urlPostEndpoint = 'http://' + INFLUX_HOST + ':' + \
            INFLUX_PORT + '/write?db=' + INFLUX_DB + "&precision=s"
        headers = {'Content-Type': 'application/octet-stream'}
        async with session.post(url=urlPostEndpoint, data=payload, headers=headers) as db_session:
            resp = db_session.status
        await session.close()
    if resp != 204:
        logging.error('Failed to send metrics to InfluxDB. Measurement: ' +
                      measurement + ', response code: ' + str(resp))
        return False
    else:
        logging.debug('send_to_influx() for ' +
                      measurement + ': response code: 204')
        return True


async def _split_list(long_list: list) -> list:
    """
    Splits long list into a list of shorter lists.
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
        logging.debug('Lists created: ' + str(len(shorter_lists)) + ' . List printout:\n' + str(shorter_lists) + '.')
        return shorter_lists


async def _send_function_stat(cluster_name, function, time_taken):
    """
    Send function execution metrics to InfluxDB.
    """
    await send_to_influx("sfc_metrics,cluster=" + cluster_name + ",function=" + function + " " + "time_taken=" + str(time_taken) + "\n")
    return


async def hi_freq_tasks():
    """
    Run high-frequency (1-5 minutes) tasks for time-sensitive metrics.

    May include some non-time-sensitive metrics if they have essential inputs for time-sensitive metrics.
    """
    time_start = round(time.time(), 3)
    global ITERATION
    ITERATION += 1
    logging.info("Iteration: " + str(ITERATION) + " of high-frequency tasks.")
    session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(
        # enable_cleanup_closed=True, timeout_ceil_threshold=20), headers=headers)
        enable_cleanup_closed=True), headers=headers)
    task_list = [cluster_faults, cluster_performance,
                 node_performance, volume_performance, sync_jobs]
    logging.info('High-frequency tasks: ' + str(len(task_list)))
    bg_tasks = set()
    for t in task_list:
        task = asyncio.create_task(t(session))
        bg_tasks.add(task)
        task.add_done_callback(bg_tasks.discard)
    await asyncio.gather(*bg_tasks)
    await session.close()
    time_end = round(time.time(), 3)
    time_taken = time_end - time_start
    logging.info('Completed combined high-frequency collection. Sending to InfluxDB next. Time taken: ' +
                 str(time_taken) + ' seconds.')
    return


async def med_freq_tasks():
    """
    Run medium-frequency (5-30 min) tasks for lower value operation data.
    """
    time_start = round(time.time(), 3)
    session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(
        enable_cleanup_closed=True, timeout_ceil_threshold=15), headers=headers)
    task_list = [accounts, cluster_capacity, iscsi_sessions, volumes]
    logging.info('Medium-frequency tasks: ' + str(len(task_list)))
    bg_tasks = set()
    for t in task_list:
        task = asyncio.create_task(t(session))
        bg_tasks.add(task)
        task.add_done_callback(bg_tasks.discard)
    await asyncio.gather(*bg_tasks)
    await session.close()
    time_end = round(time.time(), 3)
    time_taken = time_end - time_start
    logging.info('Completed medium-frequency collection and closed aiohttp session. Time taken: ' +
                 str(time_taken) + ' seconds.')
    return


async def lo_freq_tasks():
    """
    Run low-frequency (0.5-3 hours) tasks for non-time-sensitive metrics and events.
    """
    time_start = round(time.time(), 3)
    session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(
        enable_cleanup_closed=True, timeout_ceil_threshold=30), headers=headers)
    task_list = [account_efficiency, cluster_version,
                 drive_stats, volume_efficiency]
    logging.info('Low-frequency tasks: ' + str(len(task_list)))
    bg_tasks = set()
    for t in task_list:
        task = asyncio.create_task(t(session))
        bg_tasks.add(task)
        task.add_done_callback(bg_tasks.discard)
    await asyncio.gather(*bg_tasks)
    await session.close()
    time_end = round(time.time(), 3)
    time_taken = time_end - time_start
    logging.info('Completed low-frequency collection and closed aiohttp session. Time taken: ' +
                 str(time_taken) + ' seconds.')
    return


async def experimental():
    """
    Runs one or more medium-frequency and experimental collector tasks.
    """
    time_start = round(time.time(), 3)
    session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(
        enable_cleanup_closed=True, timeout_ceil_threshold=20), headers=headers)
    task_list = [volume_qos_histograms]
    logging.info('Experimental tasks: ' + str(len(task_list)))
    bg_tasks = set()
    for t in task_list:
        task = asyncio.create_task(t(session))
        bg_tasks.add(task)
        task.add_done_callback(bg_tasks.discard)
    await asyncio.gather(*bg_tasks)
    await session.close()
    time_end = round(time.time(), 3)
    time_taken = time_end - time_start
    logging.info('Completed combined experimental collection. Sending to InfluxDB next. Time taken: ' +
                 str(time_taken) + ' seconds.')
    return


async def create_database(INFLUX_DB):
    """
    Create InfluxDB database if it does not exist.
    """
    urlRequest = 'http://' + INFLUX_HOST + ':' + \
        INFLUX_PORT + '/query?q=SHOW DATABASES'
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(force_close=True, enable_cleanup_closed=True)) as session:
        async with session.post(url=urlRequest) as r:
            response = await r.json()
    db_list = response['results'][0]['series'][0]['values']
    for item in db_list:
        if 'sfc' in item:
            return
        else:
            query = 'CREATE DATABASE ' + INFLUX_DB + \
                ' WITH DURATION 31d REPLICATION 1 NAME thirty_one_days'
            urlRequest = 'http://' + INFLUX_HOST + ':' + \
                INFLUX_PORT + '/query?q=' + query + INFLUX_DB
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(force_close=True, enable_cleanup_closed=True)) as session:
                async with session.post(url=urlRequest) as r:
                    response = await r.json()
    logging.info('Exiting InfluxDB create database function.')
    return


async def get_cluster_name():
    """
    Get cluster name from SolidFire cluster.
    """
    time_start = round(time.time(), 3)
    url = SF_URL + SF_JSON_PATH + '?method=GetClusterInfo'
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=True, force_close=True, enable_cleanup_closed=True), headers=headers) as session:
        async with session.get(url, allow_redirects=True) as resp:
            result = await resp.json()
    cluster_name = result['result']['clusterInfo']['name']
    time_end = round(time.time(), 3)
    time_taken = time_end - time_start    
    logging.info('Obtained SolidFire cluster name for tagging of SolidFire metrics: ' + str(cluster_name) + '. Time taken: ' + str(time_taken) + ' seconds.')
    return cluster_name


# =============== main ========================================================


async def main():
    await create_database(INFLUX_DB)
    # NOTE: global variable for iteration count in high-frequency tasks    
    global ITERATION
    ITERATION = 0
    global CHUNK_SIZE
    global CLUSTER_NAME
    CLUSTER_NAME = await get_cluster_name()
    scheduler = AsyncIOScheduler(misfire_grace_time=10)
    scheduler.add_job(hi_freq_tasks, 'interval', seconds=INT_HI_FREQ, max_instances=1)
    scheduler.add_job(med_freq_tasks, 'interval', seconds=INT_MED_FREQ)
    scheduler.add_job(lo_freq_tasks, 'interval', seconds=INT_LO_FREQ)
    if args.experimental == True:
        logging.warning(
            'Experimental collectors enabled - adding experimental tasks.')
        scheduler.add_job(experimental, 'interval',
                          seconds=INT_EXPERIMENTAL_FREQ)
    else:
        logging.info(
            'Experimental collectors disabled not scheduling experimental tasks.')
    logging.warning('Starting scheduler.')
    scheduler.start()
    while True:
        await asyncio.sleep(100)


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
        help='password for admin account on SolidFire cluster. Default: SF_PASSWORD.')
    parser.add_argument('-ih', '--influxdb-host', nargs='?', const=1, type=str, default=INFLUX_HOST,
                        required=False, help='host IP or name of InfluxDB. Default: ' + INFLUX_HOST)
    parser.add_argument('-ip', '--influxdb-port', nargs='?', const=1, type=int,
                        default=INFLUX_PORT, required=False, help='port of InfluxDB. Default: ' + INFLUX_PORT)
    parser.add_argument('-id', '--influxdb-name', nargs='?', const=1, type=str, default=INFLUX_DB, required=False,
                        help='name of InfluxDB database to use. SFC creates it if it does not exist. Default: ' + INFLUX_DB)
    parser.add_argument('-fh', '--frequency-high', nargs='?', const=1, type=str, default=INT_HI_FREQ, required=False, metavar='HI',
                        choices=['60', '120', '180', '300'], help='high-frequency collection interval in seconds. Default: ' + str(INT_HI_FREQ))
    parser.add_argument('-fm', '--frequency-med', nargs='?', const=1, type=str, default=INT_MED_FREQ, required=False, metavar='MED',
                        choices=["300", "600", "900"], help='medium-frequency collection interval in seconds. Default: ' + str(INT_MED_FREQ))
    parser.add_argument('-fl', '--frequency-low', nargs='?', const=1, type=str, default=INT_LO_FREQ, required=False, metavar='LO',
                        choices=["1800", "3600", "7200", "10800"], help='low-frequency collection interval in seconds. Default: ' + str(INT_LO_FREQ))
    parser.add_argument('-ex', '--experimental', action='store_true', required=False,
                        help='use this switch to enable collection of experimental metrics such as volume QoS histograms (interval: 600s, fixed). Default: (disabled, with switch absent)')
    parser.add_argument('-ll', '--loglevel', nargs='?', const=1, type=str, default='INFO', required=False, choices=(
        'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'), help='log level for console output. Default: INFO')
    parser.add_argument('-lf', '--logfile', nargs='?', const=1, type=str, default=None,
                        required=False, help='log file name. SFC logs only to console by default. Default: None')
    args = parser.parse_args()
    
    FORMAT = '%(asctime)-15s - %(levelname)s - %(funcName)s - %(message)s'
    if args.logfile:
        logging.info('Logging to file: ' + args.logfile)
        logging.basicConfig(filename=args.logfile, level=args.loglevel,
                            format=FORMAT, datefmt='%Y-%m-%dT%H:%M:%SZ')
        logging.handlers.RotatingFileHandler(
            filename=args.logfile, mode='a', maxBytes=10000000, backupCount=1, encoding=None, delay=True)
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

    if args.experimental == True:
        logging.warning('Experimental collectors enabled.')
    else:
        logging.info('Experimental collectors disabled (recommended default)')

    # The below works for SolidFire 12.5, 12.7 or higher v12
    SF_JSON_PATH = '/json-rpc/12.5/'
    SF_URL = 'https://' + args.username + ":" + args.password + '@' + SF_MVIP
    SF_POST_URL = SF_URL + SF_JSON_PATH

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        print("Exception:", e)
        pass
