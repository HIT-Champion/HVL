# Kiến trúc Signet

> Tài liệu này ghi lại kiến trúc hệ thống, bản đồ công cụ nguồn mở, và các quyết định kỹ thuật
> kèm lý do. Trạng thái hiện tại: **đang khảo sát công cụ** (giai đoạn 1 của `ROADMAP.md`).

## 1. Nguyên tắc kiến trúc

### 1.1. Open-Core: điều phối, không viết lại

Signet **không** viết lại các phần mềm đã có bản nguồn mở trưởng thành. Nó là **lớp điều phối**
(orchestration layer) gắn kết chúng thành một hệ thống vận hành thống nhất. Giá trị của dự án
nằm ở *lớp keo* — cách các thành phần được nối, chuẩn hóa và đồng bộ — không nằm ở bản thân
các thành phần.

Hệ quả bắt buộc, áp dụng không ngoại lệ:

| Được phép | Không được phép |
|---|---|
| Kéo image thượng nguồn có ghim thẻ phiên bản và digest | Sao chép cây mã upstream vào kho này |
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

- **Bối cảnh:** Signet lắp ghép nhiều phần mềm thượng nguồn có giấy phép khác nhau. Tiêu chí chấm
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

### QĐ-004: Trợ lý hỏi đáp dùng lại Meilisearch tìm lai, tự viết đường ống, không Qdrant / LlamaIndex

- **Bối cảnh:** F4.2 — người dùng hỏi bằng câu tự nhiên trên kho văn bản, câu trả lời phải kèm số ký hiệu và trang,
  và chỉ dựa trên văn bản người hỏi được xem. Kế hoạch ban đầu: Qdrant (kho véc-tơ) + bge-m3 + LlamaIndex trong một
  dịch vụ `svc-ai` mới. Ràng buộc: máy 8 GB, CI không có mô hình nào, văn bản hạn chế (F3.7) không bao giờ được lộ.
- **Phương án kho truy xuất:** Qdrant — thêm image và RAM, kho thứ hai phải đồng bộ thuộc tính quyền, không tìm theo
  từ khóa tiếng Việt nên CI vẫn cần đường khác. pgvector — lọc quyền bằng đúng hàm `office.document_visible`, nhưng
  phải thay image PostgreSQL của lõi bằng image tự dựng, và PostgreSQL không có cấu hình chữ tiếng Việt. Meilisearch —
  đã chạy (F1.7), đã bỏ dấu tiếng Việt, bản CE (MIT) có tìm lai từ khóa + véc-tơ, F2.7 đã có mẫu lọc thuê ước + hậu
  kiểm; không có join nên thuộc tính quyền phải chép vào từng đoạn.
- **Phương án khung:** LlamaIndex kéo 28 gói phụ thuộc trực tiếp, NLTK và tiktoken tải dữ liệu từ Internet lúc chạy
  (mạng `ai` không ra Internet), và không biết quyền của Signet — lọc quyền, trích dẫn, kiểm câu trả lời vẫn phải
  tự viết.
- **Quyết định:** chỉ mục đoạn Meilisearch `chunks` (một tài liệu mỗi đoạn, mỗi đoạn biết trang của nó), embedder
  `userProvided`: `svc-files` tự gọi Ollama `/api/embed` (Qwen3-Embedding-0.6B, đổi sang bge-m3 bằng một biến). Không
  dùng nguồn nhúng `ollama` của Meilisearch: Meilisearch sẽ phải vào mạng `ai`, và khi không có mô hình (CI) cả lô
  thêm tài liệu lỗi, hỏng luôn đường từ khóa. Đường ống (cắt đoạn, lọc quyền, câu trích, gọi mô hình, kiểm trích dẫn)
  tự viết trong gói `svc_files/assist/` — `svc-files` đã có client Meilisearch, client Hasura, chữ PDF của F2.7, mạng
  `ai`; không thêm image, gói Python, route gateway nào.
- **Quyền ở bước truy xuất, hai lớp, cả hai đứng trước mô hình và trước người dùng:** (1) lọc trước trong Meilisearch
  theo vai trò, đúng như `office.document_visible` — văn bản hạn chế không bao giờ vào chỉ mục; (2) hậu kiểm bằng
  Hasura với token người hỏi, bỏ mọi đoạn của văn bản người hỏi không đọc được hoặc `restricted`. Lớp 1 quyết độ phủ,
  lớp 2 quyết an toàn: chỉ mục chậm vài giây sau khi bật hạn chế hay hủy giao việc vẫn không lộ đoạn nào. Không có
  đoạn nào qua hậu kiểm thì không gọi mô hình.
