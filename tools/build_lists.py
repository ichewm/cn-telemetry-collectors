#!/usr/bin/env python3
"""Compile the STABLE list into the three distribution formats.

Inputs : telemetry.domains          (source of truth, pipe-separated)
Outputs: dist/telemetry.hosts       — hosts-file format (0.0.0.0 sinkhole)
         dist/adguard.txt           — AdGuard / Adblock `||domain^` rules
         dist/telemetry.bin         — sorted 40-bit FNV-1a hashes, little-endian,
                                       consumed by the esp32-c3-adblock-cn firmware
                                       (must match HASH_BYTES=5 in src/main.cpp)

Validation is strict: malformed lines, duplicates, or invalid hostnames abort
the build. Generated artifacts are never hand-edited.
"""
import argparse
import re
import sys
from pathlib import Path

HASH_BYTES = 5  # must match the firmware (esp32-c3-adblock: src/main.cpp HASH_BYTES)
MASK = (1 << (HASH_BYTES * 8)) - 1
FNV_OFFSET = 0xcbf29ce484222325
FNV_PRIME = 0x100000001b3

# Same FNV-1a truncation as the firmware's fnv40() — kept as an independent copy
# so this repo has no build-time dependency on the firmware repo. Test vectors
# in test_build_lists.py pin the two implementations together.
def fnv40(domain: str) -> int:
    h = FNV_OFFSET
    for b in domain.encode():
        h = ((h ^ b) * FNV_PRIME) & ((1 << 64) - 1)
    return h & MASK

HOSTNAME_RE = re.compile(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$')

HEADER = ("# cn-telemetry-collectors — {desc}\n"
          "# source: https://github.com/ichewm/cn-telemetry-collectors\n"
          "# license: MIT — data and code\n"
          "# generated: do not edit; compiled from telemetry.domains\n")


def parse_list(path: Path):
    """Parse a .domains file -> list of (domain, sources, evidence, added)."""
    entries, seen = [], set()
    for n, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.split('#')[0].strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) != 4:
            sys.exit(f"{path.name}:{n}: expected 4 pipe-separated fields, got {len(parts)}: {line!r}")
        domain, sources, evidence, added = parts
        if not HOSTNAME_RE.match(domain):
            sys.exit(f"{path.name}:{n}: invalid hostname {domain!r}")
        if domain in seen:
            sys.exit(f"{path.name}:{n}: duplicate entry {domain}")
        if not sources or not added:
            sys.exit(f"{path.name}:{n}: empty sources or added field")
        seen.add(domain)
        entries.append((domain, sources, evidence, added))
    return entries


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--src', default='telemetry.domains')
    ap.add_argument('--out', default='dist')
    args = ap.parse_args()

    entries = parse_list(Path(args.src))
    domains = sorted(d for d, *_ in entries)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    (out / 'telemetry.hosts').write_text(
        HEADER.format(desc='telemetry collection endpoints (hosts format)') +
        ''.join(f'0.0.0.0 {d}\n' for d in domains))
    (out / 'adguard.txt').write_text(
        HEADER.format(desc='telemetry collection endpoints (AdGuard/Adblock rules)') +
        ''.join(f'||{d}^\n' for d in domains))
    with open(out / 'telemetry.bin', 'wb') as f:
        for h in sorted(fnv40(d) for d in domains):
            f.write(h.to_bytes(HASH_BYTES, 'little'))

    print(f'entries: {len(domains)}')
    print(f'wrote: {out}/telemetry.hosts, {out}/adguard.txt, {out}/telemetry.bin '
          f'({len(domains) * HASH_BYTES}B)')


if __name__ == '__main__':
    main()
