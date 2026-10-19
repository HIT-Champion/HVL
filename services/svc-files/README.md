# svc-files

Cửa duy nhất để tệp vào và ra khỏi kho đối tượng của Mộc. Tệp tải lên được **quét ClamAV trước**,
sạch mới ghi vào SeaweedFS và thêm dòng `core.files`; ClamAV không trả lời thì từ chối, không bao giờ lưu tệp
chưa quét. Tải xuống: svc-files hỏi Hasura **bằng chính token của người dùng** xem họ có được xem tệp không —
quy tắc quyền chỉ nằm ở `db/metadata`, svc-files không viết lại. Tìm kiếm cũng vậy: Meilisearch xếp hạng,
Hasura quyết ai được đọc văn bản nào. Văn bản đi được dựng thành PDF đúng thể thức NĐ 30 ở đây, và cổng xác thực
trả lời người ngoài một văn bản có thật, còn nguyên vẹn không.

Thuộc lõi Tầng 1 — F1.5 (dữ liệu phi cấu trúc), F1.6 (trạm kiểm dịch), F1.7 (tìm kiếm), F2.4 (dựng PDF văn bản đi)
và F2.13 (cổng xác thực) trong [`docs/ke-hoach-phat-trien.md`](../../docs/ke-hoach-phat-trien.md). Chủ: mảng AI ·
issue #19, #20.

## Trạng thái

| Phần | Trạng thái |
|---|---|
| `POST /api/files`: kiểm JWT → quét ClamAV → ghi SeaweedFS → thêm dòng `core.files` | **Xong** |
| Tệp nhiễm: ghi `file.rejected` vào sổ kiểm toán `core.audit_log` | **Xong** |
| `GET /api/files/{id}`: kiểm quyền qua Hasura → đọc SeaweedFS | **Xong** |
| `GET /api/search`: số ký hiệu, trích yếu, cơ quan ban hành; gõ không dấu được | **Xong** |
| Tìm trong nội dung PDF có lớp chữ (trường `content` đã chừa sẵn) | Phase 2 (F2.7) |
| Giải mã văn bản hạn chế, watermark khi tải | Phase 3 (F3.7) |
| `/internal/issue`: dựng PDF có số, mã QR (WeasyPrint) → quét → lưu bản phát hành | **Xong** (F2.4) |
| `GET /api/documents/{id}/preview`: PDF dự thảo cho người được đọc | **Xong** (F2.4) |
| `GET /api/verify/{mã}`, `GET /api/verify?sha256=`: không cần đăng nhập | **Xong** (F2.13) |
| Neo đầu chuỗi sổ kiểm toán ra bucket lạnh có khóa ghi (S3 Object Lock) | **Xong** (F2.12) |

## API

Đi qua APISIX ở `/api/files/*`, `/api/search`. OpenAPI tự sinh ở `/openapi.json` (chỉ trong mạng nội bộ), bản
xuất nằm ở [`docs/api/openapi/svc-files.json`](../../docs/api/openapi/svc-files.json) (`make api-docs`).

| Đường dẫn | Kết quả |
|---|---|
| `POST /api/files` (multipart, trường `file`) | `201` `{id, object_key, filename, mime_type, size_bytes, sha256, scanned_at}` |
| | `401` thiếu hoặc sai token · `403` token không có `tenant_id` |
| | `413` vượt `MOC_FILES_MAX_MB` · `400` tệp rỗng hoặc thiếu trường `file` |
| | `422` `{code: "infected", signature}` — tệp nhiễm, **không lưu**, ghi vào sổ kiểm toán |
| | `403` `unknown_tenant` — thuê ước trong token chưa có trong `core.tenants` |
| | `503` ClamAV, SeaweedFS hoặc Hasura không sẵn sàng — **không lưu** (đã ghi vào kho thì gỡ ra) |
| `GET /api/files/{id}` | `200` nội dung tệp · `404` không có tệp **hoặc** không được xem (trả như nhau) · `401` · `503` |
| `GET /api/search?q=` | `200` `{hits: [...], next_offset}` · `400` câu tìm trống · `422` tham số sai · `401` · `503` |
| `GET /api/documents/{id}/preview` | `200` PDF dự thảo (chữ "DỰ THẢO", chưa số) · `404` không có hoặc không được đọc · `409` đã phát hành |
| `GET /api/verify/{mã}` | **Không cần token.** `200` `{result: "valid" \| "not_found", document}`; nhận cả `abcde-23456`, `ABCDE 23456` |
| `GET /api/verify?sha256=` | **Không cần token.** Như trên, tra theo băm; `422` khi không phải 64 ký tự hex |
| `POST /internal/issue` | Chỉ token tài khoản dịch vụ trong `MOC_SERVICE_CLIENTS` (`403` với token người dùng). `201` `{file_id, sha256, size_bytes}` · `409` văn bản chưa cấp số · `503` ClamAV, kho, CSDL không sẵn sàng. Không có trong OpenAPI công khai, APISIX không có route tới |
| `GET /healthz` | Tiến trình còn sống |
| `GET /readyz` | `200` khi gọi được ClamAV, SeaweedFS và Hasura, ngược lại `503`; Meilisearch hỏng thì vẫn `200` nhưng `status: "degraded"` |