- **Hệ quả:** không có mô hình (CI, máy yếu) vẫn chạy đủ: tìm theo từ khóa + câu trích nguyên văn. Câu trả lời của mô
  hình chỉ hiện khi qua kiểm trích dẫn và con số, không thì trả câu trích. Đồng bộ chỉ mục đoạn là việc của
  `svc-files` (vòng nền, như F2.7). F4.3 (gợi ý giao việc) dùng lại phần truy xuất này qua route nội bộ
  `POST /internal/similar-documents`, vai trò `service` (QĐ-005). Chi tiết:
  `docs/mo-hinh-du-lieu.md` §3, README của `svc-files`.

### QĐ-005: Tác tử gợi ý giao việc: nhánh BPMN song song, kNN trên Retriever F4.2, không mô hình

- **Bối cảnh:** F4.3 — văn bản đến vừa vào sổ, lãnh đạo đơn vị mở việc "Cho ý kiến chỉ đạo" đã thấy gợi ý đơn vị chủ
  trì, hạn và căn cứ; người quyết định vẫn là lãnh đạo. Kế hoạch ban đầu: một bước máy chạy ngay trước chỉ đạo. Ràng
  buộc: dịch vụ nào chết thì văn bản vẫn phải tới lãnh đạo ngay; CI không có mô hình nào; văn bản hạn chế (F3.7) không
  bao giờ có gợi ý, không bao giờ làm căn cứ; gợi ý phải giải thích được.
- **Phương án vị trí trong quy trình:** bước tuần tự kèm timer N giây trước `chiDao` — lúc báo lãnh đạo chưa có việc
  người nào, văn bản nào cũng chậm thêm độ trễ bắt timer của Flowable, timer nhắc hạn tính muộn hơn. Tuần tự, worker tự
  giới hạn giờ — `svc-workflow` chết là văn bản kẹt hẳn. Chạy nền trong `registerIncoming` — không nằm trong BPMN, mất
  việc khi dịch vụ khởi động lại.
- **Phương án ai làm gì:** `svc-files` làm worker — thêm bí mật và đường mạng tới Flowable, chép quy tắc "phòng chủ trì
  phải có lãnh đạo phòng" của `svc-workflow`. `svc-workflow` gọi thẳng Meilisearch — chép lọc quyền và hậu kiểm của
  F4.2. Hasura Event Trigger — không nằm trong BPMN, thêm đường gọi vào.
- **Phương án thuật toán:** mô hình sinh (Qwen3) chọn đơn vị — 15–45 giây CPU mỗi văn bản, CI không có mô hình, không
  giải thích được. Bảng luật từ khóa → đơn vị — bảo trì bằng tay. scikit-learn — thêm gói, ít dữ liệu, huấn luyện lại
  mỗi khi thêm đơn vị.
- **Quyết định:**
  1. **Nhánh BPMN song song từ lúc vào sổ:** `vaoSo` → cổng song song `tachGoiY` tách hai nhánh — `chiDao` giữ nguyên
     (cả timer nhắc hạn), và việc giao ra ngoài `goiYGiaoViec` (external worker, topic `moc-goi-y`) có timer ngắt
     `PT10M` dọn nhánh khi không ai nhận việc. Hai nhánh không nối lại, không có terminate end event: nhánh gợi ý lỗi
     hay quá giờ không chặn chỉ đạo giây nào.
  2. **Ai gọi ai:** worker `svc_workflow/advisor.py` gọi `POST /internal/similar-documents` của `svc-files` bằng token
     dịch vụ sẵn có. `svc-files` chỉ truy xuất — dùng lại `Retriever` của F4.2 với phạm vi vai trò `service`, hậu kiểm,
     loại văn bản hạn chế, chỉ trả id và điểm. `svc-workflow` đọc lịch sử giao việc, bỏ phiếu, chỉ giữ đơn vị có lãnh
     đạo phòng đang hoạt động (đúng điều kiện chỉ đạo đòi), rồi lưu gợi ý và dòng sổ trong một giao dịch bằng vai trò
     Hasura `agent`, danh tính `moc-assigner`.
  3. **kNN có trọng số, không cần mô hình:** lấy tối đa 15 văn bản đến tương tự đã giao (câu tìm chỉ từ trích yếu), giữ
     văn bản có điểm từ ngưỡng trở lên, 5 văn bản đầu làm căn cứ; mỗi căn cứ bỏ phiếu cho đơn vị chủ trì gốc của nó với
     trọng số là điểm; độ tin cậy theo số căn cứ ủng hộ và tỉ phần phiếu; hạn đề xuất là trung vị số ngày xử lý của các
     căn cứ ủng hộ (văn bản đã ghi hạn thì không gợi ý hạn).
