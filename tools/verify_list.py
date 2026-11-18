#!/usr/bin/env python3
"""L1+L2 automated verification of the STABLE list. Fails the build on evidence reversal.

Answers two questions a curated list must answer continuously, not just at admission:

  L1 — evidence freshness: is every entry STILL a telemetry-only collector?
       Re-probes all STABLE entries (http + https fallback) and checks DNS
       liveness. A fingerprint that reversed into functional content is a
       HARD failure (an entry that would break real traffic if graveyards).

  L2 — negative screening: does any entry collide with a "known functional"
       allowlist? Those allowlists (anudeepND etc.) are curated from real
       breakage reports by sinkhole users — exactly the ground truth of
       "domains you must not block". A collision is a HARD failure.

Warnings (stale DNS, inconclusive probes) do not fail the build; they go into
the weekly report for human review.

Usage: python3 tools/verify_list.py [--stable telemetry.domains]
Exit:  0 clean / 1 hard failures (printed with [HARD])
"""
import argparse
import socket
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_lists import parse_list
import probe

# Curated "known-functional" allowlists — i.e. domains the sinkhole community
# has explicitly un-broken after real breakage reports. A STABLE entry that
# appears here is contradicted by better evidence. (hagezi's allowlist URL
# churns; re-add it once its location settles.)
ALLOWLIST_SOURCES = [
    'https://raw.githubusercontent.com/anudeepND/whitelist/master/domains/whitelist.txt',
]


def fetch_lines(url, timeout=30):
    try:
        text = urllib.request.urlopen(url, timeout=timeout).read().decode('utf-8', 'ignore')
        return {l.strip().lower() for l in text.splitlines()
                if l.strip() and not l.startswith(('#', '!')) and '.' in l}
    except Exception as e:
        print(f'  !! allowlist source failed: {url} ({type(e).__name__})')
        return set()


def suffix_hit(domain, allowset):
    return any(a == domain or domain.endswith('.' + a) or a.endswith('.' + domain)
               for a in allowset)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stable', default='telemetry.domains')
    ap.add_argument('--skip-probe', action='store_true',
                    help='format + screening only (no network probing)')
    args = ap.parse_args()

    entries = parse_list(Path(args.stable))
    domains = [d for d, *_ in entries]
    hard, warn = [], []

    # ---- L2: negative screening against functional allowlists ----
    allow = set()
    for url in ALLOWLIST_SOURCES:
        allow |= fetch_lines(url)
    print(f'L2: functional-allowlist corpus: {len(allow)} domains '
          f'({len(ALLOWLIST_SOURCES)} sources)')
    for d in domains:
        if suffix_hit(d, allow):
            hard.append(f'{d}: collides with a known-functional allowlist — '
                        f'the community explicitly un-broke this domain; demote')

    # ---- L1a: DNS liveness ----
    for d in domains:
        try:
            socket.getaddrinfo(d, 80)
        except socket.gaierror:
            warn.append(f'{d}: DNS does not resolve — stale entry? (dropped by '
                        f'vendor, re-registered, or geo-CDN quirk)')

    # ---- L1b: fingerprint re-probe of every STABLE entry ----
    if not args.skip_probe:
        print(f'L1: re-probing all {len(domains)} STABLE entries (http, https fallback)')
        for d in domains:
            r = probe.probe_one(d)
            v = r['verdict']
            sig = '  '.join(f'{p}={x}' for p, x in r['probe'].items())
            print(f'  {d:40s} {v}')
            print(f'  {"":40s} {sig}')
            if v.startswith('REJECT'):
                hard.append(f'{d}: fingerprint REVERSED ({v}; {sig}) — now serves '
                            f'functional content; demote or reclassify')
            elif v in ('inconclusive', 'borderline: tiny 200 at /',
                       'unreachable (http and https both fail)'):
                warn.append(f'{d}: probe {v} — re-verify by hand/pcap')

    print()
    for w in warn:
        print(f'[warn] {w}')
    for h in hard:
        print(f'[HARD] {h}')
    print(f'verdict: {len(domains)} entries, {len(hard)} hard, {len(warn)} warnings')
    sys.exit(1 if hard else 0)


if __name__ == '__main__':
    main()
