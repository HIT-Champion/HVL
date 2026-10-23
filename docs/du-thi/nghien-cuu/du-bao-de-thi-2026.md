# Dự báo đề thi tháng 11/2026 và đánh giá lại đề tài

> Viết ngày 10/09/2026, sau khi kiểm chứng ba mùa 2023–2025 (`chien-luoc-du-thi.md` mục 2.3).
> Mục đích: trả lời hai câu hỏi trước khi đầu tư thêm vào `dac-ta-dx-safety.md`:
> **(1)** đề thật tháng 11 có khả năng ép lĩnh vực và chuẩn nào; **(2)** với dự báo đó, đề tài
> DX-Safety còn đúng không, phải sửa gì.
>
> Quy ước: *(BTC)* là văn bản Ban tổ chức; *(giáo trình)* là giáo trình DX-OS; *(thời sự)* là bối
> cảnh chính sách đã kiểm chứng qua báo chí; *(đội)* là suy luận của đội. Mọi xác suất trong tài
> liệu này là ước lượng chủ quan để ra quyết định, không phải số liệu.

---

## 1. Mô hình ba mùa và điểm khác của 2026

*(BTC)* Ba mùa liền, bài giới thiệu chủ đề chỉ chốt **công nghệ**; đề thật chốt thêm **lĩnh vực**,
thường **kèm chuẩn hoặc nguồn dữ liệu bắt buộc**, và ra trước hạn nộp 3–6 tuần:

| Mùa | Chủ đề → Đề | Cái đề thêm vào | Đề ra → hạn nộp |
|---|---|---|---|
| 2023 | LLM → hỏi đáp pháp luật trên Bộ pháp điển và CSDL văn bản QPPL | Lĩnh vực + nguồn dữ liệu | không rõ → 12/2023 |
| 2024 | LCDP → kết nối cộng đồng ứng phó khẩn cấp (sau bão Yagi) | Lĩnh vực theo thời sự; ràng buộc repo | 20/11 → 09/12 (19 ngày) |
| 2025 | LOD → đô thị thông minh, SOSA/SSN + NGSI-LD + Smart Data Models, nguồn OpenAQ/OSM/GTFS, hai vai | Lĩnh vực + ba chuẩn + nguồn dữ liệu + vai | 27/10 → 08/12 (6 tuần) |

*(đội)* Mùa 2026 có hai điểm chưa từng có, và cả hai đều thu hẹp không gian đề:

1. **Chủ đề đi kèm một giáo trình 82 trang và một "hộp cát" có đặc tả cụ thể** (DX-Ticket: 2 bảng,
   17 cột, máy trạng thái, 3 sự kiện, dashboard). Hai mùa trước, chủ đề chỉ là một bài giới thiệu.
   Khi BTC đã bỏ công đặc tả một luồng mẫu, xác suất đề thật lấy luồng đó làm **yêu cầu nền** là cao.
2. **Chủ đề tự nhận là tổng hợp ba mùa trước** (LCDP ở [P], LOD ở [D], RAG ở [I]). Đề thật vì thế
   có thể **tái sử dụng chuẩn của các mùa trước** thay vì đưa chuẩn mới hoàn toàn.

---

## 2. Dự báo lĩnh vực

### 2.1. Bằng chứng

*(thời sự)* Bối cảnh SME Việt Nam năm 2026 có một cú sốc pháp lý đúng lúc: từ **01/01/2026 bỏ
thuế khoán**, toàn bộ hộ kinh doanh chuyển sang tự kê khai dựa trên hóa đơn điện tử, eTax Mobile và
dữ liệu chuyển khoản; hộ có doanh thu trên 1 tỷ đồng phải dùng hóa đơn điện tử có mã hoặc từ máy
tính tiền; sáu tháng đầu 2026 có hơn 315.000 hộ đăng ký hóa đơn từ máy tính tiền; từ 01/07/2026 có
thêm thay đổi về hóa đơn điện tử với hộ kinh doanh. Đây là "bão Yagi" của năm nay đối với khối
doanh nghiệp nhỏ.

