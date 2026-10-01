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

## Kiến trúc 4 không gian

| Trục | Không gian | Vai trò | Trạng thái |
|------|-----------|---------|-----------|
| **[H]** | Nhân sự | Môi trường làm việc số khép kín: định danh tập trung (SSO), lưu trữ chuẩn P.A.R.A, cổng thông tin nội bộ | 🚧 đang khảo sát |
| **[P]** | Quy trình | Tự động hóa luồng việc hướng sự kiện, ràng buộc Poka-yoke chống nhập sai | 🚧 đang khảo sát |
| **[D]** | Dữ liệu | Hợp nhất thành Nguồn sự thật duy nhất, dashboard thời gian thực | 🚧 đang khảo sát |
| **[I]** | Trí tuệ nhân tạo | Tác tử tự hành (Agentic AI) đọc [D], bắt sự kiện từ [P], tự thực thi | 🚧 đang khảo sát |

Nguyên tắc bất di bất dịch: **tiến hóa tuyến tính**. Không triển khai [I] khi [D] chưa có nguồn sự
thật duy nhất và [P] chưa có ràng buộc kỹ thuật — nếu không sẽ rơi vào *Garbage In, Garbage Out*.

Chi tiết kiến trúc và bản đồ công cụ: [`docs/architecture.md`](docs/architecture.md).

## Yêu cầu hệ thống

| Thành phần | Phiên bản tối thiểu | Ghi chú |
|---|---|---|
| Docker Engine | 24.0 | kèm plugin `docker compose` v2 |
| GNU Make | 4.0 | điều phối lệnh |
| Git | 2.30 | |
| RAM | 8 GB | mục tiêu: chạy được trên máy văn phòng phổ thông |
| Đĩa trống | 20 GB | |

Toàn bộ công cụ dùng để dựng Mộc đều là phần mềm nguồn mở. Không cần bất kỳ công cụ
nguồn đóng hay tự chế nào.

## Cài đặt từ mã nguồn (Building From Source)

```bash
# 1. Lấy mã nguồn
git clone https://github.com/HIT-Champion/HVL.git
cd HVL

# 2. Cấu hình (KHÔNG sửa mã nguồn để cấu hình — mọi tham số nằm trong .env)
cp .env.example .env
$EDITOR .env          # đổi mật khẩu và cổng nếu cần

# 3. Kiểm tra môi trường
make check

# 4. Dựng và khởi động toàn bộ Mộc
make build
make up

# 5. Nạp dữ liệu mẫu để chạy thử
make seed
```

Mở `http://localhost` để vào cổng thông tin. Dừng hệ thống: `make down`.

Mộc **chạy được ngoài thư mục mã nguồn**: mọi đường dẫn đều tương đối theo biến môi trường,
không phụ thuộc vị trí thư mục cài đặt.

Xem toàn bộ lệnh: `make help`.

## Khởi động từng trục riêng lẻ

Mỗi không gian là một Docker Compose profile độc lập, cho phép triển khai theo đúng lộ trình tuyến tính:

```bash
make up-h      # chỉ [H] — nền tảng nhân sự
make up-p      # [H] + [P]
make up-d      # [H] + [P] + [D]
make up        # đủ 4 trục
```

## Tài liệu

| Tài liệu | Nội dung |
|---|---|
| [`docs/olp-2026-brief.md`](docs/olp-2026-brief.md) | Tóm tắt chủ đề DX-OS + thể lệ + tiêu chí chấm OLP 2026 |
| [`docs/olp-2026-de-thi.md`](docs/olp-2026-de-thi.md) | Phân tích đề thi chính thức, kiểm tra giấy phép bảng công nghệ tham chiếu |
| [`docs/dac-ta-san-pham.md`](docs/dac-ta-san-pham.md) | Đặc tả sản phẩm: bài toán, người dùng, chức năng, kịch bản demo |
| [`docs/ke-hoach-phat-trien.md`](docs/ke-hoach-phat-trien.md) | Kế hoạch phát triển theo phase, phân công, rủi ro |
| [`docs/git_flow.md`](docs/git_flow.md) | Quy trình Git: nhánh, commit, pull request, phát hành |
| [`docs/architecture.md`](docs/architecture.md) | Kiến trúc H-P-D-I, bản đồ công cụ, quyết định kỹ thuật |
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
