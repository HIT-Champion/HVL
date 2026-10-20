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


-- Hồ sơ công việc và nộp lưu (F3.8, NĐ 30/2020 Điều 28–31; Luật Lưu trữ 2024). Chuyên viên, tổ trưởng lập hồ sơ
-- của phòng mình, đưa văn bản đã xử lý xong vào, đóng hồ sơ khi công việc kết thúc. Job nộp lưu của svc-files
-- (svc_files.archive) chọn hồ sơ đã đóng quá MOC_ARCHIVE_AFTER_DAYS ngày: ghi gói Parquet + tệp + manifest có băm vào
-- bucket lạnh (khóa ghi S3 Object Lock), rồi mới gỡ chi tiết khỏi OLTP (dòng thời gian, liên kết tệp).
-- Dòng văn bản rút gọn ở lại với trạng thái `archived`: vẫn tìm thấy, cổng xác thực vẫn trả lời "khớp".
-- Chỉ svc-files (khóa quản trị, qua hàm office.archive_case_file) chuyển hồ sơ sang `archived`; người dùng chỉ lập và
-- đóng. Giao việc ở lại CSDL: là căn cứ quyền xem văn bản (office.document_visible) và cột "đơn vị nhận" của sổ đăng
-- ký; gói lưu trữ cũng có một bản.

create table office.case_files (            -- hồ sơ công việc
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references core.tenants,
  department_id    uuid not null,
  year             int  not null check (year between 2000 and 2999),
  code             text not null check (btrim(code) <> ''),     -- ký hiệu theo danh mục hồ sơ của đơn vị
  title            text not null check (char_length(btrim(title)) between 5 and 500),
  retention_years  int  check (retention_years is null or retention_years between 1 and 100),  -- null = vĩnh viễn
  status           text not null default 'open' check (status in ('open', 'closed', 'archived')),
  closed_on        date,
  archived_at      timestamptz,
  archive_key      text check (archive_key is null or archive_key ~ '^cold/[0-9a-f-]{36}/case/[0-9a-f-]{36}/$'),
  archive_sha256   bytea check (archive_sha256 is null or octet_length(archive_sha256) = 32),
  created_by       text not null,
  created_at       timestamptz not null default now(),
  unique (tenant_id, id),
  unique (tenant_id, year, code),
  foreign key (tenant_id, department_id) references office.departments (tenant_id, id),
  check ((status = 'open') = (closed_on is null)),
  check ((status = 'archived') = (archive_key is not null and archive_sha256 is not null and archived_at is not null))
);

create table office.case_file_documents (
  tenant_id     uuid not null,
  case_file_id  uuid not null,
  document_id   uuid not null,
  added_by      text not null,
  added_at      timestamptz not null default now(),
  primary key (case_file_id, document_id),
  unique (document_id),                     -- mỗi văn bản thuộc một hồ sơ
  foreign key (tenant_id, case_file_id) references office.case_files (tenant_id, id),
  foreign key (tenant_id, document_id) references office.documents (tenant_id, id)
);

-- Văn bản vào hồ sơ: đã xử lý xong (đến: done; đi: issued), không phải văn bản hạn chế (tệp của nó mã hóa riêng,
-- F3.7), hồ sơ còn mở. Kiểm ở CSDL để mọi đường ghi (Hasura, svc-files) đều theo.
create function office.case_file_documents_check() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
declare
  doc office.documents%rowtype;
  cf  office.case_files%rowtype;
begin
  -- khóa dòng hồ sơ: đóng hồ sơ cùng lúc thì một trong hai đợi, không lọt văn bản vào hồ sơ vừa đóng
  select * into strict cf from office.case_files where id = new.case_file_id for share;
  if cf.status <> 'open' then
    raise exception 'hồ sơ % đã đóng, không thêm văn bản được', cf.code using errcode = 'check_violation';
  end if;
  select * into strict doc from office.documents where id = new.document_id;
  if doc.restricted then
    raise exception 'văn bản hạn chế không đưa vào hồ sơ nộp lưu' using errcode = 'check_violation';
  end if;
  if not ((doc.direction = 'in' and doc.status = 'done') or (doc.direction = 'out' and doc.status = 'issued')) then
    raise exception 'chỉ văn bản đã xử lý xong (đến) hoặc đã phát hành (đi) mới vào hồ sơ (đang: %)', doc.status
      using errcode = 'check_violation';
  end if;
  return new;
end
$$;

create trigger case_file_documents_check before insert on office.case_file_documents
  for each row execute function office.case_file_documents_check();

