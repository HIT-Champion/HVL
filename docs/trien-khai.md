# Triển khai lên máy chủ (VPS)

Signet chạy trên một máy chủ Linux bằng Docker Compose, cài ra thư mục riêng (`/opt/moc`) như mục "Cài ra ngoài thư
mục mã nguồn" của [README](../README.md). Trên máy chủ thêm hai thứ so với máy dev:

- **Caddy** nhận HTTPS ở cổng 443 (tự xin và gia hạn chứng thư Let's Encrypt, cổng 80 tự chuyển sang 443) rồi chuyển
  vào APISIX;
- **APISIX chỉ nghe `127.0.0.1`**: từ Internet chỉ vào được qua Caddy. Trang quản trị Keycloak và Grafana vốn đã chỉ
  nghe `127.0.0.1`, xem từ xa qua đường hầm SSH.

Máy không có IP công khai (laptop, máy ở nhà): thay Caddy bằng Cloudflare Tunnel — mục 5b.

```
Internet ──443/80──▶ Caddy (máy chủ) ──▶ 127.0.0.1:8080 APISIX ──▶ giao diện, Keycloak, Hasura, svc-files, …
                                         (mạng nội bộ Docker, không cổng nào khác mở ra ngoài)
```

Đã diễn tập ngày 22/10/2026 trên một máy Ubuntu (chưa phải VPS): bước 3–4 đúng như dưới (`.env` máy chủ, `make
install` ra thư mục riêng, chạy từ đó), một proxy TLS ở cổng 443 đặt các tiêu đề như Caddyfile ở bước 5 (nginx với
chứng thư tự ký, thay cho Caddy và Let's Encrypt), rồi qua `https://`: các mục kiểm ở bước 6, smoke, 13 kịch bản e2e
trên trình duyệt, màn kiểm dịch, ký số, che thông tin cá nhân, kiểm sổ kiểm toán. Chưa diễn tập: bước 2 (máy diễn tập
đã có Docker), Caddy, Let's Encrypt thật — xem mục 8. Phần `https` của CI (#261) chạy lại trên mọi pull request:
`.env` như bước 3, proxy như bước 5 (nginx với chứng thư tự ký thay Caddy), rồi smoke và `kiem_ban_online.py` của
bước 6.

## 1. Chuẩn bị

| Thứ cần | Tối thiểu | Ghi chú |
|---|---|---|
| Máy chủ | Ubuntu 24.04 LTS, 4 vCPU, 8 GB RAM, 40 GB đĩa | Cả hệ thống dùng khoảng 3,5 GB RAM khi chạy (đo lúc diễn tập, chưa bật mô hình); các image khoảng 2,3 GB, lúc dựng cần thêm chỗ cho image nền và bộ đệm. Bật mô hình ngôn ngữ (profile `ai`, F4.1–F4.2) thì cần 16 GB |
| Tên miền | một bản ghi A trỏ về IP máy chủ | vd `moc.example.vn`; có IPv6 thì thêm bản ghi AAAA. Let's Encrypt cần cổng 80 và 443 mở. Cloudflare Tunnel (mục 5b): không cần IP công khai, tên miền dùng nameserver của Cloudflare |
| Tài khoản | SSH vào được, có `sudo` | Các bước cài phần nền cần `sudo`; Signet chạy bằng người dùng `moc` |

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
docker --version && docker compose version     # cần Docker ≥ 24.0, compose ≥ 2.17

# Người vận hành moc: chạy Signet, sao lưu, reconciler. Nhóm docker có quyền ngang root trên máy — chỉ người vận hành
sudo adduser --disabled-password --gecos "" moc
sudo usermod -aG docker moc
sudo install -d -o moc -g moc /opt/moc /var/backups/moc     # thư mục cài, kho sao lưu (để trống)

# Tường lửa: chỉ SSH, HTTP, HTTPS
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw enable
```

Docker tự mở cổng của container mà **không qua ufw**, nên chặn bằng tường lửa không đủ: cổng của APISIX phải gắn vào
`127.0.0.1` ở bước 3. Các cổng khác của Signet (Keycloak quản trị 8180, Grafana 3300) đã chỉ nghe `127.0.0.1`.

Máy 8 GB nên thêm 4 GB swap cho lần dựng image đầu tiên:
`sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile` (thêm
`/swapfile none swap sw 0 0` vào `/etc/fstab` để giữ sau khi khởi động lại).

## 2b. Máy không kéo được image từ Docker Hub

Phần lớn image của Signet lấy từ Docker Hub (`docker.io`): 17 image trong `docker-compose.yml` và 4 image nền mà các
Dockerfile của đội dựng lên (`node`, `python`, `nginxinc/nginx-unprivileged`, `apache/apisix`). Mạng chặn Docker Hub,
hay đã hết lượt tải ẩn danh của Docker Hub (lỗi `toomanyrequests`), thì `make up`, `make install` và
`scripts/nang_cap.sh` dừng ở bước kéo hoặc dựng image. Cách xử lý: cho Docker kéo các image này qua `mirror.gcr.io`, bản
sao Docker Hub của Google.

Tạo hoặc sửa `/etc/docker/daemon.json` (cần `sudo`; người cài tự làm, Signet không sửa cấu hình Docker của máy) cho có
khóa `registry-mirrors`. Tệp đã có nội dung thì chỉ thêm khóa này, giữ JSON hợp lệ:

```json
{
  "registry-mirrors": ["https://mirror.gcr.io"]
}
```

```bash
sudo systemctl reload docker                             # nạp lại cấu hình, container đang chạy không bị dừng
docker info --format '{{json .RegistryConfig.Mirrors}}'  # phải có "https://mirror.gcr.io/"
```

Docker chỉ dùng mirror cho image của Docker Hub: thử mirror trước, mirror không có thì quay về Docker Hub. Bộ dựng mặc
định của Docker Engine (BuildKit chạy trong dockerd) cũng đọc `registry-mirrors`, nên `make up` dựng image của đội vẫn
kéo image nền qua mirror. Đã đổi sang builder `docker-container` (`docker buildx create --use …`) thì builder đó không
đọc `daemon.json`: khai mirror trong `buildkitd.toml` của nó
([Configure BuildKit](https://docs.docker.com/build/buildkit/configure/#registry-mirror)). Mọi image đều ghim theo
digest (`@sha256:…`), Docker kiểm nội dung tải về theo digest, nên mirror không tráo được image.

Ngày 26/10/2026 đã kiểm: cả 21 image ghim đều có trên `mirror.gcr.io`, đủ mọi lớp của bản `linux/amd64`. `mirror.gcr.io`
chỉ giữ các image được kéo nhiều, nên khi cài một phiên bản khác hãy kiểm lại bằng lệnh dưới. Lệnh chỉ đọc manifest,
không kéo image; chạy trong thư mục mã nguồn (bản clone hay gói phát hành đã giải nén), nơi `make up`, `make install`
dựng image:

```bash
grep -hoE '(image:|FROM) +[a-z][^ ]*@sha256:[0-9a-f]{64}' docker-compose.yml */*/Dockerfile \
  | awk '{print $2}' | sort -u | grep -vE '^(quay|ghcr)\.io/' | while read -r ref; do
    repo=${ref%%[:@]*}; [[ $repo == */* ]] || repo=library/$repo
    docker buildx imagetools inspect "mirror.gcr.io/$repo@${ref#*@}" >/dev/null 2>&1 && echo "có    $ref" ||
      echo "THIẾU $ref"
  done
