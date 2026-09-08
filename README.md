# DX-Lab

> Trạm thực hành Hệ điều hành Doanh nghiệp số (DX-OS) — lắp ghép từ phần mềm nguồn mở
> theo kiến trúc **Open-Core** và mô hình 4 không gian **H-P-D-I**.
>
> Sản phẩm dự thi **Olympic Tin học Sinh viên Việt Nam 2026 — nội dung Phần mềm Nguồn mở (OLP PMNM 2026)**.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)

---

## DX-Lab giải bài toán gì

Hơn 900.000 doanh nghiệp nhỏ và vừa (SME) cùng các cơ quan nhà nước Việt Nam đang chuyển
đổi số theo cách thất bại có hệ thống: mua nhiều phần mềm rời rạc trong khi quy trình và thói
quen nhân sự không đổi. Hệ quả là **ốc đảo thông tin** — dữ liệu tồn tại nhưng không chảy được
giữa các bộ phận, và không câu hỏi điều hành nào trả lời được bằng số liệu thật.

DX-Lab là một hệ thống **chạy được, cài được, miễn phí** giúp một tổ chức không có đội IT và
không có ngân sách bản quyền tự vận hành nghiệp vụ của mình trên nền số, theo lộ trình bắt buộc
`[H] → [P] → [D] → [I]`, với mục tiêu giảm tỷ lệ thao tác thủ công từ **100% xuống 10–20%**.

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

Toàn bộ công cụ dùng để dựng DX-Lab đều là phần mềm nguồn mở. Không cần bất kỳ công cụ
nguồn đóng hay tự chế nào.

## Cài đặt từ mã nguồn (Building From Source)

```bash
# 1. Lấy mã nguồn
git clone https://github.com/<TODO-org>/dx-lab.git
cd dx-lab

# 2. Cấu hình (KHÔNG sửa mã nguồn để cấu hình — mọi tham số nằm trong .env)
cp .env.example .env
$EDITOR .env          # đổi mật khẩu và cổng nếu cần

# 3. Kiểm tra môi trường
make check

# 4. Dựng và khởi động toàn bộ DX-Lab
make build
make up

# 5. Nạp dữ liệu mẫu để chạy thử
make seed
```

Mở `http://localhost` để vào cổng thông tin. Dừng hệ thống: `make down`.

DX-Lab **chạy được ngoài thư mục mã nguồn**: mọi đường dẫn đều tương đối theo biến môi trường,
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
| [`docs/architecture.md`](docs/architecture.md) | Kiến trúc H-P-D-I, bản đồ công cụ, quyết định kỹ thuật |
| [`docs/pof-checklist.md`](docs/pof-checklist.md) | Bảng tự chấm 50 điểm PoF |
| [`DEPENDENCIES.md`](DEPENDENCIES.md) | Danh mục phần mềm thượng nguồn + giấy phép |
| [`CHANGELOG.md`](CHANGELOG.md) | Lịch sử thay đổi |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Hướng dẫn đóng góp |
| [`ROADMAP.md`](ROADMAP.md) | Lộ trình phát triển |

## Báo lỗi và đóng góp

- **Báo lỗi / đề xuất tính năng**: mở issue tại <https://github.com/<TODO-org>/dx-lab/issues>
- **Đóng góp mã nguồn**: đọc [`CONTRIBUTING.md`](CONTRIBUTING.md) trước khi mở pull request
- **Quy tắc ứng xử**: [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)

## Giấy phép

Phát hành theo **Apache License 2.0** — một giấy phép được OSI phê duyệt.
Toàn văn: [`LICENSE`](LICENSE). Mục đích lựa chọn giấy phép: [`NOTICE`](NOTICE).

DX-Lab **điều phối** các phần mềm nguồn mở thượng nguồn ở dạng nguyên bản, không sao chép và
không chỉnh sửa mã nguồn của chúng vào kho này. Xem [`DEPENDENCIES.md`](DEPENDENCIES.md).

---

## English summary

**DX-Lab** is an open-source *Digital Enterprise Operating System* sandbox, assembled from
upstream open-source components under an Open-Core architecture. It targets small and
medium-sized enterprises and public agencies that have no in-house IT team and no software
budget.

The system is organised into four control spaces — **H** (people), **P** (process),
**D** (data), **I** (AI) — deployed strictly in that order: automation is only introduced once
the data layer has a single source of truth and the process layer enforces input constraints.

Built for the Vietnam National Olympiad in Informatics 2026, Open Source Software track.
Licensed under Apache-2.0. Contributions welcome — see `CONTRIBUTING.md`.