*(giáo trình)* Chương 1 nêu đích danh *"Hệ thống Hóa đơn điện tử khởi tạo từ máy tính tiền, Cổng
Dịch vụ công Quốc gia, Đấu thầu qua mạng, Nộp thuế điện tử đã khóa chặt mọi ngả đường thủ công"*
và *"không tuân thủ... doanh nghiệp thậm chí không thể xuất hóa đơn hợp lệ"*. Chương 6 dành riêng
một "Lớp Pháp lý" cho hóa đơn điện tử có mã, kê khai GTGT/TNDN/TNCN, chuẩn VAS, và liệt kê ngành mở
rộng: bán lẻ/TMĐT (OMS, POS), logistics (WMS), lưu trú (PMS), y tế (DICOM), giáo dục (LMS), sản
xuất (IoT lò hơi), nông nghiệp, xây dựng (CDE), dịch vụ chuyên nghiệp (timesheet, billing). Hộp cát
duy nhất là **DX-Ticket: yêu cầu bảo hành, khiếu nại, tư vấn của khách hàng**.

*(BTC)* Bài giới thiệu chủ đề nhắc "hơn 900.000 SME" và "tầng quản lý vĩ mô của Chính phủ"; thể
lệ không giới hạn ngành.

### 2.2. Bằng chứng đợt 2 (10/09/2026, buổi chiều) *(đội kiểm chứng)*

Sau khi viết bản đầu, đội đào thêm ba nguồn: bản chép Quick-guide của đội khác, tác giả giáo trình,
và hộp cát live demo của giáo trình. Kết quả thay đổi thứ hạng ở 2.3.

| Phát hiện | Bằng chứng | Hệ quả cho dự báo |
|---|---|---|
| **`Quick-guide-to-DXOS.pdf` trùng nội dung bài web 761.** | So 63 câu của bản chép Markdown (kho `dx-lab-olp2026`) với bản txt bài web: chỉ 3 khác biệt, đều là tiêu đề | Không còn tài liệu BTC nào đội chưa đọc. Đóng việc 2 ở `nghien-cuu-chu-de-2026.md` mục 6.4 |
| **Tác giả giáo trình là TS. Tạ Tuấn Anh, Công ty CP FDS**, công ty GovTech làm OpenCPS (nền tảng dịch vụ công); cùng tác giả có hai giáo trình khác: quản trị dữ liệu công (`govdata`) và dữ liệu web/ontology/RDF (`webdata`); trang `home` có mục riêng về cuộc thi OLP PMNM | Trang "Tài nguyên tham khảo" của giáo trình ghi "Tạ Tuấn Anh - FDS, 2025"; via.org.vn; mục lục hai gitbook | Người viết chủ đề đồng thời là người quen viết về **dữ liệu công, từ điển dữ liệu liên kết, GovTech**. Kịch bản cơ quan nhà nước và ràng buộc "từ điển dữ liệu / ontology" tăng hạng. Việc ông có nằm trong HĐGK hay ban ra đề hay không **chưa kiểm chứng được** (bài 751 không nêu tên) |
| **Bài báo cùng tác giả, Tạp chí KH&CN Việt Nam số 8/2026**: đề xuất "Mô hình hợp tác 57" Nhà nước–Nhà trường–Doanh nghiệp, đặt **phòng thực hành mô phỏng hệ vận hành số của SME trong trường đại học**, ngành ưu tiên **logistics, tài chính, chế biến** | opendigitransform.gitbook.io/home, mục Ứng dụng CĐS | DX-Lab trong cuộc thi là hiện thân của mô hình này. Bài giới thiệu chủ đề mục 2.3 cũng nói sinh viên thực hành "trên các cơ sở dữ liệu thực tế của doanh nghiệp". Khả năng **đề kèm bộ dữ liệu mẫu** như 2023 (pháp điển) và 2025 (nguồn dữ liệu mở) là đáng kể |
| **Hộp cát live demo là công ty giả định "Alpha Corporation"**: cổng Google Sites, thư mục Drive `[ALPHA-CORP] HỆ ĐIỀU HÀNH SỐ DX-OS` với 4 thư mục P.A.R.A, bảng tính `01_Alpha_Master_Database_Ticket` công khai | Tải được CSV: bảng `CUSTOMERS` 7 khách (Cá Nhân 4, Doanh Nghiệp 2, Đối Tác 1; Hà Nội, TP.HCM, Đà Nẵng, Hải Phòng, Cần Thơ, Đồng Nai), bảng `TICKETS` 14 dòng, **14 cột** (chưa có 3 cột bổ sung của bài 6.8), dữ liệu 10–26/05/2026, loại yêu cầu Khiếu nại 4 / Tư vấn 5 / Bảo hành 5 | Alpha là **công ty cung cấp thiết bị và phần mềm** (máy bơm nước, màn hình, linh kiện, "phần mềm quản lý kho", "gói dịch vụ cao cấp"): một SME thương mại dịch vụ kỹ thuật, không thuộc ngành hẹp nào. Hộp cát được dựng tháng 05/2026, ngay trước khi công bố chủ đề 09/06 |
| **Bài giới thiệu chủ đề 2025 không hề gợi ý đô thị thông minh hay NGSI-LD**, tác giả khác (Tiến Phạm Đức) | Bài 746, 22/09/2025 | Gợi ý trong bài giới thiệu có giá trị dự báo thấp **khi bài do người khác viết**. Năm 2026 bài giới thiệu do chính tác giả giáo trình viết và cụ thể hơn hẳn, nên trọng số cao hơn, nhưng không được coi là chắc |

