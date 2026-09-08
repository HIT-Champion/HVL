# OLP PMNM 2026 — Bản tóm tắt nền

> Nguồn: `public/Quick-guide-to-DXOS.pdf` (giới thiệu mô hình DX-OS & chủ đề thi) và
> `public/Thể lệ cuộc thi phần mềm nguồn mở - OLP 2026.pdf` (thể lệ chính thức).
> Tổng hợp ngày 31/08/2026.

---

## 0. TL;DR

- **Chủ đề 2026**: Xây dựng **Hệ điều hành Doanh nghiệp số (DX-OS)** — cụ thể là một
  **Trạm thực hành số (DX-Lab)** theo kiến trúc **Open-Core**, mô phỏng đủ 4 không gian **H-P-D-I**.
- **Thang điểm 100** = **50đ PoF** (chấm kho mã nguồn, 7–9/12/2026) + **50đ sản phẩm** (chấm chung kết 10/12/2026).
- **50đ PoF gần như không liên quan tới tính năng phần mềm** — đó là kỷ luật hạ tầng dự án nguồn mở
  (license, release, build from source, bundling, tài liệu). Chuẩn bị được **ngay từ bây giờ**, trước khi có đề.
- **Đề thi công bố tháng 11/2026**, tức chỉ ~1 tháng để code. Cửa sổ 9–11/2026 là để dựng sẵn khung + hạ tầng repo.

---

## 1. Mô hình DX-OS

### 1.1. Bài toán gốc

Chuyển đổi số (CĐS) hiện đang mắc bẫy **"ảo tưởng công nghệ"**: tổ chức đổ tiền mua hàng loạt phần mềm đắt đỏ nhưng nhân sự vẫn làm việc theo thói quen cũ — nhắn tin rải rác, báo cáo thủ công. Hệ quả là dữ liệu sinh ra bị giam trong các **ốc đảo thông tin** rời rạc và thất bại trong việc giải quyết bài toán chiến lược. Áp lực này đè lên cả tầng quản lý vĩ mô của Chính phủ lẫn hơn **900.000 SME** trên cả nước.

Luận điểm gốc của giáo trình *"Xây dựng Hệ điều hành Doanh nghiệp số: Từ Tư duy đến Hành động
(DX-OS in Action)"*:

> **CĐS về bản chất là quá trình chuyển giao quyền kiểm soát từ thao tác thủ công của con người
> sang các thuật toán tự động.**

Quá trình này được mô hình hóa bằng cấu trúc phân bổ quyền điều khiển **H-P-D-I**.

### 1.2. Kiến trúc 4 không gian H-P-D-I

| Trục         | Tên không gian                                                | Vai trò kiến trúc                                                                                                                                                                                                            | Thành phần kỹ thuật                                                                                                                                                                 |
| ------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **[H]** | Nhân sự — Kiến tạo Môi trường Làm việc Số Tích hợp | Phân tầng vận hành cơ sở. Thay vì để quy trình phụ thuộc trí nhớ/thói quen, tạo môi trường làm việc số khép kín, kiểm soát độ chính xác của luồng thông tin**ngay từ khâu đầu vào** | Quản trị định danh tập trung (**SSO**), chuẩn hóa lưu trữ tệp vật lý theo **P.A.R.A**, cổng thông tin nội bộ                                                |
| **[P]** | Quy trình — Tự động hóa Luồng công việc                | Tiếp nhận quyền điều khiển từ con người bằng cách thiết lập cấu trúc thuật toán. Xử lý bàn giao thông tin giữa các bộ phận**không cần thao tác tay**                                          | Kiến trúc**hướng sự kiện**, ràng buộc kỹ thuật **Poka-yoke** giới hạn thao tác không hợp lệ, bảo đảm toàn vẹn tại điểm chạm đầu vào             |
| **[D]** | Dữ liệu — Ra quyết định dựa trên sự thật              | Khi [P] chạy ổn định, hệ thống tự kết xuất tập dữ liệu phẳng có cấu trúc. [D] thu thập, làm sạch, đồng bộ thành**Nguồn sự thật duy nhất**, triệt tiêu ốc đảo thông tin                   | **Dashboard thời gian thực** để quản lý điều hành bằng số liệu định lượng                                                                                         |
| **[I]** | Trí tuệ Nhân tạo — Tiến đến Doanh nghiệp Tự hành     | Trạng thái kiến trúc cao nhất, mô hình**AI-Native**. AI tích hợp trực tiếp dưới dạng **tác tử tự hành**                                                                                           | Tự phân tích dữ liệu từ [D], tự nhận diện sự kiện từ [P], tự thực thi lệnh hành động cấu hình sẵn —**không cần tín hiệu/nhấp chuột của con người** |

