# Đặc tả nghiệp vụ DX-Safety — sổ sự cố an toàn và bàn phê duyệt ngoại lệ

> Bản nháp đầu tiên, ngày 10/09/2026. Đây là **nghiệp vụ nền** đội chọn để dựng lát cắt xuyên bốn
> trục H-P-D-I trước khi có đề thi tháng 11 (xem `chien-luoc-du-thi.md` mục 5.2 và
> `nghien-cuu-chu-de-2026.md` mục 6). Cấu trúc bám khuôn DX-Ticket của giáo trình DX-OS
> (`nghien-cuu-chu-de-2026.md` mục 3.2): cùng số vai, cùng kiểu máy trạng thái, cùng ba lớp
> Poka-yoke, cùng ba sự kiện tự động, cùng hành vi tác tử chín bước. Khác biệt nằm ở nghiệp vụ
> (an toàn xưởng thay vì yêu cầu khách hàng), ở **lớp ngoại lệ** và ở **đồng hồ H% đo từ dữ liệu
> vận hành thật**.
>
> **Cập nhật 10/09/2026 (chiều):** sau đợt bằng chứng 2 (`du-bao-de-thi-2026.md` mục 2.2), gói
> DX-Ticket theo hộp cát Alpha được làm **trước** cho vòng trường; DX-Safety là gói lĩnh vực thứ hai.
> Mục 3.5 và 4–10 của tài liệu này là đặc tả lõi, áp dụng nguyên cho DX-Ticket với tên thực thể đổi
> theo `ke-hoach-vong-truong.md`.
>
> Quy ước: *(giáo trình)* là phần lấy từ giáo trình, *(đội)* là thiết kế của đội. Tên bảng và cột
> dùng ASCII snake_case để chạy được trên PostgreSQL; nghĩa tiếng Việt ghi bên cạnh.

---

## 1. Bài toán và phạm vi

**Doanh nghiệp đích.** Xưởng sản xuất 30–200 lao động (cơ khí, nhựa, bao bì, may) không có bộ phận
IT, có một cán bộ an toàn kiêm nhiệm. Theo quy định an toàn vệ sinh lao động, xưởng phải ghi nhận
tai nạn và sự cố; thực tế ghi sổ tay, báo miệng, và không có số liệu để phòng ngừa.

**Ba nỗi đau khớp với ba "căn bệnh" giáo trình nêu.**

| Nỗi đau tại xưởng | Căn bệnh trong giáo trình | DX-Safety xử lý ở trục |
|---|---|---|
| Công nhân ngại báo cáo, báo thì bằng miệng hoặc Zalo, mất dấu | "Zalo hóa", việc trôi | [H] báo cáo có cấu trúc, ẩn danh được |
| Sự cố ghi sổ tay, không ai đóng, không biết còn bao nhiêu việc mở | Ốc đảo thông tin, báo cáo "tử thi" | [P] máy trạng thái, [D] dashboard |
| Xin "làm tạm" khi máy chưa sửa xong, duyệt miệng, không ai chịu trách nhiệm | Con người còn giữ quyền điều khiển | [P] bàn phê duyệt ngoại lệ, [I] tác tử chấm rủi ro |

**Phạm vi bản v0.x (trước khi có đề).** Một luồng duy nhất: **sự cố an toàn** (tai nạn, suýt xảy
ra, điều kiện mất an toàn). Trên luồng đó có **ngoại lệ** (xin vượt quy tắc) và **đồng hồ H%**.
Không làm: quản lý huấn luyện an toàn, quản lý trang bị bảo hộ, tính lương, tích hợp IoT máy móc.

**Điều chỉnh khi có đề.** Nếu đề yêu cầu nghiệp vụ khác, giữ nguyên máy trạng thái, Poka-yoke,
sự kiện, ngoại lệ, tác tử và đồng hồ H%; chỉ thay bộ enum, bộ SOP trong thư mục `[R]` và dữ liệu
mẫu. Xem mục 12. Bản dự báo `du-bao-de-thi-2026.md` (10/09/2026) nâng ý này thành kiến trúc **gói
lĩnh vực**: DX-Safety là gói `domains/safety/`, và đội làm thêm gói `domains/dx-ticket/` đúng hộp cát
giáo trình để phòng kịch bản đề bám hộp cát.

---

## 2. Vai và điểm chạm

### 2.1. Ba vai *(giáo trình)* ánh xạ vào xưởng *(đội)*