### 2.3. Xếp hạng sau đợt 2 *(đội)*

| # | Kịch bản đề | Trước đợt 2 | Sau đợt 2 | Căn cứ mới | Nếu đúng thì đội cần gì |
|---|---|---|---|---|---|
| A | **Bám hộp cát**: tái hiện DX-Ticket bằng nguồn mở cho một SME thương mại dịch vụ kỹ thuật kiểu Alpha, **có thể kèm bộ dữ liệu mẫu**, đội mở rộng theo hướng riêng | cao | **rất cao** | Hộp cát có dữ liệu thật, dựng 05/2026 sát ngày công bố; bài giới thiệu nói thực hành trên "cơ sở dữ liệu thực tế của doanh nghiệp"; tác giả chủ đề = tác giả hộp cát | Gói `dx-ticket` đúng 2 bảng, nạp được CSV của BTC, 3 sự kiện, dashboard; phần riêng là ngoại lệ, H%, tác tử |
| C | **Không ép ngành**, ép mô hình H-P-D-I + hộp cát + đo trưởng thành | trung bình | trung bình–cao | Bài báo "mô hình hợp tác 57" coi DX-Lab là phòng thực hành chung cho mọi SME | Như A, thêm bảng hỏi DTI |
| D | **Cơ quan nhà nước / dịch vụ công**, có thể ép từ điển dữ liệu hoặc ontology | thấp–trung bình | trung bình | FDS là GovTech (OpenCPS); tác giả viết nhiều về dữ liệu công, từ điển dữ liệu liên kết, khung kiến trúc dữ liệu quốc gia | Gói lĩnh vực "phản ánh kiến nghị của công dân" (ticket với vai công dân, cán bộ, lãnh đạo xã); lớp xuất dữ liệu theo từ điển dữ liệu dùng chung |
| B | **Hộ kinh doanh chuyển sang kê khai**, hóa đơn điện tử | trung bình–cao | trung bình | Thời sự vẫn đúng, nhưng giáo trình và hộp cát không đi theo hướng này; tác giả không viết về thuế | Thử nghiệm phòng sốc XML hóa đơn giữ nguyên, không đầu tư thêm |
| E | Ngành hẹp khác (logistics, tài chính, chế biến, khách sạn, y tế...) | thấp | thấp | Bài báo nêu logistics, tài chính, chế biến là ngành ưu tiên, nhưng chỉ ở mức định hướng | Gói lĩnh vực mới trong 1 tuần |

**Dự đoán sát nhất mà đội dám viết ra:** *"Xây dựng DX-Lab bằng phần mềm nguồn mở cho một doanh
nghiệp nhỏ và vừa, tái hiện được luồng DX-Ticket của hộp cát (hoặc một luồng nghiệp vụ tương đương do
đội chọn) trên bộ dữ liệu mẫu, đủ bốn không gian H-P-D-I, có cổng nội bộ, SSO, lưu trữ P.A.R.A với định
dạng mở, tự động hóa hướng sự kiện, dashboard, trợ lý AI có phê duyệt của con người; khuyến khích kế
thừa LCDP, dữ liệu mở liên kết, RAG; bắt buộc bảng kê khai giấy phép."* Phần đội không dự đoán được
là **ngành cụ thể** (nếu có) và **một chuẩn kỹ thuật** có thể bị ép thêm; hai chỗ đó giữ nguyên biện
pháp phòng ở mục 3.

