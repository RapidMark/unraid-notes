#!/usr/bin/env python3
"""Rebuild an upload whose articles are shuffled and all carry the same random name, using only its PAR2 index.

1. Download every article of the upload (identified by poster) and decode it: yEnc gives part, file size and offset.
2. Small files (PAR2, SFV, NFO) are single-article and need no placing.
3. For each data file size, the PAR2 index has, per file: MD5 of the first 16 KB, and a CRC32 per slice. The first
   article of each file is found by the 16 KB MD5; after that each next article is the candidate that makes the
   current slice's CRC32 come out right.
4. Write the files under their real names and check them against the PAR2 MD5s.

usage: assemble.py <group> <poster> <outdir>
"""
import collections
import concurrent.futures
import hashlib
import os
import re
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import nntp  # noqa: E402

YB = re.compile(rb'=ybegin part=(\d+) total=(\d+) line=\d+ size=(\d+)')
YP = re.compile(rb'=ypart begin=(\d+) end=(\d+)')
_TABLE = bytes((c - 42) % 256 for c in range(256))


def ydecode_fast(lines):
    """yEnc body lines -> (part, total, size, begin, data)."""
    part = total = size = begin = None
    body = []
    for raw in lines:
        if raw.startswith(b'=ybegin'):
            m = YB.match(raw)
            part, total, size = int(m.group(1)), int(m.group(2)), int(m.group(3))
        elif raw.startswith(b'=ypart'):
            begin = int(YP.match(raw).group(1)) - 1
        elif raw.startswith(b'=yend'):
            break
        else:
            body.append(raw)
    pieces = b''.join(body).split(b'=')
    out = [pieces[0].translate(_TABLE)]
    for p in pieces[1:]:
        if p:
            out.append(bytes(((p[0] - 106) % 256,)) + p[1:].translate(_TABLE))
    return part, total, size, (begin or 0), b''.join(out)


def par2_index(data):
    """slice size, and per file: name, length, md5, md5_16k, [(md5, crc32) per slice]."""
    files, ifsc, slice_size = {}, {}, None
    i = data.find(b'PAR2\x00PKT')
    while 0 <= i < len(data) - 64:
        length = struct.unpack('<Q', data[i + 8:i + 16])[0]
        if length < 64:
            break
        typ, body = data[i + 48:i + 64], data[i + 64:i + length]
        if typ.startswith(b'PAR 2.0\x00Main'):
            slice_size = struct.unpack('<Q', body[:8])[0]
        elif typ.startswith(b'PAR 2.0\x00FileDesc'):
            fid = body[:16]
            files[fid] = {'md5': body[16:32], 'md5_16k': body[32:48], 'length': struct.unpack('<Q', body[48:56])[0],
                          'name': body[56:].rstrip(b'\x00').decode('utf-8', 'replace')}
        elif typ.startswith(b'PAR 2.0\x00IFSC'):
            ifsc[body[:16]] = [(body[j:j + 16], struct.unpack('<I', body[j + 16:j + 20])[0]) for j in range(16, len(body), 20)]
        i = data.find(b'PAR2\x00PKT', i + length)
    for fid, f in files.items():
        f['slices'] = ifsc.get(fid, [])
    return slice_size, list(files.values())


def fetch_all(group, poster, workers=4):
    ids = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'catalog', re.sub(r'[^A-Za-z0-9@._-]', '_', poster) + '.txt.gz')
    if os.path.exists(ids):   # the catalogue already has the message ids
        import gzip
        mids = gzip.open(ids, 'rt').read().split('\n')[1:]
        mids = [m for m in mids if m]
    else:
        s = nntp()
        _, _, first, last, _ = s.group(group)
        _, ov = s.over((max(first, last - 300000), last))
        s.quit()
        mids = [h['message-id'] for _, h in ov if h.get('from') == poster]
    print(f'{len(mids)} message ids', flush=True)
    done = [0]

    def worker(chunk):
        c, out = nntp(), []
        c.sock.settimeout(60)
        for mid in chunk:
            try:
                lines = c.body(mid)[1].lines
                out.append(ydecode_fast(lines) + (mid.strip('<>'), sum(len(x) + 2 for x in lines)))
            except Exception as e:  # noqa: BLE001
                out.append(('missing', mid, str(e)[:60]))
            done[0] += 1
            if done[0] % 500 == 0:
                print(f'  downloaded {done[0]}/{len(mids)}', flush=True)
        c.quit()
        return out

    chunks = [mids[i::workers] for i in range(workers)]
    arts = []
    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        for res in ex.map(worker, chunks):
            arts.extend(res)
    return mids, arts


# --- CRC32 combine: crc(A+B) from crc(A), crc(B) and len(B); the length operator is cached -------------------

def _gf2_times(mat, vec):
    s, i = 0, 0
    while vec:
        if vec & 1:
            s ^= mat[i]
        vec >>= 1
        i += 1
    return s


