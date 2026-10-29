# Đánh giá AI trong Signet

AI trong Signet làm ba việc có thật trong luồng văn bản: đọc văn bản đến để điền sẵn form tiếp nhận (F4.1), trả lời
câu hỏi trên kho văn bản bằng câu trích có nguồn (F4.2), gợi ý đơn vị chủ trì và hạn khi văn bản vào sổ (F4.3). Bộ che
thông tin cá nhân (F4.4) không phải tác tử nhưng đứng ở lối ra mô hình của cả ba, nên được đánh giá cùng. Với từng
phần, tài liệu này ghi: làm gì; mô hình, công cụ nào (phiên bản, giấy phép); đo trên dữ liệu nào, nhãn đúng từ đâu ra;
lệnh đo lại; số đo kèm ngày, máy và nguồn; giới hạn đã biết; cơ chế an toàn nằm ở tệp nào. Mã chức năng F4.x theo
[`dac-ta-san-pham.md`](dac-ta-san-pham.md) §4.3; lý do chọn cách làm ở QĐ-004…006 trong
[`architecture.md`](architecture.md).

Ba nguyên tắc chung:

- **AI gợi ý, người quyết định.** Không tác tử nào tự tạo văn bản, tự giao việc hay trả lời thay người: văn thư đối
  chiếu rồi tự lưu form, lãnh đạo tự bấm giao, câu trả lời của mô hình luôn đi kèm câu trích nguyên văn và nguồn.
- **Chạy tại chỗ, không có mô hình vẫn chạy.** Mô hình chạy trong Ollama trên máy của tổ chức, mạng nội bộ không ra
  Internet. Không bật profile `ai` (mặc định, cả CI) thì cả bốn phần vẫn chạy bằng quy tắc, OCR và tìm kiếm toàn văn;
  cột "không bật `ai`" trong các bảng dưới đây là đường đó.
- **Số đo là cổng CI.** Mỗi lệnh `make do-…` thoát 1 khi dưới ngưỡng hoặc khi có rò rỉ (nguồn bị cấm, căn cứ là văn
  bản hạn chế, che nhầm). `do-doc-van-ban`, `do-hoi-dap`, `do-giao-viec` là bước của CI job `chay-thu`, phần `ai`
  (`.github/workflows/ci.yml`; phần này mang tên nhóm tác tử AI, CI không bật profile `ai`); `do-che-pii` chạy trong
  `make test`.

## Tóm tắt

| Mã | Tác tử (danh tính) · mã nguồn | Mô hình, công cụ | Không bật `ai` | Đo lại | Kết quả chính |
|---|---|---|---|---|---|
| F4.1 | `moc-doc-reader` · `services/svc-files/src/svc_files/docread/` | Quy tắc thể thức NĐ 30, pypdf, Tesseract `vie`; Qwen3-1.7B chỉ viết trích yếu | Đủ sáu ô, trích yếu theo quy tắc | `make do-doc-van-ban` | 22 văn bản mẫu: số ký hiệu đúng 20/22, ngày ban hành 22/22, 0 ô "chắc chắn" sai (22/10/2026; trùng ở 3 lần chạy CI ngày 26/10/2026) |
| F4.2 | `moc-assistant` · `services/svc-files/src/svc_files/assist/` | Meilisearch tìm lai, Qwen3-Embedding-0.6B, Qwen3-1.7B | Tìm từ khóa, trả câu trích nguyên văn | `make do-hoi-dap` | 19 câu: recall@3 16/16, từ chối đúng 3/3, 0 nguồn bị cấm; câu trả lời của mô hình qua kiểm 16/16 (23/10/2026, bản online) |
| F4.3 | `moc-assigner` · `services/svc-workflow/src/svc_workflow/advisor.py`, `suggest.py` | Bỏ phiếu kNN có trọng số trên phần truy xuất của F4.2; **không** mô hình sinh | Chạy đủ (tìm từ khóa) | `make do-giao-viec` | 29 văn bản lịch sử, bỏ một ra: top-1 29/29 (gốc so sánh 55 %), 0 căn cứ là văn bản hạn chế (22/10/2026) |
| F4.4 | Bộ lọc, không phải tác tử · `services/svc-files/src/svc_files/pii.py` | Nhận dạng theo cấu trúc bằng `re`, chỉ thư viện chuẩn Python | Luôn bật | `make do-che-pii` | 81 063 ký tự kho mẫu: 0 chỗ che nhầm; 18/18 đột biến mã bị test bắt (28/10/2026) |

**Không tính là AI ở đây:** ký số PAdES (F4.5) là mật mã khóa công khai (pyHanko, PKI nội bộ trong OpenBao), không có
mô hình nào; dự thảo "Báo cáo sự cố" khi cảm biến vượt ngưỡng (F3.10) là ngưỡng cộng mẫu văn bản cố định
(`services/svc-workflow/src/svc_workflow/ot.py`); ClamAV so chữ ký mã độc; tìm kiếm F2.7 là tìm từ khóa Meilisearch.

## Mô hình và công cụ