Hai nhận xét quan trọng hơn thứ hạng:

- Trong mọi kịch bản, **phần đề bài chắc chắn có** là luồng kiểu ticket với ba vai, Poka-yoke, sự
  kiện, dashboard, tác tử có phê duyệt. Đây chính là lõi của `dac-ta-dx-safety.md` mục 3–10.
- Sau đợt 2, "cú sốc chuẩn" có khả năng nhất không còn là hóa đơn XML mà là **từ điển dữ liệu /
  ontology / dữ liệu liên kết** ở [D], vì đó là chuyên môn của tác giả chủ đề và là "kế thừa 2025".
  Thử nghiệm phòng sốc NGSI-LD ở mục 3 vì thế quan trọng hơn thử nghiệm XML hóa đơn.

---

## 3. Dự báo chuẩn và ràng buộc bắt buộc

| Ứng viên | Nguồn gợi ý | Ước lượng | Chi phí chuẩn bị trước | Đội đã có? |
|---|---|---|---|---|
| Đặc tả DX-Ticket: 2 bảng, 17 cột, 3 sự kiện, máy trạng thái | *(giáo trình)* hộp cát | cao | thấp | Có, DX-Safety đã dựng theo khuôn này |
| **Nạp được bộ dữ liệu mẫu của BTC** (CSV cùng cấu trúc `CUSTOMERS` 7 cột và `TICKETS` 14 cột của Alpha) | *(giáo trình)* bảng tính hộp cát; *(BTC)* mục 2.3 bài giới thiệu | cao | thấp | Chưa; thêm `make seed FROM=<csv>` |
| Từ điển dữ liệu dùng chung / ontology cho thực thể lõi | *(đội)* chuyên môn tác giả chủ đề (`govdata`, `webdata`) | trung bình | trung bình | Chưa; định nghĩa `@context` JSON-LD cho khách hàng, ticket, sự kiện là đủ mức tối thiểu |
| Cấu trúc P.A.R.A và định dạng mở trong `[R]` (`.md`, `.csv`, `.json`, `.parquet`, `.xml`, `.yaml`) | *(giáo trình)* bài 7.3 | cao | thấp | Có trong đặc tả mục 12 |
| Bảng kê khai giấy phép tự rà soát | *(BTC)* Thông báo số 1 HĐGK 2025 | rất cao | trung bình | Đang làm (bộ kiểm toán trong CI) |
| Ít nhất một nền tảng LCDP nguồn mở ở [P] | *(BTC)* đề 2024; chủ đề 2026 nói "kế thừa" | cao | đã chọn | Appsmith CE hoặc Frappe |
| RAG với LLM nguồn mở, tác tử có human-in-the-loop | *(BTC)* đề 2023; *(giáo trình)* bài 8.5 | cao | trung bình | Ollama + Qwen, đặc tả mục 9 |
| Dashboard HPDI / DTI | *(giáo trình)* bài 2.4; bài giới thiệu chủ đề | trung bình | thấp | Có, đặc tả mục 10 |
| Dữ liệu mở liên kết ở [D]: JSON-LD, có thể NGSI-LD hoặc Smart Data Models | *(BTC)* đề 2025; chủ đề 2026 nói "kế thừa LOD" | trung bình | trung bình | Xuất JSON-LD cơ bản trong đặc tả mục 11; NGSI-LD chưa |
| Hóa đơn điện tử XML theo định dạng cơ quan thuế | *(thời sự)*; *(giáo trình)* chương 6 lớp pháp lý | thấp–trung bình | cao | Chưa |
| SSO OIDC bắt buộc | *(giáo trình)* [H] | trung bình | thấp | Keycloak |
| Ràng buộc repo: phần mở rộng nền tảng tách repo riêng | *(BTC)* đề 2024 | trung bình | thấp | Chưa quyết, cần một quy ước |

*(đội)* Bài học 2025 là chuẩn bắt buộc **không thể học trong ba tuần** nếu chưa từng chạm. Vì thế
mỗi dòng "ước lượng ≥ trung bình" mà cột cuối là "chưa" phải có một thử nghiệm nhỏ trước tháng 11,
đủ để biết cần bao nhiêu ngày khi đề ép.

---

## 4. Đánh giá lại đề tài DX-Safety

