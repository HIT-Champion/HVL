# Vận hành Signet

Các việc của người quản trị trên một bản cài đang chạy: thêm đơn vị, sao lưu và khôi phục, két bí mật, GitOps và tự
phục hồi, giám sát, hội tụ IT/OT. Cài lần đầu: [README](../README.md), mục "Cài đặt từ mã nguồn"; lên máy chủ có tên
miền và HTTPS: [`trien-khai.md`](trien-khai.md). Lệnh vận hành là `python3 scripts/moc.py …` (tên mã kỹ thuật `moc`
giữ từ tên cũ của sản phẩm).

## Thêm đơn vị (thuê ước)

Một bản cài phục vụ nhiều đơn vị (khoa, phòng, trường thành viên); mỗi người chỉ thấy dữ liệu của đơn vị mình. Thêm
một đơn vị bằng một lệnh trên máy chủ, chạy lại được (đã có thì giữ nguyên, chỉ thêm phần còn thiếu):

```bash
python3 scripts/moc.py tenant create --code KTCK --name "Khoa Cơ khí" \
    --parent-name "Trường Đại học Công nghiệp" --place-name "Hà Nội" --head-title "Trưởng khoa" \
    --department "VP=Văn phòng khoa" --department "ĐT=Tổ Đào tạo" \
    --admin quantrick --admin-name "Lê Văn Cường" --admin-email quantri@ck.example.edu.vn --dry-run
# bỏ --dry-run để làm thật; rồi:
python3 scripts/moc.py tenant list           # đơn vị, phòng, người dùng, văn bản, Organization
python3 scripts/moc.py tenant check KTCK     # Organization, thành viên, danh bạ có khớp nhau không
```

- Lệnh ghi dòng `core.tenants` và các phòng (sổ kiểm toán ghi người chạy lệnh), tạo một **Organization** trong
  Keycloak (alias suy từ mã: `KTCK` → `ktck`, `ĐT` → `dt`; thuộc tính `tenant_id` = id của đơn vị) và tài khoản quản
  trị đơn vị (`tenant_admin`, không thuộc phòng nào) với mật khẩu tạm in ra **một lần**: lần đầu đăng nhập phải đổi
  mật khẩu và cài TOTP. Mất mật khẩu đó thì chạy lại lệnh với `--reset-password`.
- Lệnh đợi `svc-workflow` chép quản trị đơn vị vào danh bạ (tối đa 90 giây, `--wait`) rồi in những gì đã tạo, đã
  giữ, những gì tự có (sổ đăng ký, subscription NGSI-LD, lọc tìm kiếm, tiền tố tệp) và những gì dùng chung có chủ ý.
- Tài khoản khác của đơn vị (văn thư, lãnh đạo…) tạo trong trang quản trị Keycloak với `tenant_id`, `department_id`,
  `moc_role`, rồi chạy lại `tenant create` để đưa vào Organization; `tenant check` chỉ ra tài khoản còn thiếu hoặc
  lạc sang Organization của đơn vị khác (thoát 1). `make seed` tự làm việc này cho hai đơn vị mẫu.
