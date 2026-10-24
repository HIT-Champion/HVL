# platform/apisix — Apache APISIX

APISIX chạy standalone (không etcd, không Admin API): route trong `apisix.yaml`, cấu hình trong `config.yaml`,
giá trị `${{TÊN}}` lấy từ biến môi trường. Đây là cổng duy nhất mở ra ngoài (`MOC_HTTP_PORT`). Chủ: #14.

- Danh sách trắng: `/realms/<realm>/*`, `/resources/*` → Keycloak; `/v1/graphql` → Hasura; `/api/files*`,
  `/api/search` → svc-files; `/ca-nhan`, `/ca-nhan/*` (chỉ GET, HEAD) → `app-ca-nhan`, Không gian cá nhân
  ([`docs/them-ung-dung.md`](../../docs/them-ung-dung.md)); còn lại → giao diện Văn phòng điện tử.
- Đường quản trị bị chặn tường minh (404): `/admin`, `/realms/*` khác realm của Signet, `/console`, `/v1/*`,
  `/v2/*`, `/healthz`, `/flowable-rest/*`.
- Kiểm JWT ở biên (`openid-connect`, chỉ Bearer, khóa qua JWKS nội bộ của Keycloak); Hasura và svc-files
  vẫn kiểm lại. Tiêu đề `X-Hasura-Admin-Secret` từ ngoài vào bị gỡ, cả tên cũ `X-Hasura-Access-Key`
  (Hasura 2.51 đã không nhận — gỡ để phòng xa).
- Giới hạn đăng nhập theo IP (`MOC_RATE_LOGIN_PER_MIN`) đếm chung cho đường cấp token, biểu mẫu đăng nhập và **mọi
  POST khác vào realm** (route `dang-nhap-post`): viết khác đường (`…/token/`, `…/token;x`) không né được bộ đếm.
- Mỗi yêu cầu có `X-Request-Id` (giữ nguyên tới sổ kiểm toán).
- `GET /api/status` (route `trang-thai`, trạng thái hệ thống) như cổng xác thực: không cần token, giới hạn theo IP
  (`MOC_RATE_STATUS_PER_MIN`, mặc định 30/phút). Chỉ đúng đường này; `/api/*` chưa khai báo vẫn rơi vào route `chan`.
- Máy chủ trạng thái của APISIX (`apisix.status`, `GET /status/ready` ở cổng 7085) chỉ nghe trong mạng nội bộ,
  không publish ra máy chủ: svc-files hỏi nó cho dòng "Cổng API" của trang trạng thái (`200` mọi worker đã nạp cấu
  hình, `503` còn worker chưa nạp).

Sửa route: sửa `apisix.yaml` rồi `docker compose restart apisix`.

## Sau proxy TLS trên máy chủ (F1.9)

Trên máy chủ, Caddy nhận HTTPS rồi chuyển vào APISIX chỉ nghe `127.0.0.1` ([`docs/trien-khai.md`](../../docs/trien-khai.md)).
APISIX 3.18 thay `X-Forwarded-Proto`, `-Host`, `-Port` bằng giá trị nó thấy (`http`, cổng 9080), trừ khi yêu cầu tới
từ địa chỉ trong `apisix.trusted_addresses`. `config.yaml` khai dải `MOC_TRUSTED_PROXY` (mặc định `127.0.0.1/32`:
không ai tới APISIX từ loopback của chính container, tức không tin ai) cho hai việc:

- `trusted_addresses`: yêu cầu từ dải này giữ `X-Forwarded-Proto`, `-Host`, `-Port` của proxy. `issuer` và trang
  đăng nhập theo `KC_HOSTNAME`, nhưng `token_endpoint`, `jwks_uri` Keycloak dựng theo chính các tiêu đề này
  (`KC_HOSTNAME_BACKCHANNEL_DYNAMIC`, `KC_PROXY_HEADERS=xforwarded`): thiếu dải tin cậy thì `token_endpoint` ra
  `http://…`, trình duyệt chặn lần đăng nhập. Yêu cầu từ ngoài dải: các tiêu đề đó bị thay, `X-Forwarded-For` gửi
  kèm bị bỏ.
- `real_ip_from` + `real_ip_header: X-Forwarded-For`: `$remote_addr` là IP người dùng, nên giới hạn tốc độ đăng
  nhập, cổng xác thực đếm riêng từng người, nhật ký truy cập ghi IP người dùng. Thiếu nó thì mọi người dùng chung một
  bộ đếm (IP gateway của mạng Docker).

Proxy không gửi `X-Forwarded-Port` (Caddy mặc định không gửi) thì APISIX điền cổng của nó và Keycloak trả
`https://tên-miền:9080/…`: Caddyfile phải có `header_up X-Forwarded-Port 443`.

