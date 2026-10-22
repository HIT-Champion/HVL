# svc-workflow

Xử lý **Hasura Actions** của Văn phòng điện tử và nối PostgreSQL (qua Hasura) với Flowable (BPMN). Ứng dụng
chỉ nói chuyện với GraphQL; thao tác nghiệp vụ là Action, Hasura chuyển sang đây kèm biến phiên lấy từ JWT —
thuê ước, người dùng, vai trò không do client tự khai. Flowable giữ trạng thái quy trình (đang ở bước nào, ai
phải làm); PostgreSQL giữ dữ liệu nghiệp vụ ([`docs/ke-hoach-phat-trien.md`](../../docs/ke-hoach-phat-trien.md) §2.1).
Chủ: issue #15.

| Action | Vai trò | Làm gì |
|---|---|---|
| `receiveIncoming(data)` | `clerk` | Tiếp nhận văn bản đến: kiểm lại `data` theo `schemas/van-ban-den.json` (poka-yoke lớp 2, F2.2), tra loại văn bản, tệp, văn bản trùng, rồi ghi văn bản `received`. Lỗi trả từng trường trong `extensions.fields` (`schemas/README.md`) |
| `registerIncoming(documentId)` | `clerk` | Vào sổ (hàm `office.register_incoming`, một giao dịch) → khởi chạy `van-ban-den` |
| `submitOutgoing(documentId, signerId)` | `staff` | Người soạn trình dự thảo → khởi chạy `van-ban-di`, hoặc trình lại sau khi bị trả lại. Có đơn vị nhận trong hệ thống (`recipient_tenant_ids`) thì kiểm: có thật, không phải đơn vị mình, văn bản không hạn chế (`400`, `fields.recipient_tenant_ids` = `unknown` / `self` / `restricted`) |
| `myTasks` | người dùng nghiệp vụ | Việc của người gọi và của nhóm vai trò của họ, khẩn trước |
| `completeTask(taskId, outcome, data)` | người được giao | Kiểm quyền và dữ liệu → nhận việc → ghi CSDL (một giao dịch) → hoàn thành trong Flowable. Phát hành văn bản đi (`vbdi.phatHanh`): cấp số đi (hàm `office.number_outgoing`) → `svc-files` dựng PDF có mã QR → ghi băm, `issued` → liên thông tới đơn vị nhận trong hệ thống |

