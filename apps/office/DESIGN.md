# Giao diện "Lịch hạn"

Hệ thiết kế của `apps/office`. Người dùng và yêu cầu ở `PRODUCT.md`. Màu, cỡ chữ, khoảng cách khai một chỗ ở
`app/assets/css/main.css`; `tests/contrast.test.ts` đọc thẳng từ đó, sửa màu mà trượt WCAG 2.2 AA thì test đỏ.

## Ý chính

Văn thư và chuyên viên làm việc theo hạn. Hộp việc vì thế là một tờ lịch: việc xếp theo ngày đến hạn, ngày hạn là con
số lớn, quá hạn và hôm nay nổi lên trước. Trang văn bản mở đầu bằng hạn và đoạn đường từ lúc vào sổ tới hạn, rồi tới
việc người dùng phải làm.

## Màu

| Vai trò | Giá trị | Dùng cho |
|---|---|---|
| Thanh bên | `#0b5a47` | khối tối duy nhất, điểm bám mắt; chữ `#cfe7dc`, mục đang mở là ô trắng chữ lục bảo |
| Trang | `#ffffff` | nền làm việc; nền phụ `--paper` `#f5f9f7`, nền chọn `--active` `#e6f2ec` |
| Mực | `stone-900` `#10201b` → `stone-400` `#56685f` | chữ chính, phụ; thang stone là xám ngả lục, không ngả vàng |
| Lục bảo | `brand-700` `#0b6b53` | nút chính, liên kết, viền focus, mục đang chọn; không tô nền rộng |
| Đỏ | `red-700` `#9f2019` | quá hạn, Hỏa tốc, lỗi |
| Hổ phách | `amber-800` `#7a4800` | hôm nay, sắp tới hạn, Khẩn |

Đỏ và hổ phách chỉ đi với trạng thái, không làm trang trí. Viền ô nhập `#7a8d84` (≥ 3:1). Trong thanh bên, viền
focus là trắng vì viền lục bảo chung chìm vào nền.

## Chữ

Be Vietnam Pro tự phục vụ (OFL-1.1, `public/fonts`), bốn độ đậm 400–700, không thêm phông khác. Tiêu đề trang 26px
600; tiêu đề khối 16px 600; chữ thường 14–16px; số đi `tabular-nums`. Ngày hạn trên lịch là chữ số lớn, không phải ô
thống kê.

## Khung

- Thanh bên 76px (biểu tượng) mở thành 248px khi rê chuột hoặc focus bàn phím, nằm đè lên trang, không đẩy nội dung.
  Hành vi giữ đúng #297/#298 (`tests/e2e/giao-dien.spec.ts`): bấm chọn thì thu, nhích chuột không mở lại, Esc thu;
  ≤ 900px hoặc màn cảm ứng thành ngăn kéo. Không ghim mở.
- Thanh trên trải hết chiều ngang: đơn vị › trang đang mở, ngày, góp ý, chuông, ngôn ngữ. Trang ngoài menu đặt tên
  qua `useState('sg-crumb')`.
- Không có chân trang kiểu website. Xác thực văn bản và trạng thái hệ thống nằm cuối thanh bên.
- Nội dung rộng tối đa 1368px, lề 40px (28px dưới 1200px, 16px trên điện thoại).

## Chuyển động

Chỉ diễn tả điều hướng, đổi trạng thái, phản hồi trực tiếp: thanh bên mở, trang mới hiện dần, việc vào/ra danh sách.
Tắt hết khi người dùng chọn giảm chuyển động.

## Không làm

Ô thống kê (số lớn + nhãn) thay cho nội dung, thẻ lồng thẻ, chữ nhỏ trên nền màu đậm ngoài thanh bên, viền màu dày
bên trái, kính mờ, dữ liệu hay số liệu bịa.
