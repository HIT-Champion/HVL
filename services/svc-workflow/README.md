# svc-workflow

Xử lý **Hasura Actions** của Văn phòng điện tử và nối PostgreSQL (qua Hasura) với Flowable (BPMN). Ứng dụng
chỉ nói chuyện với GraphQL; thao tác nghiệp vụ là Action, Hasura chuyển sang đây kèm biến phiên lấy từ JWT —
thuê ước, người dùng, vai trò không do client tự khai. Flowable giữ trạng thái quy trình (đang ở bước nào, ai
phải làm); PostgreSQL giữ dữ liệu nghiệp vụ ([`docs/du-thi/ke-hoach-phat-trien.md`](../../docs/du-thi/ke-hoach-phat-trien.md) §2.1).
Chủ: issue #15.

| Action | Vai trò | Làm gì |
|---|---|---|
| `receiveIncoming(data)` | `clerk` | Tiếp nhận văn bản đến: kiểm lại `data` theo `schemas/van-ban-den.json` (poka-yoke lớp 2, F2.2), tra loại văn bản, tệp, văn bản trùng, rồi ghi văn bản `received`. Lỗi trả từng trường trong `extensions.fields` (`schemas/README.md`) |
| `registerIncoming(documentId)` | `clerk` | Vào sổ (hàm `office.register_incoming`, một giao dịch) → khởi chạy `van-ban-den` |
| `submitOutgoing(documentId, signerId)` | `staff` | Người soạn trình dự thảo → khởi chạy `van-ban-di`, hoặc trình lại sau khi bị trả lại. Có đơn vị nhận trong hệ thống (`recipient_tenant_ids`) thì kiểm: có thật, không phải đơn vị mình, văn bản không hạn chế (`400`, `fields.recipient_tenant_ids` = `unknown` / `self` / `restricted`) |
| `myTasks` | người dùng nghiệp vụ | Việc của người gọi và của nhóm vai trò của họ, khẩn trước |
| `completeTask(taskId, outcome, data)` | người được giao | Kiểm quyền và dữ liệu → nhận việc → ghi CSDL (một giao dịch) → hoàn thành trong Flowable. Phát hành văn bản đi (`vbdi.phatHanh`): cấp số đi (hàm `office.number_outgoing`) → `svc-files` dựng PDF có mã QR → ghi băm, `issued` → liên thông tới đơn vị nhận trong hệ thống |
| `otSensorMap` | `clerk`, `staff`, `manager`, `director` | Chỉ đọc: số đo mới nhất và cờ chất lượng của các cảm biến NGSI-LD trong đơn vị người gọi (mục IT/OT bên dưới) |
| `notifyFromFlow(roles, title, text, document_id, key)` | `tu_dong` (robot của flow Node-RED) | Báo người đang hoạt động của đơn vị robot theo vai trò, thông báo `flow.message` (mục Tự động hóa bên dưới) |

Chi tiết từng loại việc, dữ liệu và nhóm ứng viên: [`docs/mo-hinh-du-lieu.md`](../../docs/mo-hinh-du-lieu.md) §4.
Hợp đồng HTTP giữa Hasura và dịch vụ (thân yêu cầu, mã lỗi): [`docs/api/openapi/svc-workflow.json`](../../docs/api/openapi/svc-workflow.json),
xuất bằng `make api-docs`.