```

Có dòng `THIẾU` thì mirror chưa giữ image đó: dùng một mirror Docker Hub khác mà máy cài vào được (của trường, của
công ty), hoặc mở Docker Hub cho lần cài ấy.

Ngoài Docker Hub, lần cài đầu còn tải từ các nguồn sau, mirror trên không thay được:

- `quay.io` (Keycloak, Parseable) và `ghcr.io` (coraza-proxy-wasm, lớp WAF dựng vào image APISIX);
- lúc dựng image của đội: gói npm (`registry.npmjs.org`), gói Python (`pypi.org`, `files.pythonhosted.org`), gói Debian
  của svc-files (`deb.debian.org`);
- lúc chạy: ClamAV tải chữ ký virus (`database.clamav.net`). Khi bật profile `ai-pull`, mô hình ngôn ngữ tải từ thư
  viện Ollama (`registry.ollama.ai`).

## 3. Lấy mã nguồn và cấu hình

Từ đây chạy bằng người dùng `moc` (`sudo -iu moc`).

```bash
git clone https://github.com/HIT-Champion/Signet.git ~/Signet
cd ~/Signet
make env          # sinh .env, mọi mật khẩu ngẫu nhiên
```

Sửa bốn dòng trong `.env` (thay `moc.example.vn` bằng tên miền thật):

```bash
sed -i -e 's#^MOC_PUBLIC_URL=.*#MOC_PUBLIC_URL=https://moc.example.vn#' \
       -e 's#^MOC_HTTP_PORT=.*#MOC_HTTP_PORT=127.0.0.1:8080#' \
       -e 's#^MOC_TRUSTED_PROXY=.*#MOC_TRUSTED_PROXY=auto#' \
       -e 's#^MOC_BACKUP_DIR=.*#MOC_BACKUP_DIR=/var/backups/moc#' .env
