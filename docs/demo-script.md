# Kịch bản demo — bằng chứng 4 nguyên lý thiết kế

Đề thi (`olp-2026-de-thi.md` §3.2) yêu cầu sản phẩm "được xây dựng dựa trên" 4 nguyên lý, kèm gợi ý bằng chứng
cho từng nguyên lý. Mỗi màn dưới đây:

- chạy bằng **một lệnh** trên hệ thống đang chạy (`make up`, `make seed`), xong trong **dưới một phút**;
- in từng bước kèm dấu ✓, sai bước nào thì dừng và nói rõ bước đó (thoát 1);
- chạy lại bao nhiêu lần cũng được, không sửa dữ liệu mẫu (mỗi lần chỉ thêm dữ liệu riêng của lần chạy, vd một
  tệp sạch chưa gắn văn bản và vài dòng sổ kiểm toán).

Trên máy chủ đã `make install`, chạy `python3 scripts/demo.py <màn>` trong thư mục cài, thay cho `make demo-<màn>`.

Khi trình bày: terminal chạy lệnh một bên, trình duyệt mở giao diện ở bên kia (đường dẫn in ở cuối mỗi màn).

| Nguyên lý | Màn | Lệnh | Tình trạng |
| --- | --- | --- | --- |
| (i) Vòng đời và tốc độ dữ liệu | Nóng → lạnh: hồ sơ đã đóng chuyển sang kho lạnh, vẫn tìm và xác thực được | `make demo-nong-lanh` | Có (F3.8) |
| (ii) Hội tụ IT/OT | Cảm biến nhiệt độ phòng máy → NGSI-LD → dựng nháp báo cáo sự cố | `make demo-it-ot` | Có (F3.10) |
| (iii) Quản trị dữ liệu | Phả hệ: báo cáo ← bảng ← sự kiện; kiểm chất lượng tự động | `make demo-pha-he` | Có (F3.9) |
| (iv) Zero-Trust + GitOps | Kiểm dịch tại cửa ngõ | `make demo-kiem-dich` | Có (F3.1) |
| (iv) Zero-Trust + GitOps | Văn bản hạn chế: tệp mã hóa trong kho, chỉ người có tên mở được, bản mở có dấu tên | `make demo-han-che` | Có (F3.7) |
| (iv) Zero-Trust + GitOps | Két bí mật: dịch vụ không giữ bí mật, két tự mở khóa | `make demo-ket-bi-mat` | Có (F3.2) |
| (iv) Zero-Trust + GitOps | Tự phục hồi từ cấu hình trong git | `make demo-tu-phuc-hoi` | Có (F3.3) |

## (i) Nóng → lạnh — `make demo-nong-lanh`

**Điều muốn chứng minh:**

- Dữ liệu có vòng đời: văn bản đang xử lý nằm ở CSDL nghiệp vụ (nóng). Hồ sơ đã đóng thì nộp lưu (NĐ 30/2020, Điều
  28–31): chi tiết chuyển sang kho lạnh rẻ, không sửa được; CSDL nghiệp vụ chỉ giữ bản ghi rút gọn.
- Chuyển đi mà không mất gì: gói có manifest băm từng phần, đọc lại so băm xong mới gỡ khỏi CSDL. Văn bản vẫn tìm
  thấy, quét mã QR vẫn "khớp", phòng đọc vẫn đọc lại được gói.
- Kho lạnh có khóa ghi: trong thời hạn bảo quản không ai xóa được gói, kể cả quản trị kho.

**Lệnh in ra 5 bước:**

1. Chuyên viên (hoặc tổ trưởng) lập hồ sơ `HS-…`, đưa vào tối đa ba văn bản đã xong mà mình đọc được, thuộc phòng
   mình (ưu tiên văn bản đi đã phát hành, có mã QR), đóng hồ sơ — ngày đóng do CSDL đặt. In số dòng liên kết tệp,
   dòng thời gian, giao việc của các văn bản đó trong CSDL.
2. Gọi job nộp lưu của svc-files ngay (bình thường là vòng nền mỗi giờ, cho hồ sơ đóng quá `MOC_ARCHIVE_AFTER_DAYS`
   ngày). In đường dẫn gói `s3://moc-cold/cold/<đơn vị>/case/<hồ sơ>/`, số văn bản, số tệp, số byte, thời gian, băm
   của manifest (`manifest-<băm>.json`).
