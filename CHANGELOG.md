# Lịch sử thay đổi

Mọi thay đổi đáng chú ý của Mộc được ghi lại trong tệp này.

Định dạng theo [Keep a Changelog 1.1.0](https://keepachangelog.com/vi/1.1.0/),
đánh phiên bản theo [Semantic Versioning 2.0.0](https://semver.org/lang/vi/).

## [Chưa phát hành]

### Đã thêm
- Khung dự án nguồn mở: giấy phép Apache-2.0 (toàn văn + thông báo mục đích + header từng tệp).
- Quy trình dựng từ mã nguồn qua `Makefile` và Docker Compose (profile `core` cho Tầng 1, `app` cho Tầng 2).
- Cấu hình tách khỏi mã nguồn qua `.env.example`.
- CI kiểm tra header giấy phép và tính hợp lệ của Compose.
- Quy trình phát hành sinh gói `.tar.gz` theo thẻ phiên bản.
- Mẫu báo lỗi / đề xuất tính năng và mẫu pull request.
- Tài liệu: README, CONTRIBUTING, CODE_OF_CONDUCT, ROADMAP, DEPENDENCIES,
  tóm tắt đề bài OLP 2026, bảng tự chấm PoF.
- Tài liệu nghiên cứu trước khi có đề thi, lưu ở `docs/nghien-cuu/`: chiến lược dự thi, hướng
  triển khai, và bản kiểm chứng chủ đề 2026 (giáo trình DX-OS, giấy phép công cụ ứng viên, kho mã
  các đội mùa trước).
- Đặc tả nghiệp vụ DX-Safety (`docs/nghien-cuu/dac-ta-dx-safety.md`): sổ sự cố an toàn xưởng, bàn
  phê duyệt ngoại lệ, đồng hồ H% đo từ dữ liệu vận hành, kịch bản demo.
- Dự báo đề thi tháng 11/2026 (`docs/nghien-cuu/du-bao-de-thi-2026.md`): mô hình ba mùa, lĩnh vực
  và chuẩn có thể bị ép, kiến trúc gói lĩnh vực để phòng; bổ sung bảng ba mùa vào chiến lược dự thi.
- Kế hoạch 4 tuần cho vòng cấp trường (`docs/nghien-cuu/ke-hoach-vong-truong.md`): phạm vi tối
  thiểu, lịch tuần, phân vai, cổng kiểm tra và danh sách cắt.
- Dự báo đề thi, đợt bằng chứng 2: tác giả chủ đề và FDS, hộp cát Alpha Corporation kèm CSV mẫu,
  đối chứng bài giới thiệu 2025; đổi gói lĩnh vực vòng trường sang DX-Ticket theo hộp cát.
- Phân tích đề thi chính thức OLP PMNM 2026 (`docs/olp-2026-de-thi.md`), kế hoạch phát triển theo
  phase (`docs/ke-hoach-phat-trien.md`) và quy trình Git của dự án (`docs/git_flow.md`).
- `DEPENDENCIES.md`: danh mục đầy đủ phần mềm thượng nguồn kèm phiên bản ghim, giấy phép, cách nạp,
  và các thành phần đã loại vì không mang giấy phép OSI.
- Đặc tả sản phẩm (`docs/dac-ta-san-pham.md`): Văn phòng điện tử quản lý văn bản đến / đi theo Nghị định
  30/2020/NĐ-CP và cổng xác thực văn bản bằng mã QR; so sánh phương án, đối chiếu kho mã công khai của
  các đội khác, căn cứ pháp lý, kịch bản demo.
- Bản nháp mô hình dữ liệu (`docs/mo-hinh-du-lieu.md`): schema `core` dùng chung và `office` của ứng dụng,
  quyền theo vai trò, Hasura Actions, task BPMN, định dạng sự kiện.
- Lõi Tầng 1 chạy bằng `make up`: Keycloak (realm `moc`, vai trò/đơn vị/phòng vào token cho Hasura),
  APISIX là cổng duy nhất (kiểm JWT ở biên, chặn đường quản trị, gỡ khóa quản trị Hasura từ ngoài vào),
  PostgreSQL + Hasura, Flowable, SeaweedFS (có kiểm khóa S3), ClamAV, Meilisearch (#13, #14, #21).
- Schema `core` + `office`, quyền 6 vai trò, sổ kiểm toán chuỗi băm; danh bạ `core.users` và hàm vào sổ
  `office.register_incoming` cấp số đến liên tiếp trong một giao dịch (#18).
- `svc-files`: tải lên qua ClamAV vào SeaweedFS, tải xuống theo quyền, tìm kiếm Meilisearch gõ không dấu (#19, #20).
- `svc-workflow`: Hasura Actions `registerIncoming`, `myTasks`, `completeTask`; quy trình BPMN
  `van-ban-den` (chỉ đạo → phân công → xử lý); đồng bộ danh bạ Keycloak; job đối soát (#15, #23).
- Giao diện Văn phòng điện tử (`apps/office`, Nuxt 4): đăng nhập SSO, hộp việc, văn bản đến, tiếp nhận có
  kiểm form và chặn trùng, chi tiết văn bản với dòng thời gian, xử lý việc, tìm kiếm; tiếng Việt / Anh;
  CSP chặt (#22).
- `make env`, `make seed` (2 đơn vị, 10 tài khoản, văn bản ở mọi bước), `make smoke` (13 kiểm tra qua
  cổng), `make e2e` (Playwright trên trình duyệt thật) (#16).
- Giới hạn tốc độ ở cổng APISIX (F1.2), vượt thì trả 429: đường nhận mật khẩu và cấp token theo địa chỉ IP
  (`MOC_RATE_LOGIN_PER_MIN`, mặc định 60/phút), GraphQL và tệp theo phiên đăng nhập (`MOC_RATE_API_PER_MIN`,
  mặc định 300/phút). Giao diện báo "thao tác quá nhanh" thay cho lỗi chung; `make smoke` thêm 3 kiểm tra.
- CI chạy kiểm thử thật trên mọi PR: test đơn vị dịch vụ, test schema và quyền trên PostgreSQL + Hasura,
  dựng toàn hệ thống rồi `make seed` → `make smoke` → `make e2e`; quét bí mật trong lịch sử commit
  (gitleaks) và lỗ hổng phụ thuộc (OSV-Scanner); kiểm workflow bằng actionlint.
- `make install PREFIX=/opt/moc` và `make uninstall`: cài ra ngoài thư mục mã nguồn — image của đội gắn thẻ
  phiên bản, compose và cấu hình chép sang `PREFIX`, tự kiểm bản cài không trỏ về mã nguồn; cài lại là nâng
  cấp, giữ `.env`. CI chạy smoke từ bản cài (F1.8, PoF #4).
- Tài liệu API (`docs/api/`, F1.10): hướng dẫn lấy token và gọi GraphQL, REST qua cổng; schema GraphQL mà
  từng vai trò thấy, bảng vai trò × truy vấn/thao tác ghi, OpenAPI của `svc-files` và `svc-workflow` — xuất
  từ hệ thống đang chạy bằng `make api-docs`, CI báo lỗi khi tài liệu lệch mã (#24).
- Văn bản đi (F2.4): chuyên viên soạn dự thảo (nội dung, nơi nhận, trả lời văn bản đến, tài liệu kèm theo),
  xem trước PDF đúng thể thức NĐ 30/2020; quy trình BPMN `van-ban-di` — lãnh đạo phòng duyệt, lãnh đạo đơn vị
  ký, trả lại ở bước nào cũng về người soạn sửa rồi trình lại (Action `submitOutgoing`); văn thư cấp số đi liên
  tiếp theo năm, ký hiệu theo NĐ 30 (`05/TB-CNTT`, `05/CNTT-ĐT`) trong một giao dịch; `svc-files` dựng bản phát
  hành bằng WeasyPrint có mã QR, quét ClamAV rồi lưu, SHA-256 ghi vào CSDL và sổ kiểm toán (#29).
- Cổng xác thực văn bản (F2.13): `/api/verify` không cần đăng nhập, mỗi lần đúng một văn bản theo mã tra cứu
  hoặc SHA-256, APISIX giới hạn theo IP (`MOC_RATE_VERIFY_PER_MIN`); trang `/xac-thuc` mở thẳng từ mã QR, thả
  tệp PDF thì trình duyệt tự tính SHA-256 — tệp không tải lên — và báo khớp hay đã bị sửa (#30).
- `make seed` thêm 6 văn bản đi ở đủ các bước; `make smoke` thêm 5 kiểm tra (tổng 23); `make e2e` thêm kịch
  bản văn bản đi: soạn, trả lại, trình lại, ký, phát hành, người ngoài kiểm tệp ở cổng xác thực.
- Thông báo realtime (F2.5): sau mỗi bước, người phải làm việc kế tiếp nhận thông báo — việc mới (kèm ý kiến khi
  bị trả lại), văn bản đã phát hành, đã báo kết quả xử lý. Thông báo lưu ở `core.notifications` (mỗi người chỉ
  đọc của mình), Centrifugo đẩy qua WebSocket `/realtime` tới kênh riêng của từng người, tự kiểm token Keycloak.
  Giao diện có chuông thông báo, tin hiện ở góc màn hình, hộp việc và trang văn bản tự tải lại (#31).
- Nhắc hạn (F2.3): mỗi bước trong hai quy trình BPMN có timer `R2/${slaDuration}` (`MOC_SLA_DURATION`, thật
  `PT24H`, demo `PT1M`); quá một thời hạn thì nhắc người phải làm, quá hai thì báo lãnh đạo của họ, ghi vào dòng
  thời gian. Văn bản đến qua hạn giải quyết thì báo người xử lý và lãnh đạo (#32).
- `make smoke` thêm 5 kiểm tra (tổng 28): token giả bị đóng kết nối, tin việc mới tới qua WebSocket, thông báo
  lưu đúng người, nhắc hạn và báo lãnh đạo khi `MOC_SLA_DURATION` ngắn (CI đặt `PT20S`); `make e2e` thêm kịch
  bản hai người dùng cùng lúc: chuyên viên trình, tổ trưởng thấy tin và việc mới không phải tải lại trang.
- Sổ kiểm toán chuỗi băm (F2.12): `svc-files` định kỳ neo hash đầu chuỗi ra bucket lạnh `moc-cold` bật S3 Object
  Lock, chế độ COMPLIANCE — trong hạn giữ không ai xóa, ghi đè hay rút ngắn hạn được, kể cả quản trị kho.
  `make audit` (`scripts/moc.py audit verify`) tính lại cả chuỗi bên ngoài CSDL, so với các mốc đã neo và với hash
  của văn bản: sửa một dòng thì chỉ ra dòng đó, sửa rồi tính lại cả chuỗi thì chỉ ra khoảng dòng bị viết lại, đổi
  hash văn bản phát hành thì chỉ ra văn bản đó; `audit anchor --to <tệp>` giữ thêm một bản mốc ngoài máy chủ. Màn
  "Sổ kiểm toán" cho lãnh đạo, quản trị đơn vị: ai, lúc nào, làm gì, cột nào đổi, dòng đã neo chưa — không lộ nội
  dung văn bản hạn chế (#33).
- SeaweedFS nằm riêng mạng `storage`, chỉ `svc-files` tới được, và tắt HTTP của filer: gọi thẳng filer thì bỏ qua
  được khóa ghi của bucket. Tắt gửi thống kê ẩn danh của SeaweedFS ra ngoài (#33).
- `make smoke` thêm 3 kiểm tra (tổng 31): neo rồi kiểm cả sổ, mốc neo không xóa được, lãnh đạo thấy hash văn bản
  vừa phát hành trong sổ; `make e2e` thêm kịch bản lãnh đạo xem sổ kiểm toán.
- Poka-yoke ba lớp cho tiếp nhận văn bản đến (F2.2) theo một JSON Schema dùng chung, `schemas/van-ban-den.json`:
  form kiểm bằng Ajv biên dịch sẵn lúc build (không cần `unsafe-eval` trong CSP); Action mới `receiveIncoming`
  của `svc-workflow` kiểm lại bằng `jsonschema` rồi tra loại văn bản, tệp, văn bản trùng; PostgreSQL chặn lần cuối
  bằng ràng buộc mới `documents_in_symbol`, `documents_in_issuer`, `documents_in_summary`, `documents_in_dates`.
  Ngoài độ dài, khoảng trắng, ngày: chặn ký tự ẩn và chữ dạng Unicode tổ hợp (chép từ PDF hay dính, làm cùng một
  văn bản lọt qua chặn trùng); form tự dọn những thứ này trước khi gửi.
  Hai lớp đầu trả lỗi từng trường cùng một bộ mã; ba lớp chạy chung bộ ca thử `schemas/van-ban-den.cases.json`
  (#34).
- `make test` chạy thêm test kiểm form (`apps/office`, Node 24); `make smoke` thêm 4 kiểm tra (tổng 35): văn thư
  không ghi thẳng được bảng văn bản, svc-workflow trả lỗi từng trường, chặn tiếp nhận trùng, CSDL chặn khi ghi
  thẳng bằng quyền quản trị; `make e2e`: form sai bị chặn trên trình duyệt, không gửi gì đi (#34).
- Sổ đăng ký văn bản đến / đi theo năm (F2.8), in được theo NĐ 30/2020, Điều 16, 22: `svc-files` dựng sổ đúng các
  cột của mẫu sổ ở Phụ lục IV (sổ đến 9 cột, sổ đi 10 cột) — `GET /api/registers/{in|out}/{năm}` cho giao diện,
  `…/pdf` ra bản in A4 ngang có bìa, bảng kẻ, chỗ văn thư ký để ký nhận và đóng sổ. Chỉ văn thư, lãnh đạo đơn vị
  xem được. Sổ luôn liền số từ 01, kể cả văn bản hạn chế người in không được đọc: dòng đó chỉ có số, ngày, số ký
  hiệu; bìa sổ báo nếu thiếu số. Mỗi lần in ghi vào sổ kiểm toán (`register.printed`: ai in, sổ nào, bao nhiêu
  dòng, bao nhiêu dòng bị che). Trang `/so-dang-ky` xem sổ theo năm, mở văn bản từ dòng sổ, in PDF (#35).
- `make smoke` thêm 3 kiểm tra (tổng 38): sổ đến, sổ đi có văn bản vừa vào sổ, phát hành và liền số; in sổ ra PDF,
  lần in vào sổ kiểm toán; chuyên viên không xem được sổ. `make e2e` thêm kịch bản văn thư xem sổ, in PDF (#35).
- Tìm theo nội dung (F2.7): ngoài số ký hiệu, trích yếu, cơ quan ban hành, tìm được cả nội dung văn bản đi và chữ
  trong tệp PDF đính kèm. `svc-files` đọc lớp chữ của PDF đã gắn vào văn bản ở vòng nền (pypdf, trong tiến trình con
  giới hạn bộ nhớ, CPU và thời gian — PDF dựng có ý đồ không làm treo dịch vụ), lưu ở bảng mới `core.file_texts`
  (không vai trò người dùng nào đọc được) để dựng lại chỉ mục không phải đọc lại tệp; tệp tải lên trước đó cũng được
  đọc bù. Văn bản hạn chế không đưa nội dung vào chỉ mục. Kết quả chỉ khớp nội dung có nhãn "Khớp trong nội dung".
  Bản scan không có lớp chữ được đánh dấu để dành OCR (F4.1). `make seed`: văn bản đến mẫu có tệp PDF tiếng Việt
  thật thay cho tệp rỗng (#36).
- Tìm kiếm: mọi từ trong câu tìm phải khớp (trước đây Meilisearch bớt dần từ khi ít kết quả, nên một công văn dài
  chỉ chứa vài từ phổ biến cũng hiện ra). **Đổi API:** `GET /api/search` bỏ `offset` / `next_offset`, thay bằng
  `cursor` / `next_cursor` — vị trí trang sau mã hóa, gắn với người tìm và câu tìm, để không đếm ngược ra số văn
  bản mình không được đọc có chứa một từ (#36).
- `make smoke` thêm 2 kiểm tra (tổng 40): tìm được công văn theo chữ chỉ có trong tệp PDF; tệp của văn bản hạn chế
  không bị đọc chữ, không tìm được theo nội dung. `make e2e`: chuyên viên tìm văn bản bằng chữ trong tệp PDF (#36).
- Màn demo kiểm dịch (F3.1, nguyên lý (iv)): `make demo-kiem-dich` chạy dưới một phút. Tệp sạch qua; tệp EICAR bị
  ClamAV chặn ở cửa ngõ, không được lưu (không có dòng trong `core.files`); lần chặn nằm trong sổ kiểm toán, được neo ra ngoài CSDL rồi kiểm lại cả
  chuỗi. Kịch bản trình bày và câu hỏi hay gặp ở `docs/demo-script.md` (chỗ ghi đủ 4 màn nguyên lý). Sổ kiểm toán
  hiện mẫu mã độc, cỡ tệp của tệp bị chặn (tên tệp vẫn ẩn). `make smoke` kiểm thêm dòng sổ của lần chặn (tổng
  41); `make e2e` thêm kịch bản văn thư tải tệp nhiễm, lãnh đạo xem lần chặn trong sổ (#37). Trang tiếp nhận hiện
  đúng mẫu mã độc của tệp bị chặn (trước đó chỉ hiện thông báo chung).
- Dashboard điều hành (F3.11) cho lãnh đạo đơn vị, trang **Điều hành**: văn bản đến chưa xong, quá hạn, khẩn chưa
  xong, thời gian xử lý trung bình (từ vào sổ đến khi xong, tỉ lệ đúng hạn); biểu đồ Apache ECharts văn bản đến
  theo trạng thái, đang xử lý và quá hạn theo phòng chủ trì, thời gian xử lý và văn bản đi phát hành theo tháng,
  kèm bảng số. Số liệu từ bốn view chỉ có số đếm (`office.v_document_counts`, `v_overdue_by_department`,
  `v_processing_time`, `v_outgoing_by_month`) qua Hasura, theo đúng thuê ước trong token; vai trò khác không đọc
  được. Văn bản hạn chế không vào phép chia nào, chỉ có con số tổng, để không ai trừ ra được trạng thái của chúng.
  `make smoke` thêm 2 kiểm tra (tổng 43), kiểm số chia khớp đúng văn bản lãnh đạo đọc được; `make e2e` thêm kịch
  bản lãnh đạo xem dashboard, văn thư không có mục này (#38).
- Sao lưu và khôi phục (F3.4): `make backup` sao lưu mọi CSDL (dữ liệu nghiệp vụ, Keycloak, Flowable) và toàn bộ
  tệp SeaweedFS, kể cả mốc neo sổ kiểm toán, vào kho restic 0.19.1 mã hóa ở `MOC_BACKUP_DIR`; lần sau chỉ thêm phần
  đổi. `make restore` dừng Mộc, thay CSDL và tệp bằng lượt mới nhất (hỏi lại trước), ghi lần khôi phục vào sổ kiểm
  toán (`system.restored`) rồi chạy lại. `python3 scripts/moc.py backup create --keep N | list | check | restore
  [LƯỢT]`. Lúc sao lưu, `svc-files` và SeaweedFS tạm dừng vài giây để mốc neo trong bucket khớp CSDL. Biến mới
  trong `.env`: `MOC_BACKUP_PASSWORD` (mất là mất bản sao lưu), `MOC_BACKUP_DIR`. CI diễn tập mỗi pull request: sao
  lưu, xóa volume CSDL và tệp, khôi phục, rồi smoke và `make audit`. Test CSDL thêm 2: dump rồi restore giữ nguyên
  chuỗi băm, dòng `system.restored` nối chuỗi (#39).
- Két bí mật OpenBao 2.7.1 (F3.2): dịch vụ `openbao` trong profile core. `svc-files`, `svc-workflow` không còn nhận
  khóa S3, khóa quản trị Hasura, khóa Meilisearch, khóa Actions, mật khẩu Flowable, khóa Centrifugo, client secret qua
  biến môi trường: lúc khởi động mỗi dịch vụ đăng nhập két bằng AppRole riêng (`role_id`/`secret_id` trong volume chỉ
  nó gắn, két cấp secret_id mới mỗi lần khởi động) và chỉ đọc được phần của mình. Static seal: khởi động lại là tự
  mở khóa. Khóa transit `moc-files` để dành cho mã hóa tệp văn bản hạn chế. Két ghi sổ mọi lần truy cập ra
  `docker compose logs openbao`. Két nằm riêng mạng nội bộ `secrets` với hai dịch vụ. Lần đầu két cấu hình bằng
  token root rồi thu hồi; về sau chỉ dùng token khởi động không sửa được policy. Biến mới trong `.env`: `MOC_OPENBAO_SEAL_KEY` (đổi sau khi khởi tạo thì két không mở được). `make
  demo-ket-bi-mat` (màn (iv), cũng là bước CI); `make smoke` thêm 2 kiểm tra (tổng 45): két đã mở khóa, dịch vụ
  không có bí mật nào trong biến môi trường, AppRole không đọc chéo. Giới hạn: `.env` vẫn là nguồn bí mật, phần mềm
  thượng nguồn vẫn đọc từ biến môi trường, két chưa có TLS và chưa nằm trong `make backup` (#40).
- GitOps và tự phục hồi (F3.3): `scripts/reconcile.py` (`make reconcile`) đưa hệ thống đang chạy về đúng trạng thái
  khai báo, mỗi lần gọi một lượt; tệp mẫu systemd timer 60 giây trong `ops/systemd/` (cài lên máy chủ, không gắn
  socket Docker vào container nào). Dịch vụ khai trong compose mà mất container hoặc đã dừng thì dựng lại, unhealthy
  thì khởi động lại. Đặt `MOC_GITOPS_DIR` (bản sao git riêng của reconciler) thì reconciler kéo nhánh
  `MOC_GITOPS_BRANCH` (mặc định `deploy`): có commit mới, hoặc tệp đã cài bị sửa tay, thì dựng image của commit đó rồi
  cài lại đúng commit vào thư mục cài; cài hỏng giữa chừng thì cài lại commit cũ; commit áp lỗi thì đợi commit kế
  tiếp. Lượt reconciler bỏ qua khi đang sao lưu, khôi phục, `make install` (chung một khóa), khi lần khôi phục trước
  dừng giữa chừng hoặc có dịch vụ đang tạm dừng có chủ ý. `install.sh` kiểm đủ tệp trước khi xóa gì ở bản cài và bị
  ngắt giữa chừng thì cài lại được. APISIX chỉ giữ địa chỉ DNS của
  dịch vụ 5 giây để thấy ngay container vừa dựng lại. `make demo-tu-phuc-hoi` (màn (iv), cũng là bước CI); bước CI
  GitOps với repo git cục bộ; `make smoke` thêm 1 kiểm tra (tổng 46): một lượt reconciler không thấy gì phải sửa.
  Giới hạn: áp một commit là cài lại toàn bộ (Mộc dừng khoảng một phút), image cũ không tự xóa, `.env` không do git
  quản (#41).
- Lập hồ sơ và nộp lưu — dữ liệu nóng sang lạnh (F3.8, màn (i)). Bảng `office.case_files`,
  `office.case_file_documents`: chuyên viên, tổ trưởng lập hồ sơ của phòng mình, đưa vào văn bản đã xử lý xong mà mình
  đọc được và thuộc phòng mình (văn bản hạn chế không vào), đóng hồ sơ; ngày đóng do CSDL đặt, hồ sơ rỗng không đóng
  được, hồ sơ đã nộp lưu không sửa được nữa. svc-files nộp lưu hồ sơ đóng từ `MOC_ARCHIVE_AFTER_DAYS` ngày (mặc định
  365): kiểm băm tệp nóng, ghi gói `cold/<đơn vị>/case/<hồ sơ>/` gồm ba bảng Parquet (DuckDB 1.5.6, lược đồ cố định),
  tệp gốc và manifest có SHA-256 từng phần, mọi tên theo băm, khóa ghi COMPLIANCE theo thời hạn bảo quản; đọc lại cả
  gói, so băm, rồi hàm SQL `office.archive_case_file` (một giao dịch, khóa dòng, CSDL lệch với gói thì không đổi gì)
  gỡ dòng thời gian, liên kết tệp và ghi `case_file.archived` vào sổ kiểm toán. Giao việc và dòng văn bản rút gọn ở
  lại: ai đọc được vẫn đọc được, vẫn tìm thấy, cổng xác thực vẫn trả "khớp". Phòng đọc
  `GET /api/case-files/{id}/archive` đọc lại gói, kiểm băm với CSDL, chỉ trả văn bản người gọi đọc được, ghi
  `case_file.read`. Sổ kiểm toán thấy ký hiệu hồ sơ, băm gói, không thấy tên hồ sơ. `make demo-nong-lanh` (màn (i),
  cũng là bước CI); `make smoke` thêm 1 kiểm tra (tổng 47). Giới hạn: chưa có giao diện lập hồ sơ, phòng đọc chưa xem
  được tệp (cùng đợt F3.7), lớp chữ PDF của văn bản đã nộp lưu không còn trong chỉ mục tìm kiếm (#42).
- Phả hệ dữ liệu và kiểm chất lượng (F3.9, màn (iii)): mỗi lượt nộp lưu là một run OpenLineage 2-0-2 với 4 bước (tệp,
  bảng, manifest, CSDL), tên dataset theo quy ước `postgres://…/moc.<schema>.<bảng>`, `s3://<bucket>/<key>`; sự kiện
  lưu trong bảng chỉ thêm `core.lineage_events` (lãnh đạo, văn thư đọc của đơn vị mình), gửi thêm tới Marquez khi đặt
  `MOC_OPENLINEAGE_URL`. Bảng Parquet được kiểm số dòng = CSDL và cột bắt buộc không null trước khi ghi gì sang kho
  lạnh; trượt thì dừng, sự kiện FAIL nằm lại trong phả hệ. `make demo-pha-he` (cũng là bước CI); `make smoke` thêm 1
  kiểm tra (tổng 48). Chưa dựng Marquez trong compose (#43).
- Tab "Lịch sử" trên trang văn bản (F3.5): ai đọc được văn bản thì xem từng lần sửa — ai, lúc nào, trường nào từ gì
  sang gì — đọc từ sổ kiểm toán qua view `office.document_history` (chính văn bản, tệp, giao việc, lần vào hồ sơ;
  không gồm danh sách được xem văn bản hạn chế); trường nội dung chỉ báo là đã đổi, không có hash. Cách hiện dòng sổ dùng chung với trang Sổ kiểm toán
  (`useAuditFormat`) (#44).
- Giám sát gọn (F3.13): APISIX bật plugin `prometheus` (cổng chỉ số 9091 nội bộ); dịch vụ `prometheus` (v3.15.0,
  không mở cổng) và `grafana` (13.2.3, chỉ `127.0.0.1:MOC_GRAFANA_PORT`, không tài khoản, chỉ xem) trong profile core;
  bảng điều khiển "Mộc — cổng API" nạp sẵn; `make smoke` +1 (tổng 49) (#45).
- Hội tụ IT/OT rút gọn (F3.10, màn (ii)): profile `iot` với context broker NGSI-LD Scorpio 6.0.2 và CSDL PostGIS
  riêng (không mở cổng); `svc-workflow` giữ subscription `temperature>MOC_OT_THRESHOLD` trong tenant NGSI-LD của mỗi
  đơn vị và nhận thông báo ở `POST /ot/notify/{mã đơn vị}` (token HMAC riêng từng đơn vị): cảm biến vượt ngưỡng →
  dự thảo văn bản đi "Báo cáo sự cố" (Báo cáo, Khẩn) từ mẫu cho chuyên viên phụ trách, sự kiện `ot.alarm`, thông báo
  khẩn; còn dự thảo chưa trình của cùng cảm biến thì không dựng thêm. Cảm biến giả lập `ot/sensor.py` (dịch vụ chạy
  một lần `ot-sensor`), `make demo-it-ot` (cũng là bước CI), nhãn sự kiện và thông báo trên giao diện (#46).
- Văn bản hạn chế truy cập (F3.7, màn (iv)): văn thư bật "Hạn chế người xem" trước khi tải tệp, tải lên
  `POST /api/files?restricted=true` chỉ nhận PDF đọc được, không mật khẩu (415 `restricted_pdf_only`; PDF phải nhập
  mật khẩu mới mở thì trạm quét chặn trước, 422 `unscannable` — mục Bảo mật). `svc-files` xin
  két OpenBao một khóa AES-256 riêng cho từng tệp (transit `moc-files`), mã hóa AES-GCM (gắn với đơn vị và tệp) rồi mới
  lưu: kho chỉ có bản mã `MOC1…`, CSDL chỉ giữ khóa đã bọc (`core.files.wrapped_dek`); bản phát hành của văn bản hạn
  chế cũng lưu mã hóa. Mở tệp: giải mã trong bộ nhớ, kiểm băm, đóng dấu tên người xem và giờ xem lên mọi trang, ghi
  `file.decrypted` vào sổ kiểm toán (không ghi được sổ thì không trả tệp), `Cache-Control: no-store`, không ETag; thư
  mục tạm của svc-files và của ClamAV là tmpfs. Bị gỡ khỏi danh sách là hết tải tệp mã hóa của văn bản, kể cả tệp
  chính mình tạo. Văn bản hạn chế không được công khai trích yếu ở cổng xác thực (ràng buộc
  `documents_restricted_private`; màn phát hành ẩn ô công khai). Danh sách người được xem: hàm `office.grant_document_access`,
  `office.revoke_document_access` (văn thư, lãnh đạo đơn vị; kiểm vai trò, đơn vị, người còn hoạt động; không tự gỡ
  mình), mỗi lần cấp, gỡ vào sổ kiểm toán; người phải làm bước quy trình kế tiếp được svc-workflow tự thêm; nhắc hạn,
  leo thang, báo quá hạn chỉ tới người có tên. CSDL giữ
  tệp khớp chế độ: văn bản hạn chế chỉ gắn tệp mã hóa và ngược lại, đã có tệp thì không đổi chế độ (trigger
  `document_files_sealed`, `documents_restricted_sealed`); tiếp nhận lệch chế độ bị trả về form (`not_sealed`,
  `sealed`). Giao diện: ô hạn chế ở màn tiếp nhận (khóa lại khi đã có tệp), nhãn "Đã mã hóa" ở tệp, mục "Người được
  xem" trên trang văn bản. Sao lưu gồm cả két (volume `openbao_data`, dừng két trong lúc chụp); diễn tập ở CI xóa cả
  két rồi kiểm tệp mã hóa từ trước vẫn mở được. `make demo-han-che` (cũng là bước CI), `make smoke` thêm 8 kiểm tra
  (tổng 57), e2e `han-che.spec.ts`. Không dùng cho bí mật nhà nước (#47).
- Liên thông văn bản trong hệ thống (F3.12): văn bản đi chọn thêm đơn vị nhận là đơn vị khác cùng dùng Mộc
  (`recipient_tenant_ids`; màn soạn có danh sách "Gửi trong hệ thống" từ view `office.dispatch_units`, tích thì tên tự
  vào ô nơi nhận). Phát hành → trigger ghi một dòng `pending` cho mỗi đơn vị nhận vào hộp thư đi `office.dispatches`
  ngay trong giao dịch phát hành, chụp mã tra cứu và băm bản phát hành; `svc-workflow` chuyển ngay (giới hạn 15 giây,
  lỗi không làm hỏng bước phát hành): `svc-files` chép bản PDF phát hành sang kho của đơn vị nhận qua API nội bộ `POST
  /internal/dispatch-file` (chỉ token dịch vụ, APISIX không định tuyến; so SHA-256 với `core.files`, băm nội dung văn
  bản và băm chụp lúc phát hành, quét ClamAV), rồi hàm `office.deliver_dispatch` chạy trong phiên của đơn vị nhận dựng
  văn bản đến `received` (cơ quan ban hành là tên đơn vị gửi, `source_id` trỏ về văn bản gửi) kèm tệp, ghi
  `office.document.arrived` bên nhận, `office.document.dispatched` bên gửi, sổ kiểm toán của cả hai đơn vị trong cùng
  giao dịch. Văn thư bên nhận (không có thì lãnh đạo đơn vị) nhận thông báo `document.incoming` đúng một lần. Gọi lại,
  chạy đua: chỉ mục `documents_source_once` chốt một văn bản đến cho mỗi văn bản gửi ở mỗi đơn vị; bên nhận đã tiếp nhận
  tay cùng văn bản thì nối vào (`duplicate`), không báo. Lỗi thì ghi `last_error`, thử lại sau 30 s·2^lần (tối đa 1
  giờ), vòng nền `MOC_DISPATCH_INTERVAL_S` (mặc định 30 giây); `svc-files` từ chối hẳn (tệp nguồn sai băm, đã sang kho
  lạnh, văn bản không còn phát hành, trạm quét chặn) thì `office.fail_dispatch` đánh dấu `failed`, không thử lại, không
  chặn nộp lưu; CSDL kiểm lại băm bản sao ở đơn vị nhận trước khi dựng văn bản đến. Văn bản hạn chế không liên thông
  (`documents_restricted_local` ở CSDL, kiểm lại ở `submitOutgoing`, ô bị khóa trên giao diện) vì tệp mã hóa gắn với đơn
  vị gửi; không gửi cho chính mình; văn bản còn dòng chờ chuyển thì chưa nộp lưu được. Mỗi bên chỉ thấy dòng liên thông
  qua văn bản của mình, văn bản bên kia vẫn cách ly. Giao diện: thẻ "Liên thông trong hệ thống" trên văn bản đi (trạng
  thái từng đơn vị, tự hỏi lại khi còn đang chuyển); văn bản đến có chip "Liên thông", thẻ "Nhận từ …" kèm mã xác thực
  của bên gửi và dòng "SHA-256 khớp bản phát hành". `make demo-lien-thong` (7 bước, cũng là bước CI), `make smoke` +1,
  e2e `lien-thong.spec.ts`, 19 test CSDL, svc-workflow +47, svc-files +26. Sổ kiểm toán hiện tên đơn vị nhận. Giới hạn:
  chưa gửi lại được dòng `failed`; danh sách đơn vị hiện cho mọi người dùng.
- Thêm đơn vị bằng một lệnh (F3.12): `python3 scripts/moc.py tenant create --code KTCK --name "Khoa Cơ khí"
  --department "VP=Văn phòng khoa" --admin quantrick` ghi đơn vị và phòng trong một giao dịch (sổ kiểm toán ghi người
  chạy lệnh), bật Organizations cho realm nếu chưa bật, tạo một Keycloak Organization cho đơn vị (thuộc tính
  `tenant_id`) và tài khoản quản trị đơn vị (mật khẩu tạm in một lần, lần đầu đăng nhập phải đổi mật khẩu và cài TOTP),
  đưa mọi tài khoản của đơn vị vào Organization, đợi danh bạ `core.users` có quản trị đơn vị. Kiểm mọi xung đột trước
  khi ghi; chạy lại được (giữ nguyên cái đã có); `--dry-run`, `--json`, `--reset-password`. `moc tenant list` và
  `moc tenant check [MÃ…]` (đơn vị ↔ Organization ↔ thành viên ↔ danh bạ; lệch thì thoát 1 kèm cách sửa). Token không
  đổi: đơn vị vẫn lấy từ thuộc tính `tenant_id`, Organization chỉ là lớp thành viên. Không tách bucket theo đơn vị (khóa
  ghi của bucket lạnh đặt sai là vĩnh viễn; cách ly đã có ở CSDL, tiền tố tệp, quyền đọc) — lý do trong
  `docs/mo-hinh-du-lieu.md` §1. Bước CI thêm đơn vị thứ ba, chạy lại, đối chiếu; `make smoke` +1 (tổng 60); test
  đơn vị `scripts/tests/` chạy trong `make test`.

### Đã sửa đổi
- Văn thư không còn ghi thẳng bảng văn bản (`insert_office_documents_one`, `update_office_documents`) lẫn bảng tệp
  đính kèm (`insert_office_document_files_one`, `delete_office_document_files`): văn bản đến kèm tệp vào qua Action
  `receiveIncoming(data: jsonb!)`, nên không đi vòng được lớp kiểm của svc-workflow. Sửa văn bản đến chưa vào sổ
  không còn qua GraphQL (giao diện chưa từng dùng). Migration dọn văn bản đến đã có (khoảng trắng thừa, ký tự ẩn,
  dạng Unicode tổ hợp) trước khi thêm ràng buộc; dòng nào còn sai thì cảnh báo kèm mã văn bản. Sổ kiểm toán ghi lần tiếp nhận là
  `svc-workflow` làm thay văn thư, kèm đúng người bấm. Ngày "hôm nay" của giao diện tính theo giờ Việt Nam (#34).
- Rà soát bản tóm tắt OLP 2026: sửa nguồn tham khảo, phân biệt yêu cầu BTC với đề xuất của đội,
  làm rõ giới hạn kiểm tra PoF và phạm vi phát triển mã nguồn riêng.
- README: phát biểu bài toán sản phẩm giải quyết (bài toán nền tảng và bài toán nghiệp vụ).
- Đổi bài toán nghiệp vụ từ luồng phê duyệt đề xuất sang quản lý văn bản đến / đi: README, kế hoạch
  phát triển (Phase 2–4, phân công, rủi ro), phân tích đề §6.2.
- CONTRIBUTING và mẫu pull request: quy ước nhánh, commit và phạm vi theo `docs/git_flow.md`.
- README, NOTICE, đặc tả sản phẩm §0: phát biểu sản phẩm theo thứ tự lõi trước, ứng dụng sau; nêu lớp
  tin cậy dùng chung của lõi (danh tính, quét mã độc, sổ kiểm toán chuỗi băm, API xác thực).
- Sổ kiểm toán chuỗi băm và cổng xác thực văn bản chuyển từ Should (Phase 3) lên Must (Phase 2): mã
  F3.5 → F2.12, F3.6 → F2.13 trong kế hoạch, đặc tả và mô hình dữ liệu.
- Kế hoạch §4: thay bảng RAM bằng danh mục tài nguyên cần có — con người, hạ tầng, tài khoản, dữ liệu,
  kiến thức, chi phí, việc phải có trước `v0.1.0`.
- Đổi tên sản phẩm từ DX-Lab sang **Mộc** (theo chữ "đóng mộc" — đóng dấu), vì "DX-Lab" là tên Trạm
  thực hành số trong chủ đề cuộc thi và trùng ứng dụng của một đội khác. Tên kỹ thuật đổi theo:
  Compose project, mạng và CSDL mặc định `moc`; biến môi trường `DXLAB_*` thành `MOC_*` (ai đã tạo
  `.env` thì sửa theo); gói phát hành `moc-<phiên bản>.tar.gz`. README và mẫu issue trỏ về repo
  `HIT-Champion/HVL`.
- Kế hoạch: dời `v0.1.0` từ 21/10 sang 25/10 vì Phase 1 chưa bắt đầu; Phase 2 thành 26/10–08/11,
  Phase 3 thành 09–20/11, Phase 4 (cũng là đệm) thành 21–25/11; giữ nguyên ngày đóng băng và ngày nộp.
- Hasura chờ `completeTask` tới 90 giây (trước là 30): phát hành gồm cấp số, dựng PDF, quét, lưu kho, máy chậm có thể
  quá 30 giây. Cổng APISIX chờ Hasura 100 giây (mặc định 60).
- `make seed` tạo Organization cho hai đơn vị mẫu (`cntt`, `kt`) và đưa tài khoản mẫu vào (cùng hàm với
  `moc tenant create`, chạy lại thì giữ nguyên); realm bật `organizationsEnabled` — bản đã dựng thì `make seed` tự bật,
  không cần `make reset`.

### Đã sửa lỗi
- Bấm lại khi hoàn thành việc lâu (phát hành) hay hai lần gọi chen nhau không còn ghi hai lần (hai phân công, hai lần
  cấp số và dựng PDF): svc-workflow cho các lần gọi cùng một việc chạy lần lượt, lần sau thấy việc đã xong; CSDL có
  chỉ mục duy nhất `document_events_task_once` theo `task_id` của sự kiện, nên lần ghi thứ hai (ví dụ từ bản sao
  dịch vụ khác) bị chặn cả giao dịch và svc-workflow chỉ hoàn thành nốt việc trong Flowable. Sự kiện ghi kèm biến
  gửi Flowable (`data.flow`): bấm lại sau lỗi "Đã lưu, nhưng chưa chuyển được bước tiếp" đi đúng nhánh đã ghi, kể cả
  khi lần bấm lại chọn khác, và việc xử lý văn bản đến không còn kẹt ở lần bấm lại. Dữ liệu cũ đã trùng thì
  migration cảnh báo và chỉ chặn từ sau dòng trùng cuối.
- Vào sổ, trình văn bản đi bấm đúp, hay trùng lúc với job đối soát, không còn khởi chạy hai quy trình cho một văn bản
  (mỗi bước hai việc, việc này đè trạng thái của việc kia): quy trình chỉ được gắn khi văn bản chưa có
  (`update … where process_id is null`); lần gọi thua theo quy trình đã gắn và hủy quy trình nó vừa khởi chạy (hủy
  không được thì nhật ký ghi `office.process.duplicate_left`).
- Quản trị đơn vị mở app gặp lỗi (hộp việc chỉ dành cho người xử lý văn bản): trang đầu của vai trò này là Sổ kiểm
  toán, và sổ không còn nút "Mở văn bản" (quản trị đơn vị không đọc nội dung nghiệp vụ). Trang văn bản tải lỗi thì hiện
  lỗi kèm nút thử lại thay vì trang trống.
- Ngày giờ trên giao diện luôn theo giờ Việt Nam, kể cả trên máy đặt múi giờ khác; ngày không kèm giờ (ngày ban hành,
  hạn) không còn lệch một ngày ở múi giờ âm.
- Danh sách văn bản đến, văn bản đi không còn cắt ở 200 dòng (văn bản cũ, dễ quá hạn, bị ẩn): mỗi lần 50 dòng, nút
  "Xem thêm". Có văn bản mới vào sổ hay đổi trạng thái giữa hai lần bấm thì không lặp, không sót dòng; "Xem thêm" lỗi
  thì báo ở góc màn hình, bảng đang xem vẫn còn.
- Lưu dự thảo không còn sửa được (đã trình, đã đổi trạng thái) không còn báo "Đã lưu" khi CSDL không ghi gì.
- Hết phiên đăng nhập giữa lúc soạn dự thảo hay tiếp nhận văn bản: phần đang nhập được giữ trong phiên của trình
  duyệt (sessionStorage) và khôi phục khi quay lại; văn bản hạn chế không được giữ. Tự rời trang (chuyển sang trang
  khác của ứng dụng) hay đăng xuất thì bỏ phần đang nhập, mở lại trang soạn là bắt đầu mới.
- e2e thông báo tìm văn bản trong đúng hộp việc, không khớp nhầm thông báo nổi; test tích hợp tìm kiếm của svc-files
  gắn tệp mã hóa vào văn bản hạn chế như ràng buộc của F3.7.
- Văn bản hạn chế giao cho người không đọc được: lãnh đạo nhận việc chỉ đạo, tổ trưởng nhận phân công mở văn bản ra
  "không tìm thấy". Nay người phải làm việc đang mở được thêm vào danh sách được xem; `completeTask` từ chối (403
  `restricted`) người không đọc được văn bản thay vì cho làm mù (#47).
- `scripts/license-header.sh` bỏ qua im lặng các tệp `.vue`, `.html`, `.xml`, `.bpmn`, `.css`,
  `.scss`, `.mjs`, `.graphql`, `.lua` — các tệp này giờ được kiểm tra và tự chèn header; loại tệp
  chưa hỗ trợ được in ra dưới dạng cảnh báo.

### Bảo mật
- Action GitHub trong CI và quy trình phát hành ghim theo SHA commit, image công cụ CI ghim theo digest;
  workflow CI chỉ có quyền đọc kho.
- Xác thực hai bước TOTP (F1.1): đăng nhập trình duyệt bắt buộc mã với văn thư, lãnh đạo phòng, lãnh đạo đơn
  vị, quản trị đơn vị (chưa cài thì Keycloak bắt cài ở lần đăng nhập đầu); vai trò khác chỉ hỏi mã nếu đã tự cài.
  `make seed` cài sẵn TOTP cho tài khoản mẫu, `make totp` in mã; `make smoke` thêm 2 kiểm tra, e2e đăng nhập kèm mã.
- Client `moc-cli` (lấy token bằng mật khẩu cho kịch bản dòng lệnh) hỏi mã TOTP theo đúng quy tắc của trình duyệt,
  tham số `otp`, thay vì bỏ qua bước này — không còn là đường vòng qua xác thực hai bước. Kịch bản trong `scripts/`
  tự tính mã từ `MOC_DEMO_TOTP_SECRET`; kịch bản và e2e ghi chung một sổ mã đã dùng (`tests/e2e/.otp-used.json`, theo
  địa chỉ hệ thống) nên không gửi lại mã đã dùng — Keycloak đếm mỗi mã bị từ chối là một lần đăng nhập sai, đủ 10 lần
  thì khóa tài khoản; mã vẫn bị từ chối thì đợi quá 1 giây mới thử mã kế. `make smoke` thêm 1 kiểm tra (tổng 58). Realm chỉ
  nạp ở lần khởi động đầu: stack đã dựng phải `make reset` (xóa dữ liệu) hoặc sửa tay luồng `moc-cli-direct-grant`
  trong trang quản trị Keycloak (auth/README.md).
- ClamAV báo tệp có mật khẩu (zip, 7z, rar, PDF phải nhập mật khẩu mới mở) và tệp giải nén vượt giới hạn quét (bom
  nén, lồng quá sâu) thay vì coi là sạch (`AlertEncrypted`, `AlertExceedsMax`): svc-files chặn (422 `unscannable`,
  kèm cách sửa), ghi `file.rejected` vào sổ kiểm toán với nhãn "Chặn tệp không quét được". PDF chỉ khóa quyền sửa,
  in (mở không cần mật khẩu) vẫn nhận.
- Thông báo về văn bản hạn chế không còn mang số ký hiệu, trích yếu, cơ quan ban hành: svc-workflow chỉ gửi nhãn,
  trigger CSDL gọt nội dung cho mọi đường ghi và gọt cả thông báo đã gửi khi văn bản chuyển sang hạn chế. Tóm tắt dòng
  sổ kiểm toán (`overview`) về văn bản hạn chế mà người xem sổ không đọc được chỉ còn tên trường, không còn giá trị
  (hàm `office.audit_overview_seen`) (#47).

<!--
Mẫu cho bản phát hành kế tiếp:

## [0.1.0] - 2026-10-xx

### Đã thêm
### Đã sửa đổi
### Đã loại bỏ
### Đã sửa lỗi
### Bảo mật
-->
