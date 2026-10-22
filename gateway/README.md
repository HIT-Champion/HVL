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

## Nhật ký truy cập không có chuỗi truy vấn (F4.4)

APISIX và nginx của giao diện **không ghi chuỗi truy vấn và Referer**. Trang Tìm kiếm, Hỏi đáp đặt câu tìm lên URL
(`/tim-kiem?q=…`, `/api/search?q=…`), bước đăng nhập mang `?code=…&state=…`, còn Referer là URL đầy đủ của trang
trước. Chuỗi truy vấn đã mã hóa phần trăm (`0912%20345%20678`, `ten%40example.com`) nên bộ che thông tin cá nhân của
dịch vụ không nhận ra, và họ tên thì không nhận dạng được — nên bỏ hẳn, không che bằng regex (QĐ-006 trong
[`docs/architecture.md`](../docs/architecture.md)).

APISIX, `config.yaml` khóa `nginx_config`:

```yaml
  http_configuration_snippet: |
    map $request_uri $moc_duong_dan {
        "~^(?<moc_dd>[^?]*)" $moc_dd;
    }
    map $upstream_uri $moc_duong_dan_upstream {
        "~^(?<moc_dd_upstream>[^?]*)" $moc_dd_upstream;
    }
  http:
    access_log_format: '$remote_addr - $remote_user [$time_local] $http_host "$request_method $moc_duong_dan $server_protocol" $status $body_bytes_sent $request_time "$http_user_agent" $upstream_addr $upstream_status $upstream_response_time "$upstream_scheme://$upstream_host$moc_duong_dan_upstream"'
```

- `log_format` của nginx không cắt chuỗi được, nên hai `map` giữ phần trước dấu `?` đầu tiên: của `$request_uri`
  (đường dẫn đúng như client gửi, như phần đường dẫn của `"$request"` cũ) và của `$upstream_uri` (APISIX đã ghép
  `?…` vào). Dòng của `/api/search?q=001205000017` ghi `"GET /api/search HTTP/1.1"`.
- Các trường khác giữ như định dạng mặc định của APISIX 3.18, kể cả đích phía sau
  (`"$upstream_scheme://$upstream_host…"`, có ích khi gỡ lỗi đường đổi hướng như `/realtime`); bỏ `$http_referer`.

nginx của app-office, `apps/office/nginx/default.conf.template` (tệp được include trong khối `http`):

```nginx
map $request_uri $moc_duong_dan {
    "~^(?<moc_dd>[^?]*)" $moc_dd;
}
log_format moc_khong_truy_van '$remote_addr - $remote_user [$time_local] '
                              '"$request_method $moc_duong_dan $server_protocol" '
                              '$status $body_bytes_sent "$http_user_agent" "$http_x_forwarded_for"';
# trong server {}
access_log /var/log/nginx/access.log moc_khong_truy_van;
```

- Đường dẫn lấy từ `$request_uri`, **không** từ `$uri`: `try_files` của ứng dụng một trang đổi `$uri` thành
  `/index.html`. Dòng của `/tim-kiem?q=…` ghi `"GET /tim-kiem HTTP/1.1"`.
- Giữ `$http_x_forwarded_for`: `$remote_addr` của app-office luôn là IP của APISIX, chỉ trường này còn IP người dùng.
- envsubst của image chỉ thay biến môi trường đã khai, nên biến nginx trong tệp giữ nguyên.

svc-files và svc-workflow (uvicorn) bỏ chuỗi truy vấn trong bộ lọc nhật ký: `GET /api/search?… HTTP/1.1`.
`services/svc-files/tests/test_pii_logging.py` kiểm tĩnh hai định dạng trên (chạy được không cần Docker);
`make demo-che-pii` kiểm trên stack thật: có dòng `/api/search`, `/tim-kiem`, không dòng nào còn `?q`.

Giới hạn: `error_log` của APISIX và nginx có định dạng cố định, không bỏ được trường nào — yêu cầu nào làm một plugin
ghi lỗi (token hết hạn khi đang ở trang Tìm kiếm, phía sau lỗi…) thì dòng lỗi vẫn có `request: "GET …?q=…"`. Referer
thì không còn câu tìm: giao diện gửi `Referrer-Policy: strict-origin` nên Referer chỉ là gốc tên miền
(`apps/office/nginx/security-headers.conf`). Gỡ lỗi tìm kiếm thì đọc `core.search` của svc-files
(`q_length`, `hits`, `request_id`). `access_log_format` hay `map` sai cú pháp thì APISIX không khởi động: sau khi sửa,
`docker compose restart apisix` rồi xem `docker compose logs apisix`.