3. CSDL nghiệp vụ: văn bản ở trạng thái `archived`; liên kết tệp, dòng thời gian về 0; giao việc giữ nguyên (căn
   cứ quyền xem, sổ đăng ký); bản tệp trong bucket nóng đã xóa.
4. Vẫn dùng được:
   - quét mã tra cứu của văn bản đi ở cổng xác thực, không đăng nhập → "khớp", trạng thái `archived`;
   - văn thư tìm theo số ký hiệu → ra văn bản đã nộp lưu;
   - phòng đọc `GET /api/case-files/{id}/archive`: manifest khớp băm trong CSDL, DuckDB đọc `documents.parquet` ra
     đúng các văn bản.
5. Thử xóa manifest bằng khóa quản trị của kho → bị từ chối (S3 Object Lock, chế độ COMPLIANCE). Dòng
   `case_file.archived` nằm trong sổ kiểm toán chuỗi băm.

**Trên giao diện:**

- *Bất kỳ ai*: mở trang xác thực, nhập mã tra cứu của văn bản vừa nộp lưu → vẫn "Văn bản khớp".
- *Lãnh đạo khoa*: **Sổ kiểm toán** → tab **Văn bản**, dòng "Nộp lưu hồ sơ" kèm ký hiệu hồ sơ, băm gói, số văn bản,
  số tệp; tên hồ sơ không hiện.
- Chưa có màn lập hồ sơ: bước 1 đi qua GraphQL với đúng quyền của chuyên viên.

**Nếu giám khảo hỏi:**

- *"Lạnh là ở đâu?"* Bucket `moc-cold` của SeaweedFS, có khóa ghi, chung với mốc neo sổ kiểm toán. Triển khai thật
  thì trỏ `MOC_COLD_BUCKET` sang ổ rẻ hơn hoặc kho S3 khác. Parquet là định dạng cột mở: công cụ nào cũng đọc được,
  không cần Mộc.
- *"Sao không dùng Kestra?"* Một job mỗi giờ không đáng thêm một máy chủ Java khoảng 1 GB RAM. Job là vòng nền trong
  svc-files, như vòng neo sổ kiểm toán. DuckDB nhúng trong svc-files, không chạy máy chủ riêng.
- *"Hỏng giữa chừng thì sao?"* Thứ tự là kiểm băm tệp nóng → ghi gói → đọc lại so băm → một giao dịch CSDL → xóa
  bản nóng. Giao dịch kiểm CSDL còn đúng như gói (khóa dòng), lệch thì không đổi gì. Hỏng trước giao dịch thì CSDL
  chưa đổi gì, lượt sau làm lại và không ghi lại phần đã có. Hỏng sau giao dịch thì chỉ thừa bản nóng, không mất gì.
- *"Văn bản hạn chế?"* Không vào hồ sơ nộp lưu: tệp của nó mã hóa bằng khóa riêng bọc trong két (F3.7). Nộp lưu
  bản mã hóa cần đưa khóa đã bọc đi cùng gói lạnh và giữ két lâu như gói — chưa làm.

## (ii) Hội tụ IT/OT — `make demo-it-ot`

**Điều muốn chứng minh:**

- Thiết bị vận hành (OT) và hệ thống văn phòng (IT) nói chuyện qua một chuẩn mở: cảm biến cập nhật bản sao số của nó
  trong context broker NGSI-LD (ETSI), Mộc đăng ký nhận sự kiện qua subscription — không viết giao thức riêng.
- Sự kiện vật lý thành văn bản hành chính: nhiệt độ phòng máy chủ vượt ngưỡng → dự thảo "Báo cáo sự cố" dựng từ mẫu,
  đứng tên chuyên viên phụ trách, đi đúng luồng văn bản đi (duyệt phòng → lãnh đạo ký → phát hành). Hệ thống dựng
  nháp, con người kiểm tra và trình — không tự gửi gì.
- Tách theo đơn vị và không tin mạng: mỗi đơn vị một tenant NGSI-LD (thực thể, lịch sử, subscription riêng); thiết
  bị chỉ thấy broker, không gọi được svc-workflow; broker gọi svc-workflow phải kèm token riêng của đơn vị; broker
  và CSDL của nó không mở cổng ra ngoài.

**Lệnh in ra 6 bước** (lần đầu tải image Scorpio và PostGIS, khoảng 380 MB):

