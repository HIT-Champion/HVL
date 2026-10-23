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

-- Liên thông văn bản trong hệ thống (F3.12): văn bản đi chọn đơn vị nhận là đơn vị khác dùng Signet; văn thư phát
-- hành thì mỗi đơn vị nhận có một văn bản đến `received` (source_id trỏ về văn bản đi), kèm bản sao tệp phát hành.
-- Mô tả:
-- docs/mo-hinh-du-lieu.md §2.2 (bảng), §4.2 (luồng, đúng một lần), §5 (sự kiện).
--
-- Đúng một lần, kể cả khi dịch vụ chết giữa chừng hay chạy nhiều bản sao:
-- - Hộp thư đi (outbox): trigger tạo một dòng `pending` cho mỗi đơn vị nhận ngay trong giao dịch phát hành
--   (ràng buộc dispatches_once). svc-workflow giao sau khi phát hành và vòng đối soát giao lại dòng còn chờ —
--   không dòng nào chỉ nằm trong bộ nhớ của dịch vụ.
-- - Giao: hàm office.deliver_dispatch khóa dòng, gọi lại khi đã giao thì trả nguyên dòng; chỉ mục
--   documents_source_once chặn văn bản đến thứ hai của cùng văn bản gửi, kể cả khi mọi lớp trên có lỗi.
-- - Tệp: id của bản sao (dispatches.file_id) định sẵn từ lúc tạo dòng, svc-files chép lại thì trùng khóa chính.
--
-- Văn bản hạn chế (F3.7) không liên thông: tệp của nó mã hóa gắn với đơn vị và tệp (AAD), đơn vị nhận không mở được,
-- và danh sách người được xem không sang được đơn vị khác (ràng buộc documents_restricted_local).
-- Lỗi mang tên ràng buộc ở đầu câu để giao diện, svc-workflow dịch thành câu dễ hiểu.

-- ---------------------------------------------------------------------------
-- Làm sạch chuỗi như bước dọn dữ liệu của migration 1792281600800_intake_rules (pg_temp.moc_clean): NFC; one_line
-- thì tab, xuống dòng thành dấu cách; bỏ ký tự vô hình, khoảng trắng hai đầu. Trích yếu văn bản đi không phải theo
-- các ràng buộc documents_in_*, nên văn bản đến dựng từ nó phải làm sạch trước khi ghi.
-- ---------------------------------------------------------------------------

create function office.clean_text(t text, one_line boolean) returns text
language sql immutable
as $$
  select regexp_replace(regexp_replace(
           case when one_line then regexp_replace(normalize(t, nfc), '[\t\n\v\f\r\u2028\u2029]+', ' ', 'g')
                else regexp_replace(regexp_replace(normalize(t, nfc), '[\t\v\f]+', ' ', 'g'),
                                    '[\u2028\u2029]', E'\n', 'g') end,
           '[\u0001-\u0009\u000b\u000c\u000e-\u001f\u007f-\u009f\u00ad\u115f\u1160\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\u3164\ufeff\uffa0\u2028\u2029]', '', 'g'),
         '^[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+|[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+$', '', 'g')
$$;

-- ---------------------------------------------------------------------------
-- Đơn vị nhận trong hệ thống
-- ---------------------------------------------------------------------------

alter table office.documents
  add column recipient_tenant_ids uuid[] not null default '{}',
  add constraint documents_recipient_units_out   check (direction = 'out' or recipient_tenant_ids = '{}'),
  add constraint documents_recipient_units_other check (not (tenant_id = any (recipient_tenant_ids))),
  add constraint documents_restricted_local      check (not (restricted and recipient_tenant_ids <> '{}'));

-- mỗi văn bản gửi sinh nhiều nhất một văn bản đến ở mỗi đơn vị (văn bản đến đã hủy vẫn giữ chỗ: không giao lại)
create unique index documents_source_once on office.documents (tenant_id, source_id) where source_id is not null;

