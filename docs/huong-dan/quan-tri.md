# Hướng dẫn cho quản trị đơn vị

Vai trò `tenant_admin`, thường là cán bộ CNTT của đơn vị. Tài khoản mẫu: `quantri` (Khoa CNTT). Đăng nhập cần mã xác
thực hai bước.

Quản trị đơn vị không đọc nội dung văn bản. Vì vậy menu không có Hộp việc, Văn bản đến, Văn bản đi, Hồ sơ công việc,
Sổ đăng ký, và không có chuông thông báo. Nếu gõ thẳng địa chỉ các trang đó, hệ thống đưa bạn về Sổ kiểm toán. Không
gian cá nhân và Bảng tin cũng không mở được với tài khoản này.

Menu gồm: Tìm kiếm, Sổ kiểm toán, Ứng dụng, Góp ý. Nút **Góp ý** và nút đổi ngôn ngữ trên thanh trên cùng dùng như
mọi vai trò ([Việc chung](viec-chung.md#góp-ý)).

## Sổ kiểm toán

Đăng nhập xong là vào thẳng **Sổ kiểm toán**. Sổ ghi mọi thay đổi dữ liệu của đơn vị, nối thành chuỗi băm SHA-256:
sửa hay xóa lén một dòng đều bị phát hiện.

1. Đầu trang cho biết chuỗi đã được neo ra ngoài cơ sở dữ liệu tới dòng nào, lúc nào. Mỗi lần neo, hệ thống chép băm
   của dòng mới nhất ra kho lưu trữ khóa ghi, không ai sửa hay xóa được, kể cả quản trị.
2. Chọn nhóm cần xem bằng các tab: Tất cả, Văn bản, Giao việc, Tệp, Người dùng và quyền xem, Danh mục.
3. Mỗi dòng có **Thời điểm**, **Người thực hiện**, **Thao tác**, **Thay đổi**, **Dòng sổ**. Bấm **Xem thêm** để tải
   các dòng cũ hơn.

Với văn bản hạn chế, sổ không hiện giá trị các trường nội dung. Quản trị đơn vị không mở được văn bản từ sổ. Kiểm cả
chuỗi từ đầu tới cuối là việc của người vận hành máy chủ, bằng lệnh `make audit`. Cách chuỗi băm và mốc neo hoạt
động: [`db/README.md`](../../db/README.md#sổ-kiểm-toán-chuỗi-băm),
[`van-hanh.md`](../van-hanh.md#mốc-neo-công-khai).

## Danh mục ứng dụng

1. Mở **Ứng dụng**. Trang chia ba nhóm: **Có sẵn trong lõi**, **Cài bằng manifest**, **Đã gỡ**.
2. Mỗi ứng dụng cài bằng manifest có **Băm manifest**: mã SHA-256 của tệp `app.yaml` lúc cài. Bấm **Chép** rồi so với
   kết quả lệnh `sha256sum` chạy trên tệp `app.yaml` của ứng dụng đó trên máy chủ (ví dụ
   `sha256sum apps/bang-tin/app.yaml`). Hai mã trùng nhau nghĩa là bản đang cài đúng là bản đã duyệt.

Cài và gỡ ứng dụng là việc của người vận hành máy chủ: [`them-ung-dung.md`](../them-ung-dung.md).

## Tổng hợp góp ý

Mở **Góp ý** trên menu. Phần **Tổng hợp của đơn vị** có điểm trung bình, số góp ý, phân bố theo mức, theo màn hình và
các góp ý gần đây. Trang không hiện tên người gửi, chỉ hiện giờ gửi. Trên đơn vị mẫu (dữ liệu nạp bằng `make seed`),
các góp ý này là của người dùng thử hệ thống.

## Phòng ban và tên đơn vị

Giao diện chưa có màn hình cho việc này. Vai trò quản trị đơn vị có quyền thêm, sửa phòng ban và sửa tên đơn vị qua API
GraphQL. Danh sách thao tác được phép: [`thao-tac-theo-vai-tro.md`](../api/thao-tac-theo-vai-tro.md). Cách gọi API:
[`api/README.md`](../api/README.md).

## Việc của người vận hành máy chủ

Quản trị đơn vị khác người vận hành máy chủ. Các việc sau làm trên máy chủ, không làm trên giao diện:

- Tạo đơn vị mới, tạo tài khoản người dùng trong Keycloak: [`van-hanh.md`](../van-hanh.md#thêm-đơn-vị-thuê-ước).
- Sao lưu, khôi phục, két bí mật, giám sát: [`van-hanh.md`](../van-hanh.md).
- Cài đặt, nâng cấp: [`trien-khai.md`](../trien-khai.md).
