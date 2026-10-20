# db — schema PostgreSQL và metadata Hasura

Dữ liệu có cấu trúc của Mộc (F1.3): schema `core` dùng chung cho mọi ứng dụng, schema `office` của ứng dụng
Văn phòng điện tử, cùng quyền đọc ghi theo vai trò và thuê ước. Mô hình và lý do của từng bảng:
[`docs/mo-hinh-du-lieu.md`](../docs/mo-hinh-du-lieu.md). Chủ: mảng AI · issue #18.

| Thư mục | Nội dung |
|---|---|
| `migrations/default/<phiên bản>_<tên>/` | `up.sql`, `down.sql` — Hasura áp theo thứ tự phiên bản |
| `metadata/` | Metadata Hasura (định dạng v3): bảng được theo dõi, quan hệ, quyền |
| `tests/` | Test trên PostgreSQL + Hasura thật: ràng buộc, quyền, sổ kiểm toán |

Image `hasura/graphql-engine:v2.51.0-ce.cli-migrations-v3` tự áp `migrations/` và `metadata/` mỗi lần khởi
động, nên trạng thái CSDL luôn đi theo git. Console tắt; không sửa schema bằng tay trên server.

## Đã có

| Phần | Trạng thái |
|---|---|
| `core.tenants`, `core.files`, `core.audit_log` (+ `audit_head`, `audit_anchors`) | **Xong** |
| `office.departments`, `document_types` (28 loại theo NĐ 30), `registers`, `documents`, `document_files`, `document_acl`, `assignments`, `document_events` | **Xong** |
| Quyền Hasura cho 6 vai trò, cách ly thuê ước | **Xong** — 38 test |
| Sổ kiểm toán chuỗi băm (F2.12): trigger trên mọi bảng nghiệp vụ, `core.audit_verify()`; mốc neo `core.audit_anchors`; lãnh đạo, quản trị đơn vị xem sổ của đơn vị qua trường `overview` (không lộ nội dung; thấy năm, số dòng của lần in sổ đăng ký; mẫu mã độc, cỡ của tệp bị kiểm dịch chặn) | **Xong** — 23 test, gồm sửa lén khi tắt trigger, viết lại cả chuỗi, cắt đuôi, đổi hash văn bản |
| `core.users` (danh bạ đồng bộ từ Keycloak), hàm `office.register_incoming` (vào sổ trong một giao dịch) | **Xong** — 10 test |
| `metadata/actions.graphql`, `actions.yaml`: `receiveIncoming`, `registerIncoming`, `submitOutgoing`, `myTasks`, `completeTask` → svc-workflow | **Xong** |
| Poka-yoke lớp 3 cho văn bản đến (F2.2): `documents_in_symbol`, `documents_in_issuer`, `documents_in_summary`, `documents_in_dates` — cùng quy tắc với `schemas/van-ban-den.json` (độ dài, khoảng trắng, ký tự ẩn, dạng NFC, năm 1900+); migration dọn trước dữ liệu cũ sửa được mà không đổi nghĩa | **Xong** — 43 test chạy chung bộ ca thử với form và svc-workflow, chèn thẳng bằng quyền quản trị |
| Văn bản đi: cột `body`, thông tin in trên văn bản ở `core.tenants`, hàm `office.number_outgoing` (cấp số đi, ký hiệu theo NĐ 30 trong một giao dịch), khung nhìn `office.issued_documents` cho cổng xác thực | **Xong** — 18 test |
| `core.file_texts` (lớp chữ của PDF để tìm theo nội dung, F2.7): không vai trò người dùng nào đọc được, xóa tệp thì xóa theo, không gắn sổ kiểm toán; tệp của văn bản hạn chế không có chữ (trigger) | **Xong** — 10 test |
| `core.notifications` (thông báo từng người, F2.5): mỗi người chỉ đọc và đánh dấu đã đọc thông báo của mình, chống gửi trùng theo khóa | **Xong** — 6 test |
| `office.case_files` (hồ sơ, nộp lưu) và các view báo cáo | Phase 2–3 |

## Vai trò

