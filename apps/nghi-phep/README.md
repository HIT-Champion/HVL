# app-nghi-phep — Đơn nghỉ phép

Ứng dụng thứ tư trên lõi Signet (#301), cắm vào bằng **một lệnh** và không sửa tệp nào của lõi:

```bash
python3 scripts/moc.py app install apps/nghi-phep/app.yaml      # make app-install APP=apps/nghi-phep/app.yaml
python3 scripts/moc.py app remove nghi-phep                     # gỡ: trang, client, container; lịch sử đơn còn
```

Nhân viên gửi đơn nghỉ phép; trưởng phòng **của chính phòng người gửi** duyệt hoặc từ chối kèm ghi chú; người gửi
theo dõi kết quả. Khác Bảng tin, ứng dụng này không có máy chủ nghiệp vụ, không có bảng riêng: quy trình (BPMN) và mẫu
đơn (JSON Schema) khai ở mục `workflow` của manifest. Lúc cài, lõi kiểm hai thứ đó rồi triển khai lên động cơ quy trình
của nó (Flowable sau `svc-workflow`). Trang gọi API chung của lõi bằng token của người dùng. Lõi kiểm lại form, quyết
định ai thấy việc nào và giữ đơn. Cơ chế, mô hình tin cậy: [`docs/them-ung-dung.md`](../../docs/them-ung-dung.md).

| Tệp | Nội dung |
|---|---|
| `app.yaml` | Manifest: đường `/nghi-phep`, image dựng từ thư mục này, 64 MiB; `database` chỉ vì manifest bắt buộc (schema trống `nghi_phep`, không migration); `workflow`: một quy trình, hai form |
| `workflow/don-nghi-phep.bpmn20.xml` | Quy trình `nghi-phep.don`: gửi đơn (`nghi-phep.don`) → "Trưởng phòng duyệt" (`nghi-phep.duyet`, nhóm `t:${tenantId}:d:${departmentId}:manager` như bước duyệt cấp phòng của văn bản đi) → cổng rẽ theo `quyetDinh` → "Đã duyệt" / "Bị từ chối". Chỉ sự kiện, việc người làm, cổng rẽ: không có mã chạy trên máy chủ; có sơ đồ BPMN DI |
| `forms/don.json`, `forms/duyet.json` | Mẫu đơn (loại nghỉ, từ ngày, đến ngày, lý do) và mẫu duyệt (quyết định, ghi chú); ca thử dùng chung `*.cases.json` |
| `server.py` | Python thư viện chuẩn, không root, hệ tệp gốc chỉ đọc: chỉ trang tĩnh ở `:8080` (CSP `script-src 'self'`, nhật ký không ghi chuỗi truy vấn), `config.json`, `healthz`. Không bí mật, không client dịch vụ |
| `public/` | Trang duy nhất: `auth.js` đăng nhập Authorization Code + PKCE (oidc-client-ts, `response_mode=fragment`, client `app-nghi-phep`); `schema-form.js` dựng form từ JSON Schema; `don.js` đường API, đọc câu trả lời, trạng thái đơn — phần không đụng trình duyệt; `app.js` vẽ ba phần; `i18n.js` bảng dịch vi/en (#398; ngôn ngữ lưu chung khóa `moc.locale` với Văn phòng điện tử) |
| `Dockerfile` | `node:24.20.0-slim` lấy bản cho trình duyệt của oidc-client-ts theo `package-lock.json`; `python:3.13.16-slim` ghim digest, user 10001 |
| `tests/` | `node --test tests/*.test.js` (form dựng từ schema; `don.js`; khớp app.yaml ↔ BPMN ↔ form; tương phản màu; bảng dịch vi/en, không chữ tiếng Việt viết cứng trong `public/*.js`); `python3 -m unittest discover -s tests` (máy chủ thật trên cổng ngẫu nhiên; BPMN chỉ dùng phần tử được phép, nhóm duyệt, mọi nút tới được kết thúc) |

## Trang

Ba phần, chuyển bằng thanh trên cùng (tiêu điểm về tiêu đề phần vừa mở):

- **Gửi đơn** — form dựng từ `forms/don.json` lấy qua API của lõi; kiểm ngay trên trình duyệt bằng chính tệp đó
  (vd đến ngày trước từ ngày), lõi kiểm lại khi nhận. Lỗi `422` của lõi hiện dưới đúng ô, tiêu điểm về ô sai đầu
  tiên.
- **Đơn của tôi** — mỗi đơn một thẻ: trạng thái (chờ trưởng phòng duyệt, đã duyệt, bị từ chối), nội dung đơn, số
  ngày nghỉ, quyết định và ghi chú của trưởng phòng.
- **Việc cần duyệt** — chỉ hiện khi có việc: đơn của nhân viên trong phòng, form quyết định từ `forms/duyet.json`.
  Danh sách tự làm mới mỗi 30 giây mà không xóa ghi chú đang gõ.

Trợ năng: mọi ô có nhãn; lỗi gắn vào ô bằng `aria-describedby`, `aria-invalid`; báo kết quả qua vùng `role="status"`,
lỗi chung qua `role="alert"`; liên kết bỏ qua tới nội dung; nút cao tối thiểu 44 px; màu chữ trên nền đạt tỉ lệ
4,5:1 (test đo).

Ngôn ngữ: tiếng Việt mặc định; nút "English" ở thanh trên đổi cả trang sang tiếng Anh, kể cả nhãn, lựa chọn, câu báo
lỗi của form (nhãn lấy từ `x-moc-ui` `{vi, en}` của tệp form, câu chung từ `public/i18n.js`). Lựa chọn lưu chung khóa
`moc.locale` với Văn phòng điện tử, Bảng tin, Không gian cá nhân; đổi lúc đang gõ thì form vẽ lại, chữ đã gõ còn
nguyên. Ngày giờ vẫn viết dd/mm/yyyy theo giờ Việt Nam.

## API chung của lõi mà trang gọi

Qua cổng, token phải có `azp` = `app-nghi-phep` (token của client khác: `403`):

| Gọi | Để |
|---|---|
| `GET /api/workflow/nghi-phep/forms/{formKey}` | Lấy JSON Schema của form |
| `POST /api/workflow/nghi-phep/processes/nghi-phep.don` `{"data": {...}}` | Gửi đơn → `201 {"id"}` |
| `GET /api/workflow/nghi-phep/processes` | Đơn của tôi |
| `GET /api/workflow/nghi-phep/tasks` | Việc cần duyệt của tôi |
| `POST /api/workflow/nghi-phep/tasks/{taskId}` `{"data": {...}}` | Duyệt → `204` |

Dữ liệu sai: `422 {"errors": {"trường": "mã"}}`, mã như `schemas/README.md` cộng `x-moc-range`.

## Kiểm

`make test` chạy hai bộ test trên. Cả luồng trên hệ thống đang chạy: `make demo-quy-trinh` — BPMN có `scriptTask`
bị từ chối lúc cài; nhân viên `giangvienktpm` gửi đơn (dữ liệu sai → `422` đúng mã); trưởng Bộ môn KTPM
`truongbmktpm` (cùng phòng) thấy và duyệt, tổ trưởng Đào tạo `totruongdt` (phòng khác) không thấy; token của
`app-office`, `moc-cli` bị từ chối; hộp việc Văn phòng điện tử không lẫn việc nghỉ phép; cài lại không đổi gì; gỡ giữ
lịch sử đơn.
