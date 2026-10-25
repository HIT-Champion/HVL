# Lịch sử thay đổi

Mọi thay đổi đáng chú ý của Signet (trước 23/10/2026 tên là Mộc) được ghi lại trong tệp này.

Định dạng theo [Keep a Changelog 1.1.0](https://keepachangelog.com/vi/1.1.0/),
đánh phiên bản theo [Semantic Versioning 2.0.0](https://semver.org/lang/vi/).

## [Chưa phát hành]

### Đã thêm
- Trợ lý hỏi đáp (F4.2): nút "Hỏi về văn bản này" ở trang chi tiết mở trang Hỏi đáp chỉ hỏi trong văn bản đó
  (`document_id` của `POST /api/documents/ask` — một điều kiện lọc nối AND sau phạm vi vai trò, hậu kiểm bằng token như
  mọi lượt, nên chỉ thu hẹp); nhãn nguồn "số ký hiệu · tr. n" mở tệp PDF trong khung xem của trình duyệt đúng trang đó
  (`#page=n`); câu hỏi có số ký hiệu, ngày hay cụm trong ngoặc kép tìm lai nghiêng về từ khóa (tỷ trọng nghĩa tối đa
  0,2, câu khác giữ `MOC_ASK_SEMANTIC_RATIO`). Test svc-files +29, office +4, e2e thêm bước trong `hoi-dap.spec.ts`.
- Bản phát hành tự kiểm gói trước khi lên trang Release: `scripts/kiem_goi.py` (`make release` ở máy, bước mới của
  `release.yml` ngay sau bước đóng gói) giải nén chính `signet-X.Y.Z.tar.gz` vào thư mục tạm và chặn tệp không được
  phát hành — tệp môi trường thật (chỉ tệp mẫu `*.example`), khóa riêng (theo tên và khối PEM), tài liệu nội bộ
  `*.local*`, `COMMIT.md`, `publics/`, `node_modules`, `__pycache__`, dữ liệu chạy, tệp lớn hơn 5 MiB; kiểm `LICENSE`,
  `NOTICE`, header giấy phép và `REUSE.toml` cho từng tệp (`license-header.sh` nay kiểm được thư mục ngoài git, trước
  đó qua mà không xét tệp nào), `.sha256`, thư mục gốc `signet-X.Y.Z/`. Gói hỏng thì `make release` gỡ thẻ vừa gắn và
  xóa gói. Tệp `VERSION` do `git archive` điền thẻ (`.gitattributes`, export-subst): cài từ gói không còn phải đặt tay
  `MOC_VERSION`. Test scripts +27 (`docs/git_flow.md` mục 6).
- Trang đăng nhập Keycloak mang thương hiệu Signet (theme `signet`, `platform/keycloak/themes/`), chung cho Văn phòng
  điện tử, P.A.R.A, Bảng tin: kế thừa `keycloak.v2` của Keycloak 26, không viết lại template — chỉ CSS (màu, phông của
  Văn phòng điện tử, nền, bo góc, cỡ chữ trên điện thoại; chế độ sáng/tối theo máy của theme cha) và logo của Văn
  phòng điện tử, cũng làm biểu tượng tab. Realm đặt `loginTheme: signet`, compose gắn thư mục chỉ đọc, CSP giữ nguyên.
  Bản cài cũ (realm không nạp lại): `python3 scripts/moc.py realm theme` sau khi nâng cấp — chỉ đặt khi realm còn dùng
  theme mặc định, báo lỗi nếu container chưa gắn thư mục theme (`docs/trien-khai.md`, mục Nâng cấp tay). Test scripts
  +14.
- Trang Danh mục ứng dụng (`/ung-dung`) trong Văn phòng điện tử, mục "Ứng dụng" ở thanh bên cho mọi vai trò: các ứng
  dụng chạy trên lõi — hai ứng dụng có sẵn trong lõi (phiên bản lõi từ `/api/status`) và ứng dụng cắm bằng `moc app
  install` — với tên, mô tả, nút Mở, phiên bản, lúc cài; lãnh đạo, quản trị đơn vị thấy thêm băm manifest (SHA-256 tệp
  `app.yaml` lúc cài, rút gọn, có nút chép) và ứng dụng đã gỡ. Đọc khung nhìn hẹp `core.app_catalog` (migration
  1792281603400): không có manifest (image, cổng, biến môi trường), không schema; `core.apps` vẫn không vào GraphQL,
  không vai trò nào ghi. `/ung-dung` thành đường giữ chỗ của `moc app`; `make demo-cai-ung-dung` kiểm danh mục sau khi
  cài, cài lại, gỡ. Test office +8, db +6, e2e +1.
- Mốc neo sổ kiểm toán công khai, người ngoài tự kiểm được (đóng #56): két ký mỗi mốc bằng khóa Ed25519 `moc-anchor`
  trong transit (két sinh, không cho xuất; chỉ `svc-files` được ký và đọc khóa công khai) trên thông điệp
  `signet-anchor-v1` gồm số dòng, hash, giờ kho ghi mốc, URL hệ thống; chữ ký tách rời nằm cạnh mốc trong bucket lạnh,
  mốc cũ không chữ ký vẫn hợp lệ. `GET /api/verify/ca.pem` (#56) và `GET /api/verify/anchor-key.pem` trả chứng thư CA
  nội bộ và khóa công khai, không cần token, két chưa có thì 404 (WAF gỡ đúng luật đuôi `.pem` trên hai đường này, loại
  trừ 10050). Trang `/xac-thuc` có liên kết "Tải chứng thư CA (minh họa)" trong khối chữ ký số và khối khóa ký mốc neo,
  kèm vân tay SHA-256 trình duyệt tự tính. `moc audit anchor --to` ghi kèm chữ ký, vân tay khóa; `--publish THƯ_MỤC`
  commit vào một bản sao git (tác giả "Signet anchor") rồi đẩy lên nếu có remote, không bao giờ ép; timer mẫu
  `platform/systemd/moc-anchor-publish.*` chạy mỗi giờ. `moc audit verify --anchors` kiểm chữ ký bằng Ed25519 viết thuần
  Python (`scripts/anchor_sig.py`, chạy được độc lập ở máy người ngoài); dòng chữ ký sai, hay dòng chưa ký đứng sau dòng
  đã ký (chữ ký bị gỡ), là lỗi, nên két đã có khóa thì `--to`/`--publish` không ghi mốc chưa ký. Sổ đăng ký in ra có mốc
  neo mới nhất ở chân trang. Dựng kho công khai cấm đẩy ép, khóa triển khai, kiểm bằng OpenSSL 3: `docs/van-hanh.md` mục
  "Mốc neo công khai"; két cũ nâng cấp tay như mục Két bí mật. Test (đếm tĩnh): svc-files +28, scripts +35,
  giao diện +5.
- Tự chẩn đoán H-P-D-I (`/tu-chan-doan`) thêm hình dạng theo giáo trình DX-OS mục 2.4 (TS. Tạ Tuấn Anh, CC BY 4.0):
  tỷ trọng `[P]`, `[D]`, `[I]` tối đa 30 % quy từ mức tự đánh giá, `[H]` là phần dư; xếp vào một trong bốn nguyên mẫu
  (Mũi giáo phân mảnh, Cánh diều lệch tâm, Ảo giác công nghệ, Kim cương toàn vẹn) hoặc "đang chuyển tiếp", ngưỡng
  ghi kèm câu giáo trình ở `docs/tu-chan-doan.md` §3. Cảnh báo "rác vào, rác ra" khi `[I]` vượt `[D]` từ 1 mức hoặc
  hình dạng là Ảo giác công nghệ: khuyên tạm dừng mở rộng `[I]`, dẫn tới cờ kiểm chất lượng số liệu ở Phả hệ số liệu.
  Chỉ để định hướng, không phải điểm DTI. Test office +3, e2e thêm bước trong `tu-chan-doan.spec.ts`.
- Cờ chất lượng dữ liệu trên trang Điều hành và Phả hệ số liệu (F3.9, F3.11): khung nhìn `office.report_checks`
  (migration 1792281603300) tính trong CSDL lúc truy vấn 5 luật trên số của trang Điều hành — tổng theo trạng thái
  khớp số văn bản đến trong bảng, tổng theo phòng khớp số đang xử lý (văn bản chưa rõ phòng chủ trì là cảnh báo),
  thời gian xử lý tính đủ văn bản đã xong, khóa ghép số không trùng không rỗng, không khung nhìn `office.v_*` nào xuất
  (trượt) hay đọc (cảnh báo) cột thông tin cá nhân theo catalog, kể cả qua view lồng — mỗi luật Đạt / Cảnh báo /
  Trượt kèm số liệu; chỉ lãnh đạo đơn vị đọc, đúng đơn vị mình. Cờ đặt cạnh nút "Nguồn số liệu" của từng biểu đồ
  (truy vấn riêng, hỏi sau khi biểu đồ đã có số nên không làm chậm biểu đồ). Trang Phả hệ thêm mục Kiểm chất lượng
  số liệu, cờ từng khung nhìn, cờ của lượt nộp lưu và từng bước theo đúng assertion svc-files đã ghi (không tính
  lại); lượt bị dừng vì trượt kiểm hiện cờ Trượt kèm mục trượt. Test db +7, office +8; smoke thêm 2 kiểm.
- Sơ đồ cảm biến kho (F3.10): trang `/cam-bien` của Văn phòng điện tử vẽ mặt bằng kho lưu trữ bằng SVG (không tile,
  không thư viện bản đồ, CSP giữ nguyên), mỗi phòng tô màu theo số đo mới nhất của cảm biến khai cùng mã phòng
  (Property NGSI-LD `room`, `sensor.py --room`) so với `MOC_OT_THRESHOLD`, kèm ba cờ chất lượng dữ liệu OT tính ở
  `svc-workflow`: mất tín hiệu (quá `MOC_OT_STALE_MIN` phút, mặc định 10, không có số đo mới), ngoài dải (không phải
  số hoặc ngoài −55…125 °C), trùng `observedAt` (số đo mới nhất cùng giờ đo với một lần đo khác trong 10 lần gần
  nhất). Trình duyệt không gọi broker: Hasura Action chỉ đọc `otSensorMap` cho văn thư, chuyên viên, lãnh đạo phòng,
  lãnh đạo đơn vị (các vai trò đọc được dự thảo "Báo cáo sự cố"), `svc-workflow` chỉ hỏi tenant NGSI-LD của đơn vị
  trong phiên; chưa bật profile `iot` thì trang báo "Chưa bật cảm biến", không lỗi 5xx. `sensor.py` thêm `--late`,
  `--frozen-clock` để giả lỗi dữ liệu; `make demo-it-ot` thêm bước 7 kiểm cờ, cách ly đơn vị. Test svc-workflow +32,
  office +8.
- Kịch bản nâng cấp bản cài `scripts/nang_cap.sh` và job CI tập nâng cấp `.github/workflows/nang-cap.yml` (#182).
  `nang` dựng image bản mới, kéo image dựng sẵn máy chưa có khi trang còn chạy, sao lưu bằng bản đang chạy, cài,
  chạy, đặt client và theme của realm rồi kiểm; `lui` cài lại bản cũ và khôi phục đúng lượt sao lưu đó; `ket` nâng két
  cũ (khóa `moc-anchor`, PKI, policy), lỗi giữa chừng thì gỡ listener tạm, hủy lượt tạo token dở, token root còn nằm
  lại thì in lệnh thu hồi; `kiem` chạy hết các mục rồi báo mục trượt: dữ liệu không ít đi, dòng sổ cuối còn nguyên
  băm, dịch vụ khỏe, phiên bản trên `/api/status`, realm, `audit verify`, smoke (thử lại một lần, chỉ khi trượt ở bước
  hỏi đáp). Job cài thẻ phát hành trước, nạp mẫu, tạo văn bản hạn chế, nâng lên commit của PR, nâng két, lùi về; sau
  mỗi bước tệp hạn chế tạo từ bản cũ phải mở lại được. Job chạy trên PR vào `main` và PR đổi migration, két, realm,
  compose, cài đặt hay sao lưu; không bắt buộc. `docs/trien-khai.md` (Nâng cấp tay) và `docs/van-hanh.md` (két cũ)
  dùng kịch bản thay cho các lệnh tay. Test scripts +18.
- Kịch bản e2e chạy giao diện tiếng Anh (F2.9): `tests/e2e/tieng-anh.spec.ts` bấm nút đổi ngôn ngữ ở thanh trên rồi
  kiểm theo vai trò và tên lấy nguyên văn từ `en.json`: menu, hộp việc, chuông thông báo, danh sách văn bản đến (tab,
  cột, trạng thái), soạn dự thảo (form trống bị chặn với lời báo tiếng Anh, lưu được), trang văn bản (trạng thái, dòng
  thời gian, tab Lịch sử), danh sách văn bản đi; tải lại trang vẫn giữ tiếng Anh, bấm "Tiếng Việt" thì về lại. Kịch
  bản thứ hai: người ngoài dùng trình duyệt tiếng Anh vẫn mở ra tiếng Việt, đổi ngôn ngữ ở trang trạng thái hệ thống
  và cổng xác thực không cần đăng nhập. e2e +2.
- Kiểm bản online qua HTTPS mỗi ngày (F1.9, #197): `scripts/kiem_ban_online.py` (chỉ thư viện chuẩn) kiểm một địa
  chỉ công khai từ bên ngoài, chạy hết các mục rồi báo mục trượt: chứng chỉ hợp lệ, TLS từ 1.2, còn ít nhất 14 ngày;
  `http://` chuyển sang `https://`; `/api/status` ok hay degraded (thành phần không ok in thành cảnh báo) và đúng
  `--version`; `issuer`, `authorization_endpoint`, `token_endpoint` của Keycloak nằm dưới `https://<máy>/realms/moc`
  (proxy chuyển đúng header); trang chủ còn CSP và `nosniff`. Job `.github/workflows/ban-online.yml` chạy kịch bản
  trên https://signet.htechcs.com lúc 07:17 mỗi ngày với thẻ phát hành mới nhất, chạy tay được, và chạy trên PR đổi
  nó; từ lúc gắn thẻ mới tới lúc nâng bản online thì job đỏ. `docs/trien-khai.md` mục 6 thêm lệnh này. Test scripts
  +15.

### Đã sửa đổi
- Lịch phiên bản (#179): `v1.2.0` ngày 30/10 là bản cho vòng trường 01/11, gồm các tính năng làm sau `v1.1.0`; bản nộp
  chấm 03/12 đổi thành `v1.3.0`, bản vá sau đó là `v1.3.x`. Tối 28/10 chốt danh sách, từ 29/10 chỉ sửa lỗi tới khi gắn
  thẻ. Sửa `docs/git_flow.md` (mục 6, mục 8), `docs/du-thi/ke-hoach-phat-trien.md` (hàng Phase 5 trong bảng trước ghi
  nhầm `v1.1.0`), `ROADMAP.md`, `docs/architecture.md`.

### Đã sửa lỗi
- Cổng thỉnh thoảng trả 502 cho `/v1/graphql` (#173), cùng loại với lỗi của `svc-files` ở 1.1.0: Hasura (máy chủ
  Warp) quét kết nối mỗi 30 giây và đóng kết nối rảnh sau 30–60 giây, APISIX giữ 60 giây; yêu cầu tới đúng lúc Hasura
  đóng thì APISIX nhận EOF hoặc RST và trả 502. Upstream `hasura` nay đặt `keepalive_pool` với `idle_timeout: 25`,
  chỉ APISIX đóng kết nối rảnh. Dựng lại với Hasura v2.51.0 và APISIX 3.18.0 như repo, gửi yêu cầu lệch −4…+4 ms
  quanh nhịp quét: trước 21/960 yêu cầu bị 502, sau 0/960. Test `test_giu_ket_noi.py` kiểm quy tắc này cho Hasura
  và `svc-files`.
- Cổng không còn chặn nhầm bước đổi mã lấy token khi bật WAF (#162): `code_verifier` base64url của PKCE (RFC 7636, như
  kịch bản demo hay thư viện OIDC khác) khoảng 1/25 000 lượt trùng mẫu libinjection (`71--7iZ…` → CRS 942100, 403); mã
  `code` gửi kèm là token ngẫu nhiên như ở trang ứng dụng. oidc-client-ts của Văn phòng điện tử, P.A.R.A, Bảng tin sinh
  verifier hex nên không dính verifier. Luật mới 10011 của `platform/apisix/apisix.yaml`, chỉ trên endpoint token, gỡ
  đúng ba luật 942100, 933…, 930120 trên hai tham số này như các token khác. Test scripts thêm kiểm luật 10011, smoke
  thêm ca đổi mã với đúng chuỗi đã bị chặn.
- Bản cài (`make install`) thiếu `scripts/nap_lo_mau.py` mà `scripts/demo.py` import ở đầu tệp, nên mọi lệnh `demo.py`
  ở `/opt/moc` dừng với `ModuleNotFoundError` (#174; thấy khi nâng bản online lên 1.1.0). Thêm tệp vào `RUNTIME` của
  `scripts/install.sh`; test mới kiểm mọi script Python được cài có đủ module cục bộ nó import, kể cả import trong hàm.
- `make install` trên máy chưa từng chạy `make up` dừng ở bước kiểm cuối "thiếu image moc/apisix:dev" (#186):
  Makefile truyền `MOC_VERSION` rỗng, compose ưu tiên biến môi trường đã đặt (kể cả rỗng) hơn `.env` của bản cài
  nên bước kiểm tìm thẻ `dev` thay vì thẻ vừa dựng. Bước kiểm nay đặt đúng phiên bản như lúc dựng. Test scripts +3
  (`install.sh` thật với `docker` giả theo thứ tự ưu tiên của compose).
- Trợ lý hỏi đáp không còn để văn bản mới chờ véc-tơ mãi khi có người hỏi liên tục (#184; smoke F4.2 trượt trên bản
  online 1.1.0). Mỗi lượt hỏi giữ vòng nhúng nền 5 giây; người hỏi lại dày hơn thế (smoke hỏi lại mỗi khoảng 3 giây)
  thì đoạn mới không được nhúng, không tìm được theo nghĩa, dù Ollama nhúng 4 đoạn chỉ mất 5 giây. Nay chuỗi giữ liền
  quá 30 giây (`MAX_HOLD_S`) thì vòng nền vẫn nhúng một lô rồi lại nhường. Test svc-files thêm ca hỏi lại mỗi 3 giây.
- Hoàn thành việc không còn lỗi "Đã lưu, nhưng chưa chuyển được bước tiếp" khi worker gợi ý giao việc cùng lúc hoàn
  thành việc ngoài trên cùng phiên quy trình (#189; thấy trong CI, `make demo-giao-viec`): Flowable khóa lạc quan,
  hủy một giao dịch và trả 500 kèm `FlowableOptimisticLockingException`. `svc-workflow` nay gọi lại tối đa 2 lần
  (sau 0,2 và 0,5 giây) cho hoàn thành việc và việc ngoài, chỉ với đúng lỗi này. Test svc-workflow +7.
- Sơ đồ cảm biến (`/cam-bien`) không còn bỏ sót cảm biến mất tín hiệu có đồng hồ chạy nhanh (#191): cờ mất tín hiệu
  xét theo `observedAt` của số đo mới nhất, thiết bị gửi giờ ở tương lai thì số đo cuối luôn có vẻ vừa đo, kể cả khi
  đã mất tín hiệu thật. Thêm cờ thứ tư `future_time` ("Giờ đo ở tương lai"): `observedAt` muộn hơn giờ máy chủ quá 2
  phút; khi đó mất tín hiệu xét theo lúc broker nhận số đo (`modifiedAt`). Cờ là một chuỗi nữa trong `flags`, kiểu
  GraphQL không đổi; phòng chỉ có cờ này vẫn tô theo số đo. `sensor.py` thêm `--clock-ahead` để giả đồng hồ nhanh,
  bước 7 của `make demo-it-ot` thêm cảm biến phòng xử lý tài liệu. Test svc-workflow +2, office +1.
- Trợ lý hỏi đáp không còn để lô nhúng nền chen vào lúc mô hình đang trả lời (#192). Trần 30 giây của #184 áp cả cho
  một câu hỏi mà Ollama viết câu trả lời lâu hơn 30 giây, vì lượt hỏi gia hạn giữ mỗi 2,5 giây và vòng nền không phân
  biệt gia hạn với câu hỏi mới: trên máy chỉ có CPU, một lô (tới 8 đoạn, khoảng 5 giây) làm câu trả lời chậm thêm. Nay
  lời gọi mô hình đang chạy (nhúng câu hỏi, viết câu trả lời, nhúng trích yếu cho tác tử gợi ý) giữ vòng nền suốt lời
  gọi, không có trần; trần 30 giây chỉ còn áp cho 5 giây giữ thêm sau mỗi lời gọi của lượt hỏi. Test svc-files thêm
  ca lời gọi dài quá 30 giây và ca lượt bị hủy giữa lời gọi.
- Dự thảo "Báo cáo sự cố" không còn ghi sang ngày hôm sau khi cảm biến có đồng hồ chạy nhanh (#195): đường cảnh báo
  vượt ngưỡng tin `observedAt` của thiết bị nếu lệch dưới một ngày, nên thiết bị nhanh 30 phút gửi số đo lúc 23 giờ 50
  thì báo cáo ghi ngày hôm sau, khóa nhắc "mỗi ngày một lần" cũng tính sang ngày hôm sau. Nay `observedAt` muộn hơn
  giờ máy chủ quá 2 phút (`FUTURE_SLACK`, như cờ `future_time` ở trên) thì giờ, ngày của báo cáo và khóa nhắc theo
  lúc máy chủ nhận thông báo; dự thảo thêm một dòng ghi rõ đồng hồ cảm biến chạy nhanh kèm giờ thiết bị gửi, sự kiện
  `ot.alarm` giữ giờ đó ở `device_observed_at`. Đồng hồ đúng giữ nguyên như trước. Test svc-workflow +3.
- Thẻ `<html lang>` không còn về `vi` khi tải lại trang lúc đang dùng tiếng Anh (#205): chữ vẫn tiếng Anh nhưng trình
  đọc màn hình đọc bằng giọng tiếng Việt. Plugin i18n đặt `lang` theo ngôn ngữ đang dùng qua `useHead`, đè lên giá trị
  ghi cứng trong `nuxt.config.ts`; e2e `tieng-anh.spec.ts` kiểm thêm `lang` sau khi tải lại ở cả hai test.

### Bảo mật
- Tải lên kiểm nội dung, không tin tên tệp hay mime trình duyệt khai (`POST /api/files`, tệp trong zip của lô nạp): sau
  ClamAV, loại nhận theo byte đầu phải khớp đuôi tệp — tệp `.pdf` thực ra là trang HTML bị chặn `415 type_mismatch`;
  chương trình, kịch bản (`MZ`, ELF, `#!`, đuôi `.exe`, `.bat`, `.js`…, xét cả tên ASCII lúc tải về: `x.bát` → `x.bat`)
  bị chặn `415 type_not_allowed`; `core.files` lưu mime theo nội dung. Loại đang dùng vẫn nhận (docx, xlsx có hay không
  mật khẩu, doc, xls cả bản HTML do phần mềm khác xuất, csv Windows khai `application/vnd.ms-excel`, ảnh PNG, WebP mang
  đuôi .jpg, chữ UTF-16, TCVN3…). Ảnh JPEG, PNG được xoay theo hướng EXIF rồi mã hóa lại trong tiến trình con có giới
  hạn để bỏ EXIF, vị trí GPS, XMP, chú thích; JPEG nhiều khung (ảnh chân dung iPhone) giữ khung đầu (`sha256`,
  `size_bytes` là của ảnh đã làm sạch); PDF và loại khác lưu nguyên từng byte. ClamAV vẫn quét byte gốc trước nên EICAR
  đổi đuôi vẫn là tệp nhiễm, có trong sổ kiểm toán. Giao diện Văn phòng điện tử, Không gian cá nhân báo đúng lỗi mới.
  Test (đếm tĩnh): svc-files +25, giao diện +1.

## [1.1.0] - 2026-10-25

Bản cho vòng trường. Lõi Signet có thêm ứng dụng thứ hai và cắm được ứng dụng mới bằng một lệnh; cổng có tường lửa
ứng dụng web; Văn phòng điện tử có giao diện hồ sơ, phòng đọc và phả hệ của từng biểu đồ báo cáo.

- Ứng dụng trên lõi: Không gian cá nhân P.A.R.A (`/ca-nhan/`); `moc app install` cài ứng dụng từ manifest mà không
  sửa tệp nào của lõi, ví dụ Bảng tin đơn vị (`apps/bang-tin`) nghe luồng sự kiện đã làm sạch `core.app_events`.
- Văn phòng điện tử: giao diện hồ sơ công việc, lãnh đạo phòng nộp lưu theo yêu cầu, phòng đọc xem tệp có dấu tên
  người xem (F3.8; nộp lưu nền đã có từ 1.0.0); phả hệ của từng biểu đồ báo cáo: biểu đồ ← khung nhìn ← bảng (F3.9,
  F3.11); tự chẩn đoán H-P-D-I cho lãnh đạo (F4.7); góp ý và số đo "sau" (F4.6).
- Bảo mật: WAF Coraza + OWASP CRS ở APISIX (F3.15), chặn mặc định, mỗi loại trừ có lý do và số đo; giao diện báo rõ
  khi cổng chặn; nâng pypdf 6.21.2 (ba GHSA) và gỡ pip khỏi image của dịch vụ.
- Dữ liệu và vận hành: API nạp lô văn bản đến; log tập trung Vector + Parseable (tắt mặc định); thông báo email;
  trang Trạng thái công khai; SBOM CycloneDX kèm mỗi bản phát hành.
- Kho mã: cấu hình phần mềm nguồn mở gom vào `platform/`, khai giấy phép REUSE, repo đổi tên `HIT-Champion/Signet`,
  gói phát hành `signet-X.Y.Z.tar.gz`; CI chia năm phần chạy song song.

### Đã thêm
- API nạp lô văn bản đến (cụm ⑤ Tầng 1): `POST /api/imports/incoming` nhận NDJSON hoặc CSV cùng trường với
  `receiveIncoming`, kèm zip tệp đính kèm tùy chọn. svc-files xử lý nền theo mẻ; mỗi dòng đi đúng đường tiếp nhận lẻ —
  ClamAV, Action `receiveIncoming` thay mặt văn thư, tùy chọn vào sổ — nên vẫn cách ly đơn vị và có dòng sổ kiểm toán
  riêng. `GET /api/imports/{id}` báo đã nhận / đạt / trùng / lỗi, `…/rows` báo lỗi từng dòng. Gửi lại cùng tệp không
  nhân đôi (`Idempotency-Key`, chỉ mục chặn trùng); svc-files khởi động lại thì lô chạy tiếp. Dòng bị từ chối thì tệp
  đã lưu được gỡ; `restricted` sai kiểu bị chặn trước khi tệp vào kho; trần byte một lô ghi vào kho
  `MOC_IMPORT_STORE_MAX_MB`; dòng được giữ khi đang làm nên hai tiến trình không làm trùng. Bảng `core.import_jobs`,
  `core.import_rows` (migration 1792281602800). Lô mẫu 200 dòng `seed/nap-lo/van-ban-den.csv`, `make demo-nap-lo`.
  Test (đếm tĩnh): svc-files +113, db +18, scripts +12, svc-workflow +2, giao diện +2.
- Tường lửa ứng dụng web ở cổng APISIX (F3.15): Coraza v3.3.3 + OWASP CRS v4.14.0 (coraza-proxy-wasm 0.6.0, ghim digest
  và băm) chặn tải tấn công (SQLi, XSS, duyệt thư mục, chèn lệnh, Log4Shell, tải lên `.php`…) trên mọi đường trước khi
  kiểm token → 403 có `X-Request-Id`, dòng chặn trong nhật ký mang cùng mã. Mặc định chặn, `MOC_WAF=On | DetectionOnly |
  Off`; giá trị sai bị `make up` và reconciler GitOps (trước khi dừng Signet) từ chối, và image dừng ngay lúc khởi động
  với dòng lỗi rõ thay vì cổng trả 503. Loại trừ CRS gỡ theo id, có lý do, chỉ trên đúng khóa: Keycloak, chữ truy vấn
  GraphQL, truy cập bằng IP; chữ tự do trong biến GraphQL (nội dung, trích yếu, ý kiến, ghi chú, góp ý), câu hỏi trợ lý,
  ô Tìm kiếm; tên tệp tải lên có `' " ; = :`. Dò trên 7 389 yêu cầu dựng từ toàn bộ chữ của dữ liệu mẫu: không chữ mẫu
  nào bị chặn nhầm (trước đó 4/21 PDF mẫu). JSON lồng sâu bị chặn trước WAF (GHSA-6gcq-wc29-5xf2). Nội dung tệp vẫn do
  ClamAV soi. APISIX dựng thành image `moc/apisix`, 4 worker (`MOC_APISIX_WORKERS`); smoke thêm 7 kiểm, có tên tệp và
  nội dung hành chính thật phải qua (`platform/apisix/README.md`, mục WAF).
- Khai giấy phép theo chuẩn REUSE: `REUSE.toml` khai Apache-2.0 cho các tệp không chèn được header (JSON, ảnh, PDF,
  tài liệu, dữ liệu mẫu), `LICENSES/Apache-2.0.txt` là bản sao của `LICENSE`; `reuse lint` 5.0.2 đạt, 482/482 tệp có
  thông tin bản quyền và giấy phép. `.env.example` mang header giấy phép, `make license-check` kiểm cả tệp này
  (PoF #2).
- README (cả bản tiếng Anh) có mục "Cấu trúc thư mục": mỗi thư mục chứa gì, mã đội tự viết nằm đâu, các tác tử AI
  (F4.1–F4.4) ở tệp nào, test của từng phần ở đâu.
- Tài liệu đánh giá AI [`docs/danh-gia-ai.md`](docs/danh-gia-ai.md): với đọc văn bản đến, trợ lý hỏi đáp, gợi ý giao
  việc và bộ che thông tin cá nhân (F4.1–F4.4) — mục đích, mô hình và công cụ kèm phiên bản, giấy phép (trỏ
  `DEPENDENCIES.md`), dữ liệu đo và cách làm nhãn, lệnh đo lại, số đo kèm ngày, máy và nguồn, phần chưa đo, giới hạn,
  cơ chế an toàn kèm tệp mã. Thêm lần đo trợ lý hỏi đáp trên bản online (23/10/2026, Qwen3-1.7B và
  Qwen3-Embedding-0.6B trên CPU): recall@3 16/16, 0 nguồn bị cấm, câu trả lời của mô hình qua kiểm 16/16, p50 8,9
  giây. Bảng Tài liệu của README (cả bản tiếng Anh) có thêm dòng này.
- Hồ sơ chất vấn: `docs/du-thi/hoi-dap-hoi-dong.md` gồm 13 câu hội đồng dễ hỏi (lên 100.000 người dùng, nguồn mở và
  khóa nhà cung cấp, lõi dùng lại cho ứng dụng khác, bảo mật, AI bịa và dữ liệu ra ngoài, sao lưu và tự phục hồi, chạy
  không Internet, chi phí, giấy phép, việc chưa làm), mỗi câu trả lời kèm đường dẫn, lệnh `make`, bước CI làm bằng
  chứng. `docs/demo-script.md` thêm mục "Phương án dự phòng" (mất mạng, hỏng laptop, AI chậm, TOTP không qua, bước demo
  lỗi; máy dự phòng chạy tại chỗ không cần Internet, video) và checklist T-1 ngày, T-1 giờ, T-5 phút.
- Bảng mức hoàn thiện [`docs/muc-hoan-thien.md`](docs/muc-hoan-thien.md): 43 tính năng F1.1–F4.6, mỗi tính năng một
  mức (Hoàn thiện 32, Dùng được 5, Minh họa 2, Một phần 1, Chưa làm 3; định nghĩa ở đầu tệp) kèm bằng chứng — tệp test
  và số hàm test đếm tĩnh (tổng 1 425, cách đếm ghi rõ), bước CI, màn demo hay kịch bản e2e — và hạn chế đã biết. Độ
  phủ 29 năng lực của 7 cụm dịch vụ Tầng 1 theo đề: 17 hoàn thiện, 3 chưa có (kịch bản serverless, API nạp lô, trục
  streaming sự kiện). Lệnh đếm lại, kiểm lại ở cuối tệp.
- Thông báo đa kênh: ngoài chuông trên web, `svc-workflow` gửi thêm email (SMTP, STARTTLS/SSL) tới địa chỉ trong
  danh bạ và tin tóm tắt lên webhook (Mattermost, Slack, ntfy) khi đặt `MOC_SMTP_HOST`, `MOC_NOTIFY_WEBHOOK_URL` —
  mặc định tắt. Hộp thư đi `core.notification_deliveries` tạo cùng giao dịch với thông báo, gửi ở nền, thử lại tối
  đa 5 lần có giãn cách, mỗi lần ghi sổ kiểm toán; webhook không có tên người, không có văn bản hạn chế; nhật ký không
  có địa chỉ email, URL. Mailpit (profile `mail`) làm hộp thư thử cho demo. Test svc-workflow +41, scripts +8.
- Chuỗi cung ứng: `make sbom` sinh SBOM CycloneDX của cây mã nguồn bằng Syft 1.54.1 (image ghim digest), bản phát hành
  đính kèm `moc-X.Y.Z.cdx.json` cùng `.sha256`; `make license-audit` (`scripts/license_audit.py`, chỉ thư viện chuẩn)
  kiểm giấy phép của mọi gói kể cả gói gián tiếp theo chính sách của `DEPENDENCIES.md`, gói chưa rõ hay ngoài chính
  sách cần ngoại lệ có lý do trong `.github/license-exceptions.json`. Job CI "Giấy phép (PoF #2)" chạy cả hai: 769 gói
  (npm 690, Python 73, action 6) đều đạt, 22 gói qua nhờ ngoại lệ. `SECURITY.md`: phiên bản được hỗ trợ, báo lỗ hổng
  riêng tư qua GitHub, thời gian phản hồi, phạm vi kể cả bản chạy thử trực tuyến. Test scripts +22.
- Trang công khai **Trạng thái hệ thống** `/trang-thai` (không cần đăng nhập, tự làm mới mỗi 30 giây): tình trạng chung
  và từng thành phần theo tầng người dùng → lõi → quy trình → dữ liệu → trí tuệ nhân tạo, phiên bản, thời gian chạy, giờ
  sao lưu gần nhất, trợ lý AI bật hay tắt kèm tên mô hình; có đường tới từ trang đăng nhập lỗi, chân trang cổng xác
  thực, thanh bên. `GET /api/status` của `svc-files` gom ở phía máy chủ (lưu đệm 10 giây cho mọi người, mỗi lần dò tối
  đa 3 giây), chỉ trả nhãn cố định, không tên máy, địa chỉ hay số liệu; APISIX giới hạn 30 lần/phút mỗi IP
  (`MOC_RATE_STATUS_PER_MIN`). `moc backup create` ghi dòng `system.backed_up` vào sổ kiểm toán. Test svc-files +36,
  office +9, e2e +1.
- Ứng dụng thứ hai trên lõi, Không gian cá nhân P.A.R.A (`/ca-nhan/`, `apps/ca-nhan`): mỗi người cất tệp của mình
  trong bốn thư mục Dự án, Lĩnh vực, Tài nguyên, Lưu trữ — tải lên qua `svc-files` (ClamAV), chuyển, tải về; client
  Keycloak riêng `app-ca-nhan`, cùng phiên SSO với Văn phòng điện tử; schema riêng `personal` có quyền đến từng dòng,
  mỗi lần xếp, chuyển vào sổ kiểm toán của lõi. Không sửa dòng nào trong `services/`; cách thêm một ứng dụng:
  `docs/them-ung-dung.md`. Bản cài cũ thêm client bằng `moc realm clients` (`make seed` cũng gọi); `make demo-ca-nhan`.
- Góp ý và số đo "sau" theo đặc tả §8 (F4.6): nút Góp ý trên thanh trên của Văn phòng điện tử — mức hài lòng 1–5,
  vài dòng, màn hình đang dùng tự gắn dạng khuôn đường dẫn (không id, không chuỗi truy vấn); bảng `office.feedback`
  cách ly theo đơn vị, người gửi chỉ thấy góp ý của mình, lãnh đạo và quản trị đơn vị xem danh sách (không có người
  gửi) và tổng hợp theo màn hình ở trang Góp ý; CSDL chặn gửi dồn (3 góp ý mỗi 10 phút, 20 mỗi 24 giờ); góp ý không
  gắn sổ kiểm toán. Trang Số đo cho lãnh đạo đơn vị và `make do-so-lieu-sau`: thời gian từ văn bản đến tới khi giao
  xử lý (trung vị, p90), tỷ lệ xử lý quá hạn, 5 lần tìm lại văn bản cũ qua API (độ trễ hệ thống), số bước chuyển tay
  so sánh định tính; cột "trước" ghi chưa đo, số trên đơn vị mẫu (`core.tenants.sample_data`) ghi rõ là dữ liệu mẫu.
  Cách đo: [`docs/so-lieu-sau.md`](docs/so-lieu-sau.md). Test db +30, office +21, scripts +16.
- Log tập trung (F3.14, profile `logs`, tắt mặc định): tệp compose phủ `platform/logs/docker-compose.logs.yml` đổi
  driver log của APISIX, app-office, app-ca-nhan, `svc-files`, `svc-workflow` sang fluentd, gửi Vector 0.59.0 rồi
  Parseable v3.2.4 (chỉ nghe 127.0.0.1, bỏ mọi capability, mật khẩu do `make env`, `make up` hay `make logs-up` sinh,
  mật khẩu rỗng thì không mở cổng, giữ `MOC_LOGS_RETENTION_DAYS` ngày). Vector ghép dòng Docker cắt ở 16 KiB rồi che
  lần hai: token Bearer/Basic (cả có `=` đệm), JWT; giá trị của khóa mật khẩu, bí mật, token, khóa API, phiên (cả có
  tiền tố, hậu tố, dict Python, mật khẩu có dấu cách, nháy không đóng, khóa ở mọi tầng của dòng JSON, khóa viết
  thoát) và của cờ dòng lệnh như `--password`; Authorization (không nháy thì tới hết dòng, cả Digest), Cookie nhiều
  cặp; mật khẩu trong chuỗi kết nối; chuỗi truy vấn của URL; email (cả có dấu), số điện thoại (cả +84), CCCD;
  CMND, số tài khoản, mã số thuế khi có từ khóa đứng trước; số viết tách nhóm không có từ khóa, họ tên vẫn lọt
  (danh sách ở `docs/van-hanh.md`). Không gắn `docker.sock`, `docker logs` vẫn đọc được; `make logs-up`,
  `make logs-tra ID=…`, `make logs-down`, `make demo-log-tap-trung`. `svc-workflow` mang `X-Request-Id` như
  `svc-files` (nhật ký, lời gọi Hasura nên vào `core.audit_log.request_id`, lời gọi `svc-files`), mã sai dạng thì
  thay bằng mã mới; APISIX ghi mã yêu cầu ở cuối dòng log truy cập. Rủi ro (CORS của Parseable, mất log khi Vector dừng)
  và cách tắt: `docs/van-hanh.md`, mục Log tập trung. Test svc-workflow +10, scripts +29, `vector test` 29 ca.
- Cắm ứng dụng vào lõi bằng một lệnh, không sửa tệp nào của lõi: `python3 scripts/moc.py app install apps/<thư
  mục>/app.yaml` (`make app-install APP=…`, `--dry-run` in kế hoạch), `app list`, `app remove` (giữ dữ liệu), `app
  sync`. Manifest theo `scripts/app-manifest.schema.json`; lệnh tạo client Keycloak (PKCE S256, 5 mapper; client dịch vụ
  khi cần), route APISIX, container, schema + migration chạy bằng vai trò CSDL riêng của ứng dụng (không quyền gì trên
  lõi; view, `DEFAULT`, trigger đọc lõi hay chạy bằng quyền của Hasura bị từ chối trước khi commit), bảng và quyền
  Hasura (lọc đơn vị; điều kiện trong quyền không `_exists`, qua quan hệ sang lõi chỉ `visible: {_eq: true}` — Hasura
  chạy điều kiện bằng quyền admin), Event Trigger — trạng thái trong `.moc-apps/` (ngoài git), tệp chạy dựng từ tệp lõi
  nguyên văn (APISIX tự nạp lại, metadata sống qua khởi động lại Hasura). Chạy lại không tạo trùng; lỗi báo đúng bước.
  Lõi phát luồng sự kiện đã làm sạch `core.app_events` (migration 1792281603200: tiếp nhận, vào sổ, phát hành; không văn
  bản hạn chế) qua Hasura Event Triggers. Ứng dụng thứ ba `apps/bang-tin` — Bảng tin đơn vị; `make demo-cai-ung-dung`;
  cách làm, ranh giới tin cậy và rủi ro ở `docs/them-ung-dung.md` mục 1. `moc backup` ghi và tạo lại vai trò CSDL của
  ứng dụng khi khôi phục sang máy mới. Test (đếm tĩnh): scripts +52, db +14, bang-tin +20.
- Tự chẩn đoán mức trưởng thành H-P-D-I cho lãnh đạo (F4.7): trang Tự chẩn đoán `/tu-chan-doan` — 12 câu do đội tự
  viết theo bốn không gian Con người, Quy trình, Dữ liệu, Trí tuệ, mỗi câu 5 mức quan sát được (vi/en, có JSON
  Schema), radar ECharts, cảnh báo lệch nền theo nguyên lý tiến hóa tuyến tính H → P → D → I, không gian nên làm
  trước, bước tiếp theo trỏ đúng trang Signet mà vai trò người xem mở được. Cạnh mỗi không gian là bằng chứng đo được
  của chính đơn vị lấy từ các view đã có (dashboard, số đo F4.6, độ chính xác tác tử F4.1/F4.3, hồ sơ nộp lưu), chỉ số
  chưa có dữ liệu thì không hiện. Lãnh đạo đơn vị lưu kết quả vào `office.maturity_assessments` (CSDL kiểm đủ bộ câu
  và tính điểm, cách ly theo đơn vị, tối đa 5 lần lưu mỗi giờ, không sửa, xóa, gắn sổ kiểm toán) để xem tiến bộ; lãnh
  đạo phòng làm được nhưng không lưu. Không phải bộ chỉ số chính thức, không quy đổi DTI. Nguồn, cách chấm, giới hạn:
  [`docs/tu-chan-doan.md`](docs/tu-chan-doan.md). Test office +18, db +18.
- Giao diện hồ sơ công việc và phòng đọc xem tệp (F3.8, màn (i)): trang **Hồ sơ công việc** của Văn phòng điện tử —
  chuyên viên, lãnh đạo phòng lập hồ sơ (ký hiệu, tiêu đề, thời hạn bảo quản), thêm văn bản đã xong của phòng, đóng hồ
  sơ; văn thư, lãnh đạo đơn vị xem cả đơn vị; lãnh đạo phòng bấm **Nộp lưu** (`POST /api/case-files/{id}/archive`; đội
  chọn lãnh đạo phòng làm người nộp, người thứ hai sau người lập; chung một lượt với vòng nộp lưu nền, ghi sổ kiểm
  toán khi giành được lượt, lỗi trả mã đúng nghĩa). Phòng đọc trên trang hồ sơ đã nộp lưu: manifest khớp băm, văn bản
  trong gói, nút **Xem** tệp PDF (`GET /api/case-files/{id}/archive/files/{file_id}`) — kiểm băm tệp với manifest,
  đóng dấu "PHÒNG ĐỌC" kèm tên người xem, giờ xem, ghi `case_file.file_viewed` vào sổ kiểm toán rồi mới trả, chỉ xem
  trong trang (`inline`, `no-store`); gói lạnh không đổi. Test svc-files +22, office +10, e2e `ho-so.spec.ts`; `make
  smoke` nộp lưu qua endpoint mới (chuyên viên gọi bị 403) và xem tệp; `make demo-nong-lanh` kiểm thêm bước xem tệp.
- Phả hệ trên báo cáo tổng hợp (F3.9, F3.11): khung nhìn `office.report_lineage` tính từ catalog PostgreSQL lúc truy
  vấn khung nhìn báo cáo `office.v_*` nào đọc bảng, view nào (đệ quy qua view lồng, không khai tay — sửa view là phả
  hệ đổi theo), chỉ có tên và cạnh, lãnh đạo đơn vị đọc như dashboard. Trang Phả hệ số liệu (`/pha-he`) và nút "Nguồn
  số liệu" trên từng biểu đồ của trang Điều hành: đồ thị ECharts biểu đồ → khung nhìn → bảng, nối với lượt nộp lưu gần
  nhất (bảng → Parquet → gói lưu trữ, số dòng đã kiểm), bảng nguồn đi kèm, tải phả hệ dạng OpenLineage (JSON Lines);
  biểu đồ nào đọc khung nhìn nào khai một chỗ, có test đối chiếu với truy vấn thật của trang. Bước `commit` của nộp
  lưu khai thêm `office.archived_document_facts`; `make demo-pha-he` thêm bước in phả hệ báo cáo, smoke thêm 2 kiểm.
  Test db +6, office +13, scripts +4, e2e +1.

### Đã sửa đổi
- README (cả bản tiếng Anh) viết lại thành 12 mục, cài đặt lên khoảng giữa trang thay vì dòng 221: Giới thiệu, Kiến
  trúc, Tính năng, Bằng chứng 4 nguyên lý, Công nghệ và giấy phép (phiên bản, giấy phép, vai trò từng thành phần),
  Cài đặt từ mã nguồn, Chạy thử (bản online signet.htechcs.com, tài khoản, địa chỉ), Vận hành và kiểm thử, Xử lý sự
  cố, Tài liệu, Đóng góp và liên hệ (nhóm phát triển), Giấy phép. Sơ đồ ASCII thay bằng sơ đồ kiến trúc động (GIF,
  tiếng Việt và tiếng Anh): luồng yêu cầu chạy trái sang phải, màu theo H-P-D-I, viền đậm là mã của đội, logo trên
  các phần mềm nguồn mở dùng nguyên bản; sinh lại bằng `python3 scripts/so_do_kien_truc.py gif` (Chromium và
  FFmpeg, chỉ khi sửa sơ đồ). Logo khai riêng trong `REUSE.toml` (`LicenseRef-Logos`), nguồn ở
  `docs/anh/logo/NGUON.md` (#108).
- Repo đổi tên `HIT-Champion/HVL` → `HIT-Champion/Signet` (#112): đường dẫn trong hướng dẫn đóng góp, chính sách
  bảo mật, mẫu issue, tài liệu triển khai, vận hành, quy trình nhánh, `scripts/release_body.py` và producer của sự
  kiện OpenLineage; lệnh `cd HVL` sau khi clone thành `cd Signet`. GitHub vẫn chuyển hướng đường dẫn cũ.
- CI nhanh hơn: job "Chạy thử toàn hệ thống (PoF #4)" chia ba phần chạy song song trên ba máy (luồng chính, e2e và
  các màn lõi; màn AI, nộp lưu, ký số, sao lưu và khôi phục; cài đặt và GitOps), phần nào cũng tự dựng và nạp
  mẫu — khoảng 27 phút còn khoảng 12 phút, vẫn chạy đủ mọi bước. PR chỉ đổi tài liệu (`*.md`, ảnh trong `docs/`,
  trừ `docs/api/`) không dựng hệ thống. Tên job ruleset yêu cầu giữ nguyên.
- CI nhanh hơn nữa (#110): job "Chạy thử toàn hệ thống (PoF #4)" chia năm phần (`luong-chinh`, `e2e`, `ai`,
  `sao-luu`, `cai-dat`); smoke chạy lại sau khôi phục và cuối GitOps không chờ timer nhắc hạn lần nữa (đã kiểm ở
  `luong-chinh`), smoke ngay sau `make install` thay bằng kiểm nhanh vì GitOps chạy smoke đủ trên cùng bản cài; job
  "Dựng từ mã nguồn" đỏ khi một bước gọi tên phần không có trong ma trận hay một phần không có bước nào; Python in
  ngay từng dòng để mốc thời gian trong nhật ký đúng. `make demo-tu-phuc-hoi` thử lại tải tệp tối đa 30 giây khi cổng
  còn trả 502/503 ngay sau khi svc-files được dựng lại (APISIX hỏi lại DNS mỗi 5 giây), in số giây đã chờ.
- Trang Release ngắn lại (`scripts/release_body.py`): dòng chỉ gói chính thức `moc-X.Y.Z.tar.gz` kèm lệnh kiểm
  `.sha256` (GitHub tự gắn "Source code (zip)" vào mọi bản phát hành mà không gỡ được, PoF #3), phần tóm tắt viết
  ngay dưới tiêu đề phiên bản trong CHANGELOG, rồi toàn bộ ghi chép gập lại. Dòng tiếp nối được nối lại: GitHub hiện
  mỗi dấu xuống dòng của mô tả Release thành một dòng mới. Mục [1.0.0], [0.1.0] thêm phần tóm tắt. Test scripts +6.
- Lịch phát hành: `v1.0.0` (23/10); `v1.1.0` trước vòng trường 01/11; bản nộp chấm là `v1.2.0` (03/12); sau `v1.2.0`,
  mỗi bản sửa lỗi gộp vào `develop` đi kèm một bản vá để lúc chấm `develop` và `main` cùng nội dung. `docs/git_flow.md`
  ghi lệnh thiết lập repo (merge commit, bật secret scanning) và lý do giữ `develop` làm nhánh mặc định; mục 11 ghi đúng
  mốc chuyển quy trình (sau `v1.0.0`) và việc các lượt chạy cũ đã bị xóa khỏi trang Actions.
- Gói phát hành đổi tên `moc-X.Y.Z.tar.gz` → `signet-X.Y.Z.tar.gz` (cả SBOM `.cdx.json` và `.sha256`) theo tên sản phẩm;
  tên mã `moc` trong mã, image, dịch vụ giữ nguyên. Gói của `v0.1.0`, `v1.0.0` giữ tên cũ (không gắn lại thẻ).
- Tài liệu phục vụ cuộc thi chuyển vào `docs/du-thi/` (phân tích đề, tóm tắt thể lệ, bảng tự chấm PoF, kế hoạch
  phát triển, thư mục `nghien-cuu/`), kèm trang mục lục; `docs/` chỉ còn tài liệu về sản phẩm. Mọi liên kết và chỗ
  nhắc đường dẫn (README, đặc tả, mô hình dữ liệu, README dịch vụ, chú thích BPMN và `flowable.py`) đã sửa theo.
- Cấu hình của phần mềm nguồn mở dùng nguyên bản gom vào `platform/`: `auth/` → `platform/keycloak/`, `gateway/` →
  `platform/apisix/`, `realtime/` → `platform/centrifugo/`, `openbao/`, `monitoring/` → `platform/openbao/`,
  `platform/monitoring/`, `ops/systemd/` → `platform/systemd/`, kèm trang `platform/README.md`. BPMN vào thư mục của
  dịch vụ nạp nó (`services/svc-workflow/processes/`), cảm biến giả lập vào `services/ot-sensor/`. Gốc repo từ 15 còn 10
  thư mục. Compose, `install.sh`, test, tài liệu đổi đường dẫn theo; đường dẫn trong container không đổi. Cài lại vào
  bản cài theo bố cục cũ thì `make install` xóa các tệp cũ (theo MANIFEST) và cả thư mục cha đã rỗng.
- CI: bước "Tài liệu API trong docs/api/ khớp mã" lệch thì sinh lại `docs/api/` trên chính hệ thống vừa dựng và tải
  lên thành artifact `docs-api-<lần chạy>` (giữ 7 ngày); người sửa PR chép về rồi commit, không phải dựng cả hệ thống
  ở máy. `docs/api/README.md` có lệnh `gh run download`.
- `ROADMAP.md` viết lại theo hiện trạng: trước đây gần như mọi mục còn `[ ]` và viết theo lúc chọn công cụ ("Chốt
  nền tảng …"). Nay giữ khung giai đoạn 0, bốn không gian H-P-D-I, giai đoạn 5 và Ngoài phạm vi; mục đã xong ghi `[x]`
  kèm thành phần và mã F hay tệp làm bằng chứng (`docs/muc-hoan-thien.md`), mục làm dở ghi rõ phần còn thiếu, việc
  đang làm ghi số PR nếu có. Thêm mục "Sau vòng trường": việc còn thiếu thật xếp theo ưu tiên, kèm lý do, không gắn
  ngày.
- `docs/architecture.md` viết lại theo hệ thống đang chạy: sơ đồ tổng thể vẽ lại bằng Mermaid với đường dẫn thật của
  APISIX; bản đồ công cụ thay bảng "đang khảo sát" bằng thành phần, phiên bản ghim, cụm Tầng 1, vị trí trong repo và mức
  theo `docs/muc-hoan-thien.md`, khe cắm chưa có ghi thẳng "chưa có". Mục mới "Ranh giới lõi và ứng dụng" xếp từng
  module của `svc-files`, `svc-workflow` và từng phần CSDL vào lõi, phần máy chủ của Văn phòng điện tử hay phần dùng
  chung mang dáng nghiệp vụ, kèm chỗ dính, lý do đang gộp và hướng tách sau `v1.1.0`. Thêm QĐ-008…QĐ-012 cho quyết định
  đã có trong mã (sự kiện trong bảng thay broker, Flowable, SeaweedFS, ứng dụng là trang tĩnh, Văn phòng chung tiến
  trình với lõi), QĐ-013 (WAF, chờ PR), hộp "Đọc trong 10 phút" và mục "Chỗ còn yếu"; §1.2, §1.3 sửa câu đã lệch
  (profile chia theo tầng, RAM đo được, "cài dưới một giờ" chưa đo).

### Đã sửa lỗi
- Cổng thỉnh thoảng trả 502 khi gọi `svc-files` (gặp ở CI của #130): APISIX giữ kết nối rảnh tới dịch vụ phía sau 60
  giây, uvicorn của `svc-files` đóng sau 5 giây; yêu cầu tới đúng lúc uvicorn đóng thì APISIX nhận EOF hoặc RST, trả
  502 và không thử lại. `svc-files` nay giữ kết nối 75 giây (`--timeout-keep-alive 75`), chỉ APISIX đóng kết nối rảnh.
  Dựng lại với APISIX 3.18 và uvicorn 0.54.0 như repo, nghỉ 4,990–5,010 giây giữa hai yêu cầu: trước 31/1 312 yêu cầu
  bị 502, sau 0/1 312.
- Tài liệu ghi lệch với mã (#119): `DEPENDENCIES.md` nói Hasura dùng Event Triggers và Redpanda được thay bằng
  Event Triggers, nhưng `db/metadata` không khai trigger nào — nay ghi đúng: sự kiện nằm trong bảng PostgreSQL,
  Centrifugo đẩy tới trình duyệt, trục sự kiện chưa có. `docs/muc-hoan-thien.md` thôi ghi "chưa có bước CI" cho
  `make demo-log-tap-trung`, `make do-so-lieu-sau`, `make demo-nap-lo` (đã chạy trong CI từ #111); `ROADMAP.md`
  ghi log tập trung là Một phần thay vì Đang làm.
- `DEPENDENCIES.md` liệt kê PDF.js (`pdfjs-dist`) dù giao diện không dùng: tệp được lấy bằng fetch rồi lưu về máy.
  Bỏ dòng đó, sửa chú thích cùng ý trong `svc-files`. Câu "gói npm gián tiếp không có giấy phép ngoài danh sách OSI"
  cũng sai: có thêm bảng năm gói ngoại lệ, đều chỉ dùng lúc dựng, lúc phát triển, không nằm trong trang phát hành —
  `caniuse-lite` (CC-BY-4.0), `mdn-data`, `@speed-highlight/core` (CC0-1.0), `node-forge` (chọn BSD-3-Clause),
  `type-fest` (chọn MIT).
- Tên 4 job CI có dấu `#` (`Giấy phép (PoF #2)`…) bị YAML hiểu phần từ ` #` là chú thích: trang Actions hiện
  `Giấy phép (PoF`, và ruleset đòi đúng tên có `#` thì không PR nào gộp được. Tên đặt trong ngoặc kép; test mới kiểm
  mọi job ruleset đòi đều có thật. Test scripts +2.
- Nhắc hạn, báo lãnh đạo (F2.3): dòng nhắc được ghi vào dòng thời gian văn bản trước khi gửi thông báo. Trước
  đây gửi trước rồi mới ghi, người bấm thông báo mở văn bản ngay có thể chưa thấy dòng nhắc; `make smoke` thỉnh
  thoảng đỏ vì đọc trúng khoảng đó. Test svc-workflow +1.
- Văn bản hạn chế quá nặng để đóng dấu có lúc bị báo "không đọc được PDF" thay vì "PDF quá nặng, vượt giới hạn bộ
  nhớ": tiến trình con nạp WeasyPrint sau khi đặt trần bộ nhớ, dlopen thư viện pango hỏng lại báo "cannot open
  shared object file" (OSError); mã C của WeasyPrint hết bộ nhớ thì chết bằng SIGTRAP hay SIGSEGV tùy bản dựng, bị
  coi là tệp hỏng. Bản sửa ở 1.0.0 chỉ cứu test (trần ≤ 64 MB thì coi là hết bộ nhớ): trần 96–160 MB vẫn báo sai.
  Nay WeasyPrint nạp trước khi đặt trần, mọi việc sau đó nằm trong `try`, hết bộ nhớ cả lúc ghi kết quả thì thoát
  bằng mã riêng; tiến trình con chết vì tín hiệu (trừ SIGXCPU) là hết bộ nhớ — tệp chỉ đi qua pypdf, mã C chỉ vẽ lớp
  dấu; bỏ đoán theo lời báo lỗi, chỉ tin MemoryError và ENOMEM. Test svc-files +13.
- brotli 1.2.0 → 1.2.1, brotlicffi 1.2.0.2 → 1.2.1.0 (`svc-files`, gói kéo theo của fontTools mà WeasyPrint dùng):
  vá lỗi ghi tràn bộ nhớ trong bộ giải nén Brotli (PYSEC-2026-4322, PYSEC-2026-4323, CRITICAL) mà OSV-Scanner trong CI
  báo từ 23/10. Bản vá phát hành 22/10: ngoại lệ quy tắc hai tuần, ghi ở `DEPENDENCIES.md`.
- Sửa các lỗi SonarQube tìm thấy ở lần quét đầu (23/10/2026). `POST /ot/notify/{tenant}` của `svc-workflow` khai trả
  204 mà có 5 nhánh `return` thân lỗi (5 BLOCKER `python:S8400`): lỗi nay ném `WorkflowError` cho một bộ xử lý chung;
  mã HTTP, thân lỗi và OpenAPI không đổi. `MOC_SMTP_TLS=none` đi cùng `MOC_SMTP_USER` từng đăng nhập máy chủ thư qua
  kết nối không mã hóa, mật khẩu đi dạng rõ: nay không đăng nhập, thư email báo lỗi gửi, lúc khởi động ghi một dòng
  `config.warning` (không chặn khởi động). Ô tìm kiếm, ô chọn văn bản đến hay đi và ô lý do lưu có tên cho trình đọc
  màn hình, nút Tìm ghi `type="submit"`, kiểm form không còn `reduce()` thiếu giá trị đầu. Ký tự điều khiển hai chiều
  trong mã `svc-files` viết bằng mã thoát. Test mới chạy lại các luật này mà không cần SonarQube: route khai 204 không
  `return` thân, ký tự hai chiều ở `services/`, `apps/`, `scripts/`, nhãn ô nhập và `type` của nút trong form ở mọi
  tệp `.vue`. Các cảnh báo còn lại là báo nhầm, không chèn `NOSONAR`. Test svc-workflow +5, office +3, scripts +2.
- Cổng WAF chặn (F3.15) thì Văn phòng điện tử báo "Cổng an ninh chặn nội dung này… (mã <X-Request-Id>)", thay cho "Có
  lỗi xảy ra: Unexpected token '<'…" (đọc trang 403 HTML của cổng như JSON), "HTTP 403" hay câu "không có quyền" sai
  nghĩa ở trang Hỏi đáp. 403 JSON của Hasura, svc-files giữ như cũ. E2e `waf.spec.ts`: tên tệp có `' ; =`, dự thảo có
  đề mục I./II./III. và đường dẫn theo IP, ô Tìm kiếm "File …?" đi qua WAF; ô Nơi nhận chỉ là `http://<IP>/…` bị chặn
  và hiện đúng mã. Test office +6.
- Đăng nhập thỉnh thoảng bị WAF chặn 403 (gặp ở CI của develop 6710703): token ngẫu nhiên do Keycloak,
  oidc-client-ts sinh tình cờ trùng mẫu của OWASP CRS — libinjection (942100) với cookie `KC_AUTH_SESSION_HASH`
  mà Keycloak bọc trong ngoặc kép (`"+…"`) hay chuỗi `8--…`, tên hàm PHP (933150: `rtrim`, `fputs`), đuôi tệp
  (930120: `.nsr`), lệnh Unix (932250). Loại trừ 10010, 10020 nay gỡ đúng các luật đó trên đúng 6 cookie và 8 tham
  số token của Keycloak, OIDC; luật SQLi khác, XSS, Java, Node.js vẫn soi. Đo với APISIX + Coraza như repo, 21 loại
  token × 2 500 giá trị ngẫu nhiên đúng dạng: trước 7/50 951 bị chặn, sau 0/50 968; 16 giá trị đã bị chặn (có giá
  trị trong log CI) nay đều qua. Test scripts +1, smoke +1 kiểm.

### Bảo mật
- Image `svc-files`, `svc-workflow` (cả `ot-sensor`, dùng chung image) gỡ pip ngay sau khi cài thư viện: pip 26.2.1
  của image nền `python:3.13.16-slim` mang theo bản sao cũ của certifi 2026.6.17 (GHSA-6q48-6c7w-9gw2, CRITICAL: gốc
  emSign có CA trung gian lộ khóa), urllib3 2.7.0 (CVE-2026-97687, CVE-2026-97689), msgpack 1.1.2
  (GHSA-6v7p-g79w-8964), setuptools 70.3.0 (CVE-2025-47273). Gói của dịch vụ đã ở bản vá, lúc chạy không dùng pip;
  không thêm, không nâng gói nào. Trivy 0.75.0 quét lại image dựng mới (23/10/2026): lỗ hổng HIGH/CRITICAL có bản sửa
  của mỗi image từ 5 (1 CRITICAL, 4 HIGH) còn 0, phần Python không còn lỗ hổng nào; HIGH/CRITICAL còn lại đều là gói
  Debian chưa có bản sửa.
- Nâng pypdf 6.21.1 → 6.21.2 trong `svc-files` (GHSA-6c7f-9265-g8fw, GHSA-gmh7-3g9r-mjh5, GHSA-jr96-gvgh-j3r4,
  HIGH: PDF tải lên dị dạng làm bước đọc chữ chạy rất lâu); gói kéo theo của `apps/office`: serialize-javascript
  7.1.2 → 7.1.3 (GHSA-m5mm-p8h7-m29v), fast-uri 3.1.8 → 3.1.9 (chỉ lúc dựng, bốn GHSA). Ngoại lệ vá bảo mật ghi ở
  `DEPENDENCIES.md`.

## [1.0.0] - 2026-10-23

Bản cho vòng trường. Văn phòng điện tử chạy đủ luồng văn bản đến và văn bản đi theo NĐ 30/2020 trên lõi dùng chung
(Keycloak, APISIX, Hasura, Flowable), dựng từ mã nguồn bằng `make`.

- Văn bản đến: kiểm dịch ClamAV, poka-yoke ba lớp, vào sổ, chỉ đạo, xử lý, nhắc hạn, thông báo realtime.
- Văn bản đi: soạn, duyệt, ký, cấp số, phát hành PDF có mã QR; sổ đăng ký đến / đi in được; liên thông giữa các
  đơn vị.
- Tin cậy: sổ kiểm toán chuỗi băm neo ra kho không xóa được, cổng xác thực văn bản công khai, văn bản hạn chế mã
  hóa, ký số PAdES (chỉ minh họa).
- AI: đọc văn bản đến, trợ lý hỏi đáp có trích nguồn, gợi ý giao việc; che thông tin cá nhân trước khi gửi mô hình.
- Vận hành: cài ra ngoài thư mục mã nguồn, sao lưu và khôi phục một lệnh, GitOps tự phục hồi, két bí mật OpenBao,
  giám sát, Cloudflare Tunnel.
- CI dựng toàn hệ thống trên mọi thay đổi rồi chạy `make seed` → `make smoke` → `make e2e` cùng các màn demo.

### Đã thêm
- Hộp việc của `giamkhao` không còn trống sau `make seed`: có công văn khẩn 152/ĐT-ĐH chờ xử lý và dự thảo phúc đáp
  bị tổ trưởng trả lại chờ sửa — giám khảo đăng nhập là thấy ngay luồng làm việc của chuyên viên.
- Cloudflare Tunnel (F1.9, profile `tunnel`, tùy chọn): máy không có IP công khai (laptop, máy ở nhà) ra Internet có
  HTTPS mà không mở cổng nào — dịch vụ `cloudflared` (`cloudflare/cloudflared:2026.10.0`, Apache-2.0, ghim digest) gọi
  ra Cloudflare và chuyển yêu cầu vào APISIX qua mạng Docker; token đọc từ tệp ngoài repo (`MOC_TUNNEL_TOKEN_FILE`,
  mặc định `/home/moc/cloudflared-tunnel`). Biến mới `MOC_EXTRA_PROFILES` (vd `tunnel`): `make up/down/ps/logs` kèm
  các profile này, `make install` ghi `COMPOSE_PROFILES=core,app,<…>` cho bản cài. Cổng APISIX: proxy tin cậy nói
  `https` mà không gửi `X-Forwarded-Port` (Cloudflare không gửi) thì route Keycloak nhận cổng 443, không phải 9080 —
  không thì không đăng nhập được qua tunnel. `docs/trien-khai.md` mục 5b; test scripts +7.
- README tiếng Anh (`README.en.md`, F2.11): dịch đúng README.md (bài toán, tính năng, trợ lý AI, bằng chứng 4
  nguyên lý, kiến trúc, cài đặt, vận hành, kiểm thử), liên kết hai chiều ở đầu hai tệp.
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
- Đọc văn bản đến (F4.1): văn thư kéo thả công văn PDF hoặc ảnh chụp vào "Tiếp nhận văn bản", tệp quét sạch thì tác tử
  `moc-doc-reader` tự đọc một lần và điền sẵn số ký hiệu, ngày ban hành, cơ quan ban hành, loại, độ khẩn, trích yếu —
  mỗi ô có nhãn "Gợi ý" / "Gợi ý (chưa chắc)" / "Gợi ý của mô hình", sửa thì thành "Đã sửa"; **tác tử không tạo văn
  bản**, văn thư đối chiếu bản gốc rồi lưu như cũ. `POST /api/files/{id}/read` (svc-files, module `docread`): chỉ văn
  thư, chỉ tệp chính mình tải lên; PDF có lớp chữ đọc theo bố cục (pypdf `layout`), ảnh và bản scan nhận dạng chữ bằng
  Tesseract (`tesseract-ocr` + `tesseract-ocr-vie` trong image); **quy tắc quyết mọi trường** (`rules.py`, thuần Python,
  bố cục NĐ 30), chữ từ OCR không trường nào được mức "chắc chắn". Đọc trong tiến trình con có giới hạn bộ nhớ / CPU /
  thời gian (quá giờ giết cả nhóm tiến trình), Pillow có trần điểm ảnh, một lượt đọc một lúc (`503 busy`), hạn tổng 50
  giây. Không bao giờ ghi đè chữ văn thư đã gõ: chỉ điền ô trống, ô còn mặc định chưa chạm, ô tác tử điền mà chưa sửa;
  độ tin cậy thấp chỉ hiện "Gợi ý: … [Dùng]". Số đo trên 14 văn bản mẫu đầu (mức trần — mẫu sạch hơn công văn thật): PDF
  có chữ 10/10 mọi trường, 0,6 giây; bản scan 3–4/4 từng trường, 1,2 giây (bảng ở README svc-files).
- Tác tử có danh tính và có sổ: vai trò Hasura mới `agent` (svc-files gọi bằng khóa quản trị + `X-Hasura-Role: agent`,
  preset ép danh tính `moc-doc-reader`, `actor_kind = agent`, thuê ước) chỉ thêm / sửa gợi ý và thêm dòng sổ
  `intake.suggested` về tệp của đơn vị trong phiên, không có quyền nào trên văn bản. Migration
  `1792281601900_intake_suggestions`: bảng `office.intake_suggestions` (gợi ý theo tệp, đọc lại thì ghi đè) và view
  `office.v_intake_accuracy` (lãnh đạo, quản trị đơn vị: bao nhiêu gợi ý văn thư giữ nguyên khi lưu). Gợi ý và dòng sổ
  đi trong một giao dịch — không ghi được sổ thì không trả gợi ý; dòng sổ chỉ có siêu dữ liệu (cách đọc, số trang, tên
  các trường tìm thấy, thời gian), không số ký hiệu, trích yếu hay chữ nào của văn bản. Sổ kiểm toán hiện "Trợ lý đọc
  văn bản (tác tử)".
- Mô hình ngôn ngữ cục bộ, tùy chọn: profile Compose `ai` (Ollama 0.35.1 ghim digest, mạng nội bộ riêng chỉ svc-files
  nối được, không mở cổng, tắt tính năng đám mây, giới hạn bộ nhớ / lõi `MOC_AI_MEM_LIMIT`, `MOC_AI_CPUS`) và `ai-pull`
  (tải Qwen3-1.7B, Apache-2.0, vào volume `ollama_models`); `make ai-model`, `make up-ai`. Mô hình **chỉ viết trích
  yếu**, chỉ khi quy tắc chưa ra trích yếu chắc chắn: thân văn bản trong thẻ riêng, ép JSON Schema, đầu ra kiểm chặt
  (độ dài, một dòng, không liên kết, địa chỉ thư, dãy số dài) — sai thì giữ trích yếu theo quy tắc. Không bật `ai`
  (mặc định, CI) thì mọi thứ vẫn chạy, trích yếu theo quy tắc. `/readyz` của svc-files báo thêm `ai`.
- Văn bản đến mẫu hư cấu `seed/van-ban-den/` (lúc đầu 10 PDF có lớp chữ, 4 ảnh / bản scan, ~1 MB; nay 22 văn bản, xem
  gạch cuối mục; nhãn đúng trong `nhan.json`) và `scripts/van_ban_mau.py` sinh lại (`make van-ban-mau`); TSV Tesseract
  của bản scan cho test. `make demo-doc-van-ban` (6 bước, cũng là bước CI) và `make do-doc-van-ban` (đo trên mọi mẫu qua
  APISIX, bảng đúng / sai / trống từng trường, thoát 1 khi PDF có chữ dưới ngưỡng — bước CI); `make smoke` +3 (tổng
  63); e2e `doc-van-ban.spec.ts` (`make e2e` gắn văn bản mẫu vào container Playwright); CI kiểm cấu hình profile `ai`,
  `ai-pull`. Test: CSDL +35, svc-files +243, giao diện +13.
- Trợ lý hỏi đáp trên kho văn bản (F4.2): trang "Hỏi đáp" (`/hoi-dap`: văn thư, chuyên viên, lãnh đạo phòng, lãnh đạo
  đơn vị; nút "Hỏi trợ lý" ở Tìm kiếm) — hỏi bằng câu tự nhiên, nhận **câu trích nguyên văn** từ văn bản chính người
  hỏi được xem, mỗi câu kèm `[n]` trỏ nguồn "số ký hiệu · tr. n" (bản scan: "trích yếu"), đoạn trích, nút mở văn bản;
  không có căn cứ thì một câu chung "Không tìm thấy văn bản nào bạn được xem có nội dung này". `POST
  /api/documents/ask` (svc-files, gói `assist/`, tự viết, không LlamaIndex): chế độ `extract` tất định, không cần mô
  hình (đường của CI); bật profile `ai` thì giao diện tự gọi tiếp `generate` — Qwen3 chạy tại chỗ viết câu trả lời
  ngắn chỉ từ các đoạn đã hậu kiểm, ép JSON Schema; **máy chủ tự gán `[n]`** cho từng câu theo bằng chứng (bỏ mọi
  `[n]` mô hình tự ghi): mỗi câu phải có một đoạn chứa phần lớn ý mới của câu và mọi số trong câu, một câu không có
  căn cứ là bỏ cả câu trả lời, vẫn trả câu trích; nhãn "Do mô hình ngôn ngữ viết — đối chiếu nguồn trước khi dùng".
  Câu hỏi, câu trả lời không lưu ở đâu cả; một lượt sinh một lúc (`503 busy`), nút "Dừng" hủy luôn lượt sinh trên máy
  chủ, hạn tổng 50 giây.
- Chỉ mục đoạn cho trợ lý: chữ PDF giữ ranh giới trang (cột `core.file_texts.page_starts`, migration
  `1792281602000_assistant`); vòng nền svc-files cắt văn bản thành đoạn ≤ 1 200 ký tự trong từng trang và đồng bộ
  sang chỉ mục Meilisearch `chunks` mỗi 5 giây — chỉ văn bản đến chưa hủy và văn bản đi đã phát hành. Tìm lai từ
  khóa + theo nghĩa (embedder `userProvided`: svc-files tự nhúng qua Ollama bằng Qwen3-Embedding-0.6B, Apache-2.0,
  `MOC_AI_EMBED_MODEL`); không có mô hình (CI) hoặc tìm lai lỗi thì tìm theo từ khóa, kèm một lượt **tìm nới** khi
  chưa đủ đoạn — chiến lược `frequency` của Meilisearch luôn giữ từ hiếm nhất của câu hỏi ("điều kiện"), nên văn bản
  trả lời không chứa từ đó không bao giờ ra; lượt nới tìm từng từ trong cùng phạm vi, cân theo độ hiếm, nhận đoạn có
  ≥ 50 % trọng số câu hỏi, qua hậu kiểm như mọi đoạn. Đoạn mô hình nhúng không nhận được đánh dấu riêng, chỉ tìm
  theo từ khóa, không chặn vòng nền; một lượt đồng bộ chỉ tiến khi mọi tác vụ Meilisearch thành công. Dùng lại
  Meilisearch sẵn có thay Qdrant (QĐ-004 trong `docs/architecture.md`). Sẵn phạm vi dịch vụ và `similar_documents`
  cho gợi ý giao việc (F4.3).
- Tác tử `moc-assistant` có sổ: mỗi câu trả lời một dòng `assistant.answered` về `ai.questions` (vai trò Hasura
  `agent`, như F4.1), chỉ siêu dữ liệu — chế độ, số đoạn, số nguồn được trích, mô hình, thời gian, cảnh báo; không ghi
  được sổ thì không trả lời. Sổ kiểm toán hiện "Trợ lý hỏi đáp"; cột thời gian đổi tên chung "Thời gian xử lý".
  `/readyz` của svc-files báo thêm `assist` (tìm theo nghĩa được chưa, số đoạn chờ nhúng, số đoạn nhúng lỗi). Cấu hình
  sai bị báo: `MOC_AI_EMBED_DIMS` lệch số chiều thật thì tắt tìm theo nghĩa và ghi lỗi, `MOC_ASK_SYNC_INTERVAL_S=0`
  khi bật trợ lý thì không khởi động. Profile `ai` giữ cùng lúc mô hình viết và mô hình nhúng
  (`OLLAMA_MAX_LOADED_MODELS=2`).
- Kho văn bản mẫu hư cấu `seed/hoi-dap/` (6 PDF, 14 trang, một văn bản hạn chế; ~135 KB) với 19 câu hỏi kiểm thử có
  đáp án (`cau-hoi.json`), sinh lại bằng `make hoi-dap-mau`. `make demo-hoi-dap` (cũng là bước CI): văn thư hỏi ra câu
  trích đúng trang, giảng viên hỏi cùng câu thì "Không tìm thấy", nội dung văn bản hạn chế không ai hỏi ra, sổ không
  có chữ nào của câu hỏi. `make do-hoi-dap` (bước CI): recall@3, tỉ lệ từ chối đúng, p50 / p95; thoát 1 khi có nguồn
  bị cấm hoặc recall@3 dưới 80 %. `make smoke` +3 (tổng 66); e2e `hoi-dap.spec.ts`. Test: CSDL +31,
  svc-files +436, giao diện +15, scripts +18.
- Tác tử gợi ý giao việc (F4.3): vào sổ một văn bản đến thì quy trình `van-ban-den` tách hai nhánh song song — bước
  chỉ đạo như cũ (lãnh đạo có việc ngay) và việc giao ra ngoài `goiYGiaoViec` (topic `moc-goi-y`, timer ngắt 10 phút;
  không nối lại, nên svc-files hay tác tử lỗi không chặn văn bản giây nào). Tác tử `moc-assigner` của svc-workflow
  (`advisor.py`) lấy các văn bản đến **đã giao** giống văn bản này qua route nội bộ `POST /internal/similar-documents`
  của svc-files (chỉ token dịch vụ, không có trong OpenAPI, không có route APISIX; câu tìm từ trích yếu; dùng lại truy
  xuất và hậu kiểm F4.2, tìm theo từ khóa luôn kèm lượt tìm nới để từ hiếm như "II" của "học kỳ II" không quyết văn
  bản nào được xét; có mô hình nhúng thì tìm lai, tối đa 3 giây), rồi bỏ phiếu kNN có trọng số, không cần mô hình
  (`suggest.py`): đơn vị chủ trì (chỉ phòng có lãnh đạo phòng), độ tin cậy cao / vừa / thấp, hạn = trung vị số ngày
  của các căn cứ (đẩy qua thứ Bảy, Chủ nhật; văn bản đã ghi hạn thì không gợi ý hạn), tối đa 5 căn cứ. Không đủ văn
  bản tương tự thì không gợi ý; svc-files không trả lời thì ghi `failed`, không thử lại. Biến `MOC_SUGGEST_ENABLED`,
  `MOC_SUGGEST_POLL_INTERVAL_S`, `MOC_SUGGEST_TIMEOUT_S`, `MOC_SUGGEST_MIN_SCORE`, `MOC_ASSIGNER_ID`. Khác kế hoạch:
  nhánh song song từ lúc vào sổ thay cho "ngay trước bước chỉ đạo" (QĐ-005 trong `docs/architecture.md`).
- Khối "Gợi ý giao việc" ở đầu form chỉ đạo của lãnh đạo đơn vị: đơn vị chủ trì, độ tin cậy bằng chữ, hạn đề xuất
  ("n ngày, như các văn bản tương tự"), tối đa 3 căn cứ "số ký hiệu — trích yếu → đơn vị · số ngày" đọc bằng token
  người xem (chỉ văn bản người xem đọc được). "Dùng gợi ý" chỉ điền form, lãnh đạo sửa nếu muốn rồi tự bấm giao; chip
  "Theo gợi ý" / "Khác gợi ý". Văn bản hạn chế không hiện khối.
- Gợi ý lưu ở bảng `office.assignment_suggestions` (migration `1792281602100`, một dòng mỗi văn bản; căn cứ chỉ là id,
  điểm, đơn vị, số ngày) cùng một dòng sổ `assignment.suggested` của `moc-assigner` (vai trò Hasura `agent`) trong
  một mutation — tự hiện ở tab Lịch sử, không có trích yếu; chỉ lãnh đạo đơn vị đọc gợi ý. View
  `office.v_assignment_suggestion_accuracy`: tỉ lệ lãnh đạo giữ đơn vị, giữ hạn, sai số hạn trên dữ liệu thật.
- `make demo-giao-viec` (10 bước, cũng là bước CI; lịch sử giao việc hư cấu `seed/giao-viec/lich-su.json`: 29 văn bản
  của Tổ Đào tạo và Bộ môn KTPM, một mồi hạn chế) — kể cả dừng svc-files: văn bản vẫn tới bước chỉ đạo ngay, gợi ý
  ghi `failed`. `make do-giao-viec` (bước CI): leave-one-out top-1/2/3, độ phủ, sai số hạn, p50 / p95; thoát 1 khi căn
  cứ là văn bản hạn chế hoặc top-1 dưới 60 %. Trên dữ liệu thử: top-1 29/29 (gốc "luôn đoán đơn vị đông nhất" 55 %;
  dữ liệu chia cụm gọn và chỉ 2 đơn vị nên cao hơn thực tế), sai số hạn trung bình 1,1 ngày, một lần gợi ý p50 71 ms.
  `make smoke` +5 (tổng 71); e2e `giao-viec.spec.ts`. Test: CSDL +47, svc-files +54, svc-workflow +93, giao
  diện +13, scripts +24.
- Kho văn bản đến mẫu của F4.1 (`seed/van-ban-den/`) lên 22 văn bản (15 PDF có lớp chữ, 7 ảnh / bản scan) để đo đúng
  "Hoàn thành khi" của Phase 4 (trên 20 công văn mẫu). 8 mẫu mới thêm ở cuối, khó hơn 14 mẫu đầu: hướng dẫn hai trang,
  nghị quyết HĐND, thông báo kết luận, kế hoạch liên tịch, công văn bệnh viện; ký hiệu ba đoạn, có năm, số có chữ cái
  phụ; ngày viết không theo NĐ 30 ("ngày 5 tháng 03", `12/10/2026`); ảnh chụp điện thoại nghiêng 3,2° trên mặt bàn, bản
  scan nền xám, PDF scan 3 trang. Nội dung 14 mẫu cũ giữ nguyên; cả 22 tệp in bằng `make van-ban-mau` trong image
  svc-files nên chạy lại ra đúng từng byte (10 PDF cũ khác byte bản trước vì bản phông nhúng; mẫu 04 ngắt một dòng khác,
  chữ không đổi). Ngưỡng của `make do-doc-van-ban` và `test_docread_samples.py` đổi sang tỉ lệ cùng độ nghiêm (≥ 90 % /
  ≥ 80 %, không ô `high` nào sai); `make do-doc-van-ban` còn thoát 1 khi cả kho dưới 20 văn bản hay số ký hiệu, ngày ban
  hành đúng không quá nửa; ngưỡng TSV chốt cho cả 7 bản scan. Số đo trên 22 văn bản: số ký hiệu đúng 20/22, ngày ban
  hành đúng 22/22 (bảng đủ trong README svc-files).
- Ký số văn bản đi (F4.5, **chỉ minh họa** — không có giá trị pháp lý như chữ ký số công cộng): `/internal/issue` ký bản
  phát hành không hạn chế theo PAdES B-B (chữ ký chứng nhận không cho sửa, ô ký ẩn) **trước khi băm**, nên
  `content_sha256`, sổ kiểm toán, bản liên thông và cổng xác thực đều theo bản đã ký. Khóa RSA-3072 của từng đơn vị
  (`moc-ky-so-<đơn vị>`) sinh và nằm trong Transit của két, `svc-files` chỉ nhờ két ký; chứng thư 1 năm do CA nội bộ một
  tầng trong két cấp (`openbao/start.sh` dựng mount `pki`, CA `moc-root`, role `moc-van-thu` khi khởi tạo két mới). Tự
  kiểm bằng pyHanko trước khi lưu; tệp và dòng `core.file_signatures` ghi trong một mutation. Két chưa có PKI → ký số tự
  tắt (nhật ký `office.signing.disabled`, dò lại sau 5 phút); ký lỗi → phát hành không ký
  (`office.document.sign_failed`); két không trả lời → `503 signing_unavailable`. Văn bản hạn chế không bao giờ ký. Tắt
  bằng `MOC_SIGN_ENABLED=false`.
- Migration `1792281602200_file_signatures`: bảng `core.file_signatures` (chuẩn, giờ ký tự khai, người ký, CA, số
  sê-ri, vân tay chứng thư, khóa và phiên bản Transit; sổ kiểm toán), `svc-files` chỉ thêm; khung nhìn cổng xác thực
  `office.issued_documents` thêm năm cột chữ ký, tìm theo băm nên văn bản đã nộp lưu vẫn hiện chữ ký; chỉ mục
  `core.files (tenant_id, sha256)`. `/api/verify*` trả thêm `document.signature` (`illustrative: true`).
- Cổng xác thực `/xac-thuc/<mã>` có khối "Chữ ký số (minh họa)": chuẩn, người ký, CA, số sê-ri, giờ ký, chú thích luôn
  hiện "chỉ để minh họa — không có giá trị pháp lý…"; văn bản không ký (trước F4.5, ký số tắt hay ký lỗi) hay văn bản
  hạn chế ghi "không có chữ ký số, tính nguyên vẹn vẫn kiểm bằng SHA-256".
- `python -m svc_files.signing verify [--ca TỆP] < tệp.pdf` (trong container svc-files): kiểm bằng pyHanko, chỉ tin CA
  nội bộ, không tải gì từ mạng; dòng đầu nói kết quả (hợp lệ / đã sửa sau khi ký / không khớp nội dung / CA lạ / không
  có chữ ký / không đọc được), mã thoát 0/1/2.
- Màn demo `make demo-ky-so` (8 bước, cũng là bước CI): CA trong két → phát hành → `/ByteRange` phủ cả tệp, cổng xác
  thực có chữ ký, CSDL cùng số sê-ri → CLI hợp lệ → thêm một lớp sửa ghi nối: "đã bị sửa sau khi ký", băm cả tệp
  không khớp → lật một bit: "không khớp nội dung" → văn bản hạn chế phát hành không chữ ký → văn bản cũ xác thực như
  trước. `make smoke` +5 kiểm (bỏ qua, in lý do, khi két chưa có PKI hay tắt ký số); e2e `van-ban-di.spec.ts` kiểm
  khối chữ ký. QĐ-007 trong `docs/architecture.md`, mục ký số ở README, README svc-files, `docs/mo-hinh-du-lieu.md`,
  `docs/demo-script.md`. Phụ thuộc mới của svc-files: pyHanko 0.37.0, pyhanko-certvalidator 0.32.1 và 15 gói kéo
  theo, ghim kèm băm (`DEPENDENCIES.md`). Test: CSDL +28, svc-files +28, scripts +22, giao diện +5.
- Che thông tin cá nhân (F4.4): bộ nhận dạng `pii.py` tự viết, chỉ dùng `re` của thư viện chuẩn — không Presidio,
  không thêm phụ thuộc (`DEPENDENCIES.md` xếp Presidio, phonenumbers vào "đã cân nhắc nhưng không dùng"). Nhận theo
  cấu trúc, không theo "dãy số đủ dài": số định danh / CCCD 12 số (mã tỉnh, chữ số thế kỷ, năm sinh), số điện thoại
  (đầu số di động đã cấp, máy bàn `02x`, `+84`, mã vùng `(024)`, viết liền hay theo nhóm), email; CMND và số tài khoản
  chỉ khi đứng sau từ khóa. Nhóm số cách nhau một ký tự trắng bất kỳ, nên số bị dàn trang ngắt dòng trong chữ PDF, OCR
  ("0912 345⏎678") vẫn bị che; nhóm đầu ≥ 3 chữ số, nên dãy số nhỏ của bảng, lịch ("Tuần 01 02 03 04 05 06") không bị
  che; bộ che lặp tới điểm bất động (idempotent). Không che UUID, số ký hiệu, ngày, tiền, tổng đài 1800 / 1900, mã số
  thuế sau "MST". Dòng lệnh `python -m svc_files.pii mask|count` (`count` không in giá trị); `svc_workflow/pii.py` là
  bản chép y hệt byte, test đỏ khi hai bản lệch.
- Mô hình chạy tại chỗ chỉ nhận bản đã che (F4.4): mọi lời gọi Ollama — nhúng đoạn, câu hỏi, trích yếu (F4.2, F4.3),
  viết câu trả lời (F4.2), viết trích yếu (F4.1, che trước khi cắt `MOC_AI_MAX_CHARS`) — qua bộ che ở lối ra; `chat`
  còn phải che thêm thì cảnh báo `office.assist.pii_at_egress`. Ngữ cảnh F4.2 dùng nhãn đánh số theo lượt (`[SĐT-1]`,
  cùng số cùng nhãn ở câu hỏi và đoạn), che rồi mới cắt cửa sổ 700 ký tự nên không lọt mẩu số, trích dẫn `[n]` và
  trang không lệch. Chỉ mục tìm kiếm, câu trích nguyên văn, nguồn trả người hỏi và sổ kiểm toán giữ số thật. Trích yếu
  mô hình viết có nhãn che bị loại (`model_rejected`). `office.assist.asked`, `office.assist.model_rejected`,
  `office.intake.read` thêm khóa `masked` (số chỗ đã che, không có giá trị). Kho mẫu không có chỗ nào bị che, nên số
  đo `make do-hoi-dap` không đổi.
- Nhật ký không mang thông tin cá nhân (F4.4): svc-files, svc-workflow gắn `PiiFilter` vào logger dịch vụ và uvicorn
  (`uvicorn.error`, `uvicorn.access`), che cả traceback; che hỏng thì cả dòng thành `core.log.redaction_failed`. Tệp bị
  chặn tên `don-0912345678.txt` ghi `don-[SĐT].txt` ở nhật ký, sổ kiểm toán giữ tên gốc. Nhật ký truy cập của uvicorn,
  APISIX (`gateway/config.yaml`) và nginx của app-office bỏ chuỗi truy vấn (`?q=…`, `?code=…`); APISIX, nginx bỏ cả
  Referer, và giao diện gửi `Referrer-Policy: strict-origin` (trước là `same-origin`) nên Referer chỉ còn gốc tên miền.
  Bỏ hẳn chứ không che bằng regex: chuỗi truy vấn mã hóa phần trăm thì bộ che không nhận ra (`gateway/README.md`).
- Trang Hỏi đáp: câu trả lời mô hình viết có nhãn che (`[SĐT-1]`…) thì ghi rõ số thật nằm trong văn bản nguồn (câu trích
  nguyên văn, các nguồn bên dưới) và tự mở khối câu trích (F4.4); mẫu nhãn của giao diện trùng `LABEL_RE` của `pii.py`
  (test so hai mẫu).
- Màn demo `make demo-che-pii` (F4.4, 7 bước, cũng là bước CI): văn thư nhận lá đơn hư cấu có CCCD, số di động, máy bàn,
  email, số tài khoản → tìm theo số CCCD ra đúng đơn, trợ lý trích nguyên văn có số thật → tệp EICAR tên có số điện
  thoại bị chặn → nhật ký `apisix`, `app-office`, `svc-files`, `svc-workflow` không còn giá trị nào ở mọi cách viết,
  dòng truy cập không còn `?q` → bật mô hình thì `office.assist.asked` có `masked` ≥ 2, không bật thì in bản che.
  `make do-che-pii` (không cần Docker, đã chạy trong `make test`): che nhầm trên kho mẫu và 15 đột biến mã của `pii.py`.
  Đo 22/10/2026: 22 văn bản đến (15 PDF có lớp chữ, 7 bản scan), 6 văn bản hỏi đáp, 1 248 chuỗi nhãn, câu hỏi, lịch sử
  giao việc — 81 023 ký tự, 747 chuỗi số ứng viên, **0 chỗ bị che**; 15/15 đột biến bị giết. QĐ-006 trong
  `docs/architecture.md`, mục che thông tin cá nhân ở README svc-files, `docs/demo-script.md`, `gateway/README.md`.
  Test: svc-files +62, svc-workflow +6, scripts +19, giao diện +3.
- Tài liệu triển khai lên máy chủ [`docs/trien-khai.md`](docs/trien-khai.md) (F1.9): Caddy nhận HTTPS (Let's Encrypt)
  trước APISIX chỉ nghe `127.0.0.1`, người vận hành `moc`, tường lửa, cài ra `/opt/moc`, lệnh kiểm sau khi lên, sao lưu
  hằng đêm, nâng cấp. Biến `.env` mới `MOC_TRUSTED_PROXY` (mặc định `127.0.0.1/32`, không tin ai): APISIX giữ
  `X-Forwarded-Proto`, `-Host`, `-Port` và lấy IP người dùng từ `X-Forwarded-For` chỉ với yêu cầu từ dải này
  (`gateway/README.md`). Diễn tập 22/10/2026 trên máy dev: proxy TLS ở cổng 443 trước bản cài, smoke, e2e, màn demo
  qua `https://`.

### Đã sửa đổi
- Quy trình Git chuyển sang Git Flow (`docs/git_flow.md`): `develop` là nhánh mặc định, mọi pull request vào đó;
  `main` chỉ nhận PR phát hành `chore(release): vX.Y.Z` từ `develop` hoặc `hotfix/X.Y.Z`. Workflow mới **PR**
  (`scripts/check_pr.py`) kiểm nhánh nguồn, tiêu đề theo Conventional Commits với loại và phạm vi trong danh sách,
  và với PR vào `main` thì CHANGELOG có mục phiên bản có dòng thay đổi, thẻ chưa có; CI chạy cho cả `develop` và
  `main`, hủy lượt cũ trên mọi nhánh trừ `main`; workflow Release dừng khi thẻ không nằm trên `main`. Ruleset khai
  trong `.github/rulesets/` (PR, 1 duyệt, 8 job xanh; thẻ `v*` không sửa, không xóa được). Mục 11 của `git_flow.md`
  ghi cách làm thực tế trước và sau 23/10/2026. Test scripts +21.
- Đổi tên hiển thị Mộc → **Signet** (nhẫn ấn đóng dấu lên văn bản, giữ ý "đóng dấu" của tên cũ): giao diện (`<title>`,
  thanh bên, trang đăng nhập, cổng xác thực, biểu tượng con dấu thay hình cây), realm Keycloak (`displayName`, tên
  client), tiêu đề API, chuỗi in ra của CLI và script, bảng điều khiển Grafana "Signet — cổng API", PDF phát hành và sổ
  in, mẫu issue, tài liệu, header giấy phép `Signet Team`. Tên mã kỹ thuật `moc` giữ nguyên: biến `MOC_*`, realm `moc`,
  client id, project compose, image, `scripts/moc.py`, `/opt/moc`, tiêu đề `X-Moc-*`, gói `moc-X.Y.Z.tar.gz`. Bản cài
  cũ: Keycloak chỉ nạp realm ở lần khởi động đầu nên trang đăng nhập Keycloak còn tên Mộc tới khi đổi Display name của
  realm trong trang quản trị; két đã dựng PKI giữ CA tên cũ (chữ ký vẫn kiểm được), két mới có "CA nội bộ Signet - MẪU".
  Văn bản mẫu đã commit (kho văn bản đến, kho hỏi đáp) giữ chân trang "chạy thử Mộc" — đổi là phải in lại PDF, đo lại.
- README viết lại gọn (bài toán, bốn con dấu của lõi, tính năng, bằng chứng bốn nguyên lý, kiến trúc, cài đặt, kiểm
  thử); sáu mục vận hành (thêm đơn vị, sao lưu, két bí mật, GitOps, giám sát, IT/OT) chuyển nguyên văn sang
  `docs/van-hanh.md`, các chỗ trỏ "README mục …" trỏ theo.
- Văn thư không còn ghi thẳng bảng văn bản (`insert_office_documents_one`, `update_office_documents`) lẫn bảng tệp
  đính kèm (`insert_office_document_files_one`, `delete_office_document_files`): văn bản đến kèm tệp vào qua Action
  `receiveIncoming(data: jsonb!)`, nên không đi vòng được lớp kiểm của svc-workflow. Sửa văn bản đến chưa vào sổ
  không còn qua GraphQL (giao diện chưa từng dùng). Migration dọn văn bản đến đã có (khoảng trắng thừa, ký tự ẩn,
  dạng Unicode tổ hợp) trước khi thêm ràng buộc; dòng nào còn sai thì cảnh báo kèm mã văn bản. Sổ kiểm toán ghi lần tiếp nhận là
  `svc-workflow` làm thay văn thư, kèm đúng người bấm. Ngày "hôm nay" của giao diện tính theo giờ Việt Nam (#34).
- Hasura chờ `completeTask` tới 90 giây (trước là 30): phát hành gồm cấp số, dựng PDF, quét, lưu kho, máy chậm có thể
  quá 30 giây. Cổng APISIX chờ Hasura 100 giây (mặc định 60).
- `make seed` tạo Organization cho hai đơn vị mẫu (`cntt`, `kt`) và đưa tài khoản mẫu vào (cùng hàm với
  `moc tenant create`, chạy lại thì giữ nguyên); realm bật `organizationsEnabled` — bản đã dựng thì `make seed` tự bật,
  không cần `make reset`.
- Tiếp nhận văn bản đến (F4.1): giao diện gọi tác tử đọc khi tệp quét sạch; `make down`, `make reset` dừng cả profile
  `ai`, `ai-pull`; `.gitignore` theo dõi `seed/van-ban-den/*.pdf`; `scripts/license-header.sh` coi `*.tsv` là dữ liệu.
- Trợ lý hỏi đáp (F4.2): `make ai-model` kéo cả mô hình nhúng (`MOC_AI_EMBED_MODEL`, mặc định
  `qwen3-embedding:0.6b`, khoảng 640 MB) và `MOC_ASK_MODEL` khi đặt riêng. Hàng đợi đọc chữ (F2.7) đọc thêm bản phát
  hành của văn bản đi; migration `1792281602000` xóa các dòng chữ đã đọc để đọc lại một lần, lần này có ranh giới
  trang — ngay sau khi nâng cấp, tìm theo nội dung có thể thiếu trong vài phút.
- Gợi ý giao việc (F4.3): "Báo cáo xong" cập nhật văn bản trước giao việc, cùng thứ tự khóa với tác tử, nên hai
  bên không chờ vòng nhau. Test BPMN của nhắc hạn chỉ xét timer gắn vào việc của người, tìm worker nhắc hạn theo topic
  `moc-sla`.
- Trợ lý hỏi đáp (F4.2): tìm theo từ khóa luôn kèm lượt tìm nới (không chỉ khi chưa đủ đoạn), rồi xếp chung mọi đoạn
  theo tỷ lệ trọng số câu hỏi mà đoạn có. Trước đây đoạn của lượt chính luôn đứng trước: hỏi "Điều kiện xét học bổng
  khuyến khích học tập là gì?" khi kho có vài công văn "đủ điều kiện xét tốt nghiệp" thì ba nguồn đầu đều lạc đề, công
  văn trả lời đứng thứ tư. Từ phổ biến (kết quả mỗi từ chỉ lấy một số đoạn đầu) vẫn được tính cho đoạn có nguyên văn
  từ đó; lượt nới lỗi thì giữ kết quả lượt chính.

### Đã sửa lỗi
- Ô chữ đại diện ở đầu trang lấy chữ đầu của từ cuối trong họ tên và không viết hoa: "Tài khoản Giám khảo" ra "k".
  Nay lấy chữ đầu của tên (claim `family_name` — firstName của Keycloak là họ và đệm), viết hoa: G. README ghi thiếu tổ
  trưởng, trưởng bộ môn trong các vai trò bắt buộc TOTP; lời nhắc cuối `seed.py` thêm lệnh của bản cài
  (`python3 scripts/totp.py` — `/opt/moc` không có Makefile).
- Sau Cloudflare Tunnel, `seed.py` và `smoke.py` dừng với "APISIX chưa sẵn sàng" dù trang vẫn mở được: Browser
  Integrity Check của Cloudflare trả 403 cho User-Agent mặc định `Python-urllib`. Các kịch bản giờ gửi
  `User-Agent: Signet-scripts`.
- Trang văn bản: thông báo realtime đến đúng lúc bấm thao tác (vd lời nhắc quá hạn khi văn thư phát hành) làm hai
  lượt tải chồng nhau, lượt cũ về sau đè lượt mới — văn bản vừa phát hành hiện lại "Đã duyệt", thẻ liên thông
  thôi hỏi lại trạng thái. Lượt tải cũ giờ bỏ kết quả (như trang văn bản đến); hộp việc cũng vậy.
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
- svc-workflow gọi svc-files (phát hành, gửi liên thông, tìm văn bản tương tự) không còn hỏng "token không hợp lệ"
  sau khi máy chủ ngủ hay VM bị tạm dừng: token dịch vụ giữ trong bộ nhớ tính hạn theo đồng hồ monotonic, đồng hồ này
  đứng yên lúc máy ngủ nên token đã hết hạn vẫn được dùng. Nay tính theo giờ thật như `exp` của token; svc-files vẫn
  trả 401 thì bỏ token, lấy token mới và gửi lại đúng một lần (nhiều lời gọi cùng lúc chỉ hỏi Keycloak một lần).
- Đặt sau proxy TLS (máy chủ có HTTPS) thì không đăng nhập được: APISIX 3.18 thay `X-Forwarded-Proto` của proxy bằng
  `http`, Keycloak trả `token_endpoint` dạng `http://…`, trình duyệt chặn (nội dung hỗn hợp, CSP `connect-src
  'self'`); mọi người dùng chung một bộ đếm giới hạn tốc độ. Nay khai `MOC_TRUSTED_PROXY` (xem phần Đã thêm).
- `make demo-che-pii`, `make demo-hoi-dap` trên bản cài mới: bước đợi chỉ mục dừng ngay khi văn bản có trong nguồn
  qua trích yếu (vào chỉ mục lúc tiếp nhận), lúc chữ các trang chưa được đọc, nên câu trả lời thiếu đoạn cần trích
  và màn đỏ. Nay đợi tới khi một trang của văn bản có trong nguồn (test scripts +4).
- Kịch bản dòng lệnh (smoke, demo) đỏ "Invalid user credentials" khi mã TOTP của khoảng 30 giây vừa được dùng ở
  nơi khác (đăng nhập trên trình duyệt, e2e chạy từ thư mục mã nguồn trong khi kịch bản chạy từ bản cài — hai nơi
  không chung sổ mã): Keycloak 26 trả 400 cho mã đã dùng y như sai mật khẩu, còn bước thử mã kế tiếp chỉ chờ 401
  nên không bao giờ chạy. Nay thử tối đa bốn mã liền nhau, cách nhau 1,5 giây — ba mã đang hiệu lực đều đã bị
  dùng thì đợi sang khoảng 30 giây mới (test scripts +4).

- Soạn văn bản đi: đang sửa một dự thảo mà bấm "Soạn văn bản đi" ở thanh bên (cùng trang, chỉ bỏ `?id=`) thì form
  còn nội dung, tệp, cờ hạn chế của dự thảo trước và Lưu tạo một văn bản mới chép từ nó. Nay đổi `?id=` là dựng lại
  trang (e2e `van-ban-di.spec.ts` kiểm); dự thảo hạn chế chỉ cho chọn tệp PDF ngay ở ô chọn tệp.
- Trình văn bản đi (`submitOutgoing`): lần trình đầu lỗi sau khi quy trình đã khởi chạy, trình lại với người ký khác
  thì việc ký vẫn giao cho người chọn lần trước — nay ghi lại người ký vào quy trình trước khi ghi CSDL; quy trình đã
  qua bước duyệt cấp phòng thì từ chối (409 `signer_locked`). Trả lại đã ghi mà Flowable chưa sang bước sửa, người
  soạn trình lại ngay thì CSDL là "đang duyệt" còn quy trình quay về bước sửa, người soạn kẹt — nay trả 409
  `return_pending`, không ghi gì. Test svc-workflow +7.
- Nộp lưu hồ sơ (F3.8) không còn làm tụt số liệu dashboard điều hành (F3.11) và số đo đọc văn bản đến (F4.1): hàm
  nộp lưu gỡ dòng thời gian, liên kết tệp mà hai khung nhìn tính từ đó, nên văn bản đã nộp lưu rơi khỏi số văn bản,
  số giờ, số đúng hạn của các tháng cũ. Nay lúc xong và tệp bản chính giữ ở `office.archived_document_facts` trong
  cùng giao dịch; văn bản nộp lưu trước bản sửa được điền lại từ sổ kiểm toán khi chạy migration. Test CSDL +1.
- Ghi chú trang Release lấy từ CHANGELOG: mục cuối kéo theo khối mẫu trong chú thích HTML (trang v0.1.0 đã đăng có
  các dòng `### Đã thêm … -->` thừa), thiếu mục thì vẫn đăng Release với một câu thay thế. Nay
  `scripts/release-notes.sh` (dùng ở `release.sh` và workflow Release) bỏ qua chú thích HTML; thiếu mục, hay mục chỉ
  có tiêu đề nhóm, thì `release.sh` không gắn thẻ và workflow dừng. Test scripts +5.

### Bảo mật
- Mọi image bên thứ ba (`docker-compose.yml`, các `Dockerfile`, image Playwright của `make e2e`) ghim thêm digest
  (`thẻ@sha256:…`, index đa nền tảng đã chạy CI): thẻ bị đẩy lại không đổi được bản máy chủ kéo về. Ba thẻ đã bị đẩy
  lại từ lúc đội kéo (`postgres:16-alpine`, `python:3.13.16-slim`, `clamav/clamav:1.5.4`) — nay vẫn chạy đúng bản đã
  kiểm. Cách nâng phiên bản: `DEPENDENCIES.md` mục Cách đọc.
- GitOps chỉ áp commit đã ký khi đặt `MOC_GITOPS_ALLOWED_SIGNERS` (tệp allowed_signers, khóa SSH của người được đẩy
  nhánh `deploy`): reconciler `git verify-commit` trước khi dừng Mộc; chưa ký, khóa lạ, chữ ký OpenPGP/X.509 (kể cả khi
  keyring của người dùng `moc` tin khóa đó) thì không áp, Mộc chạy tiếp bản cũ. Để trống thì như trước (`docs/van-hanh.md`
  mục GitOps; `docs/git_flow.md` mục 7: đẩy nhánh bằng `git merge --no-ff -S`). Test scripts +4.
- Không phát hành lại một phiên bản: `release.sh` dừng trước khi gắn thẻ khi thẻ `vX.Y.Z` đã có trên `origin` (không
  hỏi được `origin` cũng dừng) hay chỉ có ở máy (gợi ý gỡ thẻ của lần chạy dở); workflow Release dừng khi thẻ đã có
  Release, kể cả bản nháp mà GitHub để lại khi xóa thẻ của Release đã đăng; action không ghi đè tệp cùng tên, thiếu
  tệp thì lỗi, và một bước sau báo lỗi khi không tải lên đủ hai tệp. Gói `.tar.gz`, `.sha256` người dùng đã tải về
  không bị thay dưới cùng tên. Test scripts +14 (chạy lệnh của bước workflow với `gh` giả).
- Ký số (F4.5): khóa ký của từng đơn vị không ra khỏi két (policy `svc-files` chỉ có `transit/keys|sign/moc-ky-so-*`
  và `pki/sign/moc-van-thu`, không `export`, `backup`). Ai chiếm được `svc-files` vẫn ký được, xoay được khóa ký và xin
  được chứng thư cho khóa tự sinh, nhưng không mang khóa riêng đi được — cùng mức tin như khóa dữ liệu `moc-files`
  (`docs/van-hanh.md` mục Két bí mật). Két khởi tạo trước F4.5 không ký số cho tới khi quản trị nâng cấp tay (cùng
  mục).
- Che thông tin cá nhân (F4.4): sổ kiểm toán cố ý giữ bản gốc (có phân quyền và chuỗi băm, che vào là sửa chứng cứ), số
  chỗ đã che chỉ ghi ở nhật ký. Chưa che: họ tên, địa chỉ, số dính chữ (`ĐT0912…`), CMND và số tài khoản không có từ
  khóa; nhật ký Hasura, PostgreSQL, Keycloak, Meilisearch và `error_log` của APISIX, nginx (vẫn có `?q=…` khi một plugin
  ghi lỗi) không qua bộ che; véc-tơ nhúng tính trước F4.4 còn tới khi nhúng lại (README svc-files).
- Văn bản hạn chế (F3.7) không bao giờ có gợi ý đọc tự động (F4.1): svc-files trả `409` trước khi đọc byte nào —
  tệp mã hóa, hay tệp rõ còn gắn vào văn bản hạn chế (dữ liệu có từ trước F3.7) — nên không tới OCR, không tới mô
  hình; trigger `intake_suggestions_guard` chặn thêm ở CSDL việc lưu gợi ý của các tệp đó, xóa gợi ý khi văn bản bật
  hạn chế. Vai trò `agent` không đọc, ghi văn bản; dòng sổ và nhật ký của tác tử không mang nội dung văn bản.
- Trợ lý hỏi đáp (F4.2) chỉ dựa trên văn bản người hỏi được xem: lọc trước theo vai trò ngay trong chỉ mục (viết như
  `office.document_visible`), rồi hậu kiểm bằng Hasura với token người hỏi — cả hai trước mô hình và trước người dùng,
  nên chỉ mục còn cũ cũng không làm lộ; văn bản hạn chế không bao giờ vào chỉ mục, bật hạn chế là xóa mọi đoạn. Chữ
  văn bản đưa cho mô hình nằm trong thẻ riêng, thẻ giả trong văn bản bị bỏ. Dòng sổ và nhật ký của trợ lý không mang
  câu hỏi, câu trả lời hay đoạn trích.
- Văn bản hạn chế không bao giờ có gợi ý giao việc và không bao giờ làm căn cứ (F4.3): svc-files từ chối văn bản
  đích hạn chế trước khi tìm, chỉ mục không có đoạn của văn bản hạn chế, hậu kiểm bỏ văn bản vừa bật hạn chế; trigger
  `assignment_suggestions_guard` khóa văn bản đích và các căn cứ rồi chặn ở CSDL, bật hạn chế sau đó thì xóa gợi ý của
  văn bản và gỡ nó khỏi căn cứ của gợi ý khác. Dòng sổ, nhật ký của tác tử và lệnh đo không mang trích yếu hay chữ nào
  của văn bản.
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

- Pillow 12.3.0 → 13.0.0, pypdf 6.19.0 → 6.21.1 (`svc-files`): vá các lỗ hổng OSV-Scanner báo trong CI (Pillow các
  GHSA đọc ảnh, pypdf 5 GHSA) — cả hai đọc tệp người dùng tải lên; certifi 2026.7.22 → 2026.10.19 (bỏ gốc emSign có
  CA trung gian lộ khóa). Ngoại lệ quy tắc hai tuần, ghi ở `DEPENDENCIES.md`.
- Giới hạn đăng nhập theo IP (F1.2) không còn né được bằng cách viết khác đường (`…/token/`, `…/token;x`): mọi POST
  vào realm qua route `dang-nhap-post`, chung bộ đếm với route đăng nhập. Cổng gỡ thêm `X-Hasura-Access-Key` từ phía
  ngoài (tên cũ của khóa quản trị; Hasura 2.51 đã không nhận — kiểm 22/10 — gỡ để phòng xa).
- Realm `moc` đặt luồng direct grant mặc định là `moc-cli-direct-grant`: client có sẵn `admin-cli` (lấy token bằng
  mật khẩu) cũng phải gửi mã TOTP, không còn là đường vòng qua xác thực hai bước. Stack đã dựng: `make reset` hoặc
  đặt tay (auth/README.md). `make smoke` +3 (tổng 79): đường token viết khác vẫn bị đếm, `admin-cli` không có mã bị
  từ chối, khóa quản trị Hasura từ ngoài (cả tên cũ) không có tác dụng.
- Văn bản hạn chế (F3.7): PDF người dùng tải lên chỉ được kiểm, đóng dấu người xem trong tiến trình con `python -I`
  có trần bộ nhớ, CPU, thời gian (như OCR), tối đa `MOC_RESTRICTED_MAX_PAGES` trang (mặc định 500). Trước đây pypdf
  chạy ngay trong svc-files, không trần trang, hai lượt cùng lúc mà chờ không hạn: một tệp nhiều trang tí hon làm
  treo mọi lần mở tệp hạn chế. Tải lên quá trần, quá nặng: 415 `restricted_pdf_only` kèm `reason`; mở tệp không đóng
  dấu được: 422 `unstampable`; chờ lượt quá 10 giây: 503 `busy` kèm `Retry-After`. Test svc-files +14.
- Sổ kiểm toán không còn lộ danh sách được xem văn bản hạn chế (F3.7) cho lãnh đạo, quản trị đơn vị không đọc được
  văn bản: `overview` đã che nhưng cột thô `entity_id` (`<văn bản>/<người được cấp>`) và `actor_id` (người cấp) thì
  không. Nay cả dòng bị lọc ở quyền Hasura (`office.audit_log_visible`); không sửa dòng sổ nào, chuỗi băm và `make
  audit` giữ nguyên. Test CSDL +1.
- `make env` tạo `.env` quyền 600 (trước đây theo umask, thường 644: người dùng khác trên máy đọc được mật khẩu);
  `make up`, `make install`, `make check` từ chối khi `.env` còn giá trị `change_me` và in tên biến.
- Workflow Release kiểm tên thẻ đúng dạng `vMAJOR.MINOR.PATCH` và đọc phiên bản qua biến môi trường, không chèn
  `${{ }}` vào lệnh shell — tên thẻ chứa `$( )` không chạy được lệnh trong job có quyền ghi kho.

## [0.1.0] - 2026-10-18

Bộ khung dự án: giấy phép Apache-2.0, dựng từ mã nguồn bằng Make và Docker Compose, cấu hình qua `.env`, CI kiểm
header giấy phép, gói phát hành `.tar.gz`, mẫu báo lỗi và PR, tài liệu.

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

<!--
Mẫu cho bản phát hành kế tiếp:

## [x.y.z] - YYYY-MM-DD

### Đã thêm
### Đã sửa đổi
### Đã loại bỏ
### Đã sửa lỗi
### Bảo mật
-->
