# API REST của `svc-files`

> Tệp sinh tự động bằng `make api-docs` từ [`openapi/svc-files.json`](openapi/svc-files.json), không sửa
> tay. Lấy token và gọi API: [README](README.md).

Tải tệp lên qua trạm kiểm dịch ClamAV, tải xuống theo quyền, tìm văn bản. Gọi qua cổng APISIX với token Bearer do
Keycloak cấp (docs/api/README.md).

OpenAPI 3.1.0, 21 thao tác:

| Thao tác | Tóm tắt |
|---|---|
| `POST /api/files/{file_id}/read` | Đọc văn bản đến vừa tải lên (lớp chữ PDF hoặc OCR), gợi ý thông tin tiếp nhận |
| `POST /api/documents/ask` | Hỏi đáp trên kho văn bản: câu trích nguyên văn có nguồn, tùy chọn câu trả lời do mô hình viết |
| `POST /api/files` | Tải tệp lên: quét ClamAV, sạch mới lưu |
| `POST /api/imports/{kind}` | Nạp lô: gửi tệp NDJSON/CSV nhiều văn bản đến (kèm zip tệp đính kèm), xử lý nền |
| `GET /api/imports/{job_id}` | Trạng thái một lô nạp: đã nhận, đang chờ, đạt, trùng, lỗi |
| `GET /api/imports/{job_id}/rows` | Kết quả từng dòng của lô nạp (số dòng, mã, lý do) — không trả lại dữ liệu đã gửi |
| `GET /api/imports` | Các lô nạp của chính người gọi, mới trước |
| `GET /api/files/{file_id}` | Tải tệp xuống, nếu người gọi được xem tệp |
| `GET /api/search` | Tìm văn bản theo số ký hiệu, trích yếu, cơ quan ban hành, nội dung |
| `GET /api/documents/{document_id}/preview` | Xem trước văn bản đi dưới dạng PDF đúng thể thức, chưa có số và mã xác thực |
| `GET /api/registers/{direction}/{year}` | Sổ đăng ký văn bản đến / đi của một năm, đúng các cột sẽ in |
| `GET /api/registers/{direction}/{year}/pdf` | In sổ đăng ký văn bản đến / đi của một năm ra PDF để ký nhận, đóng sổ (NĐ 30/2020, Điều 16, 22) |
| `GET /api/verify/ca.pem` | Chứng thư CA nội bộ ký văn bản đi (PEM, chỉ minh họa; không cần đăng nhập) |
| `GET /api/verify/anchor-key.pem` | Khóa công khai Ed25519 ký mốc neo sổ kiểm toán (PEM SubjectPublicKeyInfo; không cần đăng nhập) |
| `GET /api/verify/{code}` | Tra văn bản đã phát hành theo mã tra cứu in cạnh mã QR (không cần đăng nhập) |
| `GET /api/verify` | Tra văn bản đã phát hành theo SHA-256 của tệp PDF (trình duyệt tự tính, không tải tệp lên) |
| `GET /api/status` | Trạng thái vận hành các thành phần của Signet (không cần đăng nhập, lưu đệm 10 giây) |
| `GET /api/case-files/{case_file_id}/archive` | Phòng đọc: đọc lại gói lưu trữ của hồ sơ đã nộp lưu từ bucket lạnh, kiểm băm |
| `POST /api/case-files/{case_file_id}/archive` | Nộp lưu ngay hồ sơ đã đóng (lãnh đạo phòng): gói Parquet + tệp + manifest vào bucket lạnh |
| `GET /api/case-files/{case_file_id}/archive/files/{file_id}` | Phòng đọc: xem một tệp trong gói lưu trữ (chỉ xem, PDF có dấu tên người xem) |
| `GET /api/case-files/archive-stats` | Trang Điều hành: số liệu văn bản đã nộp lưu — DuckDB đọc các gói Parquet trong bucket lạnh |

## `POST /api/files/{file_id}/read`

Đọc văn bản đến vừa tải lên (lớp chữ PDF hoặc OCR), gợi ý thông tin tiếp nhận

Chỉ văn thư, chỉ tệp chính mình tải lên. Tác tử `moc-doc-reader` đọc tệp, quy tắc tìm số ký hiệu, ngày ban hành, cơ quan
ban hành, loại, độ khẩn, trích yếu; có mô hình ngôn ngữ thì mô hình chỉ viết trích yếu. Mỗi lần đọc thật ghi một dòng
`intake.suggested` vào sổ kiểm toán (chỉ siêu dữ liệu, không có nội dung văn bản) cùng giao dịch lưu gợi ý. Đã có gợi ý
thì trả luôn (`cached`), trừ khi `force=true`. Không tạo văn bản: văn thư đối chiếu, sửa rồi mới lưu.

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `file_id` | đường dẫn | ✓ | `string (uuid)` |  |
| `force` | query |  | `boolean` | true: đọc lại dù đã có gợi ý lưu (nút Đọc lại). Mặc định `false`. |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Thành công | `application/json` `ReadOut` |
| 401 | Thiếu hoặc sai token (`missing_token`, `invalid_token`) |  |
| 403 | `forbidden` — không phải văn thư |  |
| 404 | `not_found` — không có tệp, không xem được, không do người gọi tải lên, hoặc không còn trong kho |  |
| 409 | `restricted` — tệp của văn bản hạn chế: không đọc (kiểm trước khi đọc byte) |  |
| 413 | `too_large` — tệp lớn hơn `MOC_READ_MAX_MB` |  |
| 415 | `unsupported` — byte đầu không phải PDF, JPEG, PNG, TIFF (không tin mime khai) |  |
| 422 | `unreadable` kèm `reason`: password, corrupt, no_text, timeout, memory, too_many_pixels — đã ghi `intake.suggested` (status unreadable) vào sổ kiểm toán |  |
| 503 | `busy` (kèm `Retry-After: 10`) chờ lượt quá `MOC_READ_QUEUE_S` · `reader_disabled` · `ocr_unavailable` · `storage_unavailable` · `database_unavailable` — gồm cả khi chưa ghi được sổ kiểm toán: không ghi được sổ thì không trả gợi ý |  |

## `POST /api/documents/ask`

Hỏi đáp trên kho văn bản: câu trích nguyên văn có nguồn, tùy chọn câu trả lời do mô hình viết

Chỉ tìm trong các văn bản người hỏi được xem (lọc trước theo vai trò trong Meilisearch, hậu kiểm bằng chính token người
hỏi qua Hasura); văn bản hạn chế không bao giờ vào chỉ mục. `extract` trả câu trích nguyên văn kèm số ký hiệu, trang;
`generate` thêm câu trả lời do mô hình chạy tại chỗ viết từ đúng các đoạn đó, mỗi câu có [n] do máy chủ gán theo bằng
chứng. Mỗi lượt ghi một dòng `assistant.answered` của tác tử `moc-assistant` vào sổ kiểm toán — không có câu hỏi, câu
trả lời; không ghi được sổ thì không trả lời. Người hỏi ngắt kết nối thì lượt bị hủy, không ghi sổ.

