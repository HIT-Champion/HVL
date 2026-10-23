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

-- Văn bản hạn chế (F3.7): tệp lưu mã hóa (svc-files, khóa dữ liệu bọc bằng transit của két), danh sách người được xem.
--
-- 1. Tệp của văn bản hạn chế phải là tệp mã hóa, tệp mã hóa chỉ gắn vào văn bản hạn chế — giữ ở CSDL cho mọi đường
--    ghi (Action tiếp nhận, dự thảo văn bản đi ghi thẳng qua Hasura, bản phát hành). Văn bản đã có tệp thì không đổi
--    chế độ hạn chế được: tệp đã lưu rõ không tự mã hóa lại. Văn bản hạn chế có từ trước F3.7 vẫn giữ tệp rõ của nó
--    (trigger chỉ kiểm khi gắn tệp, khi đổi chế độ).
-- 2. Văn thư, lãnh đạo đơn vị cấp / gỡ quyền xem văn bản hạn chế mà chính họ đang đọc được (hai hàm bên dưới, đưa
--    ra thành mutation của Hasura). Người được cấp vẫn phải có quyền theo vai trò (phòng, giao việc) như mọi văn bản;
--    văn thư và lãnh đạo đơn vị chỉ cần có tên trong danh sách. Bảng office.document_acl đã có trigger sổ kiểm toán.
-- 3. Tệp mã hóa không bao giờ có lớp chữ (core.file_texts) — thêm vào trigger bỏ qua của F2.7.
-- 4. Thông báo (F2.5) về văn bản hạn chế không mang trích yếu, số ký hiệu, ý kiến — chỉ nhãn "hạn chế": dịch vụ ghi
--    bằng vai trò service, đọc được mọi văn bản, nên CSDL gọt nội dung cho mọi đường ghi (giao việc, nhắc hạn, quá
--    hạn, phát hành); bản đẩy qua Centrifugo lấy đúng dòng đã ghi. Văn bản chuyển sang hạn chế thì gọt cả thông
--    báo cũ.
-- 5. Sổ kiểm toán (F2.12): lãnh đạo, quản trị đơn vị vẫn thấy ai làm gì với văn bản hạn chế, nhưng dòng của văn bản
--    mà họ không đọc được chỉ còn tên cột đã đổi (trạng thái, độ khẩn, hạn, người ký… cũng ẩn).
-- 6. Văn bản hạn chế không công khai trích yếu ở cổng xác thực (is_public): cổng không cần đăng nhập.
-- Lỗi mang tên ràng buộc ở đầu câu (như lỗi check của PostgreSQL) để giao diện, svc-workflow dịch thành câu dễ hiểu.

create function office.document_files_sealed() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
declare
  is_restricted boolean;
  is_encrypted  boolean;
begin
  -- khóa dòng văn bản: đổi chế độ hạn chế (trigger dưới) và gắn tệp chạy song song thì lần sau đợi lần trước xong,
  -- không thì mỗi bên chỉ thấy trạng thái cũ của bên kia và lọt tệp rõ vào văn bản hạn chế
  select d.restricted into is_restricted from office.documents d
   where d.tenant_id = new.tenant_id and d.id = new.document_id
     for share;
  select f.encrypted into is_encrypted from core.files f
   where f.tenant_id = new.tenant_id and f.id = new.file_id;
  -- không thấy văn bản hoặc tệp: để khóa ngoại báo lỗi
  if is_restricted and not is_encrypted then
    raise exception 'document_files_sealed: văn bản hạn chế chỉ gắn tệp tải lên ở chế độ hạn chế (đã mã hóa)'
      using errcode = 'check_violation';
  end if;
  if not is_restricted and is_encrypted then
    raise exception 'document_files_sealed: tệp đã mã hóa chỉ gắn vào văn bản hạn chế'
      using errcode = 'check_violation';
  end if;
  return new;
end
$$;

create trigger document_files_sealed before insert or update of tenant_id, document_id, file_id
  on office.document_files
  for each row execute function office.document_files_sealed();

