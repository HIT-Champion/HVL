# OLP PMNM 2026 — Phân tích đề thi chính thức

> Nguồn: [Đề thi Phần mềm nguồn mở - OLP 2026](https://vfossa.vn/tin-tuc/de-thi-phan-mem-nguon-mo-olp-2026-798.html)
> (VFOSSA, đăng **Thứ tư 30/09/2026**). Tổng hợp ngày 01/10/2026.
> Đọc kèm [`olp-2026-brief.md`](olp-2026-brief.md) (thể lệ + thang điểm) và
> [`pof-checklist.md`](pof-checklist.md).

---

## 0. TL;DR

- **Tên đề**: *Xây dựng Hệ điều hành Chuyển đổi số bằng Công nghệ Lõi nguồn mở (DX-OS Open-Core)*.
- **Phải nộp gì**: một mô hình **DX-OS Open-Core** gồm
  1. **Tầng 1 — nền tảng dịch vụ lõi chạy ngầm (headless), KHÔNG có UI**, hoạt động như PaaS, bắt
     buộc có: **Identity/SSO · API Gateway · Quản trị dữ liệu có cấu trúc + phi cấu trúc · Workflow engine**;
  2. **≥ 1 ứng dụng minh họa có giao diện** thuộc một không gian H-P-D-I ở **Tầng 2**.
- **Hạn nộp**: **17:00 Chủ Nhật 06/12/2026** (đề in nhầm "06/12/2025" — **đã xác nhận là 2026**). Từ hôm nay còn **~66 ngày**.
- **Đề ra sớm hơn dự kiến** (brief cũ ghi tháng 11) → có thêm ~5 tuần so với kế hoạch.
- **Thay đổi lớn nhất so với kế hoạch hiện tại của repo**: trọng tâm chuyển từ "lắp đủ 4 trục
  H-P-D-I bằng các ứng dụng có giao diện" sang **"một lõi PaaS headless + một ứng dụng chứng minh"**.
  Kiến trúc trong `docs/architecture.md` và `docker-compose.yml` cần tổ chức lại theo **3 tầng**.
- **Bẫy giấy phép**: bảng công nghệ tham chiếu của BTC có **5 thành phần không được OSI phê duyệt**
  (Vault, n8n, Redpanda, MongoDB, immudb), Orion kéo theo MongoDB, còn MinIO đã ngừng phát triển. Dùng
  nguyên bảng sẽ va vào tiêu chí PoF #2 và chính chính sách trong `DEPENDENCIES.md`. Xem §5.

---

## 1. Thông tin hành chính

| Hạng mục | Nội dung |
|---|---|
| Ngày công bố đề | 30/09/2026 |
| Hạn nộp bài | **17:00 Chủ Nhật 06/12/2026** |
| Chấm kho mã nguồn (PoF) | 7–9/12/2026 (theo thể lệ) |
| Chung kết + trình diễn | 10/12/2026 (theo thể lệ) |
| Nơi nhận bài | `olpvietnam@vaip.vn`, `thuky@vfossa.vn` |
| Tiêu đề thư | `BÀI THI PMNM 2026 - [Tên Đội] - [Tên Trường]` |
| Hỏi đáp | Nhóm Telegram <https://t.me/+YUkj6aM3bnYyOWQ1> |

**Về ngày "06/12/2025" trong đề**: lỗi đánh máy ở bản đăng đầu tiên — **hạn là 17:00 06/12/2026**; trang
đề trên vfossa.vn đã sửa thành 2026 (kiểm tra 15/10/2026). Hạn nội bộ: gửi thư **05/12/2026**.

**Nội dung thư (mẫu của BTC)**:

```text
Kính gửi BTC cuộc thi PMNM 2026,
Đội thi [Tên Đội] - [Tên Trường] đã hoàn thành bài thi và xin gửi BTC kết quả như sau
Thành viên đội
- Tên thành viên 1, năm sinh, ngành đào tạo
- Tên thành viên 2, năm sinh, ngành đào tạo
- Tên thành viên 3, năm sinh, ngành đào tạo
Người hướng dẫn: Tên Thầy/Cô - Khoa/Viện/Trường
Kho mã nguồn dự thi: [đường dẫn truy cập kho mã nguồn chứa đầy đủ nội dung kết quả dự thi]
Đội thi đã hoàn thành việc đăng kí dự thi theo đúng quy định của BTC thông qua [Tên Trường].
Chúng tôi cam kết toàn bộ bản quyền sử dụng đối với sản phẩm dự thi tuân thủ theo đúng các quy
tắc của phần mềm tự do nguồn mở.
```

Lưu ý: thư cam kết đã **đăng ký qua trường** — cần kiểm tra trường đã gửi danh sách đội cho BTC chưa.

**Buổi chung kết**: 15 phút/đội trước Ban Giám khảo, gồm 4 phần:
(1) giải pháp thiết kế và lựa chọn công nghệ · (2) tính năng nền tảng và bài toán ứng dụng minh họa ·
(3) kết quả sản phẩm và demo · (4) định hướng phát triển (nếu có).
BTC **khuyến khích chạy trên Internet** để người dùng truy cập và phản hồi.

---

## 2. Bối cảnh đề: Khung kiến trúc DX-OS 3 tầng

Đề giải bài toán hai thái cực khi đầu tư CĐS: (1) mua nhiều phần mềm rời rạc → **ốc đảo dữ liệu**;
(2) mua một hệ thống nguyên khối → **thành "con tin" của một nhà cung cấp**. Lời giải: kiến trúc
**phân tách 3 tầng** ("phân tách mối quan tâm") + **ưu tiên nguồn mở** để giữ **chủ quyền số**.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ TẦNG 3 — Nền tảng Kinh doanh số (ứng dụng ngành, cắm-rút)                    │
│  Hàng hóa (OMS/WMS/POS/TMS) · Thời gian & Dự án (PSA/Timesheet/CDE-BIM)      │
│  Trải nghiệm & Thuê bao (eKYC-AML/LMS/EMR/CRM) · Tài sản & Không gian        │
│  (MES-SCADA/BMS/Smart City IoT)                                    KHÔNG BẮT BUỘC │
├──────────────────────────────────────────────────────────────────────────────┤
│ TẦNG 2 — Không gian Năng lực số H → P → D → I (có giao diện end-user)        │
│  [H] Cổng tập trung, Drive, Kanban & Lịch, Wiki, App di động hiện trường     │
│  [P] Thanh toán & đối soát, HĐĐT, giải mã tài liệu trên RAM, e-Office,       │
│      HRM & KPI, Quản lý dự án, thiết kế biểu mẫu & quy trình BPMN            │
│  [D] Kho ẤM: NGSI-LD, Lakehouse, WebGIS, IOC/BI, DaaS, Data Lineage          │
│      Kho LẠNH: phòng đọc ảo chống sửa xóa, sổ cái mật mã bất biến            │
│  [I] Tìm kiếm toàn văn + véc-tơ, cổng giám sát AI agent, OCR, trợ lý RAG     │
│                                                   BẮT BUỘC ≥ 1 ỨNG DỤNG       │
├──────────────────────────────────────────────────────────────────────────────┤
│ TẦNG 1 — Nền tảng Dịch vụ Lõi số (PaaS, HEADLESS, không UI)                  │
│  ① Định danh, bảo mật, ATTT   ② Đa thuê ước, biên mạng, cá thể hóa           │
│  ③ Dữ liệu có cấu trúc & giao dịch   ④ Dữ liệu phi cấu trúc & hồ sơ          │
│  ⑤ Quy trình & tự động hóa   ⑥ Vận hành, giám sát, kiểm toán                 │
│  ⑦ Truyền thông & giao vận dữ liệu                                           │
│                              BẮT BUỘC: Identity/SSO · API GW · Data · Workflow │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2.1. Chi tiết 7 cụm dịch vụ Tầng 1 (nguyên văn đề, rút gọn)

| # | Cụm | Năng lực đề liệt kê |
|---|---|---|
| ① | Định danh, Bảo mật, ATTT | SSO, MFA; két sắt quản lý vòng đời khóa & bí mật; trạm kiểm dịch tệp tin; động cơ chữ ký số/mã hóa (PKI, HSM) |
| ② | Đa thuê ước, Biên mạng, Cá thể hóa | API Gateway zero-trust; rà soát & che giấu PII; multi-tenancy cách ly dữ liệu; dịch thuật/bản địa hóa đa ngôn ngữ |
| ③ | Dữ liệu có cấu trúc & Giao dịch | OLTP toàn vẹn; **tự sinh API từ CSDL, phân quyền tới cấp dòng**; quản lý phiên bản & lịch sử biến động; đóng băng số liệu chuỗi thời gian; lớp ngữ nghĩa báo cáo |
| ④ | Dữ liệu phi cấu trúc & Hồ sơ | lưu trữ đối tượng; quản lý hồ sơ/văn bản cho quy trình phê duyệt; chỉ mục toàn văn; trộn dữ liệu sinh biểu mẫu/báo cáo động |
| ⑤ | Quy trình & Tự động hóa | **BPMN** quản lý trạng thái luồng phê duyệt; thực thi kịch bản serverless; API nạp dữ liệu khối lớn theo lô |
| ⑥ | Vận hành, Giám sát, Kiểm toán | log truy vết phân tán + kiểm toán bất biến; trục streaming sự kiện; **GitOps**; sao lưu & khôi phục thảm họa |
| ⑦ | Truyền thông & Giao vận | định tuyến thông báo đa kênh; websocket thời gian thực; hàng đợi bất đồng bộ chống chối bỏ |

**Chỉ 4 dịch vụ là bắt buộc**; 7 cụm là kiến trúc đầy đủ để tham chiếu. Phủ thêm cụm nào là điểm cộng
ở *Tính nguyên gốc* và *Mức độ hoàn thiện*, không phải điều kiện.

---

## 3. Yêu cầu của đề (phân loại)

### 3.1. BẮT BUỘC

| Mã | Yêu cầu | Nguyên văn đề |
|---|---|---|
| R1 | Có **Tầng 1 headless** | "nền tảng dịch vụ lõi chạy ngầm (headless) ở Tầng 1" |
| R2 | Tầng 1 **không có UI**, chỉ là PaaS | "hoàn toàn không cung cấp giao diện UI mà chỉ hoạt động như một PaaS để cung cấp dịch vụ cho các ứng dụng hoạt động ở tầng trên" |
| R3 | Dịch vụ **Identity/SSO** | "Định danh bảo mật (Identity/SSO)" |
| R4 | Dịch vụ **API Gateway** | "Cổng API (API Gateway)" |
| R5 | Quản trị **dữ liệu có cấu trúc VÀ phi cấu trúc** | "Quản trị dữ liệu cấu trúc/phi cấu trúc" |
| R6 | **Workflow engine** | "Động cơ luồng công việc (Workflow)" |
| R7 | **≥ 1 ứng dụng minh họa có giao diện** ở Tầng 2, thuộc H-P-D-I | "ít nhất một ứng dụng minh họa giao diện nằm trong không gian H-P-D-I ở Tầng 2" |
| R8 | Kho mã nguồn mở, giấy phép OSI | Thể lệ + PoF #2 (*"có giấy phép mở **và giải quyết đúng đầu bài**"*) |

> Chú ý R8: ghi chú BTC ở tiêu chí PoF #2 (10đ) gắn **"giải quyết đúng đầu bài"** vào điểm giấy
> phép. Thiếu R1–R7 có thể mất điểm ngay ở phần PoF, không chỉ ở phần sản phẩm.

### 3.2. KỲ VỌNG (4 nguyên lý thiết kế — "cần được xây dựng dựa trên")

| # | Nguyên lý | Bằng chứng nên có trong demo |
|---|---|---|
| (i) | Phân tách theo **vòng đời & tốc độ dữ liệu**: OLTP nóng ở tầng nghiệp vụ, tự động đẩy lịch sử xuống hồ dữ liệu, không nghẽn lõi | Job định kỳ/CDC chuyển bản ghi đã đóng từ PostgreSQL sang kho lạnh (Parquet trên object storage); truy vấn phân tích chạy trên bản lạnh |
| (ii) | **Hội tụ IT/OT**: nối quy trình nghiệp vụ với dữ liệu cảm biến → bản sao số thời gian thực | Bộ giả lập cảm biến đẩy dữ liệu → context broker (NGSI-LD) → sự kiện kích hoạt workflow |
| (iii) | **Quản trị dữ liệu thế hệ mới**: tự động hóa dòng chảy, kiểm soát **phả hệ, nguồn gốc, chất lượng** trên báo cáo | Lineage hiển thị được: báo cáo X ← bảng Y ← sự kiện Z; kiểm tra chất lượng dữ liệu tự động |
| (iv) | **Zero-Trust + GitOps**: kiểm dịch mã độc tại biên, hạ tầng bằng mã, **tự phục hồi** | Upload tệp nhiễm EICAR bị chặn ở gateway; xóa một container → hệ thống tự dựng lại từ cấu hình trong git |

### 3.3. TỰ DO

- **Toàn quyền chọn công nghệ.** Bảng 7 lớp của BTC chỉ là "giải pháp tham chiếu … để minh họa làm ví dụ".
- Gợi ý mô hình headless tham khảo: **Supabase / Strapi / Directus**.
- Không bắt buộc Tầng 3.

---

## 4. Bảng công nghệ tham chiếu của BTC (7 lớp)

| Lớp | Công nghệ BTC gợi ý | Vai trò |
|---|---|---|
| 1. Trải nghiệm & Giao diện đa kênh | Nuxt 3 / Vue 3, Flutter, Centrifugo, Tailwind CSS | UI web/mobile, realtime WebSocket |
| 2. Biên mạng, Cửa ngõ & ATTT | Apache APISIX, Keycloak, HashiCorp Vault, ClamAV & Coraza WAF | Zero-trust, SSO/MFA, bí mật, kiểm dịch mã độc |
| 3. Tác nghiệp, Logic & Trạng thái thực thể | Hasura GraphQL, PostgreSQL (+PostGIS), MongoDB, Orion Context Broker | OLTP, tự sinh API, NGSI-LD / digital twin |
| 4. Tự động hóa, Quy trình & DevSecOps | ArgoCD & GitLab CI, Flowable (BPMN) & n8n, Kestra, Velero | GitOps, BPMN, kịch bản ngầm, backup/DR |
| 5. Dữ liệu siêu hội tụ, Truyền phát & Sổ cái | Redpanda, Apache Iceberg, MinIO, ImmuDB | Streaming, Lakehouse, object storage, sổ cái bất biến |
| 6. Phân tích, Không gian & Trí tuệ | Trino & DuckDB, GeoServer, Metabase & Cube.dev, Ollama / vLLM | Truy vấn phân tán, GIS, BI, LLM nội bộ |
| 7. Quản trị, Tìm kiếm & Giám sát | Vector & Parseable, OpenMetadata, Meilisearch & Qdrant, Prometheus / Grafana | Log, lineage, tìm kiếm toàn văn + véc-tơ, giám sát |

Bảng này có **~35 thành phần** — chạy hết cần cụm máy chủ cỡ vài chục GB RAM, mâu thuẫn trực tiếp với
ràng buộc "chạy được trên máy chủ 8 GB" ở `docs/architecture.md` §1.3. Cần chọn lọc (xem §6).

---

## 5. Kiểm tra giấy phép bảng tham chiếu

Đối chiếu tệp LICENSE trên GitHub và thông báo chính thức của từng dự án (kiểm tra 01/10/2026).

### 5.1. Thành phần có vấn đề

| Thành phần | Giấy phép hiện tại | OSI? | Vấn đề | Thay thế (OSI) |
|---|---|---|---|---|
| **HashiCorp Vault** | BUSL-1.1 (từ v1.15, 08/2023) | ❌ | Bản MPL cuối (≤1.14) đã hết hỗ trợ | **OpenBao** (MPL-2.0, Linux Foundation, image `openbao/openbao`) |
| **n8n** | Sustainable Use License (fair-code, từ 03/2022) | ❌ | Giáo trình DX-OS dùng n8n nhiều, nhưng không phải nguồn mở theo OSI | **Kestra** (Apache-2.0, đã có trong bảng), Node-RED (Apache-2.0) |
| **Redpanda** | BSL-1.1 + Redpanda Community License | ❌ | Mỗi bản chỉ chuyển sang Apache-2.0 sau 4 năm | **Apache Kafka** chế độ KRaft (Apache-2.0) |
| **MongoDB** | SSPL-1.0 (từ 10/2018) | ❌ | OSI đã từ chối SSPL | Bỏ hẳn — dùng PostgreSQL JSONB; nếu cần giao thức Mongo: DocumentDB (MIT) / FerretDB (Apache-2.0, đang chậm lại) |
| **immudb** | BUSL-1.1 (từ 12/2023) | ❌ | Bản Apache cũ không còn bảo trì | Bảng kiểm toán chuỗi băm (hash-chain) trong PostgreSQL, hoặc Trillian (Apache-2.0) |
| **Orion / Orion-LD** | AGPL-3.0 | ✅ nhưng… | **Bắt buộc MongoDB (SSPL)** → kéo thành phần không-OSI vào stack. Orion *cổ điển* chỉ hỗ trợ **NGSIv2, không phải NGSI-LD** như đề yêu cầu | **Scorpio** (BSD-3-Clause, chạy trên PostgreSQL) |
| **MinIO** | AGPL-3.0 | ✅ nhưng **đã chết** | Bỏ console khỏi bản community (2025), ngừng phát hành image/binary (10/2025), chế độ bảo trì (12/2025), lưu trữ (archived) 2026 — `minio/minio` trên Docker Hub không còn | **SeaweedFS** (Apache-2.0, hoạt động mạnh) hoặc Garage (AGPL-3.0) |
| **Hasura** | v2: Apache-2.0 · v3/DDN: chưa rõ | ⚠️ | Từ v2.12 image mặc định có phần EE độc quyền | Dùng **tag `vX.Y.Z-ce`** của v2, hoặc PostgREST (MIT) |
| **Directus** (đề nêu làm ví dụ) | BSL-1.1 (v10–11) → MSCL (v12) | ❌ | Chỉ dùng làm *ý tưởng* headless, không đưa vào stack | Supabase (OSI toàn bộ), Payload CMS (MIT) |
| **Strapi** (đề nêu làm ví dụ) | MIT + thư mục `ee/` độc quyền trong cùng gói | ⚠️ | Mã EE nằm chung gói, chỉ bị khóa bằng license key | Cân nhắc kỹ nếu dùng |

### 5.2. Thành phần dùng được, nhưng phải chọn đúng bản

| Thành phần | Chọn | Tránh |
|---|---|---|
| Hasura v2 | image tag `-ce` | tag mặc định (có EE) |
| Grafana | `grafana/grafana` (AGPL-3.0) | `grafana/grafana-enterprise` |
| Metabase | `metabase/metabase` (AGPL-3.0) | `metabase/metabase-enterprise` |
| Meilisearch | `getmeili/meilisearch` (MIT) | bản enterprise (BUSL) |
| GitLab | `gitlab/gitlab-ce` (MIT) | `gitlab-ee` |
| Centrifugo | `centrifugo/centrifugo` (Apache-2.0) | bản PRO |
| Ollama | phần mềm MIT, **nhưng trọng số mô hình có giấy phép riêng**: Llama, Gemma không phải OSI | Chọn mô hình trọng số Apache-2.0 (vd. dòng Qwen3, Mistral 7B) |
| Flowable | `flowable/flowable-rest` (Apache-2.0) — từ 7.0 chỉ còn bản REST, **không có UI** → hợp yêu cầu headless | — |

### 5.3. Ổn, không cần lưu ý thêm

Nuxt/Vue, Tailwind CSS, Flutter (MIT/BSD) · APISIX, Keycloak, ArgoCD, Coraza, Iceberg, Trino, vLLM,
Qdrant, Prometheus, OpenMetadata, Kestra, Velero, Cube (Apache-2.0) · PostgreSQL · PostGIS, GeoServer,
ClamAV (GPL-2.0, chạy như dịch vụ độc lập) · DuckDB (MIT) · Vector (MPL-2.0) · Parseable (AGPL-3.0) ·
Supabase (Apache-2.0/MIT/PostgreSQL License).

> **Cơ hội ghi điểm**: phát hiện và thay thế các thành phần không-OSI trong bảng tham chiếu là một
> "quyết định thiết kế" đáng trình bày ở phần 1 của buổi chung kết, và là bằng chứng trực tiếp cho
> tiêu chí PoF #2 (không xung đột giấy phép). Ghi lại từng thay thế thành ADR.

---

## 6. Đề xuất phương án

> Bản chi tiết đã rà soát nằm ở [`ke-hoach-phat-trien.md`](ke-hoach-phat-trien.md). Nếu hai tài liệu
> khác nhau, **kế hoạch là bản đúng**.

### 6.1. Lõi tối thiểu (Tầng 1) phủ đủ R3–R6

Bám sát bảng tham chiếu của BTC (giám khảo quen thuộc), thay các thành phần không-OSI ở §5.

**Bắt buộc (R3–R6):**

| Dịch vụ | Chọn | Giấy phép | Vì sao |
|---|---|---|---|
| Identity/SSO + MFA | **Keycloak** | Apache-2.0 | OIDC/SAML, MFA TOTP sẵn có; realm/organization phục vụ đa thuê ước (cụm ②) |
| API Gateway zero-trust | **Apache APISIX** (chế độ standalone, cấu hình YAML) | Apache-2.0 | Plugin `openid-connect` xác thực JWT ngay tại biên; cấu hình khai báo nằm trong git → làm nền cho GitOps (nguyên lý iv) |
| Dữ liệu có cấu trúc | **PostgreSQL 16 + Hasura v2 `-ce`** | PostgreSQL / Apache-2.0 | Tự sinh GraphQL API, **phân quyền cấp dòng** — khớp nguyên văn cụm ③; Event Triggers phát sự kiện mà không cần thêm message broker |
| Dữ liệu phi cấu trúc | **SeaweedFS** (S3 API) + **Meilisearch** CE | Apache-2.0 / MIT | Lưu trữ đối tượng + chỉ mục toàn văn (cụm ④) |
| Workflow | **Flowable REST** 8.0 | Apache-2.0 | BPMN chuẩn; từ 7.x chỉ còn bản REST, không có UI → headless tự nhiên |

**Tùy chọn — làm bằng chứng cho 4 nguyên lý (§3.2):**

| Năng lực | Chọn | Giấy phép | Phục vụ |
|---|---|---|---|
| Kiểm dịch tệp | ClamAV (quét trước khi ghi vào object storage) — kế hoạch đưa vào lõi từ Phase 1 | GPL-2.0 (dịch vụ độc lập) | (iv) |
| Két sắt bí mật | OpenBao | MPL-2.0 | (iv), cụm ① |
| Kiểm toán bất biến | Bảng audit chuỗi băm trong PostgreSQL | — (mã của đội) | cụm ⑥ |
| Dữ liệu lạnh | Job định kỳ xuất Parquet sang SeaweedFS, truy vấn bằng DuckDB | MIT | (i) |
| Giám sát | Prometheus + Grafana (`grafana/grafana`) | Apache-2.0 / AGPL-3.0 | cụm ⑥ |
| NGSI-LD / digital twin | Scorpio + bộ giả lập cảm biến | BSD-3-Clause | (ii) — bản rút gọn ở Phase 3 |

**Giao diện Tầng 2**: Nuxt 4 / Vue 3 + Tailwind CSS (MIT) — theo gợi ý của BTC, nâng từ Nuxt 3 lên Nuxt 4 là dòng chính hiện tại.

**Ước lượng tài nguyên** (chưa đo, cần kiểm chứng ở tuần 2): lõi bắt buộc + ClamAV ≈ 4–6 GB RAM
(ClamAV riêng đã ~1–1,5 GB do nạp CSDL chữ ký vào RAM). Vẫn trong ngưỡng 8 GB nếu **chưa** bật LLM cục bộ.

**Quyết định còn mở — GitOps**: Argo CD (gợi ý của BTC) đòi Kubernetes, mâu thuẫn QĐ-003 (chỉ dùng
Compose). Hai hướng: (a) chuyển sang k3s một node + Argo CD — đúng bảng tham chiếu, tốn thêm ~1–2 GB
RAM và độ phức tạp; (b) giữ Compose + cơ chế *pull* định kỳ từ git rồi `docker compose up` để tự hội tụ
— nhẹ, nhưng phải giải thích được với giám khảo. **Kế hoạch chọn (b)** — QĐ-006.

**Vì sao không đứng trên Supabase**: Supabase là PaaS headless OSI hoàn chỉnh (Auth, REST, Storage,
Realtime), nhưng **không có workflow BPMN** và Auth của nó không phải IdP SSO đầy đủ. Quan trọng hơn,
dựng lại Supabase dễ bị xem là "triển khai sản phẩm có sẵn", yếu ở tiêu chí *Tính nguyên gốc*. Tự lắp
lõi theo bảng của BTC, với một gateway và một bộ tài liệu API thống nhất, cho thấy rõ phần đóng góp
của đội.

### 6.2. Ứng dụng Tầng 2: chọn **[P] Văn phòng điện tử — quản lý văn bản và điều hành**

> Cập nhật 15/10/2026: thay hướng "luồng phê duyệt đề xuất" bằng quản lý văn bản đến / đi theo
> NĐ 30/2020, kèm cổng xác thực văn bản công khai. So sánh phương án, kho mã các đội khác, phạm vi và
> kịch bản demo: [`dac-ta-san-pham.md`](dac-ta-san-pham.md).

Lý do:

1. **Đúng Tầng 2, tránh vùng Tầng 3.** Đề định nghĩa Tầng 2 là "các cổng dịch vụ nghiệp vụ **dùng
   chung**" và nêu đích danh "Văn phòng điện tử (e-Office)" trong [P]. Ứng dụng chuyên ngành (tài sản,
   tòa nhà, sản xuất, bán hàng, CRM…) đề xếp ở Tầng 3; chọn chúng làm ứng dụng minh họa có rủi ro bị
   coi là thiếu R7, kéo theo điểm PoF #2 ("giải quyết đúng đầu bài").
