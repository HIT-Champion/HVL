# Nghiên cứu chủ đề OLP PMNM 2026 — kiểm chứng trực tuyến ngày 09/09/2026

> Tài liệu này là kết quả một phiên nghiên cứu độc lập, đối chiếu lại toàn bộ giả định trong
> [`olp-2026-brief.md`](../olp-2026-brief.md), [`chien-luoc-du-thi.md`](chien-luoc-du-thi.md) và
> [`research-huong-trien-khai.md`](research-huong-trien-khai.md) bằng nguồn trực tuyến:
> vfossa.vn và olp.vn (tin sau 09/06/2026), toàn văn 82 trang giáo trình DX-OS, tệp LICENSE thật
> của hơn 60 công cụ ứng viên, và 52 kho mã của các đội mùa trước cùng 2 đội mùa 2026.
>
> Quy ước: *(BTC)* là yêu cầu của Ban tổ chức, *(giáo trình)* là nội dung giáo trình DX-OS,
> *(đội)* là nhận định của đội. Mục nào chưa kiểm chứng được sẽ ghi rõ.

---

## 0. Kết luận ngắn

1. **Chưa có thông tin mới nào về khối PMNM sau 09/06/2026.** Hai bài id 760 và 761 vẫn là tài
   liệu chính thức mới nhất. Đề thi hẹn tháng 11/2026. OLP'26 lần thứ 35 tổ chức **8–11/12/2026
   tại VKU Đà Nẵng**; hackathon khối PMNM diễn ra **7h30–15h30 thứ Năm 10/12/2026**.
2. **Giáo trình DX-OS có một đặc tả cụ thể duy nhất: luồng DX-Ticket** với 2 bảng, 17 cột, máy
   trạng thái 3 bước, Poka-yoke 3 lớp, 3 webhook sự kiện và bộ KPI dashboard. Đây là thứ nên dựng
   ngay bằng nguồn mở, vì đề thi tháng 11 gần như chắc chắn lấy giáo trình làm khung.
3. **Giáo trình không hề nhắc Linked Open Data, JSON-LD hay RDF.** Ý "kế thừa LOD của OLP 2025"
   chỉ có trong bài giới thiệu chủ đề. Giữ JSON-LD ở mức "bảo hiểm rẻ", không đầu tư sâu.
4. **Giáo trình có mục "Vượt ngưỡng" tự gợi ý công cụ nguồn mở** (Outline, Zammad, ERPNext,
   Superset, Metabase, Airbyte, Milvus, Chroma, LangGraph...). Một số trong đó **không đạt OSI**
   (Outline là BUSL, Airbyte là Elastic License). Không được chép danh sách này nguyên trạng.
5. **Bẫy giấy phép mới của mùa 2026: NocoDB.** Từ bản 0.301.0 (09/01/2026) NocoDB đổi sang
   Sustainable Use License, đúng mô hình n8n. Ngoài ra Dify, Open WebUI (từ v0.6.6), Camunda 8
   đều không còn OSI thuần. Nhiều công cụ khác đóng mã EE độc quyền thẳng vào image cộng đồng.
6. **Công thức ánh xạ H-P-D-I của giáo trình là thứ có thể biến thành tính năng nguyên gốc**:
   `P% = DTI_P × P_supp × 30%`, `H% = 100 − (P+D+I)`. Một đội 2026 đã có công cụ chấm HPDI theo
   bảng hỏi (mục 5.5); phiên bản tính tự động từ dữ liệu vận hành thật của DX-Lab thì chưa thấy ai làm.
7. **Repo hiện tại đạt chuẩn khung nhưng còn trống**: 1 commit, 0 issue, 0 release, Compose chỉ có
   PostgreSQL. Rủi ro lớn nhất về điểm lúc này là tiêu chí #1 (*"có repo nhưng không dùng"*, −5).
8. **Mặt bằng 52 kho mã mùa trước thấp ở đúng các mức trừ PoF** (mục 5): 30/46 thiếu header, 2/52 có
   NOTICE, 2/52 có mục build from source, 40/52 viết cứng `localhost`, gần như không ai đính gói phát
   hành. Hai đội 2026 đã công khai kho mã (21 và 131 commit) và một đội đã làm chấm điểm HPDI.

---

## 1. Trạng thái repo tại 09/09/2026 (đọc mã nguồn)

| Hạng mục | Thực tế | Đánh giá |
|---|---|---|
| Kho mã | `github.com/HIT-Champion/Signet`, **công khai**, Issues đã bật | Đạt điều kiện cần của tiêu chí #1 |
| Lịch sử | **1 commit** (15/06/2026), 1 nhánh làm việc `hoangnh/docs/brief`, 0 tag, 0 release, 0 issue | Rủi ro −5 ở #1 và −5 ở #3 nếu không đổi |
| Giấy phép | `LICENSE` toàn văn Apache-2.0, `NOTICE` có mục đích giấy phép, `scripts/license-header.sh check` **sạch** trên toàn bộ tệp | Đạt #2 ở mức khung |
| Build | `Makefile` gọi `docker compose --profile all build` nhưng `docker-compose.yml` chỉ có 1 dịch vụ `postgres` dùng `image:`; không có `build:` nào | `make build` hiện **không build gì**; chưa chứng minh được #4 |
| Seed | `make seed` thoát 0 với thông báo "chưa có thư mục seed/" | README hứa "nạp dữ liệu mẫu" nhưng chưa có |
| CI | 3 job: license, build (chỉ `compose config`), docs | Kiểm tra hình thức, chưa kiểm tra chạy được |
| Release | `scripts/release.sh` + workflow tạo `.tar.gz` + `.sha256` từ tag SemVer | Đúng hướng, chưa chạy lần nào |
| Tài liệu | README còn `<TODO-org>`; `DEPENDENCIES.md` toàn dòng *chưa chốt*; `architecture.md` có 3 bản ghi quyết định | Đủ khung, thiếu nội dung |
| Máy dev hiện tại | Docker 29.1.3 nhưng **thiếu plugin `docker compose`** | Chưa dựng thử được trên máy này |

Ba tài liệu phân tích trong `docs/` (brief, chiến lược, research) có chất lượng tốt và phân biệt rõ
yêu cầu BTC với nhận định đội. Các mục sau đây bổ sung hoặc điều chỉnh chúng bằng bằng chứng mới.

---

## 2. Tình hình cuộc thi đến 09/09/2026 *(BTC, đã fetch)*

### 2.1. Không có cập nhật mới cho khối PMNM