## Nhật ký truy cập không có chuỗi truy vấn (F4.4)

APISIX và nginx của giao diện **không ghi chuỗi truy vấn và Referer**. Trang Tìm kiếm, Hỏi đáp đặt câu tìm lên URL
(`/tim-kiem?q=…`, `/api/search?q=…`), bước đăng nhập mang `?code=…&state=…`, còn Referer là URL đầy đủ của trang
trước. Chuỗi truy vấn đã mã hóa phần trăm (`0912%20345%20678`, `ten%40example.com`) nên bộ che thông tin cá nhân của
dịch vụ không nhận ra, và họ tên thì không nhận dạng được — nên bỏ hẳn, không che bằng regex (QĐ-006 trong
[`docs/architecture.md`](../../docs/architecture.md)).

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
    access_log_format: '$remote_addr - $remote_user [$time_local] $http_host "$request_method $moc_duong_dan $server_protocol" $status $body_bytes_sent $request_time "$http_user_agent" $upstream_addr $upstream_status $upstream_response_time "$upstream_scheme://$upstream_host$moc_duong_dan_upstream" "$apisix_request_id"'
```

- `log_format` của nginx không cắt chuỗi được, nên hai `map` giữ phần trước dấu `?` đầu tiên: của `$request_uri`
  (đường dẫn đúng như client gửi, như phần đường dẫn của `"$request"` cũ) và của `$upstream_uri` (APISIX đã ghép
  `?…` vào). Dòng của `/api/search?q=001205000017` ghi `"GET /api/search HTTP/1.1"`.
- Các trường khác giữ như định dạng mặc định của APISIX 3.18, kể cả đích phía sau
  (`"$upstream_scheme://$upstream_host…"`, có ích khi gỡ lỗi đường đổi hướng như `/realtime`) và mã yêu cầu
  `"$apisix_request_id"` ở cuối dòng (log tập trung F3.14 dùng để nối dòng của APISIX với svc-files, svc-workflow —
  `docs/van-hanh.md` mục Log tập trung); bỏ `$http_referer`.

nginx của app-office, `apps/office/nginx/default.conf.template` (tệp được include trong khối `http`; app-ca-nhan
dùng đúng khối này trong `apps/ca-nhan/nginx/default.conf.template`):

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

## Tường lửa ứng dụng web — WAF (F3.15)

Mọi yêu cầu vào cổng, kể cả đường không có route, qua **Coraza v3.3.3 + OWASP CRS v4.14.0** trước khi APISIX kiểm
token và giới hạn tốc độ. Tải tấn công → `403`. Coraza chạy ngay trong tiến trình APISIX dưới dạng plugin
WebAssembly (coraza-proxy-wasm 0.6.0, có sẵn bộ luật CRS): không thêm container, không đổi cổng hay đích của
Cloudflare Tunnel.

| Ở đâu | Gì |
|---|---|
| `Dockerfile` | Image `moc/apisix` = image APISIX đang ghim, thêm đúng tệp `coraza-proxy-wasm.wasm` lấy từ image `ghcr.io/corazawaf/coraza-proxy-wasm` ghim digest; `sha256sum -c` so với băm của tệp trên trang phát hành |
| `config.yaml` | `wasm.plugins`: plugin `coraza-waf`, pha `rewrite`, priority 7999; snippet `set $wasm_process_req_body on;`; `worker_processes: ${{MOC_APISIX_WORKERS:=4}}` |
| `apisix.yaml`, global rule | `serverless-pre-function` (chặn JSON lồng sâu, priority 10000) rồi `coraza-waf` với các chỉ thị SecLang bên dưới |

Hai chỗ phải có vì coraza-proxy-wasm được viết cho Envoy:

- Pha `rewrite`: global rule chạy pha rewrite trước plugin của route. Ở pha access thì `openid-connect` của route đã
  trả 401 cho GraphQL không token trước khi WAF kịp xem thân, `limit-count` đã đếm.
- `$wasm_process_req_body`: `apisix/wasm.lua` chỉ đưa thân yêu cầu cho plugin wasm khi biến này khác rỗng. Thiếu
  nó thì Coraza không thấy thân, và pha 2 của CRS (nơi cộng điểm, quyết chặn) chỉ chạy lúc phản hồi về — sau khi yêu
  cầu đã tới dịch vụ phía sau.

### Phân vai: WAF, ClamAV và kiểm quyền

| Lớp | Soi gì |
|---|---|
| WAF ở cổng | Đường dẫn, tham số, tiêu đề, cookie, thân form và JSON (cả biến GraphQL), các trường thường của multipart: SQLi, XSS, duyệt thư mục, chèn lệnh, Log4Shell… Tên tệp tải lên: duyệt thư mục, đuôi `.php`… |
| ClamAV ở `svc-files` (F1.6) | **Nội dung tệp** tải lên. coraza-proxy-wasm (TinyGo, không có hệ tệp) bỏ nội dung phần tệp của multipart, không soi: EICAR qua WAF rồi bị ClamAV trả `422` (smoke, mục "Trạm kiểm dịch") |
| `openid-connect`, Hasura, `svc-files` | Ai được làm gì. WAF không thay kiểm token, quyền theo dòng hay kiểm đầu vào của dịch vụ |

Tên tệp tải lên là dữ liệu, không là đường dẫn — `svc-files` tự làm sạch, không dựa vào WAF:

- `clean_filename` (`services/svc-files/src/svc_files/app.py`): bỏ phần thư mục (`/`, `\`), ký tự điều khiển; tên
  rỗng, `.`, `..` thành `tep-khong-ten`; chuẩn hóa NFC; cắt 255 ký tự. `' " ; = :` giữ nguyên.