### 4.1. Cái gì trong DX-Safety là bất biến, cái gì là lĩnh vực

| Thành phần (mục trong `dac-ta-dx-safety.md`) | Thuộc | Sống sót qua kịch bản A–E? |
|---|---|---|
| Bảng sự kiện chỉ ghi thêm, hàm chuyển trạng thái, RLS theo claim Keycloak (3.5, 4, 6) | Lõi | Có |
| Poka-yoke ba lớp, ghi `blocked` (5) | Lõi | Có |
| Bàn phê duyệt ngoại lệ (8) | Lõi | Có; ở kịch bản B ngoại lệ tự nhiên là "bán không xuất hóa đơn", "giảm giá vượt thẩm quyền" |
| Tác tử chín bước, công cụ, cổng phê duyệt (9) | Lõi | Có; đổi tài liệu trong `[R]` |
| Đồng hồ H% từ `events` (10) | Lõi | Có; là lợi thế lớn nhất ở kịch bản C |
| Bảng `incidents` 17 cột, `actions`, enum, SLA (3.2, 3.3) | Lĩnh vực | Đổi tên và cột nghiệp vụ; khuôn 17 cột giữ |
| SOP, seed, kịch bản demo (12, 13) | Lĩnh vực | Viết lại |
| Luồng Node-RED (7) | Nửa | Giữ khung 4 nhịp, đổi điều kiện |

Khoảng 70% khối lượng kỹ thuật là lõi và không phụ thuộc đề. Lựa chọn lĩnh vực chỉ quyết định
30% còn lại và quyết định **câu chuyện trình diễn**.

### 4.2. Ba rủi ro thật của việc chọn an toàn xưởng làm lĩnh vực demo

1. **Xa hộp cát.** Nếu đề bám DX-Ticket (kịch bản A), ban giám khảo sẽ tìm bảng khách hàng, loại
   yêu cầu bảo hành/khiếu nại/tư vấn, CSAT. DX-Safety không có khách hàng; đội phải chứng minh
   ánh xạ, tốn thời gian trình bày.
2. **Xa thời sự.** Nếu đề lấy hộ kinh doanh và hóa đơn (kịch bản B), an toàn xưởng không liên quan
   và phần chưa có (XML hóa đơn) phải làm gấp.
3. **Khó lấy dữ liệu và người xác nhận.** An toàn lao động cần người trong ngành để SLA và mức độ
   không bị bịa. Đội chưa có nguồn này.

Ngược lại, hai lợi thế vẫn đứng vững: chưa đội nào làm, và nó cho lớp ngoại lệ một lý do tồn tại
rất tự nhiên (xin chạy máy khi sự cố mở).

### 4.3. Quyết định đề xuất *(đội)*: một lõi, hai gói lĩnh vực, một thử nghiệm phòng sốc

**Sau đợt bằng chứng 2 và với hạn vòng trường một tháng, đảo thứ tự: gói `dx-ticket` (đúng hộp cát
Alpha, nạp được CSV của BTC) làm trước và là câu chuyện chính; DX-Safety là gói thứ hai, chứng minh
lõi đổi được lĩnh vực.** Lý do: kịch bản A nay là "rất cao", gói `dx-ticket` có sẵn dữ liệu mẫu để
seed, và ban giám khảo cấp trường đọc bài giới thiệu chủ đề sẽ tìm đúng luồng đó. Ba điểm nguyên gốc
(bàn ngoại lệ, đồng hồ H%, tác tử có phê duyệt) chuyển sang DX-Ticket còn tự nhiên hơn: bài 8.5 của
giáo trình đã bắt tác tử **dừng chờ duyệt khi cấp voucher hoặc phát ngôn ra ngoài**, tức là bàn phê
duyệt ngoại lệ chính là hàng đợi đó.

