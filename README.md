# cn-telemetry-collectors

A **China-first, evidence-verified list of telemetry & beacon collection endpoints** — built for DNS sinkholes, with first-class support for *graveyard mode*.

> Measured gap: EasyPrivacy — the canonical international tracking list — contains **zero** entries for umeng (the most widely embedded CN analytics SDK). Western lists systematically under-cover Chinese collection endpoints. This project fills that gap, with evidence attached to every entry.

## Why "collection endpoints" and not just "tracking domains"

Every entry is a host whose *only* job is to receive telemetry beacons — `alog.umeng.com`, `www.google-analytics.com`, `api.mixpanel.com`. Two consequences:

1. **Subdomain precision matters.** `beacon.qq.com` is Tencent Beacon's *marketing website* (a live probe returns a 65&nbsp;KB page) — graveyarding it would break a real site. Its collection endpoints live elsewhere. This is why probing is mandatory: we rejected `beacon.qq.com` on probe evidence, despite its perfect-sounding name.
2. **The list enables graveyard mode.** A sinkhole can answer `0.0.0.0` (connection refused — the SDK retries, burns battery) or, for collector-only hosts, answer with **its own address and return `204 No Content`** — the SDK records a successful upload and stops retrying. Same blocking, quieter clients. The [esp32-c3-adblock-cn](https://github.com/ichewm/esp32-c3-adblock-cn) firmware implements this against `telemetry.bin`.

## Formats & subscription URLs

| Artifact | Format | Consumers |
|---|---|---|
| `telemetry.domains` | plaintext, provenance per entry | humans, reviewers |
| `telemetry.hosts` | `0.0.0.0 domain` | Pi-hole, any hosts-file sinkhole |
| `adguard.txt` | `\|\|domain^` rules | AdGuard Home / apps, uBlock |
| `telemetry.bin` | sorted 40-bit FNV-1a hashes (little-endian) | esp32-c3-adblock firmware |
| `noise-corpus.bin` | rank-ordered top-2000 web domains, fixed 32B records | profile-fog / DNS-noise consumers (popularity-weighted draw at read time) |

Subscribe (pick whichever URL your tool accepts — content is identical):

```
# rolling release assets (canonical, versioned)
https://github.com/ichewm/cn-telemetry-collectors/releases/download/list/telemetry.hosts
https://github.com/ichewm/cn-telemetry-collectors/releases/download/list/adguard.txt
https://github.com/ichewm/cn-telemetry-collectors/releases/download/list/telemetry.bin

# raw on the dist branch (rebuilt weekly)
https://raw.githubusercontent.com/ichewm/cn-telemetry-collectors/dist/telemetry.hosts

# Gitee mirror (CN-friendly; new-repo raw access may lag on first days)
https://gitee.com/hewmbj/cn-telemetry-collectors/raw/dist/telemetry.hosts
```

## Trust model — every entry carries evidence

No domain enters the STABLE list without passing one of two admission paths:

- **Path A — multi-source corroboration**: listed by ≥ 2 independent public tracking lists (Mozilla shavar/Disconnect `Analytics`, EasyPrivacy, AdGuard filters; suffix-aware matching).
- **Path B — documented + probed**: a documented SDK collection endpoint (official docs or a capture) **plus** a probe fingerprint match.

Probing (automated in `tools/probe.py`, re-run weekly by CI) recognizes collectors by what they *lack* — a functional website — and by how they answer beacon-shaped requests. Real fingerprints from this project's first run:

| Probe | Collector signature | Functional site |
|---|---|---|
| `GET /` | tiny non-200 (`alog.umeng.com` → 500/0B; `applog.snssdk.com` → 404/144B) or tiny 200 | real HTML content (KB-scale) |
| `GET /collect?v=1&t=pageview` | **2xx + tiny body** (`www.google-analytics.com` → 200/35B) | 404 |
| any path | never serves meaningful HTML | everywhere |

New auto-discovered candidates never go straight to STABLE: weekly CI appends them to `QUARANTINE.domains`, and a human promotes them by PR after reviewing the probe evidence. Removals are PRs too. **Precision over recall** — a missed domain costs nothing (it stays sinkholed as usual); a wrong one breaks real traffic.

## Repository layout

```
telemetry.domains     STABLE list — the single source of truth
QUARANTINE.domains    candidates awaiting promotion
tools/build_lists.py  compile to hosts / adguard / firmware-bin formats
tools/probe.py        collector-fingerprint probing (the evidence machine)
tools/corroborate.py  multi-source corroboration + quarantine updates
.github/workflows/    ci (tests+build) and weekly (recompute → probe → PR → release)
```

## Weekly automation

Every Monday, CI re-fetches all sources, re-runs corroboration, probes new candidates, appends them to `QUARANTINE.domains` via a PR with the evidence attached, and republishes the compiled artifacts to the rolling `list` release.

## Relationship & roadmap

- Companion data plane of [esp32-c3-adblock-cn](https://github.com/ichewm/esp32-c3-adblock-cn): the graveyard-answer firmware consumes `telemetry.bin`, the *fog* scheduler consumes `noise-corpus.bin`.
- ~~popularity-weighted corpus as a second artifact~~ — **shipped**: `noise-corpus.bin` (Majestic top-2000, fixed-width; consumers apply head-heavy rank weighting at draw time). Consumed by the esp32-c3-adblock-cn *fog* scheduler (DNS-noise profile poisoning, default off).
- Behavioral coverage loop (L3): `tools/analyze_qlog.py` measures list recall against a live device's query log and surfaces `miss` candidates — first run already produced three quarantine candidates (Tencent `aeventlog.beacon.qq.com`, `oth.eve.mdt.qq.com`, Google `beacons.gvt2.com`).

## License

MIT — code and data. Each entry's provenance is preserved in `telemetry.domains`; the upstream lists keep their own licenses.