Ai xem được tệp: người tải lên, và người đọc được văn bản có gắn tệp đó (`db/README.md`, mục Vai trò).
Tệp tải về luôn ở dạng `attachment`, kèm `X-Content-Type-Options: nosniff` và
`Content-Security-Policy: sandbox` — tệp HTML hay SVG người dùng tải lên không chạy được như một trang của
Mộc. Giao diện xem PDF bằng PDF.js nên không cần hiển thị inline. `ETag` là SHA-256 của tệp.

Khóa đối tượng: `tenant/<tenant_id>/<yyyy>/<mm>/<id>` — thuê ước lấy từ token, không lấy từ dữ liệu client
gửi; khóa không trả ra ngoài. Mỗi dòng nhật ký là một đối tượng JSON có `request_id` (lấy từ `X-Request-Id`
do APISIX gắn); mã này cũng đi vào cột `request_id` của sổ kiểm toán.

### Tìm kiếm

`GET /api/search?q=…` nhận thêm `direction` (`in`/`out`), `status`, `type_code`, `urgency`, `year`, `limit`
(≤ 50), `offset`. Meilisearch tự bỏ dấu tiếng Việt (`tuyen sinh` khớp "tuyển sinh", `qd-dhcn` khớp
"QĐ-ĐHCN") và chịu được gõ sai một chữ.

1. Meilisearch tìm trong chỉ mục với điều kiện `tenant_id` lấy từ token — luôn đứng đầu bộ lọc, không lấy từ
   tham số. Chỉ mục chỉ trả về id (`displayedAttributes: ["id"]`).
2. svc-files hỏi Hasura **bằng token người dùng** các id đó: văn bản không được đọc bị bỏ, dữ liệu trả về là
   bản mới nhất trong CSDL. Người chỉ được đọc ít văn bản thì svc-files lấy thêm vài lượt để đủ `limit`.
3. Không trả tổng số kết quả: con số của Meilisearch tính cả văn bản người dùng không được đọc. Trang sau
   lấy bằng `offset=next_offset`; `next_offset: null` là hết.
4. Nhật ký chỉ ghi độ dài câu tìm, không ghi nội dung.

Đồng bộ chỉ mục: mỗi `MOC_SEARCH_SYNC_INTERVAL_S` giây, svc-files đọc các văn bản có `updated_at` mới qua
Hasura (khóa quản trị, chỉ đọc) và ghi đè vào Meilisearch theo id. Mỗi lượt đọc lùi lại 60 giây để không sót
giao dịch ghi xong muộn; văn bản chưa đổi không bị đẩy lại. Khởi động lại thì đồng bộ lại toàn bộ.

### Văn bản đi và cổng xác thực

- **Dựng PDF** (`render.py`): khuôn HTML theo thể thức NĐ 30, Phụ lục I — cơ quan chủ quản, tên đơn vị, số ký
  hiệu, quốc hiệu, tiêu ngữ, địa danh và ngày (ngày dưới 10, tháng 1–2 có số 0), tên loại và trích yếu (công văn:
  "V/v …" dưới số, "Kính gửi"), nội dung, nơi nhận kèm "Lưu: VT, <phòng>.", chức vụ và tên người ký, giờ ký duyệt
  trên Mộc. Bản phát hành có mã QR dẫn tới `<MOC_PUBLIC_URL>/xac-thuc/<mã>`. Mọi chữ người dùng nhập được thoát
  HTML. Phông Liberation Serif (cùng số đo Times New Roman) cài trong image.