Thân yêu cầu `application/json`: kiểu `AskIn`.

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Thành công | `application/json` `AskOut` |
| 400 | `invalid_question` — rỗng sau chuẩn hóa, quá 500 ký tự, có ký tự điều khiển, hoặc chỉ toàn từ dừng |  |
| 401 | `missing_token`, `invalid_token` (cả khi Hasura từ chối token lúc hậu kiểm) |  |
| 403 | `forbidden` — vai trò không phải văn thư, lãnh đạo, trưởng phòng, chuyên viên |  |
| 503 | `assistant_disabled` · `busy` (kèm `Retry-After: 10`, chờ lượt sinh quá `MOC_ASK_QUEUE_S`) · `search_unavailable` · `database_unavailable` — gồm cả khi chưa ghi được sổ kiểm toán: không ghi được sổ thì không trả lời |  |
| 422 | Dữ liệu gửi lên sai kiểu, thiếu trường | `application/json` `HTTPValidationError` |

## `POST /api/files`

Tải tệp lên: quét ClamAV, sạch mới lưu

Sau ClamAV: nhận loại theo byte đầu, không tin tên, mime khai; `mime_type` trả về là loại theo nội dung. Ảnh JPEG, PNG
được bỏ siêu dữ liệu (EXIF, GPS, XMP, chú thích; xoay theo hướng EXIF trước) nên `sha256`, `size_bytes` là của ảnh đã
làm sạch; tệp loại khác lưu nguyên từng byte.

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `restricted` | query |  | `boolean` | Tệp của văn bản hạn chế (F3.7): chỉ nhận PDF; lưu mã hóa bằng khóa dữ liệu riêng do két cấp, chỉ gắn được vào văn bản hạn chế, xem có dấu tên người xem. Mặc định `false`. |

Thân yêu cầu `multipart/form-data`:

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `file` | `string (binary)` | ✓ |  |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 201 | Thành công | `application/json` `FileOut` |
| 401 | Thiếu hoặc sai token |  |
| 413 | Tệp vượt giới hạn MOC_FILES_MAX_MB |  |
| 415 | `type_mismatch`: nội dung không khớp đuôi tệp (hay mime khai khi tên không có đuôi), vd tệp .pdf là HTML · `type_not_allowed`: chương trình, kịch bản chạy được (theo nội dung hay đuôi .exe, .bat, .js…) — `found` là loại theo nội dung · `restricted_pdf_only`: restricted=true mà tệp không phải PDF đọc được, không khóa, tối đa MOC_RESTRICTED_MAX_PAGES trang, hoặc quá nặng để kiểm trong giới hạn thời gian, bộ nhớ (`reason`) (PDF phải nhập mật khẩu mới mở thì bị chặn trước ở bước quét: 422 unscannable) |  |
| 422 | Tệp chứa mã độc (infected), hoặc có mật khẩu, nén quá nhiều lớp nên không quét được (unscannable) — đã chặn, không lưu, ghi file.rejected vào sổ kiểm toán · `image_unreadable` + `reason` (corrupt, too_many_pixels, timeout, memory): ảnh JPEG, PNG hỏng hoặc quá lớn nên không bỏ được siêu dữ liệu — không lưu |  |
| 503 | ClamAV, kho đối tượng, CSDL hoặc két khóa (restricted=true) không sẵn sàng; `busy` (kèm `Retry-After: 10`) khi đang kiểm, đóng dấu tệp hạn chế khác hay xử lý ảnh khác — không lưu |  |

## `POST /api/imports/{kind}`

Nạp lô: gửi tệp NDJSON/CSV nhiều văn bản đến (kèm zip tệp đính kèm), xử lý nền

Chỉ văn thư. Mỗi dòng đi đúng đường tiếp nhận lẻ: tệp đính kèm qua trạm quét ClamAV rồi mới vào kho, Action
`receiveIncoming` thay mặt người gửi (cách ly đơn vị, sổ kiểm toán chuỗi băm từng văn bản), tùy chọn `registerIncoming`.
Lỗi một dòng không hỏng dòng khác. Trả 202 và `Location` của lô; theo dõi ở GET /api/imports/{id}, lỗi từng dòng ở
/rows. Gửi lại cùng tệp không nhân đôi: dòng đã nạp báo `duplicate`; kèm `Idempotency-Key` thì nhận lại đúng lô cũ
(200).

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `kind` | đường dẫn | ✓ | `"incoming"` | Loại lô; hiện có incoming (văn bản đến) |
| `format` | query |  | `"ndjson", "csv" hoặc null` | Thiếu thì đoán theo đuôi tên tệp (.ndjson, .jsonl, .csv) rồi theo Content-Type |
| `register` | query |  | `boolean` | Vào sổ từng văn bản sau khi tiếp nhận (cấp số đến, khởi chạy quy trình, báo lãnh đạo). Lô có vào sổ tối đa MOC_IMPORT_REGISTER_MAX_ROWS dòng. Mặc định `false`. |
| `Idempotency-Key` | header |  | `string hoặc null` | Tùy chọn, 1–200 ký tự ASCII in được: gửi lại cùng khóa trả đúng lô cũ |

Thân yêu cầu `multipart/form-data`:

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `data` | `string (binary)` | ✓ | NDJSON (mỗi dòng một object) hoặc CSV có tiêu đề, UTF-8; cùng trường với receiveIncoming(data), thêm `files`: tên tệp trong zip, tệp đầu là bản chính |
| `archive` | `string (binary)` |  | Zip tệp đính kèm (tùy chọn) |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 202 | Thành công | `application/json` `ImportOut` |
| 200 | Gửi lại cùng Idempotency-Key, cùng nội dung: lô đã tạo trước đó | `application/json` `ImportOut` |
| 400 | `missing_file` · `unknown_format` · `bad_encoding` (không phải UTF-8) · `bad_header` (CSV thiếu cột bắt buộc, có cột lạ) · `bad_format` (CSV hỏng cấu trúc) · `empty` · `bad_archive` (zip hỏng, quá 5000 mục, tên trùng) · `bad_idempotency_key` · `empty_file` |  |
| 401 | Thiếu hoặc sai token |  |
| 403 | `forbidden` — không phải văn thư · `unknown_tenant` |  |
| 409 | `idempotency_conflict` — cùng Idempotency-Key mà khác tệp, định dạng hoặc register |  |
| 413 | `too_large` (thân yêu cầu, tệp dữ liệu MOC_IMPORT_DATA_MAX_MB, zip MOC_IMPORT_ZIP_MAX_MB, tổng cỡ tệp các dòng trỏ tới — mỗi lần trỏ tính một lần — MOC_IMPORT_STORE_MAX_MB) · `too_many_rows` (MOC_IMPORT_MAX_ROWS; register=true: MOC_IMPORT_REGISTER_MAX_ROWS) |  |
| 422 | `infected` / `unscannable` — chính tệp dữ liệu bị trạm quét chặn, đã ghi `file.rejected` vào sổ kiểm toán, không tạo lô |  |
| 429 | `too_many_imports` — đơn vị đã có MOC_IMPORT_MAX_OPEN lô chưa xong (kèm `Retry-After`) |  |
| 503 | `imports_disabled` (MOC_IMPORT_INTERVAL_S=0) · `busy` (chỗ giữ zip đầy, kèm `Retry-After`) · `scanner_unavailable` · `database_unavailable` |  |