def _gf2_square(mat):
    return [_gf2_times(mat, mat[n]) for n in range(32)]


_OPS = {}


def _shift_op(length):
    """Matrix that advances a CRC32 over `length` zero bytes (zlib's crc32_combine, precomputed per length)."""
    op = _OPS.get(length)
    if op is None:
        odd = [0xEDB88320] + [1 << n for n in range(31)]   # operator for one zero bit
        even = _gf2_square(odd)                              # two bits
        odd = _gf2_square(even)                              # four bits
        op = [1 << n for n in range(32)]                     # identity
        n = length
        while n:
            even = _gf2_square(odd)
            if n & 1:
                op = [_gf2_times(even, c) for c in op]
            n >>= 1
            if not n:
                break
            odd = _gf2_square(even)
            if n & 1:
                op = [_gf2_times(odd, c) for c in op]
            n >>= 1
        _OPS[length] = op
    return op


def crc_combine(crc1, crc2, len2):
    return _gf2_times(_shift_op(len2), crc1) ^ crc2 if len2 else crc1


_ZERO_CRC = {}


def _zeros_crc(n):
    if n not in _ZERO_CRC:
        _ZERO_CRC[n] = zlib.crc32(b'\x00' * n)
    return _ZERO_CRC[n]


def rebuild(arts, budget=200000, stop_on_fail=False, max_gaps=5):
    """-> (report, [(file name, md5 ok, [articles in order])], par2 index article, all ok articles).

    budget caps the combinations tried per slice: big uploads (many same-size volumes, slices spanning many
    articles) have more combinations than a CRC32 can tell apart, so they fail instead of searching forever.
    max_gaps: articles an upload may lack in total; files with gaps are placed by elimination (see below).
    """
    ok = [a for a in arts if a[0] != 'missing']
    missing = len(arts) - len(ok)
    index = None
    for a in ok:
        if a[1] == 1:
            ss, files = par2_index(a[4])
            if files and ss:
                index = (ss, files)
                break
    if not index:
        return 'no PAR2 index among single-article files', [], None, ok
    S, files = index
    index_article = a
    built = []
    by_size = collections.defaultdict(list)
    for a in ok:
        by_size[a[2]].append(a)
    taken = collections.defaultdict(set)              # per file size: articles placed in a rebuilt file
    prep = {}

    def prepare(L):
        """every article's CRC32 per slice it touches (computed once per size), and candidates per part number"""
        if L not in prep:
            seg = []
            for a in by_size[L]:
                b, d, parts, pos = a[3], a[4], {}, 0
                while pos < len(d):
                    k = (b + pos) // S
                    cut = min(len(d), (k + 1) * S - b)
                    parts[k] = (zlib.crc32(d[pos:cut]), cut - pos)
                    pos = cut
                seg.append(parts)
            cands = collections.defaultdict(list)
            for i, a in enumerate(by_size[L]):
                cands[a[0]].append(i)
            prep[L] = seg, cands
        return prep[L]

    report, written, deferred = [], 0, []
    for f in files:
        L = f['length']
        arts_f = by_size.get(L, [])
        if not arts_f:
            report.append(f'{f["name"]}: no articles of size {L}')
            continue
        seg, cands = prepare(L)
        firsts = [i for i in cands[1] if hashlib.md5(arts_f[i][4][:16384]).digest() == f['md5_16k']]
        if len(firsts) != 1:
            report.append(f'{f["name"]}: {len(firsts)} first-article matches')
            deferred.append(f)
            continue
        total = arts_f[firsts[0]][1]
        chosen, used, failed = [firsts[0]], {firsts[0]}, False
        covered = len(arts_f[firsts[0]][4])
        for k, (_, want) in enumerate(f['slices']):
            end = min((k + 1) * S, L)
            pad = S - (end - k * S)                     # PAR2 zero-pads the last slice
            base = 0
            for i in chosen:
                if k in seg[i]:
                    c, n = seg[i][k]
                    base = crc_combine(base, c, n)
            need, cov, p = [], covered, len(chosen) + 1
            while cov < end and p <= total:
                need.append(p)
                cov += len(arts_f[cands[p][0]][4]) if cands.get(p) else 0
                p += 1

            left = [budget]

            def search(depth, crc):
                if depth == len(need):
                    full = crc_combine(crc, _zeros_crc(pad), pad) if pad else crc
                    return [] if full == want else None
                for i in cands.get(need[depth], []):
                    if i in used:
                        continue
                    left[0] -= 1
                    if left[0] < 0:
                        return None
                    c, n = seg[i].get(k, (0, 0))
                    r = search(depth + 1, crc_combine(crc, c, n))
                    if r is not None:
                        return [i] + r
                return None

            pick = search(0, base)
            if pick is None:
                why = 'too many combinations' if left[0] < 0 else 'no matching article (missing or damaged)'
                report.append(f'{f["name"]}: slice {k}/{len(f["slices"])}: {why}')
                failed = True
                break
            for i in pick:
                chosen.append(i)
                used.add(i)
                covered += len(arts_f[i][4])
        if failed:
            deferred.append(f)
            if stop_on_fail and len(deferred) > max_gaps:
                break
            continue
        data = b''.join(arts_f[i][4] for i in chosen)[:L]
        good = hashlib.md5(data).digest() == f['md5']
        if good:
            taken[L].update(chosen)
        built.append((f['name'], good, [arts_f[i] for i in chosen], 0))
        written += 1
        report.append(f'{f["name"]}: {"OK" if good else "MD5 MISMATCH"} ({len(chosen)} parts)')

    # A file that failed because one of its articles is missing: once every other file of its size is rebuilt, the
    # articles left over can only be its own. Place them by part number, check every slice not touching a gap, and
    # leave the gaps to PAR2 repair in the download client.
    gaps_total = 0
    for f in deferred if len(deferred) <= max_gaps else []:
        L = f['length']
        arts_f = by_size.get(L, [])
        if not arts_f:
            continue
        seg, cands = prepare(L)
        rest = collections.defaultdict(list)
        for i, a in enumerate(arts_f):
            if i not in taken[L]:
                rest[a[0]].append(i)
        total = arts_f[next(iter(rest.values()))[0]][1] if rest else 0
        if not rest or any(len(v) > 1 for v in rest.values()):
            report.append(f'{f["name"]}: leftover articles are ambiguous, cannot place')
            continue
        gaps = [p for p in range(1, total + 1) if p not in rest]
        if gaps_total + len(gaps) > max_gaps:
            report.append(f'{f["name"]}: {len(gaps)} articles missing, too many for repair')
            continue
        order = [rest[p][0] for p in sorted(rest)]
        bad = 0
        for k, (_, want) in enumerate(f['slices']):
            lo, hi = k * S, min((k + 1) * S, L)
            inside = [i for i in order if arts_f[i][3] < hi and arts_f[i][3] + len(arts_f[i][4]) > lo]
            covered = sum(seg[i][k][1] for i in inside if k in seg[i])
            if covered != hi - lo:
                continue                                 # slice touches a gap
            crc = 0
            for i in sorted(inside, key=lambda i: arts_f[i][3]):
                c, n = seg[i][k]
                crc = crc_combine(crc, c, n)
            pad = S - (hi - lo)
            if (crc_combine(crc, _zeros_crc(pad), pad) if pad else crc) != want:
                bad += 1
        if bad:
            report.append(f'{f["name"]}: leftover articles fail {bad} slice checks, cannot place')
            continue
        taken[L].update(order)
        gaps_total += len(gaps)
        built.append((f['name'], True, [arts_f[i] for i in order], len(gaps)))
        written += 1
        report.append(f'{f["name"]}: OK by elimination, {len(gaps)} missing article(s) left to PAR2 repair (parts {gaps})')
    return (f'missing articles: {missing}; files rebuilt: {written}/{len(files)}; gaps: {gaps_total}\n' + '\n'.join(report)), \
        built, index_article, ok


