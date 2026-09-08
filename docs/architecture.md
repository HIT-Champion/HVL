# Kiến trúc DX-Lab

> Tài liệu này ghi lại kiến trúc hệ thống, bản đồ công cụ nguồn mở, và các quyết định kỹ thuật
> kèm lý do. Trạng thái hiện tại: **đang khảo sát công cụ** (giai đoạn 1 của `ROADMAP.md`).

## 1. Nguyên tắc kiến trúc

### 1.1. Open-Core: điều phối, không viết lại

DX-Lab **không** viết lại các phần mềm đã có bản nguồn mở trưởng thành. Nó là **lớp điều phối**
(orchestration layer) gắn kết chúng thành một hệ thống vận hành thống nhất. Giá trị của dự án
nằm ở *lớp keo* — cách các thành phần được nối, chuẩn hóa và đồng bộ — không nằm ở bản thân
các thành phần.

Hệ quả bắt buộc, áp dụng không ngoại lệ:

| Được phép | Không được phép |
|---|---|
| Kéo image thượng nguồn có ghim thẻ phiên bản | Sao chép cây mã upstream vào kho này |
| Ghi đè cấu hình qua `.env` và tệp cấu hình riêng | Sửa trực tiếp mã nguồn upstream |
| Viết plugin/adapter theo cơ chế mở rộng chính thức | Fork rồi vá vào bản fork |
| Gửi patch lên chính dự án thượng nguồn | Giữ bản vá riêng không công bố |

Lý do kỹ thuật: giữ khả năng nâng cấp upstream. Lý do dự thi: tiêu chí PoF #5 trừ 5 điểm cho mỗi
vi phạm bundling và chỉnh sửa gói đính kèm.

### 1.2. Tiến hóa tuyến tính

Bốn không gian triển khai theo đúng thứ tự `[H] → [P] → [D] → [I]`. Đây là ràng buộc **nhân quả**,
không phải sở thích trình bày:

```
[H] không chuẩn hóa  →  dữ liệu bẩn ngay từ điểm nhập
[P] không ràng buộc  →  không có sự kiện có cấu trúc để [D] thu thập
[D] không hợp nhất   →  [I] đọc dữ liệu mâu thuẫn  →  ảo giác dữ liệu
```

Mỗi profile trong `docker-compose.yml` tương ứng một trục, cho phép dựng và nghiệm thu từng
tầng độc lập trước khi đi tiếp.

### 1.3. Ràng buộc tài nguyên

Người dùng đích là SME không có đội IT và không có ngân sách phần mềm. Mọi quyết định kỹ thuật
phải qua được ba câu hỏi:

1. Chạy được trên **một máy chủ 8 GB RAM** không?
2. Người **không chuyên CNTT** cài được trong dưới một giờ không?
3. Có phụ thuộc dịch vụ **trả phí bắt buộc** nào không?

Nếu câu trả lời là *không / không / có* thì phương án bị loại, dù về mặt kỹ thuật nó tốt hơn.

## 2. Sơ đồ tổng thể

```
┌──────────────────────────────────────────────────────────────────────┐
│  [H] KHÔNG GIAN NHÂN SỰ                                              │
│  SSO  ·  Lưu trữ P.A.R.A  ·  Wiki  ·  Truyền thông  ·  Cổng nội bộ    │
│  → Một lần đăng nhập, một điểm vào, dữ liệu đúng ngay từ đầu vào     │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ danh tính, tài liệu, con người
┌───────────────────────────────▼──────────────────────────────────────┐
│  [P] KHÔNG GIAN QUY TRÌNH                                            │
│  Low-code biểu mẫu  ·  Workflow automation  ·  Trục tích hợp API     │
│  Ràng buộc Poka-yoke chặn dữ liệu sai tại điểm nhập                  │
│  → Phát ra SỰ KIỆN CÓ CẤU TRÚC cho mỗi bước nghiệp vụ                │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ luồng sự kiện
┌───────────────────────────────▼──────────────────────────────────────┐
│  [D] KHÔNG GIAN DỮ LIỆU                                              │
│  Thu thập → Làm sạch → Đồng bộ  ·  Từ điển dữ liệu thống nhất        │
│  NGUỒN SỰ THẬT DUY NHẤT  ·  Dashboard BI thời gian thực              │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ dữ liệu đã chuẩn hóa
┌───────────────────────────────▼──────────────────────────────────────┐
│  [I] KHÔNG GIAN TRÍ TUỆ NHÂN TẠO                                     │
│  Vector DB  ·  RAG  ·  Tác tử tự hành                                │
│  Đọc [D] · Lắng nghe sự kiện [P] · Tự thực thi hành động             │
│  Rào chắn Human-in-the-loop cho hành động rủi ro cao                 │
└──────────────────────────────────────────────────────────────────────┘
```

## 3. Bản đồ công cụ

> **Trạng thái: chưa chốt.** Bảng dưới đây liệt kê các *khe cắm chức năng* cần lấp. Việc khảo sát
> và chốt công cụ là hạng mục kế tiếp; mỗi lựa chọn phải kèm bản ghi quyết định ở mục 4.

### [H] Không gian Nhân sự

| Khe cắm | Chức năng cần có | Tiêu chí chọn | Ứng viên |
|---|---|---|---|
| Định danh tập trung | SSO, OIDC/SAML, quản lý người dùng và vai trò | Nhẹ, tích hợp được với mọi thành phần còn lại | _đang khảo sát_ |
| Lưu trữ nội bộ | Chia sẻ tệp, phân quyền theo thư mục, áp cấu trúc P.A.R.A | Có API, có webhook để [P] bắt sự kiện | _đang khảo sát_ |
| Quản trị tri thức | Wiki/CMS làm kho tài liệu — cũng là nguồn nạp cho RAG ở [I] | Xuất được Markdown/API để [I] lập chỉ mục | _đang khảo sát_ |
| Truyền thông | Chat nội bộ, kênh theo phòng ban, nhận thông báo từ [P] | Có webhook nhận thông báo tự động | _đang khảo sát_ |

