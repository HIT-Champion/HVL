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

-- Bỏ gợi ý đọc văn bản đến. core.audit_overview về định nghĩa của migration 1792281601800, core.audit() về định nghĩa
-- của migration 1792281600100, chép nguyên văn. Dòng `intake.suggested` đã ghi vào core.audit_log vẫn giữ (sổ chỉ
-- được ghi thêm), màn Sổ kiểm toán chỉ còn thấy tên các khóa của chúng.
drop view office.v_intake_accuracy;
drop trigger document_files_drop_restricted_suggestions on office.document_files;
drop trigger documents_drop_restricted_suggestions on office.documents;
drop function office.drop_restricted_suggestions();
drop table office.intake_suggestions;
drop function office.intake_suggestions_guard();

create or replace function core.audit_overview(r core.audit_log) returns jsonb
language sql stable
as $$
  select case when jsonb_typeof(r.diff) <> 'object' then '{}'::jsonb else (
    select coalesce(jsonb_object_agg(k, case when k = any (array[
             'status', 'urgency', 'direction', 'register_number', 'registered_at', 'due_on', 'issued_on',
             'restricted', 'is_public', 'role', 'enabled', 'department_id', 'user_id', 'signer_id',
             'document_id', 'file_id', 'year', 'entries', 'masked',
             'to_tenant_id', 'incoming_document_id', 'source_id', 'attempts', 'delivered_at'
           ]) or (r.action = 'file.rejected' and k in ('signature', 'size_bytes'))
              or (r.entity in ('office.case_files', 'office.case_file_documents')
                  and k in ('code', 'closed_on', 'retention_years', 'archived_at', 'archive_sha256', 'case_file_id'))
              or (r.action = 'case_file.archived' and k in ('code', 'archive_sha256', 'documents', 'files'))
              or (r.action = 'case_file.read' and k in ('code', 'archive_sha256'))
           then r.diff -> k end), '{}'::jsonb)
      from jsonb_object_keys(r.diff) as k
  ) end
$$;

-- Trigger gắn vào bảng nghiệp vụ: mỗi dòng thêm, sửa, xóa thành một dòng sổ.
-- Tham số trigger: các cột khóa ghép thành entity_id (mặc định 'id').
-- Người thực hiện:
--   qua Hasura   — biến phiên hasura.user (vai trò service → 'service', admin → 'system', còn lại 'user')
--   ghi thẳng CSDL — set local moc.actor / moc.actor_kind / moc.request_id trước khi ghi
create or replace function core.audit() returns trigger
language plpgsql security definer set search_path = pg_catalog, pg_temp
as $$
declare
  old_row jsonb := case when tg_op <> 'INSERT' then to_jsonb(old) end;
  new_row jsonb := case when tg_op <> 'DELETE' then to_jsonb(new) end;
  any_row jsonb := coalesce(new_row, old_row);
  session jsonb := nullif(current_setting('hasura.user', true), '')::jsonb;
  role    text  := session ->> 'x-hasura-role';
  changes jsonb;
  key_id  text;
begin
  select coalesce(jsonb_object_agg(k, jsonb_build_array(old_row -> k, new_row -> k)), '{}'::jsonb)
    into changes
    from jsonb_object_keys(any_row) as k
   where coalesce(old_row -> k, 'null'::jsonb) is distinct from coalesce(new_row -> k, 'null'::jsonb);

  if changes = '{}'::jsonb then
    return null;                              -- UPDATE không đổi giá trị nào
  end if;

  if tg_nargs = 0 then
    key_id := any_row ->> 'id';
  else
    select string_agg(any_row ->> a, '/' order by n) into key_id
      from unnest(tg_argv) with ordinality as t(a, n);
  end if;

  insert into core.audit_log (tenant_id, actor_id, actor_kind, request_id, action, entity, entity_id, diff)
  values (
    (any_row ->> 'tenant_id')::uuid,
    case when session is not null
         then coalesce(session ->> 'x-hasura-user-id', 'hasura:' || coalesce(role, '?'))
         else coalesce(nullif(current_setting('moc.actor', true), ''), session_user::text) end,
    case when session is not null
         then case role when 'service' then 'service' when 'admin' then 'system' else 'user' end
         else coalesce(nullif(current_setting('moc.actor_kind', true), ''), 'system') end,
    coalesce(session ->> 'x-hasura-request-id', nullif(current_setting('moc.request_id', true), '')),
    lower(tg_op),
    tg_table_schema || '.' || tg_table_name,
    coalesce(key_id, '?'),
    changes
  );
  return null;
end
$$;