- **Hệ quả:** tắt `svc-files` thì văn bản vẫn tới lãnh đạo ngay, chỉ có dòng `failed`; CI chạy đủ bằng tìm theo từ khóa
  và bỏ phiếu. Gợi ý giải thích được ("vì 3 văn bản tương tự đã giao Tổ Đào tạo") và tốt dần khi có thêm văn bản đã
  giao; ít dữ liệu, ít đơn vị hợp lệ thì độ chính xác đo được dễ cao ảo — số đo luôn báo kèm số văn bản, số đơn vị.
  Chưa xét ngày lễ khi tính hạn; chỉ gợi ý đơn vị chủ trì, chưa gợi ý người xử lý (bước phân công). Mỗi văn bản đến
  thêm một dòng tác tử ở Sổ kiểm toán và tab Lịch sử — dòng sổ không mang trích yếu, không mang căn cứ. Chi tiết:
  `docs/mo-hinh-du-lieu.md` §1, §3, §4.2, README của `svc-workflow`.

### QĐ-006: Che PII: tự viết, che ở lối ra mô hình và ở bộ lọc nhật ký, bỏ chuỗi truy vấn ở nhật ký truy cập, không che sổ kiểm toán

- **Bối cảnh:** F4.4 — văn bản đến (đơn của người dân, hồ sơ sinh viên) chứa số định danh, số điện thoại, email, số
  tài khoản. Chữ văn bản đi ra mô hình ở năm đường (trích yếu F4.1; nhúng câu hỏi, nhúng đoạn, viết câu trả lời F4.2;
  nhúng trích yếu F4.3), còn nhật ký ghi lại câu tìm qua chuỗi truy vấn (`/api/search?q=…` ở uvicorn, APISIX, nginx của
  giao diện), tên tệp bị chặn, thông điệp lỗi. Ràng buộc: người có quyền đọc văn bản vẫn phải tìm được theo số và thấy
  số thật; trích dẫn F4.2 (`[n]`, trang) không được lệch; CI không có mô hình; máy 8 GB. Đề thi nêu "rà soát & che
  giấu PII" ở cụm ②; Luật Bảo vệ dữ liệu cá nhân 91/2025/QH15 có hiệu lực từ 01/01/2026.
- **Phương án bộ nhận dạng:** Presidio (kế hoạch ban đầu) — kéo spaCy, numpy, phonenumbers, pydantic…, bộ máy NLP
  cần thêm mô hình ngôn ngữ (spaCy không có pipeline tiếng Việt chính thức) mà bộ nhận dạng dựng sẵn không có định
  dạng Việt Nam, nên vẫn phải tự viết regex. phonenumbers — metadata lớn phải ghim và cập nhật, không biết CCCD hay số
  tài khoản. Luật lỏng "0 + 9–11 chữ số" — che cả đuôi UUID, mã số thuế, số hiệu dài (các chuỗi âm tính trong
  `test_pii.py`); luật theo cấu trúc che nhầm 0 chỗ trên kho mẫu: 81 023 ký tự, 747 chuỗi số ứng viên, đo lại bằng
  `make do-che-pii`.
- **Phương án chỗ che cho mô hình:** che trong chỉ mục — mất tìm theo số, phải nhúng lại toàn bộ, câu trích không còn
  khớp văn bản gốc. Che sau khi cắt cửa sổ ngữ cảnh — lọt mẩu số bị cắt đôi ("…liên hệ 0912 345"). Điền số thật trở
  lại vào câu trả lời của mô hình — mô hình có thể đặt nhãn sai chỗ, gán số người này cho người khác.
