# Thuật ngữ

Các từ dùng trong tài liệu và giao diện Signet. Mỗi từ được giải thích trong một, hai dòng, kèm tài liệu gốc để đọc
kỹ hơn. Thuật ngữ văn thư theo Nghị định 30/2020/NĐ-CP về công tác văn thư (gọi tắt NĐ 30). Mã như F2.3 là mã tính
năng trong [`muc-hoan-thien.md`](muc-hoan-thien.md), nơi ghi mức hoàn thiện và bằng chứng của từng tính năng.

## 1. Sản phẩm và kiến trúc

| Thuật ngữ | Nghĩa | Xem thêm |
|---|---|---|
| Signet, `moc` | Signet là tên sản phẩm, trước đây tên Mộc. Tên mã kỹ thuật `moc` còn trong biến `MOC_*`, realm Keycloak `moc`, lệnh `scripts/moc.py`, image `moc/*` | [`README.md`](../README.md), [`hoi-dap-hoi-dong.md`](du-thi/hoi-dap-hoi-dong.md) câu 18 |
| DX-OS Open-Core | Chủ đề của OLP 2026: một lõi nền tảng nguồn mở dùng chung, các ứng dụng cắm lên trên. Lõi điều phối phần mềm nguồn mở có sẵn, không viết lại | [`olp-2026-brief.md`](du-thi/olp-2026-brief.md), [`architecture.md`](architecture.md) §1.1 |
| Lõi, Tầng 1 | Phần chạy ngầm, không có giao diện: định danh, cổng API, dữ liệu, quy trình và lớp tin cậy. Là profile `core` của `docker-compose.yml` | [`architecture.md`](architecture.md) §4 |
| Ứng dụng, Tầng 2 | Phần người dùng thao tác, gọi lõi qua cổng APISIX bằng token Keycloak. Văn phòng điện tử và Không gian cá nhân nằm ở profile `app`; Bảng tin cắm bằng `moc app install` | [`architecture.md`](architecture.md) §4, [`them-ung-dung.md`](them-ung-dung.md) |
| H-P-D-I | Bốn không gian của đề: [H] con người (nhân sự), [P] quy trình, [D] dữ liệu, [I] trí tuệ. Làm theo đúng thứ tự này vì không gian sau dựa vào không gian trước | [`architecture.md`](architecture.md) §1.2 |
| Bốn con dấu tin cậy | Biết ai đã làm, Sạch, Không sửa lén được, Kiểm chứng được từ bên ngoài. Ứng dụng nào cắm vào lõi cũng có sẵn bốn thứ này | [`README.md`](../README.md), mục Giới thiệu |
| Cụm ①–⑦ | Bảy cụm dịch vụ Tầng 1 của đề: ① định danh, bảo mật · ② đa thuê ước, biên mạng · ③ dữ liệu có cấu trúc · ④ dữ liệu phi cấu trúc · ⑤ quy trình, tự động hóa · ⑥ vận hành, giám sát, kiểm toán · ⑦ truyền thông, giao vận | [`muc-hoan-thien.md`](muc-hoan-thien.md) §3 |
| Nguyên lý (i)–(iv) | Bốn nguyên lý thiết kế, mỗi nguyên lý một màn demo: (i) vòng đời và tốc độ dữ liệu, (ii) hội tụ IT/OT, (iii) quản trị dữ liệu, (iv) Zero-Trust và GitOps | [`demo-script.md`](demo-script.md) |
| Đơn vị (thuê ước) | Một khoa, phòng hay trường thành viên trên cùng bản cài. Mọi bảng nghiệp vụ có `tenant_id`, mỗi người chỉ thấy dữ liệu của đơn vị mình. Thêm bằng `moc tenant create` | [`van-hanh.md`](van-hanh.md), mục Thêm đơn vị; [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §0 |
| Phòng | Phòng, tổ hay bộ môn trong một đơn vị (`office.departments`). Phòng của người dùng đi trong token (`department_id`) | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §2.1 |
| Cổng, APISIX | Lối vào duy nhất từ bên ngoài: kiểm JWT, giới hạn tốc độ, tường lửa ứng dụng web. Container ứng dụng cũng gọi lõi qua đây | [`architecture.md`](architecture.md) §2, [`platform/apisix/README.md`](../platform/apisix/README.md) |
| Profile | Nhóm dịch vụ trong `docker-compose.yml`: `core` (Tầng 1), `app` (Tầng 2), các phần tùy chọn `ai`, `iot`, `logs`, `mail`, `tunnel` | [`architecture.md`](architecture.md) §1.2 |
| Hasura Action | Thao tác nghiệp vụ gửi qua GraphQL (tiếp nhận, vào sổ, trình dự thảo, hoàn thành một bước của luồng…), do `svc-workflow` xử lý. Chỉ `svc-workflow` được đổi cột `status` | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §0, §4.1 |
| Manifest ứng dụng | Tệp `app.yaml` khai mọi thứ ứng dụng cần từ lõi: client Keycloak, route, container, schema, migration, quyền, sự kiện, quy trình | [`them-ung-dung.md`](them-ung-dung.md) §1.1 |
| `moc app install`, `moc app remove` | Cắm ứng dụng bằng một lệnh từ manifest, không sửa tệp nào của lõi; chạy lại không tạo gì trùng. Gỡ thì giữ dữ liệu | [`them-ung-dung.md`](them-ung-dung.md) §1 |
| Sự kiện của lõi | Lõi báo cho ứng dụng khi văn bản không hạn chế được tiếp nhận, vào sổ hay phát hành (`core.app_events`), qua Hasura Event Trigger. Sự kiện chỉ có 5 cột, không có nội dung văn bản | [`them-ung-dung.md`](them-ung-dung.md) §1.3 |
| Quy trình của ứng dụng | Mục `workflow` trong manifest: tệp BPMN và form JSON Schema. Quy trình chạy trên Flowable của lõi, gọi qua API `/api/workflow/<ứng dụng>/…` | [`them-ung-dung.md`](them-ung-dung.md) §1.10 |
| `MOC_OFFICE_ENABLED` | Đặt `false` thì `svc-files`, `svc-workflow` chỉ chạy phần lõi, không gắn route, Action hay vòng nền nào của Văn phòng điện tử | [`architecture.md`](architecture.md) §4.7 |

## 2. Văn bản và nghiệp vụ văn thư

| Thuật ngữ | Nghĩa | Xem thêm |
|---|---|---|
| Văn bản đến, văn bản đi | Văn bản đến nhận từ cơ quan khác; văn bản đi do đơn vị soạn và phát hành (`direction` là `in` hay `out`) | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §2.2 |
| Tiếp nhận | Văn thư nhập văn bản đến vào hệ thống. Form kiểm theo `schemas/van-ban-den.json`; tác tử đọc văn bản có thể gợi ý sẵn các ô (F2.2, F4.1) | [`muc-hoan-thien.md`](muc-hoan-thien.md) F2.2 |
| Vào sổ | Đăng ký văn bản đến vào sổ và nhận số đến. Cùng cơ quan ban hành, số ký hiệu và ngày ban hành thì không vào sổ lần hai | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §2.2 |
| Sổ đăng ký | Mỗi đơn vị, mỗi năm có một sổ văn bản đến và một sổ văn bản đi (`office.registers`). In ra PDF đúng các cột của Phụ lục IV NĐ 30 (F2.8) | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §2.1 |
| Cấp số, số đến | Số liên tiếp từ 01 trong năm, không trùng (NĐ 30, Điều 15 và 22). Số cấp trong cùng giao dịch với việc ghi văn bản nên hai văn thư bấm cùng lúc không nhận trùng số | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §2.1 |
| Số ký hiệu | Số và ký hiệu in trên văn bản, ví dụ `123/ĐHCN-ĐT` | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §2.2 |
| Tên loại | Công văn, Quyết định, Thông báo, Kế hoạch…, mỗi loại một mã (`CV`, `QĐ`, `TB`, `KH`…) | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §2.1 |
| Trích yếu | Câu tóm tắt nội dung văn bản, từ 10 đến 500 ký tự | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §2.2 |
| Mức độ khẩn | Thường, Khẩn, Thượng khẩn, Hỏa tốc. Văn bản khẩn lên đầu hộp việc | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §2.2 |
| Chỉ đạo, giao việc | Lãnh đạo ghi ý kiến chỉ đạo và giao văn bản cho phòng hay người: chủ trì, phối hợp hoặc để biết (NĐ 30, Điều 23; F2.3) | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §2.3 |
| Hạn giải quyết | Hạn của văn bản đến và của từng việc được giao. Ngoài ra mỗi bước trong luồng có thời hạn xử lý (`MOC_SLA_DURATION`, mặc định 24 giờ): quá một lần thì nhắc người làm, quá hai lần thì báo thêm lãnh đạo của họ (F2.3) | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §2.3, §4.2 |
| Hộp việc | Danh sách việc đang chờ từng người; thông báo tới ngay khi có việc mới (F2.5) | [`muc-hoan-thien.md`](muc-hoan-thien.md) F2.5 |
| Dòng thời gian | Các bước của một văn bản hiện cho người dùng xem (`office.document_events`, F2.6). Khác sổ kiểm toán, nơi ghi mọi thay đổi để kiểm | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §2.3 |
| Dự thảo, trình, duyệt | Vòng của văn bản đi trước khi phát hành: soạn dự thảo, trình lãnh đạo, bị trả lại thì sửa, rồi được duyệt (F2.4) | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §2.2 |
| Phát hành | Văn thư cấp số văn bản đi đã duyệt; hệ thống dựng bản PDF có mã QR và mã xác thực, ghi lại SHA-256 của tệp để đối chiếu sau này (F2.4) | [`muc-hoan-thien.md`](muc-hoan-thien.md) F2.4 |
| Mã xác thực | Mã 10 ký tự (A–Z, 2–7) của mỗi văn bản phát hành, in cạnh mã QR | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §2.2 |
| Cổng xác thực | Trang công khai `/xac-thuc`, không cần đăng nhập: tra mã, quét QR, hoặc thả tệp PDF để trình duyệt tự tính SHA-256 và so (F2.13) | [`muc-hoan-thien.md`](muc-hoan-thien.md) F2.13 |
| Văn bản hạn chế | Văn bản chỉ người có tên mới mở được: mỗi tệp một khóa AES-256 bọc trong két, chỉ giải mã trong bộ nhớ, bản xem đóng tên người xem (F3.7; trong mã là `sealed`). Không phải văn bản mật: Signet không quản lý bí mật nhà nước | [`muc-hoan-thien.md`](muc-hoan-thien.md) F3.7, [`dac-ta-san-pham.md`](dac-ta-san-pham.md) §2.1 |
| Liên thông | Gửi văn bản đi tới đơn vị khác trên cùng bản cài. Bên nhận có ngay văn bản đến, tệp trùng từng byte, kèm mã xác thực (F3.12) | [`muc-hoan-thien.md`](muc-hoan-thien.md) F3.12 |
| Nạp lô | Văn thư gửi một tệp NDJSON hoặc CSV gồm nhiều văn bản đến, kèm tệp zip đính kèm nếu có. Mỗi dòng qua ClamAV và Action `receiveIncoming` như khi nhập tay | [`api/README.md`](api/README.md) |
| Hồ sơ | Hồ sơ công việc gom các văn bản của một việc (`office.case_files`): đang mở, đã đóng rồi đã nộp lưu; có thời hạn bảo quản tính bằng năm hoặc vĩnh viễn | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §2.4 |
| Nộp lưu | Vòng nền của `svc-files` chuyển hồ sơ đã đóng đủ `MOC_ARCHIVE_AFTER_DAYS` ngày (mặc định 365) sang kho lạnh thành gói lưu trữ (F3.8) | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §2.4 |
| Gói lưu trữ | Bảng Parquet (văn bản, giao việc, sự kiện), tệp gốc và manifest có băm của một hồ sơ, ghi trên kho lạnh với khóa ghi theo thời hạn bảo quản | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §2.4 |
| Phòng đọc | Nơi xem lại hồ sơ đã nộp lưu: đọc gói từ kho lạnh, so băm, chỉ mở tệp PDF | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §4.3 |

## 3. Vai trò

| Vai trò | Mã | Việc chính | Xem thêm |
|---|---|---|---|
| Văn thư | `clerk` | Tiếp nhận, vào sổ văn bản đến; cấp số, phát hành văn bản đi | [`README.md`](../README.md), mục Chạy thử |
| Chuyên viên | `staff` | Xử lý văn bản được giao; soạn, trình văn bản đi | [`dac-ta-san-pham.md`](dac-ta-san-pham.md) §3 |
| Lãnh đạo phòng | `manager` | Tổ trưởng, trưởng bộ môn: phân công trong phòng, duyệt dự thảo của phòng | [`dac-ta-san-pham.md`](dac-ta-san-pham.md) §3 |
| Lãnh đạo đơn vị | `director` | Ghi ý kiến chỉ đạo, giao chủ trì, phối hợp; duyệt và ký văn bản đi; xem dashboard điều hành | [`dac-ta-san-pham.md`](dac-ta-san-pham.md) §3 |
| Quản trị đơn vị | `tenant_admin` | Xem sổ kiểm toán của đơn vị, không đọc nội dung văn bản | [`README.md`](../README.md), mục Chạy thử |
| Tác tử | vai trò Hasura `agent` | Tài khoản dịch vụ có danh tính riêng, chỉ gợi ý, người quyết; việc của nó vào sổ kiểm toán | [`architecture.md`](architecture.md) §1.2 |

Văn thư, lãnh đạo phòng, lãnh đạo đơn vị và quản trị đơn vị bắt buộc xác thực hai bước (TOTP). Truy vấn và thao tác
ghi của từng vai trò: [`api/thao-tac-theo-vai-tro.md`](api/thao-tac-theo-vai-tro.md).

## 4. Tin cậy, bảo mật và vận hành

| Thuật ngữ | Nghĩa | Xem thêm |
|---|---|---|
| Poka-yoke | Chặn nhập sai ở ba lớp: form, máy chủ và ràng buộc CSDL, cả ba theo một JSON Schema dùng chung trong `schemas/` | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §0, [`schemas/README.md`](../schemas/README.md) |
| Sổ kiểm toán | `core.audit_log`: mỗi thay đổi một dòng, các dòng nối thành chuỗi băm SHA-256. `make audit` tính lại cả chuỗi và chỉ ra dòng bị sửa (F2.12) | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §1 |
| Mốc neo | Đầu chuỗi sổ kiểm toán, ghi vào kho lạnh khóa ghi mỗi 10 phút. Mốc neo công khai chép thêm ra một kho git công khai, có chữ ký Ed25519 của két | [`van-hanh.md`](van-hanh.md), mục Mốc neo công khai |
| Kiểm dịch | `svc-files` quét mọi tệp bằng ClamAV trước khi ghi vào kho. Tệp nhiễm bị từ chối, không lưu ở đâu, và lần chặn vào sổ kiểm toán; không có kho cách ly (F1.6, F3.1) | [`van-hanh.md`](van-hanh.md), mục Quét mã độc |
| WAF | Tường lửa ứng dụng web Coraza với bộ luật OWASP CRS, chạy trong APISIX (F3.15) | [`platform/apisix/README.md`](../platform/apisix/README.md), mục WAF |
| Két bí mật | OpenBao. `svc-files`, `svc-workflow` lấy bí mật từ két bằng AppRole thay vì biến môi trường; két giữ khóa cho văn bản hạn chế và ký số (F3.2) | [`van-hanh.md`](van-hanh.md), mục Két bí mật |
| Static seal | Cách két tự mở khóa khi khởi động lại, bằng khóa `MOC_OPENBAO_SEAL_KEY` trong `.env` | [`van-hanh.md`](van-hanh.md), mục Két bí mật |
| Kho nóng, kho lạnh | Hai bucket trên SeaweedFS: `moc-files` cho tệp đang dùng, `moc-cold` cho mốc neo và gói lưu trữ. Kho lạnh bật S3 Object Lock chế độ COMPLIANCE: trong hạn giữ không ai xóa, ghi đè hay rút ngắn hạn được | [`hoi-dap-hoi-dong.md`](du-thi/hoi-dap-hoi-dong.md) câu 17, [`architecture.md`](architecture.md) QĐ-010 |
| Ký số | Bản phát hành được ký PAdES bằng khóa trong két, theo một CA nội bộ. Chỉ để minh họa, không có giá trị pháp lý (F4.5) | [`architecture.md`](architecture.md) QĐ-007 |
| Phả hệ | Ghi nguồn gốc theo chuẩn OpenLineage: gói lưu trữ truy về bảng nghiệp vụ và tệp gốc, biểu đồ ở trang Điều hành truy về khung nhìn và bảng nguồn; xem ở trang `/pha-he` (F3.9) | [`muc-hoan-thien.md`](muc-hoan-thien.md) F3.9 |
| Dashboard điều hành | Trang số liệu cho lãnh đạo: văn bản theo trạng thái, văn bản khẩn chưa xong, văn bản quá hạn; phần văn bản đã nộp lưu do DuckDB đếm trên gói Parquet (F3.11) | [`muc-hoan-thien.md`](muc-hoan-thien.md) F3.11 |
| GitOps, reconciler | `scripts/reconcile.py`, do systemd timer gọi mỗi 60 giây: đưa hệ thống về đúng khai báo trong git: khởi động lại container hỏng, dựng lại container bị mất (F3.3) | [`van-hanh.md`](van-hanh.md), mục GitOps và tự phục hồi |
| Sao lưu | restic sao lưu CSDL, tệp và két; `make backup`, `make restore` (F3.4) | [`van-hanh.md`](van-hanh.md), mục Sao lưu và khôi phục |
| Trang trạng thái | Trang công khai `/trang-thai`, không cần đăng nhập: từng thành phần của lõi đang chạy hay gián đoạn | [`van-hanh.md`](van-hanh.md), mục Trang trạng thái hệ thống |
| Tự chẩn đoán | Trang `/tu-chan-doan` cho lãnh đạo: 12 câu theo bốn không gian H-P-D-I, radar, không gian nên làm trước (F4.7) | [`tu-chan-doan.md`](tu-chan-doan.md) |
| IT/OT | Cảm biến gửi số đo qua NGSI-LD (Scorpio); vượt ngưỡng thì hệ thống dựng dự thảo "Báo cáo sự cố" vào luồng văn bản đi (F3.10) | [`van-hanh.md`](van-hanh.md), mục Hội tụ IT/OT |

## 5. Trợ lý AI

Mọi tác tử chạy được khi không có mô hình ngôn ngữ (bằng quy tắc, nhận dạng chữ và tìm toàn văn). Profile `ai` thêm
mô hình chạy tại chỗ (Ollama, Qwen3) để viết trích yếu và câu trả lời. Số đo và giới hạn:
[`danh-gia-ai.md`](danh-gia-ai.md).

| Thuật ngữ | Nghĩa | Xem thêm |
|---|---|---|
| Đọc văn bản đến | Đọc lớp chữ PDF hoặc nhận dạng chữ bản scan, gợi ý sáu ô của form tiếp nhận. Số và ngày luôn do quy tắc quyết, không do mô hình (F4.1) | [`danh-gia-ai.md`](danh-gia-ai.md) |
| Trợ lý hỏi đáp | Trả lời bằng câu trích nguyên văn kèm nguồn "số ký hiệu · tr. n", chỉ tìm trong văn bản người hỏi được xem (F4.2) | [`architecture.md`](architecture.md) QĐ-004 |
| Gợi ý giao việc | Văn bản vừa vào sổ thì gợi ý đơn vị chủ trì và hạn xử lý, kèm văn bản tương tự làm căn cứ; lãnh đạo quyết (F4.3) | [`architecture.md`](architecture.md) QĐ-005 |
| Che thông tin cá nhân | Che số CCCD, điện thoại, email, tài khoản ngân hàng trước khi tới mô hình và nhật ký (F4.4) | [`architecture.md`](architecture.md) QĐ-006 |

## 6. Ứng dụng

| Thuật ngữ | Nghĩa | Xem thêm |
|---|---|---|
| Văn phòng điện tử | Ứng dụng quản lý văn bản và điều hành theo NĐ 30 (`apps/office`), gồm cả cổng xác thực công khai | [`dac-ta-san-pham.md`](dac-ta-san-pham.md) |
| Không gian cá nhân P.A.R.A | Ứng dụng thứ hai, cắm tay (`apps/ca-nhan`, `/ca-nhan/`): tệp của mỗi người xếp trong bốn thư mục Dự án, Lĩnh vực, Tài nguyên, Lưu trữ | [`them-ung-dung.md`](them-ung-dung.md) §4 |
| Bảng tin đơn vị | Ứng dụng thứ ba, cắm bằng `moc app install` (`apps/bang-tin`, `/bang-tin/`): văn bản vừa vào sổ, vừa phát hành hiện thành tin | [`them-ung-dung.md`](them-ung-dung.md) §1.7 |
| Đơn nghỉ phép | Ứng dụng mẫu mang quy trình duyệt riêng, chạy trên Flowable của lõi (`apps/nghi-phep`, `make demo-quy-trinh`) | [`them-ung-dung.md`](them-ung-dung.md) §7 |
| Danh mục ứng dụng | Trang `/ung-dung` của Văn phòng điện tử, liệt kê các ứng dụng đã cài | [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §1 |
