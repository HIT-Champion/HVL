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


create or replace function core.audit_overview(r core.audit_log) returns jsonb
language sql stable
as $$
  select case when jsonb_typeof(r.diff) <> 'object' then '{}'::jsonb else (
    select coalesce(jsonb_object_agg(k, case when k = any (array[
             'status', 'urgency', 'direction', 'register_number', 'registered_at', 'due_on', 'issued_on',
             'restricted', 'is_public', 'role', 'enabled', 'department_id', 'user_id', 'signer_id',
             'document_id', 'file_id', 'year', 'entries', 'masked'
           ]) or (r.action = 'file.rejected' and k in ('signature', 'size_bytes')) then r.diff -> k end), '{}'::jsonb)
      from jsonb_object_keys(r.diff) as k
  ) end
$$;
drop function office.archive_case_file(jsonb);
drop trigger document_files_hot_only on office.document_files;
drop function office.document_files_hot_only();
drop table office.case_file_documents;
drop function office.case_file_documents_check();
drop function office.case_file_documents_locked();
drop table office.case_files;
drop function office.case_files_transition();
