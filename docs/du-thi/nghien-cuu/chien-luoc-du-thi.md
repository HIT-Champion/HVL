# Chiến lược dự thi OLP PMNM 2026 — hướng đi và căn cứ

> Lập ngày 09/09/2026. Tài liệu này là **quyết định định hướng của đội**, dựa trên bằng chứng thu
> được từ mùa OLP 2025 và giáo trình DX-OS. Nó bổ sung và điều chỉnh
> [`research-huong-trien-khai.md`](research-huong-trien-khai.md) — xem mục 7.
>
> Phân biệt rõ trong toàn bộ tài liệu: *(BTC)* là yêu cầu/tuyên bố của Ban tổ chức,
> *(đội)* là nhận định và lựa chọn của đội.

---

## 1. Kết luận: bài toán thật của cuộc thi

**Giáo trình DX-OS do BTC chỉ định làm tài liệu tham khảo dạy dựng DX-Lab hoàn toàn bằng
phần mềm độc quyền. Thể lệ lại bắt buộc sản phẩm dự thi phải là phần mềm nguồn mở
OSI-approved. Khoảng trống giữa hai điều đó chính là bài toán.**

Vậy hướng đi của đội:

> **DX-Lab nguồn mở = dựng lại đúng mô hình H-P-D-I và 6 điểm chạm của "Hộp cát DX-Lab"
> trong giáo trình, nhưng thay toàn bộ động cơ Google Workspace / AppSheet / Looker Studio /
> Gemini / n8n bằng các thành phần có giấy phép OSI-approved — kèm một bộ kiểm toán
> giấy phép tự động chứng minh điều đó.**

Đây không phải cách diễn giải rộng rãi của đề bài. Nó bám sát ba thứ cùng lúc: mô hình BTC dạy,
ràng buộc giấy phép BTC bắt buộc, và điểm yếu BTC vừa công khai của mùa trước.

---

## 2. Bằng chứng thu được

### 2.1. Giáo trình DX-OS dạy một stack độc quyền *(kiểm chứng trực tiếp)*

Mục [Hộp cát DX-Lab][hopcat] định nghĩa DX-Lab là môi trường "người học tự tay lắp ráp hệ sinh
thái chuyển đổi số bằng **công cụ phi mã nguồn**", gồm 6 điểm chạm công nghệ. Mục
[4.2 Hệ sinh thái Lõi][mucyeu42] liệt kê đầy đủ sản phẩm:

| Không gian | Công cụ giáo trình dùng | Giấy phép |
|---|---|---|
| [H] | Google Admin/Gmail, Keep, Tasks, Calendar, Drive/Docs, Google Sites | độc quyền |
| [H] | Telegram Supergroup | dịch vụ máy chủ độc quyền |
| [P] | Google Sheets, Google Forms | độc quyền |
| [P] | AppSheet | độc quyền |
| [P] | Google Apps Script | độc quyền |
| [P] | **n8n** | **Sustainable Use License 1.0 — không phải OSI** |
| [D] | Looker Studio | độc quyền |
| [I] | NotebookLM, Gemini Workspace & Gems | độc quyền |

**Không một thành phần nào trong hộp cát của giáo trình dùng được nguyên trạng cho bài dự thi.**

Riêng n8n cần nói rõ vì hay bị nhầm là nguồn mở: giấy phép của nó ghi *"You may use or modify
the software only for your own internal business purposes or for non-commercial or personal
use"* và *"You may distribute the software or provide it to others only if you do so free of
charge for non-commercial purposes"* — hai điều khoản hạn chế mục đích sử dụng này khiến nó
không thể là giấy phép OSI-approved [[9]].

### 2.2. Mùa 2025: gần một nửa số đội trượt đúng chỗ này *(BTC)*

[Thông báo số 1 của Hội đồng Giám khảo PMNM OLP 2025][tb1] (12/12/2025) cho biết **gần một nửa
trong 30 đội dự thi đã dùng mô-đun không phải phần mềm nguồn mở**. BTC phải điều chỉnh cách
chấm giữa chừng: thay vì mất toàn bộ điểm PoF, các đội vi phạm chỉ bị trừ cố định **10 điểm** ở
mục giấy phép và vẫn được xét giải.

BTC nêu rõ yêu cầu **từ mùa sau** — tức chính mùa 2026 này:

