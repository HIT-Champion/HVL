# FE Butter — kết nối BE và AI

Nhánh: `feat/fe-butter-ai-integration`. Nền: `origin/develop` tại
`544a6ab084ca6e5970ff5558bed8bed14f21c4f2` (fetch ngày 23/10/2026).
Đây là mã BE/AI đã tích hợp trên develop; không ghép thêm các nhánh thử nghiệm đang mở.
FE Butter lấy từ checkpoint local `c354d31`. Không merge hoặc sửa các nhánh cũ.

## Phạm vi

Chỉ thay đổi frontend, kiểm thử frontend và tài liệu. Code dưới `services/`, `db/`,
`schemas/`, `platform/` và `docker-compose.yml` được giữ đúng nền upstream.

FE tiếp tục dùng JavaScript. Giữ hợp đồng API mới nhất và chuyển logic TypeScript FE
sang JavaScript, bao gồm runtime props/emits của Vue. Giữ UI Butter, sidebar thu/mở,
responsive, retry và xử lý phản hồi cũ. Nối các chức năng:

- Đọc tệp sạch để gợi ý ô tiếp nhận, không ghi đè ô người dùng đang sửa.
- Hỏi đáp theo quyền, nguồn trích dẫn và pha sinh câu trả lời khi mô hình sẵn sàng.
- Gợi ý phòng chủ trì/hạn xử lý; người dùng xác nhận mới gửi nghiệp vụ.
- Liên thông văn bản, văn bản hạn chế và khối thông tin chữ ký minh họa.

## Mốc Git

Theo yêu cầu chủ nhánh, author date và committer date của các commit FE được dựng lại
trên dải 01–23/10/2026, giờ Việt Nam (+07:00), mỗi ngày một giờ khác nhau.
Đây là thời gian do người dùng chỉ định cho lịch sử dựng lại, không phải nhật ký thời điểm
triển khai thực tế. Nền upstream có commit ngày 23/10; lịch sử Git vì thế có thể có commit con
mang ngày sớm hơn commit cha. Không sửa lại ngày hoặc tác giả của commit BE/AI.

## Chạy local

Sử dụng `.env` local hiện có (không commit). Dựng từ thư mục nhánh mới:

```powershell
docker compose --profile core --profile app up -d --build
```

Theme đăng nhập nằm trong `apps/office/keycloak-theme`. Khi chạy local có thể mount thư mục
này vào `/opt/keycloak/themes` qua compose override (ignored), không sửa cấu hình BE upstream.
Mô hình Ollama là tùy chọn theo upstream; đọc/trích xuất theo luật vẫn hoạt động khi chưa có mô hình.

## Kiểm chứng trên stack local

- Build production và các dịch vụ core/app khởi động thành công; dữ liệu cũ được giữ.
- Compiler: 51 tệp JS/Vue hợp lệ. Unit FE: 118/118, gồm API archive cùng API đọc/hỏi đáp.
- Bộ E2E đầy đủ đầu tiên: 16/18 qua. Hai lỗi FE đã sửa: thiếu test id chữ đại diện và
  thiếu nút Soạn mới trong màn đang sửa dự thảo. Sau sửa, 3 ca responsive và ca giám khảo qua.
- Luồng văn bản đi sau sửa đã qua soạn, trả lại/sửa, duyệt, phát hành và so PDF đúng byte;
  kiểm bắt buộc PAdES dừng vì két local cũ không có PKI. Kiểm nhánh unsigned chạy riêng
  với `MOC_E2E_EXPECT_SIGNED=false`: 1/1 qua, bao gồm cả tệp bị sửa không khớp SHA-256.
  Kết quả ghi ở log `integration-unsigned-retest.log`.
- Các ca đọc lớp chữ PDF/gợi ý ô, hỏi đáp có nguồn/theo quyền, gợi ý giao việc, văn bản hạn chế,
  liên thông hai khoa, sổ PDF, audit, quản trị và realtime đã qua trên backend thật.
- 25 ảnh route/kích thước: không lỗi JavaScript hoặc tràn trang; đã xem ảnh hỏi đáp, tiếp nhận và mobile.
- REUSE 5.0.2: 514/514 tệp có thông tin bản quyền và giấy phép; font Lora khai riêng OFL-1.1.

Bằng chứng local (không commit): `.cache/integration-e2e.log`, `.cache/integration-retest.log`,
`.cache/integration-unsigned-retest.log`, `.cache/fe-unit-final.log`, `.cache/fe-check.log`,
`.cache/integration-visual.log`, `.cache/reuse-lint.log`; ảnh tại `.impeccable/review-v3/butter-live/`.

## Giới hạn được giữ rõ

Két local được tạo trước F4.5 nên chưa có PKI. Theo `platform/openbao/start.sh` và tài liệu vận hành,
PKI không tự được thêm vào két cũ sau khi token bootstrap quản trị đã bị thu hồi. Không reset két,
đổi policy, sửa BE hay giả thông tin chữ ký để vượt test. Cổng xác thực hiển thị đúng “không có chữ ký số”.
Test E2E mặc định vẫn yêu cầu PAdES; chỉ profile local được chọn rõ mới kiểm nhánh unsigned.

Chưa bật/tải mô hình Ollama. API đọc PDF theo luật, truy hồi từ khóa có trích nguồn và gợi ý giao việc
đã chạy thật; nhánh sinh câu trả lời và tìm theo embedding phụ thuộc mô hình, chưa được nghiệm thu ở máy này.
Không coi các nhánh tùy chọn chưa chạy này là pass.

Để kiểm nhánh phát hành unsigned trên két cũ bằng PowerShell:

```powershell
$env:MOC_E2E_EXPECT_SIGNED='false'
node tests/e2e/run-local.mjs van-ban-di.spec.ts
```

Để yêu cầu PAdES, bỏ biến trên hoặc đặt `true`; cần một hệ thống đã được quản trị viên dựng PKI theo BE.
