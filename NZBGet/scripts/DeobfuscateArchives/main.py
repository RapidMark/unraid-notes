#!/usr/bin/env python3
"""Extract archives posted without a file extension (7z, RAR, ZIP), found by signature."""
import os
import subprocess
import sys

SUCCESS, ERROR, NONE = 93, 94, 95

SIGNATURES = {
    b"7z\xbc\xaf\x27\x1c": "7z",
    b"Rar!\x1a\x07\x00": "rar",
    b"Rar!\x1a\x07\x01\x00": "rar",
    b"PK\x03\x04": "zip",
}
MIN_SIZE = 1024 * 1024


def kind_of(path):
    try:
        with open(path, "rb") as f:
            head = f.read(8)
    except OSError:
        return None
    for magic, kind in SIGNATURES.items():
        if head.startswith(magic):
            return kind
    return None


def extract(path, kind, dest):
    if kind == "rar":
        cmd = ["unrar", "x", "-o+", "-p-", "-y", path, dest + os.sep]
    else:
        cmd = ["7z", "x", "-y", "-p", "-o" + dest, path]
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)


def main(directory):
    if not directory or not os.path.isdir(directory):
        return NONE
    found = failed = 0
    for root, _, files in os.walk(directory):
        for name in files:
            path = os.path.join(root, name)
            if os.path.splitext(name)[1] or os.path.getsize(path) < MIN_SIZE:
                continue
            kind = kind_of(path)
            if kind is None:
                continue
            found += 1
            print(f"[INFO] {name}: {kind} archive without extension, extracting")
            result = extract(path, kind, root)
            if result.returncode == 0:
                os.remove(path)
                print(f"[INFO] {name}: extracted, archive removed")
            else:
                failed += 1
                print(f"[WARNING] {name}: extract failed: {result.stderr.strip()[:200]}")
    if found == 0:
        return NONE
    return ERROR if failed == found else SUCCESS


if __name__ == "__main__":
    if os.environ.get("NZBPP_TOTALSTATUS", "SUCCESS") != "SUCCESS":
        sys.exit(NONE)
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("NZBPP_DIRECTORY", "")))