- Khóa trong kho đối tượng theo đơn vị, ngày và id tệp (`object_key`, `storage.py`), không theo tên; tên vào cơ sở dữ
  liệu qua biến GraphQL (Hasura tham số hóa); giao diện hiện tên bằng nội suy Vue, không `v-html`.
- Tải về: `content_disposition` gửi tên ASCII đã bỏ `"` `\` kèm `filename*=UTF-8''…` mã hóa phần trăm (RFC 6266):
  `;` `=` `'` trong tên không tách được tiêu đề.
- Kiểm: `services/svc-files/tests/test_upload.py` (`test_clean_filename`: `../../etc/passwd` → `passwd`, ký tự điều
  khiển bị bỏ, `Tờ trình 'gấp'; đợt 1 = "mới": v2.pdf` giữ nguyên), `test_download.py` (`test_content_disposition`).

Vì vậy trên đường tải lên WAF không xét `' " ; = \` và `:` trong tên tệp (loại trừ 10040, bảng dưới). Vẫn chặn tên
`../…`, `.php` (403), tên có byte null (400, không phải 403: Coraza không đọc được thân multipart, luật 200002 của
recommended-conf) và soi tên trường. CRS ở paranoia 1 không có luật SQLi, XSS cho tên tệp (920120 chặn `x' UNION…` chỉ
vì dấu nháy): tên như vậy qua WAF, và vô hại vì ba điều trên.

### Luật

Thứ tự trong `directives_map.moc`:

1. `Include @recommended-conf` — thiết lập khuyến nghị của Coraza.
2. `SecRuleEngine ${{MOC_WAF:=On}}` — công tắc, mục dưới.
3. `SecRequestBodyLimit`, `SecRequestBodyInMemoryLimit` 64 MiB = `client_max_body_size` (`config.yaml`). Mặc định
   của recommended-conf là 128 KB kèm `Reject`: mọi tệp lớn hơn sẽ bị 413. WebAssembly không ghi được tệp tạm nên
   thân nằm cả trong RAM (xem số đo).
4. `SecResponseBodyAccess Off` — không soi phản hồi: phía sau là dịch vụ của Signet, soi thì phải đệm cả tệp tải về.
5. `Include @crs-setup-conf`, paranoia 1, ngưỡng điểm bất thường mặc định của CRS (vào 5, ra 4).
6. Loại trừ và luật riêng (id 10000–10099 dành cho Signet), rồi `Include @owasp_crs/*.conf`, rồi gỡ 920350.

Loại trừ — tối thiểu, mỗi cái gỡ đúng luật (theo id hoặc dải id, không theo nhãn) trên đúng tham số của đúng
đường; mỗi dòng đã thấy chặn nhầm thật khi chưa có (kiểm bằng 71 truy vấn GraphQL trích từ `apps/`, `scripts/`,
luồng đăng nhập Keycloak có TOTP, tải lên 28 tệp mẫu, và 7 389 yêu cầu dựng từ toàn bộ chữ của dữ liệu mẫu — mục
"Dò chặn nhầm trên dữ liệu thật"):

