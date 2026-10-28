# API REST của `svc-workflow`

> Tệp sinh tự động bằng `make api-docs` từ [`openapi/svc-workflow.json`](openapi/svc-workflow.json), không sửa
> tay. Lấy token và gọi API: [README](README.md).

Hasura Actions của Văn phòng điện tử: API nội bộ, chỉ Hasura gọi, không qua cổng APISIX; ứng dụng gọi các Action này
bằng GraphQL. Riêng /api/workflow/{app}/… (quy trình của ứng dụng cắm bằng manifest) đi qua cổng, cần token của client
app-<tên> (docs/api/README.md).

OpenAPI 3.1.0, 10 thao tác:

| Thao tác | Tóm tắt |
|---|---|
| `POST /ot/notify/{tenant}` | Nhận thông báo của subscription NGSI-LD: cảm biến vượt ngưỡng → dự thảo báo cáo sự cố (F3.10) |
| `POST /actions/{name}` | Chạy một Hasura Action: receiveIncoming, registerIncoming, submitOutgoing, myTasks, completeTask, otSensorMap |
| `GET /api/workflow/{app}/forms/{form_key}` | JSON Schema của một form, đúng tệp manifest khai |
| `POST /api/workflow/{app}/processes/{process_key}` | Bắt đầu quy trình với dữ liệu form bắt đầu |
| `GET /api/workflow/{app}/processes` | Đơn người này đã gửi qua ứng dụng, mới nhất trước |
| `GET /api/workflow/{app}/tasks` | Việc của ứng dụng giao cho người này hoặc nhóm của người này, cũ nhất trước |
| `POST /api/workflow/{app}/tasks/{task_id}` | Hoàn thành một việc với dữ liệu form của việc |
| `POST /actions/channels/{name}` | Kênh thông báo của chính người gọi (SMS, Zalo): myChannels, setMyChannel |
| `POST /ops/alerts` | Nhận cảnh báo của Alertmanager → thông báo ops.alert cho quản trị đơn vị (F3.13) |
| `POST /actions/tu-dong/{name}` | Robot của flow tự động hóa báo người trong đơn vị theo vai trò: notifyFromFlow (#366) |

## `POST /ot/notify/{tenant}`

Nhận thông báo của subscription NGSI-LD: cảm biến vượt ngưỡng → dự thảo báo cáo sự cố (F3.10)

Chỉ context broker gọi, kèm header X-Moc-OT-Token của đơn vị (broker nhận token khi svc-workflow tạo subscription). Thân
là Notification NGSI-LD (format normalized).

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `tenant` | đường dẫn | ✓ | `string` |  |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 204 | Thành công |  |
| 401 | Thiếu hoặc sai token của đơn vị |  |
| 404 | Chưa cấu hình MOC_NGSI_URL |  |
| 503 | Chưa ghi được CSDL, broker sẽ báo lỗi gửi |  |
| 422 | Dữ liệu gửi lên sai kiểu, thiếu trường | `application/json` `HTTPValidationError` |

## `POST /actions/{name}`

Chạy một Hasura Action: receiveIncoming, registerIncoming, submitOutgoing, myTasks, completeTask, otSensorMap

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `name` | đường dẫn | ✓ | `string` |  |
| `X-Moc-Action-Secret` | header | ✓ | `string` | Bí mật chung giữa Hasura và svc-workflow (MOC_ACTION_SECRET) |

Thân yêu cầu `application/json`:

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `action` | `object` | ✓ |  |
| `input` | `object` | ✓ | Đối số của Action, khai trong db/metadata/actions.graphql |
| `session_variables` | `object (giá trị string)` | ✓ | Biến phiên Hasura lấy từ JWT đã kiểm: x-hasura-role, x-hasura-user-id, x-hasura-tenant-id, x-hasura-department-id |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Kết quả của Action, đúng kiểu trả về khai trong db/metadata/actions.graphql | `application/json` |
| 422 | Dữ liệu gửi lên sai kiểu, thiếu trường | `application/json` `HTTPValidationError` |
| 400 | Sai định dạng Action; dữ liệu văn bản đến, kết quả hoặc dữ liệu của việc không hợp lệ | `application/json` `object` |
| 401 | Thiếu hoặc sai X-Moc-Action-Secret: không phải Hasura gọi | `application/json` `object` |
| 403 | Vai trò không được dùng Action này, hoặc việc không giao cho người gọi | `application/json` `object` |
| 404 | Không có văn bản hoặc việc | `application/json` `object` |
| 409 | Văn bản đến trùng văn bản đã tiếp nhận, văn bản sai trạng thái, việc vừa có người khác nhận, hoặc CSDL từ chối | `application/json` `object` |
| 500 | Lỗi không mong đợi; câu trả về có mã yêu cầu để tra nhật ký | `application/json` `object` |
| 503 | Chưa gọi được Flowable hoặc CSDL, thử lại sau | `application/json` `object` |

## `GET /api/workflow/{app}/forms/{form_key}`

JSON Schema của một form, đúng tệp manifest khai

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `app` | đường dẫn | ✓ | `string` |  |
| `form_key` | đường dẫn | ✓ | `string` |  |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Thành công | `application/json` `object` |
| 401 | Thiếu hoặc sai token |  |
| 403 | Token không phải của client app-<tên>, hoặc tài khoản chưa gán đơn vị |  |
| 404 | Ứng dụng chưa cài, đã gỡ hoặc không có form này |  |
| 503 | Chưa gọi được Flowable hoặc Keycloak, thử lại sau |  |
| 422 | Dữ liệu gửi lên sai kiểu, thiếu trường | `application/json` `HTTPValidationError` |

## `POST /api/workflow/{app}/processes/{process_key}`

Bắt đầu quy trình với dữ liệu form bắt đầu

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `app` | đường dẫn | ✓ | `string` |  |
| `process_key` | đường dẫn | ✓ | `string` |  |

Thân yêu cầu `application/json`:

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `data` | `object` | ✓ | Dữ liệu form: tên trường là tên biến của quy trình |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 201 | Thành công | `application/json` `object (giá trị string)` |
| 401 | Thiếu hoặc sai token |  |
| 403 | Token không phải của client app-<tên>, hoặc tài khoản chưa gán đơn vị |  |
| 404 | Ứng dụng chưa cài, đã gỡ hoặc không có quy trình này |  |
| 503 | Chưa gọi được Flowable hoặc Keycloak, thử lại sau |  |
| 422 | Dữ liệu chưa đúng form: {"errors": {trường: mã}} (schemas/README.md, x-moc-range) | `application/json` `object` |
| 413 | Thân yêu cầu lớn quá 64 KB |  |

## `GET /api/workflow/{app}/processes`

Đơn người này đã gửi qua ứng dụng, mới nhất trước

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `app` | đường dẫn | ✓ | `string` |  |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Thành công | `application/json` `object[]` |
| 401 | Thiếu hoặc sai token |  |
| 403 | Token không phải của client app-<tên>, hoặc tài khoản chưa gán đơn vị |  |
| 404 | Ứng dụng chưa cài hoặc đã gỡ |  |
| 503 | Chưa gọi được Flowable hoặc Keycloak, thử lại sau |  |
| 422 | Dữ liệu gửi lên sai kiểu, thiếu trường | `application/json` `HTTPValidationError` |

## `GET /api/workflow/{app}/tasks`

Việc của ứng dụng giao cho người này hoặc nhóm của người này, cũ nhất trước

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `app` | đường dẫn | ✓ | `string` |  |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Thành công | `application/json` `object[]` |
| 401 | Thiếu hoặc sai token |  |
| 403 | Token không phải của client app-<tên>, hoặc tài khoản chưa gán đơn vị |  |
| 404 | Ứng dụng chưa cài hoặc đã gỡ |  |
| 503 | Chưa gọi được Flowable hoặc Keycloak, thử lại sau |  |
| 422 | Dữ liệu gửi lên sai kiểu, thiếu trường | `application/json` `HTTPValidationError` |

## `POST /api/workflow/{app}/tasks/{task_id}`

Hoàn thành một việc với dữ liệu form của việc

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `app` | đường dẫn | ✓ | `string` |  |
| `task_id` | đường dẫn | ✓ | `string` |  |

Thân yêu cầu `application/json`:

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `data` | `object` | ✓ | Dữ liệu form: tên trường là tên biến của quy trình |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 204 | Thành công |  |
| 401 | Thiếu hoặc sai token |  |
| 403 | Token không phải của client app-<tên>, hoặc tài khoản chưa gán đơn vị |  |
| 404 | Ứng dụng đã gỡ; việc không còn hoặc không thuộc người này |  |
| 503 | Chưa gọi được Flowable hoặc Keycloak, thử lại sau |  |
| 409 | Việc vừa có người khác nhận |  |
| 422 | Dữ liệu chưa đúng form: {"errors": {trường: mã}} (schemas/README.md, x-moc-range) | `application/json` `object` |
| 413 | Thân yêu cầu lớn quá 64 KB |  |

## `POST /actions/channels/{name}`

Kênh thông báo của chính người gọi (SMS, Zalo): myChannels, setMyChannel

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `name` | đường dẫn | ✓ | `string` |  |
| `X-Moc-Action-Secret` | header | ✓ | `string` | Bí mật chung giữa Hasura và svc-workflow (MOC_ACTION_SECRET) |

Thân yêu cầu `application/json`:

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `action` | `object` | ✓ |  |
| `input` | `object` | ✓ | Đối số của Action, khai trong db/metadata/actions.graphql |
| `session_variables` | `object (giá trị string)` | ✓ | Biến phiên Hasura lấy từ JWT đã kiểm: x-hasura-role, x-hasura-user-id, x-hasura-tenant-id, x-hasura-department-id |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | Danh sách MyChannel: mỗi kênh cá nhân bản cài đã cấu hình một dòng (db/metadata/actions.graphql) | `application/json` |
| 422 | Dữ liệu gửi lên sai kiểu, thiếu trường | `application/json` `HTTPValidationError` |
| 400 | Sai định dạng Action, hoặc kênh chưa được cấu hình trên bản cài | `application/json` `object` |
| 401 | Thiếu hoặc sai X-Moc-Action-Secret: không phải Hasura gọi | `application/json` `object` |
| 403 | Vai trò không được dùng Action này | `application/json` `object` |
| 409 | Tài khoản chưa có trong danh bạ của đơn vị, hoặc chưa có số điện thoại để bật SMS | `application/json` `object` |
| 500 | Lỗi không mong đợi; câu trả về có mã yêu cầu để tra nhật ký | `application/json` `object` |
| 503 | Chưa gọi được CSDL, thử lại sau | `application/json` `object` |

## `POST /ops/alerts`

Nhận cảnh báo của Alertmanager → thông báo ops.alert cho quản trị đơn vị (F3.13)

Chỉ Alertmanager gọi (receiver webhook trong platform/monitoring/alertmanager.yml), kèm Authorization: Bearer
MOC_ALERT_TOKEN. Thân là webhook phiên bản 4 của Alertmanager; mỗi cảnh báo firing/resolved thành một thông báo cho mọi
người dùng vai trò tenant_admin, gửi lại không sinh thông báo thứ hai.

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 204 | Thành công |  |
| 400 | Thân không phải webhook của Alertmanager |  |
| 401 | Thiếu hoặc sai token |  |
| 404 | Chưa đặt MOC_ALERT_TOKEN |  |
| 503 | Chưa ghi được CSDL, Alertmanager sẽ gửi lại |  |

## `POST /actions/tu-dong/{name}`

Robot của flow tự động hóa báo người trong đơn vị theo vai trò: notifyFromFlow (#366)

Tham số:

| Tên | Ở | Bắt buộc | Kiểu | Mô tả |
|---|---|:-:|---|---|
| `name` | đường dẫn | ✓ | `string` |  |
| `X-Moc-Action-Secret` | header | ✓ | `string` | Bí mật chung giữa Hasura và svc-workflow (MOC_ACTION_SECRET) |

Thân yêu cầu `application/json`:

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `action` | `object` | ✓ |  |
| `input` | `object` | ✓ | Đối số của Action, khai trong db/metadata/actions.graphql |
| `session_variables` | `object (giá trị string)` | ✓ | Biến phiên Hasura lấy từ JWT đã kiểm: x-hasura-role, x-hasura-user-id, x-hasura-tenant-id, x-hasura-department-id |

Trả về:

| Mã | Nghĩa | Nội dung |
|---|---|---|
| 200 | NotifyFromFlowOutput {sent}: số người vừa nhận thông báo; người đã có thông báo cùng khóa không tính (db/metadata/actions.graphql) | `application/json` |
| 422 | Gửi kèm văn bản cho vai trò có thể không xem được nó: chỉ director, clerk (extensions.fields.roles = document_readers_only) | `application/json` `object` |
| 400 | Sai định dạng Action, hoặc đối số sai: extensions.fields chỉ trường sai và mã lỗi | `application/json` `object` |
| 401 | Thiếu hoặc sai X-Moc-Action-Secret: không phải Hasura gọi | `application/json` `object` |
| 403 | Không phải robot (vai trò tu_dong), hoặc văn bản hạn chế | `application/json` `object` |
| 404 | Không có văn bản này trong đơn vị của robot | `application/json` `object` |
| 500 | Lỗi không mong đợi; câu trả về có mã yêu cầu để tra nhật ký | `application/json` `object` |
| 503 | Chưa gọi được CSDL, thử lại sau | `application/json` `object` |

## Kiểu dữ liệu

Các kiểu mà thân yêu cầu và nội dung trả về ở trên nhắc tới.

### `HTTPValidationError`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `detail` | `ValidationError[]` |  |  |

### `ValidationError`

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|:-:|---|
| `loc` | `string hoặc integer[]` | ✓ |  |
| `msg` | `string` | ✓ |  |
| `type` | `string` | ✓ |  |
| `input` | `any` |  |  |
| `ctx` | `object` |  |  |