| Vai giáo trình | Vai trong DX-Safety | Việc làm trên hệ thống |
|---|---|---|
| Khách hàng (chỉ thấy form) | **Người báo cáo**: công nhân, tổ trưởng | Gửi báo cáo sự cố từ điện thoại; xem trạng thái báo cáo của mình; trả lời khảo sát khi đóng |
| Nhân sự vận hành (hàng đợi + việc của mình) | **Cán bộ an toàn**, **tổ trưởng bảo trì** | Nhận, điều tra, giao biện pháp, đóng sự cố; xin ngoại lệ |
| Lãnh đạo (dashboard) | **Quản đốc**, **giám đốc xưởng** | Xem dashboard, duyệt ngoại lệ, duyệt hành động tác tử |

### 2.2. Sáu điểm chạm *(giáo trình)* và công cụ nguồn mở *(đội, theo mục 6.1 bản nghiên cứu)*

| # | Điểm chạm | Công cụ giáo trình | Công cụ DX-Lab | Ghi chú |
|---|---|---|---|---|
| 1 | Cấu trúc lưu trữ P.A.R.A | Google Drive | Nextcloud Files | SOP an toàn, nội quy, biên bản ở `3-Resources/10-GOVERNANCE` |
| 2 | Cổng nội bộ DX-Portal | Google Sites | Nextcloud Collectives hoặc trang tĩnh trong Appsmith | Nút "Báo sự cố", "Bảng điều khiển", "Sổ tay an toàn" |
| 3 | Biểu mẫu thu thập | Google Forms | Appsmith CE (dự phòng Frappe) | Form công khai trong mạng nội bộ, có QR ở từng khu vực |
| 4 | CSDL lõi | Google Sheets | PostgreSQL 16 | Schema `safety` |
| 5 | Ứng dụng quản lý đa nhiệm | AppSheet | Appsmith CE | Hàng đợi, chi tiết sự cố, nút chuyển trạng thái |
| 6 | Bảng điều khiển | Looker Studio | Apache Superset | Nhúng vào cổng nội bộ |

Bao quanh: Nextcloud Talk hoặc Telegram cho cảnh báo ([H]); Node-RED làm trục sự kiện ([P]);
Ollama + Qwen + bge-m3 + pgvector cho RAG và tác tử ([I]). Định danh: Keycloak, một tài khoản
cho mọi công cụ.

---

## 3. Mô hình dữ liệu

Schema `safety` trong PostgreSQL. Bảng lõi là `incidents`, dựng theo đúng khuôn bảng `TICKETS`
17 cột của giáo trình, đổi nghĩa cột cho phù hợp.

### 3.1. Bảng danh mục (nạp từ seed, quản trị viên sửa qua Appsmith)

| Bảng | Cột chính | Ghi chú |
|---|---|---|
| `areas` (khu vực) | `area_id` PK dạng `KV-01`, `name`, `supervisor_email`, `qr_token` | Mỗi khu vực một mã QR dẫn tới form có sẵn `area_id` |
| `equipment` (thiết bị) | `equipment_id` PK dạng `TB-001`, `area_id` FK, `name`, `criticality` {A, B, C}, `status` {Vận hành, Dừng, Bảo trì} | `status` chỉ đổi qua sự kiện, không sửa tay |
| `people` (nhân sự) | `email` PK (trùng Keycloak), `full_name`, `role` {reporter, safety, maintenance, manager, director}, `area_id`, `approval_limit_vnd` | Bảng tra vai cho row-level security và ngưỡng duyệt |
| `kb_scenarios` (kịch bản xử lý) | `situation`, `standard_action`, `source_doc` | Hai cột như `KB_Kich_Ban_Xu_Ly` của giáo trình, thêm cột nguồn để RAG trích dẫn |

### 3.2. Bảng `incidents` (sự cố), khuôn 17 cột *(giáo trình)* → *(đội)*