Đã quét toàn bộ bài id 762–792 trên vfossa.vn, các chuyên mục Tin tức / Thông báo / Sự kiện /
tag OLP, và olp.vn. Kết quả: toàn bộ bài sau 09/06 là tin hội thảo bản quyền 25/08/2026, tài trợ
và Software Freedom Day 19/09/2026. **Không có đề thi, FAQ, form đăng ký hay thông báo bổ sung
nào cho PMNM 2026.**

### 2.2. Thông tin mới lấy được từ olp.vn

| Nguồn | Nội dung |
|---|---|
| Thông báo số 1 OLP/ICPC 2026 (21/08/2026) | OLP'26 lần thứ 35, **8–11/12/2026 tại Trường ĐH CNTT&TT Việt-Hàn (VKU), Đà Nẵng**; khối PMNM ký hiệu (H); đăng ký qua icpcvn.com; không có hạn riêng cho khối H |
| Chương trình OLP'26 | **Thứ Năm 10/12/2026, 7h30–15h30: "Thi Hackathon khối PMNM (H)"** |
| Trang PMNM trên olp.vn | Đăng lại thể lệ + 2 tệp PDF: *"Thể lệ cuộc thi PMNM - OLP 2026"* và **"Quick-guide-to-DXOS.pdf"** (chưa tải được qua công cụ; nên tải thủ công). Email liên hệ: office@vaip.vn |

### 2.3. Cách nộp bài các mùa trước (dự báo cho 2026)

Mùa 2024 và 2025 đều nộp **qua email** tới olpvietnam@vaip.vn, thuky@vfossa.vn, vp@vfossa.vn với
tiêu đề `BÀI THI PMNM <năm> - [Tên đội] - [Trường]`, nội dung gồm thành viên, giảng viên và **link
kho mã nguồn** ("phải có thể phân phối và cài đặt trên môi trường mới"). Hạn 2025: 17:00 thứ Hai
08/12/2025. Trình bày 15 phút. Mùa 2025 có nhóm Telegram thảo luận do BTC lập.

### 2.4. Yêu cầu mới rõ nhất cho 2026 *(BTC, Thông báo số 1 HĐGK 2025, 12/12/2025)*

Gần một nửa trong 30 đội mùa 2025 dùng mô-đun không phải nguồn mở. Từ mùa 2026: đội **tự rà soát**
mô-đun/thư viện; **cung cấp bảng kê khai minh bạch về giấy phép và nguồn gốc mô-đun bên ngoài**;
HĐGK chấm dựa trên nội dung tự kiểm; **chế tài cao hơn** nếu cố tình để lại lỗi hoặc kê khai
sai/thiếu. Bài không nhắc Docker hay việc dùng nhiều repo.

*(đội)* Bảng kê khai này chính là `DEPENDENCIES.md`, nhưng phải được **sinh tự động từ image và mã
nguồn thật**, không điền tay. Xem mục 6.

---

## 3. Giáo trình DX-OS: những gì đề thi có thể lấy ra *(giáo trình, đã đọc 82 trang)*

Giáo trình có giấy phép **CC BY 4.0**, tác giả TS. Tạ Tuấn Anh, đồng tác giả kỹ thuật là Gemini.
Toàn bộ tầng cơ bản dùng Google Workspace; nguồn mở chỉ xuất hiện ở các mục "Vượt ngưỡng".

### 3.1. Hộp cát DX-Lab: sáu điểm chạm và ba vai

Giáo trình thực hành trên **một luồng duy nhất: DX-Ticket** (quản lý yêu cầu khách hàng).

| # | Điểm chạm | Công cụ giáo trình | Vai | Không gian |
|---|---|---|---|---|
| 1 | Cấu trúc lưu trữ P.A.R.A | Google Drive | — | [H] |
| 2 | DX-Portal | Google Sites | — | [H] |
| 3 | Biểu mẫu thu thập yêu cầu | Google Forms | **khách hàng** | [P] |
| 4 | CSDL lõi | Google Sheets | — | [D] |
| 5 | Ứng dụng quản lý đa nhiệm | AppSheet | **nhân sự vận hành** | [P] |
| 6 | Bảng điều khiển quản trị | Looker Studio | **lãnh đạo** | [D] |

Bao quanh: Telegram Supergroup + Topics ([H]), Apps Script + n8n ([P]), NotebookLM + Gemini Gems ([I]).

### 3.2. Đặc tả DX-Ticket (đủ để tái hiện bằng nguồn mở)

**Bảng `CUSTOMERS`**: `Customer_ID` (PK, dạng `KH-001`), `Số_Điện_Thoại` (khóa phụ, đúng 10 số),
`Tên_Khách_Hàng`, `Email`, `Loại_Khách_Hàng` {Cá nhân, Doanh nghiệp, Đối tác}, `Địa_Chỉ_Khu_Vực`,
`Ngày_Đăng_Ký`.

**Bảng `TICKETS`** (17 cột sau bài 6.8): `Ticket_ID` (PK, dạng `TCK-001a2f9b`), `Customer_ID` (FK),
3 cột lookup chỉ đọc (SĐT, tên, email), `Thời_Gian_Nhận`, `Loại_Yêu_Cầu` {Bảo hành, Khiếu nại, Tư vấn},
`Nội_Dung`, `Hình_Ảnh_Lỗi`, `Trạng_Thái` {Chờ xử lý, Đang xử lý, Đóng}, `Thời_Gian_Đóng`,
`Thời_Gian_SLA` (= Đóng − Nhận), `Đánh_Giá_CSAT` (1–5), `Mức_Độ_Ưu_Tiên` {Khẩn cấp, Cao, Trung bình, Thấp},
`Hướng_Xử_Lý`, `Nhân_Sự_Phụ_Trách` (email), `Log_Email` (cờ idempotency).

**Máy trạng thái**: Chờ xử lý → *Bắt đầu xử lý* (gán `Nhân_Sự_Phụ_Trách` = người bấm) → Đang xử lý →
*Kết thúc xử lý* (bắt buộc nhập `Hướng_Xử_Lý`, set `Thời_Gian_Đóng`) → Đóng. Không cho sửa trạng
thái bằng tay; nút chỉ hiện đúng tiền điều kiện.

**Poka-yoke 3 lớp**: (1) frontend: regex `^[0-9]{10}$`, email, dropdown, Show_If/Required_If;
(2) backend: đóng mà thiếu `Hướng_Xử_Lý` thì rollback, đang xử lý mà thiếu người phụ trách thì
rollback; (3) thiết bị: GPS/timestamp tự lấy, không nhập tay.