create function office.documents_restricted_sealed() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
begin
  if exists (select 1 from office.document_files l
               join core.files f on f.tenant_id = l.tenant_id and f.id = l.file_id
              where l.tenant_id = new.tenant_id and l.document_id = new.id and f.encrypted <> new.restricted) then
    raise exception 'documents_restricted_sealed: văn bản đã có tệp nên không đổi được chế độ hạn chế'
      using errcode = 'check_violation';
  end if;
  return new;
end
$$;

create trigger documents_restricted_sealed before update of restricted on office.documents
  for each row when (new.restricted is distinct from old.restricted)
  execute function office.documents_restricted_sealed();

-- Lớp chữ (F2.7): bỏ qua cả tệp mã hóa — chưa gắn vào văn bản nào cũng vậy
create or replace function core.file_texts_skip_restricted() returns trigger
language plpgsql as $$
begin
  if exists (select 1 from core.files f where f.id = new.file_id and f.encrypted)
     or exists (select 1 from office.document_files f
                  join office.documents d on d.tenant_id = f.tenant_id and d.id = f.document_id
                 where f.file_id = new.file_id and d.restricted) then
    return null;
  end if;
  return new;
end $$;

-- ---------------------------------------------------------------------------
-- Danh sách người được xem văn bản hạn chế. hasura_session do Hasura truyền vào: đơn vị, người cấp, vai trò lấy từ
-- phiên. Văn bản không có, của đơn vị khác hoặc người gọi không đọc được thì báo như nhau.
-- ---------------------------------------------------------------------------

create function office.document_acl_target(document_id uuid, hasura_session json)
returns office.documents
language plpgsql volatile set search_path = pg_catalog, pg_temp
as $$
declare
  doc office.documents;
begin
  if coalesce(hasura_session ->> 'x-hasura-role', '') not in ('clerk', 'director') then
    raise exception 'chỉ văn thư và lãnh đạo đơn vị quản lý danh sách xem văn bản hạn chế'
      using errcode = 'insufficient_privilege';
  end if;
  select * into doc from office.documents d
   where d.id = document_acl_target.document_id
     and d.tenant_id::text = hasura_session ->> 'x-hasura-tenant-id'
     for update;
  if not found or not office.document_visible(doc, hasura_session) then
    raise exception 'không có văn bản %', document_acl_target.document_id using errcode = 'invalid_parameter_value';
  end if;
  if not doc.restricted then
    raise exception 'văn bản không hạn chế: người có quyền theo vai trò đều đã xem được'
      using errcode = 'check_violation';
  end if;
  return doc;
end
$$;

create function office.grant_document_access(document_id uuid, user_id text, hasura_session json)
returns setof office.document_acl
language plpgsql volatile set search_path = pg_catalog, pg_temp
as $$
declare
  doc office.documents := office.document_acl_target(grant_document_access.document_id, hasura_session);
begin
  if not exists (select 1 from core.users u
                  where u.id = grant_document_access.user_id and u.tenant_id = doc.tenant_id and u.enabled) then
    raise exception 'không có người dùng % trong đơn vị', grant_document_access.user_id
      using errcode = 'invalid_parameter_value';
  end if;
  insert into office.document_acl as a (tenant_id, document_id, user_id, granted_by)
  values (doc.tenant_id, doc.id, grant_document_access.user_id, hasura_session ->> 'x-hasura-user-id')
  on conflict on constraint document_acl_pkey do nothing;   -- cấp lại: giữ người cấp, giờ cấp lần đầu
  return query select * from office.document_acl a
                where a.document_id = doc.id and a.user_id = grant_document_access.user_id;
end
$$;

create function office.revoke_document_access(document_id uuid, user_id text, hasura_session json)
returns setof office.document_acl
language plpgsql volatile set search_path = pg_catalog, pg_temp
as $$
declare
  doc office.documents := office.document_acl_target(revoke_document_access.document_id, hasura_session);
