# gateway — Apache APISIX

APISIX chạy standalone (không etcd, không Admin API): route trong `apisix.yaml`, cấu hình trong `config.yaml`,
giá trị `${{TÊN}}` lấy từ biến môi trường. Đây là cổng duy nhất mở ra ngoài (`MOC_HTTP_PORT`). Chủ: #14.

- Danh sách trắng: `/realms/<realm>/*`, `/resources/*` → Keycloak; `/v1/graphql` → Hasura; `/api/files*`,
  `/api/search` → svc-files; còn lại → giao diện.
- Đường quản trị bị chặn tường minh (404): `/admin`, `/realms/*` khác realm của Mộc, `/console`, `/v1/*`,
  `/v2/*`, `/healthz`, `/flowable-rest/*`.
- Kiểm JWT ở biên (`openid-connect`, chỉ Bearer, khóa qua JWKS nội bộ của Keycloak); Hasura và svc-files
  vẫn kiểm lại. Tiêu đề `X-Hasura-Admin-Secret` từ ngoài vào bị gỡ.
- Mỗi yêu cầu có `X-Request-Id` (giữ nguyên tới sổ kiểm toán).

Sửa route: sửa `apisix.yaml` rồi `docker compose restart apisix`.