**Phân quyền**: khách hàng chỉ thấy form; nhân sự thấy hàng đợi "Chờ xử lý" và ticket của mình
(row-level security `Trạng_Thái="Chờ xử lý" OR Nhân_Sự_Phụ_Trách=USEREMAIL()`); quản lý thấy
dashboard.

**Ba sự kiện tự động**: (a) ticket mới → tìm/tạo khách theo SĐT → email xác nhận; (b) chuyển
*Đang xử lý* với loại *Khiếu nại* → webhook n8n → Telegram "🚨 CẢNH BÁO KHIẾU NẠI MỚI";
(c) *Đóng* → email kèm link CSAT → web app ghi điểm. Cột `Log_Email` chống gửi trùng.

**KPI dashboard**: Lagging: tổng ticket, CSAT trung bình, thời gian xử lý trung bình. Leading: tỷ lệ
tồn đọng, cơ cấu loại yêu cầu, cảnh báo độ trễ (`NOW − Thời_Gian_Nhận` với ticket chưa đóng),
tải theo nhân sự, phân bổ ưu tiên, bảng quá hạn. Lịch gửi PDF 08:00 ngày 1 hằng tháng; snapshot
`Snapshot_TICKETS_YYYYMM.csv` vào `41. Structured_Data`. Chỉ tiêu mẫu trong Playbook: *"mọi thẻ
phải được cập nhật Đang xử lý trong 15 phút"*.

**Hành vi tác tử [I]** (bài 8.5, 9 bước): sự kiện ticket mới đánh thức agent → đọc lịch sử khách →
RAG lấy điều khoản bảo hành/đền bù từ thư mục `[R]` → chấm rủi ro → lập kế hoạch JSON function
calls (nâng ưu tiên, soạn email, cấp voucher) → **dừng chờ phê duyệt nếu liên quan tài chính hoặc
phát ngôn ra ngoài** → thực thi → audit log. Agent mặc định **read-only**, quyền ghi cấp theo phiên.
Gem cố vấn đọc `KB_Kich_Ban_Xu_Ly` (2 cột: tình huống, hướng xử lý chuẩn); không có tiền lệ thì
in `[CHƯA CÓ TIỀN LỆ]` và yêu cầu trưởng bộ phận duyệt.

### 3.3. Công thức ánh xạ và khung đo trưởng thành (bài 2.3, 2.4, 2.6)

- `P% = (điểm DTI trục P / tối đa) × P_supp × 30%`; tương tự `D%`, `I%`; `H% = 100% − (P + D + I)`.
- Hệ số thực chứng: `P_supp` 0.33 (silo, nhập tay) / 0.66 (API một phần, cho bypass) / 1.0 (end-to-end,
  Poka-yoke chặn cứng). `D_supp` 0 (trễ theo ngày) / 0.5 (theo giờ) / 1.0 (real-time).
  `I_supp` 0 / 0.33 (hỏi đáp) / 0.66 (phân tích, dự báo) / 1.0 (Agentic tự kích hoạt).
- Thang [H] 5 mức: 80–100% / 60–80% / 40–60% / 20–40% / **10–20%** ("Kiến trúc sư"). Mức 10–20% là
  từ đây, không phải ngưỡng chấm của thể lệ.
- Radar 4 nguyên mẫu: "Mũi giáo phân mảnh", "Cánh diều lệch tâm", "Ảo giác công nghệ", "Kim cương
  toàn vẹn" (H=10, P=D=I=30).
- Mini-DTI 60 giây: 3 câu, mỗi câu 0/10/20/30%, `H = 100 − (C1+C2+C3)`.
- ROI theo ma trận HPDI (bài 11.2) chỉ định tính, không có công thức tiền tệ.

*(đội)* Đây là "khung đo lường" mà bài giới thiệu chủ đề gán cho nhóm tác nhân lãnh đạo. Nó có thể
cài thành tính năng thật: DX-Lab đo `P_supp` từ tỷ lệ ticket bị chặn ở backend, `D_supp` từ độ
trễ đồng bộ dashboard, `I_supp` từ số hành động agent đã thực thi. Xem mục 6.3.

### 3.4. P.A.R.A, DX-Portal, định dạng mở

Thư mục gốc `1. [P] Projects` · `2. [A] AREAS` · `3. [R] RESOURCES` · `[A] Archives`. Trong `[R]`:
`00. Alpha_Digital_Portal`, `10. GOVERNANCE` (Policies, SOP, Technical_Manuals, Templates),
`20. EXPERIENCE` (Lessons, Case_Studies, Tips, FAQ), `30. EDUCATION`, `40. ASSETS`
(`41. Structured_Data` CSV, `42. Unstructured_Data`, `43. Brand_Media`, `44. Versioned_Assets` gồm
code và system prompt). `[R]` view-only toàn công ty; RAG chỉ đọc `[R]`.

**Định dạng mở bắt buộc trong `[R]`** (bài 7.3): `.md` là gốc cho văn bản, `.pdf` song song, `.csv`
/ `.json` / `.parquet` cho dữ liệu, `.xml` cho hóa đơn điện tử, `.yaml` cho cấu hình. Đây là điểm
rất thuận cho nguồn mở: Nextcloud + Markdown khớp thẳng.

**DX-Portal 3 phân khu**: truyền thông (banner, tầm nhìn); trạm điều phối (nút "Tạo yêu cầu sự vụ",
"Bảng điều khiển quản trị", "Hỗ trợ khách hàng"); thư viện (nhúng 3 nhóm thư mục `[R]`). Thêm dashboard
nhúng trang chủ và "Sổ tay vận hành DX-Ticket".

### 3.5. Những gì giáo trình KHÔNG có

- Không nhắc LOD, RDF, JSON-LD, schema.org, Dublin Core ở bất kỳ trang nào. "Siêu dữ liệu" chỉ
  xuất hiện ở Data Fabric (OpenMetadata) và DocType của Frappe.
- Không có ngưỡng SLA cố định; không có công cụ đo "thời gian thao tác" tự động.
- Không có script cài đặt: giáo trình cố ý bắt học viên "Make a Copy" từng thành phần.
- Không nói gì về cuộc thi hay đề thi.

### 3.6. Công cụ nguồn mở giáo trình tự gợi ý ("Vượt ngưỡng") và kết quả kiểm giấy phép

