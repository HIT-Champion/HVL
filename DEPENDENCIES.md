# Danh mục phần mềm thượng nguồn và giấy phép

Tài liệu này làm rõ mọi thư viện, gói và phần mềm thượng nguồn mà Signet phụ thuộc vào — yêu cầu
bắt buộc theo tiêu chí chấm điểm PoF #5 (*"Có thông tin làm rõ các thư viện, gói đính kèm được
sử dụng"*).

Tệp này ghi vì sao: nguyên tắc thêm phụ thuộc, lý do chọn từng thành phần, chính sách giấy phép, các gói kéo theo có
giấy phép cần giải thích và các thành phần đã cân nhắc nhưng không dùng. Bảng gọn của các thành phần dùng trực tiếp
(tên, phiên bản, giấy phép, mô tả, trang chủ) nằm ở [`COPYRIGHT.txt`](COPYRIGHT.txt), sinh từ các bảng "Thành phần"
dưới đây bằng `make copyright`; `scripts/tests/test_copyright_txt.py` báo đỏ khi hai tệp lệch nhau.

## Nguyên tắc phụ thuộc

1. **Không bundle.** Kho mã nguồn này **không** chứa bản sao mã nguồn của bất kỳ dự án nào khác.
   Mọi phần mềm thượng nguồn được nạp lúc chạy qua image Docker chính thức có ghim thẻ phiên bản và
   digest, hoặc qua trình quản lý gói (`npm`, `pip`) với tệp khóa phiên bản (lockfile).
2. **Không chỉnh sửa upstream.** Mã nguồn của các dự án thượng nguồn được dùng ở dạng **nguyên
   bản**. Mọi tùy biến của Signet nằm ở lớp cấu hình, plugin hoặc adapter riêng.