grep -E '^MOC_(PUBLIC_URL|HTTP_PORT|TRUSTED_PROXY|BACKUP_DIR)=' .env     # đủ bốn dòng, đúng giá trị
make check
```

- `MOC_PUBLIC_URL` là địa chỉ người dùng gõ, có `https://`, không có `/` cuối. Keycloak, mã QR trên văn bản đi, thông
  báo realtime đều theo địa chỉ này. **Đổi sau khi đã chạy** thì realm Keycloak đã nạp vẫn giữ địa chỉ cũ — đặt đúng
  ngay từ đầu.
- `MOC_HTTP_PORT=127.0.0.1:8080`: APISIX chỉ nghe trên máy chủ, Caddy chuyển vào đây.
- `MOC_TRUSTED_PROXY=auto`: APISIX chỉ tin `X-Forwarded-Proto`, `-Host`, `-Port`, `-For` của yêu cầu tới từ dải của
  mạng Docker `moc`. Caddy tới APISIX qua cổng `127.0.0.1:8080`, Docker chuyển vào container từ gateway của mạng này.
  Thiếu dòng này thì Keycloak tưởng người dùng đang ở `http://`, trình duyệt chặn lần đăng nhập, và mọi người dùng chung
  một bộ đếm giới hạn tốc độ.
  - Lúc khởi động, APISIX đọc dải từ route mặc định của chính nó (`platform/apisix/kiem-moi-truong.sh`). Docker tạo lại
    mạng với dải khác (`make down`, nâng cấp) thì giá trị vẫn đúng.
  - Mạng `apps` của container ứng dụng là internal, không có route mặc định, nên không bao giờ được tin.
  - Không đọc được route thì APISIX dừng, báo lỗi ở `docker compose logs apisix`.
  - Đặt một dải cụ thể (vd `172.16.0.0/12`) vẫn được, nhưng dải đó phải khớp mạng sau mỗi lần tạo lại (mục 8).
- Máy demo công khai: giữ `MOC_CLI_CLIENT_ENABLED=true` để `seed.py`, `smoke.py` chạy được; muốn xem nhắc hạn ngay khi
  demo thì `MOC_SLA_DURATION=PT1M` (mặc định `PT24H`). Máy có dữ liệu thật: `MOC_CLI_CLIENT_ENABLED=false`, không chạy
  `seed.py`, `smoke.py` (cả hai ghi dữ liệu thử vào hệ thống).