| Giáo trình gợi ý | Kết quả kiểm | Ghi chú |
|---|---|---|
| Outline (wiki) | **BUSL-1.1, không OSI** | Loại |
| GitBook | SaaS độc quyền | Loại |
| Zammad, FreeScout (helpdesk) | Chưa kiểm trong phiên này | AGPL theo hiểu biết chung, cần đọc LICENSE |
| Chatwoot | Chưa kiểm | MIT + thư mục `enterprise/` riêng theo hiểu biết chung |
| ERPNext / Frappe HR | GPL-3.0 / chưa kiểm HR | Dùng được |
| Plane, OpenProject | Chưa kiểm | |
| Airbyte + dbt | **Airbyte: Elastic License 2.0, không OSI** | Loại Airbyte |
| Metabase / Superset / Rill | Metabase OSS AGPL sạch; Superset Apache-2.0 | Dùng được |
| MinIO, Iceberg, Great Expectations, OpenMetadata, Cube | Chưa kiểm | Ngoài phạm vi 8 GB RAM |
| Milvus / ChromaDB | Apache-2.0 | Dùng được |
| Llama 3 / Mistral cục bộ | Llama: giấy phép cộng đồng, **không OSI**; Mistral Apache-2.0 | Chọn Mistral hoặc Qwen |
| LangGraph / CrewAI, MCP Gateway | LangChain MIT; CrewAI chưa kiểm | |
| Tesseract, LLaVA | Chưa kiểm | |

*(đội)* Giá trị của bảng này khi trình bày: chứng minh đội đã đọc giáo trình đến tận mục nâng cao
và **phát hiện chính giáo trình gợi ý công cụ không đạt OSI**. Đây là luận điểm mạnh cho tiêu chí #7.

---

## 4. Kiểm toán giấy phép công cụ ứng viên (đọc tệp LICENSE thật, 09/09/2026)

Phương pháp: đọc tệp LICENSE trong repo qua raw.githubusercontent.com hoặc GitLab raw; kiểm tra
cây thư mục `ee/`, `enterprise/`, `premium/`; đọc Dockerfile hoặc workflow release khi cần xác định
image cộng đồng có chứa mã EE hay không. Tag là tag mới nhất tại ngày kiểm.

### 4.1. Loại thẳng (không OSI)

| Công cụ | Giấy phép thực tế | Chi tiết |
|---|---|---|
| **NocoDB** | Sustainable Use License 1.0 | Đổi từ AGPL-3.0 từ bản 0.301.0 (09/01/2026). Image `nocodb/nocodb` hiện tại không còn OSI. Đây là "n8n của mùa 2026". |
| n8n | Sustainable Use License | Như đã biết |
| Outline | BUSL-1.1, Change Date 2030-09-09 | Tệp tự ghi "is not an Open Source license" |
| Airbyte | Elastic License 2.0 | Toàn bộ platform |
| Camunda 8 | Camunda License 1.0 | Chỉ cho môi trường non-production. Camunda 7 là Apache-2.0 nhưng CE đã EOL từ 7.24 (10/2025) |
| Dify | "modified Apache 2.0" | Thêm điều kiện cấm multi-tenant và cấm bỏ logo. Không còn là Apache-2.0 nguyên bản |
| Open WebUI ≥ 0.6.6 | "Open WebUI License" | BSD-3 + điều khoản giữ thương hiệu. Bản ≤ 0.6.5 vẫn BSD-3 |
| Budibase | GPLv3 + BSL cho phần trả phí | Như đã biết |
| Llama 3.x, Gemma, VinaLLaMA | Giấy phép cộng đồng riêng | Không OSI |

### 4.2. Lõi OSI nhưng image cộng đồng chứa mã EE độc quyền

Các dự án này có LICENSE gốc là MIT/AGPL nhưng kèm đoạn *"nội dung trong thư mục `ee/` theo giấy
phép Enterprise"* (cấm dùng production không có subscription, cấm phân phối lại). Image chính thức
build từ cả monorepo, mã EE có mặt trong image và chỉ bị khóa bằng license key.

| Công cụ | Thư mục EE | Bằng chứng image không sạch |
|---|---|---|
| **Authentik** | `authentik/enterprise/` | Dockerfile `COPY ./authentik/ /authentik`; docs: "installing a license unlocks Enterprise features" |
| **Rocket.Chat** | `apps/meteor/ee/`, `ee/` | `server/main.ts` import `../ee/server`; `COPY . /app` |
| **Docmost** | `packages/ee`, `apps/*/src/ee` (submodule private) | release workflow checkout `submodules: recursive` rồi `COPY . .` |
| **Baserow** | `premium/`, `enterprise/` | Cả hai Dockerfile `COPY premium/...`, `COPY enterprise/...`. Có biến `BASEROW_OSS_ONLY` để chỉ chạy phần MIT, nhưng mã EE vẫn nằm trong image |
| **Activepieces** | `packages/ee/`, `packages/server/api/src/app/ee/` | Dockerfile xóa `packages/ee` lúc chạy nhưng `server/api` đã được build kèm `app/ee` |
| **Flowise** | `packages/server/src/enterprise/`, `IdentityManager.ts` | Image duy nhất (chưa đọc Dockerfile) |
| **Formbricks** | `apps/web/modules/ee` (17 module: sso, audit-logs, billing, whitelabel...) | Docs: "already included in the Docker images, but you need an Enterprise License Key to unlock" |
| **Automatisch** | 317 tệp `*.ee.js` | Dockerfile `COPY . /automatisch`; release cuối 08/2025, hơn 1 năm không cập nhật |
| **Windmill** | compile flag `enterprise` | Chính LICENSE tuyên bố image CE chứa "proprietary and non-public code" |

*(đội)* Muốn dùng bất kỳ công cụ nào ở bảng này thì phải tự build image từ nguồn đã loại thư mục
EE và chứng minh trong hồ sơ. Việc này tốn công và mâu thuẫn với chính sách "không fork" của đội.
Khuyến nghị: **không dùng**.

### 4.3. Trường hợp cần chọn đúng image

| Công cụ | Image sạch | Image cần tránh |
|---|---|---|
| Mattermost | `mattermost/mattermost-team-edition` (build không có tag `enterprise`) | `mattermost-enterprise-edition`, và lưu ý mọi default trong `mattermost/docker` trỏ tới bản enterprise |
| Metabase | `metabase/metabase` (LICENSE.txt xác nhận không chứa `enterprise/`) | `metabase/metabase-enterprise` |
| Grafana | `grafana/grafana-oss` | `grafana/grafana` (bản Enterprise mặc định) |
| Appsmith | `appsmith/appsmith-ce` (thư mục `ee/` trong repo chỉ là stub re-export `ce/`) | `appsmith-ee` |

### 4.4. Sạch (LICENSE một giấy phép OSI, không có thư mục EE, image chính thức không chứa mã độc quyền)

