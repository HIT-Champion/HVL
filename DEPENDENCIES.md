# Danh mục phần mềm thượng nguồn và giấy phép

Tài liệu này làm rõ mọi thư viện, gói và phần mềm thượng nguồn mà Signet phụ thuộc vào — yêu cầu
bắt buộc theo tiêu chí chấm điểm PoF #5 (*"Có thông tin làm rõ các thư viện, gói đính kèm được
sử dụng"*).

## Nguyên tắc phụ thuộc

1. **Không bundle.** Kho mã nguồn này **không** chứa bản sao mã nguồn của bất kỳ dự án nào khác.
   Mọi phần mềm thượng nguồn được nạp lúc chạy qua image Docker chính thức có ghim thẻ phiên bản và
   digest, hoặc qua trình quản lý gói (`npm`, `pip`) với tệp khóa phiên bản (lockfile).
2. **Không chỉnh sửa upstream.** Mã nguồn của các dự án thượng nguồn được dùng ở dạng **nguyên
   bản**. Mọi tùy biến của Signet nằm ở lớp cấu hình, plugin hoặc adapter riêng.
3. **Ưu tiên thư viện sẵn có của hệ thống** thay vì đóng gói kèm bản riêng.
4. **Kiểm tra tương thích giấy phép.** Mọi thành phần mới phải có giấy phép được OSI phê duyệt và
   tương thích với Apache-2.0 của Signet.

## Cách đọc

- **Phiên bản ghim**: thành phần đã chạy (Phase 1) ghi đúng thẻ trong `docker-compose.yml` — cập nhật
  18/10/2026; thành phần phase sau là bản ổn định mới nhất tại 09/10/2026, chốt lại khi đưa vào. Chỉ
  chọn bản đã phát hành ít nhất hai tuần.
- **Ngoại lệ vá bảo mật**: bản đang ghim có lỗ hổng đã công bố (OSV-Scanner trong CI báo) mà bản vá chưa đủ hai
  tuần thì dùng bản vá ngay, ghi ở đây. 22/10/2026: Pillow 13.0.0 (PyPI 16/10, vá các GHSA của 12.3.0) và pypdf
  6.21.1 (17/10, vá 5 GHSA của 6.19.0) — cả hai đọc tệp người dùng tải lên (`svc-files`); certifi 2026.10.19 (20/10,
  bỏ gốc emSign có CA trung gian lộ khóa, GHSA-6q48-6c7w-9gw2).
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
| Docker Engine | ≥ 24.0 | Apache-2.0 | Đóng gói và chạy container | Cài sẵn trên máy chủ |
| Docker Compose v2 | ≥ 2.20 | Apache-2.0 | Điều phối đa dịch vụ | Plugin của Docker |
| Caddy | ≥ 2.6 | Apache-2.0 | Proxy TLS trên máy chủ: HTTPS, chứng thư Let's Encrypt tự gia hạn ([`docs/trien-khai.md`](docs/trien-khai.md)); không nằm trong Compose | Gói hệ thống của máy chủ (`apt install caddy`) |
| Python | ≥ 3.10 | PSF-2.0 | Chạy `make seed`, `make smoke` (chỉ thư viện chuẩn) | Gói hệ thống |
| Node.js | 24.20.0 | MIT | Dựng giao diện thành trang tĩnh (chỉ ở bước dựng image) | `node:24.20.0-slim` |
| Playwright | 1.63.0 | Apache-2.0 | Kiểm thử trên trình duyệt thật — `make e2e`, `tests/e2e/` | `mcr.microsoft.com/playwright:v1.63.0-noble` |
| GNU Make | ≥ 4.0 | GPL-3.0+ | Điều phối lệnh (công cụ dựng, không liên kết vào sản phẩm) | Gói hệ thống |
| Git | ≥ 2.30 | GPL-2.0 | Quản lý mã nguồn, sinh gói phát hành | Gói hệ thống |
| uv | 0.12.19 | Apache-2.0 / MIT | Cài thư viện test theo băm và chạy `make test`, test `db/tests/` | Tệp chạy độc lập |
| actionlint | 1.7.12 | MIT | CI: kiểm cú pháp và lỗi thường gặp trong `.github/workflows/` | `rhysd/actionlint:1.7.12` |
| gitleaks | 8.30.1 | MIT | CI: quét bí mật lộ trong toàn bộ lịch sử commit | `ghcr.io/gitleaks/gitleaks:v8.30.1` |
| OSV-Scanner | 2.6.0 | Apache-2.0 | CI: đối chiếu tệp khóa phụ thuộc với cơ sở dữ liệu lỗ hổng OSV | `ghcr.io/google/osv-scanner:v2.6.0` |
| REUSE tool | 5.0.2 | GPL-3.0-or-later | Kiểm mọi tệp đều có thông tin bản quyền và giấy phép theo chuẩn REUSE (`REUSE.toml`); chạy tay, chỉ đọc kho | `uvx --from reuse==5.0.2 reuse lint` |