Bảng đầy đủ — vai trò, cách nạp, digest image, mã băm bản kê trọng số, nguồn đã kiểm giấy phép — ở
[`DEPENDENCIES.md`](../DEPENDENCIES.md#trí-tuệ-nhân-tạo), mục "Trí tuệ nhân tạo". Tóm lại:

| Thành phần | Phiên bản | Giấy phép | Dùng ở |
|---|---|---|---|
| Ollama | 0.35.1 (image ghim digest) | MIT | Chạy mô hình tại chỗ, profile `ai` (F4.1, F4.2, phần nhúng của F4.3) |
| Qwen3-1.7B | `qwen3:1.7b`, Q4_K_M, bản kê `8f68893c685c…` | Apache-2.0 | Viết trích yếu (F4.1), viết câu trả lời (F4.2) |
| Qwen3-Embedding-0.6B | `qwen3-embedding:0.6b`, Q8_0, 1024 chiều, bản kê `ac6da0dfba84…` | Apache-2.0 | Nhúng đoạn và câu hỏi (F4.2), trích yếu cần tìm văn bản tương tự (F4.3) |
| Tesseract OCR + dữ liệu `vie` | 5.5.0, `vie` 4.1.0 (tessdata_fast) | Apache-2.0 | Nhận dạng chữ bản scan, ảnh chụp (F4.1) |
| pypdf | 6.21.1 | BSD-3-Clause | Lớp chữ PDF giữ bố cục (F4.1), chữ từng trang cho chỉ mục đoạn (F4.2) |
| Meilisearch CE | v1.54.3 | MIT | Chỉ mục đoạn `chunks`, tìm lai từ khóa + véc-tơ (F4.2, F4.3) |

Mã bản kê là 12 ký tự đầu `ollama list` in ra sau `make ai-model`; bản đầy đủ ở `DEPENDENCIES.md`. Đổi mô hình bằng
`MOC_AI_MODEL`, `MOC_ASK_MODEL`, `MOC_AI_EMBED_MODEL` (vd `qwen3:4b`, `bge-m3`). Không dùng Llama, Gemma vì giấy phép
trọng số không được OSI phê duyệt. Đã cân nhắc rồi không dùng LlamaIndex, Qdrant, Presidio, PaddleOCR / VietOCR,
scikit-learn và việc để mô hình sinh chọn đơn vị chủ trì — lý do ở `DEPENDENCIES.md`, mục "Thành phần đã cân nhắc nhưng
không dùng".

## Cách đọc số đo

- **Dữ liệu hư cấu, nhãn do đội làm.** Kho mẫu không được chứa văn bản hay dữ liệu cá nhân thật, và in sạch hơn công
  văn thật, nên mọi số đo là **mức trần**. Số trên văn bản thật lấy từ view `office.v_intake_accuracy` (F4.1) và
  `office.v_assignment_suggestion_accuracy` (F4.3) khi có đơn vị chạy thử — **chưa có**.
- **Máy đo.**
  - *Máy A* — máy dev của đội: AMD Ryzen 7 7735HS, 16 luồng (số đo trong README dịch vụ và các lần đo không cần
    Docker ngày 23/10/2026: Python 3.14.6 qua `uv`, pypdf 6.21.1).
  - *Máy B* — laptop chạy bản online của đội: Intel Core i5-12500H, 16 luồng, 15 GiB RAM; Ollama 0.35.1 giới hạn
    8 lõi và 6 GB (`MOC_AI_CPUS=8`, `MOC_AI_MEM_LIMIT`), mô hình `qwen3:1.7b` + `qwen3-embedding:0.6b`.
- **Nguồn** ghi ở từng bảng: README dịch vụ, `CHANGELOG.md`, hoặc nhật ký của lần chạy (nhật ký không nằm trong repo —
  chạy lại đúng lệnh ghi kèm là ra bảng cùng dạng).
- **Số của CI.** Ba lần chạy xanh trên `develop` ngày 26/10/2026, CI job `chay-thu`, phần `ai`, máy chạy
  `ubuntu-24.04` của GitHub (không phải máy A, B), **không bật mô hình ngôn ngữ** (không có cả mô hình nhúng): run
  40273958769 tại `034fcf0`, 40275440368 tại `1799525`, 40277791744 tại `9498628`. Số trùng nhau ở cả ba lần thì ghi
  "ổn định qua 3 lần", khác nhau thì ghi khoảng. Nhật ký CI bị xóa sau 90 ngày (khoảng 24/01/2027) nên số được chép vào
  đây; đo lại thì xem các bước `make do-…` của phần `ai` trên một lần chạy `develop` mới.
- Phân vị (p50, p95) lấy theo hạng gần nhất trên các lượt của lần đo (`percentile` trong `scripts/demo.py`).
- Đường dẫn rút gọn trong các mục dưới: `docread/…`, `assist/…`, `pii.py`, `config.py` nằm trong
  `services/svc-files/src/svc_files/`; `advisor.py`, `suggest.py` nằm trong `services/svc-workflow/src/svc_workflow/`;
  `tests/…` là thư mục test của dịch vụ tương ứng.

## F4.1 — Đọc văn bản đến

**Mục đích.** Văn thư kéo thả công văn PDF hoặc ảnh chụp vào "Tiếp nhận văn bản"; tệp quét sạch thì tác tử đọc và điền
sẵn sáu ô (số ký hiệu, ngày ban hành, cơ quan ban hành, loại, độ khẩn, trích yếu), mỗi ô có nhãn "Gợi ý" kèm độ tin
cậy. Văn thư đối chiếu bản gốc, sửa, rồi tự lưu. Chi tiết:
[README svc-files](../services/svc-files/README.md#đọc-văn-bản-đến-f41).

**Mô hình, công cụ.** pypdf đọc lớp chữ giữ bố cục; ảnh và PDF scan qua Tesseract (`-l vie --oem 1 --psm 3`). Quy tắc
tự viết theo thể thức NĐ 30 (`docread/rules.py`, `layout.py`) quyết **mọi** trường. Qwen3-1.7B chỉ viết trích
yếu, chỉ khi quy tắc không ra trích yếu tin cậy cao (`MOC_AI_SUMMARY=fallback`, mặc định).

**Dữ liệu đánh giá.** `seed/van-ban-den/`: 22 văn bản hư cấu (cơ quan có chữ "Mẫu", người ký "Nguyễn Văn A", chân trang
"Văn bản giả lập…") — 15 PDF có lớp chữ, 7 ảnh / bản scan. Nhãn đúng ở `nhan.json` do chính `scripts/van_ban_mau.py`
ghi ra từ các giá trị nó dùng để in văn bản, nên đúng theo cách dựng chứ không do người đọc lại rồi gõ. Bản scan là
cùng nội dung vẽ lại bằng Pillow rồi xoay 0,5–1,5°, làm mờ, thêm nhiễu, nén JPEG. Tám mẫu 15–22 cố ý khó hơn: ký hiệu
ba đoạn, ngày không viết theo NĐ 30, cơ quan chủ quản hai dòng, văn bản liên tịch, ảnh chụp nghiêng 3,2°, nền xám,
PDF scan 3 trang. TSV Tesseract của 7 bản scan nằm ở `services/svc-files/tests/fixtures/ocr/` để đo không cần Docker.

**Đo lại.**

```bash
make do-doc-van-ban        # trên stack đang chạy (make up && make seed): tải từng mẫu qua APISIX như văn thư, so nhãn
cd services/svc-files && uv run --no-project --with-requirements requirements-dev.txt \
    python -m pytest -q -s tests/test_docread_samples.py     # không cần Docker: quy tắc trên lớp chữ và TSV OCR
make ai-model && make up-ai && make do-doc-van-ban           # có mô hình viết trích yếu
```

`make do-doc-van-ban` thoát 1 khi trên PDF có lớp chữ: số ký hiệu, ngày ban hành, loại dưới 90 %; cơ quan ban hành,
có trích yếu dưới 80 %; có ô `high` nào sai; hoặc cả kho dưới 20 văn bản, số ký hiệu hay ngày ban hành đúng không quá
nửa. Bản scan chỉ in số đo; `make test` chốt thêm ngưỡng tuyệt đối cho 7 bản scan.

**Kết quả.** Nguồn: [README svc-files](../services/svc-files/README.md#đọc-văn-bản-đến-f41), `make do-doc-van-ban` trên
stack, 22/10/2026, máy A, không bật `ai`. Mỗi ô: đúng / sai / trống; "`high` sai" là số ô chấm "chắc chắn" mà sai.

| Trường | PDF có chữ (15) | Bản scan (7, OCR) | `high` sai |
|---|---|---|---|
| Số, ký hiệu | 15 / 0 / 0 | 5 / 2 / 0 | 0 |
| Ngày ban hành | 15 / 0 / 0 | 7 / 0 / 0 | 0 |
| Cơ quan ban hành | 12 / 3 / 0 | 5 / 2 / 0 | 0 |
| Loại văn bản | 14 / 0 / 1 | 7 / 0 / 0 | 0 |
| Độ khẩn | 15 / 0 / 0 | 6 / 0 / 1 | 0 |
| Trích yếu: có gợi ý / trùng ≥ 60 % từ với nhãn | 14 / 14 | 7 / 7 | — |

- Cả kho: số ký hiệu đúng 20/22, ngày ban hành 22/22.
- Đo lại không cần Docker ngày 23/10/2026 (máy A, `tests/test_docread_samples.py`, 3 test đạt trong 0,66 giây): mọi ô
  đúng / sai / trống trùng bảng trên. Ở đường này hai số ký hiệu đọc sai từ TSV còn mang `high`; trên bản cài, mọi
  trường đọc bằng OCR bị hạ tối đa `medium` (`docread/reader.py`), nên bảng trên có 0 ô `high` sai.
- Thời gian một lần đọc (22/10, không mô hình): PDF có chữ trung bình 0,6 giây, lâu nhất 0,7 giây; ảnh / bản scan
  trung bình 1,3 giây, lâu nhất 1,9 giây. Có mô hình (21/10, 14 mẫu đầu, `qwen3:1.7b` trên CPU, mô hình đã nạp): PDF có
  chữ kèm trích yếu của mô hình 4,1 giây, ảnh scan kèm trích yếu 6,6 giây.
- Ba lần chạy CI ngày 26/10 (mục "Cách đọc số đo"): mọi ô của bảng trên trùng ở cả ba lần và trùng lần đo 22/10, ổn
  định qua 3 lần. Thời gian trung bình một lần đọc trên máy CI: PDF có chữ 0,5–0,6 giây (svc-files tự đo 452–597 ms),
  ảnh / bản scan 1,1–1,5 giây (1 065–1 482 ms).

**Chưa đo.** Chất lượng trích yếu do mô hình viết trên cả 22 mẫu (lần đo 22/10 không bật `ai`; bảng của
`do-doc-van-ban` chưa tách trích yếu theo nguồn quy tắc / mô hình — cách đo: bật `ai`, chạy lại, đọc trường
`fields.summary.source` của từng lượt). Số trên công văn thật: view `office.v_intake_accuracy` (tỉ lệ gợi ý văn thư giữ
nguyên khi lưu). So sánh PaddleOCR / VietOCR và dữ liệu `tessdata_best`.

**Giới hạn.** OCR sai dấu, thừa ký tự (`131/ĐT1-ĐHM`, `07/CĐÐ-UBND`, "Cõ phần"); cơ quan ban hành của văn bản liên tịch
hay có tên riêng đặt cạnh dòng chủ quản dễ sai; tên loại ngoài danh mục ("KẾ HOẠCH LIÊN TỊCH") thì không có loại, không
có trích yếu theo quy tắc. Bản scan (PDF không có lớp chữ) vào tìm kiếm toàn văn F2.7 và đoạn hỏi đáp F4.2 chỉ bằng
chữ OCR của `MOC_TEXT_OCR_PAGES` trang đầu (mặc định 3), có thể sai chữ, sai dấu (#253).

**Cơ chế an toàn.**

- *Quy tắc trước, mô hình sau:* số, ngày, cơ quan, loại, độ khẩn chỉ do quy tắc quyết; mô hình chỉ viết trích yếu khi
  quy tắc chưa ra trích yếu `high` và còn ≥ 5 giây trong hạn (`docread/reader.py`, `config.py`). Trường đọc bằng OCR
  không bao giờ được `high` (`docread/reader.py`).
- *Văn bản hạn chế không bao giờ được đọc:* `409 restricted` trước khi đọc byte nào, trước cả gợi ý đã lưu
  (`docread/reader.py`); trigger CSDL không cho lưu gợi ý của tệp gắn văn bản hạn chế và xóa gợi ý khi văn bản bật hạn
  chế (`db/migrations/default/1792281601900_intake_suggestions/up.sql`).
- *Chỉ văn thư, chỉ tệp chính họ tải lên, chỉ tệp đã qua ClamAV* — tệp người khác trả `404` như không có
  (`docread/reader.py`).
- *Đầu vào, đầu ra của mô hình:* thân văn bản trong thẻ `<van_ban>` (thẻ trùng tên trong văn bản bị bỏ), lời dặn không
  làm theo yêu cầu trong văn bản, ép JSON Schema, nhiệt độ 0,1, hạt giống cố định; trích yếu trả về phải 10–300 ký tự,
  một dòng, không liên kết, `@`, `<`, `>`, không dãy từ 6 chữ số, không nhãn che — sai thì `model_rejected`, giữ trích
  yếu theo quy tắc (`docread/summarize.py`; test `tests/test_docread_summarize.py`).
- *Tiến trình con có giới hạn:* đọc PDF, OCR chạy trong tiến trình con `python -I` có `RLIMIT_AS`, `RLIMIT_CPU`, quá
  giờ thì bị giết (OCR giết cả nhóm, tesseract không chạy mồ côi); Pillow có trần điểm ảnh; tesseract không thấy bí mật
  của dịch vụ (`ocr.py`, `pdflayout.py` của `svc-files`).
- *Danh tính, sổ kiểm toán:* mỗi lần đọc một dòng `intake.suggested` bằng vai trò Hasura `agent`, danh tính
  `moc-doc-reader` ép từ preset; dòng sổ chỉ có siêu dữ liệu (cách đọc, số trang, tên trường tìm thấy, mô hình, thời
  gian), không chữ của văn bản; không ghi được sổ thì không trả gợi ý (`docread/store.py`, `docread/reader.py`).
- *Người quyết định:* giao diện không bao giờ ghi đè chữ văn thư đã gõ, độ tin cậy thấp chỉ hiện "Gợi ý: … [Dùng]",
  nhãn "Gợi ý (chưa chắc)", "Gợi ý của mô hình" (`apps/office/app/utils/suggest.ts`).

## F4.2 — Trợ lý hỏi đáp trên kho văn bản (RAG)

**Mục đích.** Người dùng hỏi bằng câu thường ngày ("Điều kiện xét học bổng khuyến khích học tập là gì?"), trợ lý tìm
đoạn liên quan **trong các văn bản chính người hỏi được đọc** và trả câu trích nguyên văn kèm nguồn "số ký hiệu · tr.
n"; bật `ai` thì thêm câu trả lời ngắn do mô hình viết, có trích dẫn. Chi tiết:
[README svc-files](../services/svc-files/README.md#hỏi-đáp-trên-kho-văn-bản-f42).

**Mô hình, công cụ.** Chỉ mục đoạn `chunks` trên Meilisearch (đoạn ≤ 1 200 ký tự, không vượt trang); tìm lai từ khóa +
véc-tơ khi có Qwen3-Embedding-0.6B (tỷ trọng nghĩa 0,5 — 0,2 khi câu hỏi có số ký hiệu, ngày hay cụm trong ngoặc kép;
ngưỡng điểm 0,75), chỉ từ khóa kèm lượt tìm nới khi không có. Không câu nào trong 19 câu đánh giá dưới đây có các dấu
hiệu đó, nên số đo không đổi khi thêm quy tắc này.
Chế độ `extract` tất định, không cần mô hình; chế độ `generate` dùng Qwen3-1.7B viết câu trả lời từ tối đa 4 đoạn đã
hậu kiểm. Đường ống tự viết trong `assist/` (không LlamaIndex, QĐ-004).

**Dữ liệu đánh giá.** `seed/hoi-dap/`: 6 PDF hư cấu, 14 trang — 5 văn bản thường và 1 văn bản hạn chế (53/PA-ĐHM, cụm từ
riêng "phương án XANH LAM") — cộng các văn bản mẫu của `make seed`. `cau-hoi.json` có 41 câu, mỗi câu gắn người hỏi và
loại (`loai`). 19 câu tra cứu văn bản (`van_ban`) giữ nguyên từ trước để số đo so được:

- 16 câu dương: đáp án là số ký hiệu + trang, từ khóa phải có, câu chứa câu trả lời;
- 2 câu âm: hỏi điều không có trong kho (q17), hỏi nội dung chỉ có trong văn bản hạn chế (q18);
- 1 câu bị cấm: giảng viên Bộ môn KTPM hỏi về văn bản giao Tổ Đào tạo, không được xem (q19).

22 câu theo loại của bộ định tuyến (#423), mỗi câu ghi đường phải chọn (`route`):

- 5 câu nối tiếp (`noi_tiep`): kèm câu hỏi lượt trước (`previous`); đáp án là số ký hiệu + trang, câu trả lời là một
  câu khác của cùng văn bản ("Thế còn loại Giỏi?" sau câu hỏi về học bổng loại Xuất sắc);
- 6 câu về chính trợ lý (`gioi_thieu`), 5 câu cách dùng Signet (`huong_dan`): đáp án là mục của tệp Giới thiệu trợ lý
  hay của hướng dẫn sử dụng (`{"guide": "<tệp>#<neo>"}`);
- 6 câu ngoài phạm vi (`ngoai_pham_vi`): thời tiết, giá vàng, tỷ giá, bóng đá, làm thơ (tiếng Việt, tiếng Anh).

Nhãn: `scripts/hoi_dap_mau.py` viết mỗi thông tin cần hỏi trong đúng một câu, trên đúng một trang (ngắt trang tường
minh), rồi kiểm bằng pypdf rằng câu trả lời nằm đúng trang và chỉ ở trang đó; câu hỏi và từ khóa do đội viết. Với văn
bản của `make seed`, câu chứa câu trả lời lấy nguyên văn trong `scripts/seed_documents.py`.

**Đo lại.**

```bash
make do-hoi-dap                      # không bật ai: tìm từ khóa, chế độ extract (đường của CI)
make ai-model && make up-ai          # tải mô hình một lần, bật Ollama; đợi /readyz (trong container svc-files) báo
                                     # assist.embed_pending 0 — nhúng nền xong mới không tranh CPU với lúc đo
make do-hoi-dap                      # tìm lai + câu trả lời của mô hình cho từng câu
```

Định nghĩa: **recall@3** — câu dương có nguồn khớp đáp án (cùng số ký hiệu và cùng trang) trong 3 nguồn đầu; **từ chối
đúng** — câu âm, câu bị cấm nhận `no_evidence` hoặc `passages_only`; **nguồn bị cấm** — nguồn mang số ký hiệu trong danh
sách cấm của câu, hoặc văn bản hạn chế 53/PA-ĐHM (cấm ở **mọi** câu, của mọi người hỏi); **qua kiểm** — câu trả lời
`source: model` sau khi máy chủ kiểm trích dẫn; **trích đúng nguồn** — có `[n]` trỏ tới nguồn đáp án; **đường đúng** —
bộ định tuyến chọn đúng `route` của câu, câu nối tiếp được ghép (`rewritten`), câu ngoài phạm vi nhận câu cố định
(`answer.source: fixed`). recall@3, từ chối đúng chỉ tính trên 19 câu `van_ban`; các loại khác in riêng "đường đúng ·
trả lời đúng / số câu". Thoát 1 khi có bất kỳ nguồn bị cấm nào, recall@3 dưới 80 %, một câu đi sai đường, hoặc một câu
`gioi_thieu`, `huong_dan`, `ngoai_pham_vi` trả lời sai: các đường này không qua tìm kiếm nên không cần ngưỡng. Câu nối
tiếp tìm trong kho như câu `van_ban`, recall@3 của chúng chỉ in ra, không làm đỏ.

**Kết quả.**

| | 21/10/2026 · máy A · không bật `ai` | 21/10/2026 · máy A · bật `ai` | 23/10/2026 · máy B (bản online) · bật `ai` | 26/10/2026 · CI, 3 lần · không bật `ai` |
|---|---|---|---|---|
| Nguồn | README svc-files | README svc-files | nhật ký `python3 scripts/demo.py do-hoi-dap`, 191 giây | bước `make do-hoi-dap` của 3 run ở mục "Cách đọc số đo" |
| recall@3 (câu dương) | 16 / 16 | 16 / 16 | 16 / 16 (cả 16 nguồn đúng đứng đầu) | 16 / 16 |
| Câu trích có từ khóa của đáp án | 15 / 16 | 15 / 16 | 15 / 16 | 15 / 16 |
| Từ chối đúng | 3 / 3 (2 `no_evidence`, 1 `passages_only`) | 3 / 3 (`no_evidence`) | 3 / 3 (`no_evidence`) | 3 / 3 (1 `no_evidence`, 2 `passages_only`) |
| Lượt có nguồn bị cấm | 0 | 0 | 0 | 0 |
| Lượt tìm theo nghĩa | — | — | 19 / 19 | 0 / 19 |
| `extract` p50 / p95 | 20 / 61 ms | 0,44 / 0,70 s (gồm nhúng câu hỏi) | 0,4 / 0,5 s phía người gọi; svc-files tự đo 191 / 306 ms | svc-files tự đo 16–25 / 54–66 ms |
| Câu của mô hình: qua kiểm · có từ khóa · trích đúng nguồn | — | 16 / 16 · 16 / 16 · 16 / 16 | 16 / 16 · 16 / 16 · 16 / 16 | — |
| `generate` p50 / p95 | — | 14,3 / 23,5 s | 8,9 / 21,1 s | — |

- Cột CI chỉ đo phần tìm và trích câu (`extract`, câu trả lời là câu trích nguyên văn), **không đo câu trả lời của mô
  hình**, nên không cùng điều kiện với hai cột bật `ai`. Mọi số trừ độ trễ trùng nhau ở cả ba lần, ổn định qua 3 lần.
  So với cột 21/10 không bật `ai`, tổng từ chối đúng vẫn 3 / 3 nhưng chia khác (1 `no_evidence` + 2 `passages_only`
  thay vì 2 + 1): chưa rõ nguyên nhân.

- Lần đo 23/10 chạy trên chính máy B, gọi qua địa chỉ công khai của bản online (`MOC_PUBLIC_URL`), nên thời gian phía
  người gọi gồm cả đường mạng; trước khi đo, chờ svc-files nhúng xong các đoạn tồn (`embed_pending` = 0) để việc nhúng
  nền không tranh CPU. Như lần đo 21/10, kho tìm gồm cả văn bản mẫu của `make seed`.
- Lần đo 23/10: câu q16 ("Khoa cử giảng viên nào…") có nguồn đúng nhưng câu trích thiếu từ khóa, câu của mô hình thì
  đủ; câu âm, câu bị cấm đều `no_evidence` nên không lượt nào gọi mô hình — mô hình không có cơ hội trả lời câu không
  có căn cứ.
- Trước khi máy chủ tự gán trích dẫn, cùng mô hình chỉ qua kiểm 0 / 19 (viết đúng nội dung nhưng không ghi `[n]`) —
  vì vậy trích dẫn do máy chủ gán theo bằng chứng (README svc-files).

**Chưa đo.** Chấm câu trả lời bằng người (hiện chỉ kiểm từ khóa và trích dẫn); bộ câu hỏi lớn hơn 19 câu, trên kho
thật; so `qwen3:1.7b` với `qwen3:4b` (`MOC_ASK_MODEL`); tỉ lệ mô hình làm theo lệnh chèn trong văn bản — cách đo: thêm
văn bản mẫu chứa lệnh chèn vào `scripts/hoi_dap_mau.py` cùng câu hỏi nhắm vào nó, chạy `do-hoi-dap` với `ai`. Trên dữ
liệu thật câu hỏi không được lưu; tỉ lệ `no_evidence`, `model_rejected` đếm được từ `diff` của các dòng sổ
`assistant.answered` (có `status`, `warnings`, số nguồn được trích).

**Giới hạn.** Ngưỡng và hằng số kiểm chỉnh trên kho mẫu nhỏ; kiểm theo từ không bắt được câu sai mà dùng đúng chữ của
nguồn, và có thể loại oan câu có từ đệm; tìm từ khóa không hiểu từ đồng nghĩa (bật tìm theo nghĩa thì có); Meilisearch
chỉ xét 10 từ đầu câu tìm; bản scan chỉ có chữ OCR của 3 trang đầu, OCR không ra chữ thì chỉ có đoạn "trích yếu".
Danh sách đủ ở README svc-files.

**Cơ chế an toàn.**

- *Lọc quyền trước khi truy xuất, hậu kiểm trước khi tới mô hình:* lớp 1 lọc thuê ước và phạm vi theo vai trò ngay
  trong truy vấn Meilisearch, viết đúng như `office.document_visible` (`assist/scope.py`); lớp 2 hỏi Hasura bằng
  **token người hỏi**, bỏ văn bản không được đọc hay vừa thành hạn chế (`assist/retrieve.py`). Không lớp nào dựa vào
  lời dặn mô hình.
- *Văn bản hạn chế không bao giờ vào chỉ mục:* `chunks.eligible` loại văn bản hạn chế, văn bản đến đã hủy, văn bản đi
  chưa phát hành (`assist/chunks.py`); bật hạn chế thì vòng đồng bộ xóa mọi đoạn, hậu kiểm che khoảng trễ vài giây.
- *Không có căn cứ thì không gọi mô hình:* `no_evidence`, câu trả lời y hệt dù văn bản không tồn tại hay người hỏi
  không được đọc (`assist/answer.py`).
- *Kiểm trích dẫn và con số trước khi trả:* máy chủ bỏ mọi `[n]` mô hình ghi, rồi gán cho từng câu đoạn chứa **mọi** số
  từ 2 chữ số của câu và ≥ 60 % từ mới của câu; một câu không có căn cứ là loại cả câu trả lời, người dùng vẫn có câu
  trích (`assist/grounding.py`; test `tests/test_assist_grounding.py`). Câu trích ở chế độ `extract` là nguyên văn lớp
  chữ PDF (`assist/extract.py`).
- *Chống chèn lệnh:* chữ nguồn và câu hỏi trong thẻ `<nguon>`, `<cau_hoi>`; thẻ trùng tên bị bỏ, mọi `<` `>` còn lại
  thành `‹` `›`; mô hình không có công cụ; ép JSON Schema `{du_can_cu, tra_loi}`, nhiệt độ 0,1, hạt giống cố định;
  đầu ra 10–1 200 ký tự, không `http`, `<`, `>` (`assist/grounding.py`).
- *Danh tính, sổ kiểm toán, không lưu câu hỏi:* mỗi lượt một dòng `assistant.answered` của `moc-assistant` (vai trò
  `agent`), chỉ siêu dữ liệu — không câu hỏi, câu trả lời, đoạn trích; không ghi được sổ thì không trả lời
  (`assist/answer.py`, `assist/store.py`).
- *Hạn và lượt:* hạn tổng 50 giây (dưới 60 giây của APISIX), một lượt sinh một lúc (`503 busy`), người hỏi ngắt kết nối
  thì lời gọi Ollama bị hủy.

## F4.3 — Gợi ý giao việc

**Mục đích.** Văn thư vào sổ một văn bản đến thì quy trình `van-ban-den` mở nhánh song song; tác tử tìm các văn bản đến
**đã giao** giống văn bản này và gợi ý đơn vị chủ trì, hạn xử lý kèm căn cứ ở đầu form chỉ đạo. Lãnh đạo đơn vị dùng,
sửa hay bỏ gợi ý. Chi tiết: [README svc-workflow](../services/svc-workflow/README.md) đoạn "Tác tử gợi ý giao việc",
[README svc-files](../services/svc-files/README.md#văn-bản-tương-tự-cho-tác-tử-gợi-ý-giao-việc-f43).

**Mô hình, công cụ.** **Không mô hình sinh nào chọn đơn vị** (QĐ-005): bỏ phiếu kNN có trọng số trên tối đa 5 căn cứ,
hạn là trung vị số ngày của các căn cứ ủng hộ, dời khỏi thứ Bảy, Chủ nhật và ngày lễ của `MOC_HOLIDAYS` cùng lịch
nghỉ chính thức của nguồn công khai B (#427) (`suggest.py`, thư viện chuẩn `statistics`). Văn bản tương tự lấy từ
phần truy xuất của F4.2 qua route nội bộ `POST /internal/similar-documents` (`assist/similar.py`): câu tìm từ trích yếu,
tìm từ khóa kèm lượt tìm nới; có Qwen3-Embedding thì tìm lai, tối đa 3 giây. Flowable chạy nhánh song song và timer.

**Dữ liệu đánh giá.** `seed/giao-viec/lich-su.json`, hư cấu, số ký hiệu đuôi `-GVM`: 29 văn bản lịch sử (27 giao đơn
vị, 2 giao thẳng một người), 8 ca thử có nhãn cho màn demo (trong đó một ca không liên quan, phải ra `none`), một mồi
hạn chế 05/CTSV-GVM có trích yếu gần trùng cụm học bổng nhưng giao đơn vị khác. Nhãn (đơn vị chủ trì, số ngày) do đội
viết theo cụm chủ đề; `scripts/tests/test_giao_viec.py` kiểm nhãn không mâu thuẫn với dữ liệu `make seed` và kho hỏi
đáp. Chỉ Tổ Đào tạo và Bộ môn KTPM có lãnh đạo phòng, nên chỉ có **hai đơn vị hợp lệ**.

**Đo lại.** `make do-giao-viec`: gửi id 29 văn bản lịch sử vào `python -m svc_workflow.advisor evaluate` trong container
svc-workflow; mỗi văn bản được gợi ý như vừa vào sổ, svc-files loại chính nó khỏi kết quả (bỏ một ra, leave-one-out),
rồi so với đơn vị và hạn đã giao thật; không ghi CSDL, không ghi sổ. Thoát 1 khi có căn cứ là văn bản hạn chế (kể cả
mồi) hoặc top-1 dưới 60 % (`none`, `failed` tính là sai).

**Kết quả.**

| | `CHANGELOG.md` mục [1.0.0] | Lần chạy trình tự job CI, 22/10/2026, máy A, không bật `ai` | 26/10/2026 · CI, 3 lần · không bật `ai` |
|---|---|---|---|
| top-1 | 29 / 29 | 29 / 29 | 29 / 29 |
| Gốc so sánh "luôn đoán đơn vị đông nhất" | 55 % | 55 % | 55 % |
| Độ phủ (có gợi ý) | — | 29 / 29 | 29 / 29 |
| Đúng theo độ tin cậy: cao · vừa · thấp | — | 28 / 28 · 1 / 1 · 0 / 0 | 29 / 29 · 0 / 0 · 0 / 0 |
| Sai số hạn trung bình tuyệt đối · lệch ≤ 1 ngày | 1,1 ngày · — | 1,3 ngày · 20 / 29 | 0,9 ngày · 23 / 29 |
| Một lần gợi ý (svc-files + bỏ phiếu) p50 / p95 | 71 ms / — | 73 / 83 ms | 65–72 / 73–87 ms |
| Vào sổ → có dòng gợi ý, trên dòng thật, p50 / p95 | — | 1,0 / 2,7 s (25 văn bản) | 1,0–1,3 / 2,5–3,2 s (16–18 văn bản) |
| Lượt tìm theo nghĩa | — | 0 / 29 | 0 / 29 |
| Căn cứ là văn bản hạn chế | — | 0 | 0 |

`CHANGELOG.md` không ghi ngày và máy của lần đo; cột thứ hai là nhật ký của lần chạy ngày 22/10 (không nằm trong repo).
Cột thứ ba là bước `make do-giao-viec` của 3 run ở mục "Cách đọc số đo": mọi số trừ độ trễ và số văn bản của dòng thật
trùng nhau ở cả ba lần, ổn định qua 3 lần. So với lần 22/10, sai số hạn giảm từ 1,3 xuống 0,9 ngày, lệch ≤ 1 ngày tăng
từ 20 lên 23 / 29, cả 29 gợi ý mang độ tin cậy cao: **chưa rõ nguyên nhân**. Mã bỏ phiếu (`suggest.py`, `advisor.py`)
không đổi logic từ 22/10; phần tìm của svc-files (`assist/`) và dữ liệu `make seed` có commit đổi giữa hai lần, chưa
đối từng commit.

top-2, top-3 vô nghĩa khi chỉ có hai đơn vị hợp lệ. Dữ liệu chia cụm gọn và chỉ hai đơn vị, nên top-1 cao hơn thực tế:
đọc cùng gốc so sánh 55 %.

**Chưa đo.** Với tìm theo nghĩa (bật `ai`: 0/29 lượt ở trên là tìm từ khóa); trên nhiều đơn vị hơn; trên dữ liệu thật —
view `office.v_assignment_suggestion_accuracy` (tỉ lệ lãnh đạo giữ đơn vị, giữ hạn, sai số hạn).

**Giới hạn.** Lịch nghỉ chính thức chỉ có các năm Chính phủ đã công bố (bản chụp tới hết 2027, chưa có Giỗ Tổ 2027),
năm sau đó người vận hành lấy mới hoặc thêm vào `MOC_HOLIDAYS` (#280, #427); chỉ gợi ý đơn vị và hạn, không gợi ý
người xử lý; chỉ mục
đoạn đồng bộ vài giây một lần nên văn bản vừa giao chưa làm căn cứ ngay; trích yếu quá ngắn hay chỉ có từ chung thì ít
kết quả đúng; ngưỡng `MOC_SUGGEST_MIN_SCORE` chốt trên dữ liệu mẫu.

**Cơ chế an toàn.**

- *Không chắn quy trình:* nhánh gợi ý song song với bước chỉ đạo, không nối lại; quá 10 phút thì timer `boGoiY` dọn
  nhánh (`services/svc-workflow/processes/van-ban-den.bpmn20.xml`); svc-files lỗi thì ghi `failed`, không thử lại.
- *Văn bản hạn chế không được gợi ý, không làm căn cứ:* tác tử bỏ qua (`advisor.py`), svc-files trả `409 restricted`
  trước khi tìm (`assist/similar.py`), văn bản hạn chế không có đoạn nào trong chỉ mục, hậu kiểm bằng vai trò service
  bỏ văn bản vừa bật hạn chế; trigger CSDL chặn lưu gợi ý có căn cứ hạn chế và gỡ khi văn bản bật hạn chế sau đó
  (`db/migrations/default/1792281602100_assignment_suggestions/up.sql`).
- *Route chỉ cho dịch vụ:* `/internal/similar-documents` chỉ nhận token tài khoản dịch vụ, không có route APISIX,
  không có trong OpenAPI; chỉ trả id và điểm, không trả chữ văn bản.
- *Chỉ đơn vị có lãnh đạo phòng đang bật* mới được gợi ý; không đủ căn cứ thì `none`, không đoán (`advisor.py`,
  `suggest.py`).
- *Danh tính, sổ kiểm toán:* dòng gợi ý và một dòng `assignment.suggested` của `moc-assigner` (vai trò `agent`) ghi
  trong cùng một mutation; `diff` có đúng 9 khóa vô hướng, không trích yếu, không id căn cứ (`advisor.py`).
- *Người quyết định:* "Dùng gợi ý" chỉ điền form; lãnh đạo tự bấm giao, chip "Theo gợi ý" / "Khác gợi ý".

## F4.4 — Che thông tin cá nhân

**Mục đích.** Mô hình ngôn ngữ và nhật ký không thấy số định danh / CCCD, CMND, số điện thoại, email, số tài khoản;
người có quyền đọc văn bản vẫn thấy số thật (chỉ mục, câu trích, nguồn, sổ kiểm toán giữ bản gốc). Đây là lớp bảo vệ
lối ra của F4.1–F4.3, không phải tác tử. Chi tiết:
[README svc-files](../services/svc-files/README.md#che-thông-tin-cá-nhân-f44).

**Công cụ.** `pii.py` tự viết, chỉ dùng `re`, `unicodedata`, `logging` của thư viện chuẩn (QĐ-006); nhận theo cấu trúc
(mã tỉnh, chữ số thế kỷ, năm sinh của CCCD; đầu số di động đã cấp; CMND, số tài khoản chỉ khi đứng sau từ khóa), không
theo "dãy số đủ dài". `services/svc-workflow/src/svc_workflow/pii.py` là bản chép y hệt byte, test đỏ khi hai bản lệch.

**Dữ liệu đánh giá.** Ba phần, vì kho mẫu không được có dữ liệu cá nhân thật:

- *Che nhầm* trên mọi chữ của kho mẫu, đọc như bản chạy thật (lớp chữ và bố cục PDF, TSV OCR có sẵn): 22 văn bản đến,
  6 văn bản hỏi đáp, 1 248 chuỗi nhãn, câu hỏi, lịch sử giao việc — phải 0 chỗ bị che (`tests/test_pii_corpus.py`).
- *Bắt đúng* trên bộ định dạng tổng hợp (`tests/test_pii.py`): 95 chỗ dương tính trong 84 chuỗi, 80 chuỗi âm tính khó
  (giấy tờ, ngày, tiền, UUID, mã số thuế, đầu số chưa cấp, dãy số nhỏ của bảng…), 1 144 ca đột biến dữ liệu vào —
  số theo README svc-files.
- *Đột biến mã:* 18 bản sửa hỏng có chủ đích của `pii.py`, mỗi bản phải bị ít nhất một test bắt
  (`tests/test_pii_mutation.py`).

**Đo lại.** `make do-che-pii` (không cần Docker); trên stack: `make demo-che-pii` (nhật ký `apisix`, `app-office`,
`svc-files`, `svc-workflow` không còn giá trị nào, bật `ai` thì mô hình chỉ thấy nhãn). Thoát 1 khi có chỗ che nhầm,
sót một ca dương tính hay một đột biến sống sót.

**Kết quả.** `make do-che-pii` ngày 23/10/2026, máy A (3 test đạt, cả lệnh 11,7 giây):

| Nguồn | Tệp / chuỗi | Ký tự | Chuỗi số ứng viên | Bị che |
|---|---|---|---|---|
| `seed/van-ban-den`, PDF có lớp chữ | 15 | 37 416 | 370 | **0** |
| `seed/van-ban-den`, bản scan (TSV OCR) | 7 | 6 442 | 68 | **0** |
| `seed/hoi-dap`, mọi trang | 6 | 19 997 | 144 | **0** |
| Nhãn, câu hỏi, lịch sử giao việc | 1 248 chuỗi | 17 208 | 165 | **0** |

Đột biến mã: **18/18 bị giết** trong 1,9 giây (28/10/2026) — gồm bỏ vùng bảo vệ UUID, bỏ kiểm mã tỉnh, nới đầu số di
động, bỏ cổng mã số thuế, số tài khoản không cần từ khóa, giữ chuỗi truy vấn ở nhật ký truy cập, xuống dòng không là
phân cách, che một lượt thay vì tới điểm bất động, bỏ đường số dính sau tiền tố `ĐT`/`SĐT`/`Tel`.

**Chưa đo.** Độ nhạy trên dữ liệu thật — không đo được trong repo (không được chứa dữ liệu cá nhân thật); cách đo: trên
bản cài của đơn vị, `python -m svc_files.pii count < tệp` đếm số chỗ che mà không in giá trị, đối chiếu với người đọc.

**Giới hạn.** Sót có chủ đích: số dính chữ (trừ di động 10 số sau `ĐT`, `SĐT`, `Tel`…), số viết từng cặp, số nước
ngoài, CMND và số tài khoản không có từ khóa; che dư dãy mã 3 chữ số trùng dạng CCCD hợp lệ; không nhận họ tên, địa chỉ
(cần nhận dạng thực thể); email, số máy bàn của cơ quan cũng bị che trong chữ gửi mô hình; nhật ký của Hasura,
PostgreSQL, Keycloak, Meilisearch, Ollama không qua bộ lọc. Danh sách đủ ở README svc-files.

**Cơ chế an toàn.**

- *Che ở lối ra mô hình:* mọi lời gọi Ollama — nhúng đoạn, câu hỏi, trích yếu (F4.2, F4.3), viết câu trả lời (F4.2)
  ở `assist/ai.py`; viết trích yếu (F4.1) ở `docread/summarize.py`, che **trước** khi cắt `MOC_AI_MAX_CHARS`. Lối ra
  `chat` còn phải che thêm thì cảnh báo `office.assist.pii_at_egress` — có là lỗi.
- *Ngữ cảnh F4.2 dùng nhãn đánh số theo lượt* (`[SĐT-1]`), che rồi mới cắt cửa sổ 700 ký tự nên không lọt mẩu số;
  phần kiểm trích dẫn đọc đúng bản che mô hình đã đọc (`assist/answer.py`, `assist/grounding.py`).
- *Nhật ký:* `PiiFilter` gắn vào logger dịch vụ và uvicorn của svc-files, svc-workflow, che cả traceback; che hỏng thì
  cả dòng thành `core.log.redaction_failed`. Nhật ký truy cập của uvicorn, APISIX, nginx bỏ chuỗi truy vấn.
- *Sổ kiểm toán cố ý không che:* sổ có phân quyền và chuỗi băm, che vào là sửa chứng cứ.

## Chung cho mọi tác tử

| Cơ chế | Ở đâu |
|---|---|
| Ollama chỉ nằm mạng `ai` (`internal: true`): không ra Internet, không mở cổng, chỉ svc-files tới được; Meilisearch không vào mạng này | `docker-compose.yml`, dịch vụ `ollama`, mạng `ai` |
| Tắt tính năng đám mây của Ollama (suy luận từ xa, tìm web): `OLLAMA_NO_CLOUD: "1"` | `docker-compose.yml`, dịch vụ `ollama` |
| Tải trọng số một lần qua dịch vụ riêng `ollama-pull`, mạng riêng `ai-pull`, không chung mạng với dịch vụ nào khác | `docker-compose.yml`, `make ai-model` |
| Giới hạn tài nguyên mô hình: `MOC_AI_MEM_LIMIT` (mặc định 6g), `MOC_AI_CPUS` (mặc định 4) | `docker-compose.yml` |
| Image Ollama ghim cả digest; trọng số đối chiếu mã băm bản kê | `docker-compose.yml`, `DEPENDENCIES.md` |
| Tác tử có danh tính riêng, chỉ ghi được ba loại dòng sổ; người ghi và thuê ước ép từ phiên, gửi lên bị từ chối | `db/metadata/databases/default/tables/core_audit_log.yaml` |
| Không có mô hình vẫn chạy đủ; svc-files dò Ollama mỗi 60 giây, bật / tắt profile không phải khởi động lại | `docread/summarize.py`, `assist/ai.py` |
| Mọi mô hình chỉ nhận chữ của văn bản không hạn chế, đã che thông tin cá nhân | các mục F4.1–F4.4 ở trên |