| Trục | Công cụ | Giấy phép | Tag mới nhất |
|---|---|---|---|
| [H] | Keycloak | Apache-2.0 | 26.7.3 |
| [H] | Zitadel | AGPL-3.0-only (đổi từ Apache-2.0 tại v3, 04/2025) | v4.17.3 |
| [H] | Nextcloud server, Talk, Collectives, Notes, Deck, user_oidc | AGPL-3.0-or-later | v34.0.3 / v24.0.4 / v4.6.1 / v6.0.2 / v1.18.4 / v8.11.0 |
| [H] | Wiki.js | AGPL-3.0 | v2.5.314 |
| [H] | BookStack | MIT (không có image chính thức) | v26.05.4 |
| [H] | Zulip | Apache-2.0 | 12.2 |
| [P] | Appsmith CE | Apache-2.0 | v2.3 |
| [P] | Frappe Framework / ERPNext / Helpdesk / CRM | MIT / GPL-3.0 / AGPL-3.0 / AGPL-3.0 | v16.33.1 (v15.120.1 LTS) / v16.34.2 / v1.30.1 / v1.83.0; Helpdesk và CRM không có image riêng, phải build qua `frappe_docker` |
| [P] | Node-RED | Apache-2.0 | 5.0.7 |
| [P] | Kestra OSS | Apache-2.0 (EE ở repo đóng riêng) | v2.0.0 |
| [P] | Huginn | MIT | v2026.09.09 |
| [P] | Apache Airflow | Apache-2.0 | 3.3.1 |
| [P] | Temporal | MIT | v1.31.2 |
| [P] | Form.io server | OSL-3.0 (OSI-approved, copyleft mạng) | v4.9.1; thư viện client formio.js chưa kiểm |
| [D] | PostgreSQL / pgvector | PostgreSQL License | 18.6 / v0.8.6 |
| [D] | Apache Superset | Apache-2.0 | 6.1.0 |
| [D] | Redash | BSD-2-Clause | v26.3.0 |
| [D] | Apache NiFi | Apache-2.0 | 2.11.0 |
| [I] | Ollama | MIT | v0.33.3 |
| [I] | Langflow | MIT | v1.12.1 |
| [I] | AnythingLLM | MIT | v1.16.1 |
| [I] | LangChain, LlamaIndex | MIT | — |
| [I] | Qdrant, Chroma, Milvus, vLLM | Apache-2.0 | v1.19.1 / 1.5.9 / v3.0.1 / v0.29.0 |
| [I] | Weaviate | BSD-3-Clause | v1.39.3 |

### 4.5. Giấy phép trọng số mô hình (theo tag `license` trên Hugging Face)

| Mô hình | Giấy phép | OSI |
|---|---|---|
| **Qwen3-8B, Qwen2.5-7B-Instruct** | Apache-2.0 | Có |
| Mistral-7B-Instruct-v0.3 | Apache-2.0 | Có |
| Phi-4-mini-instruct | MIT | Có |
| AITeamVN/Vi-Qwen2-7B-RAG | Apache-2.0 | Có |
| Vistral-7B-Chat | AFL-3.0 | Có (nhưng không tương thích GPL) |
| PhoGPT-4B-Chat | bsd-3-clause theo tag; tệp LICENSE chưa đọc được | Cần kiểm lại |
| Llama 3.1 / 3.2 | Llama Community License | **Không** |
| Gemma 3 | Gemma Terms of Use | **Không** |
| VinaLLaMA | Llama 2 Community License | **Không** |
| **bge-m3**, multilingual-e5-large | MIT | Có |
| nomic-embed-text-v1.5, AITeamVN/Vietnamese_Embedding, bkai vietnamese-bi-encoder | Apache-2.0 | Có |

Lưu ý: Qwen2.5 bản 3B và 72B dùng "Qwen License" riêng, chưa kiểm; chỉ 7B và dòng Qwen3 là Apache-2.0.

### 4.6. Điểm chưa xác minh trong phiên này

Nội dung tệp LICENSE gốc của Docmost và Kestra (chỉ thấy nhãn GitHub); tệp LICENSE của PhoGPT;
giấy phép Zammad, FreeScout, Chatwoot, Plane, OpenProject, CrewAI, formio.js, Janus/coturn (HPB
của Talk); việc image Flowise có thực sự chép thư mục enterprise (suy từ cấu trúc monorepo, chưa
đọc Dockerfile). Các trường hợp Authentik, Rocket.Chat, Docmost, Baserow, Activepieces, Formbricks,
Automatisch, Windmill, Mattermost, Metabase đã đọc Dockerfile, workflow release hoặc docs chính thức.

---

## 5. Bài học từ các đội mùa trước *(đội, đọc 52 kho mã ngày 09/09/2026)*

### 5.1. Mẫu và cách đọc

Đã clone nông 52 kho mã công khai của các đội OLP PMNM 2023–2025 tìm được qua GitHub (từ khóa
OLP/PMNM/VFOSSA, tên đội trong bài kết quả) cùng 2 kho mã mùa 2026 đã công khai, rồi chạy một script
kiểm tra hình thức trên từng kho: tệp giấy phép, header trong tệp mã, NOTICE, README/CHANGELOG/
CONTRIBUTING, Dockerfile/Compose, workflow CI, mẫu issue, `.env` bị commit, tệp nhị phân trên 2 MB,
địa chỉ `localhost` viết cứng. Sau đó tra GitHub API cho số commit, release, tag và issue của các kho
đáng chú ý.

BTC không công bố liên kết kho mã trong bài kết quả, nên chỉ ánh xạ được giải cho vài đội có tên
trùng khớp: **CityLens** của PKA_OpenDynamics (Nhất 2025, 84,5 điểm), **GreenMap** của HouHackathon
(Nhì 2025), và một trong hai kho DTU mùa 2024 (**DTU-GreenHope** hoặc **DTURelifeLink**) thuộc đội
DTU_DZ_1 đoạt giải Nhất 2024. Vô địch 2025 là TLU-SKTT1 (88 điểm) nhưng chưa tìm được kho mã. Các
nhận xét dưới đây vì thế là về *mặt bằng chung*, không phải về đội đoạt giải.

### 5.2. Số liệu chung

