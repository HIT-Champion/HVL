# db — schema PostgreSQL và metadata Hasura

Dữ liệu có cấu trúc của Signet (F1.3): schema `core` dùng chung cho mọi ứng dụng, schema `office` của ứng dụng
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
| Quyền Hasura cho 9 vai trò (`clerk`, `staff`, `manager`, `director`, `tenant_admin`, `verifier`, `service`, `agent`, `tu_dong`), cách ly thuê ước | **Xong** — `test_permissions.py` 23 test, cùng phần quyền trong test của từng bảng |
| Sổ kiểm toán chuỗi băm (F2.12): trigger trên mọi bảng nghiệp vụ, `core.audit_verify()`; mốc neo `core.audit_anchors`; lãnh đạo, quản trị đơn vị xem sổ của đơn vị qua trường `overview` (không lộ nội dung; thấy năm, số dòng của lần in sổ đăng ký; mẫu mã độc, cỡ của tệp bị kiểm dịch chặn; ký hiệu hồ sơ, băm gói nộp lưu) | **Xong** — 23 test, gồm sửa lén khi tắt trigger, viết lại cả chuỗi, cắt đuôi, đổi hash văn bản |
| `core.users` (danh bạ đồng bộ từ Keycloak), hàm `office.register_incoming` (vào sổ trong một giao dịch), trigger `documents_received` (sự kiện `office.document.received` khi thêm văn bản đến, #381) | **Xong** — `test_registration.py` 11 test |
| `metadata/actions.graphql`, `actions.yaml`: `receiveIncoming`, `registerIncoming`, `submitOutgoing`, `myTasks`, `completeTask` → svc-workflow | **Xong** |
| Poka-yoke lớp 3 cho văn bản đến (F2.2): `documents_in_symbol`, `documents_in_issuer`, `documents_in_summary`, `documents_in_dates` — cùng quy tắc với `schemas/van-ban-den.json` (độ dài, khoảng trắng, ký tự ẩn, dạng NFC, năm 1900+); migration dọn trước dữ liệu cũ sửa được mà không đổi nghĩa | **Xong** — 43 test chạy chung bộ ca thử với form và svc-workflow, chèn thẳng bằng quyền quản trị |
| Văn bản đi: cột `body`, thông tin in trên văn bản ở `core.tenants`, hàm `office.number_outgoing` (cấp số đi, ký hiệu theo NĐ 30 trong một giao dịch), khung nhìn `office.issued_documents` cho cổng xác thực | **Xong** — 18 test |
| `core.file_texts` (lớp chữ của PDF để tìm theo nội dung, F2.7): không vai trò người dùng nào đọc được, xóa tệp thì xóa theo, không gắn sổ kiểm toán; tệp của văn bản hạn chế không có chữ (trigger) | **Xong** — 10 test |
| `core.notifications` (thông báo từng người, F2.5): mỗi người chỉ đọc và đánh dấu đã đọc thông báo của mình, chống gửi trùng theo khóa | **Xong** — 6 test |
| Lịch sử của văn bản (F3.5): view `office.document_history` — dòng sổ về văn bản, giao việc, tệp, lần vào hồ sơ, chỉ `overview`, không có hash, không có danh sách được xem; ai đọc được văn bản thì xem được lịch sử (văn bản hạn chế: chỉ người tạo và người có tên), phòng khác, đơn vị khác không thấy | **Xong** — 3 test |
| Sao lưu, khôi phục (F3.4): `pg_dump -Fc` → `pg_restore` giữ nguyên mọi dòng và hash của sổ kiểm toán; dòng `system.restored` nối tiếp chuỗi | **Xong** — 2 test, dump và restore ngay trong container PostgreSQL thử |
| View cho dashboard điều hành (F3.11): `office.v_document_counts`, `v_overdue_by_department`, `v_processing_time`, `v_outgoing_by_month` — chỉ có số đếm, lãnh đạo đơn vị đọc số của đơn vị mình; văn bản hạn chế không vào phép chia nào, chỉ có con số tổng | **Xong** — 6 test, trên một đơn vị riêng nên số đếm biết trước |
| Hồ sơ công việc, nộp lưu (F3.8): `office.case_files`, `office.case_file_documents`; trigger: chỉ văn bản đã xử lý xong, không hạn chế vào hồ sơ đang mở, ngày đóng do CSDL đặt, hồ sơ rỗng không đóng được, đóng rồi không mở lại, đã nộp lưu thì đóng băng; chuyên viên, tổ trưởng lập và đóng hồ sơ của phòng mình, chỉ đưa vào văn bản mình đọc được và thuộc phòng mình; hàm `office.archive_case_file` chỉ khóa quản trị gọi được, CSDL lệch với gói thì không đổi gì, lần hai bị từ chối; tệp đã nộp lưu không gắn lại vào dự thảo; sổ thấy ký hiệu hồ sơ, băm gói, không thấy tên hồ sơ | **Xong** — 8 test |
| Văn bản hạn chế (F3.7): tệp khớp chế độ (`files_encryption_key`; trigger `document_files_sealed` — văn bản hạn chế chỉ gắn tệp mã hóa và ngược lại, `documents_restricted_sealed` — có tệp thì không đổi chế độ; ràng buộc `documents_restricted_private` — văn bản hạn chế không công khai trích yếu); tệp mã hóa đã gắn vào văn bản chỉ theo quyền đọc văn bản, kể cả với người tạo dòng tệp; hàm `office.grant_document_access`, `revoke_document_access` cho văn thư, lãnh đạo đơn vị; thông báo về văn bản hạn chế bị gọt nội dung (trigger `notifications_restricted`, kể cả thông báo đã gửi khi văn bản chuyển sang hạn chế); `overview` của sổ che giá trị dòng về văn bản hạn chế người xem không đọc được (`office.audit_overview_seen`) | **Xong** — 16 test |
| Phả hệ dữ liệu (F3.9): `core.lineage_events` chỉ thêm (trigger chặn sửa, xóa kể cả ghi thẳng CSDL); lãnh đạo, văn thư đọc của đơn vị mình; vai trò khác không thấy, không ai ghi | **Xong** — 2 test |
| Liên thông văn bản trong hệ thống (F3.12): cột `office.documents.recipient_tenant_ids` (trigger `documents_recipient_units` — bỏ trùng, đơn vị có thật, khóa sau khi trình; `documents_recipient_units_other` — không gửi cho mình; `documents_restricted_local` — văn bản hạn chế không liên thông); view `office.dispatch_units` (mọi đơn vị trừ đơn vị của người xem); hộp thư đi `office.dispatches` — trigger tạo một dòng `pending` cho mỗi đơn vị nhận trong giao dịch phát hành; hàm `office.deliver_dispatch` (chỉ `service`, phiên của đơn vị nhận) tạo văn bản đến `received` kèm tệp, sự kiện ở hai bên, gọi lại thì trả nguyên dòng, trùng văn bản đã tiếp nhận thì nối vào (`duplicate`), vi phạm ràng buộc thì `failed`; chỉ mục `documents_source_once` chốt một văn bản đến cho mỗi văn bản gửi ở mỗi đơn vị; mỗi bên chỉ thấy phần của mình; sổ kiểm toán của cả hai đơn vị cùng ghi; còn dòng chờ giao thì chưa nộp lưu | **Xong** — 17 test |
| Đọc văn bản đến (F4.1, migration `1792281601900_intake_suggestions`): bảng `office.intake_suggestions` (gợi ý của tác tử `moc-doc-reader` theo tệp, ghi đè khi đọc lại, ràng buộc từng cột, chỉ sáu trường của form tiếp nhận); vai trò `agent` chỉ ghi gợi ý và dòng sổ `intake.suggested` của đơn vị trong phiên — thuê ước, danh tính, giờ đọc do Hasura, CSDL đặt; gợi ý và dòng sổ cùng một giao dịch; tệp mã hóa, tệp của văn bản hạn chế không có gợi ý (trigger chặn ghi, xóa khi văn bản bật hạn chế hoặc tệp gắn vào văn bản hạn chế); `core.audit()` ghi `actor_kind` `agent`; `overview` thấy cách đọc, không thấy nội dung; view `office.v_intake_accuracy` (lãnh đạo, quản trị đơn vị: số gợi ý văn thư giữ nguyên theo trường, độ tin cậy; bỏ văn bản hạn chế) | **Xong** — 35 test |
| Trợ lý hỏi đáp trên kho văn bản (F4.2, migration `1792281602000_assistant`): cột `core.file_texts.page_starts` (vị trí đầu mỗi trang trong chữ của PDF, để trích dẫn ghi số trang; ràng buộc `file_texts_page_starts` — chỉ khi `ok`, 1–200 trang, bắt đầu ở 0, không vượt độ dài chữ, không có null; dòng `ok` cũ bị xóa để đọc lại); vai trò `agent` ghi thêm được dòng sổ `assistant.answered` về `ai.questions` của tác tử `moc-assistant` — danh tính, thuê ước đặt sẵn từ phiên, không quyền nào khác; `overview` thấy chế độ, số đoạn, số nguồn, mô hình, thời gian, không thấy câu hỏi hay id văn bản nguồn; truy vấn nguồn của chỉ mục đoạn (khóa quản trị) và hậu kiểm bằng token người hỏi chạy đúng trên schema thật | **Xong** — 31 test |
| Gợi ý giao việc (F4.3, migration `1792281602100_assignment_suggestions`): bảng `office.assignment_suggestions` (một dòng mỗi văn bản đến của tác tử `moc-assigner` trong svc-workflow: đơn vị chủ trì, hạn đề xuất, độ tin cậy, căn cứ chỉ gồm id và số; ràng buộc hình dạng `assignment_suggestions_shape`, `assignment_suggestions_due`); vai trò `agent` chỉ thêm gợi ý và dòng sổ `assignment.suggested` về `office.documents` của đơn vị trong phiên, cùng một giao dịch — thuê ước, danh tính do Hasura đặt; văn bản hạn chế, văn bản đi không có gợi ý, văn bản hạn chế không làm căn cứ (trigger `assignment_suggestions_guard` khóa `for share` văn bản đích và căn cứ; bật hạn chế sau đó thì xóa gợi ý của văn bản, gỡ nó khỏi căn cứ của gợi ý khác); chỉ lãnh đạo đơn vị đọc, khi đọc được văn bản; `overview` và tab Lịch sử thấy kết quả, đơn vị, số ngày, độ tin cậy, không thấy trích yếu; view `office.v_assignment_suggestion_accuracy` (lãnh đạo, quản trị đơn vị: số giữ đơn vị, giữ hạn, sai số hạn, chỉ tính quyết định sau lúc gợi ý) | **Xong** — 47 test |
| Ký số văn bản đi (F4.5, chỉ minh họa, migration `1792281602200_file_signatures`): bảng `core.file_signatures` (một dòng mỗi bản phát hành đã ký: chuẩn PAdES-B-B, giờ ký tự khai, CN người ký và CA, số sê-ri, vân tay chứng thư, khóa transit `moc-ky-so-<đơn vị>` và phiên bản; ràng buộc từng cột); `svc-files` (vai trò `service`) chỉ thêm, cùng mutation với dòng `core.files` — thuê ước đặt sẵn từ phiên, khóa ngoại kèm thuê ước chặn gắn chữ ký vào tệp của đơn vị khác, xóa tệp thì xóa theo; không vai trò nào đọc, sửa, xóa; khung nhìn `office.issued_documents` thêm năm cột chữ ký (tìm theo băm `content_sha256`, nên văn bản đã nộp lưu vẫn có chữ ký; null khi không ký), chỉ mục `core.files (tenant_id, sha256)`; sổ kiểm toán có dòng `core.file_signatures` (`overview` chỉ giữ giá trị `file_id`) | **Xong** — 28 test |
| Nộp lưu không làm mất số liệu (migration `1792281602300_archived_stats`): bảng `office.archived_document_facts` (lúc xong, tệp bản chính của văn bản nộp lưu) ghi trong `office.archive_case_file` trước khi gỡ dòng thời gian, liên kết tệp; `v_processing_time`, `v_intake_accuracy` dùng bản giữ lại khi dòng sống không còn; văn bản nộp lưu trước đó điền lại từ sổ kiểm toán. Sổ không lộ danh sách được xem (migration `1792281602400_audit_acl_rows`): xem mục Sổ kiểm toán | **Xong** — 2 test (đã tính ở hai dòng Hồ sơ, Văn bản hạn chế) |
| Không gian cá nhân P.A.R.A — ứng dụng thứ hai trên lõi (`apps/ca-nhan`, migration `1792281602500_personal_space`, [`docs/them-ung-dung.md`](../docs/them-ung-dung.md)): schema riêng `personal`, không sửa `core`; bảng `personal.items` (tệp nào của ai ở thư mục nào trong bốn thư mục `projects`, `areas`, `resources`, `archives` — ràng buộc `items_para`); thuê ước, chủ do Hasura đặt từ token, mỗi người chỉ thấy, chỉ chuyển mục của mình, chỉ đổi được thư mục, không ai xóa; trigger `items_guard` chỉ cho xếp tệp chính mình tải lên, không mã hóa, cùng đơn vị (cả khi ghi thẳng CSDL); khóa ngoại kèm thuê ước tới `core.files`; sổ kiểm toán qua `core.audit('file_id')` có sẵn — `overview` chỉ giữ `file_id`, không lộ tên thư mục; clerk, staff, manager, director có không gian, `tenant_admin` không (không đọc `core.files`) | **Xong** — 11 test |
| Thông báo đa kênh (migration `1792281602600_notification_deliveries`, `1792281603700_sms_zalo_channels`): cột `core.notifications.channels` (kênh ngoài svc-workflow khai lúc ghi: `email`, `webhook`, `sms`, `zalo`); hộp thư đi `core.notification_deliveries` — trigger `notifications_deliveries` tạo một dòng `pending` cho mỗi kênh trong giao dịch ghi thông báo, gọi lại cùng khóa không thêm dòng; SMS, Zalo chỉ có dòng khi người nhận đã tự bật kênh (`core.notification_subscriptions`, Zalo phải liên kết bằng mã trước), tài khoản còn mở và — với SMS — `core.users.phone` có số; chỉ `service` của đơn vị đọc và ghi kết quả (không thêm, không xóa, không đổi kênh); không vai trò người dùng nào đọc hộp thư đi, bảng kênh tự bật hay số điện thoại; hộp thư đi không lưu địa chỉ, URL, nội dung; `sent` phải có `sent_at`; gắn sổ kiểm toán | **Xong** — 10 test |
| Góp ý và số đo "sau" (F4.6, migration `1792281602700_feedback`, `1792281602750_success_metrics`, `1792281603600_feedback_mask_pii`, [`docs/so-lieu-sau.md`](../docs/so-lieu-sau.md)): bảng `office.feedback` (mức 1–5, nội dung ≤ 500 ký tự, khuôn đường dẫn màn hình — ràng buộc `feedback_rating`, `feedback_comment`, `feedback_screen`); trigger `feedback_guard` — gọt khoảng trắng, che email và dãy số dài (`office.mask_pii`, #265), giờ gửi do CSDL đặt, chặn gửi dồn 3 góp ý mỗi 10 phút, 20 mỗi 24 giờ (lỗi `feedback_rate:`), kể cả gửi song song; trường `mine`; **không gắn sổ kiểm toán** (có chủ ý, xem Vai trò). Cột `core.tenants.sample_data` (đơn vị mẫu của `make seed`); view `office.v_time_to_assign`, `v_overdue_rate`, `v_feedback_summary` — chỉ số đếm, số giờ, văn bản hạn chế không tính | **Xong** — 33 test (`test_feedback.py` 25, `test_success_metrics.py` 8) |
| Lô nạp khối lớn (cụm ⑤, migration `1792281602800_import_jobs`): `core.import_jobs` (một lô: loại — hiện chỉ `incoming`, người tạo, phòng, định dạng, băm tệp dữ liệu và zip, `Idempotency-Key` duy nhất theo đơn vị và người tạo, `run_after` cho vòng nền, số đếm chụp lúc đóng — ràng buộc tổng khớp khi `done`), `core.import_rows` (một dòng của tệp: dữ liệu chỉ giữ khi còn chờ, `attempts` 0–20, `claimed_until` và `claim_id` — vòng nền giữ dòng khi đang làm, vòng đã mất dòng không ghi được, kết quả, mã lỗi khi `failed`; khóa ngoại kèm thuê ước, xóa lô thì xóa theo); chỉ `service` của đơn vị đọc, ghi, không vai trò người dùng nào có quyền; không gắn trigger `core.audit()` — `svc-files` ghi `import.created` cùng mutation tạo lô, trigger `import_jobs_finished` ghi `import.finished` đúng một lần khi lô chuyển sang `done` (hai vòng cùng đóng vẫn một dòng); `core.audit_overview` cho thấy loại lô, định dạng, có vào sổ không, số dòng, không thấy tên tệp | **Xong** — 40 test |
| Phả hệ báo cáo (F3.9, F3.11, migration `1792281602900_report_lineage`): view `office.report_lineage` tính từ catalog PostgreSQL (`pg_depend` của luật view, đệ quy qua view lồng view) khung nhìn báo cáo `office.v_*` đọc bảng, view nào — không khai tay, sửa view là phả hệ đổi theo; chỉ có tên và cạnh, giống nhau cho mọi đơn vị; lãnh đạo đơn vị đọc như dashboard, vai trò khác không thấy | **Xong** — 6 test |
| Kiểm chất lượng số liệu báo cáo (F3.9, F3.11, migration `1792281603300_report_checks`): view `office.report_checks` tính lúc truy vấn 5 luật trên các khung nhìn của trang Điều hành — tổng theo trạng thái khớp số văn bản đến trong bảng, tổng theo phòng khớp số đang xử lý, thời gian xử lý tính đủ văn bản đã xong, khóa ghép số không trùng, không rỗng, không `office.v_*` nào xuất / đọc cột thông tin cá nhân (catalog, `pg_depend` mức cột) — mỗi dòng PASSED / WARNING / FAILED kèm số; lãnh đạo đơn vị đọc kết quả của đơn vị mình (lọc `tenant_id`), vai trò khác không thấy | **Xong** — 7 test |
| Ứng dụng cắm bằng manifest (migration `1792281603200_app_registry`, `moc app install`, [`docs/them-ung-dung.md`](../docs/them-ung-dung.md) mục 1): `core.apps` (ứng dụng đã cài, đã gỡ — `removed_at`; đường, schema duy nhất, không phải schema của lõi), `core.app_migrations` (migration đã áp, SHA-256 nội dung) — cả hai gắn `core.audit()`, không vai trò nào đọc qua GraphQL; luồng sự kiện `core.app_events` — trigger `app_events_publish` trên `office.document_events` chép đúng 5 cột của sự kiện trong danh sách trắng (`office.document.received`, `.registered`, `.issued`) về văn bản không hạn chế; Hasura Event Trigger của từng ứng dụng không nằm trong `db/metadata` mà do `moc app` sinh vào `.moc-apps/hasura-metadata`. Migration của ứng dụng chạy bằng vai trò CSDL riêng `moc_appdb_<schema>` (session user, không superuser, chỉ làm chủ schema của ứng dụng, NOLOGIN ngoài lúc chạy): đọc, ghi, sửa lõi, tạo gì chỗ khác bị chặn; `moc_app.migration_done` (schema `moc_app`) từ chối view, `DEFAULT`, trigger… đọc bảng ngoài schema hay gọi hàm không được phép, rồi mới ghi `core.app_migrations` — sai thì không còn lại gì. Bảng tin (`apps/bang-tin`): người dùng chỉ thấy tin của đơn vị mình, của văn bản mình đọc được; vai trò dịch vụ `app_bang_tin` chỉ thêm dòng | **Xong** — 13 test (44 ca) |
| Tự chẩn đoán H-P-D-I (F4.7, migration `1792281603100_maturity_assessments`, [`docs/tu-chan-doan.md`](../docs/tu-chan-doan.md)): bảng `office.maturity_assessments` (phiên bản bộ câu — ràng buộc `maturity_framework`, câu trả lời `answers` mã câu → mức, điểm `h`, `p`, `d`, `i` — `maturity_scores`, ghi chú ≤ 300 ký tự — `maturity_note`); trigger `maturity_assessments_guard` kiểm `answers` đủ đúng bộ mã câu của phiên bản `hpdi-1` (lỗi `maturity_answers:`), CSDL tự tính bốn điểm, gọt ghi chú, đặt giờ lưu, chặn lưu dồn — mỗi đơn vị 5 lần mỗi giờ, 20 lần mỗi 24 giờ (lỗi `maturity_rate:`); chỉ `director` thêm và đọc trong đơn vị mình (không có cột `created_by`, `tenant_id`), không ai sửa, xóa; gắn sổ kiểm toán | **Xong** — 18 test (`test_maturity.py`) |
| Danh mục ứng dụng (migration `1792281603400_app_catalog`, trang `/ung-dung` của Văn phòng điện tử): view `core.app_catalog` — 9 cột của `core.apps` (tên, tên hiển thị, mô tả lấy từ manifest, đường, phiên bản, lúc cài, lúc cập nhật, lúc gỡ, băm manifest), không có manifest, schema; `core.apps` vẫn không vào GraphQL. Mọi vai trò người dùng đọc ứng dụng đang cài (7 cột); lãnh đạo, quản trị đơn vị đọc thêm băm manifest và ứng dụng đã gỡ; toàn hệ thống, mọi đơn vị cùng một danh sách; không vai trò nào ghi, `service` không đọc | **Xong** — 6 test |
| Bản scan vào chỉ mục toàn văn (#253, migration `1792281603500_file_texts_ocr`): xóa các dòng `core.file_texts` trạng thái `empty` để vòng nền của svc-files đọc lại bản scan, lần này có OCR; chữ OCR ghi `ok` như lớp chữ PDF, `note` = `ocr <số trang đã đọc>/<số trang>`. Không đổi cấu trúc, không đổi quyền; down không khôi phục dòng đã xóa — bản cũ tự đọc lại thành `empty` | **Xong** |

## Vai trò

| Vai trò | Đọc | Ghi trực tiếp (không qua Action) |
|---|---|---|
| `clerk` — văn thư | Mọi văn bản của thuê ước | — (văn bản đến kèm tệp chỉ thêm qua Action `receiveIncoming`: svc-workflow kiểm theo `schemas/van-ban-den.json`); cấp, gỡ người được xem văn bản hạn chế qua hàm |
| `staff` — chuyên viên | Văn bản mình tạo, được giao cho mình, văn bản đi của phòng mình | Thêm dự thảo văn bản đi (kể cả đơn vị nhận trong hệ thống); sửa khi còn `draft`/`returned` và là của mình; gắn và gỡ tệp |
| `manager` — lãnh đạo phòng | Văn bản phòng mình soạn hoặc được giao cho phòng mình | — |
| `director` — lãnh đạo đơn vị | Mọi văn bản của thuê ước | Cấp, gỡ người được xem văn bản hạn chế qua hàm `office.grant_document_access`, `revoke_document_access` |
| `tenant_admin` — quản trị đơn vị | Không đọc văn bản; đọc phòng ban, sổ, danh mục | Thêm, sửa phòng ban |
| `service` — `svc-workflow`, `svc-files` | Mọi dòng của thuê ước trong yêu cầu; dòng liên thông mà thuê ước là bên gửi hoặc bên nhận; không đọc `core.file_signatures` | Trạng thái, số, giao việc, tệp, dòng thời gian, sổ kiểm toán; giao văn bản liên thông qua hàm `office.deliver_dispatch`; thêm chữ ký số của bản phát hành (F4.5) |
| `verifier` — `svc-files` (cổng xác thực) | Chỉ khung nhìn `office.issued_documents` (kể cả năm cột chữ ký số, F4.5), tối đa một dòng mỗi lần | — |
| `agent` — tác tử trong `svc-files`: đọc văn bản đến (F4.1), trợ lý hỏi đáp (F4.2); trong `svc-workflow`: gợi ý giao việc (F4.3) | Chỉ `office.intake_suggestions` và cột `document_id` của `office.assignment_suggestions`, của thuê ước trong yêu cầu | Thêm, sửa gợi ý đọc văn bản; thêm gợi ý giao việc; thêm dòng sổ `intake.suggested` về tệp, `assistant.answered` về câu hỏi, `assignment.suggested` về văn bản (`actor_kind` `agent`). Không đọc, ghi văn bản, không đọc `core.files`, không đọc sổ |
| `tu_dong` — robot của flow Node-RED (#366): client `tu-dong-robot-<mã đơn vị>` (`moc tu-dong robot add`), `x-hasura-user-id` là tên client | Văn bản **không hạn chế** của đơn vị robot: số ký hiệu, trích yếu, độ khẩn, trạng thái, hạn, số và ngày vào sổ, phòng xử lý — không có nội dung, người tạo, người nhận; không đọc bảng nào khác | — (chỉ Action `notifyFromFlow`: báo người của đơn vị theo vai trò, kèm văn bản thì chỉ `director`, `clerk`) — `test_tu_dong.py` |
| `app_<tên>` — phần máy chủ của ứng dụng cắm bằng `moc app install` (client `app-<tên>-svc`, vd `app_bang_tin`) | Chỉ những gì manifest của ứng dụng khai cho vai trò này trên bảng của chính ứng dụng (Bảng tin: không đọc gì) | Bảng tin: thêm dòng `bang_tin.tin`. Không đơn vị trong token, không đọc, ghi gì của lõi |

Văn bản hạn chế (`restricted`) chỉ người tạo và người có tên trong `office.document_acl` đọc được, kể cả
`clerk` và `director`; có tên vẫn phải có quyền theo vai trò ở bảng trên. `svc-workflow` (vai trò `service`) tự thêm
người phải làm các việc đang mở của quy trình (F3.7). Quy tắc đọc viết một lần trong hàm SQL `office.document_visible`, Hasura gắn thành
trường `visible` của `office_documents`; tệp, giao việc, dòng thời gian lọc theo `document.visible`.

Liên thông (F3.12): dòng `office.dispatches` hiện ở bên gửi khi đọc được văn bản đi, ở bên nhận khi đã có văn bản
đến và đọc được nó; quan hệ sang văn bản của bên kia trả null, chỉ có tên đơn vị kia (`to_unit` / `from_unit`).

Góp ý (F4.6): mọi vai trò người dùng gửi được, chỉ ba cột `rating`, `comment`, `screen` — `tenant_id`, `user_id`
Hasura đặt từ token. `clerk`, `staff`, `manager` chỉ đọc góp ý của mình; `director`, `tenant_admin` đọc mọi góp ý
của đơn vị và tổng hợp nhưng không có cột `user_id`; trường `mine` cho mỗi người lọc góp ý của chính mình. Không ai
sửa, xóa; `service`, `agent` không có quyền. Bảng không gắn `core.audit()` — ngoại lệ có chủ ý: dòng sổ ghi người
thực hiện, lãnh đạo đọc sổ của đơn vị qua `overview` sẽ biết ai góp ý gì. Ba view số đo "sau" chỉ `director` đọc
(`v_feedback_summary` thêm `tenant_admin`).

Tự chẩn đoán H-P-D-I (F4.7): chỉ `director` lưu (cột `framework`, `answers`, `note`; `tenant_id`, `created_by`
Hasura đặt từ token) và đọc lịch sử của đơn vị mình; điểm và giờ lưu do CSDL đặt; mỗi đơn vị tối đa 5 lần lưu mỗi
giờ, 20 lần mỗi 24 giờ; không ai sửa, xóa; mỗi lần lưu một dòng sổ kiểm toán.

> ⚠️ **Không bao giờ để vai trò `admin` lọt vào token.** `admin` là vai trò có sẵn của Hasura và bỏ qua
> mọi quyền — đã thử: token có `x-hasura-default-role: admin` đọc được văn bản và sổ kiểm toán của **mọi**
> thuê ước. Quản trị đơn vị là `tenant_admin`; mapper của realm (#21) chỉ đưa 5 vai trò nghiệp vụ vào claim.

### Claim cần có trong token

Keycloak đưa vào claim `https://hasura.io/jwt/claims`:

| Claim | Ghi chú |
|---|---|
| `x-hasura-allowed-roles`, `x-hasura-default-role` | Thuộc tính người dùng `moc_role` (`platform/keycloak/README.md`) |
| `x-hasura-user-id` | `sub` |
| `x-hasura-tenant-id` | UUID của `core.tenants`; thiếu thì không thấy gì |
| `x-hasura-department-id` | UUID của `office.departments`; bắt buộc với `staff`, `manager` — `staff` thiếu claim này không tạo được dự thảo |

Hasura chỉ tin claim trong token: tiêu đề `X-Hasura-Tenant-Id` do trình duyệt gửi bị bỏ qua (có test).

### Dịch vụ gọi Hasura

`svc-workflow`, `svc-files` gửi `X-Hasura-Admin-Secret` kèm `X-Hasura-Role: service`,
`X-Hasura-Tenant-Id` (lấy từ phiên của Action hoặc token người dùng), `X-Hasura-User-Id` (người thực hiện,
ghi vào sổ kiểm toán) và `X-Hasura-Request-Id` (lấy từ `X-Request-Id` do APISIX gắn). Thiếu
`X-Hasura-Tenant-Id` thì yêu cầu bị từ chối — dịch vụ không lỡ tay đọc lẫn thuê ước.

Tác tử đọc văn bản đến (F4.1) cũng nằm trong `svc-files` nhưng gọi bằng `X-Hasura-Role: agent`,
`X-Hasura-Tenant-Id` (đơn vị của văn thư bấm đọc) và `X-Hasura-User-Id` = danh tính tác tử (`moc-doc-reader`); văn
thư bấm đọc ghi trong dữ liệu (`requested_by`, khóa `user_id` của dòng sổ). Thuê ước, danh tính tác tử là cột đặt sẵn
từ phiên, gửi kèm trong dữ liệu thì Hasura từ chối. Gợi ý và dòng sổ đi trong một yêu cầu GraphQL nhiều trường —
Hasura chạy trong một giao dịch, ghi sổ lỗi thì gợi ý cũng không được lưu.

Trợ lý hỏi đáp (F4.2) dùng cùng vai trò `agent` với danh tính `moc-assistant` (`MOC_ASSISTANT_ID`), thuê ước của người
hỏi; chỉ ghi một dòng sổ `assistant.answered` mỗi lượt hỏi, ghi xong mới trả lời. Văn bản người hỏi được xem do
`svc-files` hỏi lại Hasura bằng **token của người hỏi** (hậu kiểm, như tìm kiếm F2.7); vòng chỉ mục đoạn đọc văn bản và
chữ của tệp bằng khóa quản trị.

Tác tử gợi ý giao việc (F4.3) nằm trong `svc-workflow`, cùng vai trò `agent` với danh tính `moc-assigner`
(`MOC_ASSIGNER_ID`), thuê ước của văn bản: chỉ hỏi văn bản đã có gợi ý chưa, rồi lưu gợi ý và dòng sổ
`assignment.suggested` trong một yêu cầu GraphQL nhiều trường (một giao dịch). Văn bản, lịch sử giao việc, danh bạ đọc
bằng vai trò `service` sẵn có. Lãnh đạo đọc gợi ý bằng token của mình; căn cứ chỉ có id, giao diện hỏi lại số ký hiệu,
trích yếu bằng token người xem.

Nạp lô văn bản đến (`svc-files` `/api/imports`, migration 1792281602800): lô, dòng và dòng sổ `import.created` ghi bằng
vai trò `service` với thuê ước, người dùng lấy từ token của văn thư đã kiểm lúc tạo lô; không vai trò người dùng nào có
quyền trên `core.import_jobs`, `core.import_rows`. Vòng nền tìm lô đến giờ của mọi đơn vị bằng khóa quản trị không kèm
vai trò (chỉ đọc). Mỗi dòng được ghi bằng đúng Action `receiveIncoming` (và `registerIncoming` khi lô có vào sổ) với
**phiên của văn thư tạo lô**: khóa quản trị kèm `X-Hasura-Role: clerk`, `X-Hasura-Tenant-Id`, `X-Hasura-User-Id`,
`X-Hasura-Department-Id` lấy từ token đã kiểm lúc tạo lô, không từ dữ liệu của lô. Hasura áp quyền gọi Action của vai
trò `clerk` như khi văn thư tự gửi; đầu mỗi mẻ `svc-files` kiểm lại danh bạ, văn thư bị khóa hay đổi vai trò thì dòng
còn chờ dừng (`actor_revoked`). Dòng kết thúc mà không thành văn bản thì `svc-files` gỡ các tệp đã lưu cho dòng bằng
khóa quản trị không kèm vai trò, `X-Hasura-User-Id: svc-files:import` (vai trò `service` không có quyền xóa
`core.files`): câu xóa chỉ nhận tệp của người tạo lô trong đơn vị, chưa gắn văn bản nào (khóa ngoại của
`office.document_files` cũng chặn), tệp đã đặt vào không gian cá nhân thì giữ; sổ kiểm toán có dòng `delete core.files`
với mã yêu cầu `<lô>:<dòng>`.

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
- **Sao lưu, khôi phục** (`make backup`, `make restore`, F3.4; `scripts/backup.py`). Lúc sao lưu, `svc-files` (chỗ
  ghi mốc neo) tạm dừng từ trước khi dump CSDL tới khi chép xong bucket, nên mốc trong bucket và bảng
  `core.audit_anchors` cùng một thời điểm: khôi phục xong `make audit` vẫn khớp. Lần khôi phục thêm một dòng
  `system.restored` của nền tảng (`tenant_id` null, `entity_id` là mã lượt, `diff` có đầu chuỗi lúc sao lưu) ngay
  sau đầu chuỗi vừa khôi phục: các dòng ghi sau lúc sao lưu không còn là vì khôi phục, và sổ ghi rõ điều đó. Lượt
  sao lưu trọn vẹn ghi dòng `system.backed_up` cùng dạng (sau lúc dump), để trang trạng thái hệ thống biết giờ sao
  lưu gần nhất.
- **Màn xem sổ** cho `director`, `tenant_admin`: đọc dòng sổ của đơn vị mình, không đọc được cột `diff`, chỉ đọc
  trường `overview` (hàm `office.audit_overview_seen`, dựa trên `core.audit_overview`): cột chứa nội dung (trích
  yếu, nội dung, tên tệp, ý kiến…) có tên nhưng giá trị null; dòng về văn bản hạn chế mà người xem không đọc được
  thì mọi cột đều null, để sổ không lộ văn bản đó (F3.7). Dòng danh sách được xem (`office.document_acl`: người
  được cấp nằm ở `entity_id`, người cấp ở `actor_id`) của văn bản đó thì không hiện cả dòng — bộ lọc quyền `visible`
  (`office.audit_log_visible`, migration 1792281602400), không dòng sổ nào bị sửa.

## Thêm hoặc đổi schema

1. Tạo thư mục mới `migrations/default/<mili giây hiện tại>_<tên>/` với `up.sql` và `down.sql`
   (`date +%s%3N` cho số phiên bản). **Không sửa migration đã merge** — viết migration mới.
2. Bảng mới: thêm tệp `metadata/databases/default/tables/<schema>_<bảng>.yaml` và một dòng trong
   `tables.yaml`. Bảng nghiệp vụ có `tenant_id` thì mọi quyền đều lọc `tenant_id = X-Hasura-Tenant-Id`, và
   gắn `core.audit()` (không gắn thì ghi lý do trong migration, như `office.feedback`).
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