- **Không phải chữ ký số.** "Đã duyệt trên hệ thống Mộc" chỉ ghi lại việc người ký bấm duyệt trong Mộc. Tính toàn
  vẹn đến từ SHA-256 của tệp, lưu trong CSDL và trong sổ kiểm toán chuỗi băm, kiểm được ở cổng xác thực.
- **Dữ liệu dựng lấy từ CSDL**, không từ người gọi: `/internal/issue` chỉ nhận id văn bản, thuê ước, người thực
  hiện. Bản phát hành vẫn qua ClamAV và vào `core.files` như mọi tệp.
- **Cổng xác thực** tra khung nhìn `office.issued_documents` bằng vai trò Hasura `verifier`, mỗi lần đúng một văn
  bản. Nhật ký chỉ ghi cách tra (mã hay băm) và kết quả.

### Neo sổ kiểm toán (F2.12)

`anchors.py`. Mỗi `MOC_AUDIT_ANCHOR_INTERVAL_S` giây, nếu sổ có dòng mới từ mốc trước, svc-files đọc đầu chuỗi
(`core.audit_head`) và ghi đối tượng `anchors/<last_id 12 chữ số>-<hash>.json` vào bucket `MOC_COLD_BUCKET`, rồi
ghi bản tra cứu vào `core.audit_anchors`. Hỏng giữa chừng thì lượt sau thấy đối tượng đã có, chỉ ghi nốt dòng
tra cứu, không thêm phiên bản.

- Bucket tạo với **S3 Object Lock**; mỗi mốc ghi kèm hạn giữ COMPLIANCE `MOC_AUDIT_ANCHOR_RETENTION_DAYS` ngày.
  Trên SeaweedFS 4.48 đã thử: xóa phiên bản, rút ngắn hạn, hạ xuống GOVERNANCE, xóa bucket đều bị từ chối, kể cả
  với khóa quản trị của kho; ghi đè chỉ tạo thêm phiên bản. Bucket có sẵn mà không bật khóa ghi thì không neo vào.
- Hash nằm ngay trong tên đối tượng: lệnh kiểm (`make audit`) chỉ liệt kê bucket, không tải từng tệp. Nội dung
  đối tượng chỉ gồm `audit_id`, `hash`, nên hai lần ghi cùng một mốc (vòng nền và `audit anchor` cùng lúc) cho
  cùng nội dung. Khi liệt kê, mốc có phiên bản khác nội dung hoặc có dấu xóa mang cờ `overwritten`, `deleted`.
- Khóa ghi chỉ có hiệu lực khi đi qua cổng S3; gọi thẳng filer thì xóa được (đã thử). SeaweedFS chạy với
  `-filer.disableHttp` và chỉ chung mạng `storage` với svc-files (`docker-compose.yml`).
- Vòng neo nhớ mốc vừa ghi trong bộ nhớ, không hỏi `core.audit_anchors`; lượt neo hỏng (kho chưa lên lúc khởi
  động) thì thử lại sau 30 giây, không đợi hết chu kỳ.
- Chạy tay trong container (lệnh `scripts/moc.py` trên máy chủ gọi qua `docker compose exec`):
  `python -m svc_files.anchors now` neo ngay; `python -m svc_files.anchors list` in các mốc dạng JSON.

### Gọi Hasura

| Việc | Gọi bằng |
|---|---|
| Kiểm người dùng có được xem tệp | Token của người dùng — Hasura áp quyền của vai trò |
| Lọc kết quả tìm kiếm theo quyền | Token của người dùng |
| Thêm dòng `core.files`, ghi `file.rejected`, đọc `object_key` | Khóa quản trị + `X-Hasura-Role: service` + thuê ước, người dùng, request id lấy từ token đã kiểm |
| Đọc văn bản mới sửa để đồng bộ chỉ mục | Khóa quản trị, không kèm vai trò — việc nội bộ, chỉ đọc, không nhận tham số từ người dùng |
| Đọc văn bản để dựng bản xem trước | Token của người dùng |
| Đọc văn bản để dựng bản phát hành | Khóa quản trị + `X-Hasura-Role: service` + thuê ước trong yêu cầu của svc-workflow |
| Tra cứu ở cổng xác thực | Khóa quản trị + `X-Hasura-Role: verifier` |
| Đọc đầu chuỗi sổ kiểm toán, ghi mốc neo | Khóa quản trị, không kèm vai trò — việc nội bộ, không nhận tham số từ người dùng |

