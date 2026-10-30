# Vận hành Signet

**English:** [van-hanh.en.md](van-hanh.en.md)

Các việc của người quản trị trên một bản cài đang chạy: thêm đơn vị, sao lưu và khôi phục, két bí mật, GitOps và tự phục
hồi, giám sát, trang trạng thái hệ thống, wiki nội bộ, tự động hóa bằng Node-RED, hội tụ IT/OT. Cài lần đầu:
[README](../README.md), mục "Cài đặt từ mã nguồn"; lên máy chủ có tên miền và HTTPS: [`trien-khai.md`](trien-khai.md).
Lệnh vận hành là `python3 scripts/moc.py …` (tên mã kỹ thuật `moc` giữ từ tên cũ của sản phẩm).

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
- Đã bật wiki nội bộ thì chạy thêm `python3 scripts/moc.py wiki sync` để đơn vị mới có không gian riêng (mục Wiki
  nội bộ); chưa chạy thì người của đơn vị mới chỉ đọc được trang đầu của wiki.

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
- Wiki nội bộ (profile `wiki`): volume `wiki_data` vào cùng lượt, wiki tạm dừng trong lúc chép volume của nó (CSDL,
  tệp không chờ). Khôi phục thay cả volume đó; wiki đang chạy thì dừng trước, chạy lại sau. Lượt sao lưu có từ trước
  khi có wiki thì giữ nguyên wiki đang có.
- Tự động hóa Node-RED (profile `tu-dong`): volume `tu_dong_data` vào cùng lượt theo đúng cách đó (Node-RED tạm dừng
  lúc chép, dừng trước khi khôi phục, chạy lại sau).
- Lượt sao lưu xong ghi dòng `system.backed_up` vào sổ kiểm toán; trang trạng thái hệ thống hiện giờ của lượt gần
  nhất từ dòng đó. Ghi không được thì lệnh chỉ cảnh báo, bản sao lưu vẫn dùng được.

## Két bí mật

