# Lộ trình phát triển Signet

Lộ trình bám theo nguyên lý **tiến hóa tuyến tính** của mô hình DX-OS: `[H] → [P] → [D] → [I]`, không gian sau dùng
danh tính, sự kiện, dữ liệu của không gian trước ([`docs/architecture.md`](docs/architecture.md) §1.2). Đây cũng là thứ
tự mà một tổ chức áp dụng Signet nên đi theo, không chỉ là lịch phát triển nội bộ.

Trạng thái ghi ngày 28/10/2026, trên nhánh `develop`, đúng nội dung bản `v1.3.0` (30/10). Các giai đoạn là thứ tự
phụ thuộc, không phải lịch: phần lớn việc của cả bốn không gian ra cùng bản `v1.0.0` (23/10) và `v1.1.0`. Việc làm từ
25/10 tới 27/10 đã ra ở `v1.2.0` (27/10), giao diện Lịch hạn ở bản vá `v1.2.1` (28/10), việc làm 28/10 (cảnh báo qua
Alertmanager, Node-RED, DokuWiki, tiếng Anh, truy vết phân tán) ở `v1.3.0` (30/10, bản cho vòng trường, mục [1.3.0] của
[`CHANGELOG.md`](CHANGELOG.md)); phần làm sau đó nằm ở mục "Chưa phát hành", sẽ ra ở `v1.4.0` (03/12, bản nộp chấm).
Mã tính năng F tra ở [`docs/muc-hoan-thien.md`](docs/muc-hoan-thien.md): mức, tệp test, bước CI, lệnh trình diễn và
hạn chế đã biết của từng tính năng. Mục không có mã F ghi bằng chứng (tệp, lệnh `make`, bước CI) ngay trong dòng.

- `[x]` — đã có: mức **Hoàn thiện** trong `docs/muc-hoan-thien.md`, hoặc có bằng chứng ghi trong dòng.
- `[ ]` **Một phần** — có mã chạy được (mức Dùng được, Minh họa hay Một phần); phần còn thiếu ghi ngay sau.
- `[ ]` **Đang làm** — có người đang làm, chưa gộp vào `develop`; có pull request thì ghi số.
- `[ ]` không nhãn — chưa làm.

Việc đổi trạng thái thì sửa dòng tương ứng ở đây trong cùng pull request với thay đổi đó.

## Giai đoạn 0 — Nền dự án nguồn mở ✅

Mục tiêu: kho mã nguồn đạt chuẩn dự án nguồn mở bền vững trước khi có dòng mã nghiệp vụ đầu tiên.

- [x] Giấy phép Apache-2.0: toàn văn, `NOTICE`, header từng tệp, khai REUSE ở `REUSE.toml`; `make license-check` kiểm
      header, `make license-audit` kiểm giấy phép mọi gói kể cả gói gián tiếp theo `DEPENDENCIES.md`
- [x] Cấu hình tách khỏi mã nguồn (`.env.example`)
- [x] Quy trình dựng từ mã nguồn (`Makefile` + Docker Compose)
- [x] CI trên pull request (`.github/workflows/ci.yml`): giấy phép, dựng từ mã nguồn, tài liệu, bảo mật chuỗi cung
      ứng, test đơn vị, test trên CSDL thật, chạy thử toàn hệ thống. Ruleset `.github/rulesets/develop.json` đòi đủ kiểm
      tra mới gộp được; nhánh và tiêu đề PR theo [`docs/git_flow.md`](docs/git_flow.md)
