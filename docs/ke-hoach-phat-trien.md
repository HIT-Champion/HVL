# Kế hoạch phát triển DX-OS Open-Core — OLP PMNM 2026

> Lập ngày 01/10/2026 · cập nhật 05/10/2026 sau rà soát · **cập nhật 15/10/2026: đổi bài toán nghiệp vụ
> sang quản lý văn bản, đổi tên sản phẩm thành Mộc** · **cập nhật 18/10/2026: dời lịch Phase 1–4** (xem §7 —
> Nhật ký thay đổi).
> Dựa trên [`olp-2026-de-thi.md`](olp-2026-de-thi.md). Phạm vi sản phẩm: [`dac-ta-san-pham.md`](dac-ta-san-pham.md).
> Mô hình dữ liệu: [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md).
> Khung thời gian: **01/10 → 06/12/2026** (hạn nộp 17:00), chung kết **10/12/2026**.

---

## 0. Tóm tắt

| Phase                                                | Thời gian   | Kết quả chính                                                                                                                                                                                                                                                                | Release    |
| ---------------------------------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| **0** — Chốt kiến trúc                     | 01–20/10    | Quyết định kỹ thuật, mô hình dữ liệu, VPS, 2 spike                                                                                                                                                                                                                     | —         |
| **1** — Lõi Tầng 1 + lên mạng             | 10–25/10    | 4 dịch vụ bắt buộc chạy headless sau API Gateway; bản đầu tiên chạy trên VPS                                                                                                                                                                                         | `v0.1.0` |
| **2** — Ứng dụng [P] Văn phòng điện tử | 26/10–08/11 | Văn bản đến: tiếp nhận → kiểm dịch → vào sổ → chỉ đạo → xử lý; văn bản đi: soạn → trình → duyệt → cấp số → phát hành PDF có mã QR. Sổ kiểm toán chuỗi băm; cổng xác thực văn bản công khai. Chạy end-to-end, có test tự động | `v0.2.0` |
| **3** — 4 nguyên lý + [D]                   | 09–20/11    | Một màn demo cho mỗi nguyên lý (i)–(iv); lưu trữ chống sửa xóa; dashboard điều hành                                                                                                                                                                               | `v0.5.0` |
| **4** — [I] / **đệm**                | 21–25/11    | Đọc văn bản đến, trợ lý hỏi đáp, tác tử gợi ý giao việc — hoặc dùng làm đệm nếu trễ                                                                                                                                                                     | `v0.9.0` |
| **5** — Đóng gói, nộp bài                | 26/11–06/12 | Đóng băng tính năng, tự chấm PoF, gửi thư 05/12                                                                                                                                                                                                                        | `v1.0.0` |

### Ưu tiên (MoSCoW)

- **Must** — Phase 1 + Phase 2 + bản chạy online: toàn bộ yêu cầu bắt buộc R1–R8 của đề, cùng lớp tin
  cậy của lõi — sổ kiểm toán chuỗi băm (F2.12) và cổng xác thực văn bản (F2.13), vì đây là điểm khác biệt
  chính mà README nêu ngay dòng đầu. Trễ thì cắt Should/Could, **không** cắt ở đây.
- **Should** — Phase 3: bằng chứng cho **cả 4** nguyên lý thiết kế, lưu trữ chống sửa xóa, dashboard [D],
  đa thuê ước đầy đủ.
- **Could** — Phase 4 ([I]), WAF, log tập trung, che PII, ký số.
- **Won't** — xem §6.

### Đệm và lịch học

- **21–25/11 là đệm chính thức** (5 ngày; trước 18/10 là một tuần). Nếu đến 20/11 Must/Should chưa xong, cả đội dồn vào hoàn
  thiện; [I] chỉ giữ trợ lý RAG hoặc bỏ hẳn.
- Gửi thư **05/12** — đệm thêm 1 ngày trước hạn 17:00 06/12.
- Mỗi người điền **lịch thi giữa kỳ** vào GitHub Project ngay Phase 0; tuần có người thi thì giảm
  phạm vi tuần đó, không kéo dài phase.

---

## 1. Bài toán sản phẩm giải quyết

> Các tổ chức nhỏ chuyển đổi số bằng cách mua thêm phần mềm, nhưng mỗi phần mềm lại là một ốc đảo
> dữ liệu, hoặc buộc họ lệ thuộc một nhà cung cấp. **Mộc** là lõi nền tảng nguồn mở, tự cài, cung cấp
> sẵn định danh, cổng API, dữ liệu và quy trình cho mọi ứng dụng. Lõi "đóng mộc" lên mọi thứ đi qua nó:
> biết ai đã làm, tệp được quét mã độc trước khi lưu, mọi thay đổi vào sổ kiểm toán nên không sửa lén
> được, và những gì tổ chức phát hành ra ngoài thì người nhận kiểm chứng được. Ứng dụng Văn phòng điện
> tử chạy trên lõi cho thấy một công văn có thể đi trọn vòng đời — tiếp nhận, vào sổ, chỉ đạo, xử lý,
> trả lời, lưu trữ — mà không thất lạc, không quá hạn mà không ai hay, không bị sửa lén; và người nhận
> kiểm tra được văn bản là thật.

| Tầng bài toán                             | Ai gặp                                                                  | Vấn đề                                                                                                                                                                                                                                                                       | Mộc giải bằng                                                                                                                                                        |
| -------------------------------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Nền tảng** (đề giao)             | SME, cơ quan nhà nước đang chuyển đổi số                        | Phần mềm rời rạc → ốc đảo dữ liệu; hệ thống nguyên khối → lệ thuộc một nhà cung cấp; ứng dụng nào cũng phải dựng lại đăng nhập, lưu tệp, phân quyền, quy trình                                                                               | Lõi Tầng 1 dùng chung, không giao diện, nguồn mở, tự cài; lớp tin cậy dùng chung (danh tính, quét mã độc, sổ kiểm toán chuỗi băm, API xác thực) |
| **Nghiệp vụ** (ứng dụng minh họa) | Văn thư, chuyên viên, lãnh đạo của khoa, trường, cơ quan nhỏ | Công văn giấy và bản scan qua email, Zalo; sổ tay hoặc Excel; không biết văn bản đang ở đâu, quá hạn chưa; khó tìm lại; không kiểm được văn bản điện tử nhận được là thật; phần mềm quản lý văn bản phổ biến là sản phẩm đóng | Văn phòng điện tử (quản lý văn bản theo NĐ 30/2020) + cổng xác thực văn bản, chạy trên lõi                                                            |

Vì sao chọn bài toán này, vai trò người dùng, phạm vi chức năng, kịch bản demo:
[`dac-ta-san-pham.md`](dac-ta-san-pham.md).

### 1.1. Đơn vị chạy thử

Bài toán nghiệp vụ cần **người dùng thật**, nếu không giám khảo sẽ hỏi "ai đang gặp vấn đề này?".
Đơn vị nhắm tới: **văn thư văn phòng khoa** (hoặc phòng hành chính của trường), để:

- Lấy **quy trình thật**: sổ văn bản, cách lãnh đạo giao việc, mẫu công văn đang dùng.
- Có **người dùng thật** dùng bản online từ Phase 2; góp ý ghi thành issue (tiêu chí "thu hút cộng đồng").
- Có **số đo trước và sau** để trình bày (§1.2).

**Phương án dự phòng** nếu không tìm được đơn vị: dữ liệu là công văn, thông báo trường đã công bố công
khai; người dùng thử là giảng viên và sinh viên đóng vai văn thư, lãnh đạo; nói rõ điều này khi trình bày.

Dữ liệu nội bộ của đơn vị chạy thử **không** đưa vào repo.

### 1.2. Số đo thành công

| Chỉ số                                                         | Hiện trạng (đo ở Phase 1)                 | Sau khi dùng Mộc (đo ở Phase 4)         |
| ---------------------------------------------------------------- | --------------------------------------------- | ------------------------------------------- |
| Thời gian từ khi văn bản đến tới khi được giao xử lý | Hỏi văn thư, đếm 20 văn bản gần nhất | Tính từ dòng thời gian văn bản        |
| Tỷ lệ văn bản xử lý quá hạn                              | Sổ tay / Excel của văn thư                | Hạn giải quyết so với lúc hoàn thành |
| Thời gian tìm lại một văn bản cũ                          | Bấm giờ 5 lần tìm                         | Bấm giờ 5 lần tìm trên hệ thống      |
| Số bước chuyển tay (in, ký, mang đi, nhắn tin nhắc)      | Quan sát quy trình hiện tại               | So với quy trình trên Mộc               |

Chỉ trình bày **số đo thật**. Chỉ số nào chưa đo được thì nói rõ là chưa đo, không ước đoán.

---

## 2. Kiến trúc mục tiêu

```
       Cán bộ của đơn vị (trình duyệt)               Người ngoài (điện thoại)
                      │ HTTPS                                    │ HTTPS
┌─────────────────────▼────────────────────────┐ ┌───────────────▼───────────┐
│ TẦNG 2 — app-office (Nuxt 4)                 │ │ app-verify                │
│ Văn phòng điện tử [P] · dashboard [D]        │ │ cổng xác thực văn bản     │
│ · trợ lý [I]                                 │ │ công khai, chỉ đọc        │
└─────────────────────┬────────────────────────┘ └───────────────┬───────────┘
                      └───────────────────┬──────────────────────┘
                                          │ một cửa duy nhất
┌─────────────────────────────────────────▼──────────────────────────────────┐
│ TẦNG 1 — DX-OS Core (headless, không UI)                                   │
│                                                                            │
│  Apache APISIX — xác thực JWT tại biên · rate-limit · X-Request-Id         │
│   ├ /realms/* /resources/*  → Keycloak           (chặn /admin)             │
│   ├ /v1/graphql             → Hasura v2 CE       (chặn /v1/metadata,       │
│   │    │                                          /v2/query, /console)     │
│   │    ├ dữ liệu  → PostgreSQL (schema core + office, sổ kiểm toán)        │
│   │    └ Actions  → svc-workflow → Flowable REST (BPMN)                    │
│   ├ /api/files/*            → svc-files → ClamAV → SeaweedFS               │
│   ├ /api/search             → svc-files → Meilisearch (lọc quyền ở server) │
│   ├ /api/verify/*           → svc-files  (ẩn danh, giới hạn tốc độ chặt)   │
│   ├ /api/ai/*               → svc-ai → Ollama · Qdrant          (Phase 4)  │
│   └ /realtime               → Centrifugo (tự kiểm JWT Keycloak qua JWKS)   │
│                                                                            │
│  Chỉ trong mạng nội bộ: Keycloak admin · Hasura metadata · Flowable ·      │
│  SeaweedFS · Meilisearch · ClamAV · OpenBao · Kestra · Marquez · Grafana   │
└────────────────────────────────────────────────────────────────────────────┘
```

**Nguyên tắc headless:**

- **Chỉ APISIX mở cổng ra ngoài**, và chỉ cho những đường dẫn liệt kê ở trên (danh sách trắng).
  Tắt console thôi chưa đủ — `/admin` của Keycloak và `/v1/metadata` của Hasura phải bị chặn ở gateway.
- Giao diện quản trị (Keycloak admin, Kestra, Marquez, Grafana) chỉ truy cập qua mạng nội bộ / SSH tunnel.
- **Không phát URL ký sẵn của SeaweedFS ra ngoài**: tải lên/tải xuống luôn đi qua `svc-files`, nếu
  không tệp sẽ bỏ qua ClamAV và SeaweedFS phải mở cổng ra Internet.
- **Route ẩn danh duy nhất là `/api/verify/*`** của cổng xác thực: chỉ trả các trường công khai của
  văn bản đã phát hành, tra theo mã hoặc theo băm, không liệt kê được; giới hạn tốc độ theo IP.

### 2.1. Một nguồn sự thật cho văn bản

Tránh để Flowable và PostgreSQL cùng giữ trạng thái văn bản rồi lệch nhau:

- Ứng dụng **chỉ nói chuyện với GraphQL**. Thao tác nghiệp vụ là **Hasura Actions**
  (`registerIncoming`, `submitOutgoing`, `completeTask`) do `svc-workflow` xử lý. Người dùng và thuê ước
  lấy từ session variables mà Hasura chuyển sang, **không** tin dữ liệu client gửi.
- **Flowable** là chủ trạng thái quy trình (đang ở bước nào, ai phải làm). Bảng `office.documents` giữ
  dữ liệu nghiệp vụ và một **bản chiếu** trạng thái; chỉ `svc-workflow` được ghi vào cột trạng thái.
- Chuyển trạng thái do Flowable tự gây ra (timer nhắc, leo thang) → Flowable gọi lại `svc-workflow`
  bằng HTTP task.
- `registerIncoming`: trong một giao dịch, cấp số đến và ghi `status = registered` → khởi chạy process
  `van-ban-den` với `businessKey = document.id` → ghi `process_id`. Lỗi giữa chừng → **job đối soát**
  (mỗi 5 phút) tìm văn bản đã vào sổ mà chưa có process, so khớp với Flowable theo `businessKey` và sửa
  lệch. `submitOutgoing` làm theo cùng cách với `van-ban-di`.
