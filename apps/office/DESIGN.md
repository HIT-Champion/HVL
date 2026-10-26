# Văn phòng điện tử — thiết kế giao diện

Hướng **"bìa hồ sơ và tờ giấy"**: ý lấy từ chính đồ vật của văn thư. Tờ công văn nằm trong bìa hồ sơ, chữ mực,
dấu son đỏ. Người dùng và yêu cầu ở `PRODUCT.md`; mã ở `app/assets/css/main.css` (token, khung, thành phần) và
`tests/contrast.test.ts` (khóa tỉ lệ tương phản).

## Khung

- Thanh bên và thanh trên dùng chung một nền kraft nhạt, không kẻ ngăn. Nội dung và chân trang nằm trên một tờ giấy
  trắng cách mép phải và mép dưới 8px, viền 1px, bo 16px, không đổ bóng. Nội dung bám một mép trái, rộng tối đa
  1280px.
- `main` có lề trong 12px (trừ vào lề tờ giấy) để nền rê chuột của dòng việc tràn ra hai bên mà vẫn nằm trong
  `main`; không trang nào cuộn ngang (e2e `man-hep`).
- Điện thoại, máy tính bảng (≤ 900px hoặc màn cảm ứng): bỏ khung, tờ giấy chiếm cả màn dưới thanh trên.

## Màu

| Vai trò | Màu | Tương phản |
|---|---|---|
| Nền khung (kraft) | `#efebe2` | chữ chính 14,3:1, chữ phụ 6,4:1 |
| Tờ giấy, thẻ | `#ffffff`, viền `#e3ded3` | |
| Giấy nhạt: trạng thái rỗng, rê chuột | `#fbfaf7`, `#f8f6f1` | |
| Chữ chính | `#1d1c1a` | 17:1 trên trắng |
| Chữ phụ | `#57544c` | 7,6:1 trên trắng |
| Mực xanh: nút chính, liên kết, tab đang chọn, bước cần làm | `#284868` (rê chuột `#1d3854`) | chữ trắng 9,5:1 |
| Đỏ son: độ khẩn, quá hạn, lỗi | viền `#b42419`, chữ `#9f1f16` | 6,6:1 và 7,8:1 trên trắng |
| Logo chữ S | olive `#35432d` (bản chính thức, `public/brand`) | 8,9:1 trên kraft |
| Viền ô nhập; ô đang nhập | `#857f71`; `#284868` + vòng `#dde6f0` | 4:1 trên trắng |

Đỏ son chỉ mang nghĩa (khẩn, quá hạn, lỗi), không dùng trang trí; logo vì thế giữ màu olive. Không gradient, không
bóng khi đứng yên. Không màu nào là tín hiệu duy nhất: độ khẩn có chữ, quá hạn có câu "Quá hạn n ngày".

## Chữ

Be Vietnam Pro (OFL-1.1, tự phục vụ ở `public/fonts`). Một thang: tiêu đề trang 24/600, tiêu đề khối 16/600, chữ
14–16, chữ phụ 13; số dùng chữ số đều (`tabular-nums`).

## Thành phần

- **Dòng việc** (hộp việc, kết quả tìm kiếm): một dòng hai tầng. Tầng 1 dấu độ khẩn và trích yếu, tầng 2 số ký
  hiệu, nơi gửi, bước cần làm; cột hạn canh phải (ngày, còn hoặc quá mấy ngày). Không thẻ, ngăn bằng đường kẻ.
- **Dấu độ khẩn** in như con dấu trên công văn giấy: Khẩn viền mảnh, Thượng khẩn viền đậm, Hỏa tốc nền đỏ chữ trắng.
  Văn bản thường không có dấu.
- **Tab**: chữ có gạch chân màu mực, kèm số đếm; trên điện thoại tab hộp việc xếp lưới 2×2, tab khác xuống dòng.
- **Khung làm việc** (xử lý, chỉ đạo, phân công, trình ký): thẻ duy nhất trên trang văn bản, viền xanh mực nhạt và
  tiêu đề 16/600. Thông tin văn bản ở cột phải dạng nhãn – giá trị.
- **Hỏi đáp, góp ý, form**: nằm thẳng trên tờ giấy, các phần ngăn bằng tiêu đề và đường kẻ; không hộp lồng trong
  hộp. Câu trích nguyên văn là khối trích dẫn có vạch trái.
- **Trạng thái**: rỗng là khung nét đứt trên giấy nhạt kèm một câu vì sao và bước tiếp; lỗi là một dòng có nút Thử
  lại; không có văn bản hoặc không được xem dùng chung một câu (không lộ văn bản có tồn tại) và lối sang tìm kiếm.

## Thanh bên

- Thu về dải 76px (biểu tượng và vạch ngăn nhóm). Mở thành 248px khi con trỏ dừng trên dải 120ms hoặc khi focus bằng
  bàn phím; mở thì **nằm đè** lên tờ giấy, có mép 1px và bóng, không đẩy nội dung (e2e `giao-dien`).
- Mục chia nhóm: Công việc, Văn bản, Tra cứu, Điều hành, Khác. Mục đang mở là ô trắng như tờ giấy.
- Điện thoại: ngăn kéo mở bằng nút menu, có lớp phủ, Esc đóng và trả focus, Tab chỉ đi vòng trong ngăn kéo.

## Chuyển động

150–280ms, chỉ cho đổi trạng thái, mở thanh bên, popover, vào trang. Tắt hết khi `prefers-reduced-motion: reduce`.

## Đã cân nhắc và bỏ

- Giữ vàng bơ, olive rồi chỉnh nhẹ: vẫn thiếu điểm nhìn, nút và nền gần cùng độ sáng.
- Xám trung tính với một màu nhấn: đúng mẫu có sẵn, không ra Signet.
- Thanh bên mở thì đẩy nội dung: mỗi lần con trỏ lướt qua dải biểu tượng cả trang dịch và xuống dòng lại, chỗ định
  bấm chạy khỏi con trỏ. Giữ nằm đè, thêm nhịp chờ 120ms và mép rõ.
- Chữ S màu đỏ son: lẫn với tín hiệu khẩn và lỗi.

## Chưa phủ

Các trang quản trị và điều hành (điều hành, sơ đồ, phả hệ, tự chẩn đoán, sổ kiểm toán, cảm biến, ứng dụng, hồ sơ,
sổ đăng ký) và trang công khai (xác thực, trạng thái) mới theo bảng màu và khung chung, chưa sắp lại bố cục.
