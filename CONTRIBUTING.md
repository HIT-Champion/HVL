# Hướng dẫn đóng góp cho DX-Lab

Cảm ơn bạn đã quan tâm tới DX-Lab. Dự án hoan nghênh mọi đóng góp: báo lỗi, đề xuất tính năng,
cải thiện tài liệu, bổ sung công cụ nguồn mở cho một trong bốn không gian H-P-D-I.

## Nguyên tắc kiến trúc bắt buộc

Trước khi viết dòng mã đầu tiên, hãy nắm ba ràng buộc không được vi phạm:

1. **Không fork-và-sửa phần mềm thượng nguồn.** DX-Lab *điều phối* các dự án nguồn mở ở dạng
   nguyên bản. Mọi tùy biến phải nằm ở lớp cấu hình, plugin, hoặc adapter của riêng DX-Lab.
   Nếu cần vá upstream, hãy gửi patch lên chính dự án đó rồi ghim phiên bản.
2. **Không bundle mã nguồn của dự án khác vào kho này.** Phụ thuộc được khai báo qua image
   Docker có ghim thẻ phiên bản, hoặc qua trình quản lý gói — không sao chép cây mã vào repo.
3. **Không nhảy cóc trục.** Tính năng thuộc trục [I] chỉ được nhận nếu dữ liệu nó tiêu thụ đã do
   [D] chuẩn hóa và sự kiện nó lắng nghe đã do [P] sinh ra.

## Quy trình đóng góp

```bash
# 1. Fork và tạo nhánh
git checkout -b feat/<mô-tả-ngắn>       # hoặc fix/, docs/, chore/

# 2. Cấu hình môi trường
cp .env.example .env

# 3. Sửa mã, rồi kiểm tra trước khi commit
make check            # kiểm tra môi trường + cú pháp Compose
make license-check    # bảo đảm mọi tệp mã có header giấy phép
make license-fix      # tự chèn header nếu thiếu

# 4. Commit và mở pull request
```

## Quy ước commit

Theo [Conventional Commits](https://www.conventionalcommits.org/):

```
<loại>(<phạm vi>): <mô tả ngắn>

feat(P): thêm workflow duyệt đơn hàng nhiều cấp
fix(D): sửa lỗi trùng khóa khi đồng bộ dữ liệu khách hàng
docs(readme): bổ sung hướng dẫn chạy từng trục
chore(ci): ghim phiên bản action checkout
```

Phạm vi nên là tên trục (`H`, `P`, `D`, `I`) khi thay đổi thuộc về một không gian cụ thể.

## Yêu cầu với mã nguồn

- **Mọi tệp mã mới phải có header giấy phép Apache-2.0** ở đầu tệp. Chạy `make license-fix` để
  tự chèn. CI sẽ chặn pull request nếu thiếu (đây là tiêu chí chấm điểm bắt buộc của dự án).
- Không hard-code cấu hình. Tham số mới phải được khai báo trong `.env.example` kèm chú thích.
- Mã phải chạy được khi hệ thống được cài **ngoài** thư mục mã nguồn.
- Cập nhật `CHANGELOG.md` mục `[Chưa phát hành]` cho mọi thay đổi hướng người dùng.
- Nếu thêm một phần mềm thượng nguồn mới, phải bổ sung dòng tương ứng vào `DEPENDENCIES.md`
  kèm giấy phép và kiểm tra tính tương thích với Apache-2.0.

## Báo lỗi

Mở issue theo mẫu có sẵn tại `.github/ISSUE_TEMPLATE/`. Một báo lỗi hữu ích cần có: bước tái
hiện, kết quả mong đợi, kết quả thực tế, phiên bản DX-Lab (`git describe --tags`), và nhật ký
liên quan (`make logs`).

## Giấy phép của phần đóng góp

Khi gửi pull request, bạn đồng ý rằng phần đóng góp của mình được phát hành theo
**Apache License 2.0**, cùng giấy phép với dự án.