## `GET /api/imports/{job_id}`

Trạng thái một lô nạp: đã nhận, đang chờ, đạt, trùng, lỗi

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `job_id` | đường dẫn | ✓ | `string (uuid)` |  |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Thành công | `application/json` `ImportOut` |
| 401 | Thiếu hoặc sai token |  |
| 404 | `not_found` — không có lô, hoặc lô của người khác (kể cả cùng đơn vị) — hai trường hợp như nhau |  |
| 503 | `database_unavailable` |  |
| 422 | Dữ liệu gửi lên sai kiểu, thiếu trường | `application/json` `HTTPValidationError` |

## `GET /api/imports/{job_id}/rows`

Kết quả từng dòng của lô nạp (số dòng, mã, lý do) — không trả lại dữ liệu đã gửi

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `job_id` | đường dẫn | ✓ | `string (uuid)` |  |
| `status` | query |  | `"pending", "ok", "duplicate", "failed" hoặc null` |  |
| `after` | query |  | `integer` | Số dòng cuối của trang trước (`next_after`). Mặc định `0`. |
| `limit` | query |  | `integer` | Mặc định `100`. |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Thành công | `application/json` `ImportRowsOut` |
| 401 | Thiếu hoặc sai token |  |
| 404 | `not_found` — không có lô, hoặc lô của người khác (kể cả cùng đơn vị) — hai trường hợp như nhau |  |
| 503 | `database_unavailable` |  |
| 422 | Dữ liệu gửi lên sai kiểu, thiếu trường | `application/json` `HTTPValidationError` |

## `GET /api/imports`

Các lô nạp của chính người gọi, mới trước

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `limit` | query |  | `integer` | Mặc định `20`. |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Thành công | `application/json` `ImportsOut` |
| 401 | Thiếu hoặc sai token |  |
| 503 | `database_unavailable` |  |
| 422 | Dữ liệu gửi lên sai kiểu, thiếu trường | `application/json` `HTTPValidationError` |

## `GET /api/files/{file_id}`

Tải tệp xuống, nếu người gọi được xem tệp

Tệp của văn bản hạn chế (F3.7) được giải mã trong bộ nhớ, đóng dấu tên người xem và giờ xem lên mọi trang; mỗi lần mở
ghi một dòng `file.decrypted` vào sổ kiểm toán — không ghi được sổ thì không trả tệp.

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `file_id` | đường dẫn | ✓ | `string (uuid)` |  |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Nội dung tệp, luôn ở dạng tải về | `application/octet-stream` |
| 401 | Thiếu hoặc sai token |  |
| 404 | Không có tệp, hoặc người gọi không được xem — hai trường hợp trả như nhau |  |
| 422 | Tệp mã hóa giải mã được nhưng không đóng dấu người xem được (`unstampable`, `reason`): PDF quá MOC_RESTRICTED_MAX_PAGES trang, quá nặng hoặc hỏng — không trả tệp |  |
| 500 | Tệp mã hóa không mở được: bản mã hỏng hoặc không khớp tệp |  |
| 503 | CSDL, kho đối tượng hoặc két khóa không sẵn sàng; `busy` (kèm `Retry-After: 10`) khi đang mở, kiểm tệp hạn chế khác |  |

## `GET /api/search`

Tìm văn bản theo số ký hiệu, trích yếu, cơ quan ban hành, nội dung

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `q` | query | ✓ | `string` | Gõ có dấu hay không dấu đều được |
| `direction` | query |  | `"in", "out" hoặc null` |  |
| `status` | query |  | `"received", "registered", "in_progress", "done", "draft", "in_review", "returned", "approved", "issued", "archived", "cancelled" hoặc null` |  |
| `type_code` | query |  | `string hoặc null` |  |
| `urgency` | query |  | `"normal", "khan", "thuong_khan", "hoa_toc" hoặc null` |  |
| `year` | query |  | `integer hoặc null` |  |
| `limit` | query |  | `integer` | Mặc định `20`. |
| `cursor` | query |  | `string hoặc null` | `next_cursor` của trang trước |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Thành công | `application/json` `SearchOut` |
| 400 | Câu tìm trống, hoặc `cursor` sai, không phải của câu tìm này |  |
| 401 | Thiếu hoặc sai token |  |
| 503 | Meilisearch hoặc CSDL không sẵn sàng |  |
| 422 | Dữ liệu gửi lên sai kiểu, thiếu trường | `application/json` `HTTPValidationError` |

## `GET /api/documents/{document_id}/preview`

Xem trước văn bản đi dưới dạng PDF đúng thể thức, chưa có số và mã xác thực

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `document_id` | đường dẫn | ✓ | `string (uuid)` |  |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Bản PDF in chữ DỰ THẢO | `application/pdf` |
| 401 | Thiếu hoặc sai token |  |
| 404 | Không có văn bản đi, hoặc người gọi không được đọc — hai trường hợp trả như nhau |  |
| 409 | Văn bản đã phát hành: tải bản phát hành thay vì xem trước |  |
| 503 | CSDL không sẵn sàng |  |
| 422 | Dữ liệu gửi lên sai kiểu, thiếu trường | `application/json` `HTTPValidationError` |

## `GET /api/registers/{direction}/{year}`

Sổ đăng ký văn bản đến / đi của một năm, đúng các cột sẽ in

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `direction` | đường dẫn | ✓ | `"in", "out"` | in: sổ văn bản đến; out: sổ văn bản đi |
| `year` | đường dẫn | ✓ | `integer` |  |
| `lang` | query |  | `"vi", "en"` | Ngôn ngữ của tên cột, ghi chú, bìa; mặc định vi. Mặc định `"vi"`. |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Thành công | `application/json` `RegisterOut` |
| 401 | Thiếu hoặc sai token |  |
| 403 | Chỉ văn thư và lãnh đạo đơn vị xem, in sổ đăng ký |  |
| 503 | CSDL không sẵn sàng |  |
| 422 | Dữ liệu gửi lên sai kiểu, thiếu trường | `application/json` `HTTPValidationError` |

## `GET /api/registers/{direction}/{year}/pdf`

In sổ đăng ký văn bản đến / đi của một năm ra PDF để ký nhận, đóng sổ (NĐ 30/2020, Điều 16, 22)

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `direction` | đường dẫn | ✓ | `"in", "out"` | in: sổ văn bản đến; out: sổ văn bản đi |
| `year` | đường dẫn | ✓ | `integer` |  |
| `lang` | query |  | `"vi", "en"` | Ngôn ngữ của tên cột, ghi chú, bìa; mặc định vi. Mặc định `"vi"`. |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Sổ A4 ngang: bìa, bảng theo mẫu, chỗ ký của văn thư | `application/pdf` |
| 401 | Thiếu hoặc sai token |  |
| 403 | Chỉ văn thư và lãnh đạo đơn vị xem, in sổ đăng ký |  |
| 503 | CSDL không sẵn sàng |  |
| 422 | Dữ liệu gửi lên sai kiểu, thiếu trường | `application/json` `HTTPValidationError` |