- **Chép `.env` ra ngoài máy chủ ngay** (trình quản lý mật khẩu của đội): `MOC_BACKUP_PASSWORD` mở kho sao lưu,
  `MOC_OPENBAO_SEAL_KEY` mở két — mất là mất bản sao lưu và tệp văn bản hạn chế. Cất bản chép này ở chỗ khác với kho
  sao lưu.

## 4. Cài và chạy

```bash
cd ~/Signet
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

## 5b. Hoặc: Cloudflare Tunnel (máy không có IP công khai)

Máy ở nhà, laptop, máy sau NAT không nhận được kết nối từ Internet: thay Caddy bằng Cloudflare Tunnel. Dịch vụ
`cloudflared` (profile `tunnel`, tắt mặc định) gọi ra Cloudflare, nhận yêu cầu của tên miền — HTTPS do Cloudflare lo —
rồi chuyển vào APISIX qua mạng Docker. Máy không mở cổng nào, không cần Caddy, ufw không phải mở 80/443. Cần tên miền
đã chuyển nameserver sang Cloudflare (gói Free được).

```
Internet ──HTTPS──▶ Cloudflare ◀── đường hầm (cloudflared gọi ra) ── cloudflared ──▶ apisix:9080 ──▶ …
```

1. Trên Cloudflare (Zero Trust → Networks → Tunnels): Create a tunnel → Cloudflared, đặt tên (vd `signet`). Ở bước
   cài, chép chuỗi token sau `--token` — không cần chạy lệnh cài của Cloudflare. Thêm route **Public hostname** (giao
   diện mới gọi là Published application): hostname (vd `signet.example.vn`), Service **HTTP**, URL **`apisix:9080`**.
   Trang này chỉ cho đi tiếp khi tunnel đã kết nối: làm bước 2–4 rồi quay lại thêm route.
2. Lưu token ra tệp ngoài repo, chỉ người vận hành đọc được (lệnh hỏi token, không để lại trong lịch sử shell):

   ```bash
   read -rsp "Token: " t && (umask 077 && printf 'TUNNEL_TOKEN=%s\n' "$t" > /home/moc/cloudflared-tunnel); unset t
   ```

3. Bước 3 ở trên, thay bộ `sed` bằng:

   ```bash
   sed -i -e 's#^MOC_PUBLIC_URL=.*#MOC_PUBLIC_URL=https://signet.example.vn#' \
          -e 's#^MOC_HTTP_PORT=.*#MOC_HTTP_PORT=127.0.0.1:8080#' \
          -e 's#^MOC_TRUSTED_PROXY=.*#MOC_TRUSTED_PROXY=auto#' \
          -e 's#^MOC_EXTRA_PROFILES=.*#MOC_EXTRA_PROFILES=tunnel#' \
          -e 's#^MOC_BACKUP_DIR=.*#MOC_BACKUP_DIR=/var/backups/moc#' .env
   ```

   Token để chỗ khác thì đặt thêm `MOC_TUNNEL_TOKEN_FILE`. `.env` cũ chưa có hai biến `MOC_EXTRA_PROFILES`,
   `MOC_TUNNEL_TOKEN_FILE` thì thêm tay (mẫu ở `.env.example`).
4. Bước 4 như trên. `make install` ghi `COMPOSE_PROFILES=core,app,tunnel` vào `/opt/moc/.env`, nên `docker compose up
   -d --wait` trong `/opt/moc` dựng cả `cloudflared`; trong thư mục mã nguồn `make up`, `make down`, `make ps` cũng
   kèm profile `tunnel`. Kiểm: `docker compose logs cloudflared | grep -c 'Registered tunnel connection'` ra 4.

Bỏ qua bước 5. `cloudflared` tới APISIX từ một địa chỉ trong mạng Docker `moc` nên `MOC_TRUSTED_PROXY=auto` như với
Caddy.
Cloudflare gửi `X-Forwarded-Proto: https` và `X-Forwarded-For` (IP người dùng) nhưng không gửi `X-Forwarded-Port`:
APISIX tự lấy 443 cho các route của Keycloak (`map` `moc_cong_chuyen_tiep` trong `platform/apisix/config.yaml`), không thì
Keycloak trả địa chỉ token `https://…:9080/…` và trình duyệt không đăng nhập được. Bước 6 kiểm như với Caddy, thay
`moc.example.vn` bằng tên miền của tunnel. Tắt tunnel: bỏ `tunnel` khỏi `COMPOSE_PROFILES` (và `MOC_EXTRA_PROFILES`)
rồi `docker compose --profile tunnel rm -sf cloudflared`.

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

