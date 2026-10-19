# svc-workflow

Xử lý **Hasura Actions** của Văn phòng điện tử và nối PostgreSQL (qua Hasura) với Flowable (BPMN). Ứng dụng
chỉ nói chuyện với GraphQL; thao tác nghiệp vụ là Action, Hasura chuyển sang đây kèm biến phiên lấy từ JWT —
thuê ước, người dùng, vai trò không do client tự khai. Flowable giữ trạng thái quy trình (đang ở bước nào, ai
phải làm); PostgreSQL giữ dữ liệu nghiệp vụ ([`docs/ke-hoach-phat-trien.md`](../../docs/ke-hoach-phat-trien.md) §2.1).
Chủ: issue #15.

| Action | Vai trò | Làm gì |
|---|---|---|
| `registerIncoming(documentId)` | `clerk` | Vào sổ (hàm `office.register_incoming`, một giao dịch) → khởi chạy `van-ban-den` |
| `myTasks` | người dùng nghiệp vụ | Việc của người gọi và của nhóm vai trò của họ, khẩn trước |
| `completeTask(taskId, outcome, data)` | người được giao | Kiểm quyền và dữ liệu → nhận việc → ghi CSDL (một giao dịch) → hoàn thành trong Flowable |

Chi tiết từng loại việc, dữ liệu và nhóm ứng viên: [`docs/mo-hinh-du-lieu.md`](../../docs/mo-hinh-du-lieu.md) §4.
Hợp đồng HTTP giữa Hasura và dịch vụ (thân yêu cầu, mã lỗi): [`docs/api/openapi/svc-workflow.json`](../../docs/api/openapi/svc-workflow.json),
xuất bằng `make api-docs`.

Vòng nền: deploy `processes/*.bpmn20.xml` khi khởi động (bỏ qua tệp không đổi); đồng bộ danh bạ Keycloak →
`core.users` mỗi `MOC_DIRECTORY_SYNC_INTERVAL_S` giây; đối soát văn bản đã vào sổ mà chưa có quy trình mỗi
`MOC_RECONCILE_INTERVAL_S` giây.

## Cấu hình

| Biến | Mặc định | Ghi chú |
|---|---|---|
| `HASURA_ADMIN_SECRET` | **bắt buộc** | Gọi Hasura bằng vai trò `service` |
| `MOC_ACTION_SECRET` | **bắt buộc** | Hasura gửi kèm mỗi Action; sai thì 401 |
| `FLOWABLE_ADMIN_PASSWORD` | **bắt buộc** | Tài khoản `rest-admin` của Flowable |
| `MOC_DIRECTORY_CLIENT_SECRET` | **bắt buộc** | Client `svc-workflow` trong realm (quyền `view-users`) |
| `HASURA_URL`, `FLOWABLE_URL`, `MOC_KEYCLOAK_URL` | `http://hasura:8080`, `http://flowable:8080/flowable-rest/service`, `http://keycloak:8080` | Mạng nội bộ |
| `MOC_REALM` | `moc` | |
| `MOC_PROCESSES_DIR` | `/app/processes` | Compose gắn `processes/` vào đây |
| `MOC_SLA_DURATION` | `PT24H` | Thời hạn mỗi bước (ISO 8601) |
| `MOC_DIRECTORY_SYNC_INTERVAL_S`, `MOC_RECONCILE_INTERVAL_S` | `15`, `300` | `0` tắt vòng nền |

## Phát triển

```bash
cd services/svc-workflow
uv venv && uv pip install -r requirements-dev.txt
.venv/bin/python -m pytest          # 36 test đơn vị với Flowable, Hasura giả lập
```

Luồng thật đi qua cả hệ thống: `make up && make seed && make smoke` ở thư mục gốc. Đổi phụ thuộc: sửa
`pyproject.toml` rồi sinh lại tệp khóa như ở `services/svc-files/README.md`.