1. Các đội phải **tự rà soát** (thủ công hoặc bằng công cụ tự động) thư viện/module đã dùng;
2. Phải **cung cấp bảng khai minh bạch** về giấy phép và nguồn gốc module ngoài;
3. **Chế tài cao hơn** với vi phạm cố ý hoặc khai báo sai/thiếu.

Bài giới thiệu chủ đề 2026 cũng nhắc lại điểm này: *"Cấp phép hợp lệ... Nếu vi phạm sẽ bị trừ
điểm nặng"* [[2]].

*(đội)* Đây là cơ hội chênh lệch điểm lớn nhất còn lại. Nếu ~50% thí sinh mất 10 điểm ở chỗ mà
đội đi qua sạch, đội có lợi thế bằng đúng một bậc giải — mà không cần viết thêm một dòng
nghiệp vụ nào.

### 2.3. Đề thi tháng 11 sẽ cụ thể hơn nhiều so với bài giới thiệu chủ đề *(kiểm chứng qua mùa 2025)*

So sánh mùa 2025 cho thấy khoảng cách giữa hai văn bản:

| | Giới thiệu chủ đề (22/09/2025) | Đề thi thật (27/10/2025) |
|---|---|---|
| Nội dung | "Ứng dụng dữ liệu mở liên kết phục vụ CĐS"; nêu FAIR, RDF, SPARQL, JSON-LD, DBpedia/Wikidata | Ứng dụng **đô thị thông minh**; **bắt buộc** ontology SOSA/SSN (W3C), API **NGSI-LD** (ETSI), **FiWARE SmartDataModels**; nguồn dữ liệu OpenWeatherMap/OpenAQ/OpenStreetMap/GTFS; hai vai trò quản trị viên + công dân |

**Không thể suy ra đề thật từ bài giới thiệu chủ đề.** Đề 2025 chốt cả lĩnh vực nghiệp vụ lẫn
bộ chuẩn kỹ thuật bắt buộc — những thứ không hề xuất hiện trong bài giới thiệu trước đó.

Kiểm chứng thêm hai mùa trước đó (bổ sung 10/09/2026) cho thấy đây là mô hình ổn định, không
phải ngoại lệ của một năm:

| Mùa | Giới thiệu chủ đề | Đề thi thật | Cái đề thêm vào |
|---|---|---|---|
| 2023 | "Ứng dụng mô hình ngôn ngữ lớn" (06/09/2023). Nêu Hugging Face, LangChain, Llama 2, PhoBERT; không nêu ngành [[de23]] | Hỏi đáp tri thức pháp luật trên **Bộ pháp điển và CSDL văn bản quy phạm pháp luật** [[kq23]] | Lĩnh vực và nguồn dữ liệu bắt buộc |
| 2024 | "Nền tảng low-code" (08/08/2024). Liệt kê Budibase, Appsmith, NocoBase, n8n...; nói chung về SME [[cd24]] | Ứng dụng **kết nối cộng đồng ứng phó khẩn cấp** (dịch bệnh, bão lũ), công bố 20/11/2024 sau bão Yagi; bắt buộc ít nhất một LCDP nguồn mở; phần mở rộng nền tảng phải tách repo riêng; nộp 17:00 09/12 [[de24]] | Lĩnh vực theo thời sự, ràng buộc tổ chức repo |
| 2025 | "Dữ liệu mở liên kết" (22/09/2025) | Đô thị thông minh; SOSA/SSN, NGSI-LD, FiWARE Smart Data Models; nguồn dữ liệu và hai vai người dùng (27/10/2025) | Lĩnh vực, ba chuẩn kỹ thuật, nguồn dữ liệu, vai |

Kho mã của các đội (xem `nghien-cuu-chu-de-2026.md` mục 5) xác nhận hệ quả: 2023 gần như toàn
bộ là pháp điển, 2024 toàn bộ là cứu trợ trên Appsmith/Budibase/NocoBase, 2025 toàn bộ là ngập
lụt, không khí, giao thông trên NGSI-LD. Không đội nào làm lệch đề.

