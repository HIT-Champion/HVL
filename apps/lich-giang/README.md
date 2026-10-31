# app-lich-giang — Đổi, bù lịch giảng

Ứng dụng ngành (Tầng 3) cho trường đại học trên lõi Signet. Ứng dụng cắm vào bằng **một lệnh** và không sửa tệp nào
của lõi:

```bash
python3 scripts/moc.py app install apps/lich-giang/app.yaml      # make app-install APP=apps/lich-giang/app.yaml
python3 scripts/moc.py app remove lich-giang                     # gỡ: trang, client, container; lịch sử đề nghị còn
```

Giảng viên đề nghị **đổi lịch** (dời một buổi dạy sang ngày khác) hoặc **dạy bù** (bù buổi đã nghỉ). Đề nghị đi qua
hai cấp duyệt:

1. **Trưởng bộ môn của chính bộ môn người gửi** duyệt.
2. Nếu bộ môn đồng ý, **lãnh đạo khoa** phê duyệt. Nếu bộ môn không đồng ý, đề nghị dừng ở đó.

Người gửi theo dõi kết quả và đọc ghi chú của từng cấp.

Ứng dụng dựng theo khuôn Đơn nghỉ phép ([`apps/nghi-phep`](../nghi-phep/README.md)):
- Không có máy chủ nghiệp vụ, không có bảng riêng. Quy trình (BPMN) và mẫu (JSON Schema) khai ở mục `workflow` của
  manifest.
- Lúc cài, lõi kiểm hai thứ đó rồi triển khai lên động cơ quy trình của nó (Flowable sau `svc-workflow`).
- Trang gọi API chung của lõi bằng token của người dùng.
- Lõi kiểm lại form, quyết định ai thấy việc nào và giữ đề nghị.

Khác Đơn nghỉ phép ở hai chỗ: hai cấp duyệt nối nhau qua cổng rẽ, và cấp thứ hai giao theo vai trò của cả đơn vị chứ
không theo bộ môn.

Cơ chế và mô hình tin cậy: [`docs/them-ung-dung.md`](../../docs/them-ung-dung.md).

| Tệp | Nội dung |
|---|---|
| `app.yaml` | Manifest: đường `/lich-giang`, image dựng từ thư mục này, 64 MiB; `database` chỉ vì manifest bắt buộc (schema trống `lich_giang`, không migration); `workflow`: một quy trình, ba form |
| `workflow/doi-lich-giang.bpmn20.xml` | Quy trình `lich-giang.don`: gửi đề nghị (`lich-giang.don`) → "Trưởng bộ môn duyệt" (`lich-giang.bo-mon`, nhóm `t:${tenantId}:d:${departmentId}:manager` như bước duyệt cấp phòng của văn bản đi) → cổng rẽ theo `quyetDinhBoMon` → "Lãnh đạo khoa phê duyệt" (`lich-giang.khoa`, nhóm `t:${tenantId}:director` như bước chỉ đạo của văn bản đến) → cổng rẽ theo `quyetDinhKhoa` → "Đã duyệt" / "Khoa không duyệt"; bộ môn không đồng ý → "Bộ môn không đồng ý". Không có mã chạy trên máy chủ; có sơ đồ BPMN DI |
| `forms/don.json` | Mẫu đề nghị: loại (đổi lịch, dạy bù), học phần, lớp học phần, ngày và tiết theo lịch, ngày dạy mới (không trước hôm nay), tiết mới, phòng học, lý do |
| `forms/bo-mon.json`, `forms/khoa.json` | Mẫu duyệt của từng cấp (quyết định, ghi chú); tên trường riêng cho từng cấp nên kết quả bộ môn còn nguyên khi khoa duyệt |
| `forms/*.cases.json` | Ca thử dùng chung cho trình duyệt và `svc-workflow` |
| `server.py`, `Dockerfile`, `public/auth.js`, `public/schema-form.js`, `public/style.css` | Như `apps/nghi-phep`: trang tĩnh Python thư viện chuẩn, không root; đăng nhập PKCE bằng client `app-lich-giang`; form dựng từ JSON Schema |
| `public/don.js`, `public/app.js`, `public/i18n.js` | Đường API, trạng thái đề nghị qua hai cấp (phần không đụng trình duyệt); vẽ ba phần; bảng dịch vi/en |
| `tests/` | `node --test tests/*.test.js` (form dựng từ schema; `don.js`; khớp app.yaml ↔ BPMN ↔ form; bảng dịch vi/en); `python3 -m unittest discover -s tests` (máy chủ thật trên cổng ngẫu nhiên; BPMN chỉ dùng phần tử được phép, đúng nhóm từng cấp, mọi nút tới được kết thúc) |