```bash
python3 scripts/kiem_ban_online.py https://moc.example.vn   # từ thư mục mã nguồn, máy nào có Python cũng được
```

`make install` không chép `kiem_ban_online.py` vào `/opt/moc`. Kịch bản kiểm từ bên ngoài, như trình duyệt của người
dùng thấy, rồi báo mọi mục trượt:
- chứng chỉ hợp lệ, còn ít nhất 14 ngày;
- `http://` chuyển sang `https://`;
- `/api/status` ok (thêm `--version 1.2.0` để đòi đúng bản);
- `issuer`, `token_endpoint` như dưới đây;
- header CSP, `nosniff` còn qua proxy.

Job `.github/workflows/ban-online.yml` chạy kịch bản này trên bản online của đội, với phiên bản là thẻ phát hành mới
nhất: mỗi sáng lúc 07:17, và ngay sau khi workflow Release phát hành xong. Từ lúc phát hành tới lúc nâng, job đỏ vì
bản online còn chạy bản cũ. Nâng xong thì chạy tay job (Actions → Bản online → Run workflow) để xác nhận từ bên ngoài.
Địa chỉ đổi bằng biến `MOC_ONLINE_URL` của repo.

Job thứ hai của workflow đó kiểm bản dev https://signet-dev.htechcs.com mỗi sáng. Đây là bản cài có reconciler theo
nhánh `develop` (`MOC_GITOPS_BRANCH=develop`, kéo mỗi 15 phút). Các mục kiểm như trên, nhưng `/api/status` phải là bản
dựng từ đầu `develop` (`--commit`). Lần gộp mới nhất chưa quá 30 phút thì bản dựng từ commit liền trước cũng đạt.
Reconciler kẹt thì job đỏ. Địa chỉ đổi bằng biến `MOC_DEV_URL`.

- `issuer` và `token_endpoint` đều phải bắt đầu bằng `https://moc.example.vn/realms/moc`. `issuer` sai (`http://…`,
  `localhost`) là `MOC_PUBLIC_URL` sai; chỉ `token_endpoint` sai (`http://…` hay có `:9080`) là `MOC_TRUSTED_PROXY`
  chưa khớp dải mạng Docker, hoặc Caddyfile thiếu dòng `header_up`.
- Cột đầu dòng nhật ký APISIX phải là IP thật của máy vừa gọi `curl`. Ra `172.x.0.1` là `MOC_TRUSTED_PROXY` chưa khớp.
  Với `auto`, dải APISIX đã chọn nằm ở dòng `MOC_TRUSTED_PROXY=auto → …` của `docker compose logs apisix`. Dải đó phải
  chứa gateway của mạng `moc` (APISIX ở hai mạng `moc`, `apps`; cổng publish đi qua `moc`):
  `docker inspect $(docker compose ps -q apisix) --format '{{(index .NetworkSettings.Networks "moc_moc").Gateway}}'`.
  Đặt dải cụ thể thì sửa `/opt/moc/.env` cho khớp gateway đó, rồi `docker compose up -d apisix`.
