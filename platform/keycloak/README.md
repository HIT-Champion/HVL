# platform/keycloak — Keycloak

`realm/moc-realm.json` được Keycloak nạp ở lần khởi động đầu (bỏ qua nếu realm đã có — sửa tệp thì
`make reset`, hoặc sửa qua trang quản trị). Giá trị `${...}` lấy từ biến môi trường của container. Chủ: #21.

| Phần | Nội dung |
|---|---|
| Client `app-office` | Công khai, Authorization Code + PKCE (S256), chuyển hướng về `MOC_PUBLIC_URL` |
| Client `app-ca-nhan` | Không gian cá nhân P.A.R.A (`apps/ca-nhan`, [`docs/them-ung-dung.md`](../../docs/them-ung-dung.md)): như `app-office` — công khai, Authorization Code + PKCE (S256), cùng 5 mapper claim Hasura — nhưng chỉ chuyển hướng về `MOC_PUBLIC_URL/ca-nhan/*`. Cùng phiên SSO: đã đăng nhập Văn phòng điện tử thì không hỏi lại mật khẩu |
| Client `moc-cli` | Luồng mật khẩu cho `make seed`, `make smoke`, các màn demo, CI — không cần trên server thật thì tắt bằng `MOC_CLI_CLIENT_ENABLED=false` |
| Client `svc-workflow` | Tài khoản dịch vụ, quyền `view-users`, đọc danh bạ |
| Đăng nhập trình duyệt (luồng `moc-browser`) | Mật khẩu rồi mã TOTP. Bắt buộc với `clerk`, `manager`, `director`, `tenant_admin`: chưa cài thì Keycloak bắt cài bằng mã QR ngay lần đầu. `staff` chỉ bị hỏi mã nếu đã tự cài |
| Luồng mật khẩu của `moc-cli` (`moc-cli-direct-grant`) | Mật khẩu rồi mã TOTP (tham số `otp`) theo đúng quy tắc của `moc-browser`: không là đường vòng qua xác thực hai bước. Vai trò bắt buộc mà chưa cài TOTP thì không lấy được token (luồng này không cài được). Kịch bản trong `scripts/` tự tính mã từ `MOC_DEMO_TOTP_SECRET` (`moc_env.user_login`), không gửi lại mã đã dùng. Đây cũng là luồng mật khẩu mặc định của cả realm (`directGrantFlow`): client có sẵn `admin-cli` của realm cũng phải kèm mã, kể cả khi đã tắt `moc-cli` |
| Mapper | Claim `https://hasura.io/jwt/claims`: `x-hasura-user-id`, `-tenant-id`, `-department-id`, `-default-role`, `-allowed-roles` |
| User profile | `tenant_id`, `department_id`, `moc_role` (5 vai trò) — chỉ quản trị viên xem và sửa |
| Giao diện đăng nhập (`loginTheme: signet`) | `themes/signet/login/`, trang chung của Văn phòng điện tử, P.A.R.A, Bảng tin. Kế thừa theme `keycloak.v2` có sẵn trong image Keycloak 26 — giữ nguyên template FreeMarker, PatternFly 5, bản dịch tiếng Việt — chỉ thêm `theme.properties` (chỉ chế độ sáng, như Văn phòng điện tử), `resources/css/signet.css` (nhận diện Liền mạch #116: nền, thẻ, ô nhập, nút olive, cỡ trên điện thoại), phông Be Vietnam Pro `resources/fonts/` (trùng từng byte `apps/office/public/fonts/`, kèm `OFL.txt`), logo `resources/img/signet.svg` (trùng từng byte `apps/office/public/favicon.svg`, cũng là biểu tượng tab), biểu tượng đầu trang `resources/img/signet-symbol.svg` và tiêu đề thẻ ngắn "Đăng nhập" ở `messages/`. Tên ở đầu trang là `displayName` của realm. Compose gắn thư mục chỉ đọc vào `/opt/keycloak/themes/signet`; CSP giữ mặc định của Keycloak, CSS không tải gì từ ngoài máy chủ |
| Organizations (`organizationsEnabled`) | Mỗi đơn vị một Organization: alias suy từ mã đơn vị (`CNTT` → `cntt`, `ĐT` → `dt`), thuộc tính `tenant_id` = id trong `core.tenants`; mọi tài khoản có `tenant_id` đó là thành viên (unmanaged) và không thuộc Organization nào khác. Đây là lớp quản lý thành viên và quản trị: gom tài khoản theo đơn vị, chỗ gắn tên miền email hay IdP riêng của đơn vị về sau. **Token vẫn lấy đơn vị từ thuộc tính `tenant_id`** qua mapper ở trên, không đổi: claim `organization` của Keycloak (scope tùy chọn `organization`, client của Signet không xin) là danh sách alias, nằm ngoài namespace `https://hasura.io/jwt/claims` nên Hasura không đọc, và tài khoản thuộc nhiều Organization thì không suy ra được đúng một đơn vị. Tạo bằng `python3 scripts/moc.py tenant create`, kiểm bằng `tenant check`; `make seed` tạo cho hai đơn vị mẫu. Thành viên Organization phải có email (Keycloak từ chối sửa hồ sơ thiếu email) |

Stack dựng trước khi có một ứng dụng (vd `app-ca-nhan`) không có client của ứng dụng đó, vì realm không nạp lại:
`python3 scripts/moc.py realm clients` (`make seed` cũng gọi) thêm các client ứng dụng trên trình duyệt có trong
`moc-realm.json` mà realm đang chạy chưa có, thay `${...}` bằng giá trị trong `.env`. Không sửa client đã có, không
dựng lại `moc-cli`, `svc-workflow` (client dòng lệnh, dịch vụ) nếu quản trị đã gỡ. `--dry-run` chỉ in việc sẽ làm.

Stack dựng từ bản trước F3.12 chưa bật Organizations trong realm (realm không nạp lại): `tenant create` hoặc `make
seed` tự bật (Admin REST, gửi lại nguyên bản realm như trang quản trị), không cần `make reset`.

Stack dựng từ bản mà `moc-cli-direct-grant` chưa hỏi TOTP vẫn giữ luồng cũ, vì realm không nạp lại: `make reset`
(xóa toàn bộ dữ liệu), hoặc trong trang quản trị Keycloak mở Authentication → `moc-cli-direct-grant`, thêm hai
subflow Conditional `moc-cli-otp-bat-buoc`, `moc-cli-otp-tu-chon` sau bước mật khẩu, giống hệt trong
`moc-realm.json`. Tương tự, stack dựng trước khi realm đặt `directGrantFlow`: mở Authentication, ở luồng
`moc-cli-direct-grant` chọn Bind flow → Direct grant flow (không thì `admin-cli` lấy được token chỉ bằng mật khẩu).

Stack dựng trước khi có theme đăng nhập vẫn hiện giao diện mặc định của Keycloak, vì realm không nạp lại: cài bản mới
rồi `docker compose up -d --wait` (container keycloak dựng lại với thư mục theme), sau đó
`python3 scripts/moc.py realm theme` (`--dry-run` chỉ in việc sẽ làm) đặt `loginTheme` của `moc-realm.json` cho realm
đang chạy — chỉ khi realm còn dùng theme mặc định, không đổi theme quản trị đã chọn; Keycloak chưa thấy thư mục theme
thì báo và không đặt. Làm tay: trang quản trị → Realm settings → Themes → Login theme → `signet`.

Sửa tệp trong `themes/` thì dựng lại container: `docker compose up -d --force-recreate --wait keycloak`. Keycloak đọc
CSS mới ngay nhưng trả kèm `Cache-Control: max-age=2592000` (30 ngày) dưới cùng đường dẫn `/resources/<mã>/…`; mã giữ
nguyên qua `docker restart`, đổi khi container dựng lại (đo trên Keycloak thử 26.7.5), nên chỉ dựng lại thì trình
duyệt mới tải bản mới. Nâng cấp (`docker compose down`, `up`) dựng lại sẵn. Nâng Keycloak thì mở lại trang đăng nhập:
theme cha đổi tên lớp hay biến CSS thì phần phủ mất tác dụng (trang vẫn chạy, về giao diện gốc).

Tài khoản mẫu tạo bằng `make seed` (`seed/users.csv`), không nằm trong realm. Các tài khoản văn thư, lãnh đạo,
tổ trưởng, trưởng bộ môn, quản trị được cài sẵn TOTP bằng khóa chung `MOC_DEMO_TOTP_SECRET`; `make totp` in mã
hiện tại và khóa để thêm vào ứng dụng xác thực.
