# app-tai-lieu-api — Tài liệu API

Trang Swagger UI ở `/tai-lieu-api/` để đọc và gọi thử API của Signet ngay trên trình duyệt (#357). Lõi không có giao
diện (chỉ có API sau cổng APISIX), nên trang này là một ứng dụng Tầng 2 như Không gian cá nhân: container riêng ở
mạng `apps`, đăng nhập bằng client Keycloak riêng, "Try it out" gọi lõi qua đúng cổng mà mọi ứng dụng dùng. Nó có
sẵn trong bản cài (profile `app`), không cần lệnh cài thêm.

Hai bộ tài liệu, chọn bằng hai thẻ đầu trang (`?bo=loi`, `?bo=van-phong`):

- **API lõi (Tầng 1)** — tệp, tìm kiếm, hỏi đáp, trạng thái, khóa kiểm mốc neo, API quy trình của ứng dụng
  `/api/workflow/{app}/…`: những đường còn lại khi tắt Văn phòng bằng `MOC_OFFICE_ENABLED=false`.
- **API Văn phòng điện tử (Tầng 2)** — văn bản, sổ đăng ký, hồ sơ và nộp lưu, nạp lô văn bản đến, cổng xác thực:
  chạy chung tiến trình `svc-files` với lõi nhưng thuộc Văn phòng, tắt cùng cờ trên.

API nội bộ (`/actions/…` Hasura gọi, `/ot/notify`) không có trên trang vì không đi qua cổng. GraphQL của Hasura có
schema theo vai trò ở [`docs/api/graphql/`](../../docs/api/graphql/).

## Đăng nhập và gọi thử

Chưa đăng nhập vẫn đọc được cả hai bộ và gọi được các đường không cần token (`/api/status`, `/api/verify/…`). Bấm
"Đăng nhập để gọi thử" thì sang Keycloak (Authorization Code + PKCE, client `app-tai-lieu-api`); đã đăng nhập Văn
phòng điện tử thì không hỏi lại mật khẩu. Token của người dùng được điền sẵn vào ô `HTTPBearer` của nút Authorize,
làm mới theo phiên; đơn vị và vai trò vẫn lấy từ token như mọi ứng dụng khác. Cũng có thể dán token khác vào
Authorize, vd token lấy bằng client `moc-cli`.

`/api/workflow/{app}/…` chỉ nhận token của client `app-{app}` (kiểm `azp`), nên gọi thử từ trang này nhận `403`
`wrong_client`: đúng thiết kế, tài liệu vẫn đọc được.

## Tệp

| Tệp | Nội dung |
|---|---|
| `chia_openapi.py` | Chia `docs/api/openapi/svc-files.json`, `svc-workflow.json` thành `loi.json`, `van-phong.json` theo bảng `GROUPS` (đường → bộ, nhóm); chỉ giữ kiểu dữ liệu được dùng. Đường `/api/…` mới chưa xếp bộ, hay đường trong bảng đã mất, thì dựng image hỏng |
| `server.py` | Python thư viện chuẩn, không root, hệ tệp gốc chỉ đọc: trang tĩnh ở `:8080` (CSP `script-src 'self'; style-src 'self'`, nhật ký không ghi chuỗi truy vấn), `config.json`, `healthz`; tệp OpenAPI không có thì `404` |
| `public/` | `auth.js` đăng nhập khi người dùng bấm (oidc-client-ts, `response_mode=fragment`); `app.js` dựng Swagger UI, điền token, đổi bộ |
| `Dockerfile` | Ba bước: `node:24.20.0-slim` lấy Swagger UI và oidc-client-ts theo `package-lock.json` (`npm ci --ignore-scripts`); `python:3.13.16-slim` chia OpenAPI; image cuối chỉ có trang tĩnh, user 10001 |
| `tests/` | `python3 -m unittest discover -s tests` (máy chủ thật trên cổng ngẫu nhiên; mỗi đường qua cổng ở đúng một bộ, bộ lõi khớp `CORE_API` của `svc-files`, mỗi đường có route APISIX; Dockerfile khớp docker-compose.yml) |

Swagger UI (`swagger-ui-dist`, Apache-2.0) và oidc-client-ts không nằm trong repo: npm cài lúc dựng image, ghim
trong `package-lock.json`, kèm `LICENSE`, `NOTICE` của Swagger UI ở `lib/swagger-ui/`. Trang không gọi CDN nào.

## Dựng và chạy

Image dựng từ thư mục này cùng ngữ cảnh phụ `openapi` (`docs/api/openapi/` trong docker-compose.yml), nên trang luôn
đúng bản OpenAPI trong git của chính bản phát hành:

```bash
docker compose --profile app build app-tai-lieu-api
docker compose --profile core --profile app up -d app-tai-lieu-api
```

Bản cài cũ chưa có client `app-tai-lieu-api` thì `nang_cap.sh` tự thêm (`moc.py realm clients`); chạy tay:
`python3 scripts/moc.py realm clients`.