1. Bật profile `iot` (Scorpio + PostGIS); svc-workflow tự đăng ký subscription `temperature>35` trong tenant của đơn
   vị, kèm token. In thời gian broker sẵn sàng.
2. Cảm biến giả lập (container chạy một lần, chỉ ở mạng `iot`) gửi 5 lần đo `24 → 29 → 33 → 37 → 41 °C`.
3. Hai lần vượt ngưỡng → đúng **một** dự thảo và một thông báo (dự thảo cũ chưa trình thì chỉ nhắc, mỗi ngày
   nhiều nhất một lần): loại Báo cáo, độ khẩn
   "Khẩn", trích yếu và nội dung từ mẫu (giờ đo, nhiệt độ, ngưỡng, các mục để chuyên viên điền); dòng thời gian có sự
   kiện `ot.alarm`; chuyên viên nhận thông báo ngay.
4. Lịch sử đo nằm trong broker (NGSI-LD temporal API), cả các lần dưới ngưỡng: dữ liệu OT ở lại broker, Mộc chỉ
   nhận sự kiện cần xử lý.
5. Chuyên viên trình → tổ trưởng phòng có việc duyệt, như mọi văn bản đi.
6. Thông báo giả: từ mạng thiết bị không tới được svc-workflow; từ mạng nội bộ (container svc-files) với token sai
   → 401.

Trên giao diện (`chuyenviendt`): chuông thông báo "Cảnh báo nhiệt độ…", mục Văn bản đi có dự thảo, dòng thời gian
ghi "Cảm biến … đo 41 °C, vượt ngưỡng 35 °C — hệ thống dựng dự thảo".

**Nếu giám khảo hỏi:**

- *"Sao không gắn cảm biến thật?"* Cảm biến thật chỉ thay container giả lập: cùng các lệnh NGSI-LD vào broker (qua
  gateway IoT như IoT Agent của FIWARE, hoặc thiết bị tự gửi). Phía Mộc không đổi gì.
- *"Thiết bị có chọn được người đứng tên dự thảo?"* Chỉ một chuyên viên đang hoạt động của đúng đơn vị đó; người khác,
  vai trò khác hay đơn vị khác thì bỏ qua (ghi nhật ký). Dự thảo chỉ là nháp, người đứng tên quyết định có trình.
- *"Thiết bị của đơn vị này có ghi giả vào đơn vị kia được không?"* Ở bản rút gọn thì được, nếu vào được mạng thiết
  bị: Scorpio không xác thực, tenant do bên gửi khai. Triển khai thật đặt cổng thiết bị (IoT Agent / PEP proxy của
  FIWARE) trước broker, cấp tenant theo khóa của từng thiết bị. Phía Mộc không đổi: vẫn chỉ tin subscription.
- *"Vì sao broker riêng chứ không ghi thẳng vào CSDL?"* Bản sao số (trạng thái, lịch sử, truy vấn theo không gian)
  là việc của context broker theo chuẩn; Mộc không phải nơi giữ dữ liệu cảm biến, chỉ nhận sự kiện cần thành văn bản.
- *"Tốn bao nhiêu?"* Profile `iot` không bật mặc định: Scorpio ~400 MB RAM, PostGIS ~130 MB.

## (iii) Phả hệ và kiểm chất lượng — `make demo-pha-he`

**Điều muốn chứng minh:**

- Biết dữ liệu từ đâu ra: mỗi bước của job nộp lưu (màn (i)) để lại một sự kiện theo chuẩn mở OpenLineage. Từ gói
  lưu trữ truy ngược được về bảng nghiệp vụ và tệp gốc đã sinh ra nó.
- Chất lượng kiểm tự động, trước khi ghi: bảng Parquet nào cũng được đọc lại, số dòng phải bằng số dòng trong CSDL,
  cột bắt buộc không được rỗng. Trượt thì job dừng trước khi ghi gì sang kho lạnh, sự kiện FAIL nằm lại trong phả hệ.

**Lệnh in ra 4 bước** (chưa có lượt nộp lưu nào thì chạy màn (i) trước):

1. Lượt nộp lưu gần nhất: run của job `moc.case_file.archive`, START → 4 run con `files`, `tables`, `manifest`,
   `commit` → COMPLETE. Mỗi bước in đầu vào → đầu ra. Lãnh đạo đọc qua Hasura, chỉ thấy đơn vị mình.