| # | Cột | Kiểu | Nghĩa | Tương ứng trong `TICKETS` |
|---|---|---|---|---|
| 1 | `incident_id` | text PK, dạng `SC-` + 8 hex | Mã sự cố, sinh tự động | `Ticket_ID` |
| 2 | `reporter_email` | text, null nếu ẩn danh | Người báo cáo | `Customer_ID` |
| 3 | `reporter_name` | text, lookup chỉ đọc | Tên người báo cáo, trống nếu ẩn danh | lookup |
| 4 | `area_id` | FK `areas` | Khu vực xảy ra | lookup |
| 5 | `equipment_id` | FK `equipment`, nullable | Thiết bị liên quan | lookup |
| 6 | `reported_at` | timestamptz, mặc định `now()` | Thời điểm ghi nhận, không nhập tay | `Thời_Gian_Nhận` |
| 7 | `incident_type` | enum {Tai nạn, Suýt xảy ra, Điều kiện mất an toàn} | Loại | `Loại_Yêu_Cầu` |
| 8 | `description` | text, tối thiểu 20 ký tự | Mô tả | `Nội_Dung` |
| 9 | `photo_path` | text, bắt buộc | Ảnh hiện trường, lưu trên Nextcloud | `Hình_Ảnh_Lỗi` |
| 10 | `status` | enum, xem mục 4 | Trạng thái | `Trạng_Thái` |
| 11 | `closed_at` | timestamptz | Thời điểm đóng | `Thời_Gian_Đóng` |
| 12 | `resolution_hours` | numeric, sinh = `closed_at − reported_at` | Thời gian xử lý | `Thời_Gian_SLA` |
| 13 | `reporter_feedback` | smallint 1–5 | "Điểm này đã an toàn chưa?" do người báo cáo chấm sau khi đóng | `Đánh_Giá_CSAT` |
| 14 | `severity` | enum {Nghiêm trọng, Cao, Trung bình, Thấp} | Mức độ, tác tử đề xuất, cán bộ an toàn xác nhận | `Mức_Độ_Ưu_Tiên` |
| 15 | `root_cause` | text | Nguyên nhân gốc, bắt buộc trước khi đóng | `Hướng_Xử_Lý` |
| 16 | `assignee_email` | FK `people` | Người phụ trách, gán tự động khi bấm "Nhận" | `Nhân_Sự_Phụ_Trách` |
| 17 | `notify_log` | jsonb | Cờ chống gửi trùng cho từng sự kiện | `Log_Email` |

Cột bổ sung *(đội)*: `anonymous` boolean; `sla_due_at` timestamptz tính từ `severity`
(Nghiêm trọng 2 giờ, Cao 24 giờ, Trung bình 3 ngày, Thấp 7 ngày); `gps_lat`, `gps_lng` lấy từ
thiết bị; `hpdi_flags` jsonb ghi việc bản ghi này có bị backend chặn hay bị sửa tay (nguồn cho
mục 10).

### 3.3. Bảng `actions` (biện pháp khắc phục)

`action_id` PK · `incident_id` FK · `kind` {Tức thời, Khắc phục, Phòng ngừa} · `description` ·
`owner_email` · `due_at` · `done_at` · `verified_by_email`. Sự cố mức Nghiêm trọng hoặc Cao
phải có ít nhất một biện pháp `Phòng ngừa` đã `done_at` mới được đóng.

### 3.4. Bảng `exceptions` (ngoại lệ) *(đội)*

| Cột | Nghĩa |
|---|---|
| `exception_id` PK dạng `NL-` + 8 hex | |
| `incident_id` FK, nullable | Ngoại lệ gắn với sự cố (ví dụ xin chạy tiếp máy đang có sự cố mở) hoặc độc lập |
| `kind` enum | {Vận hành khi sự cố mở, Gia hạn thời hạn khắc phục, Bỏ qua biện pháp bắt buộc, Chi phí vượt ngưỡng} |
| `requested_by_email`, `requested_at` | Người xin, thời điểm |
| `justification` text ≥ 50 ký tự | Lý do |
| `amount_vnd` numeric | Chi phí nếu có |
| `valid_until` timestamptz | Ngoại lệ hết hiệu lực khi nào, bắt buộc |
| `risk_score` smallint 0–100, `risk_rationale` text | Tác tử chấm, con người có thể ghi đè kèm lý do |
| `status` enum | {Chờ duyệt, Đã duyệt, Từ chối, Hết hạn, Thu hồi} |
| `approver_email`, `decided_at`, `decision_note` | Quyết định |
| `precedent_id` FK self, nullable | Tiền lệ mà tác tử tìm được |

### 3.5. Bảng `events` (nhật ký sự kiện, nguồn sự thật cho [D] và [I])

`event_id` bigserial · `occurred_at` · `entity` {incident, exception, action, equipment} ·
`entity_id` · `event_type` · `actor` (email hoặc `agent:<tên>` hoặc `system`) · `payload` jsonb ·
`blocked` boolean (true nếu đây là một thao tác bị Poka-yoke lớp 2 chặn). Bảng chỉ ghi thêm, không
sửa, không xóa. Mọi đổi trạng thái đều phải đi qua hàm ghi sự kiện; đây là điều kiện để đồng hồ H%
ở mục 10 đo được.

---

## 4. Máy trạng thái sự cố

*(giáo trình)* ba trạng thái Chờ xử lý → Đang xử lý → Đóng. *(đội)* tách "Đang xử lý" thành hai
bước để bắt buộc có nguyên nhân gốc trước khi khắc phục, và thêm một trạng thái chờ xác nhận.

