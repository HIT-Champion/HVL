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

-- Bỏ dòng liên thông khỏi lịch sử văn bản và các cột liên thông khỏi màn Sổ kiểm toán: định nghĩa của migration
-- 1792281601500 và 1792281601300, chép nguyên văn. Dòng đã ghi vào core.audit_log vẫn giữ (sổ chỉ được ghi thêm);
-- văn bản đến đã giao vẫn còn, source_id vẫn trỏ về văn bản gửi.
create or replace view office.document_history as
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

create or replace function core.audit_overview(r core.audit_log) returns jsonb
language sql stable
as $$
  select case when jsonb_typeof(r.diff) <> 'object' then '{}'::jsonb else (
    select coalesce(jsonb_object_agg(k, case when k = any (array[
             'status', 'urgency', 'direction', 'register_number', 'registered_at', 'due_on', 'issued_on',
             'restricted', 'is_public', 'role', 'enabled', 'department_id', 'user_id', 'signer_id',
             'document_id', 'file_id', 'year', 'entries', 'masked'
           ]) or (r.action = 'file.rejected' and k in ('signature', 'size_bytes'))
              or (r.entity in ('office.case_files', 'office.case_file_documents')
                  and k in ('code', 'closed_on', 'retention_years', 'archived_at', 'archive_sha256', 'case_file_id'))
              or (r.action = 'case_file.archived' and k in ('code', 'archive_sha256', 'documents', 'files'))
              or (r.action = 'case_file.read' and k in ('code', 'archive_sha256'))
           then r.diff -> k end), '{}'::jsonb)
      from jsonb_object_keys(r.diff) as k
  ) end
$$;

drop function office.fail_dispatch(uuid, text, json);
drop function office.deliver_dispatch(uuid, json);
drop trigger documents_dispatch_pending on office.documents;
drop function office.documents_dispatch_pending();
drop trigger documents_dispatch on office.documents;
drop function office.documents_dispatch();
drop table office.dispatches;
drop view office.dispatch_units;
drop index office.documents_source_once;
drop trigger documents_recipient_units on office.documents;
drop function office.documents_recipient_units();
alter table office.documents
  drop constraint documents_restricted_local,
  drop constraint documents_recipient_units_other,
  drop constraint documents_recipient_units_out,
  drop column recipient_tenant_ids;
drop function office.clean_text(text, boolean);