2. **Đúng nghĩa "văn phòng điện tử" ở Việt Nam**: hệ thống quản lý văn bản và điều hành theo NĐ 30/2020
   — người ở cơ quan nào cũng nhận ra.
3. **Một kịch bản chạm đủ 4 dịch vụ bắt buộc**: đăng nhập SSO → tải công văn qua trạm kiểm dịch (dữ liệu
   phi cấu trúc) → luồng BPMN vào sổ, chỉ đạo, xử lý (workflow) → bản ghi phân quyền cấp dòng (dữ liệu có
   cấu trúc) → mọi lời gọi đi qua API Gateway.
4. **Chạm nhiều năng lực đề nêu tên mà không phải gắn thêm**: cụm ④ gần như nguyên văn (quản lý hồ sơ,
   văn bản cho phê duyệt; chỉ mục toàn văn; trộn dữ liệu sinh biểu mẫu), "giải mã an toàn tài liệu trên
   RAM" ở [P], "phòng đọc ảo chống sửa xóa" và "cổng đối soát sổ cái mật mã bất biến" ở kho lạnh [D].
5. **Câu chuyện chủ quyền số có thật**: phần mềm quản lý văn bản phổ biến là sản phẩm đóng; chưa thấy
   bản nguồn mở nào còn hoạt động.
