#!/usr/bin/env python3
"""Every 15 min: turn catalogued shuffled uploads into normal NNTmux releases.

For each upload the catalogue named (catalog.tsv) that NNTmux doesn't have yet: download its articles once, work out
which article belongs where from the PAR2 index (assemble.rebuild), skip it if the archive is passworded, and write an
NZB with the real file names. NZBs are imported with nntmux:import-nzbs, so Radarr/Sonarr find them through Hydra and
NZBGet downloads them like any other release. The article data itself is thrown away.
"""
import calendar
import csv
import gzip
import html
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assemble  # noqa: E402
from common import BASE, archive_locked, log, sql  # noqa: E402

STATE = BASE + 'index_state.json'
IMPORT = BASE + 'import/'
PER_RUN = 4            # uploads per run (about 2.5 GB each) keeps traffic steady
MAX_AGE_H = 48         # only index uploads this recent (message id lists are kept 7 days)


def _q(s):
    return s.replace("'", "''")


def write_nzb(path, name, groups, poster, built, extra):
    files = []
    for fname, _, arts in built:
        files.append((fname, arts))
    vol = 0
    for kind, arts in extra:
        if kind == 'par2':
            files.append((name + '.par2', arts))
        elif kind == 'sfv':
            files.append((name + '.sfv', arts))
        elif kind == 'nfo':
            files.append((name + '.nfo', arts))
        elif kind == 'vol':
            vol += 1
            files.append((f'{name}.vol{vol:02d}.par2', arts))
    files.sort(key=lambda f: (not f[0].endswith('.par2'), f[0]))
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<!DOCTYPE nzb PUBLIC "-//newzBin//DTD NZB 1.1//EN" "http://www.newzbin.com/DTD/nzb/nzb-1.1.dtd">',
           '<nzb xmlns="http://www.newzbin.com/DTD/2003/nzb">']
    now = int(time.time())
    for n, (fname, arts) in enumerate(files, 1):
        subj = html.escape(f'[{n}/{len(files)}] - "{fname}" yEnc (1/{len(arts)})', quote=True)
        out.append(f'<file poster="{html.escape(poster, quote=True)}" date="{now}" subject="{subj}"><groups>')
        out += [f'<group>{g}</group>' for g in groups]
        out.append('</groups><segments>')
        out += [f'<segment bytes="{a[6]}" number="{i}">{html.escape(a[5])}</segment>' for i, a in enumerate(arts, 1)]
        out.append('</segments></file>')
    out.append('</nzb>')
    with open(path, 'w') as f:
        f.write('\n'.join(out))
    os.chmod(path, 0o666)


def main():
    os.makedirs(IMPORT, exist_ok=True)
    try:
        state = json.load(open(STATE))
    except (FileNotFoundError, ValueError):
        state = {}
    try:
        rows = list(csv.DictReader(open(BASE + 'catalog.tsv'), delimiter='\t'))
    except FileNotFoundError:
        return
    now = time.time()
    todo = []
    for r in rows:
        if not r['name'] or r['poster'] in state:
            continue
        posted = calendar.timegm(time.strptime(r['posted_utc'], '%Y-%m-%d %H:%M:%S'))
        if now - posted > MAX_AGE_H * 3600:
            continue
        todo.append(r)
    imported = 0
    for r in todo[:PER_RUN]:
        name, poster = r['name'], r['poster']
        if sql(f"select count(*) from releases where searchname='{_q(name)}'").strip() != '0':
            state[poster] = {'t': now, 'result': 'already in NNTmux', 'name': name}
            continue
        ids = BASE + 'catalog/' + re.sub(r'[^A-Za-z0-9@._-]', '_', poster) + '.txt.gz'
        if not os.path.exists(ids):
            state[poster] = {'t': now, 'result': 'no message ids', 'name': name}
            continue
        t0 = time.time()
        _, arts = assemble.fetch_all(r['groups'].split(',')[0], poster)
        report, built, index_article, ok = assemble.rebuild(arts)
        good = [b for b in built if b[1]]
        if not built or len(good) != len(built):
            state[poster] = {'t': now, 'result': 'could not rebuild', 'name': name, 'report': report.split('\n')[0]}
            log(f'index: could not rebuild {name}: {report.splitlines()[0]}')
            continue
        first = min(built, key=lambda b: b[0])            # .part01.rar / .rar / .001
        locked = archive_locked(b''.join(a[4] for a in first[2][:2])[:65536])
        if locked:
            state[poster] = {'t': now, 'result': f'passworded ({locked})', 'name': name}
            continue
        path = IMPORT + re.sub(r'[/\\:*?"<>|]', '_', name)[:200] + '.nzb'
        write_nzb(path, name, r['groups'].split(','), poster, built, assemble.extras(built, index_article, ok))
        state[poster] = {'t': now, 'result': 'indexed', 'name': name, 'seconds': round(time.time() - t0)}
        log(f'index: {name} ({r["mb"]} MB, {len(built)} volumes, {round(time.time() - t0)} s)')
        imported += 1
        del arts, built, ok
    if imported:
        out = subprocess.run(['docker', 'exec', '-u', 'www-data', '-w', '/app', '-e', 'HOME=/config', 'NNTmux', 'php', 'artisan',
                              'nntmux:import-nzbs', '--folder=/config/regroup/import', '--filename', '--delete', '--delete-failed'],
                             capture_output=True, text=True)
        tail = [line for line in (out.stdout + out.stderr).splitlines() if line.strip()][-2:]
        log('index import: ' + ' | '.join(tail))
    state = {k: v for k, v in state.items() if now - v['t'] < 7 * 86400}
    json.dump(state, open(STATE, 'w'))
    log(f'index run: {imported} imported, {max(0, len(todo) - PER_RUN)} waiting')


main()