-- Gỡ văn bản khỏi hồ sơ chỉ khi hồ sơ còn mở
create function office.case_file_documents_locked() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
declare
  cur text;
begin
  -- khóa dòng hồ sơ như lúc thêm: gỡ văn bản cuối cùng cùng lúc đóng hồ sơ thì một bên đợi, không ra hồ sơ đóng rỗng
  select cf.status into cur from office.case_files cf where cf.id = old.case_file_id for share;
  if cur <> 'open' then
    raise exception 'hồ sơ đã đóng, không gỡ văn bản được' using errcode = 'check_violation';
  end if;
  return old;
end
$$;

create trigger case_file_documents_locked before delete on office.case_file_documents
  for each row execute function office.case_file_documents_locked();

-- Hồ sơ đã nộp lưu thì không sửa được nữa (kể cả khóa quản trị qua Hasura); đóng rồi chỉ job nộp lưu chuyển tiếp.
-- Ngày đóng do CSDL đặt (ngày theo giờ Việt Nam lúc đóng), không do người dùng chọn: lùi ngày là ép nộp lưu ngay,
-- đẩy ngày là không bao giờ nộp lưu. Hồ sơ rỗng không đóng được.
create function office.case_files_transition() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
begin
  if old.status = 'archived' then
    raise exception 'hồ sơ % đã nộp lưu, không sửa được', old.code using errcode = 'check_violation';
  end if;
  if old.status = 'closed' and new.status = 'open' then
    raise exception 'hồ sơ % đã đóng, không mở lại được', old.code using errcode = 'check_violation';
  end if;
  if old.status = 'open' and new.status = 'closed' then
    if not exists (select 1 from office.case_file_documents where case_file_id = old.id) then
      raise exception 'hồ sơ % chưa có văn bản nào, không đóng được', old.code using errcode = 'check_violation';
    end if;
    new.closed_on := (now() at time zone 'Asia/Ho_Chi_Minh')::date;
  elsif new.closed_on is distinct from old.closed_on then
    raise exception 'ngày đóng hồ sơ do hệ thống đặt khi đóng, không sửa được' using errcode = 'check_violation';
  end if;
  return new;
end
$$;

create trigger case_files_transition before update on office.case_files
  for each row execute function office.case_files_transition();

create index case_files_closed on office.case_files (closed_on) where status = 'closed';

-- Tệp đã nộp lưu chỉ còn trong bucket lạnh: không gắn vào văn bản nào nữa, kể cả qua Action tiếp nhận (vai trò service)
create function office.document_files_hot_only() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
begin
  if exists (select 1 from core.files where id = new.file_id and storage_tier <> 'hot') then
    raise exception 'tệp đã nộp lưu vào kho lạnh, không gắn vào văn bản được' using errcode = 'check_violation';
  end if;
  return new;
end
$$;

create trigger document_files_hot_only before insert on office.document_files
  for each row execute function office.document_files_hot_only();

-- Nộp lưu: svc-files gọi sau khi gói đã nằm trong bucket lạnh và đọc lại khớp băm. Một giao dịch, khóa dòng hồ sơ,
-- văn bản, tệp; kiểm CSDL còn đúng như lúc chụp vào gói — hồ sơ vẫn `closed`, đúng các văn bản ấy, đúng các dòng thời
-- gian và liên kết tệp ấy (không có dòng mới sinh trong lúc ghi gói) — lệch một chỗ là raise, không đổi gì, lượt sau
-- làm lại. Hai lượt nộp lưu cùng lúc: lượt sau đợi khóa rồi thấy hồ sơ đã `archived`, rollback cả sự kiện sổ kiểm toán.
-- Chỉ khóa quản trị gọi được (hàm khai trong metadata không cấp quyền cho vai trò nào).
-- p: {id, archive_key, archive_sha256 (hex), bucket, documents: [uuid], events: [bigint],
--     links: [{document_id, file_id}], cold_files: [uuid], files: số tệp trong gói}
create function office.archive_case_file(p jsonb)
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


create trigger audit after insert or update or delete on office.case_files
  for each row execute function core.audit();
create trigger audit after insert or update or delete on office.case_file_documents
  for each row execute function core.audit('case_file_id', 'document_id');

-- Màn "Sổ kiểm toán": ký hiệu hồ sơ, ngày đóng, thời hạn bảo quản, băm gói lưu trữ không phải nội dung văn bản nên
-- được thấy; tên hồ sơ do người dùng đặt (như trích yếu) vẫn ẩn. Dòng case_file.archived (svc-files ghi) hiện ký hiệu,
-- băm manifest, số văn bản, số tệp; case_file.read hiện ký hiệu và băm.
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
