# Signet — đánh giá UI và phạm vi nghiệm thu

<!-- Copyright 2026 Signet Team -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Ngày 25/10/2026. Nhánh local: `fe-integration`. Nền BE/AI được nhập nguyên bản từ `f86970f`.
Không merge nhánh, không tự vá source BE/AI, không push hoặc cập nhật AWS trong đợt này.

## Nhận định thiết kế

Trong các màn đã rà, Signet có nhận diện riêng và phục vụ công việc văn phòng rõ hơn một dashboard dựng theo mẫu:
logo S liền mạch, Butter/olive, Be Vietnam Pro, số/ký hiệu văn bản, hạn và yêu cầu được giao là những thành phần
thực sự quyết định bố cục. Không dùng KPI giả, gradient, halo trang trí, một icon màu cho mỗi thẻ hoặc số liệu tự bịa
để lấp khoảng trống. Đây là nhận định dựa trên các màn/trạng thái bên dưới, không phải chứng nhận mọi màn đều
"không thể có AI slop" hoặc không còn bất kỳ lỗi nào.

Taste và Impeccable được áp dụng theo hai cách bổ sung nhau: xem ảnh/thao tác thật để đánh giá nhiệm vụ, rồi đo và
kiểm tra implementation. Assessment A và B chạy độc lập, không đọc báo cáo của nhau. A đánh giá thiết kế Hộp việc
và chi tiết văn bản của chuyên viên; B kiểm tra DOM, bàn phím, kích thước, contrast và payload. Điểm ban đầu được
báo theo phạm vi là A 28/40, B 15/20; không tự nâng điểm sau sửa khi chưa chấm lại toàn bộ tiêu chí.

## Các vấn đề đã sửa và xác minh lại

| Vấn đề | Kết quả |
|---|---|
| Hoàn thành việc trước khi đọc được yêu cầu trên mobile | Đưa chỉ dẫn của cấp phòng và cá nhân, người giao và hạn sát ô kết quả; lấy từ assignments đã được BE cấp quyền |
| Quay lại làm mất ngữ cảnh Hộp việc | Liên kết có ngữ cảnh an toàn, nhãn “Về hộp việc”; bộ lọc/tìm kiếm giữ qua route; deep link có fallback vào sổ đến/đi |
| Thiếu chỉ dẫn và phục hồi khi bỏ trống kết quả | Nhãn bắt buộc, native required/aria-required, mô tả hệ quả, error association và focus ô thiếu |
| Tab lịch sử chỉ có hình thức | Roving tabindex, aria-controls/panel, trái/phải, Home/End; lỗi tải có retry ngay tại chỗ |
| Menu mobile mất focus khi vừa mở | Focus theo frame/transition, containment hai chiều, Escape trả về nút mở; đã thử normal và reduced motion |
| Filename bị cắt và target nhỏ | Tên tệp xuống dòng đầy đủ trên điện thoại; back/tab/language/logout/footer có vùng bấm tối thiểu 44px trong phạm vi đo |
| Font tải quá nặng | Giữ Be Vietnam Pro, đổi sang WOFF2 tự phục vụ đủ Vietnamese/Latin/Latin-ext; bỏ TTF và Lora không dùng; không thêm package |
| Halo khung xử lý và các glyph làm icon | Bỏ ring trang trí, dùng SVG thống nhất; giữ outline focus có mục đích |
| Sơ đồ cảm biến bị thu nhỏ khó đọc | Canvas giữ chiều rộng tối thiểu, cuộn ngang bằng bàn phím, hint theo container; bảng chi tiết vẫn có đầy đủ số đo |
| Cờ đồng hồ cảm biến mới | Nhận future_time từ upstream, hiện nhãn/hint đúng, không đổi luật đánh giá của BE |
| Phản hồi thao tác lâu chưa rõ | Vào sổ có trạng thái đang xử lý/aria-busy; xử lý việc có trạng thái gửi, chặn gửi trùng ở component |

Một lần vào sổ trong luồng liên thông mất khoảng 17 giây nhưng trả thành công. Test đã chờ trạng thái nghiệp vụ
trong giới hạn 60 giây thay vì timeout mặc định 15 giây; không thay kết quả mong đợi hoặc che phản hồi lỗi. Độ trễ
này là quan sát local cần theo dõi, không phải khẳng định đã tối ưu hiệu năng BE.

## Bằng chứng định lượng

- 258 unit/contract tests đạt; 76 tệp JS/Vue qua compiler check. Runtime FE vẫn là JavaScript.
- E2E đầy đủ: xem kết quả lượt cuối bên dưới. Các ca đi qua Keycloak, gateway/WAF, quyền theo đơn vị, văn bản đến/đi,
  ký duyệt/phát hành, liên thông, hồ sơ/phòng đọc, realtime, kiểm dịch, tra cứu và public status.