| Luật | Đường | Gỡ | Lý do | Chặn nhầm khi chưa có |
|---|---|---|---|---|
| 10010 | `/realms/<realm>/…` | mọi luật CRS trên `ARGS:password`, `password-new`, `password-confirm` | Mật khẩu là chuỗi tùy ý; Keycloak chỉ băm, không đưa vào truy vấn hay lệnh | `P@ss'word--1`, `x/../../y`… → 942100, 930100: không đăng nhập, không đổi mật khẩu được |
| 10010 | `/realms/<realm>/…` | 931100, 934110 trên `ARGS:redirect_uri`, `post_logout_redirect_uri` | Keycloak so redirect URI với đúng danh sách của client, không tự gọi tới URL đó | `http://localhost:8080/` (CI, máy dev) → 934110; `http://192.168.1.10:8080/` → 931100 |
| 10020 | `/`, `/<ứng dụng>/`, `…/dang-nhap` (redirect URI của mọi ứng dụng) | 931100, 934110 trên `ARGS:iss` | Keycloak gửi `iss` (RFC 9207, URL của realm) về trang đăng nhập; URL công khai là `localhost` hay IP thì CRS coi là SSRF/RFI. Không dịch vụ nào gọi tới `iss`; oidc-client-ts chỉ so với issuer đã biết | như trên, ở bước quay về ứng dụng |
| 10030 | `/v1/graphql` | dải 932000–932999 (chèn lệnh), 933000–933999 (PHP) và 942290 trên `ARGS:json.query` | Chữ truy vấn GraphQL do ứng dụng viết; Hasura phân tích theo ngữ pháp GraphQL rồi sinh SQL tham số hóa. Tên cột `diff`, `time` trùng lệnh Unix, `_is_null` trùng hàm PHP, biến `$where` trùng toán tử MongoDB. Biến vẫn soi (trừ 10031); SQLi, XSS, Log4Shell (944…), Node.js (934…) viết thẳng vào chữ truy vấn vẫn bị chặn | sổ kiểm toán, văn bản đến/đi, sơ đồ, thông báo, smoke → 932235, 932260, 933150, 942290 |
| 10031 | `/v1/graphql` | dải 932…, 933…, 931100, 931120 trên đúng 9 khóa biến chữ tự do: `json.variables.o.body`, `o.summary`, `set.body`, `set.summary` (soạn, sửa văn bản đi — `soan.vue`), `d.summary` (vào sổ văn bản đến — `tiep-nhan.vue`), `d.instruction`, `d.note`, `d.result_note` (chỉ đạo, ý kiến, kết quả — `TaskPanel.vue`), `c` (góp ý — `FeedbackButton.vue`) | Chữ người dùng gõ hay dán từ văn bản giấy; chỉ được lưu rồi hiện ra (dựng PDF thì escape), không chạy, không include, không tải URL. SQLi, XSS, duyệt thư mục, Log4Shell, Node.js trong các khóa này vẫn bị chặn; khóa khác — kể cả `o.type_code`, `o.bodyx`, `x.body`, `o.body.x` — soi đủ | 4/21 PDF mẫu (`hoi-dap/02-thi-ket-thuc`, `van-ban-den/04-ke-hoach`, `15-huong-dan`, `18-ke-hoach-lien-tich`) và mọi văn bản có đề mục `I.` `II.` `III.` → 932125; khối chữ ký dàn trang → 933210; ý kiến chỉ là một đường dẫn `http://192.168.1.10:8080/van-ban/12` → 931100; "File đính kèm ở đâu?", "HTTPS là gì?" → 931120 |
| 10032 | `/api/documents/ask` | dải 932…, 933…, 931100, 931120 trên `ARGS:json.question` | Câu hỏi cho trợ lý (`hoi-dap.vue`): người dùng dán đoạn văn bản vào hỏi; câu hỏi chỉ đưa cho tìm kiếm và mô hình ngôn ngữ | như 10031 |
| 10033 | `/api/search`, `/tim-kiem` | 931100, 931120, 933160 trên `ARGS:q` | Ô Tìm kiếm: q chỉ đưa cho Meilisearch hay đọc ở trình duyệt, không tải, không chạy. Chèn lệnh, PHP khác, SQLi, XSS trong q vẫn bị chặn | dán `http://192.168.1.10:8080/van-ban/12` → 931100; "File đính kèm ở đâu?" → 931120; dán dòng "Đính kèm: 03 file (PDF, Word, Excel)." → 933160 (hàm PHP `file(`) |
| 10040 | `/api/files`, `/api/imports/<loại>` | 920120 trên `FILES` (tên tệp); 922130 trên `MULTIPART_PART_HEADERS:file`, `data`, `archive` | Tên tệp chỉ là dữ liệu, `svc-files` tự làm sạch (mục "Phân vai"). Tên trường (`FILES_NAMES`) và đường khác vẫn soi; tên `../…`, `.php` vẫn 403 | `Tờ trình 'gấp'.pdf`, `Kế hoạch; đợt 1.pdf`, `Báo cáo "2026".pdf`, `a=b&c=d.pdf` → 920120; `Kết quả: đạt!.pdf` → 922130 (dấu `:` sau chữ có dấu) |
| 920350 | mọi đường | gỡ hẳn | Signet được mở bằng IP trong mạng nội bộ. Dưới APISIX, coraza-proxy-wasm thêm `Host` lần nữa nên luật "Host là địa chỉ IP" cộng điểm hai lần (6 ≥ 5) | mọi yêu cầu vào bằng IP → 403 |

Luật riêng — hai lỗ hổng của Coraza 3.3.3 (mục dưới):

