# Tài liệu API của Mộc

Mọi ứng dụng gọi lõi qua **một cổng duy nhất**: APISIX ở `MOC_PUBLIC_URL` (máy phát triển:
`http://localhost:8080`). Ứng dụng có thể là Văn phòng điện tử, một ứng dụng Tầng 2 khác, script hay tác tử AI.
Có hai loại API:

- **GraphQL** (Hasura) cho dữ liệu có cấu trúc và thao tác nghiệp vụ.
- **REST** (`svc-files`) cho tệp, tìm kiếm, bản xem trước văn bản đi và cổng xác thực.

Dù gọi theo cách nào, người gọi cũng phải có token Keycloak, và đơn vị lẫn vai trò luôn lấy từ token. Ngoại lệ
duy nhất là cổng xác thực văn bản đã phát hành (`/api/verify`), ai cũng gọi được.

## Tệp trong thư mục này

| Tệp | Nội dung |
|---|---|
| [`graphql/<vai trò>.graphql`](graphql/) | Schema GraphQL mà từng vai trò thấy: `clerk`, `staff`, `manager`, `director`, `tenant_admin` |
| [`thao-tac-theo-vai-tro.md`](thao-tac-theo-vai-tro.md) | Bảng vai trò × truy vấn, thao tác ghi |
| [`openapi/svc-files.json`](openapi/svc-files.json) | OpenAPI 3.1 của API tệp và tìm kiếm |
| [`openapi/svc-workflow.json`](openapi/svc-workflow.json) | OpenAPI 3.1 của API nội bộ chạy Hasura Actions, chỉ Hasura gọi |

Trừ tệp README này, mọi tệp trên **sinh tự động** từ hệ thống đang chạy:

- Schema GraphQL lấy qua cổng, bằng token của tài khoản mẫu thuộc từng vai trò. Nhờ vậy nó đúng là những gì một
  ứng dụng nhận được.
- OpenAPI do FastAPI sinh từ mã của dịch vụ.

Đổi schema, quyền hay endpoint thì sinh lại rồi commit cùng thay đổi:

```bash
make up && make seed && make api-docs
```

CI dựng hệ thống từ mã nguồn rồi chạy `scripts/api_docs.py --check`. Lệnh này báo lỗi nếu `docs/api/` lệch với
hệ thống vừa dựng, nên tài liệu không cũ đi so với mã. Muốn xem dạng trang web, mở các tệp OpenAPI bằng công cụ
đọc OpenAPI 3.1, ví dụ Swagger UI hay Redoc chạy cục bộ. Các tệp `.graphql` là SDL chuẩn, công cụ GraphQL nào
cũng nạp được.

## Đường dẫn qua cổng

| Đường dẫn | Đến | Token |
|---|---|---|
| `/realms/moc/…` | Keycloak: đăng nhập, cấp và làm mới token, JWKS | — |
| `POST /v1/graphql` | Hasura | Bắt buộc |
| `POST /api/files`, `GET /api/files/{id}`, `GET /api/search`, `GET /api/documents/{id}/preview` | `svc-files` | Bắt buộc |
| `GET /api/verify/{mã}`, `GET /api/verify?sha256=…` | `svc-files`: cổng xác thực | Không; giới hạn theo IP |
| `GET /realtime` (WebSocket) | Centrifugo: thông báo đẩy (§4) | Gửi trong lệnh `connect` đầu tiên |
| `GET /` và trang tĩnh | Giao diện Văn phòng điện tử | — |

Cổng trả `404` cho các đường còn lại:

- API quản trị và nội bộ: `/v1/metadata`, `/v2/query`, `/console`, `/admin`, `/flowable-rest/*`, `/healthz`,
  `/metrics`, …
- WebSocket tới Hasura, nên chưa dùng được `subscription` của GraphQL; thông báo đẩy đi qua `/realtime` (§4).
  Danh sách đầy đủ ở [`gateway/apisix.yaml`](../../gateway/apisix.yaml).

Token thiếu, sai chữ ký hoặc hết hạn bị cổng trả `401` trước khi tới Hasura hay `svc-files`. Hai dịch vụ này
vẫn kiểm lại token (zero-trust).

## 1. Lấy token

Keycloak là nhà cung cấp OpenID Connect:

- issuer: `${MOC_PUBLIC_URL}/realms/moc`
- tài liệu khám phá: `/realms/moc/.well-known/openid-configuration`

Access token sống 5 phút; làm mới bằng refresh token.