### 1.3. Hai nguyên lý cốt lõi

**(a) Tính tiến hóa tuyến tính bắt buộc.**
Tổ chức **không thể** đạt năng lực tự động hóa ở [I] nếu chưa chuẩn hóa dữ liệu tại [D] và chưa thiết lập
ràng buộc kỹ thuật tại [P]. Nhét AI vào quy trình chưa chuẩn hóa sẽ dẫn tới lỗi logic dữ liệu đầu vào
(**Garbage In, Garbage Out**) và sinh ảo giác dữ liệu.

**(b) Human-in-the-loop.**
Quá trình tiến hóa **tỷ lệ nghịch** với can thiệp thủ công. Khi năng lực xử lý của máy tại [P], [D], [I] tăng,
tỷ lệ thao tác tay của nhân sự (hằng số **[H]**) sụt từ **100% xuống còn 10–20%**. Nhân sự dịch chuyển
vai trò sang: thiết kế luồng thuật toán · kiểm soát chất lượng hệ thống · giám sát rào chắn đạo đức ·
phê duyệt ngoại lệ.

---

## 2. Chủ đề cuộc thi: Xây dựng DX-Lab

Hội Tin học Việt Nam và CLB **VFOSSA** công bố chủ đề OLP PMNM 2026:
**"Xây dựng Hệ điều hành Doanh nghiệp số (DX-OS) dựa trên kiến trúc Open-Core"**.

Mục tiêu: sinh viên (chuyên và không chuyên CNTT) vận dụng các nền tảng mã nguồn mở để **tự thiết kế
và xây dựng một Trạm thực hành số (DX-Lab)** — mô phỏng lại đủ 4 không gian H-P-D-I và giải quyết
triệt để các bài toán vận hành của doanh nghiệp.

### 2.1. Kế thừa hệ sinh thái công nghệ OLP các năm trước

BTC yêu cầu **chủ động kết hợp** các nền tảng đã khai thác ở các kỳ OLP trước thành một cỗ máy vận
hành hoàn chỉnh:

| Chủ đề cũ      | Công nghệ                                 | Ánh xạ vào DX-Lab                                                                                 |
| ------------------ | ------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| **OLP 2024** | Nền tảng**Low-code/No-code (LCDP)** | Xây biểu mẫu nhập liệu, thiết lập CSDL quan hệ, tạo rào chắn kỹ thuật tại**[P]** |
| **OLP 2025** | **Dữ liệu mở liên kết (LOD)**    | Chuẩn hóa cấu trúc siêu dữ liệu, hình thành Nguồn sự thật duy nhất cho**[D]**     |
| **OLP 2023** | **LLM + RAG**                         | Xây tác tử thông minh, tự động hóa quy trình ra quyết định tại**[I]**             |

### 2.2. Bản đồ công cụ theo trục (BTC **không** cho danh sách phần mềm tĩnh — đội tự nghiên cứu)

- **[H] Nhân sự**: nền tảng mở về Quản trị định danh tập trung (SSO), Quản trị lưu trữ đám mây nội bộ
  (Cloud Storage), Hệ thống quản trị tri thức (Wiki/CMS), Hệ thống truyền thông tức thời.
- **[P] Quy trình**: nền tảng low-code để dựng giao diện, kết hợp **iPaaS** và **Workflow Automation**
  để thiết lập **trục trung gian kết nối API** giữa các phần mềm.
