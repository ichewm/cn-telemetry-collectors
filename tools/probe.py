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
import ssl
import sys
import urllib.error
import urllib.request

BEACON_PATHS = ['/', '/collect?v=1&t=pageview', '/pixel']
TINY = 2048          # bodies larger than this on GET / smell like a real site
FUNC_BODY = 8192     # definitely functional content at this size
_NOVERIFY = ssl.create_default_context()
_NOVERIFY.check_hostname = False
_NOVERIFY.verify_mode = ssl.CERT_NONE


def _size(tok):
    try:
        return int(tok.split('/')[1].rstrip('B'))
    except (IndexError, ValueError):
        return 0


def _failed(tok):
    """Connection-level failure (exception class name instead of an HTTP code)."""
    return not tok.split('/')[0].isdigit()


def _fetch(url):
    ctx = _NOVERIFY if url.startswith('https') else None
    try:
        r = urllib.request.urlopen(url, timeout=6, context=ctx)
        return r.status, len(r.read())
    except urllib.error.HTTPError as e:
        return e.code, len(e.read() or b'')
    except Exception as e:
        return type(e).__name__, 0

def probe_one(domain: str):
    """Return {path: 'code/sizeB'} plus a verdict for humans/CI.

    Verdict precedence (validated against real endpoints):
      1. beacon-shaped 2xx-tiny (e.g. GA /collect -> 200/35B) beats everything:
         GA itself serves a 118KB marketing page at GET / — the beacon path is
         the decisive signal, not the landing page
      2. functional content at / (KB-scale HTML) -> REJECT
      3. tiny non-200 at / (500/0B, 404/144B — no website) -> collector
    """
    sig = {}
    for path in BEACON_PATHS:
        code, size = _fetch(f'http://{domain}{path}')
        sig[path.split('?')[0]] = f'{code}/{size}B'

    http_all_err = all(_failed(v) for v in sig.values())
    if http_all_err:                       # https-only endpoint: fingerprint over TLS
        for path in ['/', '/collect?v=1&t=pageview']:
            code, size = _fetch(f'https://{domain}{path}')
            sig['https ' + path.split('?')[0]] = f'{code}/{size}B'

    beacon = sig.get('/collect', '')
    beacon_https = sig.get('https /collect', '')
    root = sig['/']
    root_https = sig.get('https /', '')

    def _beacon_ok(tok):
        return tok.startswith('200') and _size(tok) < TINY

    verdict = 'inconclusive'
    if _beacon_ok(beacon) or _beacon_ok(beacon_https):
        verdict = 'collector: beacon-shaped 2xx-tiny'
    elif any(('ERR' not in t) and t.startswith('200') and _size(t) >= FUNC_BODY
             for t in (root, root_https)):
        verdict = 'REJECT: functional content at /'
    elif http_all_err:
        if root_https and not _failed(root_https) and _size(root_https) < TINY \
                and not root_https.startswith('200'):
            verdict = 'collector(https): tiny non-200, no website'
        elif root_https and not _failed(root_https) and _size(root_https) < TINY:
            verdict = 'borderline(https): tiny 200 at /'
        elif root_https and not _failed(root_https):
            verdict = 'REJECT: functional content at / (https)'
        else:
            verdict = 'unreachable (http and https both fail)'
    else:
        size = _size(root)
        if _failed(root):
            verdict = 'unreachable: http connection failed, https not attempted'
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