| Hạng mục kiểm tra | Kết quả trên 52 kho | Tiêu chí PoF liên quan |
|---|---|---|
| Giấy phép gốc | MIT 18 · GPL-3.0 17 · Apache-2.0 15 · AGPL-3.0 1 · không rõ 1 | #2 |
| Header giấy phép trong tệp mã (46 kho có mã) | đủ (≥95% tệp) **16** · một phần **19** · không có **11** · dùng SPDX **6** | #2, mức −5 |
| Có tệp NOTICE | **2** | #2 "thông báo mục đích giấy phép" −5 |
| Không có CHANGELOG | **21** | #6, −5 |
| Không có CONTRIBUTING | **24** | #10 |
| Không có workflow CI | **29** | #10 |
| Không có mẫu issue/PR | **17** | #6 |
| Commit sẵn tệp `.env` | **6** | Lộ bí mật, cản trở cài trên máy mới |
| Tệp nhị phân > 2 MB trong repo | **29** (7 kho chứa model `.pt/.keras/.onnx/.joblib` hoặc chỉ mục FAISS) | #5 |
| Vendor `node_modules` hoặc `lib/` vào repo | 2 | #5 |
| Không có Dockerfile/Compose nào | **13** | #4 |
| `localhost`/`127.0.0.1` viết cứng trong mã | **40** | #4 "không chạy được ngoài thư mục mã nguồn" |
| README có mục "build from source" | **2** (FloodWatch, UIP) | #4, −5 |
| Không có tệp mã nguồn nào | 6 (2 kho mùa 2024 chỉ có bản export ứng dụng Appsmith; 1 kho rỗng; 3 kho chỉ có cấu hình hoặc tài liệu) | #4, #5 |

Về phát hành (GitHub API, 11 kho tiêu biểu): hầu hết chỉ **gắn tag** rồi bấm "Release" mà không đính
kèm gói nào, tức là chỉ có `.zip`/`.tar.gz` do GitHub tự sinh. Chỉ **UIP** đính `.tar.gz` + `.whl` và
**Smart-Forecast** đính `.apk`. Nhiều đội phát hành 3–5 bản trong 1–2 ngày cuối (GreenHope: 5 release
cùng ngày 09/12/2024; CityLens: v1.0.0–v1.0.2 trong 07–08/12/2025), tên tag không nhất quán
(`V1.1.4` cạnh `v1.1.2`).

### 5.3. Đội đoạt giải khác gì mặt bằng

| Kho (giải) | Thời gian | Commit / người | Header | CI, mẫu | Release | Điểm yếu còn lại |
|---|---|---|---|---|---|---|
| CityLens (Nhất 2025) | 21/11 → 11/12/2025 | 684 / 2 | 176/178 | 3 workflow, mẫu issue+PR | 3 tag, không asset | 15 tệp `localhost`; `hanoi.osm` > 2 MB; không NOTICE |
| GreenMap-Backend (Nhì 2025) | 30/10 → 12/2025 | 86 / 3 | 69/69 | không | 1.0.0 (02/12), 1.1.0 (10/12) | README chạy 4 terminal; không CHANGELOG/CONTRIBUTING; cần Firebase |
| DTU-GreenHope (DTU 2024) | 25/11 → 13/12/2024 | 295 / 3 | 10/315 | 3 workflow | 5 tag cùng ngày | 3 tệp `.env` commit; NocoBase phải sửa `package.json`; zip 2 MB trong `release/` |
| UIP (2025, chưa rõ giải) | 20/11/2025 → 07/2026 | 363 / 1 | 267/269 SPDX | 10 workflow, CODEOWNERS, SECURITY | v1.0.0, v2.0.0 có `.tar.gz`+`.whl` | 52 tệp `localhost`; 12 dịch vụ Compose |
| Smart-Forecast (2025) | 07/11 → 09/12/2025 | 437 / 3 | 287/348 SPDX | ci, release, docs | v1.2.0 có `.apk` | — |

Ba điểm chung của nhóm này so với 40 kho còn lại: **(1)** commit dày đặc trong đúng 3 tuần sau khi có
đề (repo tạo 21/11–02/12, đẩy tới 09–11/12), tức là toàn bộ sản phẩm được làm sau khi đề ra; **(2)**
gần đủ header từng tệp và có CI; **(3)** README dài, có mục lục, kiến trúc, ảnh chụp, lệnh cài đặt
cụ thể. Ngược lại, ngay cả đội Nhất vẫn để `localhost` viết cứng, không có NOTICE và không đính gói
phát hành, nghĩa là các mức trừ ở #2, #3, #4 nhiều khả năng **không bị áp dụng chặt** trong thực tế
chấm. Không nên dựa vào đó: Thông báo số 1 HĐGK (mục 2.4) cho thấy mùa 2026 sẽ soát giấy phép kỹ hơn.

### 5.4. Lỗi lặp lại, ánh xạ vào bảng tiêu chí

