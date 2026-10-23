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

## 1. Open-Core nằm ở đâu, ứng dụng khác dùng lại lõi thế nào?

Tầng 1 là profile `core` của `docker-compose.yml` (Keycloak, APISIX, Hasura + PostgreSQL, Flowable, SeaweedFS,
Meilisearch, ClamAV, OpenBao, `svc-files`, `svc-workflow`), không có giao diện: chỉ APISIX mở cổng ra ngoài, đường quản
trị (`/console`, `/v1/metadata`, `/admin`…) trả 404. Ứng dụng nào cũng gọi lõi qua một cổng bằng token Keycloak —
GraphQL cho dữ liệu, REST cho tệp, tìm kiếm, WebSocket cho thông báo; riêng cổng xác thực văn bản không cần token — và
đơn vị, vai trò luôn lấy từ token. Dữ liệu dùng chung nằm ở schema `core` (đơn vị, tệp, sổ kiểm toán, thông báo); Văn
phòng điện tử có schema `office` riêng, ứng dụng mới thêm schema của nó và một client Keycloak theo mẫu `app-office`,
không sửa `core`. Có hai ứng dụng Tầng 2: Văn phòng điện tử (`app-office`, gồm cả cổng xác thực công khai `/xac-thuc`)
và Không gian cá nhân P.A.R.A (`app-ca-nhan`, `/ca-nhan/`). Ứng dụng thứ hai chỉ thêm schema `personal`, client
`app-ca-nhan`, một route APISIX và một service compose, không sửa dòng nào trong `services/`, và dùng chung phiên đăng
nhập, sổ kiểm toán, quét mã độc của lõi. `smoke.py` và các màn demo thao tác như người dùng qua đúng cổng đó, bằng token
của tài khoản mẫu. Phần nghiệp vụ văn phòng phía máy chủ (Actions vào sổ, phát hành, dựng PDF văn bản đi) còn nằm chung
trong `svc-workflow`, `svc-files`.

**Bằng chứng:** README mục "Kiến trúc"; [`docs/api/README.md`](../api/README.md) (§1 "Muốn thêm một ứng dụng Tầng 2");
[`docs/them-ung-dung.md`](../them-ung-dung.md) (các bước thêm ứng dụng, mẫu là `apps/ca-nhan`), `make demo-ca-nhan`;
[`docs/mo-hinh-du-lieu.md`](../mo-hinh-du-lieu.md) §0; `platform/apisix/apisix.yaml`; `make smoke` (chặn đường quản
trị); CI job `stack`, bước "Tài liệu API trong docs/api/ khớp mã (make api-docs)".

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
vị"; CI job `stack`, bước "Thêm đơn vị bằng một lệnh (moc tenant create, check)".

## 4. Bảo mật: đăng nhập, tệp độc, văn bản nhạy cảm, nhật ký

Đăng nhập một lần qua Keycloak; văn thư, lãnh đạo, tổ trưởng, quản trị đơn vị bắt buộc mã TOTP, cả ở đường lấy token
cho script. Keycloak chặn dò mật khẩu, APISIX giới hạn lượt đăng nhập theo IP và kiểm JWT ngay ở biên, dịch vụ phía
sau kiểm lại token. Mọi tệp qua ClamAV trước khi ghi vào kho; ClamAV không trả lời thì từ chối (`503`) chứ không cho
qua. Văn bản hạn chế: mỗi tệp một khóa AES-256 bọc trong két OpenBao, kho và bản sao lưu chỉ có bản mã, bản rõ chỉ ở
trong bộ nhớ cho người có tên và mang tên người xem; dịch vụ lấy bí mật từ két bằng AppRole, không qua biến môi trường.
Mọi thay đổi vào sổ kiểm toán chuỗi băm SHA-256, đầu chuỗi neo định kỳ (mặc định 10 phút) ra bucket khóa ghi:
`make audit` tính lại cả chuỗi ngoài CSDL và chỉ ra dòng bị sửa, kể cả khi người sửa tắt trigger hay viết lại cả
chuỗi. Giới hạn đã ghi: các container gọi nhau bằng HTTP trong mạng nội bộ, Hasura nối CSDL bằng siêu người dùng.

