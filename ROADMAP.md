# Lộ trình phát triển DX-Lab

Lộ trình bám theo nguyên lý **tiến hóa tuyến tính** của mô hình DX-OS: mỗi giai đoạn chỉ khởi
động khi giai đoạn trước đã ổn định. Đây cũng là lộ trình mà một tổ chức áp dụng DX-Lab nên đi
theo, không chỉ là lịch phát triển nội bộ.

## Giai đoạn 0 — Nền dự án nguồn mở ✅

Mục tiêu: kho mã nguồn đạt chuẩn dự án nguồn mở bền vững trước khi có dòng mã nghiệp vụ đầu tiên.

- [x] Giấy phép Apache-2.0: toàn văn, thông báo mục đích, header từng tệp
- [x] Cấu hình tách khỏi mã nguồn (`.env.example`)
- [x] Quy trình dựng từ mã nguồn (`Makefile` + Docker Compose)
- [x] CI kiểm tra header giấy phép và cú pháp Compose
- [x] Quy trình phát hành sinh gói `.tar.gz` theo thẻ phiên bản
- [x] Tài liệu nền: README, CONTRIBUTING, CODE_OF_CONDUCT, CHANGELOG, DEPENDENCIES

## Giai đoạn 1 — [H] Không gian Nhân sự

Mục tiêu: một nhân sự đăng nhập **một lần** và làm được toàn bộ công việc thường ngày trong môi
trường số khép kín.

- [ ] Khảo sát và chốt nền tảng quản trị định danh tập trung (SSO)
- [ ] Chốt nền tảng lưu trữ đám mây nội bộ, áp cấu trúc thư mục chuẩn **P.A.R.A**
- [ ] Chốt hệ quản trị tri thức (wiki) và kênh truyền thông nội bộ
- [ ] Cổng thông tin nội bộ gom mọi dịch vụ về một điểm vào duy nhất
- [ ] Nạp dữ liệu mẫu: sơ đồ tổ chức, tài khoản, phân quyền theo vai trò

## Giai đoạn 2 — [P] Không gian Quy trình

Mục tiêu: một nghiệp vụ chạy hết vòng đời **không cần thao tác chuyển giao thủ công** giữa các
bộ phận.

- [ ] Chốt nền tảng low-code dựng biểu mẫu và giao diện nhập liệu
- [ ] Chốt nền tảng tự động hóa luồng việc (workflow automation / iPaaS)
- [ ] Dựng trục trung gian kết nối API giữa các phần mềm của trục [H]
- [ ] Cài đặt ràng buộc **Poka-yoke**: chặn dữ liệu không hợp lệ ngay tại điểm nhập
- [ ] Kiến trúc hướng sự kiện: mọi bước nghiệp vụ phát ra sự kiện có cấu trúc

## Giai đoạn 3 — [D] Không gian Dữ liệu

Mục tiêu: mọi câu hỏi điều hành trả lời được bằng số liệu cập nhật, không cần ai tổng hợp tay.

- [ ] Chốt hệ quản trị CSDL cho dữ liệu nghiệp vụ đã cấu trúc hóa
- [ ] Đường ống thu thập — làm sạch — đồng bộ từ sự kiện của trục [P]
- [ ] Từ điển dữ liệu thống nhất, triệt tiêu xung đột ngữ nghĩa giữa các bộ phận
- [ ] **Nguồn sự thật duy nhất** cho các thực thể lõi (khách hàng, đơn hàng, nhân sự)
- [ ] Chốt nền tảng BI nguồn mở, dựng dashboard thời gian thực cho cấp quản lý

## Giai đoạn 4 — [I] Không gian Trí tuệ Nhân tạo

Điều kiện khởi động: giai đoạn 3 đã có nguồn sự thật duy nhất. **Không khởi động sớm hơn.**

- [ ] Chốt cơ sở dữ liệu véc-tơ và khung phát triển LLM nguồn mở
- [ ] Kiến trúc truy xuất tri thức (RAG) trên kho tài liệu của trục [H]
- [ ] Tác tử tự hành đọc dữ liệu [D] và lắng nghe sự kiện [P]
- [ ] Thực thi hành động cấu hình sẵn không cần thao tác của con người
- [ ] Rào chắn: ngưỡng phê duyệt của con người cho các hành động rủi ro cao
      (nguyên lý **Human-in-the-loop**)

## Giai đoạn 5 — Đóng gói cho cộng đồng

Mục tiêu: một SME không có đội IT tự cài được DX-Lab trong dưới một giờ.

- [ ] Trình cài đặt một lệnh kèm kiểm tra tiền điều kiện
- [ ] Bộ dữ liệu mẫu theo ngành để dùng thử ngay
- [ ] Khung đo lường mức độ trưởng thành H-P-D-I giúp tổ chức tự chẩn đoán
- [ ] Tài liệu vận hành: sao lưu, phục hồi, nâng cấp
- [ ] Hướng dẫn dịch giao diện và tài liệu sang tiếng Anh

## Ngoài phạm vi

Những việc dự án chủ động **không** làm, để giữ đúng bài toán:

- Viết lại từ đầu các phần mềm đã có bản nguồn mở trưởng thành (ERP, CRM, BI)
- Yêu cầu hạ tầng vượt quá khả năng của một SME (cụm Kubernetes nhiều node, GPU chuyên dụng)
- Phụ thuộc vào bất kỳ thành phần nguồn đóng hoặc dịch vụ trả phí bắt buộc nào
