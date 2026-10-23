# OLP PMNM 2026 — Bản tóm tắt nền

> Tổng hợp ngày 31/08/2026. Rà soát ngày 09/09/2026 theo hai bài đăng của VFOSSA
> (ngày 09/06/2026):
>
> - [Giới thiệu mô hình DX-OS và chủ đề cuộc thi](https://vfossa.vn/tin-tuc/gioi-thieu-mo-hinh-dx-os-va-chu-de-cuoc-thi-phan-mem-nguon-mo-olp-2026-761.html)
> - [Thể lệ OLP Phần mềm nguồn mở năm 2026](https://vfossa.vn/tin-tuc/the-le-olp-phan-mem-nguon-mo-nam-2026-760.html)
>
> Việc rà soát dựa trên bản HTML lưu cục bộ của hai bài trên, đặt trong thư mục `publics/`.
> Thư mục này **không kèm trong repo** (đã đưa vào `.gitignore`) để tránh phân phối lại
> tài liệu của BTC; hãy dùng hai liên kết gốc ở trên khi cần đối chiếu.
>
> Mục 1–2 tóm tắt bài giới thiệu; mục 3–4 tóm tắt thể lệ; mục 5–6 là nhận định và
> đề xuất của đội. Chưa đối chiếu toàn văn giáo trình DX-OS hoặc các cập nhật trực tuyến
> sau bản lưu. Khi có đề thi và thông báo mới, cần cập nhật lại phạm vi sản phẩm.

---

## 0. TL;DR

- **Chủ đề 2026**: Xây dựng **Hệ điều hành Doanh nghiệp số (DX-OS)** — cụ thể là một
  **Trạm thực hành số (DX-Lab)** theo kiến trúc **Open-Core**, mô phỏng đủ 4 không gian **H-P-D-I**.
- **Thang điểm 100** = **50đ PoF** (chấm kho mã nguồn, 7–9/12/2026) + **50đ sản phẩm** (chấm chung kết 10/12/2026).
- **50đ PoF đánh giá nền tảng và khả năng sử dụng của dự án nguồn mở**: giấy phép, quản lý mã nguồn,
  bản phát hành, cài đặt từ mã nguồn, phụ thuộc và tài liệu. Có thể chuẩn bị trước nhiều hạng mục,
  nhưng phải nghiệm thu trên sản phẩm thực tế; bộ khung và CI chưa bảo đảm đạt đủ điểm.
- **Theo lịch đã công bố, đề thi ra tháng 11/2026**, khoảng một tháng trước chung kết.
  Đội đề xuất tận dụng thời gian trước đó để khảo sát công cụ, thử tích hợp và chuẩn bị hạ tầng;
  phạm vi nghiệp vụ cuối cùng cần bám đề thi cụ thể.

---

## 1. Mô hình DX-OS

### 1.1. Bài toán gốc

Chuyển đổi số (CĐS) hiện đang mắc bẫy **"ảo tưởng công nghệ"**: tổ chức đổ tiền mua hàng loạt phần mềm đắt đỏ nhưng nhân sự vẫn làm việc theo thói quen cũ — nhắn tin rải rác, báo cáo thủ công. Hệ quả là dữ liệu sinh ra bị giam trong các **ốc đảo thông tin** rời rạc và thất bại trong việc giải quyết bài toán chiến lược. Áp lực này đè lên cả tầng quản lý vĩ mô của Chính phủ lẫn hơn **900.000 SME** trên cả nước.

Bài giới thiệu trình bày luận điểm của giáo trình *"Xây dựng Hệ điều hành Doanh nghiệp số:
Từ Tư duy đến Hành động (DX-OS in Action)"*:

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

Mức 10–20% là mô tả trong bài giới thiệu mô hình; thể lệ đã lưu chưa quy định đây là ngưỡng
nghiệm thu hay chỉ tiêu chấm điểm bắt buộc. Nếu dùng làm mục tiêu demo, đội cần định nghĩa cách đo.

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

| Chủ đề cũ      | Công nghệ                                 | Ánh xạ vào DX-Lab                                                                           |
| ------------------ | ------------------------------------------- | ---------------------------------------------------------------------------------------------- |
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

> **Kế hoạch của đội tại 09/09/2026:** chuẩn bị nền tảng nguồn mở và thử nghiệm tích hợp trước
> tháng 11; đối chiếu đề thi khi công bố và nghiệm thu sản phẩm trước đợt chấm repo ngày 7–9/12.

### 3.2. Điều kiện cần (loại từ vòng gửi xe)

> Dự án dự thi **bắt buộc** phải là phần mềm nguồn mở phát hành theo **giấy phép OSI-approved**
> ([http://opensource.org/licenses](http://opensource.org/licenses)) và **truy cập tự do mã nguồn trên Internet**.
> Chỉ dự án đáp ứng yêu cầu này mới được BTC chấm điểm xếp hạng.

---

## 4. Bảng tiêu chí chấm điểm (100đ)

### Phần I — Tiêu chí dựa trên PoF: **50đ** (chấm **trước** buổi chung kết)

| # | Tiêu chí                                                        | Tối đa     | Các mức trừ điểm                                                                                                                                                                                                                                                                                                                | Ghi chú BTC                                                               |
| - | ----------------------------------------------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------- |
| 1 | Sử dụng hệ thống quản lý mã nguồn trên Internet          | **5**  | không có web viewer **−3** · không được truy cập mở **−3** · có repo nhưng thực tế không dùng **−5**                                                                                                                                                                                                            | Có thể truy cập kho mã nguồn từ Internet                             |
| 2 | Cấp phép PMNM theo giấy phép OSI-approved                     | **10** | license không ghi trong **từng tệp mã** **−5** · mã nguồn tự thân chứa **xung đột giấy phép** **−5** · không có thông báo về mục đích giấy phép **−5** · không có **bản sao toàn văn** giấy phép **−5**                                                            | Sản phẩm có giấy phép mở **và giải quyết đúng đầu bài** |
| 3 | Có ít nhất một **release** làm sản phẩm dự thi       | **5**  | không có phát hành **−5** · không phát hành theo phiên bản **−3** · dùng **định dạng không mở** (.zip, .rar, .arj…) **−3**                                                                                                                                                                              | Release đầu tiên phải tạo **trước thời điểm nộp bài**     |
| 4 | Cài đặt, dịch từ mã nguồn (**Building From Source**) | **10** | không có hướng dẫn build **−5** · cấu hình bằng cách **sửa tay file header** **−5** · không configure được trước khi dịch **−5** · dịch bằng **công cụ nguồn đóng/tự tạo** **−5** · chương trình không chạy được nếu **nằm ngoài thư mục mã nguồn** **−5** | Sản phẩm phải cho phép cài đặt, biên dịch được từ mã nguồn  |
| 5 | Sử dụng thư viện và gói đính kèm (**bundling**)    | **10** | không cố gắng dùng thư viện **sẵn có trong hệ thống** **−5** · phát hành **kèm gói của dự án khác** mà nó phụ thuộc **−5** · **mã nguồn gói đính kèm đã bị chỉnh sửa** **−5**                                                                                             | Có thông tin làm rõ các thư viện, gói đính kèm được dùng    |
| 6 | Tài liệu và giao tiếp                                         | **10** | không có **bug tracker** **−5** · không có **changelog** **−5** · không có **README**/hướng dẫn **−5**                                                                                                                                                                                      | Tài liệu rõ ràng, thực hiện được                                  |

### Phần II — Tiêu chí dựa trên sản phẩm: **50đ** (chấm **trong** buổi chung kết)

| #  | Tiêu chí                                                                       | Tối đa | Căn cứ chấm                                                |
| -- | -------------------------------------------------------------------------------- | -------- | ------------------------------------------------------------- |
| 7  | **Tính nguyên gốc** của giải pháp kỹ thuật                         | 10       | Kết quả trình bày về sự sáng tạo của đội thi       |
| 8  | **Mức độ hoàn thiện** của sản phẩm                                 | 10       | Kết quả **chạy trình diễn** sản phẩm              |
| 9  | Mức độ **sử dụng thân thiện**                                        | 10       | Các tiện ích của sản phẩm đối với người dùng      |
| 10 | Mức độ **phát triển bền vững**                                       | 10       | Tài liệu kỹ thuật, công cụ hỗ trợ công bố kèm theo |
| 11 | **Phong cách trình diễn** & khả năng thu hút cộng đồng nguồn mở | 10       | Showcase trình diễn sản phẩm tại cuộc thi               |

**Nguồn gốc bộ tiêu chí PoF:**

- Tom Callaway, *"How you know your Free or Open Source Software Project is doomed to FAIL
  (or at least, held back from success)"*, LiveJournal, 29/05/2009 —
  [http://spot.livejournal.com/308370.html](http://spot.livejournal.com/308370.html)
- Bản dịch: Trương Anh Tuấn, *"Đánh giá khả năng phát triển của một dự án PMTDNM"* —
  [http://blog.iwayvietnam.com/tuanta/2013/04/danh-gia-kha-nang-phat-trien-cua-mot-du-an-foss/](http://blog.iwayvietnam.com/tuanta/2013/04/danh-gia-kha-nang-phat-trien-cua-mot-du-an-foss/)

---

## 5. Nhận định và đề xuất của đội

Các đề xuất dưới đây nhằm triển khai chủ đề và giảm rủi ro khi dự thi. Chúng không bổ sung
quy định của BTC và không bảo đảm mức điểm cụ thể.

1. **Chuẩn bị sớm nền tảng đáp ứng PoF, nghiệm thu trên sản phẩm hoàn chỉnh.**
   Đội có thể dựng trước LICENSE, thông báo giấy phép trong từng tệp mã, CHANGELOG, README,
   bug tracker và quy trình phát hành. CI hỗ trợ kiểm tra tự động một phần; vẫn cần kiểm chứng
   cài đặt/build thực tế, truy cập repo công khai, lịch sử sử dụng repo, bản phát hành thật và
   tính tương thích giấy phép. Tiêu chí #2 còn ghi sản phẩm phải giải quyết đúng đầu bài.
   Đội chọn tag **SemVer** và gói **`.tar.gz`** để quản lý phát hành; thể lệ yêu cầu phát hành
   theo phiên bản và định dạng mở, không chỉ định SemVer. Ví dụ `.zip` trong bảng điểm được
   giữ theo cách phân loại của thể lệ, không phải kết luận kỹ thuật chung về định dạng ZIP.
2. **Ưu tiên điều phối upstream nguyên bản để giảm rủi ro bundling.**
   Tiêu chí #5 nêu mức trừ cho phát hành kèm gói phụ thuộc và chỉnh sửa mã nguồn gói đính kèm.
   Đội chọn Docker Compose kéo image upstream nguyên bản, đặt tùy biến trong cấu hình,
   plugin hoặc adapter riêng, đồng thời ghi dependency và giấy phép trong `DEPENDENCIES.md`.
   Đây là chính sách kiến trúc của đội; hai tài liệu nguồn chưa đủ để kết luận Compose là
   phương án bắt buộc hoặc mọi hình thức fork đều bị cấm. Danh mục dependency cũng cần đi kèm
   kiểm tra cách sử dụng và nghĩa vụ giấy phép của từng thành phần.
3. **Dùng Docker kèm quy trình cài đặt từ mã nguồn có thể kiểm chứng.**
   Bài giới thiệu khuyến khích container hóa bằng Docker. Đội vẫn phải đáp ứng tiêu chí #4:
   hướng dẫn đầy đủ, cấu hình trước khi build, dùng công cụ nguồn mở và chạy được ngoài thư mục
   mã nguồn. Chỉ có Compose kéo image dựng sẵn chưa chứng minh đầy đủ khả năng build từ mã nguồn;
   cần mô tả rõ cách dựng phần đội phát triển và cách lấy/dựng các thành phần phụ thuộc.
4. **Đầu tư vào tích hợp và phần nghiệp vụ tạo giá trị.**
   Đội đề xuất tập trung vào ánh xạ nghiệp vụ H-P-D-I, chuẩn hóa dữ liệu, kết nối sự kiện và
   tác tử thực hiện hành động có kiểm soát. Tiêu chí tính nguyên gốc không giới hạn sáng tạo
   ở lớp tích hợp: đội có thể tự viết module nghiệp vụ, giao diện, cơ chế kiểm soát dữ liệu
   hoặc tác tử khi cần. Hai tài liệu đã đọc không quy định lượng code tối thiểu; phần tự viết
   cần phục vụ bài toán và phối hợp được với nền tảng nguồn mở đã chọn.
5. **Chọn một nghiệp vụ xuyên bốn trục làm kịch bản demo.**
   Đội đề xuất một quy trình SME đủ nhỏ để chạy trọn vòng đời **[H] → [P] → [D] → [I]**, cho thấy
   dữ liệu đầu vào được kiểm soát, quy trình phát sinh dữ liệu thống nhất và AI sử dụng dữ liệu
   đó để hành động. Cách này giúp thể hiện rõ tinh thần của mô hình; điểm thực tế vẫn phụ thuộc
   yêu cầu đề thi, mức độ hoàn thiện và đánh giá của giám khảo.
6. **Chuẩn bị tài liệu và khả năng trình diễn song song với triển khai.**
   Hai tiêu chí bền vững và trình diễn/thu hút cộng đồng có tổng tối đa 20đ. Đội đề xuất dùng
   tài liệu kỹ thuật, ROADMAP, CONTRIBUTING, hướng dẫn vận hành và showcase làm bằng chứng.
   Thể lệ không quy định bắt buộc đầy đủ các tên tệp này hoặc mặc định có chúng là đạt đủ điểm.

---

## 6. Việc cần làm tiếp (kế hoạch của đội)

- [ ] Rà soát bộ khung repo đã có: LICENSE, header giấy phép, CHANGELOG, README, CI và workflow
  phát hành; bổ sung bằng chứng theo `docs/du-thi/pof-checklist.md`, không tự chấm đủ điểm từ bộ khung.
- [ ] Kiểm chứng repo công khai và bug tracker được sử dụng thực tế; tạo bản phát hành có phiên bản
  trước thời điểm nộp bài.
- [ ] Chốt stack open-source cụ thể cho từng trục H / P / D / I, kèm bảng giấy phép để kiểm tra
  tương thích.
- [ ] Chọn 1 kịch bản nghiệp vụ SME chạy xuyên 4 trục để thử nghiệm; xác định phần dùng sẵn,
  phần cấu hình và phần cần tự code.
- [ ] Nghiệm thu cài đặt/build trên môi trường sạch, cấu hình trước khi dựng và khả năng chạy ngoài
  thư mục mã nguồn; cập nhật hướng dẫn theo kết quả thực tế.
- [ ] Đăng ký đội (≤3 SV + 1 giảng viên), theo dõi đề thi tháng 11/2026 và các thông báo mới của BTC;
  điều chỉnh phạm vi sản phẩm và checklist theo yêu cầu chính thức.
