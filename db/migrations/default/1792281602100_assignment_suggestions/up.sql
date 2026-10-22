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

-- Gợi ý giao việc (F4.3): văn bản đến vừa vào sổ thì nhánh BPMN song song `goiYGiaoViec` giao việc cho tác tử
-- `moc-assigner` trong svc-workflow. Tác tử tìm các văn bản đến tương tự đã giao (svc-files, truy xuất của F4.2), cho
-- mỗi căn cứ bỏ phiếu đơn vị chủ trì gốc của nó, rồi lưu đơn vị thắng, hạn đề xuất, độ tin cậy và căn cứ. Lãnh đạo thấy
-- gợi ý ở đầu form chỉ đạo, bấm "Dùng gợi ý" chỉ điền form — người quyết định vẫn là lãnh đạo. Mô tả:
-- docs/mo-hinh-du-lieu.md §1 (bảng), §2.5 (số đo), §3 (tác tử moc-assigner), §4.2 (task goiYGiaoViec), §5 (sự kiện
-- assignment.suggested); quyết định kiến trúc: docs/architecture.md QĐ-005.
--
-- - Một dòng mỗi văn bản, kể cả khi không gợi ý được (`none`: không có văn bản tương tự, chưa có lịch sử, đơn vị không
--   còn lãnh đạo phòng, phiếu quá phân tán) hay svc-files không trả lời (`failed`) — để đo độ phủ trên dữ liệu thật.
-- - Tác tử là vai trò Hasura `agent` (svc-workflow gọi bằng khóa quản trị + X-Hasura-Role: agent), như F4.1: thuê ước
--   và danh tính tác tử do Hasura đặt sẵn từ phiên (column preset), không lấy từ dữ liệu gửi lên. Vai trò này chỉ thêm
--   được dòng dưới đây và dòng sổ `assignment.suggested` — không đọc, không ghi văn bản.
-- - Căn cứ chỉ có id văn bản, điểm, đơn vị, số ngày: không có trích yếu hay số ký hiệu. Giao diện đọc số ký hiệu, trích
--   yếu của căn cứ bằng token người xem, nên không ai thấy văn bản mình không được đọc qua gợi ý.
-- - Không gắn trigger sổ kiểm toán: cùng giao dịch với dòng gợi ý, tác tử ghi một dòng sổ `assignment.suggested` chỉ có
--   số và mã (không có căn cứ), gắn vào văn bản (`entity` office.documents) nên tự hiện ở tab Lịch sử.
-- - Văn bản hạn chế (F3.7) không bao giờ có gợi ý và không bao giờ làm căn cứ: svc-files không tìm cho văn bản hạn chế
--   và bỏ văn bản hạn chế khỏi kết quả; trigger bên dưới chặn thêm ở CSDL, và dọn khi văn bản bật hạn chế sau đó.
-- Lỗi mang tên ràng buộc ở đầu câu (như lỗi check của PostgreSQL) để svc-workflow nhận ra và bỏ qua văn bản đó.

create table office.assignment_suggestions (
  document_id   uuid primary key,
  tenant_id     uuid not null,
  agent_id      text not null check (char_length(agent_id) between 1 and 64),        -- preset từ phiên agent
  process_id    text check (char_length(process_id) <= 64),                          -- phiên Flowable đã giao việc
  status        text not null check (status in ('suggested', 'none', 'failed')),
  reason        text,                                       -- lý do không gợi ý: none → no_*, low_confidence; failed
  department_id uuid,                                       -- đơn vị chủ trì gợi ý
  confidence    text check (confidence in ('high', 'medium', 'low')),
  share         real check (share > 0 and share <= 1),     -- tỉ phần phiếu của đơn vị thắng
  due_days      int  check (due_days between 1 and 365),   -- null: văn bản đã ghi hạn, hoặc căn cứ không có hạn
  due_on        date,
  -- [{document_id, score, department_id, days}] ≤ 5 phần tử; chỉ id và số, không chữ văn bản
  evidence      jsonb not null default '[]' check (jsonb_typeof(evidence) = 'array'
                  and jsonb_array_length(evidence) <= 5 and octet_length(evidence::text) <= 2048),
  candidates    int  not null default 0 check (candidates between 0 and 100),   -- số văn bản svc-files trả về
  semantic      boolean not null default false,                                  -- có tìm theo nghĩa (mô hình nhúng)
  duration_ms   int  not null check (duration_ms >= 0),
  created_at    timestamptz not null default now(),
  foreign key (tenant_id, document_id) references office.documents (tenant_id, id) on delete cascade,
  foreign key (tenant_id, department_id) references office.departments (tenant_id, id),
  -- reason phải có khi none/failed: `null in (…)` ra null, mà check coi null là đạt
  constraint assignment_suggestions_shape check (case status
    when 'suggested' then department_id is not null and confidence is not null and share is not null and reason is null
    when 'none' then reason is not null and reason in ('no_similar', 'no_history', 'no_valid_unit', 'low_confidence')
    else reason is not null and reason in ('timeout', 'unavailable') end
    and (status = 'suggested' or (department_id is null and confidence is null and share is null
                                  and due_days is null and jsonb_array_length(evidence) = 0))),
  constraint assignment_suggestions_due check ((due_days is null) = (due_on is null))
);

