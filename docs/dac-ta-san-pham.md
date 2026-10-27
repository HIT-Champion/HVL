# Đặc tả sản phẩm Signet — Văn phòng điện tử trên DX-OS Open-Core

> Lập ngày 15/10/2026. Thay hướng "luồng phê duyệt đề xuất mua sắm / tạm ứng / nghỉ phép" của kế hoạch
> ngày 05/10.
> Liên quan: phân tích đề [`olp-2026-de-thi.md`](du-thi/olp-2026-de-thi.md) · kế hoạch theo phase
> [`ke-hoach-phat-trien.md`](du-thi/ke-hoach-phat-trien.md) · mô hình dữ liệu [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md).
> Mã chức năng (F2.x, F3.x, F4.x) dùng chung với kế hoạch. Hai tài liệu lệch nhau về **lịch** thì kế
> hoạch đúng; lệch về **phạm vi sản phẩm** thì tài liệu này đúng.

---

## 0. Tóm tắt

Signet là một lõi **DX-OS Open-Core** (Tầng 1, không giao diện) cùng hai ứng dụng Tầng 2 chạy trên lõi.

**Lõi** cung cấp 4 dịch vụ đề bắt buộc — định danh, cổng API, dữ liệu có cấu trúc và phi cấu trúc,
quy trình — và một lớp **tin cậy** dùng chung: lõi "đóng dấu" lên mọi thứ đi qua nó.

- **Biết ai đã làm:** mọi lời gọi mang danh tính SSO, kể cả tác tử AI.
- **Sạch:** tệp được quét mã độc trước khi lưu.
- **Không sửa lén được:** mọi thay đổi vào sổ kiểm toán chuỗi băm (F2.12).
- **Kiểm chứng được từ bên ngoài:** tệp phát hành mang mã xác thực và SHA-256, tra qua API xác thực
  công khai (F2.13).

Ứng dụng nào cắm vào lõi cũng có sẵn lớp này. Cả bốn ý đều là Must — SSO và quét mã độc làm ở Phase 1,
sổ kiểm toán và API xác thực ở Phase 2 (§4.1) — nên không nằm trong danh sách được cắt khi trễ. Đây là
điểm khác biệt chính của sản phẩm, vì bộ thành phần lõi (Keycloak, APISIX, PostgreSQL, Flowable) thì
nhiều đội dùng giống nhau (§1.2).

Đề lấy lõi làm chủ đề và gọi ứng dụng là "minh họa", nên khi trình bày kể lõi trước, ứng dụng sau. Nhưng
ứng dụng là bắt buộc (R7), và lõi không có giao diện nên giám khảo chỉ thấy lõi qua ứng dụng: các tiêu chí
chạy trình diễn, sử dụng thân thiện, thu hút cộng đồng đều chấm trên thứ người dùng chạm vào. Ứng dụng
không được làm sơ sài.

**Hai ứng dụng** chứng minh lõi:

- **Văn phòng điện tử** (`apps/office`, không gian [P]): quản lý văn bản và điều hành theo
  Nghị định 30/2020/NĐ-CP — tiếp nhận công văn đến, vào sổ, chỉ đạo, giao xử lý; soạn, trình, duyệt,
  cấp số và phát hành công văn đi; lập hồ sơ và nộp lưu.
- **Cổng xác thực văn bản** (`apps/verify`, công khai): ai cầm một văn bản do hệ thống phát hành cũng
  quét được mã QR, hoặc thả tệp PDF vào, để biết văn bản là thật và chưa bị sửa.

Đơn vị chạy thử: văn thư văn phòng khoa (đang liên hệ). Dữ liệu mẫu: công văn, thông báo mà trường đã
công bố công khai.

---

## 1. Vì sao chọn hướng này

### 1.1. Đọc lại đề: ranh giới Tầng 2 và Tầng 3

- Đề bắt buộc *"ít nhất một ứng dụng minh họa giao diện nằm trong không gian H-P-D-I ở **Tầng 2**"* (R7).
- Tầng 2 được định nghĩa là *"môi trường giao diện người dùng cuối và hệ thống các **cổng dịch vụ
  nghiệp vụ dùng chung**"* — năng lực quản trị mà tổ chức nào cũng cần. Không gian [P] nêu đích danh
  *"Văn phòng điện tử (e-Office)"*.