## `GET /api/verify/ca.pem`

Chứng thư CA nội bộ ký văn bản đi (PEM, chỉ minh họa; không cần đăng nhập)

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Tệp PEM | `application/x-pem-file` |
| 404 | Két chưa có (két khởi tạo trước khi có tính năng này, hoặc không dùng két) |  |
| 429 | Vượt giới hạn tra cứu theo địa chỉ IP (APISIX) |  |
| 503 | Két không trả lời |  |

## `GET /api/verify/anchor-key.pem`

Khóa công khai Ed25519 ký mốc neo sổ kiểm toán (PEM SubjectPublicKeyInfo; không cần đăng nhập)

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Tệp PEM | `application/x-pem-file` |
| 404 | Két chưa có (két khởi tạo trước khi có tính năng này, hoặc không dùng két) |  |
| 429 | Vượt giới hạn tra cứu theo địa chỉ IP (APISIX) |  |
| 503 | Két không trả lời |  |

## `GET /api/verify/{code}`

Tra văn bản đã phát hành theo mã tra cứu in cạnh mã QR (không cần đăng nhập)

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `code` | đường dẫn | ✓ | `string` |  |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | valid: văn bản đã phát hành; not_found: không có văn bản nào khớp | `application/json` `VerifyOut` |
| 429 | Vượt giới hạn tra cứu theo địa chỉ IP (APISIX) |  |
| 503 | CSDL không sẵn sàng |  |
| 422 | Dữ liệu gửi lên sai kiểu, thiếu trường | `application/json` `HTTPValidationError` |

## `GET /api/verify`

Tra văn bản đã phát hành theo SHA-256 của tệp PDF (trình duyệt tự tính, không tải tệp lên)

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `sha256` | query | ✓ | `string` | SHA-256 của tệp, 64 ký tự hex |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | valid: văn bản đã phát hành; not_found: không có văn bản nào khớp | `application/json` `VerifyOut` |
| 429 | Vượt giới hạn tra cứu theo địa chỉ IP (APISIX) |  |
| 503 | CSDL không sẵn sàng |  |
| 422 | Dữ liệu gửi lên sai kiểu, thiếu trường | `application/json` `HTTPValidationError` |

## `GET /api/status`

Trạng thái vận hành các thành phần của Signet (không cần đăng nhập, lưu đệm 10 giây)

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Thành công | `application/json` `StatusOut` |
| 429 | Vượt giới hạn theo địa chỉ IP (APISIX) |  |

## `GET /api/case-files/{case_file_id}/archive`

Phòng đọc: đọc lại gói lưu trữ của hồ sơ đã nộp lưu từ bucket lạnh, kiểm băm

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `case_file_id` | đường dẫn | ✓ | `string (uuid)` |  |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Thành công | `application/json` `ArchiveOut` |
| 404 | Không có hồ sơ, hoặc người gọi không được xem |  |
| 409 | Hồ sơ chưa nộp lưu |  |
| 502 | `archive_mismatch`: gói trong bucket lạnh không khớp băm ghi trong CSDL, hoặc thiếu một phần của gói |  |
| 503 | Chưa đọc được CSDL hoặc bucket lạnh |  |
| 422 | Dữ liệu gửi lên sai kiểu, thiếu trường | `application/json` `HTTPValidationError` |

## `POST /api/case-files/{case_file_id}/archive`

Nộp lưu ngay hồ sơ đã đóng (lãnh đạo phòng): gói Parquet + tệp + manifest vào bucket lạnh

Cùng các bước như vòng nộp lưu nền: kiểm băm tệp nóng, ghi gói khóa ghi, đọc lại so băm, hàm SQL
`office.archive_case_file` một giao dịch. Giành được lượt rồi mới kiểm lại hồ sơ và ghi `case_file.archive_requested`
vào sổ kiểm toán, sau đó mới làm; CSDL ghi `case_file.archived` khi xong.

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `case_file_id` | đường dẫn | ✓ | `string (uuid)` |  |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Thành công | `application/json` `ArchiveRunOut` |
| 401 | Thiếu hoặc sai token |  |
| 403 | `forbidden`: chỉ lãnh đạo phòng (`manager`) nộp lưu hồ sơ của phòng mình |  |
| 404 | Không có hồ sơ, hoặc hồ sơ không thuộc phòng của người gọi |  |
| 409 | `not_closed` hồ sơ còn mở · `already_archived` đã nộp lưu (kể cả lượt khác vừa xong) · `archive_failed` + `message`: không nộp lưu được (văn bản không còn ở trạng thái nộp lưu được, đang gửi liên thông, tệp trong kho nóng không khớp băm…) · `archive_conflict`: CSDL từ chối vì hồ sơ hay văn bản đổi trong lúc nộp lưu — CSDL không đổi gì |  |
| 503 | CSDL, kho đối tượng hoặc sổ kiểm toán chưa sẵn sàng; `busy` (kèm `Retry-After: 10`) khi đang có lượt nộp lưu khác trong tiến trình (nút bấm hay vòng nền) — chưa ghi sổ |  |
| 422 | Dữ liệu gửi lên sai kiểu, thiếu trường | `application/json` `HTTPValidationError` |

## `GET /api/case-files/{case_file_id}/archive/files/{file_id}`

Phòng đọc: xem một tệp trong gói lưu trữ (chỉ xem, PDF có dấu tên người xem)

Cùng quy tắc quyền như `GET /api/case-files/{id}/archive`: hồ sơ người gọi xem được, tệp gắn với văn bản người gọi đọc
được. Tệp đọc từ bucket lạnh, so băm với manifest (manifest đã so với CSDL), đóng dấu tên người xem và giờ xem lên mọi
trang, ghi `case_file.file_viewed` vào sổ kiểm toán — ghi không được thì không trả tệp. Không ghi gì vào bucket lạnh.

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `case_file_id` | đường dẫn | ✓ | `string (uuid)` |  |
| `file_id` | đường dẫn | ✓ | `string (uuid)` |  |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Bản PDF có dấu tên người xem và giờ xem trên mọi trang, `Content-Disposition: inline` | `application/pdf` |
| 401 | Thiếu hoặc sai token |  |
| 404 | Không có hồ sơ, tệp không thuộc gói, hoặc người gọi không đọc được văn bản nào gắn tệp này — các trường hợp trả như nhau |  |
| 409 | Hồ sơ chưa nộp lưu |  |
| 415 | `not_viewable`: tệp không phải PDF — phòng đọc chỉ mở bản PDF đóng dấu được |  |
| 422 | `unstampable` + `reason`: PDF không đóng dấu được (quá MOC_RESTRICTED_MAX_PAGES trang, quá nặng, hỏng) — không trả tệp |  |
| 502 | `archive_mismatch`: manifest không khớp băm trong CSDL, tệp không khớp băm trong manifest, hoặc gói thiếu manifest hay tệp — không trả tệp |  |
| 503 | CSDL, bucket lạnh hoặc sổ kiểm toán chưa sẵn sàng; `busy` (kèm `Retry-After: 10`) khi đang đóng dấu tệp khác |  |