| Luật | Chặn | Vì sao |
|---|---|---|
| 10060 | ≥ 1000 tham số truy vấn → 403 | GHSA-6r3q-mjv7-xr8m: từ tham số thứ 1000 Coraza bỏ qua, không soi |
| 10061 | ≥ 1000 tham số form urlencoded → 403 | như trên, cho thân form |

Thêm một loại trừ khi có chặn nhầm: lấy `X-Request-Id` của phản hồi 403, đọc các dòng `Coraza: Warning.` của nó
(mục dưới) để biết luật (`[id "…"]`) và tham số (`… found within ARGS:<tên>`). Viết một `SecRule REQUEST_FILENAME` giới
hạn theo đường, `ctl:ruleRemoveTargetById=<luật>;ARGS:<tên>` — không gỡ luật cho mọi tham số, không gỡ toàn cục nếu
không có lý do như 920350; id mới trong 10000–10099; chú thích lý do ngay trên; thêm dòng vào bảng trên
(`scripts/tests/test_waf.py` đòi đủ). Sửa `apisix.yaml` xong: `docker compose restart apisix`. Dò chặn nhầm cho một
luồng mới mà không làm phiền người dùng: chạy `MOC_WAF=DetectionOnly`. Lưu ý:

- Gỡ theo id hay dải id (`932000-932999`), không theo nhãn: nhãn `attack-rce` gồm cả 934… (Node.js) và 944… (Java,
  Log4Shell) — gỡ theo nhãn thì mất luôn hai nhóm đó trên khóa ấy (đã thử: `${jndi:ldap://…}` qua WAF).
- `ARGS:<tên>` so khớp đúng cả khóa, không nhận biểu thức chính quy, nhưng **không phân biệt hoa thường** (Coraza so tên
  tham số như ModSecurity) và không phân biệt khóa lồng với khóa có dấu chấm (GHSA-5gj4, bảng dưới): loại trừ trên
  `json.variables.o.body` cũng áp cho `O.body`, `o.BODY` và `{"o.body": …}`. `ctl` của Coraza không có cách so phân biệt
  hoa thường, và siết cũng không thêm gì: tên biến GraphQL do người gửi tự đặt, nên loại trừ thực chất là "trường
  `body`, `summary`… của biến tên `o`, `set`, `d`, `c`" ở bất kỳ câu GraphQL nào. Chỗ chặn ở các khóa này là các nhóm
  luật vẫn soi — SQLi, XSS, duyệt thư mục, Log4Shell vẫn 403 ở cả các biến thể trên — và quyền của Hasura.
- Biến GraphQL phẳng thành `json.variables.<biến>.<trường>`, phần tử mảng thành `.0`, `.1`… Ô chữ tự do mới, hay đổi tên
  biến của ô cũ, thì thêm khóa đó vào 10031 (`test_waf.py` kiểm mỗi khóa ở đây vẫn được giao diện gửi).
- Bộ lọc Hasura (`bool_exp`) gửi trong **biến** thì toán tử thành một phần tên tham số
  (`json.variables.where.entity_id._is_null`), và 933150 (tên hàm PHP) bắt ở tên tham số (`ARGS_NAMES`). Hiện mọi chỗ
  dùng `_is_null` đều nằm trong chữ truy vấn (10030 lo); chuyển bộ lọc sang biến thì phải thêm loại trừ 933150 cho đúng
  tên đó trên `/v1/graphql`.

### Công tắc `MOC_WAF`, số worker

| `MOC_WAF` | Tác dụng |
|---|---|
| `On` (mặc định, `.env.example`) | Chặn: điểm ≥ 5 → 403 |
| `DetectionOnly` | Không chặn, vẫn ghi dòng `Coraza: Warning.` — đã thử: 0/40 tải tấn công bị chặn; 31/32 cái tới được WAF có dòng luật khớp mang `request_id` (cái còn lại: dòng quá 2048 byte, mục dưới) |
| `Off` | Tắt luật. Plugin vẫn nạp (bộ nhớ không giảm); muốn bỏ hẳn thì xóa `coraza-waf` khỏi global rule |

Đổi trong `.env` rồi `docker compose up -d apisix` (biến môi trường chỉ đọc lúc tạo container). Smoke bỏ qua khối
WAF khi `MOC_WAF` khác `On`. Đưa lên máy thật: nên chạy `DetectionOnly` vài ngày, đọc nhật ký, rồi mới `On`.

Giá trị khác ba giá trị trên (không phân biệt hoa thường; `On ` có dấu cách cũng sai): Coraza không nạp được cấu hình
và cổng trả 503 mọi yêu cầu mà lúc khởi động không báo gì. `MOC_APISIX_WORKERS` không phải `auto` hay số nguyên
dương: như vậy. Cả ba chỗ dưới dùng chung một bước kiểm — `kiem-moi-truong.sh` (`--chi-kiem` khi chạy trên máy chủ) —
và báo cùng một dòng `Signet: MOC_WAF='Bogus' không hợp lệ — chỉ nhận On, DetectionOnly hoặc Off …`:

- `make up`, `make install` (mục `env-ready` của `Makefile`): đọc giá trị compose sẽ dùng (`docker compose config`:
  biến shell rồi `.env`, trống thì `On`) và dừng trước khi bật.
- Reconciler GitOps (`scripts/reconcile.py`, gọi thẳng `docker compose up --wait`): kiểm với compose của commit sắp
  áp, **trước khi dừng Signet**. Sai thì không áp, bản đang chạy giữ nguyên, lượt báo lỗi `GitOps: không áp được
  commit …`; sửa `.env` thì lượt sau áp, không cần commit mới.
- Bật bằng cách khác (`docker compose up` tay trong bản cài `/opt/moc`): entrypoint của image `moc/apisix` in dòng
  trên rồi thoát mã 64 trước khi APISIX chạy; container khởi động lại liên tục (`restart: unless-stopped`),
  `docker compose ps` hiện `Restarting (64)`, dòng lỗi ở `docker compose logs apisix`; lượt tự phục hồi kế tiếp của
  reconciler báo `apisix đang tự khởi động lại liên tục`. `up --wait` không coi đó là lỗi (apisix không có
  healthcheck) — vì vậy hai chỗ trên kiểm trước.

`MOC_APISIX_WORKERS` (mặc định 4): mỗi worker nginx nạp riêng một bộ luật (~80 MB), nên không để `auto` (một worker
mỗi nhân CPU: 16 worker là ~1,5 GiB). 4 worker vẫn ~470 yêu cầu GraphQL mỗi giây trên 2 CPU — thừa cho một đơn vị.

### Đọc nhật ký chặn

Phản hồi 403 là trang mặc định của APISIX — không có tên luật, điểm hay chữ "Coraza" — kèm tiêu đề `X-Request-Id`.
Coraza ghi vào error log của APISIX; nginx thêm `request_id: "<X-Request-Id>"` cuối mỗi dòng:

```bash
docker compose logs apisix | grep '<X-Request-Id>'
```

- `Coraza: Warning. <tên luật> … [id "942100"] … [data "Matched Data: … found within ARGS:q: …"]` — một dòng mỗi
  luật khớp.
- `Coraza: Access denied (phase 1). Inbound Anomaly Score Exceeded … (Total Score: 20) … [id "949111"]` — lần chặn
  (phase 1: tiêu đề, tham số; phase 2: thân).
- Các dòng mang mức `[emerg]`: coraza-proxy-wasm ghi luật CRS (mức CRITICAL) bằng `LogCritical`, nginx in thành
  `emerg`. Không phải APISIX hỏng.
- nginx cắt dòng nhật ký ở 2048 byte: yêu cầu rất dài (hàng trăm tham số) mất phần `request_id` — tìm theo giờ và
  `[uri "…"]`.
- Dòng của Coraza có `[uri "…?q=…"]` và dữ liệu khớp, nên mang cả chuỗi truy vấn (giới hạn của `error_log` ở mục
  F4.4). Chỉ có dòng khi một luật khớp: các yêu cầu thật đã thử (dưới) và các yêu cầu của `make demo-che-pii` không
  sinh dòng nào.

### Dò chặn nhầm trên dữ liệu thật

Toàn bộ chữ của dữ liệu mẫu gửi qua cổng đúng như giao diện gửi, đếm phản hồi 403 (dịch vụ phía sau giả không bao
giờ trả 403, nên mọi 403 là WAF):

- Chữ: 93 thân văn bản (chữ của 21 PDF có lớp chữ trong `seed/`, `pdftotext` hai kiểu — thứ tự đọc như khi chép từ
  trình xem PDF và giữ dàn trang — cả tệp lẫn từng trang; thân văn bản của `scripts/seed_documents.py`); 791 câu ngắn
  (từng dòng của các thân đó, mọi chuỗi trong `seed/**/*.json` — có câu hỏi mẫu của trợ lý —, trích yếu, nội dung,
  ý kiến trong `scripts/seed_documents.py`, `demo.py`, `smoke.py`, và 62 câu tự viết: đề mục La Mã, khối ký, đường
  dẫn nội bộ, "File …?", đường dẫn Windows, dấu `< > ' "`…); 58 tên tệp (tệp mẫu và tên tiếng Việt có
  `' " ; = : # & % [ ] { } < > @ ~`, dạng NFD, dài 200 ký tự).