- Bảng, quyền, Actions, task và định dạng sự kiện: [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md).

### 2.2. Phần mã đội tự viết ("lớp keo" — nơi chứa tính nguyên gốc)

| Thành phần              | Ngôn ngữ             | Nhiệm vụ                                                                                                                                                                                                                                                                                                 |
| ------------------------- | ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `gateway/`              | YAML                   | Route danh sách trắng + plugin APISIX (standalone), render từ `.env`                                                                                                                                                                                                                                  |
| `services/svc-files`    | Python · FastAPI      | Tải lên → ClamAV → SeaweedFS; tải xuống sau khi kiểm quyền; tìm kiếm (lọc quyền phía server); dựng PDF văn bản đi từ mẫu, chèn số, ký hiệu, mã QR; API xác thực văn bản; mã hóa và giải mã văn bản hạn chế trong bộ nhớ; đọc hồ sơ lưu trữ lạnh bằng DuckDB |
| `services/svc-workflow` | Python · FastAPI      | Xử lý Hasura Actions, cấp số theo sổ, nhận callback từ Flowable, job đối soát, ánh xạ vai trò Keycloak → candidate group Flowable                                                                                                                                                            |
| `services/svc-ai`       | Python                 | Đọc văn bản đến, trợ lý hỏi đáp, tác tử (Phase 4)                                                                                                                                                                                                                                             |
| `db/`                   | SQL                    | Schema `core` + `office`, ràng buộc `CHECK`, trigger sổ kiểm toán, migrations + metadata Hasura                                                                                                                                                                                                 |
| `processes/`            | BPMN XML               | `van-ban-den`, `van-ban-di`; tự deploy lên Flowable khi khởi động                                                                                                                                                                                                                                 |
| `templates/`            | HTML · CSS            | Mẫu văn bản đi đúng thể thức NĐ 30 (công văn, thông báo), dựng thành PDF                                                                                                                                                                                                                    |
| `cli/dxos`              | Python · Typer        | `install`, `doctor`, `backup`, `restore`, `audit verify`, `tenant create`                                                                                                                                                                                                                      |
| `ops/reconciler`        | Shell · systemd timer | GitOps: kéo nhánh `deploy`, áp cấu hình, khởi động lại container unhealthy                                                                                                                                                                                                                      |
| `apps/office`           | TypeScript · Nuxt 4   | Văn phòng điện tử (Tầng 2)                                                                                                                                                                                                                                                                           |
| `apps/verify`           | TypeScript · Nuxt 4   | Cổng xác thực văn bản (Tầng 2, công khai); tính SHA-256 ngay trên trình duyệt                                                                                                                                                                                                                   |

Ngôn ngữ mặc định: **Python** cho dịch vụ (cùng ngôn ngữ với phần AI) và **TypeScript** cho giao diện.
Đổi nếu đội mạnh ngôn ngữ khác — chốt ở QĐ-007 (Phase 0).

### 2.3. Quy tắc làm việc