-- Bỏ trùng, xếp theo id (sổ kiểm toán không ghi một lần sửa chỉ vì đổi thứ tự tích chọn); mọi id phải là đơn vị có
-- trong hệ thống. Đã trình (khác draft, returned) thì không đổi được nữa: đơn vị nhận là một phần nội dung văn bản
-- người ký đã duyệt.
create function office.documents_recipient_units() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
begin
  new.recipient_tenant_ids := array(select distinct u from unnest(new.recipient_tenant_ids) as u order by u);
  if tg_op = 'UPDATE' then
    if old.status not in ('draft', 'returned')
       and new.recipient_tenant_ids is distinct from old.recipient_tenant_ids then
      raise exception 'documents_recipient_units: đơn vị nhận chỉ sửa được khi văn bản còn là dự thảo'
        using errcode = 'check_violation';
    end if;
  end if;
  if exists (select 1 from unnest(new.recipient_tenant_ids) as u
              where u is null or not exists (select 1 from core.tenants t where t.id = u)) then
    raise exception 'documents_recipient_units: có đơn vị nhận không thuộc hệ thống'
      using errcode = 'check_violation';
  end if;
  return new;
end
$$;

create trigger documents_recipient_units before insert or update of recipient_tenant_ids on office.documents
  for each row execute function office.documents_recipient_units();

-- Danh sách đơn vị để chọn khi soạn. Người dùng chỉ đọc được dòng core.tenants của chính mình (core_tenants.yaml),
-- nên view riêng chỉ có tên; Hasura lọc bỏ đơn vị của người xem.
create view office.dispatch_units as
select id, code, name, parent_name from core.tenants;

-- ---------------------------------------------------------------------------
-- Hộp thư đi: một dòng cho mỗi (văn bản gửi, đơn vị nhận)
-- ---------------------------------------------------------------------------

create table office.dispatches (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references core.tenants,     -- đơn vị gửi
  document_id           uuid not null,                             -- văn bản đi
  to_tenant_id          uuid not null references core.tenants,     -- đơn vị nhận
  status                text not null default 'pending'
                        check (status in ('pending', 'delivered', 'duplicate', 'failed')),
  file_id               uuid not null default gen_random_uuid(),   -- id bản sao tệp ở đơn vị nhận, định trước
  incoming_document_id  uuid unique,                               -- văn bản đến ở đơn vị nhận
  -- chụp lúc phát hành: văn bản đến không mang được mã tra cứu, băm (cả hai unique trên office.documents)
  source_verify_code    text not null,
  source_sha256         bytea not null,
  attempts              int not null default 0,                    -- số lần giao lỗi (svc-workflow đếm)
  last_error            text,
  next_attempt_at       timestamptz not null default now(),
  notified_at           timestamptz,                               -- đã báo văn thư đơn vị nhận
  delivered_at          timestamptz,
  created_at            timestamptz not null default now(),
  constraint dispatches_once unique (document_id, to_tenant_id),
  constraint dispatches_not_self check (to_tenant_id <> tenant_id),
  constraint dispatches_linked check ((status in ('delivered', 'duplicate')) = (incoming_document_id is not null)),
  foreign key (tenant_id, document_id) references office.documents (tenant_id, id),
  foreign key (to_tenant_id, incoming_document_id) references office.documents (tenant_id, id)
);

-- vòng đối soát của svc-workflow: dòng chờ đến hạn, dòng đã giao mà chưa báo
create index dispatches_due on office.dispatches (next_attempt_at) where status = 'pending' or notified_at is null;

-- tenant_id của dòng là đơn vị gửi: lần giao (chạy trong phiên của đơn vị nhận) vào sổ của đơn vị gửi, văn bản đến
-- và tệp của nó vào sổ của đơn vị nhận — cùng một giao dịch, hai sổ đều có
create trigger audit after insert or update or delete on office.dispatches
  for each row execute function core.audit();