Chi tiết từng loại việc, dữ liệu và nhóm ứng viên: [`docs/mo-hinh-du-lieu.md`](../../docs/mo-hinh-du-lieu.md) §4.
Hợp đồng HTTP giữa Hasura và dịch vụ (thân yêu cầu, mã lỗi): [`docs/api/openapi/svc-workflow.json`](../../docs/api/openapi/svc-workflow.json),
xuất bằng `make api-docs`.

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
(khóa thông báo theo dự thảo và ngày). Vòng nền còn giữ một subscription "neo" tạm dừng ở tenant mặc định
(`urn:ngsi-ld:Subscription:moc-ot-context`): Scorpio 6.0.2 cất ngữ cảnh JSON-LD của subscription trong CSDL của tenant
nhưng lúc gửi thông báo lại tìm ở tenant mặc định — thiếu neo thì broker bỏ mọi thông báo (nhật ký Scorpio: "Mutiny had
to drop … ResponseException").

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
   = ngày vào sổ + số ngày, rơi vào thứ Bảy/Chủ nhật thì sang thứ Hai, sớm nhất là ngày mai. Văn bản đã ghi hạn giải
   quyết thì không gợi ý hạn — hạn trên văn bản thắng thói quen nội bộ;
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
trong container: `docker compose exec -T svc-workflow python -m svc_workflow.advisor evaluate < ids.json`.

Giới hạn: chưa xét ngày lễ (chưa có lịch nghỉ, chỉ tránh thứ Bảy/Chủ nhật); chỉ gợi ý đơn vị chủ trì và hạn, **không**
gợi ý người xử lý (việc của bước phân công); ít dữ liệu, ít đơn vị hợp lệ thì độ chính xác top-1 dễ cao ảo — đọc kèm
số căn cứ và số đơn vị. Ngưỡng `MOC_SUGGEST_MIN_SCORE` chốt theo lần đo đầu trên stack thật.

**Văn bản hạn chế** (F3.7): sau mỗi bước, người phải làm việc đang mở được thêm vào danh sách xem
(`office.document_acl`, đã có tên thì giữ nguyên); người không đọc được văn bản thì `completeTask` từ chối (`403`
`restricted`), `registerIncoming` trả `404` như không có văn bản. Phát hành không được công khai trích yếu (`400`,
`fields.is_public = restricted`). Thông báo chỉ mang nhãn "văn bản hạn chế", không trích yếu, số ký hiệu; nhắc hạn,
leo thang, báo quá hạn chỉ tới người có tên trong danh sách xem và người tạo văn bản.

Vòng nền: deploy `processes/*.bpmn20.xml` khi khởi động (bỏ qua tệp không đổi); đồng bộ danh bạ Keycloak →
`core.users` mỗi `MOC_DIRECTORY_SYNC_INTERVAL_S` giây; mỗi `MOC_RECONCILE_INTERVAL_S` giây đối soát văn bản đã
vào sổ mà chưa có quy trình và báo văn bản đến đã qua hạn giải quyết; nhận việc nhắc hạn của Flowable; mỗi
`MOC_DISPATCH_INTERVAL_S` giây chuyển tiếp liên thông; mỗi `MOC_SUGGEST_POLL_INTERVAL_S` giây nhận việc gợi ý giao việc.

## Cấu hình

Năm bí mật (khóa Hasura, khóa Actions, mật khẩu Flowable, client secret, khóa Centrifugo) không truyền qua biến môi
trường: khi có `MOC_OPENBAO_ADDR`, lúc khởi động dịch vụ đăng nhập két OpenBao bằng AppRole của riêng mình và đọc
chúng (F3.2, `openbao/start.sh`); không đặt thì đọc thẳng biến môi trường (test, chạy tay). Két chưa sẵn sàng thì
thử lại tới 60 giây; két từ chối (`400`/`403`/`404`) thì dừng ngay.

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
| `MOC_SUGGEST_ENABLED` | `true` | Tác tử gợi ý giao việc (F4.3). `false`: vẫn nhận việc `moc-goi-y` nhưng hoàn thành ngay, không gọi svc-files, không ghi gì |
| `MOC_SUGGEST_POLL_INTERVAL_S` | `2` | Chu kỳ nhận việc gợi ý; `0` không chạy vòng nền — nhánh gợi ý tự hết sau `PT10M` |
| `MOC_SUGGEST_TIMEOUT_S` | `10` | Hạn gọi svc-files (0–40 giây); cả một việc ≤ hạn + 10 giây, dưới khóa việc `PT1M` |
| `MOC_SUGGEST_MIN_SCORE` | `0.3` | Ngưỡng điểm `_rankingScore` (0..1) để một văn bản tương tự làm căn cứ |
| `MOC_ASSIGNER_ID` | `moc-assigner` | Danh tính tác tử (1–64 ký tự): `actor_id` của dòng sổ, `agent_id` của bảng gợi ý |

## Phát triển

```bash
cd services/svc-workflow
uv venv && uv pip install -r requirements-dev.txt
.venv/bin/python -m pytest          # 396 test đơn vị với Flowable, Hasura, svc-files, Centrifugo giả lập
```

Luồng thật đi qua cả hệ thống: `make up && make seed && make smoke` ở thư mục gốc. Đổi phụ thuộc: sửa
`pyproject.toml` rồi sinh lại tệp khóa như ở `services/svc-files/README.md`.