*(đội)* Suy ra cho 2026: chủ đề đã chốt công nghệ (DX-OS, H-P-D-I, Open-Core). Đề tháng 11 sẽ
thêm **một lĩnh vực cụ thể**, rất có thể **một chuẩn hoặc nguồn dữ liệu bắt buộc**, và ràng buộc
hồ sơ giấy phép. Khoảng cách từ đề tới hạn nộp ba mùa là 3–6 tuần. Xem dự báo chi tiết ở
`du-bao-de-thi-2026.md`.

Lịch mùa 2025 cũng cho biết nhịp làm việc thực tế: đề ra 27/10 → meeting giải đáp trực tuyến
18/11 → **nộp bài qua email 17:00 ngày 08/12** → chấm và trình diễn 15 phút. Tức khoảng
**6 tuần** từ lúc có đề đến lúc nộp.

*(đội)* Áp vào 2026: đề ra tháng 11, chấm repo 7–9/12 → cửa sổ làm bài cũng chỉ khoảng 4–6 tuần.

### 2.4. Mặt bằng điểm *(BTC)*

Kết quả mùa 2025: 28 đội dự thi, vô địch **88/100** (TLU-SKTT1, ĐH Thủy Lợi), hai giải Nhất
84,5, giải Nhì 81,5–83,5 [[kq]].

*(đội)* Suy ra: PoF 50 điểm là phần khách quan, chấm trên repo, có thể ăn gần trọn nếu chuẩn bị
kỹ. Ăn trọn 50/50 PoF thì chỉ cần khoảng 35/50 điểm sản phẩm là đã ngang nhóm giải Nhất.
Đây là lý do đội đầu tư PoF trước, sản phẩm sau.

---

## 3. Hệ quả chiến lược

**(a) Không đặt cược vào một lĩnh vực nghiệp vụ cụ thể.**
Mục 2.3 cho thấy đề sẽ tự chọn lĩnh vực. Xây sẵn một sản phẩm CSKH/bảo hành hoàn chỉnh là đặt
cược vào thứ nhiều khả năng bị đề thay. Cái tái sử dụng được bất kể đề ra gì là **hạ tầng
H-P-D-I và lớp keo**; cái phải làm sau khi có đề là **lớp nghiệp vụ mỏng** bên trên.

Điều này **điều chỉnh** đề xuất ở `research-huong-trien-khai.md` mục 1: vẫn dùng một nghiệp vụ
làm kịch bản chứng minh, nhưng coi nó là **phụ tải thay được**, không phải sản phẩm.

**(b) Thiết kế để thay lớp nghiệp vụ trong 4–6 tuần.**
Mọi thứ đội dựng từ giờ tới tháng 11 phải trả lời được: *nếu đề bắt làm lĩnh vực khác, phần này
có còn dùng được không?* Nếu không, hạ ưu tiên.

**(c) Kiểm toán giấy phép là hạng mục sản phẩm, không phải việc giấy tờ.**
BTC đã nói thẳng sẽ đòi bảng khai giấy phép (2.2). Đội làm nó thành **công cụ chạy được trong
CI**, sinh bảng kê tự động từ image và mã nguồn thực tế. Nó phục vụ đồng thời tiêu chí #2
(xung đột giấy phép), #5 (làm rõ thư viện/gói đính kèm), #10 (công cụ hỗ trợ công bố kèm theo)
và là một phần của tính nguyên gốc ở #7.

**(d) Bản đồ thay thế "giáo trình → nguồn mở" chính là tính nguyên gốc.**
Tiêu chí #2 yêu cầu sản phẩm *"giải quyết đúng đầu bài"*, #7 chấm *tính nguyên gốc của giải pháp
kỹ thuật*. Việc chứng minh mô hình H-P-D-I của giáo trình chạy được **không cần bất kỳ thành
phần độc quyền nào** vừa đúng đầu bài, vừa là đóng góp không ai làm sẵn — và trả lời trực tiếp
sự cố mùa 2025.

---

## 4. Bản đồ thay thế: từ hộp cát giáo trình sang nguồn mở

### 4.0. Sáu điểm chạm công nghệ của hộp cát *(giáo trình)*

Giáo trình định nghĩa hộp cát DX-Lab bằng đúng **6 điểm chạm**, và thiết kế chúng thành một
vòng khép kín mà người học đi qua bằng **ba vai** khác nhau: khách hàng → nhân sự vận hành →
lãnh đạo.

