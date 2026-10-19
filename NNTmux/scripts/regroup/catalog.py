#!/usr/bin/env python3
"""Every 15 min: catalogue uploads NNTmux can't see (no part counters), naming them from their PAR2 index.

Reads new raw headers in every active group (resuming where the last run stopped), collects articles of the
catalogue-only techniques per poster, and once an upload has gone quiet: finds its PAR2 index among the small
articles, records name / size / files / group / time in catalog.tsv, keeps its message ids (catalog/<poster>.txt.gz,
for assemble.py), and adds the name to NNTmux's PreDB with source usenet-par2.
"""
import collections
import datetime as dt
import gzip
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, log, nntp, par2_files, release_name, sql, ydecode  # noqa: E402
from techniques import CATALOG_ONLY  # noqa: E402

STATE = BASE + 'catalog_state.json'
TSV = BASE + 'catalog.tsv'
IDS = BASE + 'catalog/'
QUIET_MIN = 10          # an upload is done when no article came for this long
MAX_PER_GROUP = 400000  # cap per group per run
FIRST_RUN_BACK = 50000  # how far back to start in a group seen for the first time
KEEP_DAYS = 7           # message id lists kept this long


def main():
    os.makedirs(IDS, exist_ok=True)
    try:
        st = json.load(open(STATE))
    except (FileNotFoundError, ValueError):
        st = {'groups': {}, 'pending': {}}
    pending = st['pending']   # poster -> {groups, n, bytes, t0, t1, small: [[bytes, mid]], mids: []}
    s = nntp()
    stats = collections.Counter()
    for g in [g for g in sql('select name from usenet_groups where active=1').split() if g]:
        try:
            _, _, first, last, _ = s.group(g)
        except Exception:  # noqa: BLE001
            continue
        start = max(st['groups'].get(g, last - FIRST_RUN_BACK) + 1, first, last - MAX_PER_GROUP)
        if start > last:
            continue
        _, ov = s.over((start, last))
        st['groups'][g] = last
        for _, h in ov:
            frm, subj, mid = h.get('from', ''), h.get('subject', ''), h.get('message-id', '')
            if not any(t.claims(frm, subj, mid) for t in CATALOG_ONLY):
                continue
            t = int(re.search(r'-(\d{13})@', mid).group(1)) / 1000
            b = int(h.get(':bytes') or 0)
            u = pending.setdefault(frm, {'groups': [], 'n': 0, 'bytes': 0, 't0': t, 't1': t, 'small': [], 'mids': []})
            if g not in u['groups']:
                u['groups'].append(g)
            if mid in u['mids']:
                continue   # cross-posted copy seen in another group
            u['n'] += 1
            u['bytes'] += b
            u['t0'], u['t1'] = min(u['t0'], t), max(u['t1'], t)
            u['mids'].append(mid)
            u['small'] = sorted(u['small'] + [[b, mid]])[:12]
            stats['articles'] += 1
    now = time.time()
    rows, titles = [], []
    for poster, u in list(pending.items()):
        if now - u['t1'] < QUIET_MIN * 60:
            continue
        del pending[poster]
        if u['n'] < 5:
            stats['too_small'] += 1
            continue
        names = []
        for _, mid in u['small']:
            try:
                names = par2_files(ydecode(s.body(mid)[1].lines))
            except Exception:  # noqa: BLE001
                continue
            if names:
                break
        name = release_name(names) if names else None
        when = dt.datetime.utcfromtimestamp(u['t0'])
        rows.append('\t'.join([f'{when:%Y-%m-%d %H:%M:%S}', name or '', str(round(u['bytes'] / 2**20)), str(len(names)),
                               str(u['n']), ','.join(u['groups']), poster]))
        with gzip.open(IDS + re.sub(r'[^A-Za-z0-9@._-]', '_', poster) + '.txt.gz', 'wt') as f:
            f.write('\n'.join([','.join(u['groups'])] + u['mids']) + '\n')
        stats['named' if name else 'no_par2_name'] += 1
        if name:
            titles.append(f'{name}\t{when:%Y-%m-%d %H:%M:%S}\t{round(u["bytes"] / 2**20)}MB\t{len(names)}\t{u["groups"][0]}')
    s.quit()
    if rows:
        new = not os.path.exists(TSV)
        with open(TSV, 'a') as f:
            if new:
                f.write('posted_utc\tname\tmb\tfiles\tarticles\tgroups\tposter\n')
            f.write('\n'.join(rows) + '\n')
    if titles:
        with open(BASE + 'catalog_predb.tsv', 'w') as f:
            f.write('\n'.join(titles) + '\n')
        out = subprocess.run(['docker', 'exec', '-u', 'www-data', '-w', '/app', '-e', 'HOME=/config', 'NNTmux', 'php', 'artisan',
                              'tinker', '--execute=require \'/config/regroup/catalog_predb.php\';'], capture_output=True, text=True)
        stats['predb_added'] = int((re.findall(r'added=(\d+)', out.stdout) or ['0'])[-1])
    for f in os.listdir(IDS):   # forget old message id lists
        if now - os.path.getmtime(IDS + f) > KEEP_DAYS * 86400:
            os.remove(IDS + f)
    st['pending'] = pending
    json.dump(st, open(STATE, 'w'))
    log('catalog: ' + ', '.join(f'{k}={v}' for k, v in sorted(stats.items())) + f', pending={len(pending)}')


main()