- Kênh: thân và trích yếu khi soạn, sửa văn bản đi (`$o`, `$set`); trích yếu và cơ quan ban hành khi vào sổ văn bản
  đến (`$d`); một dòng Nơi nhận; ý kiến chỉ đạo, ý kiến, kết quả (`completeTask`); góp ý; câu hỏi trợ lý; ô Tìm kiếm
  (`/api/search?q=`, `/tim-kiem?q=`); tải lên `/api/files` và nạp lô `/api/imports/incoming` dạng multipart như
  Chrome gửi. Tổng 7 389 yêu cầu.

| Cấu hình | Bị 403 | Chữ lấy từ dữ liệu mẫu bị 403 |
|---|---|---|
| Không có 10031–10040 | 169 (2,29 %): 931120 ×72, 932125 ×40, 931100 ×36, 920120 ×10, 932130 ×9, 933135 ×9, 933160 ×9, 933210 ×2, 922130 ×2 | 24 — chữ của 4/21 PDF |
| Hiện tại | 28 (0,38 %) | 0 |

28 lần còn lại đều là câu tự viết đặt vào ô không dành cho chúng: 26 ở Cơ quan ban hành và Nơi nhận (mục "Hạn chế"),
2 là chỗ giữ chỗ `Kính gửi ${ten_don_vi}` gõ vào ô Tìm kiếm (932130, 933135). Trong các ô chữ tự do, câu hỏi, tên tệp:
0. Thử lẩn qua chính các loại trừ (223 ca): SQLi, XSS, duyệt thư mục, `/etc/passwd`, Log4Shell trong các khóa đã loại
trừ vẫn 403; cùng tải trong khóa gần giống (`o.type_code`, `o.bodyx`, `x.body`, `o.body.x`, `q2`), ở đường khác
(`/v1/graphql/`), hay khóa của đường này gửi tới đường kia vẫn 403; tên tệp `../…`, `.php`, tên trường có `' ; =` vẫn
403. Chèn lệnh, PowerShell, PHP (trừ khi kèm đường tệp hệ thống như `file('/etc/passwd')`), `http://<IP>` trong ô
chữ tự do thì qua — cố ý. Smoke (`check_waf`) gửi lại mỗi lần chạy một mẫu chữ thật cho từng luật đã gỡ: tên tệp có
`' ; = :`, nội dung có đề mục `I.` `II.` `III.`, khối ký hai cột, "File …?", `http://<IP>`, "03 file (…)" — bỏ loại
trừ nào thì smoke đỏ.

### Lỗ hổng của Coraza 3.3.3 và biện pháp

coraza-proxy-wasm 0.6.0 (06/07/2025) là bản phát hành mới nhất, nhánh `main` vẫn Coraza 3.3.3; 12 GHSA công bố
02/10/2026 được vá ở 3.8.0/3.8.1 nhưng chưa có bản WebAssembly nào mang bản vá.

| GHSA | Mức | Ở Signet | Biện pháp |
|---|---|---|---|
| 6gcq-wc29-5xf2 — đọc JSON đệ quy không giới hạn | high | Có: thân JSON lồng ~80 tầng (vài trăm byte, không cần token) làm tràn ngăn xếp WebAssembly, worker đó trả 503 mọi yêu cầu sau | `serverless-pre-function` trước WAF: thân JSON (đúng các Content-Type làm Coraza bật bộ đọc JSON, xét mọi giá trị của tiêu đề) không hợp lệ hoặc lồng quá 32 tầng → `400 {"error":"invalid_json"}`. JSON thật của Signet sâu khoảng 8 tầng |
| 6r3q-mjv7-xr8m — bỏ tham số thứ 1000 trở đi | high | Có | Luật 10060, 10061 |
| w253-m66g-rx24 — form có `; charset=` | medium | Không lọt: SQLi trong form `…; charset=UTF-8` vẫn 403 | — |
| x26q-wvhg-fh4m — URI lỗi làm trống `ARGS_GET` | medium | Không tái hiện được: URI lỗi bị nginx trả 400 trước, URI qua được nginx thì Coraza vẫn đọc đủ tham số | — |
| 5gj4, 3wr7, g4qm, pc5q — khóa JSON có dấu chấm, `filename*`, cookie có ký tự điều khiển, `jsDecode` | medium | Có | Không — là cách lẩn WAF, không mở lỗ mới trong ứng dụng; dịch vụ vẫn tự kiểm đầu vào |
| 3c6w, rp9v, prpw, r3rm | — | Không: tắt đọc phản hồi, không có tệp tạm, không bật audit log, lỗi từ 3.4.0 | — |

