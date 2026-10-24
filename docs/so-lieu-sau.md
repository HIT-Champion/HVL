# Số đo "sau" và góp ý (F4.6)

Đặc tả [`dac-ta-san-pham.md`](dac-ta-san-pham.md) §8 chọn bốn chỉ số để biết Signet có làm việc văn thư nhanh hơn
không, mỗi chỉ số một cột "trước" (đo ở đơn vị chạy thử theo cách làm cũ) và một cột "sau" (đo trên hệ thống). Tài
liệu này ghi: cột "sau" tính thế nào, đọc ở đâu, vì sao cột "trước" còn trống, dữ liệu mẫu làm lệch số ra sao, và
phần góp ý trong ứng dụng thu gì. Mã chức năng theo đặc tả §4.3; mức hoàn thiện ở
[`muc-hoan-thien.md`](muc-hoan-thien.md).

**Kết quả: chưa đo.** Repo chưa có lần chạy `make do-so-lieu-sau` nào trên hệ thống thật, cũng chưa có đơn vị chạy
thử. Tài liệu không ghi số nào; khi có lần đo, ghi kèm ngày, máy, đơn vị và tệp `out/so-lieu-sau.json`. CI chạy lệnh
này trên dữ liệu mẫu (phần `ai-sao-luu` của job "Chạy thử toàn hệ thống", sau màn giao việc) chỉ để kiểm lệnh chạy
được và tìm ra văn bản; số đó không phải số đo.

## 1. Đọc số ở đâu

| Nơi | Ai | Có gì |
|---|---|---|
| Trang **Số đo** `/so-do` (thanh bên, mục "Số đo") | Lãnh đạo đơn vị (`director`) | Bảng bốn chỉ số, bảng theo tháng của (a), (b), nút "Đo 5 lần tìm" cho (c), điểm góp ý trung bình |
| `make do-so-lieu-sau` | Người vận hành, trên máy chạy hệ thống | Cùng bốn chỉ số, đọc bằng tài khoản lãnh đạo `truongkhoa` của seed qua APISIX; in bảng, ghi `out/so-lieu-sau.json` |
| GraphQL: `office_v_time_to_assign`, `office_v_overdue_rate`, `office_v_feedback_summary` | `director`; khung nhìn góp ý thêm `tenant_admin` | Số đếm, số giờ theo đơn vị và tháng; dòng `month` (hay `screen`) null là dòng mọi tháng (mọi màn hình) |

Ba khung nhìn ở migration `1792281602750_success_metrics`. Như dashboard điều hành, chúng chỉ có số đếm và số giờ,
không cột nào chứa trích yếu, số ký hiệu hay tên người; văn bản hạn chế không vào phép tính nào; tháng theo giờ Việt
Nam. Trung vị, p90 không cộng dồn được từ các tháng nên dòng mọi tháng tính lại trên toàn bộ văn bản (grouping sets).

## 2. Bốn chỉ số

**(a) Thời gian từ khi văn bản đến tới khi được giao xử lý** — `office.v_time_to_assign`.
- Lúc đến: dòng văn bản đến được tạo (`office.documents.created_at`) — văn thư tiếp nhận, hay liên thông tới. Lúc
  giao: lần đầu lãnh đạo đơn vị giao chủ trì (`office.assignments.assigned_at` của việc chủ trì gốc), kể cả việc giao
  rồi hủy để giao lại. Cột `handled_*`: lần đầu văn bản tới tay một người xử lý (việc chủ trì có `user_id`).
- Đặc tả ghi "từ dòng thời gian văn bản"; khung nhìn đọc hai cột trên thay vì `office.document_events` vì hai cột này
  ghi cùng giao dịch với sự kiện, còn nộp lưu (F3.8) gỡ dòng thời gian nhưng giữ văn bản và giao việc — văn bản đã
  nộp lưu vẫn được tính.
- Trung vị, p90 bằng `percentile_cont` (nội suy tuyến tính giữa hai giá trị kề nhau). Khi ít văn bản, p90 gần như là
  văn bản chậm nhất: với 4 văn bản 2, 4, 8, 24 giờ thì p90 là 19,2 giờ.