3. **Ưu tiên thư viện sẵn có của hệ thống** thay vì đóng gói kèm bản riêng.
4. **Kiểm tra tương thích giấy phép.** Mọi thành phần mới phải có giấy phép được OSI phê duyệt và
   tương thích với Apache-2.0 của Signet. Ngoại lệ chỉ khi ghi ở mục Kiểm tra tương thích giấy phép, kèm lý do và
   phạm vi: giấy phép dễ dãi tương đương một giấy phép OSI (PSF-2.0 là phần đầu của Python-2.0; MIT-CMU là một dạng
   HPND), hoặc dữ liệu, công cụ chỉ chạy lúc dựng (CC-BY-4.0, CC0-1.0). Không thành phần nào, kể cả tùy chọn, được đòi
   phần mềm nguồn đóng (#452).

## Cách đọc

- **Thành phần** dẫn tới trang chủ của dự án. Vế đầu của cột **Vai trò** (tới dấu `:`, `;` hay ngoặc đầu tiên) thành
  cột Mô tả của `COPYRIGHT.txt`, nên viết vế đó thành một cụm tự đứng được.
- **Phiên bản ghim**: thành phần đã chạy (Phase 1) ghi đúng thẻ trong `docker-compose.yml` — cập nhật
  18/10/2026; thành phần phase sau là bản ổn định mới nhất tại 09/10/2026, chốt lại khi đưa vào. Chỉ
  chọn bản đã phát hành ít nhất hai tuần.
- **Ngoại lệ vá bảo mật**: bản đang ghim có lỗ hổng đã công bố (OSV-Scanner trong CI báo) mà bản vá chưa đủ hai
  tuần thì dùng bản vá ngay, ghi ở đây. 22/10/2026: Pillow 13.0.0 (PyPI 16/10, vá các GHSA của 12.3.0) và pypdf
  6.21.1 (17/10, vá 5 GHSA của 6.19.0) — cả hai đọc tệp người dùng tải lên (`svc-files`); certifi 2026.10.19 (20/10,
  bỏ gốc emSign có CA trung gian lộ khóa, GHSA-6q48-6c7w-9gw2). 23/10/2026: brotli 1.2.1 và brotlicffi 1.2.1.0 (22/10,
  vá lỗi ghi tràn bộ nhớ trong bộ giải nén, PYSEC-2026-4322, PYSEC-2026-4323, CRITICAL) — gói kéo theo của fontTools mà
  WeasyPrint dùng trong `svc-files`. 24/10/2026: pypdf 6.21.2 (21/10, vá GHSA-6c7f-9265-g8fw, GHSA-gmh7-3g9r-mjh5,
  GHSA-jr96-gvgh-j3r4, HIGH: PDF dị dạng làm chạy rất lâu); serialize-javascript 7.1.3 (22/10, GHSA-m5mm-p8h7-m29v)
  và fast-uri 3.1.9 (19/10, bốn GHSA mức LOW/MODERATE) — gói kéo theo khi dựng `apps/office`, chọn đúng bản vá chứ
  không lấy bản mới hơn (serialize-javascript 7.1.4 ra 23/10). 27/10/2026: cùng serialize-javascript 7.1.3 cho trang
  tài liệu (`website/`, #349). 28/10/2026: plugin oauth của DokuWiki, commit b709c33 (21/10) cho wiki nội bộ (#367):
  bản trước commit 3a1666c (18/10, "fix(security): sign the login cookie") không ký cookie đăng nhập, ai biết email
  của một người làm được cookie đăng nhập thay người đó; b709c33 thêm bản sửa kèm theo (bỏ cookie bị từ chối trước khi
  DokuWiki đọc). Tác giả không công bố mã GHSA, OSV-Scanner không đọc plugin tải trong Dockerfile.
  31/10/2026 (#461): pypdf 6.21.4 (28/10) trong `svc-files`, vá bảy GHSA công bố 30/10 (PDF cố tình làm hỏng gây
  vòng lặp vô hạn hay ngốn bộ nhớ); nuxt 4.6.3 (27/10, vá GHSA-9v7c-q64q-vv33 và ba GHSA của máy chủ phát triển) và
  node-forge 1.4.1 (27/10, mười một GHSA) cho `apps/office`, joi 17.13.9 (28/10, GHSA-4528-x5fx-h6hg) cho `website/`,
  đều chỉ chạy lúc dựng. Khóa npm sinh lại với `npm install --package-lock-only --before=<giờ ra bản vá>`, nên không
  gói kéo theo nào mới hơn bản vá.
- **Digest**: image bên thứ ba trong `docker-compose.yml`, các `Dockerfile` và image Playwright của `make e2e`
  ghi dạng `thẻ@sha256:…`. Docker kéo theo digest (bản đã chạy CI), thẻ chỉ để người đọc: thẻ bị đẩy lại
  (`postgres:16-alpine`, `python:3.13.16-slim`, `clamav/clamav:1.5.4` đã bị đẩy lại sau khi đội kéo) thì
  máy mới vẫn chạy đúng bản đã kiểm. Nâng phiên bản thì đổi cả hai: digest lấy bằng
  `docker buildx imagetools inspect <thẻ>` (dòng `Digest:`, là index đa nền tảng).
- **Phase**: thời điểm thành phần được đưa vào, theo [`docs/du-thi/ke-hoach-phat-trien.md`](docs/du-thi/ke-hoach-phat-trien.md).
  Thành phần đánh dấu *Could* chỉ được thêm nếu còn thời gian.
- **Copyleft (GPL, AGPL)**: chỉ dùng ở dạng **dịch vụ độc lập giao tiếp qua mạng**, không liên kết
  vào mã của Signet, nên giấy phép của chúng không lan sang Signet.

## Công cụ dựng và vận hành

| Thành phần | Phiên bản | Giấy phép | Vai trò | Cách nạp |
|---|---|---|---|---|
| [Docker Engine](https://docs.docker.com/engine/) | ≥ 24.0 | Apache-2.0 | Đóng gói và chạy container | Cài sẵn trên máy chủ |
| [Docker Compose v2](https://github.com/docker/compose) | ≥ 2.20 | Apache-2.0 | Điều phối đa dịch vụ | Plugin của Docker |
| [Caddy](https://caddyserver.com) | ≥ 2.6 | Apache-2.0 | Proxy TLS trên máy chủ: HTTPS, chứng thư Let's Encrypt tự gia hạn ([`docs/trien-khai.md`](docs/trien-khai.md)); không nằm trong Compose | Gói hệ thống của máy chủ (`apt install caddy`) |
| [Python](https://www.python.org) | ≥ 3.10 | PSF-2.0 | Chạy `make seed`, `make smoke` (chỉ thư viện chuẩn) | Gói hệ thống |
| [Node.js](https://nodejs.org) | 24.20.0 | MIT | Dựng giao diện thành trang tĩnh, cài gói npm của `app-ca-nhan`, `app-bang-tin`, `app-nghi-phep`, `app-tai-lieu-api` và phông của theme đăng nhập (chỉ ở bước dựng image); image `moc/keycloak-fonts` (#305) dựng trên image này, chạy một lần mỗi lần `up` để chép phông vào volume (chỉ `sh` và lệnh chép, không chạy Node); chạy test `apps/ca-nhan/tests`, `apps/bang-tin/tests`, `apps/nghi-phep/tests` | `node:24.20.0-slim` |
| [Playwright](https://playwright.dev) | 1.63.0 | Apache-2.0 | Kiểm thử trên trình duyệt thật — `make e2e`, `tests/e2e/` | `mcr.microsoft.com/playwright:v1.63.0-noble` |
| [axe-core](https://github.com/dequelabs/axe-core), @axe-core/playwright | 4.13.0 | MPL-2.0 | Kiểm trợ năng tự động theo WCAG 2.0, 2.1 mức A, AA trong e2e (`tests/e2e/tro-nang.spec.ts`, #246); chỉ dùng trong test, dùng nguyên bản, không vào gói phát hành | npm, `tests/e2e/package-lock.json` |
| [GNU Make](https://www.gnu.org/software/make/) | ≥ 4.0 | GPL-3.0+ | Điều phối lệnh (công cụ dựng, không liên kết vào sản phẩm) | Gói hệ thống |
| [Git](https://git-scm.com) | ≥ 2.30 | GPL-2.0 | Quản lý mã nguồn, sinh gói phát hành | Gói hệ thống |
| [uv](https://github.com/astral-sh/uv) | 0.12.19 | Apache-2.0 / MIT | Cài thư viện test theo băm và chạy `make test`, test `db/tests/` | Tệp chạy độc lập |
| [actionlint](https://github.com/rhysd/actionlint) | 1.7.12 | MIT | Kiểm cú pháp và lỗi thường gặp trong `.github/workflows/` (CI) | `rhysd/actionlint:1.7.12` |
| [gitleaks](https://github.com/gitleaks/gitleaks) | 8.30.1 | MIT | Quét bí mật lộ trong toàn bộ lịch sử commit (CI) | `ghcr.io/gitleaks/gitleaks:v8.30.1` |
| [OSV-Scanner](https://github.com/google/osv-scanner) | 2.6.0 | Apache-2.0 | Đối chiếu tệp khóa phụ thuộc với cơ sở dữ liệu lỗ hổng OSV (CI) | `ghcr.io/google/osv-scanner:v2.6.0` |
| [REUSE tool](https://github.com/fsfe/reuse-tool) | 5.0.2 | GPL-3.0-or-later | Kiểm mọi tệp đều có thông tin bản quyền và giấy phép theo chuẩn REUSE (`REUSE.toml`); chạy tay, chỉ đọc kho | `uvx --from reuse==5.0.2 reuse lint` |
| [Syft](https://github.com/anchore/syft) | 1.54.1 | Apache-2.0 | Sinh SBOM CycloneDX của cây mã nguồn (`make sbom`, CI, bản phát hành) từ tệp khóa npm, `requirements*.txt`, action CI; đầu vào của `make license-audit`; chỉ đọc kho, hỏi PyPI giấy phép gói Python | `ghcr.io/anchore/syft:v1.54.1` (image 06/10/2026) |
| [Chromium](https://www.chromium.org) | bản có `--headless=new` | BSD-3-Clause | Chỉ khi sửa sơ đồ kiến trúc của README: chụp từng khung SVG (`python3 scripts/so_do_kien_truc.py gif`); không thuộc sản phẩm, không chạy trong CI | Gói hệ thống |
| [FFmpeg](https://ffmpeg.org) | ≥ 6.0 | LGPL-2.1-or-later (GPL-2.0-or-later tùy bản dựng) | Chỉ khi sửa sơ đồ kiến trúc: ghép các khung thành GIF với một bảng màu chung; gọi như tiến trình độc lập | Gói hệ thống |

> **Ghi chú tương thích:** Make và Git là *công cụ dựng*, được gọi như tiến trình độc lập và không
> liên kết vào sản phẩm, nên giấy phép GPL của chúng không lan sang Signet. Cả hai đều là phần
> mềm nguồn mở — Signet không dùng bất kỳ công cụ nguồn đóng hay tự chế nào để dựng
> (tiêu chí PoF #4). CI trên GitHub Actions chỉ gọi lại đúng các lệnh `make` ở trên, nên dựng và kiểm
> thử trên máy riêng không cần GitHub.

### Trang tài liệu (`website/`)

Trang tài liệu (#308) dựng thẳng từ `docs/` và các README thành trang tĩnh, đăng lên GitHub Pages. Không thuộc sản
phẩm: bản cài của Signet không chạy, không phục vụ trang này. Gói npm nạp theo `website/package-lock.json`.

| Thành phần | Phiên bản | Giấy phép | Vai trò |
|---|---|---|---|
| [Docusaurus](https://docusaurus.io) (`@docusaurus/core`, `preset-classic`, `theme-mermaid`, `utils`) | 3.10.2 | MIT | Dựng trang từ tệp `.md` (đọc như CommonMark), mục lục, sơ đồ Mermaid |
| [React](https://react.dev), React DOM | 19.2.8 | MIT | Giao diện của trang (qua Docusaurus) |
| [Mermaid](https://mermaid.js.org) | 12.2.0 | MIT | Vẽ sơ đồ Mermaid của `docs/architecture.md` (qua `@docusaurus/theme-mermaid`) |
| [`@easyops-cn/docusaurus-search-local`](https://github.com/easyops-cn/docusaurus-search-local) | 0.55.3 | MIT | Tìm kiếm: chỉ mục dựng sẵn lúc build, tìm ngay trong trình duyệt (lunr, `lunr-languages` có tiếng Việt), không gọi dịch vụ ngoài |
| [Be Vietnam Pro](https://github.com/bettergui/BeVietnamPro) (`@fontsource/be-vietnam-pro`) | 5.3.0 | OFL-1.1 | Phông của trang, cùng phông giao diện ứng dụng; tự phục vụ, không gọi CDN. Bản dựng kèm `fonts/be-vietnam-pro/OFL.txt` lấy từ gói |

Quét `website/package-lock.json` ngày 30/10/2026: 1304 gói khác nhau. Ngoài danh sách giấy phép được nhận chỉ có bốn
gói, cùng bốn gói tệp khóa không ghi giấy phép; đều có ngoại lệ ghi lý do trong `.github/license-exceptions.json`
(`caniuse-lite` dùng chung với ứng dụng web, ghi ở mục Tầng 2):

| Gói | Giấy phép | Kéo theo bởi | Ghi chú |
|---|---|---|---|
| `argparse` | Python-2.0 | js-yaml | Bộ giấy phép dễ dãi của Python, SPDX ghi OSI phê duyệt. Chỉ chạy lúc dựng |
| `elkjs` | EPL-2.0 | Mermaid | Copyleft yếu theo từng tệp, OSI phê duyệt; dùng nguyên bản, không sửa, nên không lan sang mã của Signet. Nằm trong JS của trang; mã nguồn ở [kieler/elkjs](https://github.com/kieler/elkjs) |
| `robust-predicates` | Unlicense | d3-delaunay (qua Mermaid) | Đưa mã vào phạm vi công cộng, OSI phê duyệt |
| `mdn-data` (2.0.28, 2.0.30) | CC0-1.0 | css-tree (qua csso, svgo: nén CSS, SVG lúc dựng) | Dữ liệu cú pháp CSS của MDN. CC0 đưa tác phẩm vào phạm vi công cộng, không thuộc danh sách OSI. Chỉ đọc lúc dựng; ứng dụng web không còn gói này từ #322 |
| `eval`, `require-like`, `format`, `khroma` | MIT | Docusaurus, Mermaid | `package.json` không khai giấy phép hay khai bằng trường `licenses` kiểu cũ; tệp LICENSE trong gói là MIT |

`lunr-languages` (MPL-1.1, copyleft yếu) dùng nguyên bản cho tìm kiếm tiếng Việt. Gói cho chọn giấy phép thì Signet
dùng theo MIT: `opener` 1.5.2 (webpack-bundle-analyzer) và `path-is-inside` 1.0.2 (serve-handler) là `WTFPL OR MIT`,
`type-fest` 1.4.0 và 2.19.0 (boxen; chỉ có kiểu TypeScript) là `MIT OR CC0-1.0`; đều chỉ chạy lúc dựng hay xem thử
trang. WTFPL và CC0 không thuộc danh sách OSI nên lựa chọn này ghi ra đây.

Ba gói kéo theo có lỗ hổng mà gói cha còn ghim dải cũ được ép lên bản vá bằng `overrides` trong `website/package.json`
(#349); cả ba chỉ chạy lúc dựng hay ở máy chủ phát triển, không có trong trang đăng lên. Gói cha nâng dải thì bỏ mục
tương ứng.

| Gói | Bản ép | Gói cha ghim | Ghi chú |
|---|---|---|---|
| `serialize-javascript` | 7.1.3 | copy-webpack-plugin, css-minimizer-webpack-plugin: `^6` | Hai plugin gọi `serialize(obj)`, 7.x vẫn xuất hàm CommonJS đó. Ngoại lệ vá bảo mật, xem mục Cách đọc |
| `tinypool` | 2.1.2 | @docusaurus/core 3.10.2: `^1` | Docusaurus chỉ nạp khi bật `future.faster.ssgWorkerThreads`; trang không bật. Muốn bật thì dựng thử trước |
| `uuid` (chỉ dưới sockjs) | 11.1.1 | sockjs 0.3.24 (máy chủ của `npm start`): `^8.3.2` | sockjs gọi `require('uuid').v4`, 11.x còn bản CommonJS |

## Tầng 1 — Lõi nền tảng

| Thành phần | Phiên bản ghim | Giấy phép | Vai trò | Cách nạp | Phase |
|---|---|---|---|---|---|
| [Keycloak](https://www.keycloak.org) | 26.7.5 | Apache-2.0 | Định danh tập trung: SSO, MFA, vai trò người dùng | `quay.io/keycloak/keycloak:26.7.5`, nguyên bản; theme đăng nhập `signet` gắn từ repo, phông của theme do dịch vụ chạy một lần `keycloak-fonts` (`platform/keycloak/fonts/`, #305) chép từ gói npm vào volume | 1 |
| [Apache APISIX](https://apisix.apache.org) | 3.18.0 | Apache-2.0 | Cổng API: cửa duy nhất ra Internet, kiểm JWT tại biên, giới hạn tốc độ | `apache/apisix:3.18.0-debian`, dựng thành `moc/apisix` chỉ thêm tệp WAF (`platform/apisix/Dockerfile`, F3.15) | 1 |
| [PostgreSQL](https://www.postgresql.org) | 16 | PostgreSQL License | Cơ sở dữ liệu quan hệ chính (QĐ-002) | `postgres:16-alpine` | 1 |
| [Hasura GraphQL Engine (CE)](https://github.com/hasura/graphql-engine) | v2.51.0 | Apache-2.0 | Tự sinh API GraphQL, phân quyền cấp dòng, Actions, Event Triggers (luồng `core.app_events` tới webhook của ứng dụng cài bằng `moc app install`; `hasura-cli` có sẵn trong image áp metadata trộn) | `hasura/graphql-engine:v2.51.0-ce.cli-migrations-v3` | 1 |
| [Flowable (REST)](https://github.com/flowable/flowable-engine) | 8.0.0 | Apache-2.0 | Động cơ quy trình BPMN | `flowable/flowable-rest:8.0.0` | 1 |
| [SeaweedFS](https://github.com/seaweedfs/seaweedfs) | 4.48 | Apache-2.0 | Lưu trữ đối tượng chuẩn S3 | `chrislusf/seaweedfs:4.48` | 1 |
| [ClamAV](https://www.clamav.net) | 1.5.4 | GPL-2.0 | Quét mã độc tệp tải lên (dịch vụ độc lập) | `clamav/clamav:1.5.4` | 1 |
| [Meilisearch](https://github.com/meilisearch/meilisearch) (Community Edition) | v1.54.3 | MIT | Tìm kiếm toàn văn; chỉ mục đoạn `chunks` của trợ lý hỏi đáp (F4.2): tìm lai từ khóa + véc-tơ trong bản CE, embedder `userProvided` (véc-tơ do `svc-files` tính bằng Ollama, Meilisearch không gọi mô hình nào, không vào mạng `ai`) | `getmeili/meilisearch:v1.54.3` | 1 |
| [nginx (unprivileged)](https://github.com/nginx/docker-nginx-unprivileged) | 1.30.6 | BSD-2-Clause | Phục vụ trang tĩnh của `app-office`, `app-ca-nhan` sau APISIX | `nginxinc/nginx-unprivileged:1.30.6-alpine` | 1 |
| [Centrifugo](https://centrifugal.dev) | v6.9.7 | Apache-2.0 | Đẩy thông báo thời gian thực qua WebSocket | `centrifugo/centrifugo:v6.9.7` | 2 |

**Ghi chú:**

- Hasura: **bắt buộc dùng thẻ `-ce`**. Thẻ không có hậu tố `-ce` chứa thành phần Enterprise độc quyền.
- Meilisearch: chỉ dùng `getmeili/meilisearch`, bản community (MIT). Từ khi có Enterprise Edition, kho nguồn ghi
  `SPDX-License-Identifier: MIT AND BUSL-1.1`: phần BUSL-1.1 là các module `enterprise_edition`, chỉ biên dịch khi bật
  feature `enterprise` (`#[cfg(feature = "enterprise")]` trong `crates/meilisearch-types/src/lib.rs` và
  `crates/index-scheduler/src/scheduler/mod.rs`). Workflow `publish-docker-images.yml` của v1.54.3 dựng
  `getmeili/meilisearch` với edition `community`, không thêm `--features enterprise`; bản có cờ đó đăng riêng thành
  `getmeili/meilisearch-enterprise`, Signet không dùng. Kiểm 31/10/2026.
- Centrifugo: chỉ dùng bản mã nguồn mở. Bản PRO là phần mềm thương mại.
- Flowable: từ bản 7 chỉ còn bản REST, không có giao diện — phù hợp yêu cầu "lõi không giao diện".

## Tầng 2 — Ứng dụng web

Thư viện được cài qua `npm` với `package-lock.json`; phiên bản dưới đây là dòng chính đang dùng.

| Thành phần | Phiên bản | Giấy phép | Vai trò | Cách nạp | Phase |
|---|---|---|---|---|---|
| [Nuxt](https://nuxt.com) | 4.6.3 | MIT | Khung ứng dụng web (chế độ SPA, dựng thành trang tĩnh) | npm | 1 |
| [Vue](https://vuejs.org) | 3.5 | MIT | Thư viện giao diện (qua Nuxt) | npm | 1 |
| [oidc-client-ts](https://github.com/authts/oidc-client-ts) | 3.5.0 | Apache-2.0 | Đăng nhập OIDC (Authorization Code + PKCE) với Keycloak; `app-ca-nhan`, `app-bang-tin`, `app-nghi-phep`, `app-tai-lieu-api` dùng bản dựng sẵn cho trình duyệt của cùng gói (`dist/browser/oidc-client-ts.min.js`, đã gồm jwt-decode 4.0.0, MIT) — không thêm gói nào | npm | 1 |
| [Swagger UI](https://github.com/swagger-api/swagger-ui) (`swagger-ui-dist`) | 5.33.2 | Apache-2.0 | Trang Tài liệu API `/tai-lieu-api/` (`app-tai-lieu-api`, #357): đọc và gọi thử API lõi, API Văn phòng điện tử từ OpenAPI. Dùng nguyên `swagger-ui-bundle.js`, `swagger-ui.css` của gói, kèm `LICENSE`, `NOTICE`; bản dựng sẵn đã gồm các thư viện swagger-ui dùng: React, Redux, Immutable và đa số còn lại MIT, swagger-client Apache-2.0, DOMPurify MPL-2.0 hoặc Apache-2.0, sha.js, ieee754 BSD-3-Clause, zenscroll Unlicense (đều được OSI phê duyệt). Gói kéo theo `@scarf/scarf` 1.4.0 (Apache-2.0), chỉ có bước postinstall gửi số liệu sử dụng: cài bằng `npm ci --ignore-scripts` nên không chạy, không vào image. Trang không gọi CDN | npm, ghim trong `package-lock.json` của `apps/tai-lieu-api` | 3 |
| [vue-i18n](https://vue-i18n.intlify.dev) | 11.4.14 | MIT | Song ngữ Việt / Anh | npm | 1 |
| [Tailwind CSS](https://tailwindcss.com) (+ `@tailwindcss/vite`) | 4.3.3 | MIT | Định dạng giao diện | npm | 1 |
| [Ajv](https://ajv.js.org) | 8.20.0 | MIT | Biên dịch JSON Schema dùng chung (`schemas/`) thành mã kiểm form lúc dựng; chỉ dùng lúc dựng, không vào bundle | npm | 2 |
| [Apache ECharts](https://echarts.apache.org) | 6.1.0 | Apache-2.0 | Biểu đồ dashboard điều hành (F3.11), chỉ nạp biểu đồ cột, vẽ SVG. Kéo theo zrender 6.1.0 (BSD-3-Clause) và tslib 2.3.0 (0BSD), cùng nằm trong bundle | npm | 3 |
| [Be Vietnam Pro](https://github.com/bettergui/BeVietnamPro) (`@fontsource/be-vietnam-pro`) | 5.3.0 (phông 1.002) | OFL-1.1 | Phông giao diện của nhận diện Liền mạch (#116), đủ dấu tiếng Việt. Bốn độ đậm 400, 500, 600, 700, kiểu thường; gói chia mỗi độ đậm theo bộ ký tự latin, latin-ext, vietnamese (tệp woff2, woff, CSS có `unicode-range`), dùng nguyên như gói phát hành, kèm giấy phép của gói (`OFL.txt`); trình duyệt tải từ chính máy chủ, không gọi Google Fonts. Repo không chứa tệp phông nào (#305) | npm, ghim trong `package-lock.json` của `apps/office` (Vite đưa vào `/_nuxt/`), `apps/ca-nhan` và `platform/keycloak/fonts` (image `keycloak-fonts` chép vào volume `keycloak_fonts`, Keycloak gắn vào `themes/signet/login/resources/fonts/be-vietnam-pro/`) | 3 |

Thư viện gián tiếp (khoảng 650 gói, đều chỉ dùng lúc dựng; trang phát hành chỉ còn tệp JS/CSS tĩnh) mang
giấy phép MIT, ISC, Apache-2.0, BSD-2/3-Clause, BlueOak-1.0.0, MPL-2.0 hoặc 0BSD, đều được OSI phê duyệt. Quét
`package-lock.json` ngày 30/10/2026, ngoài danh sách đó chỉ có bốn gói dưới đây. Không gói nào trong số này nằm
trong trang phát hành (đã tìm trong thư mục trang tĩnh của image `app-office`).

| Gói | Giấy phép | Kéo theo bởi | Ghi chú |
|---|---|---|---|
| `caniuse-lite` | CC-BY-4.0 | browserslist, autoprefixer | Bảng dữ liệu trình duyệt nào hỗ trợ tính năng nào, chỉ đọc lúc dựng CSS. CC-BY-4.0 là giấy phép mở cho dữ liệu, không thuộc danh sách OSI (OSI chỉ duyệt giấy phép phần mềm) |
| `@speed-highlight/core` | CC0-1.0 | youch (trang báo lỗi của máy chủ phát triển Nuxt) | Chỉ chạy lúc phát triển |
| `node-forge` | BSD-3-Clause OR GPL-2.0 | listhen (máy chủ phát triển của Nuxt) | Gói cho chọn giấy phép, Signet dùng theo BSD-3-Clause. Chỉ chạy lúc phát triển |
| `type-fest` | MIT OR CC0-1.0 | dot-prop | Chỉ có kiểu TypeScript, Signet dùng theo MIT |

Quét lại: `python3 -c "import json,collections;p=json.load(open('apps/office/package-lock.json'))['packages'];print(collections.Counter(v.get('license') for k,v in p.items() if k))"`,
hoặc kiểm cả gói npm lẫn Python theo chính sách bằng `make sbom && make license-audit` (mục cuối).

**Ghi chú:** BTC gợi ý "Nuxt 3 / Vue 3". Signet dùng **Nuxt 4** (vẫn chạy trên Vue 3) vì đây là dòng
chính hiện tại; dòng Nuxt 3 chỉ còn nhận bản vá bảo trì. Dùng `vue-i18n` trực tiếp thay cho
`@nuxtjs/i18n`: ứng dụng chạy hoàn toàn trên trình duyệt, không cần định tuyến theo ngôn ngữ. Nhận thông báo từ
Centrifugo bằng WebSocket có sẵn của trình duyệt (`app/composables/useRealtime.ts`, theo giao thức JSON công khai
của Centrifugo), không dùng thư viện `centrifuge`: nó kéo theo `protobufjs` (có script chạy lúc cài) và hơn chục
gói khác, trong khi giao diện chỉ cần nhận tin.

## Dịch vụ tự viết (`services/`, `cli/`)

Thư viện Python cài qua `pip` với tệp khóa phiên bản.

| Thành phần | Phiên bản | Giấy phép | Vai trò | Cách nạp | Phase |
|---|---|---|---|---|---|
| [FastAPI](https://fastapi.tiangolo.com) | 0.143 | MIT | Khung viết `svc-files`, `svc-workflow`, `svc-ai` (kéo theo Starlette, Pydantic — BSD-3, MIT) | pip | 1 |
| [uvicorn](https://uvicorn.dev) | 0.54 | BSD-3-Clause | Máy chủ ASGI chạy các dịch vụ | pip | 1 |
| [httpx2](https://github.com/pydantic/httpx2) (+ httpcore2, truststore) | 2.13 | BSD-3-Clause (truststore: MIT) | Gọi Hasura, Flowable, Keycloak, Meilisearch | pip | 1 |
| [python-multipart](https://github.com/Kludex/python-multipart) | 0.0.32 | Apache-2.0 | Đọc tệp tải lên (`svc-files`) | pip | 1 |
| [boto3](https://github.com/boto/boto3) | 1.43 | Apache-2.0 | Gọi SeaweedFS qua giao thức S3 (`svc-files`) | pip | 1 |
| [PyJWT](https://github.com/jpadilla/pyjwt) (+ cryptography) | 2.15 · 50.0 | MIT (cryptography: Apache-2.0 / BSD) | Kiểm JWT Keycloak trong `svc-files` và ở API quy trình cho ứng dụng của `svc-workflow` (`/api/workflow`); mã hóa con trỏ trang tìm kiếm | pip | 1 |
| [WeasyPrint](https://weasyprint.org) (+ pydyf, tinycss2, cssselect2, tinyhtml5, webencodings) | 70.0 | BSD-3-Clause (tinyhtml5: MIT) | Dựng PDF văn bản đi đúng thể thức NĐ 30 từ khuôn HTML (`svc-files`) | pip | 2 |
| [fontTools](https://github.com/fonttools/fonttools) (+ Brotli, zopfli) | 4.66 | MIT (zopfli: Apache-2.0) | Nhúng và nén phông vào PDF (WeasyPrint kéo theo) | pip | 2 |
| [Pillow](https://python-pillow.github.io) | 13.0 | MIT-CMU (HPND) | Xử lý ảnh khi dựng PDF (WeasyPrint kéo theo). Từ F4.1 khai trực tiếp: chuẩn bị ảnh chụp, ảnh trang scan trước khi nhận dạng chữ (xoay theo EXIF, đổi xám, tăng tương phản, có trần điểm ảnh), chạy trong tiến trình con có giới hạn | pip | 2 |
| [Pyphen](https://github.com/Kozea/Pyphen) | 0.18 | GPL-2.0+ / LGPL-2.1+ / MPL-1.1, Signet dùng theo MPL-1.1 | Ngắt từ khi dàn chữ (WeasyPrint kéo theo), dùng nguyên bản không sửa | pip | 2 |
| [segno](https://github.com/heuer/segno) | 1.6 | BSD-3-Clause | Mã QR in trên văn bản phát hành, dẫn tới cổng xác thực | pip | 2 |
| [pypdf](https://github.com/py-pdf/pypdf) | 6.21.4 | BSD-3-Clause | Đọc lớp chữ của PDF đính kèm để tìm theo nội dung (`svc-files`, F2.7); F4.1 đọc chữ giữ bố cục (`extraction_mode="layout"`) và lấy ảnh nhúng của trang scan để nhận dạng chữ. Thuần Python, không kéo thêm gói | pip | 2 |
| [pytest](https://pytest.org) | 9.1 | MIT | Test đơn vị và tích hợp (chỉ khi phát triển) | pip | 1 |
| [jsonschema](https://github.com/python-jsonschema/jsonschema) (+ referencing, jsonschema-specifications, rpds-py, attrs) | 4.26 | MIT | `svc-workflow` kiểm lại dữ liệu form theo JSON Schema dùng chung (`schemas/`) | pip | 2 |
| [DuckDB](https://duckdb.org) | 1.5.6 | MIT | Nộp lưu hồ sơ (F3.8, `svc-files`): ghi bảng văn bản, giao việc, dòng thời gian thành Parquet (nén zstd) và đọc lại cho phòng đọc. Một wheel nhúng, không kéo thêm gói Python, không chạy máy chủ riêng | pip | 3 |
| [pyHanko](https://github.com/MatthiasValvekens/pyHanko) (+ pyhanko-certvalidator, asn1crypto, tzlocal, lxml, aiohttp và 7 gói con, oscrypto, uritools, certifi; tzdata chỉ trên Windows) | 0.37.0 · 0.32.1 | MIT (lxml BSD-3, aiohttp Apache-2.0/MIT, certifi MPL-2.0, aiohappyeyeballs PSF-2.0) | Ký số PAdES bản phát hành bằng khóa trong Transit, kiểm chữ ký (svc-files, F4.5, chỉ minh họa) | pip | 4 |
| [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/) (SDK, exporter OTLP/HTTP, instrumentation FastAPI và httpx2, kéo theo protobuf, requests, wrapt…) | 1.45.1 · 0.66b1 | Apache-2.0 (protobuf BSD-3, wrapt BSD-2, asgiref BSD-3, urllib3 MIT) | Truy vết phân tán (#364): `svc-files`, `svc-workflow` ghi span của yêu cầu APISIX đã chọn, che theo danh sách trắng rồi gửi Jaeger (`tracing.py`). Chỉ nạp khi `MOC_TRACE_RATIO` > 0 | pip | 4 |

**Ký số văn bản đi (F4.5, chỉ minh họa)** thêm một gói khai trực tiếp, pyHanko, cùng các gói nó kéo theo. Ghim bản mới
nhất phát hành trước 06/10/2026 (quy tắc hai tuần); ngày lấy từ PyPI (lần tải lên đầu tiên của bản đó), giấy phép từ
METADATA của gói. Không thêm image, gói npm hay route gateway.

| Gói | Bản | Phát hành | Giấy phép | Vì sao có |
|---|---|---|---|---|
| pyHanko | 0.37.0 | 31/08/2026 | MIT (kèm `pdf_utils/LICENSE.PyPDF2`, BSD-3) | Khai trực tiếp: dựng chữ ký CMS/PAdES, ghi PDF, kiểm chữ ký; 0.38.0 (17/10) quá mới |
| pyhanko-certvalidator | 0.32.1 | 10/09/2026 | MIT | pyHanko đòi `>=0.32.0,<0.33` — kiểm chuỗi chứng thư |
| asn1crypto | 1.5.1 | 15/03/2022 | MIT | pyHanko, certvalidator — cấu trúc ASN.1 |
| tzlocal | 5.4.4 | 29/06/2026 | MIT | pyHanko |
| lxml | 6.1.3 | 02/09/2026 | BSD-3-Clause | pyHanko (bắt buộc; Signet không dùng phần XMP) |
| aiohttp | 3.14.4 | 05/10/2026 | Apache-2.0 AND MIT | pyHanko, certvalidator đều bắt buộc; **không dùng tới**: không tải chứng thư, CRL, OCSP qua mạng, không TSA. 3.14.5 (11/10) quá mới |
| aiohappyeyeballs | 2.7.1 | 01/07/2026 | PSF-2.0 | aiohttp |
| aiosignal | 1.4.0 | 03/07/2025 | Apache-2.0 | aiohttp |
| attrs | 26.1.0 | 19/03/2026 | MIT | aiohttp |
| frozenlist | 1.8.0 | 06/10/2025 | Apache-2.0 | aiohttp |
| multidict | 6.9.1 | 21/09/2026 | Apache-2.0 | aiohttp, yarl. aiohttp 3.14.4 đòi `multidict<7.0`, nên không dùng 7.0.0 (26/09) |
| propcache | 0.5.4 | 16/09/2026 | Apache-2.0 | aiohttp, yarl |
| yarl | 1.25.1 | 15/09/2026 | Apache-2.0 | aiohttp |
| oscrypto | 1.3.0 | 18/03/2022 | MIT | certvalidator; **không nạp** lúc chạy (kiểm chữ ký dùng `cryptography`) |
| uritools | 6.1.3 | 23/07/2026 | MIT | certvalidator |
| certifi | 2026.10.19 | 20/10/2026 | MPL-2.0 | certvalidator (gói CA công cộng, Signet không dùng: chỉ tin CA nội bộ của két). Nâng từ 2026.7.22 theo ngoại lệ vá bảo mật: GHSA-6q48-6c7w-9gw2, gốc emSign có CA trung gian lộ khóa |
| tzdata | 2026.5 | 03/10/2026 | Apache-2.0 | tzlocal, chỉ trên Windows (`sys_platform == 'win32'`): có trong tệp khóa, không cài vào image |

Gói đã có trong khóa, giữ nguyên bản: `cryptography` 50.0.2 (pyHanko đòi ≥ 48), `idna` 3.20, `typing-extensions`
4.16.0. Image `svc-files` nặng thêm khoảng 15 MB (lxml, aiohttp; có wheel manylinux cho CPython 3.13). Khóa ký và CA
không phải gói: chúng nằm trong két OpenBao sẵn có (mount `transit`, `pki`).

**Truy vết phân tán (#364)** thêm bốn gói khai trực tiếp vào cả `svc-files` và `svc-workflow`, ghim đúng bản
(`==`). Gói nó kéo theo ghim bản mới nhất phát hành trước 13/10/2026 (`--exclude-newer-package`, quy tắc hai tuần);
ngày lấy từ PyPI, giấy phép từ METADATA. Tắt (mặc định) thì không gói nào được nạp lúc chạy.

| Gói | Bản | Phát hành | Giấy phép | Vì sao có |
|---|---|---|---|---|
| opentelemetry-sdk | 1.45.1 | 06/10/2026 | Apache-2.0 | Khai trực tiếp: TracerProvider, lấy mẫu theo cha, xử lý lô |
| opentelemetry-exporter-otlp-proto-http | 1.45.1 | 06/10/2026 | Apache-2.0 | Khai trực tiếp: gửi span tới Jaeger qua OTLP/HTTP |
| opentelemetry-instrumentation-fastapi | 0.66b1 | 06/10/2026 | Apache-2.0 | Khai trực tiếp: span cho mỗi route |
| opentelemetry-instrumentation-httpx | 0.66b1 | 06/10/2026 | Apache-2.0 | Khai trực tiếp: span cho lời gọi httpx2 (`HTTPX2ClientInstrumentor`) |
| opentelemetry-exporter-otlp-proto-common, opentelemetry-proto | 1.45.1 | 06/10/2026 | Apache-2.0 | Exporter: mã hóa span sang protobuf |
| opentelemetry-exporter-http-transport, opentelemetry-exporter-otlp-common | 0.66b1 | 06/10/2026 | Apache-2.0 | Exporter |
| opentelemetry-instrumentation, -instrumentation-asgi, -semantic-conventions, -util-http | 0.66b1 | 06/10/2026 | Apache-2.0 | Instrumentation FastAPI, httpx |
| asgiref | 3.12.1 | 14/07/2026 | BSD-3-Clause | Instrumentation ASGI; 3.13.0 (23/10) quá mới |
| protobuf | 7.36.2 | 17/09/2026 | BSD-3-Clause | opentelemetry-proto |
| googleapis-common-protos | 1.75.5 | 29/09/2026 | Apache-2.0 | Exporter; 1.76.0 (22/10) quá mới |
| requests | 2.34.2 | 14/05/2026 | Apache-2.0 | Exporter gửi HTTP bằng requests |
| charset-normalizer | 3.5.2 | 30/09/2026 | MIT | requests |
| urllib3 | 2.8.0 | 15/09/2026 | MIT | requests (`svc-files` đã có qua botocore) |
| certifi | 2026.10.19 | 20/10/2026 | MPL-2.0 | requests, chỉ mới ở `svc-workflow`; cùng bản và cùng ngoại lệ vá bảo mật như `svc-files` ở bảng trên. Span đi `http://jaeger:4318`, không dùng TLS |
| wrapt | 2.5.0 | 27/09/2026 | BSD-2-Clause | Instrumentation; 2.5.1 (14/10) quá mới |
| packaging | 26.3 | 04/08/2026 | Apache-2.0 OR BSD-2-Clause | Instrumentation |

`opentelemetry-api` 1.45.1 đã có trong khóa từ trước (FastAPI kéo theo), giữ nguyên.

Phiên bản cụ thể kèm băm nằm ở `requirements.txt` của từng dịch vụ; image dịch vụ dựng từ
`python:3.13.16-slim` (PSF-2.0). Image `svc-files` cài thêm từ kho Debian: Pango (LGPL-2.1+, nạp động lúc
chạy, không sửa), HarfBuzz (MIT) và phông Liberation 2.1 (SIL OFL 1.1) — cùng số đo với Times New Roman mà
NĐ 30/2020 quy định, có đủ dấu tiếng Việt; từ F4.1 thêm Tesseract cùng dữ liệu tiếng Việt (mục Trí tuệ nhân tạo),
gọi bằng dòng lệnh trong tiến trình con, không thêm gói Python. pip của image nền chỉ dùng lúc dựng: cài xong thư
viện thì gỡ khỏi image, cùng các bản sao thư viện nó mang theo (`pip/_vendor`: certifi, urllib3, msgpack, setuptools
bản cũ có lỗ hổng đã có bản sửa). Còn lại wheel pip trong `ensurepip/_bundled` của image nền (cùng các bản sao đó, nằm
trong tệp nén): không cài, không nạp lúc chạy, Trivy không tính.

Phần máy chủ của Bảng tin (`apps/bang-tin`) và máy chủ trang của Đơn nghỉ phép (`apps/nghi-phep`) dựng từ cùng image
`python:3.13.16-slim`, chỉ thư viện chuẩn, không cài gói nào. `moc app` đọc manifest bằng bộ đọc YAML tự viết, chỉ
thư viện chuẩn (`scripts/yaml_nho.py`): không thêm PyYAML vào thư mục cài; test so kết quả với PyYAML khi máy có sẵn.

## Vận hành và bốn nguyên lý thiết kế

| Thành phần | Phiên bản ghim | Giấy phép | Vai trò | Cách nạp | Phase |
|---|---|---|---|---|---|
| [OpenBao](https://openbao.org) | 2.7.1 | MPL-2.0 | Két bí mật và khóa (thay HashiCorp Vault): `svc-files`, `svc-workflow` lấy bí mật qua AppRole, static seal tự mở khóa, khóa transit cho tệp mã hóa; PKI nội bộ (CA minh họa) và khóa ký transit của từng đơn vị cho văn bản đi (F4.5). Image nguyên bản, chỉ thêm tệp cấu hình và script khởi động của đội (`platform/openbao/`) | `openbao/openbao:2.7.1` (image 01/10/2026) | 3 |
| [Scorpio Broker](https://github.com/ScorpioBroker/ScorpioBroker) | 6.0.2 | BSD-3-Clause | Context broker NGSI-LD cho dữ liệu cảm biến (F3.10, profile `iot`): bản sao số, lịch sử đo, subscription báo `svc-workflow` khi vượt ngưỡng. Bản java mặc định (không Kafka), không mở cổng ra ngoài | `scorpiobroker/all-in-one-runner:java-6.0.2` (image 03/07/2026) | 3 |
| [PostGIS](https://postgis.net) | 16-3.5 | GPL-2.0 | CSDL riêng của Scorpio (broker bắt buộc phần mở rộng `postgis`); dịch vụ độc lập, mạng riêng chỉ broker nối được, Signet không liên kết mã | `postgis/postgis:16-3.5-alpine`, ghim digest (image 31/08/2026) | 3 |
| [Prometheus](https://prometheus.io) | v3.15.0 | Apache-2.0 | Thu chỉ số của cổng API (plugin `prometheus` của APISIX) và trạng thái từng thành phần (`GET /metrics` của svc-files) mỗi 15 giây, tính luật cảnh báo (`promtool` cùng image kiểm luật trong CI); không mở cổng ra ngoài (F3.13) | `prom/prometheus:v3.15.0` | 3 |
| [Alertmanager](https://github.com/prometheus/alertmanager) | v0.34.1 | Apache-2.0 | Nhận cảnh báo đang bật của Prometheus, gom theo luật, chống gửi dồn rồi gọi `svc-workflow` (`POST /ops/alerts`, token riêng) để thành thông báo ở chuông của quản trị đơn vị, kèm email, webhook nếu đã bật kênh (#284, F3.13; `amtool` cùng image kiểm cấu hình trong CI); không mở cổng ra ngoài, không giữ trạng thái (tmpfs) | `prom/alertmanager:v0.34.1`, ghim digest (image 17/09/2026) | 3 |
| [Grafana (OSS)](https://github.com/grafana/grafana) | 13.2.3 | AGPL-3.0 | Hiển thị giám sát: bảng điều khiển nạp từ `platform/monitoring/` (dịch vụ độc lập, chỉ nghe 127.0.0.1, chỉ xem, không tài khoản) (F3.13) | `grafana/grafana:13.2.3` | 3 |
| [cloudflared](https://github.com/cloudflare/cloudflared) | 2026.10.0 | Apache-2.0 | Cloudflare Tunnel (F1.9, profile `tunnel`, tùy chọn): máy không có IP công khai ra Internet có HTTPS mà không mở cổng — gọi ra Cloudflare, chuyển yêu cầu vào APISIX qua mạng Docker; token để ngoài repo | `cloudflare/cloudflared:2026.10.0` (image 05/10/2026) | 1 |
| [Mailpit](https://mailpit.axllent.org) | v1.31.4 | MIT | Hộp thư thử cho thông báo email của `svc-workflow` (profile `mail`, chỉ để demo, kiểm thử): nhận mọi thư qua SMTP trong mạng Docker, không chuyển tiếp ra ngoài, giao diện web chỉ nghe 127.0.0.1; không hỏi bản mới. Cài thật thì gửi qua máy chủ thư của đơn vị | `axllent/mailpit:v1.31.4`, ghim digest (image 03/10/2026) | 4 |
| [restic](https://restic.net) | 0.19.1 | BSD-2-Clause | Sao lưu, khôi phục CSDL và tệp (`moc backup`): mã hóa, khử trùng lặp; chỉ chạy khi gọi, không mạng | `restic/restic:0.19.1` | 3 |
| [Vector](https://vector.dev) | 0.59.0 | MPL-2.0 | Thu log của 9 dịch vụ qua driver fluentd của Docker, che lần hai, gửi Parseable (F3.14, profile `logs`, tắt mặc định): chạy uid 65534, không gắn `docker.sock`, cổng nhận chỉ nghe 127.0.0.1; mật khẩu Parseable qua compose secret | `timberio/vector:0.59.0-distroless-static`, ghim digest (image 06/10/2026) | 3 |
| [Parseable](https://github.com/parseablehq/parseable) | 3.2.4 | AGPL-3.0 | Lưu và tra log tập trung (F3.14, profile `logs`): dịch vụ độc lập, chỉ nghe 127.0.0.1, chạy root nhưng bỏ mọi capability, basic auth (mật khẩu rỗng thì không mở cổng), giữ `MOC_LOGS_RETENTION_DAYS` ngày, tắt kiểm bản mới và gửi số liệu sử dụng | `quay.io/parseablehq/parseable:v3.2.4`, ghim digest (image 02/10/2026) | 3 |
| [Jaeger](https://www.jaegertracing.io) | 2.22.0 | Apache-2.0 | Nhận và hiện trace (#364, profile `trace`, tắt mặc định): span OTLP/HTTP của APISIX (plugin `opentelemetry`), `svc-files`, `svc-workflow`; giữ 10 000 trace trong RAM, giao diện chỉ nghe 127.0.0.1, không tài khoản; bỏ chuỗi truy vấn trước khi lưu (`platform/trace/jaeger.yaml`) | `jaegertracing/jaeger:2.22.0`, ghim digest (image 06/10/2026) | 4 |
| [DokuWiki](https://www.dokuwiki.org) | 2026-07-14c | GPL-2.0 | Wiki nội bộ ([H] Quản trị tri thức, #367, profile `wiki`, tắt mặc định): mỗi đơn vị một không gian `don-vi:<mã>` chỉ người của đơn vị đọc và sửa (`scripts/wiki.py` ghi danh sách quyền), đăng nhập chỉ qua Keycloak, không tài khoản quản trị; dịch vụ độc lập trong mạng `apps`, chạy uid 33, bỏ mọi capability, 256 MiB | `dokuwiki/dokuwiki:2026-07-14c`, ghim digest (DokuWiki phát hành 02/09/2026), bỏ `install.php`; volume `wiki_data` nằm trong `moc backup` | 4 |
| [Plugin oauth](https://github.com/cosmocode/dokuwiki-plugin-oauth) của DokuWiki | 2026-10-20 (commit b709c33) | GPL-2.0 (kèm lusitanian/oauth 0.8.11, MIT) | Đăng nhập DokuWiki bằng OAuth: tạo tài khoản ở lần đăng nhập đầu, lấy lại nhóm (đơn vị) mỗi lần đăng nhập. Ngoại lệ vá bảo mật, xem mục Cách đọc | Tải trong `platform/wiki/Dockerfile` theo commit, kiểm sha256, nguyên bản | 4 |
| [Plugin oauthgeneric](https://github.com/cosmocode/dokuwiki-plugin-oauthgeneric) của DokuWiki | 2025-10-02 (commit b5a5653) | GPL-2.0 | Dịch vụ OAuth chung cho plugin oauth: nối client `wiki` của Keycloak, đọc tên, email, nhóm từ userinfo | Như plugin oauth | 4 |
| [Node-RED](https://nodered.org) | 5.0.8 | Apache-2.0 | Tự động hóa không sửa mã (#366, profile `tu-dong`, tắt mặc định): trình soạn flow ở `/tu-dong/`, đăng nhập chỉ qua Keycloak, chỉ vai trò `operator` của client `tu-dong` (`scripts/tu_dong.py`); không node `exec`, không cài node từ trình soạn; dịch vụ độc lập trong mạng `apps`, rootfs chỉ đọc, bỏ mọi capability, 256 MiB | `nodered/node-red:5.0.8-minimal`, ghim digest (phát hành 08/10/2026), cộng `platform/tu-dong/settings.js`; volume `tu_dong_data` nằm trong `moc backup` | 4 |
| [openid-client](https://github.com/panva/openid-client) (kèm [jose](https://github.com/panva/jose) 6.2.12, [oauth4webapi](https://github.com/panva/oauth4webapi) 3.8.8) | 6.8.8 | MIT | Passport strategy cho đăng nhập Keycloak của Node-RED: luồng code + PKCE, kiểm chữ ký, `iss`, `aud` của ID token | `npm ci --omit=dev --ignore-scripts` theo `platform/tu-dong/package-lock.json` (sha512), cả ba phát hành 05/09/2026 | 4 |
| [Coraza](https://coraza.io) + [OWASP CRS](https://coreruleset.org) | Coraza v3.3.3, CRS v4.14.0 (trong coraza-proxy-wasm 0.6.0) | Apache-2.0 | Tường lửa ứng dụng web ở cổng API (F3.15): mọi yêu cầu qua CRS paranoia 1 trước khi kiểm token, tải tấn công → 403; nội dung tệp vẫn do ClamAV soi | `ghcr.io/corazawaf/coraza-proxy-wasm:0.6.0` (phát hành 06/07/2025), ghim digest, kiểm sha256 tệp `.wasm`; APISIX nạp bằng `wasm.plugins` | 3 |

**Ghi chú:**

- Grafana: chỉ dùng `grafana/grafana` (AGPL-3.0). `grafana/grafana-enterprise` là bản độc quyền.
- Scorpio Broker: compose ghim `java-6.0.2`; thẻ này chỉ có trên Docker Hub (03/07/2026), GitHub chưa có thẻ tương ứng,
  nên giấy phép đối chiếu với nhánh `development-quarkus`, nơi phát triển dòng 6.x: BSD-3-Clause ở bản phát hành 6.0.1
  (commit `5967583`) và ở đầu nhánh lúc kiểm 31/10/2026. Nhánh `master` cũ (mã 2019) còn BSD-4-Clause, có điều khoản
  quảng cáo, không thuộc danh sách OSI; Signet không dùng mã nhánh đó. Profile `iot` tắt mặc định.
- Parseable: bản 3.x chỉ phát hành trên Quay (`quay.io/parseablehq/parseable`); `parseable/parseable` trên Docker Hub
  dừng ở 2.8.0 (29/05/2026).
- Marquez: bản phát hành gần nhất là 0.51.1 (03/2025), mã nguồn vẫn có commit năm 2026 nhưng nhịp chậm.
  Theo dõi trong Phase 3; nếu gặp lỗi chặn thì chuyển sang chỉ lưu sự kiện OpenLineage vào PostgreSQL. F3.9 đã làm
  theo hướng đó (`core.lineage_events`): tránh thêm máy chủ Java và CSDL riêng (~1 GB RAM) cho một job mỗi giờ.
- Coraza: coraza-proxy-wasm 0.6.0 là bản phát hành mới nhất và nhánh `main` vẫn dùng Coraza v3.3.3 (20/03/2025), nên
  không có bản WebAssembly nào mang Coraza đã vá (3.8.1). 3.3.3 có 12 GHSA công bố 02/10/2026: hai mức high áp dụng
  ở Signet có biện pháp ở cổng (JSON lồng sâu bị chặn trước WAF; quá 1000 tham số thì chặn), các lỗi lẩn WAF mức
  medium ghi ở [`platform/apisix/README.md`](platform/apisix/README.md), mục WAF. Gói Go biên dịch trong tệp `.wasm`
  (proxy-wasm-go-sdk, gjson, libinjection-go, go-re2, aho-corasick…) là Apache-2.0, MIT, BSD-3-Clause. SBOM và
  OSV-Scanner không đọc tệp `.wasm`: lỗ hổng mới của Coraza phải theo dõi tay (GitHub Security Advisories của
  `corazawaf/coraza`). Khi có bản phát hành mang Coraza ≥ 3.8.1 thì đổi digest và băm trong Dockerfile; hướng thay
  nếu cần bản vá sớm hơn: coraza-caddy (Coraza 3.8.1) thành một container đứng trước APISIX — so sánh ở README đó.
- DokuWiki: thẻ `2026-07-14c` của image được đẩy lại khi dựng lại; digest đang ghim là bản đẩy 24/10/2026, mã DokuWiki
  vẫn của bản phát hành 02/09/2026. Hai plugin của CosmoCode (nhóm làm DokuWiki) không có bản phát hành, chỉ có commit
  và ngày trong `plugin.info.txt`: ghim commit và sha256 của tệp nén. Plugin oauth mang sẵn thư viện lusitanian/oauth
  0.8.11 (MIT, 14/02/2018, không còn bản mới) trong `vendor/`. Tệp duy nhất của Signet mà DokuWiki đọc là
  `platform/wiki/signet.protected.php` (chỉ gán cấu hình); wiki nói chuyện với Signet qua HTTP (OpenID Connect
  qua APISIX), không liên kết mã.

## Trí tuệ nhân tạo

| Thành phần | Phiên bản ghim | Giấy phép | Vai trò | Cách nạp | Phase |
|---|---|---|---|---|---|
| [Ollama](https://ollama.com) | 0.35.1 | MIT | Chạy mô hình ngôn ngữ cục bộ (profile `ai`, tùy chọn): viết trích yếu khi quy tắc không ra trích yếu tin cậy (F4.1); nhúng đoạn văn bản và câu hỏi (`/api/embed`), viết câu trả lời có trích dẫn cho trợ lý hỏi đáp (F4.2) — giữ cùng lúc mô hình viết và mô hình nhúng (`OLLAMA_MAX_LOADED_MODELS=2`); mạng nội bộ riêng, không mở cổng, tắt tính năng đám mây (`OLLAMA_NO_CLOUD`). Bản ổn định mới nhất trước 06/10/2026, có `think` và `format` theo JSON Schema. Chỉ chạy CPU: image chính thức kèm thư viện CUDA của NVIDIA (cuBLAS, cudart; giấy phép riêng của NVIDIA, không phải nguồn mở) cho máy có GPU, Signet không cấp GPU cho `ollama` nên không dùng chúng (#452) | `ollama/ollama:0.35.1@sha256:292ee7945dfc3d5840a181f3ab86fedb1e66703e02c8af98b50f4da56b7e278c` (image 02/10/2026) | 4 |
| [Qwen3-1.7B](https://huggingface.co/Qwen/Qwen3-1.7B) | `qwen3:1.7b` (Q4_K_M, khoảng 1,36 GB) | Apache-2.0 (đã kiểm model card và tệp LICENSE trên Hugging Face của đúng cỡ 1.7B; cỡ 4B cũng Apache-2.0) | Trọng số mô hình viết trích yếu (F4.1) và câu trả lời có trích dẫn của trợ lý hỏi đáp (F4.2, chỉ từ các đoạn đã lọc theo quyền người hỏi; `svc-files` kiểm trích dẫn, con số trước khi trả). Phát hành 04/2025. Máy đủ nhanh thì đổi `MOC_AI_MODEL=qwen3:4b` hoặc chỉ riêng trợ lý `MOC_ASK_MODEL=qwen3:4b` | Tải một lần qua Ollama (`make ai-model`, profile `ai-pull`); bản kê `sha256:8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7` — so với `ollama list` | 4 |
| [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | `qwen3-embedding:0.6b` (Q8_0, 639 MB, 1024 chiều, ngữ cảnh 32K) | Apache-2.0 (khai trong model card `Qwen/Qwen3-Embedding-0.6B` và bản GGUF chính thức trên Hugging Face; kho không kèm tệp LICENSE, bản kê Ollama không có lớp giấy phép) | Mô hình nhúng đoạn văn bản và câu hỏi cho tìm theo nghĩa của trợ lý hỏi đáp (F4.2, `MOC_AI_EMBED_MODEL`; câu hỏi mang tiền tố `Instruct: …\nQuery: …`). Phát hành 05/06/2025 (bài báo arXiv 2506.05176); có trong thư viện Ollama từ 23/09/2025, Ollama hỗ trợ từ 0.12.1. MMTEB đa ngữ: trung bình 64,33, truy xuất 64,64 (bge-m3: 59,56 / 54,60 — bảng trong model card). Đổi `MOC_AI_EMBED_MODEL=bge-m3` được, cùng 1024 chiều, `svc-files` tự nhúng lại | Tải một lần qua Ollama (`make ai-model`, profile `ai-pull`); bản kê `sha256:ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d` — so với `ollama list` | 4 |
| [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) (+ dữ liệu `vie`) | 5.5.0 (gói Debian trixie `tesseract-ocr` 5.5.0-1+b1, `tesseract-ocr-vie` 1:4.1.0-2) | Apache-2.0 | Nhận dạng chữ trên công văn scan, ảnh chụp khi tiếp nhận (F4.1, `svc-files`). Dữ liệu `vie` là bản tessdata_fast 4.1.0 (mô hình LSTM nhanh). Phiên bản gói lấy từ kho Debian theo image gốc — kiểm lại bằng `dpkg-query -W 'tesseract-ocr*'` trong image `svc-files` sau khi dựng | Gói hệ thống (apt) | 4 |

**Ghi chú:** trọng số mô hình có giấy phép riêng, tách khỏi giấy phép của Ollama. Trước khi dùng phải
đọc giấy phép trên model card **của đúng kích cỡ đã chọn**. Không dùng Llama hoặc Gemma vì giấy phép
trọng số không được OSI phê duyệt. F4.1 đã kiểm Qwen3-1.7B và Qwen3-4B (Apache-2.0); lớp giấy phép trong bản
kê `qwen3:1.7b` của thư viện Ollama cũng là văn bản Apache-2.0. Ollama ghim theo ngày image lên Docker Hub
(02/10/2026): trang GitHub ghi ngày bản thử nghiệm đầu tiên nên sớm hơn ngày phát hành thật. F4.2 đã kiểm
Qwen3-Embedding-0.6B: model card (`license: apache-2.0`) của `Qwen/Qwen3-Embedding-0.6B` và của bản GGUF chính thức
`Qwen/Qwen3-Embedding-0.6B-GGUF`; khác `qwen3:1.7b`, bản kê `qwen3-embedding:0.6b` của thư viện Ollama chỉ có lớp
trọng số (bản kê và lớp cấu hình `Q8_0`, họ `qwen3`, 595,78M tham số đã đối chiếu với registry của Ollama). Trợ lý hỏi
đáp không thêm image, không thêm gói Python: đường ống truy xuất, lọc quyền, trích dẫn, kiểm câu trả lời tự viết
trong `svc-files` (httpx2 sẵn có), kho véc-tơ là Meilisearch đã chạy.

**Mở trọng số, chưa phải AI nguồn mở.** Qwen3 công bố trọng số theo Apache-2.0 nhưng không công bố mã huấn luyện và
thông tin đủ chi tiết về dữ liệu huấn luyện, nên theo Định nghĩa AI nguồn mở của OSI (OSAID 1.0) đây là mô hình mở
trọng số. Tài liệu của Signet gọi là "mô hình mở trọng số (Apache-2.0)", không gọi là "AI nguồn mở".

**F4.3 không thêm phụ thuộc** — không gói Python, gói npm, image hay route gateway nào. Tác tử gợi ý giao việc
`moc-assigner` (`svc-workflow`) dùng lại: phần truy xuất của trợ lý hỏi đáp trong `svc-files` (chỉ mục đoạn `chunks`
trên Meilisearch v1.54.3, tìm lai với Qwen3-Embedding qua Ollama khi bật profile `ai`, chỉ từ khóa khi không), gọi qua
route nội bộ bằng httpx2 sẵn có; Pydantic cho thân yêu cầu; Flowable REST 8.0.0 cho nhánh song song (`parallelGateway`,
boundary timer — BPMN chuẩn) và việc giao ra ngoài (external worker, như nhắc hạn); bỏ phiếu và hạn đề xuất tính bằng
thư viện chuẩn Python (`statistics.median_low`). Không mô hình nào chọn đơn vị: CI không bật profile `ai` vẫn chạy đủ.

**F4.4 không thêm phụ thuộc** — không gói Python, gói npm, image hay route gateway nào. Bộ che thông tin cá nhân
`pii.py` (`svc-files`, bản chép y hệt trong `svc-workflow`) chỉ dùng thư viện chuẩn Python (`re`, `unicodedata`,
`logging`); test dùng uvicorn 0.54.0 (`AccessFormatter` thật) và pypdf (đọc kho mẫu) sẵn có. Nhật ký truy cập
bỏ chuỗi truy vấn bằng khóa cấu hình sẵn có của APISIX 3.18.0 (`access_log_format`, `http_configuration_snippet`) và
`map`, `log_format` của nginx trong image giao diện; giao diện chỉ thêm một biểu thức chính quy nhận nhãn che.

## Thành phần đã cân nhắc nhưng không dùng

| Thành phần | Lý do | Thay bằng |
|---|---|---|
| HashiCorp Vault | BUSL-1.1 từ v1.15 (08/2023) — không phải OSI | OpenBao |
| Chạy mô hình bằng GPU NVIDIA (CUDA) | Bắt buộc driver NVIDIA và thư viện CUDA (cuBLAS, cudart), đều là phần mềm đóng; với card NVIDIA không có đường GPU nào hoàn toàn nguồn mở. Đã thêm ở #443, gỡ ở #452 (30/10/2026) | Ollama chạy trên CPU |
| n8n | Sustainable Use License — không phải OSI | Vòng nền trong `svc-files` cho việc chạy định kỳ; Node-RED cho tự động hóa (#366, dòng cuối bảng) |
| Redpanda | BSL-1.1 — không phải OSI | Chưa thay: sự kiện ghi vào bảng PostgreSQL trong cùng giao dịch (`office.document_events`, `core.lineage_events`, hộp thư đi `core.notification_deliveries`), Centrifugo đẩy tới trình duyệt; trục sự kiện dự kiến dùng Hasura Event Triggers, chưa khai ([`ROADMAP.md`](ROADMAP.md)) |
| MongoDB | SSPL-1.0 — không phải OSI | PostgreSQL |
| immudb | BUSL-1.1 từ 12/2023 — không phải OSI | Sổ kiểm toán chuỗi băm trong PostgreSQL |
| FIWARE Orion / Orion-LD | Bắt buộc MongoDB (SSPL); Orion cổ điển không hỗ trợ NGSI-LD | Scorpio Broker |
| MinIO | Đã ngừng phát triển, không còn phát hành image | SeaweedFS |
| Directus | BSL-1.1 / MSCL — không phải OSI | Hasura + PostgreSQL |
| Metabase | Bản mã nguồn mở không hỗ trợ đăng nhập OIDC (Keycloak); đọc thẳng CSDL, bỏ qua phân quyền thuê ước | Dashboard trong ứng dụng (ECharts) |
| bpmn-js | MIT kèm điều khoản bắt buộc giữ watermark — không thuộc danh sách OSI | Hiển thị tiến trình do đội tự vẽ |
| PaddleOCR, VietOCR | Kéo theo PaddlePaddle hoặc PyTorch (hàng trăm MB), image và CI chậm hẳn; Tesseract đủ cho công văn in | Tesseract + quy tắc bố cục NĐ 30 (F4.1) |
| Qdrant (Apache-2.0) | Thêm một image và RAM; kho véc-tơ thứ hai phải đồng bộ thuộc tính quyền với CSDL; không tìm theo từ khóa tiếng Việt nên khi không có mô hình (CI) vẫn cần đường tìm khác. Meilisearch đã chạy, đã có tìm lai từ khóa + véc-tơ trong bản CE | Chỉ mục đoạn `chunks` trong Meilisearch (F4.2) |
| LlamaIndex (MIT) | `llama-index-core` 0.14 kéo 28 gói phụ thuộc trực tiếp (numpy, SQLAlchemy, NLTK, tiktoken…); NLTK, tiktoken tải dữ liệu từ Internet lúc chạy, mà mạng `ai` không ra Internet; không làm hộ phần lọc quyền của Signet, trích dẫn và kiểm câu trả lời — đúng phần phải tự viết | Đường ống tự viết trong `svc-files` (`svc_files/assist/`, F4.2) |
| bge-m3 (MIT, 01/2024) | Phương án thay, không phải bị loại: `bge-m3:567m` F16 khoảng 1,2 GB (gấp đôi RAM), điểm truy xuất đa ngữ MMTEB thấp hơn (54,60 so với 64,64). Dùng được bằng `MOC_AI_EMBED_MODEL=bge-m3`, cùng 1024 chiều, không cần tiền tố câu hỏi | Qwen3-Embedding-0.6B (F4.2) |
| scikit-learn (BSD-3-Clause) | Thêm gói (kéo numpy, SciPy) vào `svc-workflow` cho một bộ phân loại học từ vài chục văn bản đã giao; phải huấn luyện lại mỗi khi thêm đơn vị hay có văn bản mới, và khó chỉ ra vì sao chọn đơn vị đó | Bỏ phiếu theo các văn bản tương tự đã giao (kNN có trọng số trên phần truy xuất của F4.2), căn cứ hiện kèm gợi ý (F4.3) |
| Mô hình sinh (Qwen3) chọn đơn vị chủ trì | 15–45 giây CPU mỗi văn bản; CI không có mô hình; không giải thích được vì sao chọn đơn vị đó, lại có thể bịa đơn vị không có lãnh đạo phòng | Bỏ phiếu như trên — không cần mô hình, tốt dần khi có thêm văn bản đã giao (F4.3) |
| Cấp khóa ký bằng `pki/issue` của OpenBao | Két sinh khóa rồi trả cả khóa riêng: khóa nằm trong RAM và đĩa của `svc-files`, dịch vụ phải tự giữ kín | Khóa ký trong Transit, không rời két; chứng thư qua `pki/sign` cho CSR do Transit ký (F4.5) |
| Dịch vụ dấu thời gian TSA (PAdES B-T) | Cần một dịch vụ TSA ngoài; demo phải chạy không có mạng ngoài | PAdES B-B, giờ ký tự khai, CLI và cổng xác thực ghi rõ (F4.5) |
| Trình kiểm PAdES bằng JavaScript ở cổng xác thực | Thêm một thư viện lớn vào trang công khai, trong khi trình duyệt chỉ cần băm tệp | Trình duyệt băm như F2.13; kiểm mật mã đầy đủ bằng pyHanko trong `svc-files` (`python -m svc_files.signing verify`) (F4.5) |
| Presidio (MIT) | `presidio-analyzer` 2.2 bắt buộc kéo spaCy, numpy, phonenumbers, tldextract, regex, pydantic, PyYAML, click; bộ máy NLP spaCy cần tải thêm mô hình ngôn ngữ (không có pipeline tiếng Việt chính thức); bộ nhận dạng dựng sẵn không có định dạng Việt Nam (CCCD, đầu số di động, số tài khoản) nên vẫn phải tự viết regex | `pii.py` tự viết, chỉ thư viện chuẩn, nhận theo cấu trúc (mã tỉnh, đầu số đã cấp), chạy được trong bộ lọc nhật ký (F4.4) |
| phonenumbers (Apache-2.0) | Metadata lớn phải ghim và cập nhật theo bản phát hành; không biết CCCD, CMND hay số tài khoản; luật số di động Việt Nam chỉ là "10 số, đầu số đã cấp" | Danh sách `MOBILE_PREFIXES` có ngày và nguồn trong `pii.py` (F4.4) |
| Kestra (Apache-2.0) | Nộp lưu nóng → lạnh (F3.8) là một job mỗi giờ: không đáng thêm một máy chủ Java ~1 GB RAM | Vòng nền trong `svc-files` |
| n8n, Windmill, Activepieces, Kestra cho tự động hóa (#366) | n8n theo Sustainable Use License (không phải OSI); đăng nhập SSO của Kestra, Activepieces chỉ ở bản trả phí, Windmill bản Community tối đa 10 người dùng SSO; Kestra đòi tối thiểu 4 GiB RAM | Node-RED (Apache-2.0), profile `tu-dong` |
| Marquez (Apache-2.0) | Thêm một máy chủ chỉ để lưu và xem phả hệ, trong khi Signet tự lưu và hiển thị phả hệ | Bảng `core.lineage_events` và trang phả hệ (F3.9); đặt `MOC_OPENLINEAGE_URL` thì `svc-files` gửi sự kiện sang Marquez có sẵn |
| openlineage-python (Apache-2.0) | Chỉ cần dựng sự kiện OpenLineage 2-0-2, thư viện chuẩn đủ | `svc_files.lineage` (thư viện chuẩn) |
| Typer (MIT) | Lệnh `moc` đủ dùng với thư viện chuẩn, không cần thêm gói | `argparse` |
| Gotenberg (MIT) | Thêm một image chỉ để sinh PDF | WeasyPrint trong `svc-files` dựng PDF văn bản đi |

## Kiểm tra tương thích giấy phép

Giấy phép được chấp nhận trong Signet (tương thích với Apache-2.0 ở vai trò dịch vụ độc lập):

- ✅ Apache-2.0, MIT, MIT-0, BSD-2/3-Clause, 0BSD, ISC, BlueOak-1.0.0, PostgreSQL License, MPL-2.0 (giấy phép dễ dãi
  được OSI phê duyệt) và PSF-2.0 (giấy phép dễ dãi của chính Python và image `python`; aiohappyeyeballs qua aiohttp
  của pyHanko ở F4.5, typing-extensions qua Pydantic, FastAPI). SPDX đánh dấu OSI phê duyệt cho Python-2.0, bộ giấy
  phép của Python mở đầu bằng PSF-2.0, chứ không cho riêng PSF-2.0.
- ✅ MIT-CMU chỉ cho Pillow (ngoại lệ có lý do): một dạng HPND, dễ dãi, chỉ đòi giữ thông báo bản quyền; SPDX đánh dấu
  OSI phê duyệt cho HPND nhưng chưa cho riêng MIT-CMU.
- ✅ MPL-1.1, LGPL-2.1+, SIL OFL 1.1 cho thư viện và phông dùng nguyên bản, không sửa: Pyphen (chọn MPL-1.1
  trong ba giấy phép), Pango (nạp động), phông Liberation, phông giao diện Be Vietnam Pro (gói npm
  `@fontsource/be-vietnam-pro`, không nằm trong repo; mỗi bản dựng kèm `OFL.txt` lấy từ gói), `lunr-languages` của
  trang tài liệu.
- ✅ Python-2.0, Unlicense (OSI phê duyệt) và EPL-2.0 (copyleft yếu, dùng nguyên bản) chỉ cho gói của trang tài liệu
  `website/`, qua ngoại lệ có lý do: `argparse`, `robust-predicates`, `elkjs` (mục Trang tài liệu).
- ✅ CC-BY-4.0, CC0-1.0 chỉ cho dữ liệu và công cụ chạy lúc dựng, lúc phát triển, không vào sản phẩm: `caniuse-lite`,
  `@speed-highlight/core` (mục Tầng 2), `mdn-data` (mục Trang tài liệu). Gói cho chọn giấy phép thì chọn giấy phép
  OSI: `node-forge` theo BSD-3-Clause; `type-fest`, `opener`, `path-is-inside` theo MIT.
- ⚠️ GPL-2.0/3.0, AGPL-3.0 — chấp nhận được khi chạy như **dịch vụ độc lập** giao tiếp qua mạng,
  không liên kết mã. Hiện gồm: ClamAV, PostGIS, DokuWiki cùng hai plugin oauth, oauthgeneric (GPL-2.0), Grafana và
  Parseable (AGPL-3.0).
- ❌ Mọi giấy phép không được OSI phê duyệt, giấy phép "source-available" (BUSL, SSPL, Elastic
  License, Sustainable Use License), hoặc bất kỳ thành phần nguồn đóng nào, kể cả thành phần tùy chọn (#452).
- Dữ liệu công khai trong `seed/du-lieu-mo/` (nguồn A #424, nguồn B #427) không mang giấy phép nguồn mở: đó là văn bản
  nhà nước và tin thời sự thuần túy, không thuộc phạm vi bảo hộ quyền tác giả theo Điều 15 Luật Sở hữu trí tuệ.
  `REUSE.toml` khai là `LicenseRef-VN-SHTT-Dieu-15`; nguồn và căn cứ dùng lại từng tệp ở `manifest.json` cùng thư mục.
- Logo các dự án trong sơ đồ kiến trúc (`docs/anh/logo/`, ảnh `docs/anh/kien-truc-tong-the*.gif`) không phải thành phần
  phần mềm: là nhãn hiệu của chủ sở hữu, chỉ dùng để nhận diện phần mềm nguồn mở mà Signet sử dụng hoặc gửi thông báo
  tới, không thuộc giấy phép Apache-2.0 của Signet; khai riêng trong `REUSE.toml` (`LicenseRef-Logos`), nguồn ghi ở
  `docs/anh/logo/NGUON.md`.

**Kiểm tự động, cả gói gián tiếp.** `make sbom` sinh SBOM CycloneDX của cây mã nguồn bằng Syft (tệp khóa npm kể cả gói
chỉ dùng lúc dựng, `requirements*.txt`, action trong `.github/workflows/`; giấy phép gói Python hỏi PyPI vì
`requirements.txt` không ghi). `make license-audit` (`scripts/license_audit.py`) xét từng gói theo đúng danh sách trên:
biểu thức `A OR B` qua khi một nhánh được nhận, `A AND B` phải qua cả hai; copyleft yếu qua nhưng được liệt kê riêng;
GPL, AGPL, giấy phép khác và giấy phép chưa rõ thì không qua, trừ khi có ngoại lệ ghi lý do trong
`.github/license-exceptions.json`. Ngoại lệ cho gói ngoài danh sách phải trùng giấy phép SBOM ghi (gói đổi giấy phép thì
ngoại lệ hết tác dụng); ngoại lệ cho gói SBOM không rõ giấy phép ghi giấy phép đội đã đọc trong gói và phiên bản đã
đọc. CI (job "Giấy phép (PoF #2)") chạy hai lệnh này trên mọi pull request; từ bản sau 1.0.0, mỗi bản phát hành kèm
SBOM `signet-X.Y.Z.cdx.json`.
Syft không đọc `Dockerfile`, `docker-compose.yml`: image thượng nguồn và giấy phép của chúng là các bảng ở trên.

Lần quét 30/10/2026 trên `develop` (7e2bbdb, CI run 40992435806, Syft 1.54.1): 1899 gói khác nhau — npm 1799, Python
92, action CI 8 — đều đạt. Số gói npm tăng từ 690 (lần quét 23/10) chủ yếu vì từ 27/10 quét cả trang tài liệu
`website/` (1304 gói, chỉ dùng lúc dựng). 32 gói qua nhờ ngoại lệ: 4 gói npm dữ liệu và công cụ dựng mang CC-BY-4.0,
CC0-1.0 (`mdn-data` có hai bản), 7 gói npm của trang tài liệu (mục Trang tài liệu), Pillow (MIT-CMU), 12 gói Python mà
PyPI chỉ khai giấy phép bằng classifier hay chữ tự do (WeasyPrint và các gói nó kéo theo, segno, DuckDB, protobuf,
python-dateutil, colorama — giấy phép đọc từ tệp LICENSE trong wheel) và 8 action CI (giấy phép đọc ở đúng thẻ đã
ghim). Hai gói PSF-2.0 (aiohappyeyeballs, typing-extensions) nằm trong danh sách được nhận nên không cần ngoại lệ.
Copyleft yếu: Pyphen (chọn MPL-1.1), `lunr-languages` (MPL-1.1), phông Be Vietnam Pro (OFL-1.1).

### Dịch vụ quanh dự án, không phải phụ thuộc lúc chạy

Cài và chạy Signet trên một máy (`make up`) không cần dịch vụ nào dưới đây. Chúng phục vụ việc phát triển, đăng bản
demo của đội, hoặc là lựa chọn của đơn vị cài đặt:

- **Cloudflare Tunnel:** chỉ để đưa bản online của đội ra Internet. Phần chạy trên máy là `cloudflared` (Apache-2.0,
  profile `tunnel`, tắt mặc định); máy có IP công khai thì dùng Caddy hay một reverse proxy khác thay thế.
- **GitHub (kho mã, Actions, Pages):** nơi lưu mã, chạy CI và đăng trang tài liệu, không thuộc sản phẩm. CI chỉ gọi lại
  lệnh `make` và script trong repo, chạy được trên máy riêng; trang tài liệu dựng tại chỗ bằng `npm run build` trong
  `website/`.
- **API viết câu trả lời chuẩn OpenAI (#430):** tắt mặc định. Giao thức mở, đích có thể là máy chủ nguồn mở của đơn vị
  (vLLM Apache-2.0, llama.cpp MIT); gửi tới dịch vụ đám mây là quyết định của đơn vị, và chỉ câu hỏi cùng các đoạn căn
  cứ đã che thông tin cá nhân rời máy ([`docs/van-hanh.md`](docs/van-hanh.md), mục Trợ lý hỏi đáp qua API ngoài).
  Khi bật, tên, phiên bản và giấy phép của mô hình phía đích do đơn vị chọn và tự chịu trách nhiệm; bản dự thi giữ
  mặc định, dùng Ollama tại chỗ.
- **Nơi tải về:** image từ Docker Hub, Quay.io; trọng số mô hình từ thư viện của Ollama, nguồn gốc là Hugging Face (mục
  Trí tuệ nhân tạo).