- **[D] Dữ liệu**: hệ quản trị CSDL quan hệ/phi quan hệ để cấu trúc hóa dữ liệu tĩnh, kết hợp nền tảng
  **BI nguồn mở** để thiết kế dashboard và trực quan hóa.
- **[I] AI**: thư viện học máy, **Vector Database**, **LLM Framework** nguồn mở để xây kiến trúc truy xuất
  tri thức (RAG) và thiết lập **Agentic AI**.

### 2.3. Ba nhóm tác nhân đích của DX-Lab

1. **Ban lãnh đạo, quản lý SME và cơ quan Nhà nước** — dùng khung đo lường để chẩn đoán thực trạng
   tổ chức, triệt tiêu hạn chế vận hành, tối ưu **ROI** đầu tư hạ tầng công nghệ.
2. **Chuyên gia công nghệ và tư vấn viên** — môi trường đóng gói/chia sẻ tri thức chuyên môn, kết nối
   đối tác kỹ thuật, xây năng lực tham gia mạng lưới tư vấn viên CĐS cấp quốc gia.
3. **Sinh viên và giảng viên khối kỹ thuật/kinh tế số** — môi trường thực nghiệm giả lập (**hộp cát
   DX-Lab**) trên cơ sở dữ liệu thực tế của doanh nghiệp.