create index assignment_suggestions_tenant on office.assignment_suggestions (tenant_id, created_at);

-- Văn bản đích hạn chế hoặc là văn bản đi, hay một căn cứ là văn bản hạn chế: không lưu gợi ý. Dòng sổ đi cùng giao
-- dịch nên cũng không được ghi.
create function office.assignment_suggestions_guard() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
declare
  -- trigger chạy trước ràng buộc check của cột: evidence chưa chắc là mảng
  items jsonb := case when jsonb_typeof(new.evidence) = 'array' then new.evidence else '[]'::jsonb end;
  basis uuid[];
begin
  -- id văn bản căn cứ; phần tử không mang id hợp lệ không trỏ tới văn bản nào, bỏ qua
  select coalesce(array_agg((e ->> 'document_id')::uuid), '{}')
    into basis
    from jsonb_array_elements(items) as e
   where jsonb_typeof(e) = 'object'
     and e ->> 'document_id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
  -- khóa văn bản đích và các văn bản căn cứ (như document_files_sealed): bật hạn chế chạy song song thì lần sau đợi
  -- lần trước xong, không thì gợi ý vừa ghi lọt qua lần dọn của trigger documents_drop_restricted_assignment_suggestions
  perform 1
     from office.documents d
    where d.tenant_id = new.tenant_id and (d.id = new.document_id or d.id = any (basis))
    order by d.id
      for share;
  if exists (select 1 from office.documents d
              where d.tenant_id = new.tenant_id and d.id = new.document_id
                and (d.restricted or d.direction <> 'in')) then
    raise exception 'assignment_suggestions_sealed: văn bản hạn chế, văn bản đi không có gợi ý giao việc'
      using errcode = 'check_violation';
  end if;
  if exists (select 1 from office.documents d
              where d.tenant_id = new.tenant_id and d.id = any (basis) and d.restricted) then
    raise exception 'assignment_suggestions_sealed: văn bản hạn chế không làm căn cứ gợi ý giao việc'
      using errcode = 'check_violation';
  end if;
  -- không thấy văn bản đích (thuê ước khác, chưa có): để khóa ngoại báo lỗi
  return new;
end
$$;

create trigger assignment_suggestions_guard before insert or update on office.assignment_suggestions
  for each row execute function office.assignment_suggestions_guard();

