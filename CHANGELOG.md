# Lịch sử thay đổi

Mọi thay đổi đáng chú ý của Signet (trước 23/10/2026 tên là Mộc) được ghi lại trong tệp này.

Định dạng theo [Keep a Changelog 1.1.0](https://keepachangelog.com/vi/1.1.0/),
đánh phiên bản theo [Semantic Versioning 2.0.0](https://semver.org/lang/vi/).
Mỗi thay đổi một dòng, kèm số issue hoặc PR trên GitHub; chi tiết xem PR đó và tài liệu của tính năng.

## [Chưa phát hành]

## [1.3.0] - 2026-10-30

Bản cho vòng trường 01/11. Thêm cảnh báo vận hành qua Alertmanager vào chuông của quản trị đơn vị, tự động hóa
Node-RED và wiki nội bộ DokuWiki (đăng nhập Keycloak, tắt mặc định), truy vết phân tán Jaeger (profile `trace`), kênh
SMS, Zalo; tiếng Anh cho sổ đăng ký, văn bản đi và Đơn nghỉ phép; trang Dựng form cho quản trị; hướng dẫn vận hành
tiếng Anh. Log tập trung thu cả Meilisearch; bộ che thông tin cá nhân bắt cả số di động viết liền sau `ĐT`, `SĐT`.
Nâng tại chỗ từ `v1.2.1`; bản cài cũ còn đặt `MOC_TRUSTED_PROXY` là một dải cố định thì đổi tay sang `auto` (#211).

### Đã thêm
- Truy vết phân tán bằng Jaeger qua APISIX, svc-files, svc-workflow (profile `trace`, tắt mặc định) (#364).
- Kênh thông báo SMS, Zalo tắt mặc định; mỗi người tự bật ở cuối chuông thông báo, quản trị nhập số điện thoại (#365).
- Cảnh báo của Prometheus qua Alertmanager thành thông báo ở chuông (và kênh ngoài) của quản trị đơn vị (#284).
- Wiki nội bộ DokuWiki ở `/wiki/` (profile `wiki`, tắt mặc định): đăng nhập Keycloak, mỗi đơn vị một không gian (#367).
- Sổ đăng ký văn bản đến, đi xem và in bằng tiếng Anh khi người in chọn giao diện tiếng Anh (#398).
- Trang Dựng form cho quản trị đơn vị: khai trường, xem trước, tải tệp JSON Schema cho form của ứng dụng (#303).
- Văn bản đi bằng tiếng Anh: người soạn chọn ngôn ngữ, PDF giữ thể thức NĐ 30 với phần cố định tiếng Anh (#398).
- Giao diện tiếng Anh cho Đơn nghỉ phép, cả form dựng từ JSON Schema, chung ngôn ngữ với Văn phòng điện tử (#398).
- Tự động hóa Node-RED ở `/tu-dong/` (profile `tu-dong`, tắt mặc định): đăng nhập Keycloak, chỉ người vận hành (#366).
- Robot của đơn vị cho flow Node-RED gọi API, hai flow mẫu: văn bản sắp hạn lúc 07:00, văn bản Hỏa tốc (#366).
- Hướng dẫn vận hành bằng tiếng Anh `docs/van-hanh.en.md`; README.en.md trỏ sang bản này (#59).

### Đã sửa đổi
- Log tập trung thu cả Meilisearch: nhật ký JSON, Vector che chuỗi truy vấn, lời lỗi, giá trị trích (#395).
- Sơ đồ kiến trúc ở README, `docs/architecture.md` vẽ lại theo lõi hiện tại, thêm kênh ngoài, Node-RED, DokuWiki (#374).
- Job "Bản online" chạy ngay sau Release đợi tối đa 60 phút cho bản online nâng xong rồi mới kiểm (#344).

### Đã sửa lỗi
- Tài liệu lệch mã: số dịch vụ, số test, màn demo không chạy trên bản online, ROADMAP sau `v1.2.1` (#379).
- Sự kiện `office.document.received` nay được ghi khi văn thư thêm văn bản đến, ứng dụng nghe nó mới nhận được (#381).
- Bản cài có `scripts/demo_tat_van_phong.py`; màn cắm ứng dụng trong bản cài dừng trước khi gỡ ứng dụng (#376).
- Tệp OpenLineage tải từ trang Phả hệ số liệu ghi `producer` là repo Signet, không còn tên repo cũ (#376).
- `moc app install` báo lỗi rõ với tệp form sai kiểu hay lồng quá 32 tầng (cả qua `$ref`), không còn lỗi 500 (#386).
- Smoke không còn trượt bước hỏi đáp ngay sau khi nâng cấp hay trên bản cài tìm theo nghĩa (#360).
- Bật giảm chuyển động thì thông báo, dòng hộp việc, popover hiện ngay, không qua khung trong suốt (#391).
- `moc app install` từ chối form có trường trùng từ khóa của biểu thức BPMN (`le`, `not`, `or`…) (#405).
- Tin realtime có đường dẫn là liên kết có tên với trình đọc màn hình, không còn bị axe báo `link-name` (#407).
- `release.sh` chạy được trên macOS: không có `sha256sum` thì dùng `shasum -a 256`, thiếu cả hai thì dừng sớm (#57).

### Bảo mật
- `MOC_TRUSTED_PROXY=auto`: APISIX chỉ tin mạng `moc`, không tin container ở mạng `apps`; bản cài cũ đổi tay (#211).
- Cảnh báo `deepmerge` chưa có bản vá (GHSA-gcqx-w48m-w2h4) ghi bỏ qua có hạn: gói chỉ chạy lúc dựng (#387).
- Bộ che thông tin cá nhân che cả số di động viết liền sau `ĐT`, `SĐT`, `DĐ`, `Tel`, `Phone` (`ĐT0912…`) (#58).

## [1.2.1] - 2026-10-28

Bản vá đúng bản đang chạy online: giao diện Lịch hạn (hộp việc xếp theo ngày hạn) cho Văn phòng điện tử, trang đăng
nhập, P.A.R.A, Bảng tin, và hướng dẫn sử dụng theo vai trò có ảnh chụp các màn chính. Không thêm tính năng, không đổi
API hay biến cấu hình; nâng tại chỗ từ `v1.2.0`.

### Đã sửa đổi
- Giao diện "Lịch hạn" cho Văn phòng điện tử, trang đăng nhập, P.A.R.A, Bảng tin: hộp việc xếp theo ngày hạn (#291).
- Hướng dẫn sử dụng theo vai trò khớp giao diện Lịch hạn, có ảnh chụp các màn chính (#308).

## [1.2.0] - 2026-10-27

Bản cho vòng trường 01/11. Quy trình thành dịch vụ của lõi: ứng dụng khai BPMN và form JSON Schema trong manifest, có
ứng dụng mẫu Đơn nghỉ phép chỉ dùng lõi; Văn phòng điện tử tách khỏi lõi sau một cờ. Giao diện Liền mạch, kiểm trợ năng
WCAG 2.2 AA và song ngữ; OCR bản scan, hỏi đáp trong một văn bản, thống kê kho lạnh bằng DuckDB. Vận hành: kiểm bản
online qua HTTPS mỗi ngày, kịch bản nâng cấp có lùi bản, bản dev tự theo `develop`; trang tài liệu trên GitHub Pages.

### Đã thêm
- Bản dev theo `develop` tại signet-dev.htechcs.com; job kiểm hằng ngày đòi đúng commit đầu `develop` (#344).
- Quy trình là dịch vụ của lõi: ứng dụng khai BPMN và form JSON Schema trong manifest, gọi API `/api/workflow/<tên>/…`;
  `moc app install` kiểm chặt gói, cài lỗi thì lùi bản trước, gỡ giữ lịch sử đơn (#301, #320, #323, #327, #330–#333).
- Ứng dụng mẫu Đơn nghỉ phép, chỉ có quy trình và form trên lõi: nhân viên gửi, trưởng phòng duyệt (#301, #303, #312).
- Trang Điều hành thống kê văn bản đã nộp lưu trong kho lạnh bằng DuckDB, kiểm băm từng gói (F3.8, #304, #313).
- Hạn gợi ý khi giao việc tránh cả ngày lễ, không chỉ cuối tuần; người vận hành khai thêm ngày nghỉ (F4.3, #280, #281).
- Cảnh báo Prometheus cho cổng API và từng thành phần, kể cả khi không có lưu lượng (F3.13, #255, #257, #274, #275).
- Kiểm HTTPS (F1.9): job kiểm bản online mỗi ngày (chứng chỉ, chuyển hướng, Keycloak sau proxy, header bảo mật); phần CI
  `https` dựng hệ thống sau proxy TLS, F1.9 lên Hoàn thiện (#197, #199, #261, #262, #269, #270).
- Bản scan PDF tìm được theo nội dung: OCR các trang đầu bằng Tesseract cho tìm kiếm và hỏi đáp (#253, #254, #256).
- Hỏi đáp trong một văn bản; nguồn trích mở PDF đúng trang; câu có số ký hiệu ưu tiên từ khóa (F4.2, #151, #152).
- Bản phát hành tự kiểm gói trước khi đăng: chặn bí mật, tài liệu nội bộ, tệp lớn; kiểm giấy phép (#153, #154).
- Trang đăng nhập Keycloak mang thương hiệu Signet; bản cài cũ bật bằng `moc.py realm theme` (#164, #165).
- Trang Danh mục ứng dụng (`/ung-dung`): tên, phiên bản, lúc cài; lãnh đạo, quản trị thấy băm manifest (#166, #167).
- Mốc neo sổ kiểm toán ký Ed25519, công khai bằng `moc audit anchor --publish` cho người ngoài tự kiểm (#56, #158).
- Tự chẩn đoán H-P-D-I thêm hình dạng theo bốn nguyên mẫu của giáo trình DX-OS, cảnh báo "rác vào, rác ra" (#168, #169).
- Cờ chất lượng số liệu (Đạt, Cảnh báo, Trượt) trên trang Điều hành và Phả hệ số liệu (F3.9, F3.11, #170, #177).
- Sơ đồ cảm biến kho (`/cam-bien`): phòng tô màu theo số đo mới nhất, kèm cờ chất lượng dữ liệu OT (F3.10, #181, #183).
- Kịch bản nâng cấp `nang_cap.sh`: nâng, lùi về bản cũ, nâng két, kiểm; CI tập nâng cấp rồi lùi (#182, #185).
- Kiểm song ngữ: e2e giao diện tiếng Anh, test đòi mọi chữ qua bảng dịch; hướng dẫn dịch (F2.9, #200, #201, #267, #268).
- Giao diện Liền mạch cho Văn phòng điện tử và trang đăng nhập: logo, phông tự phục vụ, thanh bên thu thành dải biểu
  tượng, hộp việc tách nhóm "Cần chú ý", chuyển động ngắn tắt được; e2e kiểm phông, ảnh (#116, #196, #214, #215).
- Log tập trung thu thêm Hasura, Keycloak, PostgreSQL, mỗi dịch vụ có luật che thông tin cá nhân (F3.14, #202, #209).
- Hướng dẫn cài khi không kéo được image từ Docker Hub: dùng mirror `mirror.gcr.io` (#219, #221).
- Trang văn bản giữ ngữ cảnh việc: "Về hộp việc" giữ bộ lọc, khung "Yêu cầu được giao", không gửi hai lần (#235, #236).
- e2e quét trợ năng bằng axe (WCAG 2.2 AA) trên các trang chính và Bảng tin (#246, #247, #250, #263, #264, #272).
- Tài liệu mới: trang xem nhanh `docs/README.md` (tự kiểm PoF đủ 24/24), thuật ngữ, hướng dẫn sử dụng theo vai trò,
  trang API REST sinh từ OpenAPI (#307, #308, #309, #319, #340, #341, #343).
- Trang Tài liệu API `/tai-lieu-api/` bằng Swagger UI: API lõi và API Văn phòng điện tử, đăng nhập để gọi thử (#357).
- Giao diện tiếng Anh cho Không gian cá nhân và Bảng tin, chung ngôn ngữ đã chọn với Văn phòng điện tử (#306, #337).
- Trang tài liệu Docusaurus đọc thẳng `docs/`, tìm kiếm tiếng Việt, không gọi CDN, đăng lên GitHub Pages (#308, #342).
- `COPYRIGHT.txt`: bản quyền và bảng phần mềm thượng nguồn, sinh từ `DEPENDENCIES.md` bằng `make copyright` (#347).

### Đã sửa đổi
- Kiểm bản online chạy thêm ngay sau mỗi lần phát hành: bản online chưa nâng lên thẻ mới thì đỏ ngay (#344, #345).
- Tách mã Văn phòng điện tử khỏi lõi: dời mã chung và câu GraphQL riêng của Văn phòng, gắn phần Văn phòng sau một cờ;
  tắt thì lõi vẫn chạy; `make demo-tat-van-phong` kiểm trong CI, không đụng bản cài khác (#302, #315, #318, #328, #329).
- Lịch phiên bản: v1.2.0 cho vòng trường, bản nộp chấm 03/12 đổi thành v1.3.0 (#179, #180, #354).
- Ứng dụng cách ly khỏi mạng lõi: chỉ tới được cổng APISIX, gọi lõi qua cổng như trình duyệt (#207, #208).
- Ảnh giao diện trong README chụp lại theo giao diện Liền mạch; CI lưu ảnh màn hình e2e ở mọi lần chạy (#218, #220).
- Không gian cá nhân theo giao diện Liền mạch; sơ đồ cảm biến, Phả hệ dùng được trên điện thoại (#235, #237, #239).
- Hỏi đáp hội đồng: thêm câu 14–18, sửa câu 1, 4, 5, 12, 13 cho khớp phần đã làm (#311, #324, #325, #335, #338).
- Tài liệu: ClamAV quét sau cổng API, không kho cách ly; chỉ svc-files, svc-workflow đọc bí mật từ két (#338, #339).
- Phông Be Vietnam Pro lấy từ gói npm thay vì lưu trong repo, vẫn tự phục vụ; dịch vụ mới `keycloak-fonts` (#305, #314).

### Đã sửa lỗi
- Reconciler dừng, chạy lại cả profile thêm của bản cài (`MOC_EXTRA_PROFILES`, như `tunnel`) khi áp commit (#351).
- Id việc, phiên quy trình gửi lên được kiểm dạng trước khi ghép vào đường dẫn REST của Flowable (#330, #331).
- Hoàn thành việc không còn báo lỗi khi Flowable gặp khóa lạc quan hay deadlock; tự gọi lại (#189, #190, #316, #317).
- Thanh bên không mở lại che trang sau khi bấm chọn mục; viền focus mục menu không còn bị cắt (#216, #217, #297, #298).
- `moc app install`, `remove`, `sync` khởi động lại APISIX khi route đổi, tránh WAF hỏng lúc nạp lại nóng (#299, #300).
- CI không còn đỏ với PR không đổi tệp nào (#295, #296).
- e2e không còn đỏ chập chờn khi ClamAV nạp lại chữ ký; tài liệu vận hành ghi cách xử lý ở máy thật (#287, #289, #290).
- Tài liệu: bảng mức hoàn thiện ghi đúng số test và việc CI đã chạy, có test bắt số lệch (#258, #259, #285, #286).
- Tài liệu: Prometheus thu cả trạng thái thành phần, log tập trung thu 8 dịch vụ (#240, #282, #283).
- Tài liệu: bằng chứng trỏ đúng job CI, có test kiểm; đánh giá AI có số đo CI, sửa phần scan (#271, #273, #276, #277).
- Báo lỗi đọc được, hai ngôn ngữ, khi vai trò không có quyền hay máy chủ trả lỗi không lý do (#242, #243, #278, #279).
- Log tập trung không còn mất dòng đầu của dịch vụ im lâu khi kết nối tới Vector đã chết (#226, #227).
- Clone repo trên Windows không còn ra CRLF làm hỏng script và test (#244, #245).
- Cổng không còn thỉnh thoảng trả 502 cho `/v1/graphql` khi Hasura đóng kết nối rảnh (#173, #175).
- WAF không còn chặn nhầm bước đổi mã lấy token của PKCE (#162, #163).
- `make install`: cài đủ module cho `demo.py`; không dừng ở bước kiểm image trên máy mới (#174, #176, #186, #187).
- Hỏi đáp: hỏi liên tục không chặn nhúng văn bản mới; nhúng nền không chen lúc mô hình trả lời (#184, #188, #192, #194).
- Cảm biến đồng hồ nhanh: cờ "Giờ đo ở tương lai", không sót mất tín hiệu; sự cố ghi đúng ngày (#191, #193, #195, #198).
- `<html lang>` theo đúng ngôn ngữ sau khi tải lại; chữ nhỏ đạt tương phản WCAG 2.2 AA (#205, #206, #212, #213).
- Tài liệu cho người chấm khớp lại với mã: cài đặt, đóng góp, vận hành, kiến trúc (#233, #234, #238).
- Màn hẹp: tiêu đề, lưới, biểu đồ, khung xử lý việc không còn tràn hay cắt nút trên điện thoại (#230, #241, #251, #252).
- Quản trị đơn vị mở trang văn bản, hồ sơ, sổ đăng ký thì được đưa về sổ kiểm toán thay vì báo lỗi (#230, #241).
- Bảng tin kiểm lại quyền mỗi lần làm mới, báo lỗi quyền bằng câu đọc được thay vì lỗi GraphQL (#230, #241, #248, #249).
- Form đưa tiêu điểm về ô sai đầu tiên, trình đọc màn hình đọc được lỗi; hộp Góp ý vừa màn hình điện thoại (#248, #249).
- `DEPENDENCIES.md` bỏ năm thành phần chưa từng dùng (Kestra, Marquez, openlineage-python, Typer, Gotenberg) (#347).

### Bảo mật
- Trang tài liệu ép serialize-javascript, tinypool, uuid lên bản vá, đóng sáu cảnh báo Dependabot (#349).
- Nuxt của Văn phòng điện tử nâng 4.5.2 → 4.6.2, đóng bốn cảnh báo Dependabot (Signet không dính) (#321, #322).
- Góp ý trong ứng dụng tự che số điện thoại, CCCD, số tài khoản, email trước khi lưu, cả góp ý đã gửi (#265, #266).
- Tải lên kiểm loại tệp theo nội dung, chặn chương trình, kịch bản; ảnh JPEG, PNG được gỡ EXIF, vị trí GPS (#149, #150).

## [1.1.0] - 2026-10-25

Bản cho vòng trường. Lõi Signet có thêm Không gian cá nhân P.A.R.A và cắm ứng dụng mới bằng `moc app install`; cổng có
tường lửa ứng dụng web Coraza + OWASP CRS; Văn phòng điện tử có hồ sơ, phòng đọc, phả hệ biểu đồ báo cáo, tự chẩn đoán
H-P-D-I. Thêm API nạp lô, log tập trung, thông báo email, trang Trạng thái, SBOM; repo đổi tên `HIT-Champion/Signet`.

### Đã thêm
- API nạp lô văn bản đến (NDJSON, CSV, kèm zip tệp đính kèm): mỗi dòng đi đường tiếp nhận lẻ, gửi lại không nhân đôi.
- Tường lửa ứng dụng web ở cổng APISIX: Coraza + OWASP CRS, chặn mặc định, mỗi loại trừ có lý do (F3.15, #130).
- Khai giấy phép theo chuẩn REUSE, `reuse lint` đạt; `make license-check` kiểm cả `.env.example` (PoF #2).
- Thông báo qua email và webhook (Mattermost, Slack, ntfy) ngoài chuông trên web; tắt mặc định, gửi nền có thử lại.
- Chuỗi cung ứng: SBOM CycloneDX kèm mỗi bản phát hành (`make sbom`), kiểm giấy phép mọi gói (`make license-audit`).
- Trang công khai Trạng thái hệ thống `/trang-thai`: từng thành phần, phiên bản, giờ sao lưu gần nhất, trợ lý AI.
- Ứng dụng thứ hai trên lõi, Không gian cá nhân P.A.R.A (`/ca-nhan/`): tệp xếp theo bốn thư mục, chung phiên SSO.
- Nút Góp ý trong Văn phòng điện tử; trang Số đo "sau" theo đặc tả §8 cho lãnh đạo đơn vị (F4.6).
- Log tập trung Vector + Parseable (profile `logs`, tắt mặc định), che bí mật và thông tin cá nhân (F3.14).
- `moc app install` cắm ứng dụng vào lõi từ manifest, không sửa tệp lõi; ví dụ Bảng tin đơn vị (#132, #137).
- Trang Tự chẩn đoán mức trưởng thành H-P-D-I cho lãnh đạo: radar, bằng chứng của đơn vị, bước nên làm (F4.7, #121).
- Trang Hồ sơ công việc: lãnh đạo phòng nộp lưu theo yêu cầu; phòng đọc xem PDF có dấu tên người xem (F3.8, #124).
- Phả hệ số liệu: biểu đồ → khung nhìn → bảng, nút "Nguồn số liệu" trên biểu đồ, tải OpenLineage (F3.9, F3.11, #126).
- Tài liệu: cấu trúc thư mục trong README, đánh giá AI, hồ sơ chất vấn, dự phòng demo, mức hoàn thiện, `SECURITY.md`.

### Đã sửa đổi
- README (cả tiếng Anh) viết lại thành 12 mục, cài đặt lên giữa trang, sơ đồ kiến trúc động thay sơ đồ ASCII (#108).
- Repo đổi tên `HIT-Champion/HVL` → `HIT-Champion/Signet`; GitHub vẫn chuyển hướng đường dẫn cũ (#112).
- CI: chạy thử toàn hệ thống chia năm phần song song, PR chỉ đổi tài liệu không dựng hệ thống, `docs/api/` lệch thì
  tải lên bản sinh lại (#110).
- Trang Release ngắn lại: chỉ gói chính thức kèm lệnh kiểm `.sha256`, đoạn tóm tắt phiên bản, ghi chép gập lại.
- Lịch phát hành: `v1.1.0` trước vòng trường 01/11, bản nộp chấm là `v1.2.0` (03/12) (#144).
- Gói phát hành đổi tên `signet-X.Y.Z.tar.gz` (cả SBOM, `.sha256`); tên mã `moc` và gói của bản cũ giữ nguyên (#144).
- Cấu hình phần mềm nguồn mở dùng nguyên bản gom vào `platform/`; `make install` dọn tệp của bố cục cũ.
- Tài liệu: phần dự thi chuyển vào `docs/du-thi/`; `ROADMAP.md`, `docs/architecture.md` viết lại theo hiện trạng (#128).

### Đã sửa lỗi
- Cổng thỉnh thoảng trả 502 khi gọi `svc-files`: nay `svc-files` giữ kết nối rảnh lâu hơn cổng (#139).
- Tên job CI có `#` (`Giấy phép (PoF #2)`…) bị YAML cắt mất nên ruleset chặn mọi PR; tên nay đặt trong ngoặc kép.
- Nhắc hạn: dòng nhắc vào dòng thời gian văn bản trước khi gửi thông báo (F2.3).
- Văn bản hạn chế quá nặng để đóng dấu không còn bị báo nhầm "không đọc được PDF" thay vì "PDF quá nặng".
- Nâng brotli, brotlicffi trong `svc-files`: vá lỗi ghi tràn bộ nhớ khi giải nén (PYSEC-2026-4322, PYSEC-2026-4323).
- Lỗi SonarQube: không đăng nhập SMTP qua kết nối không mã hóa; ô tìm kiếm, ô chọn có tên cho trình đọc màn hình.
- WAF: giao diện báo rõ khi cổng chặn, kèm mã yêu cầu; đăng nhập không còn bị chặn nhầm (F3.15, #134, #141).
- Tài liệu: sửa chỗ ghi lệch với mã về sự kiện, log, CI; `DEPENDENCIES.md` bỏ PDF.js, thêm gói ngoại lệ (#119, #122).

### Bảo mật
- Gỡ pip khỏi image `svc-files`, `svc-workflow`: pip của image nền mang bản cũ có lỗ hổng của certifi, urllib3, msgpack…
- Nâng pypdf 6.21.2 trong `svc-files` (ba GHSA: PDF dị dạng làm đọc chữ rất lâu); nâng serialize-javascript,
  fast-uri.

## [1.0.0] - 2026-10-23

Bản cho vòng trường. Văn phòng điện tử chạy đủ luồng văn bản đến và đi theo NĐ 30/2020 trên lõi dùng chung (Keycloak,
APISIX, Hasura, Flowable): liên thông, sổ kiểm toán chuỗi băm, cổng xác thực, văn bản hạn chế mã hóa, ký số minh họa;
tác tử AI đọc văn bản, hỏi đáp, gợi ý giao việc; sao lưu một lệnh, GitOps, két bí mật; CI dựng toàn hệ thống mọi PR.

### Đã thêm
- Cloudflare Tunnel tùy chọn (profile `tunnel`): máy không có IP công khai ra Internet có HTTPS, không mở cổng (F1.9).
- Giới hạn tốc độ ở cổng APISIX: đăng nhập theo IP, API theo phiên; giao diện báo "thao tác quá nhanh" (F1.2).
- CI chạy kiểm thử thật trên mọi PR: dựng toàn hệ thống rồi seed → smoke → e2e; quét bí mật, lỗ hổng phụ thuộc.
- `make install PREFIX=…`, `make uninstall`: cài ra ngoài thư mục mã nguồn, cài lại là nâng cấp và giữ `.env` (F1.8).
- Tài liệu API `docs/api/` (GraphQL theo vai trò, REST, OpenAPI): `make api-docs` xuất, CI báo khi lệch (F1.10, #24).
- Văn bản đi: soạn dự thảo, xem trước PDF theo NĐ 30/2020, duyệt, ký, trả lại, cấp số, phát hành PDF mã QR (F2.4, #29).
- Cổng xác thực công khai `/xac-thuc`: mở từ mã QR, thả PDF để trình duyệt tự tính SHA-256 và báo khớp (F2.13, #30).
- Thông báo realtime cho người làm bước kế tiếp: chuông thông báo, hộp việc và trang văn bản tự tải lại (F2.5, #31).
- Nhắc hạn trong quy trình BPMN: quá một hạn thì nhắc người phải làm, quá hai hạn thì báo lãnh đạo (F2.3, #32).
- Sổ kiểm toán chuỗi băm neo ra kho khóa ghi; `make audit` chỉ ra dòng bị sửa; màn "Sổ kiểm toán" (F2.12, #33).
- SeaweedFS nằm riêng mạng, chỉ `svc-files` tới được; tắt gửi thống kê ẩn danh ra ngoài (#33).
- Poka-yoke ba lớp cho tiếp nhận văn bản đến (form, svc-workflow, PostgreSQL) theo một JSON Schema chung (F2.2, #34).
- Sổ đăng ký văn bản đến / đi theo năm (`/so-dang-ky`), in PDF theo NĐ 30/2020, lần in vào sổ kiểm toán (F2.8, #35).
- Tìm theo nội dung văn bản đi và chữ trong tệp PDF đính kèm; văn bản hạn chế không vào chỉ mục nội dung (F2.7, #36).
- Tìm kiếm: mọi từ phải khớp. **Đổi API:** `GET /api/search` phân trang bằng `cursor` thay cho `offset` (#36).
- Màn demo `make demo-kiem-dich`: tệp EICAR bị ClamAV chặn, lần chặn vào sổ; giao diện hiện mẫu mã độc (F3.1, #37).
- Trang **Điều hành** cho lãnh đạo đơn vị: văn bản chưa xong, quá hạn, thời gian xử lý, biểu đồ ECharts (F3.11, #38).
- `make backup`, `make restore`: sao lưu mã hóa mọi CSDL và tệp, khôi phục một lệnh; CI diễn tập mỗi PR (F3.4, #39).
- Két bí mật OpenBao: dịch vụ lấy bí mật qua AppRole riêng thay cho biến môi trường; `make demo-ket-bi-mat` (F3.2, #40).
- GitOps và tự phục hồi `make reconcile`: dựng lại dịch vụ mất hay dừng, áp commit mới của nhánh `deploy` (F3.3, #41).
- Lập hồ sơ và nộp lưu nóng → lạnh: gói Parquet, tệp gốc khóa ghi theo hạn bảo quản; phòng đọc kiểm băm (F3.8, #42).
- Phả hệ dữ liệu OpenLineage cho mỗi lượt nộp lưu, kiểm chất lượng dữ liệu trước khi ghi sang kho lạnh (F3.9, #43).
- Tab "Lịch sử" trên trang văn bản: ai, lúc nào, trường nào đổi từ gì sang gì, đọc từ sổ kiểm toán (F3.5, #44).
- Giám sát cổng API bằng Prometheus và Grafana (chỉ xem, chỉ máy cục bộ), bảng điều khiển nạp sẵn (F3.13, #45).
- Hội tụ IT/OT (profile `iot`, NGSI-LD): cảm biến vượt ngưỡng tự dựng dự thảo "Báo cáo sự cố" khẩn (F3.10, #46).
- Văn bản hạn chế truy cập: tệp mã hóa bằng khóa riêng từ két, đóng dấu tên người xem khi mở, danh sách người được xem;
  không dùng cho bí mật nhà nước (F3.7, #47).
- Liên thông văn bản giữa các đơn vị cùng dùng hệ thống: bên nhận có văn bản đến kèm bản PDF đã kiểm băm (F3.12).
- `moc tenant create | list | check`: thêm đơn vị kèm Keycloak Organization và tài khoản quản trị bằng một lệnh (F3.12).
- Tác tử đọc văn bản đến: PDF hoặc ảnh chụp (OCR) được điền sẵn các trường dạng gợi ý, không tự tạo văn bản (F4.1).
- Profile `ai` tùy chọn (Ollama, Qwen3 tại chỗ): viết trích yếu khi quy tắc chưa chắc, viết câu trả lời, tìm theo nghĩa.
- Trợ lý hỏi đáp `/hoi-dap`: câu trích nguyên văn kèm nguồn, chỉ từ văn bản người hỏi được xem (F4.2).
- Tác tử gợi ý giao việc: đơn vị chủ trì, độ tin cậy, hạn theo văn bản tương tự đã giao; lỗi không chặn văn bản (F4.3).
- Khối "Gợi ý giao việc" ở form chỉ đạo: "Dùng gợi ý" chỉ điền form, lãnh đạo tự quyết và tự bấm giao (F4.3).
- Tác tử có danh tính riêng: mỗi lần đọc văn bản, trả lời, gợi ý giao việc ghi một dòng sổ kiểm toán chỉ siêu dữ liệu.
- Kho văn bản mẫu hư cấu, màn demo và lệnh đo cho từng tác tử: `make do-doc-van-ban`, `do-hoi-dap`, `do-giao-viec`.
- Ký số văn bản đi PAdES (**chỉ minh họa**): khóa từng đơn vị nằm trong két, CA nội bộ; văn bản hạn chế không ký (F4.5).
- Cổng xác thực hiện khối "Chữ ký số (minh họa)"; `signing verify`, `make demo-ky-so` phát hiện tệp sửa sau ký (F4.5).
- Che thông tin cá nhân: bộ nhận dạng tự viết (CCCD, số điện thoại, email…); mô hình chỉ nhận bản đã che (F4.4).
- Nhật ký dịch vụ che thông tin cá nhân; nhật ký truy cập bỏ chuỗi truy vấn và Referer; `make demo-che-pii` (F4.4).
- Dữ liệu mẫu và kiểm thử: `make seed` thêm văn bản đi mẫu, việc chờ xử lý cho `giamkhao`; `make smoke`, `make e2e`
  thêm kịch bản cho từng tính năng (#34, #35, #36).
- Tài liệu: README tiếng Anh (F2.11); triển khai sau proxy TLS `docs/trien-khai.md` (F1.9); `docs/demo-script.md`.

### Đã sửa đổi
- Quy trình Git chuyển sang Git Flow: `develop` là nhánh mặc định, `main` chỉ nhận PR phát hành; workflow kiểm PR.
- Đổi tên hiển thị Mộc → **Signet** (giao diện, Keycloak, API, CLI, PDF, tài liệu); tên mã `moc` giữ nguyên. Bản cài
  cũ đổi tay Display name của realm Keycloak.
- Tài liệu: README viết lại gọn; các mục vận hành chuyển sang `docs/van-hanh.md`.
- Văn thư tiếp nhận văn bản đến chỉ qua Action `receiveIncoming`, không ghi thẳng bảng; dữ liệu cũ được dọn (#34).
- Hoàn thành việc: Hasura, APISIX chờ lâu hơn cho phát hành trên máy chậm; "Báo cáo xong" không còn chờ vòng với tác tử.
- `make seed` tạo Organization cho hai đơn vị mẫu như `moc tenant create`; bản đã dựng không cần `make reset`.
- Profile `ai`: `make ai-model` kéo thêm mô hình nhúng; `make down`, `make reset` dừng cả `ai`, `ai-pull` (F4.1, F4.2).
- Tìm theo nội dung đọc thêm bản phát hành văn bản đi; ngay sau nâng cấp có thể thiếu kết quả vài phút (F2.7, F4.2).
- Trợ lý hỏi đáp xếp chung mọi đoạn theo trọng số câu hỏi: văn bản trả lời đúng không còn đứng sau nguồn lạc đề (F4.2).

### Đã sửa lỗi
- Chữ đại diện ở đầu trang lấy chữ đầu của tên và viết hoa ("Tài khoản Giám khảo" ra "G", trước là "k").
- Kịch bản dòng lệnh chạy được sau Cloudflare Tunnel; thử mã TOTP kế tiếp khi mã vừa bị dùng ở nơi khác.
- Trang văn bản, hộp việc: thông báo đến đúng lúc bấm thao tác không còn để lượt tải cũ đè lượt mới.
- Bấm đúp hay gọi chen nhau không còn ghi hai lần khi hoàn thành việc, hay khởi chạy hai quy trình cho một văn bản.
- Quản trị đơn vị mở app vào Sổ kiểm toán thay vì gặp lỗi; trang văn bản tải lỗi thì hiện lỗi kèm nút thử lại.
- Ngày giờ trên giao diện luôn theo giờ Việt Nam; ngày ban hành, hạn không còn lệch một ngày ở múi giờ âm.
- Danh sách văn bản đến, đi không còn ẩn văn bản cũ: tải dần bằng nút "Xem thêm", không lặp, không sót dòng.
- Soạn văn bản đi: lưu dự thảo đã trình không còn báo "Đã lưu"; mở trang soạn mới không còn chép dự thảo đang sửa.
- Hết phiên đăng nhập giữa lúc soạn hay tiếp nhận văn bản: phần đang nhập được giữ và khôi phục, trừ văn bản hạn chế.
- Văn bản hạn chế: người được giao việc tự vào danh sách được xem; người không đọc được không hoàn thành việc mù (#47).
- svc-workflow gọi svc-files không còn lỗi "token không hợp lệ" sau khi máy chủ ngủ hay VM bị tạm dừng.
- Đặt sau proxy TLS không đăng nhập được, mọi người chung một bộ đếm giới hạn tốc độ: nay khai báo được proxy tin cậy.
- Trình lại văn bản đi: việc ký giao đúng người ký mới chọn; trình lại khi trả lại chưa xong bị từ chối thay vì kẹt.
- Nộp lưu hồ sơ không còn làm tụt số liệu trang Điều hành và số đo đọc văn bản đến (F3.8, F3.11, F4.1).
- Ghi chú Release lấy từ CHANGELOG không còn kéo theo chú thích HTML; thiếu mục phiên bản thì không gắn thẻ.
- Kiểm thử, tài liệu: `make demo-che-pii`, `make demo-hoi-dap` đợi đủ chỉ mục; sửa e2e thông báo; README ghi đủ vai trò
  bắt buộc TOTP.

### Bảo mật
- Ghim image bên thứ ba theo digest, Action GitHub theo SHA commit: thẻ bị đẩy lại không đổi được bản kéo về.
- GitOps chỉ áp commit có chữ ký SSH của người được phép khi bật danh sách người ký; chưa ký hay khóa lạ thì giữ bản cũ.
- Phát hành: `release.sh`, workflow Release dừng khi thẻ hay Release đã có, kiểm dạng tên thẻ; workflow CI chỉ đọc kho.
- Khóa ký số từng đơn vị không ra khỏi két; két khởi tạo trước F4.5 phải nâng cấp tay mới ký số được (F4.5).
- Che thông tin cá nhân: sổ kiểm toán cố ý giữ bản gốc; chưa che họ tên, địa chỉ, nhật ký Hasura, Keycloak… (F4.4).
- Văn bản hạn chế không bao giờ được tác tử đọc, gợi ý giao việc hay làm căn cứ; CSDL chặn thêm (F3.7, F4.1, F4.3).
- Trợ lý chỉ dựa trên văn bản người hỏi được xem: lọc trong chỉ mục, hậu kiểm bằng token người hỏi (F4.2).
- Xác thực hai bước TOTP bắt buộc với văn thư, lãnh đạo, quản trị đơn vị; `make seed` cài sẵn, `make totp` in mã (F1.1).
- Lấy token bằng mật khẩu (`moc-cli`, `admin-cli`) cũng phải gửi mã TOTP; bản đã dựng cần `make reset` hoặc đặt tay.
- Tệp có mật khẩu hay vượt giới hạn quét (bom nén, lồng quá sâu) bị chặn thay vì coi là sạch, có dòng sổ kiểm toán.
- Văn bản hạn chế: thông báo không mang số ký hiệu, trích yếu; sổ kiểm toán không lộ giá trị, danh sách được xem (#47).
- Nâng Pillow 13.0.0, pypdf 6.21.1 (vá lỗ hổng khi đọc tệp tải lên) và certifi 2026.10.19 (bỏ gốc emSign).
- Giới hạn đăng nhập theo IP không còn né được bằng cách viết khác đường; cổng gỡ thêm tên cũ của khóa quản trị Hasura.
- Kiểm, đóng dấu PDF văn bản hạn chế trong tiến trình con có trần tài nguyên: tệp độc không làm treo dịch vụ (F3.7).
- `make env` tạo `.env` chỉ chủ sở hữu đọc được; `make up`, `make install`, `make check` từ chối khi còn `change_me`.

## [0.1.0] - 2026-10-18

Bộ khung dự án: giấy phép Apache-2.0, dựng từ mã nguồn bằng Make và Docker Compose, cấu hình qua `.env`, CI kiểm
header giấy phép, gói phát hành `.tar.gz`, mẫu báo lỗi và PR, tài liệu.

### Đã thêm
- Khung dự án nguồn mở Apache-2.0: dựng bằng `Makefile` và Docker Compose (profile `core`, `app`), cấu hình qua `.env`.
- CI kiểm header giấy phép và Compose; phát hành sinh gói `.tar.gz` theo thẻ; mẫu báo lỗi, đề xuất tính năng, PR.
- Tài liệu dự án: README, CONTRIBUTING, CODE_OF_CONDUCT, ROADMAP, tóm tắt đề OLP 2026, bảng tự chấm PoF.
- `DEPENDENCIES.md`: phần mềm thượng nguồn kèm phiên bản ghim, giấy phép, các thành phần đã loại vì không OSI.
- Phân tích đề thi chính thức OLP PMNM 2026, kế hoạch phát triển theo phase, quy trình Git, bản nháp mô hình dữ liệu.
- Đặc tả sản phẩm: Văn phòng điện tử quản lý văn bản đến / đi theo Nghị định 30/2020/NĐ-CP, xác thực văn bản bằng QR.
- Lõi Tầng 1 chạy bằng `make up`: Keycloak, APISIX là cổng duy nhất kiểm JWT ở biên, PostgreSQL + Hasura, Flowable,
  SeaweedFS, ClamAV, Meilisearch (#13, #14, #21).
- Schema `core` + `office`, quyền theo vai trò, sổ kiểm toán chuỗi băm, vào sổ đến cấp số liên tiếp (#18).
- `svc-files`: tải lên qua ClamAV vào SeaweedFS, tải xuống theo quyền, tìm kiếm Meilisearch gõ không dấu (#19, #20).
- `svc-workflow`: Hasura Actions nối Flowable, quy trình BPMN văn bản đến, đồng bộ danh bạ Keycloak (#15, #23).
- Giao diện Văn phòng điện tử (Nuxt 4): đăng nhập SSO, hộp việc, tiếp nhận, xử lý văn bản đến, tìm kiếm, song ngữ (#22).
- `make env`, `make seed`, `make smoke` (kiểm tra qua cổng), `make e2e` (Playwright trên trình duyệt thật) (#16).
- Tài liệu nghiên cứu trước đề thi: chiến lược dự thi, đặc tả DX-Safety, dự báo đề thi, kế hoạch vòng trường.

### Đã sửa đổi
- Đổi bài toán nghiệp vụ từ luồng phê duyệt đề xuất sang quản lý văn bản đến / đi.
- Sổ kiểm toán chuỗi băm và cổng xác thực văn bản lên Must (Phase 2): F3.5 → F2.12, F3.6 → F2.13.
- Kế hoạch: dời `v0.1.0` sang 25/10, Phase 2–4 lùi theo, giữ ngày nộp; §4 thành danh mục tài nguyên cần có.
- Đổi tên sản phẩm DX-Lab → **Mộc**; tên kỹ thuật đổi theo (biến `DXLAB_*` → `MOC_*`, gói `moc-<phiên bản>.tar.gz`).
- Tài liệu: rà soát tóm tắt OLP 2026, README nêu bài toán, quy ước nhánh và commit, phát biểu lõi trước, ứng dụng sau.

### Đã sửa lỗi
- Kiểm header giấy phép không còn bỏ qua tệp `.vue`, `.bpmn`, `.css`…; loại tệp chưa hỗ trợ được báo cảnh báo.

<!--
Mẫu cho bản phát hành kế tiếp:

## [x.y.z] - YYYY-MM-DD

### Đã thêm
### Đã sửa đổi
### Đã loại bỏ
### Đã sửa lỗi
### Bảo mật
-->