Toàn văn giáo trình: [https://opendigitransform.gitbook.io/dx-os](https://opendigitransform.gitbook.io/dx-os)

---

## 3. Thể lệ cuộc thi

**Cơ quan tổ chức**: Hội Tin học Việt Nam · **Đơn vị thường trực**: CLB VFOSSA
(căn cứ Quy chế Olympic Tin học Sinh viên Việt Nam)

| Hạng mục          | Nội dung                                                                                |
| ------------------- | ---------------------------------------------------------------------------------------- |
| Đối tượng       | Sinh viên chuyên**hoặc không chuyên** CNTT, các trường ĐH/CĐ toàn quốc |
| Hình thức         | **Lập trình hackathon theo đội**, đề do BTC đưa ra                         |
| Đội hình         | **≤ 3 thí sinh**, dẫn dắt bởi **1 giảng viên** của trường          |
| Giới hạn trường | **Tối đa 2 đội/trường**                                                      |
| Giải thưởng      | Theo quy chế OLP 2026                                                                   |

**Phương thức ra đề & làm bài:**

- Đề lập trình do chuyên gia VFOSSA xây dựng dựa trên chủ đề của năm.
- Đề **công bố trước ngày chấm chung kết 1 tháng**.
- Toàn bộ kết quả sản phẩm **phải được công bố trên một kho mã nguồn mở**.
- Các đội chuẩn bị bài trình bày + trình diễn sản phẩm tại buổi chấm.
- BTC chấm và phân hạng dựa trên **sản phẩm đã công bố trên kho nguồn mở** + **kết quả trình diễn**.

### 3.1. Lịch trình

| Thời gian               | Mốc                                                                 |
| ------------------------ | -------------------------------------------------------------------- |
| Tháng 7/2026            | Công bố chủ đề, phát động cuộc thi                          |
| **Tháng 11/2026** | **BTC công bố đề thi** + tiếp nhận danh sách đăng ký |
| 7–9/12/2026             | Chấm thi kho mã nguồn của sản phẩm dự thi                     |
| **10/12/2026**     | Trình diễn sản phẩm & chấm chung kết                           |
| 11/12/2026               | Công bố trao giải                                                 |

> **Tình trạng tại 31/08/2026**: còn ~2 tháng trước khi có đề, ~3,5 tháng tới hạn cuối.
> Đây là cửa sổ vàng để dựng sẵn khung DX-Lab và hoàn thiện hạ tầng repo ăn trọn 50đ PoF.

### 3.2. Điều kiện cần (loại từ vòng gửi xe)

> Dự án dự thi **bắt buộc** phải là phần mềm nguồn mở phát hành theo **giấy phép OSI-approved**
> ([http://opensource.org/licenses](http://opensource.org/licenses)) và **truy cập tự do mã nguồn trên Internet**.
> Chỉ dự án đáp ứng yêu cầu này mới được BTC chấm điểm xếp hạng.

---

## 4. Bảng tiêu chí chấm điểm (100đ)

### Phần I — Tiêu chí dựa trên PoF: **50đ** (chấm **trước** buổi chung kết)

| # | Tiêu chí                                                        | Tối đa     | Các mức trừ điểm                                                                                                                                                                                                                                                                                                                       | Ghi chú BTC                                                               |
| - | ----------------------------------------------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| 1 | Sử dụng hệ thống quản lý mã nguồn trên Internet          | **5**  | không có web viewer**−3**không được truy cập mở **−3**có repo nhưng thực tế không dùng **−5**                                                                                                                                                                                                            | Có thể truy cập kho mã nguồn từ Internet                             |
| 2 | Cấp phép PMNM theo giấy phép OSI-approved                     | **10** | license không ghi trong**từng tệp mã** **−5**mã nguồn tự thân chứa **xung đột giấy phép** **−5**không có thông báo về mục đích giấy phép **−5**không có **bản sao toàn văn** giấy phép **−5**                                                                   | Sản phẩm có giấy phép mở**và giải quyết đúng đầu bài** |
| 3 | Có ít nhất một**release** làm sản phẩm dự thi       | **5**  | không có phát hành**−5**không phát hành theo phiên bản **−3**dùng **định dạng không mở** (.zip, .rar, .arj…) **−3**                                                                                                                                                                              | Release đầu tiên phải tạo**trước thời điểm nộp bài**     |
| 4 | Cài đặt, dịch từ mã nguồn (**Building From Source**) | **10** | không có hướng dẫn build**−5**cấu hình bằng cách **sửa tay file header** **−5**không configure được trước khi dịch **−5**dịch bằng **công cụ nguồn đóng/tự tạo** **−5**chương trình không chạy được nếu **nằm ngoài thư mục mã nguồn** **−5** | Sản phẩm phải cho phép cài đặt, biên dịch được từ mã nguồn  |
| 5 | Sử dụng thư viện và gói đính kèm (**bundling**)    | **10** | không cố gắng dùng thư viện**sẵn có trong hệ thống** **−5**phát hành **kèm gói của dự án khác** mà nó phụ thuộc **−5****mã nguồn gói đính kèm đã bị chỉnh sửa** **−5**                                                                                              | Có thông tin làm rõ các thư viện, gói đính kèm được dùng    |
| 6 | Tài liệu và giao tiếp                                         | **10** | không có**bug tracker** **−5**không có **changelog** **−5**không có **README**/hướng dẫn **−5**                                                                                                                                                                                             | Tài liệu rõ ràng, thực hiện được                                  |

### Phần II — Tiêu chí dựa trên sản phẩm: **50đ** (chấm **trong** buổi chung kết)

| #  | Tiêu chí                                                                       | Tối đa | Căn cứ chấm                                                |
| -- | -------------------------------------------------------------------------------- | -------- | ------------------------------------------------------------- |
| 7  | **Tính nguyên gốc** của giải pháp kỹ thuật                         | 10       | Kết quả trình bày về sự sáng tạo của đội thi       |
| 8  | **Mức độ hoàn thiện** của sản phẩm                                 | 10       | Kết quả**chạy trình diễn** sản phẩm              |
| 9  | Mức độ**sử dụng thân thiện**                                        | 10       | Các tiện ích của sản phẩm đối với người dùng      |
| 10 | Mức độ**phát triển bền vững**                                       | 10       | Tài liệu kỹ thuật, công cụ hỗ trợ công bố kèm theo |
| 11 | **Phong cách trình diễn** & khả năng thu hút cộng đồng nguồn mở | 10       | Showcase trình diễn sản phẩm tại cuộc thi               |

**Nguồn gốc bộ tiêu chí PoF:**

- Tom Callaway, *"How you know your Free or Open Source Software Project is doomed to FAIL
  (or at least, held back from success)"*, LiveJournal, 29/05/2009 —
  [http://spot.livejournal.com/308370.html](http://spot.livejournal.com/308370.html)
- Bản dịch: Trương Anh Tuấn, *"Đánh giá khả năng phát triển của một dự án PMTDNM"* —
  [http://blog.iwayvietnam.com/tuanta/2013/04/danh-gia-kha-nang-phat-trien-cua-mot-du-an-foss/](http://blog.iwayvietnam.com/tuanta/2013/04/danh-gia-kha-nang-phat-trien-cua-mot-du-an-foss/)

---

## 5. Nhận định chiến lược (rút ra từ việc ghép hai tài liệu)

1. **Một nửa số điểm không nằm ở code.**
   50đ PoF là checklist kỷ luật hạ tầng dự án nguồn mở: license header trong **từng file**, LICENSE toàn
   văn, CHANGELOG, README, bug tracker (Issues), release có tag semver bằng **định dạng mở**
   (`.tar.gz`, không `.zip`). Hoàn toàn có thể tự động hóa bằng CI **trước khi biết đề**.
2. **Bẫy "bundling" mâu thuẫn trực tiếp với bản chất DX-Lab.**
   Sản phẩm là ghép nhiều nền tảng open-core, nhưng tiêu chí 5 trừ điểm nếu *phát hành kèm gói của dự
   án khác mà nó phụ thuộc* hoặc *sửa mã nguồn gói đính kèm*.
   ⇒ Kiến trúc phải là **orchestration**: `docker compose` kéo image upstream **nguyên bản**; mọi tùy
   biến nằm ở lớp config / plugin / adapter của riêng đội. **Tuyệt đối không fork-và-sửa** vào cây mã
   upstream. Cần một trang tài liệu liệt kê rõ mọi dependency + giấy phép của chúng (tránh cả bẫy
   "xung đột giấy phép" ở tiêu chí 2).
3. **Docker được BTC khuyến khích rõ ràng** để đóng gói DX-Lab — nhưng vẫn phải giữ đường
   **build from source** có hướng dẫn đầy đủ và configure được (tiêu chí 4), và chương trình phải chạy
   được **ngoài thư mục mã nguồn**.
4. **"Tính nguyên gốc" nằm ở lớp keo, không ở lớp component.**
   Ai cũng dùng các nền tảng open-source sẵn có, nên điểm sáng tạo đến từ: cách ánh xạ nghiệp vụ vào
   H-P-D-I, event bus nối [P] → [D], và tác tử [I] tiêu thụ đúng dữ liệu do chính [P] sinh ra.
5. **Kịch bản demo phải chứng minh tính tuyến tính.**
   Một nghiệp vụ chạy end-to-end xuyên **[H] → [P] → [D] → [I]** sẽ ăn điểm hơn hẳn 4 module rời rạc —
   đúng tinh thần "không nhảy cóc lên AI" của giáo trình. Nên chọn một quy trình SME cụ thể, đủ nhỏ để
   chạy trọn vẹn.
6. **20đ cho bền vững + thu hút cộng đồng** đòi tài liệu kỹ thuật, roadmap, CONTRIBUTING và một
   showcase thuyết phục. Phải chuẩn bị song song với code, không để dồn đến tháng 12.

---

## 6. Việc cần làm tiếp

- [ ] Dựng skeleton repo ăn trọn 50đ PoF (LICENSE toàn văn + SPDX header CI, CHANGELOG,
  README, Issues bật sẵn, release workflow xuất `.tar.gz` có tag semver).
- [ ] Chốt stack open-source cụ thể cho từng trục H / P / D / I, kèm bảng giấy phép để kiểm tra
  tương thích.
- [ ] Chọn 1 kịch bản nghiệp vụ SME chạy xuyên 4 trục làm xương sống cho demo.
- [ ] Đăng ký đội (≤3 SV + 1 giảng viên) và theo dõi mốc công bố đề tháng 11/2026.