2. Truy ngược: `manifest-<băm>.json` ← `documents/assignments/events-<băm>.parquet` + `files/<sha256>` ←
   `moc.office.documents`, `moc.office.assignments`, `moc.office.document_events` + đối tượng trong bucket nóng.
3. Kiểm chất lượng từng bảng: số dòng = CSDL, các cột bắt buộc không null (facet `dataQualityAssertions`,
   `outputStatistics`); số bước trượt kiểm của đơn vị.
4. Sự kiện đúng đặc tả OpenLineage 2-0-2 (`schemaURL`, `producer`, tên dataset theo quy ước): đặt
   `MOC_OPENLINEAGE_URL` là gửi được sang Marquez.

**Nếu giám khảo hỏi:**

- *"Marquez đâu?"* Chưa dựng trong compose: thêm một máy chủ Java và CSDL riêng (khoảng 1 GB RAM) cho một job mỗi
  giờ. Sự kiện lưu trong `core.lineage_events` (cột `event` là nguyên văn OpenLineage), cùng sao lưu với CSDL; bật
  Marquez chỉ cần đặt `MOC_OPENLINEAGE_URL`.
- *"Kiểm trượt thì sao?"* Thử trong test đơn vị: một văn bản thiếu trích yếu → bước `tables` FAIL, không đối tượng nào
  được ghi sang bucket lạnh (ở đó bị khóa nhiều năm), CSDL không đổi, lượt sau thử lại.
- *"Ai sửa được phả hệ?"* Không ai: bảng chỉ thêm, trigger chặn sửa và xóa kể cả khi ghi thẳng CSDL.

## (iv) Kiểm dịch tại cửa ngõ — `make demo-kiem-dich`

**Điều muốn chứng minh:**

- Không tệp nào chạm kho mà chưa qua ClamAV.
- Tệp nhiễm bị chặn ngay ở cửa ngõ, không được lưu. Thứ duy nhất còn lại là dòng sổ kiểm toán ghi lần chặn.
- Sổ kiểm toán là chuỗi băm, neo ra ngoài CSDL: ai sửa hay xóa dòng đó, kể cả quản trị, đều bị phát hiện.

**Lệnh in ra 5 bước:**

1. Văn thư tải lên một công văn bình thường qua cổng APISIX → `201`, ClamAV báo sạch, tệp vào kho.
2. Văn thư tải lên `hoa-don-….pdf` chứa **chuỗi kiểm thử EICAR**. Đây là chuỗi chuẩn để thử phần mềm diệt virus,
   không phải mã độc thật. Kết quả: `422 infected`, ClamAV báo `Eicar-Test-Signature`.
3. `core.files` không có dòng nào mang SHA-256 của tệp đó: tệp bị chặn trên luồng, trước khi ghi vào kho.
4. Lãnh đạo khoa đọc sổ kiểm toán của đơn vị, đúng quyền của mình, và thấy dòng `file.rejected`:
   - thấy giờ, người tải, mẫu mã độc, cỡ tệp;
   - không thấy tên tệp, vì tên do người dùng đặt có thể nói lên nội dung.
5. `moc audit anchor` neo đầu chuỗi ra bucket lạnh khóa ghi (object lock). `moc audit verify` tính lại cả chuỗi bên
   ngoài CSDL: chuỗi liền mạch tới dòng vừa ghi. Từ đó, sửa hay xóa dòng này đều bị phát hiện.

**Trên giao diện:**

- *Lãnh đạo khoa*: vào **Sổ kiểm toán** → tab **Tệp**, có dòng "Chặn tệp nhiễm mã độc" kèm mẫu mã độc và cỡ tệp.
- *Văn thư*: tải tệp EICAR ở **Tiếp nhận văn bản**, tệp hiện đỏ "Tệp nhiễm mã độc (…) — đã bị chặn, không lưu".

**Nếu giám khảo hỏi:**

- *"Chặn ở gateway hay ở dịch vụ?"* Ở `svc-files`, sau APISIX. Mọi đường tải tệp lên đều đi qua đây, không có
  đường nào ghi thẳng vào SeaweedFS. Tệp được quét trên luồng trước khi ghi vào kho. ClamAV không trả lời thì
  từ chối tệp (`503`), không cho qua.