- Không có bucket hay khóa dữ liệu riêng cho từng đơn vị: cách ly nằm ở token, quyền Hasura, ràng buộc CSDL và mã
  hóa gắn với đơn vị — lý do ở [`docs/mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §1. Riêng khóa ký số văn bản đi
  (F4.5, minh họa) là của từng đơn vị, để chứng thư nói được đơn vị nào phát hành; `svc-files` tự tạo nó trong két ở
  lần phát hành đầu của đơn vị.

## Sao lưu và khôi phục

`make backup` sao lưu mọi CSDL (dữ liệu nghiệp vụ, Keycloak, Flowable), toàn bộ tệp (SeaweedFS, kể cả các mốc
neo sổ kiểm toán) và két OpenBao (giữ khóa mở tệp văn bản hạn chế) vào kho [restic](https://restic.net) mã hóa ở `MOC_BACKUP_DIR` (mặc định `./backups`); lần sau
chỉ thêm phần đã đổi. Để mọi CSDL và tệp cùng một thời điểm, Signet tạm dừng ghi trong lúc dump CSDL (vài giây), còn
tải tệp lên, xuống thì đợi tới khi chép xong tệp. `make restore` kiểm bản sao lưu đọc được trọn vẹn, rồi mới dừng
Signet, thay CSDL và tệp bằng lượt mới nhất (hỏi lại trước), ghi lần khôi phục vào sổ kiểm toán rồi chạy lại; `make
audit` sau đó vẫn khớp mốc neo trong bucket. Mốc đã chép ra tệp ngoài máy chủ (`audit anchor --to`) sau lúc sao lưu
thì không còn khớp — đúng như vậy, vì các dòng đó đã mất; `make audit` chỉ ra lần khôi phục để đối chiếu.

```bash
python3 scripts/moc.py backup create --keep 14    # sao lưu, chỉ giữ 14 lượt mới nhất (đặt vào cron hằng đêm)
python3 scripts/moc.py backup list                # các lượt trong kho
python3 scripts/moc.py backup check               # kiểm cấu trúc kho
python3 scripts/moc.py backup restore 20261020-020000   # khôi phục một lượt cụ thể
```

- **Khóa kho là `MOC_BACKUP_PASSWORD` trong `.env`: mất khóa là mất bản sao lưu.** Chép `.env` ra ngoài máy chủ.
  Két khôi phục được mở bằng `MOC_OPENBAO_SEAL_KEY`, cũng trong `.env`: thiếu nó thì tệp văn bản hạn chế không mở
  được, dù dữ liệu đã về đủ. Cất bản chép `.env` ở chỗ khác với kho sao lưu: ai có cả hai là mở được mọi tệp mã hóa.
  Bản cài có từ trước khi có lệnh này: thêm vào `.env` của bản cài một dòng `MOC_BACKUP_PASSWORD=` với chuỗi ngẫu
  nhiên dài (vd. `openssl rand -hex 24`).
- Kho nên nằm trên ổ khác hoặc ổ mạng đã gắn vào máy chủ (`MOC_BACKUP_DIR=/mnt/nas/moc`, thư mục trống hoặc kho
  có sẵn), và chép thêm một bản ra ngoài đơn vị: kho chỉ gồm tệp đã mã hóa, chép bằng `rsync` được. restic chạy bằng
  root trong container (để đọc tệp của SeaweedFS): ổ NFS phải cho root ghi (`no_root_squash`).
- Chỉ mục tìm kiếm và chữ ký ClamAV không sao lưu: `svc-files` dựng lại chỉ mục từ CSDL khi khởi động, ClamAV tự
  tải chữ ký.

## Két bí mật

`svc-files` và `svc-workflow` không nhận khóa kho S3, khóa quản trị Hasura, mật khẩu Flowable… qua biến môi trường.
Lúc khởi động, mỗi dịch vụ đăng nhập két [OpenBao](https://openbao.org) bằng AppRole của riêng mình và chỉ đọc được
phần bí mật của mình; két ghi sổ mọi lần đăng nhập và đọc (`docker compose logs openbao`, giá trị đã băm HMAC). Két
dùng *static seal*: khởi động lại là tự mở khóa, không cần người nhập khóa. Két cũng giữ khóa `moc-files` (transit)
bọc khóa của từng tệp văn bản hạn chế: `svc-files` chỉ xin được khóa mới và nhờ két mở khóa đã bọc, không lấy được
khóa gốc. Từ F4.5 két có thêm PKI nội bộ để ký số văn bản đi (chỉ minh họa): CA gốc `moc-root` trong mount `pki`,
khóa ký `moc-ky-so-<đơn vị>` trong transit; `svc-files` nhờ két ký từng bản phát hành, không lấy được khóa riêng. Thử:
`make demo-ket-bi-mat`, `make demo-han-che`, `make demo-ky-so` (`docs/demo-script.md`).

Nói rõ giới hạn:

- `.env` vẫn là nguồn của các bí mật: container `openbao` nhận chúng qua biến môi trường và nạp lại vào két mỗi lần
  khởi động. Hasura, SeaweedFS, Meilisearch, Centrifugo (phần mềm thượng nguồn) vẫn đọc bí mật của chúng từ biến môi
  trường.
- Khóa mở két `MOC_OPENBAO_SEAL_KEY` nằm trong `.env`; khóa phục hồi, token khởi động và role_id/secret_id của dịch vụ
  nằm trong volume trên đĩa. Ai có quyền Docker trên máy chủ vẫn đọc được két. Két chỉ nằm trong mạng nội bộ
  `secrets` cùng hai dịch vụ (container khác không tới được), chưa có TLS.
- Két (volume `openbao_data`) nằm trong `make backup`. Mất volume mà không khôi phục thì két khởi tạo lại và nạp bí
  mật từ `.env`, nhưng khóa transit mới khác: tệp văn bản hạn chế đã lưu không mở được nữa.
- **Đổi `MOC_OPENBAO_SEAL_KEY` sau khi két đã khởi tạo thì két không mở được nữa.** Bản cài có từ trước khi có két:
  thêm vào `.env` của bản cài một dòng `MOC_OPENBAO_SEAL_KEY=` với chuỗi ngẫu nhiên dài (vd. `openssl rand -hex 32`).
- Đổi cấu hình két (thêm khóa, policy, PKI) cần token quản trị. Lần đầu khởi tạo, `openbao/start.sh` cấu hình bằng
  token root rồi thu hồi nó; các lần khởi động sau chỉ dùng token khởi động. Token khởi động không đọc thẳng được bí
  mật và không sửa được policy, nhưng cấp được secret_id nên làm được mọi việc hai dịch vụ làm được: giữ volume
  `openbao_data` như chính két.
- **PKI nội bộ (F4.5): CA gốc trong két, khóa ký từng đơn vị trong Transit; chỉ minh họa.** CA một tầng tự dựng
  (rsa-4096, 10 năm, không CRL, không OCSP), chứng thư của đơn vị sống 1 năm, không có dấu thời gian tin cậy: chữ ký
  không có giá trị pháp lý như chữ ký số công cộng. CA và khóa ký nằm trong volume `openbao_data`, đã có trong `make
  backup`. Policy của `svc-files` cho tạo, đọc, ký bằng `transit/keys/moc-ky-so-*`; glob này phủ cả `config`, `rotate`,
  `trim` và `import` của các khóa đó, và `pki/sign/moc-van-thu` ký mọi CSR. Ai chiếm được `svc-files` thì ký được, xoay
  được khóa ký, xin được chứng thư cho khóa tự sinh, nhưng không xuất được khóa riêng (không có `transit/export`,
  `transit/backup`). Mức tin này như trước: `svc-files` vốn đã mở được mọi khóa dữ liệu `moc-files`.
- **Két khởi tạo trước F4.5 không ký số** cho tới khi người quản trị nâng cấp tay hoặc dựng lại két: két đó chưa có
  PKI, policy của `svc-files` chưa có quyền ký, mà token khởi động không thêm được. `svc-files` thấy két chưa có CA thì
  tự tắt ký số (nhật ký `office.signing.disabled`, dò lại mỗi 5 phút): văn bản vẫn phát hành như cũ, chỉ không có chữ
  ký số; mọi thứ khác chạy như trước. Dựng PKI lỗi lúc khởi tạo két mới cũng vậy: `start.sh` ghi "chưa dựng được PKI
  nội bộ", két vẫn lên, và không tự thử lại.
- Nâng cấp tay một két cũ (một lần; dừng timer reconciler trước như mục GitOps bên dưới):
  1. Thêm tạm vào cuối `openbao/openbao.hcl` một listener chỉ nghe trong container, bật lại endpoint tạo token root bằng
     khóa phục hồi (OpenBao tắt mặc định từ 2.5.3; lệnh `bao operator generate-root` từ 2.6 cần sẵn token nên không
     dùng được ở đây), rồi `docker compose restart openbao`:
     ```hcl
     listener "tcp" {
       address                                  = "127.0.0.1:8210"
       tls_disable                              = true
       disable_unauthed_generate_root_endpoints = false
     }
     ```
  2. Tạo token root bằng khóa phục hồi, ghi vào `root-token` cạnh khóa phục hồi trong volume `openbao_data`. Khóa phục
     hồi, mã OTP và token chỉ đi qua tệp tạm (quyền 600) và stdin, không qua tham số dòng lệnh (`ps` nhìn thấy); bước
     nào không ra giá trị thì dừng, không ghi `root-token` rỗng:
     ```bash
     docker compose exec openbao sh -c '
       set -eu; umask 077
       A=http://127.0.0.1:8210/v1/sys/generate-root; K=/openbao/file/moc
       get() { sed -n "s/.*\"$1\":\"\([^\"]*\)\".*/\1/p"; }
       init=$(wget -qO- --post-data "{}" $A/attempt)     # két tự sinh mã OTP một lần
       otp=$(echo "$init" | get otp); nonce=$(echo "$init" | get nonce)
       [ -n "$otp" ] && [ -n "$nonce" ] || { echo "không mở được lượt tạo token root (đang có lượt dở?)"; exit 1; }
       printf "{\"key\":\"%s\",\"nonce\":\"%s\"}" "$(cat $K/recovery-key)" "$nonce" > $K/.generate-root
       enc=$(wget -qO- --post-file $K/.generate-root $A/update | get encoded_token); rm -f $K/.generate-root
       [ -n "$enc" ] || { echo "két không nhận khóa phục hồi"; exit 1; }
       printf "{\"encoded_token\":\"%s\",\"otp\":\"%s\"}" "$enc" "$otp" |
         bao write -field=token sys/decode-token - > $K/root-token.new
       [ -s $K/root-token.new ] && mv $K/root-token.new $K/root-token'
     ```
     Báo "đang có lượt dở" (lần chạy trước hỏng giữa chừng): hủy lượt đó bằng `docker compose exec -e
     BAO_ADDR=http://127.0.0.1:8210 openbao bao delete sys/generate-root/attempt` rồi chạy lại. Các bước này chưa diễn
     tập trên một két thật đã có dữ liệu: sao lưu (`make backup`) trước khi làm.
  3. Gỡ listener vừa thêm, `docker compose restart openbao`. Thấy token root, `start.sh` chạy lại phần cấu hình — làm
     lại được, không đổi bí mật, khóa `moc-files` hay AppRole; thêm PKI và policy mới của `svc-files` — rồi thu hồi
     token. Nhật ký két có "đã dựng PKI nội bộ"; `svc-files` bật ký số ở lần dò kế tiếp (hoặc `docker compose
     restart svc-files`).
- Cách cuối cùng là dựng lại két (xóa volume `openbao_data` rồi khởi động lại): bí mật nạp lại từ `.env`, có PKI, nhưng
  khóa `moc-files` mới khác nên tệp văn bản hạn chế đã lưu không mở được nữa — **không làm trên máy có dữ liệu thật**.
- Đổi bí mật trong `.env` rồi `make up`: két được dựng lại và nạp bí mật mới, `svc-files`, `svc-workflow` khởi động
  lại theo (`depends_on … restart: true`, cần Docker Compose 2.17 trở lên).

## GitOps và tự phục hồi

`scripts/reconcile.py` đưa hệ thống đang chạy về đúng trạng thái khai trong git, mỗi lượt một lần gọi. Trên máy chủ,
systemd timer gọi nó mỗi 60 giây (tệp mẫu [`ops/systemd/`](../ops/systemd/), chạy trên máy chủ chứ không trong
container: không gắn socket Docker vào container nào). Mỗi lượt:

- **Tự phục hồi**: container unhealthy thì khởi động lại; dịch vụ khai trong compose mà mất container hoặc đã dừng
  thì dựng lại (`docker compose up -d` đúng các dịch vụ đó). Thử: `make demo-tu-phuc-hoi` (`docs/demo-script.md`).
- **GitOps** (khi đặt `MOC_GITOPS_DIR` trong `.env` của bản cài): kéo nhánh `MOC_GITOPS_BRANCH` (mặc định `deploy`)
  về một bản sao git riêng của reconciler (bản sao có thay đổi chưa commit thì reconciler từ chối, không xóa việc của
  ai). Có commit mới, hoặc tệp đã cài bị sửa tay (khác băm lúc cài), thì dựng image của commit đó, dừng Signet, cài lại
  đúng commit vào thư mục cài rồi chạy lại. Cài hỏng giữa chừng thì cài lại commit đang chạy trước đó. Commit áp lỗi
  thì không thử lại mỗi phút mà đợi commit kế tiếp.

```bash
# trên máy chủ, đã make install PREFIX=/opt/moc; người vận hành moc thuộc nhóm docker
git clone -b deploy https://github.com/HIT-Champion/HVL.git /opt/moc-src
echo "MOC_GITOPS_DIR=/opt/moc-src" >> /opt/moc/.env
python3 /opt/moc/scripts/reconcile.py          # thử một lượt
sudo cp ops/systemd/moc-reconcile.* /etc/systemd/system/ && sudo systemctl enable --now moc-reconcile.timer
```

- Áp một commit là cài lại toàn bộ: Signet dừng khoảng một phút (`install.sh` không thay cấu hình dưới container đang
  chạy). Image cũ theo commit không tự xóa.
- `.env` (bí mật, cấu hình riêng của máy chủ) không nằm trong git và reconciler không đụng tới.
- Lượt reconciler bỏ qua khi đang sao lưu, khôi phục, `make install` (cả ba dùng chung một khóa trên thư mục cài),
  khi lần khôi phục trước dừng giữa chừng (không chạy lại Signet trên dữ liệu dở dang: chạy lại `backup restore`) hoặc
  có dịch vụ đang tạm dừng có chủ ý. Dịch vụ còn tạm dừng từ một lần sao lưu bị giết cứng thì reconciler chạy lại.
- Bảo trì tay (`docker compose down`, sửa cấu hình thử) thì tắt timer trước: `sudo systemctl stop moc-reconcile.timer`,
  không thì reconciler dựng lại trong vòng một phút.
- `make smoke` và `make demo-tu-phuc-hoi` gọi `reconcile.py --heal-only`: chỉ tự phục hồi, không kéo commit mới.
- **Chỉ áp commit đã ký** (nên bật trên máy chủ thật): đặt `MOC_GITOPS_ALLOWED_SIGNERS` là tệp allowed_signers
  liệt kê khóa SSH của người được đẩy nhánh `deploy`. Reconciler `git verify-commit` commit đầu nhánh trước khi dừng
  Signet; chưa ký, ký bằng khóa lạ, hay ký OpenPGP/X.509 (kể cả khi khóa có trong keyring của người dùng `moc`) thì
  không áp, Signet chạy tiếp bản cũ, lượt sau kiểm lại (thêm khóa vào tệp là áp được, không cần commit mới).

```bash
# máy người đẩy nhánh deploy (một lần): ký commit bằng khóa SSH sẵn có (.pub khi khóa nằm trong ssh-agent,
# không dùng agent thì trỏ tới tệp khóa riêng ~/.ssh/id_ed25519)
git config --global gpg.format ssh && git config --global user.signingkey ~/.ssh/id_ed25519.pub
# máy chủ: danh sách khóa được phép (chỉ root sửa được; id_ed25519.pub chép từ máy người đẩy), rồi bật
sudo install -d /etc/moc && echo "vuong@hvl namespaces=\"git\" $(cat id_ed25519.pub)" | sudo tee /etc/moc/allowed_signers
echo "MOC_GITOPS_ALLOWED_SIGNERS=/etc/moc/allowed_signers" >> /opt/moc/.env
```

  Đầu nhánh `deploy` phải là commit do người trong danh sách ký: đưa bản lên bằng `git merge --no-ff -S` thay cho
  `--ff-only` (`docs/git_flow.md` mục 7) — commit gộp trên GitHub mang chữ ký OpenPGP của GitHub, không được nhận.

## Giám sát

APISIX đếm mọi yêu cầu qua cổng (plugin `prometheus`, cổng xuất chỉ số 9091 chỉ trong mạng nội bộ). Prometheus thu
mỗi 15 giây, giữ `MOC_METRICS_RETENTION` (mặc định 15 ngày), không mở cổng ra ngoài. Grafana hiện bảng điều khiển
**Signet — cổng API** nạp sẵn: yêu cầu mỗi giây theo route, mã trạng thái (429 = vượt giới hạn tốc độ), tỉ lệ lỗi 5xx,
độ trễ p95, băng thông, kết nối đang mở.

- Grafana chỉ nghe `127.0.0.1:MOC_GRAFANA_PORT` (mặc định 3300) trên máy chủ — xem từ máy khác qua đường hầm SSH:
  `ssh -L 3300:127.0.0.1:3300 máy-chủ` rồi mở `http://localhost:3300`.
- Không có tài khoản Grafana: ai vào được cổng đó thì chỉ xem. Bảng điều khiển sửa trong
  `monitoring/grafana/dashboards/` rồi cài lại, không sửa trên giao diện.
- Grafana (AGPL-3.0) chạy nguyên bản trong container riêng; Signet chỉ nạp cấu hình qua tệp, không liên kết mã.
- Chỉ số không nằm trong bản sao lưu (`make backup`): khôi phục xong thì Prometheus thu lại từ đầu.

## Hội tụ IT/OT

Profile `iot` (không bật mặc định, khoảng 550 MB RAM) thêm context broker NGSI-LD **Scorpio** (chuẩn ETSI) cùng
CSDL PostGIS riêng của nó. Thiết bị cập nhật bản sao số của mình trong broker; `svc-workflow` giữ trong tenant NGSI-LD
của mỗi đơn vị (`NGSILD-Tenant` = mã đơn vị; mã có dấu thì `t` + băm của mã) một subscription
`temperature>MOC_OT_THRESHOLD`. Cảm biến vượt ngưỡng thì broker gọi `svc-workflow`, và dịch vụ dựng dự thảo văn bản
đi "Báo cáo sự cố" (loại Báo cáo, độ khẩn "Khẩn") từ mẫu cho chuyên viên phụ trách cảm biến, ghi sự kiện `ot.alarm`
vào dòng thời gian và báo người đó ngay. Còn dự thảo chưa trình (hoặc bị trả lại) của cùng cảm biến thì không dựng
thêm, chỉ nhắc người phụ trách, mỗi ngày nhiều nhất một lần. Dự thảo đi tiếp theo luồng văn bản đi như mọi văn bản
khác.

```bash
make demo-it-ot                       # bật profile iot, cảm biến giả lập 24 → 41 °C, dự thảo, trình
docker compose --profile iot --profile iot-sim run --rm ot-sensor --tenant CNTT --responsible chuyenviendt \
    --name "Phòng máy chủ tầng 3" --readings 30,36   # gửi tay vài lần đo
```

- Thực thể cảm biến `urn:ngsi-ld:TemperatureSensor:<mã>` có `name` (tên phòng), `responsible` (tên đăng nhập
  chuyên viên phụ trách) và `temperature` (°C, `observedAt`). Người phụ trách phải là chuyên viên đang hoạt động
  của đúng đơn vị, có phòng; không thì sự kiện bị bỏ qua (ghi nhật ký `ot.alarm_ignored`).
- Broker và CSDL của nó không mở cổng ra máy chủ. Ba mạng nội bộ riêng: thiết bị ↔ broker (`iot-devices`), broker ↔
  `svc-workflow` (`iot`), broker ↔ CSDL của nó (`iot-db`) — thiết bị không gọi được `svc-workflow`. Mỗi lần gọi
  `POST /ot/notify/<tenant>` phải kèm token riêng của đơn vị (HMAC từ khóa Actions của `svc-workflow`), sai thì 401.
- **Giới hạn:** broker không xác thực — ai vào được mạng thiết bị là ghi được vào tenant của đơn vị bất kỳ, kể cả
  khai người phụ trách là một chuyên viên của đơn vị đó. Triển khai thật phải đặt cổng thiết bị trước broker (IoT
  Agent hoặc PEP proxy của FIWARE) cấp tenant theo khóa của từng thiết bị; bản rút gọn chỉ có cảm biến giả lập.
- Broker gửi mỗi thông báo một lần: ghi CSDL lỗi thì lần vượt ngưỡng đó mất, lần đo kế tiếp còn trên ngưỡng sẽ dựng
  dự thảo.
- Cần `MOC_NGSI_DB_PASSWORD` trong `.env` (`make env` tự sinh). Thiết bị thật đi qua gateway IoT (vd IoT Agent
  của FIWARE) hoặc tự gửi NGSI-LD vào broker; lịch sử đo nằm trong broker (temporal API), không vào CSDL của Signet
  và không vào bản sao lưu.
- `make down` tắt cả profile `iot` và `iot-sim` (cảm biến giả lập, chỉ chạy một lần khi gọi).
