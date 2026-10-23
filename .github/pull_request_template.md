<!--
PR tính năng, sửa lỗi, tài liệu: nhánh đích là develop. Tiêu đề theo Conventional Commits, ví dụ:
  feat(workflow): thêm bước giám đốc duyệt khi số tiền vượt ngưỡng
Khi gộp bằng "Squash and merge", tiêu đề này trở thành commit trên develop; CI kiểm tiêu đề.
PR phát hành (develop → main): tiêu đề đúng "chore(release): vX.Y.Z". Xem docs/git_flow.md mục 6.
-->

## Nội dung thay đổi

<!-- Mô tả ngắn gọn thay đổi này làm gì và VÌ SAO cần thiết. -->

Closes #

## Mảng và thành phần

- [ ] Backend
- [ ] AI
- [ ] Frontend
- [ ] Hạ tầng / CI / tài liệu chung

<!-- Thành phần chính (phạm vi commit): gateway · auth · db · workflow · files · realtime · office · ai · data · ops · cli · scripts · e2e · ci · deps · docs · release -->

## Danh mục kiểm tra

- [ ] Tiêu đề PR theo Conventional Commits; mô tả có `Closes #<số-issue>`
- [ ] *(Thành viên đội)* Đã gắn nhãn mảng và milestone của phase hiện tại
- [ ] `make license-check` chạy sạch, không có CẢNH BÁO loại tệp chưa hỗ trợ
- [ ] `make check` chạy sạch — cấu hình Compose hợp lệ
- [ ] Đã thêm hoặc cập nhật test cho phần thay đổi (nếu có thể kiểm thử)
- [ ] Tài liệu của tính năng được cập nhật **trong chính PR này**
- [ ] Tham số cấu hình mới (nếu có) đã được khai báo trong `.env.example` kèm chú thích
- [ ] `CHANGELOG.md` mục `[Chưa phát hành]` đã được cập nhật (với thay đổi người dùng thấy được)
- [ ] Phần mềm thượng nguồn mới (nếu có) đã được ghi vào `DEPENDENCIES.md` kèm giấy phép OSI
- [ ] Không fork-sửa và không bundle mã nguồn của dự án thượng nguồn nào
- [ ] Không có bí mật, `.env`, dữ liệu thật, trọng số mô hình trong thay đổi

## Cách kiểm chứng

<!-- Các bước để người review tự chạy và xác nhận thay đổi hoạt động. -->