SBOM và OSV-Scanner của CI không đọc tệp `.wasm`: GHSA mới của `corazawaf/coraza` phải theo dõi tay. Có bản
coraza-proxy-wasm mang Coraza ≥ 3.8.1 thì đổi digest và băm trong `Dockerfile`. Cần bản vá sớm hơn: coraza-caddy
v2.6.2 (Coraza 3.8.1) đứng trước APISIX thành một container — đổi cổng mở ra ngoài, đích của Cloudflare Tunnel và
tin cậy `X-Forwarded-For` hai tầng, nên chưa chọn.

### Số đo

APISIX thử (image `moc/apisix` dựng từ `Dockerfile` này, cấu hình trong thư mục này) với dịch vụ phía sau giả trả
ngay, `--cpus 2 --memory 2g`, 4 worker; client Python cùng máy, một kết nối giữ, tuần tự 1 000 yêu cầu sau 600 yêu
cầu làm nóng (tệp 1 MB: 250, 24 MB: 20); bộ nhớ theo `docker stats`. "Không WAF" là cấu hình trước F3.15 với 4 worker.

| | Không WAF | `On` | `Off` |
|---|---|---|---|
| `GET /` (p50) | 0,42 ms | 2,28 ms | 0,53 ms |
| `GET /api/search?q=…` có token (p50) | 0,73 ms | 2,39 ms | 0,83 ms |
| GraphQL 0,6 KB có token (p50 / p95) | 0,78 / 1,1 ms | 3,88 / 6,39 ms | 0,79 / 1,26 ms |
| Tải lên 1 MB (p50) | 4,3 ms | 10,5 ms | 4,9 ms |
| Tải lên 24 MB (p50) | 83 ms | 127 ms | 96 ms |
| GraphQL, 8 luồng | 3 834 yêu cầu/giây | 470 yêu cầu/giây | 2 388 yêu cầu/giây |
| Bộ nhớ sau làm nóng | 82 MiB | 451 MiB | 450 MiB |
| Sau 8 lần tải lên 24 MB | 117 MiB | 931 MiB | — |
| Sau thêm 20 000 yêu cầu | 122 MiB | 804 MiB (không tăng dần) | — |

Yêu cầu đầu tiên của mỗi worker chậm tới ~160 ms: APISIX dựng plugin wasm lúc có yêu cầu đầu, Coraza đọc bộ luật
lúc đó (cả khi `Off`). Tệp lớn tốn RAM vì WAF giữ cả thân
trong bộ nhớ: mỗi worker tới ~230 MB sau khi soi tệp 24 MB.

### Hạn chế

- Coraza 3.3.3 còn bốn cách lẩn WAF mức medium (bảng trên) cho tới khi có bản WebAssembly đã vá.
- Nội dung tệp không qua WAF (ClamAV soi); khung tin trên WebSocket `/realtime` cũng không — chỉ yêu cầu mở kết nối.
- Trang tài khoản của Keycloak (`/realms/<realm>/account/…`, Signet không dẫn tới) dùng `PUT`, `DELETE`, `PATCH`:
  luật 911100 của CRS chỉ cho `GET HEAD POST OPTIONS` nên bị 403. Cần thì thêm một luật đặt
  `tx.allowed_methods` cho riêng đường đó.
- Chữ có dấu `+` thật xen số trong ngoặc (`(024)+3000+0000`) bị 942100 coi là SQLi. Gõ có dấu cách
  (`(024) 3000 0000`, `(+84) 912 345 678`) thì qua.
- Ô chữ tự do (10031, 10032) không còn luật chèn lệnh, PHP, RFI: chữ như `$(curl …|sh)`, `<?php …`, `http://<IP>/x`
  lưu được — cố ý, chữ chỉ được lưu và hiện ra. SQLi, XSS, duyệt thư mục, Log4Shell vẫn bị chặn ở đó.
- Các ô chữ ngắn khác (Cơ quan ban hành, Nơi nhận, Số hiệu, tên đơn vị, tên người…) vẫn soi đủ, không loại trừ vì chữ
  thật ở đó không có dạng này. Giá trị chỉ là một đường dẫn `http(s)://<IP>…` (931100), mở đầu bằng "File", "http",
  "ftp" và kết thúc bằng `?` (931120), hay có `${…}`, `file (` (932130, 933135, 933160) → 403. Ô Tìm kiếm: `${…}` → 403.
  Người dùng thấy: lưu không được, thường kèm "Có lỗi xảy ra: Unexpected token '<' … is not valid JSON" (giao diện đọc
  trang 403 của cổng như JSON); trong công cụ nhà phát triển, yêu cầu `/v1/graphql` trả `403` kèm `X-Request-Id`. Cách
  đi tiếp: thêm chữ trước đường dẫn ("Xem tại http://…"), bỏ dấu `?` cuối; người quản trị tra `X-Request-Id` (mục "Đọc
  nhật ký chặn") rồi thêm loại trừ nếu đó là chữ thật hay gặp.
- Cổng tốn thêm ~0,4–0,8 GB RAM (số đo trên).