1. **Header giấy phép** (#2): 30/46 kho thiếu hoàn toàn hoặc thiếu một phần; nhiều kho thêm header
   bằng một commit cuối ("add license headers") rồi bỏ sót tệp mới. Repo hiện tại đã có
   `scripts/license-header.sh check` trong CI, cần giữ nguyên.
2. **Đính kèm thứ không phải mã nguồn** (#5): trọng số model, chỉ mục vector, `budibase-client.js`,
   bản export `.tar.gz` của LCDP, `node_modules`. Với DX-Lab, mọi model phải tải lúc chạy (Ollama
   pull) hoặc lúc seed, không nằm trong repo.
3. **"Cài đặt" chỉ là `docker-compose up -d`** (#4): 13 kho không có Docker, 40 kho viết cứng
   `localhost`, chỉ 2 kho có mục build from source. Hầu như không kho nào chứng minh chạy được trên
   máy khác ngoài máy đội. Đây là chỗ dễ khác biệt nhất với chi phí thấp: một trang
   `docs/build-from-source.md` + biến môi trường cho mọi địa chỉ dịch vụ + chạy thử trên máy sạch.
4. **Thiếu tài liệu vận hành nguồn mở** (#6, #10): 21 kho không CHANGELOG, 24 không CONTRIBUTING,
   17 không mẫu issue; issue tracker phần lớn trống (1–6 issue mở, chủ yếu do đội tự tạo ngày cuối).
5. **Release hình thức** (#3): tag không asset, dồn vào 1–2 ngày cuối, tên không theo SemVer.
6. **Bí mật và dịch vụ đóng**: 6 kho commit `.env`; nhiều kho cần Firebase, Google Cloud, Goong Map,
   Gemini để chạy. Mâu thuẫn với yêu cầu "phân phối và cài đặt trên môi trường mới" ở mục 2.3 và là
   loại lỗi HĐGK đã nêu đích danh cho mùa 2026.
7. **NOTICE gần như không ai có** (2/52) dù bảng tiêu chí trừ 5 điểm. Repo hiện tại đã có.

### 5.5. Hai đội mùa 2026 đã công khai kho mã

| | `quangphuong19042005-sketch/dx-lab-olp2026` | `toilact/OptiMill-DX` |
|---|---|---|
| Tạo / đẩy gần nhất | 10/06/2026 (một ngày sau bài BTC) / 06/07/2026 | 18/07/2026 / 31/07/2026 |
| Commit / người | 21 / 1 | 131 / 2 |
| Giấy phép, header | MIT, SPDX 37/37, có `THIRD_PARTY_LICENSES.md` | Apache-2.0, SPDX 151/153, có `docs/license-audit.md` chạy `pip-licenses` + `license-checker` |
| Cách tiếp cận | **Lắp ráp nền tảng**: Keycloak + Nextcloud + Baserow + Metabase + Qdrant + Ollama/Gemini; tự viết DX-Portal (Next.js), DX-Core (trục sự kiện), DX-RAG, DX-Diag | **Tự viết dọc**: FastAPI + React + PostgreSQL/pgvector + Ollama, không lắp nền tảng nào; nghiệp vụ xưởng cơ khí gia công theo đơn (RFQ → báo giá AI → lệnh sản xuất → giao) |
| Tính năng trùng với đề xuất ở mục 6.3 | Xuất JSON-LD/DCAT; tự khởi tạo P.A.R.A trên Nextcloud khi boot; **DX-Diag chấm HPDI theo bảng hỏi** (`app/diag/questions.ts`) và vẽ radar | Máy trạng thái + Poka-yoke 2 lớp, nhật ký sự kiện, dashboard, RAG có human-in-the-loop, JSON-LD export |
| Kỷ luật PoF | CI test 4 thành phần; tag v0.6–v0.8 nhưng chưa có release | `CHECKLIST.md` với luật hằng tuần: commit mỗi ngày từ cả 3 tài khoản, mở issue trước khi code, SPDX cho tệp mới, CI ruff+pytest+tsc; có `demo-script.md`, kịch bản quay video |
| Điểm đội có thể phản biện | Baserow: image cộng đồng chứa mã EE (mục 4.2); mặc định gọi Gemini qua API (khóa trong `.env`); 5 tệp `localhost` | Không tái dùng nền tảng nguồn mở nào ở [H]/[P]/[D], khó bảo vệ ý "kết hợp LCDP + LOD + RAG" của bài giới thiệu chủ đề; chưa có release |

Kho `dx-lab-olp2026` còn chép bài giới thiệu chủ đề và thể lệ ra Markdown trong `docs/`
(`quick-guide-to-dxos.md` 104 dòng, `the-le-cuoc-thi-pmnm-olp-2026.md` 116 dòng). Đó là bản chép
của đội khác, chưa đối chiếu với PDF gốc, chỉ dùng để tham khảo nhanh.

### 5.6. Rút ra cho DX-Lab *(đội)*

- **Mục 0.6 và 6.3.2 phải sửa lại**: "Dashboard HPDI" đã có một đội làm ở dạng bảng hỏi. Khác biệt của
  đội chỉ còn ở chỗ tính `P_supp`, `D_supp`, `I_supp` **từ dữ liệu vận hành thật** (ticket bị chặn,
  độ trễ đồng bộ, hành động agent), và phải nói rõ như vậy khi trình bày.
- **Hai đối thủ đã có 21 và 131 commit, đội có 1.** Việc #1 trong mục 6.4 (merge, mở issue, commit
  đều) là khẩn cấp hơn mọi việc khác.
- **Bốn hạng mục gần như không đội nào làm, chi phí thấp**: NOTICE (đã có), gói phát hành thật
  `.tar.gz` + `.sha256` (đã có script, chưa chạy), trang build from source được kiểm chứng trên máy
  sạch, và không có `localhost` viết cứng. Thêm vào CI ba kiểm tra: không có tệp > 2 MB, không có
  `.env`, không có `localhost` trong mã nguồn.
- **Chọn nền tảng phải bảo vệ được bằng mục 4**: `dx-lab-olp2026` dùng Baserow và Gemini là hai chỗ
  đội có thể chỉ ra trong phần "tính bền vững" để làm nổi bật stack sạch OSI ở mục 6.1 và tùy chọn
  LLM cục bộ.
- **Học cách làm hồ sơ của OptiMill-DX**: kiểm toán giấy phép chạy bằng lệnh có thể lặp lại và ghi
  ngày; checklist PoF công khai trong repo; kịch bản demo viết sẵn. Đây là dạng "công cụ hỗ trợ công
  bố kèm theo" mà tiêu chí #10 nhắc tới.

---

## 6. Đề xuất điều chỉnh chiến lược *(đội)*

### 6.1. Stack chốt sau kiểm toán

| Trục | Điểm chạm giáo trình | Chốt | Vì sao |
|---|---|---|---|
| [H] | SSO | **Keycloak** | Apache-2.0, không EE, image chính thức sạch, hỗ trợ OIDC cho mọi thành phần còn lại |
| [H] | P.A.R.A, DX-Portal, ghi chú, chat | **Nextcloud** Files + Collectives + Deck + Talk, app `user_oidc` | Một nền tảng thay bốn công cụ Google; toàn bộ AGPL-3.0 sạch; Markdown khớp yêu cầu định dạng mở của `[R]` |
| [P] | Form khách hàng + app vận hành | **Appsmith CE** (Apache-2.0) *hoặc* **Frappe Helpdesk** (AGPL) | Quyết định sau khi dựng thử cả hai trong tháng 9; NocoDB đã bị loại |
| [P] | Trục sự kiện, iPaaS | **Node-RED** | Apache-2.0; thay Apps Script + n8n |
| [D] | CSDL lõi | **PostgreSQL 16** + `pgvector` | Đã chốt QĐ-002; pgvector gộp luôn vector DB vào cùng tiến trình, tiết kiệm RAM |
| [D] | Dashboard | **Apache Superset** (dự phòng Metabase OSS) | Apache-2.0; Metabase AGPL cũng sạch nếu dùng đúng image |
| [I] | LLM cục bộ | **Ollama** + **Qwen3-8B** (hoặc Qwen2.5-7B) + **bge-m3** | Runtime MIT, model và embedding đều Apache-2.0/MIT |
| [I] | Agent | Dịch vụ Python nhỏ do đội viết trên **LangChain** (MIT), hoặc AnythingLLM/Langflow (MIT) | Flowise và Dify bị loại |

Loại khỏi danh sách cân nhắc: NocoDB, Budibase, n8n, Outline, Docmost, Rocket.Chat, Authentik,
Baserow, Activepieces, Flowise, Dify, Open WebUI mới, Airbyte, Camunda 8, Windmill.

### 6.2. Điều chỉnh với các tài liệu hiện có

- `research-huong-trien-khai.md` mục 4: NocoDB từ "chưa xác minh" thành **loại** (SUL từ 01/2026).
  Metabase từ "phải xác minh tính năng ở OSS" thành "image `metabase/metabase` sạch theo LICENSE.txt".
- `chien-luoc-du-thi.md` mục 4.2: bổ sung NocoDB, Outline, Dify, Open WebUI vào bảng bẫy. Mục 5.2:
  ánh xạ JSON-LD hạ từ "bảo hiểm rẻ" xuống "tùy chọn cuối", vì giáo trình không dùng LOD; giữ một
  bản xuất JSON-LD đơn giản cho `[R]` là đủ.
- `architecture.md` mục 3: điền ứng viên theo bảng 6.1. QĐ-002 sửa thành "PostgreSQL cho mọi thành
  phần *hỗ trợ* PostgreSQL; Frappe (nếu chọn) chạy MariaDB riêng".
- `DEPENDENCIES.md`: thay các dòng *chưa chốt* bằng bảng 6.1 kèm tag và giấy phép ở mục 4.4.

### 6.3. Ba tính năng "nguyên gốc" nên đặt cược

1. **DX-Ticket nguồn mở đúng đặc tả giáo trình** (mục 3.2): cùng 2 bảng, 17 cột, 3 sự kiện, Poka-yoke
   3 lớp và row-level security, nhưng không có một thành phần Google nào. Đây là bằng chứng trực
   tiếp cho tiêu chí #2 "giải quyết đúng đầu bài".
2. **Dashboard HPDI tự động** (mục 3.3): tính `P_supp`, `D_supp`, `I_supp` từ dữ liệu vận hành thật
   (tỷ lệ ticket bị backend chặn, độ trễ đồng bộ, số hành động agent) và vẽ radar 4 trục theo đúng
   công thức bài 2.4. Đội `dx-lab-olp2026` đã có bản chấm theo bảng hỏi (mục 5.5); đo từ dữ liệu
   vận hành thật là phần chưa ai làm và phải là trọng tâm khi trình bày.
3. **Bộ kiểm toán giấy phép chạy trong CI**: đọc `docker-compose.yml`, kéo nhãn `org.opencontainers.image.*`
   và SBOM của từng image, đối chiếu danh sách SPDX cho phép, sinh `DEPENDENCIES.md` và fail build
   khi có thành phần ngoài danh sách. Trả lời trực tiếp yêu cầu "bảng kê khai" của HĐGK (mục 2.4).

### 6.4. Việc làm trong tháng 9

| # | Việc | Đạt khi |
|---|---|---|
| 1 | Merge nhánh docs, mở 5–10 issue thật cho các đầu việc dưới đây, commit đều mỗi tuần | `git log` trải đều; Issues có mở và đóng |
| 2 | ~~Tải thủ công `Quick-guide-to-DXOS.pdf`~~ Đã đối chiếu 10/09 qua bản chép của đội khác: trùng bài web 761 (`du-bao-de-thi-2026.md` mục 2.2) | Xong |
| 3 | Cài plugin `docker compose` trên máy dev; đưa Keycloak + Nextcloud + Postgres vào Compose profile `h`; đo RAM thật | `make up-h` chạy, SSO thật, số RAM ghi vào `architecture.md` |
| 4 | Dựng thử DX-Ticket trên Appsmith CE và trên Frappe Helpdesk, mỗi bên 2 ngày; chọn một | Bản ghi quyết định QĐ-004 |
| 5 | Viết bộ kiểm toán giấy phép (6.3.3), nối vào CI | CI fail khi thêm image không có trong allowlist |
| 5b | Thêm vào CI ba kiểm tra rút từ mục 5.4: không tệp > 2 MB, không `.env`, không `localhost` viết cứng trong mã | CI fail khi vi phạm |
| 6 | Phát hành `v0.1.0` với `.tar.gz` + `.sha256` ngay khi profile `h` chạy được | Trang Releases có bản đầu tiên |
| 7 | Gửi email office@vaip.vn hỏi 3 câu ở `research-huong-trien-khai.md` mục 9 | Có trả lời hoặc có ghi nhận đã hỏi |
| 8 | Tách lõi và gói lĩnh vực; gói `safety` rồi gói `dx-ticket` chạy trên cùng lõi (`du-bao-de-thi-2026.md` mục 4.3) | Đổi gói bằng một biến môi trường, demo cả hai |
| 9 | Hai thử nghiệm phòng sốc: sinh XML hóa đơn điện tử từ bản ghi mẫu; xuất `events` ra NGSI-LD | Ghi số ngày cần nếu đề ép, vào `du-bao-de-thi-2026.md` mục 3 |

---

## 7. Nguồn đã kiểm chứng trong phiên

**BTC**: vfossa.vn bài 760, 761 (09/06/2026); 749 (đề 2025), 750 (meeting 2025), 752 (Thông báo số 1
HĐGK, 12/12/2025), 753 (kết quả 2025), 729 (kết quả 2024); olp.vn Thông báo số 1 OLP/ICPC 2026
(21/08/2026), Chương trình OLP'26, trang PMNM. Đã quét bài id 762–792 và các chuyên mục.

**Giáo trình**: https://opendigitransform.gitbook.io/dx-os — 82 trang theo `llms.txt`, đọc dạng
Markdown. Không đọc được hình sơ đồ và live demo bên ngoài.

**Giấy phép**: tệp LICENSE/COPYING/LICENSE.txt trong repo của mọi công cụ ở mục 4 qua
raw.githubusercontent.com hoặc gitlab.com raw; Dockerfile và workflow release của Authentik,
Rocket.Chat, Docmost, Mattermost, Windmill, Metabase; model card Hugging Face cho mục 4.5.

**Đội mùa trước và 2026**: 52 kho mã trên GitHub (clone nông ngày 09/09/2026, script kiểm tra hình thức
chạy cục bộ); GitHub API ngày 10/09/2026 cho commit, release, tag, issue của 11 kho ở mục 5.3 và 5.5;
bài kết quả vfossa 753 (2025) và 729 (2024) để ánh xạ giải.

**Chưa làm**: chưa build hay chạy thử bất kỳ tổ hợp nào trong mục 6.1; chưa tìm được kho mã của đội vô
địch 2025 (TLU-SKTT1).
