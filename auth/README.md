# auth — Keycloak

`realm/moc-realm.json` được Keycloak nạp ở lần khởi động đầu (bỏ qua nếu realm đã có — sửa tệp thì
`make reset`, hoặc sửa qua trang quản trị). Giá trị `${...}` lấy từ biến môi trường của container. Chủ: #21.

| Phần | Nội dung |
|---|---|
| Client `app-office` | Công khai, Authorization Code + PKCE (S256), chuyển hướng về `MOC_PUBLIC_URL` |
| Client `moc-cli` | Luồng mật khẩu cho `make seed`, `make smoke`, `make e2e` — tắt bằng `MOC_CLI_CLIENT_ENABLED=false` trên server thật |
| Client `svc-workflow` | Tài khoản dịch vụ, quyền `view-users`, đọc danh bạ |
| Đăng nhập trình duyệt (luồng `moc-browser`) | Mật khẩu rồi mã TOTP. Bắt buộc với `clerk`, `manager`, `director`, `tenant_admin`: chưa cài thì Keycloak bắt cài bằng mã QR ngay lần đầu. `staff` chỉ bị hỏi mã nếu đã tự cài |
| Luồng mật khẩu của `moc-cli` (`moc-cli-direct-grant`) | Chỉ kiểm mật khẩu, không hỏi TOTP — lý do phải tắt client này trên server thật |
| Mapper | Claim `https://hasura.io/jwt/claims`: `x-hasura-user-id`, `-tenant-id`, `-department-id`, `-default-role`, `-allowed-roles` |
| User profile | `tenant_id`, `department_id`, `moc_role` (5 vai trò) — chỉ quản trị viên xem và sửa |

Tài khoản mẫu tạo bằng `make seed` (`seed/users.csv`), không nằm trong realm. Các tài khoản văn thư, lãnh đạo,
quản trị được cài sẵn TOTP bằng khóa chung `MOC_DEMO_TOTP_SECRET`; `make totp` in mã hiện tại và khóa để thêm
vào ứng dụng xác thực. Còn làm: giao diện đăng nhập riêng (`auth/themes/`).
