"""Obfuscation techniques the regroup job knows how to undo.

Each technique has three parts:
  claims(from_, subject, msgid) -> bool   recognise one raw article header (also used by the signature report)
  fetch(window_hours) -> articles          read its unfinished pieces from NNTmux
  group(articles) -> uploads               rebuild files and uploads

An upload is {'group', 'poster', 'N', 'files': [{'f', 'tp', 'start', 'end', 'parts': {part: (msgid, bytes)}}]};
file 1 must be the PAR2 index. The engine (regroup.py) then names, checks and imports it. To add a technique,
add an entry to TECHNIQUES.
"""
import collections
import re
from dataclasses import dataclass
from typing import Callable

from common import sql


@dataclass
class Technique:
    name: str
    description: str
    claims: Callable
    fetch: Callable
    group: Callable


# --- Nyuu, random name per article: [27/62] "X8Iqg1gnf6CUFzEHc7qbsut1tEyEdj4e" yEnc (127/942) -------------------

_NYUU_SUBJECT = re.compile(r'^\[\d+/\d+\] "[A-Za-z0-9]{20,}" yEnc( \(\d+/\d+\))?( \d+)?$')
_NYUU_MS = re.compile(r'-(\d{13})@')


def _nyuu_claims(from_, subject, msgid):
    return bool(_NYUU_SUBJECT.match(subject))


def _nyuu_fetch(window_hours):
    q = f"""select g.name, c.fromname, c.totalfiles, b.filenumber, b.totalparts, p.partnumber, p.size,
               unix_timestamp(c.date), p.messageid
        from collections c join usenet_groups g on g.id=c.groups_id join binaries b on b.collections_id=c.id
        join parts p on p.binaries_id=b.id
        where c.date > utc_timestamp() - interval {window_hours} hour
          and c.subject regexp '^\\\\[[0-9]+/[0-9]+\\\\] "[A-Za-z0-9]{{20,}}" yEnc$'"""
    arts = []
    for line in sql(q).splitlines():
        p = line.split('\t')
        if len(p) != 9:
            continue
        group, poster, N, f, tp, pn, size, ts, mid = p
        m = _NYUU_MS.search(mid)   # Nyuu message ids carry the post time in ms, finer than the Date header
        arts.append((group, poster, int(N), int(f), int(tp), int(pn), int(size),
                     int(m.group(1)) / 1000 if m else float(ts), mid.strip('<>')))
    arts.sort(key=lambda a: a[7])
    return arts


def _nyuu_group(arts):
    """Articles -> files by (poster, N, f, part total); files -> uploads by chaining f-1 -> f as it is posted."""
    files, open_by_key = [], collections.defaultdict(list)
    for group, poster, N, f, tp, pn, size, t, mid in arts:
        key = (group, poster, N, f, tp)
        inst = next((i for i in reversed(open_by_key[key]) if pn not in i['parts'] and t - i['end'] < 300), None)
        if inst is None:
            inst = {'group': group, 'poster': poster, 'N': N, 'f': f, 'tp': tp, 'parts': {}, 'start': t, 'end': t}
            open_by_key[key].append(inst)
            files.append(inst)
        inst['parts'][pn] = (mid, size)
        inst['end'] = max(inst['end'], t)
    uploads, by_poster = [], collections.defaultdict(list)
    for fi in files:
        by_poster[(fi['group'], fi['poster'], fi['N'])].append(fi)
    for (group, poster, N), fl in by_poster.items():
        fl.sort(key=lambda x: x['start'])
        open_ups = []
        for fi in fl:
            cands = [u for u in open_ups
                     if u['files'][-1]['f'] == fi['f'] - 1 and abs(fi['start'] - u['files'][-1]['end']) < 120]
            if fi['f'] == 1 or not cands:
                u = {'group': group, 'poster': poster, 'N': N, 'files': [fi]}
                open_ups.append(u)
                uploads.append(u)
                continue
            min(cands, key=lambda u: (abs(fi['start'] - u['files'][-1]['end']), u['files'][-1]['tp'] != fi['tp']))['files'].append(fi)
    return uploads


# --- Nyuu, one random poster per upload, random subjects without part counters, articles shuffled ---------------
# NNTmux drops these at ingest (no part counter), so they are read from raw headers by catalog.py. They can be found
# and named cheaply (the poster isolates the upload, the PAR2 index names it), but building an NZB needs every
# article downloaded (assemble.py). Catalog-only: no fetch/group here.

_SHUFFLED_SUBJECT = re.compile(r'^[A-Za-z0-9]{16,40}$')
_SHUFFLED_POSTER = re.compile(r'^[a-z0-9]{10}@[a-z0-9]{5}\.[a-z0-9]{3}$')   # one per upload, e.g. wpqbi363zb@amtxh.3py
_SHUFFLED_MID = re.compile(r'^<[A-Za-z]+-\d{13}@nyuu>$')


def shuffled_claims(from_, subject, msgid):
    return bool(_SHUFFLED_SUBJECT.match(subject) and _SHUFFLED_POSTER.match(from_) and _SHUFFLED_MID.match(msgid))


CATALOG_ONLY = [
    Technique('nyuu-shuffled', 'Nyuu, random poster per upload, no part counters, shuffled (catalog only)',
              shuffled_claims, None, None),
]

TECHNIQUES = [
    Technique('nyuu-random-name', 'Nyuu, file f of N kept, random name per article',
              _nyuu_claims, _nyuu_fetch, _nyuu_group),
]
