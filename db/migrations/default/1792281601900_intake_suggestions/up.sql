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

-- Đọc văn bản đến (F4.1): văn thư tải công văn lên màn tiếp nhận, tác tử `moc-doc-reader` trong svc-files đọc tệp
-- (lớp chữ PDF, không có thì OCR) và gợi ý số ký hiệu, ngày ban hành, cơ quan ban hành, loại, độ khẩn, trích yếu.
-- Văn thư đối chiếu, sửa rồi mới lưu — văn bản vẫn chỉ vào qua Action receiveIncoming như cũ. Mô tả:
-- docs/mo-hinh-du-lieu.md §1 (bảng), §2.5 (số đo), §3 (vai trò agent), §5 (sự kiện intake.suggested).
--
-- - Tác tử là vai trò Hasura `agent` (svc-files gọi bằng khóa quản trị + X-Hasura-Role: agent): thuê ước và danh tính
--   tác tử do Hasura đặt sẵn từ phiên (column preset), không lấy từ dữ liệu gửi lên. Vai trò này chỉ ghi được bảng
--   dưới đây và dòng sổ `intake.suggested` — không đọc, không ghi văn bản, không đọc core.files.
-- - Gợi ý lưu theo tệp (khóa file_id): lần bấm "Đọc văn bản" sau trả ngay bản đã lưu; đối chiếu gợi ý với văn bản văn
--   thư đã lưu cho số đo "giữ nguyên bao nhiêu gợi ý" trên dữ liệu thật (view office.v_intake_accuracy).
-- - Không gắn trigger sổ kiểm toán: gợi ý là dữ liệu dẫn xuất có nội dung văn bản (như core.file_texts, F2.7). Mỗi
--   lần đọc thật, svc-files ghi một dòng sổ `intake.suggested` chỉ có siêu dữ liệu (cách đọc, số trang, tên các
--   trường tìm thấy…) trong cùng giao dịch với gợi ý.
-- - Văn bản hạn chế (F3.7) không bao giờ được đọc: svc-files từ chối tệp mã hóa trước khi đọc byte; trigger bên dưới
--   chặn thêm ở CSDL việc lưu gợi ý của tệp mã hóa hay tệp gắn vào văn bản hạn chế, và xóa gợi ý khi văn bản bật hạn
--   chế hoặc khi tệp được gắn vào văn bản hạn chế (dữ liệu có từ trước F3.7).
-- Lỗi mang tên ràng buộc ở đầu câu (như lỗi check của PostgreSQL) để svc-files, giao diện dịch thành câu dễ hiểu.

create table office.intake_suggestions (
  file_id         uuid primary key,
  tenant_id       uuid not null,
  requested_by    text not null check (char_length(requested_by) between 1 and 64),   -- sub văn thư bấm đọc
  agent_id        text not null check (char_length(agent_id) between 1 and 64),       -- preset từ phiên agent
  status          text not null check (status in ('ok', 'empty')),
  method          text not null check (method in ('text', 'ocr')),
  pages           int  not null check (pages between 0 and 200),
  -- {trường: {value, confidence, source}}, chỉ sáu trường của form tiếp nhận
  fields          jsonb not null default '{}'
                  check (jsonb_typeof(fields) = 'object' and octet_length(fields::text) <= 16384
                    and fields - array['type_code','symbol','issued_on','issuer_name','summary','urgency'] = '{}'::jsonb),
  warnings        jsonb not null default '[]' check (jsonb_typeof(warnings) = 'array'),   -- mã cảnh báo cố định
  summary_source  text not null default 'none' check (summary_source in ('rule', 'model', 'none')),
  model           text check (char_length(model) <= 100),                              -- tên mô hình đã dùng
  duration_ms     int  not null check (duration_ms >= 0),
  read_at         timestamptz not null default now(),          -- trigger đặt lại ở mỗi lần ghi
  foreign key (tenant_id, file_id) references core.files (tenant_id, id) on delete cascade
);

-- Tệp mã hóa (văn bản hạn chế, F3.7) hoặc tệp đang gắn vào văn bản hạn chế: không lưu gợi ý. Bản gợi ý (trích yếu,
-- số ký hiệu) là chữ trần của văn bản, lưu ra sẽ vô hiệu việc mã hóa tệp.
create function office.intake_suggestions_guard() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
begin
  -- khóa văn bản đang gắn tệp: bật hạn chế chạy song song thì lần sau đợi lần trước xong (như document_files_sealed),
  -- không thì gợi ý vừa ghi lọt qua lần xóa của trigger documents_drop_restricted_suggestions
  perform 1
     from office.document_files l
     join office.documents d on d.tenant_id = l.tenant_id and d.id = l.document_id
    where l.file_id = new.file_id
      for share of d;
  if exists (select 1 from core.files f where f.tenant_id = new.tenant_id and f.id = new.file_id and f.encrypted)
     or exists (select 1 from office.document_files l
                  join office.documents d on d.tenant_id = l.tenant_id and d.id = l.document_id
                 where l.file_id = new.file_id and d.restricted) then
    raise exception 'intake_suggestions_sealed: tệp của văn bản hạn chế không được đọc tự động, không lưu gợi ý'
      using errcode = 'check_violation';
  end if;
  -- không thấy tệp (thuê ước khác, chưa có): để khóa ngoại báo lỗi
  new.read_at := now();
  return new;
end
$$;