- *"Mã độc mới, chưa có mẫu thì sao?"* ClamAV chỉ bắt được mẫu đã biết. Mẫu tự cập nhật nhiều lần mỗi ngày
  (freshclam chạy sẵn trong image `clamav/clamav`). Lớp sau là: tệp không bao giờ được thực thi trên máy chủ,
  PDF chỉ được đọc trong tiến trình con có giới hạn bộ nhớ, CPU và thời gian (F2.7).

## (iv) Văn bản hạn chế — `make demo-han-che`

**Điều muốn chứng minh:**

- Không tin vào chỗ lưu: tệp đính kèm trong kho tệp và bản sao lưu chỉ là bản mã, người quản trị CSDL chỉ thấy khóa
  đã bọc. Khóa của từng tệp bọc trong két, chỉ két mở được. (Trích yếu, nội dung soạn trên hệ thống vẫn nằm trong
  CSDL, chỉ được che bằng phân quyền.)
- Không tin vào vị trí trong mạng: mỗi lần mở tệp đều hỏi lại quyền theo người, theo văn bản. Người không có tên nhận
  `404` y như tệp không tồn tại.
- Bản rõ chỉ có trong bộ nhớ, trong khoảnh khắc trả về, mang tên người xem; mỗi lần mở đều vào sổ kiểm toán.

**Lệnh in ra 6 bước:**

1. Văn thư tải `nang-luong-….pdf` lên ở chế độ hạn chế. `svc-files` xin két một khóa AES-256 riêng cho tệp, mã hóa
   rồi mới ghi: đọc thẳng đối tượng trong kho thấy bắt đầu bằng `MOC1`, không có đầu `%PDF`, không có chữ trong tệp.
   CSDL chỉ giữ khóa đã bọc (`vault:v1:…`).
2. Văn thư tiếp nhận văn bản hạn chế. Quy trình giao lãnh đạo khoa cho ý kiến chỉ đạo, và `svc-workflow` tự thêm lãnh
   đạo khoa vào danh sách được xem — nhận việc mà không mở được văn bản thì vô nghĩa.
3. Tổ trưởng Tổ Đào tạo không có tên: không đọc được văn bản, mở thẳng đường dẫn tệp → `404`.
4. Lãnh đạo khoa mở tệp: bản giải mã trong bộ nhớ, trên trang có dòng "VĂN BẢN HẠN CHẾ — bản giải mã cho …, giờ…",
   `Cache-Control: no-store`; băm khác bản gốc vì mỗi người, mỗi lần mở là một bản riêng.
5. Thông báo việc mới của lãnh đạo khoa chỉ có nhãn "Văn bản hạn chế", không số ký hiệu, trích yếu, cơ quan ban hành.
6. Sổ kiểm toán có dòng `file.decrypted` của lãnh đạo khoa; lần tổ trưởng bị từ chối không giải mã gì nên không có
   dòng.

**Trên giao diện:**

- *Văn thư*: **Tiếp nhận văn bản**, tích "Hạn chế người xem" *trước khi* tải tệp (chỉ nhận PDF; đã có tệp thì ô này
  khóa lại), tệp hiện "Đã quét — sạch, đã mã hóa". Trang văn bản: tệp có nhãn "Đã mã hóa", mục **Người được xem** có
  lãnh đạo khoa, gỡ hoặc cấp thêm người được.
- *Lãnh đạo khoa*: chuông ghi "Việc mới … Văn bản hạn chế"; mở tệp thấy tên mình đóng chéo trang.
- *Tổ trưởng*: dán đường dẫn văn bản → "Không tìm thấy văn bản, hoặc bạn không có quyền xem."

**Nếu giám khảo hỏi:**

- *"Đây là văn bản mật à?"* Không. Đây là văn bản hạn chế người xem trong cơ quan (lương, kỷ luật, nhân sự). Văn bản
  mật nhà nước phải dùng hệ thống, mật mã được cấp phép riêng theo Luật Bảo vệ bí mật nhà nước 2018; giao diện và tài
  liệu đều ghi rõ điều này.
- *"Lấy được ổ đĩa, bản sao lưu thì sao?"* Chỉ có bản mã và khóa đã bọc. Mở khóa phải qua két, két cần khóa mở két
  trong `.env`. Bản sao lưu gồm cả két (để khôi phục được), nên `.env` phải giữ riêng, ngoài bản sao lưu.