`svc-files` và `svc-workflow` không nhận khóa kho S3, khóa quản trị Hasura, mật khẩu Flowable… qua biến môi trường.
Lúc khởi động, mỗi dịch vụ đăng nhập két [OpenBao](https://openbao.org) bằng AppRole của riêng mình và chỉ đọc được
phần bí mật của mình; két ghi sổ mọi lần đăng nhập và đọc (`docker compose logs openbao`, giá trị đã băm HMAC). Két
dùng *static seal*: khởi động lại là tự mở khóa, không cần người nhập khóa. Két cũng giữ khóa `moc-files` (transit)
bọc khóa của từng tệp văn bản hạn chế: `svc-files` chỉ xin được khóa mới và nhờ két mở khóa đã bọc, không lấy được
khóa gốc. Từ F4.5 két có thêm PKI nội bộ để ký số văn bản đi (chỉ minh họa): CA gốc `moc-root` trong mount `pki`,
khóa ký `moc-ky-so-<đơn vị>` trong transit; `svc-files` nhờ két ký từng bản phát hành, không lấy được khóa riêng. Két
còn giữ khóa Ed25519 `moc-anchor` (transit) ký mốc neo sổ kiểm toán: `svc-files` chỉ ký và đọc khóa công khai (mục Mốc
neo công khai bên dưới). Thử: `make demo-ket-bi-mat`, `make demo-han-che`, `make demo-ky-so` (`docs/demo-script.md`).

Nói rõ giới hạn:

- `.env` vẫn là nguồn của các bí mật: container `openbao` nhận chúng qua biến môi trường và nạp lại vào két mỗi lần
  khởi động. Phần mềm thượng nguồn vẫn đọc bí mật của chúng từ biến môi trường: PostgreSQL, Keycloak, Flowable,
  Hasura, SeaweedFS, Meilisearch, Centrifugo, và Parseable, Scorpio, restic khi bật profile của chúng.
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
- **Két khởi tạo trước khi có chữ ký mốc neo không ký mốc** cho tới khi nâng cấp tay như dưới đây: két đó chưa có khóa
  `moc-anchor`, policy của `svc-files` chưa có quyền ký. `svc-files` vẫn neo vào bucket lạnh như trước, chỉ không có chữ
  ký (nhật ký `core.audit.anchor_unsigned`, một lần mỗi lần khởi động); `/api/verify/anchor-key.pem` trả 404, trang
  `/xac-thuc` ẩn khối mốc neo; `moc audit anchor --to`, `--publish` ghi dòng không chữ ký. Mốc cũ không chữ ký vẫn hợp
  lệ khi kiểm. Nâng cấp xong, `svc-files` ký từ lượt neo kế tiếp, không cần khởi động lại: policy mới áp ngay cho token
  đang dùng.
- Nâng cấp tay một két cũ, một lần: dừng timer reconciler trước như mục GitOps bên dưới, sao lưu (`python3
  scripts/moc.py backup create`), rồi từ thư mục mã nguồn của bản đang cài chạy `scripts/nang_cap.sh ket /opt/moc`.
  Két đã có khóa `moc-anchor` (`/api/verify/anchor-key.pem` trả khóa công khai) thì kịch bản không làm gì. Các bước:
  1. Thêm tạm vào cuối `platform/openbao/openbao.hcl` của bản cài một listener chỉ nghe trong container
     (`127.0.0.1:8210`, `disable_unauthed_generate_root_endpoints = false`): bật lại endpoint tạo token root bằng khóa
     phục hồi, OpenBao tắt mặc định từ 2.5.3; lệnh `bao operator generate-root` từ 2.6 cần sẵn token nên không dùng
     được ở đây. Khởi động lại két.
  2. Trong container, tạo token root bằng khóa phục hồi, ghi vào `root-token` cạnh khóa phục hồi trong volume
     `openbao_data`. Khóa phục hồi, mã OTP và token chỉ đi qua tệp tạm (quyền 600) và stdin, không qua tham số dòng
     lệnh (`ps` nhìn thấy); bước nào không ra giá trị thì dừng, không ghi `root-token` rỗng.
  3. Trả `openbao.hcl` về đúng bản đã cài, khởi động lại két. Thấy token root, `start.sh` chạy lại phần cấu hình — làm
     lại được, không đổi bí mật, khóa `moc-files` hay AppRole; thêm PKI, khóa `moc-anchor` và policy mới của
     `svc-files` — rồi thu hồi token (nhật ký két: "đã cấu hình két; token root đã thu hồi"). Kịch bản khởi động lại
     `svc-files` (nó nhớ kết quả đọc khóa 5 phút) và chờ `/api/verify/anchor-key.pem` ra một khối `PUBLIC KEY`;
     `svc-files` ký mốc neo từ lượt neo kế tiếp.

  Lỗi ở bất kỳ bước nào thì kịch bản hủy lượt tạo token root còn dở, trả `openbao.hcl` về như cũ, khởi động lại két;
  sửa lỗi rồi chạy lại. Két không tự cấu hình xong thì token root vừa tạo còn nằm trong volume: kịch bản in lệnh thu
  hồi và xóa nó, dùng khi không chạy lại nữa. Job CI `.github/workflows/nang-cap.yml` tập đúng kịch bản này trên két
  của bản phát hành trước, sau khi nâng bản cài lên: tệp văn bản hạn chế tạo từ bản cũ vẫn mở được, smoke đạt.
- Cách cuối cùng là dựng lại két (xóa volume `openbao_data` rồi khởi động lại): bí mật nạp lại từ `.env`, có PKI, nhưng
  khóa `moc-files` mới khác nên tệp văn bản hạn chế đã lưu không mở được nữa — **không làm trên máy có dữ liệu thật**.
  Khóa `moc-anchor` cũng mới: mốc đã công bố trước đó vẫn kiểm được bằng khóa cũ còn trong lịch sử kho mốc công khai.
- Đổi bí mật trong `.env` rồi `make up`: két được dựng lại và nạp bí mật mới, `svc-files`, `svc-workflow` khởi động
  lại theo (`depends_on … restart: true`, cần Docker Compose 2.17 trở lên).

## Mốc neo công khai

Sổ kiểm toán là một chuỗi băm; `svc-files` neo đầu chuỗi (số dòng cuối, hash của nó) vào bucket lạnh khóa ghi mỗi 10
phút, và `moc audit verify` chỉ ra dòng bị viết lại khi đối chiếu với các mốc (`docs/mo-hinh-du-lieu.md` §1). Bucket
đó vẫn nằm trên chính máy chủ. Mốc neo công khai đưa một bản ra ngoài, ai cũng kiểm được mà không phải tin máy chủ:

- Két ký mỗi mốc bằng khóa Ed25519 `moc-anchor` trong transit — két sinh khóa, không cho xuất; policy của `svc-files`
  chỉ cho ký và đọc khóa công khai. Mốc ghi khi két chưa có khóa (két cũ, mục Két bí mật) vẫn hợp lệ, chỉ không có chữ
  ký.
- Mỗi giờ, timer trên máy chủ chép mốc mới nhất kèm chữ ký vào `anchors.jsonl` của một **kho git công khai** do đơn vị
  giữ, commit và đẩy lên. Nhánh của kho cấm đẩy ép, nên mốc đã công bố không rút lại được, kể cả khi máy chủ bị chiếm.
- Khóa công khai: `https://<máy chủ>/api/verify/anchor-key.pem` (không cần đăng nhập), bản sao `anchor-key.pem` trong
  kho mốc; vân tay SHA-256 hiện ở cuối trang `/xac-thuc`.

Thông điệp két ký cho một mốc là năm dòng UTF-8, dòng nào cũng kết thúc bằng một ký tự xuống dòng (`\n`):

```text
signet-anchor-v1
<audit_id: số dòng sổ, thập phân>
<hash: 64 chữ hex thường>
<anchored_at: lúc kho ghi mốc vào bucket lạnh, giờ UTC, dạng 2026-10-25T01:15:03Z>
<system: URL công khai của hệ thống, MOC_PUBLIC_URL>
```

Chữ ký là Ed25519 thuần (RFC 8032, không băm trước). Dòng đầu tách chữ ký này khỏi mọi việc ký khác, `system` gắn mốc
với đúng một hệ thống (mốc của bản chạy thử không mạo được mốc của bản thật). Mọi trường đều suy ra từ mốc đã khóa
trong bucket, nên ký lại một mốc ra đúng chữ ký cũ. Mỗi dòng của `anchors.jsonl` chứa đủ các trường để dựng lại thông
điệp, kèm vân tay khóa (`key`, SHA-256 của DER khóa công khai) và chữ ký (`sig`, base64) — trong tệp là một dòng,
ở đây ngắt ra cho dễ đọc:

```json
{"v": "signet-anchor-v1", "audit_id": 42, "hash": "abab…ab", "anchored_at": "2026-10-25T01:15:03Z",
 "system": "https://signet.example", "key": "sha256:06e3fd8f…", "sig": "6Zd3HmfkSkXW…"}
```

### Cài đặt (một lần)

1. **Tạo một kho công khai riêng** cho mốc, vd `signet-anchors` trên GitHub, GitLab hay Gitea của đơn vị — không chứa
   gì khác, không dùng chung với mã nguồn. Bảo vệ nhánh mặc định: **cấm đẩy ép (force push), cấm xóa nhánh**, không
   bắt buộc review (máy chủ đẩy thẳng). GitHub: Settings → Rules → Rulesets (hoặc Branches) → bật *Block force pushes*,
   *Restrict deletions* cho nhánh mặc định, không cho ai bỏ qua (kể cả quản trị). GitLab: Settings → Repository →
   Protected branches, *Allowed to force push* tắt.
2. **Khóa triển khai** (deploy key) chỉ ghi được vào đúng kho đó, không dùng token cá nhân hay khóa của người nào. Trên
   máy chủ, bằng người vận hành `moc`:
   ```bash
   ssh-keygen -t ed25519 -N '' -C "signet-anchor@$(hostname)" -f ~/.ssh/signet-anchors
   cat >> ~/.ssh/config <<'CONF'
   Host signet-anchors
     HostName github.com
     User git
     IdentityFile ~/.ssh/signet-anchors
     IdentitiesOnly yes
   CONF
   ```
   Thêm `~/.ssh/signet-anchors.pub` vào kho: GitHub Settings → Deploy keys → *Allow write access*; GitLab Settings →
   Repository → Deploy keys → *Grant write permissions*. Khóa này không đọc hay ghi được kho nào khác.
3. **Bản sao trên máy chủ**, đúng đường dẫn trong `platform/systemd/moc-anchor-publish.service`:
   ```bash
   sudo install -d -o moc -g moc /var/lib/moc
   sudo -u moc git clone signet-anchors:<tổ chức>/signet-anchors.git /var/lib/moc/neo-cong-khai
   sudo -u moc python3 /opt/moc/scripts/moc.py audit anchor --publish /var/lib/moc/neo-cong-khai   # thử một lượt
   ```
   Lượt đầu commit `anchors.jsonl` và `anchor-key.pem` với tác giả cố định "Signet anchor", thông điệp `Anchor #<số
   dòng> <16 chữ hex đầu của hash>`, rồi `git push` lên `origin`.
4. **Timer** (tệp mẫu, như reconciler GitOps):
   ```bash
   sudo cp platform/systemd/moc-anchor-publish.service platform/systemd/moc-anchor-publish.timer /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now moc-anchor-publish.timer
   journalctl -u moc-anchor-publish -f
   ```

`--publish` chỉ thêm commit: không bao giờ `--force`, không amend, không viết lại lịch sử. Đầu chuỗi chưa đổi thì
không có commit mới. Push lỗi (mất mạng, kho từ chối) thì lệnh thoát 2, commit vẫn nằm ở bản sao và lượt sau đẩy
tiếp; nhánh trên kho đã đi khác (ai đó đẩy commit khác) thì push bị từ chối và người vận hành phải xem tay — lệnh không
tự ép. Bản sao chưa có remote thì chỉ commit tại chỗ. Không dùng kho git: `moc audit anchor --to TỆP` chỉ ghi thêm
dòng vào một tệp để chép ra ngoài bằng cách khác.

Két đã có khóa thì không mốc nào được ghi ra tệp mà thiếu chữ ký: két không trả lời lúc ký (hoặc lúc hỏi khóa), tệp
đã có dòng có chữ ký, hay cạnh tệp đã có `anchor-key.pem` thì `--to`/`--publish` không ghi dòng chưa ký, thoát 2, và
lượt sau ký lại (cùng mốc ra cùng chữ ký). Nhờ vậy người kiểm coi một dòng chưa ký đứng sau dòng đã ký là chữ ký đã bị
gỡ — lỗi như chữ ký sai. `--publish` chỉ ghi `anchor-key.pem` khi tệp đã có dòng có chữ ký, nên `anchor-key.pem` nằm
cạnh một tệp không còn dòng ký nào cũng là lỗi; `anchor_sig.py` không thấy dòng nào có chữ ký thì thoát 2 (chưa kiểm
được gì). Dòng chưa ký đứng trước mọi dòng đã ký là mốc ghi khi két chưa có khóa: ai gỡ chữ ký của những dòng đầu tệp
(giữ lại dòng ký sau đó) thì chỉ lịch sử git của kho công khai cho thấy (lệnh `git log -p` ở dưới).

### Kiểm từ bên ngoài (chỉ cần git, jq, OpenSSL 3)

```bash
git clone https://github.com/<tổ chức>/signet-anchors.git && cd signet-anchors
# khóa đúng của hệ thống: vân tay phải trùng vân tay ở cuối trang https://<máy chủ>/xac-thuc
openssl pkey -pubin -in anchor-key.pem -outform DER | sha256sum
# lịch sử chỉ có thêm dòng: lệnh này không in gì (không dòng nào của anchors.jsonl từng bị sửa hay xóa)
git log -p --format= -- anchors.jsonl | grep '^-[^-]'
```

Kiểm chữ ký một dòng (ở đây là dòng cuối; dòng khác thì thay `tail -n 1` bằng `sed -n <số dòng>p`):

```bash
tail -n 1 anchors.jsonl > line.json
jq -r '.v, .audit_id, .hash, .anchored_at, .system' line.json > msg.bin     # đúng năm dòng đã ký
jq -r .sig line.json | openssl base64 -d -A > sig.bin
openssl pkeyutl -verify -pubin -inkey anchor-key.pem -rawin -in msg.bin -sigfile sig.bin
```

`Signature Verified Successfully`: dòng do két của hệ thống ký và chưa bị sửa chữ nào. Không có jq thì viết tay thông
điệp từ các trường của dòng: `printf '%s\n' signet-anchor-v1 <audit_id> <hash> <anchored_at> <system> > msg.bin`.
Kiểm cả tệp một lần: từ mã nguồn Signet, `python3 scripts/anchor_sig.py anchors.jsonl anchor-key.pem` (Python thuần,
không cài thêm gì, không cần hệ thống đang chạy).

Đơn vị đối chiếu sổ với mốc đã công bố trên máy chủ: `python3 scripts/moc.py audit verify --anchors
/var/lib/moc/neo-cong-khai/anchors.jsonl` — kiểm chữ ký từng dòng (bằng `anchor-key.pem` cạnh tệp, `--key`, hoặc khóa
két đang dùng), rồi so từng mốc với chuỗi tính lại: mốc lệch là sổ đã bị viết lại từ khoảng đó; dòng chữ ký sai, hay
dòng chưa ký sau dòng đã ký, là lỗi (thoát 1) và không được dùng để kết luận.

Nói rõ giới hạn:

- Chữ ký chứng minh dòng do két của hệ thống ký, không chứng minh sổ đúng: người chiếm được `svc-files` ký được mốc
  mới cho một chuỗi đã viết lại. Cái chặn là các mốc cũ đã công bố không rút được — nhánh cấm đẩy ép, người khác đã
  clone — nên mốc cũ lệch với sổ mới và `moc audit verify --anchors` chỉ ra.
- `anchored_at` là giờ của kho đối tượng trên máy chủ; giờ trong commit cũng do máy chủ đặt. Bằng chứng thời gian
  độc lập là lúc push mà nhà cung cấp git ghi (GitHub: trang Activity của kho) và các bản clone của người khác.
- Khóa triển khai nằm trên máy chủ: người chiếm máy chủ thêm được commit (kể cả commit sửa dòng cũ) nhưng không xóa
  được lịch sử; lệnh `git log -p … | grep` ở trên lộ ra ngay.
- Dựng lại két là có khóa `moc-anchor` mới: `anchor-key.pem` trong kho được ghi đè ở lượt kế tiếp, mốc ký trước đó
  kiểm bằng khóa cũ trong lịch sử (`git log -p -- anchor-key.pem`); trường `key` của từng dòng cho biết khóa nào.
- Kho công khai cho người ngoài thấy nhịp hoạt động (số dòng sổ theo giờ) và URL hệ thống, không thấy nội dung nào: hash
  chỉ là băm.
- Sổ đăng ký văn bản in ra (`/api/registers/…/pdf`) có mốc neo mới nhất lúc in ở chân trang (`Mốc neo #<số> · <16 chữ
  hex> · <giờ>`): đối chiếu dòng đó trong kho mốc là biết sổ kiểm toán lúc in chưa bị viết lại về sau.

## GitOps và tự phục hồi

`scripts/reconcile.py` đưa hệ thống đang chạy về đúng trạng thái khai trong git, mỗi lượt một lần gọi. Trên máy chủ,
systemd timer gọi nó mỗi 60 giây (tệp mẫu [`platform/systemd/`](../platform/systemd/), chạy trên máy chủ chứ không trong
container: không gắn socket Docker vào container nào). Mỗi lượt:

- **Tự phục hồi**: container unhealthy thì khởi động lại; dịch vụ khai trong compose mà mất container hoặc đã dừng
  thì dựng lại (`docker compose up -d` đúng các dịch vụ đó). Dịch vụ chạy một lần `keycloak-fonts` (chép phông của
  theme đăng nhập vào volume, #305) đã xong, thoát 0, không tính là đã dừng. Thử: `make demo-tu-phuc-hoi`
  (`docs/demo-script.md`).
- **GitOps** (khi đặt `MOC_GITOPS_DIR` trong `.env` của bản cài): kéo nhánh `MOC_GITOPS_BRANCH` (mặc định `deploy`)
  về một bản sao git riêng của reconciler. Lần chạy đầu mà bản sao có thay đổi chưa commit thì reconciler từ chối,
  không xóa việc của ai; từ khi đã áp một commit, mỗi lần áp đều `checkout -f` và `clean -fd` bản sao, nên đừng sửa
  tay trong đó. Có commit mới, hoặc tệp đã cài bị sửa tay (khác băm lúc cài), thì dựng image của commit đó, dừng
  Signet, cài lại đúng commit vào thư mục cài rồi chạy lại. Cài hỏng giữa chừng thì cài lại commit đang chạy trước đó.
  Commit áp lỗi thì không thử lại mỗi phút mà đợi commit kế tiếp.

```bash
# trên máy chủ, đã make install PREFIX=/opt/moc; người vận hành moc thuộc nhóm docker
git clone -b deploy https://github.com/HIT-Champion/Signet.git /opt/moc-src
echo "MOC_GITOPS_DIR=/opt/moc-src" >> /opt/moc/.env
python3 /opt/moc/scripts/reconcile.py          # thử một lượt
sudo cp platform/systemd/moc-reconcile.* /etc/systemd/system/ && sudo systemctl enable --now moc-reconcile.timer
```

- Áp một commit là cài lại toàn bộ: Signet dừng khoảng một phút (`install.sh` không thay cấu hình dưới container đang
  chạy). Image cũ theo commit không tự xóa.
- Profile thêm trong `MOC_EXTRA_PROFILES` của bản cài (`tunnel`, `ai`…) đi cùng mọi lệnh compose của reconciler, như
  `Makefile`: áp commit dừng rồi chạy lại cả chúng, tự phục hồi cũng thấy chúng (#351).
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

## Quét mã độc (ClamAV)

Mọi tệp tải lên đều qua ClamAV trước khi lưu. Container `clamav` tự tải chữ ký mới (freshclam, mỗi ngày một lần),
người vận hành không phải làm gì. Có một hạn chế (#287): mỗi lần clamd nạp lại chữ ký, nó ngừng quét tới khi nạp xong.
Đã đo: khoảng 10 giây trên máy CI, 8 giây bằng một container thử trên máy chạy bản online; máy bận hay yếu có thể
tới khoảng 1 phút. Lý do là compose đặt `ConcurrentDatabaseReload no` để đỡ RAM (#288 đo lại lựa chọn này).
Clamd nạp lại vào hai lúc:

- mỗi ngày một lần, ngay sau khi freshclam tải bản chữ ký mới;
- khoảng 10 phút sau khi ClamAV khởi động (`make up`, nâng cấp, khởi động lại máy), nếu đúng lúc khởi động freshclam
  tải được bản mới.

Cách nhận ra và xử lý:

- **Người dùng thấy:** tệp đứng ở "Đang tải lên và quét virus…". Quá 60 giây (`CLAMAV_TIMEOUT_S` của `svc-files`) thì
  báo trạm quét mã độc chưa sẵn sàng (`503 scanner_unavailable`), tệp chưa được lưu. Trang trạng thái có thể báo
  "Quét mã độc" gián đoạn trong lúc đó.
- **Xử lý:** chờ khoảng 1 phút rồi tải lại. Không cần khởi động lại gì: khởi động lại `clamav` chỉ làm nó nạp chữ ký
  lại từ đầu.
- **Nhận ra trong nhật ký:** trên máy chủ, trong thư mục cài, chạy `docker compose logs clamav`. Lúc bắt đầu nạp lại
  có dòng "SelfCheck: Database modification detected. Forcing reload" hoặc "Clamd successfully notified about the
  update", rồi "Reading databases from /var/lib/clamav". Nạp xong có "Database correctly reloaded".
- **Kiểm tải lên ngay sau khi nâng cấp:** nhật ký có "daily.cld updated" (hay "daily.cvd updated") kèm "Clamd was NOT
  notified" nghĩa là khoảng 10 phút sau khi khởi động clamd sẽ tự nạp lại. Muốn kiểm ngay thì cho nạp luôn: chạy
  `docker compose exec -T clamav clamdscan --reload`, chờ dòng "Database correctly reloaded" rồi mới tải lên.
- **Tải chữ ký mới ngay, không chờ lượt hằng ngày.** Ví dụ trước khi nâng cấp, để lúc khởi động lại chữ ký đã mới
  nhất và clamd không phải nạp lại giữa chừng. Lệnh:

  ```bash
  docker compose exec -T clamav freshclam --log=/tmp/freshclam-tay.log
  ```

  - **Phải có `--log`.** freshclam chạy nền giữ khóa tệp nhật ký `/var/log/clamav/freshclam.log`, nên thiếu cờ này
    lệnh báo "Failed to lock the log file" rồi dừng, không cập nhật gì.
  - **Chạy bằng root vẫn an toàn.** Lệnh bỏ quyền root theo `DatabaseOwner`, nên tệp chữ ký vẫn thuộc user `clamav`
    và freshclam nền vẫn cập nhật tiếp được.
  - **Có bản mới thì clamd nạp lại ngay.** freshclam báo "Clamd successfully notified about the update"; tải lên dừng
    tới khi nhật ký có "Database correctly reloaded". Đo bằng một container thử trên máy chạy bản online: khoảng 8
    giây; khi máy đang bận có thể lâu hơn.
  - **Đã mới nhất** thì lệnh chỉ báo "database is up-to-date".
  - **Vẫn báo lỗi khóa** thì có thể freshclam nền đang tự cập nhật: chờ 1 phút rồi chạy lại.

## Lịch nghỉ lễ chính thức (nguồn công khai B)

Hạn gợi ý giao việc (F4.3) tránh Tết Âm lịch, Giỗ Tổ, ngày nghỉ bù và coi thứ Bảy làm bù là ngày làm việc, theo lịch
nghỉ chính thức của cán bộ, công chức, viên chức (#427). Bản chụp nằm ở `seed/du-lieu-mo/ngay-nghi-le/`:

- `ngay-nghi.json`: ngày lễ cố định (Điều 112 Bộ luật Lao động, Ngày Văn hóa Việt Nam 24/11), các khoảng nghỉ theo
  năm, ngày làm bù; mỗi mục ghi văn bản căn cứ;
- `trich/*.txt`: câu trích các bài trên Báo Điện tử Chính phủ nêu đúng các ngày đó, kèm URL bài;
- `manifest.json`: URL, ngày lấy, SHA-256 từng tệp, căn cứ dùng lại (Điều 15 Luật Sở hữu trí tuệ), tuổi tối đa 400
  ngày.

`docker-compose.yml` gắn thư mục này chỉ đọc vào svc-workflow; `MOC_HOLIDAYS_FILE` (mặc định
`/app/du-lieu-mo/ngay-nghi-le/ngay-nghi.json`, rỗng thì tắt) cộng lịch đó vào `MOC_HOLIDAYS`. Không có tệp thì chỉ còn
`MOC_HOLIDAYS` như trước; tệp hỏng thì svc-workflow dừng lúc khởi động và báo `MOC_HOLIDAYS_FILE`.

Lấy mới khi Chính phủ công bố lịch nghỉ năm sau (thường vào tháng 10), không cần Docker:

1. thêm một mục vào `PAGES` của `scripts/nguon_ngay_nghi_le.py`: URL bài, tệp trích, khoảng ngày, chuỗi ngày đúng như
   bài viết;
2. `python3 scripts/nguon_ngay_nghi_le.py` đọc lại mọi bài, kiểm từng ngày có trên bài rồi mới thay bản chụp. Trang
   không tải được hay không còn ngày nào đó thì lệnh thoát 1, bản chụp cũ giữ nguyên;
3. `docker compose restart svc-workflow`. Gợi ý đã lưu giữ hạn cũ.

Nguồn ngừng hoạt động thì gợi ý vẫn chạy bằng bản chụp; năm bản chụp chưa có thì thêm ngày vào `MOC_HOLIDAYS`.

## Giám sát

APISIX đếm mọi yêu cầu qua cổng (plugin `prometheus`, cổng xuất chỉ số 9091 không publish: chỉ container ở mạng
`moc`, `apps` tới được — container ứng dụng đọc được số đếm theo route, không có token hay dữ liệu nghiệp vụ).
Prometheus còn thu bảng trạng thái của `svc-files` (`GET /metrics`, #274): mỗi thành phần của trang `/trang-thai` một
dòng `moc_component_up`, cùng lần dò và lưu đệm 10 giây với `/api/status`; `/metrics` chỉ gọi được trong mạng `moc`,
qua cổng API thì 404. Prometheus thu mỗi 15 giây, giữ `MOC_METRICS_RETENTION` (mặc định 15 ngày), không mở cổng ra
ngoài. Grafana hiện
bảng điều khiển **Signet — cổng API** nạp sẵn: yêu cầu mỗi giây theo route, mã trạng thái (429 = vượt giới hạn tốc
độ), tỉ lệ lỗi 5xx, độ trễ p95, băng thông, kết nối đang mở.

- Grafana chỉ nghe `127.0.0.1:MOC_GRAFANA_PORT` (mặc định 3300) trên máy chủ — xem từ máy khác qua đường hầm SSH:
  `ssh -L 3300:127.0.0.1:3300 máy-chủ` rồi mở `http://localhost:3300`.
- Không có tài khoản Grafana: ai vào được cổng đó thì chỉ xem. Bảng điều khiển sửa trong
  `platform/monitoring/grafana/dashboards/` rồi cài lại, không sửa trên giao diện.
- Grafana (AGPL-3.0) chạy nguyên bản trong container riêng; Signet chỉ nạp cấu hình qua tệp, không liên kết mã.
- Chỉ số không nằm trong bản sao lưu (`make backup`): khôi phục xong thì Prometheus thu lại từ đầu.
- Prometheus chỉ đọc `platform/monitoring/prometheus.yml` và `canh-bao.yml` lúc khởi động, Alertmanager cũng vậy với
  `alertmanager.yml`. Sửa tay trên máy đang chạy thì khởi động lại dịch vụ đó: `docker compose restart prometheus`
  (`alertmanager`) trong thư mục cài. Lúc nâng cấp, `scripts/nang_cap.sh` đã
  dừng rồi chạy lại cả hệ thống nên bản mới tự nạp tệp mới.

### Cảnh báo

Prometheus tính 8 luật trong `platform/monitoring/canh-bao.yml` mỗi 15 giây: nhóm `cong-api` trên chỉ số APISIX
(#255), nhóm `thanh-phan` trên bảng trạng thái của svc-files (#274). Nhãn `route` là id route trong
`platform/apisix/apisix.yaml`; nhãn `component` là mã thành phần ở `services/svc-files/README.md`, mục Trạng thái hệ
thống.

| Cảnh báo | Mức | Bật khi |
|---|---|---|
| `GatewayMetricsDown` | critical | Prometheus không thu được chỉ số của APISIX quá 2 phút: cổng có thể đã dừng |
| `UpstreamUnreachable` | critical | Một route trả 502 hoặc 504 liên tục 3 phút: APISIX tự sinh hai mã này khi dịch vụ sau cổng chết hay quá giờ |
| `High5xxRatio` | warning | Hơn 5% yêu cầu lỗi 5xx trong 5 phút, khi có hơn 0,1 yêu cầu/giây |
| `SlowRoute` | warning | p95 thời gian trả lời trên 3 giây trong 10 phút, ở route graphql, app-office, app-ca-nhan, keycloak, dang-nhap, dang-nhap-post |
| `ComponentDown` | critical | Một thành phần bắt buộc (`cong-api`, `dang-nhap`, `csdl`, `quet-ma-doc`, `quy-trinh`, `luu-tru`) gián đoạn quá 2 phút: trang `/trang-thai` báo cả Signet gián đoạn |
| `OptionalComponentDown` | warning | Két khóa (`ket-khoa`) hay tìm kiếm (`tim-kiem`) gián đoạn quá 5 phút |
| `StatusMetricsDown` | critical | Prometheus không đọc được `/metrics` của svc-files quá 2 phút: svc-files có thể đã dừng. Khi đó các dòng `moc_component_up` mất chứ không về 0, nên `ComponentDown` không bật |
| `AlertRulesFailing` | warning | Prometheus tính luật bị lỗi trong 10 phút qua |

- Xem ở hàng "Cảnh báo đang bật" cuối bảng điều khiển Grafana. `pending` là điều kiện đã đúng nhưng chưa đủ thời
  gian của luật. Trên máy chủ, trong thư mục cài:
  `docker compose exec -T prometheus wget -q -O - http://localhost:9090/api/v1/alerts`.
- Cảnh báo đang bật đi tiếp sang Alertmanager (#284, `platform/monitoring/alertmanager.yml`): gom theo tên cảnh báo,
  chờ 30 giây trước lần gửi đầu, gửi phần đổi mỗi phút, còn bật thì nhắc lại sau 12 giờ. Alertmanager gọi
  `svc-workflow` (`POST /ops/alerts`, token `MOC_ALERT_TOKEN`): mỗi lần bật, mỗi lần hết là một thông báo ở chuông của
  mọi quản trị đơn vị (vai trò `tenant_admin`) của mọi đơn vị, bấm vào mở trang `/trang-thai`. Bản cài đã bật email,
  webhook, SMS, Zalo (mục Thông báo đa kênh) thì cảnh báo đi cả kênh đó, trừ khi `MOC_NOTIFY_*_KINDS` liệt kê loại mà
  không có `ops.alert`.
- Thông báo chỉ mang câu `summary` của luật, mức, nhãn `component`, `route`. Alertmanager gửi lại (nhắc 12 giờ, khởi
  động lại mất nhật ký gửi) không thêm dòng: khóa chống trùng là fingerprint, thời điểm bật và trạng thái.
- `MOC_ALERT_TOKEN`: `make env` sinh; `.env` cũ thiếu dòng này thì `make up`, `make install` (cả `scripts/nang_cap.sh`)
  tự thêm một chuỗi ngẫu nhiên. Để trống là tắt: Alertmanager chạy `alertmanager-khong-gui.yml` (nhận mà không gửi),
  `POST /ops/alerts` trả 404. Token là bí mật của svc-workflow trong két; đổi token: sửa `.env`, `docker compose up -d`
  (tạo lại `openbao`, `alertmanager`) rồi `docker compose restart svc-workflow`.
- API 9093 của Alertmanager không đăng nhập (đẩy cảnh báo, tạo silence): Alertmanager chỉ ở mạng `alerts`
  (`internal`) cùng Prometheus, `svc-workflow`; dịch vụ khác của mạng `moc` không tới được.
- Hạn chế: PostgreSQL, Hasura hay `svc-workflow` gián đoạn thì cảnh báo về chính sự cố đó chưa vào chuông được
  (`svc-workflow` trả 503, Alertmanager gửi lại ở các lần sau); trong lúc đó chỉ Grafana, Prometheus thấy. Gửi lỗi vì
  token sai (401) không có cảnh báo riêng: Prometheus chưa thu chỉ số của Alertmanager. Tắt tạm một cảnh báo phải dùng
  `amtool` trong container: `docker compose exec alertmanager amtool silence add alertname=<tên> --comment=<lý do>
  --alertmanager.url=http://localhost:9093`.
- Thử cả đường đi: `make demo-canh-bao` (cảnh báo giả, không đụng dịch vụ thật). Cảnh báo Alertmanager đang giữ:
  `docker compose exec -T alertmanager wget -q -O - http://localhost:9093/api/v2/alerts`. Gửi lỗi thì xem
  `docker compose logs alertmanager` và dòng `ops.alert.failed` của svc-workflow.
- 503 không tính là "không trả lời". svc-files trả 503 có chủ ý (`busy`, `scanner_unavailable`… kèm `Retry-After`),
  nên 503 chỉ tính vào tỉ lệ 5xx. Độ trễ của svc-files không xét: tải lên, đọc văn bản đến, hỏi đáp vốn chậm theo
  thiết kế.
- svc-workflow không có route riêng mà nằm sau Hasura Actions; lỗi của nó về trình duyệt là GraphQL 200 có `errors`,
  nên nhóm `cong-api` không thấy. Nhóm `thanh-phan` thấy qua thành phần `quy-trinh`: bảng trạng thái gọi `/readyz` của
  svc-workflow, trong đó có kiểm Flowable.
- Nhóm `cong-api` dựa trên lưu lượng thật: không ai gọi tới thì nhóm này không thấy dịch vụ chết. Nhóm `thanh-phan`
  thì không cần lưu lượng: Prometheus thu bảng trạng thái 15 giây một lần.
- Trợ lý AI không có cảnh báo: Ollama không trả lời thì bảng trạng thái báo `off` như khi chưa bật (không phân biệt
  được), và thành phần `off` không có dòng `moc_component_up`.
- Đổi ngưỡng: sửa `canh-bao.yml` cùng ca tương ứng trong `platform/monitoring/kiem-tra/canh-bao.test.yml`, chạy
  `promtool test rules` như bước "Giám sát" của job build trong `.github/workflows/ci.yml`, rồi cài lại.

## Dữ liệu công khai

Signet kèm bản chụp dữ liệu từ nguồn công khai của nhà nước trong `seed/du-lieu-mo/<mã nguồn>/` (#424): tệp gốc và
`manifest.json` ghi URL, ngày lấy, căn cứ dùng lại, SHA-256 từng tệp. Nguồn A `cong-bao-gddt`: bốn thông tư của Bộ
GD&ĐT về giáo dục đại học, bản Công báo (`seed/du-lieu-mo/cong-bao-gddt/README.md`).

- **Bản cài không gọi nguồn lúc chạy.** `svc-files` đọc các manifest qua mount chỉ đọc `/srv/du-lieu-mo`, so SHA-256
  rồi báo ở `GET /api/status` (khóa `open_data`: `ok`, `stale` khi quá `max_age_days`, `broken` khi thiếu tệp hay sai
  băm) và trang `/trang-thai`. Nguồn ngừng hoạt động thì Signet vẫn dùng bản chụp gần nhất, trang trạng thái cho biết
  dữ liệu đã bao nhiêu ngày.
- **Nạp:** `make seed` nạp mỗi tệp thành một văn bản đến của Khoa CNTT qua API nạp lô (CSV + zip, ClamAV, như văn
  thư nạp tay), loại "Thông tư" (migration `1792281604000_document_type_tt`). Bản cài đã có dữ liệu mẫu thì chạy
  riêng `python3 scripts/moc.py du-lieu-mo nap`; chạy lại không tạo trùng. Trang văn bản nhận ra văn bản từ nguồn công
  khai nhờ SHA-256 của tệp đính kèm trùng với manifest; trợ lý hỏi đáp trích được như mọi văn bản đến.
- **Kiểm:** `make du-lieu-mo` (`python3 scripts/moc.py du-lieu-mo kiem`) so băm, in tuổi dữ liệu; thoát 1 khi bản
  chụp hỏng.
- **Lấy mới** (máy của đội, cần Internet, không chạy trên máy chủ): `make du-lieu-mo-lay`. Lệnh chỉ thay bản chụp khi
  mọi tệp tải xong, khớp manifest và tổng không quá 3 MB; nguồn lỗi thì giữ bản cũ, thoát 1. Bản chụp mới đi qua PR
  như mọi tệp `seed/`.
- **Thêm nguồn:** một module `scripts/nguon_<mã>.py` có `NGUON`, `TEN`, `lay(thu_muc)` trả manifest (khuôn trong
  `scripts/du_lieu_mo.py`). Chỉ dùng nguồn có căn cứ dùng lại rõ (giấy phép mở, hoặc Điều 15 Luật Sở hữu trí tuệ với
  văn bản nhà nước), đúng `robots.txt` và điều khoản trang, không dữ liệu cá nhân; khai giấy phép tệp trong
  `REUSE.toml`.

## Trợ lý hỏi đáp qua API ngoài

Mặc định trợ lý hỏi đáp (F4.2) viết câu trả lời bằng mô hình chạy tại chỗ trong Ollama. Máy yếu (CPU chậm) hay muốn
mô hình lớn hơn thì cho bước viết đi tới một máy chủ nói chuẩn OpenAI (#430): vLLM hay llama.cpp trên máy có GPU của
đơn vị, hoặc dịch vụ đám mây. Đặt trong `.env`:

```
MOC_ASK_API=openai
MOC_ASK_API_URL=https://may-chu-mo-hinh/v1
MOC_ASK_MODEL=<tên mô hình máy chủ đó nhận>
MOC_ASK_API_KEY=<khóa, để trống nếu máy chủ không đòi>
```

rồi `docker compose up -d` (tạo lại `openbao`, `svc-files`). Đổi khóa về sau: sửa `.env`, `docker compose up -d` rồi
`docker compose restart svc-files`.

- **Cái gì rời máy:** chỉ lời gọi viết câu trả lời: câu hỏi và tối đa 4 đoạn văn bản làm căn cứ, **đã che** số điện
  thoại, CCCD, email, số tài khoản (F4.4). Tìm theo nghĩa (mô hình nhúng) và trích yếu văn bản đến vẫn ở Ollama; không
  bật profile `ai` thì trợ lý tìm theo từ khóa, chỉ bước viết dùng API. Mô hình nguồn mở chạy tại chỗ vẫn là mặc
  định khuyên dùng: gửi văn bản tới dịch vụ đám mây là quyết định của đơn vị về dữ liệu của mình.
- **Kiểm như cũ:** đầu ra ép theo JSON Schema (`response_format`), máy chủ Signet vẫn kiểm từng câu với đoạn nguồn và
  con số rồi mới gắn trích dẫn; không đạt thì trả câu trích nguyên văn.
- **Khóa:** là bí mật của `svc-files` trong két như các khóa khác (mục Két bí mật), không nằm trong biến môi trường của
  container `svc-files`, không vào nhật ký. Chỉ đi trong tiêu đề `Authorization` tới `MOC_ASK_API_URL`. URL dạng
  `http://` thì `svc-files` ghi `config.warning` lúc khởi động: khóa và đoạn văn bản đi không mã hóa, chỉ hợp với máy
  chủ trong mạng nội bộ tin cậy.
- **Tên mô hình:** `MOC_ASK_MODEL` bắt buộc, đúng tên máy chủ đó nhận (vd. `Qwen/Qwen3-4B` của vLLM); không lấy
  `MOC_AI_MODEL` như khi viết tại chỗ. Thiếu thì `svc-files` dừng lúc khởi động.
- **Sẵn sàng:** `svc-files` hỏi `GET {MOC_ASK_API_URL}/models` lúc khởi động và mỗi 60 giây; khóa sai (401, 403) hay
  sai tên mô hình (404) thì coi như chưa sẵn sàng tới lượt dò sau. Nhật ký: `office.assist.ai_ready`,
  `office.assist.ai_unavailable` có `"where": "external"` và mã HTTP, không có khóa.
- **Sổ kiểm toán:** dòng `assistant.answered` ghi `model` và `model_where` (`local`: Ollama; `external`: API ngoài).

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
  lại vẫn chạy. Trợ lý AI *Tắt* khi chưa bật profile `ai`, tắt hỏi đáp, hoặc Ollama không trả lời: trang không phân
  biệt được ba trường hợp này, nên *Tắt* mà profile `ai` đang bật thì xem `docker compose logs ollama`. Trợ lý vẫn tìm
  theo từ khóa. Viết câu trả lời qua API ngoài (mục dưới) thì phần mềm của thành phần ghi "API ngoài".
- **Không lộ gì:** chỉ có nhãn cố định và trạng thái; không tên máy, địa chỉ IP, URL nội bộ, phiên bản từng thành phần,
  số người dùng hay số văn bản, thông báo lỗi. Lý do cụ thể nằm trong nhật ký của `svc-files` (sự kiện
  `core.status.changed`, ghi khi một thành phần đổi trạng thái): `docker compose logs svc-files | grep status.changed`.
- **Không thành đường tấn công:** `svc-files` lưu đệm kết quả 10 giây cho mọi người, mỗi lần dò một thành phần tối đa
  3 giây (mặc định của `MOC_STATUS_CACHE_S`, `MOC_STATUS_TIMEOUT_S` trong `svc-files`; compose không truyền hai biến
  này, đặt trong `.env` không có tác dụng); APISIX giới hạn `MOC_RATE_STATUS_PER_MIN` (mặc định 30) lần một phút mỗi
  địa chỉ IP, vượt thì `429`.
- Trang chỉ trả lời "đang chạy hay không" ngay lúc này; diễn biến theo thời gian, độ trễ, tỉ lệ lỗi xem ở Grafana (mục
  Giám sát). API: `GET /api/status` ([`docs/api/README.md`](api/README.md) §3).

## Log tập trung

Profile `logs` (tắt mặc định) gom log của các dịch vụ về một chỗ để tra theo **mã yêu cầu**. APISIX gắn mã
`X-Request-Id` cho mọi yêu cầu (giữ mã client tự gửi, trả lại ở header của phản hồi) và ghi ở cuối dòng truy cập;
Hasura chuyển mã sang `svc-workflow`; `svc-workflow` ghi mã trong nhật ký, gửi tiếp sang Hasura và `svc-files`. Cùng
một mã nằm ở dòng log của APISIX, `svc-workflow`, Hasura, `svc-files` và ở cột `request_id` của sổ kiểm toán
`core.audit_log`.

Đường đi: driver log `fluentd` của Docker → **Vector** 0.59 (cổng `127.0.0.1:24224` trên máy chủ, tách mã yêu cầu, che
lần hai) → **Parseable** 3.2 (lưu trên volume `parseable_data`, API và giao diện ở `127.0.0.1:8400`, tài khoản `moc`).
Driver đặt trong tệp compose phủ [`platform/logs/docker-compose.logs.yml`](../platform/logs/docker-compose.logs.yml),
chỉ nạp khi bật. Không gắn `docker.sock`, không đọc `/var/lib/docker`. `docker logs`, `make logs` vẫn đọc được như cũ
(Docker giữ bản cục bộ 10 MB × 3 cho driver ngoài).

- **Thu:** `apisix`, `app-office`, `app-ca-nhan`, `svc-files`, `svc-workflow` — các dịch vụ tự che thông tin cá nhân
  trong nhật ký (F4.4) — cùng `hasura`, `keycloak`, `postgres`, `meilisearch`: bốn dịch vụ này không tự che, Vector
  che bằng luật riêng (dưới đây) trước bước che chung. **Không thu** OpenBao, Flowable, SeaweedFS…: chưa có luật riêng,
  đưa vào kho log là đưa thông tin cá nhân chưa che đi xa thêm một chỗ.
- **Luật riêng** cho bốn dịch vụ không tự che, mỗi luật có ca trong `vector.test.yaml`:
  - **Hasura** (dòng JSON): `event` là `hasura.<loại log>` (`hasura.http-log`, `hasura.websocket-log`…);
    `request_id` lấy trong `detail` (`detail.request_id`, `detail.operation.request_id`, ở `websocket-log` là
    `detail.event.detail.request_id`). Đó là `X-Request-Id` mà APISIX, `svc-workflow`, `svc-files` gửi kèm lời gọi
    GraphQL, nên `make logs-tra` ra cả dòng của Hasura. Khóa `query`, `raw_query` là chuỗi (câu GraphQL, thân yêu
    cầu) và cả nhánh `query.variables` (khóa trong biến `jsonb` cũng là dữ liệu), `generated_sql` (của `query-log`, mặc
    định tắt), `internal` của lỗi (tham số, câu SQL, `DETAIL` của PostgreSQL) thay bằng `[REDACTED]`; `operationName`
    giữ lại. Hasura 2.51 ghi câu và biến mỗi lần mở subscription. Dòng `http-log` lỗi của nó chỉ có `code`, `error`,
    `path`, kể cả với vai trò admin và `DEV_MODE=true` (đã thử 26/10/2026). Luật `raw_query`, `internal` để phòng
    bản khác.
  - **PostgreSQL**: mỗi mục log bắt đầu bằng tiền tố mặc định `%m [%p] ` rồi loại (`ERROR:`, `DETAIL:`…). Dòng
    không có tiền tố bị bỏ: đó là dòng tiếp của mục nhiều dòng (câu lệnh hay dòng vi phạm có xuống dòng) hay lời
    của script khởi tạo, không biết thuộc mục nào nên không che đúng được. Các phần bị che:
    - `STATEMENT:`, `QUERY:` chỉ giữ từ đầu (`STATEMENT:  insert [REDACTED]`);
    - `DETAIL:` che giá trị khóa (`Key (email)=([REDACTED]) already exists.`), dòng vi phạm (`Failing row contains
      ([REDACTED]).`), `Token "…"` của JSON sai;
    - `CONTEXT:` che câu trong nháy (`SQL statement "…"`) và đoạn trích sau `line N:` (`JSON data`, `COPY`);
    - tham số `$1 = '…'`, giá trị gõ sai kiểu (`invalid input syntax for type uuid: "…"`, `malformed array
      literal: "…"`; luật này cũng chạy cho lời lỗi Hasura chuyển nguyên).

    Dòng dừng giữa giá trị (giá trị có xuống dòng) thì che tới hết dòng. Lời báo `ERROR:` giữ nguyên: lời của các
    hàm trong `db/migrations` chỉ có mã, trạng thái, số hồ sơ. Đổi `log_line_prefix` thì mọi dòng bị bỏ.
  - **Keycloak**: `username="…"` ở sự kiện `LOGIN_ERROR` (tên người dùng gõ vào: gõ nhầm mật khẩu vào ô tên thì
    lộ). `userId`, `clientId`, `error` giữ lại. `sessionId`, chuỗi truy vấn của `redirect_uri` đã bị bước che chung che.
  - **Meilisearch** ghi JSON (`MEILI_EXPERIMENTAL_LOGS_MODE=json` trong `docker-compose.yml`): mỗi yêu cầu HTTP một
    dòng lúc đóng span `HTTP request`, `event` là `meilisearch.http` (dòng khác: `meilisearch.<target>`). Thay cả giá
    trị `query_parameters` (gọi `GET` thì có câu tìm `q=…`, biểu thức `filter=…`) và `error` (lời lỗi trích giá trị
    tài liệu, biểu thức lọc, có khi nhiều dòng); bỏ `spans` (lặp lại `span`). Chuỗi khác che từ dấu `` ` `` đầu tiên
    tới hết chuỗi: Meilisearch trích giá trị trong dấu đó (``Document identifier `…` is invalid``). `route`, `method`,
    `status_code`, thời gian xử lý giữ lại. Dòng `/health` trả 200 (bảng trạng thái hỏi liên tục) bị bỏ. Bỏ chế độ
    JSON thì luật chữ cùng nội dung vẫn chạy, nhưng dòng tiếp của lời lỗi nhiều dòng không che được. Đừng đặt
    `MEILI_LOG_LEVEL=DEBUG` khi đang thu log: mức đó ghi câu tìm và kết quả vào `fields`, luật không che.
- **Che lần hai** ([`platform/logs/vector.yaml`](../platform/logs/vector.yaml)), mỗi dạng dưới đây có ca trong
  [`vector.test.yaml`](../platform/logs/vector.test.yaml) (43 ca cả luật riêng ở trên; bỏ một luật nào thì có ca đỏ):
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
    giây thì che từng phần (bí mật vắt qua chỗ chia lọt);
  - PostgreSQL: lời báo `ERROR:` của hàm tự viết (`raise exception '… %', giá_trị`), token sau `syntax error at or
    near "…"`, `HINT:`, `DETAIL:` khác các dạng ở trên;
  - Hasura: lời lỗi khác hai dạng giá trị gõ sai kiểu ở trên; `user_vars` (vai trò, mã người dùng, mã đơn vị),
    `http_info.ip`, đường dẫn URL giữ nguyên;
  - Keycloak: trường khác `username` của sự kiện (`ipAddress`, đường dẫn của `redirect_uri`), dòng traceback Java.

  **Che thừa** (không lọt, chỉ mất chữ): khóa vô hại có chữ `token`, `session`, `pwd` (`max_tokens`,
  `session_timeout=3600`, `PWD=/app`); số, kể cả ngày giờ, nằm trong 20 ký tự sau từ khóa (`tài khoản a lúc
  2026-10-24 10:00` thành `tài khoản a lúc [STK]:00`); đoạn giống số điện thoại, CCCD trong chuỗi hex (mã
  `uuid4().hex`) — cột `request_id` tách trước khi che nên vẫn tra đúng; phần còn lại của dòng sau `Authorization`,
  `Cookie` không nháy, sau nháy không đóng (dòng JSON: của chuỗi đó), sau giá trị cờ dòng lệnh không nháy (tới khóa
  `a=` kế tiếp: `--password X --host db` thành `--password [REDACTED]`, `--no-password db_moc --format c`,
  `--sort-key name` cũng bị che); từ dài từ 8 ký tự đứng sau chữ `basic`, `bearer` (`basic authentication`); dấu `,`
  `;` ngay sau giá trị bị che (`token=X,user=a` thành `token=[REDACTED]user=a`).
- **Cột** của luồng `moc`: `service`, `container`, `stream` (stdout/stderr), `timestamp`, `event`, `request_id` (dòng
  JSON của `svc-files`, `svc-workflow`, Hasura; dòng của APISIX; chỉ mã đúng dạng `[A-Za-z0-9._:-]{1,128}`, như
  `event`; dòng PostgreSQL, Keycloak không có, tra theo `service`),
  `message`; Parseable thêm `p_timestamp` (giờ nhận, UTC), `p_src_ip` (IP của Vector trong mạng `logs`),
  `p_user_agent` (của Vector).

```bash
make logs-up                       # bật: Vector, Parseable; tạo lại 9 container; đặt giữ log; tới lần make up sau
make logs-tra ID=<mã>              # dòng của mọi dịch vụ mang mã, 60 phút gần nhất (PHUT=… để đổi)
make demo-log-tap-trung            # màn demo: một mã qua APISIX → svc-workflow → Hasura, svc-files; SQL lỗi…
make logs-down                     # tắt: 9 dịch vụ về json-file, dừng Vector, Parseable; giữ log đã lưu
```

- **Bật lâu dài:** thêm `logs` vào `MOC_EXTRA_PROFILES` trong `.env` (vd `MOC_EXTRA_PROFILES=tunnel,logs`) rồi chạy
  `make up` (hoặc `make logs-up`); từ đó `make up`, `make down`, `make ps`… tự nạp tệp phủ và profile, và mỗi lần
  `make up` thêm mật khẩu vào `.env` cũ nếu thiếu, tạo luồng, đặt lại thời gian giữ log (kể cả sau khi xóa volume
  `parseable_data`). Chỉ `make logs-up` mà không thêm vào `MOC_EXTRA_PROFILES` thì `make up` lần sau trả 9 dịch vụ về
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

- **Bật hay tắt phải tạo lại 9 container** (`apisix`, `app-office`, `app-ca-nhan`, `svc-files`, `svc-workflow`,
  `hasura`, `keycloak`, `postgres`, `meilisearch`): đổi driver log chỉ có hiệu lực khi tạo lại container.
  `make logs-up`, `make logs-down` (và `make up` lần đầu sau khi thêm hay bỏ `logs` trong `MOC_EXTRA_PROFILES`) khởi
  động lại cả CSDL, Hasura, Keycloak, Meilisearch: vài giây không đăng nhập, không ghi được, không tìm được; dịch vụ
  khác giữ kết nối tới CSDL (Flowable) phải tự nối lại. Nên bật, tắt ngoài giờ làm việc.
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
  Số đo này có trước khi bật báo nhận (mục dưới).
- **Báo nhận từng dòng** (`fluentd-request-ack: "true"`, #226): driver gửi kèm mã `chunk`, Vector trả `ack` ngay khi
  dòng đã vào pipeline. Vector không bật `acknowledgements` đầu-cuối nên không chờ Parseable lưu. Không có `ack` (kết
  nối đã chết, ví dụ sau khi Vector chạy lại) thì driver đóng kết nối, nối lại rồi gửi lại dòng đó. Trước #226,
  dòng đầu tiên của một dịch vụ im lâu (PostgreSQL, Keycloak) ghi vào kết nối chết thì mất mà không báo lỗi.
  `make demo-log-tap-trung` (bước 8) kiểm việc này. Hệ quả:
  - Vector nhận dòng rồi chết trước khi kịp trả `ack` thì dòng đó tới kho hai lần;
  - mỗi container gửi lần lượt từng dòng và chờ `ack` rồi mới gửi tiếp. Việc chờ nằm trong dockerd: dịch vụ vẫn không
    bị chặn (`mode: non-blocking`), dòng chưa gửi nằm trong bộ đệm như khi Vector chết.
- **Lớp che của Vector không thay được F4.4:** chỉ thu dịch vụ đã che; dịch vụ mới muốn thu thì phải che trong chính nó
  trước.
- `X-Request-Id` do client đặt được (APISIX giữ mã client gửi). `svc-workflow` chỉ nhận mã khớp
  `[A-Za-z0-9._:-]{1,128}`, mã khác thì thay bằng mã mới (trả lại ở header); `svc-files` chưa kiểm (như từ trước):
  chuỗi tùy ý vào nhật ký và các dòng sổ kiểm toán nó ghi. Vector chỉ đưa mã đúng dạng đó vào cột `request_id`;
  `make logs-tra` kiểm mã trước khi ghép vào câu SQL.
- Log chỉ nối dòng theo mã; thời gian từng chặng xem ở mục Truy vết phân tán dưới đây. Docker rootless và Docker
  Desktop (dockerd không chung mạng với máy chủ): chưa thử cổng `127.0.0.1:24224`. RAM lúc nghỉ khoảng 18 MiB
  (Vector) và 45 MiB (Parseable) — `docker stats` trên máy dev ngày 23/10/2026; dưới tải chưa đo.

## Truy vết phân tán

Profile `trace` (tắt mặc định, #364) cho thấy một yêu cầu đi qua những chặng nào, mỗi chặng mất bao lâu: APISIX →
`svc-files` hay Hasura → `svc-workflow` → các lời gọi HTTP của dịch vụ (Hasura, Meilisearch, OpenBao, Ollama,
Flowable…).
**Jaeger** 2.22 nhận span qua OTLP/HTTP (cổng 4318, chỉ trong mạng `moc`), giữ 10 000 trace mới nhất trong RAM
([`platform/trace/jaeger.yaml`](../platform/trace/jaeger.yaml)) và mở giao diện ở `127.0.0.1:16686` trên máy chủ.

```bash
# .env: thêm trace vào MOC_EXTRA_PROFILES (vd MOC_EXTRA_PROFILES=tunnel,trace) và đặt tỉ lệ, rồi
MOC_TRACE_RATIO=0.1
make up
ssh -L 16686:127.0.0.1:16686 <máy chủ>   # xem từ xa: http://127.0.0.1:16686
```

- **Lấy mẫu ở APISIX:** plugin `opentelemetry` (global rule trong `apisix.yaml`) chọn `MOC_TRACE_RATIO` yêu cầu (0–1)
  theo `trace_id`, gửi `traceparent` cho dịch vụ phía sau. `svc-files`, `svc-workflow` không tự chọn: chỉ ghi span khi
  `traceparent` mang cờ đã chọn, nên việc nền (đồng bộ danh bạ, gửi thông báo, lập chỉ mục) không sinh span. Hasura
  chuyển tiếp `traceparent` sang Action (`forward_client_headers`), nên span của `svc-workflow` nằm cùng trace với
  APISIX; Hasura không có span riêng (bản CE không hỗ trợ OpenTelemetry).
- **Tìm theo mã yêu cầu:** span của APISIX có thẻ `x-request-id`; trên giao diện Jaeger chọn dịch vụ `apisix`, ô Tags
  gõ `x-request-id=<mã>`. Mã này cũng là mã của `make logs-tra` (mục Log tập trung).
- **Tắt** (`MOC_TRACE_RATIO=0`, mặc định): APISIX không ghi span nào, hai dịch vụ không nạp OpenTelemetry. Giữ `0` khi
  không bật profile `trace`: tỉ lệ khác 0 mà không có Jaeger thì APISIX và dịch vụ ghi lỗi gửi span vào nhật ký.
  Giá trị phải là số từ 0 tới 1 (`0`, `0.1`, `1`); sai thì `make up`, reconciler GitOps và chính container APISIX
  dừng và báo lỗi, vì APISIX gặp giá trị sai sẽ bỏ cả global rule chung với WAF và mã yêu cầu.
- **Che dữ liệu, hai lớp:**
  - `svc-files`, `svc-workflow` (`tracing.py`) chỉ gửi thuộc tính trong danh sách trắng: phương thức, mã trạng thái,
    route, đường dẫn không có chuỗi truy vấn, tên máy. Chuỗi qua bộ che thông tin cá nhân (F4.4). Lời gọi tới máy
    ngoài mạng của Signet (tên có dấu chấm hay địa chỉ IP: webhook, liên thông) không có span và không
    mang `traceparent`, nên mã trace không ra khỏi các dịch vụ nội bộ. Lỗi chỉ giữ tên loại ngoại lệ, không giữ
    thông điệp hay traceback. Không ghi header nào (`Authorization`, cookie).
  - Jaeger bỏ `http.target` (đường dẫn kèm chuỗi truy vấn) trong span của APISIX, giữ `url.path`.
- **Giới hạn:**
  - span của APISIX vẫn có `user_agent.original` và `x-request-id` do client gửi (chuỗi tùy ý);
  - client tự gửi `traceparent` thì APISIX nối vào `trace_id` đó, và chọn theo chính `trace_id` đó: client chọn được
    `trace_id` rơi vào tỉ lệ, chỉ làm tăng số span (giới hạn tốc độ vẫn áp);
  - Flowable, Keycloak, PostgreSQL chưa gửi span;
  - Jaeger 2.22 bỏ API HTTP v1 mà nguồn dữ liệu Jaeger của Grafana dùng, nên chưa xem trace trong Grafana;
  - trace mất khi container Jaeger khởi động lại; giao diện không có tài khoản, như Grafana.
- **RAM** (máy dev, 28/10/2026): Jaeger nghỉ 11 MiB, đỉnh 123 MiB khi đầy 10 000 trace 6 span (bộ nhớ cgroup của
  container; trần compose 256m). Mỗi tiến trình `svc-files`, `svc-workflow` thêm khoảng 15 MiB khi bật (RSS, đo
  trước và sau khi nạp OpenTelemetry); tắt thì không thêm gì.

## Wiki nội bộ

Profile `wiki` (tắt mặc định, #367) thêm **DokuWiki** ở `/wiki/`: sổ tay, quy trình, hướng dẫn nội bộ viết dạng trang
wiki, không phải văn bản có số. Mỗi đơn vị một không gian `don-vi:<mã>` chỉ người của đơn vị đó đọc, sửa, tải tệp
lên; trang đầu liệt kê không gian của các đơn vị. Đăng nhập chỉ qua Keycloak (cùng tài khoản, cùng bước đăng nhập như
Văn phòng điện tử); chưa đăng nhập thì vào `/wiki/` chuyển sang trang đăng nhập. Trang Ứng dụng của Văn phòng điện tử
có thẻ "Wiki nội bộ" khi wiki đang trả lời.

```bash
# bật lâu dài: .env thêm wiki vào MOC_EXTRA_PROFILES (vd MOC_EXTRA_PROFILES=tunnel,wiki), rồi
make up                                 # dựng image, chạy wiki, chạy moc wiki sync
# hoặc bật một lần (make down tắt, make up sau đó không bật lại)
make wiki-up
make demo-wiki                          # kiểm: hai đơn vị không đọc, không sửa được trang của nhau
python3 scripts/moc.py wiki sync        # sau mỗi lần thêm đơn vị (moc tenant create)
make wiki-down                          # tắt: bỏ wiki khỏi MOC_EXTRA_PROFILES trước; giữ trang, tệp đã lưu
```

- **`moc wiki sync`** thêm client Keycloak `wiki` (confidential, bí mật `MOC_WIKI_CLIENT_SECRET` — `make up`, `make
  wiki-up` thêm vào `.env` cũ nếu thiếu) hoặc đặt lại bí mật, đường chuyển hướng và mapper `groups` (= `tenant_id`)
  của nó; rồi ghi danh sách quyền `conf/acl.auth.php` và trang đầu từ `core.tenants`. Chạy lại được; `--dry-run` chỉ
  in việc sẽ làm. Mã đơn vị thành tên không gian như alias của Organization (`KTCK` → `ktck`, `ĐT` → `dt`).
- **Quyền:** DokuWiki xét từ không gian sâu nhất lên. Mỗi đơn vị có đúng một dòng cho không gian của mình; không gian
  cha `don-vi` không cấp cho ai, nên không gian không còn dòng (đơn vị đổi mã, đơn vị mới chưa chạy `wiki sync`) rơi
  về dòng `* @ALL 0`: không ai đọc, không ai tạo trang. Người đăng nhập đọc được trang đầu và các trang hướng dẫn cú
  pháp đi kèm DokuWiki (`wiki:*`), không sửa được. Nhóm của một người lấy lại từ Keycloak mỗi lần đăng nhập: chuyển
  sang đơn vị khác thì lần đăng nhập sau mất quyền ở đơn vị cũ.
- **Không có tài khoản quản trị DokuWiki** (quản trị đọc được mọi không gian): trang quản trị, cài plugin, sửa cấu
  hình trên giao diện đều tắt. Cấu hình nằm ở
  [`platform/wiki/signet.protected.php`](../platform/wiki/signet.protected.php) (gắn chỉ đọc), plugin đi theo image;
  trình cài đặt `install.php` đã bỏ. Tài khoản trong wiki do plugin oauth tạo ở
  lần đăng nhập đầu, không đăng ký, không đặt lại mật khẩu trong wiki.
- **Sơ đồ trang** (`?do=index`) hiện tên không gian của mọi đơn vị (trang đầu vốn liệt kê chúng), không hiện trang
  của đơn vị khác. Tìm kiếm chỉ trả trang người tìm đọc được.
- **Mạng, tài nguyên:** container ở mạng `apps` như ứng dụng cắm thêm, chạy uid 33, bỏ mọi capability, trần 256 MiB
  (issue #367 đo container trống 37–70 MiB; chưa đo dưới tải); tệp tải lên tới 64 MB như mọi đường qua APISIX. Wiki
  gọi Keycloak qua `http://apisix:9080`, không tới thẳng dịch vụ lõi nào. WAF bỏ một số luật trên ô nội dung trang
  và tham số đăng nhập (loại trừ 10070, [`platform/apisix/README.md`](../platform/apisix/README.md)): chọn theo các
  loại trừ đã đo ở Văn phòng điện tử, chưa đo chặn nhầm trên chính wiki.
- **Sao lưu:** volume `wiki_data` (trang, bản cũ của trang, tệp tải lên, tài khoản, danh sách quyền) vào `moc backup`
  (mục Sao lưu và khôi phục).
- **Giới hạn:** chưa có không gian chung cả trường cùng sửa; đơn vị đổi mã thì trang cũ còn trong volume nhưng không
  ai đọc được tới khi chuyển tay sang không gian mới; trang wiki không vào ô tìm kiếm của Văn phòng điện tử.
  - Plugin oauth nối tài khoản wiki với tài khoản Keycloak theo email: người không có email trong Keycloak không đăng
    nhập được wiki; xóa một tài khoản Keycloak rồi tạo người khác cùng email thì người mới dùng lại tên wiki cũ (lịch
    sử sửa trang ghi chung một tên), còn quyền vẫn theo đơn vị của người mới. Email, `tenant_id` chỉ quản trị sửa
    được trong Keycloak, nên người dùng không tự nhận tài khoản wiki của người khác.
  - Nội dung trang vẫn qua các luật SQLi, XSS của WAF như ô chữ tự do của Văn phòng điện tử: trang có ví dụ câu SQL,
    mã HTML có thể bị chặn (403) khi lưu; gặp thì người quản trị thêm loại trừ trong `apisix.yaml`.

## Tự động hóa bằng Node-RED

Profile `tu-dong` (tắt mặc định, #366) thêm **Node-RED 5.0.8** ở `/tu-dong/`: người vận hành nền tảng kéo thả flow
(hẹn giờ, gọi HTTP, hàm JavaScript, mẫu chữ) thay vì viết thêm vòng lặp trong mã dịch vụ. Đăng nhập chỉ qua Keycloak
(client công khai `tu-dong`, PKCE), và chỉ người có vai trò `operator` của client đó vào được trình soạn; không ai có
sẵn vai trò này, kể cả quản trị đơn vị.

```bash
# bật lâu dài: .env thêm tu-dong vào MOC_EXTRA_PROFILES (vd MOC_EXTRA_PROFILES=wiki,tu-dong), rồi
make up                                 # dựng image, chạy Node-RED, chạy moc tu-dong sync
# hoặc bật một lần (make down tắt, make up sau đó không bật lại)
make tu-dong-up
python3 scripts/moc.py tu-dong operator add <tên đăng nhập>      # cấp vai trò; remove gỡ, list liệt kê
make demo-tu-dong                       # kiểm: chưa đăng nhập, không có vai trò thì không vào; triển khai flow qua cổng
make tu-dong-down                       # tắt: bỏ tu-dong khỏi MOC_EXTRA_PROFILES trước; giữ flow đã lưu
```

- **`moc tu-dong sync`** thêm client Keycloak `tu-dong`, vai trò `operator` và mapper `tu-dong-roles` (đưa vai trò
  vào ID token), hoặc đặt lại đường chuyển hướng khi đổi `MOC_PUBLIC_URL`. Chạy lại được; `--dry-run` chỉ in việc sẽ
  làm. Node-RED chỉ tin vai trò trong ID token, thứ thư viện `openid-client` đã kiểm chữ ký, `iss`, `aud`.
- **Gỡ vai trò** có hiệu lực ở lần đăng nhập sau: token trình soạn còn hạn (8 giờ) vẫn dùng được tới khi hết hạn hoặc
  Node-RED khởi động lại (`docker compose --profile tu-dong restart tu-dong`).
- **Khóa sẵn trong [`platform/tu-dong/settings.js`](../platform/tu-dong/settings.js)** (gắn vào image, không sửa trên
  giao diện): không có node `exec` (chạy lệnh shell), không có node đọc, ghi, theo dõi tệp (`file`, `file in`, `watch`);
  không cài, không tải node lên từ trình soạn; node Function không nạp module ngoài; flow chưa mở endpoint HTTP
  (`httpNodeRoot` tắt); không gửi số liệu chẩn đoán ra ngoài. Lúc dựng image, `kiem-tra.cjs` nạp thật tệp này và kiểm
  các khóa đó, kiểm cả hàm xét vai trò.
- **`MOC_TU_DONG_SECRET`** mã hóa thông tin đăng nhập lưu trong flow (mật khẩu, token của node): `make up`,
  `make tu-dong-up` thêm vào `.env` cũ nếu thiếu. Đổi khóa thì Node-RED không mở được thông tin đăng nhập đã lưu;
  khôi phục sang máy mới cũng cần đúng khóa này, nên nó đi cùng bản chép `.env` (mục Sao lưu và khôi phục).
- **Mạng, tài nguyên:** container ở mạng `apps` như ứng dụng cắm thêm: flow chỉ tới lõi qua `http://apisix:9080`
  (kiểm token, giới hạn tốc độ, WAF như với trình duyệt), không tới CSDL hay dịch vụ lõi nào. Rootfs chỉ đọc (ghi
  vào `/data`, `/tmp`), bỏ mọi capability, trần 256 MiB (issue #366 đo container trống khoảng 75 MiB; chưa đo dưới
  tải). WAF gỡ ba luật bắt nhầm token đăng nhập (loại trừ 10080) và không soi thân của API lưu flow, thư viện (10081),
  vì thân đó là mã JavaScript, HTML ([`platform/apisix/README.md`](../platform/apisix/README.md)).
- **Sao lưu:** volume `tu_dong_data` (flow, thông tin đăng nhập đã mã hóa, phiên trình soạn) vào `moc backup`
  (mục Sao lưu và khôi phục). Ai sửa flow nào ghi vào nhật ký container (`docker compose --profile tu-dong logs
  tu-dong`, dòng audit của Node-RED), chưa vào sổ kiểm toán.
- **Giới hạn:**
  - Node-RED là một không gian flow chung, không tách theo đơn vị: người có vai trò `operator` sửa được mọi flow, và
    flow gọi được mọi API qua cổng mà thông tin đăng nhập trong flow cho phép. Vì vậy đây là công cụ của người vận
    hành nền tảng, không phải của từng đơn vị.
  - Chưa có: endpoint nhận webhook (`/tu-dong/hook/…`) và bước BPMN gọi flow qua `svc-workflow` — bước tiếp theo
    của #366.

### Robot của flow và hai flow mẫu

Flow gọi API của lõi bằng **robot của một đơn vị**, không mượn tài khoản người (#366):

```bash
python3 scripts/moc.py tu-dong robot add CNTT     # in ROBOT_ID, ROBOT_SECRET; chạy lại thì đặt lại cấu hình, giữ bí mật
python3 scripts/moc.py tu-dong robot list         # robot đang có, đơn vị của từng robot
python3 scripts/moc.py tu-dong robot rotate CNTT  # bí mật lộ: Keycloak sinh bí mật mới, bí mật cũ hết dùng ngay
python3 scripts/moc.py tu-dong robot remove CNTT  # gỡ robot; token đã cấp còn dùng được tới khi hết hạn (5 phút)
```

- **Robot là gì:** client Keycloak confidential `tu-dong-robot-<mã>` chỉ có luồng `client_credentials` (không đăng
  nhập trình duyệt, không mật khẩu người), không full scope. Access token mang cố định vai trò Hasura `tu_dong`, đơn
  vị của robot và `x-hasura-user-id` là chính tên robot. Tài khoản dịch vụ của client không vào danh bạ người dùng.
- **Robot được làm gì:** đọc văn bản **không hạn chế** của đơn vị mình, kể cả dự thảo văn bản đi (`draft`, `returned`)
  như lãnh đạo, văn thư thấy (số ký hiệu, trích yếu, độ khẩn, trạng thái, hạn, ngày vào sổ, phòng xử lý; không có nội
  dung, người tạo, người nhận), và gọi Action `notifyFromFlow` báo người trong đơn vị theo vai trò. Không ghi bảng nào,
  không đọc danh bạ, thông báo, văn bản hạn chế hay của đơn vị khác
  ([`db/tests/test_tu_dong.py`](../db/tests/test_tu_dong.py)).
- **`notifyFromFlow(roles, title, text, document_id, key)`** (svc-workflow): gửi thông báo loại `flow.message` vào
  chuông, đẩy tức thời như thông báo khác; cùng `key` thì không gửi lại (flow chạy lại không báo trùng). Gắn
  `document_id` thì chỉ gửi được cho `director`, `clerk` — hai vai trò xem được mọi văn bản không hạn chế của đơn vị,
  để trích yếu không tới người không được xem văn bản đó. Văn bản của đơn vị khác, văn bản hạn chế bị từ chối.
  Luật này chỉ giữ văn bản gắn kèm: flow tự chép trích yếu, số ký hiệu vào `title`, `text` thì chúng tới mọi vai trò
  đã chọn — người viết flow chỉ gửi những thông tin đó cho `director`, `clerk`, như hai flow mẫu.
- **Kênh ngoài:** `flow.message` đi chuông và cả email, webhook, SMS, Zalo khi `MOC_NOTIFY_*_KINDS` để trống (mọi
  loại); danh sách văn bản sắp hạn mang theo nhiều trích yếu. Muốn tin của flow chỉ ở chuông thì liệt kê các loại
  khác vào `MOC_NOTIFY_*_KINDS`, bỏ `flow.message`.
- **Hai flow mẫu** ([`platform/tu-dong/flow-mau.json`](../platform/tu-dong/flow-mau.json), tab "Signet — flow mẫu",
  để tắt): (1) 07:00 hằng ngày gom văn bản đến chưa xong có hạn trong 3 ngày tới, báo lãnh đạo đơn vị một tin; (2) mỗi
  phút tìm văn bản Hỏa tốc vừa vào sổ, báo lãnh đạo mỗi văn bản một tin, bấm vào mở văn bản. Dùng: trình soạn → menu
  ☰ → Import → chọn tệp; mở tab, điền `ROBOT_ID`, `ROBOT_SECRET` (biến bí mật, mã hóa bằng `MOC_TU_DONG_SECRET`)
  trong phần Environment của tab; bật tab, Deploy. Một đơn vị một robot: muốn chạy cho đơn vị khác thì nhân bản tab,
  điền robot của đơn vị đó.

## Hội tụ IT/OT

Profile `iot` (không bật mặc định, khoảng 550 MB RAM) thêm context broker NGSI-LD **Scorpio** (chuẩn ETSI) cùng
CSDL PostGIS riêng của nó. Thiết bị cập nhật bản sao số của mình trong broker; `svc-workflow` giữ trong tenant NGSI-LD
của mỗi đơn vị (`NGSILD-Tenant` = mã đơn vị; mã có dấu thì `t` + băm của mã) một subscription
`temperature>MOC_OT_THRESHOLD`. Cảm biến vượt ngưỡng thì broker gọi `svc-workflow`, và dịch vụ dựng dự thảo văn bản
đi "Báo cáo sự cố" (loại Báo cáo, độ khẩn "Khẩn") từ mẫu cho chuyên viên phụ trách cảm biến, ghi sự kiện `ot.alarm`
vào dòng thời gian và báo người đó ngay. Còn dự thảo chưa trình (hoặc bị trả lại) của cùng cảm biến thì không dựng
thêm, chỉ nhắc người phụ trách, mỗi ngày nhiều nhất một lần. Giờ, ngày của báo cáo và của lượt nhắc theo giờ đo thiết
bị gửi (`observedAt`); giờ đó muộn hơn giờ máy chủ quá 2 phút (đồng hồ thiết bị chạy nhanh, như cờ **giờ đo ở tương
lai** bên dưới) thì theo lúc máy chủ nhận số đo, và dự thảo ghi rõ giờ thiết bị — không thì thiết bị nhanh 30 phút
gửi số đo lúc 23 giờ 50 làm báo cáo ghi ngày hôm sau. Dự thảo đi tiếp theo luồng văn bản đi như mọi văn bản khác.

```bash
make demo-it-ot                       # bật profile iot, cảm biến giả lập 24 → 41 °C, dự thảo, trình
docker compose --profile iot --profile iot-sim run --rm ot-sensor --tenant CNTT --responsible chuyenviendt \
    --name "Phòng máy chủ tầng 3" --readings 30,36   # gửi tay vài lần đo
```

- Thực thể cảm biến `urn:ngsi-ld:TemperatureSensor:<mã>` có `name` (tên phòng), `responsible` (tên đăng nhập
  chuyên viên phụ trách), `room` (mã phòng trên sơ đồ kho, tùy chọn: `sensor.py --room kho-1`) và `temperature` (°C,
  `observedAt`). Người phụ trách phải là chuyên viên đang hoạt động của đúng đơn vị, có phòng; không thì sự kiện bị
  bỏ qua (ghi nhật ký `ot.alarm_ignored`).
- **Sơ đồ cảm biến** (`/cam-bien` của Văn phòng điện tử, văn thư, chuyên viên, lãnh đạo phòng, lãnh đạo đơn vị): mặt
  bằng kho lưu trữ mẫu (SVG, không tải gì ngoài), mỗi phòng tô màu theo số đo mới nhất của cảm biến cùng mã phòng so
  với `MOC_OT_THRESHOLD`. Đọc qua Hasura Action `otSensorMap`: `svc-workflow` chỉ hỏi broker ở tenant của đơn vị
  người xem. Bốn cờ chất lượng tính ở `svc-workflow`: **mất tín hiệu** — quá `MOC_OT_STALE_MIN` phút (mặc định 10,
  1–1440) không có số đo mới; đặt từ 2–3 lần chu kỳ gửi của thiết bị thật; **ngoài dải** — giá trị không phải số
  hoặc ngoài −55…125 °C (dải đo của cảm biến DS18B20, hằng số trong `ot.py`); **trùng `observedAt`** — số đo mới
  nhất cùng giờ đo với một lần đo khác trong 10 lần gần nhất (temporal API); **giờ đo ở tương lai** — `observedAt`
  muộn hơn giờ máy chủ quá 2 phút (`FUTURE_SLACK` trong `ot.py`): đồng hồ thiết bị chạy nhanh. Khi đó mất tín hiệu
  xét theo lúc broker nhận số đo (`modifiedAt`), không theo giờ thiết bị — không thì thiết bị lệch giờ mà mất tín
  hiệu không bao giờ bị gắn cờ. Profile `iot` tắt thì trang báo "Chưa bật cảm biến", không lỗi. Giả lỗi để xem cờ:
  `sensor.py --late 30` (số đo cũ 30 phút), `--frozen-clock` (đồng hồ đứng), `--clock-ahead 30` (đồng hồ nhanh 30
  phút), `--readings 22,-127`.
- Broker và CSDL của nó không mở cổng ra máy chủ. Ba mạng nội bộ riêng: thiết bị ↔ broker (`iot-devices`), broker ↔
  `svc-workflow` (`iot`), broker ↔ CSDL của nó (`iot-db`) — thiết bị không gọi được `svc-workflow`. Mỗi lần gọi
  `POST /ot/notify/<tenant>` phải kèm token riêng của đơn vị (HMAC từ khóa Actions của `svc-workflow`), sai thì 401.
- **Giới hạn của sơ đồ:** mặt bằng mẫu cố định trong `apps/office/app/utils/otMap.ts` (một tầng, 6 phòng), mọi đơn vị
  dùng chung; dải đo không theo từng cảm biến; broker ghi lịch sử bất đồng bộ nên cờ trùng `observedAt` có thể chậm vài
  giây; tối đa 100 cảm biến mỗi đơn vị. Cờ chỉ hiện trên sơ đồ: số đo vượt ngưỡng vẫn dựng dự thảo "Báo cáo sự cố" kể
  cả khi ngoài dải.
- **Giới hạn:** broker không xác thực — ai vào được mạng thiết bị là ghi được vào tenant của đơn vị bất kỳ, kể cả
  khai người phụ trách là một chuyên viên của đơn vị đó. Triển khai thật phải đặt cổng thiết bị trước broker (IoT
  Agent hoặc PEP proxy của FIWARE) cấp tenant theo khóa của từng thiết bị; bản rút gọn chỉ có cảm biến giả lập.
- Broker gửi mỗi thông báo một lần: ghi CSDL lỗi thì lần vượt ngưỡng đó mất, lần đo kế tiếp còn trên ngưỡng sẽ dựng
  dự thảo.
- Cần `MOC_NGSI_DB_PASSWORD` trong `.env` (`make env` tự sinh). Thiết bị thật đi qua gateway IoT (vd IoT Agent
  của FIWARE) hoặc tự gửi NGSI-LD vào broker; lịch sử đo nằm trong broker (temporal API), không vào CSDL của Signet
  và không vào bản sao lưu.
- `make down` tắt cả profile `iot` và `iot-sim` (cảm biến giả lập, chỉ chạy một lần khi gọi).
