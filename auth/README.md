# auth — Keycloak

`realm/moc-realm.json` được Keycloak nạp ở lần khởi động đầu (bỏ qua nếu realm đã có — sửa tệp thì
`make reset`, hoặc sửa qua trang quản trị). Giá trị `${...}` lấy từ biến môi trường của container. Chủ: #21.

| Phần | Nội dung |
|---|---|
| Client `app-office` | Công khai, Authorization Code + PKCE (S256), chuyển hướng về `MOC_PUBLIC_URL` |
| Client `moc-cli` | Luồng mật khẩu cho `make seed`, `make smoke`, `make e2e` — tắt bằng `MOC_CLI_CLIENT_ENABLED=false` trên server thật |
| Client `svc-workflow` | Tài khoản dịch vụ, quyền `view-users`, đọc danh bạ |
| Mapper | Claim `https://hasura.io/jwt/claims`: `x-hasura-user-id`, `-tenant-id`, `-department-id`, `-default-role`, `-allowed-roles` |
| User profile | `tenant_id`, `department_id`, `moc_role` (5 vai trò) — chỉ quản trị viên xem và sửa |

Tài khoản mẫu tạo bằng `make seed` (`seed/users.csv`), không nằm trong realm. Còn làm: TOTP bắt buộc cho
văn thư và lãnh đạo, giao diện đăng nhập riêng (`auth/themes/`).