| Việc | Lý do | Chi phí ước tính |
|---|---|---|
| Tách mọi thứ thuộc "lĩnh vực" ở mục 4.1 vào `domains/<tên>/` gồm `domain.yaml` (enum, SLA, ngưỡng, nhãn màn hình), `schema-ext.sql` (cột nghiệp vụ thêm vào khuôn 17 cột), `resources/` (SOP Markdown), `seed/`, `demo.md` | Chứng minh bằng mã rằng lõi độc lập lĩnh vực; khi đề ra chỉ thêm một thư mục | 3–4 ngày, làm ngay khi viết schema |
| Gói `domains/dx-ticket/` đúng đặc tả giáo trình: CUSTOMERS + TICKETS 17 cột, bảo hành/khiếu nại/tư vấn, CSAT, 3 sự kiện; seed từ CSV Alpha; ngoại lệ gồm "cấp voucher vượt thẩm quyền", "gia hạn SLA", "đóng không có hướng xử lý" | Kịch bản A rất cao; là bằng chứng "giải quyết đúng đầu bài" ở tiêu chí #2; có dữ liệu mẫu sẵn | Làm trước, trong `ke-hoach-vong-truong.md` |
| Gói `domains/safety/` theo `dac-ta-dx-safety.md` | Lĩnh vực hiếm, chứng minh lõi đổi được lĩnh vực | Sau vòng trường, 3–4 ngày |
| Thử nghiệm phòng sốc 1: sinh một hóa đơn điện tử dạng XML theo định dạng cơ quan thuế từ một bản ghi mẫu, ký số giả lập, lưu vào `[R]/41-Structured_Data` | Phòng kịch bản B; biết trước cần mấy ngày | 2 ngày, không đưa vào demo |
| Thử nghiệm phòng sốc 2: xuất `events` ra NGSI-LD entity qua một adapter Node-RED, kiểm tra bằng bộ Smart Data Models có sẵn | Phòng "kế thừa 2025" ở [D] | 1–2 ngày |
| Quy ước repo: mọi mở rộng cho nền tảng thượng nguồn (plugin Appsmith, app Nextcloud) để trong repo riêng, repo chính chỉ tham chiếu | Phòng ràng buộc của đề 2024 | nửa ngày, ghi vào `CONTRIBUTING.md` |

Đặc tả DX-Safety không bỏ: 70% nội dung của nó (mục 3.5, 4–10) là đặc tả lõi và áp dụng nguyên cho
gói `dx-ticket`, chỉ đổi tên thực thể.

### 4.4. Điều chỉnh cho các tài liệu hiện có

- `dac-ta-dx-safety.md` mục 1 và 12: thay "sửa ba enum trong `config/domain.yaml`" bằng cơ chế gói
  lĩnh vực ở 4.3; thêm gói `dx-ticket`.
- `nghien-cuu-chu-de-2026.md` mục 6.4: thêm ba việc (gói lĩnh vực, thử nghiệm XML hóa đơn, thử
  nghiệm NGSI-LD).
- `architecture.md`: bản ghi QĐ-007 "Lõi độc lập lĩnh vực, nghiệp vụ là gói cấu hình" với lý do là
  mô hình ba mùa ở mục 1.
- `ROADMAP.md`: mốc "hai gói chạy trên cùng lõi" trước 31/10/2026.

---

## 5. Lịch làm việc suy từ ba mùa

| Mốc | Căn cứ | Việc của đội |
|---|---|---|
| Nay → 30/09 | | Lõi chạy với gói `safety`; release `v0.1.0`; hai thử nghiệm phòng sốc |
| 01/10 → 31/10 | Đề 2025 ra 27/10, đề 2024 ra 20/11 | Gói `dx-ticket`; dashboard HPDI; tài liệu build from source trên máy sạch; `v0.2.0` |
| Đề ra (dự kiến 11/2026) → +3 ngày | | Đọc đề, lập bảng "yêu cầu đề ↔ thành phần đã có ↔ thiếu"; quyết định gói lĩnh vực thứ ba hay chỉnh gói có sẵn |
| +3 ngày → hạn nộp (≈ 3–5 tuần; chấm repo 07–09/12) | Hạn 2025 là 08/12, 2024 là 09/12 | Làm phần thiếu; mọi thứ khác đã xong |
| Meeting giải đáp (2025 tổ chức 18/11) | | Chuẩn bị sẵn 3 câu hỏi ở `research-huong-trien-khai.md` mục 9 |
| 10/12/2026, 7h30–15h30 | Chương trình OLP'26 | Trình diễn 15 phút tại VKU Đà Nẵng |

---

## 6. Tín hiệu cần theo dõi hằng tuần

- vfossa.vn: bài id > 792, chuyên mục Thông báo; olp.vn trang PMNM và tệp `Quick-guide-to-DXOS.pdf`
  (chưa tải được bằng công cụ, cần tải tay).