| # | Điểm chạm | Vai trò trong giáo trình | Vai người học đóng | Không gian |
|---|---|---|---|---|
| 1 | **Cấu trúc lưu trữ P.A.R.A** | Quy hoạch không gian lưu trữ, phân định ranh giới Dự án / Vùng trách nhiệm / Tài nguyên / Lưu trữ tĩnh | tổ chức thư mục | [H] |
| 2 | **DX-Portal** | Cổng thông tin nội bộ, tập trung bảng tin, quy trình, tài liệu đào tạo — "Nguồn sự thật duy nhất" | dựng cổng | [H] |
| 3 | **Biểu mẫu thu thập yêu cầu** | Điểm chạm ngoại vi, có rào chắn xác thực định dạng (số điện thoại, email) | **khách hàng** | [P] |
| 4 | **Cơ sở dữ liệu lõi** | Tầng lưu trữ backend: cấu trúc dữ liệu, khóa chính/khóa ngoại | thiết kế CSDL quan hệ | [D] |
| 5 | **Ứng dụng quản lý đa nhiệm** | Giao diện vận hành: nút chuyển trạng thái, rào chắn Poka-yoke | **nhân sự vận hành** | [P] |
| 6 | **Bảng điều khiển quản trị** | Dashboard giám sát thời gian thực (DSS), truy vấn chéo chỉ số | **lãnh đạo** | [D]/[I] |

Ba thứ **nằm ngoài** 6 điểm chạm nhưng vẫn thuộc hộp cát: trục truyền thông (Telegram), trục tự
động hóa (Apps Script + n8n) và lớp AI (NotebookLM, Gemini). Chúng bao quanh 6 điểm chạm chứ
không nằm trong danh sách.

*(đội)* Giá trị của danh sách này: nó là **bản đặc tả cụ thể duy nhất mà đội có được trước khi có
đề tháng 11** — đủ để bắt tay dựng ngay, và độc lập với lĩnh vực nghiệp vụ mà đề sẽ chọn. Vòng
ba vai (khách hàng → vận hành → lãnh đạo) cũng dùng thẳng được làm **kịch bản trình diễn 15 phút**
ở chung kết.

### 4.1. Bảng thay thế

Cột "Trạng thái" ghi rõ mức kiểm chứng, để không nhầm giữa đã xác minh và mới là ứng viên.
Cột "ĐC" đánh dấu dòng nào thuộc 6 điểm chạm ở mục 4.0.

| ĐC | Thành phần | Công cụ độc quyền | Thay bằng *(đội đề xuất)* | Giấy phép | Trạng thái |
|---|---|---|---|---|---|
| — | Định danh tập trung (SSO) | Google Admin/Gmail | Keycloak | Apache-2.0 | ứng viên, giấy phép đã ghi nhận ở research |
| **1** | Lưu trữ P.A.R.A | Google Drive | Nextcloud Files | AGPL-3.0 | ứng viên |
| **2** | DX-Portal (cổng nội bộ) | Google Sites | Nextcloud Collectives | AGPL-3.0 | ứng viên |
| — | Ghi chú / nhiệm vụ / lịch | Keep, Tasks, Calendar | Nextcloud Notes/Deck/Calendar | AGPL-3.0 | ứng viên |
| — | Truyền thông tức thời | Telegram Supergroup | Nextcloud Talk | AGPL-3.0 | ứng viên |
| **3** | Biểu mẫu thu thập yêu cầu | Google Forms | lớp low-code ở ĐC 5 | — | theo ĐC 5 |
| **4** | CSDL lõi | Google Sheets | PostgreSQL | PostgreSQL License | **đã chốt** (QĐ-002) |
| **5** | Ứng dụng quản lý đa nhiệm | AppSheet | Frappe / Appsmith — **còn mở** | MIT / Apache-2.0 | Appsmith Apache-2.0 **đã xác minh** |
| — | Trục tự động hóa | Apps Script + **n8n** | **Node-RED** | Apache-2.0 | ứng viên; n8n **đã xác minh là không dùng được** |
| **6** | Bảng điều khiển quản trị | Looker Studio | Apache Superset | Apache-2.0 | ứng viên |
| — | AI nội bộ / RAG | NotebookLM, Gemini | Ollama + pgvector + khung RAG | MIT / PostgreSQL License | ứng viên; **giấy phép model phải xét riêng** |