- Mở `https://moc.example.vn` trên trình duyệt, đăng nhập `vanthu` (mật khẩu `MOC_DEMO_PASSWORD`, mã TOTP từ
  `python3 scripts/totp.py`). Tài khoản cho giám khảo: `giamkhao` (chuyên viên, không cần TOTP; hộp việc có sẵn hai
  việc).
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
kho chỉ gồm tệp đã mã hóa). Diễn tập khôi phục: [`van-hanh.md`](van-hanh.md) mục "Sao lưu và khôi phục".

**Tự phục hồi và GitOps** (tùy chọn): [`van-hanh.md`](van-hanh.md) mục "GitOps và tự phục hồi" — systemd timer
`platform/systemd/` chạy `reconcile.py` mỗi 60 giây (đúng `User=moc`, `WorkingDirectory=/opt/moc` như ở đây). Muốn
commit mới trên nhánh `deploy` tự được cài lại thì làm thêm một bản sao riêng của reconciler (`/opt/moc-src`, nhánh
`deploy`) và đặt `MOC_GITOPS_DIR` như `van-hanh.md` — không dùng chung `~/Signet`.

**Nâng cấp tay** (không dùng GitOps): dừng timer reconciler nếu có (`sudo systemctl stop moc-reconcile.timer`), lấy mã
nguồn bản mới (gói `.tar.gz` của trang Release, hoặc `git pull` trong `~/Signet`), rồi từ thư mục đó:

```bash
scripts/nang_cap.sh nang /opt/moc
```

Kịch bản:

1. Dựng image bản mới khi trang còn chạy, kéo trước các image dựng sẵn máy chưa có (của mọi profile bản cài đang bật):
   lúc dừng trang không phải chờ tải, lỗi mạng thì dừng ở đây khi chưa đổi gì.
2. Sao lưu bằng chính bản đang chạy, in mã lượt, chép `.env` ra `/opt/moc/.env.truoc-<lượt>` (quyền 600, có bí mật):
   nâng xong, không cần lùi nữa thì xóa.
3. Dừng trang, `make install PREFIX=/opt/moc`, chạy lại. Hasura áp migration mới khi khởi động. `.env` của bản cài được
   giữ, trừ `MOC_VERSION` và hai biến `make install` đặt lại mỗi lần: `COMPOSE_PROFILES` (`core,app` cộng
   `MOC_EXTRA_PROFILES`) và `COMPOSE_FILE` (theo profile `logs` và ứng dụng đã cài), nên sửa tay hai biến này sẽ mất.
4. Chạy `moc.py realm clients` và `realm theme`.
5. Kiểm từng mục rồi báo các mục trượt:
   - số người dùng, văn bản, tệp không ít đi; dòng cuối sổ kiểm toán lúc trước còn nguyên băm (so với số liệu chụp ở
     bước 2, nên chỉ `nang` kiểm được);
   - dịch vụ chạy trước khi nâng vẫn chạy (chỉ `nang`), không cái nào chưa khỏe;
   - `/api/status` báo đúng phiên bản mới;
   - realm đủ client và theme;
   - `moc.py audit verify`;
   - `smoke.py`. Smoke trượt đúng ở bước hỏi đáp (chữ chưa kịp vào chỉ mục khi máy quá tải) thì chạy lại một lần, có in
     rõ là lần thử lại.

Nếu dừng giữa chừng sau khi trang đã dừng, hoặc kiểm có mục trượt, kịch bản in lệnh lùi:

```bash
scripts/nang_cap.sh lui /opt/moc <mã nguồn bản cũ> <lượt>
```

Lệnh lùi cài lại bản cũ rồi khôi phục đúng lượt sao lưu đó: CSDL, tệp và két về như lúc trước khi nâng, sau đó kiểm lại
như trên, trừ hai mục chỉ `nang` kiểm được. Gói cũ chưa có tệp `VERSION` (trước 1.2.0) thì đặt `MOC_VERSION=1.1.0`
trước lệnh.

