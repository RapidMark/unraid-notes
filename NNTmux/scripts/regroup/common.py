"""Shared helpers for the regroup job and the signature report: NNTmux DB, Usenet, yEnc, PAR2, archive checks, NZB."""
import collections
import datetime as dt
import html
import nntplib
import re
import ssl
import struct
import subprocess

BASE = '/mnt/user/appdata/nntmux/regroup/'          # /config/regroup inside the container


def log(msg, path=BASE + 'regroup.log'):
    with open(path, 'a') as f:
        f.write(f'[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n')


def sql(q):
    return subprocess.run(['docker', 'exec', 'NNTmux', 'mariadb', '-N', '--quick', 'nntmux', '-e', q],
                          capture_output=True, text=True, check=True).stdout


def nntp():
    """Connect with NNTmux's own Usenet login (read from the container, never stored)."""
    env = dict(line.split('=', 1) for line in subprocess.run(
        ['docker', 'exec', 'NNTmux', 'sh', '-c', 'env | grep -E "^NNTP_(SERVER|PORT|SSLENABLED|USERNAME|PASSWORD)="'],
        capture_output=True, text=True, check=True).stdout.splitlines())
    if env.get('NNTP_SSLENABLED', '').lower() in ('true', '1'):
        return nntplib.NNTP_SSL(env['NNTP_SERVER'], int(env['NNTP_PORT']), env['NNTP_USERNAME'], env['NNTP_PASSWORD'],
                                ssl_context=ssl.create_default_context())
    return nntplib.NNTP(env['NNTP_SERVER'], int(env['NNTP_PORT']), env['NNTP_USERNAME'], env['NNTP_PASSWORD'])


def ydecode(lines):
    out, body = bytearray(), False
    for raw in lines:
        if raw.startswith(b'=ybegin'):
            body = True
            continue
        if raw.startswith(b'=ypart'):
            continue
        if raw.startswith(b'=yend'):
            break
        if not body:
            continue
        esc = False
        for c in raw:
            if esc:
                out.append((c - 106) % 256)
                esc = False
            elif c == 61:
                esc = True
            else:
                out.append((c - 42) % 256)
    return bytes(out)


def par2_files(data):
    """(name, length) for every file the PAR2 index describes."""
    found, i = {}, data.find(b'PAR2\x00PKT')
    while 0 <= i < len(data) - 64:
        length = struct.unpack('<Q', data[i + 8:i + 16])[0]
        if length < 64:
            break
        if data[i + 48:i + 64] == b'PAR 2.0\x00FileDesc':
            size = struct.unpack('<Q', data[i + 112:i + 120])[0]
            found[data[i + 120:i + length].rstrip(b'\x00').decode('utf-8', 'replace')] = size
        i = data.find(b'PAR2\x00PKT', i + length)
    return sorted(found.items())


ARCHIVE = re.compile(r'(\.part\d+\.rar|\.r\d\d|\.rar|\.7z(\.\d+)?|\.zip|\.\d{3})$', re.I)


def release_name(names):
    """The name the archive volumes share (ignores .nfo/.sfv and other extras)."""
    stems = collections.Counter(ARCHIVE.sub('', n) for n, _ in names if ARCHIVE.search(n))
    return stems.most_common(1)[0][0] if stems else None


def _vint(b, i):
    v = shift = 0
    while i < len(b):
        c = b[i]
        v |= (c & 0x7f) << shift
        i += 1
        shift += 7
        if not c & 0x80:
            break
    return v, i


def archive_locked(b):
    """'headers' when a password is needed even to list the files, 'files' when names are visible but the contents
    are encrypted, None when it opens without one. b = the first few KB of the first archive volume."""
    try:
        if b.startswith(b'Rar!\x1a\x07\x01\x00'):          # RAR5
            i = 8
            while i + 4 < len(b):
                hsize, j = _vint(b, i + 4)
                end = j + hsize
                htype, k = _vint(b, j)
                hflags, k = _vint(b, k)
                extra = data = 0
                if hflags & 0x01:
                    extra, k = _vint(b, k)
                if hflags & 0x02:
                    data, k = _vint(b, k)
                if htype == 4:                             # archive encryption header
                    return 'headers'
                if htype == 2:                             # first file header: look for an encryption record
                    r = end - extra
                    while extra and r < end:
                        rsize, q = _vint(b, r)
                        if _vint(b, q)[0] == 0x01:
                            return 'files'
                        r = q + rsize
                    return None
                i = end + data
            return None
        if b.startswith(b'Rar!\x1a\x07\x00'):              # RAR4
            i = 7
            while i + 7 <= len(b):
                htype, hflags, hsize = b[i + 2], struct.unpack('<H', b[i + 3:i + 5])[0], struct.unpack('<H', b[i + 5:i + 7])[0]
                if htype == 0x73 and hflags & 0x0080:      # main header: encrypted headers
                    return 'headers'
                if htype == 0x74:                          # first file header: password flag
                    return 'files' if hflags & 0x0004 else None
                add = struct.unpack('<I', b[i + 7:i + 11])[0] if hflags & 0x8000 else 0
                i += hsize + add
            return None
    except (IndexError, struct.error):
        return None
    return None  # 7z/zip/unknown: left to NNTmux's own password check


def nzb(u, file_names):
    """NZB for a rebuilt upload. file_names maps file number -> real name."""
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<!DOCTYPE nzb PUBLIC "-//newzBin//DTD NZB 1.1//EN" "http://www.newzbin.com/DTD/nzb/nzb-1.1.dtd">',
           '<nzb xmlns="http://www.newzbin.com/DTD/2003/nzb">']
    for fi in sorted(u['files'], key=lambda x: x['f']):
        subj = html.escape(f'[{fi["f"]}/{u["N"]}] - "{file_names[fi["f"]]}" yEnc (1/{fi["tp"]})', quote=True)
        out.append(f'<file poster="{html.escape(u["poster"], quote=True)}" date="{int(fi["start"])}" subject="{subj}">')
        out.append(f'<groups><group>{u["group"]}</group></groups><segments>')
        for pn, (mid, size) in sorted(fi['parts'].items()):
            out.append(f'<segment bytes="{size}" number="{pn}">{html.escape(mid)}</segment>')
        out.append('</segments></file>')
    out.append('</nzb>')
    return '\n'.join(out)