## `GET /api/case-files/archive-stats`

Trang Điều hành: số liệu văn bản đã nộp lưu — DuckDB đọc các gói Parquet trong bucket lạnh

Quyền như trang Điều hành: chỉ lãnh đạo đơn vị, số liệu của đơn vị trong token (Hasura trả các hồ sơ đã nộp lưu người
gọi xem được). Mỗi gói: manifest so băm với CSDL, bảng văn bản so băm với manifest, rồi DuckDB đếm trên mọi bảng một
lượt. Chỉ số đếm; lưu đệm tới khi có hồ sơ mới nộp lưu (có gói không đọc được thì 60 giây). Mỗi tập manifest mới là một
run OpenLineage `moc.archive.stats` (đầu vào: các bảng Parquet đã đọc).

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Thành công | `application/json` `ArchiveStatsOut` |
| 401 | Thiếu hoặc sai token |  |
| 403 | `forbidden`: chỉ lãnh đạo đơn vị (`director`), như trang Điều hành |  |
| 503 | Chưa đọc được CSDL hoặc bucket lạnh |  |

## Kiểu dữ liệu

Các kiểu mà thân yêu cầu và nội dung trả về ở trên nhắc tới.

### `ArchiveDepartmentOut`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `department_id` | `string (uuid) hoặc null` | ✓ | Phòng lập hồ sơ, theo manifest của gói |
| `case_files` | `integer` | ✓ |  |
| `documents` | `integer` | ✓ |  |

### `ArchiveOut`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `case_file_id` | `string (uuid)` | ✓ |  |
| `code` | `string` | ✓ |  |
| `title` | `string` | ✓ |  |
| `closed_on` | `string (date) hoặc null` | ✓ |  |
| `archived_at` | `string (date-time)` | ✓ |  |
| `archive_key` | `string` | ✓ | Tiền tố của gói trong bucket lạnh (khóa ghi S3 Object Lock) |
| `manifest_sha256` | `string` | ✓ | Băm manifest.json đọc từ bucket lạnh — đã so khớp với CSDL |
| `retain_until` | `string (date-time)` | ✓ | Hạn giữ khóa ghi của gói |
| `documents` | `ArchivedDocumentOut[]` | ✓ | Văn bản người gọi đọc được (cùng quy tắc như trước khi nộp lưu), đọc từ bảng Parquet trong gói (DuckDB) |
| `files` | `ArchivedFileOut[]` | ✓ | Tệp của các văn bản trên |
| `hidden` | `integer` | ✓ | Số văn bản trong gói người gọi không được đọc — chỉ biết có, không biết là gì |

### `ArchiveRunOut`

Kết quả nộp lưu theo yêu cầu: gói đã nằm trong bucket lạnh, đọc lại khớp băm, CSDL đã chuyển `archived`.

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `case_file_id` | `string (uuid)` | ✓ |  |
| `code` | `string` | ✓ |  |
| `archive_key` | `string` | ✓ | Tiền tố của gói trong bucket lạnh (khóa ghi S3 Object Lock) |
| `archive_sha256` | `string` | ✓ | Băm manifest của gói — cũng là case_files.archive_sha256 |
| `documents` | `integer` | ✓ |  |
| `files` | `integer` | ✓ |  |
| `bytes` | `integer` | ✓ | Tổng số byte tệp và bảng Parquet đã ghi vào gói |
| `run_id` | `string` | ✓ | Run OpenLineage của lượt nộp lưu (core.lineage_events, F3.9) |

### `ArchiveStatsOut`

