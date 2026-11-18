#!/usr/bin/env python3
"""Recompute corroboration across public tracking lists; report new candidates.

Sources (fetched live, all degrade gracefully on failure):
  - Mozilla shavar / Disconnect  — Analytics category (entity -> domains)
  - EasyPrivacy                  — ||domain^ rules
  - AdGuard DNS filter (best effort; URL churn tolerated)

Matching is suffix-aware (list roots vs collection subdomains). A candidate is
reported when it appears in >= 2 sources and matches a collection-endpoint
naming pattern. New candidates that are not already in telemetry.domains or
QUARANTINE.domains are appended to QUARANTINE.domains with source provenance —
the weekly CI turns that into a PR for human review.

Usage:
  python3 tools/corroborate.py                # report + update QUARANTINE
  python3 tools/corroborate.py --dry-run      # report only
"""
import argparse
import datetime
import json
import re
import sys
import urllib.request
from pathlib import Path

SHAVAR_URL = ('https://raw.githubusercontent.com/mozilla-services/'
              'shavar-prod-lists/master/disconnect-blacklist.json')
EASYPRIVACY_URL = 'https://easylist-downloads.adblockplus.org/easyprivacy.txt'
ADGUARD_URLS = [  # best effort; the project reshuffles URLs periodically
    'https://raw.githubusercontent.com/AdguardTeam/AdGuardDNSFilter/master/Filters/filter.txt',
    'https://filters.adtidy.org/windows/filters/spyware.txt',
]

# collection-endpoint naming: log(s)/collect/pixel/beacon/analytics/stats/...
COLLECTOR_PAT = re.compile(
    r'^(www\.)?(a?logs?|applog|alog|collect|collector|pixel|beacon|analytics?|'
    r'stats?|metrics?|telemetry|tracking|insights?|monitor)([.-]|$)', re.I)


def fetch(url: str, timeout: int = 45):
    try:
        return urllib.request.urlopen(url, timeout=timeout).read().decode('utf-8', 'ignore')
    except Exception as e:
        print(f'  !! source failed: {url} ({type(e).__name__})', file=sys.stderr)
        return ''


def shavar_analytics():
    txt = fetch(SHAVAR_URL)
    if not txt:
        return set(), []
    domains = set()
    for entity in json.loads(txt)['categories'].get('Analytics', []):
        for name, sub in entity.items():
            if isinstance(sub, dict):
                for homepage, doms in sub.items():
                    if isinstance(doms, list):
                        domains.update(d for d in doms
                                       if isinstance(d, str) and '.' in d and '/' not in d)
    return domains, ['shavar:Analytics']


def rule_domains():
    srcs = []
    easy = set(re.findall(r'^\|\|([a-z0-9.-]+)\^', fetch(EASYPRIVACY_URL), re.M))
    if easy:
        srcs.append('easyprivacy')
    adguard = set()
    for url in ADGUARD_URLS:
        adguard |= set(re.findall(r'^\|\|([a-z0-9.-]+)\^', fetch(url), re.M))
    if adguard:
        srcs.append('adguard')
    return easy, adguard, srcs


def suffix_match(domain: str, ruleset: set) -> bool:
    return any(r == domain or domain.endswith('.' + r) or r.endswith('.' + domain)
               for r in ruleset)


def parse_existing(path: Path):
    if not path.exists():
        return set()
    return {l.split('|')[0].strip() for l in path.read_text().splitlines()
            if l.strip() and not l.lstrip().startswith('#')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--quarantine', default='QUARANTINE.domains')
    ap.add_argument('--stable', default='telemetry.domains')
    args = ap.parse_args()

    shavar, shavar_src = shavar_analytics()
    easy, adguard, rule_src = rule_domains()
    print(f'sources ok: {shavar_src + rule_src} '
          f'(shavar:{len(shavar)} easyprivacy:{len(easy)} adguard:{len(adguard)})')

    candidates = []
    for d in sorted(shavar):
        if not COLLECTOR_PAT.match(d):
            continue
        hits = ['shavar:Analytics'] + \
               (['easyprivacy'] if suffix_match(d, easy) else []) + \
               (['adguard'] if suffix_match(d, adguard) else [])
        if len(hits) >= 2:
            candidates.append((d, hits))

    known = parse_existing(Path(args.stable)) | parse_existing(Path(args.quarantine))
    fresh = [(d, h) for d, h in candidates if d not in known]
    print(f'corroborated candidates: {len(candidates)}, already known: '
          f'{len(candidates) - len(fresh)}, NEW: {len(fresh)}')
    for d, h in fresh:
        print(f'  NEW {d}  {"+".join(h)}')

    if fresh and not args.dry_run:
        today = datetime.date.today().isoformat()
        with open(args.quarantine, 'a') as f:
            f.write('\n# --- auto-discovered {today} (weekly CI; needs promotion review) ---\n'
                    .format(today=today))
            for d, h in fresh:
                f.write(f'{d} | {",".join(h)} | awaiting probe evidence (run '
                        f'tools/probe.py {d}) | {today}\n')
        print(f'appended {len(fresh)} candidates to {args.quarantine}')


if __name__ == '__main__':
    main()