- **Quyết định:**
  1. **Tự viết** `pii.py` (khoảng 500 dòng, chỉ `re` của thư viện chuẩn): nhận theo cấu trúc (mã tỉnh, thế kỷ, năm
     sinh, đầu số đã cấp, `+84`, mã vùng), CMND và số tài khoản chỉ khi có từ khóa; thời gian tuyến tính, đủ nhanh để
     chạy trong bộ lọc nhật ký. Không thêm phụ thuộc nào.
  2. **Che cho mô hình ở hai lớp:** (a) lối ra — mọi lời gọi Ollama (nhúng, chat, trích yếu) qua bộ che, bất biến
     "không byte chữ nào tới `MOC_AI_URL` mà chưa che"; lớp này idempotent (bộ che lặp tới điểm bất động), ở `chat` mà
     còn phải che thêm thì ghi cảnh báo `office.assist.pii_at_egress`. (b) chỗ dựng ngữ cảnh F4.2 — một bộ che đánh
     số `[SĐT-1]` cho mỗi lượt hỏi, cùng giá trị cùng nhãn, để phần kiểm trích dẫn đọc đúng bản mô hình đã đọc.
  3. **Che sau khi chọn câu, trước khi cắt cửa sổ:** câu tốt nhất chọn trên chữ gốc, đổi vị trí sang bản che rồi mới
     cắt; chỉ mục, câu trích nguyên văn, nguồn trả người dùng không đổi.
  4. **Nhật ký:** bộ lọc `logging.Filter` che chuỗi cuối cùng (message, traceback, stack) ở logger dịch vụ và uvicorn;
     ở nhật ký truy cập (uvicorn, APISIX, nginx) **bỏ chuỗi truy vấn và Referer** thay vì che bằng regex — chuỗi đã mã
     hóa phần trăm (`0912%20345%20678`) thì regex không thấy, họ tên thì không nhận dạng được. Che hỏng thì bỏ cả dòng.
  5. **Dùng chung bằng bản chép y hệt byte** `svc_workflow/pii.py`, test so byte — như tiền lệ hai bản `openbao.py`;
     không làm gói chung (phải đổi compose, hai Dockerfile, cài đặt, phát hành chỉ vì một tệp).
  6. **Sổ kiểm toán không che:** sổ có phân quyền và chuỗi băm, che vào sổ làm sai băm và mất giá trị chứng cứ; số chỗ
     đã che chỉ ghi ở nhật ký (khóa `masked`), không vào `diff`. Không băm hay giả danh giá trị trong nhật ký (không
     gian số điện thoại cỡ 10⁹, băm không khóa dò ngược được), không có biến tắt che.
- **Hệ quả:** CI không bật mô hình vẫn kiểm đủ bằng test đơn vị (mô hình giả ghi lại yêu cầu) và `make demo-che-pii`
  (đọc `docker compose logs`). Kho mẫu không có chỗ nào bị che, nên ngữ cảnh của bộ đo hỏi đáp y hệt trước F4.4. Mô
  hình trả `[EMAIL-1]` khi được hỏi email của cơ quan — giao diện chỉ người dùng sang câu trích nguyên văn. Sót có chủ
  đích (số dính chữ, họ tên, địa chỉ, CMND không từ khóa…), véc-tơ nhúng tính trước F4.4 còn tới khi nhúng lại, nhật ký
  Hasura, PostgreSQL, Keycloak và `error_log` của APISIX, nginx nằm ngoài phạm vi. Hai danh mục (mã tỉnh, đầu số di
  động) đổi theo thời gian, có ngày và nguồn trong mã. Chi tiết: README của `svc-files` (mục "Che thông tin cá nhân"),
  `platform/apisix/README.md`.

### QĐ-007: Ký số PDF: khóa ký trong Transit, CA nội bộ một tầng trong két, pyHanko; chỉ minh họa

> Chữ ký ở đây **chỉ để minh họa**: CA tự dựng trong két, không phải dịch vụ chứng thực chữ ký số công cộng, chữ ký
> không có giá trị pháp lý.

- **Bối cảnh:** F4.5 — bản phát hành văn bản đi đã có mã QR và SHA-256 (F2.13), cổng xác thực cho người ngoài kiểm "có
  thật, nguyên vẹn", nhưng PDF chưa mang chữ ký số nên trình đọc PDF không cho biết ai phát hành. Ràng buộc: demo phải
  chạy không có mạng ngoài; két OpenBao (F3.2) đã giữ khóa dữ liệu `moc-files` (F3.7) như một "HSM mềm"; phát hành là
  việc chính, ký số chỉ ở mức Could nên két thiếu thứ gì thì văn bản vẫn phải phát hành được; stack đang chạy có dữ liệu
  thật, không khởi tạo lại két được (khóa `moc-files` sẽ đổi).
- **Phương án giữ khóa:** `pki/issue` — két sinh khóa rồi trả cả khóa riêng, khóa nằm trong RAM và đĩa của `svc-files`.
  Một khóa chung "Hệ thống Signet" — chứng thư không cho biết đơn vị nào phát hành. USB token, ký ở trình duyệt — ngoài
  phạm vi. **Transit** — khóa riêng sinh và ở lại trong két, `svc-files` chỉ gửi băm cần ký.
- **Phương án CA:** CA gốc + CA trung gian — két chỉ có một nút, CA gốc không thể để ngoại tuyến nên tầng trung gian
  không tăng an toàn, chỉ thêm một chứng thư phải xoay. CA ngoài két (tệp khóa) — thêm một bí mật phải giữ.
