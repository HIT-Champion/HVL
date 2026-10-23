# svc-files

Cửa duy nhất để tệp vào và ra khỏi kho đối tượng của Signet. Tệp tải lên được **quét ClamAV trước**,
sạch mới ghi vào SeaweedFS và thêm dòng `core.files`; ClamAV không trả lời thì từ chối, không bao giờ lưu tệp
chưa quét. Tải xuống: svc-files hỏi Hasura **bằng chính token của người dùng** xem họ có được xem tệp không —
quy tắc quyền chỉ nằm ở `db/metadata`, svc-files không viết lại. Tìm kiếm cũng vậy: Meilisearch xếp hạng,
Hasura quyết ai được đọc văn bản nào; tìm được cả theo chữ trong tệp PDF đính kèm. Văn bản đi được dựng thành PDF đúng thể thức NĐ 30 ở đây, và cổng xác thực
trả lời người ngoài một văn bản có thật, còn nguyên vẹn không. Sổ đăng ký văn bản đến / đi cũng in ra PDF ở đây.
Văn bản đi gửi đơn vị khác trong hệ thống thì bản phát hành được chép sang kho của đơn vị nhận ở đây (liên thông).
Văn thư tải văn bản đến lên thì tác tử `moc-doc-reader` đọc tệp (lớp chữ PDF hoặc OCR) và gợi ý thông tin tiếp nhận.
Người dùng hỏi bằng lời thì trợ lý `moc-assistant` tìm đoạn liên quan trong các văn bản **chính họ được đọc** và trả
lời bằng câu trích nguyên văn kèm số ký hiệu, số trang; mô hình chạy tại chỗ viết câu trả lời ngắn nếu có (F4.2).

Thuộc lõi Tầng 1 — F1.5 (dữ liệu phi cấu trúc), F1.6 (trạm kiểm dịch), F1.7 và F2.7 (tìm kiếm, cả nội dung PDF),
F2.4 (dựng PDF văn bản đi), F2.8 (sổ đăng ký in được), F2.13 (cổng xác thực), F3.12 (liên thông), F4.1 (đọc văn
bản đến) và F4.2 (hỏi đáp trên kho văn bản) trong [`docs/du-thi/ke-hoach-phat-trien.md`](../../docs/du-thi/ke-hoach-phat-trien.md). Chủ: mảng AI ·
issue #19, #20.

## Trạng thái

| Phần | Trạng thái |
|---|---|
| `POST /api/files`: kiểm JWT → quét ClamAV → ghi SeaweedFS → thêm dòng `core.files` | **Xong** |
| Tệp nhiễm: ghi `file.rejected` vào sổ kiểm toán `core.audit_log` | **Xong** |
| `GET /api/files/{id}`: kiểm quyền qua Hasura → đọc SeaweedFS | **Xong** |
| `GET /api/search`: số ký hiệu, trích yếu, cơ quan ban hành; gõ không dấu được | **Xong** |
| Tìm trong nội dung văn bản đi và lớp chữ của PDF đính kèm; báo kết quả nào khớp nội dung | **Xong** (F2.7) |
| `POST /api/files/{id}/read`: đọc văn bản đến (lớp chữ PDF hoặc OCR Tesseract), quy tắc gợi ý 6 trường, mô hình tùy chọn viết trích yếu, ghi sổ của tác tử | **Xong** (F4.1) |
| `POST /api/documents/ask`: hỏi đáp trên các văn bản người hỏi được đọc — chỉ mục đoạn theo trang, quyền hai lớp, câu trích nguyên văn, mô hình tùy chọn viết câu trả lời có kiểm trích dẫn, ghi sổ của trợ lý | **Xong** (F4.2) |
| `/internal/similar-documents`: văn bản đến tương tự đã giao cho tác tử gợi ý giao việc — câu tìm từ trích yếu, dùng lại truy xuất F4.2, hậu kiểm quyền dịch vụ, không trả chữ | **Xong** (F4.3) |
| Che thông tin cá nhân (số định danh, điện thoại, email, số tài khoản) trong chữ gửi mô hình và trong nhật ký; câu trích, nguồn, sổ kiểm toán giữ bản gốc | **Xong** (F4.4) |
| Văn bản hạn chế: lưu mã hóa (khóa riêng từng tệp từ két), tải về giải mã trong bộ nhớ, đóng dấu người xem, ghi sổ | **Xong** (F3.7) |
| `/internal/issue`: dựng PDF có số, mã QR (WeasyPrint) → quét → lưu bản phát hành | **Xong** (F2.4) |
| Ký số PAdES bản phát hành bằng khóa của đơn vị trong két, CA nội bộ (chỉ minh họa); `signature` ở cổng xác thực; `python -m svc_files.signing verify` | **Xong** (F4.5, bản tối thiểu) |
| `GET /api/documents/{id}/preview`: PDF dự thảo cho người được đọc | **Xong** (F2.4) |
| `GET /api/verify/{mã}`, `GET /api/verify?sha256=`: không cần đăng nhập | **Xong** (F2.13) |
| Neo đầu chuỗi sổ kiểm toán ra bucket lạnh có khóa ghi (S3 Object Lock) | **Xong** (F2.12) |
| `GET /api/registers/{in\|out}/{năm}` và `/pdf`: sổ đăng ký văn bản đến / đi theo mẫu NĐ 30, in A4 ngang | **Xong** (F2.8) |
| Nộp lưu hồ sơ đã đóng sang bucket lạnh (Parquet + tệp + manifest có băm), `GET /api/case-files/{id}/archive` | **Xong** (F3.8) |
| Phả hệ OpenLineage cho từng bước nộp lưu, kiểm chất lượng bảng Parquet trước khi ghi | **Xong** (F3.9) |
| `/internal/dispatch-file`: chép bản phát hành sang kho của đơn vị nhận trong hệ thống (kiểm băm, quét, id định trước) | **Xong** (F3.12) |
| Phòng đọc xem tệp đã nộp lưu (chỉ xem, watermark) | Chưa |

## API

Đi qua APISIX ở `/api/files/*`, `/api/search`, `/api/documents/*`, `/api/registers/*`, `/api/verify`,
`/api/case-files/*`. OpenAPI tự sinh ở `/openapi.json` (chỉ trong mạng nội bộ), bản
xuất nằm ở [`docs/api/openapi/svc-files.json`](../../docs/api/openapi/svc-files.json) (`make api-docs`).

| Đường dẫn | Kết quả |
|---|---|
| `POST /api/files` (multipart, trường `file`) | `201` `{id, object_key, filename, mime_type, size_bytes, sha256, scanned_at, encrypted}` |
| | `?restricted=true` — tệp cho văn bản hạn chế, lưu mã hóa (mục Văn bản hạn chế): `415` `restricted_pdf_only` + `reason` khi không phải PDF đọc được, không mật khẩu, tối đa `MOC_RESTRICTED_MAX_PAGES` trang, hoặc quá nặng để kiểm (`timeout`, `memory`) · `503` `vault_unavailable` khi két chưa sẵn sàng, `busy` (+ `Retry-After: 10`) khi đang kiểm, đóng dấu tệp hạn chế khác — **không lưu** |
| | `401` thiếu hoặc sai token · `403` token không có `tenant_id` |
| | `413` vượt `MOC_FILES_MAX_MB` · `400` tệp rỗng hoặc thiếu trường `file` |
| | `422` `{code: "infected", signature}` — tệp nhiễm, **không lưu**, ghi vào sổ kiểm toán |
| | `403` `unknown_tenant` — thuê ước trong token chưa có trong `core.tenants` |
| | `503` ClamAV, SeaweedFS hoặc Hasura không sẵn sàng — **không lưu** (đã ghi vào kho thì gỡ ra) |
| `POST /api/files/{id}/read` | Chỉ `clerk`, chỉ tệp chính mình tải lên. `?force=true` đọc lại. `200` `{file_id, status, method, pages, fields, warnings, summary_source, model, duration_ms, cached, read_at}` · `401` · `403` `forbidden` · `404` `not_found` (cả tệp người khác) · `409` `restricted` tệp mã hóa hoặc tệp đang gắn vào văn bản hạn chế (trước gợi ý đã lưu, trước khi đọc byte) · `413` `too_large` · `415` `unsupported` · `422` `unreadable` + `reason` · `503` `busy` (+ `Retry-After: 10`), `reader_disabled`, `ocr_unavailable`, `storage_unavailable`, `database_unavailable` — mục Đọc văn bản đến |
| `POST /api/documents/ask` | `clerk`, `staff`, `manager`, `director`. Thân `{question, mode: extract\|generate, direction, year, type_code, ask_id}`. `200` `{ask_id, status, answer, extract, sources, semantic, ai_available, warnings, duration_ms}`, `Cache-Control: no-store` · `400` `invalid_question` · `401` · `403` `forbidden` · `422` thân sai · `503` `assistant_disabled`, `busy` (+ `Retry-After: 10`), `search_unavailable`, `database_unavailable` — mục Hỏi đáp trên kho văn bản |
| `GET /api/files/{id}` | `200` nội dung tệp · `404` không có tệp **hoặc** không được xem (trả như nhau) · `401` · `503` · tệp mã hóa: `200` bản giải mã có dấu người xem, `422` `unstampable` + `reason` không đóng dấu được (quá `MOC_RESTRICTED_MAX_PAGES` trang, quá nặng, hỏng), `500` `sealed_corrupt` bản mã hỏng hoặc không khớp tệp, `503` két hoặc sổ kiểm toán chưa sẵn sàng, `busy` (+ `Retry-After: 10`) |
| `GET /api/search?q=` | `200` `{hits: [...], next_cursor}` · `400` câu tìm trống, `cursor` sai · `422` tham số sai · `401` · `503` |
| `GET /api/documents/{id}/preview` | `200` PDF dự thảo (chữ "DỰ THẢO", chưa số) · `404` không có hoặc không được đọc · `409` đã phát hành |
| `GET /api/registers/{in\|out}/{năm}` | Chỉ `clerk`, `director`. `200` `{direction, year, title, org_name, columns, entries: [{number, document_id, hidden, cells}], last_number, missing}` · `403` vai trò khác · `422` chiều sổ hay năm (2000–2100) sai · `401` · `503` |
| `GET /api/registers/{in\|out}/{năm}/pdf` | Như trên, trả PDF `so-dang-ky-van-ban-{den\|di}-<năm>.pdf`; ghi `register.printed` vào sổ kiểm toán trước khi trả, ghi không được thì `503`, không có PDF |
| `GET /api/verify/{mã}` | **Không cần token.** `200` `{result: "valid" \| "not_found", document}`; nhận cả `abcde-23456`, `ABCDE 23456`. `document.signature`: chữ ký số của bản phát hành `{level, signer, ca, serial, signed_at, illustrative: true}`, `null` với văn bản cũ, văn bản hạn chế (F4.5) |
| `GET /api/verify?sha256=` | **Không cần token.** Như trên, tra theo băm; `422` khi không phải 64 ký tự hex |
| `GET /api/case-files/{id}/archive` | Người xem được hồ sơ (phòng mình với `staff`, `manager`; cả đơn vị với `clerk`, `director`). `200` `{case_file_id, code, title, closed_on, archived_at, archive_key, manifest_sha256, retain_until, documents, files, hidden}` — văn bản người gọi đọc được, đọc từ bảng Parquet trong gói; `hidden` là số văn bản còn lại · `404` không có hoặc không được xem · `409` `not_archived` · `502` `archive_mismatch` gói không khớp băm trong CSDL · `401` · `503`. Ghi `case_file.read` vào sổ kiểm toán trước khi trả |
| `POST /internal/issue` | Chỉ token tài khoản dịch vụ trong `MOC_SERVICE_CLIENTS` (`403` với token người dùng). `201` `{file_id, sha256, size_bytes}` — `sha256` của bản đã ký số (F4.5) · `409` văn bản chưa cấp số · `503` ClamAV, kho, CSDL không sẵn sàng; `signing_unavailable` két không trả lời khi ký — **không lưu**. Không có trong OpenAPI công khai, APISIX không có route tới |
| `POST /internal/dispatch-file` | Như `/internal/issue` (chỉ dịch vụ nội bộ). Thân `{dispatch_id, actor_id}`. `201` `{file_id, sha256, size_bytes}` bản sao mới · `200` cùng thân khi bản sao đã có · `404` không có dòng `office.dispatches` · `409` `{code}`: `not_pending` dòng không còn chờ, `not_issued` văn bản chưa phát hành, `restricted` văn bản hạn chế / tệp mã hóa, `cold` tệp đã sang kho lạnh, `integrity` byte trong kho không khớp băm · `422` trạm quét chặn · `503` ClamAV, kho, CSDL không sẵn sàng (mục Liên thông) |
| `POST /internal/similar-documents` | Như `/internal/issue` (chỉ dịch vụ nội bộ). Thân `{tenant_id, document_id, limit}` (`limit` 1–30, mặc định 15; thừa trường → `422`). `200` `{document_id, hits: [{document_id, score}], terms, semantic, duration_ms}` · `404` `not_found` · `409` `not_incoming`, `restricted` · `503` `assistant_disabled`, `search_unavailable`, `database_unavailable` (mục Văn bản tương tự cho tác tử gợi ý giao việc) |
| `GET /healthz` | Tiến trình còn sống |
| `GET /readyz` | `200` khi gọi được ClamAV, SeaweedFS và Hasura, ngược lại `503`; Meilisearch hỏng thì vẫn `200` nhưng `status: "degraded"`; `ai`: mô hình trích yếu (F4.1) đang sẵn sàng không; `assist: {index, semantic, model, embed_pending, embed_failed}` (F4.2): chỉ mục đoạn đã đồng bộ xong một lượt; tìm theo nghĩa được (mô hình nhúng sẵn sàng, đúng số chiều, embedder đã áp trong Meilisearch); mô hình viết câu trả lời sẵn sàng; số đoạn còn chờ nhúng và số đoạn làm mô hình nhúng lỗi (null khi không nhúng hoặc chưa đếm) — cả hai không ảnh hưởng `status` |

Ai xem được tệp: người tải lên, và người đọc được văn bản có gắn tệp đó (`db/README.md`, mục Vai trò).
Tệp tải về luôn ở dạng `attachment`, kèm `X-Content-Type-Options: nosniff` và
`Content-Security-Policy: sandbox` — tệp HTML hay SVG người dùng tải lên không chạy được như một trang của
Signet. Giao diện lấy tệp bằng fetch kèm token rồi lưu về máy nên không cần hiển thị inline. `ETag` là SHA-256 của tệp (tệp mã hóa thì không
có `ETag`: mỗi lần mở là một bản khác).

Khóa đối tượng: `tenant/<tenant_id>/<yyyy>/<mm>/<id>` — thuê ước lấy từ token, không lấy từ dữ liệu client
gửi; khóa không trả ra ngoài. Mỗi dòng nhật ký là một đối tượng JSON có `request_id` (lấy từ `X-Request-Id`
do APISIX gắn); mã này cũng đi vào cột `request_id` của sổ kiểm toán.

### Tìm kiếm

`GET /api/search?q=…` nhận thêm `direction` (`in`/`out`), `status`, `type_code`, `urgency`, `year`, `limit`
(≤ 50), `offset`. Meilisearch tự bỏ dấu tiếng Việt (`tuyen sinh` khớp "tuyển sinh", `qd-dhcn` khớp
"QĐ-ĐHCN") và chịu được gõ sai một chữ.

