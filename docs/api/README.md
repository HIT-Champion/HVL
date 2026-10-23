# Tài liệu API của Signet

Mọi ứng dụng gọi lõi qua **một cổng duy nhất**: APISIX ở `MOC_PUBLIC_URL` (máy phát triển:
`http://localhost:8080`). Ứng dụng có thể là Văn phòng điện tử, một ứng dụng Tầng 2 khác, script hay tác tử AI.
Có hai loại API:

- **GraphQL** (Hasura) cho dữ liệu có cấu trúc và thao tác nghiệp vụ.
- **REST** (`svc-files`) cho tệp, tìm kiếm, bản xem trước văn bản đi và cổng xác thực.

Dù gọi theo cách nào, người gọi cũng phải có token Keycloak, và đơn vị lẫn vai trò luôn lấy từ token. Ngoại lệ
là cổng xác thực văn bản đã phát hành (`/api/verify`) và trạng thái hệ thống (`/api/status`), ai cũng gọi được.

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
hệ thống vừa dựng, nên tài liệu không cũ đi so với mã. Khi lệch, CI sinh bản mới trên chính hệ thống đó và tải lên
thành artifact `docs-api-<lần chạy>` của job "Chạy thử: luong-chinh"; không cần dựng ở máy:

```bash
gh run download <run-id> -n docs-api-1 -D docs/api   # <run-id> lấy ở trang Checks của PR
```

Muốn xem dạng trang web, mở các tệp OpenAPI bằng công cụ
đọc OpenAPI 3.1, ví dụ Swagger UI hay Redoc chạy cục bộ. Các tệp `.graphql` là SDL chuẩn, công cụ GraphQL nào
cũng nạp được.

## Đường dẫn qua cổng

| Đường dẫn | Đến | Token |
|---|---|---|
| `/realms/moc/…` | Keycloak: đăng nhập, cấp và làm mới token, JWKS | — |
| `POST /v1/graphql` | Hasura | Bắt buộc |
| `POST /api/files`, `GET /api/files/{id}`, `POST /api/files/{id}/read`, `GET /api/search`, `GET /api/documents/{id}/preview`, `POST /api/documents/ask`, `GET /api/registers/…`, `GET /api/case-files/…` | `svc-files` | Bắt buộc |
| `GET /api/verify/{mã}`, `GET /api/verify?sha256=…` | `svc-files`: cổng xác thực | Không; giới hạn theo IP |
| `GET /api/status` | `svc-files`: trạng thái hệ thống | Không; giới hạn theo IP |
| `GET /realtime` (WebSocket) | Centrifugo: thông báo đẩy (§4) | Gửi trong lệnh `connect` đầu tiên |
| `GET /ca-nhan/` và trang tĩnh dưới đó | Không gian cá nhân P.A.R.A (`app-ca-nhan`), ứng dụng thứ hai trên lõi | — |
| `GET /` và trang tĩnh | Giao diện Văn phòng điện tử | — |

Cổng trả `404` cho các đường còn lại:

- API quản trị và nội bộ: `/v1/metadata`, `/v2/query`, `/console`, `/admin`, `/flowable-rest/*`, `/healthz`,
  `/metrics`, …
- WebSocket tới Hasura, nên chưa dùng được `subscription` của GraphQL; thông báo đẩy đi qua `/realtime` (§4).
  Danh sách đầy đủ ở [`platform/apisix/apisix.yaml`](../../platform/apisix/apisix.yaml).

Token thiếu, sai chữ ký hoặc hết hạn bị cổng trả `401` trước khi tới Hasura hay `svc-files`. Hai dịch vụ này
vẫn kiểm lại token (zero-trust).

## 1. Lấy token

Keycloak là nhà cung cấp OpenID Connect:

- issuer: `${MOC_PUBLIC_URL}/realms/moc`
- tài liệu khám phá: `/realms/moc/.well-known/openid-configuration`

Access token sống 5 phút; làm mới bằng refresh token.

- **Ứng dụng trên trình duyệt** dùng Authorization Code + PKCE (S256) với client công khai, như client
  `app-office`.
  - Muốn thêm một ứng dụng Tầng 2: thêm client vào [`platform/keycloak/realm/moc-realm.json`](../../platform/keycloak/realm/moc-realm.json)
    theo mẫu `app-office`. Giữ nguyên `protocolMappers` để token có claim của Hasura; đổi `clientId` và
    `redirectUris`. Bản cài đã chạy thì thêm client vào realm bằng `python3 scripts/moc.py realm clients`. Các bước
    còn lại và ví dụ đầy đủ (client `app-ca-nhan`): [`docs/them-ung-dung.md`](../them-ung-dung.md).
  - Văn thư, lãnh đạo và quản trị đơn vị phải nhập mã TOTP sau mật khẩu ([`platform/keycloak/README.md`](../../platform/keycloak/README.md)).