## Trang

Ba phần, chuyển bằng thanh trên cùng:

- **Gửi đề nghị**: form dựng từ `forms/don.json` lấy qua API của lõi. Trình duyệt kiểm ngay bằng chính tệp đó (vd
  ngày dạy mới đã qua, tiết viết sai dạng), lõi kiểm lại khi nhận. Lỗi `422` của lõi hiện dưới đúng ô.
- **Đề nghị của tôi**: mỗi đề nghị một thẻ, gồm trạng thái, nội dung và quyết định, ghi chú của từng cấp đã duyệt.
  Trạng thái là một trong: chờ trưởng bộ môn, bộ môn đã đồng ý chờ khoa, đã duyệt, bộ môn không đồng ý, khoa không
  duyệt.
- **Việc cần duyệt**: chỉ hiện khi có việc. Trưởng bộ môn thấy đề nghị của giảng viên trong bộ môn. Lãnh đạo khoa
  thấy đề nghị bộ môn đã đồng ý, kèm ý kiến của trưởng bộ môn. Danh sách tự làm mới mỗi 30 giây mà không xóa ghi chú
  đang gõ.

Trợ năng, ngôn ngữ (vi/en, lưu chung khóa `moc.locale`) và màu như Đơn nghỉ phép.

## API chung của lõi mà trang gọi

Qua cổng, token phải có `azp` = `app-lich-giang` (token của client khác: `403`):

| Gọi | Để |
|---|---|
| `GET /api/workflow/lich-giang/forms/{formKey}` | Lấy JSON Schema của form |
| `POST /api/workflow/lich-giang/processes/lich-giang.don` `{"data": {...}}` | Gửi đề nghị → `201 {"id"}` |
| `GET /api/workflow/lich-giang/processes` | Đề nghị của tôi |
| `GET /api/workflow/lich-giang/tasks` | Việc cần duyệt của tôi |
| `POST /api/workflow/lich-giang/tasks/{taskId}` `{"data": {...}}` | Duyệt → `204` |

Dữ liệu sai trả `422 {"errors": {"trường": "mã"}}`, với mã như `schemas/README.md`.

## Kịch bản với tài khoản mẫu

Tài khoản trong `seed/users.csv`, đơn vị Khoa CNTT:

1. `giangvienktpm` (giảng viên Bộ môn KTPM) gửi đề nghị dạy bù.
2. `truongbmktpm` (trưởng Bộ môn KTPM) thấy việc và đồng ý. `totruongdt` thuộc phòng khác nên không thấy.
3. `truongkhoa` (lãnh đạo khoa) thấy đề nghị kèm ý kiến bộ môn, rồi phê duyệt.
4. `giangvienktpm` thấy "Đã duyệt" cùng ghi chú của cả hai cấp.

## Kiểm

`make test` chạy hai bộ test trên. Lõi tự kiểm BPMN và form lúc cài (danh sách trắng, `svc_workflow/apps`). Ca thử
`forms/*.cases.json` cũng chạy trong `services/svc-workflow/tests/test_app_forms.py`.