```
Ghi nhận ──[Nhận]──▶ Điều tra ──[Kết luận nguyên nhân]──▶ Khắc phục ──[Hoàn tất]──▶ Chờ xác nhận ──[Xác nhận]──▶ Đóng
    │                    │                                                                  │
    └──[Từ chối: trùng/không phải sự cố]──▶ Hủy                                            └──[Chưa an toàn]──▶ Khắc phục
```

| Chuyển | Ai bấm | Tiền điều kiện (Poka-yoke lớp 2, backend kiểm tra) | Hệ quả tự động |
|---|---|---|---|
| Nhận | safety, maintenance | `status = Ghi nhận`; `severity` đã xác nhận | `assignee_email` = người bấm; sự kiện `incident.accepted` |
| Kết luận nguyên nhân | assignee | `root_cause` ≥ 30 ký tự | sự kiện `incident.investigated` |
| Hoàn tất | assignee | Mọi `actions.kind ∈ {Tức thời, Khắc phục}` có `done_at`; mức Nghiêm trọng/Cao có ≥ 1 `Phòng ngừa` đã xong; không còn ngoại lệ `Chờ duyệt` gắn với sự cố | thiết bị về `Vận hành` nếu đang `Dừng` vì sự cố này; gửi khảo sát cho người báo cáo |
| Xác nhận | reporter (hoặc safety nếu ẩn danh, sau 48 giờ) | `reporter_feedback` đã có | `closed_at`, `resolution_hours`; sự kiện `incident.closed` |
| Chưa an toàn | reporter | `reporter_feedback ≤ 2` | quay lại Khắc phục, giữ nguyên assignee, đánh dấu tái mở |
| Từ chối | safety | nhập lý do; nếu trùng phải chỉ `incident_id` gốc | sự kiện `incident.rejected` |

Không có API hay màn hình nào cho phép ghi thẳng vào `status`. Nút chỉ hiện khi tiền điều kiện
đúng (lớp 1), backend kiểm tra lại (lớp 2) và ghi sự kiện `blocked = true` nếu bị chặn.

---

## 5. Poka-yoke ba lớp *(giáo trình)* áp cho DX-Safety *(đội)*

| Lớp | Nơi | Quy tắc |
|---|---|---|
| 1. Giao diện | Form Appsmith | `area_id` lấy từ QR, không chọn tay; ảnh bắt buộc; mô tả ≥ 20 ký tự; `incident_type` là dropdown; ô "ẩn danh" bật thì ẩn trường tên và email; số điện thoại (nếu có) `^[0-9]{10}$` |
| 2. Backend | Ràng buộc PostgreSQL + hàm chuyển trạng thái | `CHECK` trên độ dài; trigger từ chối `UPDATE status` trực tiếp; tiền điều kiện ở mục 4; `exceptions.valid_until` ≤ 30 ngày; không cho tạo ngoại lệ trùng `kind` + `incident_id` khi còn một ngoại lệ `Chờ duyệt` hoặc `Đã duyệt` còn hiệu lực |
| 3. Thiết bị | Trình duyệt di động | `reported_at`, `gps_lat/lng` lấy tự động; ảnh chụp trực tiếp từ camera, không chọn từ thư viện (thuộc tính `capture`) |

Mỗi lần lớp 2 chặn là một sự kiện `blocked = true`. Tỷ lệ này là đầu vào của `P_supp` ở mục 10.

---

## 6. Phân quyền (row-level security)

Keycloak cấp vai qua claim `role`; Appsmith và Superset đọc claim này. Ở PostgreSQL:

| Vai | `incidents` | `exceptions` | `events` | Dashboard |
|---|---|---|---|---|
| reporter | Chỉ dòng có `reporter_email = current_user_email()`; dòng ẩn danh chỉ tra được bằng mã theo dõi | Không | Không | Không |
| safety, maintenance | `status = 'Ghi nhận' OR assignee_email = current_user_email()` (đúng công thức giáo trình) | Của mình + gắn với sự cố mình phụ trách | Đọc | Bảng cá nhân |
| manager | Toàn bộ khu vực mình phụ trách | Duyệt trong ngưỡng `approval_limit_vnd` | Đọc | Toàn bộ |
| director | Toàn bộ | Duyệt mọi ngưỡng | Đọc | Toàn bộ |
| `agent:*` | Đọc | Đọc, ghi `risk_score` | Ghi sự kiện của mình | Không |