Chọn Nextcloud cho các điểm chạm 2–5 là chủ ý *(đội)*: một nền tảng thay được bốn công cụ
Google, giảm số dịch vụ phải dựng và số giấy phép phải kiểm — quan trọng với ràng buộc RAM và
với chính bảng kiểm toán ở mục 3(c).

### 4.2. Bẫy giấy phép đã phát hiện

Đã tự kiểm tra trong phiên nghiên cứu này:

| Phần mềm | Kết luận |
|---|---|
| **n8n** | Sustainable Use License 1.0 — hạn chế mục đích sử dụng và phân phối. **Không dùng.** Đây là bẫy nguy hiểm nhất vì chính giáo trình dạy nó. |
| **Budibase** | Nhiều giấy phép trong một repo: GPLv3 cho phần chính, **BSL cho tính năng trả phí**, MPL-2.0 cho mã client. **Không dùng** — BSL không phải OSI. |
| **Mattermost** | Đa giấy phép: AGPL-3.0 **hoặc** giấy phép thương mại cho mã nguồn; MIT cho bản biên dịch; Apache-2.0 cho admin tools. Dùng được nhưng phải khai rõ từng phần — thêm việc mà không thêm giá trị so với Nextcloud Talk. |
| **Appsmith** | Apache-2.0 ở tệp LICENSE. Sạch. *Chưa rà toàn bộ cây mã xem có thư mục enterprise riêng không.* |
| **NocoDB** | **Chưa xác minh được** trong phiên này. Phải kiểm trước khi cân nhắc. |

Ghi nhận từ `research-huong-trien-khai.md`, chưa tự kiểm lại trong phiên này: Flowise tách phần
enterprise sang giấy phép thương mại; Metabase có bản OSS AGPL và bản enterprise thương mại.

> **Quy tắc rút ra *(đội)*:** không kết luận giấy phép từ README, badge hay bài giới thiệu. Chỉ
> kết luận sau khi đọc tệp LICENSE của **đúng phiên bản sẽ dùng**, và rà xem repo có thư mục
> `ee/` hoặc `enterprise/` mang giấy phép khác không. Đây chính là lỗi đã hạ nửa số đội mùa 2025.

---

## 5. Việc làm ngay và việc phải chờ đề

### 5.1. Tháng 9 — đóng các rủi ro không phụ thuộc đề

Toàn bộ hạng mục dưới đây có giá trị bất kể đề tháng 11 ra gì.

| Ưu tiên | Việc | Đạt khi |
|---|---|---|
| 1 | **Sửa các lỗi khung hiện có**: `make build` chưa build gì, `make seed` sẽ lỗi, README còn `<TODO-org>` và hứa cổng web chưa tồn tại | `git clone` trên máy sạch → `make check && make build && make up` chạy đúng như README mô tả |
| 2 | **Chứng minh build từ mã nguồn** cho ít nhất một thành phần đội kiểm soát; lập bảng phạm vi build từng thành phần | Có log build thật; nói rõ phần nào build từ source, phần nào dùng image ghim digest, và vì sao |
| 3 | **Bộ kiểm toán giấy phép tự động** sinh `DEPENDENCIES.md` từ image + mã nguồn thực tế, chạy trong CI | CI fail khi có thành phần giấy phép không nằm trong danh sách cho phép |
| 4 | **Repo có dấu vết dùng thật**: commit trải đều, issue mở và đóng thật, release `v0.1.0` có `.tar.gz` + `.sha256` | Tiêu chí #1 và #3 không còn rủi ro; xem [`pof-checklist.md`](../pof-checklist.md) |
| 5 | **Dựng thử và đo** khối [H] (Keycloak + Nextcloud): SSO thật, ánh xạ vai trò, đăng xuất | Biết con số RAM/thời gian dựng thật, thay cho giả định 8 GB |

Hạng mục 4 gấp: repo hiện mới có **một commit duy nhất, không tag, không release**, trong khi mức
trừ nặng nhất của tiêu chí #1 là *"có hệ thống quản lý mã nguồn nhưng trên thực tế không được
sử dụng"* (−5). Rủi ro này tăng theo từng ngày không commit và không thể bù vào tháng 12.

### 5.2. Tháng 10 — một lát cắt xuyên bốn trục, cố ý mỏng

Chọn **một** nghiệp vụ nhỏ, chạy trọn `[H] → [P] → [D] → [I]`, với mục tiêu **chứng minh lớp
keo**, không phải chứng minh nghiệp vụ:

- [P] biểu mẫu low-code + chặn dữ liệu sai **ở backend**, phát sự kiện có cấu trúc
- [D] ID thống nhất, đồng bộ, một bản xuất JSON-LD, dashboard Superset
- [I] RAG trên tài liệu ở [H], trích dẫn nguồn, dừng lại xin người duyệt khi vượt quyền

Giữ ranh giới nghiệp vụ/nền tảng rõ ràng để tháng 11 thay được phần nghiệp vụ mà không đụng nền.

*(đội)* Nghiệp vụ dùng thử vẫn là CSKH/bảo hành như `research-huong-trien-khai.md` đề xuất — vì
giáo trình có sẵn bài mẫu DX-Ticket nên đỡ công đặc tả — nhưng **coi là phụ tải thay được**.

Phần [D] giữ ánh xạ dữ liệu liên kết: đề 2025 đã ép LOD rất sâu (SOSA/SSN, NGSI-LD) và bài chủ
đề 2026 vẫn nhắc LOD như một trong ba nền kế thừa [[2]]. Chuẩn bị sẵn năng lực JSON-LD là bảo
hiểm rẻ.

### 5.3. Tháng 11 — bám đề, và dự phòng cú sốc chuẩn kỹ thuật

Khi có đề: đối chiếu lại lĩnh vực, chức năng, cách nộp; **dự trù đề ép một bộ chuẩn kỹ thuật cụ
thể chưa từng nhắc trong bài giới thiệu chủ đề** (như NGSI-LD/FiWARE năm 2025) và chừa 1–2 tuần
cho việc học và tích hợp chuẩn đó.

Theo dõi kênh BTC: mùa 2025 có buổi giải đáp trực tuyến sau khi ra đề. Các câu hỏi ở
`research-huong-trien-khai.md` mục 9 (phạm vi Building From Source, cách xét bundling khi phát
hành image, cách chấm module nằm ở repo riêng) nên hỏi tại đó.

---

## 6. Rủi ro còn lại

| Rủi ro | Mức | Xử lý |
|---|---|---|
| Đề tháng 11 đổi lĩnh vực, phần nghiệp vụ tháng 10 thành bỏ | cao | Giữ nghiệp vụ mỏng và tách khỏi nền (mục 3b) |
| Đề ép bộ chuẩn kỹ thuật lạ | trung bình–cao | Chừa quỹ thời gian tháng 11; sẵn năng lực JSON-LD |
| AGPL của Nextcloud lan sang mã đội | trung bình | Chỉ giao tiếp qua mạng/API, không liên kết mã; ghi rõ trong `DEPENDENCIES.md` |
| Bộ đủ 4 trục + LLM không chạy nổi trên 8 GB | trung bình | Đo thật ở mục 5.1(5); hạ mục tiêu xuống profile chạy được, hoặc dùng LLM qua API ngoài với model có giấy phép rõ |
| Phạm vi "Building From Source" bị hiểu khác BTC | trung bình | Lập bảng phạm vi build minh bạch; hỏi BTC tại buổi giải đáp |
| Giấy phép **model AI** ≠ giấy phép runtime | trung bình | Kiểm riêng model sinh văn bản và model embedding; đưa vào bảng kiểm toán |

---

## 7. Điều chỉnh với các tài liệu hiện có

- [`research-huong-trien-khai.md`](research-huong-trien-khai.md) — giữ nguyên phần khảo sát công
  cụ và bẫy giấy phép (vẫn đúng và hữu ích). **Điều chỉnh**: hạ CSKH/bảo hành từ *domain của sản
  phẩm* xuống *phụ tải chứng minh thay được* (mục 3a ở đây). Câu hỏi cho BTC ở mục 9 nay đã có
  kênh để hỏi (mục 5.3).
- [`architecture.md`](../../architecture.md) — cần sửa hai chỗ: (1) lệnh cấm fork tuyệt đối đang được
  trình bày như ràng buộc bắt buộc, thực tế là chính sách của đội; (2) QĐ-002 ép mọi ứng dụng
  dùng chung PostgreSQL sẽ vỡ nếu chọn Frappe (chạy MariaDB). Bổ sung bản đồ thay thế ở mục 4
  vào phần "Bản đồ công cụ".