> **Ghi chú tương thích:** Make và Git là *công cụ dựng*, được gọi như tiến trình độc lập và không
> liên kết vào sản phẩm, nên giấy phép GPL của chúng không lan sang Signet. Cả hai đều là phần
> mềm nguồn mở — Signet không dùng bất kỳ công cụ nguồn đóng hay tự chế nào để dựng
> (tiêu chí PoF #4). CI trên GitHub Actions chỉ gọi lại đúng các lệnh `make` ở trên, nên dựng và kiểm
> thử trên máy riêng không cần GitHub.

## Tầng 1 — Lõi nền tảng

| Thành phần | Phiên bản ghim | Giấy phép | Vai trò | Cách nạp | Phase |
|---|---|---|---|---|---|
| Keycloak | 26.7.5 | Apache-2.0 | Định danh tập trung: SSO, MFA, vai trò người dùng | `quay.io/keycloak/keycloak:26.7.5` | 1 |
| Apache APISIX | 3.18.0 | Apache-2.0 | Cổng API: cửa duy nhất ra Internet, kiểm JWT tại biên, giới hạn tốc độ | `apache/apisix:3.18.0-debian` | 1 |
| PostgreSQL | 16 | PostgreSQL License | Cơ sở dữ liệu quan hệ chính (QĐ-002) | `postgres:16-alpine` | 1 |
| Hasura GraphQL Engine (CE) | v2.51.0 | Apache-2.0 | Tự sinh API GraphQL, phân quyền cấp dòng, Actions, Event Triggers | `hasura/graphql-engine:v2.51.0-ce.cli-migrations-v3` | 1 |
| Flowable (REST) | 8.0.0 | Apache-2.0 | Động cơ quy trình BPMN | `flowable/flowable-rest:8.0.0` | 1 |
| SeaweedFS | 4.48 | Apache-2.0 | Lưu trữ đối tượng chuẩn S3 | `chrislusf/seaweedfs:4.48` | 1 |
| ClamAV | 1.5.4 | GPL-2.0 | Quét mã độc tệp tải lên (dịch vụ độc lập) | `clamav/clamav:1.5.4` | 1 |
| Meilisearch (Community Edition) | v1.54.3 | MIT | Tìm kiếm toàn văn; chỉ mục đoạn `chunks` của trợ lý hỏi đáp (F4.2): tìm lai từ khóa + véc-tơ trong bản CE, embedder `userProvided` (véc-tơ do `svc-files` tính bằng Ollama, Meilisearch không gọi mô hình nào, không vào mạng `ai`) | `getmeili/meilisearch:v1.54.3` | 1 |
| nginx (unprivileged) | 1.30.6 | BSD-2-Clause | Phục vụ trang tĩnh của `app-office` sau APISIX | `nginxinc/nginx-unprivileged:1.30.6-alpine` | 1 |
| Centrifugo | v6.9.7 | Apache-2.0 | Đẩy thông báo thời gian thực qua WebSocket | `centrifugo/centrifugo:v6.9.7` | 2 |

**Ghi chú:**

- Hasura: **bắt buộc dùng thẻ `-ce`**. Thẻ không có hậu tố `-ce` chứa thành phần Enterprise độc quyền.
- Meilisearch: chỉ dùng `getmeili/meilisearch` (MIT). Bản enterprise mang giấy phép BUSL-1.1.
- Centrifugo: chỉ dùng bản mã nguồn mở. Bản PRO là phần mềm thương mại.
- Flowable: từ bản 7 chỉ còn bản REST, không có giao diện — phù hợp yêu cầu "lõi không giao diện".

## Tầng 2 — Ứng dụng web

Thư viện được cài qua `npm` với `package-lock.json`; phiên bản dưới đây là dòng chính đang dùng.

| Thành phần | Phiên bản | Giấy phép | Vai trò | Cách nạp | Phase |
|---|---|---|---|---|---|
| Nuxt | 4.5.2 | MIT | Khung ứng dụng web (chế độ SPA, dựng thành trang tĩnh) | npm | 1 |
| Vue | 3.5 | MIT | Thư viện giao diện (qua Nuxt) | npm | 1 |
| oidc-client-ts | 3.5.0 | Apache-2.0 | Đăng nhập OIDC (Authorization Code + PKCE) với Keycloak | npm | 1 |
| vue-i18n | 11.4.13 | MIT | Song ngữ Việt / Anh | npm | 1 |
| Tailwind CSS (+ `@tailwindcss/vite`) | 4.3.3 | MIT | Định dạng giao diện | npm | 1 |
| Ajv | 8.20.0 | MIT | Biên dịch JSON Schema dùng chung (`schemas/`) thành mã kiểm form lúc dựng; chỉ dùng lúc dựng, không vào bundle | npm | 2 |
| Apache ECharts | 6.1.0 | Apache-2.0 | Biểu đồ dashboard điều hành (F3.11), chỉ nạp biểu đồ cột, vẽ SVG. Kéo theo zrender 6.1.0 (BSD-3-Clause) và tslib 2.3.0 (0BSD), cùng nằm trong bundle | npm | 3 |

Thư viện gián tiếp (khoảng 700 gói, đều chỉ dùng lúc dựng; trang phát hành chỉ còn tệp JS/CSS tĩnh) mang
giấy phép MIT, ISC, Apache-2.0, BSD-2/3-Clause, BlueOak-1.0.0, MPL-2.0 hoặc 0BSD, đều được OSI phê duyệt. Quét
`package-lock.json` ngày 23/10/2026, ngoài danh sách đó chỉ có năm gói dưới đây. Không gói nào trong số này nằm
trong trang phát hành (đã tìm trong thư mục trang tĩnh của image `app-office`).

| Gói | Giấy phép | Kéo theo bởi | Ghi chú |
|---|---|---|---|
| `caniuse-lite` | CC-BY-4.0 | browserslist, autoprefixer | Bảng dữ liệu trình duyệt nào hỗ trợ tính năng nào, chỉ đọc lúc dựng CSS. CC-BY-4.0 là giấy phép mở cho dữ liệu, không thuộc danh sách OSI (OSI chỉ duyệt giấy phép phần mềm) |
| `mdn-data` | CC0-1.0 | css-tree (nén CSS lúc dựng) | Dữ liệu cú pháp CSS của MDN. CC0 đưa tác phẩm vào phạm vi công cộng, không thuộc danh sách OSI |
| `@speed-highlight/core` | CC0-1.0 | youch (trang báo lỗi của máy chủ phát triển Nuxt) | Chỉ chạy lúc phát triển |
| `node-forge` | BSD-3-Clause OR GPL-2.0 | listhen (máy chủ phát triển của Nuxt) | Gói cho chọn giấy phép, Signet dùng theo BSD-3-Clause. Chỉ chạy lúc phát triển |
| `type-fest` | MIT OR CC0-1.0 | dot-prop | Chỉ có kiểu TypeScript, Signet dùng theo MIT |

Quét lại: `python3 -c "import json,collections;p=json.load(open('apps/office/package-lock.json'))['packages'];print(collections.Counter(v.get('license') for k,v in p.items() if k))"`.

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
| FastAPI | 0.143 | MIT | Khung viết `svc-files`, `svc-workflow`, `svc-ai` (kéo theo Starlette, Pydantic — BSD-3, MIT) | pip | 1 |
| uvicorn | 0.54 | BSD-3-Clause | Máy chủ ASGI chạy các dịch vụ | pip | 1 |
| httpx2 (+ httpcore2, truststore) | 2.13 | BSD-3-Clause (truststore: MIT) | Gọi Hasura, Flowable, Keycloak, Meilisearch | pip | 1 |
| python-multipart | 0.0.32 | Apache-2.0 | Đọc tệp tải lên (`svc-files`) | pip | 1 |
| boto3 | 1.43 | Apache-2.0 | Gọi SeaweedFS qua giao thức S3 (`svc-files`) | pip | 1 |
| PyJWT (+ cryptography) | 2.15 · 50.0 | MIT (cryptography: Apache-2.0 / BSD) | Kiểm JWT Keycloak trong `svc-files`; mã hóa con trỏ trang tìm kiếm | pip | 1 |
| WeasyPrint (+ pydyf, tinycss2, cssselect2, tinyhtml5, webencodings) | 70.0 | BSD-3-Clause (tinyhtml5: MIT) | Dựng PDF văn bản đi đúng thể thức NĐ 30 từ khuôn HTML (`svc-files`) | pip | 2 |
| fontTools (+ Brotli, zopfli) | 4.66 | MIT (zopfli: Apache-2.0) | Nhúng và nén phông vào PDF (WeasyPrint kéo theo) | pip | 2 |
| Pillow | 13.0 | MIT-CMU (HPND) | Xử lý ảnh khi dựng PDF (WeasyPrint kéo theo). Từ F4.1 khai trực tiếp: chuẩn bị ảnh chụp, ảnh trang scan trước khi nhận dạng chữ (xoay theo EXIF, đổi xám, tăng tương phản, có trần điểm ảnh), chạy trong tiến trình con có giới hạn | pip | 2 |
| Pyphen | 0.18 | GPL-2.0+ / LGPL-2.1+ / MPL-1.1, Signet dùng theo MPL-1.1 | Ngắt từ khi dàn chữ (WeasyPrint kéo theo), dùng nguyên bản không sửa | pip | 2 |
| segno | 1.6 | BSD-3-Clause | Mã QR in trên văn bản phát hành, dẫn tới cổng xác thực | pip | 2 |
| pypdf | 6.21.1 | BSD-3-Clause | Đọc lớp chữ của PDF đính kèm để tìm theo nội dung (`svc-files`, F2.7); F4.1 đọc chữ giữ bố cục (`extraction_mode="layout"`) và lấy ảnh nhúng của trang scan để nhận dạng chữ. Thuần Python, không kéo thêm gói | pip | 2 |
| pytest | 9.1 | MIT | Test đơn vị và tích hợp (chỉ khi phát triển) | pip | 1 |
| Typer | 0.27 | MIT | Khung viết lệnh `moc` khi thêm `backup`, `restore`, `doctor`; `moc audit` hiện chỉ dùng thư viện chuẩn | pip | 3 |
| jsonschema (+ referencing, jsonschema-specifications, rpds-py, attrs) | 4.26 | MIT | `svc-workflow` kiểm lại dữ liệu form theo JSON Schema dùng chung (`schemas/`) | pip | 2 |
| DuckDB | 1.5.6 | MIT | Nộp lưu hồ sơ (F3.8, `svc-files`): ghi bảng văn bản, giao việc, dòng thời gian thành Parquet (nén zstd) và đọc lại cho phòng đọc. Một wheel nhúng, không kéo thêm gói Python, không chạy máy chủ riêng | pip | 3 |
| openlineage-python | 1.53 | Apache-2.0 | Dự kiến phát sự kiện truy vết dữ liệu. **Chưa đưa vào**: svc-files dựng sự kiện OpenLineage 2-0-2 bằng thư viện chuẩn (F3.9, `svc_files.lineage`) | pip | 3 |
| pyHanko (+ pyhanko-certvalidator, asn1crypto, tzlocal, lxml, aiohttp và 7 gói con, oscrypto, uritools, certifi; tzdata chỉ trên Windows) | 0.37.0 · 0.32.1 | MIT (lxml BSD-3, aiohttp Apache-2.0/MIT, certifi MPL-2.0, aiohappyeyeballs PSF-2.0) | Ký số PAdES bản phát hành bằng khóa trong Transit, kiểm chữ ký (svc-files, F4.5, chỉ minh họa) | pip | 4 |

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

Phiên bản cụ thể kèm băm nằm ở `requirements.txt` của từng dịch vụ; image dịch vụ dựng từ
`python:3.13.16-slim` (PSF-2.0). Image `svc-files` cài thêm từ kho Debian: Pango (LGPL-2.1+, nạp động lúc
chạy, không sửa), HarfBuzz (MIT) và phông Liberation 2.1 (SIL OFL 1.1) — cùng số đo với Times New Roman mà
NĐ 30/2020 quy định, có đủ dấu tiếng Việt; từ F4.1 thêm Tesseract cùng dữ liệu tiếng Việt (mục Trí tuệ nhân tạo),
gọi bằng dòng lệnh trong tiến trình con, không thêm gói Python.

## Vận hành và bốn nguyên lý thiết kế

| Thành phần | Phiên bản ghim | Giấy phép | Vai trò | Cách nạp | Phase |
|---|---|---|---|---|---|
| OpenBao | 2.7.1 | MPL-2.0 | Két bí mật và khóa (thay HashiCorp Vault): `svc-files`, `svc-workflow` lấy bí mật qua AppRole, static seal tự mở khóa, khóa transit cho tệp mã hóa; PKI nội bộ (CA minh họa) và khóa ký transit của từng đơn vị cho văn bản đi (F4.5). Image nguyên bản, chỉ thêm tệp cấu hình và script khởi động của đội (`platform/openbao/`) | `openbao/openbao:2.7.1` (image 01/10/2026) | 3 |
| Kestra | v2.0.5 | Apache-2.0 | Dự kiến chạy job ngầm. **Chưa đưa vào**: nộp lưu nóng → lạnh (F3.8) chạy thành vòng nền trong `svc-files` — một job mỗi giờ không đáng thêm một máy chủ Java ~1 GB RAM | `kestra/kestra:v2.0.5` | 3 |
| Marquez | 0.51.1 | Apache-2.0 | Lưu và hiển thị phả hệ dữ liệu (lineage). **Chưa đưa vào compose**: sự kiện lưu trong `core.lineage_events` (F3.9); đặt `MOC_OPENLINEAGE_URL` thì svc-files gửi sang Marquez | `marquezproject/marquez:0.51.1` | 3 |
| Scorpio Broker | 6.0.2 | BSD-3-Clause | Context broker NGSI-LD cho dữ liệu cảm biến (F3.10, profile `iot`): bản sao số, lịch sử đo, subscription báo `svc-workflow` khi vượt ngưỡng. Bản java mặc định (không Kafka), không mở cổng ra ngoài | `scorpiobroker/all-in-one-runner:java-6.0.2` (image 03/07/2026) | 3 |
| PostGIS | 16-3.5 | GPL-2.0 | CSDL riêng của Scorpio (broker bắt buộc phần mở rộng `postgis`); dịch vụ độc lập, mạng riêng chỉ broker nối được, Signet không liên kết mã | `postgis/postgis:16-3.5-alpine`, ghim digest (image 31/08/2026) | 3 |
| Prometheus | v3.15.0 | Apache-2.0 | Thu chỉ số của cổng API (plugin `prometheus` của APISIX) mỗi 15 giây; không mở cổng ra ngoài (F3.13) | `prom/prometheus:v3.15.0` | 3 |
| Grafana (OSS) | 13.2.3 | AGPL-3.0 | Hiển thị giám sát: bảng điều khiển nạp từ `platform/monitoring/` (dịch vụ độc lập, chỉ nghe 127.0.0.1, chỉ xem, không tài khoản) (F3.13) | `grafana/grafana:13.2.3` | 3 |
| cloudflared | 2026.10.0 | Apache-2.0 | Cloudflare Tunnel (F1.9, profile `tunnel`, tùy chọn): máy không có IP công khai ra Internet có HTTPS mà không mở cổng — gọi ra Cloudflare, chuyển yêu cầu vào APISIX qua mạng Docker; token để ngoài repo | `cloudflare/cloudflared:2026.10.0` (image 05/10/2026) | 1 |
| restic | 0.19.1 | BSD-2-Clause | Sao lưu, khôi phục CSDL và tệp (`moc backup`): mã hóa, khử trùng lặp; chỉ chạy khi gọi, không mạng | `restic/restic:0.19.1` | 3 |
| Vector | 0.59.0 | MPL-2.0 | Thu gom log *(Could)* | `timberio/vector:0.59.0-debian` | 3 |
| Parseable | 3.2 | AGPL-3.0 | Lưu và tra cứu log *(Could)* | `parseable/parseable` (ghim thẻ khi đưa vào) | 3 |
| Coraza | 3.8 | Apache-2.0 | Tường lửa ứng dụng web tại gateway *(Could)* | Plugin proxy-wasm cho APISIX | 3 |

**Ghi chú:**

- Grafana: chỉ dùng `grafana/grafana` (AGPL-3.0). `grafana/grafana-enterprise` là bản độc quyền.
- Marquez: bản phát hành gần nhất là 0.51.1 (03/2025), mã nguồn vẫn có commit năm 2026 nhưng nhịp chậm.
  Theo dõi trong Phase 3; nếu gặp lỗi chặn thì chuyển sang chỉ lưu sự kiện OpenLineage vào PostgreSQL. F3.9 đã làm
  theo hướng đó (`core.lineage_events`): tránh thêm máy chủ Java và CSDL riêng (~1 GB RAM) cho một job mỗi giờ.

## Trí tuệ nhân tạo

| Thành phần | Phiên bản ghim | Giấy phép | Vai trò | Cách nạp | Phase |
|---|---|---|---|---|---|
| Ollama | 0.35.1 | MIT | Chạy mô hình ngôn ngữ cục bộ (profile `ai`, tùy chọn): viết trích yếu khi quy tắc không ra trích yếu tin cậy (F4.1); nhúng đoạn văn bản và câu hỏi (`/api/embed`), viết câu trả lời có trích dẫn cho trợ lý hỏi đáp (F4.2) — giữ cùng lúc mô hình viết và mô hình nhúng (`OLLAMA_MAX_LOADED_MODELS=2`); mạng nội bộ riêng, không mở cổng, tắt tính năng đám mây (`OLLAMA_NO_CLOUD`). Bản ổn định mới nhất trước 06/10/2026, có `think` và `format` theo JSON Schema | `ollama/ollama:0.35.1@sha256:292ee7945dfc3d5840a181f3ab86fedb1e66703e02c8af98b50f4da56b7e278c` (image 02/10/2026) | 4 |
| Qwen3-1.7B | `qwen3:1.7b` (Q4_K_M, khoảng 1,36 GB) | Apache-2.0 (đã kiểm model card và tệp LICENSE trên Hugging Face của đúng cỡ 1.7B; cỡ 4B cũng Apache-2.0) | Trọng số mô hình viết trích yếu (F4.1) và câu trả lời có trích dẫn của trợ lý hỏi đáp (F4.2, chỉ từ các đoạn đã lọc theo quyền người hỏi; `svc-files` kiểm trích dẫn, con số trước khi trả). Phát hành 04/2025. Máy đủ nhanh thì đổi `MOC_AI_MODEL=qwen3:4b` hoặc chỉ riêng trợ lý `MOC_ASK_MODEL=qwen3:4b` | Tải một lần qua Ollama (`make ai-model`, profile `ai-pull`); bản kê `sha256:8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7` — so với `ollama list` | 4 |
| Qwen3-Embedding-0.6B | `qwen3-embedding:0.6b` (Q8_0, 639 MB, 1024 chiều, ngữ cảnh 32K) | Apache-2.0 (khai trong model card `Qwen/Qwen3-Embedding-0.6B` và bản GGUF chính thức trên Hugging Face; kho không kèm tệp LICENSE, bản kê Ollama không có lớp giấy phép) | Mô hình nhúng đoạn văn bản và câu hỏi cho tìm theo nghĩa của trợ lý hỏi đáp (F4.2, `MOC_AI_EMBED_MODEL`; câu hỏi mang tiền tố `Instruct: …\nQuery: …`). Phát hành 05/06/2025 (bài báo arXiv 2506.05176); có trong thư viện Ollama từ 23/09/2025, Ollama hỗ trợ từ 0.12.1. MMTEB đa ngữ: trung bình 64,33, truy xuất 64,64 (bge-m3: 59,56 / 54,60 — bảng trong model card). Đổi `MOC_AI_EMBED_MODEL=bge-m3` được, cùng 1024 chiều, `svc-files` tự nhúng lại | Tải một lần qua Ollama (`make ai-model`, profile `ai-pull`); bản kê `sha256:ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d` — so với `ollama list` | 4 |
| Tesseract OCR (+ dữ liệu `vie`) | 5.5.0 (gói Debian trixie `tesseract-ocr` 5.5.0-1+b1, `tesseract-ocr-vie` 1:4.1.0-2) | Apache-2.0 | Nhận dạng chữ trên công văn scan, ảnh chụp khi tiếp nhận (F4.1, `svc-files`). Dữ liệu `vie` là bản tessdata_fast 4.1.0 (mô hình LSTM nhanh). Phiên bản gói lấy từ kho Debian theo image gốc — kiểm lại bằng `dpkg-query -W 'tesseract-ocr*'` trong image `svc-files` sau khi dựng | Gói hệ thống (apt) | 4 |
| Gotenberg | 8.37.0 | MIT | Sinh PDF *(Could)* | `gotenberg/gotenberg:8.37.0` | 4 |

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
| n8n | Sustainable Use License — không phải OSI | Kestra |
| Redpanda | BSL-1.1 — không phải OSI | Hasura Event Triggers (không cần message broker) |
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

## Kiểm tra tương thích giấy phép

Giấy phép được chấp nhận trong Signet (tương thích với Apache-2.0 ở vai trò dịch vụ độc lập):

- ✅ Apache-2.0, MIT, BSD-2/3-Clause, PostgreSQL License, ISC, MPL-2.0, PSF-2.0 (giấy phép dễ dãi được OSI phê
  duyệt, của chính Python và image `python`; F4.5: aiohappyeyeballs)
- ✅ MPL-1.1, LGPL-2.1+, SIL OFL 1.1 cho thư viện và phông dùng nguyên bản, không sửa: Pyphen (chọn MPL-1.1
  trong ba giấy phép), Pango (nạp động), phông Liberation.
- ✅ CC-BY-4.0, CC0-1.0 chỉ cho dữ liệu và công cụ chạy lúc dựng, lúc phát triển, không vào sản phẩm: `caniuse-lite`,
  `mdn-data`, `@speed-highlight/core` (mục Tầng 2). Gói cho chọn giấy phép thì chọn giấy phép OSI: `node-forge`
  theo BSD-3-Clause, `type-fest` theo MIT.
- ⚠️ GPL-2.0/3.0, AGPL-3.0 — chấp nhận được khi chạy như **dịch vụ độc lập** giao tiếp qua mạng,
  không liên kết mã. Hiện gồm: ClamAV và PostGIS (GPL-2.0), Grafana và Parseable (AGPL-3.0).
- ❌ Mọi giấy phép không được OSI phê duyệt, giấy phép "source-available" (BUSL, SSPL, Elastic
  License, Sustainable Use License), hoặc bất kỳ thành phần nguồn đóng nào.
