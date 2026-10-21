# Truy vấn và thao tác ghi theo vai trò

> Tệp sinh tự động bằng `make api-docs` từ hệ thống đang chạy, không sửa tay. Cách gọi API: [README](README.md).

Mỗi vai trò thấy một schema GraphQL riêng ở `POST /v1/graphql`, lấy qua cổng APISIX bằng token của tài khoản
mẫu trong bảng dưới. Trường không có trong schema của vai trò thì gọi sẽ bị Hasura báo lỗi `validation-failed`.
Ngoài ra Hasura còn lọc theo dòng (cùng đơn vị, cùng phòng, văn bản hạn chế) và theo cột; quy tắc ở
[`db/README.md`](../../db/README.md#vai-trò).

| Vai trò | Tài khoản mẫu | Truy vấn | Thao tác ghi | Schema |
|---|---|--:|--:|---|
| `clerk` (văn thư) | `vanthu` | 35 | 8 | [`graphql/clerk.graphql`](graphql/clerk.graphql) |
| `staff` (chuyên viên) | `chuyenviendt` | 28 | 23 | [`graphql/staff.graphql`](graphql/staff.graphql) |
| `manager` (lãnh đạo phòng) | `totruongdt` | 28 | 13 | [`graphql/manager.graphql`](graphql/manager.graphql) |
| `director` (lãnh đạo đơn vị) | `truongkhoa` | 44 | 6 | [`graphql/director.graphql`](graphql/director.graphql) |
| `tenant_admin` (quản trị đơn vị) | `quantri` | 18 | 11 | [`graphql/tenant_admin.graphql`](graphql/tenant_admin.graphql) |

## Truy vấn (`query`)

| Trường | `clerk` | `staff` | `manager` | `director` | `tenant_admin` |
|---|:-:|:-:|:-:|:-:|:-:|
| `core_audit_anchors` |  |  |  | ✓ | ✓ |
| `core_audit_anchors_aggregate` |  |  |  | ✓ | ✓ |
| `core_audit_log` |  |  |  | ✓ | ✓ |
| `core_audit_log_aggregate` |  |  |  | ✓ | ✓ |
| `core_audit_log_by_pk` |  |  |  | ✓ | ✓ |
| `core_files` | ✓ | ✓ | ✓ | ✓ |  |
| `core_files_by_pk` | ✓ | ✓ | ✓ | ✓ |  |
| `core_lineage_events` | ✓ |  |  | ✓ |  |
| `core_lineage_events_aggregate` | ✓ |  |  | ✓ |  |
| `core_lineage_events_by_pk` | ✓ |  |  | ✓ |  |
| `core_notifications` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `core_notifications_aggregate` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `core_notifications_by_pk` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `core_tenants` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `core_tenants_by_pk` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `core_users` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `core_users_by_pk` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `myTasks` | ✓ | ✓ | ✓ | ✓ |  |
| `office_assignments` | ✓ | ✓ | ✓ | ✓ |  |
| `office_assignments_by_pk` | ✓ | ✓ | ✓ | ✓ |  |
| `office_case_file_documents` | ✓ | ✓ | ✓ | ✓ |  |
| `office_case_file_documents_by_pk` | ✓ | ✓ | ✓ | ✓ |  |
| `office_case_files` | ✓ | ✓ | ✓ | ✓ |  |
| `office_case_files_by_pk` | ✓ | ✓ | ✓ | ✓ |  |
| `office_departments` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `office_departments_by_pk` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `office_document_acl` | ✓ |  |  | ✓ |  |
| `office_document_acl_by_pk` | ✓ |  |  | ✓ |  |
| `office_document_events` | ✓ | ✓ | ✓ | ✓ |  |
| `office_document_events_by_pk` | ✓ | ✓ | ✓ | ✓ |  |
| `office_document_files` | ✓ | ✓ | ✓ | ✓ |  |
| `office_document_files_by_pk` | ✓ | ✓ | ✓ | ✓ |  |
| `office_document_history` | ✓ | ✓ | ✓ | ✓ |  |
| `office_document_types` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `office_document_types_by_pk` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `office_documents` | ✓ | ✓ | ✓ | ✓ |  |
| `office_documents_aggregate` | ✓ | ✓ | ✓ | ✓ |  |
| `office_documents_by_pk` | ✓ | ✓ | ✓ | ✓ |  |
| `office_registers` | ✓ |  |  | ✓ | ✓ |
| `office_registers_by_pk` | ✓ |  |  | ✓ | ✓ |
| `office_v_document_counts` |  |  |  | ✓ |  |
| `office_v_outgoing_by_month` |  |  |  | ✓ |  |
| `office_v_overdue_by_department` |  |  |  | ✓ |  |
| `office_v_processing_time` |  |  |  | ✓ |  |

## Thao tác ghi (`mutation`)

| Trường | `clerk` | `staff` | `manager` | `director` | `tenant_admin` |
|---|:-:|:-:|:-:|:-:|:-:|
| `completeTask` | ✓ | ✓ | ✓ | ✓ |  |
| `delete_office_case_file_documents` |  | ✓ | ✓ |  |  |
| `delete_office_case_file_documents_by_pk` |  | ✓ | ✓ |  |  |
| `delete_office_document_files` |  | ✓ |  |  |  |
| `delete_office_document_files_by_pk` |  | ✓ |  |  |  |
| `insert_office_case_file_documents` |  | ✓ | ✓ |  |  |
| `insert_office_case_file_documents_one` |  | ✓ | ✓ |  |  |
| `insert_office_case_files` |  | ✓ | ✓ |  |  |
| `insert_office_case_files_one` |  | ✓ | ✓ |  |  |
| `insert_office_departments` |  |  |  |  | ✓ |
| `insert_office_departments_one` |  |  |  |  | ✓ |
| `insert_office_document_files` |  | ✓ |  |  |  |
| `insert_office_document_files_one` |  | ✓ |  |  |  |
| `insert_office_documents` |  | ✓ |  |  |  |
| `insert_office_documents_one` |  | ✓ |  |  |  |
| `office_grant_document_access` | ✓ |  |  | ✓ |  |
| `office_revoke_document_access` | ✓ |  |  | ✓ |  |
| `receiveIncoming` | ✓ |  |  |  |  |
| `registerIncoming` | ✓ |  |  |  |  |
| `submitOutgoing` |  | ✓ |  |  |  |
| `update_core_notifications` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `update_core_notifications_by_pk` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `update_core_notifications_many` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `update_core_tenants` |  |  |  |  | ✓ |
| `update_core_tenants_by_pk` |  |  |  |  | ✓ |
| `update_core_tenants_many` |  |  |  |  | ✓ |
| `update_office_case_files` |  | ✓ | ✓ |  |  |
| `update_office_case_files_by_pk` |  | ✓ | ✓ |  |  |
| `update_office_case_files_many` |  | ✓ | ✓ |  |  |
| `update_office_departments` |  |  |  |  | ✓ |
| `update_office_departments_by_pk` |  |  |  |  | ✓ |
| `update_office_departments_many` |  |  |  |  | ✓ |
| `update_office_documents` |  | ✓ |  |  |  |
| `update_office_documents_by_pk` |  | ✓ |  |  |  |
| `update_office_documents_many` |  | ✓ |  |  |  |

`subscription` có trong schema của Hasura nhưng chưa gọi được qua cổng (chưa mở WebSocket), nên không liệt kê.