-- Phát hành: một dòng pending cho mỗi đơn vị nhận, trong cùng giao dịch với trạng thái issued. Chỉ chạy lúc chuyển
-- sang issued; gặp lại (ai đó đưa trạng thái về rồi phát hành lại) thì dòng đã có giữ nguyên.
create function office.documents_dispatch() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
begin
  insert into office.dispatches (tenant_id, document_id, to_tenant_id, source_verify_code, source_sha256)
  select new.tenant_id, new.id, r, new.verify_code, new.content_sha256
    from unnest(new.recipient_tenant_ids) as r
  on conflict on constraint dispatches_once do nothing;
  return null;
end
$$;

create trigger documents_dispatch after update of status on office.documents
  for each row
  when (new.direction = 'out' and new.status = 'issued' and old.status <> 'issued' and new.recipient_tenant_ids <> '{}')
  execute function office.documents_dispatch();

-- Nộp lưu (F3.8) gỡ dòng thời gian, tệp của văn bản: chưa giao xong thì chưa nộp lưu. serialization_failure để job
-- nộp lưu của svc-files coi như CSDL đổi giữa chừng và thử lại ở lượt sau.
create function office.documents_dispatch_pending() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
begin
  if exists (select 1 from office.dispatches x where x.document_id = new.id and x.status = 'pending') then
    raise exception 'documents_dispatch_pending: văn bản còn đang gửi liên thông, chưa nộp lưu được'
      using errcode = 'serialization_failure';
  end if;
  return new;
end
$$;

create trigger documents_dispatch_pending before update of status on office.documents
  for each row when (new.status = 'archived' and old.status <> 'archived')
  execute function office.documents_dispatch_pending();

-- ---------------------------------------------------------------------------
-- Giao một dòng: tạo văn bản đến ở đơn vị nhận. Chỉ vai trò service gọi được (svc-workflow, sau khi svc-files đã chép
-- tệp sang đơn vị nhận với id = dispatches.file_id); gọi trong phiên của đơn vị NHẬN — thuê ước và người thực hiện
-- lấy từ hasura_session, dòng của đơn vị khác báo như không có.
--
-- - Đã giao (hoặc đã đánh dấu trùng, lỗi) từ lần gọi trước: trả nguyên dòng.
-- - Đơn vị nhận đã có văn bản đến trùng (cùng khóa của documents_in_dedup — tiếp nhận tay từ bản giấy, thư điện tử):
--   `duplicate`, nối vào văn bản đó, không thêm bản thứ hai.
-- - Văn bản đến vi phạm ràng buộc (trích yếu sau khi làm sạch quá ngắn, tệp đã sang kho lạnh…): `failed` kèm tên
--   ràng buộc (hoặc câu tiếng Việt của trigger chặn), không ghi gì khác; văn thư bên nhận tiếp nhận tay chen đúng lúc
--   ghi (documents_in_dedup): `duplicate`.
-- - Bản sao tệp ở đơn vị nhận khác băm bản phát hành: `failed`. Chưa có tệp ở đơn vị nhận (khóa ngoại): lỗi, dòng
--   vẫn `pending` để lượt sau giao lại.
-- ---------------------------------------------------------------------------

create function office.deliver_dispatch(dispatch_id uuid, hasura_session json)
returns setof office.dispatches
language plpgsql volatile set search_path = pg_catalog, pg_temp
as $$
declare
  tenant         uuid := (hasura_session ->> 'x-hasura-tenant-id')::uuid;
  actor          text := hasura_session ->> 'x-hasura-user-id';
  x              office.dispatches;
  src            office.documents;
  sender_name    text;
  receiver_name  text;
  issuer         text;
  sym            text;
  dup            uuid;
  doc_id         uuid;
  failed_on      text;
  failed_msg     text;