- **Script** dùng client `moc-cli`, luồng mật khẩu kèm mã TOTP (tham số `otp`) — hỏi mã theo đúng quy tắc của
  trình duyệt. Không cần trên server thật thì tắt (`MOC_CLI_CLIENT_ENABLED=false`).

```bash
export MOC=http://localhost:8080 MOC_DEMO_PASSWORD='…giá trị trong .env…'
OTP=123456   # mã hiện tại trong ứng dụng xác thực; tài khoản mẫu: make totp
TOKEN=$(curl -s "$MOC/realms/moc/protocol/openid-connect/token" -d grant_type=password -d client_id=moc-cli \
  -d username=vanthu --data-urlencode "password=$MOC_DEMO_PASSWORD" -d otp=$OTP | jq -r .access_token)
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

# 2. tiếp nhận văn bản đến kèm tệp: trạng thái received; data đúng schemas/van-ban-den.json
gql '{"query": "mutation ($d: jsonb!) { receiveIncoming(data: $d) { document_id document { status } } }",
      "variables": {"d": {"type_code": "CV", "symbol": "123/ĐHCN-ĐT", "issuer_name": "Trường Đại học Công nghiệp",
        "issued_on": "2026-10-19", "urgency": "khan", "summary": "Về việc rà soát chương trình đào tạo",
        "file_ids": ["'"$FILE"'"]}}}'

# 3. vào sổ: cấp số đến, lãnh đạo đơn vị nhận việc "vbden.chiDao" trong hộp việc
gql '{"query": "mutation ($id: uuid!) { registerIncoming(documentId: $id) { register_number } }",
      "variables": {"id": "<document_id ở bước 2>"}}'
```

`receiveIncoming` kiểm lại `data` theo [`schemas/van-ban-den.json`](../../schemas/van-ban-den.json), đúng tệp mà form
của giao diện kiểm: trường lạ, thiếu trường, sai độ dài, ngày ban hành sau hôm nay… đều bị từ chối, kèm trường sai
và mã lỗi để ứng dụng hiện ngay dưới ô nhập ([`schemas/README.md`](../../schemas/README.md)):

```json
{"errors": [{"message": "Dữ liệu văn bản đến chưa hợp lệ: summary, symbol",
             "extensions": {"code": "invalid", "fields": {"symbol": "not", "summary": "minLength"}}}]}
```

