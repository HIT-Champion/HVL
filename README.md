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
| Nhập sai, vào sổ trùng | Chặn nhập sai ngay từ form (Poka-yoke) và trong CSDL | [P] |
| Tệp đính kèm có thể chứa mã độc | Quét virus trước khi lưu | Lõi |
| Không kiểm được văn bản nhận được là thật | Văn bản phát hành có mã QR; cổng xác thực công khai, ai cũng kiểm được | Lõi + [D] |
| Hồ sơ bị sửa lén sau khi lưu | Sổ kiểm toán chuỗi băm; lưu trữ hồ sơ sang kho lạnh có băm | Lõi + [D] |
| Văn bản nhạy cảm bị lộ | Lưu mã hóa, chỉ giải mã trong bộ nhớ khi người có quyền xem | [P] |
| Lãnh đạo không biết việc nghẽn ở đâu | Dashboard điều hành từ số liệu thật | [D] |
| Tìm lại văn bản cũ mất thời gian | Tìm kiếm toàn văn; trợ lý hỏi đáp có trích dẫn số ký hiệu | [I] |

Chi tiết phạm vi, vai trò người dùng và kịch bản demo: [`docs/dac-ta-san-pham.md`](docs/dac-ta-san-pham.md).

Bài toán này đi đúng lộ trình tiến hóa `[H] → [P] → [D] → [I]` của mô hình DX-OS: có danh tính số
mới chuẩn hóa được quy trình, quy trình chuẩn mới sinh ra số liệu sạch, có số liệu sạch thì AI mới
gợi ý đúng. Mục tiêu của mô hình là giảm tỷ lệ thao tác thủ công từ **100% xuống 10–20%**.

## Đang chạy được

Lát cắt đầu tiên chạy trọn từ giao diện xuống lõi: **văn bản đến** — văn thư tải công văn lên (quét
ClamAV) → nhập thông tin, chặn trùng → vào sổ, hệ thống cấp số đến liên tiếp → lãnh đạo khoa chỉ đạo,
giao phòng chủ trì và phối hợp, đặt hạn → lãnh đạo phòng phân công → chuyên viên báo kết quả. Mỗi bước có
trong hộp việc của đúng người, hiện trên dòng thời gian văn bản và vào sổ kiểm toán chuỗi băm; tìm lại
được bằng chữ không dấu.

```
 Trình duyệt ──► APISIX :8080 ─┬─ /            → app-office (Nuxt, trang tĩnh)          Tầng 2
                (kiểm JWT,     ├─ /realms/moc/* → Keycloak (đăng nhập SSO)
                 X-Request-Id) ├─ /v1/graphql   → Hasura ─┬─ PostgreSQL (core, office)  Tầng 1
                               │                          └─ Actions → svc-workflow → Flowable (BPMN)
                               └─ /api/files, /api/search → svc-files ─ ClamAV · SeaweedFS · Meilisearch
```

| Thành phần | Vai trò | Thư mục |
|---|---|---|
| Keycloak 26 | SSO; vai trò, đơn vị, phòng đưa vào token cho Hasura | `auth/realm/` |
| Apache APISIX 3 | Cổng duy nhất mở ra ngoài: danh sách trắng đường dẫn, kiểm JWT ở biên, chặn đường quản trị, giới hạn tốc độ đăng nhập (theo IP) và API (theo phiên) | `gateway/` |
| Hasura 2 + PostgreSQL 16 | GraphQL tự sinh, quyền theo vai trò và đơn vị đến từng dòng, sổ kiểm toán chuỗi băm | `db/` |
| Flowable 8 | Quy trình BPMN xử lý văn bản đến | `processes/` |
| `svc-workflow` | Hasura Actions: vào sổ, hộp việc, hoàn thành việc; đồng bộ danh bạ Keycloak | `services/svc-workflow/` |
| `svc-files` | Tải tệp qua ClamAV vào SeaweedFS, tải xuống theo quyền, tìm kiếm Meilisearch | `services/svc-files/` |
| `app-office` | Giao diện Văn phòng điện tử (Nuxt 4, Tailwind), tiếng Việt / tiếng Anh | `apps/office/` |

Phần còn lại theo [`docs/ke-hoach-phat-trien.md`](docs/ke-hoach-phat-trien.md): văn bản đi, dựng PDF có mã QR
và cổng xác thực (Phase 2), bằng chứng 4 nguyên lý và dashboard (Phase 3), AI (Phase 4).

## Yêu cầu hệ thống

| Thành phần | Phiên bản tối thiểu | Ghi chú |
|---|---|---|
| Docker Engine | 24.0 | kèm plugin `docker compose` v2 |
| GNU Make | 4.0 | điều phối lệnh |
| Python | 3.10 | chỉ cho `make seed`, `make smoke`, `make install` (thư viện chuẩn, không cài thêm gì) |
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
| `vanthu` | Văn thư Khoa CNTT | Tiếp nhận, vào sổ; mọi văn bản đến của khoa |
| `truongkhoa` | Lãnh đạo khoa | Hộp việc chỉ đạo; mọi văn bản của khoa |
| `totruongdt` | Tổ trưởng Đào tạo | Văn bản giao cho tổ; phân công |
| `chuyenviendt`, `giamkhao` | Chuyên viên Tổ Đào tạo | Văn bản được giao cho mình |
| `vanthukt`, `truongkhoakt` | Khoa Kinh tế | Chỉ văn bản của Khoa Kinh tế |

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

## Kiểm thử

| Lệnh | Kiểm gì | Cần |
|---|---|---|
| `make test` | Test đơn vị của `svc-files`, `svc-workflow` | Python + [uv](https://github.com/astral-sh/uv) |
| `make smoke` | Đi trọn luồng văn bản đến qua cổng APISIX; chặn EICAR, chặn đường quản trị, cách ly đơn vị, giới hạn tốc độ | Hệ thống đang chạy + `make seed` |
| `make e2e` | Cùng luồng trên trình duyệt thật (Playwright, chạy trong container) | Như trên |
| `db/tests/` | 62 test schema, quyền, sổ kiểm toán trên PostgreSQL + Hasura thật | xem `db/README.md` |

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) chạy toàn bộ bảng trên cho mọi pull request: dựng hệ
thống từ mã nguồn bằng đúng các lệnh `make env` → `make up` → `make seed` → `make smoke` → `make e2e`, rồi
`make install` sang thư mục khác và chạy lại smoke từ bản cài; đồng thời quét bí mật trong lịch sử commit
(gitleaks) và lỗ hổng đã biết trong các tệp khóa phụ thuộc (OSV-Scanner).

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