-- Văn bản vừa bật hạn chế: xóa gợi ý của chính nó, gỡ nó khỏi căn cứ của các gợi ý khác. Đơn vị, độ tin cậy, hạn của
-- các gợi ý đó giữ nguyên — lãnh đạo đã có thể làm theo; chỉ còn ít căn cứ hơn. Hàm riêng, không sửa
-- office.drop_restricted_suggestions (F4.1).
create function office.drop_restricted_assignment_suggestions() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
begin
  delete from office.assignment_suggestions s where s.tenant_id = new.tenant_id and s.document_id = new.id;
  -- Một lệnh bật hạn chế nhiều văn bản: trigger từng dòng chạy sau khi cả lệnh xong, nên gỡ mọi căn cứ đang hạn chế
  -- chứ không chỉ văn bản này (dòng sửa xong không được còn căn cứ hạn chế — trigger guard chặn), và bỏ qua gợi ý của
  -- văn bản cũng vừa bật hạn chế (lượt của chính nó xóa dòng đó).
  update office.assignment_suggestions s
     set evidence = (select coalesce(jsonb_agg(e order by n), '[]'::jsonb)
                       from jsonb_array_elements(s.evidence) with ordinality as t(e, n)
                      where not exists (
                        select 1 from office.documents d
                         where d.tenant_id = s.tenant_id and d.restricted
                           and d.id = case when e ->> 'document_id'
                                                ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                                           then (e ->> 'document_id')::uuid end))
   where s.tenant_id = new.tenant_id
     and exists (select 1 from jsonb_array_elements(s.evidence) as e
                  where lower(e ->> 'document_id') = new.id::text)
     and not exists (select 1 from office.documents d
                      where d.tenant_id = s.tenant_id and d.id = s.document_id and d.restricted);
  return null;
end
$$;

create trigger documents_drop_restricted_assignment_suggestions after update of restricted on office.documents
  for each row when (new.restricted and not old.restricted)
  execute function office.drop_restricted_assignment_suggestions();

-- ---------------------------------------------------------------------------
-- Màn Sổ kiểm toán và tab Lịch sử: dòng `assignment.suggested` của tác tử hiện kết quả (suggested | none | failed), lý
-- do không gợi ý, số ngày đề xuất, độ tin cậy, số căn cứ, số văn bản tương tự, có tìm theo nghĩa không, thời gian.
-- department_id (đơn vị gợi ý) đã có trong danh sách chung. Khóa là outcome, outcome_reason chứ không phải status,
-- reason, để không mang nhãn của F4.1, F4.2 ở giao diện. Khóa khác cố tình nhét vào diff (trích yếu…) vẫn chỉ có tên.
-- Còn lại như migration 1792281602000, giữ nguyên các khóa của F3.12, F4.1 và F4.2.
-- ---------------------------------------------------------------------------

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
              or (r.action = 'assignment.suggested'
                  and k in ('outcome', 'outcome_reason', 'due_days', 'confidence', 'evidence', 'candidates', 'semantic',
                            'duration_ms'))
           then r.diff -> k end), '{}'::jsonb)
      from jsonb_object_keys(r.diff) as k
  ) end
$$;

-- ---------------------------------------------------------------------------
-- Lãnh đạo giữ hay đổi gợi ý trên dữ liệu thật: mỗi kết quả, mỗi mức tin cậy — số gợi ý, số đã giao, số giữ đơn vị,
-- số giữ hạn, tổng số ngày lệch hạn. "Đã giao" là việc chủ trì gốc chưa hủy, giao **sau** lúc gợi ý (giao trước đó thì
-- gợi ý không góp phần). Giao cho một người thì tính về phòng của người đó (core.users), như v_overdue_by_department.
-- Chỉ có số đếm. Văn bản bật hạn chế thì gợi ý của nó bị xóa, ra khỏi phép đếm.
-- ---------------------------------------------------------------------------

create view office.v_assignment_suggestion_accuracy as
with lead as (
  select distinct on (a.document_id) a.tenant_id, a.document_id, a.due_on, a.assigned_at,
         coalesce(a.department_id, u.department_id) as department_id
    from office.assignments a left join core.users u on u.tenant_id = a.tenant_id and u.id = a.user_id
   where a.role = 'lead' and a.parent_id is null and a.status <> 'cancelled'
   order by a.document_id, a.assigned_at)
select s.tenant_id, s.status, s.confidence,
       count(*)::int as suggested,
       count(l.document_id)::int as decided,
       count(*) filter (where l.department_id = s.department_id)::int as kept_unit,
       count(*) filter (where s.due_on is not null and l.due_on is not null)::int as due_compared,
       count(*) filter (where s.due_on is not null and l.due_on = s.due_on)::int as kept_due,
       coalesce(sum(abs(l.due_on - s.due_on)) filter (where s.due_on is not null and l.due_on is not null), 0)::int
         as due_abs_error_days
  from office.assignment_suggestions s
  left join lead l on l.tenant_id = s.tenant_id and l.document_id = s.document_id and l.assigned_at > s.created_at
 group by s.tenant_id, s.status, s.confidence;