- **Ứng dụng trên trình duyệt** dùng Authorization Code + PKCE (S256) với client công khai, như client
  `app-office`.
  - Muốn thêm một ứng dụng Tầng 2: thêm client vào [`auth/realm/moc-realm.json`](../../auth/realm/moc-realm.json)
    theo mẫu `app-office`. Giữ nguyên `protocolMappers` để token có claim của Hasura; đổi `clientId` và
    `redirectUris`.
  - Văn thư, lãnh đạo và quản trị đơn vị phải nhập mã TOTP sau mật khẩu ([`auth/README.md`](../../auth/README.md)).
- **Script trên máy phát triển** dùng client `moc-cli`, luồng mật khẩu, không hỏi TOTP. Client này phải tắt trên
  server thật (`MOC_CLI_CLIENT_ENABLED=false`).

```bash
export MOC=http://localhost:8080 MOC_DEMO_PASSWORD='…giá trị trong .env…'
TOKEN=$(curl -s "$MOC/realms/moc/protocol/openid-connect/token" -d grant_type=password -d client_id=moc-cli \
  -d username=vanthu --data-urlencode "password=$MOC_DEMO_PASSWORD" | jq -r .access_token)
```

Token mang claim `https://hasura.io/jwt/claims` với người dùng, đơn vị, phòng và vai trò
([`db/README.md`](../../db/README.md#claim-cần-có-trong-token)). Hasura chỉ tin claim trong token: tiêu đề
`X-Hasura-Tenant-Id` do client tự gửi bị bỏ qua. Mỗi token chỉ mang một vai trò.

## 2. GraphQL: `POST /v1/graphql`

Mỗi vai trò thấy một schema riêng ([`graphql/`](graphql/)), có quyền đến từng dòng và từng cột. Tên trường theo
quy ước của Hasura:

- truy vấn: `<schema>_<bảng>`, kèm `_by_pk` và `_aggregate`;
- ghi: `insert_…`, `update_…`, `delete_…`.

Gọi một trường không có trong schema của vai trò thì nhận lỗi `validation-failed`, chẳng hạn quản trị đơn vị đọc
`office_documents`.

```bash
gql() { curl -s "$MOC/v1/graphql" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d "$1"; }

# 5 văn bản mới nhất mà người gọi được đọc
gql '{"query": "{ office_documents(limit: 5, order_by: {created_at: desc}) { id symbol summary status urgency } }"}'

# hộp việc của người gọi
gql '{"query": "{ myTasks { id name form_key document_id due_on urgency } }"}'
```

Thao tác nghiệp vụ là **Hasura Action**: Hasura kiểm token và vai trò rồi chuyển cho `svc-workflow`. Mọi
Action đều gọi lại được sau lỗi mạng mà không cấp số hai lần.

| Action | Ai gọi | Làm gì |
|---|---|---|
| `registerIncoming(documentId)` | `clerk` | Vào sổ văn bản đến: cấp số đến liên tiếp, khởi chạy quy trình `van-ban-den` |
| `submitOutgoing(documentId, signerId)` | `staff` (người soạn) | Trình dự thảo văn bản đi cho lãnh đạo phòng duyệt, chọn lãnh đạo đơn vị ký; trình lại sau khi bị trả lại |
| `myTasks` | `clerk`, `staff`, `manager`, `director` | Hộp việc: việc giao đích danh và việc của nhóm vai trò, khẩn xếp trước |
| `completeTask(taskId, outcome, data)` | Người được giao việc | Hoàn thành việc; `data` kiểm theo loại việc |

Các loại việc, `outcome` và `data` của từng loại có ở [`docs/mo-hinh-du-lieu.md`](../mo-hinh-du-lieu.md) §4.2.
Luồng văn bản đến của văn thư, giống `make smoke`:

```bash
# 1. tải công văn lên (§3), lấy id tệp
FILE=$(curl -s "$MOC/api/files" -H "Authorization: Bearer $TOKEN" -F file=@cong-van.pdf | jq -r .id)

# 2. nhập văn bản đến kèm tệp: trạng thái received
gql '{"query": "mutation ($o: office_documents_insert_input!) { insert_office_documents_one(object: $o) { id status } }",
      "variables": {"o": {"type_code": "CV", "symbol": "123/ĐHCN-ĐT", "issuer_name": "Trường Đại học Công nghiệp",
        "issued_on": "2026-10-19", "urgency": "khan", "summary": "Về việc rà soát chương trình đào tạo",
        "files": {"data": [{"file_id": "'"$FILE"'", "role": "main"}]}}}}'

# 3. vào sổ: cấp số đến, lãnh đạo đơn vị nhận việc "vbden.chiDao" trong hộp việc
gql '{"query": "mutation ($id: uuid!) { registerIncoming(documentId: $id) { register_number } }",
      "variables": {"id": "<id ở bước 2>"}}'
```

Văn bản đi của chuyên viên: soạn dự thảo (`insert_office_documents_one` với `body`, `recipients`) → tải bản xem
trước (§3) → `submitOutgoing` → lãnh đạo phòng `completeTask` việc `vbdi.duyetPhong` → người ký `vbdi.duyetDonVi`
→ văn thư `vbdi.phatHanh` với `outcome: "issue"`. Bước cuối cấp số đi, dựng PDF có mã QR và gắn vào văn bản với
vai trò `issued`; `verify_code` và `content_sha256` của văn bản là mã tra cứu và băm của tệp đó.

```bash
gql '{"query": "mutation ($d: uuid!, $s: String!) { submitOutgoing(documentId: $d, signerId: $s) { status } }",
      "variables": {"d": "<id dự thảo>", "s": "<id lãnh đạo đơn vị trong core_users>"}}'
```

**Lỗi.** Hasura trả HTTP 200 kèm `errors`. Lỗi của Action có `extensions.code` do `svc-workflow` đặt, ví dụ
`task_taken`, `not_your_task`, `wrong_status`; `message` là câu tiếng Việt hiển thị được cho người dùng:

```json
{"errors": [{"message": "Việc không còn — có thể đã có người xử lý", "extensions": {"code": "task_not_found"}}]}
```

## 3. Tệp và tìm kiếm: `svc-files`

Mô tả đầy đủ (tham số, kiểu trả về, mã lỗi) nằm trong [`openapi/svc-files.json`](openapi/svc-files.json).

| Đường dẫn | Làm gì |
|---|---|
| `POST /api/files` (multipart, trường `file`) | Quét ClamAV, sạch mới lưu → `201 {id, filename, mime_type, size_bytes, sha256, scanned_at}`. Tệp nhiễm → `422`, không lưu, ghi sổ kiểm toán |
| `GET /api/files/{id}` | Tải về nếu người gọi được xem; không có tệp và không được xem đều trả `404` |
| `GET /api/search?q=…` | Tìm theo số ký hiệu, trích yếu, cơ quan ban hành; gõ không dấu được; chỉ trả văn bản người gọi được đọc |
| `GET /api/documents/{id}/preview` | PDF đúng thể thức NĐ 30 của dự thảo văn bản đi, chưa có số, in chữ "DỰ THẢO"; văn bản đã phát hành thì tải bản phát hành |
| `GET /api/verify/{mã}` | **Không cần token.** Văn bản đã phát hành có mã tra cứu này: số ký hiệu, ngày, cơ quan ban hành, SHA-256; trích yếu chỉ khi công khai |
| `GET /api/verify?sha256=…` | **Không cần token.** Như trên, tra theo SHA-256 của tệp PDF (trình duyệt tự tính, tệp không tải lên) |

```bash
curl -s -OJ "$MOC/api/files/$FILE" -H "Authorization: Bearer $TOKEN"
curl -s -G "$MOC/api/search" -H "Authorization: Bearer $TOKEN" --data-urlencode 'q=tuyen sinh' --data-urlencode limit=10

# cổng xác thực, không đăng nhập: theo mã in cạnh mã QR, hoặc theo băm của tệp nhận được
curl -s "$MOC/api/verify/ABCDE-23456"
curl -s "$MOC/api/verify?sha256=$(sha256sum cong-van-nhan-duoc.pdf | cut -d' ' -f1)"
```

Trang `/xac-thuc/<mã>` của giao diện (mã QR trên văn bản trỏ tới đây) gọi đúng hai đường trên; ứng dụng khác
cũng dùng được để tự kiểm văn bản nhận được.

Tệp được gắn vào văn bản bằng GraphQL (`files` khi tạo văn bản, hoặc `insert_office_document_files_one`), không
qua REST. Lỗi của `svc-files` có dạng `{"detail": {"code": "…", "message": "…"}}`.

## 4. Thông báo: `core_notifications` và `/realtime`

Sau mỗi bước, người phải làm tiếp nhận một thông báo: việc mới (`task.assigned`), quá hạn (`task.overdue`), báo
lãnh đạo khi quá hạn hai lần (`task.escalated`), văn bản đã phát hành (`document.issued`), đã báo kết quả xử lý
(`document.processed`), văn bản đến qua hạn giải quyết (`document.overdue`). Ai nhận gì: [`docs/mo-hinh-du-lieu.md`](../mo-hinh-du-lieu.md) §5.

Thông báo lưu ở bảng `core_notifications`; mỗi người chỉ đọc được của mình và chỉ sửa được `read_at`:

```graphql
{
  core_notifications(order_by: {id: desc}, limit: 20) { id kind document_id data created_at read_at }
  core_notifications_aggregate(where: {read_at: {_is_null: true}}) { aggregate { count } }
}
mutation ($at: timestamptz!) {
  update_core_notifications(where: {read_at: {_is_null: true}}, _set: {read_at: $at}) { affected_rows }
}
```

`data` giữ những gì cần để hiện câu thông báo (`form_key`, `summary`, `symbol`, `note`, `assignee_name`…); câu
chữ do ứng dụng dựng, theo ngôn ngữ của người dùng.

Muốn nhận ngay khi có, mở WebSocket tới `/realtime` (Centrifugo, [giao thức JSON](https://centrifugal.dev/docs/transports/client_protocol))
và gửi access token Keycloak trong lệnh đầu tiên. Centrifugo tự kiểm token và đưa kết nối vào kênh riêng
`personal:#<sub>` của người đó; không đăng ký được kênh nào khác, không gửi tin được.

```text
→ {"id":1,"connect":{"token":"<access token>"}}
← {"id":1,"connect":{"client":"…","expires":true,"ttl":299,"ping":25,"pong":true,"subs":{"personal:#<sub>":{}}}}
← {"push":{"channel":"personal:#<sub>","pub":{"data":{"id":42,"kind":"task.assigned","document_id":"…","data":{…},"created_at":"…"}}}}
← {}                                   ping mỗi 25 giây → trả lời {}
→ {"id":2,"refresh":{"token":"<token mới>"}}   trước khi hết ttl
```

Token sai thì Centrifugo đóng kết nối với mã `3500`; trang khác tên miền (`Origin`) không mở được kết nối. Mở
kết nối giới hạn theo địa chỉ IP (`MOC_RATE_REALTIME_PER_MIN`). Tin đẩy lúc mất kết nối không gửi lại: nối lại
thì đọc lại `core_notifications`. Giao diện Mộc làm đúng như vậy trong
[`apps/office/app/composables/useRealtime.ts`](../../apps/office/app/composables/useRealtime.ts).

## 5. Quy ước chung

- **`X-Request-Id`**: cổng gắn vào mọi phản hồi. Mã này cũng có trong nhật ký của dịch vụ và cột `request_id`
  của sổ kiểm toán; gửi kèm khi báo lỗi.
- **Giới hạn tốc độ**, vượt thì trả `429`:
  - Đăng nhập và cấp token: theo địa chỉ IP, `MOC_RATE_LOGIN_PER_MIN` (mặc định 60/phút).
  - GraphQL và tệp: theo token, `MOC_RATE_API_PER_MIN` (mặc định 300/phút).
  - Cổng xác thực: theo địa chỉ IP, `MOC_RATE_VERIFY_PER_MIN` (mặc định 30/phút).
  - Mở kết nối `/realtime`: theo địa chỉ IP, `MOC_RATE_REALTIME_PER_MIN` (mặc định 60/phút).
  - Phản hồi có `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` (giây).
- **Thuê ước**: không gửi `tenant_id`; Hasura và `svc-files` lấy từ token. Người của đơn vị này không đọc được
  dữ liệu của đơn vị khác (`make smoke` kiểm).

## 6. API nội bộ, không qua cổng

| Bên gọi → bên nhận | Cách gọi | Tài liệu |
|---|---|---|
| Hasura → `svc-workflow` `POST /actions/{name}` | Tiêu đề `X-Moc-Action-Secret` và biến phiên lấy từ JWT | [`openapi/svc-workflow.json`](openapi/svc-workflow.json) |
| `svc-files`, `svc-workflow` → Hasura | Khóa quản trị + `X-Hasura-Role: service` + đơn vị, người dùng, request id lấy từ token | [`db/README.md`](../../db/README.md#dịch-vụ-gọi-hasura) |
| `svc-workflow` → `svc-files` `POST /internal/issue` | Token tài khoản dịch vụ `svc-workflow` (client credentials của Keycloak) | [`services/svc-files/README.md`](../../services/svc-files/README.md) |
| `svc-workflow` → Flowable REST, Keycloak | Tài khoản dịch vụ | [`services/svc-workflow/README.md`](../../services/svc-workflow/README.md) |
| `svc-workflow` → Flowable `external-job-api` | Tự lấy việc nhắc hạn (topic `moc-sla`) do timer trong BPMN tạo | [`services/svc-workflow/README.md`](../../services/svc-workflow/README.md) |
| `svc-workflow` → Centrifugo `POST /api/batch` (cổng nội bộ 9000) | Tiêu đề `X-API-Key` (`CENTRIFUGO_API_KEY`) | [`realtime/config.yaml`](../../realtime/config.yaml) |