`scripts/nang_cap.sh kiem /opt/moc` chỉ chạy phần kiểm. Job CI `.github/workflows/nang-cap.yml` chạy cả ba đường trên
bản cài của thẻ phát hành trước: nâng lên commit của PR, nâng két cũ (`ket`, [`van-hanh.md`](van-hanh.md) mục Két bí
mật), lùi về. Job chạy trên PR phát hành và trên PR có đổi migration, két, realm, compose, cài đặt hay sao lưu.

Realm Keycloak chỉ nạp từ tệp ở lần khởi động đầu, nên phần realm mới của bản sau không tự vào bản cài cũ. Nâng cấp
bằng GitOps cũng vậy. Hai lệnh realm ở bước 4 lo phần này, chạy lại không đổi gì
([`platform/keycloak/README.md`](../platform/keycloak/README.md)):

- `realm theme` đặt theme đăng nhập Signet, chỉ khi realm còn dùng theme mặc định. Nó báo lỗi nếu container keycloak
  chưa gắn thư mục theme.
- `realm clients` thêm client của ứng dụng mới.

Biến `.env` mới của bản mới (CHANGELOG ghi rõ) thêm vào `/opt/moc/.env`. **Không chạy `make reset` hay
`docker compose down -v` trên máy chủ**: xóa sạch dữ liệu, kể cả két (tệp văn bản hạn chế không mở được nữa).

**Mô hình ngôn ngữ** (tùy chọn, máy 16 GB): `docker compose --profile ai-pull run --rm ollama-pull` (tải trọng số
khoảng 2 GB, một lần) rồi `docker compose --profile ai up -d --wait ollama`.

**Thông báo qua email, webhook** (tùy chọn; mặc định chỉ có chuông trên web): khai máy chủ thư của đơn vị trong
`/opt/moc/.env` — `MOC_SMTP_HOST`, `MOC_SMTP_TLS=starttls` (hoặc `ssl`), `MOC_SMTP_USER`, `MOC_SMTP_PASSWORD`,
`MOC_SMTP_FROM=Signet <signet@moc.example.vn>` — và/hoặc `MOC_NOTIFY_WEBHOOK_URL` của kênh chat chung (incoming webhook
Mattermost, Slack; ntfy thì thêm `MOC_NOTIFY_WEBHOOK_FORMAT=ntfy`), rồi `docker compose up -d --wait`: két nạp lại mật
khẩu SMTP và URL webhook, svc-workflow khởi động lại. Người nhận email là địa chỉ trong Keycloak: tài khoản chưa có
email thì chỉ thấy chuông. Lần gửi xem trong CSDL (chỉ trạng thái, số lần thử, tên lỗi):

```bash
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$1"' _ \
  "select channel, status, count(*), max(attempts), string_agg(distinct last_error, ', ')
     from core.notification_deliveries group by 1, 2"
```

Thử trên máy, không cần máy chủ thư: đặt `MOC_EXTRA_PROFILES=mail`, `MOC_SMTP_HOST=mailpit`, `MOC_SMTP_PORT=1025`,
`MOC_SMTP_TLS=none`, `MOC_SMTP_FROM=signet@moc.example` rồi `make up` — Mailpit (hộp thư thử, profile `mail`) nhận mọi
thư mà không chuyển đi đâu, xem ở `http://127.0.0.1:8025` (chỉ mở trên máy; đổi cổng bằng `MOC_MAIL_UI_PORT`). Mailpit
không thuộc profile `core`, `app`: là công cụ demo, thư nằm trong tệp tạm của container, không có volume (tối đa 500
thư, mất khi container dừng), không dùng làm máy chủ thư thật.

## 8. Giới hạn đã biết

