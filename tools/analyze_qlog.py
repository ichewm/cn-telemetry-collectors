#!/usr/bin/env python3
"""L3 behavioral loop: measure list coverage against a live device's query log.

Pulls /stats.json (the read-only, unauthenticated dashboard endpoint) from a
deployed esp32-c3-adblock-cn device and compares its recent query log against
the STABLE telemetry list:

  - graveyard hits   — log entries the device answered with the graveyard
                       (verifies the fog/graveyard chain end to end)
  - candidate misses — BLOCKED domains that appear repeatedly but are NOT in
                       the STABLE list: the human-reviewable gap between what
                       the household actually sees and what we cover

This is the coverage half of the trust model: admission proves precision;
this measures recall. Small window (device keeps the last ~60 queries live)
— run it periodically and accumulate, or wire it to a qlog exporter later.

Usage: python3 tools/analyze_qlog.py [http://c3adblock.local]
"""
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_lists import parse_list


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else 'http://c3adblock.local'
    stats = json.load(urllib.request.urlopen(f'{base}/stats.json', timeout=8))
    log = stats.get('log', [])

    root = Path(__file__).parent.parent
    stable = {d for d, *_ in parse_list(root / 'telemetry.domains')}

    grave_hits = [e['d'] for e in log if e['b'] and e['d'] in stable]
    blocked_counter = Counter(e['d'] for e in log if e['b'] and e['d'] not in stable)

    print(f'device: {base}  fw={stats.get("fw", "?")}  '
          f'graveyard-answered (device): {stats.get("grave", "?")}')
    print(f'log window: {len(log)} queries '
          f'({sum(1 for e in log if e["b"])} blocked)')
    print()
    print('graveyard-list domains seen in this window:')
    for d in sorted(set(grave_hits)):
        print(f'  [grave] {d}')
    print()
    print('blocked-but-not-in-list domains (coverage candidates -> QUARANTINE):')
    for d, c in blocked_counter.most_common():
        print(f'  [miss x{c}] {d}')
    if not blocked_counter:
        print('  (none in this window)')


if __name__ == '__main__':
    main()