1. Meilisearch tìm trong chỉ mục với điều kiện `tenant_id` lấy từ token — luôn đứng đầu bộ lọc, không lấy từ
   tham số. Chỉ mục chỉ trả về id (`displayedAttributes: ["id"]`). Mọi từ trong câu tìm phải khớp
   (`matchingStrategy: "all"`): mặc định của Meilisearch bớt dần từ khi ít kết quả, nên khi đã tìm cả nội dung tệp,
   một công văn dài chỉ chứa vài từ phổ biến của câu tìm cũng hiện ra.
2. svc-files hỏi Hasura **bằng token người dùng** các id đó: văn bản không được đọc bị bỏ, dữ liệu trả về là
   bản mới nhất trong CSDL. Người chỉ được đọc ít văn bản thì svc-files lấy thêm vài lượt để đủ `limit`.
3. Không trả tổng số kết quả: con số của Meilisearch tính cả văn bản người dùng không được đọc. Vì cùng lý do,
   vị trí trang sau cũng không trả dạng số (tìm với `limit=1` rồi lấy vị trí trừ 1 là ra số văn bản mình không được
   đọc có chứa từ đó): `next_cursor` là vị trí đã mã hóa AES-GCM, gắn với người tìm, câu tìm và bộ lọc. Trang sau
   lấy bằng `cursor=<next_cursor>`; `next_cursor: null` là hết; cursor của người khác, câu tìm khác, hoặc bị sửa
   nhận `400 invalid_cursor`. Khóa dẫn xuất (HKDF) từ `HASURA_ADMIN_SECRET`: đổi khóa đó thì cursor cũ hết hiệu lực.
4. Nhật ký chỉ ghi độ dài câu tìm, không ghi nội dung.
5. Mỗi kết quả có `matched_content`: câu tìm khớp nội dung mà không khớp số ký hiệu, trích yếu, cơ quan ban hành.
   Meilisearch không cho biết khớp ở trường nào khi chỉ hiện id, nên svc-files hỏi thêm một lượt, chỉ trong ba
   trường đó và chỉ với các id vừa tìm được (`attributesToSearchOn`, mọi từ phải khớp).

Đồng bộ chỉ mục: mỗi `MOC_SEARCH_SYNC_INTERVAL_S` giây, svc-files đọc các văn bản có `updated_at` mới — hoặc có
tệp vừa được đọc chữ — qua Hasura (khóa quản trị, chỉ đọc) và ghi đè vào Meilisearch theo id. Mỗi lượt đọc lùi
lại 60 giây để không sót giao dịch ghi xong muộn; văn bản chưa đổi (đủ mọi mốc thời gian của văn bản và chữ các
tệp) không bị đẩy lại, đẩy lỗi thì lượt sau đẩy lại. Lật trang theo id, không theo offset: văn bản đổi giữa lúc
đang lật không làm trượt mất dòng ở mép trang. Khởi động lại thì đồng bộ lại toàn bộ (chữ của PDF đọc từ CSDL,
không đọc lại tệp).

### Nội dung tệp PDF (F2.7)

`texts.py`, `pdftext.py`. Trường `content` của chỉ mục là nội dung văn bản đi cộng chữ của các tệp PDF gắn vào
văn bản (bản chính, tài liệu kèm theo; không lấy bản phát hành vì nó chính là nội dung đã có), tối đa 100 000 ký
tự mỗi văn bản. Xếp hạng: khớp nội dung đứng sau khớp số ký hiệu, trích yếu, cơ quan ban hành.

- **Đọc ở vòng nền**, mỗi `MOC_TEXT_INTERVAL_S` giây, các PDF **đã gắn vào văn bản** (bản chính, tài liệu kèm
  theo; từ F4.2 cả bản phát hành văn bản đi — chỉ trợ lý hỏi đáp dùng, chỉ mục tìm kiếm vẫn không lấy) mà chưa đọc;
  còn tồn (vd tệp tải lên trước khi có F2.7) thì đọc tiếp ngay. Chữ từng trang nối bằng xuống dòng, vị trí đầu mỗi
  trang lưu ở `page_starts` (F4.2: trích dẫn có số trang). Kết quả ghi vào
  `core.file_texts` (khóa quản trị; không vai trò người dùng nào đọc được bảng này), mỗi tệp một lần: `ok`, `empty`
  (không có lớp chữ — bản scan, để dành OCR F4.1), `failed` kèm lý do (`encrypted`, `timeout`, `memory`,
  `too large`, `missing` — kho không có đối tượng, `unreadable` — kho lỗi 5 lượt liền, `not saved` — CSDL không
  nhận kết quả, `bad output`, lỗi của pypdf).
- **Một tệp lỗi không chặn hàng đợi.** Hàng đợi chung mọi thuê ước, tệp cũ nhất trước: tệp nào cũng phải đi tới
  một dòng kết quả, nếu không thì tệp đó đứng đầu mãi. Số trang tệp tự khai (`/Count`, pypdf trả nguyên với tệp mã
  hóa) không được tin — lấy số trang thật sau khi duyệt cây trang; kết quả của tiến trình con được kiểm đúng ràng
  buộc của bảng trước khi ghi; CSDL vẫn từ chối thì ghi `failed` trơn. Kho tạm lỗi thì tệp sau vẫn được đọc.
- **Văn bản hạn chế không đưa nội dung vào chỉ mục**, tệp của nó cũng không được đọc chữ: kể cả người được đọc
  văn bản cũng chỉ tìm được theo số ký hiệu, trích yếu, cơ quan ban hành. Bản chữ trần nằm ngoài tệp sẽ vô hiệu
  việc lưu mã hóa tệp của văn bản hạn chế (F3.7). CSDL chặn thêm bằng trigger: không ghi chữ cho tệp của văn bản
  hạn chế, và xóa chữ đã đọc khi văn bản bật hạn chế hoặc khi tệp được gắn vào văn bản hạn chế; lượt đồng bộ kế
  tiếp đẩy lại văn bản với nội dung rỗng.
- **Chưa xử lý** (ghi lại để làm sau): bỏ tệp đính kèm mà không sửa văn bản (gọi thẳng `delete_office_document_files`)
  thì chữ của tệp còn trong chỉ mục tới lần sửa văn bản kế tiếp — giao diện luôn sửa văn bản trong cùng lệnh nên
  dùng thường không gặp. Hàng đợi đọc chữ là một hàng chung: một người gắn nhiều PDF chậm làm chậm việc đọc chữ
  của mọi thuê ước (mỗi tệp tối đa 60 giây).
- **Không đọc PDF trong tiến trình của svc-files.** Tệp do người dùng tải lên, ClamAV chỉ biết nó không chứa mã
  độc đã biết; một PDF dựng có ý đồ vẫn làm bộ đọc chạy mãi hoặc ăn hết bộ nhớ. Mỗi tệp đọc trong một tiến trình
  con (`python -I pdftext.py`) giới hạn 1 GB bộ nhớ ảo, CPU và 60 giây; quá hạn thì bị giết, tệp ghi `failed`.
  Đọc tối đa 200 trang đầu, giữ 50 000 ký tự, đưa về Unicode dựng sẵn (NFC), bỏ ký tự điều khiển và ký tự ẩn.
- PDF khóa bằng mật khẩu chủ (cấm sửa, cấm chép) nhưng mở không cần mật khẩu vẫn đọc được; cần mật khẩu để mở
  thì `failed`, `encrypted`. Tệp đã mã hóa ở kho (F3.7) không đọc.

### Đọc văn bản đến (F4.1)

`docread/`. Văn thư kéo thả công văn PDF hoặc ảnh chụp vào "Tiếp nhận văn bản"; tệp quét sạch thì giao diện gọi
`POST /api/files/{id}/read` và điền sẵn số ký hiệu, ngày ban hành, cơ quan ban hành, loại, độ khẩn, trích yếu — mỗi ô
có nhãn "Gợi ý". **Tác tử không tạo văn bản**: văn thư đối chiếu với bản gốc, sửa, bấm lưu (`receiveIncoming` như cũ).

- **Ai, tệp nào.** Chỉ văn thư, chỉ tệp chính họ tải lên (`created_by`) — tệp người khác trả `404` như không có. Chỉ
  tệp có dòng `core.files`, tức đã qua ClamAV. **Văn bản hạn chế không bao giờ được đọc**: tệp mã hóa (F3.7), hay
  tệp đang gắn vào văn bản hạn chế (kể cả tệp rõ có từ trước F3.7), trả `409` trước cả gợi ý đã lưu và trước khi đọc
  byte nào (bản chữ trần hay bản gửi mô hình đều vô hiệu việc hạn chế); CSDL chặn thêm bằng trigger (không lưu gợi ý
  của tệp gắn vào văn bản hạn chế, xóa gợi ý khi văn bản bật hạn chế).
- **Đọc.** Nhận loại theo byte đầu (PDF `%PDF-`, JPEG, PNG, TIFF), không tin mime khai. PDF: lớp chữ giữ bố cục
  (`pdflayout.py`, pypdf chế độ `layout`, `MOC_READ_TEXT_PAGES` trang đầu); trang 1 có từ 40 ký tự không trắng thì
  dùng (`method: text`), không thì OCR ảnh nhúng lớn nhất của từng trang (không rasterize: image không có poppler,
  pdfium — PDF máy scan là một ảnh mỗi trang); PDF ít chữ mà không có ảnh nhúng nào, hay máy chủ chưa OCR được (thiếu
  tesseract, thiếu dữ liệu ngôn ngữ), thì dùng lớp chữ ít ỏi đó (`method: text`). Ảnh: OCR (`method: ocr`). OCR
  (`ocr.py`): Pillow xoay theo EXIF, đổi xám, giãn tương phản, đưa cạnh dài về 2000–3500 px, gửi PNG cho
  `tesseract stdin stdout -l vie --oem 1 --psm 3 tsv`.
- **Tiến trình con có giới hạn**, như `pdftext.py`: `python -I`, `RLIMIT_AS` (lớp chữ 1 GB, OCR `MOC_OCR_MEMORY_MB`),
  `RLIMIT_CPU`, quá giờ thì giết. Tiến trình OCR mở phiên riêng: quá giờ hoặc yêu cầu bị hủy thì giết **cả nhóm**
  (`os.killpg`), tesseract không chạy mồ côi. Pillow có trần điểm ảnh (`MOC_OCR_MAX_PIXELS`), cả khi pypdf giải mã
  ảnh nhúng trong PDF: kích thước khai được kiểm trước khi giải nén, kích thước thật kiểm lúc Pillow mở — vượt trần là
  `too_many_pixels`. Tesseract chết vì tín hiệu là lỗi của tệp (`422`): `SIGKILL`, `SIGABRT` hay tự báo không cấp phát
  được → `memory`, tín hiệu khác → `corrupt`; `503 ocr_unavailable` chỉ khi thiếu tesseract hoặc dữ liệu ngôn ngữ.
  Tesseract chỉ nhận `PATH`, `OMP_THREAD_LIMIT=1` (và `TESSDATA_PREFIX` nếu đặt) — không thấy bí mật của svc-files.
  Kết quả của tiến trình con được kiểm lại trước khi dùng.
- **Quy tắc quyết mọi trường** (`rules.py`, `layout.py` — thuần Python, regex tuyến tính trên ≤ 20 000 ký tự, kiểm
  thử được, giải thích được). Mô hình chỉ viết **trích yếu**, chỉ khi quy tắc không ra trích yếu tin cậy cao
  (`MOC_AI_SUMMARY=fallback`) và còn ≥ 5 giây trong hạn tổng: số, ngày từ mô hình có thể bịa.
- **Mô hình tùy chọn** (`summarize.py`): Ollama ở profile `ai` của compose, mạng nội bộ không ra Internet. svc-files dò
  `GET /api/tags` lúc khởi động và mỗi 60 giây — bật / tắt profile không phải khởi động lại svc-files; vừa thấy mô
  hình thì nạp trước. Gọi `/api/chat` không stream, tắt suy nghĩ, ép JSON Schema `{"trich_yeu"}`, nhiệt độ 0,1, hạt
  giống cố định; thân văn bản trong thẻ `<van_ban>` (thẻ trùng tên trong văn bản bị bỏ), lời dặn bảo mô hình không làm
  theo yêu cầu nằm trong văn bản. Đầu ra kiểm chặt: 10–300 ký tự, một dòng, không ký tự điều khiển / vô hình, không
  `http`, `www.`, `@`, `<`, `>`, không dãy từ 6 chữ số liền nhau (số điện thoại, số tài khoản) — sai thì
  `model_rejected`, trích yếu quy tắc giữ nguyên. Không có mô hình vẫn chạy đủ.
- **Hạn và lượt.** Đồng bộ, hạn tổng `MOC_READ_DEADLINE_S` (50 giây, dưới 60 giây mặc định của APISIX). Một lượt đọc
  một lúc (`MOC_READ_CONCURRENCY`): OCR, mô hình tranh CPU; chờ quá `MOC_READ_QUEUE_S` thì `503 busy` kèm
  `Retry-After: 10` (không dùng `429`: giao diện coi `429` là giới hạn tốc độ của APISIX).
- **Tác tử có danh tính, có sổ.** Lưu gợi ý (`office.intake_suggestions`) và ghi **một** dòng `intake.suggested` vào
  sổ kiểm toán trong cùng một mutation, bằng vai trò Hasura `agent`: preset ép `actor_id = moc-doc-reader`,
  `actor_kind = agent`, thuê ước — dữ liệu gửi lên không giả được; vai trò `agent` không có quyền nào trên văn bản.
  `diff` chỉ có siêu dữ liệu (người yêu cầu, tệp, trạng thái, cách đọc, số trang, tên các trường tìm thấy, nguồn trích
  yếu, mô hình, thời gian, lý do) — không số ký hiệu, trích yếu, tên tệp, chữ OCR. **Không ghi được sổ thì không trả
  gợi ý** (`503`). Đọc hỏng (`422`) chỉ ghi dòng sổ. Lần bấm sau trả gợi ý đã lưu (`cached: true`, không ghi sổ);
  "Đọc lại" (`force=true`) đọc lại và ghi sổ.
- **Nhật ký không có chữ của văn bản**: `office.intake.read` {file_id, tenant_id, actor_id, method, pages, chars, found,
  duration_ms, model, cached}, `office.intake.read_failed` {file_id, reason}. Lỗi của quy tắc chỉ ghi tên lỗi.

| Kết quả | Ý nghĩa |
|---|---|
| `status` | `ok` ít nhất một trường · `empty` đọc được mà không ra trường nào |
| `fields.<khóa>` | `{value, confidence: high\|medium\|low, source: rule\|model}`; khóa ⊂ `type_code, symbol, issued_on, issuer_name, summary, urgency`; `issued_on` ISO, `urgency` ∈ `normal, khan, thuong_khan, hoa_toc` |
| `warnings` | `future_date`, `invalid_date`, `symbol_no_number`, `type_conflict`, `low_text`, `truncated`, `model_unavailable` (cần mà chưa có mô hình), `model_timeout`, `model_rejected`, `model_skipped` (không đủ thời gian) |
| `422 reason` | `password` PDF phải nhập mật khẩu · `corrupt` (cả tesseract sập) · `no_text` không chữ không ảnh · `timeout` · `memory` (cả tesseract bị giết vì hết bộ nhớ) · `too_many_pixels` |

**Số đo** (`make do-doc-van-ban` trên stack thật, 22/10/2026, 22 văn bản trong `seed/van-ban-den/`: 15 PDF có
chữ + 7 ảnh / bản scan; máy đo: AMD Ryzen 7 7735HS, 16 luồng, một lượt đọc một lúc, tesseract 5.5.0 + `vie` 4.1.0). Mẫu hư cấu in sạch hơn
công văn thật — đây là **mức trần**; số thật đo bằng view `office.v_intake_accuracy` khi có đơn vị chạy thử. Mẫu 15–22
thêm sau để đo "Hoàn thành khi" của Phase 4 và khó hơn 14 mẫu đầu (ký hiệu ba đoạn, có năm, số có chữ cái phụ; ngày
viết không theo NĐ 30; cơ quan chủ quản hai dòng, văn bản liên tịch, cơ quan ngoài ngành giáo dục; ảnh chụp nghiêng
3,2°, bản scan nền xám, PDF scan 3 trang).