- [x] CI ngắn lại: job chạy thử toàn hệ thống chia năm phần chạy song song, mỗi phần tự dựng và nạp mẫu, vẫn đủ mọi
      bước (#111)
- [x] Phát hành gói `.tar.gz` kèm `.sha256` theo thẻ phiên bản (`.github/workflows/release.yml`, `make release`): đã
      phát hành `v0.1.0` (18/10) và `v1.0.0` (23/10). Bản sau `v1.0.0` đính kèm thêm SBOM CycloneDX (`make sbom`)
- [x] Tài liệu nền: README (cả bản tiếng Anh), CONTRIBUTING, CODE_OF_CONDUCT, CHANGELOG, DEPENDENCIES, SECURITY

## Giai đoạn 1 — [H] Không gian Nhân sự

Mục tiêu: một nhân sự đăng nhập **một lần** và làm được toàn bộ công việc thường ngày trong môi
trường số khép kín.

- [x] Định danh tập trung: Keycloak, SSO, TOTP bắt buộc với vai trò quan trọng, `tenant_id` và `department_id` trong
      token (F1.1, F2.1)
- [x] Một điểm vào: cổng API APISIX, danh sách trắng đường dẫn, kiểm JWT ở biên, giới hạn tốc độ (F1.2)
- [x] Tường lửa ứng dụng web ở cổng: Coraza + OWASP CRS trong APISIX, chặn mặc định, loại trừ có lý do (F3.15,
      nguyên lý iv; mức Dùng được: chữ lạ ở ô chữ ngắn có thể bị chặn nhầm, người quản trị phải thêm loại trừ)
- [x] Lưu trữ tệp nội bộ: SeaweedFS, tệp chỉ vào và ra qua `svc-files`, ClamAV quét trước khi ghi (F1.5, F1.6)
- [x] Cấu trúc thư mục **P.A.R.A**: Không gian cá nhân `apps/ca-nhan` (Dự án, Lĩnh vực, Tài nguyên, Lưu trữ), ứng
      dụng thứ hai cắm vào lõi, không sửa dòng nào trong `services/`
      ([`docs/them-ung-dung.md`](docs/them-ung-dung.md), bước CI `make demo-ca-nhan`)
- [x] Cắm ứng dụng bằng một lệnh: `moc app install apps/<thư mục>/app.yaml`, không sửa tệp nào của lõi; ứng dụng thứ ba
      Bảng tin đơn vị `apps/bang-tin` ([`docs/them-ung-dung.md`](docs/them-ung-dung.md) mục 1, mức Dùng được, bước CI
      `make demo-cai-ung-dung`); ứng dụng chạy quy trình riêng trên Flowable của lõi qua `/api/workflow/*`, ứng dụng mẫu
      Đơn nghỉ phép `apps/nghi-phep` (#301, bước CI `make demo-quy-trinh`)
- [ ] **Một phần** — cổng nội bộ: các ứng dụng chung một phiên SSO, cùng một tên miền sau APISIX; trang Ứng dụng
      (`/ung-dung`) của Văn phòng mở các ứng dụng khác, các ứng dụng kia có liên kết về Văn phòng; chưa có trang cổng
      riêng
- [ ] **Một phần** — truyền thông nội bộ: thông báo tức thời trong ứng dụng (Centrifugo, F2.5), thêm email, webhook
      Mattermost, Slack, ntfy, SMS, Zalo, tắt mặc định (`docs/muc-hoan-thien.md` mục 3, cụm ⑦); không có chat riêng
- [x] Hệ quản trị tri thức (wiki): DokuWiki ở `/wiki/`, profile `wiki` tắt mặc định; đăng nhập Keycloak, mỗi đơn vị
      một không gian chỉ người của đơn vị đọc, sửa ([`docs/van-hanh.md`](docs/van-hanh.md) mục Wiki nội bộ, bước CI
      `make demo-wiki`, #367). Chưa có không gian chung cả trường, trang wiki chưa vào tìm kiếm và trợ lý hỏi đáp
- [x] Dữ liệu mẫu: `make seed` tạo đơn vị, phòng ban, tài khoản theo vai trò, văn bản ở mọi bước, qua API như người
      dùng thật (F2.10); thêm đơn vị bằng một lệnh `moc tenant create` (F3.12)

## Giai đoạn 2 — [P] Không gian Quy trình

Mục tiêu: một nghiệp vụ chạy hết vòng đời **không cần thao tác chuyển giao thủ công** giữa các
bộ phận.

- [x] Động cơ quy trình: Flowable 8 chạy BPMN `van-ban-den`, `van-ban-di`; ứng dụng gọi Hasura Actions, chỉ
      `svc-workflow` ghi trạng thái văn bản, có callback và job đối soát (F1.4)
- [x] Ứng dụng Văn phòng điện tử `apps/office`: văn bản đến từ tiếp nhận tới xử lý, tự nhắc hạn rồi báo lãnh đạo; văn
      bản đi từ soạn tới phát hành PDF có mã QR và SHA-256; hộp việc, dòng thời gian, sổ đăng ký (F2.2–F2.8)
- [x] Liên thông văn bản giữa các đơn vị trên cùng bản cài, dữ liệu hai bên vẫn cách ly (F3.12)
- [x] Ràng buộc **Poka-yoke** ba lớp — form, máy chủ, CSDL — theo một JSON Schema dùng chung
      `schemas/van-ban-den.json`; chặn vào sổ trùng (F2.2)
- [x] Trục API giữa các thành phần: GraphQL tự sinh từ CSDL (Hasura) và REST của `svc-files`, cùng đi qua APISIX; tài
      liệu API xuất tự động ở `docs/api/` (F1.3, F1.10); trang Tài liệu API `/tai-lieu-api/` (Swagger UI, gọi thử qua
      cổng, #357) và trang tài liệu Docusaurus trên GitHub Pages (#308, #342)
- [ ] **Một phần** — API nạp lô văn bản đến `POST /api/imports/incoming` (cụm ⑤, mức Dùng được; bước CI
      `make demo-nap-lo`): mới có một loại lô, chưa có màn "Nhập lô" trên giao diện
- [ ] **Một phần** — hướng sự kiện: các bước của văn bản ghi vào `office.document_events`, mọi thay đổi vào sổ kiểm
      toán `core.audit_log`; ứng dụng cài bằng `moc app install` nhận luồng `core.app_events` qua Hasura Event
      Triggers (đến, vào sổ, phát hành; không văn bản hạn chế). Chưa có broker streaming: không phát lại, không bảo
      đảm thứ tự (cụm ⑥)
- [ ] **Một phần** — biểu mẫu low-code: form của ứng dụng cắm bằng manifest khai bằng JSON Schema, trang tự dựng form
      (Đơn nghỉ phép, #312); form của Văn phòng viết trong mã, JSON Schema dùng chung mới có cho form tiếp nhận văn bản
      đến, khuôn văn bản đi viết trong `services/svc-files/src/svc_files/render.py` (F2.4); chưa có trình dựng form
      (#303)
- [ ] **Một phần** — tự động hóa không cần sửa mã dịch vụ (kịch bản serverless, cụm ⑤): Node-RED ở `/tu-dong/`,
      profile `tu-dong` tắt mặc định, cho người vận hành nền tảng soạn flow; đăng nhập Keycloak, chỉ vai trò `operator`
      ([`docs/van-hanh.md`](docs/van-hanh.md) mục Tự động hóa bằng Node-RED, bước CI `make demo-tu-dong`, #366). Flow
      gọi lõi bằng robot của đơn vị (`moc tu-dong robot add`, vai trò Hasura `tu_dong` chỉ đọc, Action
      `notifyFromFlow`), hai flow mẫu. Còn thiếu: webhook, bước BPMN gọi flow; việc nền của lõi vẫn viết trong
      `svc-files`, `svc-workflow`

## Giai đoạn 3 — [D] Không gian Dữ liệu

Mục tiêu: mọi câu hỏi điều hành trả lời được bằng số liệu cập nhật, không cần ai tổng hợp tay.

- [x] CSDL nghiệp vụ: PostgreSQL 16 + Hasura v2 CE, quyền theo vai trò và đơn vị tới từng dòng, migrations và
      metadata tự áp (F1.3; lý do chọn: `docs/architecture.md` QĐ-002)
- [x] **Nguồn sự thật duy nhất** cho văn bản: PostgreSQL giữ dữ liệu nghiệp vụ, Flowable giữ bước quy trình, chỉ
      `svc-workflow` ghi cột trạng thái, job đối soát sửa chỗ lệch (F1.4;
      [`docs/du-thi/ke-hoach-phat-trien.md`](docs/du-thi/ke-hoach-phat-trien.md) §2.1)
- [x] Sổ kiểm toán chuỗi băm, đầu chuỗi neo ra bucket khóa ghi, `make audit` chỉ ra dòng bị sửa (F2.12); tab Lịch sử
      trên trang văn bản đọc từ sổ này (F3.5)
- [x] Dashboard điều hành: ECharts trong `apps/office`, bốn view số đếm qua Hasura, đúng quyền đơn vị (F3.11). Không
      dùng Metabase: bản nguồn mở không đăng nhập bằng Keycloak được và đọc thẳng CSDL, bỏ qua quyền đơn vị
      (`docs/du-thi/ke-hoach-phat-trien.md` §6)
- [x] Vòng đời nóng → lạnh (F3.8): hồ sơ đã đóng nộp lưu thành Parquet + tệp + manifest có băm trên bucket khóa ghi
      (`make demo-nong-lanh`); trên giao diện: trang Hồ sơ công việc, lãnh đạo phòng nộp lưu, phòng đọc xem tệp PDF
      có dấu tên người xem; trang Điều hành đếm văn bản đã nộp lưu bằng DuckDB trên gói Parquet (#304)
- [x] Phả hệ dữ liệu (F3.9): OpenLineage cho lượt nộp lưu, kiểm số dòng và cột bắt buộc trước khi ghi Parquet
      (`make demo-pha-he`); phả hệ báo cáo ← khung nhìn ← bảng tính từ catalog PostgreSQL, trang Phả hệ số liệu
      (`/pha-he`) vẽ đồ thị, mỗi biểu đồ ở trang Điều hành có nút Nguồn số liệu
- [ ] **Một phần** — từ điển dữ liệu: bảng, quyền, định dạng sự kiện ghi ở
      [`docs/mo-hinh-du-lieu.md`](docs/mo-hinh-du-lieu.md); chưa có lớp ngữ nghĩa báo cáo — chỉ số, chiều định nghĩa
      một lần, dùng chung — nên mỗi báo cáo là một view viết tay (cụm ③, mức Một phần)
- [ ] Đường ống thu thập — làm sạch — đồng bộ từ sự kiện [P] sang kho phân tích riêng: dashboard đang đọc thẳng view
      trên CSDL nghiệp vụ
- [ ] Đóng băng số liệu chuỗi thời gian: chưa có kho chuỗi thời gian riêng, chưa chụp số liệu theo kỳ (cụm ③)

## Giai đoạn 4 — [I] Không gian Trí tuệ Nhân tạo

Điều kiện khởi động: giai đoạn 3 đã có nguồn sự thật duy nhất. **Không khởi động sớm hơn.** Bốn tính năng AI F4.1–F4.4
chạy được không cần mô hình ngôn ngữ (quy tắc, OCR, tìm kiếm toàn văn); bật mô hình thì thêm phần viết trích yếu, viết
câu trả lời và tìm theo nghĩa.

- [x] Mô hình chạy tại chỗ, không gửi dữ liệu ra ngoài: Ollama với Qwen3 1,7B và Qwen3-Embedding 0,6B trên CPU, tắt
      mặc định (`make ai-model`, `make up-ai`). Tìm theo nghĩa dùng lại Meilisearch, không thêm CSDL véc-tơ riêng
      (`docs/architecture.md` QĐ-004)
- [x] Truy xuất tri thức (RAG): trợ lý hỏi đáp trên kho văn bản, trả câu trích nguyên văn kèm "số ký hiệu · tr. n",
      lọc quyền ở bước truy xuất (F4.2). Kho tri thức hiện là văn bản của Văn phòng điện tử; wiki nội bộ (#367)
      chưa nối vào
- [x] Tác tử đọc văn bản đến: lớp chữ PDF hoặc OCR Tesseract, điền sẵn form, văn thư xác nhận (F4.1)
- [x] Tác tử nghe sự kiện [P], đọc dữ liệu [D]: văn bản vừa vào sổ thì nhánh BPMN song song gợi ý đơn vị chủ trì và
      hạn từ các văn bản tương tự đã giao (F4.3)
- [x] Rào chắn **Human-in-the-loop**: tác tử chỉ gợi ý, người quyết; tác tử có danh tính riêng (vai trò `agent`), việc
      của nó vào sổ kiểm toán; CCCD, số điện thoại bị che trước khi tới mô hình và nhật ký (F4.4)
- [x] Đo từng tác tử: dữ liệu đo, số đo kèm ngày và máy, giới hạn ở [`docs/danh-gia-ai.md`](docs/danh-gia-ai.md);
      `make do-doc-van-ban`, `make do-hoi-dap`, `make do-giao-viec` đỏ khi dưới ngưỡng
- [ ] **Một phần** — tự thực thi hành động (F3.10, mức Minh họa): cảm biến giả lập vượt ngưỡng thì tác tử dựng dự thảo
      "Báo cáo sự cố" vào luồng văn bản đi, vẫn phải trình và duyệt (`make demo-it-ot`). Có chủ ý: tác tử F4.1–F4.4
      không tự tạo văn bản, tự giao việc hay trả lời thay người (`docs/danh-gia-ai.md`)
- [ ] Cổng giám sát tác tử AI (đề nêu ở [I] của Tầng 2): chưa có màn riêng

## Giai đoạn 5 — Đóng gói cho cộng đồng

Mục tiêu: một SME không có đội IT tự cài được Signet trong dưới một giờ.

- [x] Cài từ mã nguồn bằng lệnh `make`: `make env`, `make up`, `make seed`; `make check` kiểm có Docker, plugin
      compose, cấu hình hợp lệ; `make install PREFIX=…` cài ra ngoài thư mục mã nguồn rồi chạy từ đó, có bước CI (F1.8)
- [ ] Chứng minh "dưới một giờ": chưa đo với người ngoài đội trên máy sạch (việc của Phase 5 trong
      `docs/du-thi/ke-hoach-phat-trien.md`); `make check` chưa kiểm RAM và phiên bản Docker
- [x] Lên mạng (F1.9, mức Hoàn thiện): HTTPS sau Caddy hoặc Cloudflare Tunnel theo
      [`docs/trien-khai.md`](docs/trien-khai.md); phần CI `https` (#261) chạy smoke qua proxy TLS nginx với chứng
      thư tự ký trên mọi pull request. Cloudflare Tunnel chưa kiểm trong CI
- [x] Tài liệu vận hành: sao lưu, khôi phục, két bí mật, GitOps, giám sát ([`docs/van-hanh.md`](docs/van-hanh.md));
      triển khai, nâng cấp (`docs/trien-khai.md`). Sao lưu → xóa → khôi phục chạy trong CI (F3.4); reconciler GitOps
      dựng lại container bị xóa (F3.3)
- [x] Trang công khai Trạng thái hệ thống `/trang-thai`: tình trạng từng thành phần, phiên bản, giờ sao lưu gần nhất
      (`docs/van-hanh.md`, mục Trang trạng thái hệ thống)
- [x] Giám sát và cảnh báo (F3.13): Prometheus + Grafana thu chỉ số của APISIX và trạng thái từng thành phần (#274);
      luật cảnh báo (#255, #274) qua Alertmanager thành thông báo ở chuông của quản trị đơn vị, kèm email, webhook nếu
      đã bật (#284). Chưa có chỉ số bên trong từng dịch vụ
- [ ] **Một phần** — log tập trung (F3.14, mức Dùng được, #105): Vector + Parseable theo profile `logs`, tắt mặc
      định; `X-Request-Id` đi xuyên `svc-workflow`; thu 9 dịch vụ, cả Hasura, Keycloak, PostgreSQL (#202),
      Meilisearch (#395)
- [ ] **Một phần** — khung tự chẩn đoán mức trưởng thành H-P-D-I cho lãnh đạo (F4.7, mức Dùng được,
      `/tu-chan-doan`): bộ câu do đội tự viết, chưa thử với đơn vị thật; một người trả lời cho cả đơn vị
- [ ] **Một phần** — dữ liệu mẫu theo ngành: mới một ngành, văn thư của khoa, trường — `make seed` (F2.10) và lô 200
      văn bản đến `seed/nap-lo/van-ban-den.csv`; văn bản là giả lập, chưa lấy từ công văn đã công bố như kế hoạch
- [ ] **Một phần** — tiếng Anh: giao diện Văn phòng điện tử Việt / Anh cùng bộ khóa (F2.9, mức Dùng được), Không
      gian cá nhân và Bảng tin cũng có bản tiếng Anh (#306), `README.en.md`, hướng dẫn dịch cho người đóng góp
      (`CONTRIBUTING.md`, mục "Dịch giao diện"), hướng dẫn vận hành `docs/van-hanh.en.md` (#59); các tài
      liệu khác chưa có bản tiếng Anh
- [ ] **Một phần** — cộng đồng và số đo thực tế: `CONTRIBUTING.md`, mẫu issue (F2.11, mức Một phần); thu góp ý và
      trang Số đo theo đặc tả §8 (F4.6, mức Dùng được). Chưa có đơn vị chạy thử nên cột "trước" của số đo còn trống

## Sau vòng trường

Việc còn thiếu thật theo `docs/muc-hoan-thien.md`, xếp theo ưu tiên, kèm lý do. Không gắn ngày: kế hoạch chỉ có hai
mốc, đóng băng tính năng 26/11 và bản nộp chấm `v1.4.0` ngày 03/12 (`docs/du-thi/ke-hoach-phat-trien.md`, Phase 5).
Việc nào chưa xong trước 26/11 thì để sau `v1.4.0`.

1. **Đơn vị chạy thử thật** (F2.11, F4.6): đo cột "trước" của số đo §8, nhận góp ý của người ngoài đội. Mọi số đo hiện
   tính trên dữ liệu mẫu; chưa có đơn vị dùng thật thì chưa biết sản phẩm giải đúng bài toán đến đâu.
2. **Trục sự kiện** (cụm ⑥, một phần): ứng dụng cài bằng `moc app install` đã nghe được sự kiện [P] qua luồng
   `core.app_events` và Hasura Event Triggers, không đọc thẳng bảng của Văn phòng điện tử. Còn thiếu: phát lại, thứ
   tự, thêm loại sự kiện ngoài văn bản; chưa thêm broker.
3. **Việc nền khai báo, kịch bản serverless** (cụm ⑤, một phần): Node-RED (profile `tu-dong`, #366) cho người vận
   hành soạn flow, gọi lõi bằng robot của đơn vị; còn thiếu webhook, bước BPMN gọi flow qua `svc-workflow`
   (topic `moc-tu-dong`). Việc nền của lõi vẫn viết trong mã dịch vụ.
4. **Truy vết, giám sát đủ** (cụm ⑥): span của Hasura, Flowable, Keycloak, PostgreSQL (Jaeger mới có span của cổng và
   hai dịch vụ, #364), chỉ số từng dịch vụ, cảnh báo — nối tiếp log tập trung (#105).
5. **Thông báo đa kênh đủ** (cụm ⑦): SMS, Zalo đã có, từng người tự bật (#365); còn cho từng người tắt email, webhook
   riêng từng đơn vị thay một URL chung.
6. **Lớp ngữ nghĩa báo cáo, số liệu theo kỳ** (cụm ③): chỉ số và chiều định nghĩa một lần cho mọi báo cáo; chụp số
   liệu theo kỳ để số đã chốt không đổi về sau.
7. **Khuôn văn bản, biểu mẫu sửa được không cần sửa mã** ([P] low-code): trước hết cho quản trị đơn vị tự sửa mẫu văn
   bản đi (F2.4). Thiết kế quy trình bằng giao diện cần một công cụ thay `bpmn-js`, vốn bị loại vì giấy phép
   (`docs/du-thi/ke-hoach-phat-trien.md` §6).
8. **Hạn chế đã ghi của tính năng đã có**: gửi lại liên thông lỗi (F3.12), thời hạn từng bước của quy trình không
   trừ ngày nghỉ, ngày lễ (F2.3), lịch ngày lễ âm lịch tự có thay vì người vận hành thêm mỗi năm (F4.3), chữ OCR của cả
   bản scan chứ không chỉ 3 trang đầu (F2.7), két bí mật có TLS và xoay khóa (F3.2), tự chép kho sao lưu ra ngoài máy
   chủ (F3.4).
9. **Dịch thuật trong lõi** (cụm ②): dịch vụ dịch chạy tại chỗ cho mọi ứng dụng. Xếp sau vì người dùng hiện là cơ
   quan trong nước và giao diện đã có tiếng Anh.
10. **WebGIS** (đề nêu ở [D] của Tầng 2): nghiệp vụ văn thư hiện chưa cần bản đồ; làm khi có ứng dụng cần.

Cần tổ chức bên ngoài cấp phép hay cấp kết nối, nên chỉ làm khi có đơn vị dùng đứng ra
([`docs/dac-ta-san-pham.md`](docs/dac-ta-san-pham.md) §4.4 xếp vào "Không làm"): chữ ký số công cộng, USB token, HSM
cho khóa ký — F4.5 hiện là PKI nội bộ, chỉ minh họa; liên thông Trục văn bản quốc gia (edXML).

## Ngoài phạm vi

Những việc dự án chủ động **không** làm, để giữ đúng bài toán:

- Viết lại từ đầu các phần mềm đã có bản nguồn mở trưởng thành (ERP, CRM, BI)
- Yêu cầu hạ tầng vượt quá khả năng của một SME (cụm Kubernetes nhiều node, GPU chuyên dụng): Docker Compose trên một
  máy (`docs/architecture.md` QĐ-003), mô hình AI chạy trên CPU
- Phụ thuộc vào bất kỳ thành phần nguồn đóng hoặc dịch vụ trả phí bắt buộc nào
- Văn bản Mật, Tối mật, Tuyệt mật: Luật Bảo vệ bí mật nhà nước 2018 cấm lưu trên máy kết nối Internet
- Ứng dụng di động riêng: giao diện web dùng được trên điện thoại
- Ứng dụng ngành của Tầng 3: đề không bắt buộc
