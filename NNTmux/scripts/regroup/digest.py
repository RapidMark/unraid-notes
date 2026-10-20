#!/usr/bin/env python3
"""Daily digest of the indexing setup: what the rebuild jobs did, how NNTmux is keeping up, and anything stuck.

Appends to digest.log and writes digest_latest.txt (both in this folder). Lines starting with "!!" need attention.
"""
import collections
import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, sql  # noqa: E402

now = dt.datetime.now()
since = now - dt.timedelta(hours=24)
out, alerts = [], []


def section(title):
    out.append('')
    out.append(title)


def alert(msg):
    alerts.append(msg)
    out.append('!! ' + msg)


# --- rebuild jobs (regroup.log, local time) --------------------------------------------------------------------
section('Rebuild jobs, last 24 h')
counts, imported = collections.Counter(), []
for line in open(BASE + 'regroup.log', errors='ignore'):
    m = re.match(r'\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] (.*)', line)
    if not m or dt.datetime.fromisoformat(m.group(1)) < since:
        continue
    msg = m.group(2)
    if msg.startswith('run nyuu-random-name:'):
        counts['regroup runs'] += 1
        for k, v in re.findall(r'(\w+)=(\d+)', msg):
            if k in ('passworded_headers', 'passworded_files', 'named', 'incomplete'):
                counts['regroup ' + k] += int(v)
    elif msg.startswith('catalog:'):
        counts['catalog runs'] += 1
        for k, v in re.findall(r'(\w+)=(\d+)', msg):
            if k in ('named', 'no_par2_name', 'predb_added'):
                counts['catalog ' + k] += int(v)
    elif msg.startswith('index: ') and '(' in msg:
        imported.append(msg[7:])
    elif msg.startswith('index: could not rebuild'):
        counts['index could not rebuild'] += 1
    elif msg.startswith('index run:'):
        counts['index runs'] += 1
for k, v in sorted(counts.items()):
    out.append(f'  {k}: {v}')
out.append(f'  index imported: {len(imported)}')
out += [f'    {x}' for x in imported[-15:]]
if counts['catalog runs'] < 60:
    alert(f'catalog ran only {counts["catalog runs"]} times (expected ~96)')
if counts['index runs'] < 60:
    alert(f'index ran only {counts["index runs"]} times (expected ~96)')

# --- NNTmux releases by category, last 24 h --------------------------------------------------------------------
section('NNTmux releases, last 24 h, by category')
rows = sql("""select coalesce(p.title, c.title) top, count(*),
                 sum(r.categories_id not in (10,20)), sum(r.predb_id>0), sum(r.passwordstatus=1)
          from releases r join categories c on c.id=r.categories_id left join root_categories p on p.id=c.root_categories_id
          where r.adddate > now() - interval 24 hour group by top order by 2 desc""")
out.append(f'  {"category":12} {"created":>8} {"named":>7} {"predb":>7} {"pw":>6}')
for line in rows.splitlines():
    cat, n, named, pre, pw = line.split('\t')
    out.append(f'  {cat[:12]:12} {n:>8} {named:>7} {pre:>7} {pw:>6}')
src = sql("""select p.source, count(*) from releases r join predb p on p.id=r.predb_id
             where r.adddate > now() - interval 24 hour group by p.source order by 2 desc""")
out.append('  PreDB names used: ' + ', '.join(l.replace('\t', ' ') for l in src.splitlines()))

# --- health checks ---------------------------------------------------------------------------------------------
section('Health')
for line in sql("select source, timestampdiff(minute, max(predate), utc_timestamp()) from predb "
                "where source in ('srrdb','drunkenslug','usenet-par2') group by source").splitlines():
    s, age = line.split('\t')
    out.append(f'  PreDB {s}: newest entry {age} min old')
    if s == 'srrdb' and int(age) > 180:
        alert(f'PreDB IRC feed (srrdb) stale: {age} min - restart the scraper (#1900 not deployed yet)')
    if s == 'drunkenslug' and int(age) > 180:
        alert(f'DrunkenSlug PreDB feed stale: {age} min')
# a quiet group has old posts but nothing to fetch, so alert only when it is also far behind the server
for line in sql("select g.name, timestampdiff(minute, g.last_record_postdate, utc_timestamp()), "
                "coalesce(a.last_record - g.last_record, 0) from usenet_groups g left join short_groups a on a.name=g.name "
                "where g.active=1 order by 2 desc").splitlines():
    g, lag, gap = line.split('\t')
    if lag != 'NULL' and int(lag) > 60 and int(gap) > 50000:
        alert(f'header lag {g}: {lag} min, {int(gap):,} articles behind')
out.append('  header lag (worst 3): ' + ', '.join(
    l.replace('\t', ' ') + ' min' for l in sql("select name, timestampdiff(minute, last_record_postdate, utc_timestamp()) "
                                               "from usenet_groups where active=1 order by 2 desc limit 3").splitlines()))
stuck = sql("select count(*), coalesce(round(sum(filesize)/1073741824),0) from collections "
            "where dateadded < now() - interval 2 hour and totalfiles > 1 and subject regexp '\\\\.(mkv|rar|par2)'").split('\t')
out.append(f'  stuck named uploads (>2 h incomplete): {stuck[0]} ({stuck[1].strip()} GiB)')
lock = 0
logf = f'/mnt/user/appdata/nntmux/storage/logs/laravel-{now:%Y-%m-%d}.log'
if os.path.exists(logf):
    lock = sum(1 for l in open(logf, errors='ignore') if 'Lock retries exhausted' in l)
out.append(f'  lock errors today: {lock}')
conns = subprocess.run(['docker', 'exec', 'NNTmux', 'sh', '-c', 'ss -tn state established "( dport = :563 )" | tail -n +2 | wc -l'],
                       capture_output=True, text=True).stdout.strip()
out.append(f'  NNTmux Usenet connections now: {conns}')

# --- Radarr / Sonarr indexers, Hydra ---------------------------------------------------------------------------
section('Indexers')
for app in ('radarr', 'sonarr'):
    c = sqlite3.connect(f'file:/mnt/user/appdata/{app}/{app}.db?mode=ro', uri=True)
    for lvl, till in c.execute('select EscalationLevel, DisabledTill from IndexerStatus'):
        out.append(f'  {app}: escalation {lvl}, disabled till {till}')
        if till and till > dt.datetime.utcnow().isoformat():
            alert(f'{app} has its Hydra indexer disabled until {till} - retest it')
y = open('/mnt/user/appdata/hydra2/nzbhydra.yml').read()
for m in re.finditer(r'\n  name: "([^"]+)"', y):
    block = y[y.rfind('\n- ', 0, m.start()):y.find('\n- ', m.end())]
    st = re.search(r'\n  state: "([^"]+)"', block)
    if st and st.group(1) != 'ENABLED':
        out.append(f'  Hydra {m.group(1)}: {st.group(1)}')
    elif st:
        out.append(f'  Hydra {m.group(1)}: enabled')

head = [f'Digest {now:%Y-%m-%d %H:%M}', f'{len(alerts)} item(s) need attention' if alerts else 'All OK']
text = '\n'.join(head + out) + '\n'
open(BASE + 'digest_latest.txt', 'w').write(text)
with open(BASE + 'digest.log', 'a') as f:
    f.write(text + '\n')
print(text)
