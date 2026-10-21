# svc-files

Cửa duy nhất để tệp vào và ra khỏi kho đối tượng của Mộc. Tệp tải lên được **quét ClamAV trước**,
sạch mới ghi vào SeaweedFS và thêm dòng `core.files`; ClamAV không trả lời thì từ chối, không bao giờ lưu tệp
chưa quét. Tải xuống: svc-files hỏi Hasura **bằng chính token của người dùng** xem họ có được xem tệp không —
quy tắc quyền chỉ nằm ở `db/metadata`, svc-files không viết lại. Tìm kiếm cũng vậy: Meilisearch xếp hạng,
Hasura quyết ai được đọc văn bản nào; tìm được cả theo chữ trong tệp PDF đính kèm. Văn bản đi được dựng thành PDF đúng thể thức NĐ 30 ở đây, và cổng xác thực
trả lời người ngoài một văn bản có thật, còn nguyên vẹn không. Sổ đăng ký văn bản đến / đi cũng in ra PDF ở đây.
Văn bản đi gửi đơn vị khác trong hệ thống thì bản phát hành được chép sang kho của đơn vị nhận ở đây (liên thông).
Văn thư tải văn bản đến lên thì tác tử `moc-doc-reader` đọc tệp (lớp chữ PDF hoặc OCR) và gợi ý thông tin tiếp nhận.

Thuộc lõi Tầng 1 — F1.5 (dữ liệu phi cấu trúc), F1.6 (trạm kiểm dịch), F1.7 và F2.7 (tìm kiếm, cả nội dung PDF),
F2.4 (dựng PDF văn bản đi), F2.8 (sổ đăng ký in được), F2.13 (cổng xác thực), F3.12 (liên thông) và F4.1 (đọc văn
bản đến) trong [`docs/ke-hoach-phat-trien.md`](../../docs/ke-hoach-phat-trien.md). Chủ: mảng AI ·
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
| Văn bản hạn chế: lưu mã hóa (khóa riêng từng tệp từ két), tải về giải mã trong bộ nhớ, đóng dấu người xem, ghi sổ | **Xong** (F3.7) |
| `/internal/issue`: dựng PDF có số, mã QR (WeasyPrint) → quét → lưu bản phát hành | **Xong** (F2.4) |
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
| | `?restricted=true` — tệp cho văn bản hạn chế, lưu mã hóa (mục Văn bản hạn chế): `415` `restricted_pdf_only` khi không phải PDF đọc được, không mật khẩu · `503` `vault_unavailable` khi két chưa sẵn sàng — **không lưu** |
| | `401` thiếu hoặc sai token · `403` token không có `tenant_id` |
| | `413` vượt `MOC_FILES_MAX_MB` · `400` tệp rỗng hoặc thiếu trường `file` |
| | `422` `{code: "infected", signature}` — tệp nhiễm, **không lưu**, ghi vào sổ kiểm toán |
| | `403` `unknown_tenant` — thuê ước trong token chưa có trong `core.tenants` |
| | `503` ClamAV, SeaweedFS hoặc Hasura không sẵn sàng — **không lưu** (đã ghi vào kho thì gỡ ra) |
| `POST /api/files/{id}/read` | Chỉ `clerk`, chỉ tệp chính mình tải lên. `?force=true` đọc lại. `200` `{file_id, status, method, pages, fields, warnings, summary_source, model, duration_ms, cached, read_at}` · `401` · `403` `forbidden` · `404` `not_found` (cả tệp người khác) · `409` `restricted` tệp mã hóa hoặc tệp đang gắn vào văn bản hạn chế (trước gợi ý đã lưu, trước khi đọc byte) · `413` `too_large` · `415` `unsupported` · `422` `unreadable` + `reason` · `503` `busy` (+ `Retry-After: 10`), `reader_disabled`, `ocr_unavailable`, `storage_unavailable`, `database_unavailable` — mục Đọc văn bản đến |
| `GET /api/files/{id}` | `200` nội dung tệp · `404` không có tệp **hoặc** không được xem (trả như nhau) · `401` · `503` · tệp mã hóa: `200` bản giải mã có dấu người xem, `500` `sealed_corrupt` bản mã hỏng hoặc không khớp tệp, `503` két hoặc sổ kiểm toán chưa sẵn sàng |
| `GET /api/search?q=` | `200` `{hits: [...], next_cursor}` · `400` câu tìm trống, `cursor` sai · `422` tham số sai · `401` · `503` |
| `GET /api/documents/{id}/preview` | `200` PDF dự thảo (chữ "DỰ THẢO", chưa số) · `404` không có hoặc không được đọc · `409` đã phát hành |
| `GET /api/registers/{in\|out}/{năm}` | Chỉ `clerk`, `director`. `200` `{direction, year, title, org_name, columns, entries: [{number, document_id, hidden, cells}], last_number, missing}` · `403` vai trò khác · `422` chiều sổ hay năm (2000–2100) sai · `401` · `503` |
| `GET /api/registers/{in\|out}/{năm}/pdf` | Như trên, trả PDF `so-dang-ky-van-ban-{den\|di}-<năm>.pdf`; ghi `register.printed` vào sổ kiểm toán trước khi trả, ghi không được thì `503`, không có PDF |
| `GET /api/verify/{mã}` | **Không cần token.** `200` `{result: "valid" \| "not_found", document}`; nhận cả `abcde-23456`, `ABCDE 23456` |
| `GET /api/verify?sha256=` | **Không cần token.** Như trên, tra theo băm; `422` khi không phải 64 ký tự hex |
| `GET /api/case-files/{id}/archive` | Người xem được hồ sơ (phòng mình với `staff`, `manager`; cả đơn vị với `clerk`, `director`). `200` `{case_file_id, code, title, closed_on, archived_at, archive_key, manifest_sha256, retain_until, documents, files, hidden}` — văn bản người gọi đọc được, đọc từ bảng Parquet trong gói; `hidden` là số văn bản còn lại · `404` không có hoặc không được xem · `409` `not_archived` · `502` `archive_mismatch` gói không khớp băm trong CSDL · `401` · `503`. Ghi `case_file.read` vào sổ kiểm toán trước khi trả |
| `POST /internal/issue` | Chỉ token tài khoản dịch vụ trong `MOC_SERVICE_CLIENTS` (`403` với token người dùng). `201` `{file_id, sha256, size_bytes}` · `409` văn bản chưa cấp số · `503` ClamAV, kho, CSDL không sẵn sàng. Không có trong OpenAPI công khai, APISIX không có route tới |
| `POST /internal/dispatch-file` | Như `/internal/issue` (chỉ dịch vụ nội bộ). Thân `{dispatch_id, actor_id}`. `201` `{file_id, sha256, size_bytes}` bản sao mới · `200` cùng thân khi bản sao đã có · `404` không có dòng `office.dispatches` · `409` `{code}`: `not_pending` dòng không còn chờ, `not_issued` văn bản chưa phát hành, `restricted` văn bản hạn chế / tệp mã hóa, `cold` tệp đã sang kho lạnh, `integrity` byte trong kho không khớp băm · `422` trạm quét chặn · `503` ClamAV, kho, CSDL không sẵn sàng (mục Liên thông) |
| `GET /healthz` | Tiến trình còn sống |
| `GET /readyz` | `200` khi gọi được ClamAV, SeaweedFS và Hasura, ngược lại `503`; Meilisearch hỏng thì vẫn `200` nhưng `status: "degraded"`; `ai`: mô hình trích yếu (F4.1) đang sẵn sàng không — không ảnh hưởng `status` |