6. **Có người dùng thật trong trường**: văn thư khoa; dữ liệu mẫu là công văn trường đã công bố.

Thứ tự tiến hóa tuyến tính vẫn giữ: [P] cần [H] (danh tính) làm nền và sinh dữ liệu sạch cho dashboard
[D] và trợ lý [I] trên chính kho văn bản.

### 6.3. Tái cấu trúc repo theo 3 tầng

| Hiện tại | Đề xuất |
|---|---|
| Compose profile theo trục `h`, `p`, `d`, `i` | Profile theo tầng: `core` (Tầng 1) · `app` (Tầng 2) · `ops`, `ai` (mở rộng) |
| `[H]` chứa SSO như một ứng dụng | SSO, gateway, dữ liệu, workflow chuyển xuống **Tầng 1**; [H] ở Tầng 2 chỉ còn ứng dụng có UI |
| Thiếu khái niệm "headless" | Chỉ API Gateway được publish cổng ra ngoài, với route danh sách trắng (chặn `/admin` của Keycloak, `/v1/metadata` của Hasura); giao diện quản trị chỉ mở trong mạng nội bộ |
| Giá trị nằm ở "lớp keo" (đúng) | Lớp keo cụ thể hóa thành: cấu hình gateway thống nhất, một tài liệu API (OpenAPI/GraphQL) cho toàn lõi, SDK/CLI cho ứng dụng Tầng 2, quy ước sự kiện, kịch bản cấp phát thuê ước |

