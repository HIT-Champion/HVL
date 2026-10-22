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

-- Nộp lưu (F3.8) không xóa số liệu của dashboard điều hành (F3.11) và số đo đọc văn bản đến (F4.1). Hàm
-- office.archive_case_file gỡ dòng thời gian (office.document_events) và liên kết tệp (office.document_files) của các
-- văn bản trong hồ sơ, mà hai khung nhìn tính từ chính các dòng đó:
-- - office.v_processing_time lấy lúc xong từ sự kiện processed / filed: văn bản `archived` vẫn nằm trong điều kiện của
--   view nhưng mất lúc xong nên rơi khỏi phép đếm — số văn bản, số giờ, số đúng hạn của các tháng cũ tụt sau mỗi lượt
--   nộp lưu.
-- - office.v_intake_accuracy nối gợi ý với văn bản qua dòng document_files vai trò main: gợi ý của văn bản đã nộp lưu
--   không còn được đếm.
-- Bảng office.archived_document_facts giữ đúng hai thứ ấy, một dòng mỗi văn bản nộp lưu, ghi trong cùng giao dịch nộp
-- lưu ngay trước khi xóa. Hai khung nhìn vẫn tính từ dòng thời gian, liên kết tệp như cũ và chỉ dùng bản giữ lại khi
-- dòng sống không còn: văn bản chưa nộp lưu được tính y như trước. Mô tả: docs/mo-hinh-du-lieu.md §2.4, §2.5.
--
-- - Dữ liệu dẫn xuất, chép từ dòng sắp xóa (như core.file_texts, F2.7): không gắn sổ kiểm toán — lượt nộp lưu đã có
--   dòng `case_file.archived`, mỗi liên kết tệp bị gỡ đã có dòng sổ của office.document_files, gói lưu trữ có bản đủ.
-- - Không đưa vào metadata Hasura: không vai trò nào đọc, ghi; chỉ hai khung nhìn đọc. Lược đồ GraphQL không đổi.
-- - Văn bản đã nộp lưu trước migration này: lấy lại từ sổ kiểm toán (chỉ đọc). Lúc xong là lần cuối trạng thái chuyển
--   sang `done` — svc-workflow ghi cùng giao dịch với sự kiện processed / filed, nên chỉ lệch vài mili giây; bản chính
--   là dòng document_files vai trò main bị xóa trong giao dịch nộp lưu (không trước lúc archived_at của hồ sơ).

create table office.archived_document_facts (   -- số liệu giữ lại khi nộp lưu (F3.8), một dòng mỗi văn bản
  document_id    uuid primary key,
  tenant_id      uuid not null,
  finished_at    timestamptz,                    -- sự kiện processed / filed cuối cùng; null: không có
  main_file_ids  uuid[] not null default '{}',   -- tệp bản chính (document_files vai trò main) lúc nộp lưu
  foreign key (tenant_id, document_id) references office.documents (tenant_id, id)
);

-- Văn bản đã nộp lưu trước migration này (xem đầu tệp)
insert into office.archived_document_facts (document_id, tenant_id, finished_at, main_file_ids)
select d.id, d.tenant_id,
       (select max(a.occurred_at) from core.audit_log a
         where a.entity = 'office.documents' and a.entity_id = d.id::text and a.tenant_id = d.tenant_id
           and a.diff -> 'status' ->> 1 = 'done'),
       array(select distinct (a.diff -> 'file_id' ->> 0)::uuid
               from core.audit_log a
              where a.entity = 'office.document_files' and split_part(a.entity_id, '/', 1) = d.id::text
                and a.tenant_id = d.tenant_id and a.action = 'delete' and a.diff -> 'role' ->> 0 = 'main'
                and a.occurred_at >= cf.archived_at
              order by 1)
  from office.documents d
  join office.case_file_documents cd on cd.tenant_id = d.tenant_id and cd.document_id = d.id
  join office.case_files cf on cf.tenant_id = cd.tenant_id and cf.id = cd.case_file_id and cf.status = 'archived'
 where d.status = 'archived';

-- ---------------------------------------------------------------------------
-- Nộp lưu: chép nguyên hàm của migration 1792281601300, chỉ thêm lệnh ghi office.archived_document_facts ngay trước
-- khi xóa dòng thời gian, liên kết tệp (cùng giao dịch, sau mọi bước kiểm).
-- ---------------------------------------------------------------------------

