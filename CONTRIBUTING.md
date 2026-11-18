# Contributing

Thanks for hardening the list. This document is the contract that keeps the
list trustworthy — read it before your first PR.

## What belongs here

**Collection endpoints only**: a hostname whose sole purpose is to *receive*
telemetry/analytics beacons. If the host also serves functional content
(a website, an API your app needs, a login page), it does not belong here —
not even "mostly telemetry". We bias to precision: a missed domain costs
nothing (it is still sinkholed with `0.0.0.0` like any other blocklist entry);
a wrong entry breaks real traffic for every consumer of this list.

**Explicitly out of scope:**
- Marketing/company domains (`umeng.com` is a website; `alog.umeng.com` is a collector)
- Shared logging infrastructure (`*.log.aliyuncs.com` etc. — self-hosted per app)
- Self-hosted analytics patterns (per-app hostnames cannot be enumerated safely)
- Crash reporters are accepted **by policy** (they don't affect the end user),
  flag them in the evidence field so consumers can filter if they disagree
- Anything you cannot attach evidence for

## Admission paths (either one qualifies)

### Path A — multi-source corroboration
The domain appears in **≥ 2 independent public tracking lists**:
Mozilla shavar (Disconnect) `Analytics` category, EasyPrivacy, AdGuard filters.
Run `python3 tools/corroborate.py --dry-run` to check — suffix-aware matching
is used, because list roots (`google-analytics.com`) and rules
(`www.google-analytics.com^`) rarely match exactly.

### Path B — documented endpoint + probe
For CN SDKs (western lists have near-zero coverage — we measured), attach:
1. **Documentation or capture** — the SDK's official docs, or a pcap/log excerpt
   showing the app posting beacons to this host
2. **A probe fingerprint** — run `python3 tools/probe.py your.domain` and paste
   the output into the evidence field

## The probe fingerprint (what counts as evidence)

| Probe | Collector says | Functional site says |
|---|---|---|
| `GET /` | tiny non-200 (500/0B, 404/144B, 504/158B — all real examples) or a tiny 200 | real HTML (KB-scale) |
| `GET /collect?v=1&t=pageview` | 2xx + tiny body (GA: 200/35B) | 404 |
| `http://` refused | https-only collector — **inconclusive**, needs docs (Path B) or 2 sources (Path A) | |

**The cautionary tale that shaped this rule**: `beacon.qq.com` — a name that
could not be more telemetry-flavored — serves a 65&nbsp;KB product website at
`GET /`. It is rejected. The name is the hypothesis; the probe is the evidence.

## Workflow

```
1. Open a PR adding your entry to QUARANTINE.domains (format below)
2. CI probes it and attaches the fingerprint to the PR
3. A reviewer promotes qualifying entries to telemetry.domains (sets `added`)
4. Weekly CI rebuilds + republishes dist/ artifacts and the rolling release
```

Entry format (pipe-separated, comments with `#`):

```
domain | sources | evidence | added
```

- `sources` — comma-separated provenance (`shavar:Analytics`, `easyprivacy`,
  `umeng-sdk-docs`, `manual-pcap`, …)
- `evidence` — probe output (`probe:http GET /=500/0B`), or
  `2src; https-only endpoint`, or a link to docs/pcap
- `added` — date of promotion to STABLE

## Removals

Open a PR deleting the line, with one of: dropped from its sources, probe
reversal (endpoint now serves functional content), or a consumer breakage
report. Breakage reports trump everything.

## Local development

```bash
python3 tools/test_build_lists.py        # unit tests (hash format pinned to firmware)
python3 tools/build_lists.py             # compile dist/ artifacts
python3 tools/probe.py some.domain       # gather evidence
python3 tools/corroborate.py --dry-run   # check sources for a domain
```
