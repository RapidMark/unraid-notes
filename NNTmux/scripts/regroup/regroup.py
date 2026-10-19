#!/usr/bin/env python3
"""Every 15 min: rebuild obfuscated uploads NNTmux can't group and import the usable ones as named releases.

For every technique in techniques.py: read its unfinished pieces from NNTmux, rebuild the uploads, and once an upload
has finished posting, read the real names from its PAR2 index (one article). Passworded uploads (encrypted
headers or encrypted files) are skipped; the rest are written as NZBs under that name and imported with nntmux:import-nzbs, where
NNTmux's normal processing (look inside, password check, categories) takes over.
"""
import collections
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, archive_locked, log, nntp, nzb, par2_files, release_name, ydecode  # noqa: E402
from techniques import TECHNIQUES  # noqa: E402

STATE = BASE + 'state.json'
IMPORT = BASE + 'import/'
WINDOW_HOURS = 3      # how far back to read unfinished pieces
SETTLE_MIN = 15       # an upload counts as finished when nothing was posted to it for this long
MIN_COMPLETE = 0.99   # share of articles that must be present (PAR2 repairs the rest)
DRY = os.environ.get('DRY') == '1'   # list what would be imported, change nothing


class Conn:
    """One Usenet connection, opened only when a technique needs an article."""
    def __init__(self):
        self.c = None

    def body(self, mid):
        self.c = self.c or nntp()
        return ydecode(self.c.body('<' + mid + '>')[1].lines)

    def close(self):
        if self.c:
            self.c.quit()


def handle(u, tech, state, stats, conn, now):
    fs = sorted(u['files'], key=lambda x: x['f'])
    key = tech.name + '|' + u['poster'] + '|' + min(mid for fi in fs for mid, _ in fi['parts'].values())
    if fs[0]['f'] != 1:
        return 'started_before_window'
    last = max(fi['end'] for fi in fs)
    if now - last < SETTLE_MIN * 60:
        return 'still_posting'
    if key in state:
        return 'already_done'
    have, want = sum(len(fi['parts']) for fi in fs), sum(fi['tp'] for fi in fs)
    if len(fs) != u['N'] or [fi['f'] for fi in fs] != list(range(1, u['N'] + 1)) or have < want * MIN_COMPLETE:
        if now - last > 3600:
            state[key] = {'t': now, 'result': f'incomplete {len(fs)}/{u["N"]} files, {have}/{want} articles'}
        return 'incomplete'
    try:
        names = par2_files(conn.body(fs[0]['parts'][min(fs[0]['parts'])][0]))
    except Exception as e:  # noqa: BLE001 - one bad article shouldn't stop the run
        log(f'{tech.name}: par2 fetch failed ({u["poster"]}, {len(fs)} files): {str(e)[:80]}')
        return 'par2_error'
    name = release_name(names) if names else None
    if not name or len(names) >= u['N']:
        state[key] = {'t': now, 'result': 'no usable PAR2 names'}
        return 'no_name'
    n_par = u['N'] - len(names)   # PAR2 files come first, then the data files in name order
    try:
        first_data = fs[n_par]
        head = conn.body(first_data['parts'][min(first_data['parts'])][0])[:65536]
    except Exception as e:  # noqa: BLE001
        log(f'{tech.name}: data peek failed for {name}: {str(e)[:80]}')
        return 'data_peek_error'
    locked = archive_locked(head)
    if locked:
        state[key] = {'t': now, 'result': f'passworded ({locked})', 'name': name}
        return f'passworded_{locked}'
    if DRY:
        print(f'{tech.name}: would import {name} ({u["group"]}, {u["N"]} files)')
        return 'named'
    file_names = {f: (name + '.par2' if f == 1 else f'{name}.vol{f - 1:02d}.par2') for f in range(1, n_par + 1)}
    file_names.update({n_par + 1 + i: n for i, (n, _) in enumerate(names)})
    path = IMPORT + re.sub(r'[/\\:*?"<>|]', '_', name)[:200] + '.nzb'
    with open(path, 'w') as f:
        f.write(nzb(u, file_names))
    os.chmod(path, 0o666)
    gib = round(sum(s for fi in fs for _, s in fi['parts'].values()) / 2**30, 2)
    state[key] = {'t': now, 'result': 'named', 'name': name, 'gib': gib}
    log(f'{tech.name}: named {name} ({u["group"]}, {gib} GiB)')
    return 'named'


def main():
    os.makedirs(IMPORT, exist_ok=True)
    os.chmod(IMPORT, 0o777)
    try:
        state = json.load(open(STATE))
    except (FileNotFoundError, ValueError):
        state = {}
    now = time.time()
    state = {k: v for k, v in state.items() if now - v['t'] < 86400}   # forget after a day
    conn, named = Conn(), 0
    for tech in TECHNIQUES:
        stats = collections.Counter()
        for u in tech.group(tech.fetch(WINDOW_HOURS)):
            stats[handle(u, tech, state, stats, conn, now)] += 1
        named += stats['named']
        line = f'{tech.name}: ' + ', '.join(f'{k}={v}' for k, v in sorted(stats.items()))
        print(line) if DRY else log('run ' + line)
    conn.close()
    if DRY:
        return
    if named:
        out = subprocess.run(['docker', 'exec', '-u', 'www-data', '-w', '/app', '-e', 'HOME=/config', 'NNTmux', 'php', 'artisan',
                              'nntmux:import-nzbs', '--folder=/config/regroup/import', '--filename', '--delete', '--delete-failed'],
                             capture_output=True, text=True)
        tail = [line for line in (out.stdout + out.stderr).splitlines() if line.strip()][-3:]
        log('import: ' + ' | '.join(tail))
    json.dump(state, open(STATE, 'w'))


main()
