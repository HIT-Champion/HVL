# Mộc

> Lõi **DX-OS Open-Core** tự cài, lắp hoàn toàn từ phần mềm nguồn mở: định danh, cổng API, dữ liệu và
> quy trình dùng chung cho mọi ứng dụng. Lõi "đóng mộc" (đóng dấu) lên mọi thứ đi qua nó: biết ai đã
> làm, tệp sạch mã độc, không sửa lén được, và người ngoài kiểm chứng được.
>
> Ứng dụng đầu tiên trên lõi: **Văn phòng điện tử** quản lý văn bản đến / đi theo Nghị định
> 30/2020/NĐ-CP, kèm cổng xác thực văn bản bằng mã QR.
>
> Sản phẩm dự thi **Olympic Tin học Sinh viên Việt Nam 2026 — nội dung Phần mềm Nguồn mở (OLP PMNM 2026)**.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![CI](https://github.com/HIT-Champion/HVL/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/HIT-Champion/HVL/actions/workflows/ci.yml)

---

## Mộc giải bài toán gì

> Các tổ chức nhỏ chuyển đổi số bằng cách mua thêm phần mềm, nhưng mỗi phần mềm lại là một ốc đảo
> dữ liệu, hoặc buộc họ lệ thuộc một nhà cung cấp. **Mộc** là lõi nền tảng nguồn mở, tự cài, cung cấp
> sẵn định danh, cổng API, dữ liệu và quy trình cho mọi ứng dụng. Lõi "đóng mộc" lên mọi thứ đi qua nó:
> biết ai đã làm, tệp được quét mã độc trước khi lưu, mọi thay đổi vào sổ kiểm toán nên không sửa lén
> được, và những gì tổ chức phát hành ra ngoài thì người nhận kiểm chứng được. Ứng dụng Văn phòng điện
> tử chạy trên lõi cho thấy một công văn có thể đi trọn vòng đời — tiếp nhận, vào sổ, chỉ đạo, xử lý,
> trả lời, lưu trữ — mà không thất lạc, không quá hạn mà không ai hay, không bị sửa lén; và người nhận
> kiểm tra được văn bản là thật.

### Bài toán nền tảng

Hơn 900.000 doanh nghiệp nhỏ và vừa (SME) cùng các cơ quan nhà nước Việt Nam đang chuyển đổi số
theo một trong hai cách đều dẫn tới ngõ cụt:

- **Mua nhiều phần mềm rời rạc** — mỗi phần mềm một tài khoản, một kho dữ liệu, một quy trình.
  Dữ liệu tồn tại nhưng không chảy được giữa các bộ phận: **ốc đảo dữ liệu**.
- **Mua một hệ thống nguyên khối** — cồng kềnh, khó nâng cấp, tổ chức trở thành "con tin" của một
  nhà cung cấp và mất **chủ quyền số**.

Trong cả hai trường hợp, mỗi ứng dụng mới lại phải dựng lại từ đầu phần đăng nhập, lưu tệp, phân
quyền và quy trình duyệt.

Mộc tách phần dùng chung đó thành một **lõi nền tảng chạy ngầm, không giao diện**, dựng hoàn toàn
từ phần mềm nguồn mở để tổ chức tự làm chủ. Ứng dụng mới chỉ cần cắm vào lõi; thay ứng dụng ở tầng
trên không phải động đến lõi.

Điểm riêng của lõi Mộc là một lớp **tin cậy** dùng chung. Ứng dụng nào cắm vào cũng có sẵn, không phải
tự làm:

| Lõi "đóng mộc" | Nghĩa là | Thành phần | Cụm Tầng 1 |
|---|---|---|---|
| Biết ai đã làm | Mọi lời gọi mang danh tính SSO, kể cả tác tử AI | Keycloak, APISIX | ① ② |
| Sạch | Tệp được quét mã độc trước khi lưu | `svc-files` + ClamAV | ① |
| Không sửa lén được | Mọi thay đổi vào sổ kiểm toán chuỗi băm; hash đầu chuỗi neo ra ngoài CSDL | PostgreSQL, schema `core` | ⑥ |
| Kiểm chứng được từ bên ngoài | Tệp phát hành mang mã xác thực và SHA-256; API xác thực công khai, không cần đăng nhập | `svc-files`, route `/api/verify` | ④ ⑥ |

### Ứng dụng đầu tiên trên lõi: Văn phòng điện tử

Ở khoa, trường và các cơ quan nhỏ, công văn vẫn đến bằng giấy hoặc bản scan gửi qua email, Zalo; văn
thư ghi sổ tay hoặc Excel; lãnh đạo bút phê trên giấy. Phần mềm quản lý văn bản phổ biến lại là sản phẩm
đóng, giữ dữ liệu văn bản của cơ quan trong hệ thống của nhà cung cấp. Văn phòng điện tử chạy trên lõi
Mộc, quản lý văn bản đến và đi theo Nghị định 30/2020/NĐ-CP về công tác văn thư:

| Vấn đề hiện nay | Mộc xử lý bằng | Không gian |
|---|---|---|
| Văn bản thất lạc, không biết đang nằm ở bàn ai | Vào sổ, luồng xử lý BPMN, hộp việc, thông báo tức thời | [P] |
| Quá hạn giải quyết mà không ai nhắc | Hạn theo từng việc được giao, tự nhắc rồi leo thang; văn bản khẩn lên đầu | [P] |
| Nhập sai, vào sổ trùng | Chặn nhập sai ở cả form, máy chủ và CSDL theo một JSON Schema dùng chung (Poka-yoke); chặn vào sổ trùng | [P] |
| Tệp đính kèm có thể chứa mã độc | Quét virus trước khi lưu | Lõi |
| Không kiểm được văn bản nhận được là thật | Văn bản phát hành có mã QR; cổng xác thực công khai, ai cũng kiểm được | Lõi + [D] |
| Hồ sơ bị sửa lén sau khi lưu | Sổ kiểm toán chuỗi băm; lưu trữ hồ sơ sang kho lạnh có băm | Lõi + [D] |
| Văn bản nhạy cảm bị lộ | Lưu mã hóa, chỉ giải mã trong bộ nhớ khi người có quyền xem | [P] |
| Lãnh đạo không biết việc nghẽn ở đâu | Dashboard điều hành từ số liệu thật | [D] |
| Tìm lại văn bản cũ mất thời gian | Tìm kiếm toàn văn, cả chữ trong tệp PDF đính kèm; trợ lý hỏi đáp có trích dẫn số ký hiệu | [I] |

Chi tiết phạm vi, vai trò người dùng và kịch bản demo: [`docs/dac-ta-san-pham.md`](docs/dac-ta-san-pham.md).

Bài toán này đi đúng lộ trình tiến hóa `[H] → [P] → [D] → [I]` của mô hình DX-OS: có danh tính số
mới chuẩn hóa được quy trình, quy trình chuẩn mới sinh ra số liệu sạch, có số liệu sạch thì AI mới
gợi ý đúng. Mục tiêu của mô hình là giảm tỷ lệ thao tác thủ công từ **100% xuống 10–20%**.

## Đang chạy được

Lát cắt đầu tiên chạy trọn từ giao diện xuống lõi: **văn bản đến** — văn thư tải công văn lên (quét
ClamAV) → nhập thông tin, chặn trùng → vào sổ, hệ thống cấp số đến liên tiếp → lãnh đạo khoa chỉ đạo,
giao phòng chủ trì và phối hợp, đặt hạn → lãnh đạo phòng phân công → chuyên viên báo kết quả. Mỗi bước có
trong hộp việc của đúng người, hiện trên dòng thời gian văn bản và vào sổ kiểm toán chuỗi băm; tìm lại
được bằng chữ không dấu, kể cả chữ chỉ có trong tệp PDF đính kèm.

Lát cắt thứ hai là **văn bản đi và cổng xác thực**. Chuyên viên soạn công văn trả lời và xem trước bản PDF đúng
thể thức NĐ 30. Sau đó dự thảo được trình lãnh đạo phòng duyệt; bị trả lại thì sửa rồi trình lại. Lãnh đạo khoa
ký duyệt, rồi văn thư cấp số đi. Hệ thống dựng PDF có số, ký hiệu, ngày, **mã QR và SHA-256**. Người ngoài quét
mã QR, không cần đăng nhập, thấy văn bản có thật. Thả tệp nhận được vào trang xác thực: tệp nguyên vẹn thì
"khớp", sửa một byte thì "không khớp".

Văn thư và lãnh đạo khoa xem **sổ đăng ký văn bản đến, văn bản đi** theo năm, đúng các cột của mẫu sổ trong NĐ 30,
rồi in ra PDF để ký nhận và đóng sổ — nghị định bắt in khi đăng ký bằng hệ thống. Sổ luôn liền số từ 01, kể cả văn
bản hạn chế người in không được đọc (dòng đó chỉ có số, ngày, số ký hiệu); mỗi lần in vào sổ kiểm toán.

Ở mọi bước, người phải làm tiếp **nhận thông báo ngay** (Centrifugo, WebSocket): tin hiện ở góc màn hình, chuông
giữ lại tin, hộp việc tự cập nhật không phải tải lại trang. Để một bước quá thời hạn (`MOC_SLA_DURATION`, thật
`PT24H`, demo `PT1M`) thì timer trong quy trình BPMN nhắc người phải làm; quá hai thời hạn thì báo lãnh đạo của
họ, và dòng thời gian văn bản ghi lại cả hai lần.

```
 Trình duyệt ──► APISIX :8080 ─┬─ /             → app-office (Nuxt, trang tĩnh; /xac-thuc công khai)  Tầng 2
                (kiểm JWT,     ├─ /realms/moc/*  → Keycloak (đăng nhập SSO, TOTP)
                 X-Request-Id) ├─ /v1/graphql    → Hasura ─┬─ PostgreSQL (core, office)               Tầng 1
                               │                           └─ Actions → svc-workflow → Flowable (BPMN)
                               ├─ /api/files, /api/search, /api/documents/*, /api/registers/* → svc-files
                               ├─ /api/verify (không token, giới hạn theo IP) → svc-files
                               │  svc-files: ClamAV · SeaweedFS · Meilisearch · dựng PDF (WeasyPrint)
                               └─ /realtime (WebSocket) → Centrifugo ◄── svc-workflow đẩy thông báo
```

| Thành phần | Vai trò | Thư mục |
|---|---|---|
| Keycloak 26 | SSO; vai trò, đơn vị, phòng đưa vào token cho Hasura | `auth/realm/` |
| Apache APISIX 3 | Cổng duy nhất mở ra ngoài: danh sách trắng đường dẫn, kiểm JWT ở biên, chặn đường quản trị, giới hạn tốc độ đăng nhập (theo IP) và API (theo phiên) | `gateway/` |
| Hasura 2 + PostgreSQL 16 | GraphQL tự sinh, quyền theo vai trò và đơn vị đến từng dòng, sổ kiểm toán chuỗi băm | `db/` |
| Flowable 8 | Quy trình BPMN xử lý văn bản đến, duyệt và phát hành văn bản đi | `processes/` |
| `svc-workflow` | Hasura Actions: vào sổ, trình văn bản đi, hộp việc, hoàn thành việc, phát hành; thông báo sau mỗi bước, nhắc hạn theo timer BPMN; đồng bộ danh bạ Keycloak | `services/svc-workflow/` |
| Centrifugo 6 | Đẩy thông báo tới trình duyệt qua WebSocket, kênh riêng từng người; tự kiểm token Keycloak | `realtime/` |
| OpenBao 2 | Két bí mật: `svc-files`, `svc-workflow` lấy bí mật qua AppRole lúc khởi động; static seal tự mở khóa; khóa transit cho tệp mã hóa | `openbao/` |
| `svc-files` | Tải tệp qua ClamAV vào SeaweedFS, tải xuống theo quyền, tìm kiếm Meilisearch; dựng PDF văn bản đi có mã QR, in sổ đăng ký; cổng xác thực công khai | `services/svc-files/` |
| `app-office` | Giao diện Văn phòng điện tử (Nuxt 4, Tailwind), tiếng Việt / tiếng Anh | `apps/office/` |
| Prometheus 3 + Grafana 13 | Giám sát cổng API: số yêu cầu, mã trạng thái, độ trễ theo route; chỉ trong mạng nội bộ | `monitoring/` |

Phần còn lại theo [`docs/ke-hoach-phat-trien.md`](docs/ke-hoach-phat-trien.md): bằng chứng 4 nguyên lý
(Phase 3), AI (Phase 4). Đã có dashboard điều hành cho lãnh đạo đơn vị (trang **Điều hành**), sao lưu, khôi
phục một lệnh (`make backup`, `make restore`), két bí mật OpenBao, reconciler GitOps và tự phục hồi.
Văn bản phát hành có mã QR và SHA-256, chưa có chữ ký số theo hạ tầng khóa công khai.

## Yêu cầu hệ thống

| Thành phần | Phiên bản tối thiểu | Ghi chú |
|---|---|---|
| Docker Engine | 24.0 | kèm plugin `docker compose` v2 từ 2.17 |
| GNU Make | 4.0 | điều phối lệnh |
| Python | 3.10 | chỉ cho `make seed`, `make smoke`, `make audit`, `make demo-kiem-dich`, `make demo-ket-bi-mat`, `make demo-tu-phuc-hoi`, `make demo-nong-lanh`, `make demo-pha-he`, `make reconcile`, `make backup`, `make restore`, `make install`, `make api-docs` (thư viện chuẩn, không cài thêm gì) |
| RAM | 8 GB | cả hệ thống đo được khoảng 2,6 GB khi chạy (ClamAV 1 GB, Keycloak 0,6 GB, Flowable 0,3 GB) |
| Đĩa trống | 10 GB | image khoảng 5 GB |

Toàn bộ công cụ dùng để dựng Mộc đều là phần mềm nguồn mở. Không cần bất kỳ công cụ
nguồn đóng hay tự chế nào.

## Cài đặt từ mã nguồn (Building From Source)

```bash
# 1. Lấy mã nguồn
git clone https://github.com/HIT-Champion/HVL.git
cd HVL

# 2. Cấu hình (KHÔNG sửa mã nguồn để cấu hình — mọi tham số nằm trong .env)
make env              # sinh .env từ .env.example, mật khẩu ngẫu nhiên; hoặc: cp .env.example .env rồi sửa
make check

# 3. Dựng image của đội và khởi động toàn bộ (lần đầu vài phút: tải image, ClamAV nạp chữ ký)
make up

# 4. Nạp dữ liệu mẫu: 2 đơn vị, phòng ban, 10 tài khoản, ~17 văn bản ở mọi bước của quy trình
make seed
```

Mở <http://localhost:8080> và đăng nhập bằng một tài khoản mẫu; mật khẩu chung là giá trị
`MOC_DEMO_PASSWORD` trong `.env`. Văn thư, lãnh đạo và quản trị đơn vị bắt buộc xác thực hai bước: sau mật
khẩu nhập mã TOTP. `make seed` cài sẵn cho các tài khoản này một khóa chung (`MOC_DEMO_TOTP_SECRET`); `make totp`
in mã hiện tại và khóa để thêm một lần vào ứng dụng xác thực trên điện thoại (FreeOTP, Aegis, Google
Authenticator). Tài khoản thật thuộc các vai trò này tự cài TOTP bằng mã QR ở lần đăng nhập đầu.

| Tài khoản | Vai trò | Thấy gì |
|---|---|---|
| `vanthu` | Văn thư Khoa CNTT | Tiếp nhận, vào sổ; cấp số, phát hành văn bản đi; mọi văn bản của khoa |
| `truongkhoa` | Lãnh đạo khoa | Hộp việc chỉ đạo, ký duyệt văn bản đi; mọi văn bản của khoa |
| `totruongdt` | Tổ trưởng Đào tạo | Văn bản giao cho tổ; phân công; duyệt dự thảo của tổ |
| `chuyenviendt`, `giamkhao` | Chuyên viên Tổ Đào tạo | Văn bản được giao cho mình; soạn, trình văn bản đi |
| `vanthukt`, `truongkhoakt` | Khoa Kinh tế | Chỉ văn bản của Khoa Kinh tế |

Cổng xác thực văn bản không cần đăng nhập: <http://localhost:8080/xac-thuc>. Mã của các văn bản mẫu đã phát hành
có trên trang chi tiết văn bản (mục Văn bản đi, tab Đã phát hành).

Dừng: `make down` (giữ dữ liệu) · xóa sạch dữ liệu: `make reset` · xem mọi lệnh: `make help`.
Trang quản trị Keycloak chỉ mở trên máy chủ: <http://127.0.0.1:8180/admin> (tài khoản `KEYCLOAK_ADMIN_*`).

### Cài ra ngoài thư mục mã nguồn

`make install` dựng image của đội gắn thẻ phiên bản, chép `docker-compose.yml`, `.env` và các tệp cấu hình
mà container dùng sang `PREFIX`, rồi kiểm tra bản cài không còn trỏ về thư mục mã nguồn. Sau đó xóa thư mục
mã nguồn đi hệ thống vẫn chạy.

```bash
sudo install -d -o "$USER" /opt/moc     # thư mục cài thuộc người vận hành, không cần chạy make bằng root
make install PREFIX=/opt/moc
make down                               # nếu đang chạy trong thư mục mã nguồn: hai bản dùng chung dữ liệu
cd /opt/moc && docker compose up -d --wait
python3 scripts/seed.py                 # dữ liệu mẫu, lần đầu
```

- `PREFIX` mặc định là `/opt/moc`. Phiên bản lấy từ `git describe`; cài từ gói `.tar.gz` thì đặt tay:
  `make install PREFIX=/opt/moc MOC_VERSION=0.1.0`.
- Nâng cấp: dừng bản cài, `make install` lại với cùng `PREFIX`. Compose, cấu hình và image được thay; `.env`
  của bản cài được giữ, chỉ đổi `MOC_VERSION`.
- Gỡ: `make uninstall PREFIX=/opt/moc` xóa đúng các tệp đã cài, giữ `.env` và dữ liệu.

### Sao lưu và khôi phục

`make backup` sao lưu mọi CSDL (dữ liệu nghiệp vụ, Keycloak, Flowable) và toàn bộ tệp (SeaweedFS, kể cả các mốc
neo sổ kiểm toán) vào kho [restic](https://restic.net) mã hóa ở `MOC_BACKUP_DIR` (mặc định `./backups`); lần sau
chỉ thêm phần đã đổi. Để mọi CSDL và tệp cùng một thời điểm, Mộc tạm dừng ghi trong lúc dump CSDL (vài giây), còn
tải tệp lên, xuống thì đợi tới khi chép xong tệp. `make restore` kiểm bản sao lưu đọc được trọn vẹn, rồi mới dừng
Mộc, thay CSDL và tệp bằng lượt mới nhất (hỏi lại trước), ghi lần khôi phục vào sổ kiểm toán rồi chạy lại; `make
audit` sau đó vẫn khớp mốc neo trong bucket. Mốc đã chép ra tệp ngoài máy chủ (`audit anchor --to`) sau lúc sao lưu
thì không còn khớp — đúng như vậy, vì các dòng đó đã mất; `make audit` chỉ ra lần khôi phục để đối chiếu.

```bash
python3 scripts/moc.py backup create --keep 14    # sao lưu, chỉ giữ 14 lượt mới nhất (đặt vào cron hằng đêm)
python3 scripts/moc.py backup list                # các lượt trong kho
python3 scripts/moc.py backup check               # kiểm cấu trúc kho
python3 scripts/moc.py backup restore 20261020-020000   # khôi phục một lượt cụ thể
```

- **Khóa kho là `MOC_BACKUP_PASSWORD` trong `.env`: mất khóa là mất bản sao lưu.** Chép `.env` ra ngoài máy chủ.
  Bản cài có từ trước khi có lệnh này: thêm vào `.env` của bản cài một dòng `MOC_BACKUP_PASSWORD=` với chuỗi ngẫu
  nhiên dài (vd. `openssl rand -hex 24`).
- Kho nên nằm trên ổ khác hoặc ổ mạng đã gắn vào máy chủ (`MOC_BACKUP_DIR=/mnt/nas/moc`, thư mục trống hoặc kho
  có sẵn), và chép thêm một bản ra ngoài đơn vị: kho chỉ gồm tệp đã mã hóa, chép bằng `rsync` được. restic chạy bằng
  root trong container (để đọc tệp của SeaweedFS): ổ NFS phải cho root ghi (`no_root_squash`).
- Chỉ mục tìm kiếm và chữ ký ClamAV không sao lưu: `svc-files` dựng lại chỉ mục từ CSDL khi khởi động, ClamAV tự
  tải chữ ký.

### Két bí mật

`svc-files` và `svc-workflow` không nhận khóa kho S3, khóa quản trị Hasura, mật khẩu Flowable… qua biến môi trường.
Lúc khởi động, mỗi dịch vụ đăng nhập két [OpenBao](https://openbao.org) bằng AppRole của riêng mình và chỉ đọc được
phần bí mật của mình; két ghi sổ mọi lần đăng nhập và đọc (`docker compose logs openbao`, giá trị đã băm HMAC). Két
dùng *static seal*: khởi động lại là tự mở khóa, không cần người nhập khóa. Két cũng giữ khóa `moc-files` (transit)
để mã hóa tệp văn bản hạn chế về sau. Thử: `make demo-ket-bi-mat` (`docs/demo-script.md`).

Nói rõ giới hạn:

- `.env` vẫn là nguồn của các bí mật: container `openbao` nhận chúng qua biến môi trường và nạp lại vào két mỗi lần
  khởi động. Hasura, SeaweedFS, Meilisearch, Centrifugo (phần mềm thượng nguồn) vẫn đọc bí mật của chúng từ biến môi
  trường.
- Khóa mở két `MOC_OPENBAO_SEAL_KEY` nằm trong `.env`; khóa phục hồi, token khởi động và role_id/secret_id của dịch vụ
  nằm trong volume trên đĩa. Ai có quyền Docker trên máy chủ vẫn đọc được két. Két chỉ nằm trong mạng nội bộ
  `secrets` cùng hai dịch vụ (container khác không tới được), chưa có TLS.
- Két (volume `openbao_data`) chưa nằm trong `make backup`. Mất volume thì két khởi tạo lại và nạp bí mật từ `.env`,
  nhưng khóa transit mới sẽ khác.
- **Đổi `MOC_OPENBAO_SEAL_KEY` sau khi két đã khởi tạo thì két không mở được nữa.** Bản cài có từ trước khi có két:
  thêm vào `.env` của bản cài một dòng `MOC_OPENBAO_SEAL_KEY=` với chuỗi ngẫu nhiên dài (vd. `openssl rand -hex 32`).
- Đổi cấu hình két (thêm khóa, policy) cần token quản trị. Lần đầu khởi tạo, `openbao/start.sh` cấu hình bằng token
  root rồi thu hồi nó. Token khởi động không đọc thẳng được bí mật và không sửa được policy, nhưng cấp được secret_id
  nên làm được mọi việc hai dịch vụ làm được: giữ volume `openbao_data` như chính két.
- Đổi bí mật trong `.env` rồi `make up`: két được dựng lại và nạp bí mật mới, `svc-files`, `svc-workflow` khởi động
  lại theo (`depends_on … restart: true`, cần Docker Compose 2.17 trở lên).

### GitOps và tự phục hồi

`scripts/reconcile.py` đưa hệ thống đang chạy về đúng trạng thái khai trong git, mỗi lượt một lần gọi. Trên máy chủ,
systemd timer gọi nó mỗi 60 giây (tệp mẫu [`ops/systemd/`](ops/systemd/), chạy trên máy chủ chứ không trong container:
không gắn socket Docker vào container nào). Mỗi lượt:

- **Tự phục hồi**: container unhealthy thì khởi động lại; dịch vụ khai trong compose mà mất container hoặc đã dừng
  thì dựng lại (`docker compose up -d` đúng các dịch vụ đó). Thử: `make demo-tu-phuc-hoi` (`docs/demo-script.md`).
- **GitOps** (khi đặt `MOC_GITOPS_DIR` trong `.env` của bản cài): kéo nhánh `MOC_GITOPS_BRANCH` (mặc định `deploy`)
  về một bản sao git riêng của reconciler (bản sao có thay đổi chưa commit thì reconciler từ chối, không xóa việc của
  ai). Có commit mới, hoặc tệp đã cài bị sửa tay (khác băm lúc cài), thì dựng image của commit đó, dừng Mộc, cài lại
  đúng commit vào thư mục cài rồi chạy lại. Cài hỏng giữa chừng thì cài lại commit đang chạy trước đó. Commit áp lỗi
  thì không thử lại mỗi phút mà đợi commit kế tiếp.

```bash
# trên máy chủ, đã make install PREFIX=/opt/moc; người vận hành moc thuộc nhóm docker
git clone -b deploy https://github.com/HIT-Champion/HVL.git /opt/moc-src
echo "MOC_GITOPS_DIR=/opt/moc-src" >> /opt/moc/.env
python3 /opt/moc/scripts/reconcile.py          # thử một lượt
sudo cp ops/systemd/moc-reconcile.* /etc/systemd/system/ && sudo systemctl enable --now moc-reconcile.timer
```

- Áp một commit là cài lại toàn bộ: Mộc dừng khoảng một phút (`install.sh` không thay cấu hình dưới container đang
  chạy). Image cũ theo commit không tự xóa.
- `.env` (bí mật, cấu hình riêng của máy chủ) không nằm trong git và reconciler không đụng tới.
- Lượt reconciler bỏ qua khi đang sao lưu, khôi phục, `make install` (cả ba dùng chung một khóa trên thư mục cài),
  khi lần khôi phục trước dừng giữa chừng (không chạy lại Mộc trên dữ liệu dở dang: chạy lại `backup restore`) hoặc
  có dịch vụ đang tạm dừng có chủ ý. Dịch vụ còn tạm dừng từ một lần sao lưu bị giết cứng thì reconciler chạy lại.
- Bảo trì tay (`docker compose down`, sửa cấu hình thử) thì tắt timer trước: `sudo systemctl stop moc-reconcile.timer`,
  không thì reconciler dựng lại trong vòng một phút.
- `make smoke` và `make demo-tu-phuc-hoi` gọi `reconcile.py --heal-only`: chỉ tự phục hồi, không kéo commit mới.

### Giám sát

APISIX đếm mọi yêu cầu qua cổng (plugin `prometheus`, cổng xuất chỉ số 9091 chỉ trong mạng nội bộ). Prometheus thu
mỗi 15 giây, giữ `MOC_METRICS_RETENTION` (mặc định 15 ngày), không mở cổng ra ngoài. Grafana hiện bảng điều khiển
**Mộc — cổng API** nạp sẵn: yêu cầu mỗi giây theo route, mã trạng thái (429 = vượt giới hạn tốc độ), tỉ lệ lỗi 5xx,
độ trễ p95, băng thông, kết nối đang mở.

- Grafana chỉ nghe `127.0.0.1:MOC_GRAFANA_PORT` (mặc định 3300) trên máy chủ — xem từ máy khác qua đường hầm SSH:
  `ssh -L 3300:127.0.0.1:3300 máy-chủ` rồi mở `http://localhost:3300`.
- Không có tài khoản Grafana: ai vào được cổng đó thì chỉ xem. Bảng điều khiển sửa trong
  `monitoring/grafana/dashboards/` rồi cài lại, không sửa trên giao diện.
- Grafana (AGPL-3.0) chạy nguyên bản trong container riêng; Mộc chỉ nạp cấu hình qua tệp, không liên kết mã.
- Chỉ số không nằm trong bản sao lưu (`make backup`): khôi phục xong thì Prometheus thu lại từ đầu.

## Kiểm thử

| Lệnh | Kiểm gì | Cần |
|---|---|---|
| `make test` | Test đơn vị của `svc-files`, `svc-workflow`; kiểm form theo `schemas/` trên cùng bộ ca thử với svc-workflow và CSDL ([`schemas/README.md`](schemas/README.md)) | Python + [uv](https://github.com/astral-sh/uv); Node 24 và `npm ci` trong `apps/office` |
| `make smoke` | Đi trọn luồng văn bản đến và văn bản đi qua cổng APISIX, tra cổng xác thực không đăng nhập, nhận thông báo qua WebSocket, neo sổ kiểm toán rồi kiểm lại cả chuỗi; dữ liệu văn bản đến sai bị chặn ở svc-workflow và ở CSDL; chặn EICAR, chặn đường quản trị, cách ly đơn vị, giới hạn tốc độ; két đã mở khóa, dịch vụ không có bí mật trong biến môi trường, AppRole không đọc chéo; một lượt reconciler không thấy gì phải sửa; lập hồ sơ, nộp lưu, văn bản đã lưu vẫn xác thực được, phòng đọc đọc lại gói; Prometheus thu được chỉ số của cổng, Grafana có bảng điều khiển. Nhắc hạn chỉ kiểm khi `MOC_SLA_DURATION` ≤ 1 phút (`MOC_SLA_DURATION=PT20S make up` rồi `MOC_SLA_DURATION=PT20S make smoke`) | Hệ thống đang chạy + `make seed` |
| `make e2e` | Các luồng trên trình duyệt thật (Playwright, chạy trong container): form sai bị chặn trước khi gửi, kể cả thả tệp PDF vào trang xác thực: nguyên vẹn thì khớp, sửa một byte thì không; hai người dùng cùng lúc: chuyên viên trình, tổ trưởng thấy tin và việc mới không phải tải lại trang; lãnh đạo xem sổ kiểm toán; văn thư tải tệp EICAR bị chặn ngay, lãnh đạo thấy lần chặn trong sổ; lãnh đạo xem dashboard điều hành, văn thư không có mục này | Như trên |
| `make demo-kiem-dich` | Màn demo (iv) kiểm dịch, dưới một phút: tệp sạch qua, tệp EICAR bị ClamAV chặn ở cửa ngõ, không lưu gì; lần chặn nằm trong sổ kiểm toán, neo ra ngoài CSDL rồi kiểm lại cả chuỗi (`docs/demo-script.md`) | Hệ thống đang chạy + `make seed` |
| `make demo-ket-bi-mat` | Màn demo (iv) két bí mật, dưới một phút: dịch vụ không có bí mật trong biến môi trường; khởi động lại két thì két tự mở khóa; khởi động lại svc-files thì nó lấy lại khóa kho từ két và nhận tệp; AppRole không đọc chéo; sổ của két không chứa giá trị bí mật (`docs/demo-script.md`) | Hệ thống đang chạy + `make seed` |
| `make demo-tu-phuc-hoi` | Màn demo (iv) tự phục hồi, dưới một phút: xóa hẳn container `svc-files`, dừng `centrifugo`; tải tệp hỏng; một lượt reconciler dựng lại cả hai, tải tệp lại được (`docs/demo-script.md`) | Hệ thống đang chạy + `make seed` |
| `make demo-nong-lanh` | Màn demo (i) nóng → lạnh, dưới một phút: lập hồ sơ từ văn bản đã xong, đóng, nộp lưu ngay; gói Parquet + tệp + manifest có băm nằm trong bucket lạnh có khóa ghi, chi tiết rời khỏi CSDL; văn bản vẫn tìm thấy, quét mã vẫn "khớp"; phòng đọc đọc lại gói, kiểm băm; xóa gói bị từ chối (`docs/demo-script.md`) | Hệ thống đang chạy + `make seed` |
| `make demo-pha-he` | Màn demo (iii) phả hệ + chất lượng: lượt nộp lưu gần nhất là một run OpenLineage với 4 bước; truy ngược gói lưu trữ về bảng nghiệp vụ và tệp gốc; bảng Parquet nào cũng đã kiểm số dòng = CSDL, cột bắt buộc không null trước khi ghi (`docs/demo-script.md`) | Hệ thống đang chạy + `make seed` |
| `make audit` | Tính lại sổ kiểm toán chuỗi băm bên ngoài CSDL, so với các mốc đã neo ra bucket lạnh có khóa ghi và với hash của văn bản đã phát hành; sửa lén thì chỉ ra dòng bị sửa (`db/README.md`, mục Sổ kiểm toán) | Hệ thống đang chạy |
| Diễn tập khôi phục | `make backup` hai lượt, xóa volume CSDL và tệp, `python3 scripts/moc.py backup restore --yes`, rồi `make smoke` và `make audit` phải qua (bước trong CI) | Hệ thống đang chạy + `make seed` |
| `db/tests/` | 168 test schema, quyền, ràng buộc chặn dữ liệu sai (chung bộ ca thử với form), sổ kiểm toán (kể cả các kiểu sửa lén, giữ nguyên qua dump và khôi phục), cấp số đến và đi, thông báo trên PostgreSQL + Hasura thật | xem `db/README.md` |

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) chạy toàn bộ bảng trên cho mọi pull request: dựng hệ thống
từ mã nguồn bằng đúng các lệnh `make env` → `make up` → `make seed` → `make smoke` → `make e2e` → `make
demo-ket-bi-mat` → `make demo-tu-phuc-hoi` → `make demo-nong-lanh` → `make demo-pha-he`; diễn tập sao lưu, xóa dữ liệu, khôi phục rồi smoke lại; rồi `make install`
sang thư mục khác và chạy lại smoke từ bản cài; GitOps với repo git cục bộ: đẩy commit lên nhánh `deploy` thì
reconciler áp vào bản cài, sửa tay `docker-compose.yml` đã cài thì reconciler đưa về; kiểm tài liệu API trong
`docs/api/` khớp hệ thống vừa dựng; đồng thời quét bí mật trong lịch sử commit (gitleaks) và lỗ hổng đã biết trong các
tệp khóa phụ thuộc (OSV-Scanner).

## Tài liệu

| Tài liệu | Nội dung |
|---|---|
| [`docs/olp-2026-brief.md`](docs/olp-2026-brief.md) | Tóm tắt chủ đề DX-OS + thể lệ + tiêu chí chấm OLP 2026 |
| [`docs/olp-2026-de-thi.md`](docs/olp-2026-de-thi.md) | Phân tích đề thi chính thức, kiểm tra giấy phép bảng công nghệ tham chiếu |
| [`docs/dac-ta-san-pham.md`](docs/dac-ta-san-pham.md) | Đặc tả sản phẩm: bài toán, người dùng, chức năng, kịch bản demo |
| [`docs/ke-hoach-phat-trien.md`](docs/ke-hoach-phat-trien.md) | Kế hoạch phát triển theo phase, phân công, rủi ro |
| [`docs/git_flow.md`](docs/git_flow.md) | Quy trình Git: nhánh, commit, pull request, phát hành |
| [`docs/architecture.md`](docs/architecture.md) | Kiến trúc H-P-D-I, bản đồ công cụ, quyết định kỹ thuật |
| [`docs/mo-hinh-du-lieu.md`](docs/mo-hinh-du-lieu.md) | Mô hình dữ liệu, quyền, Hasura Actions, định dạng sự kiện |
| [`docs/api/`](docs/api/README.md) | Tài liệu API: lấy token, gọi GraphQL và REST qua cổng; schema GraphQL theo vai trò và OpenAPI xuất tự động (`make api-docs`) |
| [`docs/pof-checklist.md`](docs/pof-checklist.md) | Bảng tự chấm 50 điểm PoF |
| [`docs/nghien-cuu/`](docs/nghien-cuu/) | Nghiên cứu trước khi có đề thi (lưu trữ) |
| [`DEPENDENCIES.md`](DEPENDENCIES.md) | Danh mục phần mềm thượng nguồn + giấy phép |
| [`CHANGELOG.md`](CHANGELOG.md) | Lịch sử thay đổi |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Hướng dẫn đóng góp |
| [`ROADMAP.md`](ROADMAP.md) | Lộ trình phát triển |

## Báo lỗi và đóng góp

- **Báo lỗi / đề xuất tính năng**: mở issue tại <https://github.com/HIT-Champion/HVL/issues>
- **Đóng góp mã nguồn**: đọc [`CONTRIBUTING.md`](CONTRIBUTING.md) trước khi mở pull request
- **Quy tắc ứng xử**: [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)

## Giấy phép

Phát hành theo **Apache License 2.0** — một giấy phép được OSI phê duyệt.
Toàn văn: [`LICENSE`](LICENSE). Mục đích lựa chọn giấy phép: [`NOTICE`](NOTICE).

Mộc **điều phối** các phần mềm nguồn mở thượng nguồn ở dạng nguyên bản, không sao chép và
không chỉnh sửa mã nguồn của chúng vào kho này. Xem [`DEPENDENCIES.md`](DEPENDENCIES.md).

---

## English summary

Small organisations digitalise by buying more software, but each tool becomes a data silo or
locks them into a single vendor. **Mộc** (Vietnamese for the official seal stamped on a
document) is a self-hosted, open-source core platform — identity and SSO, an API gateway,
structured and unstructured data, and a workflow engine — that every application can build on,
assembled from upstream open-source components under an Open-Core architecture. The core puts
its seal on everything that passes through it: every call carries an identity, every file is
scanned for malware before it is stored, every change goes into a hash-chained audit log, and
whatever the organisation issues can be verified by outsiders through a public API.

The first application on the core is an e-Office that manages incoming and outgoing
official documents under Vietnam's Decree 30/2020 on clerical work: an official letter is
received, registered, assigned, handled, answered and archived without getting lost, missing
its deadline unnoticed or being silently altered. Every issued document carries a QR code, and a
public verification portal lets anyone check that a copy is genuine and unmodified. It targets
small and medium-sized enterprises, schools and public agencies that have no in-house IT team
and no software budget.

The system is organised into four control spaces — **H** (people), **P** (process),
**D** (data), **I** (AI) — deployed strictly in that order: automation is only introduced once
the data layer has a single source of truth and the process layer enforces input constraints.

Built for the Vietnam National Olympiad in Informatics 2026, Open Source Software track.
Licensed under Apache-2.0. Contributions welcome — see `CONTRIBUTING.md`.