- **Phương án dạng chữ ký:** PAdES B-T (có dấu thời gian tin cậy) — cần dịch vụ TSA, demo không có mạng ngoài. Ô ký hiện
  hình — PDF đã in chức vụ, tên người ký; một hộp chữ ký dễ bị hiểu nhầm là chữ ký số công cộng.
- **Quyết định:**
  1. **Khóa ký trong Transit (Q1):** mỗi đơn vị một khóa `moc-ky-so-<tenant_id>` (rsa-3072), `svc-files` tạo ở lần phát
     hành đầu. Chứng thư lấy theo chuỗi: CSR do chính Transit ký (`transit/keys/<k>/csr`) → `pki/sign/moc-van-thu`
     (`svc-files` đặt CN "<đơn vị>, <cơ quan chủ quản>"; quá 64 byte UTF-8 thì chỉ tên đơn vị) → `set-certificate` gắn
     vào đúng phiên bản khóa. pyHanko (MIT) dựng CMS/PAdES và ghi PDF; một lớp `Signer` của Signet gửi phần thuộc
     tính đã ký tới `transit/sign/<k>/sha2-256` (PKCS#1 v1.5). Policy của `svc-files` có `transit/keys/moc-ky-so-*`,
     `transit/sign/moc-ky-so-*`, `pki/sign/moc-van-thu`; không có `transit/export`, `transit/backup`.
  2. **PKI một tầng trong két (Q2):** mount `pki`, CA gốc `moc-root` kiểu `internal` (rsa-4096, 10 năm, CN "CA nội bộ
     Signet - MẪU, chỉ minh họa"); role `moc-van-thu` cấp chứng thư 1 năm, KU DigitalSignature + ContentCommitment, EKU
     Document Signing. Không CRL, không OCSP. CA và khóa ký nằm trong volume `openbao_data`, đã có trong `make backup`.
  3. **Bật PKI trong `setup()` của `platform/openbao/start.sh` (Q3, bản tối thiểu):** két mới (cài mới, CI) dựng PKI và policy
     mới lúc khởi tạo, bằng token root trước khi thu hồi nó. Dựng PKI lỗi chỉ ghi nhật ký, két vẫn lên, `svc-files` tự
     tắt ký số. **Két khởi tạo trước F4.5 không tự nâng cấp:** token khởi động không sửa được policy, nên két đó không
     ký cho tới khi quản trị nâng cấp tay (tạo lại token root bằng khóa phục hồi, khởi động lại két để `setup()` chạy
     lại) hoặc dựng lại két — `van-hanh.md` mục Két bí mật. Bản đầy đủ của hợp đồng (listener 127.0.0.1 chỉ mở
     ở lần khởi động cần nâng cấp, tự tạo token root một lần) đã cắt khỏi bản này.
  4. **Ký trong `/internal/issue`, sau khi dựng PDF, trước khi băm (Q4):** băm, `content_sha256`, sổ kiểm toán, bản liên
     thông và cổng xác thực đều theo bản đã ký; `svc-workflow` không đổi. `svc-files` tự kiểm chữ ký trước khi lưu.
  5. **PAdES B-B, chữ ký chứng nhận không cho sửa (Q5):** `ETSI.CAdES.detached`, SHA-256, `certify=True`,
     `NO_CHANGES`, ô ký ẩn; không TSA, không LTV — giờ ký là giờ tự khai, CLI và cổng xác thực nói rõ.
- **Hệ quả:** ai chiếm được `svc-files` thì ký được (như mọi HSM: gọi được là ký được), xoay được khóa ký (glob phủ
  `config`, `rotate`), xin được chứng thư cho khóa tự sinh qua `pki/sign`, nhưng không mang khóa riêng đi được, và két
  ghi sổ từng lần ký — mức tin như `moc-files` hiện nay. Văn bản hạn chế không ký (mỗi lần mở đều viết lại PDF), văn bản
  phát hành trước F4.5 không ký lại. Trình đọc PDF báo chữ ký "chưa tin cậy" cho tới khi nhập CA nội bộ — đúng như mong
  đợi. Thêm pyHanko 0.37.0 và 16 gói kéo theo (`DEPENDENCIES.md`), image `svc-files` nặng thêm khoảng 15 MB; lần phát
  hành đầu của mỗi đơn vị chậm thêm chừng nửa giây trên máy dev (két sinh khóa RSA, máy yếu lâu hơn). Chi tiết:
  `docs/mo-hinh-du-lieu.md` §1, §3, §4.3, §5, README của `svc-files`, `van-hanh.md` mục Két bí mật.