Cả kho 22 văn bản: **số ký hiệu đúng 20/22, ngày ban hành đúng 22/22**.

| Trường | PDF có chữ (15): đúng / sai / trống | Bản scan (7, OCR): đúng / sai / trống | `high` sai |
|---|---|---|---|
| Số, ký hiệu | 15 / 0 / 0 | 5 / 2 / 0 | 0 |
| Ngày ban hành | 15 / 0 / 0 | 7 / 0 / 0 | 0 |
| Cơ quan ban hành | 12 / 3 / 0 | 5 / 2 / 0 | 0 |
| Loại văn bản | 14 / 0 / 1 | 7 / 0 / 0 | 0 |
| Độ khẩn | 15 / 0 / 0 | 6 / 0 / 1 | 0 |
| Trích yếu (có gợi ý / trùng ≥ 60% từ) | 14 / 14 | 7 / 7 | — |

Chỗ sai của bản scan (đều do OCR, không ô nào được chấm `high` trên bản cài): số ký hiệu của 11 đọc "131/ĐT1-ĐHM", của
20 (ảnh chụp nghiêng) đọc "07/CĐÐ-UBND"; dấu "HỎA TỐC" của 20 không nhận ra; cơ quan của 14 thành "Cõ phần", của 21
(nền xám) chỉ lấy dòng "Chi Nhánh Cần Thơ". Sai của PDF có chữ: xem đoạn dưới.

Đo trước 5 PDF có chữ mới (15–19) bằng quy tắc, không cần Docker (như `tests/test_docread_samples.py`, 22/10/2026):
số ký hiệu 5/5, ngày ban hành 5/5 (một `medium`: ngày viết `12/10/2026`), loại 4/5, cơ quan ban hành 2/5, có trích
yếu 4/5; không ô `high` nào sai. Trống: "KẾ HOẠCH LIÊN TỊCH" không phải tên loại trong danh mục, ký hiệu `KHLT` cũng
không, nên không có loại, không có trích yếu. Sai (đều `medium`): văn bản của Văn phòng UBND thành "Văn phòng tỉnh
Mẫu"; văn bản liên tịch chỉ lấy cơ quan dòng cuối; tên bệnh viện đã có tên riêng vẫn bị nối "tỉnh Mẫu" của dòng chủ
quản. Không sửa quy tắc cho các mẫu này (không phải lỗi đọc thể thức NĐ 30).

Lần đo trước (21/10/2026, 14 mẫu đầu: 10 PDF có chữ + 4 bản scan; máy đo: AMD Ryzen 7 7735HS, 16 luồng, tesseract
5.5.0 + `vie` 4.1.0):

| Trường | PDF có chữ: đúng / sai / trống | Bản scan (OCR): đúng / sai / trống | `high` sai |
|---|---|---|---|
| Số, ký hiệu | 10 / 0 / 0 | 3 / 1 / 0 | 0 (*) |
| Ngày ban hành | 10 / 0 / 0 | 4 / 0 / 0 | 0 |
| Cơ quan ban hành | 10 / 0 / 0 | 3 / 1 / 0 | 0 |
| Loại văn bản | 10 / 0 / 0 | 4 / 0 / 0 | 0 |
| Độ khẩn | 10 / 0 / 0 | 4 / 0 / 0 | 0 |
| Trích yếu (có gợi ý / trùng ≥ 60% từ) | 10 / 10 | 4 / 4 | — |

(*) OCR đọc `131/ĐT-ĐHM` thành `131/ĐT1-ĐHM` (thừa một chữ số) mà quy tắc vẫn chấm `high` — vì vậy mọi trường
đọc bằng OCR hạ xuống tối đa `medium`: vẫn điền sẵn, nhãn "Gợi ý (chưa chắc)", văn thư đối chiếu bản gốc. Ô sai còn lại
là dấu (`Cõ phần` thay `Cổ phần`, `medium`).

| Thời gian một lần đọc (21/10, 14 mẫu đầu) | Trung bình | Lớn nhất |
|---|---|---|
| PDF có chữ, không mô hình | 0,6 giây | 0,7 giây |
| Ảnh / PDF scan (OCR 1 trang) | 1,2 giây | 1,5 giây |
| PDF có chữ + trích yếu bằng `qwen3:1.7b` (CPU, mô hình đã nạp) | 4,1 giây | 4,1 giây |
| Ảnh scan + trích yếu bằng `qwen3:1.7b` | 6,6 giây | 6,6 giây |

Lần đo 22/10 trên cả 22 văn bản (không mô hình): PDF có chữ trung bình 0,6 giây, lâu nhất 0,7 giây; ảnh / bản scan
trung bình 1,3 giây, lâu nhất 1,9 giây (13, PDF chỉ có ảnh).

Mô hình chỉ chạy khi quy tắc chưa ra trích yếu chắc chắn: trên 14 mẫu đầu là 2 lần (giấy mời không có dòng V/v, ảnh
xám), các tệp khác giữ thời gian như khi không bật mô hình. Từ bản này chữ OCR không trường nào `high` nên mọi ảnh, bản
scan đều qua mô hình khi bật `ai` (thêm khoảng 3,5–6 giây).

Chưa làm: OCR bản scan cho tìm kiếm toàn văn (F2.7 chỉ đọc lớp chữ); so sánh PaddleOCR / VietOCR; dữ liệu
`tessdata_best` (gói Debian là bản nhanh — đặt `TESSDATA_PREFIX` trỏ volume nếu cần chính xác hơn).

### Hỏi đáp trên kho văn bản (F4.2)

