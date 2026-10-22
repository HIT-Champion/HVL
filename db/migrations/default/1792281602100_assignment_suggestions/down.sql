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

-- Bỏ gợi ý giao việc. core.audit_overview về định nghĩa của migration 1792281602000, chép nguyên văn. Dòng
-- `assignment.suggested` đã ghi vào core.audit_log vẫn giữ (sổ chỉ được ghi thêm), màn Sổ kiểm toán và tab Lịch sử chỉ
-- còn thấy tên các khóa của chúng (trừ department_id).
drop view office.v_assignment_suggestion_accuracy;
drop trigger documents_drop_restricted_assignment_suggestions on office.documents;
drop function office.drop_restricted_assignment_suggestions();
drop trigger assignment_suggestions_guard on office.assignment_suggestions;
drop table office.assignment_suggestions;
drop function office.assignment_suggestions_guard();

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
              or (r.action = 'intake.suggested'
                  and k in ('method', 'pages', 'found', 'summary_source', 'model', 'duration_ms', 'reason'))
              or (r.action = 'assistant.answered'
                  and k in ('ask_id', 'mode', 'answer_source', 'hits', 'cited', 'semantic', 'model', 'embed_model',
                            'duration_ms', 'warnings'))
           then r.diff -> k end), '{}'::jsonb)
      from jsonb_object_keys(r.diff) as k
  ) end
$$;