## Cấu hình

| Biến | Mặc định | Ghi chú |
|---|---|---|
| `MOC_OIDC_ISSUER` | **bắt buộc** | URL công khai của realm, trùng claim `iss`, vd `https://moc.example/realms/moc` |
| `MOC_OIDC_JWKS_URL` | **bắt buộc** | URL nội bộ, vd `http://keycloak:8080/realms/moc/protocol/openid-connect/certs` |
| `MOC_OIDC_AUDIENCE` | trống | Đặt thì kiểm claim `aud` |
| `SEAWEEDFS_S3_ACCESS_KEY`, `SEAWEEDFS_S3_SECRET_KEY` | **bắt buộc** | |
| `SEAWEEDFS_S3_ENDPOINT` | `http://seaweedfs:8333` | |
| `SEAWEEDFS_S3_REGION` | `us-east-1` | |
| `MOC_FILES_BUCKET` | `moc-files` | Tự tạo nếu chưa có |
| `MOC_FILES_MAX_MB` | `25` | Phải nhỏ hơn `StreamMaxLength` của clamd |
| `CLAMAV_HOST`, `CLAMAV_PORT` | `clamav`, `3310` | |
| `CLAMAV_TIMEOUT_S` | `60` | |
| `HASURA_URL` | `http://hasura:8080` | Gọi trong mạng nội bộ, không qua APISIX |
| `HASURA_ADMIN_SECRET` | **bắt buộc** | Trùng giá trị Hasura dùng |
| `HASURA_TIMEOUT_S` | `10` | |
| `MEILISEARCH_URL` | `http://meilisearch:7700` | |
| `MEILISEARCH_API_KEY` | **bắt buộc** | Hiện dùng master key của Meilisearch (chỉ trong mạng nội bộ) |
| `MOC_SEARCH_INDEX` | `documents` | Tự tạo và áp cấu hình khi khởi động |
| `MOC_SEARCH_SYNC_INTERVAL_S` | `5` | `0` tắt vòng đồng bộ nền |
| `MOC_PUBLIC_URL` | phần trước `/realms/` của `MOC_OIDC_ISSUER` | In vào mã QR của bản phát hành |
| `MOC_SERVICE_CLIENTS` | `svc-workflow` | Client Keycloak được gọi `/internal/*`, cách nhau dấu phẩy |
| `MOC_COLD_BUCKET` | `moc-cold` | Bucket lạnh có khóa ghi, tự tạo; phải khác `MOC_FILES_BUCKET` |
| `MOC_AUDIT_ANCHOR_INTERVAL_S` | `600` | Chu kỳ neo đầu chuỗi sổ kiểm toán; `0` tắt vòng neo |
| `MOC_AUDIT_ANCHOR_RETENTION_DAYS` | `3650` | Hạn giữ mỗi mốc; trong hạn không ai xóa được |

## Phát triển