**Bằng chứng:** `platform/keycloak/README.md`; `make demo-kiem-dich`, `make demo-han-che`, `make demo-ket-bi-mat`,
`make audit`; `db/README.md` (test sổ kiểm toán, gồm các kiểu sửa lén); [`docs/trien-khai.md`](../trien-khai.md) §8;
CI job `stack` (các bước `make demo-*`), job `security` (gitleaks, OSV-Scanner).

## 5. AI có bịa không, dữ liệu có ra khỏi máy không?

Mô hình (Qwen3 1,7B và Qwen3-Embedding 0,6B, trọng số Apache-2.0) chạy bằng Ollama trên chính máy chủ, trong mạng
Docker `ai` không ra Internet, đã tắt tính năng đám mây; chữ gửi mô hình đã che số định danh, điện thoại, email, số
tài khoản. Trợ lý chỉ tìm trong văn bản người hỏi được xem: lọc ngay trong chỉ mục theo quy tắc quyền, rồi hậu kiểm
từng văn bản bằng Hasura với token người hỏi trước khi đoạn nào tới mô hình; văn bản hạn chế không bao giờ vào chỉ
mục. Đường mặc định không cần mô hình: câu trích nguyên văn kèm "số ký hiệu · tr. n"; khi mô hình viết, `svc-files` tự
gắn [n] cho từng câu theo đoạn nguồn, câu không có căn cứ thì người dùng chỉ thấy câu trích. Đo trên bản online ngày
23/10/2026 (laptop i5-12500H, Ollama 0.35.1 dùng 8 lõi CPU, `python3 scripts/demo.py do-hoi-dap`, 19 câu): recall@3
16/16, từ chối đúng 3/3, 0 nguồn bị cấm, tìm p50 0,4 s / p95 0,5 s; câu của mô hình trích đúng nguồn 16/16, viết p50
8,9 s / p95 21,1 s. Kho mẫu nhỏ, câu hỏi do đội viết: đây là mức trần, chưa phải số trên văn bản thật.

**Bằng chứng:** `make demo-hoi-dap`, `make do-hoi-dap` (thoát 1 khi có nguồn bị cấm), `make demo-che-pii`,
`make do-che-pii`; `services/svc-files/README.md` (bảng số đo); `docs/architecture.md` QĐ-004, QĐ-006;
`docker-compose.yml` (dịch vụ `ollama`, mạng `ai`); CI job `stack`, bước "Đo chất lượng hỏi đáp (make do-hoi-dap)".

## 6. Hỏng máy, mất dữ liệu thì sao?

`make backup` sao lưu mọi CSDL (nghiệp vụ, Keycloak, Flowable), toàn bộ tệp và két OpenBao vào kho restic mã hóa; để
CSDL và tệp cùng một thời điểm, Signet tạm dừng ghi vài giây. `make restore` kiểm bản sao đọc được trọn vẹn rồi mới thay
dữ liệu, ghi lần khôi phục vào sổ kiểm toán; `make audit` sau đó vẫn khớp mốc neo. CI diễn tập đúng chuỗi sao lưu → xóa
dữ liệu → khôi phục → smoke ở mọi pull request. Tự phục hồi: reconciler (systemd timer mỗi 60 giây) dựng lại container
bị xóa, chạy lại container đã dừng hay unhealthy, và khi bật GitOps thì đưa cấu hình bị sửa tay về đúng commit; két tự
mở khóa nên khởi động lại không cần người. Giới hạn: một máy, nên mất phần dữ liệu từ lần sao lưu gần nhất; kho sao lưu
phải chép ra máy khác, `.env` (khóa kho, khóa két) cất riêng; chưa đo thời gian khôi phục trên dữ liệu lớn.

**Bằng chứng:** [`docs/van-hanh.md`](../van-hanh.md) mục "Sao lưu và khôi phục", "GitOps và tự phục hồi";
[`docs/trien-khai.md`](../trien-khai.md) §7 (sao lưu hằng đêm); `make demo-tu-phuc-hoi`; CI job `stack`, bước "Sao
lưu, xóa dữ liệu, khôi phục rồi kiểm lại (make backup, make restore)" và "GitOps — reconciler áp commit mới, sửa lệch
cấu hình (scripts/reconcile.py)".

## 7. Một thành phần ngừng thì hệ thống ra sao?

