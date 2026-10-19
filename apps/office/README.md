# app-office — Văn phòng điện tử

Ứng dụng Tầng 2 trên lõi Mộc: hộp việc, văn bản đến (tiếp nhận, vào sổ, chỉ đạo, phân công, xử lý), văn bản đi
(soạn, trình, duyệt, phát hành), cổng xác thực công khai, thông báo tức thời, dòng thời gian, tìm kiếm. Nuxt 4 ở
chế độ SPA: dựng thành trang tĩnh, nginx phục vụ sau APISIX; mọi dữ liệu lấy qua cổng cùng tên miền —
`/v1/graphql` (Hasura), `/api/*` (svc-files), `/realms/moc` (Keycloak), `/realtime` (Centrifugo, WebSocket). Chủ: #22.

| Thư mục | Nội dung |
|---|---|
| `app/pages/` | `index` (hộp việc), `van-ban-den/` (danh sách, tiếp nhận), `van-ban-di/` (danh sách, soạn), `van-ban/[id]` (chi tiết), `tim-kiem`, `xac-thuc/[[code]]` (công khai, không đăng nhập) |
| `app/composables/` | `useAuth` (OIDC + PKCE, oidc-client-ts), `useApi` (GraphQL, tải tệp, tìm kiếm), `useRealtime` (một kết nối WebSocket tới Centrifugo, tự nối lại, làm mới token), `useNotifications` (chuông thông báo) |
| `app/components/TaskPanel.vue` | Khung xử lý theo `formKey` của BPMN |
| `app/components/NotificationBell.vue` | Chuông: số chưa đọc, 20 tin mới nhất, đánh dấu đã đọc |
| `app/locales/` | Tiếng Việt, tiếng Anh |
| `nginx/` | Cấu hình phục vụ: CSP chặt, `/config.json` đọc realm từ biến môi trường |

- **Quyền** do Hasura và các dịch vụ kiểm; giao diện chỉ đọc vai trò từ token để vẽ menu.
- **Poka-yoke lớp 1**: form kiểm đúng các ràng buộc của CSDL và báo văn bản trùng trước khi lưu.
- **CSP**: chỉ chạy mã của chính trang; các đoạn script nội tuyến Nuxt sinh ra được cho phép theo băm SHA-256
  tính lúc dựng (`scripts/csp-hashes.mjs`), không mở `unsafe-inline`.

## Phát triển

Cần Docker (dựng trong `node:24.20.0-slim`, npm 11 — npm 9/10 lỗi khi cài Nuxt 4.5).

```bash
docker compose --profile app up -d --build app-office    # dựng lại sau khi sửa, ~40 giây
make e2e                                                 # kiểm thử trên trình duyệt thật
```