create trigger intake_suggestions_guard before insert or update on office.intake_suggestions
  for each row execute function office.intake_suggestions_guard();

-- Văn bản vừa bật hạn chế, hoặc tệp vừa gắn vào văn bản hạn chế: xóa gợi ý đã lưu của các tệp đó. Chỉ xảy ra với dữ
-- liệu có từ trước F3.7: nay văn bản hạn chế chỉ gắn tệp mã hóa (document_files_sealed), mà tệp mã hóa không có gợi ý.
-- Hàm riêng, không sửa office.drop_restricted_texts (F2.7).
create function office.drop_restricted_suggestions() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
begin
  if tg_table_name = 'documents' then
    delete from office.intake_suggestions s using office.document_files l
     where l.tenant_id = new.tenant_id and l.document_id = new.id and s.file_id = l.file_id;
  elsif exists (select 1 from office.documents d
                 where d.tenant_id = new.tenant_id and d.id = new.document_id and d.restricted) then
    delete from office.intake_suggestions s where s.file_id = new.file_id;
  end if;
  return null;
end
$$;

create trigger documents_drop_restricted_suggestions after update of restricted on office.documents
  for each row when (new.restricted and not old.restricted) execute function office.drop_restricted_suggestions();

create trigger document_files_drop_restricted_suggestions after insert on office.document_files
  for each row execute function office.drop_restricted_suggestions();

-- ---------------------------------------------------------------------------
-- Sổ kiểm toán: phiên Hasura vai trò `agent` ghi actor_kind 'agent'. Chép nguyên thân hàm của migration
-- 1792281600100, chỉ thêm nhánh agent ở dòng chọn actor_kind. Hiện vai trò agent chỉ ghi bảng không gắn trigger này
-- (office.intake_suggestions) và dòng sổ tự ghi; nhánh để tác tử về sau ghi bảng nghiệp vụ vẫn mang đúng loại.
-- ---------------------------------------------------------------------------

-- Trigger gắn vào bảng nghiệp vụ: mỗi dòng thêm, sửa, xóa thành một dòng sổ.
-- Tham số trigger: các cột khóa ghép thành entity_id (mặc định 'id').
-- Người thực hiện:
--   qua Hasura   — biến phiên hasura.user (vai trò service → 'service', agent → 'agent', admin → 'system',
--                  còn lại 'user')
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
         then case role when 'service' then 'service' when 'agent' then 'agent' when 'admin' then 'system' else 'user' end
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

-- ---------------------------------------------------------------------------
-- Màn Sổ kiểm toán: dòng `intake.suggested` của tác tử hiện cách đọc (text | ocr), số trang, tên các trường tìm thấy,
-- nguồn trích yếu, tên mô hình, thời gian, lý do đọc hỏng. status, user_id (văn thư bấm đọc), file_id đã có trong
-- danh sách chung. Khóa khác cố tình nhét vào diff (trích yếu, số ký hiệu…) vẫn chỉ có tên. Còn lại như migration
-- 1792281601800, giữ nguyên các khóa liên thông của F3.12.
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
           then r.diff -> k end), '{}'::jsonb)
      from jsonb_object_keys(r.diff) as k
  ) end
$$;

-- ---------------------------------------------------------------------------
-- Độ chính xác của gợi ý trên dữ liệu thật: mỗi trường, mỗi mức tin cậy — số lần gợi ý và số lần văn thư giữ nguyên
-- khi lưu. Chỉ tính tệp là bản chính (role main) của văn bản đến không hủy, không hạn chế. "Giữ nguyên": số ký hiệu
-- bỏ mọi khoảng trắng, không phân biệt hoa thường; cơ quan ban hành gộp khoảng trắng, không phân biệt hoa thường; ngày
-- so dạng YYYY-MM-DD; trường khác phải bằng nhau. Chỉ có số đếm, không cột nào chứa giá trị của trường.
-- ---------------------------------------------------------------------------

create view office.v_intake_accuracy as
with pairs as (
  select s.tenant_id,
         f.key                     as field,
         f.value ->> 'confidence'  as confidence,
         f.value ->> 'value'       as proposed,
         case f.key
           when 'type_code'   then d.type_code
           when 'symbol'      then d.symbol
           when 'issued_on'   then to_char(d.issued_on, 'YYYY-MM-DD')
           when 'issuer_name' then d.issuer_name
           when 'summary'     then d.summary
           when 'urgency'     then d.urgency
         end                       as saved
    from office.intake_suggestions s
    join office.document_files l on l.tenant_id = s.tenant_id and l.file_id = s.file_id and l.role = 'main'
    join office.documents d on d.tenant_id = l.tenant_id and d.id = l.document_id
   cross join lateral jsonb_each(s.fields) as f(key, value)
   where d.direction = 'in' and d.status <> 'cancelled' and not d.restricted
)
select tenant_id,
       field,
       confidence,
       count(*)::int as suggested,
       count(*) filter (where case field
         when 'symbol'      then upper(regexp_replace(proposed, '\s+', '', 'g'))
                               = upper(regexp_replace(saved, '\s+', '', 'g'))
         when 'issuer_name' then lower(regexp_replace(btrim(proposed), '\s+', ' ', 'g'))
                               = lower(regexp_replace(btrim(saved), '\s+', ' ', 'g'))
         else proposed = saved
       end)::int as kept
  from pairs
 group by tenant_id, field, confidence;