Mỗi phụ thuộc có cách lùi riêng, chọn theo hướng an toàn. Ollama tắt hay quá giờ: trích yếu theo quy tắc, trợ lý về tìm
theo từ khóa và trả câu trích, `svc-files` dò lại mô hình mỗi 60 giây. `svc-files` ngừng đúng lúc văn bản vào sổ: lãnh
đạo vẫn có việc chỉ đạo, chỉ mất gợi ý giao việc. ClamAV ngừng: tải tệp bị từ chối, vì thà chặn còn hơn lưu tệp chưa
quét; Meilisearch ngừng: trợ lý báo `503 search_unavailable` chứ không trả lời mò. Liên thông giữa hai đơn vị ghi outbox
trong cùng giao dịch phát hành, vòng nền gửi lại giãn dần từ 30 giây tới 1 giờ; container chết hẳn thì reconciler dựng
lại trong vòng một phút.

**Bằng chứng:** [`docs/demo-script.md`](../demo-script.md) (các mục "Nếu giám khảo hỏi"); `make demo-giao-viec` (bước
10: dừng `svc-files` giữa chừng); `make demo-tu-phuc-hoi`; `services/svc-files/README.md` (mã lỗi `503` của trợ lý).

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

Không có tiền giấy phép: mọi thành phần là phần mềm nguồn mở, GitHub và Cloudflare gói Free đủ dùng; chi phí là máy
và điện. Hệ thống mặc định (15 container) dùng khoảng 3,2–3,5 GB RAM khi chạy, chưa bật mô hình; máy chủ đề xuất
4 vCPU, 8 GB RAM, 40 GB đĩa, nhưng chưa đo thật trên máy 8 GB. Bật mô hình AI cần máy 16 GB (Ollama giới hạn mặc định
6 GB RAM, 4 lõi; đặt lại bằng `MOC_AI_MEM_LIMIT`, `MOC_AI_CPUS`). Bản online <https://signet.htechcs.com> chạy trên một
laptop của đội (i5-12500H) qua Cloudflare Tunnel, không cần IP công khai.

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

**Bằng chứng:** README mục "Cài đặt từ mã nguồn"; CI job `build` ("Dựng từ mã nguồn (PoF #4)"), job `stack`, bước
"Cài ra ngoài thư mục mã nguồn và chạy từ đó (make install)"; [`pof-checklist.md`](pof-checklist.md) tiêu chí 3, 4;
[`ke-hoach-phat-trien.md`](ke-hoach-phat-trien.md) §4.1.

## 12. H-P-D-I ở đâu, khác gì phần mềm quản lý văn bản sẵn có?

Một công văn đi trọn [H] → [P] → [D] → [I]: danh tính SSO, đơn vị và phòng trong token ([H]); luồng BPMN vào sổ, chỉ
đạo, xử lý, phát hành, chặn nhập sai ở form, máy chủ và CSDL theo một JSON Schema ([P]); dashboard điều hành, sổ đăng
ký, nộp lưu sang kho lạnh có phả hệ ([D]); tác tử đọc văn bản đến, hỏi đáp, gợi ý giao việc dùng chính dữ liệu đó
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
cho một máy. Chưa có thực thi kịch bản serverless (cụm ⑤) và công cụ low-code: form, quy trình viết bằng mã (JSON Schema
trong `schemas/`, BPMN XML), chưa có trình thiết kế quy trình trên giao diện (bpmn-js bị loại vì giấy phép). Thông báo
gửi trong ứng dụng qua WebSocket (Centrifugo) và, khi cấu hình, qua email và webhook chat; chưa có SMS, Zalo, chưa cho
từng người chọn kênh. Một máy, không chịu lỗi nhiều nút, chưa đo tải; bản online chạy trên laptop qua Cloudflare Tunnel,
chưa lên VPS thật. Ký số chỉ minh họa bằng CA nội bộ, chưa liên thông Trục văn bản quốc gia, không dùng cho văn bản mật;
số đo AI trên kho văn bản giả lập, chưa có đơn vị dùng thật.

**Bằng chứng:** [`ke-hoach-phat-trien.md`](ke-hoach-phat-trien.md) §6 "Không làm — và lý do";
[`docs/dac-ta-san-pham.md`](../dac-ta-san-pham.md) §4.4; [`docs/trien-khai.md`](../trien-khai.md) §8; các mục "Còn gì
chưa làm?" trong [`docs/demo-script.md`](../demo-script.md).