- `waiting`: văn bản chưa được giao, còn chờ vào sổ hay chờ chỉ đạo — không vào trung vị. Văn bản lãnh đạo cho lưu
  không giao chỉ đếm ở `arrived`. Văn bản đã hủy, văn bản hạn chế không tính. Số giờ âm (lúc giao nhập tay trước lúc
  văn bản đến, vd nạp thẳng vào CSDL) tính là 0.

**(b) Tỷ lệ văn bản xử lý quá hạn** — `office.v_overdue_rate`.
- Hạn giải quyết (`due_on`) so với lúc xong: sự kiện `processed` / `filed` cuối cùng, văn bản đã nộp lưu thì bản giữ
  lại trong `office.archived_document_facts`. Ngày so theo giờ Việt Nam; nhóm theo tháng của hạn.
- `late` gồm văn bản xong sau hạn và văn bản chưa xong mà đã qua hạn (`late_open`) — bỏ văn bản chưa xong thì tỷ lệ
  đẹp hơn thật. Văn bản chưa xong, chưa tới hạn chỉ đếm ở `pending`, không vào mẫu số `judged`. Văn bản không có hạn
  không tính. `judged` = 0 thì không có tỷ lệ (trang và lệnh in "chưa có dữ liệu", không in 0 %).
- Khác cột đúng hạn của trang Điều hành (`v_processing_time`): trang đó chỉ đếm văn bản đã xong, theo tháng xong.

**(c) Thời gian tìm lại một văn bản cũ** — bấm giờ 5 lần tìm, không lưu trong CSDL.
- Lấy 25 văn bản đến cũ nhất (không hạn chế, không hủy, có số ký hiệu), chọn 5 số ký hiệu khác nhau, gọi lần lượt
  `GET /api/search?q=<số ký hiệu>&limit=20` (không song song, không lượt khởi động), ghi số mili giây và vị trí của văn
  bản cần tìm trong kết quả. Báo trung vị, lần chậm nhất, số lần thấy.
- Đây là **độ trễ hệ thống**, không phải thời gian một người tìm ra văn bản: không gồm lúc gõ, đọc kết quả. Tìm theo
  số ký hiệu là trường hợp dễ; người thật hay nhớ mang máng trích yếu hay cơ quan ban hành. Nút trên trang Số đo đo
  từ trình duyệt nên có cả thời gian đi về qua mạng của người bấm, kết quả không lưu lại. Lệnh `make` đo từ máy chạy
  lệnh tới địa chỉ `MOC_PUBLIC_URL` qua APISIX: trên bản cài thật (HTTPS, có thể qua Cloudflare Tunnel) số đo gồm cả
  bắt tay TLS và đường đi qua Cloudflare, không chỉ thời gian xử lý trong hệ thống.

**(d) Số bước chuyển tay (in, ký, mang đi, nhắn tin nhắc)** — chỉ so sánh định tính, không có số. Đếm số bước cần
quan sát quy trình giấy ở đơn vị chạy thử (cột "trước"), mà chưa có đơn vị nào. Bảng dưới so từng bước theo những gì
hệ thống làm được hôm nay:

| Bước | Quy trình giấy | Trên Signet |
|---|---|---|
| Nhận văn bản đến | Văn thư nhận bản giấy, ghi sổ tay | Vẫn đến bằng giấy hay thư điện tử từ ngoài; văn thư quét, tải PDF lên, vào sổ trên hệ thống (F2.2, F2.3) |
| Trình lãnh đạo chỉ đạo | Mang bản giấy lên phòng lãnh đạo, chờ bút phê | Văn bản vào hộp việc của lãnh đạo, có thông báo; lãnh đạo giao chủ trì, phối hợp trên hệ thống (F2.3, F2.5) |
| Chuyển phòng xử lý | Photo, mang tới từng phòng | Phòng được giao thấy ngay trong hộp việc; lãnh đạo phòng phân công người (F2.3) |
| Nhắc hạn | Gọi điện, nhắn tin | Sự kiện `office.document.overdue` báo trên web; email, webhook khi bản cài cấu hình `MOC_SMTP_HOST`, `MOC_NOTIFY_WEBHOOK_URL` (mặc định tắt) |
| Văn bản đi | Soạn, in, trình ký, đóng dấu, cấp số tay | Soạn, duyệt, cấp số, phát hành PDF trên hệ thống (F2.4); ký số F4.5 chỉ minh họa nên vẫn in để ký tay, đóng dấu |
| Phát hành, xác thực | Gửi bản giấy, bên nhận gọi hỏi lại | PDF có mã QR, SHA-256; ai cũng tra được ở cổng xác thực công khai (F2.13) |
| Gửi đơn vị khác | Thư bưu điện, thư điện tử | Liên thông (F3.12) chỉ giữa các đơn vị trên cùng hệ thống; đơn vị ngoài vẫn gửi như cũ |
| Tìm lại văn bản cũ | Lật sổ, lục tủ | Tìm theo số ký hiệu, trích yếu, cơ quan ban hành, nội dung PDF có lớp chữ (F2.7) |

