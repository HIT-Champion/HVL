# Signet

**English:** [README.en.md](README.en.md)

> **Lõi nền tảng nguồn mở, tự cài, đóng dấu tin cậy lên mọi thứ đi qua nó** — kèm ứng dụng đầu tiên chạy trên lõi:
> **Văn phòng điện tử** quản lý văn bản đến, văn bản đi theo Nghị định 30/2020/NĐ-CP.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![CI](https://github.com/HIT-Champion/Signet/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/HIT-Champion/Signet/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/HIT-Champion/Signet)](https://github.com/HIT-Champion/Signet/releases)

Sản phẩm dự thi **Olympic Tin học Sinh viên Việt Nam 2026 — nội dung Phần mềm Nguồn mở (OLP PMNM 2026)**, chủ đề
DX-OS Open-Core.

**Dùng thử:** <https://signet.htechcs.com> (bản v1.1.0, xem [Chạy thử](#chạy-thử)) · tự cài trên máy mình bằng bốn
lệnh ở [Cài đặt từ mã nguồn](#cài-đặt-từ-mã-nguồn-building-from-source).

**Đọc nhanh:** [Giới thiệu](#giới-thiệu) · [Kiến trúc](#kiến-trúc) · [Tính năng](#tính-năng) ·
[4 nguyên lý](#bằng-chứng-4-nguyên-lý) · [Công nghệ](#công-nghệ-và-giấy-phép) ·
[Cài đặt](#cài-đặt-từ-mã-nguồn-building-from-source) · [Chạy thử](#chạy-thử) · [Vận hành](#vận-hành-và-kiểm-thử) ·
[Sự cố](#xử-lý-sự-cố) · [Tài liệu](#tài-liệu) · [Liên hệ](#đóng-góp-và-liên-hệ) · [Giấy phép](#giấy-phép)

---

## Giới thiệu

*Signet* là chiếc nhẫn ấn xưa dùng để đóng dấu lên thư từ, văn bản: nhìn dấu biết ai gửi, niêm còn nguyên biết chưa ai
mở hay sửa. Lõi Signet làm đúng việc đó cho dữ liệu số.

Hơn 900.000 doanh nghiệp nhỏ và vừa cùng các trường, khoa, cơ quan cấp cơ sở đang chuyển đổi số bằng cách mua nhiều
phần mềm rời rạc (dữ liệu thành **ốc đảo**) hoặc một hệ thống nguyên khối (thành "con tin" của nhà cung cấp, mất **chủ
quyền số**). Đằng nào thì mỗi ứng dụng mới cũng dựng lại từ đầu phần đăng nhập, lưu tệp, phân quyền, quy trình duyệt —
và tự lo phần tin cậy, mà thường là không lo.

Signet tách phần dùng chung đó thành một **lõi chạy ngầm, không giao diện**, lắp hoàn toàn từ phần mềm nguồn mở để tổ
chức tự cài, tự làm chủ. Ứng dụng mới chỉ cần cắm vào lõi là có sẵn bốn con dấu tin cậy, không phải tự làm:

| Con dấu | Nghĩa là | Thành phần | Cụm Tầng 1 |
|---|---|---|---|
| Biết ai đã làm | Mọi lời gọi mang danh tính SSO, kể cả của tác tử AI; vai trò quan trọng bắt buộc xác thực hai bước | Keycloak, APISIX | ① ② |
| Sạch | Tệp được quét mã độc trước khi lưu, tệp bẩn không chạm tới kho | `svc-files` + ClamAV | ① |
| Không sửa lén được | Mọi thay đổi vào sổ kiểm toán chuỗi băm; mốc đầu chuỗi neo ra ngoài CSDL, sửa lén thì `make audit` chỉ ra dòng bị sửa | PostgreSQL, schema `core` | ⑥ |
| Kiểm chứng được từ bên ngoài | Văn bản phát hành mang mã QR, SHA-256 và chữ ký số (minh họa, không có giá trị pháp lý); cổng xác thực công khai, không cần đăng nhập | `svc-files`, route `/api/verify` | ④ ⑥ |

## Kiến trúc

[![Sơ đồ kiến trúc: người dùng đi qua cổng APISIX vào hai ứng dụng Tầng 2 và các dịch vụ lõi Tầng 1](docs/anh/kien-truc-tong-the.gif)](docs/anh/kien-truc-tong-the.gif)

Tầng 1 là lõi không giao diện: định danh, cổng API, dữ liệu, quy trình và lớp tin cậy. Tầng 2 là ứng dụng: Văn phòng
điện tử và Không gian cá nhân P.A.R.A, ứng dụng thứ hai cắm vào cùng lõi mà không sửa dòng mã nào của lõi
([`docs/them-ung-dung.md`](docs/them-ung-dung.md)). Ứng dụng thứ ba, Bảng tin đơn vị, chỉ có khi cắm bằng lệnh
`moc app install` nên không vẽ trong sơ đồ. Chỉ cổng APISIX mở ra ngoài, mọi yêu cầu qua tường lửa ứng dụng web ở đó
trước khi tới lõi; nhãn trên mũi tên là đường dẫn thật. Bên trong máy cũng vậy:
- container ứng dụng ở mạng Docker riêng `apps` (không ra Internet), nơi dịch vụ lõi duy nhất là APISIX;
- vì thế phần máy chủ của ứng dụng cũng gọi lõi qua cổng, qua cùng bước kiểm token, giới hạn tốc độ, WAF như trình
  duyệt;
- `make demo-cai-ung-dung` kiểm container chỉ tới được APISIX
  ([`docs/them-ung-dung.md`](docs/them-ung-dung.md#14-migration-và-mô-hình-tin-cậy) mục 1.4).

Viền đậm là mã của đội, hộp có logo là phần mềm nguồn mở dùng nguyên bản, chấm sáng đi theo hai yêu cầu thật. Kiến trúc
H-P-D-I và các quyết định kỹ thuật: [`docs/architecture.md`](docs/architecture.md).

## Tính năng

### Văn phòng điện tử

Ở khoa, trường và các cơ quan nhỏ, công văn vẫn đến bằng giấy hoặc bản scan gửi qua email, Zalo; văn thư ghi sổ tay
hoặc Excel; lãnh đạo bút phê trên giấy. Trên Signet, một công văn đi trọn vòng đời **tiếp nhận → vào sổ → chỉ đạo →
xử lý → trả lời → phát hành → lưu trữ** theo Nghị định 30/2020/NĐ-CP về công tác văn thư:

| Vấn đề hiện nay | Signet xử lý bằng | Không gian |
|---|---|---|
| Văn bản thất lạc, không biết đang nằm ở bàn ai | Vào sổ, luồng xử lý BPMN, hộp việc của đúng người, thông báo tức thời | [P] |
| Quá hạn giải quyết mà không ai nhắc | Hạn theo từng việc được giao, tự nhắc rồi báo lãnh đạo; văn bản khẩn lên đầu | [P] |
| Nhập sai, vào sổ trùng | Chặn nhập sai ở cả form, máy chủ và CSDL theo một JSON Schema dùng chung (Poka-yoke); chặn vào sổ trùng | [P] |
| Văn thư gõ lại từng công văn đến | Tác tử đọc lớp chữ PDF hoặc nhận dạng chữ bản scan, gợi ý sẵn số ký hiệu, ngày, cơ quan, trích yếu | [I] |
| Đơn vị gửi văn bản cho nhau qua email | Liên thông trên cùng bản cài: bên nhận có ngay văn bản đến, tệp trùng từng byte, kèm mã xác thực | [P] |
| Văn bản nhạy cảm bị lộ | Mã hóa từng tệp, chỉ giải mã trong bộ nhớ cho người có tên; bản mở đóng tên người xem lên mọi trang | [P] |
| Lãnh đạo không biết việc nghẽn ở đâu | Dashboard điều hành từ số liệu thật | [D] |
| Tìm lại văn bản cũ mất thời gian | Tìm toàn văn, cả chữ trong tệp PDF đính kèm; trợ lý hỏi đáp trả lời kèm số ký hiệu và trang | [I] |

Ngoài ra: sổ đăng ký văn bản đến, đi đúng mẫu NĐ 30; nhiều đơn vị trên một bản cài, mỗi người chỉ thấy dữ liệu của
đơn vị mình; giao diện tiếng Việt và tiếng Anh. Phạm vi và vai trò:
[`docs/dac-ta-san-pham.md`](docs/dac-ta-san-pham.md); mức hoàn thiện từng tính năng kèm bằng chứng:
[`docs/muc-hoan-thien.md`](docs/muc-hoan-thien.md).

### Không gian cá nhân P.A.R.A

Tệp của mỗi người xếp trong bốn thư mục Dự án · Lĩnh vực · Tài nguyên · Lưu trữ; client Keycloak riêng, gọi lõi qua
cổng như mọi ứng dụng, không sửa dòng mã nào của lõi (`make demo-ca-nhan`).

### Cắm thêm ứng dụng bằng một lệnh

`python3 scripts/moc.py app install apps/bang-tin/app.yaml` đọc manifest của ứng dụng rồi tạo client Keycloak, route
APISIX, container, schema và migration chạy bằng vai trò CSDL riêng của ứng dụng (không có quyền gì trên lõi), bảng và
quyền Hasura, và đăng ký nhận sự kiện văn bản của lõi; không sửa tệp nào của lõi. Chạy lại không tạo gì trùng;
`moc app remove` gỡ ứng dụng nhưng giữ dữ liệu. Ứng dụng mẫu là Bảng tin đơn vị (`apps/bang-tin`, `/bang-tin/`): văn
bản vừa vào sổ, vừa phát hành hiện lên theo sự kiện của lõi, mỗi người chỉ thấy tin của văn bản mình được xem
(`make demo-cai-ung-dung`). Cách làm, mô hình tin cậy và giới hạn: [`docs/them-ung-dung.md`](docs/them-ung-dung.md)
mục 1.

### Trợ lý AI chạy tại chỗ

AI trong Signet chỉ **gợi ý**, người quyết định; mọi thứ chạy trên máy chủ của tổ chức, không gửi dữ liệu ra ngoài.

| Tác tử | Làm gì |
|---|---|
| Đọc văn bản đến | Đọc lớp chữ PDF, hoặc nhận dạng chữ (Tesseract tiếng Việt) nếu là ảnh chụp, bản scan, rồi gợi ý sáu ô của form tiếp nhận kèm độ tin cậy. Số và ngày luôn do quy tắc theo thể thức NĐ 30 quyết, không bao giờ do mô hình. Trên 22 văn bản mẫu: số ký hiệu đúng 20/22, ngày ban hành đúng 22/22 |
| Hỏi đáp trên kho văn bản | Hỏi bằng câu thường ngày, nhận câu trích nguyên văn kèm nguồn "số ký hiệu · tr. n"; chỉ tìm trong văn bản người hỏi được xem, văn bản hạn chế không bao giờ vào chỉ mục |
| Gợi ý giao việc | Văn bản vừa vào sổ thì gợi ý đơn vị chủ trì và hạn xử lý, kèm các văn bản tương tự đã giao làm căn cứ; chạy song song, không chắn việc của lãnh đạo |
| Che thông tin cá nhân | Số CCCD, điện thoại, email, tài khoản ngân hàng bị che trước khi tới mô hình và nhật ký; người có quyền đọc văn bản vẫn thấy số thật |

Cả bốn chạy được **không cần mô hình ngôn ngữ**, nên CI, máy yếu, máy không có Internet đều chạy. Mô hình cục bộ
(Ollama, Qwen3 1,7B, chạy trên CPU) viết trích yếu và câu trả lời: `make ai-model` rồi `make up-ai`. Số đo và giới hạn
từng tác tử: [`docs/danh-gia-ai.md`](docs/danh-gia-ai.md).

### Ảnh chụp màn hình

Chụp tự động trong lượt e2e (`make e2e`), dữ liệu mẫu hư cấu. Giao diện mặc định tiếng Việt, trang nào cũng có bản
tiếng Anh.

| Văn thư tải công văn lên, tác tử điền sẵn các ô | Lãnh đạo xem việc nghẽn ở đâu | Người nhận tự kiểm văn bản, không cần đăng nhập |
|---|---|---|
| [![Tiếp nhận văn bản đến với các ô gợi ý](docs/anh/doc-van-ban-goi-y.png)](docs/anh/doc-van-ban-goi-y.png) | [![Dashboard điều hành](docs/anh/dieu-hanh.png)](docs/anh/dieu-hanh.png) | [![Cổng xác thực văn bản công khai](docs/anh/xac-thuc.png)](docs/anh/xac-thuc.png) |

## Bằng chứng 4 nguyên lý

Mỗi nguyên lý thiết kế của đề có màn demo chạy bằng **một lệnh**, dưới một phút, in từng bước kèm ✓, chạy lại bao
nhiêu lần cũng được — kịch bản trình bày ở [`docs/demo-script.md`](docs/demo-script.md).

| Nguyên lý | Màn demo | Lệnh |
|---|---|---|
| (i) Vòng đời và tốc độ dữ liệu | Hồ sơ đã đóng nộp lưu thành gói Parquet + tệp + manifest có băm trên kho lạnh khóa ghi; vẫn tìm thấy, quét mã QR vẫn "khớp"; trên giao diện: lập hồ sơ, lãnh đạo phòng nộp lưu, phòng đọc xem tệp có dấu tên người xem | `make demo-nong-lanh` |
| (ii) Hội tụ IT/OT | Cảm biến nhiệt độ → NGSI-LD (Scorpio) → vượt ngưỡng thì dựng dự thảo "Báo cáo sự cố" vào luồng văn bản đi | `make demo-it-ot` |
| (iii) Quản trị dữ liệu | Phả hệ OpenLineage: gói lưu trữ truy ngược về bảng nghiệp vụ và tệp gốc; kiểm số dòng, cột bắt buộc trước khi ghi; mỗi biểu đồ ở trang Điều hành truy về khung nhìn và bảng nguồn (tính từ catalog PostgreSQL), xem đồ thị ở trang Phả hệ số liệu (`/pha-he`) | `make demo-pha-he` |
| (iv) Zero-Trust | Kiểm dịch: tệp EICAR bị chặn ở cửa ngõ, lần chặn vào sổ kiểm toán | `make demo-kiem-dich` |
| (iv) Zero-Trust | Văn bản hạn chế: tệp mã hóa trong kho, chỉ người có tên mở được, bản mở có dấu tên | `make demo-han-che` |
| (iv) Zero-Trust | Két bí mật: dịch vụ không giữ bí mật, két tự mở khóa khi khởi động lại | `make demo-ket-bi-mat` |
| (iv) GitOps | Tự phục hồi: xóa container, reconciler dựng lại theo khai báo trong git | `make demo-tu-phuc-hoi` |

Các màn nghiệp vụ, cùng cách chạy: `make demo-lien-thong` (liên thông hai đơn vị), `make demo-nap-lo` (nạp lô văn bản
đến), `make demo-doc-van-ban`, `make demo-hoi-dap`, `make demo-giao-viec`, `make demo-che-pii` (trợ lý AI),
`make demo-ky-so` (ký số, minh họa), `make demo-ca-nhan` (ứng dụng thứ hai trên cùng lõi), `make demo-cai-ung-dung`
(cắm ứng dụng thứ ba bằng một lệnh), `make demo-log-tap-trung` (log tập trung).

## Công nghệ và giấy phép

Signet điều phối phần mềm nguồn mở ở dạng nguyên bản: image chính thức, phiên bản ghim, không sửa mã thượng nguồn.
Danh mục đầy đủ, cả thư viện và lý do chọn: [`DEPENDENCIES.md`](DEPENDENCIES.md).

| Không gian | Thành phần | Phiên bản | Giấy phép | Vai trò trong Signet |
|---|---|---|---|---|
| Cổng | Apache APISIX | 3.18.0 | Apache-2.0 | Cổng duy nhất mở ra ngoài: kiểm JWT ở biên, danh sách trắng đường dẫn, giới hạn tốc độ |
| Cổng | Coraza, OWASP CRS (coraza-proxy-wasm) | 3.3.3, 4.14.0 (0.6.0) | Apache-2.0 | Tường lửa ứng dụng web chạy trong APISIX: soi mọi yêu cầu trước khi kiểm token, tải tấn công nhận 403 |
| [H] | Keycloak | 26.7.5 | Apache-2.0 | Đăng nhập một lần, TOTP; vai trò, đơn vị, phòng đưa vào token |
| [P] | Flowable | 8.0.0 | Apache-2.0 | Quy trình BPMN văn bản đến, văn bản đi |
| [P] | Centrifugo | 6.9.7 | Apache-2.0 | Thông báo tức thời qua WebSocket, kênh riêng từng người |
| [D] | PostgreSQL | 16 | PostgreSQL | CSDL chính, sổ kiểm toán chuỗi băm |
| [D] | Hasura GraphQL Engine CE | 2.51.0 | Apache-2.0 | GraphQL tự sinh, quyền theo vai trò và đơn vị đến từng dòng |
| [D] | SeaweedFS | 4.48 | Apache-2.0 | Kho tệp chuẩn S3, kho lạnh khóa ghi cho hồ sơ nộp lưu |
| [D] | Meilisearch CE | 1.54.3 | MIT | Tìm toàn văn, chỉ mục đoạn của trợ lý hỏi đáp |
| [I] | Ollama, trọng số Qwen3 | 0.35.1 | MIT; trọng số Apache-2.0 | Mô hình ngôn ngữ cục bộ, tùy chọn (profile `ai`) |
| [I] | Tesseract OCR | 5.5.0 | Apache-2.0 | Nhận dạng chữ trên công văn scan, ảnh chụp |
| Tin cậy | ClamAV | 1.5.4 | GPL-2.0 | Quét mã độc trước khi lưu |
| Tin cậy | OpenBao | 2.7.1 | MPL-2.0 | Két bí mật, khóa mã hóa văn bản hạn chế, CA nội bộ và khóa ký |
| IT/OT | Scorpio Broker, PostGIS | 6.0.2, 16-3.5 | BSD-3-Clause, GPL-2.0 | Bản sao số của cảm biến theo NGSI-LD (profile `iot`) |
| Vận hành | Prometheus, Grafana OSS | 3.15.0, 13.2.3 | Apache-2.0, AGPL-3.0 | Giám sát cổng API, chỉ trong mạng nội bộ |
| Vận hành | Vector, Parseable | 0.59.0, 3.2.4 | MPL-2.0, AGPL-3.0 | Log tập trung đã che thông tin cá nhân, tùy chọn (profile `logs`) |
| Vận hành | restic | 0.19.1 | BSD-2-Clause | Sao lưu mã hóa CSDL, tệp, két |

Mọi giấy phép đều được OSI phê duyệt. Thành phần GPL, AGPL (ClamAV, PostGIS, Grafana, Parseable) chạy thành dịch vụ
độc lập, giao tiếp qua mạng, không liên kết mã nên không xung đột với Apache-2.0. Giấy phép mọi gói, kể cả gói gián
tiếp, được kiểm tự động bằng `make license-audit`.

## Cài đặt từ mã nguồn (Building From Source)

### Yêu cầu hệ thống

| Thành phần | Phiên bản tối thiểu | Ghi chú |
|---|---|---|
| Docker Engine | 24.0 | kèm plugin `docker compose` v2 từ 2.17 và `docker buildx` |
| GNU Make | 4.0 | điều phối lệnh |
| Python | 3.10 | chỉ thư viện chuẩn, không cài thêm gì: dữ liệu mẫu, smoke, demo, sao lưu, cài đặt và các lệnh vận hành |
| RAM | 8 GB | cả hệ thống (profile mặc định, 16 container) đo được khoảng 3,2 GB khi chạy (ClamAV 0,8 GB, Keycloak 0,6 GB, APISIX và Flowable mỗi dịch vụ 0,35 GB, Grafana 0,3 GB), đo từ trước khi thêm `app-ca-nhan` (một nginx phục vụ trang tĩnh); bật mô hình AI cần thêm tới 6 GB |
| Đĩa trống | 10 GB | image khoảng 5 GB; mô hình AI thêm khoảng 2 GB |

Toàn bộ công cụ dùng để dựng Signet đều là phần mềm nguồn mở. Không cần bất kỳ công cụ nguồn đóng hay tự chế nào.

### Các bước

```bash
# 1. Lấy mã nguồn
git clone https://github.com/HIT-Champion/Signet.git
cd Signet

# 2. Cấu hình (KHÔNG sửa mã nguồn để cấu hình — mọi tham số nằm trong .env)
make env              # sinh .env từ .env.example, mật khẩu ngẫu nhiên; hoặc: cp .env.example .env rồi sửa
make check

# 3. Dựng image của đội và khởi động toàn bộ (lần đầu vài phút: tải image, ClamAV nạp chữ ký)
make up

# 4. Nạp dữ liệu mẫu: 2 đơn vị, phòng ban, 10 tài khoản, văn bản ở mọi bước của quy trình
make seed
```

Mở <http://localhost:8080> và đăng nhập bằng một tài khoản ở mục [Chạy thử](#chạy-thử). Dừng: `make down` (giữ dữ liệu)
· xóa sạch dữ liệu: `make reset` · xem mọi lệnh: `make help`. Lên máy chủ có tên miền và HTTPS (Caddy trước APISIX),
hoặc máy không có IP công khai như laptop, máy ở nhà (Cloudflare Tunnel, profile `tunnel`, không mở cổng nào):
[`docs/trien-khai.md`](docs/trien-khai.md).

### Cài ra ngoài thư mục mã nguồn

`make install` dựng image của đội gắn thẻ phiên bản, chép `docker-compose.yml`, `.env` và các tệp cấu hình mà
container dùng sang `PREFIX`, rồi kiểm tra bản cài không còn trỏ về thư mục mã nguồn. Sau đó xóa thư mục mã nguồn đi
hệ thống vẫn chạy.

```bash
sudo install -d -o "$USER" /opt/moc     # thư mục cài thuộc người vận hành, không cần chạy make bằng root
make install PREFIX=/opt/moc
make down                               # nếu đang chạy trong thư mục mã nguồn: hai bản dùng chung dữ liệu
cd /opt/moc && docker compose up -d --wait
python3 scripts/seed.py                 # dữ liệu mẫu, lần đầu
```

- `PREFIX` mặc định là `/opt/moc`. Phiên bản lấy từ `git describe`; cài từ gói `.tar.gz` thì đặt tay:
  `make install PREFIX=/opt/moc MOC_VERSION=0.1.0`.
- Gói có tệp `VERSION` ở thư mục gốc thì phiên bản đã ghi sẵn trong đó (`git archive` điền khi đóng gói), `make install`
  tự đọc, không cần đặt tay.
- Nâng cấp: dừng bản cài, `make install` lại với cùng `PREFIX`. Compose, cấu hình và image được thay; `.env` của bản
  cài được giữ, trừ `MOC_VERSION`, `COMPOSE_PROFILES` và `COMPOSE_FILE` do `make install` đặt lại mỗi lần.
  Bản cài đang chạy có dữ liệu thì dùng `scripts/nang_cap.sh nang /opt/moc`: sao lưu trước, kiểm sau, có lệnh lùi
  ([`docs/trien-khai.md`](docs/trien-khai.md) mục Vận hành).
- Gỡ: `make uninstall PREFIX=/opt/moc` xóa đúng các tệp đã cài, giữ `.env` và dữ liệu.

## Chạy thử

**Bản online** <https://signet.htechcs.com> chạy bản phát hành v1.1.0 trên máy của đội, ra Internet qua Cloudflare
Tunnel. Tài khoản dùng thử gửi kèm hồ sơ dự thi; repo không công khai mật khẩu. Tính năng mới hơn v1.1.0 (mục
"Chưa phát hành" của [`CHANGELOG.md`](CHANGELOG.md)) có khi tự cài từ mã nguồn.

**Bản tự cài:** mật khẩu chung của các tài khoản mẫu là giá trị `MOC_DEMO_PASSWORD` trong `.env`. Văn thư, lãnh đạo,
tổ trưởng, trưởng bộ môn và quản trị đơn vị bắt buộc xác thực hai bước: sau mật khẩu nhập mã TOTP. `make seed` cài sẵn
cho các tài khoản này một khóa chung (`MOC_DEMO_TOTP_SECRET`); `make totp` in mã hiện tại và khóa để thêm một lần vào
ứng dụng xác thực trên điện thoại (FreeOTP, Aegis, Google Authenticator). Tài khoản thật thuộc các vai trò này tự cài
TOTP bằng mã QR ở lần đăng nhập đầu.

| Tài khoản | Vai trò | Thấy gì |
|---|---|---|
| `vanthu` | Văn thư Khoa CNTT | Tiếp nhận, vào sổ; cấp số, phát hành văn bản đi; mọi văn bản của khoa |
| `truongkhoa` | Lãnh đạo khoa | Hộp việc chỉ đạo, ký duyệt văn bản đi; dashboard điều hành; mọi văn bản của khoa |
| `totruongdt`, `truongbmktpm` | Tổ trưởng Đào tạo, trưởng Bộ môn KTPM | Văn bản giao cho tổ, bộ môn; phân công; duyệt dự thảo |
| `chuyenviendt`, `giamkhao`, `giangvienktpm` | Chuyên viên, giảng viên | Văn bản được giao cho mình; soạn, trình văn bản đi |
| `quantri` | Quản trị đơn vị | Sổ kiểm toán của khoa; không đọc nội dung văn bản |
| `vanthukt`, `truongkhoakt` | Khoa Kinh tế | Chỉ văn bản của Khoa Kinh tế |

Ban giám khảo thử nhanh bằng `giamkhao` (chuyên viên, không cần TOTP): hộp việc có sẵn một công văn khẩn chờ xử lý
và một dự thảo phúc đáp bị tổ trưởng trả lại chờ sửa.

| Địa chỉ trên bản tự cài | Là gì | Đăng nhập |
|---|---|---|
| <http://localhost:8080> | Văn phòng điện tử | Có |
| <http://localhost:8080/ca-nhan/> | Không gian cá nhân P.A.R.A | Có |
| <http://localhost:8080/bang-tin/> | Bảng tin đơn vị, sau khi cắm bằng `make app-install APP=apps/bang-tin/app.yaml` | Có |
| <http://localhost:8080/xac-thuc> | Cổng xác thực văn bản: nhập mã hoặc thả tệp PDF; mã của văn bản mẫu ở trang chi tiết văn bản (Văn bản đi, tab Đã phát hành) | Không |
| <http://localhost:8080/trang-thai> | Trạng thái hệ thống | Không |
| <http://127.0.0.1:8180/admin> | Quản trị Keycloak, chỉ mở trên máy chủ (tài khoản `KEYCLOAK_ADMIN_*`) | Có |
| <http://127.0.0.1:3300> | Grafana giám sát cổng API, chỉ mở trên máy chủ (từ xa: đường hầm SSH) | Không |

## Vận hành và kiểm thử

Các việc của người quản trị trên bản cài đang chạy nằm ở [`docs/van-hanh.md`](docs/van-hanh.md):

| Việc | Lệnh chính |
|---|---|
| [Thêm đơn vị](docs/van-hanh.md#thêm-đơn-vị-thuê-ước) (khoa, phòng, trường thành viên) | `python3 scripts/moc.py tenant create …` |
| [Sao lưu và khôi phục](docs/van-hanh.md#sao-lưu-và-khôi-phục) mọi CSDL, tệp, két vào kho restic mã hóa | `make backup`, `make restore` |
| [Két bí mật](docs/van-hanh.md#két-bí-mật) OpenBao: giới hạn, nâng cấp két cũ để ký số | `make demo-ket-bi-mat` |
| [GitOps và tự phục hồi](docs/van-hanh.md#gitops-và-tự-phục-hồi): systemd timer, chỉ áp commit đã ký | `make reconcile` |
| [Giám sát](docs/van-hanh.md#giám-sát) cổng API bằng Prometheus + Grafana | đường hầm SSH tới cổng 3300 |
| [Log tập trung](docs/van-hanh.md#log-tập-trung): Vector + Parseable, tra theo mã yêu cầu `X-Request-Id` | `make logs-up`, `make logs-tra ID=…` |
| [Hội tụ IT/OT](docs/van-hanh.md#hội-tụ-itot): broker NGSI-LD, cảm biến | `make demo-it-ot` |
| [Cắm ứng dụng](docs/them-ung-dung.md#1-một-lệnh-moc-app-install) bằng manifest, không sửa lõi; gỡ giữ dữ liệu | `python3 scripts/moc.py app install …`, `app list`, `app remove` |
| [Tường lửa ứng dụng web](platform/apisix/README.md#tường-lửa-ứng-dụng-web--waf-f315): chặn, chỉ ghi nhật ký hay tắt; đọc dòng chặn theo `X-Request-Id` | `MOC_WAF=On` · `DetectionOnly` · `Off` |
| [Kiểm sổ kiểm toán](db/README.md) ngoài CSDL | `make audit` |

| Lệnh | Kiểm gì | Cần |
|---|---|---|
| `make test` | Test đơn vị của `svc-files`, `svc-workflow`, lệnh vận hành; kiểm form theo `schemas/` trên cùng bộ ca thử với máy chủ và CSDL; test của Không gian cá nhân và Bảng tin | Python + [uv](https://github.com/astral-sh/uv); Node 24 và `npm ci` trong `apps/office` |
| `make smoke` | Đi trọn luồng văn bản đến, văn bản đi qua cổng APISIX; cổng xác thực, thông báo WebSocket, sổ kiểm toán; chặn dữ liệu sai, EICAR, đường quản trị; cách ly đơn vị; giới hạn tốc độ; két bí mật; reconciler; nộp lưu; giám sát; WAF chặn tải tấn công mà không chặn nhầm dữ liệu thật | Hệ thống đang chạy + `make seed` |
| `make e2e` | Trình duyệt thật (Playwright, trong container): form sai bị chặn trước khi gửi, thả tệp vào trang xác thực, hai người dùng cùng lúc nhận thông báo, sổ kiểm toán, dashboard, ký số | Như trên |
| `make do-doc-van-ban`, `do-hoi-dap`, `do-giao-viec`, `do-che-pii`, `do-so-lieu-sau` | Đo các tác tử AI trên bộ mẫu có đáp án (đúng / sai / trống từng trường, recall@3, độ phủ); số đo "sau" theo đặc tả §8 | Hệ thống đang chạy (`do-che-pii` không cần) |
| `db/tests/` | Schema, quyền theo vai trò và đơn vị, ràng buộc, sổ kiểm toán (kể cả các kiểu sửa lén) trên PostgreSQL + Hasura thật | xem [`db/README.md`](db/README.md) |
| `make sbom`, `make license-audit` | SBOM CycloneDX của cây mã nguồn (Syft); giấy phép của mọi gói npm, Python, action CI, kể cả gói gián tiếp, theo chính sách trong `DEPENDENCIES.md` | Docker, mạng tới PyPI |

[CI](.github/workflows/ci.yml) chạy cả bảng trên và các màn demo cho mọi pull request đổi mã: dựng từ mã nguồn bằng
đúng các lệnh cài đặt, diễn tập sao lưu và khôi phục, cài ra thư mục khác, GitOps, quét bí mật và lỗ hổng phụ thuộc.
Nhắc hạn chỉ kiểm được khi hạn ngắn: `MOC_SLA_DURATION=PT20S make up` rồi `MOC_SLA_DURATION=PT20S make smoke`.

## Xử lý sự cố

| Hiện tượng | Nguyên nhân và cách xử lý |
|---|---|
| `make check` báo thiếu `.env` hoặc `docker compose` | Chạy `make env` để sinh `.env`; cài plugin Docker Compose v2 từ 2.17 trở lên |
| `make up` dừng khi kéo hay dựng image: hết thời gian chờ tới `docker.io`, hoặc `toomanyrequests` | Mạng chặn Docker Hub hoặc đã hết lượt tải ẩn danh. Cho Docker kéo qua bản sao `mirror.gcr.io` (khóa `registry-mirrors`, cần `sudo`) theo mục 2b của [`docs/trien-khai.md`](docs/trien-khai.md#2b-máy-không-kéo-được-image-từ-docker-hub) |
| `make up` chạy lâu, dịch vụ còn `starting` hoặc `unhealthy` | Lần đầu phải tải khoảng 5 GB image và ClamAV nạp chữ ký virus, mất vài phút; `make up` chờ tối đa 10 phút. Theo dõi bằng `make ps`, `make logs` |
| Cổng 8080 đã có chương trình khác dùng | Đặt `MOC_HTTP_PORT=8081` và `MOC_PUBLIC_URL=http://localhost:8081` trong `.env` trước lần `make up` đầu tiên: realm Keycloak chỉ nạp địa chỉ này một lần, đã chạy rồi thì `make reset` rồi dựng lại |
| Mở bằng IP trong mạng LAN thì không đăng nhập được | Trình duyệt chỉ cho dùng Web Crypto (đăng nhập PKCE, tính SHA-256 ở trang xác thực) trên `https` hoặc `localhost`. Dùng `localhost`, hoặc lên HTTPS theo [`docs/trien-khai.md`](docs/trien-khai.md) |
| Mã TOTP bị từ chối | Đồng hồ điện thoại lệch (mã đổi mỗi 30 giây): bật giờ tự động, hoặc lấy mã theo đồng hồ máy chủ bằng `make totp`. Sai 10 lần thì Keycloak tạm khóa tài khoản |
| Báo "Cổng an ninh chặn nội dung này vì có chữ giống mẫu tấn công" (HTTP 403) | WAF ở cổng APISIX thấy chữ giống tải tấn công. Sửa chữ hoặc tên tệp rồi gửi lại. Nếu là dữ liệu thật bị chặn nhầm thì lấy mã yêu cầu (`X-Request-Id`) của lần chặn, tìm bằng `docker compose logs apisix \| grep <mã>` và thêm loại trừ theo [`platform/apisix/README.md`](platform/apisix/README.md#đọc-nhật-ký-chặn); tạm thời có thể đặt `MOC_WAF=DetectionOnly` (chỉ ghi nhật ký) rồi `docker compose up -d apisix` |
| Máy chậm hoặc hết RAM sau khi bật AI | Mô hình cần thêm tới 6 GB RAM. Tắt bằng `docker compose --profile ai stop ollama`; các tác tử tự về chế độ không cần mô hình |

Chưa gỡ được thì [mở issue theo mẫu báo lỗi](https://github.com/HIT-Champion/Signet/issues/new?template=bug_report.yml),
kèm kết quả `make ps` và đoạn `make logs` của dịch vụ lỗi.

## Tài liệu

| Nhóm | Tài liệu |
|---|---|
| Dùng và vận hành | [Kịch bản demo](docs/demo-script.md) · [Vận hành](docs/van-hanh.md) · [Triển khai lên máy chủ](docs/trien-khai.md) · [Tài liệu API](docs/api/README.md) · [Thêm ứng dụng mới trên lõi](docs/them-ung-dung.md) |
| Kỹ thuật | [Kiến trúc H-P-D-I](docs/architecture.md) · [Mô hình dữ liệu và quyền](docs/mo-hinh-du-lieu.md) · [Đặc tả sản phẩm](docs/dac-ta-san-pham.md) · [Mức hoàn thiện kèm bằng chứng](docs/muc-hoan-thien.md) · [Đánh giá AI](docs/danh-gia-ai.md) · [Số đo "sau" theo đặc tả §8](docs/so-lieu-sau.md) · [Tự chẩn đoán H-P-D-I](docs/tu-chan-doan.md) · [Quy trình Git](docs/git_flow.md) |
| Dự thi | [Bảng tự chấm PoF](docs/du-thi/pof-checklist.md) · [Câu hội đồng dễ hỏi](docs/du-thi/hoi-dap-hoi-dong.md) · [Chủ đề, thể lệ, tiêu chí chấm](docs/du-thi/olp-2026-brief.md) · [Phân tích đề thi](docs/du-thi/olp-2026-de-thi.md) · [Kế hoạch phát triển](docs/du-thi/ke-hoach-phat-trien.md) · [Nghiên cứu trước khi có đề](docs/du-thi/nghien-cuu/) |
| Dự án | [Phụ thuộc và giấy phép](DEPENDENCIES.md) · [Lịch sử thay đổi](CHANGELOG.md) · [Hướng dẫn đóng góp](CONTRIBUTING.md) · [Chính sách bảo mật](SECURITY.md) · [Lộ trình](ROADMAP.md) · [Quy tắc ứng xử](CODE_OF_CONDUCT.md) |

### Cấu trúc thư mục

Mã đội tự viết nằm ở `apps/`, `services/` và `db/`. `platform/` chỉ chứa cấu hình cho các phần mềm nguồn mở mà lõi dùng
nguyên bản (image chính thức, không sửa mã thượng nguồn).

```
apps/                Văn phòng điện tử (office/, Nuxt 4) · Không gian cá nhân P.A.R.A (ca-nhan/) · Bảng tin đơn vị
                     (bang-tin/, cắm bằng moc app install)
services/            svc-workflow/: Hasura Actions, quy trình BPMN, thông báo, nhắc hạn, gợi ý giao việc
                     svc-files/: tệp, kiểm dịch, tìm kiếm, dựng PDF, ký số, cổng xác thực, các tác tử AI
                     ot-sensor/: cảm biến nhiệt độ giả lập (profile iot-sim)
db/                  Lược đồ PostgreSQL, quyền Hasura theo vai trò và đơn vị, sổ kiểm toán chuỗi băm; tests/
schemas/             JSON Schema của form, dùng chung cho giao diện, dịch vụ và CSDL
platform/            Cấu hình Keycloak, APISIX, Centrifugo, OpenBao, giám sát, log tập trung, systemd
scripts/             Lệnh vận hành (moc.py, seed, smoke, backup, audit, reconcile, demo), cài đặt, công cụ của repo
                     (kiểm PR, phát hành, header giấy phép, sinh sơ đồ kiến trúc so_do_kien_truc.py)
seed/ tests/e2e/     Dữ liệu mẫu hư cấu · test trình duyệt (Playwright)
docs/                Tài liệu sản phẩm; api/: tài liệu API; du-thi/: tài liệu dự thi
docker-compose.yml   Toàn hệ thống, chia profile core, app, ai, iot, logs…
Makefile             Lối vào mọi lệnh: make env, up, seed, test, smoke, install…
```

> Signet trước đây tên **Mộc**. Tên mã kỹ thuật `moc` vẫn giữ trong mã và cấu hình: biến `MOC_*`, realm `moc`, lệnh
> `scripts/moc.py`, image `moc/*`, thư mục cài `/opt/moc`.

## Đóng góp và liên hệ

- **Báo lỗi, đề xuất tính năng:** mở issue theo
  [mẫu báo lỗi](https://github.com/HIT-Champion/Signet/issues/new?template=bug_report.yml) hoặc
  [mẫu đề xuất](https://github.com/HIT-Champion/Signet/issues/new?template=feature_request.yml); xem
  [mọi issue](https://github.com/HIT-Champion/Signet/issues).
- **Lịch sử thay đổi:** [`CHANGELOG.md`](CHANGELOG.md) theo Keep a Changelog; các bản phát hành ở
  [Releases](https://github.com/HIT-Champion/Signet/releases).
- **Đóng góp mã nguồn:** đọc [`CONTRIBUTING.md`](CONTRIBUTING.md) và quy trình Git
  [`docs/git_flow.md`](docs/git_flow.md) trước khi mở pull request; tuân theo
  [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
- **Lỗ hổng bảo mật:** không mở issue công khai — báo riêng tư theo [`SECURITY.md`](SECURITY.md).

| Thành viên | GitHub | Email |
|---|---|---|
| Nguyễn Huy Hoàng | [HoangTechCS-AIE](https://github.com/HoangTechCS-AIE) | <nguyenhuyhoangqbx5@gmail.com> |
| Đinh Văn Vượng | [Vanvuong2005827](https://github.com/Vanvuong2005827) | <vanvuong2005827@gmail.com> |
| Nguyễn Lê Hoài Nam | [nguyenlehoainam](https://github.com/nguyenlehoainam) | <namngyenhoai21@gmail.com> |

## Giấy phép

Phát hành theo **Apache License 2.0** — một giấy phép được OSI phê duyệt. Toàn văn: [`LICENSE`](LICENSE). Mục đích
lựa chọn giấy phép: [`NOTICE`](NOTICE).

Mọi tệp đều có thông tin bản quyền và giấy phép theo chuẩn [REUSE](https://reuse.software): tệp mã mang header
Apache-2.0 (`make license-check`), tệp không chèn được header (JSON, ảnh, PDF, tài liệu) khai trong
[`REUSE.toml`](REUSE.toml). Kiểm toàn bộ kho: `uvx --from reuse==5.0.2 reuse lint`.

Signet **điều phối** các phần mềm nguồn mở thượng nguồn ở dạng nguyên bản, không sao chép và không chỉnh sửa mã nguồn
của chúng vào kho này. Logo các dự án trong sơ đồ kiến trúc là nhãn hiệu của chủ sở hữu, chỉ dùng để nhận diện thành
phần, không thuộc giấy phép Apache-2.0 của Signet: [`docs/anh/logo/NGUON.md`](docs/anh/logo/NGUON.md).
