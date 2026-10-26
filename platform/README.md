# platform — cấu hình cho phần mềm nguồn mở

Thư mục này chỉ chứa cấu hình và script khởi động cho các phần mềm nguồn mở mà lõi Signet dùng nguyên bản: image
chính thức, ghim phiên bản và digest trong [`docker-compose.yml`](../docker-compose.yml), danh mục và giấy phép ở
[`DEPENDENCIES.md`](../DEPENDENCIES.md). Không có mã thượng nguồn nào được chép vào đây hay bị sửa. Compose gắn các tệp
vào container ở chế độ chỉ đọc; `make install` chép chúng vào bản cài.

| Thư mục | Phần mềm | Gắn vào container | Nội dung |
|---|---|---|---|
| [`keycloak/`](keycloak/) | Keycloak | `/opt/keycloak/data/import` | Realm `moc`: client, vai trò, mapper, bắt buộc TOTP |
| [`apisix/`](apisix/) | Apache APISIX | `/usr/local/apisix/conf/` | Route danh sách trắng, kiểm JWT, giới hạn tốc độ, nhật ký |
| [`centrifugo/`](centrifugo/) | Centrifugo | `/centrifugo` | Kênh thông báo riêng từng người, kiểm token Keycloak |
| [`openbao/`](openbao/) | OpenBao | `/moc` | Cấu hình máy chủ; `start.sh` khởi tạo, mở khóa két, cấp AppRole, dựng PKI |
| [`monitoring/`](monitoring/) | Prometheus, Grafana | `/etc/prometheus/`, `/etc/grafana/` | Thu chỉ số cổng API, nguồn dữ liệu, bảng điều khiển |
| [`logs/`](logs/) | Vector (profile `logs`) | `/etc/vector/` | Nhận log của 8 dịch vụ qua driver fluentd, tách mã yêu cầu, che lần hai, gửi Parseable; test của bước che; tệp compose phủ đổi driver log ([`docs/van-hanh.md`](../docs/van-hanh.md#log-tập-trung)) |
| [`systemd/`](systemd/) | systemd (trên máy chủ) | không gắn — chép vào `/etc/systemd/system/` | Hẹn giờ chạy `scripts/reconcile.py` mỗi 60 giây |