Văn bản đã tiếp nhận (cùng cơ quan ban hành, số ký hiệu, ngày ban hành) trả `duplicate`. Văn thư không ghi thẳng
được bảng văn bản (`insert_office_documents_one`), nên ứng dụng nào cũng phải qua lớp kiểm này.

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
| `GET /api/search?q=…` | Tìm theo số ký hiệu, trích yếu, cơ quan ban hành, nội dung văn bản đi và chữ trong tệp PDF đính kèm (văn bản hạn chế chỉ tìm theo ba trường đầu); gõ không dấu được, mọi từ phải khớp; chỉ trả văn bản người gọi được đọc; `matched_content: true` khi chỉ khớp nội dung; trang sau: `cursor=<next_cursor>` |
| `GET /api/documents/{id}/preview` | PDF đúng thể thức NĐ 30 của dự thảo văn bản đi, chưa có số, in chữ "DỰ THẢO"; văn bản đã phát hành thì tải bản phát hành |
| `GET /api/registers/{in\|out}/{năm}` | Văn thư, lãnh đạo đơn vị: sổ đăng ký văn bản đến / đi của một năm, đúng các cột của mẫu sổ NĐ 30 (Phụ lục IV); văn bản hạn chế người gọi không được đọc chỉ có số, ngày, số ký hiệu; `missing` là các số thiếu dòng |
| `GET /api/registers/{in\|out}/{năm}/pdf` | Như trên, ra bản in A4 ngang để ký nhận, đóng sổ; mỗi lần in ghi `register.printed` vào sổ kiểm toán |
| `POST /api/files/{id}/read` | Văn thư, chỉ tệp chính mình tải lên: tác tử đọc văn bản đến (F4.1) gợi ý số ký hiệu, ngày ban hành, cơ quan ban hành, loại, độ khẩn, trích yếu, mỗi trường kèm độ tin cậy; không tạo văn bản. Một lượt đọc một lúc (`503 busy`) |
| `POST /api/documents/ask` | Văn thư, chuyên viên, lãnh đạo: trợ lý hỏi đáp (F4.2) `{question, mode: extract\|generate}` → câu trả lời, mỗi câu kèm `[n]` trỏ nguồn (số ký hiệu, trang), chỉ từ văn bản người hỏi được đọc; không có căn cứ → `status: no_evidence`. Câu hỏi, câu trả lời không lưu |
| `GET /api/case-files/{id}/archive` | Hồ sơ đã nộp lưu (F3.8): đọc lại từ gói trên bucket lạnh sau khi khớp băm với CSDL; chỉ văn bản người gọi được đọc |
| `GET /api/verify/{mã}` | **Không cần token.** Văn bản đã phát hành có mã tra cứu này: số ký hiệu, ngày, cơ quan ban hành, SHA-256; trích yếu chỉ khi công khai |
| `GET /api/verify?sha256=…` | **Không cần token.** Như trên, tra theo SHA-256 của tệp PDF (trình duyệt tự tính, tệp không tải lên) |
| `GET /api/status` | **Không cần token.** Tình trạng từng thành phần (`ok`, `degraded`, `down`, `off`) theo tầng, tình trạng chung, phiên bản, thời gian chạy, giờ sao lưu gần nhất, trợ lý AI bật hay tắt; lưu đệm 10 giây, không có địa chỉ nội bộ hay số liệu |

```bash
curl -s -OJ "$MOC/api/files/$FILE" -H "Authorization: Bearer $TOKEN"
curl -s -G "$MOC/api/search" -H "Authorization: Bearer $TOKEN" --data-urlencode 'q=tuyen sinh' --data-urlencode limit=10
curl -s -OJ "$MOC/api/registers/in/2026/pdf" -H "Authorization: Bearer $TOKEN"     # token văn thư hoặc lãnh đạo đơn vị
curl -s "$MOC/api/documents/ask" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"question": "Điều kiện xét học bổng khuyến khích học tập là gì?", "mode": "extract"}'

# cổng xác thực, không đăng nhập: theo mã in cạnh mã QR, hoặc theo băm của tệp nhận được
curl -s "$MOC/api/verify/ABCDE-23456"
curl -s "$MOC/api/verify?sha256=$(sha256sum cong-van-nhan-duoc.pdf | cut -d' ' -f1)"

# trạng thái hệ thống, không đăng nhập
curl -s "$MOC/api/status"
```

Trang `/xac-thuc/<mã>` của giao diện (mã QR trên văn bản trỏ tới đây) gọi đúng hai đường xác thực trên; ứng dụng
khác cũng dùng được để tự kiểm văn bản nhận được. Trang `/trang-thai` gọi `/api/status` mỗi 30 giây.

Tệp được gắn vào văn bản bằng GraphQL (`file_ids` của `receiveIncoming`, `files` khi chuyên viên tạo dự thảo, hoặc
`insert_office_document_files_one`), không qua REST. Lỗi của `svc-files` có dạng `{"detail": {"code": "…", "message": "…"}}`.

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
thì đọc lại `core_notifications`. Giao diện Signet làm đúng như vậy trong
[`apps/office/app/composables/useRealtime.ts`](../../apps/office/app/composables/useRealtime.ts).

Bản cài có cấu hình máy chủ thư hoặc webhook thì cùng thông báo đó còn đi qua email, kênh chat (svc-workflow gửi ở
nền, [README của svc-workflow](../../services/svc-workflow/README.md) mục "Thông báo qua email, webhook"). Ứng dụng
không phải làm gì thêm; bảng hộp thư đi `core_notification_deliveries` không mở cho vai trò người dùng.

## 5. Sổ kiểm toán: `core_audit_log` (lãnh đạo, quản trị đơn vị)

Mọi thay đổi dữ liệu nghiệp vụ vào sổ kiểm toán chuỗi băm. Vai trò `director`, `tenant_admin` đọc được dòng sổ
của đơn vị mình, nhưng không đọc cột `diff`. Thay vào đó là trường `overview`: tên mọi cột đã đổi, kèm giá trị
`[cũ, mới]` chỉ ở các cột không chứa nội dung (trạng thái, số, ngày, cờ, mã người, mã văn bản). Cột chứa nội
dung và hash có giá trị `null`, để sổ không lộ văn bản hạn chế (có hash là tra được văn bản ở cổng xác thực).

