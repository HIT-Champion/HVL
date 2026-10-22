-- Copyright 2026 Mộc Team
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

-- Bỏ chữ ký số (F4.5). Khung nhìn của cổng xác thực về định nghĩa của migration 1792281601600, chép nguyên văn:
-- create or replace không bỏ được cột, nên xóa rồi dựng lại (không khung nhìn, hàm nào phụ thuộc nó). Dòng sổ
-- `core.file_signatures` đã ghi vào core.audit_log vẫn giữ (sổ chỉ được ghi thêm). PDF đã ký vẫn mang chữ ký của nó.
drop view office.issued_documents;

create view office.issued_documents as
select d.verify_code,
       d.content_sha256,
       d.symbol,
       d.issued_on,
       d.type_code,
       dt.name   as type_name,
       t.name    as issuer_name,
       t.parent_name,
       case when d.is_public and not d.restricted then d.summary end as summary,
       d.status
  from office.documents d
  join core.tenants t on t.id = d.tenant_id
  join office.document_types dt on dt.code = d.type_code
 where d.direction = 'out' and d.status in ('issued', 'archived');

drop index core.files_tenant_sha256;
drop table core.file_signatures;