- icpcvn.com: mở đăng ký khối H.
- Nhóm Telegram BTC lập cho khối PMNM (mùa 2025 có), thường là nơi lộ sớm định dạng đề.
- GitHub: kho mã mới có từ khóa `dx-lab`, `dx-os`, `olp2026`; hiện mới có hai kho (mục 5.5 bản nghiên
  cứu). Nếu xuất hiện kho nào dựng hóa đơn điện tử hoặc NGSI-LD, đó là tín hiệu đội khác biết gì đó.
- Chính sách: Nghị định hoặc Thông tư mới về hóa đơn điện tử hộ kinh doanh có hiệu lực 01/07/2026
  và các hướng dẫn cuối năm; nếu BTC lấy thời sự thì đây là nguồn.

---

## 7. Nguồn

- Đề thi PMNM 2024: https://vfossa.vn/tin-tuc/cong-bo-de-thi-noi-dung-phan-mem-nguon-mo-olympic-tin-hoc-sinh-vien-viet-nam-2024-727.html
- Giới thiệu chủ đề 2024: https://www.vfossa.vn/tin-tuc/gioi-thieu-chu-de-cuoc-thi-phan-mem-nguon-mo-olp-2024-709.html
- Giới thiệu chủ đề 2023: https://vfossa.vn/hoat-dong-cong-dong/gioi-thieu-chu-de-pmnm-olp-2023-679.html
- Kết quả 2023 (mô tả đề): https://vfossa.vn/tin-tuc/olp-2023-tim-ra-doi-vo-dich-hang-muc-phan-mem-nguon-mo-695.html
- Đề thi PMNM 2025: https://vfossa.vn/thong-bao/de-thi-phan-mem-nguon-mo-olp-2025-749.html
- Bỏ thuế khoán từ 01/01/2026: https://vietnamnet.vn/bo-thue-khoan-sang-ke-khai-7-viec-ho-kinh-doanh-can-lam-truoc-1-1-2026-2473487.html ;
  thay đổi hóa đơn điện tử từ 01/07/2026: https://luatvietnam.vn/thue-phi-le-phi/8-thay-doi-lon-ve-hoa-don-dien-tu-doi-voi-ho-kinh-doanh-tu-01-7-2026-565-110602-article.html
- Giáo trình DX-OS chương 1 (rào chắn pháp lý), chương 6 (lớp pháp lý, ngành mở rộng), bài 7.3
  (định dạng mở), hộp cát DX-Lab: https://opendigitransform.gitbook.io/dx-os
- Hộp cát Alpha Corporation: https://sites.google.com/view/alpha-corporation/ ; thư mục P.A.R.A
  https://drive.google.com/drive/folders/1OVUtAc6U6E7mgDiIZLjlAEru4yAGEgnH ; bảng tính
  `01_Alpha_Master_Database_Ticket` (id `1j2r_qx0uzgSZ9IC1NUwvuuzbmFkmKY_SDhJx2emO-34`, tải CSV qua
  `gviz/tq?tqx=out:csv&sheet=TICKETS` và `sheet=CUSTOMERS` ngày 10/09/2026).
- Tác giả và FDS: https://opendigitransform.gitbook.io/dx-os/chia-se-tri-thuc-mo/tai-nguyen-tham-khao ;
  https://via.org.vn/Cong-ty-Co-phan-Phat-trien-Nguon-mo-va-Dich-vu-FDS ; https://opendigitransform.gitbook.io/home
  (mục "Chuyển đổi số doanh nghiệp nhỏ và vừa: Gỡ nút thắt nhân lực từ mô hình đào tạo thực hành",
  Tạp chí KH&CN Việt Nam số 8/2026; mục "Cuộc thi OLP Phần mềm Nguồn mở").
- Giới thiệu chủ đề 2025 (đối chứng): https://vfossa.vn/tin-tuc/gioi-thieu-chu-de-cuoc-thi-phan-mem-nguon-mo-olp-2025-746.html
- Chưa kiểm chứng: thành phần HĐGK 2026 và ai ra đề (bài 751 và 752 không nêu tên); biên bản meeting
  giải đáp 2025 (trang 750 chỉ là thông báo đăng ký). `Quick-guide-to-DXOS.pdf` đã đối chiếu qua bản
  chép của đội khác, trùng bài web 761.
