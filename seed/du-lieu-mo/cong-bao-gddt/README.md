# Nguồn công khai `cong-bao-gddt`: thông tư của Bộ GD&ĐT về giáo dục đại học trên Công báo

Nguồn: **Công báo nước Cộng hòa xã hội chủ nghĩa Việt Nam**, Văn phòng Chính phủ, <https://congbao.chinhphu.vn/>.
Bốn tệp PDF trong thư mục này là bản Công báo (có chữ ký số của Công báo) của bốn thông tư do Bộ Giáo dục và Đào tạo
ban hành. `manifest.json` ghi từng tệp: trang văn bản trên Công báo, liên kết tải, số Công báo, ngày lấy, SHA-256.

| Số ký hiệu | Trích yếu | Ngày ban hành | Công báo |
|---|---|---|---|
| 26/2026/TT-BGDĐT | Quy định chuẩn nghề nghiệp giảng viên đại học | 09/04/2026 | số 249 ngày 26/04/2026 |
| 49/2026/TT-BGDĐT | Quy định ứng dụng công nghệ trong giáo dục đại học, giáo dục nghề nghiệp | 30/06/2026 | số 421 ngày 20/07/2026 |
| 58/2026/TT-BGDĐT | Hướng dẫn về quy chế tổ chức và hoạt động của cơ sở giáo dục đại học | 07/07/2026 | số 452 ngày 30/07/2026 |
| 06/2026/TT-BGDĐT | Ban hành Quy chế tuyển sinh các ngành đào tạo trình độ đại học và ngành Giáo dục Mầm non trình độ cao đẳng | 15/02/2026 | số 148 ngày 15/03/2026 |

## Căn cứ dùng lại

- Khoản 2 Điều 15 Luật Sở hữu trí tuệ: "Văn bản quy phạm pháp luật, văn bản hành chính, văn bản khác thuộc lĩnh vực
  tư pháp và bản dịch chính thức của văn bản đó" không thuộc phạm vi bảo hộ quyền tác giả. Thông tư của Bộ trưởng là
  văn bản quy phạm pháp luật.
  - Chữ điều luật đọc ngày 30/10/2026 trên văn bản hợp nhất số 160/2026/VBHN-LQ-VPQH ngày 29/9/2026 (Luật số
    50/2005/QH11, sửa đổi, bổ sung tới Luật số 131/2025/QH15), tệp PDF có chữ ký số của Văn phòng Chính phủ trên
    datafiles.chinhphu.vn, Điều 15 ở trang 15. Khoản 4 của Điều 15 mới thêm theo Luật 131/2025, khoản 2 giữ nguyên.
- Điều khoản của Công báo: "Ghi rõ nguồn 'congbao.chinhphu.vn' khi phát hành lại thông tin từ các nguồn này." Signet
  ghi nguồn ở tệp này, ở `manifest.json` và trên trang trạng thái.
- robots.txt của congbao.chinhphu.vn cho phép mọi đường; máy tải tệp g7.cdnchinhphu.vn không có robots.txt (đọc
  30/10/2026). Lệnh lấy chỉ đọc trang công khai, không đăng nhập, gửi tám yêu cầu cách nhau một giây.
- Không có dữ liệu cá nhân ngoài tên, chức vụ người ký in trong văn bản; manifest không ghi tên người ký.

Giấy phép của các tệp PDF trong REUSE.toml: `LicenseRef-VN-SHTT-Dieu-15`
(`LICENSES/LicenseRef-VN-SHTT-Dieu-15.txt`), không phải Apache-2.0 của Signet.

## Lấy mới, kiểm, nạp

- `make du-lieu-mo-lay` (`python3 scripts/du_lieu_mo.py lay cong-bao-gddt`): đọc lại bốn trang, tải lại PDF. Chỉ thay
  bản chụp khi mọi tệp tải xong và khớp manifest; lỗi thì giữ bản cũ. Đổi bản chụp đi qua PR.
- `make du-lieu-mo`: so SHA-256 với manifest, in tuổi dữ liệu. Quá 400 ngày thì trang trạng thái báo dữ liệu cũ.
- `make seed` nạp bốn thông tư thành văn bản đến của Khoa CNTT (văn thư `vanthu`) qua API nạp lô, loại "Thông tư".
  Không cần Internet. Trợ lý hỏi đáp trích được các văn bản này như mọi văn bản đến.

Danh sách văn bản ở `VAN_BAN` trong `scripts/nguon_cong_bao_gddt.py`. Thêm văn bản: thêm một dòng ở đó, chạy lại lệnh
lấy, giữ tổng dưới 3 MB.

## Chưa làm

- Văn bản nào hết hiệu lực hay bị thay thế thì bản chụp không tự biết: xem lại danh sách khi lấy mới (hạn 400 ngày).