## 3. Cột "trước": chưa đo

Cột "trước" của cả bốn chỉ số là "chưa đo" trên trang, trong lệnh và trong JSON: chưa có đơn vị chạy thử (đặc tả §10
câu 2), và đặc tả §8 yêu cầu chỉ trình bày số đo thật. Trang và lệnh không điền số ước đoán. Khi có đơn vị chạy thử,
đo theo đúng cột "trước" của đặc tả: (a) hỏi văn thư, đếm 20 văn bản đến gần nhất từ sổ; (b) sổ tay, tệp Excel của
văn thư; (c) bấm giờ 5 lần tìm văn bản cũ theo cách đơn vị đang làm; (d) quan sát, đếm số bước của một văn bản đến và
một văn bản đi. Ghi số đó kèm ngày, đơn vị vào tài liệu này; cột "sau" đo trên chính đơn vị đó sau vài tuần dùng.

## 4. Dữ liệu mẫu

`make seed` nạp hai đơn vị mẫu (Khoa Công nghệ thông tin, Khoa Kinh tế) — cột `core.tenants.sample_data` là `true`;
đơn vị thêm sau (`moc tenant create`) là `false`. Khi đơn vị có cờ này, trang Số đo, trang Góp ý và lệnh `make` đều
ghi rõ số tính trên dữ liệu mẫu. Lý do:

- Kịch bản seed đi hết các bước (tiếp nhận, vào sổ, giao, phân công) liền nhau trong vài giây, nên (a) ra vài giây —
  không phải nhịp làm việc của người.
- Hạn của văn bản mẫu là ngày seed cộng `due_in` ngày (`scripts/seed_documents.py`). Ngay sau khi seed, (b) là 0 % hoặc
  "chưa có dữ liệu"; về sau văn bản mẫu chưa xong lần lượt qua hạn thành `late_open` và tỷ lệ tăng dần.
- (c) đo trên vài chục văn bản mẫu, chưa nói được gì về độ trễ khi kho có hàng nghìn văn bản.

## 5. Góp ý trong ứng dụng

Nút **Góp ý** trên thanh trên của Văn phòng điện tử, mọi vai trò đã đăng nhập: chọn mức hài lòng 1–5, viết vài dòng
(không bắt buộc, tối đa 500 ký tự); giao diện tự gắn màn hình đang dùng. Trang **Góp ý** `/gop-y`: ai cũng xem lại góp
ý mình đã gửi; lãnh đạo, quản trị đơn vị xem thêm tổng hợp của đơn vị (theo màn hình, theo mức) và các góp ý gần đây.

- **Thu gì:** mức 1–5, nội dung, khuôn đường dẫn màn hình (`/van-ban/:id`, không phải id thật, không chuỗi truy vấn —
  ràng buộc `feedback_screen`), giờ gửi do CSDL đặt. `user_id` chỉ để người gửi lọc góp ý của mình (trường `mine`) và
  chặn gửi dồn; không vai trò nào đọc được cột này.
- **Không thu:** họ tên, vai trò, phòng, trình duyệt, địa chỉ IP — không có cột nào cho các thứ này, nhưng khuôn màn
  hình có thể gián tiếp cho biết vai trò (xem hạn chế dưới).