- Ứng dụng chuyên ngành thuộc **Tầng 3**: hàng hóa (OMS, WMS, POS, TMS), dự án (PSA, Timesheet),
  khách hàng (eKYC, LMS, EMR, CRM), tài sản và không gian (MES/SCADA, BMS, Smart City IoT).

Hệ quả: một ứng dụng quản lý thiết bị, kho, bán hàng hay CRM dễ bị xếp vào Tầng 3. Khi đó đội có thể bị
coi là thiếu R7, và theo ghi chú ở tiêu chí PoF #2 ("giải quyết đúng đầu bài") có thể mất điểm cả phần PoF.

### 1.2. Các đội khác đang làm gì

Kho mã OLP 2026 công khai trên GitHub, tra ngày 15/10/2026 (cùng 2 kho tra ngày 09/09 ở
[`nghien-cuu/nghien-cuu-chu-de-2026.md`](du-thi/nghien-cuu/nghien-cuu-chu-de-2026.md) §5.5):

| Kho | Ứng dụng | Ghi chú |
|---|---|---|
| [HaUI-ImplSolution/DX-OS](https://github.com/HaUI-ImplSolution/DX-OS) | DX-Farm (hợp tác xã trồng lúa) + **"DX-Lab: trạm vận hành CNTT của khoa"** (báo sự cố, mượn thiết bị, đặt phòng máy) | Quảng bá "một lõi, nhiều ứng dụng"; **trùng tên DX-Lab** |
| [hieunofun/AI-Powered-DX-OS](https://github.com/hieunofun/AI-Powered-DX-OS) | Mua sắm → nhận hàng → đối chiếu hóa đơn 3 chiều | Keycloak, APISIX, Flowable |
| [lexuanbao258-collab/dxos-open-core](https://github.com/lexuanbao258-collab/dxos-open-core) | Cổng yêu cầu dịch vụ nội bộ: gửi yêu cầu, giao việc, phê duyệt | Spring Boot |
| [EngLandLee/FreshMesh-DXOS](https://github.com/EngLandLee/FreshMesh-DXOS) | Điều chuyển hàng tươi giữa các mini-mart | Keycloak, APISIX, Flowable |
| [TheAnhhZ/metrace](https://github.com/TheAnhhZ/metrace) | Truy xuất suất ăn bếp ăn tập thể, khóa lô khi thu hồi | Lõi gần giống đội: Keycloak, APISIX, PostgreSQL, SeaweedFS, Flowable |
| [giabuh/dx-osd](https://github.com/giabuh/dx-osd) | Khách hàng tiềm năng → CRM | Chatwoot + Frappe CRM |
| [truong-newbie/PMNM_2026_DX_FSM](https://github.com/truong-newbie/PMNM_2026_DX_FSM) | Quản lý dịch vụ hiện trường | Dùng n8n (không phải OSI) |
| [gagaduy/OpenDXOS](https://github.com/gagaduy/OpenDXOS) | Thương mại số + đa tác tử | — |
| [OpenVie/OpenVie](https://github.com/OpenVie/OpenVie) | RAG tiếng Việt trên tài liệu nội bộ | — |
| `toilact/OptiMill-DX` (09/09) | Xưởng cơ khí gia công theo đơn | Tự viết, không lắp nền tảng |

Rút ra:

- Phần lớn các đội chọn **một ngành cụ thể** — tức nằm ở vùng Tầng 3 của đề.
- Bộ lõi Keycloak + APISIX + PostgreSQL + Flowable phổ biến → tính nguyên gốc không đến từ việc chọn stack.
- Hướng "phòng máy / phòng lab" và điểm nhấn "một lõi, hai ứng dụng" **đã có đội làm**.
- "Cổng yêu cầu, phê duyệt nội bộ" trùng một phần với 2 đội.
- **Chưa thấy đội nào** làm quản lý văn bản đến/đi, cổng xác thực văn bản hay lưu trữ chống sửa xóa.

### 1.3. Các phương án đã cân nhắc

| | Phê duyệt đề xuất (kế hoạch 05/10) | **Quản lý văn bản (chọn)** | Cổng giám sát tác tử AI | Vận hành phòng máy |
|---|---|---|---|---|
| Đúng Tầng 2 | Có | **Có** | Có (đề nêu trong [I]) | Dễ bị xếp Tầng 3 |
| Nguyên gốc | Trung bình — trùng 2 đội | **Cao** | Rất cao | Thấp — đã có đội làm |
| Người dùng thật | Khá | **Tốt** — văn thư khoa, công văn công khai | Yếu | Tốt |
| Màn demo | Khá | **Rất tốt** — giám khảo tự quét QR | Tốt nếu mô hình chạy ổn | Khá |
| Rủi ro kỹ thuật | Thấp | Trung bình — OCR, dựng PDF | Cao — LLM trên CPU | Thấp |
| Chi phí đổi so với 05/10 | 0 | Thấp — lõi giữ nguyên | Cao | Thấp |

Ý hay nhất của hướng "giám sát tác tử" được giữ lại trong sản phẩm: tác tử có danh tính riêng, mọi hành
động vào sổ kiểm toán, người thật quyết định (F4.3).

---

## 2. Bài toán

Ở khoa, trường và các cơ quan nhỏ:

- Công văn đến bằng giấy hoặc bản scan gửi qua email, Zalo. Văn thư ghi sổ tay hoặc Excel; lãnh đạo bút
  phê trên giấy rồi chuyển tay.
- Không ai biết văn bản đang nằm ở bàn ai, đã quá hạn giải quyết chưa.
- Tìm lại một công văn cũ mất nhiều thời gian.
- Văn bản điện tử nhận được không kiểm tra được là thật hay bị sửa — trong khi NĐ 30 (Điều 21) yêu cầu
  văn thư kiểm tra tính xác thực và toàn vẹn của văn bản điện tử đến.
- Phần mềm quản lý văn bản phổ biến là sản phẩm đóng (VNPT iOffice, E-OFFICE của EVN…): dữ liệu văn bản
  của cơ quan nằm trong hệ thống của nhà cung cấp. Bản nguồn mở duy nhất tìm thấy (DDOC trên Drupal,
  công bố 2013) không còn thấy hoạt động.

| Vấn đề | Giải bằng | Không gian / cụm |
|---|---|---|
| Văn bản thất lạc, không biết đang ở đâu | Vào sổ, luồng xử lý BPMN, hộp việc, dòng thời gian | [P] · ⑤ |
| Quá hạn mà không ai nhắc | Hạn giải quyết theo từng việc, timer nhắc rồi leo thang; văn bản khẩn lên đầu | [P] · ⑤ ⑦ |
| Nhập sai, vào sổ trùng | Poka-yoke 3 lớp; chặn trùng cùng cơ quan + số ký hiệu + ngày | [P] · ③ |
| Tệp đính kèm chứa mã độc | Quét virus trước khi lưu | Lõi · ① |
| Khó tìm lại văn bản cũ | Tìm kiếm toàn văn; trợ lý hỏi đáp có trích dẫn | [I] · ④ |
| Không kiểm được văn bản là thật | PDF phát hành có mã QR + SHA-256; cổng xác thực công khai | [D] kho lạnh · ⑥ |
| Hồ sơ bị sửa lén sau khi lưu | Sổ kiểm toán chuỗi băm, neo ra ngoài CSDL; gói lưu trữ có băm | [D] · ⑥ |
| Văn bản nhạy cảm bị lộ | Lưu mã hóa, chỉ giải mã trong bộ nhớ khi người có quyền xem | [P] · ① |
| Lãnh đạo không biết điểm nghẽn | Dashboard: quá hạn theo phòng, thời gian xử lý | [D] |
| Lệ thuộc nhà cung cấp | Nguồn mở, tự cài, lõi tái dùng cho ứng dụng khác | Toàn bộ |

### 2.1. Căn cứ pháp lý

Trích theo bản đăng trên hethongphapluat.com và thuvienphapluat.vn — **đối chiếu lại với văn bản gốc
trước khi đưa vào slide**.

| Văn bản | Nội dung dùng trong sản phẩm |
|---|---|
| NĐ 30/2020/NĐ-CP, Điều 4 | Văn bản đi, đến phải đăng ký, phát hành hoặc chuyển giao trong ngày, chậm nhất ngày làm việc tiếp theo; mức độ khẩn: Hỏa tốc, Thượng khẩn, Khẩn |
| Điều 15 | Số văn bản liên tiếp từ 01 (ngày 01/01) đến 31/12; số và ký hiệu là duy nhất trong năm |
| Điều 16, 18 | Đăng ký văn bản đi bằng sổ hoặc bằng hệ thống (đăng ký bằng hệ thống thì in sổ ra giấy đủ các trường theo mẫu, ký nhận, đóng sổ); phát hành trong ngày ký |
| Điều 21, 22 | Văn thư kiểm tra tính xác thực, toàn vẹn của văn bản điện tử đến; số đến liên tiếp theo thứ tự tiếp nhận trong năm; đăng ký bằng hệ thống thì cũng in sổ ra giấy như văn bản đi |
| Phụ lục IV | Mẫu sổ đăng ký văn bản đi (10 cột: số ký hiệu, ngày, tên loại và trích yếu, người ký, nơi nhận, đơn vị và người nhận bản lưu, số lượng bản, ngày chuyển, ký nhận, ghi chú) và văn bản đến (9 cột: ngày đến, số đến, tác giả, số ký hiệu, ngày, tên loại và trích yếu, đơn vị hoặc người nhận, ký nhận, ghi chú) — F2.8 in đúng các cột này |
| Điều 23, 24 | Người có thẩm quyền ghi ý kiến chỉ đạo, xác định đơn vị/cá nhân chủ trì, phối hợp và thời hạn giải quyết; văn bản khẩn giải quyết ngay |
| Điều 30, 31 | Nộp lưu hồ sơ vào Lưu trữ cơ quan trong 01 năm kể từ khi công việc kết thúc |
| Luật Lưu trữ 2024 (33/2024/QH15, hiệu lực 01/7/2025) | Tài liệu lưu trữ số có giá trị pháp lý như thông điệp dữ liệu |
| Luật Bảo vệ bí mật nhà nước 2018, Điều 5 khoản 5 | **Cấm** soạn thảo, lưu giữ tài liệu bí mật nhà nước trên máy tính đã hoặc đang kết nối Internet → sản phẩm **không** quản lý văn bản mật |
| QCVN 102:2016/BTTTT (sửa đổi 1:2022) | Gói tin edXML để liên thông văn bản giữa các hệ thống → **định hướng**, không làm trong cuộc thi |

---

## 3. Người dùng và vai trò

| Vai trò | Mã vai trò (Keycloak) | Ở khoa | Việc chính |
|---|---|---|---|
| Văn thư | `clerk` | Cán bộ văn phòng khoa | Tiếp nhận, vào sổ văn bản đến; cấp số, phát hành văn bản đi; lập sổ |
| Chuyên viên | `staff` | Giảng viên, cán bộ | Xử lý văn bản được giao; soạn dự thảo văn bản đi |
| Lãnh đạo phòng | `manager` | Trưởng bộ môn, trưởng phòng | Phân công trong phòng; duyệt dự thảo của phòng |
| Lãnh đạo đơn vị | `director` | Trưởng, phó khoa | Ghi ý kiến chỉ đạo, giao chủ trì / phối hợp; duyệt và ký văn bản đi |
| Quản trị | `tenant_admin` | Cán bộ CNTT | Phòng ban, người dùng, sổ, mẫu văn bản |
| Người ngoài | không đăng nhập | Sinh viên, đối tác | Kiểm tra văn bản trên cổng xác thực |
| Tác tử | tài khoản dịch vụ | — | Đọc văn bản đến, gợi ý giao việc, soạn nháp báo cáo sự cố; **không tự quyết** |

TOTP bắt buộc cho `clerk`, `manager`, `director`. Tài khoản dùng thử cho giám khảo ở vai trò `staff`.

---

## 4. Chức năng

### 4.1. Must — Phase 2 (`v0.2.0`)

| Mã | Chức năng |
|---|---|
| F2.1 | Đăng nhập SSO, hồ sơ cá nhân, tài khoản dùng thử cho giám khảo |
| F2.2 | **Tiếp nhận văn bản đến**: tải PDF/ảnh → quét virus → nhập số ký hiệu, ngày ban hành, cơ quan ban hành, loại, trích yếu, độ khẩn, hạn. Poka-yoke 3 lớp; chặn vào sổ trùng |
| F2.3 | **Vào sổ và xử lý văn bản đến** (BPMN `van-ban-den`): cấp số đến liên tiếp theo năm → lãnh đạo đơn vị chỉ đạo, giao chủ trì / phối hợp, hạn → lãnh đạo phòng phân công → chuyên viên xử lý, báo kết quả. Timer nhắc, leo thang; văn bản khẩn lên đầu hộp việc |
| F2.4 | **Soạn và phát hành văn bản đi** (BPMN `van-ban-di`): dự thảo từ mẫu đúng thể thức (công văn, thông báo) hoặc tải tệp, giữ các phiên bản → trình → duyệt hoặc trả lại → văn thư cấp số → hệ thống dựng PDF có số, ký hiệu, ngày, **mã QR và SHA-256**. Có thể gắn "trả lời văn bản đến số …" |
| F2.5 | Hộp việc + thông báo realtime theo từng người |
| F2.6 | Dòng thời gian văn bản: ai nhận, ai chỉ đạo, ai xử lý, ý kiến, lúc nào |
| F2.7 | Tìm kiếm theo số ký hiệu, trích yếu, cơ quan ban hành và nội dung PDF có lớp chữ |
| F2.8 | Sổ đăng ký văn bản đến / đi theo năm; xuất PDF để in (NĐ 30, Điều 16, 22, Phụ lục IV) |
| F2.9 | Khóa i18n Việt / Anh từ ngày đầu |
| F2.10 | `make seed` qua API: ~50 văn bản ở nhiều trạng thái, văn bản đến lấy từ công văn đã công bố công khai |
| F2.11 | Cộng đồng: đơn vị chạy thử dùng bản online, README tiếng Anh, "good first issue" |
| F2.12 | **Sổ kiểm toán chuỗi băm** (trước là F3.5): mọi thay đổi vào chuỗi băm SHA-256; `dxos audit verify` chỉ ra dòng bị sửa; neo hash đầu chuỗi ra ngoài CSDL. Hash của mọi văn bản phát hành nằm trong chuỗi |
| F2.13 | **Cổng xác thực văn bản** (trước là F3.6, `apps/verify`): quét QR hoặc nhập mã → số ký hiệu, ngày, cơ quan ban hành, trích yếu (nếu văn bản được đánh dấu công khai) và kết quả khớp. Thả tệp PDF vào → **trình duyệt tự tính SHA-256, không tải tệp lên** → so khớp. Văn thư dùng cùng chức năng khi tiếp nhận văn bản đến từ một hệ thống Signet khác (NĐ 30, Điều 21) |

### 4.2. Should — Phase 3 (`v0.5.0`)

Chức năng riêng của sản phẩm; các màn chứng minh 4 nguyên lý của lõi nằm cùng bảng Phase 3 trong kế hoạch.
Mã F3.6 bỏ trống vì đã lên Must (F2.13).

| Mã | Chức năng |
|---|---|
| F3.5 | **Lịch sử thay đổi**: tab "Lịch sử" trên trang văn bản hiển thị diff từng lần sửa, đọc từ sổ kiểm toán (F2.12) |
| F3.7 | **Văn bản hạn chế truy cập**: tệp lưu mã hóa (khóa dữ liệu bọc bằng OpenBao Transit), chỉ giải mã trong bộ nhớ của `svc-files` khi người trong danh sách được phép xem; xem có watermark tên người xem; nội dung không đưa vào chỉ mục tìm kiếm. Đúng năng lực *"giải mã an toàn tài liệu trên RAM"* của đề. **Không dùng cho bí mật nhà nước** |
| F3.8 | **Lập hồ sơ và nộp lưu** (nguyên lý i): hồ sơ công việc đóng quá `DXOS_ARCHIVE_AFTER_DAYS` → gói lưu trữ (Parquet + PDF + manifest có băm) sang bucket `cold`; OLTP chỉ giữ bản ghi rút gọn để vẫn tìm và xác thực được; xem trong **phòng đọc ảo** (chỉ xem, watermark) |
| F3.10 | **IT/OT** (nguyên lý ii): cảm biến nhiệt độ phòng máy chủ vượt ngưỡng → tác tử dựng nháp "báo cáo sự cố" từ mẫu → đi vào luồng văn bản đi để trình lãnh đạo |
| F3.11 | **Dashboard điều hành**: văn bản đến theo trạng thái, quá hạn theo phòng, thời gian xử lý trung bình, văn bản khẩn, văn bản đi theo tháng |
| F3.12 | **Hai đơn vị trên một hệ thống**: phát hành văn bản cho đơn vị khác trong hệ thống → tự thành văn bản đến của đơn vị nhận, đã xác thực; dữ liệu hai bên vẫn cách ly |

### 4.3. Could — Phase 4 (`v0.9.0`)

| Mã | Chức năng |
|---|---|
| F4.1 | **Đọc văn bản đến**: PDF có lớp chữ → đọc thẳng; ảnh / bản scan → OCR. Quy tắc cho số ký hiệu, ngày (mẫu "Số: …/…", "ngày … tháng … năm …"); mô hình ngôn ngữ chỉ tóm trích yếu. Điền sẵn form, văn thư xác nhận. **Giữ đầu tiên** nếu tuần đệm bị dùng |
| F4.2 | **Trợ lý** hỏi đáp trên kho văn bản, trả lời kèm số ký hiệu và trang; lọc theo quyền ở bước truy xuất; không đưa văn bản hạn chế vào chỉ mục |
| F4.3 | **Tác tử gợi ý giao việc**: đề xuất đơn vị chủ trì và hạn dựa trên văn bản tương tự trước đây; có danh tính riêng, hành động vào sổ kiểm toán; lãnh đạo quyết |
| F4.4 | Che CCCD, số điện thoại trong log và ngữ cảnh gửi mô hình |
| F4.5 | Ký số PDF (PAdES) bằng PKI nội bộ do OpenBao cấp — **chỉ minh họa**, không có giá trị pháp lý như chữ ký số công cộng |
| F4.6 | Thu góp ý, đo số liệu "sau" theo §8 |
| F4.7 | **Tự chẩn đoán H-P-D-I** cho lãnh đạo: bộ câu bốn không gian × 5 mức, radar, bước tiếp theo trỏ phân hệ Signet, bằng chứng đo được từ số liệu của chính đơn vị, lưu lịch sử ([`tu-chan-doan.md`](tu-chan-doan.md)) |

### 4.4. Không làm

| Hạng mục | Lý do |
|---|---|
| Văn bản Mật, Tối mật, Tuyệt mật | Luật Bảo vệ bí mật nhà nước 2018 cấm lưu trên máy kết nối Internet |
| Liên thông Trục văn bản quốc gia (edXML) | Cần mã định danh và kết nối do cơ quan nhà nước cấp — định hướng phát triển |
| Chữ ký số công cộng, USB token, HSM | Cần tổ chức chứng thực được cấp phép |
| Quản lý con dấu và thiết bị lưu khóa bí mật | Ngoài phạm vi phần mềm |
| Ứng dụng di động | Không đủ thời gian; giao diện web dùng được trên điện thoại |

---

## 5. Hai ứng dụng trên một lõi

| | `apps/office` | `apps/verify` |
|---|---|---|
| Người dùng | Cán bộ của đơn vị | Bất kỳ ai |
| Đăng nhập | SSO Keycloak, TOTP theo vai trò | Không |
| Route ở APISIX | `/v1/graphql`, `/api/files/*`, `/api/search`, `/realtime` — kiểm JWT tại biên | `/api/verify/*` — ẩn danh, giới hạn tốc độ chặt |
| Dữ liệu | Quyền cấp dòng theo thuê ước, phòng, người được giao | Chỉ các trường công khai của văn bản đã phát hành; không liệt kê được |

Một ứng dụng thứ ba cắm vào lõi cần: một client Keycloak, một nhóm route APISIX, một vai trò Hasura và một
tiền tố bucket — không sửa mã của lõi. Đây là bằng chứng cho nguyên tắc "đổi tầng trên, giữ tầng dưới".

---

## 6. Ánh xạ yêu cầu của đề

| Yêu cầu | Bằng chứng |
|---|---|
| R1, R2 — Tầng 1 headless | Lõi không có giao diện; chỉ APISIX mở cổng ra ngoài, theo danh sách trắng |
| R3 — Identity/SSO | Keycloak: SSO, TOTP, vai trò, thuộc tính `tenant_id`, `department_id` trong JWT |
| R4 — API Gateway | APISIX: kiểm JWT, giới hạn tốc độ, route công khai riêng cho cổng xác thực |
| R5 — Dữ liệu có cấu trúc | PostgreSQL + Hasura: API tự sinh, quyền cấp dòng, sổ kiểm toán |
| R5 — Dữ liệu phi cấu trúc | SeaweedFS + ClamAV + Meilisearch: công văn, đính kèm, tìm kiếm toàn văn |
| R6 — Workflow | Flowable: `van-ban-den`, `van-ban-di` |
| R7 — Ứng dụng Tầng 2 | Văn phòng điện tử ([P]) + cổng xác thực |
| (i) Vòng đời dữ liệu | Lập hồ sơ, nộp lưu: nóng → lạnh, có căn cứ NĐ 30 và Luật Lưu trữ |
| (ii) IT/OT | Cảm biến → bản sao số NGSI-LD → báo cáo sự cố vào luồng văn bản đi |
| (iii) Quản trị dữ liệu | Phả hệ: báo cáo dashboard ← bảng ← sự kiện; nguồn gốc mỗi văn bản (ai nhận, ai sửa, bản nào được phát hành) |
| (iv) Zero-Trust + GitOps | Kiểm dịch trước khi lưu, két bí mật, cấu hình trong git, tự phục hồi |

Các năng lực đề nêu tên mà sản phẩm chạm tới một cách tự nhiên:

- Cụm ④ gần như nguyên văn: lưu trữ đối tượng, *"quản lý hồ sơ và văn bản nghiệp vụ phục vụ trực tiếp cho
  các quy trình phê duyệt"*, chỉ mục toàn văn, *"trộn dữ liệu tự động sinh biểu mẫu"* (dựng công văn từ mẫu).
- Cụm ①: trạm kiểm dịch tệp, két khóa, PKI (Could).
- [P]: *"Văn phòng điện tử (e-Office)"*, *"Giải mã an toàn tài liệu trên RAM"*.
- [D] kho lạnh: *"Phòng đọc ảo bảo mật chống sửa xóa"*, *"Cổng đối soát sổ cái mật mã bất biến"*.
- [I]: tìm kiếm, OCR, trợ lý RAG.

---

## 7. Kịch bản demo 5 phút

| # | Màn | Dự phòng nếu hỏng |
|---|---|---|
| 1 | Văn thư tải lên một công văn scan → quét virus → hệ thống điền sẵn số ký hiệu, ngày, cơ quan ban hành, trích yếu → văn thư xác nhận, vào sổ, nhận số đến | Không có F4.1 thì văn thư nhập tay — luồng không đổi |
| 2 | Lãnh đạo khoa ghi ý kiến chỉ đạo: giao phòng Đào tạo chủ trì, hạn 3 ngày → chuyên viên nhận thông báo ngay | — |
| 3 | Chuyên viên soạn công văn trả lời từ mẫu → trình → lãnh đạo duyệt → văn thư cấp số → PDF phát hành có mã QR | — |
| 4 | **Giám khảo quét QR bằng điện thoại** → "văn bản thật, ban hành ngày …". Sửa một chữ trong PDF, thả vào cổng → "không khớp" | Quét bằng điện thoại của đội |
| 5 | Hỏi trợ lý "tháng này có công văn nào về tuyển sinh sắp quá hạn?" → trả lời kèm số ký hiệu; dashboard văn bản quá hạn theo phòng | Không có F4.2 thì dùng tìm kiếm + dashboard |
| 6 | `docker rm -f` một dịch vụ → hệ thống tự dựng lại; tệp EICAR bị từ chối trước khi lưu | Video quay sẵn |

---

## 8. Số đo thành công

| Chỉ số | Trước (đo ở đơn vị chạy thử, Phase 1) | Sau (đo trên hệ thống, Phase 4) |
|---|---|---|
| Thời gian từ khi văn bản đến tới khi được giao xử lý | Hỏi văn thư, đếm 20 văn bản gần nhất | Từ dòng thời gian văn bản |
| Tỷ lệ văn bản xử lý quá hạn | Sổ tay / Excel của văn thư | Hạn giải quyết so với lúc hoàn thành |
| Thời gian tìm lại một văn bản cũ | Bấm giờ 5 lần tìm | Bấm giờ 5 lần tìm trên hệ thống |
| Số bước chuyển tay (in, ký, mang đi, nhắn tin nhắc) | Quan sát quy trình hiện tại | So với quy trình trên hệ thống |

Chỉ trình bày số đo thật. Chỉ số nào chưa đo được thì nói rõ là chưa đo.

---

## 9. Rủi ro riêng của hướng này

| Rủi ro | Cách chặn |
|---|---|
| Nghiệp vụ văn thư mới với cả đội | Chỉ lấy phần ở §2.1; một buổi hỏi văn thư khoa ngay Phase 1; đối chiếu điều khoản gốc |
| Giám khảo hỏi "khác gì VNPT iOffice?" | Không đua tính năng. Khác ở: tự làm chủ, nguồn mở, cổng xác thực mở cho người ngoài, lõi tái dùng cho ứng dụng khác |
| Ký số nội bộ bị hiểu là có giá trị pháp lý | F4.5 là Could; khi trình bày nói rõ chỉ minh họa |
| NĐ 30 quy định phông Times New Roman (không phải nguồn mở) | Dùng Liberation Serif (SIL OFL 1.1, cùng kích thước chữ với Times New Roman) cài từ gói hệ thống; đơn vị có bản quyền phông thì đổi qua `.env` |
| "Văn bản hạn chế" bị hiểu là văn bản mật | Ghi rõ trong giao diện và tài liệu: không dùng cho bí mật nhà nước |
| Dữ liệu thật chứa thông tin cá nhân | Chỉ dùng công văn đã công bố; dữ liệu nội bộ của đơn vị không vào repo |
| OCR tiếng Việt kém trên ảnh chụp | Ưu tiên PDF có lớp chữ; quy tắc cho số ký hiệu, ngày; OCR chỉ cho bản scan; luôn nhập tay được |
| IT/OT là nguyên lý gượng nhất | Trình bày là năng lực của lõi, minh họa qua một loại văn bản; không thổi phồng |
| Đội chưa công khai repo cũng làm e-Office | Khác biệt nằm ở cổng xác thực, lưu trữ chống sửa xóa, văn bản hạn chế — không ở e-Office chung chung |

---

## 10. Câu hỏi còn mở

1. **Tên sản phẩm — đã chốt 15/10/2026: Mộc** (theo chữ "đóng mộc" — đóng dấu). Hai tên đã loại:
   "DX-Lab" trùng ứng dụng của HaUI và tên Trạm thực hành số trong chủ đề cuộc thi; "AgentLab" trùng
   dự án nguồn mở ServiceNow/AgentLab và gợi một sản phẩm về tác tử AI. Tên repo giữ nguyên `HVL` (đổi thành
   `Signet` ngày 25/10/2026); tên kỹ thuật (Compose project, CSDL mặc định, gói phát hành) là `moc`, biến môi
   trường `MOC_*`.
   **Đổi 23/10/2026: Signet** — nhẫn ấn đóng dấu lên văn bản, giữ ý "đóng dấu" của tên cũ; chỉ đổi tên hiển thị
   (giao diện, tài liệu, chuỗi in ra, header giấy phép "Signet Team"), tên kỹ thuật `moc` giữ nguyên.
2. **Đơn vị chạy thử**: văn thư khoa nào đồng ý dùng thử; nếu không, dùng phương án dự phòng ở kế hoạch §1.1.
   Khoa thường không có con dấu riêng; văn bản mang dấu do văn thư trường phát hành. Cần hỏi khoa có tự
   đánh số văn bản đi (thông báo, kế hoạch nội bộ) không. Nếu không, luồng văn bản đi chạy thử ở văn thư
   trường hoặc bằng dữ liệu mẫu.
3. **Mẫu văn bản đi làm trước**: đề xuất công văn và thông báo.
4. Hỏi BTC: trang đăng nhập do Keycloak phát ra có bị coi là giao diện của Tầng 1 không
   ([`olp-2026-de-thi.md`](du-thi/olp-2026-de-thi.md) §8).

---

## 11. Nguồn

- Đề thi OLP PMNM 2026: <https://vfossa.vn/tin-tuc/de-thi-phan-mem-nguon-mo-olp-2026-798.html>
- Nghị định 30/2020/NĐ-CP về công tác văn thư:
  <https://thuvienphapluat.vn/van-ban/Bo-may-hanh-chinh/Nghi-dinh-30-2020-ND-CP-cong-tac-van-thu-436532.aspx>,
  <https://hethongphapluat.com/nghi-dinh-30-2020-nd-cp-ve-cong-tac-van-thu.html>
- Luật Lưu trữ 2024: <https://thuvienphapluat.vn/van-ban/Bo-may-hanh-chinh/Luat-Luu-tru-2024-545181.aspx>
- Luật Bảo vệ bí mật nhà nước 2018, Điều 5: <https://hethongphapluat.com/luat-bao-ve-bi-mat-nha-nuoc-2018/dieu-5>
- QCVN 102:2016/BTTTT: <https://luatvietnam.vn/thong-tin/quy-chuan-viet-nam-qcvn-102-2016-btttt-bo-thong-tin-va-truyen-thong-155610-d3.html>
- VNPT iOffice: <https://www.sggp.org.vn/vnpt-ioffice-phat-huy-hieu-qua-tai-thi-truong-trong-nuoc-va-nuoc-ngoai-post692092.html>
- E-OFFICE của EVN: <https://tapchicongthuong.vn/evn-chuyen-giao-e-office-den-tay-dai-hoc-bach-khoa-ha-noi-65893.htm>
- DDOC: <https://groups.drupal.org/ddoc-vietnam-egov>
- Kho mã các đội: liên kết trong bảng §1.2.
