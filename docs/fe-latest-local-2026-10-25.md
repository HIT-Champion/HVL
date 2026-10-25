# Signet — FE integration and local acceptance, 25/10/2026

<!-- Copyright 2026 Signet Team -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

**Báo cáo giai đoạn đầu.** Trạng thái tiếp nối và bằng chứng hiện tại ở [fe-ui-audit-2026-10-25.md](fe-ui-audit-2026-10-25.md).

Source of this original stage: `origin/develop` at `f9abff0`. Working branch: `fe-integration`.
The integration imports the upstream snapshot without a merge. The existing FE Butter identity, JavaScript runtime,
Signet mark and hover/keyboard navigation are retained.

## Scope

Updated FE contracts for current APIs, incoming/outgoing documents, restricted access, archive case files and reading
room, audit events, metrics, lineage and quality checks, H-P-D-I self-assessment, app catalog, feedback and public status.
Navigation exposes these screens according to the user's backend role. The personal-space FE shares the font,
Butter/olive colors, focus states and responsive controls.

GraphQL calls reject non-success HTTP JSON responses and malformed responses without a data envelope, so a failed
mutation is never shown as saved. Structured backend error codes are retained. Two regression tests cover this case.
Lineage uses the shared Butter/olive, muted blue-gray and neutral palette instead of saturated blue/purple nodes.

Fixed runtime props lost when converting TypeScript components to JavaScript. Charts, source links, quality flags and
workflow processing forms now declare their actual Vue props; a compiler-based regression test covers those contracts.
Fixed collapsed navigation hit areas so their centers stay within the visible rail. Added keyboard-accessible scroll
regions for lineage tables, readable minimum table widths and responsive header/action sizing.

## Verification

- Office and personal-space unit/contract tests: 255 passed, no skipped tests.
- JavaScript/Vue compiler check: 75 files passed.
- Browser acceptance uses real Keycloak SSO and the local APISIX gateway, with WAF enabled. Test accounts use the
  seed's role permissions. Role-specific browser contexts are closed between scenarios.
- Screenshots cover 21 routes/states at 1440, 768 and 390 CSS pixels. These are sampled states, not a claim that every
  possible state and permission combination has been visually checked.
- REUSE lint passes, including self-hosted font notices for the personal-space app.
- Impeccable source detector scanned 76 files. It reported no source-pattern findings, but explicitly did not run parsed
  contrast/tiny-text rules for Vue files. Its result is supplementary to browser screenshots and interaction tests.

Screenshot sweep: 63 captures, no JavaScript page errors, no HTTP 5xx responses and no document-level horizontal overflow
in the sampled states. A later mobile header refinement is covered by explicit heading-width/height regression checks.
Browser suite: 29/29 scenarios passed through real SSO, workflow, archive, realtime notifications, access control,
public verification and WAF. After the last mobile header and GraphQL error-handling fixes, the focused FE/personal-space
suite is rerun, including the additional feedback retry scenario. Focused final result: 7/7 passed (24 seconds), including real feedback persistence after an injected HTTP 503.
Across both runs, 30 distinct browser scenarios passed.

Taste's app inspector also checked the public status screen at 1440/768/390: zero FAIL findings and one `panel-void`
warning. Equal-height layer groups are retained to compare the same operational layers across columns; the empty space
is not a placeholder for fabricated data. The three renders were visually reviewed.

Additional FE checks cover populated sensor readings with high-temperature and stale-signal flags using an explicit API
fixture. This validates rendering, not a live broker connection. Feedback testing exercises failure, preservation of the
comment and retry against the real local API.

The mobile lineage overflow came from absolutely positioned screen-reader detail text in quality badges. Positioning
that text relative to its badge resolves the overflow while preserving accessible detail; no page-wide overflow hiding
is used. Mobile page actions stack below headings to preserve a readable text measure.

## Local runtime and boundaries

Open `http://localhost:8080`. The isolated Compose project is `signet-fe-local`; existing local volumes are preserved.
The latest DB migrations, metadata and demo seed are loaded into this project. Windows-only LF script copies and
mount overrides live in ignored local files; upstream service scripts are not edited.

`git diff f86970f -- services db platform schemas scripts docker-compose.yml` must remain empty. These paths
contain the upstream snapshot, without custom BE or AI modifications.

At this original stage, no language model had been downloaded or enabled locally. In the continuation, both default models were downloaded and enabled; semantic indexing remains blocked and the user chose to wait for BE. Q&A can be tested in keyword/extract mode; this does not
validate model generation, embeddings or model quality. The optional sensor broker is off, so the sensor screen shows
an honest unavailable state. Live sensor readings require separate runtime setup.

The existing AWS demo remains on its prior release. This work does not push to GitHub or update the server.

## Reproduce

With the local stack running and demo seed available:

```powershell
node apps/office/scripts/check.mjs
node --test apps/office/tests/*.test.js apps/ca-nhan/tests/*.test.js
node tests/e2e/run-local.mjs
```

The E2E runner reads local `.env` values without printing credentials. On Windows it selects installed Edge; set
`MOC_E2E_CHANNEL` to override. Do not run simultaneous OTP-based suites against the same demo accounts.


Continuation note: upstream advanced from f9abff0 to f86970f. The latter snapshot was imported unchanged, including
Flowable optimistic-lock retries, scoped PKCE WAF exclusions, and future sensor-clock flags. It does not fix the
existing-index embedding transition. The user decision to wait for BE on that blocker remains in force.