Cần Python ≥ 3.12 và [uv](https://github.com/astral-sh/uv) (MIT/Apache-2.0) hoặc `pip`.

```bash
cd services/svc-files
uv venv && uv pip install -r requirements-dev.txt     # hoặc: python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest                            # test đơn vị, không cần Docker
```

### Test tích hợp với ClamAV, SeaweedFS, PostgreSQL + Hasura thật

Đi trọn luồng: tải lên → bản ghi `core.files` → tải xuống; lãnh đạo chỉ xem được sau khi tệp gắn vào văn bản;
thuê ước khác nhận 404; EICAR bị chặn và nằm trong chuỗi băm của sổ kiểm toán; thuê ước lạ không để lại
tệp mồ côi; tìm kiếm trả đúng văn bản từng vai trò được đọc. Hasura dựng bằng `db/tests/stack.sh` (schema và quyền lấy từ `db/` của cây mã nguồn) với khóa
công khai RS256, vì svc-files chỉ nhận token RS256 như của Keycloak.

```bash
K=$(mktemp -d)
openssl genrsa -out $K/it.pem 2048 && openssl rsa -in $K/it.pem -pubout -out $K/it.pub
docker run -d --name moc-it-clamav -p 127.0.0.1:13310:3310 clamav/clamav:1.5.4
docker run -d --name moc-it-seaweedfs -p 127.0.0.1:18333:8333 chrislusf/seaweedfs:4.48 \
  server -s3 -dir=/data -ip.bind=0.0.0.0 -volume.max=0 -master.volumeSizeLimitMB=512
docker run -d --name moc-it-meili -p 127.0.0.1:17700:7700 -e MEILI_ENV=production -e MEILI_NO_ANALYTICS=true \
  -e MEILI_MASTER_KEY=it-meili-master-key-0123456789 getmeili/meilisearch:v1.54.3
MOC_IT_JWT_PUBLIC_KEY=$K/it.pub ../../db/tests/stack.sh up
# đợi ClamAV nạp xong chữ ký (~1 phút, `docker ps` báo healthy)
MOC_IT=1 MOC_IT_JWT_PRIVATE_KEY=$K/it.pem .venv/bin/python -m pytest -m integration
../../db/tests/stack.sh down && docker rm -f moc-it-clamav moc-it-seaweedfs moc-it-meili && rm -r $K
```

Test dùng chuỗi kiểm thử chuẩn EICAR (không phải mã độc thật), ghép từ hai nửa để chính tệp mã nguồn
không bị phần mềm diệt virus chặn.

### Đổi phụ thuộc

Sửa `pyproject.toml`, rồi sinh lại hai tệp khóa và cập nhật `DEPENDENCIES.md` trong cùng PR:

```bash
uv pip compile pyproject.toml --universal --python-version 3.12 --generate-hashes --no-header -o requirements.txt
uv pip compile pyproject.toml --extra dev --universal --python-version 3.12 --generate-hashes --no-header -o requirements-dev.txt
```

## Ghi chú khi đưa vào Compose (#13)

- **SeaweedFS**: mỗi bucket là một *collection*, master tạo sẵn nhiều volume cho nó. Với `-volume.max`
  quá nhỏ, mọi lệnh ghi lỗi `No writable volumes and no free volumes left`. Dùng `-volume.max=0` (tự tính
  theo đĩa) và `-master.volumeSizeLimitMB` vừa phải.
- **SeaweedFS** gắn vào IP của container lúc khởi động; container nối nhiều mạng thì thêm
  `-ip.bind=0.0.0.0`, nếu không các mạng khác không gọi được cổng S3.
- **SeaweedFS** chạy `server -s3` không kèm cấu hình danh tính thì S3 **không kiểm khóa**. Chấp nhận được khi
  SeaweedFS chỉ nằm trong mạng nội bộ; bản triển khai phải nạp tệp danh tính S3 (`-s3.config`).
- **ClamAV**: giữ volume `/var/lib/clamav`; image `clamav/clamav:1.5.4` đã kèm sẵn chữ ký nên quét được ngay
  sau khi clamd nạp xong (đo trên máy dev: khoảng 1 phút, 3,6 triệu chữ ký).
- **Meilisearch**: `MEILI_ENV=production`, `MEILI_MASTER_KEY` (≥ 16 byte, từ `.env`), `MEILI_NO_ANALYTICS=true`,
  volume `/meili_data`. Mất volume cũng không sao: svc-files khởi động lại là đồng bộ lại toàn bộ.
- **svc-files** cần `HASURA_URL`, `HASURA_ADMIN_SECRET`, `MOC_OIDC_ISSUER`, `MOC_OIDC_JWKS_URL` giống Hasura,
  `MEILISEARCH_API_KEY` giống `MEILI_MASTER_KEY`; `depends_on` Hasura. Đã chạy thử image với JWKS thật (không dùng khóa tĩnh): tải lên, tải xuống, chặn
  EICAR, `X-Request-Id` đi tới sổ kiểm toán.
