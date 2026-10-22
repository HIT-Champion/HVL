# Triển khai lên máy chủ (VPS)

Mộc chạy trên một máy chủ Linux bằng Docker Compose, cài ra thư mục riêng (`/opt/moc`) như mục "Cài ra ngoài thư
mục mã nguồn" của [README](../README.md). Trên máy chủ thêm hai thứ so với máy dev:

- **Caddy** nhận HTTPS ở cổng 443 (tự xin và gia hạn chứng thư Let's Encrypt, cổng 80 tự chuyển sang 443) rồi chuyển
  vào APISIX;
- **APISIX chỉ nghe `127.0.0.1`**: từ Internet chỉ vào được qua Caddy. Trang quản trị Keycloak và Grafana vốn đã chỉ
  nghe `127.0.0.1`, xem từ xa qua đường hầm SSH.

```
Internet ──443/80──▶ Caddy (máy chủ) ──▶ 127.0.0.1:8080 APISIX ──▶ giao diện, Keycloak, Hasura, svc-files, …
                                         (mạng nội bộ Docker, không cổng nào khác mở ra ngoài)
```

Đã diễn tập ngày 22/10/2026 trên một máy Ubuntu (chưa phải VPS): bước 3–4 đúng như dưới (`.env` máy chủ, `make
install` ra thư mục riêng, chạy từ đó), một proxy TLS ở cổng 443 đặt các tiêu đề như Caddyfile ở bước 5 (nginx với
chứng thư tự ký, thay cho Caddy và Let's Encrypt), rồi qua `https://`: các mục kiểm ở bước 6, smoke, 13 kịch bản e2e
trên trình duyệt, màn kiểm dịch, ký số, che thông tin cá nhân, kiểm sổ kiểm toán. Chưa diễn tập: bước 2 (máy diễn tập
đã có Docker), Caddy, Let's Encrypt thật — xem mục 8.

## 1. Chuẩn bị

| Thứ cần | Tối thiểu | Ghi chú |
|---|---|---|
| Máy chủ | Ubuntu 24.04 LTS, 4 vCPU, 8 GB RAM, 40 GB đĩa | Cả hệ thống dùng khoảng 3,5 GB RAM khi chạy (đo lúc diễn tập, chưa bật mô hình); các image khoảng 2,3 GB, lúc dựng cần thêm chỗ cho image nền và bộ đệm. Bật mô hình ngôn ngữ (profile `ai`, F4.1–F4.2) thì cần 16 GB |
| Tên miền | một bản ghi A trỏ về IP máy chủ | vd `moc.example.vn`; có IPv6 thì thêm bản ghi AAAA. Let's Encrypt cần cổng 80 và 443 mở |
| Tài khoản | SSH vào được, có `sudo` | Các bước cài phần nền cần `sudo`; Mộc chạy bằng người dùng `moc` |

Đặt tên miền trước: Let's Encrypt chỉ cấp chứng thư khi tên miền đã trỏ đúng IP (`dig +short moc.example.vn`).

## 2. Cài phần nền (một lần, cần `sudo`)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl git make python3 caddy ufw

# Docker Engine + plugin compose + buildx từ kho của Docker, theo docs.docker.com/engine/install/ubuntu
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt update && sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
docker --version && docker compose version     # cần Docker ≥ 24.0, compose ≥ 2.20

# Người vận hành moc: chạy Mộc, sao lưu, reconciler. Nhóm docker có quyền ngang root trên máy — chỉ người vận hành
sudo adduser --disabled-password --gecos "" moc
sudo usermod -aG docker moc
sudo install -d -o moc -g moc /opt/moc /var/backups/moc     # thư mục cài, kho sao lưu (để trống)

# Tường lửa: chỉ SSH, HTTP, HTTPS
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw enable
```

Docker tự mở cổng của container mà **không qua ufw**, nên chặn bằng tường lửa không đủ: cổng của APISIX phải gắn vào
`127.0.0.1` ở bước 3. Các cổng khác của Mộc (Keycloak quản trị 8180, Grafana 3300) đã chỉ nghe `127.0.0.1`.

Máy 8 GB nên thêm 4 GB swap cho lần dựng image đầu tiên:
`sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile` (thêm
`/swapfile none swap sw 0 0` vào `/etc/fstab` để giữ sau khi khởi động lại).

## 3. Lấy mã nguồn và cấu hình

Từ đây chạy bằng người dùng `moc` (`sudo -iu moc`).

```bash
git clone https://github.com/HIT-Champion/HVL.git ~/HVL
cd ~/HVL
make env          # sinh .env, mọi mật khẩu ngẫu nhiên
```

Sửa bốn dòng trong `.env` (thay `moc.example.vn` bằng tên miền thật):

```bash
sed -i -e 's#^MOC_PUBLIC_URL=.*#MOC_PUBLIC_URL=https://moc.example.vn#' \
       -e 's#^MOC_HTTP_PORT=.*#MOC_HTTP_PORT=127.0.0.1:8080#' \
       -e 's#^MOC_TRUSTED_PROXY=.*#MOC_TRUSTED_PROXY=172.16.0.0/12#' \
       -e 's#^MOC_BACKUP_DIR=.*#MOC_BACKUP_DIR=/var/backups/moc#' .env
grep -E '^MOC_(PUBLIC_URL|HTTP_PORT|TRUSTED_PROXY|BACKUP_DIR)=' .env     # đủ bốn dòng, đúng giá trị
make check
```

- `MOC_PUBLIC_URL` là địa chỉ người dùng gõ, có `https://`, không có `/` cuối. Keycloak, mã QR trên văn bản đi, thông
  báo realtime đều theo địa chỉ này. **Đổi sau khi đã chạy** thì realm Keycloak đã nạp vẫn giữ địa chỉ cũ — đặt đúng
  ngay từ đầu.
- `MOC_HTTP_PORT=127.0.0.1:8080`: APISIX chỉ nghe trên máy chủ, Caddy chuyển vào đây.
- `MOC_TRUSTED_PROXY=172.16.0.0/12`: APISIX chỉ tin `X-Forwarded-Proto`, `-Host`, `-Port`, `-For` của yêu cầu tới từ dải
  này. Caddy tới APISIX qua cổng `127.0.0.1:8080`, Docker chuyển vào container từ gateway của mạng Docker (thường
  `172.x.0.1`). Thiếu dòng này thì Keycloak tưởng người dùng đang ở `http://`, trình duyệt chặn lần đăng nhập, và mọi
  người dùng chung một bộ đếm giới hạn tốc độ. Docker của máy chủ đặt dải mạng khác (`default-address-pools` trong
  `/etc/docker/daemon.json`) thì đặt đúng dải đó — bước 6 có lệnh kiểm.
- Máy demo công khai: giữ `MOC_CLI_CLIENT_ENABLED=true` để `seed.py`, `smoke.py` chạy được; muốn xem nhắc hạn ngay khi
  demo thì `MOC_SLA_DURATION=PT1M` (mặc định `PT24H`). Máy có dữ liệu thật: `MOC_CLI_CLIENT_ENABLED=false`, không chạy
  `seed.py`, `smoke.py` (cả hai ghi dữ liệu thử vào hệ thống).
- **Chép `.env` ra ngoài máy chủ ngay** (trình quản lý mật khẩu của đội): `MOC_BACKUP_PASSWORD` mở kho sao lưu,
  `MOC_OPENBAO_SEAL_KEY` mở két — mất là mất bản sao lưu và tệp văn bản hạn chế. Cất bản chép này ở chỗ khác với kho
  sao lưu.

## 4. Cài và chạy

```bash
cd ~/HVL
make install PREFIX=/opt/moc                    # dựng image của đội (lần đầu lâu), chép sang /opt/moc
cd /opt/moc
docker compose up -d --wait --wait-timeout 900  # lần đầu ClamAV tải chữ ký, vài phút
docker compose ps                               # mọi dịch vụ healthy
python3 scripts/seed.py                         # chỉ máy demo: 2 đơn vị, 10 tài khoản, văn bản mẫu
```

Từ đây mọi lệnh vận hành chạy trong `/opt/moc` bằng `python3 scripts/…` và `docker compose …` (bản cài không có
`Makefile`): `make smoke` thành `python3 scripts/smoke.py`, `make demo-kiem-dich` thành `python3 scripts/demo.py
kiem-dich`, `make totp` thành `python3 scripts/totp.py`.

## 5. HTTPS bằng Caddy

Thay toàn bộ `/etc/caddy/Caddyfile` (cần `sudo`):

```
moc.example.vn {
	reverse_proxy 127.0.0.1:8080 {
		header_up X-Forwarded-Port 443
	}
}
```

```bash
sudo systemctl reload caddy
sudo journalctl -u caddy -n 30 --no-pager       # thấy "certificate obtained successfully"
```

Caddy tự đặt `X-Forwarded-For` (IP người dùng), `X-Forwarded-Proto: https`, `X-Forwarded-Host`, giữ nguyên `Host` và
chuyển được WebSocket (thông báo realtime). Riêng `X-Forwarded-Port` Caddy không gửi, mà thiếu nó thì APISIX điền cổng
của chính nó (9080) và Keycloak trả địa chỉ `https://moc.example.vn:9080/…` cho bước lấy token — dòng `header_up` ở
trên là để chặn việc đó. Không giới hạn cỡ yêu cầu ở Caddy: APISIX chặn trên 64 MB, `svc-files` chặn theo
`MOC_FILES_MAX_MB`.

## 6. Kiểm sau khi lên

```bash
cd /opt/moc
python3 scripts/smoke.py                # máy demo: luồng chính qua đúng địa chỉ https công khai
python3 scripts/moc.py audit verify     # sổ kiểm toán nguyên vẹn
python3 scripts/demo.py kiem-dich       # một màn demo bất kỳ (docs/demo-script.md)
curl -sI https://moc.example.vn/admin/ | head -1                      # phải bị chặn (404)
curl -s https://moc.example.vn/realms/moc/.well-known/openid-configuration \
  | grep -oE '"(issuer|token_endpoint)":"[^"]*"'
docker compose logs --tail 3 apisix                                   # cột đầu: IP của người vừa gọi
```

- `issuer` và `token_endpoint` đều phải bắt đầu bằng `https://moc.example.vn/realms/moc`. `issuer` sai (`http://…`,
  `localhost`) là `MOC_PUBLIC_URL` sai; chỉ `token_endpoint` sai (`http://…` hay có `:9080`) là `MOC_TRUSTED_PROXY`
  chưa khớp dải mạng Docker, hoặc Caddyfile thiếu dòng `header_up`.
- Cột đầu dòng nhật ký APISIX phải là IP thật của máy vừa gọi `curl`. Ra `172.x.0.1` là `MOC_TRUSTED_PROXY` chưa khớp:
  lấy gateway thật bằng `docker inspect $(docker compose ps -q apisix) --format '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}'`, sửa
  `/opt/moc/.env` rồi `docker compose up -d apisix`.
- Mở `https://moc.example.vn` trên trình duyệt, đăng nhập `vanthu` (mật khẩu `MOC_DEMO_PASSWORD`, mã TOTP từ
  `python3 scripts/totp.py`). Tài khoản cho giám khảo: `giamkhao` (chuyên viên, không cần TOTP).
- Phát hành một văn bản đi rồi **quét mã QR trên bản PDF bằng điện thoại thật** → "khớp" (điều kiện của Phase 2).

## 7. Vận hành

**Xem trang quản trị** từ máy mình qua đường hầm SSH:
`ssh -L 8180:127.0.0.1:8180 -L 3300:127.0.0.1:3300 moc@moc.example.vn`, rồi mở `http://127.0.0.1:8180/admin`
(Keycloak, tài khoản `KEYCLOAK_ADMIN_*`) và `http://127.0.0.1:3300` (Grafana).

**Sao lưu hằng đêm** (`crontab -e` của người dùng `moc`):

```
15 2 * * * cd /opt/moc && python3 scripts/moc.py backup create --keep 14 >> $HOME/sao-luu.log 2>&1
```

Kho ở `/var/backups/moc` vẫn nằm trên cùng máy chủ: chép thêm ra ngoài (`rsync -a /var/backups/moc/ máy-khác:…`;
kho chỉ gồm tệp đã mã hóa). Diễn tập khôi phục: README mục "Sao lưu và khôi phục".

**Tự phục hồi và GitOps** (tùy chọn): README mục "GitOps và tự phục hồi" — systemd timer `ops/systemd/` chạy
`reconcile.py` mỗi 60 giây (đúng `User=moc`, `WorkingDirectory=/opt/moc` như ở đây). Muốn commit mới trên nhánh
`deploy` tự được cài lại thì làm thêm một bản sao riêng của reconciler (`/opt/moc-src`, nhánh `deploy`) và đặt
`MOC_GITOPS_DIR` như README — không dùng chung `~/HVL`.

**Nâng cấp tay** (không dùng GitOps):

```bash
cd /opt/moc && python3 scripts/moc.py backup create     # sao lưu trước
cd ~/HVL && git pull
cd /opt/moc && docker compose down
cd ~/HVL && make install PREFIX=/opt/moc         # giữ .env của bản cài, chỉ đổi MOC_VERSION
cd /opt/moc && docker compose up -d --wait --wait-timeout 900
```

Biến `.env` mới của bản mới (CHANGELOG ghi rõ) thêm vào `/opt/moc/.env`. **Không chạy `make reset` hay
`docker compose down -v` trên máy chủ**: xóa sạch dữ liệu, kể cả két (tệp văn bản hạn chế không mở được nữa).

**Mô hình ngôn ngữ** (tùy chọn, máy 16 GB): `docker compose --profile ai-pull run --rm ollama-pull` (tải trọng số
khoảng 2 GB, một lần) rồi `docker compose --profile ai up -d --wait ollama`.

## 8. Giới hạn đã biết

- **Chưa chạy trên VPS thật**: đã diễn tập đủ các bước trên một máy (xem đầu tài liệu) với chứng thư tự ký và nginx
  đóng vai Caddy; chưa xin chứng thư Let's Encrypt thật, chưa đo trên máy 8 GB.
- **Chỉ đoạn trình duyệt ↔ Caddy có TLS.** Các dịch vụ gọi nhau bằng HTTP trong mạng Docker (APISIX → Keycloak, các
  dịch vụ → OpenBao, …). Mạng này không mở ra ngoài, nhưng một container bị chiếm quyền thì thấy được lưu lượng chưa
  mã hóa trong đó.
- **`MOC_TRUSTED_PROXY=172.16.0.0/12` tin mọi container trên máy**: container nào cũng gửi được `X-Forwarded-For`
  giả để né giới hạn tốc độ đăng nhập. Muốn hẹp hơn thì đặt đúng gateway lấy ở bước 6 (`172.x.0.1/32`).
- **Hasura nối CSDL bằng `POSTGRES_USER`**, là siêu người dùng của Postgres. Quyền theo vai trò nằm ở metadata Hasura
  (trang metadata bị chặn ở APISIX), chưa có vai trò CSDL riêng quyền hẹp.
- **Mọi tài khoản mẫu của `seed.py` dùng chung `MOC_DEMO_PASSWORD`.** Hợp với máy demo; máy có dữ liệu thật thì không
  chạy `seed.py` (bước 3).
- **GitOps không kiểm chữ ký commit**: ai đẩy được lên nhánh `deploy` là cài được lên máy chủ.
- **Image ghim theo tag**, chỉ PostGIS và Ollama ghim thêm digest: một tag bị đẩy lại thì lần kéo sau nhận image khác.