Ai xem được tệp: người tải lên, và người đọc được văn bản có gắn tệp đó (`db/README.md`, mục Vai trò).
Tệp tải về luôn ở dạng `attachment`, kèm `X-Content-Type-Options: nosniff` và
`Content-Security-Policy: sandbox` — tệp HTML hay SVG người dùng tải lên không chạy được như một trang của
Mộc. Giao diện xem PDF bằng PDF.js nên không cần hiển thị inline. `ETag` là SHA-256 của tệp (tệp mã hóa thì không
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
  theo) mà chưa đọc; còn tồn (vd tệp tải lên trước khi có F2.7) thì đọc tiếp ngay. Kết quả ghi vào
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

**Số đo** (`make do-doc-van-ban` trên stack thật, 21/10/2026, 10 PDF có chữ + 4 bản scan trong `seed/van-ban-den/`;
máy đo: AMD Ryzen 7 7735HS, 16 luồng, một lượt đọc một lúc, tesseract 5.5.0 + `vie` 4.1.0). Mẫu hư cấu in sạch hơn công
văn thật — đây là **mức trần**; số thật đo bằng view `office.v_intake_accuracy` khi có đơn vị chạy thử.

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

| Thời gian một lần đọc | Trung bình | Lớn nhất |
|---|---|---|
| PDF có chữ, không mô hình | 0,6 giây | 0,7 giây |
| Ảnh / PDF scan (OCR 1 trang) | 1,2 giây | 1,5 giây |
| PDF có chữ + trích yếu bằng `qwen3:1.7b` (CPU, mô hình đã nạp) | 4,1 giây | 4,1 giây |
| Ảnh scan + trích yếu bằng `qwen3:1.7b` | 6,6 giây | 6,6 giây |

Mô hình chỉ chạy khi quy tắc chưa ra trích yếu chắc chắn: trên 14 mẫu là 2 lần (giấy mời không có dòng V/v, ảnh xám),
các tệp khác giữ thời gian như khi không bật mô hình. Từ bản này chữ OCR không trường nào `high` nên mọi ảnh, bản scan
đều qua mô hình khi bật `ai` (thêm khoảng 3,5–6 giây).

Chưa làm: OCR bản scan cho tìm kiếm toàn văn (F2.7 chỉ đọc lớp chữ); so sánh PaddleOCR / VietOCR; dữ liệu
`tessdata_best` (gói Debian là bản nhanh — đặt `TESSDATA_PREFIX` trỏ volume nếu cần chính xác hơn).

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
| `MOC_AI_URL` | `http://ollama:11434` | Ollama của profile `ai`; rỗng: tắt mô hình |
| `MOC_AI_MODEL` | `qwen3:1.7b` | Tên mô hình trong Ollama (thử `qwen3:4b` nếu máy đủ nhanh) |
| `MOC_AI_TIMEOUT_S` | `20` | Hạn mô hình; quá thì trích yếu theo quy tắc (`model_timeout`) |
| `MOC_AI_MAX_CHARS` | `3000` | Số ký tự thân văn bản gửi mô hình |
| `MOC_AI_SUMMARY` | `fallback` | `fallback`: chỉ hỏi mô hình khi quy tắc không ra trích yếu tin cậy cao · `always`: luôn hỏi |
| `MOC_AGENT_ID` | `moc-doc-reader` | Danh tính tác tử trong sổ kiểm toán |
| `MOC_TESSERACT_BIN` | `tesseract` | Chương trình tesseract (test thay bằng bản giả) |

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
