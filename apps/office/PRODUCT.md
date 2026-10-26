# Văn phòng điện tử — người dùng và yêu cầu giao diện

Tài liệu đầu vào cho mọi thay đổi giao diện của `apps/office`. Quyết định thiết kế cụ thể nằm ở `DESIGN.md`.

## Người dùng

- **Chuyên viên xử lý văn bản** (nhóm chính): mở hộp việc, đọc văn bản, làm một việc (xử lý, báo cáo kết quả, soạn
  văn bản đi) rồi sang việc sau. Ngồi máy tính văn phòng cả ngày, màn 1280–1440px, dùng chuột lẫn bàn phím.
- **Văn thư**: tiếp nhận văn bản đến (tải tệp, đọc tự động, vào sổ), cấp số và phát hành văn bản đi.
- **Lãnh đạo**: chỉ đạo, phân công, duyệt, xem điều hành; hay xem nhanh trên điện thoại (390px).

## Việc chính: quét, đọc, làm

1. **Quét**: hộp việc cho thấy ngay việc nào khẩn, quá hạn, sắp đến hạn; mỗi việc đọc được trong một lần lướt mắt
   (trích yếu, số ký hiệu, nơi gửi, bước cần làm, hạn).
2. **Đọc**: trang văn bản đặt việc đang chờ người dùng lên trước, thông tin văn bản ở cột bên để tra mà không rời
   khung việc.
3. **Làm**: khung xử lý, chỉ đạo, phân công, trình ký là phần nổi nhất trang; làm xong quay về hộp việc.

## Yêu cầu giao diện (Nam, 26/10/2026)

- Sáng, hơi cổ điển nhưng hiện đại; được tự chọn phối màu (không bắt buộc giữ vàng bơ). Tương phản rõ, đạt WCAG 2.2
  AA.
- Chữ không chân dễ đọc, phân cấp rõ; bố cục đơn giản, thoáng vừa, việc đang làm đặt trước; bo góc nhẹ.
- Thanh bên trái liền mép, thu gọn được, mở khi rê chuột; dùng được bằng bàn phím và trên điện thoại.
- Chuyển động mượt, tắt khi người dùng chọn giảm chuyển động.
- Giữ logo chữ S Liền mạch của Signet.
- Tránh: lưới thẻ rải khắp trang, nhiều cỡ chữ lẫn lộn, nền nhạt không có điểm nhìn, chỉ đổi màu cho có.

## Ràng buộc

- Không thêm chức năng, không dữ liệu giả; giữ API, hợp đồng GraphQL, quyền, `data-testid` và selector e2e.
- Mọi chữ qua i18n (vi, en). Phông, icon, thư viện mới phải có giấy phép OSI, tự phục vụ, khai trong
  `DEPENDENCIES.md`.
- Trang đăng nhập là theme Keycloak `signet` (`platform/keycloak/themes/signet`): chỉ đổi CSS, logo, phông.
