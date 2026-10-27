# Hướng dẫn cho văn thư

Vai trò `clerk`. Tài khoản mẫu: `vanthu` (Khoa CNTT), `vanthukt` (Khoa Kinh tế). Đăng nhập cần mã xác thực hai bước.
Văn thư thấy mọi văn bản của đơn vị mình, trừ văn bản hạn chế không được cấp quyền xem.

Menu gồm: Hộp việc, Văn bản đến, Tiếp nhận văn bản, Văn bản đi, Sổ đăng ký, Hồ sơ công việc (chỉ xem), Sơ đồ cảm biến,
Tìm kiếm, Hỏi đáp, Ứng dụng, Góp ý. Phần dùng chung: [Việc chung](viec-chung.md).

## Tiếp nhận một văn bản đến

1. Bấm **Tiếp nhận văn bản** trên menu, hoặc **Tiếp nhận mới** trên Hộp việc.
2. Kéo thả tệp PDF hoặc ảnh chụp vào ô **Tệp văn bản**, hoặc bấm vào ô để chọn tệp. Tệp được quét virus trước khi lưu.
   Tệp nhiễm mã độc bị chặn và không được lưu.
3. Bấm **Đọc văn bản**. Hệ thống đọc chữ trong tệp PDF, hoặc nhận dạng chữ nếu là bản scan (có thể mất đến 30 giây),
   rồi điền sẵn các ô. Ô được điền sẵn có nhãn **Gợi ý**. Ô nào có gợi ý khác thì gợi ý hiện dưới ô, kèm nút **Dùng**.
4. Đối chiếu từng ô với bản gốc và sửa nếu sai: Loại văn bản, Số, ký hiệu, Cơ quan ban hành, Ngày ban hành, Trích yếu
   nội dung, Độ khẩn, Hạn giải quyết. Bấm lưu nghĩa là văn thư xác nhận các ô này.
5. Bấm **Lưu và vào sổ**. Văn bản được cấp số đến, liên tiếp theo năm, rồi chuyển tới lãnh đạo đơn vị để chỉ đạo.

Nếu chỉ bấm **Lưu văn bản**, văn bản sẽ nằm ở tab **Chờ vào sổ** của mục Văn bản đến. Khi sẵn sàng, mở văn bản đó và
bấm **Vào sổ**. Nếu văn bản có vẻ đã được tiếp nhận trước đó (trùng số ký hiệu, cơ quan ban hành, ngày), màn hình sẽ
báo để bạn kiểm tra lại.

Cách hệ thống đọc văn bản và giới hạn của nó: [`demo-script.md`](../demo-script.md), mục "đọc văn bản đến".

## Tiếp nhận văn bản hạn chế

1. Trên trang tiếp nhận, tích **Hạn chế người xem** trước khi tải tệp lên. Chỉ nhận tệp PDF. Tệp được mã hóa trước
   khi lưu, và hệ thống không tự đọc tệp này: bạn nhập tay các ô.
2. Lưu như văn bản thường.
3. Trên trang văn bản, ở khung **Người được xem**, mở ô **Chọn người**, chọn tên rồi bấm **Cấp quyền xem**. Bấm **Gỡ**
   để thu lại quyền. Người phải làm bước tiếp theo được hệ thống tự thêm vào danh sách.

Bản tải về có dấu tên người xem, và mỗi lần mở đều ghi vào sổ kiểm toán. Chi tiết:
[`demo-script.md`](../demo-script.md), mục "Văn bản hạn chế".

## Vào sổ văn bản liên thông

Khi một đơn vị khác cùng dùng Signet phát hành văn bản gửi đơn vị bạn, văn bản đó tự vào mục **Văn bản đến**, kèm bản
PDF đã phát hành. Chuông thông báo sẽ báo "Văn bản đến liên thông từ …".

1. Mở văn bản. Trang ghi đơn vị gửi, mã xác thực của bên gửi và kết quả so khớp SHA-256 với bản phát hành.
2. Bấm **Mở trang xác thực** nếu muốn đối chiếu thêm.
3. Bấm **Vào sổ**. Từ đây văn bản đi tiếp như mọi văn bản đến khác.

## Cấp số và phát hành văn bản đi

Việc **Cấp số và phát hành** đến Hộp việc sau khi lãnh đạo đơn vị ký duyệt.

1. Mở việc. Bấm **Xem bản PDF trước khi duyệt** để kiểm tra bản sẽ phát hành.
2. Tích **Công khai trích yếu trên cổng xác thực** nếu muốn người tra mã thấy cả trích yếu. Không tích thì họ chỉ thấy
   số, ngày và cơ quan ban hành. Văn bản hạn chế không công khai trích yếu được.
3. Bấm **Cấp số và phát hành**, rồi xác nhận. Số đi được cấp liên tiếp theo năm và không thu hồi được.

Văn bản phát hành xong sẽ sang tab **Đã phát hành** của mục Văn bản đi. Trang văn bản có **Mã xác thực** để gửi kèm
cho người nhận. Nếu người soạn đã chọn đơn vị ở mục "Gửi trong hệ thống", văn bản sẽ tự chuyển tới văn thư các đơn vị
đó. Trạng thái từng đơn vị hiện ở khung **Liên thông trong hệ thống** trên trang văn bản.

## Sổ đăng ký

1. Mở **Sổ đăng ký**. Chọn **Năm**, rồi chọn **Sổ văn bản đến** hoặc **Sổ văn bản đi**. Các cột đúng mẫu sổ của Nghị
   định 30/2020/NĐ-CP, Phụ lục IV.
2. Bấm vào một dòng để mở văn bản. Trên sổ có dòng báo sổ liền số hay thiếu số nào. Nếu sổ thiếu số, báo quản trị hệ
   thống trước khi in.
3. Bấm **In sổ (PDF)** để in ra giấy, ký nhận và đóng sổ cuối năm. Cột Ký nhận và Số lượng bản ghi tay trên bản in.
   Mỗi lần in đều được ghi vào sổ kiểm toán.

## Theo dõi văn bản

- **Văn bản đến** có các tab: Chờ vào sổ, Đang xử lý, Đã xong, Tất cả.
- **Văn bản đi** có các tab: Dự thảo, Đang trình, Đã phát hành, Tất cả.
- **Hồ sơ công việc**: văn thư chỉ xem hồ sơ của đơn vị. Chuyên viên và lãnh đạo phòng là người lập hồ sơ
  ([Chuyên viên](chuyen-vien.md#hồ-sơ-công-việc)).