- *"Người có tên chụp màn hình, chuyển tiếp thì sao?"* Không chặn được. Tên người xem và giờ xem nằm trên mọi trang,
  sổ kiểm toán ghi từng lần mở: lộ thì truy được từ bản nào.
- *"Lãnh đạo khoa vốn đọc được mọi văn bản, sao còn cần có tên?"* Vai trò chưa đủ: văn bản hạn chế còn cần có tên.
  Người nhận việc được tự thêm; văn thư, lãnh đạo khoa thêm hoặc gỡ người khác, mỗi lần đều vào sổ.
- *"Tìm theo nội dung được không?"* Không: tệp mã hóa không được đọc chữ, nội dung văn bản hạn chế không vào chỉ mục,
  vì một bản chữ trần nằm ngoài tệp là vô hiệu việc mã hóa. Tìm theo số ký hiệu, trích yếu vẫn được nếu có quyền.

## (iv) Két bí mật — `make demo-ket-bi-mat`

**Điều muốn chứng minh:**

- Dịch vụ của đội không nhận bí mật qua biến môi trường (`docker inspect` hay `/proc/<pid>/environ` không lộ gì);
  bí mật nằm trong két OpenBao, mỗi dịch vụ đăng nhập bằng danh tính riêng (AppRole) và chỉ đọc được phần của mình.
- Két tự mở khóa khi khởi động lại (static seal), nên máy chủ khởi động lại hay dịch vụ bị dựng lại (F3.3) không cần
  người nhập khóa.
- Mọi lần đăng nhập, đọc bí mật đều vào sổ của két; giá trị bí mật trong sổ đã băm.

**Lệnh in ra 5 bước:**

1. Băm giá trị từng biến môi trường trong container `svc-files`, `svc-workflow`, so với băm của các bí mật trong
   `.env`: không khớp cái nào. Env chỉ có địa chỉ két (`MOC_OPENBAO_ADDR`, `MOC_OPENBAO_SECRET_PATH`).
2. `docker compose restart openbao`: két khởi động lại, tự mở khóa, nạp lại bí mật và cấp secret_id mới cho từng dịch
   vụ (hủy cái cũ) trong vài giây; `svc-files`, `svc-workflow` khởi động lại theo và lấy lại bí mật. `bao status`:
   seal `static`, `sealed=false`.
3. `docker compose restart svc-files`: dịch vụ đăng nhập két bằng secret_id mới, lấy khóa kho S3, rồi văn thư tải một
   tệp lên → `201`. Khóa kho không đi qua đâu ngoài két.
4. Trong container `svc-workflow`, thử đọc phần bí mật của `svc-files` bằng AppRole của `svc-workflow` → két từ chối
   `403`.
5. Đọc sổ của két (`docker compose logs openbao`) từ lúc khởi động lại: thấy `svc-files` đăng nhập rồi đọc
   `moc/data/svc-files`, và lần `svc-workflow` đọc chéo bị từ chối ở bước 4; không giá trị bí mật nào xuất hiện rõ
   trong sổ.

**Nếu giám khảo hỏi:**

- *"Bí mật vẫn nằm trong `.env` mà?"* Đúng. `.env` vẫn là nguồn: container `openbao` nhận chúng và nạp vào két mỗi
  lần khởi động. Cái được: dịch vụ của đội không giữ bí mật trong biến môi trường, mỗi dịch vụ chỉ đọc được phần của
  mình, mọi lần đọc có sổ. Phần mềm thượng nguồn (Hasura, SeaweedFS, Meilisearch, Centrifugo) vẫn đọc bí mật của
  chúng từ biến môi trường.
- *"Khóa mở két để đâu?"* `MOC_OPENBAO_SEAL_KEY` trong `.env`, khóa phục hồi và token khởi động trong volume của két,
  `role_id`/`secret_id` của dịch vụ trong volume riêng của dịch vụ đó. Ai có quyền Docker trên máy chủ vẫn đọc được
  két. Static seal đổi an toàn lấy khả năng tự phục hồi; bản thật nên dùng KMS hoặc HSM (seal `pkcs11`, `awskms`…).
- *"Ai cấu hình két?"* Lần đầu, `openbao/start.sh` cấu hình bằng token root rồi thu hồi nó ngay. Các lần sau chỉ
  dùng token khởi động: không đọc thẳng được bí mật, không sửa được policy, nhưng cấp được secret_id cho hai dịch vụ
  — nên volume của két phải được giữ như chính két.
