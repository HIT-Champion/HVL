# Hỏi đáp với hội đồng

> Những câu hội đồng dễ hỏi sau phần trình diễn, kèm câu trả lời của đội cho Signet. Câu hỏi rút từ yêu cầu và bốn
> nguyên lý của đề ([`olp-2026-de-thi.md`](olp-2026-de-thi.md) §3), tiêu chí chấm 7–11
> ([`olp-2026-brief.md`](olp-2026-brief.md) §4) và bảng tự chấm [`pof-checklist.md`](pof-checklist.md).
> Mỗi câu trả lời nói trong khoảng nửa phút; dòng **Bằng chứng** là chỗ mở ngay khi hội đồng muốn xem: đường dẫn trong
> repo, lệnh `make`, bước CI (`.github/workflows/ci.yml`). Số liệu chỉ lấy từ số đo đã ghi, chưa đo thì nói chưa đo.
> Kịch bản trình diễn và phương án khi có sự cố: [`../demo-script.md`](../demo-script.md).

| # | Câu hỏi | Gắn với |
|---|---|---|
| 1 | [Open-Core nằm ở đâu, ứng dụng khác dùng lại lõi thế nào?](#1-open-core-nằm-ở-đâu-ứng-dụng-khác-dùng-lại-lõi-thế-nào) | R1–R7, tiêu chí 7 |
| 2 | [Vì sao nguồn mở, có thoát được một nhà cung cấp không?](#2-vì-sao-nguồn-mở-có-thoát-được-một-nhà-cung-cấp-không) | Bối cảnh đề, tiêu chí 10 |
| 3 | [Từ 100 lên 100.000 người dùng thì sao?](#3-từ-100-lên-100000-người-dùng-thì-sao) | Tiêu chí 8, 10 |
| 4 | [Bảo mật: đăng nhập, tệp độc, văn bản nhạy cảm, nhật ký](#4-bảo-mật-đăng-nhập-tệp-độc-văn-bản-nhạy-cảm-nhật-ký) | Nguyên lý (iv), cụm ① ⑥ |
| 5 | [AI có bịa không, dữ liệu có ra khỏi máy không?](#5-ai-có-bịa-không-dữ-liệu-có-ra-khỏi-máy-không) | Trục [I], tiêu chí 7 |
| 6 | [Hỏng máy, mất dữ liệu thì sao?](#6-hỏng-máy-mất-dữ-liệu-thì-sao) | Nguyên lý (iv), cụm ⑥ |
| 7 | [Một thành phần ngừng thì hệ thống ra sao?](#7-một-thành-phần-ngừng-thì-hệ-thống-ra-sao) | Tiêu chí 8 |
| 8 | [Không có Internet có chạy được không?](#8-không-có-internet-có-chạy-được-không) | Chủ quyền số |
| 9 | [Tốn bao nhiêu, máy tối thiểu thế nào?](#9-tốn-bao-nhiêu-máy-tối-thiểu-thế-nào) | Tiêu chí 9, 10 |
| 10 | [Giấy phép tuân thủ thế nào?](#10-giấy-phép-tuân-thủ-thế-nào) | PoF #2, #5 |
| 11 | [Người khác dựng lại từ mã nguồn được không?](#11-người-khác-dựng-lại-từ-mã-nguồn-được-không) | PoF #4, tiêu chí 10 |
| 12 | [H-P-D-I ở đâu, khác gì phần mềm quản lý văn bản sẵn có?](#12-h-p-d-i-ở-đâu-khác-gì-phần-mềm-quản-lý-văn-bản-sẵn-có) | Tiêu chí 7, 9 |
| 13 | [Còn gì chưa làm?](#13-còn-gì-chưa-làm) | Tiêu chí 8, 11 |
| 14 | [Lõi "không giao diện" mà sao có Grafana, trang quản trị Keycloak?](#14-lõi-không-giao-diện-mà-sao-có-grafana-trang-quản-trị-keycloak) | Tiêu chí 7, cụm ① ⑥ |
| 15 | [Ứng dụng thứ ba muốn có luồng duyệt riêng thì làm thế nào?](#15-ứng-dụng-thứ-ba-muốn-có-luồng-duyệt-riêng-thì-làm-thế-nào) | R1–R7, tiêu chí 7 |
| 16 | [Vì sao cài ứng dụng bằng dòng lệnh, không có nút trên giao diện?](#16-vì-sao-cài-ứng-dụng-bằng-dòng-lệnh-không-có-nút-trên-giao-diện) | Tiêu chí 9, nguyên lý (iv) |
| 17 | [Kho lạnh có thật sự tách khỏi kho nóng không?](#17-kho-lạnh-có-thật-sự-tách-khỏi-kho-nóng-không) | Nguyên lý (i), cụm ④ |
| 18 | [Sản phẩm tên Signet, sao lệnh và cấu hình vẫn là `moc`?](#18-sản-phẩm-tên-signet-sao-lệnh-và-cấu-hình-vẫn-là-moc) | PoF #3, #6 |

## 1. Open-Core nằm ở đâu, ứng dụng khác dùng lại lõi thế nào?

Tầng 1 là profile `core` của `docker-compose.yml` (Keycloak, APISIX, Hasura + PostgreSQL, Flowable, SeaweedFS,
Meilisearch, ClamAV, OpenBao, `svc-files`, `svc-workflow`), không có giao diện: chỉ APISIX mở cổng ra ngoài, đường quản
trị (`/console`, `/v1/metadata`, `/admin`…) trả 404. Ứng dụng nào cũng gọi lõi qua một cổng bằng token Keycloak —
GraphQL cho dữ liệu, REST cho tệp, tìm kiếm, WebSocket cho thông báo; riêng cổng xác thực văn bản không cần token — và
đơn vị, vai trò luôn lấy từ token. Dữ liệu dùng chung nằm ở schema `core` (đơn vị, tệp, sổ kiểm toán, thông báo); Văn
phòng điện tử có schema `office` riêng, ứng dụng mới thêm schema của nó và một client Keycloak theo mẫu `app-office`,
không sửa `core`. Có ba ứng dụng Tầng 2: Văn phòng điện tử (`app-office`, gồm cả cổng xác thực công khai `/xac-thuc`),
Không gian cá nhân P.A.R.A (`app-ca-nhan`, `/ca-nhan/`) và Bảng tin đơn vị (`/bang-tin/`). Ứng dụng thứ hai làm tay:
thêm schema `personal`, và thêm client `app-ca-nhan`, một route, một service vào chính các tệp cấu hình của lõi (realm,
`apisix.yaml`, `docker-compose.yml`); không sửa dòng nào trong `services/`, và dùng chung phiên đăng nhập, sổ kiểm toán,
quét mã độc của lõi. Ứng dụng thứ ba cắm bằng một lệnh: `moc app install apps/bang-tin/app.yaml` đọc manifest rồi tạo
client Keycloak, route APISIX, container, schema và migration chạy bằng vai trò CSDL riêng của ứng dụng (không có quyền
gì trên lõi), quyền Hasura và Event Trigger nhận sự kiện văn bản của lõi; các tệp lõi không đổi (`git diff` trống), gỡ
thì giữ dữ liệu. `smoke.py` và các màn demo thao tác như người dùng qua đúng cổng đó, bằng token của tài khoản mẫu. Ứng
dụng còn mang được quy trình duyệt của riêng nó lên động cơ quy trình của lõi (câu 15).

Chỗ lõi chưa sạch, đội nói thẳng: Văn phòng điện tử vẫn nằm trong lõi ở cả ba lớp. Mã: phần nghiệp vụ văn phòng phía máy
chủ (Actions vào sổ, phát hành, dựng PDF văn bản đi, vòng nộp lưu) chạy chung tiến trình với lõi, trong thư mục
`office/` của `svc-files` và `svc-workflow`. CSDL: 29 trên 45 bảng Hasura theo dõi thuộc schema `office` (15 `core`, 1
`personal`); 31 trên 36 migration đụng `office`, 26 trong số đó nhắc tới cả `core` lẫn `office` trong cùng một tệp, nên
muốn dựng CSDL lõi không có Văn phòng thì phải tách lại các tệp đó. Cổng: route của `svc-files` trong
`platform/apisix/apisix.yaml` mang luôn `/api/documents/*`, `/api/registers/*`, `/api/case-files/*`. Phần đã làm là bước
1–2 của `docs/architecture.md` §4.7 (#302): mã Văn phòng tách thành router riêng sau cờ `MOC_OFFICE_ENABLED`; tắt cờ thì
hai dịch vụ vẫn lên, không gắn route, Action, BPMN hay vòng nền nào của Văn phòng, phần lõi của `make smoke` và
`make demo-ca-nhan` vẫn đạt. Cờ đó cho thấy ranh giới trong mã đã có; tách CSDL, vai trò và gói riêng là bước 3–5, chưa
làm, chưa xếp ngày (#324).

**Bằng chứng:** README mục "Kiến trúc"; [`docs/api/README.md`](../api/README.md) (§1 "Muốn thêm một ứng dụng Tầng 2");
[`docs/them-ung-dung.md`](../them-ung-dung.md) (§1 `moc app install`, mẫu `apps/bang-tin`; §3–§4 làm tay, mẫu
`apps/ca-nhan`), `make demo-cai-ung-dung`, `make demo-ca-nhan`, `make demo-quy-trinh` (ứng dụng mang quy trình riêng,
`apps/nghi-phep`), `make demo-tat-van-phong`; [`docs/architecture.md`](../architecture.md) §4.7 (tiêu chí xong 4 đạt ở
#302); [`docs/mo-hinh-du-lieu.md`](../mo-hinh-du-lieu.md) §0; `db/metadata/databases/default/tables/` (tệp `core_*`,
`office_*`), `db/migrations/default/`; `platform/apisix/apisix.yaml` (route của `svc-files`); `make smoke` (chặn đường
quản trị); CI job `chay-thu`, phần `luong-chinh`, bước "Tài liệu API trong docs/api/ khớp mã (make api-docs)" và bước
"Tắt Văn phòng điện tử, lõi vẫn chạy (make demo-tat-van-phong)".

## 2. Vì sao nguồn mở, có thoát được một nhà cung cấp không?

Đề đặt bài toán tổ chức thành "con tin" của một nhà cung cấp; Signet trả lời bằng ba điều kiểm được. Mã của đội theo
Apache-2.0, phần mềm thượng nguồn chạy trong sản phẩm đều mang giấy phép OSI, dùng image chính thức ghim phiên bản và
digest, không sửa mã thượng nguồn — ai cũng dựng lại được toàn bộ. Dữ liệu và giao tiếp theo chuẩn mở: PostgreSQL, API
S3 (SeaweedFS), OpenID Connect (Keycloak), BPMN 2.0 (Flowable), gói nộp lưu Parquet kèm manifest băm, NGSI-LD,
OpenLineage, PDF ký PAdES; gói lưu trữ đọc được bằng công cụ bất kỳ, không cần Signet. Không có dịch vụ trả phí bắt
buộc: mô hình AI chạy tại chỗ, Cloudflare Tunnel chỉ là một cách đưa lên Internet (profile `tunnel`, tắt mặc định; máy
có IP công khai dùng Caddy). Thành phần nào trong bảng tham chiếu của BTC không đạt OSI hoặc đã ngừng phát triển thì
không dùng, chỗ cần thì thay: Vault → OpenBao, MinIO → SeaweedFS, immudb → chuỗi băm trong PostgreSQL, Orion (kéo
MongoDB) → Scorpio.

**Bằng chứng:** `LICENSE`, `NOTICE`; `DEPENDENCIES.md` mục "Thành phần đã cân nhắc nhưng không dùng";
[`olp-2026-de-thi.md`](olp-2026-de-thi.md) §5; `docs/architecture.md` QĐ-001; `make demo-nong-lanh` (DuckDB đọc gói
Parquet); [`docs/trien-khai.md`](../trien-khai.md) §5, §5b.

## 3. Từ 100 lên 100.000 người dùng thì sao?

Chưa đo tải. Bản hiện tại nhắm một trường, khoa hay SME trên một máy: Docker Compose, không tự mở rộng, không chịu lỗi
nhiều nút (QĐ-003). Bước đầu là tách theo đơn vị: một bản cài đã phục vụ nhiều đơn vị (`moc tenant create`), và
100.000 người thường là nhiều trường, sở, nên chia thành nhiều bản cài trước khi phải dựng cụm. Trong một bản cài,
giao diện là trang tĩnh, Hasura và APISIX không giữ dữ liệu nghiệp vụ nên về nguyên tắc nhân bản được sau bộ cân bằng
tải (chưa thử); riêng giới hạn tốc độ của APISIX đếm tại chỗ (`policy: local`), nhiều bản cổng phải dùng bộ đếm chung.
Nút thắt đã biết: sổ kiểm toán là một chuỗi băm duy nhất, mọi giao dịch ghi sổ xếp hàng trên dòng `core.audit_head`
(phải chia chuỗi theo đơn vị); PostgreSQL là điểm lỗi đơn (QĐ-002); vòng nền của `svc-files`, `svc-workflow` (nộp
lưu, neo sổ, nhắc hạn, nhúng) chưa thử chạy nhiều bản song song.

**Bằng chứng:** `docs/architecture.md` QĐ-002, QĐ-003; `db/migrations/default/1792281600100_core_schema/up.sql` (khóa
`core.audit_head`); `platform/apisix/apisix.yaml` (`limit-count`); [`docs/van-hanh.md`](../van-hanh.md) mục "Thêm đơn
vị"; CI job `chay-thu`, phần `luong-chinh`, bước "Thêm đơn vị bằng một lệnh (moc tenant create, check)".

## 4. Bảo mật: đăng nhập, tệp độc, văn bản nhạy cảm, nhật ký

Đăng nhập một lần qua Keycloak; văn thư, lãnh đạo, tổ trưởng, quản trị đơn vị bắt buộc mã TOTP, cả ở đường lấy token cho
script. Keycloak chặn dò mật khẩu, APISIX giới hạn lượt đăng nhập theo IP và kiểm JWT ngay ở biên, dịch vụ phía sau kiểm
lại token. Trước cả bước kiểm token, mọi yêu cầu qua tường lửa ứng dụng web Coraza + OWASP CRS 4.14 (paranoia 1) chạy
trong APISIX: SQLi, XSS, đọc tệp hệ thống, tải lên tệp `.php` nhận 403 kèm mã yêu cầu để tra nhật ký; mỗi loại trừ cho
dữ liệu thật có lý do và test riêng. Mọi tệp qua ClamAV trước khi ghi vào kho: `svc-files` quét ngay khi nhận, tức là
sau cổng APISIX, vì WAF ở cổng không soi được nội dung tệp trong multipart; ClamAV không trả lời thì từ chối (`503`) chứ
không cho qua. Tệp nhiễm bị từ chối và không được lưu ở đâu, không có kho cách ly: sổ kiểm toán ghi lần chặn (người tải,
cỡ tệp, SHA-256, tên mẫu ClamAV). Văn bản hạn chế: mỗi tệp một khóa AES-256 bọc trong két OpenBao, kho và bản sao lưu
chỉ có bản mã, bản rõ chỉ ở trong bộ nhớ cho người có tên và mang tên người xem; hai dịch vụ của đội (`svc-files`,
`svc-workflow`) lấy bí mật từ két bằng AppRole, không qua biến môi trường. Mọi thay đổi vào sổ kiểm toán chuỗi băm
SHA-256, đầu chuỗi neo định kỳ (mặc định 10 phút) ra bucket khóa ghi: `make audit` tính lại cả chuỗi ngoài CSDL và chỉ
ra dòng bị sửa, kể cả khi người sửa tắt trigger hay viết lại cả chuỗi. Giới hạn đã ghi: phần mềm thượng nguồn
(PostgreSQL, Keycloak, Flowable, Hasura, SeaweedFS, Meilisearch, Centrifugo; Parseable, Scorpio, restic khi bật profile)
vẫn nhận bí mật qua biến môi trường, và `.env` vẫn là nguồn của mọi bí mật, kể cả khóa mở két (static seal, để két tự mở
khi khởi động lại); các container gọi nhau bằng HTTP trong mạng nội bộ, Hasura nối CSDL bằng siêu người dùng; chưa có
bản WebAssembly nào mang Coraza đã vá 12 lỗ hổng công bố 02/10/2026 — hai lỗ mức high có biện pháp ở cổng, các cách lẩn
WAF mức medium thì dịch vụ vẫn tự kiểm đầu vào.

**Bằng chứng:** `platform/keycloak/README.md`; `platform/apisix/README.md` mục WAF (luật, loại trừ, lỗ hổng của Coraza
3.3.3; ClamAV soi nội dung tệp); `make smoke` khối "Tường lửa ứng dụng web"; `make demo-kiem-dich`, `make demo-han-che`,
`make demo-ket-bi-mat`, `make audit`; [`docs/muc-hoan-thien.md`](../muc-hoan-thien.md) F3.2 (giới hạn của két);
`db/README.md` (test sổ kiểm toán, gồm các kiểu sửa lén); [`docs/trien-khai.md`](../trien-khai.md) §8; CI job
`chay-thu`: phần `luong-chinh` (`make smoke`, bước `make demo-han-che`, `make demo-ket-bi-mat`), phần `e2e`
(`kiem-dich.spec.ts`), phần `sao-luu` (`make audit` sau khi khôi phục); job `security` (gitleaks, OSV-Scanner).

## 5. AI có bịa không, dữ liệu có ra khỏi máy không?

Mô hình (Qwen3 1,7B và Qwen3-Embedding 0,6B, trọng số Apache-2.0) chạy bằng Ollama trên chính máy chủ, trong mạng Docker
`ai` không ra Internet, đã tắt tính năng đám mây; chữ gửi mô hình đã che số định danh, điện thoại, email, số tài khoản.
Trợ lý chỉ tìm trong văn bản người hỏi được xem: lọc ngay trong chỉ mục theo quy tắc quyền, rồi hậu kiểm từng văn bản
bằng Hasura với token người hỏi trước khi đoạn nào tới mô hình; văn bản hạn chế không bao giờ vào chỉ mục. Đường mặc
định không cần mô hình: câu trích nguyên văn kèm "số ký hiệu · tr. n"; khi mô hình viết, `svc-files` tự gắn [n] cho từng
câu theo đoạn nguồn, câu không có căn cứ thì người dùng chỉ thấy câu trích. Đo trên bản online ngày 23/10/2026 (laptop
i5-12500H, Ollama 0.35.1 dùng 8 lõi CPU, `python3 scripts/demo.py do-hoi-dap`, 19 câu): recall@3 16/16, từ chối đúng
3/3, 0 nguồn bị cấm, tìm p50 0,4 s / p95 0,5 s; câu của mô hình trích đúng nguồn 16/16, viết p50 8,9 s / p95 21,1 s. Kho
mẫu nhỏ, câu hỏi do đội viết: đây là mức trần, chưa phải số trên văn bản thật. CI không bật profile `ai`: phần `ai` của
CI chạy đường không mô hình (tìm theo từ khóa, trả lời bằng câu trích) và giữ phần quyền — câu về quyền hay văn bản hạn
chế mà ra nguồn bị cấm thì CI đỏ. Đường có mô hình (Ollama, Qwen3) chỉ được kiểm bằng test đơn vị với mô hình giả và lần
đo tay ở trên; chưa có bước CI nào gọi mô hình thật.

**Bằng chứng:** `make demo-hoi-dap`, `make do-hoi-dap` (thoát 1 khi có nguồn bị cấm), `make demo-che-pii`,
`make do-che-pii`; `services/svc-files/README.md` (bảng số đo); [`docs/danh-gia-ai.md`](../danh-gia-ai.md) (CI không bật
profile `ai`); `services/svc-files/tests/assist_fakes.py` (mô hình giả); `docs/architecture.md` QĐ-004, QĐ-006;
`docker-compose.yml` (dịch vụ `ollama`, mạng `ai`); CI job `chay-thu`, phần `ai`, bước "Đo chất lượng hỏi đáp (make
do-hoi-dap)", không có mô hình.

## 6. Hỏng máy, mất dữ liệu thì sao?

`make backup` sao lưu mọi CSDL (nghiệp vụ, Keycloak, Flowable), toàn bộ tệp và két OpenBao vào kho restic mã hóa; để
CSDL và tệp cùng một thời điểm, Signet tạm dừng ghi vài giây. `make restore` kiểm bản sao đọc được trọn vẹn rồi mới thay
dữ liệu, ghi lần khôi phục vào sổ kiểm toán; `make audit` sau đó vẫn khớp mốc neo. CI diễn tập đúng chuỗi sao lưu → xóa
dữ liệu → khôi phục → smoke ở mọi pull request. Tự phục hồi: reconciler (systemd timer mỗi 60 giây) dựng lại container
bị xóa, chạy lại container đã dừng hay unhealthy, và khi bật GitOps thì đưa cấu hình bị sửa tay về đúng commit; két tự
mở khóa nên khởi động lại không cần người. Giới hạn: một máy, nên mất phần dữ liệu từ lần sao lưu gần nhất; kho sao lưu
phải chép ra máy khác, `.env` (khóa kho, khóa két) cất riêng; chưa đo thời gian khôi phục trên dữ liệu lớn.

**Bằng chứng:** [`docs/van-hanh.md`](../van-hanh.md) mục "Sao lưu và khôi phục", "GitOps và tự phục hồi";
[`docs/trien-khai.md`](../trien-khai.md) §7 (sao lưu hằng đêm); `make demo-tu-phuc-hoi`; CI job `chay-thu`, phần
`sao-luu`, bước "Sao lưu, xóa dữ liệu, khôi phục rồi kiểm lại (make backup, make restore)" và phần `cai-dat`, bước
"GitOps — reconciler áp commit mới, sửa lệch cấu hình (scripts/reconcile.py)".

## 7. Một thành phần ngừng thì hệ thống ra sao?

Mỗi phụ thuộc có cách lùi riêng, chọn theo hướng an toàn. Ollama tắt hay quá giờ: trích yếu theo quy tắc, trợ lý về tìm
theo từ khóa và trả câu trích, `svc-files` dò lại mô hình mỗi 60 giây. `svc-files` ngừng đúng lúc văn bản vào sổ: lãnh
đạo vẫn có việc chỉ đạo, chỉ mất gợi ý giao việc. ClamAV ngừng: tải tệp bị từ chối, vì thà chặn còn hơn lưu tệp chưa
quét; Meilisearch ngừng: trợ lý báo `503 search_unavailable` chứ không trả lời mò. Liên thông giữa hai đơn vị ghi outbox
trong cùng giao dịch phát hành, vòng nền gửi lại giãn dần từ 30 giây tới 1 giờ; container chết hẳn thì reconciler dựng
lại trong vòng một phút. Ai cũng xem được thành phần nào đang chạy, chậm hay ngừng ở trang công khai `/trang-thai` —
không cần đăng nhập, không lộ địa chỉ hay lỗi nội bộ.

**Bằng chứng:** [`docs/demo-script.md`](../demo-script.md) (các mục "Nếu giám khảo hỏi"); `make demo-giao-viec` (bước
10: dừng `svc-files` giữa chừng); `make demo-tu-phuc-hoi`; `services/svc-files/README.md` (mã lỗi `503` của trợ lý);
[`docs/van-hanh.md`](../van-hanh.md) (trang trạng thái, `GET /api/status`).

## 8. Không có Internet có chạy được không?

Sau lần cài đầu (tải image, chữ ký ClamAV, `make ai-model`), đăng nhập, TOTP, quy trình, tìm kiếm, OCR và mô hình AI đều
chạy tại chỗ; giao diện không tải phông hay script từ CDN; ký số không gọi dịch vụ dấu thời gian bên ngoài. Kho tệp, két
và mô hình nằm trong mạng Docker `internal`, không ra Internet. Cần Internet: tải chữ ký ClamAV mới (image đã kèm sẵn
một bộ, bộ tải về giữ trong volume `clamav_data`), kéo commit mới cho GitOps, và cho người ngoài truy cập (Cloudflare
Tunnel hay Caddy). Trong thư mục cài, image của đội đã dựng sẵn (`pull_policy: never`), khởi động lại không phải dựng.
Chưa diễn tập chạy hẳn không mạng trong CI; checklist trình diễn có bước tắt mạng rồi chạy smoke trên máy dự phòng.

**Bằng chứng:** `docker-compose.yml` (mạng `storage`, `secrets`, `ai`; `OLLAMA_NO_CLOUD`); `scripts/install.sh`
(`pull_policy: never`); `DEPENDENCIES.md` (dòng "Dịch vụ dấu thời gian TSA"); [`docs/demo-script.md`](../demo-script.md)
mục "Checklist trước giờ trình diễn".

## 9. Tốn bao nhiêu, máy tối thiểu thế nào?

Không có tiền giấy phép: mọi thành phần là phần mềm nguồn mở, GitHub và Cloudflare gói Free đủ dùng; chi phí là máy và
điện. Hệ thống mặc định (19 dịch vụ, 18 chạy liên tục) dùng khoảng 3,2–3,5 GB RAM khi chạy, chưa bật mô hình — số đo từ
trước khi thêm `app-ca-nhan`, `app-tai-lieu-api`, hai trang tĩnh nhỏ; máy chủ đề xuất 4 vCPU, 8 GB RAM, 40 GB đĩa, nhưng
chưa đo thật trên máy 8 GB. Bật mô hình AI cần máy 16 GB (Ollama giới hạn mặc định 6 GB RAM, 4 lõi; đặt lại bằng
`MOC_AI_MEM_LIMIT`, `MOC_AI_CPUS`). Bản online <https://signet.htechcs.com> chạy trên một laptop của đội (i5-12500H) qua
Cloudflare Tunnel, không cần IP công khai.

**Bằng chứng:** README mục "Yêu cầu hệ thống"; [`docs/trien-khai.md`](../trien-khai.md) §1, §5b, §8;
`docker-compose.yml` (dịch vụ `ollama`); `docs/architecture.md` §1.3.

## 10. Giấy phép tuân thủ thế nào?

Mã của đội theo Apache-2.0: toàn văn ở `LICENSE`, mục đích giấy phép ở `NOTICE`, header SPDX trong từng tệp mã; tệp
không chèn được header (JSON, ảnh, PDF, tài liệu) khai trong `REUSE.toml`. `DEPENDENCIES.md` ghi từng thành phần thượng
nguồn với phiên bản ghim, giấy phép, cách nạp và mục kiểm tương thích (kể cả năm gói npm mang giấy phép ngoại lệ, chỉ
dùng lúc dựng hay lúc phát triển, không nằm trong trang phát hành); GPL, AGPL (ClamAV, PostGIS, Grafana) chỉ chạy như
dịch vụ độc lập qua mạng, không liên kết mã. Trọng số mô hình kiểm riêng trên model card của đúng cỡ đã chọn (Qwen3:
Apache-2.0); Llama, Gemma bị loại vì giấy phép trọng số không thuộc danh sách OSI. Repo không kèm mã của dự án khác,
image dùng nguyên bản; CI kiểm các điều này ở mọi pull request.

**Bằng chứng:** `make license-check`; `uvx --from reuse==5.0.2 reuse lint`; `DEPENDENCIES.md`; CI job `license`
("Giấy phép (PoF #2)": "Header giấy phép trong từng tệp mã", "Không bundle mã nguồn dự án khác");
[`pof-checklist.md`](pof-checklist.md) tiêu chí 2, 5.

## 11. Người khác dựng lại từ mã nguồn được không?

`git clone` → `make env` (sinh `.env`, mật khẩu ngẫu nhiên; không sửa tệp mã nào) → `make up` → `make seed`; chỉ cần
Docker, Make và Python 3.10 thư viện chuẩn, đều là phần mềm nguồn mở. CI làm đúng chuỗi đó trên máy sạch ở mọi pull
request, rồi smoke, e2e trên trình duyệt thật và 12 màn demo. `make install PREFIX=…` cài ra ngoài thư mục mã nguồn,
CI smoke lại từ bản cài. Bản phát hành là gói `.tar.gz` kèm `.sha256` (`make release`). Chưa có người ngoài đội tự cài
từ README trên máy sạch: việc này còn trong kế hoạch.

**Bằng chứng:** README mục "Cài đặt từ mã nguồn"; CI job `build` ("Dựng từ mã nguồn (PoF #4)"), job `chay-thu`, phần
`cai-dat`, bước "Cài ra ngoài thư mục mã nguồn và chạy từ đó (make install)"; [`pof-checklist.md`](pof-checklist.md)
tiêu chí 3, 4; [`ke-hoach-phat-trien.md`](ke-hoach-phat-trien.md) §4.1.

## 12. H-P-D-I ở đâu, khác gì phần mềm quản lý văn bản sẵn có?

Một công văn đi trọn [H] → [P] → [D] → [I]: danh tính SSO, đơn vị và phòng trong token ([H]); luồng BPMN vào sổ, chỉ
đạo, xử lý, phát hành, chặn nhập sai ở form, máy chủ và CSDL theo một JSON Schema ([P]); dashboard điều hành, sổ đăng
ký, nộp lưu sang kho lạnh có phả hệ, rồi đếm lại văn bản đã nộp lưu theo năm, loại, phòng ngay trên các gói Parquet
bằng DuckDB ở trang Điều hành ([D]); tác tử đọc văn bản đến, hỏi đáp, gợi ý giao việc dùng chính dữ liệu đó
([I]). Đội không đua tính năng với sản phẩm thương mại: khác ở chỗ tổ chức tự cài, tự giữ dữ liệu, mã nguồn mở; người
nhận ngoài hệ thống tự kiểm văn bản bằng mã QR, SHA-256 ở cổng xác thực công khai; lớp tin cậy (danh tính, kiểm dịch,
sổ kiểm toán, kiểm chứng từ bên ngoài) nằm ở lõi để ứng dụng khác dùng lại. AI chỉ gợi ý, người quyết định: câu trả
lời kèm nguồn, gợi ý giao việc kèm căn cứ, mỗi lượt tác tử làm việc để lại một dòng sổ kiểm toán mang danh tính riêng
của nó (loại `agent`).

**Bằng chứng:** README mục "Bài toán", "Tính năng", "Bằng chứng 4 nguyên lý";
[`docs/dac-ta-san-pham.md`](../dac-ta-san-pham.md) §5, §9; `make demo-doc-van-ban`, `make demo-giao-viec`,
`make demo-nong-lanh`.

## 13. Còn gì chưa làm?

Chưa có trục streaming sự kiện (Kafka…): sự kiện nằm trong PostgreSQL (dòng thời gian văn bản, outbox liên thông), đủ
cho một máy. Ứng dụng cắm bằng `moc app install` nhận ba loại sự kiện văn bản qua Hasura Event Trigger (luồng
`core.app_events`): gửi lại khi lỗi, nhưng không đọc lại từ một vị trí, không bảo đảm thứ tự. Chưa có thực thi kịch
bản serverless (cụm ⑤). Low-code mới ở mức khai báo: ứng dụng cắm thêm khai form bằng JSON Schema và trang dựng form từ
chính tệp đó, không viết mã giao diện (`apps/nghi-phep/public/schema-form.js`), khai quy trình bằng BPMN XML; form
của Văn phòng điện tử vẫn viết trong mã (#303), chưa có trình thiết kế quy trình hay form trên giao diện (bpmn-js bị
loại vì giấy phép). Quy trình của ứng dụng cắm thêm mới là quy trình duyệt: chưa có timer, bước tự động, gọi API ra
ngoài; form chưa có tệp đính kèm (#325). Thông báo gửi trong ứng dụng qua
WebSocket (Centrifugo) và, khi cấu hình, qua email, webhook chat, SMS, Zalo; SMS, Zalo do từng người tự bật, email
chưa cho từng người tắt, SMS và Zalo chưa thử với tài khoản thật.
Một máy, không chịu lỗi nhiều nút, chưa đo tải; bản online chạy trên laptop qua Cloudflare Tunnel, chưa lên VPS thật.
Ký số chỉ minh họa bằng CA nội bộ, chưa liên thông Trục văn bản quốc gia, không dùng cho văn bản mật; số đo AI trên
kho văn bản giả lập, chưa có đơn vị dùng thật.

**Bằng chứng:** [`ke-hoach-phat-trien.md`](ke-hoach-phat-trien.md) §6 "Không làm — và lý do";
[`docs/dac-ta-san-pham.md`](../dac-ta-san-pham.md) §4.4; [`docs/trien-khai.md`](../trien-khai.md) §8; các mục "Còn gì
chưa làm?" trong [`docs/demo-script.md`](../demo-script.md).

## 14. Lõi "không giao diện" mà sao có Grafana, trang quản trị Keycloak?

"Không giao diện" nghĩa là lõi không có màn hình nghiệp vụ: mọi màn hình người dùng thấy thuộc tầng ứng dụng (Văn
phòng điện tử, Không gian cá nhân, Bảng tin), kể cả hai trang công khai `/trang-thai` và `/xac-thuc` — chúng là trang
của `apps/office`, lấy dữ liệu từ lõi qua cổng như mọi trang khác. Ứng dụng chỉ gọi lõi bằng API sau APISIX. Giao diện
còn lại đi theo phần mềm nguồn mở dùng nguyên bản, và không cái nào là màn hình nghiệp vụ:

- Bàn điều khiển cho người vận hành máy chủ: trang quản trị Keycloak, Grafana, và khi bật profile thì Parseable (log),
  Mailpit (hộp thư thử). Cả bốn chỉ nghe `127.0.0.1`, từ xa phải qua đường hầm SSH. Cổng công khai duy nhất là
  APISIX, và route `chan` của cổng chặn `/admin`, `/console`, `/realms/*` (trừ realm của Signet), `/flowable-rest/*`
  cùng các API nội bộ. Không ứng dụng nào gọi tới các bàn này.
- Trang đăng nhập của Keycloak (theme `signet`): theo OIDC, người dùng nhập mật khẩu, và mã TOTP với vai trò bắt buộc
  (văn thư, lãnh đạo, tổ trưởng, quản trị đơn vị), ở trang của dịch vụ danh tính chứ không ở ứng dụng. Nhờ vậy không
  ứng dụng nào thấy mật khẩu, và ba ứng dụng dùng chung một lần đăng nhập. Theme chỉ thêm CSS, logo và câu chữ tiếng
  Việt, tiếng Anh, không thay mẫu trang; cổng chỉ mở đường đăng nhập của realm Signet.
- Không có giao diện: Hasura tắt console (`HASURA_GRAPHQL_ENABLE_CONSOLE: "false"`); Flowable dùng bản REST, không có
  giao diện (QĐ-009).

**Bằng chứng:** `docker-compose.yml` (cổng của Keycloak, Grafana, Parseable, Mailpit gắn `127.0.0.1`);
`platform/apisix/apisix.yaml` (route `keycloak` chỉ mở realm `${MOC_REALM}`, route `chan`);
[`docs/architecture.md`](../architecture.md) §2 và QĐ-009; README, bảng địa chỉ ở mục "Chạy thử";
[`docs/van-hanh.md`](../van-hanh.md) mục "Giám sát".

## 15. Ứng dụng thứ ba muốn có luồng duyệt riêng thì làm thế nào?

Khai mục `workflow` trong manifest: các tệp BPMN và form JSON Schema của nó. `moc app install` gửi gói cho
`svc-workflow` kiểm trước mọi thay đổi, rồi triển khai lên chính Flowable của lõi thành một deployment đặt tên theo băm
nội dung. BPMN chỉ được dùng phần tử của một quy trình duyệt (danh sách trắng: không `scriptTask`, `serviceTask`,
listener hay biểu thức tùy ý, vì chúng chạy bằng quyền của động cơ); khóa quy trình mang tiền tố `<tên>.` nên không chạm
được quy trình Văn phòng hay của ứng dụng khác. Form kiểm cả ở trình duyệt lẫn ở lõi, có trần chi phí cho `pattern` để
một form không làm đứng dịch vụ. Trang của ứng dụng gọi API chung `/api/workflow/<tên>/…` qua APISIX: lấy form, gửi
đơn, xem đơn của mình, xem và hoàn thành việc. API chỉ nhận token của client `app-<tên>` (claim `azp`); đơn vị, phòng,
người gửi lấy từ token, việc giao theo nhóm `t:<đơn vị>:<vai trò>` hay theo phòng. Không ứng dụng nào gọi thẳng
Flowable: cổng chặn `/flowable-rest/*`. Ứng dụng mẫu Đơn nghỉ phép (`apps/nghi-phep`) không có máy chủ nghiệp vụ, không
có bảng, cắm bằng `moc app install` như Bảng tin. Giới hạn: mới là quy trình duyệt, như câu 13 (#325).

**Bằng chứng:** [`docs/them-ung-dung.md`](../them-ung-dung.md) mục 1.10 (kiểm BPMN, kiểm form, bảng API) và mục 7;
`apps/nghi-phep/app.yaml`; `services/svc-workflow/src/svc_workflow/apps/` (`bpmn.py`, `forms.py`, `api.py`);
`make demo-quy-trinh` (BPMN độc bị từ chối, dữ liệu sai form trả `422`, việc duyệt tới đúng phòng); CI job
`chay-thu`, phần `luong-chinh`, bước "Quy trình của ứng dụng qua lõi (make demo-quy-trinh)".

## 16. Vì sao cài ứng dụng bằng dòng lệnh, không có nút trên giao diện?

Cài một ứng dụng là việc của người vận hành máy chủ, không phải của người dùng. Lệnh cần dựng image và chạy container
qua Docker, tạo client trong Keycloak bằng quyền quản trị, tạo vai trò và schema trong PostgreSQL, ghi route APISIX và
metadata Hasura: 8 bước, 9 khi ứng dụng có quy trình. Một nút trên web nghĩa là một dịch vụ mở ra mạng phải giữ các
quyền đó, và lỗ hổng ở dịch vụ đó sẽ thành quyền điều khiển Docker trên máy chủ. Vì vậy đội để việc cài ở dòng lệnh
trên máy chủ, như cách cài chính Signet, và làm cho lệnh dễ dùng:
- `--dry-run` in kế hoạch từng bước trước khi đổi gì;
- chạy lại chỉ làm phần còn thiếu; lỗi giữa chừng báo đúng bước;
- bước Hasura lỗi thì trả tệp chạy về như trước; quy trình mới không chạy khi các bước sau nó lỗi;
- gỡ thì giữ dữ liệu.

Người dùng thấy ứng dụng đã cài ở trang Danh mục ứng dụng của Văn phòng điện tử (`/ung-dung`): tên, mô tả, nút Mở,
phiên bản. Lãnh đạo, quản trị đơn vị thấy thêm băm manifest để so với bản đã duyệt. Chưa có giao diện quản trị để cài,
gỡ.

**Bằng chứng:** [`docs/them-ung-dung.md`](../them-ung-dung.md) mục 1 (lệnh, trang Danh mục ứng dụng), 1.2 (từng bước
ghi vào đâu), 1.9 (giới hạn); `scripts/ung_dung.py`; `make demo-cai-ung-dung` (cài, cài lại, gỡ giữ dữ liệu); e2e
`ung-dung.spec.ts`.

## 17. Kho lạnh có thật sự tách khỏi kho nóng không?

Tách về quyền và vòng đời, chưa tách về máy. Kho lạnh là bucket `moc-cold` trên cùng SeaweedFS với bucket nóng
`moc-files`, bật S3 Object Lock chế độ COMPLIANCE: trong hạn giữ, không ai xóa, ghi đè hay rút ngắn hạn được, kể cả tài
khoản quản trị kho. Vòng nộp lưu là một tác vụ nền trong tiến trình `svc-files` (phần Văn phòng): hồ sơ đã đóng thành
gói Parquet + tệp + manifest có băm trong bucket lạnh, chi tiết rời CSDL; văn bản vẫn tìm thấy, cổng xác thực vẫn
"khớp", và gói đọc được bằng DuckDB hay công cụ Parquet bất kỳ, không cần Signet. Chưa có: kho lạnh ở máy hay dịch vụ S3
khác (cấu hình chỉ đổi được tên bucket, `MOC_COLD_BUCKET`, còn địa chỉ S3 dùng chung với kho nóng), và job nộp lưu chạy
tách khỏi `svc-files`. Vì bucket lạnh nằm trên chính máy chủ, mốc neo sổ kiểm toán còn chép ra ngoài được
(`moc audit anchor --to`, `--publish`) và được két ký bằng khóa Ed25519 `moc-anchor` để người ngoài tự kiểm (#56).

**Bằng chứng:** [`docs/architecture.md`](../architecture.md) QĐ-010; `services/svc-files/src/svc_files/config.py`
(`MOC_COLD_BUCKET` phải khác bucket nóng); `services/svc-files/src/svc_files/app.py` (vòng `office.archiver`);
`services/svc-files/src/svc_files/anchors.py` (chữ ký mốc neo); `make demo-nong-lanh` (xóa gói bị từ chối); CI job
`chay-thu`, phần `sao-luu`, bước "Nộp lưu hồ sơ nóng → lạnh (make demo-nong-lanh)".

## 18. Sản phẩm tên Signet, sao lệnh và cấu hình vẫn là `moc`?

Signet là tên sản phẩm; dự án trước đây tên Mộc. Phần người dùng và người tải thấy đã mang tên Signet: giao diện, trang
đăng nhập (theme `signet`), README, gói phát hành `signet-<phiên bản>.tar.gz` cùng SBOM `signet-<phiên bản>.cdx.json`.
Tên mã kỹ thuật `moc` còn trong biến `MOC_*`, realm Keycloak `moc`, lệnh `scripts/moc.py`, image `moc/*`, thư mục cài
mẫu `/opt/moc`. Đổi các tên này đụng vào bản cài đang chạy: tên realm nằm trong issuer của mọi token mà APISIX và Hasura
kiểm, biến `MOC_*` nằm trong `.env` của mọi bản cài. Vì vậy đổi tên mã phải đi kèm một bước nâng cấp chuyển đổi cho bản
đang chạy; đội chưa xếp lịch việc này.

**Bằng chứng:** README mục "Tài liệu" (ghi chú về tên mã); `.github/workflows/release.yml` (tên gói phát hành);
`docker-compose.yml` (`HASURA_GRAPHQL_JWT_SECRET`: issuer `${MOC_PUBLIC_URL}/realms/${MOC_REALM:-moc}`);
`platform/apisix/apisix.yaml` (`discovery` theo `MOC_REALM`).
