# Hướng dẫn cho lãnh đạo phòng

Vai trò `manager`: trưởng phòng, tổ trưởng, trưởng bộ môn. Tài khoản mẫu: `totruongdt` (Tổ trưởng Đào tạo),
`truongbmktpm` (trưởng Bộ môn Kỹ thuật phần mềm). Đăng nhập cần mã xác thực hai bước. Lãnh đạo phòng thấy văn bản
được giao cho phòng mình.

Menu gồm: Hộp việc, Văn bản đến, Văn bản đi, Hồ sơ công việc, Sơ đồ cảm biến, Tìm kiếm, Hỏi đáp, Tự chẩn đoán, Ứng dụng,
Góp ý. Phần dùng chung: [Việc chung](viec-chung.md).

## Phân công văn bản đến

Việc **Phân công xử lý** đến Hộp việc khi lãnh đạo đơn vị giao phòng bạn chủ trì một văn bản.

1. Mở việc. Đọc ý kiến chỉ đạo và hạn ở mục **Giao xử lý** trên trang văn bản.
2. Ở khung **Phân công trong phòng**, chọn người trong ô **Giao cho**, ghi **Lời dặn** nếu cần, rồi bấm **Giao việc**.
   Người đó nhận việc **Xử lý văn bản**.
3. Nếu tự làm thì bấm **Tôi tự xử lý**. Việc **Xử lý văn bản** sẽ về Hộp việc của bạn, cách làm giống chuyên viên
   ([Xử lý văn bản được giao](chuyen-vien.md#xử-lý-văn-bản-được-giao)).

## Duyệt dự thảo của phòng

Việc **Duyệt dự thảo cấp phòng** đến Hộp việc khi chuyên viên trong phòng trình một dự thảo văn bản đi.

1. Mở việc, bấm **Xem bản PDF trước khi duyệt**.
2. Nếu dự thảo đạt, bấm **Đồng ý, trình ký**. Dự thảo chuyển tới lãnh đạo đơn vị mà người soạn đã chọn để ký.
3. Nếu chưa đạt, ghi vào ô **Ý kiến** lý do và chỗ cần sửa, rồi bấm **Trả lại**. Ô này bắt buộc khi trả lại. Dự thảo về
   người soạn với việc **Sửa dự thảo theo ý kiến**. Khi người soạn trình lại, dự thảo quay về bạn duyệt.

## Hồ sơ công việc

Lập hồ sơ, thêm văn bản và đóng hồ sơ làm giống chuyên viên
([Hồ sơ công việc](chuyen-vien.md#hồ-sơ-công-việc)). Riêng lãnh đạo phòng được nộp lưu hồ sơ của phòng.

## Nộp lưu hồ sơ

1. Mở **Hồ sơ công việc**, sang tab **Đã đóng**, rồi mở hồ sơ cần nộp lưu.
2. Bấm **Nộp lưu** và xác nhận. Gói lưu trữ chuyển vào kho lạnh, bị khóa ghi tới hết thời hạn bảo quản: không ai sửa
   hay xóa được. Cơ sở dữ liệu nghiệp vụ chỉ giữ lại bản ghi rút gọn.
3. Hồ sơ sang tab **Đã nộp lưu**. Từ đây hồ sơ chỉ mở được ở chế độ xem, gọi là **Phòng đọc**.

Hồ sơ đã đóng mà không ai nộp lưu thì hệ thống tự nộp lưu sau thời hạn cấu hình, mặc định 365 ngày. Kho lạnh hoạt động
thế nào: [`demo-script.md`](../demo-script.md), mục "Nóng → lạnh".

## Duyệt đơn nghỉ phép

Chỉ có khi đơn vị đã cài ứng dụng Đơn nghỉ phép. Bạn chỉ nhận đơn của người trong phòng mình.

1. Mở **Ứng dụng**, ở thẻ **Đơn nghỉ phép** bấm **Mở**. Phần **Việc cần duyệt** chỉ hiện khi có đơn đang chờ.
2. Ở từng đơn, chọn **Quyết định** là Đồng ý hoặc Từ chối, ghi **Ghi chú** nếu cần, rồi bấm **Gửi quyết định**.
3. Người gửi thấy quyết định và ghi chú ở phần **Đơn của tôi**.

Danh sách đơn tự làm mới 30 giây một lần, không xóa ghi chú bạn đang gõ.

## Tự chẩn đoán

Mở **Tự chẩn đoán** để tự đánh giá mức trưởng thành số của đơn vị theo bốn không gian: Con người, Quy trình, Dữ liệu,
Trí tuệ. Trả lời từng câu để xem kết quả và việc nên làm trước. Lãnh đạo phòng không lưu được kết quả và không thấy
bằng chứng đo được của đơn vị; hai việc đó dành cho lãnh đạo đơn vị. Bộ câu hỏi và cách chấm:
[`tu-chan-doan.md`](../tu-chan-doan.md).