```graphql
{
  core_audit_log(where: {entity_id: {_eq: "<id văn bản>"}}, order_by: {id: desc}, limit: 50) {
    id occurred_at actor_id actor_kind action entity entity_id hash overview
  }
  core_audit_anchors(order_by: {audit_id: desc}, limit: 1) { audit_id anchored_at }   # đã neo tới dòng nào
}
```

Ví dụ `overview` của lần phát hành: `{"status": ["approved", "issued"], "issued_on": [null, "2026-10-19"],
"content_sha256": null, "symbol": null, …}`. Kiểm cả chuỗi không làm qua API, vì chuỗi chung cho mọi đơn vị: quản trị máy chủ chạy
`make audit` ([`db/README.md`](../../db/README.md#sổ-kiểm-toán-chuỗi-băm)).

## 6. Quy ước chung

- **`X-Request-Id`**: cổng gắn vào mọi phản hồi. Mã này cũng có trong nhật ký của dịch vụ và cột `request_id`
  của sổ kiểm toán; gửi kèm khi báo lỗi.
- **Giới hạn tốc độ**, vượt thì trả `429`:
  - Đăng nhập và cấp token: theo địa chỉ IP, `MOC_RATE_LOGIN_PER_MIN` (mặc định 60/phút).
  - GraphQL và tệp: theo token, `MOC_RATE_API_PER_MIN` (mặc định 300/phút).
  - Cổng xác thực: theo địa chỉ IP, `MOC_RATE_VERIFY_PER_MIN` (mặc định 30/phút).
  - Mở kết nối `/realtime`: theo địa chỉ IP, `MOC_RATE_REALTIME_PER_MIN` (mặc định 60/phút).
  - Trạng thái hệ thống: theo địa chỉ IP, `MOC_RATE_STATUS_PER_MIN` (mặc định 30/phút).
  - Phản hồi có `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` (giây).
- **Thuê ước**: không gửi `tenant_id`; Hasura và `svc-files` lấy từ token. Người của đơn vị này không đọc được
  dữ liệu của đơn vị khác (`make smoke` kiểm).

## 7. API nội bộ, không qua cổng

| Bên gọi → bên nhận | Cách gọi | Tài liệu |
|---|---|---|
| Hasura → `svc-workflow` `POST /actions/{name}` | Tiêu đề `X-Moc-Action-Secret` và biến phiên lấy từ JWT | [`openapi/svc-workflow.json`](openapi/svc-workflow.json) |
| `svc-files`, `svc-workflow` → Hasura | Khóa quản trị + `X-Hasura-Role: service` + đơn vị, người dùng, request id lấy từ token | [`db/README.md`](../../db/README.md#dịch-vụ-gọi-hasura) |
| `svc-workflow` → `svc-files` `POST /internal/issue` | Token tài khoản dịch vụ `svc-workflow` (client credentials của Keycloak) | [`services/svc-files/README.md`](../../services/svc-files/README.md) |
| `svc-workflow` → Flowable REST, Keycloak | Tài khoản dịch vụ | [`services/svc-workflow/README.md`](../../services/svc-workflow/README.md) |
| `svc-workflow` → Flowable `external-job-api` | Tự lấy việc nhắc hạn (topic `moc-sla`) do timer trong BPMN tạo | [`services/svc-workflow/README.md`](../../services/svc-workflow/README.md) |
| `svc-workflow` → Centrifugo `POST /api/batch` (cổng nội bộ 9000) | Tiêu đề `X-API-Key` (`CENTRIFUGO_API_KEY`) | [`platform/centrifugo/config.yaml`](../../platform/centrifugo/config.yaml) |
| `svc-files` → SeaweedFS, bucket lạnh `moc-cold` | S3, bucket bật Object Lock; ghi mốc neo sổ kiểm toán kèm hạn giữ COMPLIANCE | [`services/svc-files/README.md`](../../services/svc-files/README.md) |
| `scripts/moc.py` trên máy chủ → PostgreSQL, `svc-files` | `docker compose exec` (không mở thêm cổng) | [`db/README.md`](../../db/README.md#sổ-kiểm-toán-chuỗi-băm) |
