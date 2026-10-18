# Danh mục phần mềm thượng nguồn và giấy phép

Tài liệu này làm rõ mọi thư viện, gói và phần mềm thượng nguồn mà Mộc phụ thuộc vào — yêu cầu
bắt buộc theo tiêu chí chấm điểm PoF #5 (*"Có thông tin làm rõ các thư viện, gói đính kèm được
sử dụng"*).

## Nguyên tắc phụ thuộc

1. **Không bundle.** Kho mã nguồn này **không** chứa bản sao mã nguồn của bất kỳ dự án nào khác.
   Mọi phần mềm thượng nguồn được nạp lúc chạy qua image Docker chính thức có ghim thẻ phiên bản,
   hoặc qua trình quản lý gói (`npm`, `pip`) với tệp khóa phiên bản (lockfile).
2. **Không chỉnh sửa upstream.** Mã nguồn của các dự án thượng nguồn được dùng ở dạng **nguyên
   bản**. Mọi tùy biến của Mộc nằm ở lớp cấu hình, plugin hoặc adapter riêng.
3. **Ưu tiên thư viện sẵn có của hệ thống** thay vì đóng gói kèm bản riêng.
4. **Kiểm tra tương thích giấy phép.** Mọi thành phần mới phải có giấy phép được OSI phê duyệt và
   tương thích với Apache-2.0 của Mộc.

## Cách đọc

- **Phiên bản ghim**: thành phần đã chạy (Phase 1) ghi đúng thẻ trong `docker-compose.yml` — cập nhật
  18/10/2026; thành phần phase sau là bản ổn định mới nhất tại 09/10/2026, chốt lại khi đưa vào. Chỉ
  chọn bản đã phát hành ít nhất hai tuần.
- **Phase**: thời điểm thành phần được đưa vào, theo [`docs/ke-hoach-phat-trien.md`](docs/ke-hoach-phat-trien.md).
  Thành phần đánh dấu *Could* chỉ được thêm nếu còn thời gian.
- **Copyleft (GPL, AGPL)**: chỉ dùng ở dạng **dịch vụ độc lập giao tiếp qua mạng**, không liên kết
  vào mã của Mộc, nên giấy phép của chúng không lan sang Mộc.

## Công cụ dựng và vận hành

| Thành phần | Phiên bản | Giấy phép | Vai trò | Cách nạp |
|---|---|---|---|---|
| Docker Engine | ≥ 24.0 | Apache-2.0 | Đóng gói và chạy container | Cài sẵn trên máy chủ |
| Docker Compose v2 | ≥ 2.20 | Apache-2.0 | Điều phối đa dịch vụ | Plugin của Docker |
| Python | ≥ 3.10 | PSF-2.0 | Chạy `make seed`, `make smoke` (chỉ thư viện chuẩn) | Gói hệ thống |
| Node.js | 24.20.0 | MIT | Dựng giao diện thành trang tĩnh (chỉ ở bước dựng image) | `node:24.20.0-slim` |
| Playwright | 1.63.0 | Apache-2.0 | Kiểm thử trên trình duyệt thật — `make e2e`, `tests/e2e/` | `mcr.microsoft.com/playwright:v1.63.0-noble` |
| GNU Make | ≥ 4.0 | GPL-3.0+ | Điều phối lệnh (công cụ dựng, không liên kết vào sản phẩm) | Gói hệ thống |
| Git | ≥ 2.30 | GPL-2.0 | Quản lý mã nguồn, sinh gói phát hành | Gói hệ thống |

