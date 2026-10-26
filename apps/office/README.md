# app-office — Văn phòng điện tử

Ứng dụng Tầng 2 trên lõi Signet: hộp việc, văn bản đến (tiếp nhận, vào sổ, chỉ đạo, phân công, xử lý), văn bản đi
(soạn, trình, duyệt, phát hành), sổ đăng ký in được, cổng xác thực công khai, thông báo tức thời, dòng thời gian,
tìm kiếm. Nuxt 4 ở
chế độ SPA: dựng thành trang tĩnh, nginx phục vụ sau APISIX; mọi dữ liệu lấy qua cổng cùng tên miền —
`/v1/graphql` (Hasura), `/api/*` (svc-files), `/realms/moc` (Keycloak), `/realtime` (Centrifugo, WebSocket). Chủ: #22.

| Thư mục | Nội dung |
|---|---|
| `app/pages/` | `index` (hộp việc), `van-ban-den/` (danh sách, tiếp nhận), `van-ban-di/` (danh sách, soạn), `van-ban/[id]` (chi tiết; tab Dòng thời gian | Lịch sử — dòng sổ kiểm toán về văn bản, F3.5), `tim-kiem` (cả chữ trong tệp PDF, nhãn "Khớp trong nội dung"), `so-dang-ky` (văn thư, lãnh đạo đơn vị: sổ đến / đi theo năm, in PDF), `so-kiem-toan` (lãnh đạo, quản trị đơn vị), `dieu-hanh` (dashboard điều hành, lãnh đạo đơn vị; biểu đồ ECharts qua `app/components/EChart.vue`, kèm bảng số; phần văn bản đã nộp lưu đọc từ kho lạnh ở `app/components/ArchiveBoard.vue`, #304), `so-do` (số đo "sau" theo đặc tả §8, lãnh đạo đơn vị — F4.6, `docs/so-lieu-sau.md`), `gop-y` (góp ý của mình; lãnh đạo, quản trị đơn vị xem thêm tổng hợp của đơn vị), `xac-thuc/[[code]]` (công khai, không đăng nhập) |
| `app/composables/` | `useAuth` (OIDC + PKCE, oidc-client-ts), `useApi` (GraphQL, tải tệp, tìm kiếm, sổ đăng ký), `useRealtime` (một kết nối WebSocket tới Centrifugo, tự nối lại, làm mới token), `useNotifications` (chuông thông báo), `useAuditFormat` (hiện một dòng sổ kiểm toán: nhãn, người làm, trường đã đổi — trang Sổ kiểm toán và tab Lịch sử) |
| `app/components/TaskPanel.vue` | Khung xử lý theo `formKey` của BPMN |
| `scripts/forms.mjs`, `app/utils/forms.ts` | Biên dịch `schemas/*.json` (gốc repo) thành mã kiểm form lúc dựng; quy lỗi về `{trường: mã}` như svc-workflow |
| `tests/` | Test kiểm form trên bộ ca thử dùng chung `schemas/*.cases.json` (`npm test`, Node 24) |
| `app/components/NotificationBell.vue` | Chuông: số chưa đọc, 20 tin mới nhất, đánh dấu đã đọc |
| `app/components/FeedbackButton.vue` | Nút Góp ý trên thanh trên: mức hài lòng 1–5, vài dòng, tự gắn khuôn đường dẫn màn hình đang dùng (`app/utils/feedback.ts`) |
| `app/pages/tu-chan-doan.vue`, `app/data/tu-chan-doan.json`, `app/utils/hpdi.ts` | Tự chẩn đoán H-P-D-I cho lãnh đạo (F4.7, `docs/tu-chan-doan.md`): bộ câu kèm JSON Schema (`app/data/tu-chan-doan.schema.json`), cách chấm, bằng chứng đo được từ các view đã có, radar qua `EChart.vue` |
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

## Giao diện Liền mạch

Nhận diện Signet "Liền mạch" (#116): hai nét nối thành chữ S, logo và biểu tượng ở `public/brand/`, biểu tượng tab
`public/favicon.svg` (trang đăng nhập Keycloak dùng bản trùng từng byte). Mọi thông số nằm trong
`app/assets/css/main.css`; thêm màn hình mới thì dùng lại các lớp có sẵn thay vì đặt màu, cỡ chữ riêng.

| Phần | Thông số |
|---|---|
| Màu | Hành động olive `#555b3f` (rê chuột `#42492e`), viền focus `#666d4c` dày 2px cách 3px; thanh bên vàng bơ `#eee3bc` (viền `#e0d3a5`, mục đang mở `#fffdf5`); nền trang `#f4f5f1`, mặt thẻ trắng, chữ `#202820`, chữ phụ `#515b50`, viền `#d9ddd4`, viền ô nhập `#898a79`; nhóm "Cần chú ý" nền `#fffdf6` viền `#cbb57a`; quá hạn `#a02727`. Thang `brand-*`, `stone-*`, `amber-*` của Tailwind chỉnh theo cùng tông |
| Chữ | Be Vietnam Pro 400/500/600/700 tự phục vụ (`public/fonts/`, OFL-1.1), không tải phông ngoài. Thân 16px dòng 1,5; chữ phụ 14px; tiêu đề trang 24px (hộp việc 28px/700); tên việc 17px/600, việc cần chú ý 19px/600; con số dạng tabular |
| Bo góc, khoảng cách | Nhãn 4px, nút và ô nhập 8px, thẻ 12px. Nút, ô nhập cao tối thiểu 44px, nút đệm 8px/14px. Khoảng 8, 12, 16, 24px; hàng việc đệm 20px/24px |
| Khung | Thanh bên 244px thu về dải 76px, mở khi rê chuột vào hoặc focus bằng bàn phím, nằm đè lên nội dung (nội dung không xê dịch), thu lại sau khi chọn trang. Từ 900px trở xuống hoặc màn cảm ứng: ngăn kéo 256px mở bằng nút menu, có lớp phủ, Esc đóng và trả focus, Tab đi vòng trong ngăn kéo. Dưới 640px bảng văn bản thành thẻ xếp dọc, ô nhập chữ 16px |
| Chuyển động | Chỉ diễn tả điều hướng, đổi trạng thái, phản hồi trực tiếp; không hiệu ứng khi cuộn. Trang mới hiện dần, trượt lên 8px trong 260ms, trang cũ gỡ ngay (không lúc nào có hai trang trên màn hình); lọc, xếp lại việc vào 220–280ms, ra 110–140ms; chuông thông báo mở từ góc phải 160–240ms; thông báo tạm trượt vào 200–300ms; nút nhấn lún 1px, thu 0,98. `prefers-reduced-motion: reduce` bỏ hết thời gian chuyển và dịch chuyển, trạng thái vẫn đổi |