-- Nộp lưu: svc-files gọi sau khi gói đã nằm trong bucket lạnh và đọc lại khớp băm. Một giao dịch, khóa dòng hồ sơ,
-- văn bản, tệp; kiểm CSDL còn đúng như lúc chụp vào gói — hồ sơ vẫn `closed`, đúng các văn bản ấy, đúng các dòng thời
-- gian và liên kết tệp ấy (không có dòng mới sinh trong lúc ghi gói) — lệch một chỗ là raise, không đổi gì, lượt sau
-- làm lại. Hai lượt nộp lưu cùng lúc: lượt sau đợi khóa rồi thấy hồ sơ đã `archived`, rollback cả sự kiện sổ kiểm toán.
-- Chỉ khóa quản trị gọi được (hàm khai trong metadata không cấp quyền cho vai trò nào).
-- p: {id, archive_key, archive_sha256 (hex), bucket, documents: [uuid], events: [bigint],
--     links: [{document_id, file_id}], cold_files: [uuid], files: số tệp trong gói}
create or replace function office.archive_case_file(p jsonb)
returns setof office.case_files
language plpgsql volatile set search_path = pg_catalog, pg_temp
as $$
declare
  cf       office.case_files%rowtype;
  docs     uuid[] := array(select x::uuid from jsonb_array_elements_text(p -> 'documents') x order by 1);
  events   bigint[] := array(select x::bigint from jsonb_array_elements_text(p -> 'events') x order by 1);
  links    text[] := array(select (l ->> 'document_id') || '/' || (l ->> 'file_id')
                             from jsonb_array_elements(p -> 'links') l order by 1);
  cold     uuid[] := array(select x::uuid from jsonb_array_elements_text(p -> 'cold_files') x);
  session  jsonb := nullif(current_setting('hasura.user', true), '')::jsonb;
  n        int;
begin
  select * into cf from office.case_files where id = (p ->> 'id')::uuid for update;
  if not found or cf.status <> 'closed' then
    raise exception 'hồ sơ % không còn ở trạng thái đã đóng (%), không nộp lưu', coalesce(cf.code, p ->> 'id'),
      coalesce(cf.status, 'không có') using errcode = 'check_violation';
  end if;
  if p ->> 'archive_key' is distinct from format('cold/%s/case/%s/', cf.tenant_id, cf.id)
     or exists (select 1 from unnest(cold) f
                 where not exists (select 1 from jsonb_array_elements(p -> 'links') l
                                    where (l ->> 'file_id')::uuid = f)) then
    raise exception 'gói nộp lưu của hồ sơ % không khớp hồ sơ', cf.code using errcode = 'check_violation';
  end if;
  if docs is distinct from array(select document_id from office.case_file_documents where case_file_id = cf.id
                                  order by 1) then
    raise exception 'văn bản trong hồ sơ % đổi trong lúc nộp lưu', cf.code using errcode = 'serialization_failure';
  end if;
  perform 1 from office.documents where id = any (docs) and status in ('done', 'issued') and not restricted
     for update;
  get diagnostics n = row_count;
  if n <> cardinality(docs) then
    raise exception 'văn bản trong hồ sơ % đổi trạng thái trong lúc nộp lưu', cf.code using errcode = 'serialization_failure';
  end if;
  perform 1 from core.files where id = any (cold) for update;   -- chặn gắn tệp vào văn bản khác giữa chừng
  if events is distinct from array(select id from office.document_events where document_id = any (docs) order by 1)
     or links is distinct from array(select document_id || '/' || file_id from office.document_files
                                      where document_id = any (docs) order by 1) then
    raise exception 'dòng thời gian hoặc tệp của hồ sơ % đổi trong lúc nộp lưu', cf.code
      using errcode = 'serialization_failure';
  end if;

  update office.case_files
     set status = 'archived', archived_at = now(), archive_key = p ->> 'archive_key',
         archive_sha256 = decode(p ->> 'archive_sha256', 'hex')
   where id = cf.id;
  update office.documents set status = 'archived' where id = any (docs);
  -- lúc xong (dashboard F3.11) và tệp bản chính (số đo đọc văn bản F4.1): hai khung nhìn đọc từ đây khi dòng thời
  -- gian, liên kết tệp đã gỡ (migration 1792281602300)
  insert into office.archived_document_facts (document_id, tenant_id, finished_at, main_file_ids)
  select d.id, d.tenant_id,
         (select max(e.created_at) from office.document_events e
           where e.document_id = d.id and e.kind in ('office.document.processed', 'office.document.filed')),
         array(select l.file_id from office.document_files l
                where l.document_id = d.id and l.role = 'main' order by 1)
    from office.documents d
   where d.id = any (docs);
  delete from office.document_events where id = any (events);
  delete from office.document_files where document_id = any (docs);
  if exists (select 1 from office.document_files where file_id = any (cold)) then
    raise exception 'tệp của hồ sơ % còn gắn với văn bản khác', cf.code using errcode = 'serialization_failure';
  end if;
  update core.files set storage_tier = 'cold' where id = any (cold);

  insert into core.audit_log (tenant_id, actor_id, actor_kind, request_id, action, entity, entity_id, diff)
  values (cf.tenant_id,
          coalesce(session ->> 'x-hasura-user-id', nullif(current_setting('moc.actor', true), ''), session_user::text),
          'system',
          coalesce(session ->> 'x-hasura-request-id', nullif(current_setting('moc.request_id', true), '')),
          'case_file.archived', 'office.case_files', cf.id::text,
          jsonb_build_object('code', cf.code, 'archive_key', p ->> 'archive_key',
                             'archive_sha256', p ->> 'archive_sha256', 'bucket', p ->> 'bucket',
                             'documents', cardinality(docs), 'files', (p ->> 'files')::int));
  return query select * from office.case_files where id = cf.id;
