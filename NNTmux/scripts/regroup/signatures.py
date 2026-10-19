#!/usr/bin/env python3
"""Weekly: which posting signatures carry the most volume, and which does nothing handle yet?

Samples the newest headers in every active group straight from Usenet (including the articles NNTmux drops),
reduces poster and message id to a shape (7044df2112 <7d15379@0c41e.com> -> h <h@h.com>), and ranks the shapes by
GiB/hour. Each is marked: claimed by a regroup technique, handled by NNTmux (part counter + real file name),
part counter but random names, or no part counter (NNTmux drops these at ingest).
Writes signatures_latest.txt and appends the top rows to signatures_history.tsv.
"""
import collections
import datetime as dt
import email.utils
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, nntp, sql  # noqa: E402
from techniques import CATALOG_ONLY, TECHNIQUES  # noqa: E402

SAMPLE = int(os.environ.get('SAMPLE', 100000))   # newest articles per group
TOP = 30

_TOKEN = re.compile(r'[A-Za-z0-9]+')
_COUNTER = re.compile(r'\(\d+/\d+\)')
_FILENAME = re.compile(r'\.(rar|r\d\d|par2|7z|zip|\d{3}|mkv|mp4|avi|nfo|nzb|sfv|epub|pdf|flac|mp3|iso|bin|zst)\b', re.I)


def _tok(m):
    t = m.group(0)
    if len(t) >= 5 and re.fullmatch(r'[0-9a-f]+', t) and re.search(r'\d', t):
        return 'h'
    if len(t) >= 5 and re.fullmatch(r'[0-9A-F]+', t) and re.search(r'\d', t):
        return 'H'
    if t.isdigit():
        return '9'
    if len(t) >= 12 or (len(t) >= 8 and re.search(r'\d', t) and re.search(r'[A-Za-z]', t)):
        return 'r'
    return t


def shape(s):
    return _TOKEN.sub(_tok, s.strip())[:60]


def status(subject, from_, msgid):
    for t in TECHNIQUES + CATALOG_ONLY:
        if t.claims(from_, subject, msgid):
            return 'claimed: ' + t.name
    if _COUNTER.search(subject):
        return 'NNTmux handles' if _FILENAME.search(subject) else 'part counter, random names'
    return 'no part counter (dropped)'


def main():
    groups = [g for g in sql('select name from usenet_groups where active=1').split() if g]
    sigs = collections.defaultdict(lambda: {'n': 0, 'bytes': 0, 'groups': set(), 'status': collections.Counter(), 'ex': None})
    hours, total = 0.0, 0
    s = nntp()
    for g in groups:
        try:
            _, _, first, last, _ = s.group(g)
            _, ov = s.over((max(first, last - SAMPLE), last))
        except Exception:  # noqa: BLE001 - skip a group the server won't list
            continue
        ts = []
        for _, h in ov:
            try:
                ts.append(email.utils.parsedate_to_datetime(h['date']).timestamp())
            except Exception:  # noqa: BLE001
                continue
            frm, subj, mid, b = h.get('from', ''), h.get('subject', ''), h.get('message-id', ''), int(h.get(':bytes') or 0)
            k = (shape(frm), shape(mid))
            d = sigs[k]
            d['n'] += 1
            d['bytes'] += b
            d['groups'].add(g)
            d['status'][status(subj, frm, mid)] += 1
            d['ex'] = d['ex'] or (frm[:50], subj[:70])
            total += b
        if len(ts) > 1:
            hours += (max(ts) - min(ts)) / 3600
    s.quit()
    hours = hours / max(len(groups), 1) or 1   # average span the samples cover
    rows = sorted(sigs.items(), key=lambda kv: -kv[1]['bytes'])
    now = dt.datetime.now()
    lines = [f'Posting signatures by volume, {now:%Y-%m-%d %H:%M}, newest {SAMPLE:,} articles in {len(groups)} active groups '
             f'(about {hours:.1f} h per group)', '',
             f'{"GiB/h":>7} {"share":>6}  {"status":32} {"groups":>6}  signature (poster | message id)   example subject']
    for (fs, ms), d in rows[:TOP]:
        st = d['status'].most_common(1)[0][0]
        lines.append(f'{d["bytes"] / 2**30 / hours:7.1f} {100 * d["bytes"] / total:5.1f}%  {st:32} {len(d["groups"]):6}  '
                     f'{fs} | {ms}   {d["ex"][1]}')
    unclaimed = [(k, d) for k, d in rows if d['status'].most_common(1)[0][0] in ('no part counter (dropped)', 'part counter, random names')]
    lines += ['', f'Unclaimed obfuscated volume: {sum(d["bytes"] for _, d in unclaimed) / 2**30 / hours:.1f} GiB/h '
                  f'({100 * sum(d["bytes"] for _, d in unclaimed) / total:.1f}% of everything sampled)']
    open(BASE + 'signatures_latest.txt', 'w').write('\n'.join(lines) + '\n')
    hist = BASE + 'signatures_history.tsv'
    new = not os.path.exists(hist)
    with open(hist, 'a') as f:
        if new:
            f.write('date\tposter_shape\tmsgid_shape\tstatus\tgib_per_hour\tshare_pct\n')
        for (fs, ms), d in rows[:TOP]:
            f.write(f'{now:%Y-%m-%d}\t{fs}\t{ms}\t{d["status"].most_common(1)[0][0]}\t'
                    f'{d["bytes"] / 2**30 / hours:.1f}\t{100 * d["bytes"] / total:.1f}\n')
    print('\n'.join(lines))


main()