begin
  -- khóa dòng: hai lần giao chen nhau (svc-workflow sau phát hành và vòng đối soát, nhiều bản sao dịch vụ) thì lần
  -- sau đợi lần trước xong rồi thấy dòng đã giao
  select * into x
    from office.dispatches d
   where d.id = deliver_dispatch.dispatch_id and d.to_tenant_id = tenant
     for update;
  if not found then
    raise exception 'không có lượt gửi liên thông % tới đơn vị này', deliver_dispatch.dispatch_id
      using errcode = 'invalid_parameter_value';
  end if;
  if x.status <> 'pending' then
    return next x;                            -- đã giao từ lần gọi trước
    return;
  end if;

  select * into strict src from office.documents d where d.tenant_id = x.tenant_id and d.id = x.document_id;
  select t.name into strict sender_name from core.tenants t where t.id = x.tenant_id;
  select t.name into strict receiver_name from core.tenants t where t.id = x.to_tenant_id;

  if src.direction <> 'out' or src.status not in ('issued', 'archived') or src.restricted then
    update office.dispatches d
       set status = 'failed',
           last_error = format('văn bản gửi đang ở trạng thái %s%s, không giao liên thông được', src.status,
                               case when src.restricted then ', hạn chế' else '' end)
     where d.id = x.id
    returning d.* into x;
    return next x;
    return;
  end if;

  -- lớp kiểm thứ hai sau svc-files: bản sao đã có ở đơn vị nhận phải cùng băm với bản phát hành chụp lúc phát hành
  -- (chưa có tệp thì khóa ngoại của document_files báo lỗi bên dưới, dòng vẫn pending)
  if exists (select 1 from core.files f
              where f.tenant_id = tenant and f.id = x.file_id and f.sha256 is distinct from x.source_sha256) then
    update office.dispatches d
       set status = 'failed', last_error = 'tệp chép sang đơn vị nhận không khớp băm bản phát hành'
     where d.id = x.id
    returning d.* into x;
    return next x;
    return;
  end if;

  issuer := office.clean_text(sender_name, true);
  sym := office.clean_text(src.symbol, true);

  begin
    select d.id into dup
      from office.documents d
     where d.tenant_id = tenant and d.direction = 'in' and d.status <> 'cancelled'
       and lower(d.issuer_name) = lower(issuer) and d.symbol = sym and d.issued_on = src.issued_on;

    if found then
      update office.dispatches d
         set status = 'duplicate', incoming_document_id = dup, delivered_at = now(), last_error = null
       where d.id = x.id
      returning d.* into x;
      insert into office.document_events (tenant_id, document_id, kind, actor_id, actor_kind, data)
      values (x.tenant_id, x.document_id, 'office.document.dispatch_duplicate', actor, 'service',
              jsonb_build_object('dispatch_id', x.id, 'to_tenant_id', x.to_tenant_id, 'to_name', receiver_name));
    else
      insert into office.documents (tenant_id, direction, status, type_code, symbol, issuer_name, issued_on, summary,
                                    urgency, source_id, created_by)
      values (tenant, 'in', 'received', src.type_code, sym, issuer, src.issued_on,
              office.clean_text(src.summary, false), src.urgency, src.id, actor)
      returning id into doc_id;

      insert into office.document_files (tenant_id, document_id, file_id, role, added_by)
      values (tenant, doc_id, x.file_id, 'main', actor);

      insert into office.document_events (tenant_id, document_id, kind, actor_id, actor_kind, data)
      values (tenant, doc_id, 'office.document.arrived', actor, 'service',
              jsonb_build_object('dispatch_id', x.id, 'from_tenant_id', x.tenant_id, 'from_name', sender_name,
                                 'verify_code', x.source_verify_code)),
             (x.tenant_id, x.document_id, 'office.document.dispatched', actor, 'service',
              jsonb_build_object('dispatch_id', x.id, 'to_tenant_id', x.to_tenant_id, 'to_name', receiver_name));

      update office.dispatches d
         set status = 'delivered', incoming_document_id = doc_id, delivered_at = now(), last_error = null
       where d.id = x.id
      returning d.* into x;
    end if;
  exception when check_violation or unique_violation then
    -- mọi thứ ghi trong khối đã quay lui
    get stacked diagnostics failed_on = constraint_name, failed_msg = message_text;
    dup := null;
    if failed_on = 'documents_in_dedup' then
      -- văn thư bên nhận vừa tiếp nhận tay đúng văn bản này, chen giữa lúc kiểm trùng và lúc ghi: như trùng
      select d.id into dup
        from office.documents d
       where d.tenant_id = tenant and d.direction = 'in' and d.status <> 'cancelled'
         and lower(d.issuer_name) = lower(issuer) and d.symbol = sym and d.issued_on = src.issued_on;
    end if;
    if dup is not null then
      update office.dispatches d
         set status = 'duplicate', incoming_document_id = dup, delivered_at = now(), last_error = null
       where d.id = x.id
      returning d.* into x;
      insert into office.document_events (tenant_id, document_id, kind, actor_id, actor_kind, data)
      values (x.tenant_id, x.document_id, 'office.document.dispatch_duplicate', actor, 'service',
              jsonb_build_object('dispatch_id', x.id, 'to_tenant_id', x.to_tenant_id, 'to_name', receiver_name));
    else
      -- giao lại cũng ra lỗi đó: đánh dấu hỏng. Ràng buộc check/unique: ghi tên ràng buộc (câu của PostgreSQL là
      -- tiếng Anh, kèm tên bảng); trigger chặn (document_files_hot_only…) không có tên ràng buộc mà có câu tiếng Việt
      update office.dispatches d
         set status = 'failed',
             last_error = case when coalesce(failed_on, '') = '' then left(failed_msg, 500)
                               else format('đơn vị nhận không tạo được văn bản đến (ràng buộc %s)', failed_on) end
       where d.id = x.id
      returning d.* into x;
    end if;
  end;

  return next x;