### [P] Không gian Quy trình

| Khe cắm | Chức năng cần có | Tiêu chí chọn | Ứng viên |
|---|---|---|---|
| Low-code biểu mẫu | Dựng form nhập liệu, CSDL quan hệ, ràng buộc trường | Ràng buộc validation mạnh (Poka-yoke), có webhook | _đang khảo sát_ |
| Tự động hóa luồng việc | Trigger theo sự kiện, nối API giữa các dịch vụ [H] | Nhiều connector sẵn, chạy được offline | _đang khảo sát_ |

### [D] Không gian Dữ liệu

| Khe cắm | Chức năng cần có | Tiêu chí chọn | Ứng viên |
|---|---|---|---|
| CSDL nghiệp vụ | Lưu trữ thực thể lõi đã chuẩn hóa | Ổn định, phổ biến, dễ sao lưu | **PostgreSQL 16** (đã chốt) |
| Đồng bộ & làm sạch | Thu thập sự kiện từ [P], khử trùng lặp, áp từ điển dữ liệu | Khai báo được bằng cấu hình, không cần viết nhiều mã | _đang khảo sát_ |
| BI / Dashboard | Trực quan hóa thời gian thực cho cấp quản lý | Kết nối trực tiếp PostgreSQL, nhúng được vào cổng [H] | _đang khảo sát_ |

### [I] Không gian Trí tuệ Nhân tạo

| Khe cắm | Chức năng cần có | Tiêu chí chọn | Ứng viên |
|---|---|---|---|
| Cơ sở dữ liệu véc-tơ | Lưu embedding tài liệu từ wiki và kho lưu trữ [H] | Chạy được trong 8 GB RAM | _đang khảo sát_ |
| Khung RAG | Truy xuất tri thức, trích dẫn nguồn | Chạy được với LLM cục bộ lẫn API ngoài | _đang khảo sát_ |
| Tác tử tự hành | Lắng nghe sự kiện [P], quyết định, gọi hành động | Có cơ chế phê duyệt của con người | _đang khảo sát_ |

## 4. Bản ghi quyết định kiến trúc

Mỗi lựa chọn công cụ được ghi lại theo mẫu: *bối cảnh → phương án đã cân nhắc → quyết định → hệ quả*.

### QĐ-001: Chọn Apache-2.0 làm giấy phép dự án

- **Bối cảnh:** DX-Lab lắp ghép nhiều phần mềm thượng nguồn có giấy phép khác nhau. Tiêu chí chấm
  điểm PoF #2 trừ 5 điểm nếu *"mã nguồn tự thân chứa sự không tương thích của các giấy phép"*.
- **Phương án:** MIT (đơn giản nhất) · Apache-2.0 (permissive, có điều khoản sáng chế) ·
  GPL-3.0 / AGPL-3.0 (copyleft mạnh).
- **Quyết định:** Apache-2.0.
- **Lý do:** permissive nên gần như không thể phát sinh xung đột với giấy phép của các thành phần
  thượng nguồn; có điều khoản cấp phép sáng chế rõ ràng (MIT không có); có quy ước header chuẩn
  cho từng tệp — đúng thứ tiêu chí PoF #2 đòi hỏi. Copyleft mạnh bị loại vì rủi ro tương thích khi
  liên kết với thành phần permissive, và vì cản trở SME tích hợp vào hệ thống sẵn có của họ.
- **Hệ quả:** mọi tệp mã phải mang header Apache-2.0 (CI cưỡng chế); thành phần mang giấy phép
  copyleft chỉ được dùng ở dạng **dịch vụ độc lập giao tiếp qua mạng**, không liên kết mã.

### QĐ-002: Chọn PostgreSQL làm CSDL nền

- **Bối cảnh:** Trục [D] cần một CSDL quan hệ làm nơi trú của nguồn sự thật duy nhất; các thành
  phần ở [H] và [P] cũng cần CSDL riêng.
- **Quyết định:** PostgreSQL 16 (image chính thức `postgres:16-alpine`), dùng chung cho mọi thành
  phần, tách bằng schema hoặc database riêng.
- **Lý do:** hầu hết ứng viên ở cả bốn trục đều hỗ trợ PostgreSQL; gộp về một hệ quản trị giúp
  giảm dung lượng RAM — yếu tố quyết định với ràng buộc 8 GB; giấy phép PostgreSQL License
  (permissive) tương thích Apache-2.0; sao lưu và phục hồi đơn giản cho SME không có DBA.
- **Hệ quả:** PostgreSQL trở thành điểm lỗi đơn (single point of failure) — tài liệu vận hành ở
  giai đoạn 5 phải có quy trình sao lưu và phục hồi rõ ràng.

### QĐ-003: Điều phối bằng Docker Compose, không dùng Kubernetes

- **Bối cảnh:** Cần điều phối khoảng 8–12 dịch vụ.
- **Quyết định:** Docker Compose v2 với profile theo trục.
- **Lý do:** SME không có đội vận hành Kubernetes; Compose cài trong một lệnh, đọc hiểu được bởi
  người không chuyên; profile ánh xạ trực tiếp sang bốn không gian H-P-D-I, giúp nghiệm thu từng
  tầng theo đúng lộ trình tuyến tính.
- **Hệ quả:** không có tự động mở rộng theo tải và không có khả năng chịu lỗi đa node — chấp nhận
  được với quy mô một SME; ghi rõ giới hạn này trong tài liệu vận hành.
