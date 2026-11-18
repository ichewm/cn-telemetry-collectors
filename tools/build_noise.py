#!/usr/bin/env python3
"""Build the DNS-noise corpus artifact (profile-fog data source).

The corpus is the popularity-ranked top of the public web (Majestic Million,
ranked by referring subnets), encoded as FIXED-WIDTH 32-byte records so the
consumer can pick a random entry with one seek: `offset = rank * 32`.

Popularity weighting is NOT baked into the file — the consumer (firmware fog
scheduler) draws the RANK from a head-heavy distribution at query time, which
keeps the artifact a plain, auditable, rank-ordered list.

Outputs (dist/):
  noise-corpus.bin   2000 x 32B records, NUL-padded, rank-ordered
  noise-corpus.txt   same, human-readable (provenance/testing)
"""
import argparse
import re
import sys
import urllib.request
from pathlib import Path

RECORD = 32
COUNT = 2000
MAJESTIC_URL = 'https://downloads.majestic.com/majestic_million.csv'
HOSTNAME_RE = re.compile(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$')


def encode_corpus(domains):
    """domains (rank-ordered) -> fixed-width bytes; silently skips invalid/overlong/dupes."""
    out = bytearray()
    seen = set()
    for d in domains:
        d = d.strip().lower()
        if d.startswith('www.'):
            d = d[4:]
        if not HOSTNAME_RE.match(d):
            continue
        if len(d) + 1 > RECORD or d in seen:
            continue
        seen.add(d)
        rec = d.encode() + b'\x00' * (RECORD - len(d))
        out += rec
    n = len(out) // RECORD
    return bytes(out[:COUNT * RECORD]), min(n, COUNT)


def fetch_majestic(max_lines=3000):
    """Stream the Majestic CSV; stop after enough lines (don't pull 80MB)."""
    req = urllib.request.Request(MAJESTIC_URL, headers={'User-Agent': 'cn-telemetry-collectors/1.0'})
    domains = []
    with urllib.request.urlopen(req, timeout=120) as r:
        header = r.readline().decode().split(',')
        di = header.index('Domain')
        for line in r:
            parts = line.decode('utf-8', 'ignore').split(',')
            if len(parts) > di:
                domains.append(parts[di])
            if len(domains) >= max_lines:
                break
    return domains


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='dist')
    args = ap.parse_args()

    print(f'fetching {MAJESTIC_URL} (streamed, top lines only) ...')
    domains = fetch_majestic()
    blob, n = encode_corpus(domains)
    if n < COUNT // 2:
        sys.exit(f'too few valid domains ({n}) — source unusable')
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'noise-corpus.bin').write_bytes(blob)
    (out / 'noise-corpus.txt').write_text(
        '# cn-telemetry-collectors noise corpus — rank-ordered, fixed 32B records\n'
        '# source: Majestic Million (referring-subnet rank), streamed top\n'
        + ''.join(blob[i * RECORD:blob.find(b'\x00', i * RECORD)].decode() + '\n'
                  for i in range(n)))
    print(f'corpus: {n} records x {RECORD}B = {len(blob)}B -> {out}/noise-corpus.bin')


if __name__ == '__main__':
    main()