begin
  if revoke_document_access.user_id = hasura_session ->> 'x-hasura-user-id' then
    raise exception 'không tự gỡ quyền xem của chính mình' using errcode = 'check_violation';
  end if;
  return query delete from office.document_acl a
                where a.document_id = doc.id and a.user_id = revoke_document_access.user_id
            returning a.*;
end
$$;

-- ---------------------------------------------------------------------------
-- Thông báo về văn bản hạn chế: chỉ nhãn, không nội dung
-- ---------------------------------------------------------------------------

create function office.notification_redacted(data jsonb) returns jsonb
language sql immutable
as $$ select (data - 'summary' - 'symbol' - 'issuer_name' - 'note') || '{"restricted": true}' $$;

create function office.notifications_restricted() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
begin
  if new.document_id is not null and exists (select 1 from office.documents d
                                              where d.tenant_id = new.tenant_id and d.id = new.document_id
                                                and d.restricted) then
    new.data := office.notification_redacted(new.data);
  end if;
  return new;
end
$$;

create trigger notifications_restricted before insert or update of data, document_id on core.notifications
  for each row execute function office.notifications_restricted();

create function office.documents_restricted_notifications() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
begin
  update core.notifications n set data = office.notification_redacted(n.data)
   where n.tenant_id = new.tenant_id and n.document_id = new.id;
  return null;
end
$$;

create trigger documents_restricted_notifications after update of restricted on office.documents
  for each row when (new.restricted and not old.restricted)
  execute function office.documents_restricted_notifications();

-- ---------------------------------------------------------------------------
-- Sổ kiểm toán theo người xem: trường overview (core_audit_log) gọi hàm này với phiên Hasura. Nằm ở schema office
-- vì phải đọc văn bản (core không phụ thuộc office).
-- ---------------------------------------------------------------------------

create function office.audit_overview_seen(r core.audit_log, hasura_session json) returns jsonb
language plpgsql stable set search_path = pg_catalog, pg_temp
as $$
declare
  overview jsonb := core.audit_overview(r);
  doc_id   text;
  doc      office.documents;
  uuid_re  constant text := '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
begin
  if overview = '{}'::jsonb then
    return overview;
  end if;
  -- văn bản của dòng sổ: khóa của trigger core.audit() (migration 1792281600200, 1792281601300)
  doc_id := case r.entity
              when 'office.documents' then r.entity_id
              when 'office.document_files' then split_part(r.entity_id, '/', 1)
              when 'office.document_acl' then split_part(r.entity_id, '/', 1)
              when 'office.case_file_documents' then split_part(r.entity_id, '/', 2)
              when 'office.assignments' then case when r.entity_id ~ uuid_re then
                                               (select s.document_id::text from office.assignments s
                                                 where s.id = r.entity_id::uuid) end
            end;
  -- so theo uuid để dùng khóa chính (mỗi dòng sổ trả về gọi hàm này một lần)
  if doc_id is null or doc_id !~ uuid_re then
    return overview;
  end if;
  select * into doc from office.documents d where d.id = doc_id::uuid and d.tenant_id = r.tenant_id;
  if found and doc.restricted and not coalesce(office.document_visible(doc, hasura_session), false) then
    return (select jsonb_object_agg(k, null) from jsonb_object_keys(overview) as k);
  end if;
  return overview;
end
$$;

-- ---------------------------------------------------------------------------
-- Văn bản hạn chế không công khai trích yếu ở cổng xác thực
-- ---------------------------------------------------------------------------

alter table office.documents
  add constraint documents_restricted_private check (not (restricted and is_public)) not valid;
do $$
begin
  alter table office.documents validate constraint documents_restricted_private;
exception when check_violation then
  raise warning 'Văn bản hạn chế cũ đang công khai trích yếu (đặt is_public = false rồi validate lại %): %',
    'documents_restricted_private',
    (select string_agg(id::text, ', ') from office.documents where restricted and is_public);
end
$$;

-- cổng xác thực cũng không đọc trích yếu của văn bản hạn chế, kể cả dòng cũ chưa sửa
create or replace view office.issued_documents as
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
