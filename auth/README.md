# auth — Keycloak

`realm/moc-realm.json` được Keycloak nạp ở lần khởi động đầu (bỏ qua nếu realm đã có — sửa tệp thì
`make reset`, hoặc sửa qua trang quản trị). Giá trị `${...}` lấy từ biến môi trường của container. Chủ: #21.

| Phần | Nội dung |
|---|---|
| Client `app-office` | Công khai, Authorization Code + PKCE (S256), chuyển hướng về `MOC_PUBLIC_URL` |
| Client `moc-cli` | Luồng mật khẩu cho `make seed`, `make smoke`, các màn demo, CI — không cần trên server thật thì tắt bằng `MOC_CLI_CLIENT_ENABLED=false` |
| Client `svc-workflow` | Tài khoản dịch vụ, quyền `view-users`, đọc danh bạ |
| Đăng nhập trình duyệt (luồng `moc-browser`) | Mật khẩu rồi mã TOTP. Bắt buộc với `clerk`, `manager`, `director`, `tenant_admin`: chưa cài thì Keycloak bắt cài bằng mã QR ngay lần đầu. `staff` chỉ bị hỏi mã nếu đã tự cài |
| Luồng mật khẩu của `moc-cli` (`moc-cli-direct-grant`) | Mật khẩu rồi mã TOTP (tham số `otp`) theo đúng quy tắc của `moc-browser`: không là đường vòng qua xác thực hai bước. Vai trò bắt buộc mà chưa cài TOTP thì không lấy được token (luồng này không cài được). Kịch bản trong `scripts/` tự tính mã từ `MOC_DEMO_TOTP_SECRET` (`moc_env.user_login`), không gửi lại mã đã dùng |
| Mapper | Claim `https://hasura.io/jwt/claims`: `x-hasura-user-id`, `-tenant-id`, `-department-id`, `-default-role`, `-allowed-roles` |
| User profile | `tenant_id`, `department_id`, `moc_role` (5 vai trò) — chỉ quản trị viên xem và sửa |
| Organizations (`organizationsEnabled`) | Mỗi đơn vị một Organization: alias suy từ mã đơn vị (`CNTT` → `cntt`, `ĐT` → `dt`), thuộc tính `tenant_id` = id trong `core.tenants`; mọi tài khoản có `tenant_id` đó là thành viên (unmanaged) và không thuộc Organization nào khác. Đây là lớp quản lý thành viên và quản trị: gom tài khoản theo đơn vị, chỗ gắn tên miền email hay IdP riêng của đơn vị về sau. **Token vẫn lấy đơn vị từ thuộc tính `tenant_id`** qua mapper ở trên, không đổi: claim `organization` của Keycloak (scope tùy chọn `organization`, client của Mộc không xin) là danh sách alias, nằm ngoài namespace `https://hasura.io/jwt/claims` nên Hasura không đọc, và tài khoản thuộc nhiều Organization thì không suy ra được đúng một đơn vị. Tạo bằng `python3 scripts/moc.py tenant create`, kiểm bằng `tenant check`; `make seed` tạo cho hai đơn vị mẫu. Thành viên Organization phải có email (Keycloak từ chối sửa hồ sơ thiếu email) |

Stack dựng từ bản trước F3.12 chưa bật Organizations trong realm (realm không nạp lại): `tenant create` hoặc `make
seed` tự bật (Admin REST, gửi lại nguyên bản realm như trang quản trị), không cần `make reset`.

Stack dựng từ bản mà `moc-cli-direct-grant` chưa hỏi TOTP vẫn giữ luồng cũ, vì realm không nạp lại: `make reset`
(xóa toàn bộ dữ liệu), hoặc trong trang quản trị Keycloak mở Authentication → `moc-cli-direct-grant`, thêm hai
subflow Conditional `moc-cli-otp-bat-buoc`, `moc-cli-otp-tu-chon` sau bước mật khẩu, giống hệt trong
`moc-realm.json`.

Tài khoản mẫu tạo bằng `make seed` (`seed/users.csv`), không nằm trong realm. Các tài khoản văn thư, lãnh đạo,
quản trị được cài sẵn TOTP bằng khóa chung `MOC_DEMO_TOTP_SECRET`; `make totp` in mã hiện tại và khóa để thêm
vào ứng dụng xác thực. Còn làm: giao diện đăng nhập riêng (`auth/themes/`).