- **Ai thấy gì:** văn thư, chuyên viên, lãnh đạo phòng chỉ thấy góp ý của mình. Lãnh đạo đơn vị, quản trị đơn vị thấy
  nội dung, màn hình, giờ gửi của mọi góp ý trong đơn vị, không thấy người gửi. Không ai sửa, xóa qua GraphQL.
- **Chặn gửi dồn:** mỗi người tối đa 3 góp ý mỗi 10 phút, 20 góp ý mỗi 24 giờ — trigger `feedback_guard` ở CSDL, áp cho
  mọi đường ghi kể cả mutation nhiều dòng và các lần gửi song song. Quá giới hạn: lỗi `feedback_rate`, giao diện báo
  bằng câu tiếng Việt.
- **Không gắn sổ kiểm toán** — ngoại lệ có chủ ý so với các bảng nghiệp vụ khác: sổ ghi người thực hiện từng dòng, lãnh
  đạo đọc sổ của đơn vị sẽ biết ai góp ý gì. Góp ý không phải hồ sơ nghiệp vụ.

Hạn chế đã biết:

- "Không hiện người gửi" không phải ẩn danh: giờ gửi chính xác vẫn hiện, ở đơn vị ít người lãnh đạo có thể đoán ra
  người gửi; quản trị hệ thống đọc được bảng trong CSDL. Giao diện ghi đúng như vậy, không hứa ẩn danh.
- Khuôn màn hình lộ vai trò: có màn chỉ một vai trò dùng — `/van-ban-den/tiep-nhan` của văn thư, `/so-do` của lãnh đạo
  đơn vị. Đơn vị chỉ có một văn thư thì góp ý gửi từ màn tiếp nhận, cộng giờ gửi, cho lãnh đạo biết ngay ai gửi. Làm
  tròn giờ trên trang Góp ý cũng không che được: lãnh đạo, quản trị đơn vị đọc `created_at` chính xác qua GraphQL.
  Người gửi muốn kín hơn thì gửi từ màn chung (hộp việc, tìm kiếm).
- Hệ thống không lọc số CCCD, số điện thoại trong nội dung; form chỉ nhắc "Đừng ghi họ tên, số CCCD, số điện thoại".
- Kế hoạch phát triển đặt mục tiêu ≥ 5 người ngoài đội dùng thử và để lại góp ý; đến nay chưa có.

## 6. Cách chạy

```bash
make up && make seed          # hệ thống đang chạy, có dữ liệu mẫu
make do-so-lieu-sau           # in bảng bốn chỉ số, ghi out/so-lieu-sau.json
```

Lệnh thoát 1 khi không đủ 5 văn bản đến có số ký hiệu để tìm, hoặc một lần tìm không thấy văn bản cần tìm trong 20 kết
quả đầu; JSON vẫn được ghi trước khi thoát. Thiếu dữ liệu cho (a), (b) không phải lỗi, chỉ in "chưa có dữ liệu".
Chưa có bước CI chạy lệnh này. Các khóa của `out/so-lieu-sau.json`:

| Khóa | Nội dung |
|---|---|
| `measured_at`, `account` | Giờ đo (UTC, ISO 8601), tài khoản đọc số (`truongkhoa`) |
| `tenant` | `code`, `name` của đơn vị; `sample`: số tính trên dữ liệu mẫu |
| `before` | Luôn là `"chưa đo"` |
| `time_to_assign` | `all`: dòng mọi tháng của `office.v_time_to_assign`; `months`: các tháng, cũ trước |
| `overdue_rate` | `all`, `months` như trên; `late_pct`: `late / judged × 100`, `null` khi `judged` = 0 |
| `search` | `kind` (`"độ trễ hệ thống"`), `endpoint`, `limit`, `runs` (`document_id`, `symbol`, `ms`, `rank`), `median_ms`, `max_ms`, `found` |
| `handoffs` | `kind` `"định tính"`, `value` `null`, `doc` trỏ tài liệu này |
| `feedback` | `count`, `average` (điểm trung bình, `null` khi chưa có), `with_comment` |

Test: db `test_feedback.py`, `test_success_metrics.py` (job `db` của CI); office `feedback.test.ts`,
`metrics.test.ts`; scripts `test_so_lieu_sau.py`. Mô hình dữ liệu: [`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §2.5.
