# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Ưu tiên chuyên viên xử lý văn bản trong công việc hằng ngày, do người dùng xác nhận ngày 23/10/2026.
Các vai trò văn thư, lãnh đạo phòng, lãnh đạo đơn vị và quản trị đơn vị vẫn giữ chức năng theo quyền backend.

## Product Purpose

Signet là văn phòng điện tử: tiếp nhận, vào sổ, chỉ đạo, phân công, xử lý văn bản đến;
soạn, trình, duyệt, phát hành văn bản đi; tra cứu và tập hợp hồ sơ công việc.
Chuyên viên cần nhận biết nhiệm vụ của mình, đọc đúng văn bản và hoàn thành đúng bước.

## Operating Context

Nuxt 4 JavaScript SPA, tiếng Việt và tiếng Anh. Stack Docker local sau APISIX ở cổng 8080;
Keycloak SSO/OTP; API GraphQL và REST; thông báo Centrifugo ở bản production.
Các luồng chi tiết được đối chiếu trong docs/so-do-nghiep-vu-fe.md.

## Capabilities and Constraints

Giữ nguyên hợp đồng API, quyền, trạng thái, nội dung và các luồng đã chạy.
Không push GitHub. Giao diện desktop, tablet và mobile đều sử dụng được.
Số đếm lấy từ dữ liệu thật; không thêm hồ sơ, KPI hay năng lực AI không có trong backend.

## Brand Commitments

Tên Signet, tiếng Việt tự nhiên. Người dùng muốn vintage vừa đủ nhưng hiện đại hơn,
bố cục có chủ đích và tránh AI-slop; đã giao quyền chọn hướng thiết kế cho trợ lý.
Áp dụng đồng thời Taste Skill và Impeccable. Bản giấy ngà, serif lớn và sidebar cũ
là phản ví dụ người dùng đã từ chối, không phải chuẩn thị giác phải bảo tồn.

Cập nhật yêu cầu trực tiếp ngày 23/10/2026: sidebar nằm bên trái và có thể thu/mở;
bảng màu vintage nhưng sáng, hiện đại; bố cục đơn giản; component bo nhẹ, mềm mại.
Motion phục vụ thao tác thu/mở, lựa chọn và phản hồi, có phương án giảm chuyển động.
Yêu cầu sidebar mới thay thế mọi suy diễn rằng người dùng không muốn sidebar.
Ba phương án tĩnh, cạnh vuông và thanh màu rượu vang đậm ở vòng trước đã bị yêu cầu reroll.

Người dùng đã chọn **Butter** trong vòng reroll: sidebar vàng bơ sáng, nền trắng ấm,
hành động olive đậm, vùng công việc cần chú ý phía trên và danh sách còn lại phía dưới.
Đây là hướng được chọn để triển khai vào ứng dụng thật, không chỉ là một bản thử màu.

## Evidence on Hand

Mã nguồn và API local thật, dữ liệu demo theo vai trò; luồng đến/đi, PDF/QR,
dashboard, kiểm toán, realtime, hồ sơ và nộp lưu đã có kiểm thử.
Ảnh bản cũ trong apps/office/.taste-skill và .cache/acceptance.

## Product Principles

- Nhiệm vụ và hành động tiếp theo đứng trước phần trang trí.
- Quyền backend là nguồn quyết định; menu chỉ hỗ trợ định hướng.
- Trạng thái rỗng, lỗi, quá hạn và tải dữ liệu phải đọc được và có cách tiếp tục.
- Một hệ component nhất quán cho toàn bộ màn hình nghiệp vụ.

Cập nhật 24/10/2026: giao diện dùng sans nhất quán; mật độ thoáng vừa, ưu tiên đọc từng công việc. Người dùng chọn logo Liền mạch: hai nét nối thành chữ S; dùng cho sidebar, favicon và nhận diện. Giữ Butter nhưng tăng phân biệt nền/chữ và giới hạn vùng đọc.