- *"Két dùng làm gì nữa?"* Khóa transit `moc-files` để mã hóa tệp của văn bản hạn chế (F3.7, `make demo-han-che`):
  `svc-files` chỉ xin được khóa dữ liệu mới và mở khóa đã bọc, không bao giờ cầm khóa gốc.

## (iv) Tự phục hồi — `make demo-tu-phuc-hoi`

**Điều muốn chứng minh:**

- Trạng thái mong muốn nằm trong git (`docker-compose.yml`, cấu hình cổng, policy két…); một reconciler đều đặn
  so trạng thái đang chạy với khai báo và tự sửa phần lệch, không cần người.
- Dịch vụ chết hay bị xóa hẳn thì được dựng lại; cấu hình bị sửa tay trên máy chủ thì bị đưa về đúng commit.

**Lệnh in ra 4 bước (dưới một phút):**

1. Một lượt `scripts/reconcile.py`: "đã khớp trạng thái khai báo, không có gì phải làm".
2. Phá: `docker rm -f` container `svc-files` (mất hẳn, không phải chỉ dừng), `docker stop` container `centrifugo`.
   Văn thư tải tệp → cổng trả lỗi vì không tới được dịch vụ.
3. Một lượt reconciler (trên máy chủ là systemd timer mỗi 60 giây, ở đây gọi ngay): in "dựng lại svc-files (không
   còn container)", "chạy lại centrifugo (đã dừng: …)".
4. Hai dịch vụ về `running (healthy)` (svc-files lấy lại bí mật từ két F3.2), văn thư tải tệp → `201`.

**Phần GitOps** (chạy trong CI, bước "GitOps"; trên máy chủ xem README mục "GitOps và tự phục hồi"):

- Đẩy một commit lên nhánh `deploy` của repo → lượt reconciler kế tiếp in "áp commit … (nhánh deploy: cũ → mới)",
  tệp `VERSION` của bản cài mang commit mới, smoke vẫn qua.
- Sửa tay `docker-compose.yml` trong thư mục cài → lượt kế tiếp in "tệp đã cài bị sửa tay, đưa về commit …" và
  tệp trở lại đúng như trong git.

**Đối chiếu bốn nguyên tắc OpenGitOps 1.0:**

| Nguyên tắc | Ở Mộc |
| --- | --- |
| Khai báo (declarative) | Toàn bộ hệ thống khai trong `docker-compose.yml` + cấu hình từng thành phần (realm Keycloak, metadata Hasura, cổng APISIX, cấu hình két); không bước dựng tay nào ngoài `.env` |
| Có phiên bản, bất biến (versioned and immutable) | Trạng thái mong muốn là một commit git; image dựng theo commit (`MOC_VERSION` = `git describe`), tệp `VERSION` của bản cài ghi commit; lùi phiên bản = đẩy commit cũ lên `deploy` |
| Tự kéo về (pulled automatically) | Reconciler trên máy chủ tự `git fetch`; không ai đẩy vào máy chủ, CI không cần quyền vào máy chủ |
| Liên tục đối chiếu (continuously reconciled) | systemd timer mỗi 60 giây: so commit, so băm tệp đã cài, so container đang chạy với khai báo; lệch thì sửa |

**Nếu giám khảo hỏi:**

- *"Sao không dùng Argo CD hay Flux?"* Hai công cụ đó chạy trên Kubernetes; Mộc nhắm máy chủ đơn vị chạy Docker
  Compose. Reconciler là một script thư viện chuẩn Python, đọc được trong vài phút.
- *"Docker có `restart: unless-stopped` rồi mà?"* Chính sách đó chỉ chạy lại container còn tồn tại và không chạy lại
  container bị `docker stop`. Container bị xóa hẳn, hay cấu hình lệch khỏi git, thì chỉ reconciler đưa về được.
- *"Áp commit có làm gián đoạn không?"* Có, khoảng một phút: reconciler dựng image trước, rồi dừng Mộc, cài lại đúng
  commit và chạy lại. Commit áp lỗi thì reconciler đợi commit kế tiếp chứ không thử lại liên tục.
- *"`.env` thì sao?"* Không nằm trong git (chứa bí mật), reconciler không đụng tới; đổi `.env` vẫn là việc của
  người vận hành.