- Sáu ảnh mới của Hộp việc/chi tiết ở 1440/768/390: không tràn document, đúng font. 21 route/trạng thái đã có lượt
  rà rộng ở ba kích thước; các ảnh đó là mẫu trạng thái, không chứng minh mọi tổ hợp vai trò/dữ liệu.
- B đo contrast chữ trong sáu DOM mẫu: thấp nhất 4.77:1. Không suy rộng thành chứng nhận WCAG đầy đủ cho icon,
  placeholder, pseudo-element, ảnh hoặc thiết bị thực.
- Font Office thực tải 175,804 byte so với 545,964 trước đó (giảm 67.8%); Cá nhân 163,336 byte; Keycloak Be Vietnam Pro
  128,784 byte. Không có TTF hoặc lỗi font ở lượt xác minh login sau refresh cache. Keycloak vẫn dùng icon font của nó.
- Bộ font tĩnh đủ 12 subset/weight là 189,656 byte; cả 36 bản sao có manifest/hash và giấy phép. CDP xác nhận chữ
  tiếng Việt dùng glyph Be Vietnam Pro thực, không chỉ dựa vào tên font-family.
- Bốn runtime dependencies của Office vẫn được dùng; package.json/lockfile không thêm package. ECharts không xuất
  hiện trong request Hộp việc/chi tiết của chuyên viên; không suy rộng phép đo đó cho mọi vai trò/route.
- REUSE lint đạt. Quy trình và quy ước: [fe-development-workflow.md](fe-development-workflow.md).

## Công cụ và ngoại lệ có chủ đích

Taste probe/layout/app và bộ judge gốc được chạy trong browser đã đăng nhập cho sáu route, ba chiều rộng. Lượt sau
sửa không có FAIL; các WARN còn lại là trang ngắn trước khi có câu hỏi/lịch sử và cột timeline độc lập. Không kéo dài
card, bịa thêm dữ liệu hoặc nhồi panel để làm detector hết khoảng trắng. Form soạn được căn giữa trong vùng làm việc.

Impeccable source detector trả 0 finding nhưng chỉ quét regex Vue; đây là tín hiệu bổ sung. Binary hiện tại không hỗ
trợ --cdp như tài liệu nêu và live overlay bị CSP chặn; không có overlay thành công. Không tắt CSP để làm công cụ chạy.
Các phép đo DOM/browser độc lập và thao tác bàn phím là bằng chứng kỹ thuật thực. Chưa thử screen reader/thiết bị
cảm ứng vật lý, print ở mọi máy hoặc throttling mạng, nên không tuyên bố những phần đó đạt.

## Tích hợp AI — CHƯA HOÀN TẤT

Hai mô hình đúng digest đã tải và nạp, nhưng readyz báo `assist.semantic=false`, model có sẵn và các đoạn còn chờ
nhúng. Chỉ mục cũ thiếu vector khi đổi sang userProvided. Người dùng đã chọn ghi lỗi và chờ BE; không dựng lại chỉ
mục, không xóa dữ liệu hoặc tự sửa nguồn AI/BE. Có mô hình trong RAM không chứng minh tích hợp hoàn toàn.

Xem [fe-be-blocker-embedding-2026-10-25.md](fe-be-blocker-embedding-2026-10-25.md). Mục tiêu chung vẫn chưa đạt;
chỉ có thể hoàn tất phần semantic/generation acceptance sau khi BE xử lý và chạy lại đường thật trên UI.

## Kết quả lượt kiểm thử cuối

- Bộ E2E ổn định cuối: **31/31 đạt**, 7 phút, trên image đã cố định; không thay source/recreate dịch vụ trong lượt chạy.
- Unit/contract: **258/258 đạt**, không skip. Compiler: **76 tệp JS/Vue đạt**. REUSE lint đạt.
- Ca cảm biến dùng API fixture (đã ghi rõ trong tên test), kiểm tra cả future_time, layout ba kích thước,
  SVG có semantics đúng, vùng cuộn bàn phím và chữ sơ đồ không bị thu nhỏ. Không coi đó là kết nối broker thật.
- readyz sau chạy: core ready, AI model sẵn sàng, `assist.semantic=false`, pending 61 đoạn tại thời điểm ghi.
  Giữ nguyên lỗi này theo quyết định chờ BE. Không đánh dấu mục tiêu tổng thể hoàn tất.
- Có thêm WARN tiny-text trên danh sách hồ sơ mobile với dữ liệu mẫu dài hơn: năm/trạng thái/nhãn phụ 12px;
  tên hồ sơ và thao tác chính vẫn 14px. Giữ phân cấp này; đây không phải chứng nhận khả năng đọc ở mọi thiết bị.

Log và ảnh chi tiết nằm trong `.cache/latest-review/` cùng hai thư mục assessment cục bộ. Không commit các phiên
đăng nhập hoặc bí mật. Source service/platform/schema/script khớp nguyên bản commit f86970f qua Git diff.
