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
| `submitOutgoing(documentId, signerId)` | `staff` | Người soạn trình dự thảo → khởi chạy `van-ban-di`, hoặc trình lại sau khi bị trả lại |
| `myTasks` | người dùng nghiệp vụ | Việc của người gọi và của nhóm vai trò của họ, khẩn trước |
| `completeTask(taskId, outcome, data)` | người được giao | Kiểm quyền và dữ liệu → nhận việc → ghi CSDL (một giao dịch) → hoàn thành trong Flowable. Phát hành văn bản đi (`vbdi.phatHanh`): cấp số đi (hàm `office.number_outgoing`) → `svc-files` dựng PDF có mã QR → ghi băm, `issued` |

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

**Văn bản hạn chế** (F3.7): sau mỗi bước, người phải làm việc đang mở được thêm vào danh sách xem
(`office.document_acl`, đã có tên thì giữ nguyên); người không đọc được văn bản thì `completeTask` từ chối (`403`
`restricted`), `registerIncoming` trả `404` như không có văn bản. Phát hành không được công khai trích yếu (`400`,
`fields.is_public = restricted`). Thông báo chỉ mang nhãn "văn bản hạn chế", không trích yếu, số ký hiệu; nhắc hạn,
leo thang, báo quá hạn chỉ tới người có tên trong danh sách xem và người tạo văn bản.

Vòng nền: deploy `processes/*.bpmn20.xml` khi khởi động (bỏ qua tệp không đổi); đồng bộ danh bạ Keycloak →
`core.users` mỗi `MOC_DIRECTORY_SYNC_INTERVAL_S` giây; mỗi `MOC_RECONCILE_INTERVAL_S` giây đối soát văn bản đã
vào sổ mà chưa có quy trình và báo văn bản đến đã qua hạn giải quyết; nhận việc nhắc hạn của Flowable.

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
| `MOC_FILES_URL` | `http://svc-files:8000` | Dựng bản phát hành văn bản đi; gọi bằng token tài khoản dịch vụ của client `svc-workflow` |
| `MOC_NGSI_URL` | trống | Context broker NGSI-LD, vd `http://scorpio:9090`; trống thì tắt IT/OT (`/ot/notify` trả 404) |
| `MOC_OT_THRESHOLD` | `35` | Ngưỡng nhiệt độ (°C) của subscription |
| `MOC_OT_NOTIFY_URL` | `http://svc-workflow:8000` | Địa chỉ broker dùng để gọi lại dịch vụ |
| `MOC_OT_SUBSCRIPTION_INTERVAL_S` | `15` | Chu kỳ kiểm subscription; `0` tắt vòng nền |

## Phát triển

```bash
cd services/svc-workflow
uv venv && uv pip install -r requirements-dev.txt
.venv/bin/python -m pytest          # 207 test đơn vị với Flowable, Hasura, Centrifugo giả lập
```

Luồng thật đi qua cả hệ thống: `make up && make seed && make smoke` ở thư mục gốc. Đổi phụ thuộc: sửa
`pyproject.toml` rồi sinh lại tệp khóa như ở `services/svc-files/README.md`.
