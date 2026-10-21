#!/usr/bin/env python3
"""NZBGet queue extension: re-sort the queue each time an NZB is added (NZBGet's GroupSort, default newest first)."""
import base64
import json
import os
import sys
import urllib.request

POSTPROCESS_SUCCESS = 93


def rpc(method, params):
    host = os.environ.get('NZBOP_CONTROLIP', '127.0.0.1')
    host = '127.0.0.1' if host in ('0.0.0.0', '') else host
    url = f'http://{host}:{os.environ.get("NZBOP_CONTROLPORT", "6789")}/jsonrpc'
    auth = base64.b64encode(f'{os.environ.get("NZBOP_CONTROLUSERNAME", "")}:{os.environ.get("NZBOP_CONTROLPASSWORD", "")}'.encode()).decode()
    req = urllib.request.Request(url, json.dumps({'method': method, 'params': params}).encode(),
                                 {'Authorization': 'Basic ' + auth, 'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())['result']


if os.environ.get('NZBNA_EVENT') != 'NZB_ADDED':
    sys.exit(POSTPROCESS_SUCCESS)
order = os.environ.get('NZBPO_SORTORDER', 'age+')
ids = [g['NZBID'] for g in rpc('listgroups', [0])]
if len(ids) > 1:
    rpc('editqueue', ['GroupSort', order, ids])
    print(f'[INFO] QueueSort: sorted {len(ids)} items by {order}')
sys.exit(POSTPROCESS_SUCCESS)
