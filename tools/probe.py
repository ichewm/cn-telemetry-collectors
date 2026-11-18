#!/usr/bin/env python3
"""Probe domains for the telemetry-collector fingerprint.

A collector endpoint is recognizable by what it does NOT have (a functional
website) plus how it answers beacon-shaped requests. The fingerprint below was
derived from live measurement — see the tables in CONTRIBUTING.md.

Signals (per domain, plain HTTP first; https endpoints legitimately refuse):
  GET /            functional sites serve real HTML (>= a few KB, 200);
                   collectors return 3xx/4xx/5xx or a tiny 200
  GET /collect?... beacon-shaped path on a collector returns 2xx with a tiny
                   body (e.g. Google Analytics: 200 / 35B)
  any path         collectors never serve meaningful HTML content anywhere

Usage:
  python3 tools/probe.py domain1 domain2 ...       # probe specific domains
  cat candidates.txt | python3 tools/probe.py      # probe from stdin
  python3 tools/probe.py --json a.com b.com        # machine-readable output
"""
import argparse
import json
import socket
import sys
import urllib.error
import urllib.request

BEACON_PATHS = ['/', '/collect?v=1&t=pageview', '/pixel']
TINY = 2048          # bodies larger than this on GET / smell like a real site
FUNC_BODY = 8192     # definitely functional content at this size


def probe_one(domain: str):
    """Return {path: 'code/sizeB'} plus a naive verdict for humans."""
    sig = {}
    for path in BEACON_PATHS:
        url = f'http://{domain}{path}'
        try:
            r = urllib.request.urlopen(url, timeout=6)
            code, size = r.status, len(r.read())
        except urllib.error.HTTPError as e:
            code, size = e.code, len(e.read() or b'')
        except Exception as e:
            code, size = type(e).__name__, 0
        sig[path.split('?')[0]] = f'{code}/{size}B'

    root = sig['/']
    verdict = 'inconclusive'
    if 'ERR' in root:
        verdict = 'http-refused (https-only? alive-unknown)'
    else:
        size = int(root.split('/')[1].rstrip('B') or 0)
        beacon = sig.get('/collect', '')
        if root.startswith('200') and size >= FUNC_BODY:
            verdict = 'REJECT: functional content at /'
        elif any(beacon.startswith('200') and int(beacon.split('/')[1].rstrip('B') or 99) < TINY
                 for _ in [0]):
            verdict = 'collector: beacon-shaped 2xx-tiny'
        elif size < TINY and not root.startswith('200'):
            verdict = 'collector: tiny non-200 at / (no website)'
        elif size < TINY:
            verdict = 'borderline: tiny 200 at /'
    return {'domain': domain, 'probe': sig, 'verdict': verdict}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('domains', nargs='*')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--timeout', type=int, default=6)
    args = ap.parse_args()
    socket.setdefaulttimeout(args.timeout)

    domains = args.domains or [l.strip().split('|')[0].strip()
                               for l in sys.stdin if l.strip() and not l.startswith('#')]
    results = [probe_one(d) for d in domains]
    if args.json:
        json.dump(results, sys.stdout, indent=2)
        return
    for r in results:
        probes = '  '.join(f'{p}={v}' for p, v in r['probe'].items())
        print(f'{r["domain"]:36s} {probes}')
        print(f'{"":36s} -> {r["verdict"]}')


if __name__ == '__main__':
    main()
