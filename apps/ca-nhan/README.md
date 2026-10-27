# app-ca-nhan — Không gian cá nhân P.A.R.A

Ứng dụng thứ hai trên lõi Signet: mỗi người một chỗ cất tệp của riêng mình trong bốn thư mục Dự án, Lĩnh vực, Tài
nguyên, Lưu trữ; tải lên, chuyển thư mục, tải về. Thêm vào mà không sửa mã của lõi — các bước và bằng chứng ở
[`docs/them-ung-dung.md`](../../docs/them-ung-dung.md). Trang tĩnh JavaScript thuần (không bước biên dịch), nginx
phục vụ ở `/ca-nhan/` sau APISIX; mọi dữ liệu lấy qua cổng cùng tên miền — `/realms/moc` (Keycloak, client
`app-ca-nhan`), `/v1/graphql` (Hasura, bảng `personal.items`), `/api/files` (svc-files: ClamAV, kho tệp).

| Tệp | Nội dung |
|---|---|
| `public/index.html`, `style.css` | Trang duy nhất; màu Liền mạch như Văn phòng điện tử, trên điện thoại bảng thành thẻ |
| `fonts/be-vietnam-pro/` (chỉ trong image) | Phông Be Vietnam Pro tự phục vụ (OFL-1.1, kèm `OFL.txt`): Dockerfile lấy từ gói npm `@fontsource/be-vietnam-pro` như Văn phòng, repo không chứa tệp phông (#305); `index.html` nạp `be-vietnam-pro.css` trước `style.css`; không gọi Google Fonts |
| `public/app.js` | Vẽ thư mục, danh sách, tải lên → xếp vào thư mục đang mở, chuyển, tải về; chữ gán bằng `textContent` |
| `public/auth.js` | Đăng nhập Authorization Code + PKCE bằng oidc-client-ts (bản cho trình duyệt, `lib/`), cùng phiên SSO với Văn phòng điện tử; token trong `sessionStorage` |
| `public/api.js` | Gọi GraphQL, `POST /api/files` (có tiến độ), `GET /api/files/{id}`; lỗi thành câu đọc được |
| `public/i18n.js` | Bảng dịch vi/en (#306), ngôn ngữ lưu ở `localStorage` khóa `moc.locale` chung với Văn phòng điện tử; `localize()` gán chữ cho phần tử mang `data-i18n` và đặt `<html lang>` |
| `public/para.js` | Phần không đụng trình duyệt: bốn thư mục, câu GraphQL, định dạng cỡ và giờ, câu báo lỗi, đọc claim |
| `nginx/` | `/ca-nhan/config.json` (realm từ biến môi trường), CSP `script-src 'self'`, nhật ký không ghi chuỗi truy vấn |
| `tests/` | `npm test` (`node --test`, Node 22+, không cần `npm ci`): đối chiếu thư mục với ràng buộc CSDL, câu GraphQL với quyền Hasura, client realm, route, compose; logic của `para.js`, `api.js`; bảng dịch (`i18n.test.js`: không chữ tiếng Việt viết cứng ngoài bảng, hai bảng cùng khóa) |

Chạy: `make up` (service `app-ca-nhan` trong profile `app`), mở `${MOC_PUBLIC_URL}/ca-nhan/`; kiểm cả luồng qua cổng:
`make demo-ca-nhan`. Bản cài dựng trước khi có ứng dụng này: `python3 scripts/moc.py realm clients` thêm client.