---

## 7. Lộ trình

Lộ trình chi tiết theo phase (chức năng, thành phần mã nguồn mở, tiêu chí hoàn thành, phân công) nằm ở
[`ke-hoach-phat-trien.md`](ke-hoach-phat-trien.md). Hai mốc cần nhớ: release đầu tiên phải có **trước
thời điểm nộp bài** (PoF #3) — kế hoạch ra `v0.1.0` ngày 25/10; gửi thư nộp bài **05/12**.

---

## 8. Câu hỏi nên gửi BTC (nhóm Telegram)

1. ~~Hạn nộp in trong đề là "06/12/**2025**" — BTC xác nhận là **17:00 06/12/2026**?~~ ✅ Đã rõ: 06/12/2026.
2. "Tầng 1 hoàn toàn không cung cấp giao diện UI": console quản trị sẵn có của thành phần thượng nguồn
   (ví dụ trang admin của Keycloak, console của Hasura) có bị tính là vi phạm không, nếu không được
   công bố ra ngoài API Gateway?
3. Thành phần trong bảng tham chiếu nhưng **không mang giấy phép OSI** (xem §5) có được dùng như dịch
   vụ độc lập không, hay đội phải thay bằng phương án OSI?
4. Ứng dụng Tầng 2 có được dùng nền tảng low-code nguồn mở có sẵn, hay phải tự viết giao diện?
5. Hạn chót trường gửi danh sách đăng ký đội là ngày nào?
6. Trang đăng nhập SSO do Keycloak phát ra (đã đổi giao diện theo ứng dụng Tầng 2) có bị coi là giao diện
   của Tầng 1 không?

---

## 9. Việc cần làm ngay

- [ ] Cập nhật `olp-2026-brief.md`: mốc "đề công bố tháng 11/2026" → **30/09/2026**.
- [ ] Hỏi BTC các câu còn lại ở §8 (câu 2–6).
- [ ] Viết ADR chốt stack Tầng 1 (dựa trên §5–§6) và cập nhật `DEPENDENCIES.md`.
- [ ] Tổ chức lại `docker-compose.yml` theo profile 3 tầng; cập nhật `README.md`, `ROADMAP.md`.
- [ ] Kiểm tra với trường: đội đã có trong danh sách đăng ký gửi BTC chưa.