Số liệu văn bản đã nộp lưu của đơn vị: DuckDB đọc các bảng Parquet trong bucket lạnh (#304). Chỉ số đếm.

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `case_files` | `integer` | ✓ | Số hồ sơ đã nộp lưu có gói đọc được, khớp băm |
| `documents` | `integer` | ✓ |  |
| `incoming` | `integer` | ✓ |  |
| `outgoing` | `integer` | ✓ |  |
| `by_year` | `ArchiveYearOut[]` | ✓ |  |
| `by_type` | `ArchiveTypeOut[]` | ✓ |  |
| `by_department` | `ArchiveDepartmentOut[]` | ✓ |  |
| `unreadable` | `UnreadablePackageOut[]` | ✓ | Hồ sơ có gói không đọc được (lệch băm, thiếu đối tượng, sai dạng): không vào số liệu, bình thường rỗng. Chỉ `case_file_id` và ký hiệu (`code`); lý do ghi vào nhật ký (`case_file.archive_stats_skipped`) |
| `bucket` | `string` | ✓ | Bucket lạnh (khóa ghi S3 Object Lock) chứa các gói |
| `computed_at` | `string (date-time)` | ✓ | Lúc DuckDB tính; tính lại khi có hồ sơ mới nộp lưu |

### `ArchiveTypeOut`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `type_code` | `string` | ✓ | Mã loại văn bản (office.document_types) |
| `incoming` | `integer` | ✓ |  |
| `outgoing` | `integer` | ✓ |  |

### `ArchiveYearOut`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `year` | `integer hoặc null` | ✓ | Năm ban hành của văn bản (thiếu thì năm của hồ sơ) |
| `incoming` | `integer` | ✓ |  |
| `outgoing` | `integer` | ✓ |  |

### `ArchivedDocumentOut`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `id` | `string (uuid)` | ✓ |  |
| `direction` | `"in", "out"` | ✓ |  |
| `type_code` | `string` | ✓ |  |
| `symbol` | `string hoặc null` | ✓ |  |
| `issuer_name` | `string hoặc null` | ✓ |  |
| `issued_on` | `string (date) hoặc null` | ✓ |  |
| `summary` | `string` | ✓ |  |
| `register_number` | `integer hoặc null` | ✓ |  |
| `verify_code` | `string hoặc null` | ✓ |  |
| `content_sha256` | `string hoặc null` | ✓ |  |

### `ArchivedFileOut`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `file_id` | `string (uuid)` | ✓ | Mở trong phòng đọc: GET /api/case-files/{id}/archive/files/{file_id} |
| `filename` | `string` | ✓ |  |
| `mime_type` | `string` | ✓ |  |
| `sha256` | `string` | ✓ |  |
| `bytes` | `integer` | ✓ |  |
| `document_ids` | `string (uuid)[]` | ✓ | Văn bản người gọi đọc được có gắn tệp này |
| `viewable` | `boolean` | ✓ | Xem được trong phòng đọc (PDF, đóng dấu người xem); tệp khác chỉ hiện băm, cỡ |

### `AskAnswer`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `text` | `string` | ✓ | Chữ thuần; mỗi ý kèm [n] trỏ tới `sources[n-1]`. Giao diện hiển thị như chữ, không như HTML |
| `source` | `"extract", "model", "fixed", "data"` | ✓ | extract: câu trích nguyên văn · model: mô hình viết, máy chủ kiểm và gán [n] theo bằng chứng · fixed: câu cố định cho câu hỏi ngoài phạm vi · data: câu có số từ dữ liệu của người hỏi |
| `model` | `string hoặc null` | ✓ | Mô hình đã viết câu trả lời; null với câu trích |

### `AskIn`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `question` | `string` | ✓ | Câu hỏi, tối đa 500 ký tự sau chuẩn hóa |
| `mode` | `"extract", "generate"` |  | extract: chỉ câu trích nguyên văn (dưới 1 giây) · generate: thêm câu trả lời do mô hình viết (15–40 giây, chỉ khi `ai_available`). Mặc định `"extract"`. |
| `direction` | `"in", "out" hoặc null` |  | Chỉ văn bản đến (in) hoặc văn bản đi (out) |
| `year` | `integer hoặc null` |  | Năm ban hành |
| `type_code` | `string hoặc null` |  | Mã loại văn bản, vd CV |
| `document_id` | `string (uuid) hoặc null` |  | Chỉ hỏi trong một văn bản (nút "Hỏi về văn bản này"). Chỉ thu hẹp phạm vi: văn bản người hỏi không được xem, văn bản hạn chế hay không có thì trả `no_evidence` như mọi lượt |
| `ask_id` | `string (uuid) hoặc null` |  | Gửi lại `ask_id` của lượt extract ở lượt generate: hai dòng sổ kiểm toán cùng một câu hỏi |
| `previous` | `string hoặc null` |  | Câu hỏi của lượt ngay trước trong cùng phạm vi (`rewritten` của lượt đó nếu có), để hiểu câu nối tiếp như "Còn khoa Kinh tế thì sao?". Máy chủ không lưu; sai dạng thì bị bỏ qua |

### `AskOut`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `ask_id` | `string (uuid)` | ✓ |  |
| `status` | `"answered", "passages_only", "no_evidence"` | ✓ | answered: có câu trả lời · passages_only: có đoạn liên quan, chưa trích được câu trả lời ngắn · no_evidence: không có văn bản nào người hỏi được xem có nội dung này |
| `answer` | `AskAnswer hoặc null` | ✓ | Câu trả lời của mô hình nếu đạt, không thì câu trích; null khi không có |
| `extract` | `AskAnswer hoặc null` | ✓ | Câu trích nguyên văn; null khi không câu nào đạt |
| `sources` | `AskSource[]` | ✓ | Theo thứ tự xếp hạng, tối đa `MOC_ASK_TOP_K`; [] khi no_evidence |
| `semantic` | `boolean` | ✓ | Lượt này có tìm theo nghĩa (mô hình nhúng) |
| `ai_available` | `boolean` | ✓ | Mô hình viết câu trả lời đang sẵn sàng (gọi lại với mode=generate) |
| `warnings` | `"embed_unavailable", "model_unavailable", "model_timeout", "model_rejected", "model_declined"[]` | ✓ |  |
| `duration_ms` | `integer` | ✓ |  |
| `route` | `"van_ban", "gioi_thieu", "huong_dan", "ngoai_pham_vi", "viec_cua_toi", "dem_van_ban"` | ✓ | Đường bộ định tuyến đã chọn: van_ban: tìm trong kho văn bản · gioi_thieu: câu về chính trợ lý, câu chào · huong_dan: cách dùng Signet, trả lời từ hướng dẫn sử dụng · ngoai_pham_vi: câu cố định, không tìm · viec_cua_toi: đếm việc trong Hộp việc của người hỏi · dem_van_ban: đếm văn bản người hỏi được xem. Trừ van_ban, huong_dan, các đường không gọi mô hình, cả khi mode=generate |
| `route_reason` | `string` | ✓ | Mã lý do, máy đọc: `kw:<mẫu>` (mẫu đã khớp) hoặc `mac-dinh` |
| `rewritten` | `string hoặc null` | ✓ | Câu nối tiếp đã ghép với `previous` thành câu độc lập — câu đem đi tìm. null khi không phải câu nối tiếp |
| `data` | `object hoặc null` |  | Đường viec_cua_toi, dem_van_ban: các số và bộ lọc của câu trả lời `source: data`, máy đọc. viec_cua_toi: `{kind: tasks, on, tasks, overdue, today, soon, no_due}` · dem_van_ban: `{kind: documents, counts: {in?, out?}, type_code, from, to}` (`to` là ngày sau ngày cuối; null: không lọc theo ngày). null với đường khác |
| `link` | `string hoặc null` |  | Trang trong Signet xem danh sách đã đếm: `/` (Hộp việc, Lịch hạn), `/van-ban-den`, `/van-ban-di`; null khi không có trang nào hợp |

### `AskSource`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `n` | `integer` | ✓ | Số trong dấu [n], từ 1 |
| `document_id` | `string (uuid) hoặc null` | ✓ | null với nguồn `guide` |
| `symbol` | `string hoặc null` | ✓ |  |
| `type_code` | `string hoặc null` | ✓ |  |
| `type_name` | `string hoặc null` | ✓ |  |
| `summary` | `string` | ✓ |  |
| `issuer_name` | `string hoặc null` | ✓ |  |
| `issued_on` | `string (date) hoặc null` | ✓ |  |
| `direction` | `"in", "out" hoặc null` | ✓ |  |
| `status` | `string hoặc null` | ✓ |  |
| `kind` | `"page", "meta", "guide"` | ✓ | page: đoạn chữ của tệp · meta: chỉ có trích yếu (bản scan, chưa có tệp, tệp không đọc được chữ) · guide: mục của hướng dẫn sử dụng hay của Giới thiệu trợ lý; `symbol` là tên tài liệu, `summary` là tiêu đề mục |
| `file_id` | `string (uuid) hoặc null` | ✓ |  |
| `file_role` | `"main", "attachment", "issued" hoặc null` | ✓ | main: bản chính · attachment: tài liệu kèm theo · issued: bản phát hành văn bản đi |
| `page` | `integer hoặc null` | ✓ | Trang trong tệp; null với đoạn meta hoặc chữ chưa có ranh giới trang |
| `excerpt` | `string` | ✓ | Đoạn trích ≤ 600 ký tự quanh câu khớp nhất |
| `cited` | `boolean` | ✓ | Câu trả lời có trích nguồn này |
| `path` | `string hoặc null` |  | Chỉ nguồn `guide`: tệp trong repo kèm neo mục, vd `docs/huong-dan/viec-chung.md#đơn-nghỉ-phép` |

### `FileOut`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `id` | `string (uuid)` | ✓ |  |
| `filename` | `string` | ✓ |  |
| `mime_type` | `string` | ✓ |  |
| `size_bytes` | `integer` | ✓ |  |
| `sha256` | `string` | ✓ |  |
| `scanned_at` | `string (date-time)` | ✓ |  |
| `encrypted` | `boolean` |  | Mặc định `false`. |

### `HTTPValidationError`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `detail` | `ValidationError[]` |  |  |

### `ImportOut`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `id` | `string (uuid)` | ✓ |  |
| `kind` | `"incoming"` | ✓ | incoming: văn bản đến |
| `status` | `"queued", "running", "done"` | ✓ | queued: chờ vòng nền · running: đang xử lý · done: mọi dòng đã xong (đạt, trùng hoặc lỗi) |
| `filename` | `string` | ✓ | Tên tệp dữ liệu đã gửi |
| `format` | `"ndjson", "csv"` | ✓ |  |
| `register` | `boolean` | ✓ | Vào sổ từng văn bản sau khi tiếp nhận (registerIncoming) |
| `total` | `integer` | ✓ | Số dòng dữ liệu đã nhận (không tính dòng trống, tiêu đề CSV) |
| `pending` | `integer` | ✓ | Dòng chưa xử lý |
| `ok` | `integer` | ✓ | Dòng đã ghi (và vào sổ khi register=true) |
| `duplicate` | `integer` | ✓ | Dòng trùng văn bản đã có (cùng số ký hiệu, cơ quan ban hành, ngày ban hành) |
| `failed` | `integer` | ✓ | Dòng lỗi — lý do ở GET /api/imports/{id}/rows?status=failed |
| `note` | `string hoặc null` | ✓ | Ghi chú của lô, vd tạm dừng vì lõi bận, tệp nén mất sau khi svc-files khởi động lại |
| `created_at` | `string (date-time)` | ✓ |  |
| `started_at` | `string (date-time) hoặc null` | ✓ |  |
| `finished_at` | `string (date-time) hoặc null` | ✓ |  |

### `ImportRowOut`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `line` | `integer` | ✓ | NDJSON: dòng vật lý tính từ 1; CSV: hàng như Excel (tiêu đề là 1) |
| `status` | `"pending", "ok", "duplicate", "failed"` | ✓ |  |
| `code` | `string hoặc null` | ✓ | Mã lỗi khi failed, vd invalid, bad_json, missing_attachment, infected, archive_lost, register_failed (services/svc-files/README.md) |
| `message` | `string hoặc null` | ✓ | Lý do, tiếng Việt |
| `fields` | `object (giá trị string) hoặc null` | ✓ | Lỗi theo trường như form tiếp nhận: trường → mã (schemas/README.md) |
| `document_id` | `string (uuid) hoặc null` | ✓ | Văn bản đã tạo (cả khi vào sổ lỗi: register_failed) |
| `register_number` | `integer hoặc null` | ✓ | Số đến khi register=true |

### `ImportRowsOut`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `rows` | `ImportRowOut[]` | ✓ |  |
| `next_after` | `integer hoặc null` | ✓ | Gửi lại ở tham số `after` để lấy trang sau; null khi đã hết |

### `ImportsOut`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `imports` | `ImportOut[]` | ✓ |  |

### `ReadField`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `value` | `string` | ✓ | issued_on: ngày ISO; urgency: normal \| khan \| thuong_khan \| hoa_toc; type_code: mã trong danh mục loại văn bản |
| `confidence` | `"high", "medium", "low"` | ✓ | high, medium: giao diện điền sẵn; low: chỉ hiện gợi ý, văn thư bấm Dùng |
| `source` | `"rule", "model"` | ✓ | rule: quy tắc; model: mô hình ngôn ngữ (chỉ trích yếu) |

### `ReadOut`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `file_id` | `string (uuid)` | ✓ |  |
| `status` | `"ok", "empty"` | ✓ | ok: tìm được ít nhất một trường; empty: đọc được mà không ra trường nào |
| `method` | `"text", "ocr"` | ✓ | text: lớp chữ của PDF; ocr: nhận dạng chữ bản scan, ảnh |
| `pages` | `integer` | ✓ | Số trang của tệp |
| `fields` | `object (giá trị ReadField)` | ✓ | Chỉ có khóa đã tìm thấy |
| `warnings` | `string[]` | ✓ | Mã cố định: future_date, invalid_date, symbol_no_number, type_conflict, low_text, truncated, model_unavailable, model_timeout, model_rejected, model_skipped |
| `summary_source` | `"rule", "model", "none"` | ✓ |  |
| `model` | `string hoặc null` | ✓ | Mô hình ngôn ngữ đã gọi; null nếu không gọi |
| `duration_ms` | `integer` | ✓ |  |
| `cached` | `boolean` | ✓ | true: gợi ý đã lưu từ lần đọc trước (không đọc lại, không ghi sổ) |
| `read_at` | `string (date-time)` | ✓ |  |

### `RegisterEntryOut`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `number` | `integer` | ✓ | Số đến (sổ đến) hoặc số văn bản đi (sổ đi) |
| `document_id` | `string (uuid) hoặc null` | ✓ | Mở văn bản trên giao diện; null khi dòng bị che |
| `hidden` | `boolean` | ✓ | Văn bản hạn chế người gọi không được đọc: chỉ có số, ngày, số ký hiệu |
| `cells` | `string[]` | ✓ | Giá trị từng cột, đúng thứ tự `columns`; ô Ký nhận để trống |

### `RegisterOut`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `direction` | `"in", "out"` | ✓ |  |
| `year` | `integer` | ✓ |  |
| `title` | `string` | ✓ |  |
| `org_name` | `string` | ✓ |  |
| `columns` | `string[]` | ✓ | Cột theo mẫu sổ đăng ký, NĐ 30/2020/NĐ-CP Phụ lục IV |
| `entries` | `RegisterEntryOut[]` | ✓ |  |
| `last_number` | `integer` | ✓ | Số cuối đã cấp trong năm |
| `missing` | `integer[]` | ✓ | Số đã cấp mà không có dòng — sổ phải liền số, bình thường rỗng |

### `SearchHit`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `id` | `string (uuid)` | ✓ |  |
| `direction` | `"in", "out"` | ✓ |  |
| `status` | `"received", "registered", "in_progress", "done", "draft", "in_review", "returned", "approved", "issued", "archived", "cancelled"` | ✓ |  |
| `type_code` | `string` | ✓ |  |
| `symbol` | `string hoặc null` | ✓ |  |
| `issuer_name` | `string hoặc null` | ✓ |  |
| `issued_on` | `string (date) hoặc null` | ✓ |  |
| `summary` | `string` | ✓ |  |
| `urgency` | `"normal", "khan", "thuong_khan", "hoa_toc"` | ✓ |  |
| `register_number` | `integer hoặc null` | ✓ |  |
| `registered_at` | `string (date-time) hoặc null` | ✓ |  |
| `due_on` | `string (date) hoặc null` | ✓ |  |
| `matched_content` | `boolean` |  | Khớp trong nội dung (văn bản đi, chữ của tệp PDF đính kèm), không khớp số ký hiệu, trích yếu, cơ quan ban hành. Mặc định `false`. |

### `SearchOut`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `hits` | `SearchHit[]` | ✓ |  |
| `next_cursor` | `string hoặc null` | ✓ | Gửi lại ở tham số `cursor` để lấy trang sau; null khi đã hết |

### `StatusAi`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `enabled` | `boolean` | ✓ | Mô hình viết câu trả lời của trợ lý đang sẵn sàng |
| `model` | `string hoặc null` | ✓ | Tên mô hình khi bật, vd qwen3:1.7b; null khi tắt |
| `semantic` | `boolean` | ✓ | Tìm theo nghĩa được (mô hình nhúng sẵn sàng) |

### `StatusComponent`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `id` | `string` | ✓ | Mã thành phần, vd cong-api, dang-nhap, csdl, quy-trinh, tro-ly-ai |
| `layer` | `string` | ✓ | Mã tầng trong `layers` |
| `label` | `string` | ✓ | Tên tiếng Việt, vd Đăng nhập một lần |
| `software` | `string` | ✓ | Phần mềm nguồn mở đảm nhận (không kèm phiên bản), vd Keycloak |
| `status` | `"ok", "degraded", "down", "off"` | ✓ | ok: hoạt động · degraded: chạy một phần · down: gián đoạn (không trả lời, quá hạn dò) · off: tắt theo cấu hình (vd chưa bật mô hình ngôn ngữ) |

### `StatusLayer`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `id` | `string` | ✓ |  |
| `label` | `string` | ✓ |  |

### `StatusOpenData`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `source` | `string` | ✓ | Mã nguồn, tên thư mục trong seed/du-lieu-mo, vd cong-bao-gddt |
| `name` | `string hoặc null` | ✓ |  |
| `publisher` | `string hoặc null` | ✓ | Cơ quan công bố |
| `home_url` | `string hoặc null` | ✓ |  |
| `reuse_basis` | `string hoặc null` | ✓ | Căn cứ dùng lại (điều luật hay giấy phép) |
| `licence` | `string hoặc null` | ✓ | Giấy phép mở nếu nguồn có; null: dùng lại theo `reuse_basis` |
| `fetched_at` | `string (date-time) hoặc null` | ✓ | Lúc lấy bản chụp |
| `age_days` | `integer hoặc null` | ✓ | Tuổi bản chụp, tính bằng ngày |
| `max_age_days` | `integer hoặc null` | ✓ |  |
| `state` | `"ok", "stale", "broken"` | ✓ | ok · stale: quá `max_age_days` · broken: manifest hỏng, thiếu tệp, sai cỡ hay sai SHA-256 |
| `files` | `StatusOpenDataFile[]` | ✓ |  |

### `StatusOpenDataFile`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `file` | `string` | ✓ | Tên tệp trong bản chụp, vd tt-26-2026-tt-bgddt.pdf |
| `url` | `string hoặc null` | ✓ | Nơi đã tải tệp (http/https) |
| `sha256` | `string` | ✓ | SHA-256 của tệp; trùng `sha256` của một tệp đính kèm là văn bản từ nguồn này |
| `bytes` | `integer` | ✓ |  |
| `fetched_at` | `string (date-time) hoặc null` | ✓ | Lúc tải tệp; null: như `fetched_at` của nguồn |
| `meta` | `object (giá trị string hoặc integer hoặc number hoặc boolean hoặc null)` | ✓ | Thông tin tùy nguồn, chỉ giá trị đơn, vd symbol, issuer_name, issued_on, page_url, gazette |

### `StatusOut`

Trạng thái vận hành, công khai: chỉ chữ cố định và trạng thái, không tên máy, địa chỉ hay số liệu nghiệp vụ.

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `status` | `"ok", "degraded", "down"` | ✓ | down: có thành phần thiết yếu gián đoạn · degraded: thành phần khác gián đoạn hoặc chạy một phần |
| `checked_at` | `string (date-time)` | ✓ | Lúc dò; kết quả lưu đệm MOC_STATUS_CACHE_S giây (mặc định 10) |
| `version` | `string` | ✓ | Phiên bản Signet đang chạy (MOC_VERSION) |
| `uptime_s` | `integer` | ✓ | Số giây svc-files đã chạy liên tục từ lần khởi động gần nhất |
| `last_backup_at` | `string (date-time) hoặc null` | ✓ | Lượt sao lưu gần nhất (`moc backup create`) mà CSDL biết; null: chưa có |
| `ai` | `StatusAi` | ✓ |  |
| `layers` | `StatusLayer[]` | ✓ | Các tầng theo thứ tự hiện: người dùng → lõi → quy trình → dữ liệu → trí tuệ nhân tạo |
| `components` | `StatusComponent[]` | ✓ |  |
| `open_data` | `StatusOpenData[]` |  | Nguồn dữ liệu công khai đi kèm bản cài (#424): nguồn gốc, tuổi dữ liệu; bản cài không gọi nguồn lúc chạy, chỉ đọc bản chụp |

### `UnreadablePackageOut`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `case_file_id` | `string (uuid)` | ✓ |  |
| `code` | `string` | ✓ |  |

### `ValidationError`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `loc` | `string hoặc integer[]` | ✓ |  |
| `msg` | `string` | ✓ |  |
| `type` | `string` | ✓ |  |
| `input` | `any` |  |  |
| `ctx` | `object` |  |  |

### `VerifiedDocument`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `symbol` | `string` | ✓ |  |
| `issued_on` | `string (date)` | ✓ |  |
| `type_name` | `string` | ✓ |  |
| `issuer_name` | `string` | ✓ |  |
| `parent_name` | `string hoặc null` | ✓ |  |
| `summary` | `string hoặc null` | ✓ |  |
| `sha256` | `string` | ✓ |  |
| `verify_code` | `string` | ✓ |  |
| `status` | `"issued", "archived"` | ✓ |  |
| `signature` | `VerifiedSignature hoặc null` |  | Chữ ký số của bản phát hành (F4.5, chỉ minh họa); null: văn bản phát hành khi ký số chưa bật hoặc ký lỗi, hoặc văn bản hạn chế |

### `VerifiedSignature`

Chữ ký số của bản phát hành (F4.5) — PKI nội bộ của Signet, chỉ minh họa, không có giá trị pháp lý như chữ ký số công
cộng. svc-files đã tự kiểm chữ ký lúc ký; kiểm lại tệp: python -m svc_files.signing verify.

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `level` | `"PAdES-B-B"` | ✓ | Chuẩn chữ ký: PAdES mức B-B, không có dấu thời gian tin cậy |
| `signer` | `string` | ✓ | Người ký: CN chứng thư của đơn vị phát hành |
| `ca` | `string` | ✓ | CN của CA nội bộ cấp chứng thư |
| `serial` | `string` | ✓ | Số sê-ri chứng thư, hex thường |
| `signed_at` | `string (date-time)` | ✓ | Giờ ký tự ghi trong chữ ký (không có dấu thời gian tin cậy) |
| `illustrative` | `true` |  | Luôn true: chữ ký chỉ để minh họa. Mặc định `true`. |

### `VerifyOut`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `result` | `"valid", "not_found"` | ✓ |  |
| `document` | `VerifiedDocument hoặc null` |  |  |