`assist/`. Trang "Hỏi đáp văn bản" gọi `POST /api/documents/ask`: người dùng hỏi bằng lời (vd "Điều kiện xét học bổng
khuyến khích học tập là gì?"), trợ lý tìm đoạn liên quan trong các văn bản **chính người hỏi được đọc** và trả câu trích
nguyên văn kèm nguồn "88/CTSV · tr. 1". Văn thư, chuyên viên, trưởng phòng, lãnh đạo hỏi được; vai trò khác `403`. Mỗi
câu hỏi độc lập, không lưu hội thoại.

**Chỉ mục đoạn** (`chunks.py`, `index.py`, `meili.py`). Chỉ mục Meilisearch riêng `MOC_ASK_INDEX` (`chunks`), một tài
liệu mỗi đoạn, cùng máy Meilisearch với tìm kiếm F2.7.

- **Nguồn**: chữ PDF của F2.7 (`core.file_texts`, có `page_starts`), không đọc lại tệp. Văn bản đến: bản chính và tài
  liệu kèm theo (đánh trang riêng từng tệp), mọi trạng thái trừ `cancelled`. Văn bản đi: chỉ khi `issued`, `archived`,
  nguồn là bản phát hành — dự thảo chưa có giá trị, đổi liên tục. **Văn bản hạn chế không bao giờ có đoạn nào.**
- **Cắt đoạn** theo từng trang, ≤ 1 200 ký tự, cắt ở ranh giới câu rồi khoảng trắng, đoạn sau mở đầu bằng câu cuối của
  đoạn trước; không đoạn nào vượt trang. Bản scan, tệp lỗi, văn bản chưa có tệp: một đoạn "trích yếu" (loại, số ký
  hiệu, ngày, cơ quan ban hành, trích yếu) — trích dẫn ghi "trích yếu", không bịa số trang.
- **Mỗi đoạn mang thuộc tính quyền** chép từ văn bản: thuê ước, chiều, phòng, người tạo, phòng và người được giao
  (giao việc chưa hủy).
- **Vòng nền** mỗi `MOC_ASK_SYNC_INTERVAL_S` giây, như chỉ mục F2.7 (con trỏ thời gian lùi 60 giây, lật trang theo id).
  Văn bản đổi khi: sửa văn bản, một tệp vừa đọc chữ, có giao việc mới. Đoạn mới hoặc đổi chữ thì ghi lại cả đoạn; chỉ
  đổi thuộc tính quyền thì cập nhật một phần, giữ véc-tơ. Văn bản bật hạn chế, bị hủy, văn bản đi về dự thảo: xóa mọi
  đoạn. Mọi tác vụ Meilisearch của một lượt phải xong thì con trỏ mới tiến; một tác vụ lỗi thì lượt sau đọc lại.
- **Tìm theo nghĩa** (tùy chọn): embedder `userProvided` đặt tên theo mô hình (`emb_qwen3_embedding_0_6b`); svc-files
  tự gọi Ollama `/api/embed` theo lô `MOC_AI_EMBED_BATCH` đoạn ở vòng nền, và không mở lô mới trong lúc một lượt hỏi
  đang gọi Ollama (nhúng câu hỏi, viết câu trả lời). Meilisearch không vào mạng `ai`. Chưa có véc-tơ thì đoạn vẫn tìm được bằng từ khóa; không có mô hình (CI) thì
  chỉ tìm từ khóa. Đổi `MOC_AI_EMBED_MODEL` là bỏ embedder cũ và nhúng lại từ đầu. Câu hỏi đưa đi nhúng mang tiền tố
  chỉ dẫn mà Qwen3-Embedding cần (`Instruct: …\nQuery: …`); đoạn văn bản thì không.
- **Khi nhúng lỗi.** Cấu hình tìm từ khóa và cấu hình embedder áp thành hai tác vụ: embedder bị Meilisearch từ chối thì
  ghi `index_failed` (`stage: embedder`), thử lại mỗi 60 giây, còn đồng bộ và xóa đoạn vẫn chạy (`semantic: false`).
  Lô nhúng lỗi vì quá giờ, mất kết nối, Ollama bận hay mất mô hình thì để lượt sau. Lỗi khác (HTTP 500, véc-tơ NaN…)
  thì nhúng lại từng đoạn; đoạn vẫn lỗi trong khi mô hình nhúng được đoạn khác hoặc câu mẫu thì bị đánh dấu
  `embed_model = "<mô hình>#failed"` (`embed_skipped` ghi id) để không chặn các đoạn sau: đoạn đó chỉ tìm được theo từ
  khóa, được nhúng lại khi chữ đổi hoặc đổi mô hình. Véc-tơ đầu tiên Ollama trả mà khác `MOC_AI_EMBED_DIMS` chiều là
  sai cấu hình: tắt tìm theo nghĩa, ghi lỗi `embed_dims_mismatch`, sửa biến rồi khởi động lại. `/readyz` báo số đoạn
  chờ nhúng và số đoạn hỏng.

**Quyền ở hai lớp, cả hai đứng trước mô hình và trước người dùng** (`scope.py`, `retrieve.py`):

1. **Lọc trước** trong Meilisearch: thuê ước lấy từ token (luôn đứng đầu), rồi điều kiện theo vai trò viết đúng như
   `office.document_visible` — văn thư, lãnh đạo: cả đơn vị; trưởng phòng: văn bản của phòng mình hoặc có giao việc
   cho phòng mình (token không có phòng thì không tìm gì); chuyên viên: mình tạo, được giao cho mình, hoặc văn bản đi
   của phòng mình. Lớp này chỉ quyết **độ phủ**.
2. **Hậu kiểm** bằng Hasura với **token người hỏi** (như tìm kiếm F2.7), bỏ cả văn bản đang `restricted`. Lớp này quyết
   **an toàn**: chỉ mục chậm vài giây sau khi bật hạn chế hay hủy giao việc cũng không lộ đoạn nào. svc-files không
   viết lại quy tắc quyền. Số ký hiệu, trích yếu, trạng thái trả về lấy từ Hasura (bản mới nhất), không từ chỉ mục.

**Tìm nới** (mỗi lần tìm theo từ khóa). Chiến lược `frequency` của Meilisearch bỏ dần từ phổ biến của câu tìm nhưng
luôn giữ từ hiếm nhất: hỏi "Điều kiện xét học bổng khuyến khích học tập là gì?" mà trong kho vài văn bản về xét tốt
nghiệp có chữ "điều kiện" thì lượt chính chỉ ra các văn bản đó, công văn trả lời (88/CTSV: "…xét chọn sinh viên có
điểm … từ 3,2…") không bao giờ ra. Lượt nới gửi một `/multi-search`: mỗi từ của câu tìm một câu riêng trong cùng phạm
vi, kèm số đoạn trong phạm vi. Mỗi từ nặng `ln(1 + N / df)` (từ không đoạn nào trong phạm vi có tính như `df` = 0,5,
để phạm vi hẹp không làm vài từ phổ biến thành "cả câu hỏi"); đoạn có tổng trọng số ≥ 50 % câu hỏi được thêm, qua hậu
kiểm như mọi đoạn. Rồi **mọi đoạn xếp chung theo tỷ lệ trọng số** câu hỏi mà đoạn có — kể cả các đoạn lượt chính đã
đọc nhưng chưa lấy; cùng tỷ lệ thì giữ thứ tự của Meilisearch: đoạn chỉ có "điều kiện … xét" không đứng trước đoạn có
gần đủ câu hỏi, dù lượt chính đã đủ đoạn. Kết quả của mỗi từ chỉ lấy `candidates` đoạn đầu, nên từ phổ biến còn được
tính cho đoạn có nguyên văn từ đó (bỏ dấu như Meilisearch) — đoạn có đủ câu hỏi không bị chấm thấp vì đứng sau trong
kết quả của từ phổ biến. Lượt nới lỗi thì giữ kết quả lượt chính. Nhật ký `office.assist.asked` ghi số đoạn nhờ tìm nới
(`relaxed`). Khi tìm theo nghĩa, phần nghĩa đã phủ câu hỏi dùng chữ khác nên không nới.

Không đoạn nào qua được hai lớp → `no_evidence`, **không gọi mô hình**; trả lời y hệt nhau dù văn bản không tồn tại hay
người hỏi không được đọc.

**Trả lời** (`vi.py`, `extract.py`, `grounding.py`, `answer.py`). Hai chế độ; giao diện gọi `extract` trước rồi tự gọi
`generate` nếu `ai_available`, gửi lại `ask_id`.

- `extract` (mặc định, tất định, không cần mô hình — đường của CI): câu tìm là tối đa 10 từ của câu hỏi đã bỏ từ dừng
  (Meilisearch chỉ xét 10 từ đầu). Mỗi đoạn lấy câu có nhiều từ của câu hỏi nhất (so trên chữ bỏ dấu; bằng điểm thì câu
  chỉ nhắc lại trích yếu, số ký hiệu xếp sau câu nội dung); giữ câu chung ≥ 34 % và ≥ 2 từ với câu hỏi; tối đa 3 câu, ưu tiên khác
  văn bản, mỗi câu ≤ 320 ký tự. Mỗi dòng `“<câu nguyên văn>” [n]`, `n` là số thứ tự nguồn. Tách câu theo lớp chữ PDF:
  dòng bị ngắt do dàn trang (dòng sau bắt đầu bằng chữ thường) nối lại; không tách ở `TP.`, `ThS.`, `PGS.`…, số thập
  phân, số ký hiệu, số thứ tự đầu dòng.
- `generate`: thêm câu trả lời do mô hình viết (`MOC_ASK_MODEL`, mặc định bằng `MOC_AI_MODEL`), chỉ khi mô hình sẵn
  sàng và còn ≥ 5 giây trong hạn. Mô hình chỉ thấy **4 đoạn đầu đã hậu kiểm**, mỗi đoạn ≤ 700 ký tự quanh câu tốt nhất,
  tổng ≤ `MOC_ASK_CONTEXT_CHARS`, bọc trong thẻ `<nguon so="1" ky_hieu="88/CTSV" trang="1">`; thẻ trùng tên trong chữ
  văn bản bị bỏ, mọi `<` `>` còn lại đổi thành `‹` `›`; lời dặn bảo mô hình không làm theo yêu cầu nằm trong dữ liệu; mô
  hình không có công cụ nào. `/api/chat` không stream, tắt suy nghĩ, ép JSON Schema `{du_can_cu, tra_loi}`, nhiệt độ
  0,1, hạt giống cố định. **Đầu ra kiểm chặt**: 10–1 200 ký tự, không ký tự điều khiển / vô hình, không `http`, `<`,
  `>`, ```` ``` ````. **Máy chủ gán trích dẫn, không phải mô hình** (Qwen3-1.7B viết đúng nội dung nhưng không ghi
  `[n]`: 0/19 câu qua cách kiểm cũ): bỏ mọi `[n]` mô hình ghi, rồi với từng câu chọn đoạn chứa mọi số từ 2 chữ số của
  câu (`3.2` khớp `3,2`, `200 000` khớp `200.000`, `15/11` khớp `15/11/2026`; số trong câu hỏi cũng được) và ≥ 60 % từ
  mới của câu (từ không có trong câu hỏi), nhiều từ mới nhất thì được trích; `[n]` đặt trước dấu câu cuối. Một câu
  không đoạn nào đạt là loại cả câu trả lời. Không đạt thì người dùng vẫn thấy câu trích, kèm `model_rejected`. Giao diện hiện câu trả lời dạng chữ thuần.
- **Hạn và lượt.** Hạn tổng `MOC_ASK_DEADLINE_S` (50 giây, dưới 60 giây của APISIX); nhúng câu hỏi ≤ 5 giây (lỗi thì
  tìm từ khóa, `embed_unavailable`); gọi mô hình ≤ `MOC_ASK_MODEL_TIMEOUT_S`. Một lượt `generate` một lúc
  (`MOC_ASK_CONCURRENCY`), chờ quá `MOC_ASK_QUEUE_S` thì `503 busy` kèm `Retry-After: 10`; `extract` không phải chờ.
  Người hỏi ngắt kết nối (nút "Dừng", Esc, đóng trang) thì lượt bị hủy: lời gọi Ollama ngắt, lượt sinh được nhả, không
  trả lời nên không ghi sổ — chỉ nhật ký `office.assist.ask_cancelled`.
- **Trợ lý có danh tính, có sổ.** Mỗi lượt hỏi ghi **một** dòng `assistant.answered` (thực thể `ai.questions`, id =
  `ask_id`) bằng vai trò Hasura `agent`: preset ép `actor_id = moc-assistant`, `actor_kind = agent`, thuê ước. `diff`
  chỉ có siêu dữ liệu: `user_id, ask_id, mode, status, answer_source, hits, cited` (số nguồn được trích), `documents`
  (id các văn bản trả về), `semantic, model, embed_model, duration_ms, warnings` — **không câu hỏi, câu trả lời, đoạn
  trích**. **Không ghi được sổ thì không trả lời** (`503 database_unavailable`). Lượt `generate` gửi lại `ask_id` nên
  hai dòng sổ cùng một thực thể.
- **Nhật ký không có chữ**: `office.assist.asked` {tenant_id, actor_id, mode, status, q_length, terms, candidates, hits,
  cited, semantic, model, warnings, duration_ms}, `office.assist.ask_failed` {code}, `office.assist.model_rejected`
  {reason}, `office.assist.embed_failed` {reason}, `office.assist.ai_ready` / `ai_unavailable` (khi đổi trạng thái),
  `office.assist.embed_dims_mismatch` {dims, expected} (mức error), `office.assist.indexed` / `embedded` /
  `embed_skipped` {ids} / `index_failed` {error, stage, reason}, `config.warning` {message} lúc khởi động.

| Kết quả | Ý nghĩa |
|---|---|
| `status` | `answered` có câu trả lời · `passages_only` có đoạn liên quan mà không câu nào đủ khớp để trích · `no_evidence` không đoạn nào (`sources: []`) |
| `answer`, `extract` | `{text, source: extract\|model, model}`; `extract` luôn là câu trích, `answer` là câu của mô hình khi đạt kiểm, không thì bằng `extract`; null khi không có |
| `sources[]` | Tối đa `MOC_ASK_TOP_K`, theo thứ tự xếp hạng, `n` từ 1: `document_id, symbol, type_code, type_name, summary, issuer_name, issued_on, direction, status` (từ Hasura), `kind: page\|meta, file_id, file_role: main\|attachment\|issued, page, excerpt` (≤ 600 ký tự quanh câu tốt nhất, một dòng), `cited` |
| `semantic` · `ai_available` | Lượt này có tìm theo nghĩa · mô hình viết câu trả lời đang sẵn sàng |
| `warnings` | `embed_unavailable`, `model_unavailable`, `model_timeout`, `model_rejected`, `model_declined` (mô hình nói không đủ căn cứ) |
| `400 invalid_question` | Rỗng sau chuẩn hóa, > 500 ký tự, có ký tự điều khiển, chỉ toàn từ dừng |
| `401` · `403` | Thiếu / sai token, Hasura từ chối token lúc hậu kiểm · vai trò không được hỏi |
| `503` | `assistant_disabled` (`MOC_ASK_ENABLED=false`) · `busy` · `search_unavailable` (Meilisearch) · `database_unavailable` (Hasura, hoặc không ghi được sổ) |

**Số đo** (`make do-hoi-dap` trên bản cài thử, 21/10/2026: kho mẫu `seed/hoi-dap/` 6 văn bản 14 trang + dữ liệu `make
seed`, 19 câu có đáp án trong `cau-hoi.json` — 16 câu dương, 2 câu không có trong kho, 1 câu hỏi văn bản người hỏi không
được xem; hỏi đúng người, qua APISIX; máy đo như trên). Kho mẫu nhỏ, câu hỏi do đội viết — **mức trần**, số thật khi
có đơn vị chạy thử.

| | Không bật `ai` (CI) | Bật `ai` (Qwen3-Embedding-0.6B + Qwen3-1.7B, CPU) |
|---|---|---|
| recall@3 (nguồn đúng trong 3 nguồn đầu, câu dương) | 16 / 16 | 16 / 16 |
| Từ chối đúng (câu âm, câu bị cấm) | 3 / 3 (2 `no_evidence`, 1 `passages_only`) | 3 / 3 (`no_evidence`) |
| Lượt có nguồn bị cấm (văn bản hạn chế, văn bản không được xem) | 0 | 0 |
| Câu trích có từ khóa của đáp án | 15 / 16 | 15 / 16 |
| Thời gian `extract` p50 / p95 | 20 / 61 ms | 0,44 / 0,70 s (gồm nhúng câu hỏi) |
| Câu của mô hình qua kiểm · có từ khóa · trích đúng nguồn | — | 16 / 16 · 16 / 16 · 16 / 16 |
| Thời gian `generate` p50 / p95 | — | 14,3 / 23,5 s |

Câu tìm lai (tỷ trọng nghĩa 0,5) của câu dương có nguồn đúng đứng đầu với điểm ≥ 0,88, câu âm điểm cao nhất ≤ 0,70 —
nên ngưỡng `MOC_ASK_MIN_SCORE_SEMANTIC` 0,75. Trước khi máy chủ tự gán trích dẫn, cùng mô hình chỉ qua kiểm 0 / 19
(không ghi `[n]`). Nhúng 61 đoạn của kho mẫu mất khoảng 2 phút. Ngắt kết nối giữa lượt `generate` qua APISIX (`499`
sau 4 giây): svc-files hủy lượt, không ghi sổ, câu hỏi kế tiếp chạy ngay.

Chưa làm, giới hạn đã biết:

- Gỡ tệp đính kèm mà không sửa văn bản (gọi thẳng `delete_office_document_files`): đoạn của tệp còn trong chỉ mục tới
  lần văn bản đổi sau, và hậu kiểm theo văn bản không bắt được — như giới hạn đã ghi của F2.7 (giao diện luôn sửa văn
  bản trong cùng lệnh).
- Hủy một giao việc không đổi `updated_at` hay `assigned_at`, nên thuộc tính quyền của đoạn còn cũ tới lần văn bản đổi
  sau. Việc này chỉ làm giảm độ phủ; hậu kiểm vẫn giữ an toàn.
- Meilisearch chỉ xét 10 từ đầu của câu tìm; câu hỏi gõ không dấu bỏ được ít từ dừng hơn. Bản scan chỉ có đoạn "trích
  yếu" (chưa OCR nền). Tách câu dựa trên lớp chữ PDF, có thể lệch với PDF dàn trang lạ.
- Ngưỡng và hằng số kiểm (`RELAX_MIN`, độ phủ 60 %, ngưỡng câu trích) chỉnh trên kho mẫu nhỏ; cần đo lại trên kho
  thật. Kiểm theo từ không bắt được câu sai mà dùng đúng chữ của nguồn (vd "loại Xuất sắc" khi nguồn có cả "Xuất sắc"
  lẫn "Tốt"); câu có từ đệm không có trong nguồn ("… như sau:") có thể bị loại oan — người dùng vẫn có câu trích.
- Tìm theo từ khóa không hiểu từ đồng nghĩa: câu hỏi dùng chữ khác hẳn văn bản chỉ ra khi bật tìm theo nghĩa.

### Văn bản tương tự cho tác tử gợi ý giao việc (F4.3)

`assist/similar.py`. Văn thư vào sổ một văn bản đến thì quy trình mở nhánh song song `goiYGiaoViec`; tác tử
`moc-assigner` của svc-workflow nhận việc, gọi `POST /internal/similar-documents` để lấy các văn bản đến **đã giao**
giống văn bản này, rồi tự bỏ phiếu chọn đơn vị chủ trì và hạn từ lịch sử giao việc của chúng (README svc-workflow).
svc-files **chỉ truy xuất**: không chọn đơn vị, không lưu gợi ý, không ghi sổ.

- **Gọi được**: chỉ token tài khoản dịch vụ trong `MOC_SERVICE_CLIENTS` như `/internal/issue` (`401`, `403`
  `not_a_service` với token người dùng). Không có trong `/openapi.json`, APISIX không có route tới. Không có biến cấu
  hình mới: route chạy theo `MOC_ASK_ENABLED` — tắt trợ lý thì chỉ mục đoạn không đồng bộ, route trả `503
  assistant_disabled` và tác tử bỏ qua văn bản.
- **Văn bản đích** đọc bằng vai trò service của **đúng thuê ước trong yêu cầu** (`SimilarTarget`): thuê ước khác hay
  không có → `404 not_found`; văn bản đi → `409 not_incoming`; văn bản hạn chế → `409 restricted` — dừng ở đó, không
  gọi Meilisearch, không nhúng.
- **Câu tìm chỉ lấy từ trích yếu**: chuẩn hóa NFC, gộp khoảng trắng; bỏ **một** tiền tố khuôn mẫu ở đầu ("Về việc",
  "V/v", "V/v:", "Thông báo", "Kế hoạch", "Giấy mời", "Quyết định", "Công văn", "Tờ trình", không phân biệt hoa
  thường); bỏ chữ "việc"; rồi lấy tối đa 10 term như câu hỏi F4.2. "Về việc xét cấp học bổng khuyến khích học tập học
  kỳ II năm học 2026–2027" → `xét cấp học bổng khuyến khích tập kỳ II năm`. Không dùng nội dung tệp: Meilisearch chỉ
  xét 10 từ đầu, mà đầu công văn toàn khuôn mẫu ("Căn cứ…", "Kính gửi…"). Trích yếu chỉ có khuôn mẫu → `hits: []`,
  không tìm.
- **Tìm theo nghĩa (tùy chọn)**: có mô hình nhúng và Meilisearch đã có embedder thì nhúng trích yếu kèm chỉ dẫn riêng
  của Qwen3-Embedding ("…retrieve earlier letters about the same matter"), tối đa **3 giây**, trong lúc đó vòng nhúng
  nền không mở lô mới. Quá giờ, lỗi, hay tìm lai bị Meilisearch từ chối thì tìm lại chỉ bằng từ khóa
  (`semantic: false`) — CI không có mô hình vẫn chạy đủ.
- **Truy xuất** dùng lại `Retriever` của F4.2 (`Retriever.similar`) trên chỉ mục đoạn: lọc trước thuê ước (luôn đứng
  đầu), `direction = "in"`, `status IN ["in_progress", "done", "archived"]` (đã có người nhận xử lý), trừ chính văn bản
  đích; gộp đoạn theo văn bản, điểm = `_rankingScore` cao nhất trong các đoạn (4 chữ số), giảm dần, tối đa `limit`.
  Tìm theo từ khóa thì **luôn chạy thêm lượt tìm nới** của F4.2 (mỗi từ một câu, cân theo độ hiếm), kể cả khi lượt chính
  đã đủ: chiến lược `frequency` bắt mọi văn bản phải có từ hiếm nhất của trích yếu, mà từ hiếm thường không nói gì về
  chủ đề — "học kỳ II" thì chỉ văn bản có chữ "II" được xét, 88/CTSV ("học kỳ I", cùng chủ đề) không bao giờ ra. Điểm
  văn bản = số lớn hơn giữa `_rankingScore` và tỷ lệ trọng số từ chung (cùng thang 0–1, cùng tăng theo độ phủ câu tìm).
  **Hậu kiểm** bằng vai trò service của thuê ước: văn bản hạn chế (kể cả vừa bật, chỉ mục chưa kịp xóa), văn bản vừa
  hủy bị bỏ; chiều, trạng thái kiểm lại trên bản mới nhất từ Hasura. Văn bản hạn chế không bao giờ có đoạn trong chỉ
  mục, nên không bao giờ làm căn cứ.
- **Không có ngưỡng điểm ở đây**: ngưỡng `MOC_SUGGEST_MIN_SCORE` thuộc svc-workflow. Điểm tìm theo từ khóa và điểm
  tìm lai có phân bố khác nhau (ngưỡng tìm lai `MOC_ASK_MIN_SCORE_SEMANTIC` vẫn áp như F4.2).
- **Không trả chữ văn bản, nhật ký không có chữ**: kết quả chỉ có id và điểm. Nhật ký `office.assist.similar`
  {tenant_id, document_id, caller, hits, terms, semantic, duration_ms, error} — `error` là lỗi tìm lai đã lùi về từ
  khóa; lần bị từ chối chỉ có `code` (`not_found`, `restricted`, `search_unavailable`…), `error` (lỗi Meilisearch,
  Hasura nếu có) và `duration_ms`. Không có trích yếu, không có câu tìm.

| Kết quả | Ý nghĩa |
|---|---|
| `hits[]` | `{document_id, score}` — văn bản đến đã giao, đã hậu kiểm, điểm giảm dần, ≤ `limit` |
| `terms` | Số term của câu tìm (0: trích yếu chỉ có khuôn mẫu, không tìm) — không gửi chữ |
| `semantic` · `duration_ms` | Lượt này có tìm theo nghĩa · thời gian xử lý ở svc-files |
| `404 not_found` | Không có văn bản trong thuê ước `tenant_id` |
| `409 not_incoming` · `409 restricted` | Văn bản đi · văn bản hạn chế — không tìm gì thêm |
| `503` | `assistant_disabled` (`MOC_ASK_ENABLED=false`) · `search_unavailable` (Meilisearch) · `database_unavailable` (Hasura) |

Giới hạn: chỉ mục đoạn đồng bộ mỗi `MOC_ASK_SYNC_INTERVAL_S` giây, nên văn bản vừa chuyển sang "đang xử lý" vài giây
trước chưa làm căn cứ được; trích yếu quá ngắn hay chỉ có từ chung thì ít kết quả đúng.

### Che thông tin cá nhân (F4.4)

`pii.py` — tự viết, chỉ dùng `re` của thư viện chuẩn (QĐ-006 trong
[`docs/architecture.md`](../../docs/architecture.md)); `svc_workflow/pii.py` là bản chép y hệt byte, test của
svc-workflow đỏ ngay khi hai bản lệch nhau. Mô hình ngôn ngữ và nhật ký **không thấy** số định danh, số điện thoại,
email, số tài khoản mà bộ nhận dạng nhận ra trong văn bản (cách viết sót: mục giới hạn bên dưới); người có quyền đọc
văn bản thì vẫn thấy số thật: chỉ mục tìm kiếm, câu trích nguyên văn, nguồn trả người hỏi và sổ kiểm toán giữ bản gốc.
Che luôn bật, không có biến cấu hình để tắt.

| Loại | Nhãn ở nhật ký, lối ra mô hình | Nhãn trong ngữ cảnh F4.2 | Nhận khi |
|---|---|---|---|
| Số định danh / CCCD 12 số | `[CCCD]` | `[CCCD-n]` | 3 số đầu là một trong 63 mã tỉnh (Thông tư 59/2021/TT-BCA), chữ số thứ 4 là 0–3, năm sinh không ở tương lai; **hoặc** 12 số bất kỳ ngay sau từ khóa ("CCCD", "căn cước", "số định danh"…) |
| CMND | `[CMND]` | `[CMND-n]` | **chỉ** ngay sau từ khóa ("CMND", "CMT", "chứng minh nhân dân"…), 9 hoặc 12 số |
| Điện thoại | `[SĐT]` | `[SĐT-n]` | di động 10 số có đầu số đã cấp (10/2026, gồm 095), máy bàn `02x` 11 số, di động 11 số cũ; `+84`, `(+84)`, `0084`, `+84 (0)`, `84…` liền, mã vùng `(024)`; viết liền hay theo nhóm (nhóm đầu ≥ 3 chữ số, trừ sau `+84` / mã vùng) |
| Email | `[EMAIL]` | `[EMAIL-n]` | cú pháp địa chỉ có tên miền cấp cao (`user@localhost`, `@pytest.fixture` không khớp) |
| Số tài khoản | `[STK]` | `[STK-n]` | **chỉ** ngay sau từ khóa ("số tài khoản", "STK", "tài khoản ngân hàng số"…), 6–19 chữ số |

Từ khóa so trên bản bỏ dấu, không phân biệt hoa thường. Không che: UUID, số ký hiệu (`131/ĐT-ĐHM`), ngày, tiền, tổng đài
1800 / 1900, số 8 chữ số, mã số thuế 10 số sau "MST" / "mã số thuế", dãy số nhỏ của bảng, lịch ("Tuần 01 02 03 04 05
06", "phòng 08 12 15 20 22"), dãy đếm ("001⏎002⏎003⏎004"). Nhận theo cấu trúc, không theo "dãy số đủ dài": chuỗi số ứng
viên (các nhóm chữ số cách nhau **một** dấu cách, chấm, gạch, tab, cách hẹp hay xuống dòng; `_` là ranh giới như dấu
cách) → cụm tối đa 6 nhóm liền nhau, nhóm đầu ≥ 3 chữ số → kiểm mã tỉnh, thế kỷ, đầu số. Che xong một số có thể gỡ điều
kiện chặn của số bên cạnh (`001205000017,0084…@…`), nên bộ che lặp tới khi bản che không còn gì để che (tối đa 3 lượt):
bản che idempotent. Thời gian tuyến tính theo độ dài chữ (chuỗi bệnh lý 100 000 ký tự ≤ 500 ms, văn bản 20 000 ký tự cỡ
10 ms).

- **Chữ gửi mô hình, lớp 1 — lối ra.** Mọi lời gọi Ollama đều che trước khi gửi: nhúng đoạn và câu hỏi (F4.2), nhúng
  trích yếu (F4.3), viết câu trả lời (F4.2) ở `assist/ai.py`; viết trích yếu (F4.1) ở `docread/summarize.py` — che
  **trước** khi cắt `MOC_AI_MAX_CHARS`, để không lọt mẩu số vắt qua chỗ cắt. Không byte chữ nào tới `MOC_AI_URL` mà
  chưa qua bộ che. Trích yếu mô hình viết ra có nhãn thì bị loại như trích yếu có số điện thoại (`model_rejected`).
  Bản che idempotent: `chat` (viết câu trả lời) mà còn phải che thêm nghĩa là chỗ gọi đã quên che → cảnh báo
  `office.assist.pii_at_egress` `{"masked": n}` — bình thường không bao giờ có, có là lỗi. `embed` che mà không ghi
  gì: đoạn nhúng ở vòng nền luôn mang chữ gốc. Đầu vào nhúng mang nhãn `[SĐT]`, nên tìm theo nghĩa không phân biệt
  hai số; tìm theo từ khóa vẫn dùng số gốc.
- **Lớp 2 — ngữ cảnh F4.2** (`assist/answer.py`, `assist/grounding.py`). Mỗi lượt `generate` một bộ che đánh số:
  câu hỏi che trước (số trong câu hỏi nhận nhãn số 1), rồi các đoạn. Cùng giá trị thì cùng nhãn (`+84 912…` và
  `0912…` là một số; email so chữ thường), nên mô hình vẫn biết số nào của ai. Phần kiểm trích dẫn đọc đúng bản che mô
  hình đã đọc. Số ký hiệu ở đầu mỗi nguồn không qua bộ che của lượt, chỉ qua lối ra.
- **Trích dẫn giữ nguyên.** Câu tốt nhất vẫn chọn trên chữ gốc (câu trích nguyên văn). Dựng ngữ cảnh: che cả đoạn,
  đổi vị trí câu tốt nhất sang bản che (`Masked.window`), **rồi mới** cắt ≤ 700 ký tự — cửa sổ không bao giờ cắt đôi
  một con số. `[n]`, trang, số ký hiệu không đổi; nhãn không có dạng `[n]` nên không bị hiểu là trích dẫn. Câu trả lời
  của mô hình giữ nhãn, không điền số thật trở lại (mô hình có thể đặt nhãn sai chỗ, gán số người này cho người khác);
  trang Hỏi đáp ghi "số thật nằm trong văn bản nguồn: xem câu trích nguyên văn và các nguồn bên dưới" và tự mở
  khối câu trích.
- **Nhật ký.** `_setup_logging` gọi `pii.install_log_redaction`: bộ lọc `PiiFilter` gắn vào logger của dịch vụ,
  `uvicorn`, `uvicorn.error`, `uvicorn.access` và handler của chúng. Bộ lọc che chuỗi cuối cùng của bản ghi (message đã
  ghép tham số, traceback, stack); dòng truy cập của uvicorn **bỏ chuỗi truy vấn** (`GET /api/search?… HTTP/1.1`),
  vì chuỗi đã mã hóa phần trăm (`0912%20345%20678`) thì không regex nào thấy. Che hỏng thì cả dòng thành
  `core.log.redaction_failed`: thà mất một dòng. Tệp nhiễm tên `don-0912345678.txt`: dòng `core.file.rejected` ghi
  `don-[SĐT].txt`, còn dòng sổ `file.rejected` giữ tên gốc — sổ có phân quyền và chuỗi băm, che vào sổ thì mất giá
  trị chứng cứ. APISIX và nginx của giao diện cũng bỏ chuỗi truy vấn và Referer:
  [`gateway/README.md`](../../gateway/README.md).
- **Số chỗ đã che** (không bao giờ có giá trị) ở khóa `masked`, không vào sổ kiểm toán:

  | Sự kiện | `masked` |
  |---|---|
  | `office.assist.asked` | tổng số chỗ bộ che của lượt `generate` đã che — câu hỏi và cả đoạn, kể cả số nằm ngoài cửa sổ 700 ký tự; 0 khi không hỏi mô hình |
  | `office.assist.model_rejected` | như trên, cho lượt mô hình viết bị loại |
  | `office.intake.read` | số chỗ đã che trong phần chữ thật sự gửi mô hình viết trích yếu (trước chỗ cắt `MOC_AI_MAX_CHARS`); 0 khi không gọi mô hình hay trả gợi ý đã lưu |
  | `office.assist.pii_at_egress` (cảnh báo) | số chỗ lối ra `chat` phải che thêm — chỉ xuất hiện khi có lỗi |

- **Dòng lệnh** (đọc stdin, svc-workflow dùng `svc_workflow.pii`):

  ```bash
  docker compose exec -T svc-files python -m svc_files.pii mask  < don.txt   # bản che, nhãn trơn [SĐT]
  docker compose exec -T svc-files python -m svc_files.pii count < don.txt   # {"chars", "total", "spans"} — không in giá trị
  ```

**Đo — `make do-che-pii`** (không cần Docker; `test_pii_corpus.py` và `test_pii_mutation.py` đã chạy trong
`make test`). Che nhầm trên kho mẫu (đo 22/10/2026, 22 văn bản đến), đọc như bản chạy thật (lớp chữ và bố cục của
PDF, TSV OCR có sẵn) — tổng 81 023 ký tự, 747 chuỗi số ứng viên, 0 chỗ bị che:

| Nguồn | Tệp / chuỗi | Ký tự | Chuỗi số ứng viên | Bị che |
|---|---|---|---|---|
| `seed/van-ban-den`, PDF có lớp chữ | 15 | 37 416 | 370 | **0** |
| `seed/van-ban-den`, bản scan (TSV OCR) | 7 | 6 442 | 68 | **0** |
| `seed/hoi-dap`, mọi trang | 6 | 19 957 | 144 | **0** |
| Nhãn, câu hỏi, lịch sử giao việc | 1 248 chuỗi | 17 208 | 165 | **0** |

Bắt đúng chỉ chứng minh được trên bộ định dạng tổng hợp (`test_pii.py`), vì kho mẫu không có — và không được có —
dữ liệu thật mang thông tin cá nhân: 95 chỗ dương tính trong 84 chuỗi đều bị che (cả số ngắt dòng, tên tệp
`don_0912…`), 80 chuỗi âm tính khó (giấy tờ, ngày, tiền, UUID, hex, mã số thuế, đầu số chưa cấp, dãy số nhỏ của bảng,
email giả…) không bị che, 1 144 ca đột biến dữ liệu vào (11 toán tử) đúng kỳ vọng. Đột biến mã: 15 đột biến của
`pii.py` (bỏ vùng bảo vệ UUID, bỏ kiểm mã tỉnh, nới đầu số, bỏ cổng mã số thuế, giữ chuỗi truy vấn, xuống dòng không
là phân cách, bỏ điều kiện nhóm đầu ≥ 3 chữ số, che một lượt…) — **15/15 bị test giết**, khoảng 1,5 giây. Có chỗ che
nhầm, sót một ca dương tính hay một đột biến sống sót thì lệnh thoát 1.

**Giới hạn:**

- **Sót có chủ đích:** số dính chữ (`ĐT0912…`), số có hai ký tự trắng liền (hai dấu cách, dòng trống, cách rồi
  xuống dòng), CCCD sau `/`; số viết từng cặp (`09 12 34 56 78`: nhóm đầu 2 chữ số), `84 912 345 678` (bỏ dấu cộng mà
  có cách — viết liền `84912345678` thì che), số viết theo nhóm nối bằng phẩy không cách (`0912 345 678,0987 654 321`;
  hai dãy ≥ 9 chữ số liền nối bằng phẩy thì che cả hai); số máy bàn kiểu cũ 10 số (trước 2017), số nước ngoài; CMND
  và số tài khoản không có từ khóa; chữ không ở dạng NFC có thể sót từ khóa.
- **Che nhầm có chủ đích:** dãy mã 3 chữ số trùng dạng CCCD hợp lệ (mã tỉnh, chữ số thế kỷ, năm sinh đều đúng), như
  `012 045 078 090`, `010.203.040.506`, danh sách mã tỉnh `001 002 004 006` — mơ hồ với CCCD viết 3-3-3-3, che dư là
  phía an toàn.
- **Xuống dòng:** một ký tự trắng bất kỳ (dấu cách, xuống dòng, `\r\n`, tab, cách không ngắt, cách hẹp) là phân cách
  nhóm, nên số bị dàn trang ngắt dòng trong lớp chữ PDF, OCR ("0912 345⏎678", "001205⏎000017") bị che ở mọi lối ra:
  nhúng đoạn, trích yếu F4.1, ngữ cảnh F4.2. Số cách bởi dòng trống thì không: ngữ cảnh F4.2 gộp khoảng trắng rồi che
  lại bằng cùng bộ che, còn nhúng đoạn và trích yếu F4.1 gửi nguyên (đoạn của `chunks.py` và chữ trích yếu bỏ dòng
  trống giữa hai dòng nên ít gặp). Ngược lại, số cuối dòng ghép được với số đầu dòng sau: cột bảng tách mỗi ô một dòng
  có thể thành một số và bị che (che thừa; dãy đếm đã loại). Sau từ khóa, trọn chuỗi vắt dòng sai độ dài thì lùi về
  cuối một dòng ("CMND số 123456789⏎2. Địa chỉ" che 9 số). Mã số thuế bị cửa sổ cắt mất từ khóa "MST" đứng trước
  thì bị che như số điện thoại (che thừa).
- **Không làm:** họ tên, địa chỉ (cần nhận dạng thực thể, chưa có mô hình tiếng Việt nhẹ), hộ chiếu, biển số xe,
  giấy phép lái xe, số BHXH. Điểm mở rộng: thêm một nguồn khoảng vào `find()` và một nhãn vào `LABELS`, sửa
  `LABEL_RE` cùng `MASK_RE` của app-office (test so hai mẫu).
- **Che quá tay trong chữ gửi mô hình:** bộ nhận dạng không phân biệt cá nhân với tổ chức, nên email và số máy bàn
  của cơ quan cũng bị che — hỏi "email phòng đào tạo" thì mô hình trả `[EMAIL-1]`, câu trích có địa chỉ thật. Kho
  hỏi đáp mẫu không có chỗ nào bị che, nên số đo `make do-hoi-dap` không đổi.
- **Danh mục đổi theo thời gian:** đầu số di động mới phải thêm vào `MOBILE_PREFIXES`; chưa xác nhận số định danh của
  người đăng ký khai sinh sau khi sắp xếp tỉnh (07/2025) còn nằm trong 63 mã tỉnh — nếu không, chỉ đường từ khóa bắt
  được.
- **Véc-tơ nhúng cũ:** đoạn đã nhúng trước F4.4 (trên chữ chưa che) giữ véc-tơ cũ trong Meilisearch tới khi nhúng lại
  (đổi `MOC_AI_EMBED_MODEL` hoặc dựng lại chỉ mục).
- **Nhật ký ngoài phạm vi:** Hasura (http-log khi lỗi), PostgreSQL (`DETAIL` của lỗi ràng buộc), Keycloak (tên đăng nhập
  khi đăng nhập sai), Meilisearch và Ollama (khi bật `OLLAMA_DEBUG`) không qua bộ lọc nào; `make demo-che-pii` đọc nhật
  ký Hasura, PostgreSQL, Keycloak, Meilisearch và chỉ cảnh báo. `error_log` của APISIX và nginx có định dạng cố định:
  yêu cầu nào làm một plugin ghi lỗi (token hết hạn khi đang ở trang Tìm kiếm, phía sau lỗi…) thì dòng lỗi vẫn có
  `request: "GET …?q=…"`; Referer thì không còn câu tìm vì giao diện gửi `Referrer-Policy: strict-origin`. Bản ghi của
  logger khác không có handler, rơi vào `logging.lastResort` (WARNING trở lên), không qua `PiiFilter`.
- **Gỡ lỗi tìm kiếm khó hơn** vì nhật ký truy cập không còn câu tìm; bù lại `core.search` vẫn có `q_length`, `hits`,
  `request_id`.

Căn cứ: Luật Bảo vệ dữ liệu cá nhân số 91/2025/QH15 và Nghị định 356/2025/NĐ-CP (cùng hiệu lực từ 01/01/2026) xếp số
điện thoại, số định danh cá nhân vào dữ liệu cá nhân cơ bản, thông tin ngân hàng vào nhóm nhạy cảm.

### Văn bản đi và cổng xác thực

- **Dựng PDF** (`render.py`): khuôn HTML theo thể thức NĐ 30, Phụ lục I — cơ quan chủ quản, tên đơn vị, số ký
  hiệu, quốc hiệu, tiêu ngữ, địa danh và ngày (ngày dưới 10, tháng 1–2 có số 0), tên loại và trích yếu (công văn:
  "V/v …" dưới số, "Kính gửi"), nội dung, nơi nhận kèm "Lưu: VT, <phòng>.", chức vụ và tên người ký, giờ ký duyệt
  trên Signet. Bản phát hành có mã QR dẫn tới `<MOC_PUBLIC_URL>/xac-thuc/<mã>`. Mọi chữ người dùng nhập được thoát
  HTML. Phông Liberation Serif (cùng số đo Times New Roman) cài trong image.
- **"Đã duyệt trên hệ thống Signet"** chỉ ghi lại việc người ký bấm duyệt trong Signet. Tính toàn vẹn đến từ SHA-256 của
  tệp, lưu trong CSDL và trong sổ kiểm toán chuỗi băm, kiểm được ở cổng xác thực. Từ F4.5 bản phát hành (không hạn
  chế) có thêm chữ ký số PAdES bằng PKI nội bộ — chỉ minh họa (mục Ký số văn bản đi).
- **Dữ liệu dựng lấy từ CSDL**, không từ người gọi: `/internal/issue` chỉ nhận id văn bản, thuê ước, người thực
  hiện. Bản phát hành vẫn qua ClamAV và vào `core.files` như mọi tệp.
- **Cổng xác thực** tra khung nhìn `office.issued_documents` bằng vai trò Hasura `verifier`, mỗi lần đúng một văn
  bản. Nhật ký chỉ ghi cách tra (mã hay băm) và kết quả.

### Ký số văn bản đi (F4.5, chỉ minh họa)

`signing.py`. **Chỉ minh họa, không có giá trị pháp lý như chữ ký số công cộng**: chứng thư do CA nội bộ trong két
của Signet cấp (CN "CA nội bộ Signet - MẪU, chỉ minh họa"), CA này không nằm trong danh sách tin cậy nào nên trình
đọc PDF báo chữ ký "chưa tin cậy" — đúng như mong đợi (nhập chứng thư CA vào trình đọc thì báo hợp lệ).

- **Khóa ký không rời két.** Mỗi đơn vị một khóa transit `moc-ky-so-<id đơn vị>` (RSA-3072), svc-files tạo ở lần ký
  đầu. svc-files chỉ gửi phần thuộc tính đã ký sang `transit/sign/<khóa>/sha2-256` (PKCS#1 v1.5); két ghi sổ từng
  lần ký. Policy của svc-files không có `transit/export`, `transit/backup`.
- **Chứng thư.** CA gốc một tầng dựng trong `setup()` của `openbao/start.sh`. Phiên bản khóa chưa có chứng thư thì:
  CSR do chính transit ký (`transit/keys/<khóa>/csr`) → `pki/sign/moc-van-thu` với CN "<đơn vị>, <cơ quan chủ quản>"
  (quá 64 byte UTF-8 thì chỉ tên đơn vị: chữ có dấu tốn 2–3 byte, "Khoa Công nghệ thông tin, Trường Đại học Công
  nghiệp" là 67 byte) → kiểm chứng thư mang đúng khóa công khai của transit → gắn chuỗi lá + CA vào
  phiên bản khóa (`set-certificate`). Chứng thư lá sống 1 năm, KU DigitalSignature + ContentCommitment, EKU Document
  Signing. Hai lần phát hành đầu của một đơn vị chạy song song vẫn chỉ tạo một khóa, xin một chứng thư.
- **Luồng `/internal/issue`**: dựng PDF → ký → tự kiểm → SHA-256 → ClamAV → lưu → thêm `core.files` và
  `core.file_signatures` trong **một** mutation. Băm trả svc-workflow, `content_sha256`, sự kiện `issued`, sổ kiểm
  toán, bản liên thông (chép nguyên byte), cổng xác thực đều theo bản đã ký — svc-workflow không đổi. Mã QR mã hóa
  URL theo mã tra cứu nên không đổi.
- **Dạng chữ ký**: PAdES B-B (`ETSI.CAdES.detached`, SHA-256), chữ ký chứng nhận không cho sửa (DocMDP P=1), ô ký ẩn
  `MocKySo`, lý do "Phát hành văn bản <số ký hiệu>", địa danh, liên hệ là URL xác thực. Bản đã ký được tự kiểm bằng
  pyHanko với đúng CA của két (phủ cả tệp, không có sửa đổi sau khi ký); không đạt thì phát hành không ký.
- **Văn bản hạn chế không ký**: mỗi lần mở bị viết lại để đóng dấu người xem nên chữ ký hỏng ngay lần đầu; người nhận
  kiểm bằng mã. **Văn bản phát hành trước F4.5** giữ nguyên (ký lại sẽ đổi băm đã ghi sổ): `signature: null`.
- **Kiểm mật mã một tệp** bằng pyHanko, chỉ tin CA của két, không tải gì từ mạng:

  ```bash
  docker compose exec -T svc-files python -m svc_files.signing verify < van-ban.pdf
  # CA mặc định đọc từ két; --ca <tệp> là đường dẫn TRONG container (chép vào trước bằng docker compose cp)
  ```

  Dòng đầu nói kết quả; mã thoát `0` hợp lệ · `1` đã sửa sau khi ký (lớp sửa bổ sung, byte nối thêm), chữ ký không
  khớp nội dung, chứng thư không do CA nội bộ Signet cấp, không có chữ ký · `2` không đọc được PDF hoặc không lấy
  được CA (mặc định `$MOC_OPENBAO_ADDR/v1/pki/ca/pem`, không cần token). Chứng thư đã hết hạn mà hợp lệ tại giờ ký tự khai thì
  vẫn `0`, kèm một dòng ghi chú.

| Tình huống | `/internal/issue` | Nhật ký |
|---|---|---|
| Ký được | `201`, PDF đã ký, có dòng `core.file_signatures` | `office.document.signed` {key_name, key_version, serial, duration_ms} |
| Văn bản hạn chế, `MOC_SIGN_ENABLED=false`, không có két | `201`, không ký | — |
| Két chưa có CA (`pki/ca/pem` trả 204/403/404: két khởi tạo trước F4.5) | `201`, không ký; 300 giây sau dò lại | `office.signing.disabled` {reason: no_pki}, một lần mỗi lượt dò |
| Két từ chối khóa ký hay `pki/sign` (`403`, policy cũ) | `201`, không ký; 300 giây sau dò lại | `office.document.sign_failed` + `office.signing.disabled` {reason: forbidden} |
| pyHanko lỗi, tự kiểm không đạt, két trả `400` | `201`, không ký | `office.document.sign_failed` (mức error) |
| Két không trả lời (mạng, 5xx, hết giờ) | **`503` `signing_unavailable`**, không lưu gì, văn thư bấm lại | `office.document.sign_failed` |
| Lần ký đầu của đơn vị | `201`, chậm hơn chừng nửa giây trên máy dev (két sinh RSA-3072, máy yếu lâu hơn) | `office.signing.key_created`, `office.signing.certificate_issued` |

Lúc khởi động svc-files dò két một lần, nhật ký có `office.signing.ready` hoặc `office.signing.disabled`. Nhật ký
không chứa trích yếu hay PDF. Ký và tự kiểm một PDF chạy trong event loop, đo trong test (két giả) khoảng 30–50 ms.

Giới hạn:
- Không dấu thời gian tin cậy (PAdES B-T cần dịch vụ TSA), không thông tin kiểm dài hạn (LTV), không CRL/OCSP: giờ
  ký là giờ tự khai — CLI và cổng xác thực ghi rõ.
- Chứng thư chỉ xin khi phiên bản khóa chưa có; chưa tự cấp lại khi sắp hết hạn, khi đơn vị đổi tên hay két đổi CA.
  Chứng thư hết hạn thì tự kiểm không đạt, văn bản phát hành không ký (nhật ký báo `sign_failed`); xoay khóa transit
  (`transit/keys/<khóa>/rotate`, token quản trị) thì svc-files đọc lại khóa sau lần tự kiểm hỏng đó (hoặc khi khởi
  động lại) và xin chứng thư cho phiên bản mới.
- Két khởi tạo trước F4.5 chưa có PKI: ký số tự tắt, mọi thứ khác chạy như cũ cho tới khi két được nâng cấp
  ([`docs/van-hanh.md`](../../docs/van-hanh.md#két-bí-mật), mục Két bí mật).
- Cổng xác thực chưa có link tải chứng thư CA; lấy thẳng từ két (`pki/ca/pem`).

Rủi ro đã chấp nhận:
- Glob `transit/keys/moc-ky-so-*` trong policy của svc-files phủ cả `config` và `rotate`: ai chiếm svc-files có thể
  xoay khóa hay bật `exportable` — vẫn không xuất được vì không có quyền `transit/export`, `transit/backup`; chữ ký cũ
  vẫn kiểm được vì chứng thư nằm trong PDF. Không chặn được bằng `deny` (glob đặt sau thắng).
- `pki/sign/moc-van-thu` ký mọi CSR: ai chiếm svc-files xin được chứng thư cho khóa tự sinh. Không thêm quyền thực vì
  vốn đã gọi được `transit/sign` — như mọi HSM, gọi được là ký được nhưng không mang khóa đi được, và két ghi sổ từng
  lần ký. Mức tin này như hiện nay: svc-files vốn đã mở được mọi khóa dữ liệu `moc-files`.

### Liên thông trong hệ thống (F3.12)

`dispatch.py`. Văn bản đi chọn đơn vị nhận trong hệ thống thì lúc phát hành CSDL thêm một dòng `office.dispatches`
(outbox) cho mỗi đơn vị. svc-workflow gọi `POST /internal/dispatch-file` với id dòng đó, rồi gọi hàm
`office_deliver_dispatch` trong phiên của đơn vị nhận để tạo văn bản đến (`received`, `source_id` = văn bản gửi).

- **Bên gọi chỉ đưa id dòng outbox.** svc-files tự đọc dòng đó, văn bản nguồn và bản phát hành (vai trò `issued`)
  bằng khóa quản trị; không chỉ định được tệp nào khác.
- **Từ chối (409)** khi dòng không còn `pending`; văn bản chưa phát hành; văn bản hạn chế hoặc tệp mã hóa (bản mã có
  AAD = đơn vị gửi ‖ id tệp, khóa nằm trong két của đơn vị gửi — không chép được, CSDL cũng chặn chọn đơn vị nhận cho
  văn bản hạn chế); tệp đã sang kho lạnh; SHA-256 của byte đọc từ kho khác `core.files.sha256`, khác
  `content_sha256` của văn bản hoặc khác băm chụp vào dòng outbox lúc phát hành.
- **Như mọi tệp vào kho**: quét ClamAV trước (chặn thì `422`, ghi `file.rejected` vào sổ của đơn vị nhận), ghi ở
  `tenant/<đơn vị nhận>/<yyyy>/<mm>/<file_id>`, dòng `core.files` thuộc đơn vị nhận — trigger sổ kiểm toán ghi dòng đó
  vào sổ của đơn vị nhận. Bản sao là tệp `main` của văn bản đến nên vòng đọc chữ và đồng bộ tìm kiếm tự nhận như tệp
  tải lên thường (tải lên cũng không lập chỉ mục ngay).
- **Đúng một bản sao**: id tệp định trước (`dispatches.file_id`). Gọi lại khi bản sao đã có → `200` cùng thân (kể cả
  khi dòng outbox vừa chuyển `delivered`). Hai lần gọi chen nhau: trong một tiến trình thì xếp hàng; khác tiến trình
  thì lần thêm dòng sau gặp trùng khóa chính, dùng dòng của lần trước, chỉ bỏ đối tượng của mình khi khóa khác
  (cùng tháng thì cùng một khóa — đó là đối tượng của dòng thắng). Không thêm được dòng mà cũng không có dòng nào thì
  bỏ đối tượng vừa ghi, `503`; không đọc được CSDL để biết thì giữ đối tượng (thà thừa còn hơn dòng trỏ vào chỗ trống).

### Sổ đăng ký văn bản (F2.8)

`registers.py`. NĐ 30/2020, Điều 16 (văn bản đi) và Điều 22 (văn bản đến): đăng ký bằng hệ thống thì in ra giấy đủ
các trường theo mẫu sổ ở Phụ lục IV, ký nhận và đóng sổ.

- **Cột theo mẫu sổ.** Sổ đến 9 cột: Ngày đến, Số đến, Tác giả, Số ký hiệu, Ngày tháng, Tên loại và trích yếu,
  Đơn vị hoặc người nhận, Ký nhận, Ghi chú. Sổ đi 10 cột: Số ký hiệu, Ngày tháng, Tên loại và trích yếu, Người ký,
  Nơi nhận, Đơn vị và người nhận bản lưu, Số lượng bản, Ngày chuyển, Ký nhận, Ghi chú. Ô Ký nhận, Số lượng bản để
  trống, ghi tay trên bản in. Đơn vị nhận văn bản đến là nơi chủ trì lãnh đạo giao; chưa giao thì là lãnh đạo đơn
  vị. Ghi chú có độ khẩn, hạn giải quyết, "Hạn chế", "Đã hủy", mã xác thực của văn bản đi.
- **Liền số.** Sổ đọc mọi văn bản đã vào sổ của năm bằng vai trò `service`, kể cả văn bản hạn chế người in không
  được đọc, rồi hỏi Hasura bằng token người in xem họ đọc được dòng nào. Dòng không đọc được chỉ có số, ngày, số
  ký hiệu, ghi chú "Hạn chế"; trích yếu, tác giả, người ký, phòng soạn, nơi nhận, người nhận, độ khẩn bị che,
  `document_id` là `null`. So với số cuối đã cấp (`office.registers.last_number`), số nào không có dòng thì nằm
  trong `missing` và bìa sổ báo ra. Số cuối và các dòng là hai câu đọc riêng, nên thấy thiếu thì đọc lại một lần
  trước khi báo (văn thư khác vừa vào sổ đúng lúc đó).
- **Văn bản đi đã cấp số mà chưa phát hành** (dựng bản phát hành lỗi, còn `approved`): ô Ngày chuyển để trống,
  không in mã xác thực, ghi chú "Đã cấp số, chưa phát hành".
- **Một chỗ dựng ô.** Bản JSON cho giao diện và bản PDF cùng các ô đã định dạng (ngày `dd/mm/yyyy` theo giờ Việt
  Nam), nên màn hình và giấy không lệch nhau. PDF A4 ngang: bìa (cơ quan chủ quản, đơn vị, năm, từ ngày đến ngày,
  từ số đến số), bảng có hàng đánh số cột lặp lại ở mỗi trang, chỗ văn thư ký cuối sổ.
- **Mỗi lần in** ghi `register.printed` (`entity_id` `in/2026`, kèm số dòng và số dòng bị che) vào sổ kiểm toán.
  Mỗi lúc dựng tối đa hai bản in, để in sổ dài không chiếm hết luồng của tải tệp lên, xuống.

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

### Nộp lưu hồ sơ — nóng → lạnh (F3.8)

`archive.py`, theo NĐ 30/2020 (lập hồ sơ, nộp lưu) và [`docs/mo-hinh-du-lieu.md`](../../docs/mo-hinh-du-lieu.md) §2.4.
Chuyên viên, trưởng phòng lập hồ sơ công việc của phòng (`office.case_files`), đưa vào văn bản đã xong mà mình đọc
được và thuộc phòng mình (đến `done` giao cho mình hoặc cho phòng, đi `issued` của phòng; không nhận văn bản hạn chế),
rồi đóng hồ sơ — ngày đóng do CSDL đặt. Không vai trò nào đặt được `archived`: chỉ svc-files làm, sau khi gói đã nằm
trong bucket lạnh.

Mỗi `MOC_ARCHIVE_INTERVAL_S` giây, svc-files nộp lưu các hồ sơ đóng từ `MOC_ARCHIVE_AFTER_DAYS` ngày trở lên:

1. Đọc hồ sơ cùng văn bản, giao việc, dòng thời gian, tệp. Văn bản nào đã hạn chế hoặc không còn ở trạng thái xong/đã
   ban hành thì dừng. Đọc từng tệp trong bucket nóng, băm phải khớp băm lúc tải lên — lệch một tệp là dừng trước khi
   ghi gì sang bucket lạnh (đối tượng ở đó bị khóa nhiều năm).
2. Ghi gói vào `MOC_COLD_BUCKET` dưới `cold/<tenant_id>/case/<id>/`, mọi tên theo băm nội dung: `files/<sha256>`,
   `documents-<sha256>.parquet`, `assignments-<sha256>.parquet`, `events-<sha256>.parquet` (DuckDB, nén zstd, lược đồ
   cột cố định), `manifest-<sha256>.json` liệt kê từng phần kèm SHA-256, số dòng. Mỗi đối tượng khóa COMPLIANCE tới
   hết thời hạn bảo quản tính theo năm lịch **từ ngày đóng hồ sơ** (`retention_years`; vĩnh viễn thì 100 năm; đã
   quá hạn thì giữ tới hết ngày mai). Manifest không ghi giờ chạy, nên lượt chạy lại ra đúng gói cũ: đối tượng đã có
   đúng nội dung (lượt trước hỏng giữa chừng) thì không ghi lại; tên theo băm nên hai lượt cùng lúc không đè nhau.
3. Đọc lại cả gói từ bucket lạnh, so băm. Lệch một đối tượng là dừng, CSDL chưa đổi gì.
4. Hàm SQL `office.archive_case_file` (chỉ khóa quản trị gọi được), một giao dịch có khóa dòng: kiểm hồ sơ còn
   `closed`, đúng các văn bản, dòng thời gian, liên kết tệp đã vào gói (không có dòng mới sinh trong lúc ghi gói) —
   lệch thì không đổi gì, lượt sau làm lại; `archive_key` phải đúng thư mục gói của hồ sơ; rồi hồ sơ `archived` kèm `archive_key`, `archive_sha256` (băm manifest),
   văn bản `archived`, xóa dòng thời gian, liên kết tệp, tệp `storage_tier = 'cold'`, sự kiện `case_file.archived`
   vào sổ kiểm toán. Giao việc ở lại: là căn cứ quyền xem văn bản và cột "đơn vị nhận" của sổ đăng ký.
5. Xóa bản nóng của tệp. Tệp còn gắn với văn bản ngoài hồ sơ thì giữ ở bucket nóng.

Một hồ sơ lỗi không chặn hồ sơ khác: lượt nền ghi `case_file.archive_failed` vào nhật ký rồi làm hồ sơ kế tiếp; hồ
sơ vừa lỗi được bỏ qua 24 giờ (tính trong tiến trình) để không chiếm chỗ của hồ sơ khác trong giới hạn mỗi lượt. Tệp đã
sang lạnh không gắn lại được vào văn bản nào (trigger `document_files_hot_only`).

Sau khi nộp lưu, dòng văn bản rút gọn ở lại: ai đọc được trước đó vẫn đọc được, tìm thấy theo số, ký hiệu, trích yếu;
cổng xác thực vẫn trả `valid` theo mã tra cứu và băm (trạng thái `archived`). Lớp chữ của PDF đính kèm không còn trong
chỉ mục tìm kiếm; tệp không tải được qua `/api/files/{id}` nữa, chỉ đọc từ gói; tệp đã nộp lưu không gắn lại được vào
dự thảo. Phòng đọc chỉ trả những văn bản trong gói mà người gọi đọc được, kèm số văn bản bị ẩn (`hidden`).

**Phả hệ và kiểm chất lượng (F3.9, `svc_files.lineage`).** Mỗi lượt là một run OpenLineage 2-0-2 của job
`moc.case_file.archive` (START, rồi COMPLETE hoặc FAIL) với 4 run con: `files` (bucket nóng → `files/<sha256>`),
`tables` (bảng `moc.office.*` → Parquet), `manifest` (Parquet + tệp → manifest), `commit` (manifest → các bảng CSDL).
Bảng Parquet được dựng và kiểm **trước** khi ghi gì sang lạnh: DuckDB đọc lại, số dòng phải bằng số dòng lấy từ CSDL,
cột bắt buộc không null (facet `dataQualityAssertions`, `outputStatistics`, `schema`); trượt thì bước `tables` FAIL,
cảnh báo `lineage.quality_failed` trong nhật ký, dừng nộp lưu. Bước nào lỗi thì run con của bước đó FAIL; thông báo
lỗi trong phả hệ chỉ có tên lớp lỗi (không tên tệp, số ký hiệu). Sự kiện ghi vào `core.lineage_events` (khóa quản trị)
và, nếu đặt `MOC_OPENLINEAGE_URL`, gửi thêm tới máy chủ nhận OpenLineage (Marquez). Ghi phả hệ lỗi chỉ thành cảnh báo,
không chặn nộp lưu. Không có tên hồ sơ, trích yếu trong sự kiện — chỉ key đối tượng, tên bảng, số dòng.

Chưa làm: dọn bản nóng khi giao dịch đã chạy mà svc-files không nhận được trả lời (hồ sơ đã `archived`, tệp đã
`cold`, bản nóng còn thừa — không mất gì).

Chạy tay trong container: `python -m svc_files.archive now --case-file <id>` nộp lưu ngay một hồ sơ đã đóng (màn demo
`make demo-nong-lanh`); `python -m svc_files.archive now --after-days 0` nộp lưu mọi hồ sơ đã đóng, in hồ sơ nào lỗi.

### Văn bản hạn chế (F3.7)

`sealed.py`. Không dùng cho bí mật nhà nước (Luật Bảo vệ bí mật nhà nước 2018 đòi hệ thống, mật mã được cấp phép).

- **Tải lên** `POST /api/files?restricted=true`: quét ClamAV như mọi tệp, rồi chỉ nhận PDF mở được không cần mật
  khẩu (cần đọc được để đóng dấu). Két cấp một khóa dữ liệu AES-256 riêng cho tệp (`transit/datakey/plaintext/
  moc-files`): khóa rõ để mã hóa trong bộ nhớ rồi bỏ, khóa đã bọc (`vault:v1:…`) ghi vào `core.files.wrapped_dek`
  cùng `encrypted = true`. Kho chỉ nhận bản mã `MOC1` + nonce 12 byte + AES-256-GCM với AAD = id đơn vị ‖ id tệp
  (chép bản mã sang dòng tệp khác thì không mở được). `sha256`, `size_bytes` của dòng tệp là của bản rõ.
- **Bản phát hành** của văn bản hạn chế (`/internal/issue`) cũng lưu mã hóa như vậy.
- **Mở tệp** `GET /api/files/{id}`: kiểm quyền như mọi tệp — tệp mã hóa đã gắn vào văn bản thì chỉ theo quyền đọc
  văn bản, kể cả với người tạo dòng tệp (bị gỡ khỏi danh sách xem là hết tải) — két mở khóa đã bọc (`transit/decrypt`), giải mã trong bộ
  nhớ, so SHA-256 của bản rõ với CSDL, đóng dấu tên người xem và giờ xem (giờ Việt Nam) lên mọi trang — chữ chéo
  giữa trang, một dòng đầu, một dòng cuối trang (WeasyPrint dựng lớp dấu, pypdf ghép) — rồi ghi `file.decrypted` vào
  sổ kiểm toán; ghi sổ không được thì không trả tệp. Trả kèm `Cache-Control: no-store`, không `ETag`. Tối đa hai lần
  mở cùng lúc (bản mã, bản rõ đều nằm trong bộ nhớ).
- **PDF do người dùng tải lên không mở trong tiến trình svc-files** (như mục Nội dung tệp PDF, Đọc văn bản đến): kiểm
  lúc tải lên và đóng dấu lúc xem chạy `sealed.py` thành tiến trình con `python -I` — `RLIMIT_AS` 1 GB, hạn 20 giây
  (kiểm) / 30 giây (đóng dấu), `RLIMIT_CPU` = hạn + 5; quá hạn thì giết cả nhóm. PDF vào, bản có dấu ra qua ống
  stdin/stdout, không xuống đĩa; tiến trình con không ghi nhật ký. Kiểm và đóng dấu chung hai lượt cùng lúc; chờ lượt
  quá 10 giây thì `503 busy` kèm `Retry-After: 10`, không treo yêu cầu.
- **Trần số trang** `MOC_RESTRICTED_MAX_PAGES` (mặc định 500): tệp hàng vạn trang tí hon làm mỗi lần xem tốn hàng
  phút. Tải lên quá trần, quá nặng (hết giờ, hết bộ nhớ) → `415 restricted_pdf_only` kèm `reason` (`too_many_pages`,
  `timeout`, `memory`, `password`, `corrupt`…); lúc xem (tệp có từ trước khi có trần, hoặc trần vừa hạ) → `422
  unstampable` kèm `reason`, ghi `core.file.stamp_failed`, không trả tệp. Đo 22/10: đóng dấu 500 trang ~3 giây.
- **Bản rõ không ghi xuống đĩa**: Starlette đệm tệp tải lên lớn ở `/tmp`, clamd ghi luồng nhận qua INSTREAM ra thư
  mục tạm trước khi quét — `/tmp` của svc-files và của ClamAV đều là tmpfs (compose).
- svc-files chỉ xin khóa mới và nhờ két mở khóa đã bọc, không lấy được khóa gốc `moc-files` (policy trong
  `openbao/start.sh`). Mất két (volume `openbao_data`) là mất mọi tệp văn bản hạn chế — két nằm trong `make backup`.
- Tệp mã hóa không được đọc chữ, không vào chỉ mục (mục Nội dung tệp PDF); văn bản hạn chế không vào hồ sơ nộp lưu.
- Văn bản đi hạn chế: bản tải về nào cũng mang dấu người xem nên băm khác bản phát hành — người nhận kiểm ở cổng xác
  thực bằng mã in cạnh mã QR, không kiểm theo băm được. Cổng xác thực không bao giờ hiện trích yếu của văn bản hạn chế
  (ràng buộc `documents_restricted_private`: văn bản hạn chế không được `is_public`).
- Chưa làm: xoay khóa `moc-files` rồi bọc lại khóa cũ (`transit/rewrap`); bản xem trước dự thảo văn bản đi hạn chế
  (`/api/documents/{id}/preview`) chưa đóng dấu người xem.

### Gọi Hasura

| Việc | Gọi bằng |
|---|---|
| Kiểm người dùng có được xem tệp | Token của người dùng — Hasura áp quyền của vai trò |
| Lọc kết quả tìm kiếm theo quyền | Token của người dùng |
| Thêm dòng `core.files`, ghi `file.rejected`, đọc `object_key` | Khóa quản trị + `X-Hasura-Role: service` + thuê ước, người dùng, request id lấy từ token đã kiểm |
| Bản phát hành có chữ ký số: `core.files` + `core.file_signatures` trong một mutation (F4.5) | Như trên, thuê ước trong yêu cầu của svc-workflow; dòng chữ ký không có vai trò nào đọc, cổng xác thực đọc qua `office.issued_documents` |
| Đọc văn bản mới sửa để đồng bộ chỉ mục | Khóa quản trị, không kèm vai trò — việc nội bộ, chỉ đọc, không nhận tham số từ người dùng |
| Tìm PDF chờ đọc chữ, ghi `core.file_texts` | Khóa quản trị, không kèm vai trò — việc nội bộ, không nhận tham số từ người dùng |
| Đọc văn bản để dựng bản xem trước | Token của người dùng |
| Đọc văn bản để dựng bản phát hành | Khóa quản trị + `X-Hasura-Role: service` + thuê ước trong yêu cầu của svc-workflow |
| Đọc sổ đăng ký một năm | Khóa quản trị + `X-Hasura-Role: service` + thuê ước, người dùng lấy từ token đã kiểm; rồi token của người dùng để biết dòng nào được đọc |
| Tra cứu ở cổng xác thực | Khóa quản trị + `X-Hasura-Role: verifier` |
| Đọc đầu chuỗi sổ kiểm toán, ghi mốc neo | Khóa quản trị, không kèm vai trò — việc nội bộ, không nhận tham số từ người dùng |
| Đọc hồ sơ, văn bản, tệp để nộp lưu; gọi hàm `office_archive_case_file` | Khóa quản trị, không kèm vai trò, `X-Hasura-User-Id: svc-files:archive` — việc nội bộ; id hồ sơ lấy từ CSDL hoặc lệnh chạy tay. Hàm không cấp quyền cho vai trò nào |
| Phòng đọc: tìm hồ sơ, lọc văn bản người gọi đọc được | Token của người dùng; ghi `case_file.read` như ghi `register.printed` |
| Liên thông: đọc dòng outbox, văn bản nguồn, bản phát hành; bản sao đã có chưa | Khóa quản trị, không kèm vai trò — id dòng do svc-workflow gửi, mọi thứ khác đọc từ CSDL |
| Liên thông: thêm dòng `core.files` của bản sao | Khóa quản trị + `X-Hasura-Role: service` + thuê ước **nhận** (đọc từ dòng outbox), người thực hiện `svc-workflow` |
| Đọc văn bản đến: tệp có xem được, có do người gọi tải lên | Token của người dùng (`created_by` trong `core_files_by_pk`) |
| Đọc văn bản đến: vị trí tệp trong kho, tệp có gắn vào văn bản hạn chế nào không (`document_files.document.restricted`) | Như tải xuống: khóa quản trị + `X-Hasura-Role: service` + thuê ước trong token |
| Đọc văn bản đến: gợi ý đã lưu, lưu gợi ý + ghi `intake.suggested` (một mutation) | Khóa quản trị + `X-Hasura-Role: agent` + thuê ước trong token + `X-Hasura-User-Id: <MOC_AGENT_ID>` — preset của vai trò ép danh tính, thuê ước |
| Đọc văn bản đến: danh mục loại văn bản (giữ 10 phút) | Khóa quản trị, không kèm vai trò — danh mục chung, chỉ đọc |
| Hỏi đáp: đọc văn bản vừa đổi kèm chữ theo trang, thuộc tính quyền để đồng bộ chỉ mục đoạn (`ChunkSources`) | Khóa quản trị, không kèm vai trò — việc nội bộ, chỉ đọc, mọi thuê ước; văn bản hạn chế chỉ đọc để xóa đoạn |
| Hỏi đáp: hậu kiểm đoạn tìm được (`AskDocuments`) | Token của người hỏi — Hasura áp quyền đọc văn bản |
| Hỏi đáp: ghi `assistant.answered` (`GhiSoTroLy`) | Khóa quản trị + `X-Hasura-Role: agent` + thuê ước trong token + `X-Hasura-User-Id: <MOC_ASSISTANT_ID>` — preset của vai trò ép danh tính, thuê ước |
| Gợi ý giao việc (F4.3): đọc văn bản đích (`SimilarTarget`) | Khóa quản trị + `X-Hasura-Role: service` + thuê ước trong yêu cầu của svc-workflow + `X-Hasura-User-Id: svc-files` — văn bản thuê ước khác trả null |
| Gợi ý giao việc (F4.3): hậu kiểm văn bản tương tự (`AskDocumentsService`) | Khóa quản trị + `X-Hasura-Role: service` + thuê ước; không bao giờ văn bản hạn chế |

## Cấu hình

Bí mật (khóa S3, khóa quản trị Hasura, khóa Meilisearch) không truyền qua biến môi trường. Khi có `MOC_OPENBAO_ADDR`,
lúc khởi động dịch vụ đăng nhập két OpenBao bằng AppRole của riêng mình và đọc chúng (F3.2, `openbao/start.sh`); bí
mật trong két đè lên biến cùng tên. Không đặt `MOC_OPENBAO_ADDR` thì đọc thẳng biến môi trường (test, chạy tay).
Két chưa sẵn sàng thì thử lại tới 60 giây; két từ chối (`400`/`403`/`404`) thì dừng ngay.

| Biến | Mặc định | Ghi chú |
|---|---|---|
| `MOC_OPENBAO_ADDR` | trống | Địa chỉ két, vd `http://openbao:8200`; trống thì không dùng két |
| `MOC_OPENBAO_SECRET_PATH` | `moc/data/svc-files` | Đường kv-v2 chứa bí mật của dịch vụ |
| `MOC_OPENBAO_ROLE_ID_FILE`, `MOC_OPENBAO_SECRET_ID_FILE` | `/run/openbao/role_id`, `/run/openbao/secret_id` | Két ghi vào volume chỉ dịch vụ này gắn; mỗi lần két khởi động cấp secret_id mới, hủy cái cũ |
| `MOC_OIDC_ISSUER` | **bắt buộc** | URL công khai của realm, trùng claim `iss`, vd `https://moc.example/realms/moc` |
| `MOC_OIDC_JWKS_URL` | **bắt buộc** | URL nội bộ, vd `http://keycloak:8080/realms/moc/protocol/openid-connect/certs` |
| `MOC_OIDC_AUDIENCE` | trống | Đặt thì kiểm claim `aud` |
| `SEAWEEDFS_S3_ACCESS_KEY`, `SEAWEEDFS_S3_SECRET_KEY` | **bắt buộc** | Lấy từ két |
| `SEAWEEDFS_S3_ENDPOINT` | `http://seaweedfs:8333` | |
| `SEAWEEDFS_S3_REGION` | `us-east-1` | |
| `MOC_FILES_BUCKET` | `moc-files` | Tự tạo nếu chưa có |
| `MOC_FILES_MAX_MB` | `25` | Phải nhỏ hơn `StreamMaxLength` của clamd |
| `MOC_FILES_TRANSIT_KEY` | `moc-files` | Khóa transit trong két bọc khóa của tệp văn bản hạn chế (F3.7); không đặt `MOC_OPENBAO_ADDR` thì không nhận, không mở tệp mã hóa (`503`) |
| `MOC_RESTRICTED_MAX_PAGES` | `500` | Trần số trang PDF của văn bản hạn chế (≥ 1): quá thì không nhận (`415`), không đóng dấu (`422`) |
| `MOC_SIGN_ENABLED` | `true` | Ký số PAdES bản phát hành (F4.5, chỉ minh họa); `false`: phát hành không ký, không gọi transit hay PKI. Chỉ có tác dụng khi có `MOC_OPENBAO_ADDR` |
| `CLAMAV_HOST`, `CLAMAV_PORT` | `clamav`, `3310` | |
| `CLAMAV_TIMEOUT_S` | `60` | |
| `HASURA_URL` | `http://hasura:8080` | Gọi trong mạng nội bộ, không qua APISIX |
| `HASURA_ADMIN_SECRET` | **bắt buộc** | Trùng giá trị Hasura dùng; lấy từ két |
| `HASURA_TIMEOUT_S` | `10` | |
| `MEILISEARCH_URL` | `http://meilisearch:7700` | |
| `MEILISEARCH_API_KEY` | **bắt buộc** | Hiện dùng master key của Meilisearch (chỉ trong mạng nội bộ); lấy từ két |
| `MOC_SEARCH_INDEX` | `documents` | Tự tạo và áp cấu hình khi khởi động |
| `MOC_SEARCH_SYNC_INTERVAL_S` | `5` | `0` tắt vòng đồng bộ nền |
| `MOC_TEXT_INTERVAL_S` | `10` | Chu kỳ đọc chữ của PDF mới gắn vào văn bản; `0` tắt vòng đọc |
| `MOC_PUBLIC_URL` | phần trước `/realms/` của `MOC_OIDC_ISSUER` | In vào mã QR của bản phát hành |
| `MOC_SERVICE_CLIENTS` | `svc-workflow` | Client Keycloak được gọi `/internal/*`, cách nhau dấu phẩy |
| `MOC_COLD_BUCKET` | `moc-cold` | Bucket lạnh có khóa ghi, tự tạo; phải khác `MOC_FILES_BUCKET` |
| `MOC_AUDIT_ANCHOR_INTERVAL_S` | `600` | Chu kỳ neo đầu chuỗi sổ kiểm toán; `0` tắt vòng neo |
| `MOC_AUDIT_ANCHOR_RETENTION_DAYS` | `3650` | Hạn giữ mỗi mốc; trong hạn không ai xóa được |
| `MOC_ARCHIVE_INTERVAL_S` | `3600` | Chu kỳ tìm hồ sơ đến hạn nộp lưu; `0` tắt vòng nộp lưu |
| `MOC_ARCHIVE_AFTER_DAYS` | `365` | Hồ sơ đóng từ chừng ấy ngày trở lên thì nộp lưu |
| `MOC_OPENLINEAGE_URL` | (rỗng) | Gửi thêm sự kiện phả hệ tới máy chủ OpenLineage, vd `http://marquez:5000/api/v1/lineage`; rỗng thì chỉ ghi `core.lineage_events` |
| `MOC_READ_ENABLED` | `true` | Đọc văn bản đến (F4.1); `false`: `503 reader_disabled` |
| `MOC_READ_MAX_MB` | = `MOC_FILES_MAX_MB` | Tệp lớn hơn thì không đọc (`413`) |
| `MOC_READ_TEXT_PAGES` | `3` | Số trang đầu đọc lớp chữ |
| `MOC_OCR_MAX_PAGES` | `1` | Số trang đầu OCR (số, ngày, cơ quan, trích yếu đều ở trang 1) |
| `MOC_OCR_LANG` | `vie` | Dữ liệu ngôn ngữ của tesseract, vd `vie+eng` |
| `MOC_OCR_TIMEOUT_S` | `40` | Hạn tiến trình con OCR, quá thì giết cả nhóm; `RLIMIT_CPU` = hạn + 5 |
| `MOC_OCR_MEMORY_MB` | `1536` | `RLIMIT_AS` của tiến trình con OCR (tesseract kế thừa) |
| `MOC_OCR_MAX_PIXELS` | `40000000` | Trần điểm ảnh, chặn ảnh bom giải nén (`422 too_many_pixels`) |
| `MOC_READ_CONCURRENCY` | `1` | Số lượt đọc cùng lúc |
| `MOC_READ_QUEUE_S` | `15` | Chờ lượt quá thì `503 busy` |
| `MOC_READ_DEADLINE_S` | `50` | Hạn tổng một yêu cầu đọc (dưới 60 giây của APISIX) |
| `MOC_AI_URL` | `http://ollama:11434` | Ollama của profile `ai` (đọc văn bản đến và hỏi đáp dùng chung); rỗng: tắt mô hình |
| `MOC_AI_MODEL` | `qwen3:1.7b` | Tên mô hình trong Ollama (thử `qwen3:4b` nếu máy đủ nhanh) |
| `MOC_AI_TIMEOUT_S` | `20` | Hạn mô hình; quá thì trích yếu theo quy tắc (`model_timeout`) |
| `MOC_AI_MAX_CHARS` | `3000` | Số ký tự thân văn bản gửi mô hình |
| `MOC_AI_SUMMARY` | `fallback` | `fallback`: chỉ hỏi mô hình khi quy tắc không ra trích yếu tin cậy cao · `always`: luôn hỏi |
| `MOC_AGENT_ID` | `moc-doc-reader` | Danh tính tác tử trong sổ kiểm toán |
| `MOC_TESSERACT_BIN` | `tesseract` | Chương trình tesseract (test thay bằng bản giả) |
| `MOC_ASK_ENABLED` | `true` | Hỏi đáp (F4.2); `false`: `503 assistant_disabled`, không chạy vòng chỉ mục đoạn, không dò mô hình |
| `MOC_ASK_INDEX` | `chunks` | Chỉ mục đoạn trong Meilisearch, `[A-Za-z0-9_-]{1,64}`, khác `MOC_SEARCH_INDEX`; tự tạo và áp cấu hình khi khởi động |
| `MOC_ASK_SYNC_INTERVAL_S` | `5` | Chu kỳ đồng bộ + nhúng chỉ mục đoạn; `0` chỉ hợp lệ khi `MOC_ASK_ENABLED=false` (bật trợ lý mà không có vòng nền thì chỉ mục đoạn không bao giờ có: svc-files từ chối khởi động) |
| `MOC_ASK_TOP_K` · `MOC_ASK_CANDIDATES` · `MOC_ASK_PER_DOC` | `5` · `24` · `2` | Số nguồn trả về · số đoạn lấy từ Meilisearch mỗi lượt · số đoạn tối đa mỗi văn bản |
| `MOC_ASK_MIN_SCORE` · `MOC_ASK_MIN_SCORE_SEMANTIC` | `0` · `0.75` | Ngưỡng `_rankingScore` khi tìm từ khóa · tìm lai (0–1). Từ khóa để 0: chiến lược `frequency` đã buộc đoạn chứa từ hiếm nhất của câu hỏi, điểm `words` thấp cả với nguồn đúng. Tìm lai 0,75: trên kho mẫu nguồn đúng đứng đầu ≥ 0,88, câu không có đáp án ≤ 0,70 |
| `MOC_ASK_SEMANTIC_RATIO` | `0.5` | Tỷ trọng tìm theo nghĩa trong tìm lai (0–1) |
| `MOC_ASK_DEADLINE_S` | `50` | Hạn tổng một lượt hỏi, tối đa 55 (dưới 60 giây của APISIX) |
| `MOC_ASK_MODEL` | rỗng = `MOC_AI_MODEL` | Mô hình viết câu trả lời, vd `qwen3:4b`. Khác `MOC_AI_MODEL` (kèm mô hình nhúng) là ba mô hình tranh hai chỗ của Ollama (`OLLAMA_MAX_LOADED_MODELS=2` trong compose): nạp đi nạp lại, dễ quá giờ — svc-files ghi `config.warning` lúc khởi động; muốn mô hình khác thì để trống biến này và đổi `MOC_AI_MODEL` |
| `MOC_ASK_MODEL_TIMEOUT_S` | `40` | Hạn gọi mô hình viết câu trả lời (`model_timeout`) |
| `MOC_ASK_CONTEXT_CHARS` | `2800` | Tổng ký tự các đoạn gửi mô hình |
| `MOC_ASK_CONCURRENCY` · `MOC_ASK_QUEUE_S` | `1` · `20` | Số lượt `generate` cùng lúc · chờ lượt quá thì `503 busy` |
| `MOC_AI_EMBED_MODEL` | `qwen3-embedding:0.6b` | Mô hình nhúng trong Ollama (`bge-m3` thay được); đặt rỗng: không nhúng, chỉ tìm từ khóa |
| `MOC_AI_EMBED_DIMS` · `MOC_AI_EMBED_BATCH` | `1024` · `8` | Số chiều véc-tơ, phải đúng của mô hình (sai thì tắt tìm theo nghĩa, ghi lỗi `embed_dims_mismatch`) · số đoạn mỗi lô nhúng nền |
| `MOC_ASSISTANT_ID` | `moc-assistant` | Danh tính trợ lý trong sổ kiểm toán (`X-Hasura-User-Id` của vai trò agent) |

## Phát triển

Cần Python ≥ 3.12 và [uv](https://github.com/astral-sh/uv) (MIT/Apache-2.0) hoặc `pip`.

```bash
cd services/svc-files
uv venv && uv pip install -r requirements-dev.txt     # hoặc: python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest                            # test đơn vị, không cần Docker
```

### Test tích hợp với ClamAV, SeaweedFS, PostgreSQL + Hasura thật

Đi trọn luồng: tải lên → bản ghi `core.files` → tải xuống; lãnh đạo chỉ xem được sau khi tệp gắn vào văn bản;
thuê ước khác nhận 404; EICAR bị chặn và nằm trong chuỗi băm của sổ kiểm toán; zip, PDF có mật khẩu và zip lồng
quá sâu bị chặn (`unscannable`), PDF chỉ khóa quyền sửa vẫn nhận; thuê ước lạ không để lại tệp mồ côi; tìm kiếm trả đúng văn bản từng vai trò được đọc; đọc chữ PDF đã gắn vào văn bản (bỏ tệp của văn bản
hạn chế, tệp chưa gắn) rồi tìm được theo nội dung. Hasura dựng bằng `db/tests/stack.sh` (schema và quyền lấy từ `db/` của cây mã nguồn) với khóa
công khai RS256, vì svc-files chỉ nhận token RS256 như của Keycloak.

```bash
K=$(mktemp -d)
openssl genrsa -out $K/it.pem 2048 && openssl rsa -in $K/it.pem -pubout -out $K/it.pub
docker run -d --name moc-it-clamav -p 127.0.0.1:13310:3310 \
  -e CLAMD_CONF_AlertEncrypted=yes -e CLAMD_CONF_AlertExceedsMax=yes clamav/clamav:1.5.4   # như docker-compose.yml
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

`uv` giữ các bản đã ghim trong tệp khóa. Gói mới và gói nó kéo theo phải là bản phát hành ít nhất hai tuần
(`DEPENDENCIES.md`): thêm `--exclude-newer-package <gói>=<ngày>` cho từng gói mới vào cả hai lệnh. pyHanko (F4.5) sinh
với `--exclude-newer-package <gói>=2026-10-06T00:00:00Z` cho pyhanko, pyhanko-certvalidator, asn1crypto, tzlocal,
tzdata, lxml, aiohttp, aiohappyeyeballs, aiosignal, attrs, frozenlist, multidict, propcache, yarl, oscrypto, uritools,
certifi. Vá bảo mật chưa đủ hai tuần (`DEPENDENCIES.md`, mục Cách đọc): gói khai trực tiếp thì nâng cận dưới trong
`pyproject.toml` (pillow, pypdf), gói kéo theo thì thêm `-P <gói>==<bản>` vào cả hai lệnh (certifi 2026.10.19).

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
