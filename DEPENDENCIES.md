# Danh mục phần mềm thượng nguồn và giấy phép

Tài liệu này làm rõ mọi thư viện, gói và phần mềm thượng nguồn mà DX-Lab phụ thuộc vào — yêu cầu
bắt buộc theo tiêu chí chấm điểm PoF #5 (*"Có thông tin làm rõ các thư viện, gói đính kèm được
sử dụng"*).

## Nguyên tắc phụ thuộc

1. **Không bundle.** Kho mã nguồn này **không** chứa bản sao mã nguồn của bất kỳ dự án nào khác.
   Mọi phần mềm thượng nguồn được nạp lúc chạy qua image Docker chính thức có ghim thẻ phiên bản,
   hoặc qua trình quản lý gói của hệ thống.
2. **Không chỉnh sửa upstream.** Mã nguồn của các dự án thượng nguồn được dùng ở dạng **nguyên
   bản**. Mọi tùy biến của DX-Lab nằm ở lớp cấu hình, plugin hoặc adapter riêng.
3. **Ưu tiên thư viện sẵn có của hệ thống** thay vì đóng gói kèm bản riêng.
4. **Kiểm tra tương thích giấy phép.** Mọi thành phần mới phải có giấy phép được OSI phê duyệt và
   tương thích với Apache-2.0 của DX-Lab.

## Công cụ dựng và vận hành

| Thành phần | Phiên bản | Giấy phép | Vai trò | Cách nạp |
|---|---|---|---|---|
| Docker Engine | ≥ 24.0 | Apache-2.0 | Đóng gói và chạy container | Cài sẵn trên máy chủ |
| Docker Compose v2 | ≥ 2.20 | Apache-2.0 | Điều phối đa dịch vụ | Plugin của Docker |
| GNU Make | ≥ 4.0 | GPL-3.0+ | Điều phối lệnh (công cụ dựng, không liên kết vào sản phẩm) | Gói hệ thống |
| Git | ≥ 2.30 | GPL-2.0 | Quản lý mã nguồn, sinh gói phát hành | Gói hệ thống |

> **Ghi chú tương thích:** Make và Git là *công cụ dựng*, được gọi như tiến trình độc lập và không
> liên kết vào sản phẩm, nên giấy phép GPL của chúng không lan sang DX-Lab. Cả hai đều là phần
> mềm nguồn mở — DX-Lab không dùng bất kỳ công cụ nguồn đóng hay tự chế nào để dựng
> (tiêu chí PoF #4).

## Thành phần theo trục H-P-D-I

Bảng dưới đây được điền dần trong quá trình khảo sát (xem `docs/architecture.md`).
Mỗi dòng phải ghi rõ: tên dự án, phiên bản ghim, giấy phép, vai trò trong DX-Lab, và cách nạp.

### [H] Không gian Nhân sự

| Thành phần | Phiên bản | Giấy phép | Vai trò | Cách nạp |
|---|---|---|---|---|
| _chưa chốt_ | | | Quản trị định danh tập trung (SSO) | |
| _chưa chốt_ | | | Lưu trữ đám mây nội bộ | |
| _chưa chốt_ | | | Hệ quản trị tri thức (wiki/CMS) | |
| _chưa chốt_ | | | Truyền thông nội bộ tức thời | |

### [P] Không gian Quy trình

| Thành phần | Phiên bản | Giấy phép | Vai trò | Cách nạp |
|---|---|---|---|---|
| _chưa chốt_ | | | Nền tảng low-code dựng biểu mẫu | |
| _chưa chốt_ | | | Tự động hóa luồng việc / iPaaS | |

### [D] Không gian Dữ liệu

| Thành phần | Phiên bản | Giấy phép | Vai trò | Cách nạp |
|---|---|---|---|---|
| PostgreSQL | 16-alpine | PostgreSQL License | CSDL quan hệ nền cho nguồn sự thật duy nhất | Image chính thức |
| _chưa chốt_ | | | Nền tảng BI / dashboard | |

### [I] Không gian Trí tuệ Nhân tạo

| Thành phần | Phiên bản | Giấy phép | Vai trò | Cách nạp |
|---|---|---|---|---|
| _chưa chốt_ | | | Cơ sở dữ liệu véc-tơ | |
| _chưa chốt_ | | | Khung phát triển LLM / RAG | |
| _chưa chốt_ | | | Khung tác tử tự hành | |

## Kiểm tra tương thích giấy phép

Giấy phép được chấp nhận trong DX-Lab (tương thích với Apache-2.0 ở vai trò dịch vụ độc lập):

- ✅ Apache-2.0, MIT, BSD-2/3-Clause, PostgreSQL License, ISC, MPL-2.0
- ⚠️ GPL-2.0/3.0, AGPL-3.0 — chấp nhận được khi chạy như **dịch vụ độc lập** giao tiếp qua mạng,
  không liên kết mã. Phải ghi chú rõ ràng ở cột vai trò.
- ❌ Mọi giấy phép không được OSI phê duyệt, giấy phép "source-available" (BUSL, SSPL, Elastic
  License), hoặc bất kỳ thành phần nguồn đóng nào.