Báo cáo ẩn danh: hệ thống trả cho người báo cáo một **mã theo dõi** (8 ký tự) ngay sau khi gửi;
không lưu email; ảnh bị xóa EXIF trước khi lưu. Cán bộ an toàn không thể thấy ai gửi.

---

## 7. Sự kiện tự động (Node-RED)

*(giáo trình)* ba sự kiện: ticket mới → email; khiếu nại → Telegram; đóng → CSAT. *(đội)* giữ đúng
ba nhịp đó, thêm một nhịp SLA.

| # | Kích hoạt | Hành động | Chống trùng |
|---|---|---|---|
| a | `incident.created` | Sinh mã theo dõi; gửi xác nhận (email hoặc chỉ hiển thị mã nếu ẩn danh); đánh thức tác tử (mục 9) | `notify_log.created` |
| b | `incident.accepted` với `severity ∈ {Nghiêm trọng}` **hoặc** `incident.created` với `incident_type = Tai nạn` | Đặt `equipment.status = Dừng`; gửi "🚨 DỪNG MÁY" tới kênh khu vực trên Nextcloud Talk hoặc Telegram, kèm ảnh và vị trí; tạo `actions.kind = Tức thời` "Cách ly khu vực" | `notify_log.alert` |
| c | `incident.completed` | Gửi khảo sát 1 câu "Điểm này đã an toàn chưa? 1–5" tới người báo cáo (link có mã theo dõi) | `notify_log.survey` |
| d | Mỗi 15 phút | Sự cố `status ∉ {Đóng, Hủy}` và `now() > sla_due_at` → gửi nhắc tới assignee và supervisor khu vực; tạo sự kiện `incident.sla_breached` | `notify_log.sla` (chỉ một lần cho mỗi mốc) |

Tất cả luồng Node-RED nằm trong `config/node-red/flows.json`, đọc địa chỉ dịch vụ từ biến môi
trường, không có `localhost` viết cứng.

---

## 8. Bàn phê duyệt ngoại lệ *(đội)*

Nguyên tắc: **mọi hành vi vượt quy tắc đều phải có một bản ghi `exceptions` còn hiệu lực**. Hệ thống
không cho làm việc đó bằng cách khác.

Bốn quy tắc bị "khóa cứng" và ngoại lệ tương ứng:

| Quy tắc | Khóa ở đâu | Ngoại lệ mở khóa |
|---|---|---|
| Thiết bị `Dừng` không được ghi nhận ca vận hành | `equipment.status` + trigger | `Vận hành khi sự cố mở`: có `valid_until`, có biện pháp giảm thiểu, người duyệt ≥ manager |
| Không dời `actions.due_at` sau khi đặt | Trigger từ chối `UPDATE due_at` | `Gia hạn thời hạn khắc phục`: tối đa 2 lần, mỗi lần ≤ 7 ngày |
| Sự cố Nghiêm trọng/Cao phải có biện pháp phòng ngừa mới đóng | Tiền điều kiện "Hoàn tất" | `Bỏ qua biện pháp bắt buộc`: chỉ director duyệt |
| Chi phí khắc phục ≤ `approval_limit_vnd` của người giao việc | Kiểm tra khi tạo `actions` có `cost_vnd` | `Chi phí vượt ngưỡng`: chuỗi duyệt manager → director theo ngưỡng |

Vòng đời ngoại lệ: `Chờ duyệt` → (`Đã duyệt` | `Từ chối`) ; `Đã duyệt` → `Hết hạn` khi
`now() > valid_until` (Node-RED quét 15 phút) hoặc `Thu hồi` bởi người duyệt. Ngoại lệ `Chờ duyệt`
quá 48 giờ tự chuyển `Từ chối` với ghi chú "hết hạn chờ". Người xin không được xin lại cùng
`kind` + `incident_id` trong 24 giờ sau khi bị từ chối.

Tác tử chấm `risk_score` trước khi người duyệt mở (mục 9). Người duyệt thấy: lý do, điểm rủi ro,
căn cứ, tiền lệ gần nhất, và ba nút Duyệt / Từ chối / Duyệt có điều kiện (bắt buộc rút
`valid_until`).

Chỉ số [D] từ bảng này: số ngoại lệ trên mỗi quy tắc mỗi tháng; quy tắc nào bị xin nhiều nhất là quy
tắc cần được sửa. Đây là vòng lặp học của tổ chức mà giáo trình gọi là "tiến hóa quy trình".

---

## 9. Tác tử [I]: hành vi chín bước *(giáo trình bài 8.5)* cho DX-Safety *(đội)*

Dịch vụ Python nhỏ (`i-agent`), LangChain + Ollama, mặc định **chỉ đọc**; quyền ghi cấp theo
phiên và chỉ với các công cụ đã khai báo.