**Quy trình của ứng dụng (#301)**: gói `svc_workflow/apps/` (luôn bật, không phụ thuộc `MOC_OFFICE_ENABLED`) mở năm
đường `/api/workflow/{app}/…` qua APISIX cho ứng dụng cắm bằng manifest — token phải của client `app-{app}` — và lệnh
`python -m svc_workflow.apps.deploy check|install|remove <tên>` mà `moc app install | remove` gọi trong container:
kiểm BPMN theo danh sách trắng, form, rồi triển khai thành một deployment trên cùng Flowable. Chi tiết:
[`docs/them-ung-dung.md`](../../docs/them-ung-dung.md) mục 1.10, [`docs/api/README.md`](../../docs/api/README.md) §8.

**Cảnh báo vận hành (#284, F3.13)**: `alerts.py` (luôn bật) mở `POST /ops/alerts` trong mạng nội bộ cho Alertmanager
(`platform/monitoring/alertmanager.yml`), kèm `Authorization: Bearer <MOC_ALERT_TOKEN>`. Mỗi cảnh báo `firing` hay
`resolved` của webhook thành một thông báo `ops.alert` cho mọi người dùng vai trò `tenant_admin` của mọi đơn vị, đi
chuông và kênh ngoài như thông báo khác; khóa chống trùng `ops.alert:<fingerprint>:<startsAt>:<status>` nên
Alertmanager gửi lại không thêm dòng. Thông báo chỉ có câu `summary`, mức, nhãn `component`, `route` của luật. Thiếu
token → 404, sai token → 401, thân sai dạng → 400, chưa ghi được CSDL → 503 (Alertmanager gửi lại).

**Tự động hóa bằng Node-RED (#366)**: `tu_dong.py` (luôn bật) nhận Action `notifyFromFlow` ở
`POST /actions/tu-dong/{name}`. Chỉ vai trò `tu_dong` gọi được: token client credentials của robot đơn vị, người làm
(`x-hasura-user-id`) là tên client của robot, không phải người trong danh bạ. Robot báo mọi người đang hoạt động có vai
trò trong `roles` của chính đơn vị mình (đọc, ghi bằng vai trò service theo đơn vị của phiên); thông báo
`flow.message` mang `title` (một dòng, ≤ 120 ký tự), `text` (≤ 1000 ký tự, giữ xuống dòng), `robot` và phần văn bản như
thông báo khác, đi chuông và kênh ngoài (webhook, SMS, Zalo không mang `text`). Khóa chống trùng `flow:<robot>:<key>`:
gửi lại cùng `key` không thêm dòng, `sent` là số người vừa nhận. Kèm `document_id` thì chỉ được `director`, `clerk`
(hai vai trò thấy mọi văn bản không hạn chế của đơn vị; vai trò khác → 422 `fields.roles = document_readers_only`);
văn bản của đơn vị khác → 404, văn bản hạn chế → 403. Nhật ký `tu_dong.notify` không có tiêu đề, lời nhắn.

**Không ghi hai lần**: các lần gọi cùng một việc (`completeTask`) hay cùng một văn bản (vào sổ, trình, job đối soát)
chạy lần lượt trong tiến trình, lần sau thấy việc lần trước đã làm. CSDL chặn thêm khi có nhiều bản sao dịch vụ:
chỉ mục duy nhất `document_events_task_once` (một việc một sự kiện — lỗi này thì đọc lại sự kiện đã ghi, hoàn
thành nốt trong Flowable theo biến `flow` ghi kèm), và `process_id` chỉ gắn khi văn bản chưa có — lần gọi thua theo
quy trình đã gắn, hủy quy trình nó vừa khởi chạy (`FlowableClient.delete_process`; lỗi thì nhật ký ghi
`office.process.duplicate_left`). Nhiều bản sao thì vẫn có thể làm thừa trước lúc ghi (dựng PDF phát
hành không dùng tới); dịch vụ hiện chạy một tiến trình. Còn một chỗ chưa gọn: lần gọi trước hết giờ chờ ở Hasura
(90 giây) nhưng vẫn chạy xong, người dùng bấm lại thì lần sau báo "Việc không còn" (404) dù việc đã làm — tải lại
trang là thấy bước mới.

**Thông báo** (F2.5, `notify.py`): sau mỗi bước, người phải làm việc kế tiếp nhận thông báo — ghi
`core.notifications` rồi đẩy qua HTTP API nội bộ của Centrifugo tới kênh riêng `personal:#<sub>`. Thông báo gửi
sau khi bước đã ghi xong; lỗi ghi hay lỗi đẩy chỉ ghi nhật ký, không làm hỏng bước nghiệp vụ. Mỗi người nhận
một lần cho mỗi khóa (gọi lại Action không gửi trùng).

**Thông báo qua email, webhook** (`channels.py`, chỉ khi đặt `MOC_SMTP_HOST` hoặc `MOC_NOTIFY_WEBHOOK_URL`; mặc định
tắt, mọi thứ như trên): lúc ghi thông báo, `Router.route` khai kênh ngoài ở cột `channels` của từng dòng
`core.notifications` — email cho mỗi người nhận, webhook một tin cho cả sự kiện (gắn vào dòng của người nhận đầu tiên).
Trigger CSDL tạo một dòng `core.notification_deliveries` `pending` cho mỗi kênh trong cùng giao dịch (hộp thư đi như
liên thông): thông báo đã lưu thì không mất thư khi dịch vụ dừng; gọi lại cùng khóa không thêm dòng. Vòng nền
`Router.serve` chạy ngay khi có thông báo mới và mỗi `MOC_NOTIFY_INTERVAL_S` giây, mỗi lượt tối đa 20 dòng đến hạn của
mọi đơn vị:

- email: `smtplib` của thư viện chuẩn, chạy ở luồng riêng, STARTTLS hoặc SSL theo `MOC_SMTP_TLS`; địa chỉ, họ tên đọc
  từ danh bạ (`core.users`, đồng bộ từ Keycloak) lúc gửi. Tiêu đề `[Signet] <như chuông>`, thân có số ký hiệu, trích
  yếu, ý kiến và liên kết `<MOC_PUBLIC_URL>/van-ban/<id>`; `Message-ID` cố định theo dòng, `Auto-Submitted:
  auto-generated`;
- webhook: `POST` JSON `{"text": …}` (incoming webhook của Mattermost, Slack) hoặc, với
  `MOC_NOTIFY_WEBHOOK_FORMAT=ntfy`, thân là chữ thuần, tiêu đề và liên kết ở tham số `title`, `click`. Webhook là kênh
  chung nên tin không có tên người ("Người được giao"), không có ý kiến; thông báo của văn bản hạn chế không lên webhook
  (xét lúc ghi và lúc gửi, vì CSDL gọt thông báo khi văn bản chuyển sang hạn chế).

Câu chữ lấy như chuông (`apps/office/app/locales/vi.json`, `task.*`, `notify.*`; `tests/test_channels.py` đối chiếu
hai bên). Kết quả mỗi dòng: `sent`; lỗi tạm (không nối được, hết giờ, SMTP 4xx, HTTP 408, 429, 5xx) thì thử lại sau
30 s·2^lần, tối đa 5 lần rồi `failed`; bị từ chối hẳn (SMTP 5xx với người nhận hay nội dung, HTTP 4xx khác, chuyển
hướng) thì `failed` ngay; `skipped` khi người nhận chưa có email, đã khóa, kênh đã tắt sau lúc xếp hàng, hoặc văn bản
hạn chế trên webhook. Gửi ít nhất một lần, không phải đúng một lần: dừng giữa lúc gửi và lúc ghi kết quả thì lượt sau
gửi lại (cùng `Message-ID`). Ghi kết quả có khóa lạc quan (còn `pending`, đúng số lần thử), giả định một tiến trình
như các vòng nền khác. Hộp thư đi không lưu địa chỉ, URL hay nội dung; `last_error` và nhật ký
(`core.notification.delivered`, `delivery_failed`, `delivery_skipped`) chỉ có id dòng, kênh, loại, số lần thử, tên lớp
lỗi kèm mã SMTP/HTTP — không chép thông điệp lỗi của smtplib, httpx2 vì chúng mang địa chỉ người nhận, URL webhook.
Mỗi lần xếp hàng và mỗi kết quả vào sổ kiểm toán chuỗi băm (đã gửi cho ai, qua kênh nào, lúc nào, thử mấy lần). Thử
trên máy không cần máy chủ thư: profile `mail` (Mailpit) — xem [docs/trien-khai.md](../../docs/trien-khai.md) mục 7.

**Thông báo qua SMS, Zalo** (`channels.py`, `subscriptions.py`, #365; chỉ khi đặt `MOC_SMS_GATEWAY_URL` hoặc
`MOC_ZALO_BOT_TOKEN`, mặc định tắt): khác email, hai kênh này chỉ gửi cho người **tự bật** ở mục Kênh thông báo cuối
chuông (Action `myChannels`, `setMyChannel`, bảng `core.notification_subscriptions`). `Router.route` khai `sms`,
`zalo` cho mọi dòng thông báo, trừ văn bản hạn chế; trigger CSDL chỉ xếp hàng khi người nhận còn bật kênh, tài khoản
chưa khóa và — với SMS — danh bạ có số. Lúc gửi xét lại cả ba điều. Tin ngắn, không tên người, không ý kiến hay trích
yếu: `Signet: <như chuông>` kèm liên kết.

- SMS: [SMS Gateway for Android](https://github.com/capcom6/android-sms-gateway) (Apache-2.0) chế độ Local Server
  trên một điện thoại có SIM cùng mạng LAN với máy chủ: `POST <MOC_SMS_GATEWAY_URL>/message`, Basic Auth, 202 là đã
  vào hàng gửi của điện thoại. Số lấy từ `core.users.phone`, đồng bộ từ thuộc tính `phone_number` của Keycloak
  (quản trị nhập; người dùng chỉ xem, không tự sửa), chuẩn hóa về `+84…` (`directory.py`). Giao diện chỉ thấy số đã
  che (`+84••••••678`).
- Zalo: bot của đơn vị trên Zalo Bot Platform (`MOC_ZALO_BOT_TOKEN`). Bật Zalo sinh mã 8 ký tự hạn 15 phút; người
  dùng nhắn mã cho bot, vòng nền đọc tin bằng `getUpdates` (long polling 30 giây, lùi dần tới 5 phút khi lỗi — bot
  không được đặt webhook), ghi `zalo_chat_id` rồi trả lời trong Zalo. Chỉ nhận chat ghi rõ là riêng
  (`chat_type: PRIVATE`); mã sai, hết hạn thì bot báo lại; tin không phải mã nhận lời nhắc cách dùng, mỗi chat tối đa
  một lần trong 10 phút. Tắt Zalo xóa chat_id, bật lại phải liên kết lại.

Thử lại, `failed`, `skipped` như email; lỗi Zalo ghi mã lỗi của API (`Zalo <mã>`), 429 và lỗi tạm thử lại. Nhật ký
không có số điện thoại, chat_id, mã liên kết hay nội dung tin.

**Nhắc hạn** (`sla.py`): mỗi việc trong BPMN có timer `R2/${slaDuration}`; timer bắn thì Flowable tạo việc giao
ra ngoài (external worker, topic `moc-sla`), dịch vụ lấy về mỗi `MOC_SLA_POLL_INTERVAL_S` giây: quá một thời
hạn thì nhắc người phải làm, quá hai thì báo thêm lãnh đạo của họ.

**IT/OT** (F3.10, `ot.py`, chỉ khi đặt `MOC_NGSI_URL`): mỗi `MOC_OT_SUBSCRIPTION_INTERVAL_S` giây đảm bảo mỗi
đơn vị có một subscription NGSI-LD (id cố định `urn:ngsi-ld:Subscription:moc-ot-alarm`, `temperature>MOC_OT_THRESHOLD`)
trỏ về `POST /ot/notify/{tenant}` kèm header `X-Moc-OT-Token` = HMAC-SHA256 của `MOC_ACTION_SECRET` trên tên tenant.
Tên tenant NGSI-LD = mã đơn vị nếu chỉ có chữ, số ASCII, không thì `t` + 16 ký tự hex băm của mã. Đổi ngưỡng thì
thay subscription; broker chưa chạy thì chỉ ghi nhật ký một lần; một đơn vị lỗi không chặn đơn vị khác. Thông báo
tới thì kiểm token, đọc từng cảm biến vượt ngưỡng (bỏ ký tự điều khiển trong tên phòng), rồi dựng dự thảo văn bản đi
"Báo cáo sự cố" (một giao dịch GraphQL cùng sự kiện `ot.alarm`) đứng tên chuyên viên khai ở thuộc tính `responsible`
của cảm biến, và báo người đó. Còn dự thảo chưa trình hoặc bị trả lại của cùng cảm biến thì không dựng thêm, chỉ nhắc
(khóa thông báo theo dự thảo và ngày). Giờ, ngày trong dự thảo và ngày của khóa theo `observedAt` của thiết bị;
muộn hơn giờ máy chủ quá 2 phút (`FUTURE_SLACK`, đồng hồ thiết bị chạy nhanh) thì theo giờ máy chủ nhận thông báo,
dự thảo ghi rõ giờ thiết bị gửi, sự kiện giữ giờ đó ở `device_observed_at`. Vòng nền còn giữ một subscription
"neo" tạm dừng ở tenant mặc định (`urn:ngsi-ld:Subscription:moc-ot-context`): Scorpio 6.0.2 cất ngữ cảnh JSON-LD của
subscription trong CSDL của tenant nhưng lúc gửi thông báo lại tìm ở tenant mặc định — thiếu neo thì broker bỏ mọi
thông báo (nhật ký Scorpio: "Mutiny had to drop … ResponseException").

**Sơ đồ cảm biến** (F3.10, Action `otSensorMap`, trang `/cam-bien` của Văn phòng điện tử): đọc broker ở tenant NGSI-LD
của đơn vị trong biến phiên — `GET /ngsi-ld/v1/entities?type=TemperatureSensor&options=sysAttrs` (tối đa 100 cảm
biến) và lịch sử 10 lần đo gần nhất của từng cảm biến (temporal API, tối đa 8 lời gọi một lúc, cả lượt 8 giây) — rồi
trả số đo mới nhất, mã phòng (Property `room`), ngưỡng và bốn cờ chất lượng: `stale` (quá `MOC_OT_STALE_MIN` phút
không có số đo, theo `observedAt`, thiếu hay ở tương lai thì `modifiedAt` — lúc broker nhận), `out_of_range` (không
phải số hữu hạn hoặc ngoài −55…125 °C — dải đo của DS18B20), `duplicate_time` (số đo mới nhất trùng `observedAt` với
lần đo khác trong lịch sử), `future_time` (`observedAt` muộn hơn giờ máy chủ quá 2 phút — đồng hồ thiết bị chạy
nhanh; thiết bị đó mất tín hiệu vẫn bị gắn `stale`).
Vai trò `clerk`, `staff`, `manager`, `director`. Chưa đặt `MOC_NGSI_URL` thì `status` = `off`; broker không trả lời
hay trả lỗi thì `unavailable` — vẫn 200, không 5xx. Chỉ đọc, không ghi CSDL.

**Liên thông trong hệ thống** (F3.12, `dispatch.py`): văn bản đi có đơn vị nhận trong hệ thống thì lúc phát hành
CSDL tạo một dòng `office.dispatches` `pending` cho mỗi đơn vị, cùng giao dịch (trigger — hộp thư đi). Sau khi
chuyển bước, `completeTask` chuyển ngay các dòng của văn bản đó (giới hạn 15 giây, lỗi không làm hỏng bước phát
hành): `svc-files` chép bản PDF phát hành sang đơn vị nhận (`POST /internal/dispatch-file`, id bản sao định trước)
→ hàm `office.deliver_dispatch`, gọi trong phiên của bên nhận, dựng văn bản đến `received` gắn bản sao, ghi sự kiện
ở cả hai bên → báo văn thư bên nhận (`document.incoming`; không có văn thư thì lãnh đạo đơn vị) → đặt
`notified_at`. Lỗi thì ghi `last_error` (bên gửi thấy ở thẻ "Liên thông"), thử lại sau 30 s·2^lần, tối đa 1 giờ; mỗi
`MOC_DISPATCH_INTERVAL_S` giây vòng nền chuyển dòng đã đến hạn và báo dòng đã chuyển mà chưa báo (dịch vụ dừng giữa
chừng). Bên nhận đã tiếp nhận tay văn bản này thì dòng thành `duplicate`, nối vào văn bản đã có, không báo ai; CSDL
từ chối dữ liệu thì `failed`, không thử lại (chưa có thao tác gửi lại). Mỗi dòng một lượt (`dispatch:<id>`), mỗi
người nhận một thông báo (khóa `doc:<văn bản đến>:document.incoming`); sự kiện liên thông không mang `task_id`.

**Tác tử gợi ý giao việc** (F4.3, `advisor.py`, `suggest.py`): vào sổ xong, quy trình `van-ban-den` tách hai nhánh
song song (cổng `tachGoiY`): bước chỉ đạo như cũ, và việc giao ra ngoài `goiYGiaoViec` (topic `moc-goi-y`). Nhánh gợi ý
không nối lại, không có terminate: lãnh đạo có việc "Cho ý kiến chỉ đạo" ngay lúc vào sổ, không chờ tác tử; quá 10 phút
không ai nhận việc (dịch vụ dừng, `MOC_SUGGEST_POLL_INTERVAL_S=0`) thì timer ngắt `boGoiY` (`PT10M`, hằng) dọn nhánh.
Mỗi `MOC_SUGGEST_POLL_INTERVAL_S` giây dịch vụ nhận tối đa 5 việc (khóa `PT1M`, chạy cùng lúc), với mỗi việc:

1. lãnh đạo đã chỉ đạo (không còn việc `vbden.chiDao` mở), văn bản không phải văn bản đến, văn bản hạn chế, hoặc đã có
   gợi ý → bỏ qua, không ghi gì;
2. hỏi svc-files `POST /internal/similar-documents` (token tài khoản dịch vụ, hạn `MOC_SUGGEST_TIMEOUT_S`): tối đa 15
   văn bản đến đã giao (`in_progress`/`done`/`archived`) tìm theo trích yếu — svc-files chỉ trả id và điểm, đã loại
   văn bản hạn chế. Hết giờ → dòng `failed/timeout`; không gọi được hay lỗi 5xx → `failed/unavailable`; trợ lý tắt
   (`503 assistant_disabled`), `404`, `409` → bỏ qua. **Không thử lại**: dòng `failed` là kết quả cuối, lãnh đạo giao
   như thường lệ;
3. đọc lần giao chủ trì đầu tiên của các văn bản đủ điểm (`MOC_SUGGEST_MIN_SCORE`; lọc lại văn bản hạn chế), giao thẳng
   một người thì tính phòng của người đó; chỉ giữ phòng có thật và có lãnh đạo phòng đang bật — đúng điều kiện chỉ đạo
   không báo `no_manager`;
4. bỏ phiếu (kNN có trọng số, không cần mô hình): 5 căn cứ điểm cao nhất, mỗi căn cứ một phiếu nặng bằng điểm cho đơn
   vị đã chủ trì nó; hòa thì điểm đơn lẻ cao hơn, rồi id nhỏ hơn. Tin cậy **cao** khi ≥ 3 căn cứ ủng hộ và ≥ 70 % phiếu,
   **vừa** khi ≥ 2 căn cứ và ≥ 50 %, **thấp** khi ≥ 40 %; dưới nữa thì không gợi ý (`none/low_confidence`). Không có
   văn bản tương tự, chưa văn bản nào được giao, hoặc đơn vị không có lãnh đạo phòng → `none` với lý do
   `no_similar`/`no_history`/`no_valid_unit`;
5. hạn: trung vị (thấp) số ngày từ lúc vào sổ (giờ VN) tới hạn của các căn cứ ủng hộ, chỉ tính 1..365 ngày; hạn đề xuất
   = ngày vào sổ + số ngày, sớm nhất là ngày mai, rơi vào thứ Bảy, Chủ nhật (trừ ngày làm bù) hay ngày lễ
   (`MOC_HOLIDAYS`, `MOC_HOLIDAYS_FILE`) thì sang ngày làm việc kế tiếp. Văn bản đã ghi hạn giải quyết thì không gợi ý hạn — hạn trên văn bản thắng thói quen nội bộ;
6. lưu dòng `office.assignment_suggestions` (căn cứ chỉ có id, điểm, đơn vị, số ngày) và một dòng sổ
   `assignment.suggested` trong **cùng một mutation**, bằng vai trò `agent` danh tính `MOC_ASSIGNER_ID` (preset ép thuê
   ước, `agent_id`, `actor_id`, `actor_kind = agent`), mã yêu cầu `goi-y:<id việc>`. `diff` có đúng 9 khóa vô hướng:
   `outcome`, `outcome_reason`, `department_id`, `due_days`, `confidence`, `evidence` (số căn cứ), `candidates`,
   `semantic`, `duration_ms` — không trích yếu, không id căn cứ. CSDL báo `assignment_suggestions_pkey` (lần chạy khác
   đã lưu) hay `assignment_suggestions_sealed` (văn bản hoặc căn cứ vừa thành hạn chế) → bỏ qua.

Lỗi lạ, CSDL hay Flowable không trả lời → báo lỗi việc, Flowable giao lại sau 30 giây; hết lượt thử thì việc vào hàng
việc chết và timer dọn nhánh. Timer bắn lúc dịch vụ đang giữ việc thì báo hoàn thành nhận 404 — chỉ ghi nhật ký. Nhật ký
`office.assign.suggested` mỗi việc: `tenant_id`, `document_id`, `outcome` (`suggested`/`none`/`failed`/`skipped`),
`reason`, `confidence`, `candidates`, `semantic`, `duration_ms` — không có chữ của văn bản. Tác tử chỉ gợi ý; lãnh đạo
dùng hay sửa ở form chỉ đạo, view `office.v_assignment_suggestion_accuracy` đo tỉ lệ giữ gợi ý.

Đo trên lịch sử (`make do-giao-viec`): `python -m svc_workflow.advisor evaluate` đọc stdin
`{"tenant_id": "…", "documents": ["id", …]}`, với mỗi văn bản bỏ phiếu lại như thể nó vừa vào sổ (svc-files đã loại
chính nó — leave-one-out) rồi in stdout `{"rows": [{document_id, actual: {department_id, days}, status, reason,
department_id, ranking, confidence, due_days, evidence, semantic, duration_ms}]}`. Không ghi CSDL, không ghi sổ, không in
chữ văn bản; svc-files từ chối thì dòng `failed` với lý do (`restricted`, `not_found`, `timeout`, `unavailable`…). Chạy
trong container: `docker compose exec -T svc-workflow python -m svc_workflow.advisor evaluate < ids.json`. Số đo
(top-1, gốc so sánh, sai số hạn, độ trễ) và giới hạn của chúng: [`docs/danh-gia-ai.md`](../../docs/danh-gia-ai.md),
mục F4.3.

**Ngày lễ** (`MOC_HOLIDAYS`, #280). Các mục cách nhau bằng dấu phẩy: `MM-DD` lặp hằng năm, `YYYY-MM-DD` một ngày,
`YYYY-MM-DD..YYYY-MM-DD` một khoảng tối đa 31 ngày. Mặc định `01-01,04-30,05-01,09-02` là các ngày lễ dương lịch cố
định ở Điều 112 Bộ luật Lao động 2019. Tết Âm lịch, Giỗ Tổ Hùng Vương, ngày liền kề Quốc khánh, ngày nghỉ bù và thứ
Bảy làm bù đổi theo năm: dịch vụ đọc thêm lịch nghỉ chính thức của nguồn công khai B (`MOC_HOLIDAYS_FILE`, #427), bản
chụp `seed/du-lieu-mo/ngay-nghi-le/ngay-nghi.json` gắn chỉ đọc vào `/app/du-lieu-mo/ngay-nghi-le/`. Tệp có `fixed`
(`MM-DD` hằng năm), `days_off` (khoảng `from`..`to`), `workdays` (thứ Bảy, Chủ nhật làm bù: ngày làm việc, trừ khi
cũng là ngày lễ). Năm tệp chưa có thì người vận hành thêm vào `MOC_HOLIDAYS` theo lịch nghỉ Chính
phủ công bố, rồi tạo lại container svc-workflow. Lấy mới tệp: `python3 scripts/nguon_ngay_nghi_le.py`
([`docs/van-hanh.md`](../../docs/van-hanh.md), mục Lịch nghỉ lễ chính thức). Sai dạng, ngày không có thật, khoảng
ngược hay dài quá 31 ngày — ở biến hay ở tệp — thì dịch vụ dừng lúc khởi động; không có tệp thì chỉ còn
`MOC_HOLIDAYS`. Đổi biến chỉ áp cho gợi ý mới, gợi ý đã
lưu giữ nguyên hạn cũ. Thời hạn từng bước của quy trình (`MOC_SLA_DURATION`) vẫn đếm theo đồng hồ, không trừ ngày nghỉ.

Giới hạn: lịch nghỉ chính thức chỉ có các năm đã công bố (bản chụp hiện tới hết 2027, chưa có Giỗ Tổ 2027) và là
lịch của cán bộ, công chức, viên chức — đơn vị nghỉ khác thì sửa `MOC_HOLIDAYS`; chỉ gợi ý đơn vị chủ trì và
hạn, **không** gợi ý người xử lý (việc của bước phân công); ít dữ liệu, ít đơn vị hợp lệ thì độ chính xác top-1 dễ cao
ảo — đọc kèm số căn cứ và số đơn vị. Ngưỡng `MOC_SUGGEST_MIN_SCORE` chốt theo lần đo đầu trên stack thật.

**Văn bản hạn chế** (F3.7): sau mỗi bước, người phải làm việc đang mở được thêm vào danh sách xem
(`office.document_acl`, đã có tên thì giữ nguyên); người không đọc được văn bản thì `completeTask` từ chối (`403`
`restricted`), `registerIncoming` trả `404` như không có văn bản. Phát hành không được công khai trích yếu (`400`,
`fields.is_public = restricted`). Thông báo chỉ mang nhãn "văn bản hạn chế", không trích yếu, số ký hiệu; nhắc hạn,
leo thang, báo quá hạn chỉ tới người có tên trong danh sách xem và người tạo văn bản.

Vòng nền: deploy `processes/*.bpmn20.xml` khi khởi động (bỏ qua tệp không đổi); đồng bộ danh bạ Keycloak →
`core.users` mỗi `MOC_DIRECTORY_SYNC_INTERVAL_S` giây; mỗi `MOC_RECONCILE_INTERVAL_S` giây đối soát văn bản đã
vào sổ mà chưa có quy trình và báo văn bản đến đã qua hạn giải quyết; nhận việc nhắc hạn của Flowable; mỗi
`MOC_DISPATCH_INTERVAL_S` giây chuyển tiếp liên thông; mỗi `MOC_SUGGEST_POLL_INTERVAL_S` giây nhận việc gợi ý giao việc.

**Nhật ký không có thông tin cá nhân** (F4.4): `_setup_logging` gọi `pii.install_log_redaction`, nên mọi dòng của
dịch vụ, `uvicorn.error` và `uvicorn.access` đi qua bộ lọc `PiiFilter` — số định danh, số điện thoại, email, số tài
khoản thành `[CCCD]`, `[SĐT]`, `[EMAIL]`, `[STK]`, kể cả trong traceback của `office.action.failed`; dòng truy cập bỏ
chuỗi truy vấn. `svc_workflow/pii.py` là bản chép y hệt byte của `svc_files/pii.py` (QĐ-006): sửa ở svc-files rồi chép
sang, `tests/test_pii_copy.py` đỏ ngay khi hai bản lệch nhau. svc-workflow không gọi mô hình nào nên chỉ dùng phần
nhật ký; sổ kiểm toán không che. Đếm chỗ cần che trong một đoạn chữ, không in giá trị: `docker compose exec -T
svc-workflow python -m svc_workflow.pii count < tệp`. Loại, nhãn, giới hạn: README svc-files mục
[Che thông tin cá nhân (F4.4)](../svc-files/README.md#che-thông-tin-cá-nhân-f44).

## Cấu hình

Năm bí mật (khóa Hasura, khóa Actions, mật khẩu Flowable, client secret, khóa Centrifugo) không truyền qua biến môi
trường: khi có `MOC_OPENBAO_ADDR`, lúc khởi động dịch vụ đăng nhập két OpenBao bằng AppRole của riêng mình và đọc
chúng (F3.2, `platform/openbao/start.sh`); không đặt thì đọc thẳng biến môi trường (test, chạy tay). Mật khẩu SMTP,
URL webhook (thường chứa khóa), token của Alertmanager cũng đi qua két, là bí mật tùy chọn: rỗng thì két không có.
Két chưa sẵn sàng thì thử lại tới 60 giây; két từ chối (`400`/`403`/`404`) thì dừng ngay.

| Biến | Mặc định | Ghi chú |
|---|---|---|
| `MOC_OPENBAO_ADDR` | trống | Địa chỉ két, vd `http://openbao:8200`; trống thì không dùng két |
| `MOC_OPENBAO_SECRET_PATH` | `moc/data/svc-workflow` | Đường kv-v2 chứa bí mật của dịch vụ |
| `MOC_OPENBAO_ROLE_ID_FILE`, `MOC_OPENBAO_SECRET_ID_FILE` | `/run/openbao/role_id`, `/run/openbao/secret_id` | Két ghi vào volume chỉ dịch vụ này gắn |
| `HASURA_ADMIN_SECRET` | **bắt buộc** | Gọi Hasura bằng vai trò `service` |
| `MOC_ACTION_SECRET` | **bắt buộc** | Hasura gửi kèm mỗi Action; sai thì 401 |
| `FLOWABLE_ADMIN_PASSWORD` | **bắt buộc** | Tài khoản `rest-admin` của Flowable |
| `MOC_DIRECTORY_CLIENT_SECRET` | **bắt buộc** | Client `svc-workflow` trong realm (quyền `view-users`) |
| `HASURA_URL`, `FLOWABLE_URL`, `MOC_KEYCLOAK_URL` | `http://hasura:8080`, `http://flowable:8080/flowable-rest/service`, `http://keycloak:8080` | Mạng nội bộ |
| `MOC_REALM` | `moc` | |
| `MOC_OFFICE_ENABLED` | `true` | Phần Văn phòng điện tử (#302, `office/api.py`): route `/actions/{name}`, `/ot/notify/{tenant}`, triển khai BPMN trong `MOC_PROCESSES_DIR`, sáu vòng nền của Văn phòng. `false`: dịch vụ vẫn lên với phần chung — đồng bộ danh bạ, thông báo và kênh ngoài, `/healthz`, `/readyz`; route của Văn phòng trả 404, không đọc `MOC_SCHEMAS_DIR`. Để kiểm lõi đứng được một mình (`make demo-tat-van-phong`), không dùng khi vận hành thật |
| `MOC_PROCESSES_DIR` | `/app/processes` | Compose gắn `processes/` vào đây |
| `MOC_SCHEMAS_DIR` | `/app/schemas` | JSON Schema dùng chung với giao diện, dựng sẵn vào image từ `schemas/` ở gốc repo (`docker build --build-context schemas=schemas services/svc-workflow`). Thiếu hoặc hỏng tệp thì dịch vụ dừng khi khởi động |
| `MOC_SLA_DURATION` | `PT24H` | Thời hạn mỗi bước (ISO 8601: ngày, giờ, phút, giây — `P1D`, `PT24H`, `PT1M`). Sai dạng thì dịch vụ dừng khi khởi động. Gắn vào quy trình lúc khởi chạy: đổi giá trị không đổi hạn của văn bản đang xử lý |
| `CENTRIFUGO_API_KEY` | trống | Khóa HTTP API của Centrifugo; trống thì chỉ lưu thông báo, không đẩy realtime |
| `MOC_CENTRIFUGO_URL` | `http://centrifugo:9000` | Cổng nội bộ của Centrifugo (API), không qua APISIX |
| `MOC_DIRECTORY_SYNC_INTERVAL_S`, `MOC_RECONCILE_INTERVAL_S`, `MOC_SLA_POLL_INTERVAL_S` | `15`, `300`, `5` | `0` tắt vòng nền |
| `MOC_DISPATCH_INTERVAL_S` | `30` | Chu kỳ vòng nền liên thông (F3.12); ngắn để lần thử lại đúng hẹn. `0` tắt |
| `MOC_FILES_URL` | `http://svc-files:8000` | Dựng bản phát hành văn bản đi, chép bản phát hành khi liên thông; gọi bằng token tài khoản dịch vụ của client `svc-workflow` |
| `MOC_NGSI_URL` | trống | Context broker NGSI-LD, vd `http://scorpio:9090`; trống thì tắt IT/OT (`/ot/notify` trả 404) |
| `MOC_OT_THRESHOLD` | `35` | Ngưỡng nhiệt độ (°C) của subscription |
| `MOC_OT_NOTIFY_URL` | `http://svc-workflow:8000` | Địa chỉ broker dùng để gọi lại dịch vụ |
| `MOC_OT_SUBSCRIPTION_INTERVAL_S` | `15` | Chu kỳ kiểm subscription; `0` tắt vòng nền |
| `MOC_OT_STALE_MIN` | `10` | Sơ đồ cảm biến: quá chừng ấy phút (1–1440) không có số đo thì cảm biến mang cờ `stale` (mất tín hiệu) |
| `MOC_SUGGEST_ENABLED` | `true` | Tác tử gợi ý giao việc (F4.3). `false`: vẫn nhận việc `moc-goi-y` nhưng hoàn thành ngay, không gọi svc-files, không ghi gì |
| `MOC_SUGGEST_POLL_INTERVAL_S` | `2` | Chu kỳ nhận việc gợi ý; `0` không chạy vòng nền — nhánh gợi ý tự hết sau `PT10M` |
| `MOC_SUGGEST_TIMEOUT_S` | `10` | Hạn gọi svc-files (0–40 giây); cả một việc ≤ hạn + 10 giây, dưới khóa việc `PT1M` |
| `MOC_SUGGEST_MIN_SCORE` | `0.3` | Ngưỡng điểm `_rankingScore` (0..1) để một văn bản tương tự làm căn cứ |
| `MOC_ASSIGNER_ID` | `moc-assigner` | Danh tính tác tử (1–64 ký tự): `actor_id` của dòng sổ, `agent_id` của bảng gợi ý |
| `MOC_HOLIDAYS` | `01-01,04-30,05-01,09-02` | Ngày lễ hạn gợi ý phải tránh, ngoài thứ Bảy, Chủ nhật: `MM-DD` hằng năm, `YYYY-MM-DD`, `YYYY-MM-DD..YYYY-MM-DD` (≤ 31 ngày); trống thì như mặc định. Xem đoạn "Ngày lễ" |
| `MOC_HOLIDAYS_FILE` | `/app/du-lieu-mo/ngay-nghi-le/ngay-nghi.json` | Lịch nghỉ chính thức (nguồn công khai B, #427) cộng vào `MOC_HOLIDAYS`, kể cả thứ Bảy làm bù; rỗng thì tắt, không có tệp thì bỏ qua, tệp hỏng thì dừng lúc khởi động |
| `MOC_SMTP_HOST` | trống | Máy chủ thư; trống thì tắt kênh email |
| `MOC_SMTP_TLS` | `starttls` | `starttls`, `ssl` hoặc `none` (không mã hóa, chỉ cho relay nội bộ như Mailpit, không bao giờ đăng nhập — xem dưới bảng) |
| `MOC_SMTP_PORT` | theo `MOC_SMTP_TLS` | `587` (starttls), `465` (ssl), `25` (none) |
| `MOC_SMTP_USER`, `MOC_SMTP_PASSWORD` | trống | Đăng nhập SMTP khi có `MOC_SMTP_USER`, chỉ qua `starttls` hoặc `ssl`; mật khẩu lấy từ két |
| `MOC_SMTP_FROM` | trống | Người gửi, vd `Signet <signet@ten-mien>`; bắt buộc (có `@`) khi đặt `MOC_SMTP_HOST` |
| `MOC_NOTIFY_WEBHOOK_URL` | trống | URL `http`/`https` nhận tin; lấy từ két; trống thì tắt kênh webhook |
| `MOC_NOTIFY_WEBHOOK_FORMAT` | `json` | `json` (`{"text": …}`: Mattermost, Slack) hoặc `ntfy` |
| `MOC_NOTIFY_EMAIL_KINDS`, `MOC_NOTIFY_WEBHOOK_KINDS` | trống (mọi loại) | Chỉ gửi các loại này, cách nhau bằng dấu phẩy, vd `task.overdue,task.escalated`; loại lạ thì dịch vụ dừng khi khởi động |
| `MOC_SMS_GATEWAY_URL` | trống | Địa chỉ `http(s)://` của SMS Gateway for Android (Local Server), vd `http://192.168.1.50:8080`; trống thì tắt kênh SMS |
| `MOC_SMS_GATEWAY_USER`, `MOC_SMS_GATEWAY_PASSWORD` | trống | Basic Auth hiện trong ứng dụng trên điện thoại; bắt buộc khi đặt URL; mật khẩu lấy từ két |
| `MOC_ZALO_BOT_TOKEN` | trống | Token bot Zalo (nằm trong đường dẫn API, lấy từ két); trống thì tắt kênh Zalo |
| `MOC_ZALO_BOT_URL` | trống | Địa chỉ `https://` mở bot, hiện cho người dùng lúc liên kết |
| `MOC_NOTIFY_SMS_KINDS`, `MOC_NOTIFY_ZALO_KINDS` | trống (mọi loại) | Như `MOC_NOTIFY_EMAIL_KINDS`; SMS tốn tiền, nên đặt vd `task.overdue,task.escalated` |
| `MOC_NOTIFY_INTERVAL_S` | `5` | Chu kỳ vòng nền gửi thông báo ngoài; `0` tắt (dòng chờ nằm nguyên tới khi bật lại) |
| `MOC_PUBLIC_URL` | trống | Địa chỉ trang web cho liên kết trong thư, tin webhook; trống thì không kèm liên kết |
| `MOC_ALERT_TOKEN` | trống | Token của Alertmanager khi gọi `POST /ops/alerts` (16–200 ký tự chữ, số, `.` `_` `~` `+` `/` `-`; `make env` sinh), lấy từ két; trống thì route trả 404 |

`MOC_SMTP_TLS=none` mà có `MOC_SMTP_USER`: svc-workflow không nối máy chủ thư để mật khẩu không đi qua kết nối rõ.
Dịch vụ vẫn chạy, lúc khởi động ghi một dòng `config.warning`; mỗi thư báo lỗi với lý do trong `last_error` và được
thử lại 4 lần (sau 30, 60, 120, 240 giây) rồi thành `failed`. Cấu hình chỉ đọc lúc khởi động: sửa `.env` (chuyển
sang `starttls`/`ssl`, hoặc bỏ `MOC_SMTP_USER` nếu relay không cần đăng nhập) rồi khởi động lại svc-workflow trong
khoảng 7,5 phút đó thì thư đang chờ vẫn đi; quá thời gian đó thư không gửi lại.

## Phát triển

```bash
cd services/svc-workflow
uv venv && uv pip install -r requirements-dev.txt
.venv/bin/python -m pytest          # 461 test đơn vị với Flowable, Hasura, svc-files, Centrifugo, SMTP, webhook giả lập
```

Luồng thật đi qua cả hệ thống: `make up && make seed && make smoke` ở thư mục gốc. Đổi phụ thuộc: sửa
`pyproject.toml` rồi sinh lại tệp khóa như ở `services/svc-files/README.md`.
