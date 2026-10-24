# app-office — Văn phòng điện tử

Ứng dụng Tầng 2 trên lõi Signet: hộp việc, văn bản đến (tiếp nhận, vào sổ, chỉ đạo, phân công, xử lý), văn bản đi
(soạn, trình, duyệt, phát hành), sổ đăng ký in được, cổng xác thực công khai, thông báo tức thời, dòng thời gian,
tìm kiếm. Nuxt 4 ở
chế độ SPA: dựng thành trang tĩnh, nginx phục vụ sau APISIX; mọi dữ liệu lấy qua cổng cùng tên miền —
`/v1/graphql` (Hasura), `/api/*` (svc-files), `/realms/moc` (Keycloak), `/realtime` (Centrifugo, WebSocket). Chủ: #22.

| Thư mục | Nội dung |
|---|---|
| `app/pages/` | `index` (hộp việc), `van-ban-den/` (danh sách, tiếp nhận), `van-ban-di/` (danh sách, soạn), `van-ban/[id]` (chi tiết; tab Dòng thời gian | Lịch sử — dòng sổ kiểm toán về văn bản, F3.5), `tim-kiem` (cả chữ trong tệp PDF, nhãn "Khớp trong nội dung"), `so-dang-ky` (văn thư, lãnh đạo đơn vị: sổ đến / đi theo năm, in PDF), `so-kiem-toan` (lãnh đạo, quản trị đơn vị), `dieu-hanh` (dashboard điều hành, lãnh đạo đơn vị; biểu đồ ECharts qua `app/components/EChart.vue`, kèm bảng số), `so-do` (số đo "sau" theo đặc tả §8, lãnh đạo đơn vị — F4.6, `docs/so-lieu-sau.md`), `gop-y` (góp ý của mình; lãnh đạo, quản trị đơn vị xem thêm tổng hợp của đơn vị), `xac-thuc/[[code]]` (công khai, không đăng nhập) |
| `app/composables/` | `useAuth` (OIDC + PKCE, oidc-client-ts), `useApi` (GraphQL, tải tệp, tìm kiếm, sổ đăng ký), `useRealtime` (một kết nối WebSocket tới Centrifugo, tự nối lại, làm mới token), `useNotifications` (chuông thông báo), `useAuditFormat` (hiện một dòng sổ kiểm toán: nhãn, người làm, trường đã đổi — trang Sổ kiểm toán và tab Lịch sử) |
| `app/components/TaskPanel.vue` | Khung xử lý theo `formKey` của BPMN |
| `scripts/forms.mjs`, `app/utils/forms.ts` | Biên dịch `schemas/*.json` (gốc repo) thành mã kiểm form lúc dựng; quy lỗi về `{trường: mã}` như svc-workflow |
| `tests/` | Test kiểm form trên bộ ca thử dùng chung `schemas/*.cases.json` (`npm test`, Node 24) |
| `app/components/NotificationBell.vue` | Chuông: số chưa đọc, 20 tin mới nhất, đánh dấu đã đọc |
| `app/components/FeedbackButton.vue` | Nút Góp ý trên thanh trên: mức hài lòng 1–5, vài dòng, tự gắn khuôn đường dẫn màn hình đang dùng (`app/utils/feedback.ts`) |
| `app/locales/` | Tiếng Việt, tiếng Anh |
| `nginx/` | Cấu hình phục vụ: CSP chặt, `/config.json` đọc realm từ biến môi trường |

- **Quyền** do Hasura và các dịch vụ kiểm; giao diện chỉ đọc vai trò từ token để vẽ menu.
- **Poka-yoke lớp 1**: form tiếp nhận văn bản đến kiểm theo `schemas/van-ban-den.json` — cùng tệp svc-workflow
  kiểm lại và CSDL chặn bằng ràng buộc (`schemas/README.md`) — và báo văn bản trùng trước khi lưu. Ajv biên dịch
  schema thành mã JavaScript lúc dựng (module ảo `virtual:moc-forms`), nên trình duyệt không cần `unsafe-eval`.
- **CSP**: chỉ chạy mã của chính trang; các đoạn script nội tuyến Nuxt sinh ra được cho phép theo băm SHA-256
  tính lúc dựng (`scripts/csp-hashes.mjs`), không mở `unsafe-inline`.

## Phát triển

Cần Docker (dựng trong `node:24.20.0-slim`, npm 11 — npm 9/10 lỗi khi cài Nuxt 4.5).

```bash
docker compose --profile app up -d --build app-office    # dựng lại sau khi sửa, ~40 giây
npm ci --ignore-scripts && npm test                      # kiểm form theo schemas/ (Node 24, không cần trình duyệt)
make e2e                                                 # kiểm thử trên trình duyệt thật
```

Image dựng từ `apps/office` cộng ngữ cảnh phụ `schemas` (compose tự đưa vào): dựng tay thì
`docker build --build-context schemas=schemas -t moc/app-office apps/office` ở gốc repo.