| Bước | Việc | Công cụ tác tử được gọi |
|---|---|---|
| 1 | Sự kiện `incident.created` hoặc `exception.created` đánh thức | Node-RED → HTTP |
| 2 | Đọc lịch sử: sự cố cùng khu vực/thiết bị 12 tháng, ngoại lệ đã duyệt liên quan | `query_incidents`, `query_exceptions` (đọc) |
| 3 | RAG lấy điều khoản từ `[R]/10-GOVERNANCE`: nội quy an toàn, SOP dừng máy, hướng dẫn phân loại mức độ; và `kb_scenarios` | `search_docs` (pgvector, chỉ đọc `[R]`) |
| 4 | Chấm: đề xuất `severity` (sự cố) hoặc `risk_score` (ngoại lệ), kèm căn cứ trích dẫn | — |
| 5 | Lập kế hoạch JSON: danh sách hành động dự kiến | — |
| 6 | Phân loại hành động: **tự làm** (ghi `severity` đề xuất, ghi `risk_score`, tạo `actions` dạng nháp, gắn tiền lệ) hay **chờ duyệt** (đặt thiết bị `Dừng`, gửi thông báo ra ngoài nhóm khu vực, mọi thứ có `amount_vnd`) | `propose_action` / `request_approval` |
| 7 | Nếu có mục chờ duyệt: tạo bản ghi chờ trong hàng đợi của manager, dừng | — |
| 8 | Thực thi phần được phép hoặc đã duyệt | `set_equipment_status`, `notify_channel` (ghi, theo phiên) |
| 9 | Ghi audit: mỗi bước một sự kiện `actor = agent:safety-v1`, gồm prompt hash, tài liệu đã trích, hành động, kết quả | `events` |

Quy tắc bắt buộc: không có tiền lệ và không có SOP khớp thì ghi `[CHƯA CÓ TIỀN LỆ]`, không chấm
điểm, chuyển thẳng cho manager. Mọi kết quả LLM đều hiển thị nguồn trích dẫn; người dùng có thể
bấm "sai" và nêu lý do, lý do này được ghi vào `kb_scenarios` sau khi cán bộ an toàn duyệt.

Chế độ LLM: `LLM_MODE=local` (Ollama, Qwen3-8B hoặc Qwen2.5-7B, embedding bge-m3) là mặc định;
`LLM_MODE=api` chỉ là tùy chọn và phải ghi rõ trong tài liệu là dịch vụ ngoài, không phải thư viện
đính kèm.

---

## 10. Đồng hồ H% đo từ dữ liệu vận hành *(đội, công thức giáo trình bài 2.3–2.4)*

Giáo trình cho công thức `X% = (DTI_X / max) × X_supp × 30%` và `H% = 100 − (P + D + I)`, với hệ số
thực chứng `X_supp` chấm tay. DX-Safety **đo `X_supp` từ bảng `events`**, còn `DTI_X` lấy từ bảng
hỏi mini-DTI 3 câu (nhập một lần, sửa được).

| Hệ số | Giáo trình chấm tay | DX-Safety đo, cửa sổ 30 ngày trượt |
|---|---|---|
| `P_supp` | 0.33 silo, nhập tay / 0.66 API một phần, cho bypass / 1.0 end-to-end, chặn cứng | `1 − (số thao tác bị lớp 2 chặn + số bản ghi sửa tay + số ngoại lệ đã duyệt) / tổng chuyển trạng thái`; kẹp về ba mức 0.33 / 0.66 / 1.0 theo ngưỡng < 0.5 / < 0.9 / ≥ 0.9 |
| `D_supp` | 0 trễ theo ngày / 0.5 theo giờ / 1.0 real-time | Trung vị của `thời điểm dashboard cập nhật − occurred_at` trên các sự kiện; > 24 giờ → 0, > 1 giờ → 0.5, còn lại 1.0 |
| `I_supp` | 0 / 0.33 hỏi đáp / 0.66 phân tích, dự báo / 1.0 tác tử tự kích hoạt | Không có sự kiện `actor = agent:*` → 0; chỉ có `search_docs` → 0.33; có `severity`/`risk_score` đề xuất được chấp nhận ≥ 50% → 0.66; có hành động ghi được duyệt và thực thi → 1.0 |

