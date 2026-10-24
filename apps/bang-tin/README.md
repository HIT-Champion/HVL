# app-bang-tin — Bảng tin đơn vị

Ứng dụng thứ ba trên lõi Signet, cắm vào bằng **một lệnh** và không sửa tệp nào của lõi:

```bash
python3 scripts/moc.py app install apps/bang-tin/app.yaml      # make app-install APP=apps/bang-tin/app.yaml
python3 scripts/moc.py app remove bang-tin                     # gỡ: route, client, trigger, container; giữ dữ liệu
```

Văn bản vừa vào sổ, vừa phát hành trong đơn vị, cập nhật theo sự kiện của lõi: Hasura Event Trigger trên
`core.app_events` gọi webhook của ứng dụng, phần máy chủ ghi tin vào bảng `bang_tin.tin` bằng danh tính dịch vụ riêng;
trang hỏi lại bảng đó bằng token của người dùng, nên mỗi người chỉ thấy tin của văn bản mình được xem. Cách làm, mô hình
tin cậy và giới hạn: [`docs/them-ung-dung.md`](../../docs/them-ung-dung.md) mục 1.

| Tệp | Nội dung |
|---|---|
| `app.yaml` | Manifest (`scripts/app-manifest.schema.json`): đường `/bang-tin`, image dựng từ thư mục này, schema `bang_tin`, quyền Hasura, danh tính dịch vụ, sự kiện nghe |
| `migrations/0001_tin/up.sql` | Bảng `bang_tin.tin`, chạy bằng vai trò CSDL riêng `moc_appdb_bang_tin` (chỉ làm chủ schema `bang_tin`) |
| `server.py` | Python thư viện chuẩn, không root: trang tĩnh ở `:8080` (CSP `script-src 'self'`, nhật ký không ghi chuỗi truy vấn); webhook `POST /su-kien` ở `:8081` (chỉ trong mạng nội bộ, kiểm header bí mật, trùng là đã ghi, lỗi → 503 để Hasura gửi lại) |
| `public/` | Trang duy nhất; `auth.js` đăng nhập Authorization Code + PKCE (oidc-client-ts, `response_mode=fragment`), `tin.js` câu GraphQL và phần không đụng trình duyệt, `app.js` vẽ danh sách bằng `textContent` |
| `Dockerfile` | `node:24.20.0-slim` lấy bản cho trình duyệt của oidc-client-ts; `python:3.13.16-slim` ghim digest, user 10001 |
| `tests/` | `node --test tests/*.test.js` (câu GraphQL ↔ quyền trong `app.yaml` và của lõi, nhãn ↔ sự kiện nghe); `python3 -m unittest discover -s tests` (máy chủ thật trên cổng ngẫu nhiên, Keycloak và Hasura giả) |

Kiểm cả luồng trên hệ thống đang chạy: `make demo-cai-ung-dung`.