def write_files(built, outdir):
    os.makedirs(outdir, exist_ok=True)
    for name, _, arts_in_order, _ in built:
        size = arts_in_order[0][2]
        with open(os.path.join(outdir, name), 'wb') as fh:
            fh.write(b''.join(a[4] for a in arts_in_order)[:size])


def extras(built, index_article, ok):
    """Articles not in the rebuilt data files: PAR2 index, SFV/NFO and PAR2 recovery files, each as (kind, [articles])."""
    used = {id(a) for _, _, arts_in_order, _ in built for a in arts_in_order}
    rest = [a for a in ok if id(a) not in used]
    out, by_size = [], collections.defaultdict(list)
    for a in rest:
        by_size[a[2]].append(a)
    for size, group in by_size.items():
        parts = collections.Counter(a[0] for a in group)
        total = group[0][1]
        if total == 1:   # single-article files: name them by content
            for a in group:
                head = a[4][:200]
                kind = 'par2' if a is index_article or head.startswith(b'PAR2\x00PKT') else \
                       'sfv' if b'cksfv' in head or head.startswith(b';') else 'nfo'
                out.append((kind, [a]))
        elif len(group) == total and all(v == 1 for v in parts.values()):   # one complete file of this size
            first = min(group, key=lambda a: a[0])
            kind = 'vol' if first[4][:8] == b'PAR2\x00PKT' else 'other'
            out.append((kind, sorted(group, key=lambda a: a[0])))
    return out


if __name__ == '__main__':
    group, poster, outdir = sys.argv[1:4]
    import time
    t0 = time.time()
    mids, arts = fetch_all(group, poster)
    print(f'{len(mids)} articles listed, {sum(a[0] != "missing" for a in arts)} downloaded in {time.time() - t0:.0f} s', flush=True)
    t1 = time.time()
    report, built, _, _ = rebuild(arts)
    print(report)
    write_files(built, outdir)
    print(f'assembled in {time.time() - t1:.0f} s')