end
$$;

-- ---------------------------------------------------------------------------
-- Dashboard (F3.11): như migration 1792281601200, lúc xong của văn bản đã nộp lưu lấy từ bản giữ lại khi dòng thời
-- gian không còn sự kiện processed / filed. Văn bản chưa nộp lưu không có dòng trong bảng giữ lại: tính y như cũ.
-- ---------------------------------------------------------------------------

-- Thời gian từ vào sổ đến khi xong (người được giao báo xong, hoặc lãnh đạo cho lưu không xử lý), theo tháng xong. Lúc
-- xong lấy từ dòng thời gian (office.document_events), ghi cùng giao dịch với trạng thái done; nộp lưu gỡ dòng thời
-- gian thì lấy bản giữ lại lúc nộp lưu (office.archived_document_facts). Văn bản không có sự kiện đó (vd nhập thẳng vào
-- CSDL) không được tính. Trả tổng số giờ, không trả trung bình đã làm tròn: giao diện tự chia, gộp được nhiều tháng
-- mà không lệch. on_time chỉ đếm trong số văn bản có hạn (with_due).
create or replace view office.v_processing_time as
with finished as (
  select d.tenant_id,
         d.registered_at,
         d.due_on,
         coalesce((select max(e.created_at) from office.document_events e
                    where e.document_id = d.id
                      and e.kind in ('office.document.processed', 'office.document.filed')),
                  (select k.finished_at from office.archived_document_facts k
                    where k.document_id = d.id and k.tenant_id = d.tenant_id)) as finished_at
    from office.documents d
   where d.direction = 'in' and d.status in ('done', 'archived') and d.registered_at is not null
     and not d.restricted
)
select tenant_id,
       date_trunc('month', finished_at at time zone 'Asia/Ho_Chi_Minh')::date as month,
       count(*)::int as documents,
       (sum(extract(epoch from finished_at - registered_at)) / 3600)::float8 as total_hours,
       count(due_on)::int as with_due,
       count(*) filter (where (finished_at at time zone 'Asia/Ho_Chi_Minh')::date <= due_on)::int as on_time
  from finished
 where finished_at is not null
 group by 1, 2;

-- ---------------------------------------------------------------------------
-- Độ chính xác của gợi ý đọc văn bản đến (F4.1): như migration 1792281601900, tệp bản chính lấy từ liên kết tệp còn
-- sống cộng bản giữ lại lúc nộp lưu (liên kết của văn bản đã nộp lưu đã bị gỡ, không trùng với liên kết sống).
-- ---------------------------------------------------------------------------

create or replace view office.v_intake_accuracy as
with main_files as (
  select l.tenant_id, l.document_id, l.file_id
    from office.document_files l
   where l.role = 'main'
  union all
  select k.tenant_id, k.document_id, m.file_id
    from office.archived_document_facts k
   cross join unnest(k.main_file_ids) as m(file_id)
),
pairs as (
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
    join main_files l on l.tenant_id = s.tenant_id and l.file_id = s.file_id
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