| Vai trò | Đọc | Ghi trực tiếp (không qua Action) |
|---|---|---|
| `clerk` — văn thư | Mọi văn bản của thuê ước | — (văn bản đến kèm tệp chỉ thêm qua Action `receiveIncoming`: svc-workflow kiểm theo `schemas/van-ban-den.json`) |
| `staff` — chuyên viên | Văn bản mình tạo, được giao cho mình, văn bản đi của phòng mình | Thêm dự thảo văn bản đi; sửa khi còn `draft`/`returned` và là của mình; gắn và gỡ tệp |
| `manager` — lãnh đạo phòng | Văn bản phòng mình soạn hoặc được giao cho phòng mình | — |
| `director` — lãnh đạo đơn vị | Mọi văn bản của thuê ước | — |
| `tenant_admin` — quản trị đơn vị | Không đọc văn bản; đọc phòng ban, sổ, danh mục | Thêm, sửa phòng ban |
| `service` — `svc-workflow`, `svc-files` | Mọi dòng của thuê ước trong yêu cầu | Trạng thái, số, giao việc, tệp, dòng thời gian, sổ kiểm toán |
| `verifier` — `svc-files` (cổng xác thực) | Chỉ khung nhìn `office.issued_documents`, tối đa một dòng mỗi lần | — |

Văn bản hạn chế (`restricted`) chỉ người tạo và người có tên trong `office.document_acl` đọc được, kể cả
`clerk` và `director`. Quy tắc đọc viết một lần trong hàm SQL `office.document_visible`, Hasura gắn thành
trường `visible` của `office_documents`; tệp, giao việc, dòng thời gian lọc theo `document.visible`.

