# Signet

**Tiếng Việt:** [README.md](README.md)

> **A self-hosted, open-source core platform that puts a seal of trust on everything that passes through it** — with
> its first application on top: an **e-Office** for incoming and outgoing official documents under Vietnam's Decree
> 30/2020/NĐ-CP on clerical work.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![CI](https://github.com/HIT-Champion/HVL/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/HIT-Champion/HVL/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/HIT-Champion/HVL)](https://github.com/HIT-Champion/HVL/releases)

A *signet* is the ring once pressed into wax to seal letters and documents: the seal tells you who sent it, and an
unbroken seal tells you nobody opened or altered it. The Signet core does the same for digital data. Every action
carries an identity, every file is scanned for malware before it is stored, every change goes into an audit log that
cannot be silently rewritten, and documents the organisation issues can be verified by their recipients.

Built for the **Vietnam Student Olympiad in Informatics 2026 — Open Source Software track (OLP PMNM 2026)**, theme
DX-OS Open-Core. Most project documentation is written in Vietnamese; this page is a translation of
[README.md](README.md).

**Quick links:** [Problem](#the-problem) · [Features](#features) ·
[Four design principles](#evidence-for-the-four-design-principles) · [Architecture](#architecture) ·
[Install](#building-from-source) · [Operations](#operations) · [Testing](#testing) · [Documentation](#documentation)

---

## The problem

More than 900,000 small and medium enterprises, together with schools, faculties and grassroots public agencies, are
digitalising in one of two ways, and both hit a wall:

- **Buying many separate tools**: each with its own accounts, data store and process. The data exists but cannot flow
  between departments: **data silos**.
- **Buying one monolithic system**: heavy and hard to upgrade; the organisation becomes a "hostage" of one vendor and
  loses its **digital sovereignty**.

Either way, every new application rebuilds sign-in, file storage, permissions and approval workflows from scratch — and
has to take care of trust on its own, which it usually does not.

Signet splits that shared part into a **headless core running in the background**, assembled entirely from open-source
software so the organisation can install and own it. A new application only plugs into the core; replacing an
application on the upper tier does not touch the core.

### The four seals of the core

What sets Signet apart is a shared **trust** layer. Every application that plugs in gets it out of the box, without
building it itself:

| Seal | Meaning | Components | Tier 1 cluster |
|---|---|---|---|
| Known author | Every call carries an SSO identity, AI agents included; privileged roles must use two-factor authentication | Keycloak, APISIX | ① ② |
| Clean | Files are scanned for malware before they are stored; infected files never reach storage | `svc-files` + ClamAV | ① |
| Tamper-evident | Every change goes into a hash-chained audit log; the chain's anchor lives outside the database, and `make audit` points at the altered row | PostgreSQL, schema `core` | ⑥ |
| Verifiable from outside | Issued documents carry a QR code, a SHA-256 hash and a digital signature (illustrative only, no legal validity); the public verification portal needs no login | `svc-files`, route `/api/verify` | ④ ⑥ |

## Features

### e-Office

In faculties, schools and small agencies, official letters still arrive on paper or as scans sent over email and chat
apps; the clerk logs them in a notebook or a spreadsheet; managers write instructions on paper. Popular document
management products are closed and keep the agency's data on the vendor's systems. On Signet, an official letter goes
through its whole life cycle **receive → register → instruct → handle → reply → issue → archive** following Decree
30/2020/NĐ-CP on clerical work:

| Problem today | How Signet handles it | Space |
|---|---|---|
| Documents get lost; nobody knows whose desk they are on | Registration, a BPMN workflow, the right person's task inbox, instant notifications | [P] |
| Deadlines pass with no reminder | A deadline per assignment, automatic reminders, then escalation to managers; urgent documents go to the top | [P] |
| Typos and duplicate registrations | Wrong input is blocked in the form, on the server and in the database by one shared JSON Schema (poka-yoke); duplicates are refused | [P] |
| Clerks retype every incoming letter | An agent reads the PDF text layer or OCRs the scan and suggests the number, date, issuing body and summary | [I] |
| Attachments may carry malware | Virus scan before storage | Core |
| No way to tell whether a received document is genuine | QR code, SHA-256, PAdES signature (illustrative); a public portal anyone can use | Core + [D] |
| Units send documents to each other by email | In-system exchange on the same installation: the recipient gets an incoming document at once, byte-identical file, with a verification code | [P] |
| Records altered after filing | Hash-chained audit log; filed records move to write-locked cold storage, hashed | Core + [D] |
| Sensitive documents leak | Per-file encryption, decrypted only in memory for named readers; every opened page is stamped with the viewer's name | [P] |
| Managers cannot see where work is stuck | An executive dashboard built on real data | [D] |
| Finding old documents takes time | Full-text search, including text inside attached PDFs; a Q&A assistant answers with document number and page | [I] |

Also: incoming and outgoing registers in the Decree 30 format, printable to PDF for signing and closing; several units
on one installation, each person seeing only their own unit's data; Vietnamese and English interface. Scope and user
roles in detail (Vietnamese): [`docs/dac-ta-san-pham.md`](docs/dac-ta-san-pham.md).

The problem follows the `[H] → [P] → [D] → [I]` path of the DX-OS model: a digital identity comes first so processes
can be standardised, standard processes produce clean data, and clean data lets AI make the right suggestions.

### Local AI assistants

AI in Signet only **suggests**; people decide. Everything runs on the organisation's own server and no data is sent out.

- **Reading incoming letters**: when the clerk uploads a letter, an agent reads the PDF text layer, or recognises the
  text (Vietnamese Tesseract) for photos and scans, and suggests values for the six fields of the intake form with a
  confidence score. Numbers and dates are always decided by rules following the Decree 30 format, never by a model.
  On 22 sample documents: document number correct 20/22, issue date correct 22/22.
- **Q&A over the document store**: ask in everyday language and get verbatim quotes with the source "number · p. n".
  The assistant only searches documents the asker may read; restricted documents never enter the index.
- **Assignment suggestions**: when a document is registered, an agent suggests the lead unit and the deadline, with
  similar past assignments as evidence. It runs in parallel and never blocks the manager.
- **Personal data masking**: national ID numbers, phone numbers, emails and bank accounts are masked before they
  reach a model or the logs; people allowed to read the document still see the real numbers.

All four work **without a language model** (rules, OCR, full-text search), so they run in CI, on weak machines and
offline. Turn on the local model (Ollama with Qwen3 1.7B and Qwen3-Embedding 0.6B, on CPU) to write summaries, search
by meaning and write answers: `make ai-model` (downloads the models once), then `make up-ai`. Method and full numbers
(Vietnamese): [`services/svc-files/README.md`](services/svc-files/README.md).

### Screenshots

Taken automatically during the e2e run (`make e2e`), with fictional sample data. The interface is in Vietnamese by
default; every page also has an English version.

| The clerk uploads an incoming letter, the agent pre-fills the fields | Managers see where work is stuck | Recipients verify a document without signing in |
|---|---|---|
| [![Receiving an incoming document with suggested fields](docs/anh/doc-van-ban-goi-y.png)](docs/anh/doc-van-ban-goi-y.png) | [![Management dashboard](docs/anh/dieu-hanh.png)](docs/anh/dieu-hanh.png) | [![Public document verification portal](docs/anh/xac-thuc.png)](docs/anh/xac-thuc.png) |

## Evidence for the four design principles

The contest requires the product to be built on four design principles. Each principle has a demo run by **one
command**, under a minute, printing every step with a ✓, repeatable any number of times — the presentation script is
[`docs/demo-script.md`](docs/demo-script.md).

| Principle | Demo | Command |
|---|---|---|
| (i) Data life cycle and velocity | A closed file is archived as a Parquet package + files + hashed manifest in write-locked cold storage; still searchable, and scanning the QR code still says "match" | `make demo-nong-lanh` |
| (ii) IT/OT convergence | Temperature sensor → NGSI-LD (Scorpio) → above the threshold, a draft "incident report" enters the outgoing document workflow | `make demo-it-ot` |
| (iii) Data governance | OpenLineage provenance: the archive package traces back to the business tables and original files; row counts and required columns checked before writing | `make demo-pha-he` |
| (iv) Zero-Trust | Quarantine: an EICAR file is blocked at the door, and the block is written to the audit log | `make demo-kiem-dich` |
| (iv) Zero-Trust | Restricted documents: files encrypted in storage, only named people can open them, opened copies carry the viewer's name | `make demo-han-che` |
| (iv) Zero-Trust | Secrets vault: services hold no secrets, the vault unseals itself on restart | `make demo-ket-bi-mat` |
| (iv) GitOps | Self-healing: delete a container and the reconciler rebuilds it from what git declares | `make demo-tu-phuc-hoi` |

Business demos, run the same way: `make demo-lien-thong` (exchange between two units), `make demo-doc-van-ban`,
`make demo-hoi-dap`, `make demo-giao-viec`, `make demo-che-pii` (AI assistants), `make demo-ky-so` (digital
signature, illustrative).

## Architecture

Tier 1 is the core — identity, API gateway, data, workflow and the trust layer — with no user interface. Tier 2 holds
the applications, here the e-Office. Only the APISIX gateway is exposed.

```
 Browser ──► APISIX :8080 ─┬─ /             → app-office (Nuxt, static pages; public /xac-thuc)       Tier 2
            (JWT check,    ├─ /realms/moc/*  → Keycloak (SSO login, TOTP)
             X-Request-Id) ├─ /v1/graphql    → Hasura ─┬─ PostgreSQL (core, office)                  Tier 1
                           │                           └─ Actions → svc-workflow → Flowable (BPMN)
                           ├─ /api/files, /api/search, /api/documents/*, /api/registers/* → svc-files
                           ├─ /api/verify (no token, rate-limited per IP) → svc-files
                           │  svc-files: ClamAV · SeaweedFS · Meilisearch · PDF rendering · Ollama (optional)
                           └─ /realtime (WebSocket) → Centrifugo ◄── svc-workflow pushes notifications
```

| Component | Role | Directory |
|---|---|---|
| Keycloak 26 | SSO, TOTP; roles, unit and department go into the token for Hasura | `auth/realm/` |
| Apache APISIX 3 | The only exposed gateway: path allow-list, JWT check at the edge, admin paths blocked, rate limits for login (per IP) and API (per session) | `gateway/` |
| Hasura 2 + PostgreSQL 16 | Generated GraphQL, row-level permissions by role and unit, hash-chained audit log | `db/` |
| Flowable 8 | BPMN processes for handling incoming documents and approving and issuing outgoing ones | `processes/` |
| `svc-workflow` | Hasura Actions: registration, submitting outgoing documents, task inbox, completing tasks, issuing; notifications, reminders; Keycloak directory sync; sensor alerts | `services/svc-workflow/` |
| `svc-files` | Uploads through ClamAV into SeaweedFS, Meilisearch search; outgoing-document PDFs with a QR code, PAdES signature (illustrative), printed registers; verification portal; the AI agents | `services/svc-files/` |
| Centrifugo 6 | Pushes notifications to the browser over WebSocket, one channel per person | `realtime/` |
| OpenBao 2 | Secrets vault: services fetch secrets via AppRole at start-up; encryption keys for restricted documents; internal CA and per-unit signing keys | `openbao/` |
| `app-office` | The e-Office interface (Nuxt 4, Tailwind), Vietnamese / English | `apps/office/` |
| Prometheus 3 + Grafana 13 | API gateway monitoring: request count, status codes, latency per route; internal network only | `monitoring/` |
| Scorpio 6 + PostGIS (profile `iot`) | NGSI-LD context broker: digital twins of sensors, measurement history | `ot/` |
| Ollama (profile `ai`, optional) | Local language model on its own internal network, cloud features off | `docker-compose.yml` |

The H-P-D-I model, tool map and technical decisions: [`docs/architecture.md`](docs/architecture.md). Data model and
permissions: [`docs/mo-hinh-du-lieu.md`](docs/mo-hinh-du-lieu.md) (both in Vietnamese).

> Signet was formerly named **Mộc**. The technical codename `moc` remains in code and configuration: `MOC_*`
> variables, realm `moc`, the `scripts/moc.py` command, `moc/*` images, the `/opt/moc` install directory.

## System requirements

| Component | Minimum version | Notes |
|---|---|---|
| Docker Engine | 24.0 | with the `docker compose` v2 plugin 2.17+ and `docker buildx` |
| GNU Make | 4.0 | runs the commands |
| Python | 3.10 | standard library only, nothing to install: sample data, smoke tests, demos, backup, install and operations commands |
| RAM | 8 GB | the whole system (default profiles, 15 containers) measured at about 3.2 GB when running (ClamAV 0.8 GB, Keycloak 0.6 GB, APISIX and Flowable 0.35 GB each, Grafana 0.3 GB); the AI model needs up to 6 GB more |
| Free disk | 10 GB | images about 5 GB; AI models about 2 GB more |

Every tool used to build Signet is open-source software. No closed-source or home-made tool is needed.

## Building from source

```bash
# 1. Get the source
git clone https://github.com/HIT-Champion/HVL.git
cd HVL

# 2. Configure (do NOT edit source code to configure — every parameter lives in .env)
make env              # creates .env from .env.example with random passwords; or: cp .env.example .env and edit
make check

# 3. Build the team's images and start everything (first run takes a few minutes: image pulls, ClamAV signatures)
make up

# 4. Load sample data: 2 units, departments, 10 accounts, documents at every step of the workflow
make seed
```

Open <http://localhost:8080> and sign in with a sample account; the shared password is the value of
`MOC_DEMO_PASSWORD` in `.env`. Clerks, faculty leaders, team and division heads, and unit administrators must use
two-factor authentication: after the password, enter a TOTP code. `make seed` gives these accounts a shared key
(`MOC_DEMO_TOTP_SECRET`); `make totp` prints the current code and the key, which you can add once to an authenticator
app on your phone (FreeOTP, Aegis, Google Authenticator). Real accounts in these roles set up TOTP with a QR code on
first sign-in.

| Account | Role | Sees |
|---|---|---|
| `vanthu` | Clerk, Faculty of IT | Receives and registers; numbers and issues outgoing documents; every document of the faculty |
| `truongkhoa` | Dean | Instruction inbox, signs off outgoing documents; executive dashboard; every document of the faculty |
| `totruongdt`, `truongbmktpm` | Head of Training, Head of the Software Engineering department | Documents assigned to their team or department; assigns work; reviews drafts |
| `chuyenviendt`, `giamkhao`, `giangvienktpm` | Officer, lecturers | Documents assigned to them; drafts and submits outgoing documents |
| `quantri` | Unit administrator | The faculty's audit log; cannot read document contents |
| `vanthukt`, `truongkhoakt` | Faculty of Economics | Only Faculty of Economics documents |

Judges can try it quickly as `giamkhao` (an officer, no TOTP needed): the inbox already holds an urgent letter to
handle and a reply draft the team head sent back for changes. The document verification portal needs no login:
<http://localhost:8080/xac-thuc>; codes of the issued sample documents are on each document's detail page (Outgoing
documents, Issued tab).

Stop: `make down` (keeps data) · wipe all data: `make reset` · list every command: `make help`.
The Keycloak admin console is only reachable on the server itself: <http://127.0.0.1:8180/admin> (`KEYCLOAK_ADMIN_*`
account).

### Installing outside the source tree

`make install` builds the team's images tagged with the version, copies `docker-compose.yml`, `.env` and the
configuration files the containers use to `PREFIX`, then checks that the installation no longer points back to the
source tree. Delete the source tree afterwards and the system keeps running.

```bash
sudo install -d -o "$USER" /opt/moc     # the install directory belongs to the operator, so make need not run as root
make install PREFIX=/opt/moc
make down                               # if it is running in the source tree: both share the same data
cd /opt/moc && docker compose up -d --wait
python3 scripts/seed.py                 # sample data, first time only
```

- `PREFIX` defaults to `/opt/moc`. The version comes from `git describe`; when installing from a `.tar.gz` package,
  set it by hand: `make install PREFIX=/opt/moc MOC_VERSION=0.1.0`.
- Upgrade: stop the installation and run `make install` again with the same `PREFIX`. Compose, configuration and
  images are replaced; the installation's `.env` is kept, only `MOC_VERSION` changes.
- Uninstall: `make uninstall PREFIX=/opt/moc` removes exactly the installed files, keeping `.env` and the data.
- On a server with a domain name and HTTPS: [`docs/trien-khai.md`](docs/trien-khai.md) (Vietnamese) — Caddy in front
  of APISIX, `MOC_HTTP_PORT=127.0.0.1:8080`, `MOC_TRUSTED_PROXY` so APISIX trusts Caddy's `X-Forwarded-*` headers. On
  a machine without a public IP (a laptop, a machine at home): Cloudflare Tunnel, profile `tunnel` (section 5b), with
  no port opened.

## Operations

Administrator tasks on a running installation are described in [`docs/van-hanh.md`](docs/van-hanh.md) (Vietnamese):

| Task | Main command |
|---|---|
| [Adding a unit](docs/van-hanh.md#thêm-đơn-vị-thuê-ước) (faculty, office, member school) | `python3 scripts/moc.py tenant create …` |
| [Backup and restore](docs/van-hanh.md#sao-lưu-và-khôi-phục) of every database, file and the vault into an encrypted restic repository | `make backup`, `make restore` |
| [Secrets vault](docs/van-hanh.md#két-bí-mật) OpenBao: limits, upgrading an old vault for digital signatures | `make demo-ket-bi-mat` |
| [GitOps and self-healing](docs/van-hanh.md#gitops-và-tự-phục-hồi): systemd timer, applies signed commits only | `make reconcile` |
| [Monitoring](docs/van-hanh.md#giám-sát) of the API gateway with Prometheus + Grafana | SSH tunnel to port 3300 |
| [IT/OT convergence](docs/van-hanh.md#hội-tụ-itot): NGSI-LD broker, sensors | `make demo-it-ot` |
| [Checking the audit log](db/README.md) outside the database | `make audit` |

## Testing

| Command | What it checks | Needs |
|---|---|---|
| `make test` | Unit tests of `svc-files`, `svc-workflow` and the operations commands; form validation against `schemas/` with the same test cases as the server and database | Python + [uv](https://github.com/astral-sh/uv); Node 24 and `npm ci` in `apps/office` |
| `make smoke` | The full incoming and outgoing document flows through APISIX; verification portal, WebSocket notifications, audit log; blocking bad data, EICAR, admin paths; unit isolation; rate limits; secrets vault; reconciler; archiving; monitoring | A running system + `make seed` |
| `make e2e` | A real browser (Playwright, in a container): bad forms blocked before sending, dropping a file on the verification page, two users notified at the same time, audit log, dashboard, digital signature | Same as above |
| `make demo-*` | The demos above; any failing step stops with exit code 1 | Same as above |
| `make audit` | Recomputes the hash-chained audit log outside the database, compares it with the anchor in cold storage and with the hashes of issued documents | A running system |
| `make do-doc-van-ban`, `do-hoi-dap`, `do-giao-viec`, `do-che-pii` | Measure the AI agents on labelled samples: right / wrong / empty per field, recall@3, coverage | A running system (`do-che-pii` does not need one) |
| `db/tests/` | Schema, permissions by role and unit, constraints, audit log (including tampering attempts) on real PostgreSQL + Hasura | see [`db/README.md`](db/README.md) |

Reminders can only be tested with short step deadlines (the real one is `PT24H`): `MOC_SLA_DURATION=PT20S make up`,
then `MOC_SLA_DURATION=PT20S make smoke`.

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs the whole table above on every pull request: it
builds the system from source with exactly `make env` → `make up` → `make seed` → `make smoke` → `make e2e` → 12 demos
(the quarantine demo is part of smoke); rehearses backup, wiping the data, restoring and running smoke again; runs
`make install` into another directory and smoke from the installation; GitOps against a local git repository; checks
that the API documentation in `docs/api/` matches the freshly built system; scans the commit history for secrets
(gitleaks) and the dependency lock files for known vulnerabilities (OSV-Scanner).

## Documentation

| Document | Content |
|---|---|
| [`docs/demo-script.md`](docs/demo-script.md) | Demo script: the four principles and the business demos, one command each |
| [`docs/van-hanh.md`](docs/van-hanh.md) | Operations: adding units, backup, secrets vault, GitOps, monitoring, IT/OT |
| [`docs/trien-khai.md`](docs/trien-khai.md) | Deploying to a server: HTTPS with Caddy in front of APISIX, operator account, firewall, nightly backup, upgrades |
| [`docs/api/`](docs/api/README.md) | API documentation: getting a token, calling GraphQL and REST through the gateway; per-role GraphQL schema and generated OpenAPI |
| [`docs/architecture.md`](docs/architecture.md) | H-P-D-I architecture, tool map, technical decisions |
| [`docs/mo-hinh-du-lieu.md`](docs/mo-hinh-du-lieu.md) | Data model, permissions, Hasura Actions, event formats |
| [`docs/dac-ta-san-pham.md`](docs/dac-ta-san-pham.md) | Product specification: problem, users, features |
| [`docs/du-thi/ke-hoach-phat-trien.md`](docs/du-thi/ke-hoach-phat-trien.md) | Development plan by phase, assignments, risks |
| [`docs/git_flow.md`](docs/git_flow.md) | Git workflow: branches, commits, pull requests, releases |
| [`docs/du-thi/pof-checklist.md`](docs/du-thi/pof-checklist.md) | Self-assessment against the 50-point PoF criteria |
| [`docs/du-thi/olp-2026-brief.md`](docs/du-thi/olp-2026-brief.md), [`docs/du-thi/olp-2026-de-thi.md`](docs/du-thi/olp-2026-de-thi.md) | The DX-OS theme, rules, judging criteria; analysis of the official problem statement |
| [`docs/du-thi/nghien-cuu/`](docs/du-thi/nghien-cuu/) | Research done before the problem statement was published (archived) |
| [`DEPENDENCIES.md`](DEPENDENCIES.md) | Upstream software, pinned versions, licenses |
| [`CHANGELOG.md`](CHANGELOG.md) | Change history |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Contributing guide |
| [`ROADMAP.md`](ROADMAP.md) | Roadmap |

## Reporting bugs and contributing

- **Bugs / feature requests**: open an issue at <https://github.com/HIT-Champion/HVL/issues>
- **Code contributions**: read [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request
- **Code of conduct**: [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)

## License

Released under the **Apache License 2.0**, an OSI-approved license. Full text: [`LICENSE`](LICENSE). Why this license
was chosen: [`NOTICE`](NOTICE).

Signet **orchestrates** upstream open-source software in its original form; it does not copy or modify their source
code into this repository. See [`DEPENDENCIES.md`](DEPENDENCIES.md).
