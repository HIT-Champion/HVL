-- Copyright 2026 Signet Team
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.
--
-- SPDX-License-Identifier: Apache-2.0

-- Lịch sử thay đổi của văn bản (F3.5, tab "Lịch sử" trên trang văn bản): các dòng sổ kiểm toán về chính văn bản, tệp
-- gắn với nó (entity_id "<văn bản>/<tệp>"), các lần giao việc, lần đưa vào hồ sơ — cho mọi người đọc được văn bản,
-- không riêng lãnh đạo. Như màn Sổ kiểm toán, chỉ có `overview` (giá trị của cột không chứa nội dung, hàm
-- core.audit_overview): văn bản hạn chế cũng không lộ trích yếu, tên tệp qua lịch sử. Không có prev_hash/hash — kiểm
-- chuỗi là việc của lãnh đạo (màn Sổ kiểm toán, `moc audit verify`).
-- Không gồm danh sách được xem văn bản hạn chế (office.document_acl): người trong danh sách không được biết ai khác
-- cũng có tên. Dòng văn bản vào hồ sơ bỏ id hồ sơ: người phòng khác đọc được văn bản nhưng không xem được hồ sơ.
-- Mỗi nhánh nối bằng `=` trên chỉ mục, để lọc theo một văn bản không phải quét cả sổ.

create index audit_log_entity_head on core.audit_log (entity, split_part(entity_id, '/', 1));
create index audit_log_case_file_doc on core.audit_log (split_part(entity_id, '/', 2))
  where entity = 'office.case_file_documents';

create view office.document_history as
select a.id, a.tenant_id, d.id as document_id, a.occurred_at, a.actor_id, a.actor_kind, a.action, a.entity,
       core.audit_overview(a) as overview
  from office.documents d
  join core.audit_log a on a.entity = 'office.documents' and a.entity_id = d.id::text and a.tenant_id = d.tenant_id
union all
select a.id, a.tenant_id, d.id, a.occurred_at, a.actor_id, a.actor_kind, a.action, a.entity, core.audit_overview(a)
  from office.documents d
  join core.audit_log a on a.entity = 'office.document_files' and split_part(a.entity_id, '/', 1) = d.id::text
                       and a.tenant_id = d.tenant_id
union all
select a.id, a.tenant_id, d.id, a.occurred_at, a.actor_id, a.actor_kind, a.action, a.entity,
       core.audit_overview(a) - 'case_file_id'
  from office.documents d
  join core.audit_log a on a.entity = 'office.case_file_documents' and split_part(a.entity_id, '/', 2) = d.id::text
                       and a.tenant_id = d.tenant_id
union all
select a.id, a.tenant_id, x.document_id, a.occurred_at, a.actor_id, a.actor_kind, a.action, a.entity,
       core.audit_overview(a)
  from office.assignments x
  join core.audit_log a on a.entity = 'office.assignments' and a.entity_id = x.id::text and a.tenant_id = x.tenant_id;
