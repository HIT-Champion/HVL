# Butter — bàn giao local ngày 23/10/2026

Phương án Butter được anh chọn sau reroll. Đã áp dụng vào ứng dụng Nuxt JavaScript thật
ở http://localhost:8080, trên nhánh `feat/fe-local-acceptance`. Chưa push GitHub.
Việc chọn phương án không thay cho nghiệm thu thẩm mỹ của bản triển khai.

## Thay đổi

- Sidebar trái thu/mở, lưu lựa chọn; menu điện thoại giữ focus, Escape đóng và trả focus.
- Nền giấy sáng, butter và olive; chữ công việc sans, Lora chỉ cho thương hiệu.
- Control bo 8px, panel 12px; chuyển động sidebar 260ms, hover/ngữ cảnh ngắn, hỗ trợ reduced motion.
- Hộp việc chia “Cần chú ý” cho việc khẩn/quá hạn và phần còn lại. Mỗi việc xuất hiện một lần;
  cả hàng mở thẳng văn bản. Giữ lọc, tìm không dấu, trạng thái rỗng/lỗi và realtime.
- Đồng bộ các màn danh sách, form, hồ sơ, biểu đồ, đăng nhập và favicon.
- Hồ sơ có trạng thái chọn rõ; biểu đồ trạng thái dùng thanh ngang để nhãn đọc được trên điện thoại.

## Áp dụng skill và kiểm chứng

Taste dùng nhánh app screens để kiểm mật độ chữ, kiểu chữ, màu và responsive.
Impeccable dùng quy trình reroll có prototype tương tác, chốt Butter rồi triển khai code,
kiểm motion, accessibility và ghi lại hệ thiết kế trong `DESIGN.md`, `.impeccable/design.json`
và surface brief. Không xem việc chạy công cụ là bằng chứng giao diện đã đẹp.

- Compiler: 41 tệp JavaScript/Vue hợp lệ; kiểm form 55/55.
- Bộ E2E đầy đủ trước hai sửa cuối: 11/11 qua trên backend local thật.
- Sau sửa hồ sơ/biểu đồ: 5/5 E2E liên quan qua (responsive, sidebar, hồ sơ, điều hành, thử lại form).
- 23 ảnh route/kích thước; kiểm mở văn bản trực tiếp, xóa lọc và focus mobile qua.
- Sidebar thu còn 76px, nhớ sau reload; reduced motion và focus menu qua, không lỗi console trong lượt đo motion.
- Tương phản mẫu: chữ sidebar 10.67:1, chữ việc chú ý 11.02:1, nút chính 7.11:1;
  viền input 3.51:1 trên trắng. Đây là phép đo các mẫu, không tuyên bố audit WCAG toàn bộ.
- Taste inspector có session ứng dụng: 0 FAIL, 0 WARN; chỉ ngoại lệ `palette-cream`
  theo yêu cầu vintage. Đã xem ảnh thực tế desktop/tablet/mobile, hồ sơ và biểu đồ sau sửa.

Reviewer độc lập phát hiện hai lỗi hồ sơ/nhãn biểu đồ nêu trên trước khi hết hạn mức.
Hai vai reviewer/documenter sau đó không chạy tiếp được do hạn mức; agent chính hoàn tất
rà lại các sửa đã biết và tài liệu theo degraded playbook. Không có verdict độc lập cuối.

Ảnh local tại `.impeccable/review-v3/butter-live/`; báo cáo Taste tại
`apps/office/.taste-skill/butter-final/`. Log tại `.cache/butter-finish-retest.log`,
`.cache/butter-finish-recapture.log`, `.cache/butter-motion-final.log`, `.cache/butter-taste.log`.
Các bằng chứng này bị bỏ qua Git; không kèm token hay mật khẩu trong tài liệu bàn giao.

## Giới hạn

Chưa có backend từ xa; các luồng dùng stack Docker local. Smoke toàn repo trên Windows
vẫn có giới hạn module Linux `fcntl` như báo cáo trước. Danh sách tải tối đa 200 mục theo
quyền API, không phải tổng toàn cơ sở dữ liệu. Các báo cáo v1/v2/v3 là lịch sử.

Tài khoản chuyên viên: `chuyenviendt`; mật khẩu lấy từ `.env` local.
Xem `fe-nghiem-thu-local.md` để chạy lại và thử các luồng nghiệp vụ.
