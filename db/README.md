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
| Quyền Hasura cho 6 vai trò, cách ly thuê ước | **Xong** — 52 test |
| Sổ kiểm toán chuỗi băm: trigger trên mọi bảng nghiệp vụ, `core.audit_verify()` | **Xong** (F2.12 làm sớm); job neo hash ra ngoài CSDL ở Phase 2 |
| `core.users` (danh bạ đồng bộ từ Keycloak), hàm `office.register_incoming` (vào sổ trong một giao dịch) | **Xong** — 10 test |
| `metadata/actions.graphql`, `actions.yaml`: `registerIncoming`, `submitOutgoing`, `myTasks`, `completeTask` → svc-workflow | **Xong** |
| Văn bản đi: cột `body`, thông tin in trên văn bản ở `core.tenants`, hàm `office.number_outgoing` (cấp số đi, ký hiệu theo NĐ 30 trong một giao dịch), khung nhìn `office.issued_documents` cho cổng xác thực | **Xong** — 18 test |
| `core.notifications` (thông báo từng người, F2.5): mỗi người chỉ đọc và đánh dấu đã đọc thông báo của mình, chống gửi trùng theo khóa | **Xong** — 6 test |
| `office.case_files` (hồ sơ, nộp lưu) và các view báo cáo | Phase 2–3 |

## Vai trò

| Vai trò | Đọc | Ghi trực tiếp (không qua Action) |
|---|---|---|
| `clerk` — văn thư | Mọi văn bản của thuê ước | Thêm văn bản đến (`received`), sửa khi còn `received`; gắn và gỡ tệp mình tải lên |
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
- Kiểm tra: `select * from core.audit_verify();` — không trả dòng nào là chuỗi nguyên vẹn; ngược lại chỉ ra
  `audit_id` và loại lỗi (`hash`, `prev_hash`, `gap`, `head`). Superuser tắt trigger để sửa lén vẫn bị phát
  hiện (có test); sửa rồi tính lại cả chuỗi thì chỉ bắt được khi đối chiếu với hash đã neo ra ngoài
  (job neo — Phase 2).

## Thêm hoặc đổi schema

1. Tạo thư mục mới `migrations/default/<mili giây hiện tại>_<tên>/` với `up.sql` và `down.sql`
   (`date +%s%3N` cho số phiên bản). **Không sửa migration đã merge** — viết migration mới.
2. Bảng mới: thêm tệp `metadata/databases/default/tables/<schema>_<bảng>.yaml` và một dòng trong
   `tables.yaml`. Bảng nghiệp vụ có `tenant_id` thì mọi quyền đều lọc `tenant_id = X-Hasura-Tenant-Id`, và
   gắn `core.audit()`.
3. Đặt tên cho ràng buộc `check` (vd `documents_in_identity`): Hasura trả tên này trong lỗi, giao diện dịch
   thành câu tiếng Việt.
4. Sửa `docs/mo-hinh-du-lieu.md` trong cùng PR, thêm test vào `tests/`.

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