- **Chưa chạy trên VPS thật**: đã diễn tập đủ các bước trên một máy (xem đầu tài liệu) với chứng thư tự ký và nginx
  đóng vai Caddy; chưa xin chứng thư Let's Encrypt thật, chưa đo trên máy 8 GB.
- **Chỉ đoạn trình duyệt ↔ Caddy có TLS.** Các dịch vụ gọi nhau bằng HTTP trong mạng Docker (APISIX → Keycloak, các
  dịch vụ → OpenBao, …). Mạng này không mở ra ngoài, nhưng một container bị chiếm quyền thì thấy được lưu lượng chưa
  mã hóa trong đó.
- **`MOC_TRUSTED_PROXY=auto` tin mọi container ở mạng `moc`**: các dịch vụ lõi, `cloudflared`, và gateway mà cổng
  publish đi qua. Container ứng dụng chỉ ở mạng `apps` (internal), nằm ngoài dải đó: `X-Forwarded-For` giả của chúng bị
  bỏ, giới hạn tốc độ đăng nhập đếm theo IP thật của container (#211).
  - Một dịch vụ lõi bị chiếm quyền vẫn giả được `X-Forwarded-For`.
  - Bản cài cũ còn `MOC_TRUSTED_PROXY=172.16.0.0/12` thì tin mọi container trên máy, kể cả mạng `apps`. Nâng cấp không
    đổi `.env`: đổi tay sang `auto` rồi `docker compose up -d apisix`.
  - Dải cụ thể (vd gateway `172.x.0.1/32` lấy ở bước 6) không tự theo mạng. Dải và gateway do Docker cấp lúc tạo mạng.
    `make down` rồi `make up`, nâng cấp bằng `scripts/nang_cap.sh` hay reconciler GitOps (cả hai `docker compose down`
    trước khi cài) đều xóa, tạo lại mọi mạng và có thể đánh số lại. Giá trị cố định khi đó trỏ sai mạng: Keycloak trả
    `token_endpoint` `http://…` (trình duyệt chặn đăng nhập), mọi người dùng chung một bộ đếm giới hạn. `auto` đọc lại
    dải mỗi lần APISIX khởi động nên không lệch.
- **Cloudflare Tunnel (mục 5b): TLS kết thúc ở Cloudflare**, Cloudflare thấy nội dung yêu cầu trước khi chuyển vào
  đường hầm — hợp với máy demo, cân nhắc với dữ liệu thật. Máy tắt hay mất mạng là trang ngừng; Cloudflare gói Free
  giới hạn mỗi yêu cầu 100 MB (APISIX đã chặn trên 64 MB).
- **Hasura nối CSDL bằng `POSTGRES_USER`**, là siêu người dùng của Postgres. Quyền theo vai trò nằm ở metadata Hasura
  (trang metadata bị chặn ở APISIX), chưa có vai trò CSDL riêng quyền hẹp.
- **Mọi tài khoản mẫu của `seed.py` dùng chung `MOC_DEMO_PASSWORD`.** Hợp với máy demo; máy có dữ liệu thật thì không
  chạy `seed.py` (bước 3).
- **Thông báo email, webhook gửi ít nhất một lần**: svc-workflow dừng đúng lúc vừa gửi mà chưa ghi kết quả thì lần sau
  gửi lại (thư cùng `Message-ID`, hộp thư thường gộp). Webhook là một URL chung cho cả bản cài, mọi đơn vị cùng đổ về
  một kênh chat; mỗi lần gửi thêm hai dòng sổ kiểm toán. Chưa đo tải gửi thư; một lượt vòng nền gửi tuần tự tối đa 20
  dòng.
- **GitOps kiểm chữ ký commit chỉ khi đặt `MOC_GITOPS_ALLOWED_SIGNERS`** (`van-hanh.md` mục GitOps): để trống thì ai đẩy
  được lên nhánh `deploy` là cài được lên máy chủ.
