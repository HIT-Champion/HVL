# Vận hành Signet

Các việc của người quản trị trên một bản cài đang chạy: thêm đơn vị, sao lưu và khôi phục, két bí mật, GitOps và tự phục
hồi, giám sát, trang trạng thái hệ thống, hội tụ IT/OT. Cài lần đầu: [README](../README.md), mục "Cài đặt từ mã nguồn";
lên máy chủ có tên miền và HTTPS: [`trien-khai.md`](trien-khai.md). Lệnh vận hành là `python3 scripts/moc.py …` (tên mã
kỹ thuật `moc` giữ từ tên cũ của sản phẩm).

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
- Lượt sao lưu xong ghi dòng `system.backed_up` vào sổ kiểm toán; trang trạng thái hệ thống hiện giờ của lượt gần
  nhất từ dòng đó. Ghi không được thì lệnh chỉ cảnh báo, bản sao lưu vẫn dùng được.

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
- Đổi cấu hình két (thêm khóa, policy, PKI) cần token quản trị. Lần đầu khởi tạo, `platform/openbao/start.sh` cấu hình bằng
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
  1. Thêm tạm vào cuối `platform/openbao/openbao.hcl` một listener chỉ nghe trong container, bật lại endpoint tạo token root bằng
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
systemd timer gọi nó mỗi 60 giây (tệp mẫu [`platform/systemd/`](../platform/systemd/), chạy trên máy chủ chứ không trong
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
sudo cp platform/systemd/moc-reconcile.* /etc/systemd/system/ && sudo systemctl enable --now moc-reconcile.timer
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
  `platform/monitoring/grafana/dashboards/` rồi cài lại, không sửa trên giao diện.
- Grafana (AGPL-3.0) chạy nguyên bản trong container riêng; Signet chỉ nạp cấu hình qua tệp, không liên kết mã.
- Chỉ số không nằm trong bản sao lưu (`make backup`): khôi phục xong thì Prometheus thu lại từ đầu.

## Trang trạng thái hệ thống

`<MOC_PUBLIC_URL>/trang-thai` là trang công khai, không cần đăng nhập: người dùng tự xem Signet có đang chạy bình
thường không trước khi gọi bộ phận kỹ thuật. Trang đăng nhập (khi lỗi), chân trang của cổng xác thực và thanh bên sau
khi đăng nhập đều có đường tới đây. Trang tự làm mới mỗi 30 giây khi đang mở.

- **Hiện gì:** tình trạng chung và từng thành phần (*Hoạt động*, *Một phần*, *Gián đoạn*, *Tắt*) theo tầng người
  dùng → lõi → quy trình → dữ liệu → trí tuệ nhân tạo: Cổng API, Đăng nhập một lần, CSDL, Két khóa, Quét mã độc, Quy
  trình, Lưu trữ tệp, Tìm kiếm, Trợ lý AI; phiên bản (`MOC_VERSION`), thời gian `svc-files` chạy liên tục, giờ sao
  lưu gần nhất, trợ lý AI bật hay tắt kèm tên mô hình.
- **Đọc thế nào:** Cổng API, Đăng nhập một lần, CSDL, Quét mã độc, Quy trình, Lưu trữ tệp gián đoạn thì tình trạng
  chung là *Hệ thống đang gián đoạn*. Két khóa, Tìm kiếm, Trợ lý AI gián đoạn, hoặc thành phần nào chỉ chạy một phần,
  thì *Một số thành phần đang gặp sự cố*: văn bản hạn chế và ký số (két), tìm kiếm, hỏi đáp tạm không dùng được, còn
  lại vẫn chạy. Trợ lý AI *Tắt* (chưa bật profile `ai`, hoặc tắt hỏi đáp) là cấu hình, không phải sự cố.
- **Không lộ gì:** chỉ có nhãn cố định và trạng thái; không tên máy, địa chỉ IP, URL nội bộ, phiên bản từng thành phần,
  số người dùng hay số văn bản, thông báo lỗi. Lý do cụ thể nằm trong nhật ký của `svc-files` (sự kiện
  `core.status.changed`, ghi khi một thành phần đổi trạng thái): `docker compose logs svc-files | grep status.changed`.
- **Không thành đường tấn công:** `svc-files` lưu đệm kết quả 10 giây cho mọi người (`MOC_STATUS_CACHE_S`), mỗi lần
  dò một thành phần tối đa 3 giây (`MOC_STATUS_TIMEOUT_S`); APISIX giới hạn `MOC_RATE_STATUS_PER_MIN` (mặc định 30)
  lần một phút mỗi địa chỉ IP, vượt thì `429`.
- Trang chỉ trả lời "đang chạy hay không" ngay lúc này; diễn biến theo thời gian, độ trễ, tỉ lệ lỗi xem ở Grafana (mục
  Giám sát). API: `GET /api/status` ([`docs/api/README.md`](api/README.md) §3).

## Log tập trung

Profile `logs` (tắt mặc định) gom log của các dịch vụ về một chỗ để tra theo **mã yêu cầu**. APISIX gắn mã
`X-Request-Id` cho mọi yêu cầu (giữ mã client tự gửi, trả lại ở header của phản hồi) và ghi ở cuối dòng truy cập;
Hasura chuyển mã sang `svc-workflow`; `svc-workflow` ghi mã trong nhật ký, gửi tiếp sang Hasura và `svc-files`. Cùng
một mã nằm ở dòng log của APISIX, `svc-workflow`, `svc-files` và ở cột `request_id` của sổ kiểm toán
`core.audit_log`.

Đường đi: driver log `fluentd` của Docker → **Vector** 0.59 (cổng `127.0.0.1:24224` trên máy chủ, tách mã yêu cầu, che
lần hai) → **Parseable** 3.2 (lưu trên volume `parseable_data`, API và giao diện ở `127.0.0.1:8400`, tài khoản `moc`).
Driver đặt trong tệp compose phủ [`platform/logs/docker-compose.logs.yml`](../platform/logs/docker-compose.logs.yml),
chỉ nạp khi bật. Không gắn `docker.sock`, không đọc `/var/lib/docker`. `docker logs`, `make logs` vẫn đọc được như cũ
(Docker giữ bản cục bộ 10 MB × 3 cho driver ngoài).

- **Thu:** `apisix`, `app-office`, `app-ca-nhan`, `svc-files`, `svc-workflow` — các dịch vụ đã che thông tin cá nhân
  trong nhật ký (F4.4). **Không thu** Hasura, Keycloak, PostgreSQL, Meilisearch, OpenBao…: nhật ký của chúng chưa
  che, đưa vào kho log là đưa thông tin cá nhân chưa che đi xa thêm một chỗ.
- **Che lần hai** ([`platform/logs/vector.yaml`](../platform/logs/vector.yaml)), mỗi dạng dưới đây có ca trong
  [`vector.test.yaml`](../platform/logs/vector.test.yaml) (29 ca; bỏ một luật nào thì có ca đỏ):
  - token `Bearer`/`Basic` (từ 8 ký tự, kể cả có dấu `=` đệm ở cuối như `Basic dXNlcjpwYXNzd29yZA==`), chuỗi dạng JWT;
  - giá trị của khóa có chữ `password`, `passwd`, `pwd`, `secret`, `token`, `api key`, `private key`, `credential`,
    `session`, kể cả có tiền tố, hậu tố (`HASURA_ADMIN_SECRET=`, `POSTGRES_PASSWORD=`, `access_token`,
    `client_secret`, `x-api-key`): trong nháy kép, nháy đơn (dict Python trong traceback), hoặc không nháy (tới khóa kế
    tiếp, kể cả mật khẩu có dấu cách); nháy mở mà không đóng (dòng bị cắt giữa giá trị: `password="X…`,
    `{'password': 'X…`) thì tới hết dòng, trong một chuỗi của dòng JSON thì tới hết chuỗi đó;
  - giá trị đứng sau cờ dòng lệnh dài có chữ `passw`, `pwd`, `secret`, `token`, `key`, `credential`:
    `'--password', 'X'`, `'--api-key', 'X'` (list Python), `["--db-password", "X"]` (mảng JSON), `--password X` (cả ở
    đầu dòng);
  - cả giá trị của `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`: trong nháy thì tới hết nháy (nháy
    không đóng thì như trên); không nháy thì tới **hết dòng** (nhiều cặp `a=b; c=d`, `Digest username="u",
    response="…"`), riêng trong một chuỗi của dòng JSON thì tới hết chuỗi đó;
  - mật khẩu trong chuỗi kết nối `scheme://người:mật-khẩu@máy`;
  - chuỗi truy vấn của URL có `/` đứng trước `?` (tuyệt đối, tương đối, `máy:cổng/đường-dẫn` như
    `svc-files:8000/api/search?q=…`): không nháy, trong nháy đơn (`URL('…?q=…')`), trong nháy kép (cả giá trị trong
    nháy là URL thì bỏ hết chuỗi truy vấn, kể cả có dấu cách);
  - email (cả chữ có dấu, `@` viết `\u0040` hay `%40`), số điện thoại `0…`, `+84…`, `84…` (di động 10 số, cố định 11
    số), CCCD 12 số, kể cả dính chữ (`sđt0912…`) và hai số liền nhau;
  - số đứng sau từ khóa (cách tới 20 ký tự không phải chữ số), kể cả viết tách nhóm: `CCCD`/`căn cước`, `CMND`/`chứng
    minh` (từ 9 số), `STK`/`tài khoản`, `MST`/`mã số thuế` (từ 6 số), `SĐT`/`điện thoại`/`fax`/`tel`/`phone` (từ 8
    số), vd `CMND 123456789`, `STK 0011004123456`, `MST 0101234567`, `SĐT: 0912 345 678`. Từ khóa dính chữ cái phía
    sau (`telemetry`, `telegram`) không tính.

  Dòng JSON được giải mã rồi viết lại (khóa xếp theo chữ cái) trước khi che: ký tự thoát (`pass\u0077ord`) không giấu
  được chữ; khóa bí mật ở mọi tầng, mọi kiểu giá trị (số, `null`, object lồng) bị thay cả giá trị — kể cả khóa vô hại
  như `max_tokens`. Dòng không phải JSON thì được giải mã các chuỗi `\u00XX` là ký tự ASCII in được (trừ khi đứng sau
  một dấu `\` thật; chữ số hex là chữ hoa hay thường, nhiều mã liền nhau) trước khi che: khóa viết thoát trong đoạn
  JSON nằm giữa dòng thường (`ERROR {"pass\u0077ord": …}`) cũng bị che. Dòng dài hơn 16 KiB Docker cắt làm nhiều bản
  ghi: Vector ghép lại (theo container và mã mảnh, xong ngay ở mảnh cuối) trước khi che (đã thử với driver thật: dòng
  40 000 byte vẫn tách được `request_id`, mật khẩu vắt qua chỗ cắt vẫn bị che); dòng thường không bị gộp; thông điệp
  cắt ở 16 384 ký tự. Lỗi lúc chạy bước che thì bỏ dòng, không gửi nguyên văn (`drop_on_error: true`, có
  test tĩnh trong `scripts/tests/test_log_tap_trung.py` vì `vector test` không gây được lỗi lúc chạy).

  Chỉ là lưới an toàn cho dòng lọt qua (dòng lỗi nginx, traceback), **không thay** lớp che của từng dịch vụ (F4.4).
  **Còn lọt** (đã thử 24/10/2026):
  - số không có từ khóa đứng trước mà viết tách nhóm (`0912 345 678`, `0912.345.678`, `(+84) 912-345-678`,
    `(+84)912345678`, `+84 912345678`, `84-912-345-678`, `024 3869 1234`) hoặc không đúng dạng số điện thoại, CCCD
    (CMND 9 số, số tài khoản, mã số thuế đứng một mình như `123456789`, `0011004123456`, `0101234567`); từ khóa dính
    chữ cái phía sau (`phones 0912 345 671`);
  - họ tên, địa chỉ; số dính liền chữ số khác;
  - khóa không có các chữ trên: `pass`, `passphrase`, `pin`, `otp`, `auth`, `key`, `signature` (cả
    `X-Amz-Signature`), khóa tiếng Việt (`mat_khau`, `khoa_bi_mat`);
  - cờ dòng lệnh ngắn: `'-p', 'X'`, `-pX`; giá trị cờ bắt đầu bằng `-` (`--password -X`); thân khóa PEM (base64 đứng
    riêng một dòng);
  - header dạng cặp trong list, tuple, mảng JSON (`[(b'authorization', b'Digest …')]`, `Headers([('cookie',
    'sid=…')])`, `{"headers": [["Cookie", "sid=…"]]}`): chỉ được che khi giá trị là token `Bearer`/`Basic`, JWT, hay
    cặp có khóa chứa chữ `session` (`KEYCLOAK_SESSION=…`, `AUTH_SESSION_ID=…`, `session=…`);
  - chuỗi JSON nằm trong chuỗi JSON (thoát hai tầng: `{"body": "{\"inner\": \"{\\\"password\\\": …}\"}"}`; thoát
    một tầng thì vẫn che); giá trị có `\u0022` (dấu `"` viết thoát; Python, Node viết `\"`): bước giải mã đổi nó thành
    `"` nên phần sau lọt (`"ab\u0022cd X"` thành `"[REDACTED]"cd X"`);
  - hai giá trị nháy đơn không đóng trên cùng một dòng (`Cookie: 'a ; token: 'X`): phần sau dấu nháy thứ hai;
  - chuỗi truy vấn không có `/` đứng trước (`search?q=…`); chuỗi truy vấn có dấu cách chỉ bỏ tới dấu cách đầu khi
    không nháy, trong nháy đơn (`URL('svc-files:8000/x?q=Tran Thi B')` còn `Thi B`) hay nằm giữa chuỗi nháy kép
    (`msg="tim svc-files:8000/a?q=Do Thi I"`);
  - số sau từ khóa tách nhóm bằng dấu cách không ngắt (U+00A0); từ khóa gõ dạng Unicode tổ hợp (NFD);
  - ký tự nhiều byte nằm đúng chỗ Docker cắt thành `�`; dòng quá 64 mảnh (khoảng 1 MiB) hoặc mảnh cuối tới sau 10
    giây thì che từng phần (bí mật vắt qua chỗ chia lọt).

  **Che thừa** (không lọt, chỉ mất chữ): khóa vô hại có chữ `token`, `session`, `pwd` (`max_tokens`,
  `session_timeout=3600`, `PWD=/app`); số, kể cả ngày giờ, nằm trong 20 ký tự sau từ khóa (`tài khoản a lúc
  2026-10-24 10:00` thành `tài khoản a lúc [STK]:00`); đoạn giống số điện thoại, CCCD trong chuỗi hex (mã
  `uuid4().hex`) — cột `request_id` tách trước khi che nên vẫn tra đúng; phần còn lại của dòng sau `Authorization`,
  `Cookie` không nháy, sau nháy không đóng (dòng JSON: của chuỗi đó), sau giá trị cờ dòng lệnh không nháy (tới khóa
  `a=` kế tiếp: `--password X --host db` thành `--password [REDACTED]`, `--no-password db_moc --format c`,
  `--sort-key name` cũng bị che); từ dài từ 8 ký tự đứng sau chữ `basic`, `bearer` (`basic authentication`); dấu `,`
  `;` ngay sau giá trị bị che (`token=X,user=a` thành `token=[REDACTED]user=a`).
- **Cột** của luồng `moc`: `service`, `container`, `stream` (stdout/stderr), `timestamp`, `event`, `request_id` (dòng
  JSON của `svc-files`, `svc-workflow`; dòng của APISIX; chỉ mã đúng dạng `[A-Za-z0-9._:-]{1,128}`, như `event`),
  `message`; Parseable thêm `p_timestamp` (giờ nhận, UTC), `p_src_ip` (IP của Vector trong mạng `logs`),
  `p_user_agent` (của Vector).

```bash
make logs-up                       # bật: Vector, Parseable; tạo lại 5 container; đặt giữ log; tới lần make up sau
make logs-tra ID=<mã>              # dòng của mọi dịch vụ mang mã, 60 phút gần nhất (PHUT=… để đổi)
make demo-log-tap-trung            # màn demo: một mã đi qua APISIX → svc-workflow → svc-files
make logs-down                     # tắt: 5 dịch vụ về json-file, dừng Vector, Parseable; giữ log đã lưu
```

- **Bật lâu dài:** thêm `logs` vào `MOC_EXTRA_PROFILES` trong `.env` (vd `MOC_EXTRA_PROFILES=tunnel,logs`) rồi chạy
  `make up` (hoặc `make logs-up`); từ đó `make up`, `make down`, `make ps`… tự nạp tệp phủ và profile, và mỗi lần
  `make up` thêm mật khẩu vào `.env` cũ nếu thiếu, tạo luồng, đặt lại thời gian giữ log (kể cả sau khi xóa volume
  `parseable_data`). Chỉ `make logs-up` mà không thêm vào `MOC_EXTRA_PROFILES` thì `make up` lần sau trả 5 dịch vụ về
  `json-file` (Vector, Parseable vẫn chạy nhưng không nhận gì).
- **Mật khẩu:** `MOC_LOGS_PASSWORD` do `make env` sinh; `.env` sinh trước F3.14 thiếu dòng này thì `make logs-up` (và
  `make up` khi `logs` có trong `MOC_EXTRA_PROFILES`) tự thêm một chuỗi ngẫu nhiên đúng như `make env` (không in ra).
  Dòng có mà rỗng thì hai lệnh này dừng; Parseable cũng không khởi động khi mật khẩu rỗng (biến `P_ADDR` rỗng) — không
  bao giờ mở cổng nhận đăng nhập rỗng. Như các mật khẩu khác của repo (`POSTGRES_PASSWORD`…), mật khẩu này hiện
  nguyên văn trong `docker compose config` và `docker inspect` của `parseable` (biến `P_PASSWORD`; Parseable 3.2.4
  không đọc mật khẩu từ tệp). Vector đọc từ compose secret: không có trong biến môi trường, cấu hình, log của Vector.
- **Mã yêu cầu lấy ở đâu:** header `X-Request-Id` của phản hồi (công cụ phát triển của trình duyệt, tab Network); câu
  lỗi "đã ghi nhật ký với mã …" của Hasura Actions; cột `request_id` của sổ kiểm toán. Việc nền không có yêu cầu gốc
  (tác tử gợi ý giao việc) dùng mã `goi-y:<việc>`.
- **Giao diện:** `http://127.0.0.1:8400`, tài khoản `moc`, mật khẩu `MOC_LOGS_PASSWORD`; từ máy khác qua đường hầm
  SSH: `ssh -L 8400:127.0.0.1:8400 máy-chủ`. Tra bằng SQL trên luồng `moc`, vd
  `select p_timestamp, service, event, message from moc where service = 'svc-workflow' order by p_timestamp desc
  limit 50`. Gói giao diện có tham chiếu tới máy chủ ngoài (phông chữ, công cụ hỗ trợ của Parseable) — chưa kiểm lúc
  chạy có tải không; đường chính là `make logs-tra` và API. Xem rủi ro CORS ở dưới.
- **Giữ log:** `MOC_LOGS_RETENTION_DAYS` ngày (mặc định 7); Parseable xóa dữ liệu cũ mỗi ngày lúc 00:00 UTC. Đổi số
  ngày thì chạy lại `python3 scripts/log_tap_trung.py init`. Kho log **không** nằm trong bản sao lưu (`make backup`).
- **Xóa hẳn log đã lưu:** sau `make logs-down`, `docker volume rm moc_parseable_data` (`make reset` cũng xóa).
- **Bản cài** (`make install`): `MOC_EXTRA_PROFILES` có `logs` thì `install.sh` ghi `COMPOSE_FILE` (tệp phủ) vào `.env`
  của bản cài, `docker compose` gõ tay và reconciler đều nạp; `.env` của bản cài phải có `MOC_LOGS_PASSWORD`; chạy
  `python3 scripts/log_tap_trung.py init` trong thư mục cài một lần để đặt thời gian giữ log. Reconciler chỉ dựng lại
  profile `core`, `app`: Vector, Parseable tự khởi động lại nhờ `restart: unless-stopped`, không được tự phục hồi khi
  mất container.
- **Kiểm cấu hình** không cần bật, không mạng, chỉ gắn tệp trong repo (CI có thể chạy cùng lệnh):

  ```bash
  V=timberio/vector:0.59.0-distroless-static@sha256:2138c72ef15477d3a60126da851407a198ec61d2ff4cd600a4e69db5f6a29ff7
  M=(-v "$PWD/platform/logs:/etc/vector:ro"
     -v "$PWD/platform/logs/kiem-tra/mat-khau-gia.txt:/run/secrets/moc_logs_password:ro")
  docker run --rm --network none "${M[@]}" "$V" validate --deny-warnings /etc/vector/vector.yaml
  docker run --rm --network none "${M[@]}" "$V" test /etc/vector/vector.yaml /etc/vector/vector.test.yaml
  ```

**Rủi ro, hạn chế người vận hành cần biết:**

- **Bật hay tắt phải tạo lại 5 container** (`apisix`, `app-office`, `app-ca-nhan`, `svc-files`, `svc-workflow`): vài
  giây gián đoạn; đổi driver log chỉ có hiệu lực khi tạo lại container.
- **Cổng fluent `127.0.0.1:24224` không cần đăng nhập** (driver `fluentd` của Docker không có xác thực): tiến trình
  nào trên máy chủ cũng gửi được dòng giả vào kho log (dòng giả vẫn qua bước che). Máy chủ dùng chung nhiều người thì
  đây là hạn chế thật.
- **Vector dùng tài khoản quản trị duy nhất `moc` của Parseable** (qua compose secret, không qua biến môi trường): chưa
  tách tài khoản chỉ được nạp; ai đọc được secret trong container Vector là có toàn quyền kho log.
- **Parseable chạy bằng root** trong container, nhưng bỏ mọi capability (`cap_drop: [ALL]`) và
  `no-new-privileges`. Không chạy được bằng uid khác 0: trên volume mới Parseable không tạo được thư mục và dừng
  ("Permission denied", đã thử 23/10/2026). Image distroless, không có shell nên không có healthcheck; chỉ ở mạng
  `logs`, không tới được dịch vụ nào khác của Signet. Mạng `logs` không `internal` (phải mở cổng 127.0.0.1) nên
  Parseable, Vector ra Internet được; đã tắt kiểm bản cập nhật và gửi số liệu sử dụng của Parseable.
- **CORS của Parseable cho `https://cdn.parseable.com`:** Parseable 3.2.4 luôn cho nguồn này gọi API kèm thông tin
  đăng nhập (preflight 200, `access-control-allow-credentials: true`); nguồn khác thì không. Không tắt được:
  `P_CORS=false` còn mở cho **mọi** nguồn, `P_ALLOW_ORIGINS` chỉ thêm nguồn (đã thử 23/10/2026). Nghĩa là trang trên
  `cdn.parseable.com` mở trong trình duyệt đang đăng nhập giao diện Parseable có thể đọc kho log. Gói giao diện còn
  tham chiếu `orchestrator.cloud-staging.parseable.com`. Giảm rủi ro: tra bằng `make logs-tra`; dùng giao diện thì
  dùng xong đóng trình duyệt hoặc dùng hồ sơ trình duyệt riêng.
- **Mất log khi Parseable hoặc Vector chết lâu:** Parseable không nhận thì Vector giữ tới 10 000 dòng trong bộ nhớ rồi
  bỏ dòng mới; Vector chết thì Docker đệm trong bộ nhớ có giới hạn (`mode: non-blocking`, `max-buffer-size: 4m`) rồi
  bỏ — dịch vụ không bị chặn. Bản cục bộ (`docker logs`) vẫn còn. Đo bằng driver thật (kiểm thử độc lập, 23/10/2026):
  dừng Vector (`docker stop -t 1`) thì mất 13 dòng đang trong lô của Vector; dòng của container chạy lâu ghi lúc
  Vector chết vẫn tới sau khi Vector chạy lại; container ngắn hạn ghi lúc Vector chết thì mất hết (0/100 000 dòng).
- **Lớp che của Vector không thay được F4.4:** chỉ thu dịch vụ đã che; dịch vụ mới muốn thu thì phải che trong chính nó
  trước.
- `X-Request-Id` do client đặt được (APISIX giữ mã client gửi). `svc-workflow` chỉ nhận mã khớp
  `[A-Za-z0-9._:-]{1,128}`, mã khác thì thay bằng mã mới (trả lại ở header); `svc-files` chưa kiểm (như từ trước):
  chuỗi tùy ý vào nhật ký và các dòng sổ kiểm toán nó ghi. Vector chỉ đưa mã đúng dạng đó vào cột `request_id`;
  `make logs-tra` kiểm mã trước khi ghép vào câu SQL.
- Không có tracing (span, thời gian từng chặng): chỉ nối dòng theo mã. Docker rootless và Docker Desktop (dockerd
  không chung mạng với máy chủ): chưa thử cổng `127.0.0.1:24224`. RAM lúc nghỉ khoảng 18 MiB (Vector) và 45 MiB
  (Parseable) — `docker stats` trên máy dev ngày 23/10/2026; dưới tải chưa đo.

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