> ⚠️ **Không bao giờ để vai trò `admin` lọt vào token.** `admin` là vai trò có sẵn của Hasura và bỏ qua
> mọi quyền — đã thử: token có `x-hasura-default-role: admin` đọc được văn bản và sổ kiểm toán của **mọi**
> thuê ước. Quản trị đơn vị là `tenant_admin`; mapper của realm (#21) chỉ đưa 5 vai trò nghiệp vụ vào claim.

### Claim cần có trong token

Keycloak đưa vào claim `https://hasura.io/jwt/claims`:

| Claim | Ghi chú |
|---|---|
| `x-hasura-allowed-roles`, `x-hasura-default-role` | Thuộc tính người dùng `moc_role` (`auth/README.md`) |
| `x-hasura-user-id` | `sub` |
| `x-hasura-tenant-id` | UUID của `core.tenants`; thiếu thì không thấy gì |
| `x-hasura-department-id` | UUID của `office.departments`; bắt buộc với `staff`, `manager` — `staff` thiếu claim này không tạo được dự thảo |

Hasura chỉ tin claim trong token: tiêu đề `X-Hasura-Tenant-Id` do trình duyệt gửi bị bỏ qua (có test).

### Dịch vụ gọi Hasura

`svc-workflow`, `svc-files` gửi `X-Hasura-Admin-Secret` kèm `X-Hasura-Role: service`,
`X-Hasura-Tenant-Id` (lấy từ phiên của Action hoặc token người dùng), `X-Hasura-User-Id` (người thực hiện,
ghi vào sổ kiểm toán) và `X-Hasura-Request-Id` (lấy từ `X-Request-Id` do APISIX gắn). Thiếu
`X-Hasura-Tenant-Id` thì yêu cầu bị từ chối — dịch vụ không lỡ tay đọc lẫn thuê ước.

## Sổ kiểm toán chuỗi băm

- Trigger `core.audit()` ghi mỗi lần thêm, sửa, xóa dòng của bảng nghiệp vụ: ai, lúc nào, cột nào đổi
  từ giá trị nào sang giá trị nào. Người thực hiện lấy từ phiên Hasura; dịch vụ ghi thẳng CSDL thì
  `set local moc.actor = '…'` (và `moc.actor_kind`, `moc.request_id`) trước khi ghi.
- Mỗi dòng mang `hash = sha256(prev_hash ‖ các trường của dòng)`. Đầu chuỗi nằm ở `core.audit_head`;
  khóa dòng này khiến các giao dịch ghi sổ xếp hàng, nên thứ tự `id` trùng thứ tự chuỗi (đã thử 20 yêu
  cầu ghi song song).
- `core.audit_log` chỉ được ghi thêm: sửa, xóa, `truncate` đều bị trigger chặn.
- Kiểm nhanh trong CSDL: `select * from core.audit_verify();` — không trả dòng nào là chuỗi nguyên vẹn; ngược
  lại chỉ ra `audit_id` và loại lỗi (`hash`, `prev_hash`, `gap`, `head`). Superuser tắt trigger để sửa một dòng
  vẫn bị phát hiện.
- **Neo ra ngoài CSDL.** Superuser sửa một dòng rồi tính lại hash cả chuỗi phía sau thì `core.audit_verify()`
  báo nguyên vẹn (có test cho chính trường hợp này). Vì vậy `svc-files` định kỳ chép đầu chuỗi ra bucket lạnh
  `moc-cold` bật S3 Object Lock, chế độ COMPLIANCE: trong hạn giữ không ai xóa, ghi đè hay rút ngắn hạn được,
  kể cả khóa quản trị của kho (`services/svc-files/README.md`). `core.audit_anchors` là bản tra cứu các lần neo.
- **Kiểm đầy đủ: `make audit`** (`python3 scripts/moc.py audit verify`, chạy được cả trong thư mục cài). Lệnh
  tự tính lại chuỗi bên ngoài CSDL (không tin `core.audit_verify()`, vì superuser sửa được cả hàm), so hash của
  dòng tại mỗi mốc neo trong bucket, và so `content_sha256` của văn bản với giá trị lần cuối ghi vào sổ. Viết
  lại chuỗi thì lệnh chỉ ra khoảng dòng bị sửa, nằm giữa mốc cuối còn khớp và mốc đầu bị lệch. Mọi câu đọc nằm
  trong một giao dịch `REPEATABLE READ`, nên dòng mới ghi trong lúc kiểm không gây báo nhầm. Thoát `0` khi nguyên
  vẹn, `1` khi có dòng bị sửa, `2` khi chưa đủ bằng chứng: chưa có mốc nào, mốc mới nhất quá cũ, bucket không
  khóa ghi, hay bảng `core.audit_anchors` ghi một mốc mà bucket không có.
  `python3 scripts/moc.py audit anchor --to <tệp>` neo ngay và ghi thêm mốc vào một tệp, để chép ra ngoài máy
  chủ; kiểm cả tệp đó: `audit verify --anchors <tệp>`.
- **Màn xem sổ** cho `director`, `tenant_admin`: đọc dòng sổ của đơn vị mình, không đọc được cột `diff`, chỉ đọc
  trường `overview` (hàm `core.audit_overview`): cột chứa nội dung (trích yếu, nội dung, tên tệp, ý kiến…) có
  tên nhưng giá trị null, để sổ không lộ văn bản hạn chế mà lãnh đạo không được đọc.

## Thêm hoặc đổi schema

1. Tạo thư mục mới `migrations/default/<mili giây hiện tại>_<tên>/` với `up.sql` và `down.sql`
   (`date +%s%3N` cho số phiên bản). **Không sửa migration đã merge** — viết migration mới.
2. Bảng mới: thêm tệp `metadata/databases/default/tables/<schema>_<bảng>.yaml` và một dòng trong
   `tables.yaml`. Bảng nghiệp vụ có `tenant_id` thì mọi quyền đều lọc `tenant_id = X-Hasura-Tenant-Id`, và
   gắn `core.audit()`.
3. Đặt tên cho ràng buộc `check` (vd `documents_in_identity`): Hasura trả tên này trong lỗi, svc-workflow và
   giao diện dịch thành câu tiếng Việt. Ràng buộc cho dữ liệu người dùng nhập theo form phải khớp schema ở
   `schemas/` (xem `schemas/README.md`), kèm ca thử trong `schemas/*.cases.json`.
4. Thêm ràng buộc lên bảng đã có dữ liệu: dọn trước những gì sửa được mà không đổi nghĩa, rồi
   `add constraint … not valid` và `validate constraint` trong khối bắt `check_violation`, như migration
   `1792281600800_intake_rules`. Dữ liệu cũ còn sai thì migration vẫn chạy, cảnh báo trong nhật ký Hasura kèm mã
   văn bản. Ràng buộc vẫn chặn mọi lần ghi — **kể cả sửa chính dòng sai đó** (vào sổ, đổi trạng thái…), nên phải
   sửa nội dung dòng đó bằng quyền quản trị rồi chạy `alter table … validate constraint <tên>`.
5. Sửa `docs/mo-hinh-du-lieu.md` trong cùng PR, thêm test vào `tests/`.

## Test

Cần Docker, `curl`, Python ≥ 3.12.

```bash
db/tests/stack.sh up                    # PostgreSQL (trong RAM) + Hasura ở 127.0.0.1:18080, nạp db/ hiện tại
cd db/tests
uv venv && uv pip install -r requirements.txt     # hoặc: python -m venv .venv && .venv/bin/pip install -r requirements.txt
MOC_IT=1 .venv/bin/python -m pytest
cd ../.. && db/tests/stack.sh down
```

Không đặt `MOC_IT=1` thì test tự bỏ qua. Chạy lại nhiều lần trên cùng CSDL được (mỗi lần dùng thuê ước mới);
`stack.sh reset` để bắt đầu từ CSDL trống. Token trong test ký HS256 bằng khóa cố định chỉ dùng cho test —
khối claim giống hệt token Keycloak. `MOC_IT_JWT_PUBLIC_KEY=<tệp PEM> db/tests/stack.sh up` dựng Hasura kiểm
token RS256 thay cho HS256 — dùng cho test đầu-cuối của `svc-files` (`services/svc-files/README.md`). Đổi phiên bản pytest: sửa dòng dưới rồi sinh lại tệp khóa.

```bash
echo "pytest>=9.1,<10" | uv pip compile - --universal --python-version 3.12 --generate-hashes --no-header -o db/tests/requirements.txt
```

## Cấu hình trong Compose

Khối `hasura` trong `docker-compose.yml` ở gốc repo (rút gọn):

```yaml
hasura:
  image: hasura/graphql-engine:v2.51.0-ce.cli-migrations-v3
  volumes:
    - ./db/migrations:/hasura-migrations:ro
    - ./db/metadata:/hasura-metadata:ro
  environment:
    HASURA_GRAPHQL_DATABASE_URL: postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
    HASURA_GRAPHQL_METADATA_DATABASE_URL: postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
    HASURA_GRAPHQL_ADMIN_SECRET: ${HASURA_ADMIN_SECRET:?}
    # iss là URL công khai; JWKS lấy qua mạng nội bộ
    HASURA_GRAPHQL_JWT_SECRET: '{"jwk_url":"${MOC_OIDC_JWKS_URL}","issuer":"${MOC_OIDC_ISSUER}","claims_namespace":"https://hasura.io/jwt/claims"}'
    HASURA_GRAPHQL_ENABLED_APIS: graphql,metadata
    HASURA_GRAPHQL_ENABLE_CONSOLE: "false"
    HASURA_GRAPHQL_DEV_MODE: "false"
    HASURA_GRAPHQL_ENABLE_TELEMETRY: "false"
    HASURA_GRAPHQL_INFER_FUNCTION_PERMISSIONS: "false"   # quyền gọi hàm khai tường minh
    MOC_WORKFLOW_URL: http://svc-workflow:8000           # handler của Actions
    MOC_ACTION_SECRET: ${MOC_ACTION_SECRET:?}
    # KHÔNG đặt HASURA_GRAPHQL_UNAUTHORIZED_ROLE: không có vai trò ẩn danh
  depends_on:
    postgres: {condition: service_healthy}
```

- `MOC_OIDC_ISSUER`, `MOC_OIDC_JWKS_URL` dùng chung với `svc-files`; thêm `HASURA_ADMIN_SECRET` vào `.env.example`.
- Không mở cổng Hasura ra máy chủ. APISIX (#14) chỉ chuyển `/v1/graphql`; `/v1/metadata`, `/v2/query`,
  `/v1/query`, `/console` phải bị chặn — `metadata` vẫn bật vì image cần nó để tự áp migration lúc khởi động.
- Hiện Hasura nối CSDL bằng tài khoản chủ của image `postgres` (superuser). Phase 3: tách vai trò CSDL riêng
  cho Hasura không có quyền superuser, để không ai qua Hasura tắt được trigger của sổ kiểm toán.
