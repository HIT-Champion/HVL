# Signet

**Tiếng Việt:** [README.md](README.md)

> **A self-hosted, open-source core platform that puts a seal of trust on everything that passes through it** — with
> its first application on top: an **e-Office** for incoming and outgoing official documents under Vietnam's Decree
> 30/2020/NĐ-CP on clerical work.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![CI](https://github.com/HIT-Champion/Signet/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/HIT-Champion/Signet/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/HIT-Champion/Signet)](https://github.com/HIT-Champion/Signet/releases)

Built for the **Vietnam Student Olympiad in Informatics 2026 — Open Source Software track (OLP PMNM 2026)**, theme
DX-OS Open-Core. Most project documentation is written in Vietnamese; this page is a translation of
[README.md](README.md).

**Try it:** <https://signet.htechcs.com> (release v1.1.0, see [Try it out](#try-it-out)) · or install it on your own
machine with four commands from [Building from source](#building-from-source).

**Five-minute tour and documentation map (in Vietnamese):** [`docs/README.md`](docs/README.md).

**Quick links:** [Introduction](#introduction) · [Architecture](#architecture) · [Features](#features) ·
[Four principles](#evidence-for-the-four-design-principles) · [Technology](#technology-and-licenses) ·
[Install](#building-from-source) · [Try it out](#try-it-out) · [Operations](#operations-and-testing) ·
[Troubleshooting](#troubleshooting) · [Documentation](#documentation) · [Contact](#contributing-and-contact) ·
[License](#license)

---

## Introduction

A *signet* is the ring once pressed into wax to seal letters and documents: the seal tells you who sent it, and an
unbroken seal tells you nobody opened or altered it. The Signet core does the same for digital data.

More than 900,000 small and medium enterprises, together with schools, faculties and grassroots agencies, digitalise
by buying many separate tools (the data turns into **silos**) or one monolithic system (the organisation becomes a
"hostage" of one vendor and loses its **digital sovereignty**). Either way, every new application rebuilds sign-in,
file storage, permissions and approval workflows from scratch — and has to take care of trust on its own, which it
usually does not.

Signet splits that shared part into a **headless core running in the background**, assembled entirely from open-source
software so the organisation can install and own it. A new application only plugs into the core and gets four seals of
trust out of the box, without building them itself:

| Seal | Meaning | Components | Tier 1 cluster |
|---|---|---|---|
| Known author | Every call carries an SSO identity, AI agents included; privileged roles must use two-factor authentication | Keycloak, APISIX | ① ② |
| Clean | Files are scanned for malware before they are stored; infected files never reach storage | `svc-files` + ClamAV | ① |
| Tamper-evident | Every change goes into a hash-chained audit log; the chain's anchor lives outside the database, and `make audit` points at the altered row | PostgreSQL, schema `core` | ⑥ |
| Verifiable from outside | Issued documents carry a QR code, a SHA-256 hash and a digital signature (illustrative only, no legal validity); the public verification portal needs no login | `svc-files`, route `/api/verify` | ④ ⑥ |

## Architecture

[![Architecture diagram: users go through the APISIX gateway to the two Tier 2 applications and the Tier 1 core services](docs/anh/kien-truc-tong-the.en.gif)](docs/anh/kien-truc-tong-the.en.gif)

Tier 1 is the headless core: identity, API gateway, data, workflow and the trust layer. Tier 2 holds the
applications: the e-Office and the P.A.R.A personal space, a second application plugged into the same core without
changing a line of core code ([`docs/them-ung-dung.md`](docs/them-ung-dung.md), Vietnamese). A third application, the
unit news board, exists only once installed with `moc app install`, so the diagram does not show it. Only the APISIX
gateway is exposed, and every request passes its web application firewall before it reaches the core; the labels on
its arrows are the real paths. The same holds inside the machine:
- application containers sit on their own Docker network, `apps` (no Internet access), where APISIX is the only core
  service;
- so an application's server side also reaches the core through the gateway, with the same token check, rate limits
  and WAF as a browser;
- `make demo-cai-ung-dung` checks that the container reaches APISIX only
  ([`docs/them-ung-dung.md`](docs/them-ung-dung.md#14-migration-và-mô-hình-tin-cậy) section 1.4, Vietnamese).

Thick borders mark the team's own code, boxes with a logo are upstream open source used as is, and the moving dots
follow two real requests. H-P-D-I architecture and technical decisions: [`docs/architecture.md`](docs/architecture.md)
(Vietnamese).

## Features

### e-Office

In faculties, schools and small agencies, official letters still arrive on paper or as scans sent over email and chat
apps; the clerk logs them in a notebook or a spreadsheet; managers write instructions on paper. On Signet, an official
letter goes through its whole life cycle **receive → register → instruct → handle → reply → issue → archive** following
Decree 30/2020/NĐ-CP on clerical work:

| Problem today | How Signet handles it | Space |
|---|---|---|
| Documents get lost; nobody knows whose desk they are on | Registration, a BPMN workflow, the right person's task inbox, instant notifications | [P] |
| Deadlines pass with no reminder | A deadline per assignment, automatic reminders, then escalation to managers; urgent documents go to the top | [P] |
| Typos and duplicate registrations | Wrong input is blocked in the form, on the server and in the database by one shared JSON Schema (poka-yoke); duplicates are refused | [P] |
| Clerks retype every incoming letter | An agent reads the PDF text layer or OCRs the scan and suggests the number, date, issuing body and summary | [I] |
| Units send documents to each other by email | In-system exchange on the same installation: the recipient gets an incoming document at once, byte-identical file, with a verification code | [P] |
| Sensitive documents leak | Per-file encryption, decrypted only in memory for named readers; every opened page is stamped with the viewer's name | [P] |
| Managers cannot see where work is stuck | An executive dashboard built on real data | [D] |
| Finding old documents takes time | Full-text search, including text inside attached PDFs and scans (OCR); a Q&A assistant answers with document number and page | [I] |

Also: incoming and outgoing registers in the Decree 30 format; several units on one installation, each person seeing
only their own unit's data; the e-Office interface in Vietnamese and English. Scope and roles:
[`docs/dac-ta-san-pham.md`](docs/dac-ta-san-pham.md); maturity of each feature with its evidence:
[`docs/muc-hoan-thien.md`](docs/muc-hoan-thien.md) (both in Vietnamese).

### P.A.R.A personal space

Each person's files in four folders — Projects · Areas · Resources · Archives; its own Keycloak client, calling the
core through the gateway like any application, without changing a line of core code (`make demo-ca-nhan`).

### Plugging in an application with one command

`python3 scripts/moc.py app install apps/bang-tin/app.yaml` reads the application's manifest and creates its Keycloak
client, APISIX route, container, schema and migrations run under the application's own database role (with no rights
on the core), Hasura tables and permissions, and a subscription to the core's document events. No core file changes.
Running it again creates nothing twice; `moc app remove` uninstalls the application and keeps its data. The sample
application is the unit news board (`apps/bang-tin`, `/bang-tin/`): documents just registered or issued appear as the
core's events arrive, and each person only sees items for documents they may read (`make demo-cai-ung-dung`). How it
works, the trust model and limits: [`docs/them-ung-dung.md`](docs/them-ung-dung.md) section 1 (Vietnamese).

### Local AI assistants

AI in Signet only **suggests**; people decide. Everything runs on the organisation's own server and no data is sent out.

| Agent | What it does |
|---|---|
| Reading incoming letters | Reads the PDF text layer, or recognises the text (Vietnamese Tesseract) for photos and scans, and suggests values for the six fields of the intake form with a confidence score. Numbers and dates are always decided by rules following the Decree 30 format, never by a model. On 22 sample documents: document number correct 20/22, issue date correct 22/22 |
| Q&A over the document store | Ask in everyday language and get verbatim quotes with the source "number · p. n"; only searches documents the asker may read, and restricted documents never enter the index |
| Assignment suggestions | When a document is registered, suggests the lead unit and the deadline, with similar past assignments as evidence; runs in parallel and never blocks the manager |
| Personal data masking | National ID numbers, phone numbers, emails and bank accounts are masked before they reach a model or the logs; people allowed to read the document still see the real numbers |

All four work **without a language model**, so they run in CI, on weak machines and offline. A local model (Ollama,
Qwen3 1.7B, on CPU) writes summaries and answers: `make ai-model`, then `make up-ai`. Measurements and limitations of
each agent (Vietnamese): [`docs/danh-gia-ai.md`](docs/danh-gia-ai.md).

### Screenshots

Taken automatically during the e2e run (`make e2e`), with fictional sample data. The interface is in Vietnamese by
default; every e-Office page also has an English version (the P.A.R.A personal space and Bảng tin are in
Vietnamese only).

| The clerk uploads an incoming letter, the agent pre-fills the fields | Managers see where work is stuck | Recipients verify a document without signing in |
|---|---|---|
| [![Receiving an incoming document with suggested fields](docs/anh/doc-van-ban-goi-y.png)](docs/anh/doc-van-ban-goi-y.png) | [![Management dashboard](docs/anh/dieu-hanh.png)](docs/anh/dieu-hanh.png) | [![Public document verification portal](docs/anh/xac-thuc.png)](docs/anh/xac-thuc.png) |

## Evidence for the four design principles

Each design principle of the contest has a demo run by **one command**, under a minute, printing every step with a ✓,
repeatable any number of times — the presentation script is [`docs/demo-script.md`](docs/demo-script.md).

| Principle | Demo | Command |
|---|---|---|
| (i) Data life cycle and velocity | A closed file is archived as a Parquet package + files + hashed manifest in write-locked cold storage; still searchable, and scanning the QR code still says "match"; in the UI: build case files, department heads archive, the reading room shows files stamped with the viewer's name; the director's dashboard counts archived documents with DuckDB straight from the Parquet packages in cold storage | `make demo-nong-lanh` |
| (ii) IT/OT convergence | Temperature sensor → NGSI-LD (Scorpio) → above the threshold, a draft "incident report" enters the outgoing document workflow | `make demo-it-ot` |
| (iii) Data governance | OpenLineage provenance: the archive package traces back to the business tables and original files; row counts and required columns checked before writing; every Overview chart traces back to its view and source tables (computed from the PostgreSQL catalog), shown as a graph on the Data lineage page (`/pha-he`) | `make demo-pha-he` |
| (iv) Zero-Trust | Quarantine: an EICAR file is blocked at the door, and the block is written to the audit log | `make demo-kiem-dich` |
| (iv) Zero-Trust | Restricted documents: files encrypted in storage, only named people can open them, opened copies carry the viewer's name | `make demo-han-che` |
| (iv) Zero-Trust | Secrets vault: services hold no secrets, the vault unseals itself on restart | `make demo-ket-bi-mat` |
| (iv) GitOps | Self-healing: delete a container and the reconciler rebuilds it from what git declares | `make demo-tu-phuc-hoi` |

Business demos, run the same way: `make demo-lien-thong` (exchange between two units), `make demo-nap-lo` (batch import
of incoming documents), `make demo-doc-van-ban`, `make demo-hoi-dap`, `make demo-giao-viec`, `make demo-che-pii` (AI
assistants), `make demo-ky-so` (digital signature, illustrative), `make demo-ca-nhan` (a second application on the same
core), `make demo-cai-ung-dung` (plugging in a third application with one command), `make demo-quy-trinh` (a fourth
application that brings its own process and runs it on the core's workflow engine), `make demo-tat-van-phong`
(turning off the e-Office part, the core keeps running), `make demo-log-tap-trung` (centralised logs).

## Technology and licenses

Signet orchestrates open-source software in its original form: official images, pinned versions, no upstream code
modified. The full list, libraries and reasons for each choice included: [`DEPENDENCIES.md`](DEPENDENCIES.md).

| Space | Component | Version | License | Role in Signet |
|---|---|---|---|---|
| Gateway | Apache APISIX | 3.18.0 | Apache-2.0 | The only exposed entry point: JWT check at the edge, path allow-list, rate limits |
| Gateway | Coraza, OWASP CRS (coraza-proxy-wasm) | 3.3.3, 4.14.0 (0.6.0) | Apache-2.0 | Web application firewall inside APISIX: inspects every request before the token check, attack payloads get 403 |
| [H] | Keycloak | 26.7.5 | Apache-2.0 | Single sign-on, TOTP; roles, unit and department go into the token |
| [P] | Flowable | 8.0.0 | Apache-2.0 | BPMN workflows for incoming and outgoing documents |
| [P] | Centrifugo | 6.9.7 | Apache-2.0 | Instant notifications over WebSocket, one channel per person |
| [D] | PostgreSQL | 16 | PostgreSQL | Main database, hash-chained audit log |
| [D] | Hasura GraphQL Engine CE | 2.51.0 | Apache-2.0 | Generated GraphQL, row-level permissions by role and unit |
| [D] | SeaweedFS | 4.48 | Apache-2.0 | S3-compatible file store, write-locked cold storage for archived records |
| [D] | Meilisearch CE | 1.54.3 | MIT | Full-text search, chunk index of the Q&A assistant |
| [I] | Ollama, Qwen3 weights | 0.35.1 | MIT; weights Apache-2.0 | Local language model, optional (profile `ai`) |
| [I] | Tesseract OCR | 5.5.0 | Apache-2.0 | Text recognition on scanned and photographed letters |
| Trust | ClamAV | 1.5.4 | GPL-2.0 | Malware scanning before storage |
| Trust | OpenBao | 2.7.1 | MPL-2.0 | Secrets vault, encryption keys for restricted documents, internal CA and signing keys |
| IT/OT | Scorpio Broker, PostGIS | 6.0.2, 16-3.5 | BSD-3-Clause, GPL-2.0 | NGSI-LD digital twins of sensors (profile `iot`) |
| Operations | Prometheus, Grafana OSS | 3.15.0, 13.2.3 | Apache-2.0, AGPL-3.0 | Monitoring and alerts for the API gateway and each component's status, internal network only |
| Operations | Vector, Parseable | 0.59.0, 3.2.4 | MPL-2.0, AGPL-3.0 | Centralised logs with personal data masked, optional (profile `logs`) |
| Operations | restic | 0.19.1 | BSD-2-Clause | Encrypted backup of databases, files and the vault |

Every license is OSI-approved. The GPL and AGPL components (ClamAV, PostGIS, Grafana, Parseable) run as independent
services talking over the network, with no linked code, so they do not conflict with Apache-2.0. The license of every
package, transitive ones included, is checked automatically with `make license-audit`.

## Building from source

### System requirements

| Component | Minimum version | Notes |
|---|---|---|
| Docker Engine | 24.0 | with the `docker compose` v2 plugin 2.17+ and `docker buildx` |
| GNU Make | 4.0 | runs the commands |
| Python | 3.10 | standard library only, nothing to install: sample data, smoke tests, demos, backup, install and operations commands |
| RAM | 8 GB | the whole system (default profiles, 16 containers) measured at about 3.2 GB when running (ClamAV 0.8 GB, Keycloak 0.6 GB, APISIX and Flowable 0.35 GB each, Grafana 0.3 GB), measured before `app-ca-nhan` (an nginx serving static pages) was added; the AI model needs up to 6 GB more |
| Free disk | 10 GB | images about 5 GB; AI models about 2 GB more |

Every tool used to build Signet is open-source software. No closed-source or home-made tool is needed.

### Steps

```bash
# 1. Get the source
git clone https://github.com/HIT-Champion/Signet.git
cd Signet

# 2. Configure (do NOT edit source code to configure — every parameter lives in .env)
make env              # creates .env from .env.example with random passwords; or: cp .env.example .env and edit
make check

# 3. Build the team's images and start everything (first run takes a few minutes: image pulls, ClamAV signatures)
make up

# 4. Load sample data: 2 units, departments, 10 accounts, documents at every step of the workflow
make seed
```

Open <http://localhost:8080> and sign in with an account from [Try it out](#try-it-out). Stop: `make down` (keeps data)
· wipe all data: `make reset` · list every command: `make help`. On a server with a domain name and HTTPS (Caddy in
front of APISIX), or on a machine without a public IP such as a laptop or a machine at home (Cloudflare Tunnel, profile
`tunnel`, no port opened): [`docs/trien-khai.md`](docs/trien-khai.md) (Vietnamese).

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
- If the package has a `VERSION` file at its root, the version is already recorded there (`git archive` fills it in
  when packing) and `make install` reads it, no need to set it by hand.
- Upgrade: stop the installation and run `make install` again with the same `PREFIX`. Compose, configuration and
  images are replaced; the installation's `.env` is kept, except `MOC_VERSION`,
  `COMPOSE_PROFILES` and `COMPOSE_FILE`, which `make install` sets again each time.
  For a running installation with data, use `scripts/nang_cap.sh nang /opt/moc`: it backs up first, checks
  afterwards and prints the rollback command ([`docs/trien-khai.md`](docs/trien-khai.md), section Vận hành).
- Uninstall: `make uninstall PREFIX=/opt/moc` removes exactly the installed files, keeping `.env` and the data.

## Try it out

**Online:** <https://signet.htechcs.com> runs release v1.1.0 on the team's machine, reaching the Internet through
Cloudflare Tunnel. Trial accounts are sent with the contest submission; the repository does not publish passwords.
Features newer than v1.1.0 (the "Chưa phát hành" — unreleased — section of [`CHANGELOG.md`](CHANGELOG.md)) are
available when you install from source.

**Your own installation:** the shared password of the sample accounts is the value of `MOC_DEMO_PASSWORD` in `.env`.
Clerks, faculty leaders, team and division heads, and unit administrators must use two-factor authentication: after
the password, enter a TOTP code. `make seed` gives these accounts a shared key (`MOC_DEMO_TOTP_SECRET`); `make totp`
prints the current code and the key, which you can add once to an authenticator app on your phone (FreeOTP, Aegis,
Google Authenticator). Real accounts in these roles set up TOTP with a QR code on first sign-in.

| Account | Role | Sees |
|---|---|---|
| `vanthu` | Clerk, Faculty of IT | Receives and registers; numbers and issues outgoing documents; every document of the faculty |
| `truongkhoa` | Dean | Instruction inbox, signs off outgoing documents; executive dashboard; every document of the faculty |
| `totruongdt`, `truongbmktpm` | Head of Training, Head of the Software Engineering department | Documents assigned to their team or department; assigns work; reviews drafts |
| `chuyenviendt`, `giamkhao`, `giangvienktpm` | Officer, lecturers | Documents assigned to them; drafts and submits outgoing documents |
| `quantri` | Unit administrator | The faculty's audit log; cannot read document contents |
| `vanthukt`, `truongkhoakt` | Faculty of Economics | Only Faculty of Economics documents |

Judges can try it quickly as `giamkhao` (an officer, no TOTP needed): the inbox already holds an urgent letter to
handle and a reply draft the team head sent back for changes.

| Address on your own installation | What it is | Sign-in |
|---|---|---|
| <http://localhost:8080> | e-Office | Yes |
| <http://localhost:8080/ca-nhan/> | P.A.R.A personal space | Yes |
| <http://localhost:8080/bang-tin/> | Unit news board, once installed with `make app-install APP=apps/bang-tin/app.yaml` | Yes |
| <http://localhost:8080/xac-thuc> | Document verification portal: enter a code or drop a PDF; codes of the issued sample documents are on each document's detail page (Outgoing documents, Issued tab) | No |
| <http://localhost:8080/trang-thai> | System status | No |
| <http://127.0.0.1:8180/admin> | Keycloak admin console, only on the server itself (`KEYCLOAK_ADMIN_*` account) | Yes |
| <http://127.0.0.1:3300> | Grafana API gateway monitoring, only on the server itself (remotely: SSH tunnel) | No |

## Operations and testing

Administrator tasks on a running installation are described in [`docs/van-hanh.md`](docs/van-hanh.md) (Vietnamese):

| Task | Main command |
|---|---|
| [Adding a unit](docs/van-hanh.md#thêm-đơn-vị-thuê-ước) (faculty, office, member school) | `python3 scripts/moc.py tenant create …` |
| [Backup and restore](docs/van-hanh.md#sao-lưu-và-khôi-phục) of every database, file and the vault into an encrypted restic repository | `make backup`, `make restore` |
| [Secrets vault](docs/van-hanh.md#két-bí-mật) OpenBao: limits, upgrading an old vault for digital signatures | `make demo-ket-bi-mat` |
| [GitOps and self-healing](docs/van-hanh.md#gitops-và-tự-phục-hồi): systemd timer, applies signed commits only | `make reconcile` |
| [Monitoring](docs/van-hanh.md#giám-sát) of the API gateway with Prometheus + Grafana | SSH tunnel to port 3300 |
| [Centralised logs](docs/van-hanh.md#log-tập-trung): Vector + Parseable, searched by request id `X-Request-Id` | `make logs-up`, `make logs-tra ID=…` |
| [IT/OT convergence](docs/van-hanh.md#hội-tụ-itot): NGSI-LD broker, sensors | `make demo-it-ot` |
| [Plugging in an application](docs/them-ung-dung.md#1-một-lệnh-moc-app-install) from a manifest, no core changes; removal keeps data | `python3 scripts/moc.py app install …`, `app list`, `app remove` |
| [Web application firewall](platform/apisix/README.md#tường-lửa-ứng-dụng-web--waf-f315): block, log only or off; find a block by `X-Request-Id` | `MOC_WAF=On` · `DetectionOnly` · `Off` |
| [Checking the audit log](db/README.md) outside the database | `make audit` |

| Command | What it checks | Needs |
|---|---|---|
| `make test` | Unit tests of `svc-files`, `svc-workflow` and the operations commands; form validation against `schemas/` with the same test cases as the server and database; tests of the personal space and the news board | Python + [uv](https://github.com/astral-sh/uv); Node 24 and `npm ci` in `apps/office` |
| `make smoke` | The full incoming and outgoing document flows through APISIX; verification portal, WebSocket notifications, audit log; blocking bad data, EICAR, admin paths; unit isolation; rate limits; secrets vault; reconciler; archiving; monitoring; the WAF blocks attack payloads without blocking real data | A running system + `make seed` |
| `make e2e` | A real browser (Playwright, in a container): bad forms blocked before sending, dropping a file on the verification page, two users notified at the same time, audit log, dashboard, digital signature | Same as above |
| `make do-doc-van-ban`, `do-hoi-dap`, `do-giao-viec`, `do-che-pii`, `do-so-lieu-sau` | Measure the AI agents on labelled samples (right / wrong / empty per field, recall@3, coverage); the "after" metrics of spec §8 | A running system (`do-che-pii` does not need one) |
| `db/tests/` | Schema, permissions by role and unit, constraints, audit log (including tampering attempts) on real PostgreSQL + Hasura | see [`db/README.md`](db/README.md) |
| `make sbom`, `make license-audit` | CycloneDX SBOM of the source tree (Syft); the license of every npm package, Python package and CI action, transitive ones included, against the policy in `DEPENDENCIES.md` | Docker, network access to PyPI |

[CI](.github/workflows/ci.yml) runs the table above and the demos on every pull request that changes code: it builds
from source with exactly the install commands, rehearses backup and restore, installs into another directory, runs
GitOps, and scans for secrets and vulnerable dependencies. Reminders can only be tested with short deadlines:
`MOC_SLA_DURATION=PT20S make up`, then `MOC_SLA_DURATION=PT20S make smoke`.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `make check` reports a missing `.env` or `docker compose` | Run `make env` to create `.env`; install the Docker Compose v2 plugin, 2.17 or newer |
| `make up` stops while pulling or building images: a timeout reaching `docker.io`, or `toomanyrequests` | The network blocks Docker Hub, or the anonymous pull limit is used up. Let Docker pull through the `mirror.gcr.io` mirror (`registry-mirrors`, needs `sudo`) as described in section 2b of [`docs/trien-khai.md`](docs/trien-khai.md#2b-máy-không-kéo-được-image-từ-docker-hub) (Vietnamese) |
| `make up` takes long, services still `starting` or `unhealthy` | The first run pulls about 5 GB of images and ClamAV loads its virus signatures, which takes a few minutes; `make up` waits up to 10 minutes. Watch with `make ps`, `make logs` |
| Port 8080 is already used by another program | Set `MOC_HTTP_PORT=8081` and `MOC_PUBLIC_URL=http://localhost:8081` in `.env` before the first `make up`: the Keycloak realm loads this address only once, so if it already ran, `make reset` and start again |
| Signing in fails when opened by a LAN IP address | Browsers only allow Web Crypto (PKCE sign-in, SHA-256 on the verification page) over `https` or on `localhost`. Use `localhost`, or set up HTTPS following [`docs/trien-khai.md`](docs/trien-khai.md) |
| The TOTP code is rejected | The phone's clock is off (codes change every 30 seconds): turn on automatic time, or get the code from the server's clock with `make totp`. After 10 wrong attempts Keycloak temporarily locks the account |
| "The security gateway blocked this content because some text looks like an attack pattern" (HTTP 403) | The WAF in the APISIX gateway saw text that looks like an attack payload. Edit the text or file name and send again. If real data was blocked by mistake, take the request id (`X-Request-Id`) of the block, find it with `docker compose logs apisix \| grep <id>` and add an exclusion as described in [`platform/apisix/README.md`](platform/apisix/README.md#đọc-nhật-ký-chặn) (Vietnamese); meanwhile you can set `MOC_WAF=DetectionOnly` (log only) and run `docker compose up -d apisix` |
| The machine slows down or runs out of RAM after turning on AI | The model needs up to 6 GB more RAM. Turn it off with `docker compose --profile ai stop ollama`; the agents fall back to working without a model |

Still stuck?
[Open an issue with the bug report template](https://github.com/HIT-Champion/Signet/issues/new?template=bug_report.yml),
including the output of `make ps` and the `make logs` excerpt of the failing service.

## Documentation

Most documents are in Vietnamese.

| Group | Documents |
|---|---|
| Use and operations | [Demo script](docs/demo-script.md) · [Operations](docs/van-hanh.md) · [Deploying to a server](docs/trien-khai.md) · [API documentation](docs/api/README.md) · [Adding a new application on the core](docs/them-ung-dung.md) |
| Technical | [H-P-D-I architecture](docs/architecture.md) · [Data model and permissions](docs/mo-hinh-du-lieu.md) · [Product specification](docs/dac-ta-san-pham.md) · [Feature maturity with evidence](docs/muc-hoan-thien.md) · [AI evaluation](docs/danh-gia-ai.md) · ["After" metrics of spec §8](docs/so-lieu-sau.md) · [H-P-D-I self-assessment](docs/tu-chan-doan.md) · [Git workflow](docs/git_flow.md) |
| Contest | [PoF self-assessment](docs/du-thi/pof-checklist.md) · [Likely jury questions](docs/du-thi/hoi-dap-hoi-dong.md) · [Theme, rules, judging criteria](docs/du-thi/olp-2026-brief.md) · [Problem statement analysis](docs/du-thi/olp-2026-de-thi.md) · [Development plan](docs/du-thi/ke-hoach-phat-trien.md) · [Research before the problem statement](docs/du-thi/nghien-cuu/) |
| Project | [Dependencies and licenses](DEPENDENCIES.md) · [Change history](CHANGELOG.md) · [Contributing guide](CONTRIBUTING.md) · [Security policy](SECURITY.md) · [Roadmap](ROADMAP.md) · [Code of conduct](CODE_OF_CONDUCT.md) |

### Repository layout

The team's own code lives in `apps/`, `services/` and `db/`. `platform/` only holds configuration for the open source
software the core uses unmodified (official images, no changes to upstream code).

```
apps/                e-Office (office/, Nuxt 4) · P.A.R.A personal space (ca-nhan/) · unit news board
                     (bang-tin/, plugged in with moc app install)
services/            svc-workflow/: Hasura Actions, BPMN workflows, notifications, reminders, assignment suggestions
                     svc-files/: files, quarantine, search, PDF rendering, signing, verification portal, AI agents
                     ot-sensor/: simulated temperature sensor (profile iot-sim)
db/                  PostgreSQL schema, Hasura permissions by role and unit, hash-chained audit log; tests/
schemas/             Form JSON Schemas, shared by the interface, the services and the database
platform/            Configuration for Keycloak, APISIX, Centrifugo, OpenBao, monitoring, centralised logs, systemd
scripts/             Operations commands (moc.py, seed, smoke, backup, audit, reconcile, demo), install, repo tooling
                     (PR checks, releases, license headers, architecture diagram generator so_do_kien_truc.py)
seed/ tests/e2e/     Fictional sample data · browser tests (Playwright)
docs/                Product documentation; api/: API docs; du-thi/: contest documents
docker-compose.yml   The whole system, split into profiles core, app, ai, iot, logs…
Makefile             Entry point for every command: make env, up, seed, test, smoke, install…
```

> Signet was formerly named **Mộc**. The technical codename `moc` remains in code and configuration: `MOC_*`
> variables, realm `moc`, the `scripts/moc.py` command, `moc/*` images, the `/opt/moc` install directory.

## Contributing and contact

- **Bugs, feature requests:** open an issue with the
  [bug report template](https://github.com/HIT-Champion/Signet/issues/new?template=bug_report.yml) or the
  [feature request template](https://github.com/HIT-Champion/Signet/issues/new?template=feature_request.yml); see
  [all issues](https://github.com/HIT-Champion/Signet/issues).
- **Change history:** [`CHANGELOG.md`](CHANGELOG.md) following Keep a Changelog; releases are on
  [Releases](https://github.com/HIT-Champion/Signet/releases).
- **Code contributions:** read [`CONTRIBUTING.md`](CONTRIBUTING.md) and the Git workflow
  [`docs/git_flow.md`](docs/git_flow.md) before opening a pull request; follow the
  [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
- **Security vulnerabilities:** do not open a public issue — report privately, see [`SECURITY.md`](SECURITY.md).

| Member | GitHub | Email |
|---|---|---|
| Nguyễn Huy Hoàng | [HoangTechCS-AIE](https://github.com/HoangTechCS-AIE) | <nguyenhuyhoangqbx5@gmail.com> |
| Đinh Văn Vượng | [Vanvuong2005827](https://github.com/Vanvuong2005827) | <vanvuong2005827@gmail.com> |
| Nguyễn Lê Hoài Nam | [nguyenlehoainam](https://github.com/nguyenlehoainam) | <namngyenhoai21@gmail.com> |

## License

Released under the **Apache License 2.0**, an OSI-approved license. Full text: [`LICENSE`](LICENSE). Why this license
was chosen: [`NOTICE`](NOTICE).

Every file carries copyright and licensing information following the [REUSE](https://reuse.software) specification:
source files have an Apache-2.0 header (`make license-check`), and files that cannot hold a header (JSON, images, PDF,
docs) are declared in [`REUSE.toml`](REUSE.toml). Check the whole repository with
`uvx --from reuse==5.0.2 reuse lint`.

Signet **orchestrates** upstream open-source software in its original form; it does not copy or modify their source
code into this repository. The project logos in the architecture diagram are trademarks of their owners, used only to
identify the components, and are not covered by Signet's Apache-2.0 license:
[`docs/anh/logo/NGUON.md`](docs/anh/logo/NGUON.md).