end
$$;

-- ---------------------------------------------------------------------------
-- Đánh dấu hỏng một dòng còn chờ: svc-files từ chối chép vĩnh viễn (tệp nguồn sai băm, đã sang kho lạnh, văn bản
-- không còn phát hành, trạm quét chặn) — thử lại cũng vậy, mà dòng `pending` còn chặn nộp lưu văn bản gửi. Chỉ vai
-- trò service (svc-workflow), trong phiên của bên gửi hoặc bên nhận; dòng đã giao thì giữ nguyên.
-- ---------------------------------------------------------------------------

create function office.fail_dispatch(dispatch_id uuid, reason text, hasura_session json)
returns setof office.dispatches
language plpgsql volatile set search_path = pg_catalog, pg_temp
as $$
declare
  tenant uuid := (hasura_session ->> 'x-hasura-tenant-id')::uuid;
begin
  return query
  with u as (
    update office.dispatches d
       set status = 'failed', last_error = left(coalesce(nullif(btrim(reason), ''), 'không chuyển được'), 500)
     where d.id = fail_dispatch.dispatch_id and d.status = 'pending'
       and (d.tenant_id = tenant or d.to_tenant_id = tenant)
    returning d.*)
  select * from u;
end
$$;

-- ---------------------------------------------------------------------------
-- Sổ kiểm toán: cột chỉ chứa id, số đếm, thời điểm của lần gửi liên thông được thấy (màn Sổ kiểm toán, tab Lịch sử).
-- Băm, mã tra cứu chụp từ văn bản gửi (source_sha256, source_verify_code) và lỗi (last_error) vẫn ẩn. Còn lại như
-- migration 1792281601300.
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
           then r.diff -> k end), '{}'::jsonb)
      from jsonb_object_keys(r.diff) as k
  ) end
$$;

-- Lịch sử của văn bản gửi (F3.5): thêm các lần gửi liên thông. Dòng sổ mang tenant_id của đơn vị gửi nên chỉ hiện ở
-- văn bản đi; văn bản đến bên nhận có lịch sử riêng (dòng thêm văn bản, tệp — trong sổ của đơn vị nhận).
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
  join core.audit_log a on a.entity = 'office.assignments' and a.entity_id = x.id::text and a.tenant_id = x.tenant_id
union all
select a.id, a.tenant_id, x.document_id, a.occurred_at, a.actor_id, a.actor_kind, a.action, a.entity,
       core.audit_overview(a)
  from office.dispatches x
  join core.audit_log a on a.entity = 'office.dispatches' and a.entity_id = x.id::text and a.tenant_id = x.tenant_id;