Kết quả vẽ radar bốn trục H-P-D-I trên Superset (hoặc trang riêng trong cổng), có đường lịch sử
theo tuần và bốn nguyên mẫu của giáo trình ("Mũi giáo phân mảnh", "Cánh diều lệch tâm", "Ảo giác
công nghệ", "Kim cương toàn vẹn") làm mốc so sánh. Mọi số trên radar bấm vào được để xem truy vấn
SQL sinh ra nó. Cách đo này là đề xuất của đội, không phải chuẩn của giáo trình; tài liệu và phần
trình bày phải nói rõ như vậy.

---

## 11. Dashboard [D] (Superset)

*(giáo trình)* chia lagging và leading. *(đội)* cụ thể cho an toàn xưởng.

| Nhóm | Chỉ số | Nguồn |
|---|---|---|
| Lagging | Tổng sự cố theo loại và mức; thời gian xử lý trung bình; điểm "đã an toàn" trung bình | `incidents` |
| Leading | Tỷ lệ suýt xảy ra trên tai nạn (cao là tốt, chứng tỏ văn hóa báo cáo); sự cố mở quá SLA; tải theo người phụ trách; thiết bị có ≥ 2 sự cố trong 90 ngày; số ngoại lệ đang hiệu lực theo khu vực | `incidents`, `exceptions`, `events` |
| Quy trình | Tỷ lệ thao tác bị chặn theo màn hình; sự cố tái mở; ngoại lệ theo quy tắc | `events` |
| HPDI | Radar và lịch sử H% (mục 10) | `events`, bảng mini-DTI |

Lịch: PDF tổng hợp 08:00 ngày 1 hằng tháng vào `[R]/40-ASSETS/41-Structured_Data` cùng snapshot
`Snapshot_INCIDENTS_YYYYMM.csv` (đúng quy ước giáo trình). Xuất dữ liệu mở: `GET /open-data/incidents.jsonld`
với `@context` schema.org, đã ẩn danh và gộp theo khu vực, tuần; đây là phần "bảo hiểm rẻ" cho ý
kế thừa OLP 2025.

---

## 12. Dữ liệu mẫu và SOP trong `[R]`

Thư mục `seed/` gồm:

- `areas.csv` 4 khu vực (Tiện, Phay CNC, Hàn, Kho); `equipment.csv` 12 thiết bị; `people.csv` 14 người
  đủ 5 vai, mật khẩu demo nạp vào Keycloak bằng script.
- `incidents.csv` 80 sự cố trong 90 ngày, phân bố 55 suýt xảy ra / 20 điều kiện mất an toàn /
  5 tai nạn, 10 sự cố còn mở trong đó 3 quá SLA, 4 sự cố tái mở; `actions.csv` tương ứng.
- `exceptions.csv` 9 ngoại lệ: 5 đã duyệt, 2 từ chối, 1 hết hạn, 1 chờ duyệt (dùng cho demo).
- `events.csv` sinh từ các bảng trên bằng script, có 12% thao tác bị chặn để H% ra khoảng 35–45%.
- `resources/` chép lên Nextcloud khi seed: `10-GOVERNANCE/Noi_quy_an_toan.md`,
  `SOP_Dung_may_khan_cap.md`, `Huong_dan_phan_loai_muc_do.md`, `Chinh_sach_ngoai_le.md`;
  `20-EXPERIENCE/Bai_hoc_su_co_2025.md`; `kb_scenarios.csv` 25 tình huống. Toàn bộ là Markdown,
  đúng yêu cầu định dạng mở của giáo trình bài 7.3, và là tài liệu do đội tự viết (Apache-2.0).

Khi có đề tháng 11: thêm một thư mục `domains/<tên>/` gồm `domain.yaml` (enum, SLA, ngưỡng, nhãn
màn hình), `schema-ext.sql` (cột nghiệp vụ thêm vào khuôn 17 cột), `resources/`, `seed/`, `demo.md`.
Máy trạng thái, Poka-yoke, sự kiện, ngoại lệ, tác tử, đồng hồ H% giữ nguyên. Cơ chế này được chứng
minh trước bằng gói thứ hai `domains/dx-ticket/` (xem `du-bao-de-thi-2026.md` mục 4.3).

---

## 13. Kịch bản demo 15 phút *(đội)*

Máy demo: một laptop 16 GB, `make up-all` xong trước; Ollama đã pull model. Dự phòng: video quay
sẵn cho bước 4 và 6 nếu LLM chậm.

| Phút | Cảnh | Điều ban giám khảo thấy | Trục |
|---|---|---|---|
| 0–1 | Bối cảnh | Một xưởng thật, sổ tay an toàn chụp ảnh, ba nỗi đau (mục 1) | — |
| 1–3 | Công nhân báo sự cố | Quét QR ở máy phay, form hiện sẵn khu vực, chụp ảnh, chọn "Suýt xảy ra", bật ẩn danh, nhận mã theo dõi. Thử gửi không ảnh: bị chặn ngay | [H][P] |
| 3–5 | Tác tử làm việc | Trong 10 giây: `severity` đề xuất "Cao", trích dẫn đoạn SOP phân loại, tìm thấy 2 sự cố cùng máy trong 90 ngày, tạo nháp biện pháp phòng ngừa. Không tự dừng máy vì chưa được duyệt | [I] |
| 5–7 | Cán bộ an toàn | Mở hàng đợi, xác nhận mức "Cao", bấm Nhận. Thử bấm Hoàn tất ngay: bị chặn vì chưa có nguyên nhân gốc và chưa có biện pháp phòng ngừa; sự kiện `blocked` xuất hiện trong nhật ký | [P] |
| 7–9 | Ngoại lệ | Tổ trưởng xin "Vận hành khi sự cố mở" 2 ngày để kịp đơn hàng. Tác tử chấm rủi ro 72/100, dẫn tiền lệ bị từ chối tháng trước. Quản đốc duyệt có điều kiện, rút còn 1 ngày. Thử xin lại cùng nội dung: bị chặn | [P][I] |
| 9–11 | Đóng vòng | Kết luận nguyên nhân, đánh dấu biện pháp xong, Hoàn tất. Công nhân nhận khảo sát, chấm 5. Sự cố Đóng, thiết bị về Vận hành, kênh Talk nhận thông báo | [P][H] |
| 11–13 | Dashboard | Superset: chỉ số dẫn trước, thiết bị tái phát, ngoại lệ theo quy tắc. Bấm một số để xem SQL | [D] |
| 13–14 | Đồng hồ H% | Radar đổi từ "Cánh diều lệch tâm" sang gần "Kim cương" sau 90 ngày dữ liệu; giải thích cách đo và nói rõ đây là đề xuất của đội | [D][I] |
| 14–15 | Nguồn mở | `DEPENDENCIES.md` sinh tự động từ image, CI kiểm giấy phép, release `.tar.gz` + `.sha256`, hướng dẫn build from source đã chạy trên máy sạch | PoF |

Câu chốt: "Không một thành phần nào ở đây là của Google, và không một thao tác nào vượt quy tắc mà
không để lại dấu vết."

---

## 14. Việc cần làm và quyết định còn mở

| # | Việc | Phụ thuộc | Đầu ra |
|---|---|---|---|
| 1 | Viết `db/schema.sql` cho mục 3, gồm trigger chuyển trạng thái và RLS | QĐ-002 | Chạy được bằng `make seed` |
| 2 | Dựng form và hàng đợi trên Appsmith CE; song song thử Frappe Helpdesk 2 ngày | Mục 6.4 bản nghiên cứu, việc 4 | QĐ-004 chọn nền [P] |
| 3 | Luồng Node-RED cho 4 sự kiện mục 7 | 1, 2 | `config/node-red/flows.json` |
| 4 | Dịch vụ `i-agent` với 6 công cụ ở mục 9, chế độ local | 1 | Image build từ `services/i-agent/Dockerfile` |
| 5 | Dashboard Superset và trang radar H% | 1 | Xuất `config/superset/dashboards.zip` |
| 6 | Script sinh `seed/` và đẩy `resources/` lên Nextcloud | 1 | `make seed` |
| 7 | Viết `docs/demo-script.md` chi tiết theo mục 13 và quay video dự phòng | 2–5 | Video ≤ 5 phút |

Quyết định còn mở, cần bản ghi trong `architecture.md`:

- **QĐ-004** nền [P]: Appsmith CE hay Frappe Helpdesk (tiêu chí: RLS theo claim Keycloak, webhook,
  form công khai, RAM).
- **QĐ-005** kênh cảnh báo: Nextcloud Talk (một nền tảng, AGPL sạch) hay Telegram (quen với xưởng,
  nhưng là dịch vụ ngoài). Đề xuất: Talk mặc định, Telegram là tùy chọn qua Node-RED.
- **QĐ-006** đồng hồ H%: có đưa ngưỡng kẹp 0.33 / 0.66 / 1.0 vào `config/domain.yaml` để người dùng
  tự chỉnh không, hay cố định để khỏi bị "chỉnh cho đẹp".

Ba câu cần hỏi người làm an toàn thật (giảng viên khoa cơ khí hoặc một xưởng quen): mức độ và SLA
ở mục 3.2 có hợp lý không; ngoại lệ nào hay xảy ra nhất; báo cáo ẩn danh có được chấp nhận trong
văn hóa xưởng không.