> **Ghi chú tương thích:** Make và Git là *công cụ dựng*, được gọi như tiến trình độc lập và không
> liên kết vào sản phẩm, nên giấy phép GPL của chúng không lan sang Mộc. Cả hai đều là phần
> mềm nguồn mở — Mộc không dùng bất kỳ công cụ nguồn đóng hay tự chế nào để dựng
> (tiêu chí PoF #4).

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
| Meilisearch (Community Edition) | v1.54.3 | MIT | Tìm kiếm toàn văn | `getmeili/meilisearch:v1.54.3` | 1 |
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
| Ajv | 8.20 | MIT | Kiểm tra form theo JSON Schema dùng chung | npm | 2 |
| PDF.js (`pdfjs-dist`) | 6.4 | Apache-2.0 | Xem PDF ngay trên trang | npm | 2 |
| Apache ECharts | 6.1 | Apache-2.0 | Biểu đồ dashboard điều hành | npm | 3 |

Thư viện gián tiếp (khoảng 600 gói, đều chỉ dùng lúc dựng; trang phát hành chỉ còn tệp JS/CSS tĩnh) mang
giấy phép MIT, ISC, Apache-2.0, BSD, BlueOak-1.0.0, MPL-2.0 hoặc CC0 — đã quét `node_modules` ngày
18/10/2026, không có giấy phép ngoài danh sách OSI.

**Ghi chú:** BTC gợi ý "Nuxt 3 / Vue 3". Mộc dùng **Nuxt 4** (vẫn chạy trên Vue 3) vì đây là dòng
chính hiện tại; dòng Nuxt 3 chỉ còn nhận bản vá bảo trì. Dùng `vue-i18n` trực tiếp thay cho
`@nuxtjs/i18n`: ứng dụng chạy hoàn toàn trên trình duyệt, không cần định tuyến theo ngôn ngữ.

## Dịch vụ tự viết (`services/`, `cli/`)

Thư viện Python cài qua `pip` với tệp khóa phiên bản.

| Thành phần | Phiên bản | Giấy phép | Vai trò | Cách nạp | Phase |
|---|---|---|---|---|---|
| FastAPI | 0.143 | MIT | Khung viết `svc-files`, `svc-workflow`, `svc-ai` (kéo theo Starlette, Pydantic — BSD-3, MIT) | pip | 1 |
| uvicorn | 0.54 | BSD-3-Clause | Máy chủ ASGI chạy các dịch vụ | pip | 1 |
| httpx2 (+ httpcore2, truststore) | 2.13 | BSD-3-Clause (truststore: MIT) | Gọi Hasura, Flowable, Keycloak, Meilisearch | pip | 1 |
| python-multipart | 0.0.32 | Apache-2.0 | Đọc tệp tải lên (`svc-files`) | pip | 1 |
| boto3 | 1.43 | Apache-2.0 | Gọi SeaweedFS qua giao thức S3 (`svc-files`) | pip | 1 |
| PyJWT (+ cryptography) | 2.15 | MIT (cryptography: Apache-2.0 / BSD) | Kiểm JWT Keycloak trong `svc-files` | pip | 1 |
| pytest | 9.1 | MIT | Test đơn vị và tích hợp (chỉ khi phát triển) | pip | 1 |
| Typer | 0.27 | MIT | Khung viết lệnh `dxos` | pip | 3 |
| jsonschema | 4.26 | MIT | Kiểm tra dữ liệu đề xuất theo JSON Schema dùng chung | pip | 2 |
| DuckDB | 1.5 | MIT | Đọc hồ sơ lưu trữ lạnh (Parquet) | pip | 3 |
| openlineage-python | 1.53 | Apache-2.0 | Phát sự kiện truy vết dữ liệu | pip | 3 |

Phiên bản cụ thể kèm băm nằm ở `requirements.txt` của từng dịch vụ; image dịch vụ dựng từ
`python:3.13.16-slim` (PSF-2.0).

## Vận hành và bốn nguyên lý thiết kế

| Thành phần | Phiên bản ghim | Giấy phép | Vai trò | Cách nạp | Phase |
|---|---|---|---|---|---|
| OpenBao | 2.7.1 | MPL-2.0 | Két quản lý bí mật và khóa (thay HashiCorp Vault) | `openbao/openbao:2.7.1` | 3 |
| Kestra | v2.0.5 | Apache-2.0 | Chạy job ngầm: chuyển dữ liệu nóng → lạnh, kiểm tra sổ kiểm toán | `kestra/kestra:v2.0.5` | 3 |
| Marquez | 0.51.1 | Apache-2.0 | Lưu và hiển thị phả hệ dữ liệu (lineage) | `marquezproject/marquez:0.51.1` | 3 |
| Scorpio Broker | 6.0.2 | BSD-3-Clause | Context broker NGSI-LD cho dữ liệu cảm biến (IT/OT) | `scorpiobroker/all-in-one-runner:java-6.0.2` | 3 |
| Prometheus | v3.15.0 | Apache-2.0 | Thu thập chỉ số giám sát | `prom/prometheus:v3.15.0` | 3 |
| Grafana (OSS) | 13.2.3 | AGPL-3.0 | Hiển thị giám sát (dịch vụ độc lập, chỉ mạng nội bộ) | `grafana/grafana:13.2.3` | 3 |
| restic | 0.19.1 | BSD-2-Clause | Sao lưu và khôi phục | Gói hệ thống | 3 |
| Vector | 0.59.0 | MPL-2.0 | Thu gom log *(Could)* | `timberio/vector:0.59.0-debian` | 3 |
| Parseable | 3.2 | AGPL-3.0 | Lưu và tra cứu log *(Could)* | `parseable/parseable` (ghim thẻ khi đưa vào) | 3 |
| Coraza | 3.8 | Apache-2.0 | Tường lửa ứng dụng web tại gateway *(Could)* | Plugin proxy-wasm cho APISIX | 3 |

**Ghi chú:**

- Grafana: chỉ dùng `grafana/grafana` (AGPL-3.0). `grafana/grafana-enterprise` là bản độc quyền.
- Marquez: bản phát hành gần nhất là 0.51.1 (03/2025), mã nguồn vẫn có commit năm 2026 nhưng nhịp chậm.
  Theo dõi trong Phase 3; nếu gặp lỗi chặn thì chuyển sang chỉ lưu sự kiện OpenLineage vào PostgreSQL.

## Trí tuệ nhân tạo

| Thành phần | Phiên bản ghim | Giấy phép | Vai trò | Cách nạp | Phase |
|---|---|---|---|---|---|
| Ollama | 0.40.2 | MIT | Chạy mô hình ngôn ngữ cục bộ | `ollama/ollama:0.40.2` | 4 |
| Qwen3 (4B hoặc 8B, chốt sau spike) | — | Apache-2.0 | Trọng số mô hình ngôn ngữ | Tải qua Ollama | 4 |
| bge-m3 | — | MIT | Mô hình nhúng văn bản cho tìm kiếm ngữ nghĩa | Tải qua Ollama | 4 |
| Qdrant | v1.19.2 | Apache-2.0 | Cơ sở dữ liệu véc-tơ | `qdrant/qdrant:v1.19.2` | 4 |
| LlamaIndex | 0.14 | MIT | Khung RAG và tác tử (khung AI duy nhất) | pip | 4 |
| Tesseract **hoặc** PaddleOCR (chốt sau spike) | 5.5.3 / 3.7 | Apache-2.0 | Nhận dạng chữ trên chứng từ | Gói hệ thống / pip | 4 |
| Presidio | 2.2 | MIT | Che thông tin cá nhân *(Could)* | pip | 4 |
| Gotenberg | 8.37.0 | MIT | Sinh PDF *(Could)* | `gotenberg/gotenberg:8.37.0` | 4 |
| pyHanko | 0.37 | MIT | Ký số PDF *(Could)* | pip | 4 |

**Ghi chú:** trọng số mô hình có giấy phép riêng, tách khỏi giấy phép của Ollama. Trước khi dùng phải
đọc giấy phép trên model card **của đúng kích cỡ đã chọn**. Không dùng Llama hoặc Gemma vì giấy phép
trọng số không được OSI phê duyệt.

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

## Kiểm tra tương thích giấy phép

Giấy phép được chấp nhận trong Mộc (tương thích với Apache-2.0 ở vai trò dịch vụ độc lập):

- ✅ Apache-2.0, MIT, BSD-2/3-Clause, PostgreSQL License, ISC, MPL-2.0
- ⚠️ GPL-2.0/3.0, AGPL-3.0 — chấp nhận được khi chạy như **dịch vụ độc lập** giao tiếp qua mạng,
  không liên kết mã. Hiện gồm: ClamAV (GPL-2.0), Grafana và Parseable (AGPL-3.0).
- ❌ Mọi giấy phép không được OSI phê duyệt, giấy phép "source-available" (BUSL, SSPL, Elastic
  License, Sustainable Use License), hoặc bất kỳ thành phần nguồn đóng nào.