- [`pof-checklist.md`](../pof-checklist.md) — bổ sung một dòng cho yêu cầu mới của BTC ở mục 2.2:
  bảng khai giấy phép và nguồn gốc module ngoài, sinh tự động.
- [`olp-2026-brief.md`](../olp-2026-brief.md) — bổ sung mục 2.2 (sự cố giấy phép mùa 2025 và yêu cầu
  siết cho mùa 2026); đây là thông tin của BTC mà bản tóm tắt hiện chưa có.

---

## 8. Nguồn

Kiểm chứng trực tiếp trong phiên nghiên cứu ngày 09/09/2026: hai bài VFOSSA 2026 (bản lưu cục
bộ), bốn bài VFOSSA mùa 2025, mục lục và ba mục nội dung của giáo trình DX-OS, bốn tệp LICENSE
thượng nguồn. **Chưa build hay chạy thử bất kỳ tổ hợp nào được đề xuất ở mục 4.**

[1]: https://vfossa.vn/tin-tuc/the-le-olp-phan-mem-nguon-mo-nam-2026-760.html "Thể lệ OLP PMNM 2026"
[2]: https://vfossa.vn/tin-tuc/gioi-thieu-mo-hinh-dx-os-va-chu-de-cuoc-thi-phan-mem-nguon-mo-olp-2026-761.html "Giới thiệu mô hình DX-OS và chủ đề OLP 2026"
[tb1]: https://vfossa.vn/tin-tuc/thong-bao-so-1-pmnm-olp-2025-752.html "Thông báo số 1 từ Hội đồng Giám khảo PMNM OLP 2025"
[de2025]: https://vfossa.vn/tin-tuc/de-thi-phan-mem-nguon-mo-olp-2025-749.html "Đề thi PMNM OLP 2025"
[cd2025]: https://vfossa.vn/tin-tuc/gioi-thieu-chu-de-cuoc-thi-phan-mem-nguon-mo-olp-2025-746.html "Giới thiệu chủ đề OLP 2025"
[kq]: https://vfossa.vn/tin-tuc/cong-bo-ket-qua-phan-thi-phan-mem-nguon-mo-753.html "Kết quả PMNM OLP 2025"
[mt2025]: https://vfossa.vn/tin-tuc/meeting-online-trao-doi-tu-van-giai-dap-olp-2025-khoi-thi-pmnm-750.html "Meeting giải đáp OLP 2025"
[hopcat]: https://opendigitransform.gitbook.io/dx-os/hop-cat-dx-lab "Hộp cát DX-Lab — giáo trình DX-OS"
[mucyeu42]: https://opendigitransform.gitbook.io/dx-os/phan-ii-xay-dung-he-dieu-hanh/chuong-4-kien-truc-dx-lab-tram-khong-gian-thuc-thi/4.2.-he-sinh-thai-loi-dong-co-all-in-one "DX-OS mục 4.2 — Hệ sinh thái Lõi"
[9]: https://github.com/n8n-io/n8n/blob/master/LICENSE.md "n8n Sustainable Use License"
[bud]: https://github.com/Budibase/budibase/blob/master/LICENSE "Budibase LICENSE"
[app]: https://github.com/appsmithorg/appsmith/blob/release/LICENSE "Appsmith LICENSE"
[mm]: https://github.com/mattermost/mattermost/blob/master/LICENSE.txt "Mattermost LICENSE"
[de23]: https://vfossa.vn/hoat-dong-cong-dong/gioi-thieu-chu-de-pmnm-olp-2023-679.html "Giới thiệu chủ đề PMNM OLP 2023"
[kq23]: https://vfossa.vn/tin-tuc/olp-2023-tim-ra-doi-vo-dich-hang-muc-phan-mem-nguon-mo-695.html "Kết quả PMNM OLP 2023"
[cd24]: https://www.vfossa.vn/tin-tuc/gioi-thieu-chu-de-cuoc-thi-phan-mem-nguon-mo-olp-2024-709.html "Giới thiệu chủ đề PMNM OLP 2024"
[de24]: https://vfossa.vn/tin-tuc/cong-bo-de-thi-noi-dung-phan-mem-nguon-mo-olympic-tin-hoc-sinh-vien-viet-nam-2024-727.html "Đề thi PMNM OLP 2024"
