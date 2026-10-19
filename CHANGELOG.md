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

### Đã sửa đổi
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

### Đã sửa lỗi
- `scripts/license-header.sh` bỏ qua im lặng các tệp `.vue`, `.html`, `.xml`, `.bpmn`, `.css`,
  `.scss`, `.mjs`, `.graphql`, `.lua` — các tệp này giờ được kiểm tra và tự chèn header; loại tệp
  chưa hỗ trợ được in ra dưới dạng cảnh báo.

### Bảo mật
- Action GitHub trong CI và quy trình phát hành ghim theo SHA commit, image công cụ CI ghim theo digest;
  workflow CI chỉ có quyền đọc kho.
- Xác thực hai bước TOTP (F1.1): đăng nhập trình duyệt bắt buộc mã với văn thư, lãnh đạo phòng, lãnh đạo đơn
  vị, quản trị đơn vị (chưa cài thì Keycloak bắt cài ở lần đăng nhập đầu); vai trò khác chỉ hỏi mã nếu đã tự cài.
  Client `moc-cli` của kịch bản dòng lệnh bỏ qua bước này và phải tắt trên server thật. `make seed` cài sẵn
  TOTP cho tài khoản mẫu, `make totp` in mã; `make smoke` thêm 2 kiểm tra, e2e đăng nhập kèm mã.

<!--
Mẫu cho bản phát hành kế tiếp:

## [0.1.0] - 2026-10-xx

### Đã thêm
### Đã sửa đổi
### Đã loại bỏ
### Đã sửa lỗi
### Bảo mật
-->