- **GitHub Project** + một milestone cho mỗi phase; mọi việc là một issue (cũng là bằng chứng cho
  PoF #1 "có dùng repo thật" và PoF #6 "có bug tracker").
- Mỗi tính năng: nhánh → PR → **một người khác review** → merge. **Tài liệu của tính năng nằm trong
  cùng PR** — không dồn viết tài liệu cuối kỳ.
- Cả 3 người commit đều đặn; không dồn commit lớn sát hạn.
- CI cho mỗi PR: kiểm tra header giấy phép, `docker compose config`, `make smoke` (từ Phase 1),
  e2e Playwright (từ Phase 2).
- Quyết định kỹ thuật ghi thành **QĐ-00x** trong `docs/architecture.md`, tiếp nối QĐ-001…003.
- Cấu hình mọi thành phần render từ `.env`; không ghi cứng URL hay mật khẩu (PoF #4).
- Cuối mỗi phase: demo cho giảng viên hướng dẫn, góp ý ghi thành issue.

---

## Phase 0 — Chốt kiến trúc (01–20/10)

Tính đến 05/10 chưa có đầu ra → chỉ giữ 8 việc tối thiểu, hạn **09/10**. Phần trễ được bù bằng việc
dời đa thuê ước đầy đủ khỏi Phase 1. Đến 18/10 vẫn chưa có issue, PR nào trên GitHub → hạn mới **20/10**;
hai spike chạy song song với những ngày đầu Phase 1.

| #   | Việc                                                                                                                                                                                                                                                                                                                                          | Người            |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------ |
| 0.1 | Hỏi BTC các câu còn lại ở `olp-2026-de-thi.md` §8 trên nhóm Telegram (câu 1 về hạn nộp đã rõ)                                                                                                                                                                                                                                | Frontend           |
| 0.2 | Chốt gọn (mỗi QĐ ≤ nửa trang): **QĐ-004** kiến trúc 3 tầng · **QĐ-005** stack lõi + thay thế thành phần non-OSI · **QĐ-006** GitOps = Compose + reconciler · **QĐ-007** ngôn ngữ                                                                                                                 | Cả đội          |
| 0.3 | Mô hình dữ liệu (`core.tenants`, `core.files`, `core.audit_log`, `office.documents`, `office.registers`, `office.assignments`…) + danh sách Hasura Actions + định dạng sự kiện — để 3 người code song song không giẫm nhau. Bản nháp: [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md)                              | Backend + AI       |
| 0.4 | ✅ **Đã có server 16 GB RAM (server của Minh).** Còn: xin tài khoản SSH riêng cho đội; hỏi Minh server có đang chạy dịch vụ khác không (RAM còn trống, cổng 80/443 đã bị dùng chưa) và có giữ chạy liên tục đến hết 10/12 không; ghi lại CPU, đĩa, hệ điều hành; trỏ tên miền; cài Docker | Backend            |
| 0.5 | **Spike 1:** Keycloak → APISIX → Hasura. APISIX kiểm JWT ở biên; Hasura đọc `tenant_id` + vai trò qua `claims_map`. Lưu ý: `iss` trong token là URL công khai, còn Hasura lấy JWKS qua URL nội bộ                                                                                                                  | Backend + Frontend |
| 0.6 | **Spike 2:** `flowable/flowable-rest:8.0.0` + PostgreSQL, deploy 1 BPMN qua REST, đổi mật khẩu mặc định của user `rest-admin`                                                                                                                                                                                                | Backend            |
| 0.7 | Lập GitHub Project + 6 milestone; điền lịch thi; xác nhận với trường đội đã có trong danh sách đăng ký                                                                                                                                                                                                                       | Frontend           |
| 0.8 | Liên hệ **đơn vị chạy thử** (§1.1) — văn thư văn phòng khoa — nhờ giảng viên hướng dẫn giới thiệu; một buổi hỏi quy trình văn thư, và hỏi khoa có tự đánh số văn bản đi không; chốt đơn vị hoặc chuyển sang phương án dự phòng trước 25/10                                           | AI                 |
| 0.9 | Cả đội đồng ý **bài toán nghiệp vụ** theo [`dac-ta-san-pham.md`](dac-ta-san-pham.md) và **tên sản phẩm Mộc** (đã đổi trong tài liệu và cấu hình 15/10; §10 của đặc tả)                                                                                                                               | Cả đội          |

Dời sang Phase 1: viết lại `architecture.md` đầy đủ, đổi profile `docker-compose.yml` thành
`core / app / ops / ai`, cập nhật `README.md`, `ROADMAP.md`, `DEPENDENCIES.md`.

**Hoàn thành khi:** 2 spike chạy được; QĐ-004…007 và mô hình dữ liệu đã merge; bài toán nghiệp vụ đã chốt.

---

## Phase 1 — Lõi Tầng 1 + lên mạng (10–25/10) → `v0.1.0`

**Mục tiêu:** đáp ứng R1–R6 — một PaaS headless mà ứng dụng nào cũng gọi được qua một cổng duy nhất,
và chạy được trên Internet ngay từ bản đầu.

| Mã   | Chức năng                                                                                                                                                                                                                                                                                                                                                                                                                 | Mã nguồn mở                                          | Giấy phép                    |
| ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- | ------------------------------ |
| F1.1  | **SSO + MFA**: realm `dxos` import từ JSON trong git; vai trò `clerk / staff / manager / director / tenant_admin` (văn thư / chuyên viên / lãnh đạo phòng / lãnh đạo đơn vị / quản trị đơn vị — **không** đặt tên `admin`: vai trò có sẵn của Hasura, bỏ qua mọi quyền); TOTP bắt buộc cho `clerk`, `manager`, `director`; `tenant_id` và `department_id` là thuộc tính người dùng, đưa vào JWT bằng mapper (mỗi người thuộc một thuê ước, một phòng) | Keycloak                                                | Apache-2.0                     |
| F1.2  | **API Gateway zero-trust**: route danh sách trắng như §2; kiểm JWT tại biên; rate-limit; CORS; `X-Request-Id`                                                                                                                                                                                                                                                                                                | Apache APISIX (standalone)                              | Apache-2.0                     |
| F1.3  | **Dữ liệu có cấu trúc**: GraphQL tự sinh; quyền theo vai trò + `tenant_id` (cách ly cấp dòng); migrations + metadata tự áp từ git khi khởi động; console tắt                                                                                                                                                                                                                                      | PostgreSQL 16 + Hasura `v2.51.0-ce.cli-migrations-v3` | PostgreSQL / Apache-2.0        |
| F1.4  | **Workflow**: BPMN trong `processes/` tự deploy; Hasura Actions → `svc-workflow`; callback + job đối soát theo §2.1                                                                                                                                                                                                                                                                                         | Flowable REST 8.0                                       | Apache-2.0                     |
| F1.5  | **Dữ liệu phi cấu trúc**: một bucket, khóa đối tượng có tiền tố `tenant/<id>/…`; tải lên/xuống luôn qua `svc-files`                                                                                                                                                                                                                                                                             | SeaweedFS                                               | Apache-2.0                     |
| F1.6  | **Trạm kiểm dịch**: quét mọi tệp trước khi ghi. Giữ volume `/var/lib/clamav` (CDN của ClamAV chặn nếu tải chữ ký quá dày); đặt `ConcurrentDatabaseReload no` để RAM không nhân đôi lúc cập nhật                                                                                                                                                                                       | ClamAV                                                  | GPL-2.0 (dịch vụ độc lập) |
| F1.7  | **Tìm kiếm toàn văn**: `/api/search` qua `svc-files`, gắn bộ lọc thuê ước phía server                                                                                                                                                                                                                                                                                                                  | Meilisearch CE                                          | MIT                            |
| F1.8  | **Cài ra ngoài thư mục nguồn**: `make install PREFIX=/opt/dxos` chép compose + cấu hình đã render; hệ thống chạy được từ PREFIX (PoF #4)                                                                                                                                                                                                                                                           | Mã của đội                                          | —                             |
| F1.9  | **Lên mạng**: deploy lên VPS, HTTPS, Keycloak sau proxy (`KC_HOSTNAME`, `KC_PROXY_HEADERS`); reconciler bản đầu kéo nhánh `deploy`                                                                                                                                                                                                                                                                      | Mã của đội                                          | —                             |
| F1.10 | **Tài liệu API**: schema GraphQL + OpenAPI của `svc-*` xuất tự động                                                                                                                                                                                                                                                                                                                                          | Mã của đội                                          | —                             |

Dời khỏi Phase 1: Centrifugo → Phase 2; Keycloak Organizations, bucket riêng từng thuê ước,
`dxos tenant create` → Phase 3 (Should).

### Hoàn thành khi

- `make up` (profile `core`) dựng toàn bộ lõi trên máy sạch; chỉ cổng gateway mở. Gọi `/admin` và
  `/v1/metadata` qua gateway → bị chặn.
- `make smoke` chạy trong CI: lấy token → truy vấn GraphQL → tải tệp lên (**tệp mẫu EICAR bị chặn**)
  → thêm văn bản đến → `registerIncoming` (có số đến) → `completeTask`. **Người của thuê ước A không
  đọc được dữ liệu thuê ước B.**
- Đo RAM thực tế của profile `core`, ghi vào README.
- Đã có đơn vị chạy thử, bộ quy chế và số đo hiện trạng theo §1.2 — hoặc đã chuyển sang phương án dự phòng.
- **URL công khai chạy `v0.1.0`**; release `.tar.gz` + `SHA256SUMS`.

---

## Phase 2 — Ứng dụng [P] Văn phòng điện tử (26/10–08/11) → `v0.2.0`

**Mục tiêu:** đáp ứng R7 — một ứng dụng có giao diện, dùng **cả 4** dịch vụ bắt buộc trong một kịch bản —
và có lớp tin cậy của lõi: mọi thay đổi vào sổ kiểm toán chuỗi băm, văn bản phát hành kiểm chứng được từ
bên ngoài.

| Mã   | Chức năng                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | Dịch vụ lõi dùng         | Mã nguồn mở thêm                                                                                        |
| ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- | ----------------------------------------------------------------------------------------------------------- |
| F2.1  | Đăng nhập SSO, hồ sơ cá nhân. **Tài khoản dùng thử cho giám khảo** ở vai trò `staff` (không MFA); tài khoản văn thư, lãnh đạo dùng TOTP trên điện thoại của đội                                                                                                                                                                                                                                                                                                                            | Keycloak                     | —                                                                                                          |
| F2.2  | **Tiếp nhận văn bản đến**: tải PDF/ảnh (hiển thị trạng thái quét) → nhập số ký hiệu, ngày ban hành, cơ quan ban hành, loại, trích yếu, độ khẩn, hạn giải quyết. **Poka-yoke 3 lớp** với một JSON Schema dùng chung: kiểm ở form → kiểm lại trong Action handler → ràng buộc `CHECK` trong PostgreSQL. Chặn vào sổ trùng (cùng cơ quan, số ký hiệu, ngày)                                                                                                       | Hasura Actions, svc-files    | Ajv (MIT), `jsonschema` (MIT)                                                                             |
| F2.3  | **Vào sổ và xử lý văn bản đến** (BPMN `van-ban-den`): văn thư vào sổ, hệ thống cấp số đến liên tiếp theo năm → lãnh đạo đơn vị ghi ý kiến chỉ đạo, giao chủ trì / phối hợp, hạn giải quyết → lãnh đạo phòng phân công → chuyên viên xử lý, báo kết quả. Văn bản khẩn lên đầu hộp việc. **Timer tham số hóa** `DXOS_SLA_DURATION` (ISO 8601 — thật `PT24H`, demo `PT1M`) → nhắc → leo thang; quá hạn giải quyết → báo lãnh đạo | Flowable                     | —                                                                                                          |
| F2.4  | **Soạn và phát hành văn bản đi** (BPMN `van-ban-di`): dự thảo từ mẫu đúng thể thức (công văn, thông báo) hoặc tải tệp, giữ các phiên bản → trình lãnh đạo phòng → lãnh đạo đơn vị duyệt hoặc trả lại → văn thư cấp số đi → hệ thống dựng PDF có số, ký hiệu, ngày, **mã QR và SHA-256** để xác thực về sau                                                                                                                                         | Flowable, svc-files          | WeasyPrint (BSD-3-Clause), segno (BSD-3-Clause); phông Liberation Serif (OFL-1.1) cài từ gói hệ thống |
| F2.5  | **Hộp việc của tôi** + thông báo realtime trên kênh riêng của từng người                                                                                                                                                                                                                                                                                                                                                                                                                                       | svc-workflow                 | Centrifugo (Apache-2.0)                                                                                     |
| F2.6  | **Dòng thời gian văn bản**: ai nhận, ai chỉ đạo, ai xử lý, ý kiến, lúc nào                                                                                                                                                                                                                                                                                                                                                                                                                                    | Hasura                       | —                                                                                                          |
| F2.7  | **Tìm kiếm** theo số ký hiệu, trích yếu, cơ quan ban hành và nội dung PDF có lớp chữ                                                                                                                                                                                                                                                                                                                                                                                                                          | svc-files                    | —                                                                                                          |
| F2.8  | **Sổ đăng ký văn bản đến / đi** theo năm; xuất PDF để in (NĐ 30, Điều 16, 22, Phụ lục IV)                                                                                                                                                                                                                                                                                                                                                                                                                   | Hasura, svc-files            | —                                                                                                          |
| F2.9  | **Song ngữ** Việt/Anh: dùng khóa i18n từ ngày đầu; bản dịch tiếng Anh làm nếu kịp                                                                                                                                                                                                                                                                                                                                                                                                                             | —                           | @nuxtjs/i18n (MIT)                                                                                          |
| F2.10 | **Dữ liệu mẫu**: `make seed` tạo người dùng (realm import), phòng ban, sổ rồi **chạy kịch bản qua API** để có ~50 văn bản ở nhiều trạng thái — không chèn thẳng vào CSDL, nếu không Flowable sẽ không có process tương ứng. Văn bản đến lấy từ công văn, thông báo trường đã công bố công khai                                                                                                                                                                  | —                           | —                                                                                                          |
| F2.11 | **Cộng đồng**: mời đơn vị chạy thử dùng bản online; README tiếng Anh; 3–5 issue "good first issue"; bài giới thiệu kèm URL demo trong nhóm Telegram VFOSSA                                                                                                                                                                                                                                                                                                                                                | —                           | —                                                                                                          |
| F2.12 | **⑥ Sổ kiểm toán chuỗi băm** (trước là F3.5): trigger `core.audit()` ghi mọi thay đổi của bảng nghiệp vụ thành chuỗi băm SHA-256 (khóa advisory để ghi tuần tự); `dxos audit verify` tính lại chuỗi và chỉ ra dòng bị sửa; job định kỳ **neo hash đầu chuỗi ra ngoài CSDL** (bucket lạnh + tệp trong repo), để superuser không thể sửa rồi tính lại cả chuỗi; hash của mọi văn bản phát hành nằm trong chuỗi                                           | PostgreSQL (schema `core`) | —                                                                                                          |
| F2.13 | **[D] Cổng xác thực văn bản** (trước là F3.6, `apps/verify`): mã QR trên PDF mở thẳng trang xác thực → thông tin công khai + kết quả khớp; nhập mã tay được; thả tệp PDF → trình duyệt tự tính SHA-256 (không tải tệp lên) → so khớp. `svc-files` trả `/api/verify/*`; APISIX mở route này **ẩn danh**, giới hạn tốc độ theo IP, không liệt kê được. Văn thư dùng cùng chức năng khi tiếp nhận văn bản điện tử đến                          | svc-files, APISIX            | Web Crypto API của trình duyệt                                                                           |

Giao diện: Nuxt 4 / Vue 3 + Tailwind CSS (MIT) — Nuxt 4 thay Nuxt 3 trong gợi ý của BTC vì Nuxt 3 chỉ còn nhận bản vá bảo trì. Tiến trình quy trình hiển thị dạng dòng các bước do đội
tự vẽ. **Không nhúng `bpmn-js`**: giấy phép là MIT có thêm điều khoản bắt buộc giữ watermark, không
thuộc danh sách OSI. Xem PDF trên trình duyệt bằng PDF.js (Apache-2.0).

### Hoàn thành khi

- Kịch bản 5 phút: văn thư nhận công văn đến → vào sổ → lãnh đạo khoa chỉ đạo, giao phòng Đào tạo →
  chuyên viên xử lý, soạn công văn trả lời → trình → duyệt → văn thư cấp số, phát hành PDF có mã QR;
  có thông báo realtime ở từng bước; timer `PT1M` tự nhắc khi để quá hạn.
- Kịch bản trên chạy **tự động bằng Playwright** (Apache-2.0) trong CI.
- Form sai bị chặn ở cả 3 lớp, có test cho từng lớp. Hai người ở hai phòng chỉ thấy văn bản của mình
  và phòng mình (test quyền).
- Quét QR trên một văn bản đã phát hành bằng điện thoại thật → "khớp"; sửa một ký tự trong PDF →
  "không khớp". Gọi `/api/verify` không cần đăng nhập; vượt giới hạn tốc độ thì bị chặn.
- `dxos audit verify` báo chuỗi nguyên vẹn; sửa tay một dòng trong `core.audit_log` → lệnh chỉ ra đúng
  dòng đó; hash đầu chuỗi đã được neo ra ngoài CSDL. Có test cho cả hai trường hợp.
- Demo cho giảng viên hướng dẫn và văn thư của đơn vị chạy thử.

---

## Phase 3 — Bằng chứng 4 nguyên lý + không gian [D] (09–20/11) → `v0.5.0`

**Mục tiêu:** mỗi nguyên lý (i)–(iv) có **một màn demo ≤ 1 phút**, chạy lại được bằng một lệnh, ghi ở
`docs/demo-script.md`; văn bản đã nộp lưu sang kho lạnh vẫn tìm và xác thực được.

| Mã   | Nguyên lý / cụm                           | Chức năng                                                                                                                                                                                                                                                                                                                                                                                 | Mã nguồn mở                               | Ưu tiên                                                                                          |
| ----- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| F3.1  | **(iv)** Kiểm dịch                   | Màn demo: tệp EICAR bị chặn ở cửa ngõ và ghi `file.rejected` vào sổ kiểm toán (ClamAV đã có từ Phase 1)                                                                                                                                                                                                                                                                   | ClamAV                                       | Should                                                                                             |
| F3.2  | **(iv)** Két bí mật                 | **Static seal** để tự mở khóa khi khởi động lại (không thì két bị khóa, phá màn tự phục hồi); dịch vụ lấy mật khẩu CSDL qua AppRole; khóa Transit cho F3.7. Khi trình bày nói rõ: khóa mở và credential AppRole vẫn nằm trên đĩa                                                                                                                 | OpenBao (MPL-2.0)                            | Should                                                                                             |
| F3.3  | **(iv)** GitOps + tự phục hồi       | Reconciler chạy bằng **systemd timer trên host** (không gắn socket Docker vào container): mỗi 60 giây kéo nhánh `deploy` → `docker compose up -d`; khởi động lại container unhealthy. Demo: `docker rm -f` một dịch vụ → tự dựng lại. Chuẩn bị bảng đối chiếu 4 nguyên tắc OpenGitOps để trả lời "GitOps mà không có Argo CD?"             | Docker Compose + mã của đội              | Should                                                                                             |
| F3.4  | **⑥** Sao lưu                        | `dxos backup` / `dxos restore`: `pg_dump` + restic cho CSDL và dữ liệu SeaweedFS                                                                                                                                                                                                                                                                                                   | restic (BSD-2-Clause)                        | Should                                                                                             |
| F3.5  | **⑥** Lịch sử thay đổi            | Tab "Lịch sử" trên trang văn bản hiển thị diff từng lần sửa, đọc từ sổ kiểm toán. Bản thân sổ kiểm toán đã lên Must (F2.12)                                                                                                                                                                                                                                         | —                                           | Should                                                                                             |
| F3.6  | —                                           | *Đã lên Must: cổng xác thực văn bản là F2.13*                                                                                                                                                                                                                                                                                                                                    | —                                           | —                                                                                                 |
| F3.7  | **[P]** giải mã tài liệu trên RAM | **Văn bản hạn chế truy cập**: tệp lưu mã hóa (khóa dữ liệu bọc bằng OpenBao Transit), chỉ giải mã trong bộ nhớ của `svc-files` cho người trong danh sách; xem có watermark; không đưa nội dung vào chỉ mục. **Không dùng cho bí mật nhà nước**                                                                                          | OpenBao                                      | Should                                                                                             |
| F3.8  | **(i)** Nóng → lạnh                 | **Lập hồ sơ và nộp lưu**: hồ sơ công việc đóng quá `DXOS_ARCHIVE_AFTER_DAYS` → gói Parquet + PDF + manifest có băm trên bucket `cold` → gỡ chi tiết khỏi OLTP, giữ bản ghi rút gọn. Văn bản đã lưu **vẫn tìm thấy và xác thực được**; xem trong phòng đọc ảo (chỉ xem, watermark) qua `svc-files` đọc Parquet bằng DuckDB | Kestra · DuckDB                             | Should                                                                                             |
| F3.9  | **(iii)** Lineage + chất lượng      | Job phát sự kiện OpenLineage cho từng bước, quy ước tên dataset thống nhất từ đầu; kiểm tra chất lượng (số dòng khớp, không null) → lỗi thì cảnh báo                                                                                                                                                                                                             | Marquez (Apache-2.0)                         | Should                                                                                             |
| F3.10 | **(ii)** IT/OT (bản rút gọn)        | Cảm biến nhiệt độ phòng máy chủ (giả lập) → context broker NGSI-LD → subscription → `svc-workflow` dựng nháp **"báo cáo sự cố"** từ mẫu → vào luồng văn bản đi để trình lãnh đạo                                                                                                                                                                   | Scorpio `all-in-one-runner` (BSD-3-Clause) | Should                                                                                             |
| F3.11 | **[D]** Dashboard điều hành         | Trang trong app-office: văn bản đến theo trạng thái, quá hạn theo phòng, thời gian xử lý trung bình, văn bản khẩn, văn bản đi theo tháng. Lấy số liệu qua view + aggregate của Hasura → **tự đúng SSO và quyền thuê ước**                                                                                                                            | Apache ECharts (Apache-2.0)                  | Should                                                                                             |
| F3.12 | Đa thuê ước đầy đủ                   | Keycloak Organizations, bucket riêng từng thuê ước, `tenantId` trong Flowable, `dxos tenant create`; **văn bản đi gửi đơn vị khác trong hệ thống tự thành văn bản đến của đơn vị nhận**                                                                                                                                                                 | Keycloak                                     | Should — cắt đầu tiên nếu trễ (cột `tenant_id` từ Phase 1 đã đủ để demo cách ly) |
| F3.13 | **⑥** Giám sát                      | Sức khỏe dịch vụ (chỉ trong mạng nội bộ)                                                                                                                                                                                                                                                                                                                                            | Prometheus · Grafana (`grafana/grafana`)  | Should                                                                                             |
| F3.14 | Log tập trung                               | Tra log xuyên dịch vụ theo `X-Request-Id`                                                                                                                                                                                                                                                                                                                                              | Vector · Parseable                          | Could                                                                                              |
| F3.15 | WAF                                          | Chặn SQLi/XSS theo OWASP CRS tại gateway — chỉ spike nếu dư thời gian                                                                                                                                                                                                                                                                                                                | Coraza (proxy-wasm)                          | Could                                                                                              |

Thứ tự cắt khi trễ: F3.15 → F3.14 → F3.12 → F3.13 → F3.5 → F3.7. **Không cắt** 4 màn nguyên lý. Cổng xác
thực và sổ kiểm toán — màn demo chính — đã lên Must ở Phase 2.

### Hoàn thành khi

- `docs/demo-script.md` có đủ 4 màn (i)–(iv), mỗi màn chạy bằng một lệnh.
- Văn bản đã nộp lưu sang kho lạnh: quét QR → vẫn "khớp".
- Diễn tập: xóa volume PostgreSQL → `dxos restore` → hệ thống trở lại đúng dữ liệu.

---

## Phase 4 — [I] Trí tuệ / đệm (21–25/11) → `v0.9.0`

**Quy tắc:** nếu đến 20/11 Must/Should chưa xong, 5 ngày này là đệm; [I] chỉ giữ F4.1 hoặc bỏ.

Người làm AI **bắt đầu 2 spike từ Phase 2** (tuần 26/10), lúc khối lượng phần dữ liệu còn nhẹ, để Phase 4 chỉ còn tích hợp:

- **Spike OCR:** Tesseract (`vie`) so với PaddleOCR và VietOCR trên ~20 công văn scan và ảnh chụp
  thật — ảnh chụp tiếng Việt thường sai dấu, chọn theo kết quả đo. Đo cả tỷ lệ đọc đúng số ký hiệu
  và ngày ban hành bằng quy tắc, không cần mô hình ngôn ngữ.
- **Spike mô hình:** Qwen3 4B so với 8B — chất lượng tiếng Việt, tốc độ trên CPU của VPS, và giấy phép
  ghi trên model card **của từng kích cỡ**.

| Mã              | Chức năng                                                                                                                                                                                                                                                                                                                                                                                            | Mã nguồn mở                                                          | Giấy phép                                     |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------- | ----------------------------------------------- |
| F4.1             | **Đọc văn bản đến**: PDF có lớp chữ → đọc thẳng; ảnh / bản scan → OCR. Quy tắc cho số ký hiệu, ngày ban hành, cơ quan ban hành; mô hình ngôn ngữ chỉ tóm trích yếu. Điền sẵn form tiếp nhận, văn thư xác nhận. Tác tử dùng tài khoản dịch vụ riêng, hành động vào sổ kiểm toán                                                           | pypdf · Tesseract / PaddleOCR / VietOCR (theo spike) · Ollama + Qwen3 | BSD-3-Clause · Apache-2.0 · MIT · Apache-2.0 |
| F4.2             | **Trợ lý hỏi đáp trên kho văn bản**: trả lời **kèm số ký hiệu và trang**; lọc thuê ước và quyền ở **bước truy xuất** (payload filter của Qdrant), không dựa vào prompt; văn bản hạn chế không vào chỉ mục                                                                                                                                       | Ollama + Qwen3 · bge-m3 · Qdrant · LlamaIndex                        | MIT · Apache-2.0 · MIT · Apache-2.0 · MIT   |
| F4.3             | **Tác tử gợi ý giao việc**: là một **service task bất đồng bộ trong BPMN**, chạy ngay trước bước lãnh đạo chỉ đạo; đề xuất đơn vị chủ trì và hạn dựa trên văn bản tương tự trước đây. Người quyết định (Human-in-the-loop); hành động của tác tử vào sổ kiểm toán; quá thời gian thì bỏ qua gợi ý, không chặn quy trình | LlamaIndex (dùng chung với F4.2)                                      | MIT                                             |
| F4.4 *(Could)* | **Che PII**: ẩn CCCD / số điện thoại trong log và trong ngữ cảnh gửi cho LLM (tự viết bộ nhận dạng cho định dạng Việt Nam)                                                                                                                                                                                                                                                     | Presidio                                                                | MIT                                             |
| F4.5 *(Could)* | **Ký số** PDF văn bản đi (PAdES) bằng PKI nội bộ do OpenBao cấp — chỉ minh họa, không có giá trị pháp lý như chữ ký số công cộng                                                                                                                                                                                                                                         | pyHanko                                                                 | MIT                                             |
| F4.6             | **Thu góp ý và đo kết quả**: đơn vị chạy thử + ≥ 5 người ngoài đội dùng bản online và để lại issue; đo các chỉ số "sau" theo §1.2                                                                                                                                                                                                                                    | —                                                                      | —                                              |

Chỉ dùng **một** framework AI (LlamaIndex) cho cả RAG lẫn tác tử. Không dùng Llama hoặc Gemma vì trọng
số không mang giấy phép OSI.

### Hoàn thành khi

- Trên 20 công văn mẫu, số ký hiệu và ngày ban hành được điền đúng ở phần lớn văn bản; ghi tỷ lệ đo được
  vào README (không ước đoán).
- 10 câu hỏi kiểm thử đều có trích dẫn đúng văn bản.
- Gợi ý của tác tử đã có sẵn khi lãnh đạo mở việc chỉ đạo.
- Bản online chạy ổn định liên tục từ 25/11 đến ngày nộp.

---

## Phase 5 — Đóng gói và nộp bài (26/11–06/12) → `v1.0.0`

| Ngày           | Việc                                                                                                                                                                                                                  |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 26/11           | **Đóng băng tính năng** — từ đây chỉ sửa lỗi                                                                                                                                                         |
| 26–30/11       | Tự chấm theo `pof-checklist.md` (Backend chủ trì). Nhờ **một người ngoài đội** cài từ README trên máy sạch, cài ra PREFIX ngoài thư mục nguồn và chạy được (PoF #4)                  |
| 26–30/11       | Rà tài liệu (đã viết dần theo PR): kiến trúc, API, vận hành (sao lưu/phục hồi/nâng cấp), `demo-script.md`, `ROADMAP.md` sau cuộc thi; đối chiếu `DEPENDENCIES.md` với phiên bản đã ghim |
| 03/12           | Release `v1.0.0`: `.tar.gz` + `SHA256SUMS` + CHANGELOG. Release notes ghi rõ **tệp chính thức là `.tar.gz`** (GitHub luôn tự gắn "Source code (zip)" và không gỡ được)                     |
| **05/12** | **Gửi thư nộp bài**                                                                                                                                                                                          |
| Từ 17:00 06/12 | **Không push lên nhánh chính** — kho mã được chấm 7–9/12. Slide và video làm ở nhánh hoặc repo khác                                                                                             |
| 07–09/12       | Slide 15 phút theo 4 phần BTC yêu cầu, mở đầu bằng bài toán (§1) và kết bằng số đo trước/sau; quay video demo dự phòng; tập ít nhất 3 lần; kiểm tra VPS trước giờ thi                      |
| 10/12           | Chung kết                                                                                                                                                                                                             |

---

## 3. Phân công (đội 3 người: Backend · AI · Frontend)

| Mảng                                                          | Phase 0                                                   | Phase 1                                                                                                                                                               | Phase 2                                                                                                                                                                                                                                             | Phase 3                                                                                                                                         | Phase 4                                              | Phase 5                       |
| -------------------------------------------------------------- | --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- | ----------------------------- |
| **Backend** — @Vanvuong2005827 (chủ PoF & phát hành) | Mô hình dữ liệu + Actions, Spike 1 + 2, kiểm tra VPS | APISIX, Flowable, `svc-workflow` + Actions, `make install`, `make smoke`, deploy VPS                                                                            | Centrifugo, cấp số theo sổ, timer nhắc + callback, seed qua API, CI e2e, route ẩn danh `/api/verify/*` + giới hạn tốc độ                                                                                                                | OpenBao (+ khóa Transit), reconciler, sao lưu, giám sát, nhận sự kiện IT/OT, đa thuê ước + liên thông giữa đơn vị *(Should)* | Ổn định online, thu góp ý, ký số *(Could)*  | Tự chấm PoF, release        |
| **AI** — @HoangTechCS-AIE (kiêm dữ liệu)             | Mô hình dữ liệu, liên hệ đơn vị chạy thử       | Schema `core` + `office`, Hasura (migrations, quyền), SeaweedFS, `svc-files` + ClamAV, Meilisearch + `/api/search`                                           | Poka-yoke lớp CSDL + JSON Schema chung, **dựng PDF văn bản đi từ mẫu + mã QR**, **sổ kiểm toán chuỗi băm + neo hash**, **API xác thực**, sổ đăng ký, view cho dashboard, **spike OCR + chọn mô hình** | Mã hóa văn bản hạn chế, nộp lưu nóng→lạnh, Marquez                                                                                   | Đọc văn bản đến, trợ lý hỏi đáp, tác tử | Rà tài liệu                |
| **Frontend** — @nguyenlehoainam                         | Hỏi BTC, GitHub Project, Spike 1 (phần Keycloak)        | Keycloak realm (vai trò, mapper `tenant_id` + `department_id`, TOTP, giao diện đăng nhập), khung Nuxt + đăng nhập OIDC, vẽ quy trình BPMN cùng Backend | **app-office**: tiếp nhận văn bản đến, chỉ đạo / giao việc, soạn văn bản đi, hộp việc, chi tiết văn bản, sổ, tìm kiếm, i18n, Playwright; **app-verify** (cổng xác thực); README tiếng Anh                     | Dashboard [D] (ECharts), tab Lịch sử, phòng đọc ảo, giao diện IT/OT + cảm biến giả lập                                               | Giao diện trợ lý + đọc văn bản đến          | Slide, kịch bản demo, video |

`svc-files` (dữ liệu phi cấu trúc, dựng PDF, xác thực, tìm kiếm) do AI làm vì gắn với dữ liệu và việc đọc
văn bản về sau; Backend review.
Mỗi mảng có một người khác thường xuyên review PR, để có người thay khi ai đó vắng dài ngày.

---

## 4. Tài nguyên cần có

Dự án gần như không tốn tiền: mọi phần mềm đều nguồn mở, mô hình AI chạy trên server của đội. Thứ cần
nhiều nhất là thời gian của 3 người, một server đủ RAM, dữ liệu và người dùng thật. Cột "Tình trạng" ghi
theo ngày 15/10/2026 — cập nhật khi có thay đổi.

### 4.1. Con người và thời gian

| Nguồn lực                           | Cần gì                                                                                                             | Tình trạng                                             |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| Đội 3 người                       | Backend, AI (kiêm dữ liệu), Frontend; ~7 tuần đến 06/12, trong đó có đệm 21–25/11                  | Có; mỗi người điền lịch thi giữa kỳ (việc 0.7) |
| Giảng viên hướng dẫn             | Giới thiệu đơn vị chạy thử; xem demo cuối mỗi phase; đứng tên trong thư nộp bài                       | Chưa điền                                             |
| Văn thư khoa (đơn vị chạy thử) | Một buổi hỏi quy trình; số đo "trước" theo §1.2; dùng bản online từ Phase 2                              | Đang liên hệ; có phương án dự phòng (§1.1)     |
| Người ngoài đội                  | ≥ 5 người dùng thử và để lại issue (F4.6); 1 người tự cài từ README trên máy sạch (Phase 5, PoF #4) | Chưa có                                                |

### 4.2. Hạ tầng

| Nguồn lực                    | Cần gì                                                                                                                                                                                                | Tình trạng                                                                                                        |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Server chạy bản online       | RAM theo bảng dưới; đĩa ước **≥ 50 GB** cho image Docker, mô hình AI, chữ ký ClamAV và dữ liệu (ước tính, đo lại ở Phase 1); cổng 80/443; tài khoản SSH riêng của đội | Server dùng chung với Minh, 16 GB RAM; CPU, đĩa, hệ điều hành, cổng, tài khoản SSH chưa rõ (việc 0.4) |
| Tên miền + HTTPS             | Tên miền hoặc tên miền con; chứng chỉ Let's Encrypt                                                                                                                                              | Chưa có                                                                                                           |
| Máy phát triển              | Docker Engine + Docker Compose v2; ≥ 8 GB RAM để chạy `core`, 16 GB để chạy thoải mái                                                                                                        | Mỗi người tự kiểm bằng `make check`                                                                         |
| Máy dự phòng cho chung kết | Một laptop chạy được bản demo khi mạng hoặc server hỏng (§5)                                                                                                                                  | Có                                                                                                                 |
| Điện thoại                  | Ứng dụng TOTP nguồn mở (FreeOTP) cho tài khoản văn thư, lãnh đạo; camera quét QR khi demo và chụp công văn cho spike OCR                                                                | Có                                                                                                                 |

**RAM theo profile** (ước lượng — đo lại ở Phase 1):

| Profile   | Thành phần                                                                                            | RAM ước tính                                |
| --------- | ------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| `core`  | PostgreSQL, Keycloak, APISIX, Hasura, SeaweedFS, Meilisearch, Flowable, ClamAV, svc-files, svc-workflow | ~4–6 GB                                       |
| + `app` | app-office, app-verify, Centrifugo                                                                      | thêm ~0,5 GB → **mục tiêu SME 8 GB** |
| + `ops` | OpenBao, Kestra, Marquez, Scorpio, Prometheus, Grafana                                                  | thêm ~3–4 GB                                 |
| + `ai`  | Ollama + Qwen3 4B/8B (4-bit), bge-m3, Qdrant, OCR, svc-ai                                               | thêm ~5–8 GB                                 |

**VPS hiện có: 16 GB RAM** — thừa cho `core` + `app` + `ops` (~8–10 GB). Bật thêm `ai` thì tổng
ước 13–18 GB, **sát hoặc vượt 16 GB**. Cách xử lý, theo thứ tự ưu tiên: (1) đo RAM thật thay cho ước
lượng; (2) chọn Qwen3 4B nếu 8B không vừa; (3) lúc demo [I] tạm tắt Kestra và Marquez (job ngầm, không
ảnh hưởng màn demo khác). Không cần nâng cấp VPS trừ khi số đo thật buộc phải nâng.

### 4.3. Tài khoản và dịch vụ — đều miễn phí

- **GitHub**: repo công khai, Actions (repo công khai không giới hạn phút chạy), Discussions, Projects,
  Releases. Mỗi thành viên bật xác thực 2 lớp.
- **Docker Hub**: CI đăng nhập để không bị giới hạn lượt tải image ẩn danh (§5).
- **Nhóm Telegram của BTC**: hỏi đáp.
- Không dùng API trả phí: mô hình ngôn ngữ chạy bằng Ollama trên server.
- Phần mềm: tất cả mang giấy phép OSI, ghim phiên bản trong [`DEPENDENCIES.md`](../DEPENDENCIES.md);
  phông Liberation Serif thay Times New Roman.

### 4.4. Dữ liệu

| Dữ liệu                                                      | Dùng cho                  | Tình trạng                                                          |
| -------------------------------------------------------------- | -------------------------- | --------------------------------------------------------------------- |
| ~50 công văn, thông báo trường đã công bố công khai | `make seed` (F2.10)      | Chưa thu thập                                                       |
| ~20 công văn scan và ảnh chụp                             | Spike OCR (Phase 2), F4.1  | Chưa có                                                             |
| Mẫu công văn, thông báo đúng thể thức                 | Mẫu văn bản đi (F2.4)  | Có theo Phụ lục NĐ 30; chờ mẫu đơn vị chạy thử đang dùng |
| Quy trình thật và số đo "trước"                         | §1.2                      | Chờ đơn vị chạy thử — **không đưa vào repo**         |
| 10 câu hỏi kiểm thử kèm đáp án                         | Trợ lý hỏi đáp (F4.2) | Làm ở Phase 4                                                       |

### 4.5. Kiến thức cần học

| Mảng     | Cần nắm                                                                                            |
| --------- | ---------------------------------------------------------------------------------------------------- |
| Backend   | APISIX, Flowable BPMN, Centrifugo, vận hành Docker trên server, systemd timer cho reconciler      |
| AI        | Quyền theo dòng của Hasura, trigger PostgreSQL cho chuỗi băm, WeasyPrint, OCR tiếng Việt, RAG |
| Frontend  | Keycloak và OIDC, Nuxt 4, Playwright, ECharts                                                       |
| Cả đội | Thể thức và quy trình văn thư theo NĐ 30 — phần trích ở `dac-ta-san-pham.md` §2.1      |

### 4.6. Chi phí

Ước **0 đồng** nếu dùng server của Minh và tên miền con miễn phí. Nếu mua tên miền riêng thì thêm phí
tên miền theo năm. Không nâng cấp server trừ khi số đo RAM thật buộc phải nâng (§4.2).

### 4.7. Phải có trước 25/10 (`v0.1.0` chạy trên Internet)

1. Thông số và quyền truy cập server: CPU, đĩa, hệ điều hành, tài khoản SSH riêng, cổng 80/443 (việc 0.4).
2. Tên miền.
3. Đơn vị chạy thử và tên giảng viên hướng dẫn (việc 0.8).
4. Máy của từng thành viên: Docker Compose v2, cấu hình Git theo [`git_flow.md`](git_flow.md) §4.1,
   `make check` chạy sạch.

---

## 5. Rủi ro và cách chặn

| Rủi ro                                                                                                         | Cách chặn                                                                                                                                                                                                                                                                            |
| --------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Trễ tiến độ                                                                                                 | MoSCoW; đệm 21–25/11; thứ tự cắt của Phase 3; mỗi phase kết thúc bằng một release dùng được                                                                                                                                                                      |
| Phase 2 nặng thêm vì F2.12, F2.13 lên Must                                                                  | Bảng `core.audit_log` và trigger viết luôn cùng schema ở F1.3 nếu Phase 1 còn giờ; `app-verify` chỉ là một trang, không đăng nhập. Phase 2 trễ thì để sau phần bản dịch tiếng Anh của F2.9 (vốn chỉ làm nếu kịp), **không** cắt F2.12, F2.13 |
| Thi giữa kỳ                                                                                                   | Lịch thi điền từ Phase 0; giảm phạm vi tuần có thi                                                                                                                                                                                                                             |
| Thành viên vắng dài ngày                                                                                   | Mỗi mảng có người thứ hai review PR thường xuyên                                                                                                                                                                                                                              |
| Không tìm được đơn vị chạy thử                                                                        | Phương án dự phòng ở §1.1: công văn đã công bố của trường, người dùng thử là giảng viên và sinh viên đóng vai                                                                                                                                               |
| Nghiệp vụ văn thư mới với cả đội                                                                       | Chỉ làm phần quy định ở `dac-ta-san-pham.md` §2.1; một buổi hỏi văn thư khoa ngay Phase 1                                                                                                                                                                                |
| Giám khảo hỏi "khác gì VNPT iOffice?" hoặc hiểu nhầm ký số nội bộ có giá trị pháp lý           | Trả lời theo `dac-ta-san-pham.md` §9; ký số chỉ là Could và chỉ minh họa                                                                                                                                                                                                   |
| BTC trả lời khác giả định                                                                                 | Hỏi ngay Phase 0; ví dụ nếu cấm cả console nội bộ thì tắt hẳn                                                                                                                                                                                                               |
| Server dùng chung với Minh: thiếu RAM, trùng cổng 80/443, bị khởi động lại hoặc tắt ngoài ý muốn | Hỏi rõ ở việc 0.4; nếu trùng cổng thì đặt APISIX sau reverse proxy sẵn có của Minh; thống nhất lịch "không đụng server" quanh 05–10/12; luôn có bản chạy trên laptop dự phòng                                                                               |
| VPS 16 GB không đủ khi bật cả 4 profile                                                                    | Đo RAM thật ở Phase 1 và Phase 3; lúc demo [I] tắt Kestra/Marquez, chọn mô hình 4B nếu 8B không vừa                                                                                                                                                                        |
| Lỗi chỉ lộ khi chạy thật (HTTPS, proxy, redirect URI, websocket)                                           | Lên mạng từ Phase 1; mỗi release tự deploy qua reconciler                                                                                                                                                                                                                         |
| Push nhầm lên máy demo                                                                                       | Reconciler chỉ kéo nhánh `deploy`; chỉ merge vào `deploy` khi đã qua CI                                                                                                                                                                                                     |
| Docker Hub giới hạn pull ẩn danh; CDN ClamAV chặn tải dày                                                 | CI đăng nhập Docker Hub và cache image; giữ volume chữ ký ClamAV                                                                                                                                                                                                                |
| Mạng hỏng lúc chung kết                                                                                     | Video demo dự phòng; một bản chạy được trên laptop                                                                                                                                                                                                                            |
| LLM chậm hoặc kém tiếng Việt                                                                               | Spike từ Phase 2; [I] là Could; số ký hiệu và ngày đọc bằng quy tắc, không cần mô hình; tác tử bất đồng bộ có timeout                                                                                                                                            |
| Mất điểm PoF vì dịch vụ tự viết                                                                         | Mỗi `svc-*` có Dockerfile, header SPDX, cấu hình qua `.env`, không bundle thư viện; `make install` ra ngoài thư mục nguồn                                                                                                                                             |
| Thành phần đổi giấy phép giữa chừng                                                                     | Ghim phiên bản image; rà lại `DEPENDENCIES.md` ở Phase 5                                                                                                                                                                                                                        |

---

## 6. Không làm — và lý do

| Hạng mục                                                          | Lý do                                                                                                                                                                                     |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Tầng 3 (ứng dụng ngành)                                         | Đề không bắt buộc                                                                                                                                                                     |
| Kubernetes / Argo CD                                                | QĐ-006: Compose + reconciler đủ cho GitOps ở quy mô SME, không thêm 1–2 GB RAM và độ phức tạp                                                                                 |
| Ứng dụng di động Flutter                                        | Không đủ thời gian                                                                                                                                                                     |
| Kafka, Lakehouse Iceberg đầy đủ                                 | Nặng; Parquet trên object storage + DuckDB đủ cho nguyên lý (i)                                                                                                                      |
| Metabase                                                            | Bản mã nguồn mở không đăng nhập được bằng Keycloak (OIDC là tính năng trả phí) và đọc thẳng CSDL, bỏ qua quyền thuê ước → thay bằng dashboard trong app-office |
| `bpmn-js`                                                         | Giấy phép không thuộc danh sách OSI (điều khoản watermark)                                                                                                                         |
| URL ký sẵn của SeaweedFS ra ngoài                               | Bỏ qua ClamAV và buộc SeaweedFS mở cổng ra Internet                                                                                                                                   |
| n8n, HashiCorp Vault, Redpanda, MongoDB, immudb                     | Không mang giấy phép OSI — xem `olp-2026-de-thi.md` §5                                                                                                                              |
| Văn bản Mật, Tối mật, Tuyệt mật                              | Luật Bảo vệ bí mật nhà nước 2018 (Điều 5) cấm soạn thảo, lưu giữ trên máy kết nối Internet                                                                              |
| Liên thông Trục văn bản quốc gia (edXML, QCVN 102:2016/BTTTT) | Cần mã định danh và kết nối do cơ quan nhà nước cấp — để ở định hướng phát triển                                                                                     |
| Chữ ký số công cộng, USB token, HSM                            | Cần tổ chức chứng thực được cấp phép; PKI nội bộ chỉ minh họa (F4.5)                                                                                                         |

---

## 7. Nhật ký thay đổi kế hoạch

**05/10/2026** — sau rà soát toàn bộ kế hoạch:

- **Lịch:** Phase 0 rút còn 8 việc, kéo đến 09/10; thêm tuần đệm 19–25/11; lên mạng từ Phase 1 thay
  vì Phase 4; thêm quy tắc lịch thi.
- **Gateway:** route danh sách trắng (chặn `/admin` của Keycloak, `/v1/metadata` của Hasura); bỏ URL
  ký sẵn ra ngoài; tìm kiếm đi qua `svc-files` vì Meilisearch không nhận JWT Keycloak.
- **Nguồn sự thật:** Hasura Actions + `svc-workflow` là bên ghi trạng thái duy nhất; callback từ
  Flowable; job đối soát.
- **Phase 1:** bỏ đa thuê ước đầy đủ (chỉ giữ cột `tenant_id`); ClamAV chuyển từ Phase 3 về; thêm
  `make install` và deploy VPS; Centrifugo sang Phase 2; dùng image Hasura `-ce.cli-migrations-v3`.
- **Phase 2:** JSON Forms → một JSON Schema dùng chung (Ajv + `jsonschema`); SLA tham số hóa; tài
  khoản demo cho giám khảo; seed qua API; e2e Playwright; bắt đầu hoạt động cộng đồng.
- **Phase 3:** thêm bản rút gọn IT/OT (ii) cho khớp mục tiêu "đủ 4 nguyên lý"; OpenBao static seal;
  reconciler chạy trên host, kéo nhánh `deploy`; `pg_dump` + restic thay pgBackRest; bỏ docker-autoheal;
  neo hash sổ kiểm toán ra ngoài CSDL; đường đọc hồ sơ lưu trữ lạnh; Metabase → ECharts; Vector,
  Parseable, Coraza hạ xuống Could.
- **Phase 4:** một framework AI duy nhất; 2 spike từ 05/11; tác tử là service task bất đồng bộ trong BPMN.
- **Phase 5:** `SHA256SUMS` và ghi chú về tệp zip của GitHub; không push lên nhánh chính sau hạn nộp.
- **Phân công:** chuyển `svc-files` sang A, dashboard và Marquez sang B; A làm chủ PoF và phát hành.
- **Tài nguyên:** cộng thêm bge-m3, OCR, Scorpio vào ước lượng; kế hoạch nâng VPS theo phase.
- **Bài toán:** thêm §1 (câu phát biểu bài toán, đơn vị chạy thử, số đo thành công) và việc 0.8;
  đánh số lại các mục phía sau. Câu phát biểu cũng được đưa vào `README.md`.

**09/10/2026**

- Hạn nộp đã rõ: **17:00 06/12/2026** (đề in nhầm năm 2025).
- Đã có VPS **16 GB RAM** → việc 0.4 chỉ còn ghi cấu hình, trỏ tên miền, cài Docker; bỏ kế hoạch nâng VPS
  theo phase, thay bằng đo RAM thật và tắt bớt job ngầm khi demo [I].
- Phân công theo 3 mảng thật của đội: **Backend · AI · Frontend** thay cho A/B/C. AI kiêm phần dữ liệu
  (schema, Hasura, `svc-files`, sổ kiểm toán, nóng→lạnh, lineage); Frontend nhận cấu hình Keycloak và
  vẽ BPMN; spike AI dời sớm lên Phase 2.
- Điền thành viên: Backend @Vanvuong2005827 · AI @HoangTechCS-AIE · Frontend @nguyenlehoainam.

**15/10/2026** — đổi bài toán nghiệp vụ, lý do đầy đủ ở [`dac-ta-san-pham.md`](dac-ta-san-pham.md) §1:

- **Bài toán:** từ "luồng phê duyệt đề xuất mua sắm / tạm ứng / nghỉ phép" sang **quản lý văn bản đến / đi
  theo NĐ 30/2020** + **cổng xác thực văn bản** công khai. Lý do: đề định nghĩa Tầng 2 là "cổng dịch vụ
  nghiệp vụ dùng chung" và xếp ứng dụng chuyên ngành vào Tầng 3; các kho mã công khai của đội khác đã có
  cổng yêu cầu nội bộ, mua sắm, vận hành phòng máy; chưa đội nào làm quản lý văn bản và xác thực văn bản.
- **Lõi Tầng 1 và Phase 1 giữ nguyên**, trừ: vai trò thêm `clerk`, JWT thêm `department_id`, `make smoke`
  dùng `registerIncoming`.
- **Phase 2:** F2.2–F2.4, F2.8 viết lại cho văn bản đến / đi và sổ đăng ký; PDF phát hành có mã QR + SHA-256.
- **Phase 3:** đánh mã F3.1–F3.15; thêm cổng xác thực (F3.6), văn bản hạn chế giải mã trên RAM (F3.7);
  nóng → lạnh thành lập hồ sơ, nộp lưu (F3.8); IT/OT tạo nháp báo cáo sự cố (F3.10).
- **Phase 4:** F4.1 thành đọc văn bản đến (giữ đầu tiên nếu dùng tuần đệm); trợ lý hỏi đáp trên kho văn
  bản; tác tử gợi ý giao việc; ký số chỉ minh họa.
- **Không làm:** thêm văn bản mật, liên thông Trục văn bản quốc gia, chữ ký số công cộng.
- Thêm việc 0.9 (chốt bài toán, tên sản phẩm) và bản nháp mô hình dữ liệu
  [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md).
- **Tên sản phẩm:** DX-Lab → **Mộc** (theo chữ "đóng mộc"). "DX-Lab" là tên Trạm thực hành số trong chủ
  đề cuộc thi và trùng ứng dụng của đội HaUI. Tên kỹ thuật đổi theo: Compose project và CSDL mặc định
  `moc`, biến môi trường `MOC_*`, gói phát hành `moc-<phiên bản>.tar.gz`. Repo giữ tên `HVL`.
- **Phát biểu sản phẩm:** kể lõi trước, ứng dụng sau; điểm khác biệt là lớp tin cậy của lõi (danh tính,
  quét mã độc, sổ kiểm toán chuỗi băm, API xác thực).
- **Sổ kiểm toán chuỗi băm và cổng xác thực lên Must:** F3.5 → **F2.12**, F3.6 → **F2.13**, làm trong
  Phase 2 (`v0.2.0`). Lý do: đây là điểm khác biệt README nêu ngay dòng đầu, không được để rơi vào nhóm
  có thể cắt. Phần còn lại của F3.5 (tab "Lịch sử" hiển thị diff) giữ ở Phase 3, mức Should; mã F3.6 bỏ
  trống để các mã F3.x khác không đổi.
- **§4 mở rộng thành "Tài nguyên cần có":** con người, hạ tầng, tài khoản, dữ liệu, kiến thức, chi phí và
  những thứ phải có trước 21/10; bảng RAM theo profile giữ nguyên ở §4.2.

**18/10/2026** — dời lịch:

- Đến 18/10 repo vẫn chưa có issue, PR hay dòng mã nào của lõi; còn 3 ngày tới `v0.1.0` (21/10) là không
  kịp. Dời **`v0.1.0` → 25/10**, Phase 2 → 26/10–08/11 (giữ đủ 2 tuần vì đây là sản phẩm chính),
  Phase 3 → 09–20/11 (rút 2 ngày), Phase 4 → 21–25/11 (rút 2 ngày, cũng là đệm).
- **Giữ nguyên** ngày đóng băng 26/11, `v1.0.0` 03/12, gửi thư 05/12. Phase 0 kéo đến 20/10, hai spike
  chạy song song đầu Phase 1. Không kịp 25/10 thì cắt F1.10 sang đầu Phase 2, không lùi thêm.

**18/10/2026** — làm #18 (schema + Hasura):

- **Vai trò `admin` đổi thành `tenant_admin`.** Chạy thử cho thấy Hasura coi `admin` trong JWT là quản trị
  toàn quyền: đọc được dữ liệu của mọi thuê ước. Realm (#21) phải dùng tên mới.
- **Phần CSDL của F2.12 làm luôn trong #18** (trigger chuỗi băm, `core.audit_verify()`), vì bảng
  `core.audit_log` đằng nào cũng tạo ở F1.3. Phase 2 còn job neo hash, lệnh `dxos audit verify` và màn xem sổ.
- `office.document_files`, `office.document_acl` thêm cột `tenant_id`; khóa ngoại giữa các bảng nghiệp vụ đi
  kèm `tenant_id`, để CSDL tự chặn việc trỏ sang dữ liệu của thuê ước khác.

**18/10/2026 (tối)** — Frontend và Backend chưa bắt đầu (chưa có realm Keycloak, khung Nuxt, Compose); người làm
AI làm thay toàn bộ lát cắt đầu tiên theo chiều dọc thay vì làm xong lõi rồi mới làm giao diện. Đã chạy được
bằng `make up && make seed`: #13 (Compose, Makefile), #14 (APISIX), #15 (svc-workflow + Actions), #16 (seed,
smoke), #21 (realm), #22 (giao diện), #23 (BPMN văn bản đến), cùng #18–#20. Vai trò lấy từ thuộc tính
`moc_role` (một giá trị cho cả hai claim vai trò của Hasura) thay vì vai trò realm. Danh bạ `core.users` đồng
bộ từ Keycloak. Kế tiếp: lát văn bản đi + PDF có mã QR + cổng xác thực (F2.4, F2.13). Rủi ro mới: lịch sử
commit chỉ một tác giả (PoF #1) — cần hai bạn nhận việc Phase 2.

**19/10/2026** — Phase 1 xong phần mã (còn F1.9 chờ server): CI 7 job chạy thật, `make install` (F1.8), giới hạn
tốc độ (F1.2), TOTP bắt buộc với văn thư và lãnh đạo (F1.1), tài liệu API xuất tự động (F1.10). Làm sớm lõi của
Phase 2:

- **F2.4 và F2.13 đã chạy** từ giao diện xuống lõi, có smoke và e2e. Lát văn bản đi gồm soạn, xem trước, trình,
  trả lại hoặc ký duyệt; văn thư cấp số đi; PDF có mã QR và SHA-256. Cổng xác thực công khai tra theo mã hoặc thả
  tệp.
- **PDF dựng từ khuôn HTML** (WeasyPrint, phông Liberation Serif cùng số đo Times New Roman), chưa nhận tệp dự
  thảo `.docx` tải lên. Lý do: số, ngày, mã QR phải in đúng chỗ theo thể thức, còn tệp người dùng tải lên thì không
  biết chỗ trống nằm đâu.
- **Không phải chữ ký số.** Văn bản ghi "Đã duyệt trên hệ thống Mộc". Tính toàn vẹn dựa vào SHA-256 trong CSDL,
  sổ kiểm toán chuỗi băm và cổng xác thực. Chữ ký số PKI (PAdES) để sau, nếu còn thời gian.
- **F2.5 và timer nhắc hạn đã chạy.** Sau mỗi bước, người phải làm tiếp nhận thông báo qua Centrifugo; thông báo
  lưu ở `core.notifications`, nên mất kết nối không mất tin. Nhắc hạn đổi so với bản thiết kế: timer vẫn nằm trong
  BPMN (`R2/${slaDuration}`), nhưng `svc-workflow` **tự lấy** việc nhắc về (external worker của Flowable) thay
  cho callback `POST /internal/flowable/events`. Lý do: Flowable không phải giữ địa chỉ và khóa của dịch vụ nào,
  `svc-workflow` dừng thì việc nhắc chờ đó chứ không mất. Giao diện nhận tin bằng WebSocket có sẵn của trình
  duyệt, không dùng `centrifuge-js` (kéo theo `protobufjs` có script chạy lúc cài).
- **F2.12 xong.** `svc-files` định kỳ neo đầu chuỗi sổ kiểm toán ra bucket lạnh `moc-cold` bật S3 Object Lock
  (COMPLIANCE): đã thử trên SeaweedFS 4.48, xóa phiên bản, rút ngắn hạn giữ, xóa bucket đều bị từ chối, kể cả với
  khóa quản trị của kho. `make audit` tính lại cả chuỗi bên ngoài CSDL. Có test cho sửa một dòng, sửa rồi tính
  lại cả chuỗi (`core.audit_verify()` trong CSDL bị qua mặt, mốc neo thì không), cắt đuôi, đổi hash văn bản phát
  hành. Màn "Sổ kiểm toán" cho lãnh đạo, quản trị đơn vị. Khác bản thiết kế:
  - Lệnh là `python3 scripts/moc.py audit verify` (`make audit`) thay cho `dxos audit verify`: tên kỹ thuật đã
    đổi sang `moc` cùng tên sản phẩm. Viết bằng thư viện chuẩn thay Typer, để chạy ngay trong thư mục cài mà
    không cài thêm gói.
  - Bản neo "tệp trong repo" thành `audit anchor --to <tệp>`: đơn vị tự chép tệp ra kho git riêng. Chưa có
    server nên chưa chạy tự động.
  - Màn xem sổ không hiện giá trị của cột chứa nội dung, vì lãnh đạo không được đọc văn bản hạn chế.
- **F2.2 xong.** Một JSON Schema dùng chung, `schemas/van-ban-den.json`, cho ba lớp: form kiểm bằng Ajv, Action
  mới `receiveIncoming` của `svc-workflow` kiểm lại bằng `jsonschema`, PostgreSQL chặn lần cuối bằng 4 ràng buộc
  `CHECK` mới. Ba lớp chạy chung một bộ ca thử (`schemas/van-ban-den.cases.json`), mỗi lớp một bộ test; `make
  smoke`, `make e2e` kiểm lại trên hệ thống thật. Khác bản thiết kế:
  - Ajv biên dịch schema thành mã JavaScript lúc dựng (standalone), không chạy trên trình duyệt: CSP của ứng dụng
    không cho `unsafe-eval`. Ajv chỉ là phụ thuộc lúc dựng.
  - Văn thư không còn quyền ghi thẳng bảng văn bản; trước đây giao diện ghi thẳng bằng GraphQL nên lớp Action
    chưa có. Sửa văn bản đến chưa vào sổ tạm không còn (giao diện chưa từng dùng).
  - "Hôm nay" (ngày ban hành không sau hôm nay, hạn không trước hôm nay) và "chữ ở dạng Unicode dựng sẵn" không
    viết được trong JSON Schema: thêm hai từ khóa chú thích `x-moc-date`, `x-moc-nfc`, form và `svc-workflow` tự
    kiểm; CSDL kiểm NFC bằng `is nfc normalized`, còn ngày thì kiểm điều yếu hơn mà không phụ thuộc lúc ghi.
  - Thêm điều bản kế hoạch chưa nói: chặn ký tự ẩn và chữ dạng tổ hợp chép từ PDF, vì chúng làm cùng một văn bản
    lọt qua chặn trùng.
  - Dữ liệu của các việc trong quy trình (`completeTask`) vẫn kiểm bằng Pydantic ở `svc-workflow`, form soạn văn
    bản đi vẫn ghi thẳng; chuyển sang JSON Schema dùng chung khi làm lại các form đó.
- Phase 2 còn lại: sổ đăng ký in được (F2.8).

**20/10/2026** — F2.8:

- **F2.8 xong.** Sổ đăng ký văn bản đến / đi theo năm, đúng các cột của mẫu sổ ở NĐ 30, Phụ lục IV (sổ đến 9
  cột, sổ đi 10 cột), xem trên trang `/so-dang-ky` và in PDF A4 ngang để ký nhận, đóng sổ (Điều 16, 22). Chỉ văn
  thư, lãnh đạo đơn vị xem được; mỗi lần in vào sổ kiểm toán. Khác bản thiết kế:
  - `svc-files` dựng sổ (`GET /api/registers/{in|out}/{năm}`, `…/pdf`) thay cho hai view `office.v_register_in`,
    `v_register_out` trong Hasura. Lý do: sổ phải liền số từ 01 kể cả văn bản hạn chế, mà lãnh đạo, văn thư không
    đọc được văn bản hạn chế của người khác (`office.document_visible`), nên view đọc bằng quyền người dùng sẽ
    hở số. `svc-files` đọc cả năm bằng vai trò `service`, hỏi lại Hasura bằng token người in xem họ đọc được dòng
    nào, dòng còn lại chỉ in số, ngày, số ký hiệu. Quy tắc ai đọc gì vẫn chỉ nằm ở Hasura.
  - Màn hình và bản in dùng chung các ô đã định dạng, nên không lệch nhau.
  - Ô Ký nhận, Số lượng bản để trống, ghi tay trên bản in: hệ thống không biết bản giấy gửi đi mấy bản.
- Phase 2 còn lại: tìm trong nội dung PDF có lớp chữ (F2.7 hiện mới tìm theo số ký hiệu, trích yếu, cơ quan ban
  hành; trường `content` của chỉ mục đã chừa sẵn) và F2.11 (cộng đồng, không phải mã).

**20/10/2026** — F2.7:

- **F2.7 xong.** Tìm được theo nội dung văn bản đi và chữ trong tệp PDF đính kèm; kết quả chỉ khớp nội dung có
  nhãn "Khớp trong nội dung". Khác bản thiết kế:
  - Chữ của PDF lưu trong CSDL (`core.file_texts`), không chỉ trong Meilisearch: svc-files khởi động lại thì đồng
    bộ lại toàn bộ chỉ mục, không phải đọc lại mọi tệp.
  - Đọc ở vòng nền, không lúc tải lên: lúc tải lên tệp chưa gắn vào văn bản nào, chưa biết văn bản có hạn chế không;
    vòng nền còn đọc bù tệp tải lên trước đó.
  - **Văn bản hạn chế không tìm được theo nội dung**, kể cả với người được đọc nó. Lý do: bản chữ trần nằm ngoài
    tệp sẽ vô hiệu việc lưu mã hóa tệp của văn bản hạn chế (F3.7); và chỉ mục chỉ còn siêu dữ liệu của văn bản hạn
    chế như trước.
  - PDF đọc trong tiến trình con giới hạn bộ nhớ, CPU, thời gian: tệp do người ngoài gửi, ClamAV không bắt được
    PDF dựng để làm treo bộ đọc.
  - Bản scan, ảnh chụp không có lớp chữ: đánh dấu `empty`, để dành OCR ở F4.1.
- `make seed` dựng tệp PDF tiếng Việt thật cho văn bản đến mẫu (WeasyPrint trong container svc-files), để màn tìm
  kiếm có nội dung thật mà tìm; ví dụ "giáo dục quốc phòng" ra công văn 131/ĐT-ĐH.
- Sửa sau rà soát:
  - Một PDF dựng có ý đồ (khai hàng tỉ trang) từng chặn được hàng đợi đọc chữ của mọi thuê ước. Nay tệp nào cũng đi
    tới một dòng kết quả.
  - Vị trí trang sau của tìm kiếm trước đây trả dạng số, đếm ngược ra được số văn bản mình không được đọc có chứa
    một từ. Nay mã hóa (`cursor`).
  - Tìm kiếm bắt mọi từ phải khớp.
  - Trigger CSDL xóa chữ khi văn bản bật hạn chế.
- Phase 2 còn lại: F2.11 (cộng đồng, không phải mã).

**20/10/2026** — F3.1 (Phase 3, làm sớm):

- **F3.1 xong.** `make demo-kiem-dich` là màn (iv) Kiểm dịch, chạy bằng một lệnh, dưới một phút:
  - tệp sạch qua; tệp EICAR bị ClamAV chặn trên luồng, không được lưu (không có dòng trong `core.files`);
  - lần chặn nằm trong sổ kiểm toán, được neo ra bucket lạnh khóa ghi rồi kiểm lại cả chuỗi.
- Phần chặn và phần ghi sổ đã có từ F1.6 và F2.12. F3.1 thêm:
  - màn demo một lệnh, chạy được cả trong thư mục cài;
  - `docs/demo-script.md`, nơi ghi đủ 4 màn nguyên lý — điều kiện hoàn thành Phase 3;
  - sổ kiểm toán hiện mẫu mã độc và cỡ của tệp bị chặn (chỉ ở dòng `file.rejected`; cỡ tệp đã lưu vẫn ẩn);
    tên tệp vẫn ẩn vì do người dùng đặt;
  - smoke và e2e kiểm cả dòng sổ của lần chặn.
- Phase 3 còn lại: F3.2–F3.5, F3.7–F3.15.

**20/10/2026** — F3.11 (Phase 3):

- **F3.11 xong.** Trang **Điều hành** cho lãnh đạo đơn vị:
  - thẻ tổng: văn bản đến chưa xong, quá hạn, khẩn chưa xong, thời gian xử lý trung bình và tỉ lệ đúng hạn;
  - biểu đồ Apache ECharts 6.1.0 (chỉ nạp biểu đồ cột, vẽ SVG), mỗi biểu đồ kèm bảng số.
- Số liệu lấy qua view của Hasura như kế hoạch, nên tự đúng SSO và quyền thuê ước, không thêm dịch vụ. Tính lúc
  mở trang, có nút làm mới; không dùng kênh realtime.
- Chỗ khác kế hoạch:
  - Bốn view thay cho hai: thêm `v_document_counts` (theo trạng thái, độ khẩn, quá hạn) và `v_outgoing_by_month`.
  - Văn bản hạn chế không vào phép chia nào, chỉ có con số tổng. Lý do (phát hiện khi rà soát): lãnh đạo đọc được
    mọi văn bản khác, nên lấy số chia trừ đi là ra trạng thái, phòng, thời gian xử lý của văn bản hạn chế. Đổi lại,
    số quá hạn trên dashboard không gồm văn bản hạn chế.
  - Chỉ vai trò `director` đọc được. Quản trị đơn vị không đọc nội dung nghiệp vụ. Lãnh đạo phòng xem số của
    phòng mình để sau, nếu đơn vị chạy thử cần.
  - Lúc xong của văn bản đến lấy từ dòng thời gian (sự kiện báo xong hoặc cho lưu), không thêm cột mới.
- Phase 3 còn lại: F3.2–F3.5, F3.7–F3.10, F3.12–F3.15.

**20/10/2026** — F3.4 (Phase 3):

- **F3.4 xong.** `make backup`, `make restore` (`moc backup create --keep N | list | check | restore [LƯỢT]`):
  - mỗi lượt gồm `pg_dump -Fc` của mọi CSDL trong máy chủ PostgreSQL và cả volume SeaweedFS, vào kho restic 0.19.1
    mã hóa (container `restic`, profile `backup`, không mạng); lượt thiếu manifest không dùng để khôi phục;
  - khôi phục: dừng Mộc, dựng PostgreSQL, `pg_restore --create` từng CSDL, so hash dòng sổ kiểm toán cuối lúc sao
    lưu, khôi phục volume tệp, ghi lần khôi phục vào sổ, chạy lại;
  - CI diễn tập mỗi pull request: xóa volume CSDL và tệp, khôi phục, rồi smoke và `make audit` phải qua.
- Chỗ khác kế hoạch:
  - restic chạy trong container có image ghim thay cho gói hệ thống: không cài gì lên máy chủ, mọi nơi cùng một
    phiên bản.
  - Sao lưu cả volume SeaweedFS chứ không chỉ tệp văn bản, vì bucket lạnh giữ mốc neo sổ kiểm toán cùng trạng thái
    khóa ghi. `svc-files` và SeaweedFS tạm dừng suốt lúc dump CSDL và chép tệp. Lý do: mốc neo ghi vào bucket
    trước, vào CSDL sau; chụp hai nơi ở hai thời điểm thì khôi phục xong `make audit` báo chuỗi bị cắt (mốc vượt
    quá CSDL) hoặc báo bảng mốc có mốc mà bucket không có.
  - Lần khôi phục thành một dòng sổ kiểm toán (`system.restored`), để các dòng mất đi sau lúc sao lưu có lý do
    ghi ngay trong sổ.
  - Không sao lưu `.env` (chứa chính khóa kho): tài liệu dặn chép ra ngoài máy chủ. Chỉ mục Meilisearch và chữ ký
    ClamAV không sao lưu, vì dựng lại được.
- Phase 3 còn lại: F3.2, F3.3, F3.5, F3.7–F3.10, F3.12–F3.15.

**20/10/2026** — F3.2 (Phase 3):

- **F3.2 xong.** Két bí mật OpenBao 2.7.1 (`openbao/`, dịch vụ `openbao`):
  - `svc-files`, `svc-workflow` không còn nhận bí mật qua biến môi trường; lúc khởi động mỗi dịch vụ đăng nhập
    AppRole riêng, chỉ đọc được phần bí mật của mình (kv-v2 `moc/`); két cấp secret_id mới mỗi lần khởi động;
  - static seal: khởi động lại là tự mở khóa (cần cho màn tự phục hồi F3.3); két ghi sổ mọi lần truy cập ra stdout;
  - khóa transit `moc-files` (AES-256-GCM) cho F3.7; policy của `svc-files` chỉ xin khóa dữ liệu mới và mở khóa đã
    bọc, không lấy được khóa gốc;
  - `make demo-ket-bi-mat` (màn (iv), bước CI), `make smoke` +2.
- Chỗ khác kế hoạch:
  - Két nằm trong profile `core` chứ không phải `ops`: `svc-files`, `svc-workflow` không khởi động được khi thiếu két.
  - AppRole cấp bí mật dịch vụ (khóa S3, khóa quản trị Hasura, khóa Meilisearch, khóa Actions, mật khẩu Flowable,
    khóa Centrifugo, client secret) chứ không phải mật khẩu CSDL: hai dịch vụ của đội không nối thẳng PostgreSQL.
  - OpenBao 2.7 bỏ storage `file` (dùng raft một nút), chỉ cho khai thiết bị audit trong tệp cấu hình, và chặn
    `generate-root` khi chưa đăng nhập. Vì vậy két được cấu hình bằng token root một lần lúc khởi tạo rồi thu hồi;
    các lần khởi động sau dùng token khởi động: không đọc thẳng được bí mật, không sửa được policy, nhưng cấp được
    secret_id cho hai vai trò có sẵn (nên volume của két phải được giữ như chính két).
  - Két nằm riêng mạng `secrets` (internal) với hai dịch vụ dùng nó: container khác không gọi được két, kể cả lúc két
    chưa khởi tạo.
  - Khóa static seal 32 byte suy từ `MOC_OPENBAO_SEAL_KEY` bằng SHA-256, để `make env` sinh như mọi khóa khác.
- Nói rõ khi trình bày: `.env` vẫn là nguồn bí mật và chứa khóa mở két; khóa phục hồi, token khởi động, secret_id
  nằm trên đĩa; phần mềm thượng nguồn (Hasura, SeaweedFS, Meilisearch, Centrifugo) vẫn đọc bí mật từ biến môi
  trường; két chưa có TLS và chưa nằm trong `make backup` (F3.7 phải thêm, vì mất khóa transit là mất tệp mã hóa).
- Phase 3 còn lại: F3.3, F3.5, F3.7–F3.10, F3.12–F3.15.

**20/10/2026** — F3.3 (Phase 3):

- **F3.3 xong.** Reconciler GitOps và tự phục hồi (`scripts/reconcile.py`, `make reconcile`, tệp mẫu systemd timer
  60 giây trong `ops/systemd/`):
  - tự phục hồi: dịch vụ khai trong compose mà mất container hoặc đã dừng thì `up -d`, unhealthy thì khởi động lại;
  - GitOps (khi đặt `MOC_GITOPS_DIR`): kéo nhánh `deploy` về bản sao git riêng; commit mới, hoặc tệp đã cài bị sửa tay
    (so băm từng tệp theo danh sách `.moc-install`), thì dựng image, cài lại đúng commit, chạy lại; commit áp lỗi thì
    đợi commit kế tiếp chứ không thử lại mỗi phút;
  - `make demo-tu-phuc-hoi` (màn (iv), bước CI), bước CI GitOps với repo git cục bộ, `make smoke` +1 (tổng 46).
- Chỗ khác kế hoạch:
  - Không dùng Flux hay Argo CD: hai công cụ này cần Kubernetes, Mộc chạy Docker Compose. Reconciler là script thư
    viện chuẩn, chạy bằng systemd timer trên máy chủ chứ không trong container (không gắn socket Docker vào đâu).
  - Áp một commit là cài lại toàn bộ (`down` → `install.sh install` → `up --wait`, Mộc dừng khoảng một phút):
    `install.sh` không cho thay cấu hình dưới container đang chạy. Image dựng xong trước khi dừng Mộc.
  - Reconciler, `scripts/backup.py` và `install.sh` dùng chung một khóa (flock trên thư mục chạy Mộc): không dựng lại
    dịch vụ giữa lúc khôi phục, cài đặt. Khôi phục dừng giữa chừng để lại dấu `.moc-restoring`: reconciler không chạy
    lại Mộc trên dữ liệu dở dang. Dịch vụ tạm dừng có chủ ý thì bỏ qua cả lượt; còn tạm dừng từ lần sao lưu bị giết
    cứng thì chạy lại.
  - Cài hỏng sau khi đã dừng Mộc thì reconciler cài lại commit cũ; `install.sh` kiểm đủ tệp trước khi xóa và ghi danh
    sách tệp (cũ lẫn mới) trước khi chép, nên bị ngắt giữa chừng vẫn cài lại được.
  - APISIX giữ địa chỉ DNS dịch vụ 5 giây thay vì theo TTL (mặc định tới 10 phút): container dựng lại có địa chỉ mới.
- Nói rõ khi trình bày: `.env` (bí mật, cấu hình riêng máy chủ) không nằm trong git nên không do reconciler quản;
  image cũ không tự xóa; bảo trì tay thì phải dừng timer trước, không thì reconciler dựng lại trong vòng một phút.
- Phase 3 còn lại: F3.5, F3.7–F3.10, F3.12–F3.15.

**20/10/2026** — F3.8 (Phase 3):

- **F3.8 xong.** Lập hồ sơ và nộp lưu — dữ liệu nóng sang lạnh (màn (i)):
  - CSDL: `office.case_files`, `office.case_file_documents` (migration `1792281601300_case_files`); chuyên viên, tổ
    trưởng lập hồ sơ của phòng mình, đưa vào văn bản đã xử lý xong mình đọc được và thuộc phòng mình, đóng hồ sơ (ngày
    đóng do CSDL đặt); không vai trò nào đặt được `archived`;
  - svc-files (`svc_files.archive`): vòng nền mỗi giờ nộp lưu hồ sơ đóng từ `MOC_ARCHIVE_AFTER_DAYS` ngày — gói
    Parquet (DuckDB 1.5.6) + tệp gốc + manifest có băm, mọi tên theo băm, khóa ghi COMPLIANCE theo thời hạn bảo quản;
    đọc lại cả gói, so băm, rồi hàm SQL `office.archive_case_file` (một giao dịch, khóa dòng, lệch với gói thì không
    đổi gì) gỡ dòng thời gian, liên kết tệp, ghi `case_file.archived`;
  - văn bản đã nộp lưu vẫn tìm thấy theo số, ký hiệu, trích yếu và cổng xác thực vẫn trả "khớp"; phòng đọc
    `GET /api/case-files/{id}/archive` đọc lại gói, kiểm băm với CSDL, chỉ trả văn bản người gọi đọc được;
  - `make demo-nong-lanh` (màn (i), bước CI), `make smoke` +1 (tổng 47), 7 test CSDL, 12 test đơn vị.
- Chỗ khác kế hoạch:
  - Không dùng Kestra: job nộp lưu là vòng nền trong `svc-files` (như vòng neo sổ kiểm toán), chạy tay được bằng
    `python -m svc_files.archive now`. Một job mỗi giờ không đáng thêm một máy chủ Java khoảng 1 GB RAM; DuckDB nhúng
    trong svc-files, không chạy máy chủ riêng.
  - Gói gồm ba bảng Parquet riêng (văn bản, giao việc, dòng thời gian) thay vì một `metadata.parquet`; mọi tên theo
    băm nội dung (manifest cũng vậy), tệp giữ nguyên định dạng gốc.
  - Giao việc ở lại CSDL (gói cũng có một bản): xóa đi thì người được giao mất quyền xem văn bản và sổ đăng ký ghi sai
    cột "đơn vị nhận". Chỉ dòng thời gian và liên kết tệp rời CSDL; phần nặng là tệp, rời bucket nóng.
  - Văn bản hạn chế không vào hồ sơ: tệp của nó sẽ mã hóa riêng (F3.7), nộp lưu bản mã hóa cần thêm bước giữ khóa.
  - Gói và mốc neo sổ kiểm toán chung một bucket lạnh có khóa ghi (`MOC_COLD_BUCKET`), khác tiền tố.
  - Chưa có giao diện lập hồ sơ (làm qua GraphQL, demo, smoke), chưa có e2e mới; phòng đọc chỉ trả danh sách văn bản
    và tệp trong gói, chưa xem được tệp có watermark (cùng đợt F3.7).
- Nói rõ khi trình bày: sau khi nộp lưu, lớp chữ PDF của văn bản không còn trong chỉ mục tìm kiếm (vẫn tìm theo số,
  ký hiệu, trích yếu); thống kê thời gian xử lý không tính văn bản đã nộp lưu (dòng thời gian đã rời CSDL); gói đã
  ghi thì trong thời hạn bảo quản không ai xóa được, kể cả quản trị kho.
- Phase 3 còn lại: F3.5, F3.7, F3.9, F3.10, F3.12–F3.15.

**20/10/2026** — F3.9 (Phase 3):

- **F3.9 xong.** Phả hệ dữ liệu và kiểm chất lượng (màn (iii)):
  - svc-files (`svc_files.lineage`): mỗi lượt nộp lưu (F3.8) là một run OpenLineage 2-0-2 của job
    `moc.case_file.archive` với 4 run con — `files`, `tables`, `manifest`, `commit` (facet `parent`); tên dataset
    theo quy ước OpenLineage: `postgres://postgres:5432` + `moc.<schema>.<bảng>`, `s3://<bucket>` + key;
  - kiểm chất lượng: bảng Parquet dựng xong được DuckDB đọc lại — số dòng bằng số dòng lấy từ CSDL, cột bắt buộc không
    null (facet `dataQualityAssertions`, `outputStatistics`, `schema`); trượt thì bước FAIL, cảnh báo trong nhật ký,
    job dừng trước khi ghi gì sang bucket lạnh (đổi thứ tự so với F3.8: dựng và kiểm bảng trước, chép tệp sau);
  - CSDL: `core.lineage_events` (migration `1792281601400_lineage`), chỉ thêm (trigger chặn sửa, xóa), lãnh đạo và
    văn thư đọc của đơn vị mình qua Hasura; cột `event` giữ nguyên sự kiện;
  - `make demo-pha-he` (màn (iii), bước CI), `make smoke` +1 (tổng 48), 2 test CSDL, 6 test đơn vị.
- Chỗ khác kế hoạch:
  - Chưa dựng Marquez trong compose: thêm máy chủ Java và CSDL riêng (~1 GB RAM) cho một job mỗi giờ; bản phát hành
    gần nhất đã từ 03/2025. Sự kiện lưu trong PostgreSQL — đúng phương án dự phòng đã ghi trong `DEPENDENCIES.md` —
    và gửi được sang Marquez bằng `MOC_OPENLINEAGE_URL` (có test đơn vị, chưa thử với Marquez thật).
  - Không dùng `openlineage-python`: sự kiện dựng bằng thư viện chuẩn, không thêm phụ thuộc.
  - Phả hệ mới phủ job nộp lưu (job dữ liệu duy nhất hiện có); "báo cáo" của dashboard (F3.11) đọc thẳng view, chưa có
    job nên chưa có run.
- Phase 3 còn lại: F3.5, F3.7, F3.10, F3.12–F3.15.

**20/10/2026** — F3.5 (Phase 3):

- **F3.5 xong.** Tab "Lịch sử" trên trang văn bản:
  - CSDL: view `office.document_history` (migration `1792281601500_document_history`) — các dòng sổ kiểm toán về văn
    bản, tệp gắn với nó, giao việc, lần đưa vào hồ sơ; chỉ trường `overview` (cột nội dung chỉ có tên), không có hash,
    không có danh sách được xem văn bản hạn chế; Hasura cho chuyên viên, tổ trưởng, văn thư, lãnh đạo đọc khi đọc
    được văn bản; mỗi nhánh nối trên chỉ mục, không quét cả sổ;
  - giao diện: tab "Lịch sử" cạnh "Dòng thời gian", tải khi mở; cách hiện một dòng sổ gom vào `useAuditFormat`, dùng
    chung với trang Sổ kiểm toán;
  - 3 test CSDL, e2e: chuyên viên mở tab Lịch sử của văn bản vừa xử lý.
- Chỗ khác kế hoạch: làm F3.5 trước F3.10 và F3.7 (thứ tự hàng đợi đêm 20/10) vì vừa một lượt kiểm trước 09:00; F3.10
  cần thêm context broker NGSI-LD, F3.7 cần mã hóa tệp — để phiên sau.
- Phase 3 còn lại: F3.7, F3.10, F3.12–F3.15.

**20/10/2026** — F3.13 (Phase 3):

- **F3.13 xong (bản gọn).** Giám sát cổng API:
  - APISIX bật plugin `prometheus` toàn cục, nhãn route theo id trong `gateway/apisix.yaml`; cổng xuất chỉ số 9091
    chỉ trong mạng `moc`;
  - dịch vụ `prometheus` (thu 15 giây, giữ `MOC_METRICS_RETENTION`) và `grafana` (nguồn dữ liệu và bảng điều khiển
    "Mộc — cổng API" nạp từ `monitoring/`); Grafana chỉ nghe 127.0.0.1, không tạo tài khoản quản trị, chỉ xem ẩn danh;
  - `make smoke` +1 (tổng 49): Prometheus đọc được APISIX, có số đếm theo route, Grafana có bảng điều khiển; mỗi
    dịch vụ giới hạn 512 MB RAM; chỉ số không vào bản sao lưu.
- Chỗ khác kế hoạch: hai dịch vụ nằm trong profile `core` chứ không profile riêng — các script vận hành (sao lưu,
  khôi phục, reconciler) gọi compose với `--profile core --profile app`, để chung profile thì tự phục hồi và khôi
  phục quản lý luôn cả giám sát; tốn thêm khoảng 300 MB RAM. Chưa có chỉ số của từng dịch vụ (svc-files,
  svc-workflow, Hasura, PostgreSQL) và chưa có cảnh báo (Alertmanager) — để sau.
- Phase 3 còn lại: F3.7, F3.10, F3.12, F3.14, F3.15.

**20/10/2026** — F3.10 (Phase 3):

- **F3.10 xong (bản rút gọn), màn (ii).** Hội tụ IT/OT:
  - profile `iot`: Scorpio 6.0.2 (bản java mặc định, không Kafka) + PostGIS riêng; không mở cổng, CSDL broker ở
    mạng riêng chỉ broker nối được;
  - `svc-workflow` giữ subscription `temperature>ngưỡng` trong tenant NGSI-LD của từng đơn vị, nhận thông báo ở
    `/ot/notify/{mã đơn vị}` kèm token HMAC riêng từng đơn vị; vượt ngưỡng → dự thảo "Báo cáo sự cố" (Báo cáo, Khẩn)
    từ mẫu, sự kiện `ot.alarm`, thông báo khẩn cho chuyên viên phụ trách; chống trùng khi dự thảo cũ chưa trình;
  - cảm biến giả lập `ot/sensor.py` (thư viện chuẩn, chạy một lần); `make demo-it-ot` (bước CI): 5 lần đo, đúng một
    dự thảo, lịch sử đo trong broker, trình → tổ trưởng có việc duyệt, sai token → 401;
  - 14 test đơn vị (`test_ot.py`); giao diện: nhãn sự kiện ở dòng thời gian, thông báo khẩn.
- Chỗ khác kế hoạch:
  - profile riêng `iot` chứ không `core` (~550 MB RAM, chỉ bật cho màn này); Scorpio bắt buộc PostGIS nên thêm image
    `postgis/postgis:16-3.5-alpine` (GPL-2.0, dịch vụ độc lập — bản 16-3.6 mới đẩy 19/10, quá mới);
  - người đứng tên dự thảo do cảm biến khai (`responsible` = tên đăng nhập chuyên viên) vì chỉ người soạn mới trình
    được văn bản đi; người khai sai vai trò hay khác đơn vị thì bỏ qua;
  - token xác thực broker suy từ `MOC_ACTION_SECRET` (không thêm bí mật mới); lịch sử đo ở lại broker, không vào
    CSDL của Mộc và không vào bản sao lưu; chưa có giao diện xem cảm biến;
  - Scorpio không xác thực: thiết bị vào được mạng `iot-devices` là ghi được vào tenant bất kỳ. Thiết bị tách khỏi
    svc-workflow bằng mạng riêng; cổng thiết bị cấp tenant theo khóa (IoT Agent / PEP proxy) để phiên sau;
  - lỗi của Scorpio 6.0.2 với tenant: ngữ cảnh của subscription cất theo tenant nhưng lúc gửi thông báo lại tìm ở tenant
    mặc định → mọi thông báo bị bỏ (thử trên stack rời trước đó qua được vì broker còn ra Internet). Vòng qua bằng một
    subscription "neo" tạm dừng ở tenant mặc định; nên báo lỗi cho dự án Scorpio.
- Phase 3 còn lại: F3.7, F3.12, F3.14, F3.15.
