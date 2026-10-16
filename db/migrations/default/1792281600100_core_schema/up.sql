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

-- Schema core: dữ liệu dùng chung của lõi — thuê ước, tệp đã kiểm dịch, sổ kiểm toán chuỗi băm.
-- Mô tả và lý do: docs/mo-hinh-du-lieu.md §1.

create schema core;

create table core.tenants (                 -- cơ quan, đơn vị dùng hệ thống
  id          uuid primary key default gen_random_uuid(),
  code        text not null unique
              check (code ~ '^[^[:space:]/-]{1,20}$'),  -- viết tắt trong ký hiệu văn bản; '/' và '-' là dấu phân cách
  name        text not null check (btrim(name) <> ''),
  org_ident   text unique check (char_length(org_ident) = 13),  -- mã định danh theo QCVN 102 (tùy chọn)
  created_at  timestamptz not null default now()
);

create table core.files (                   -- tệp đã qua kiểm dịch; tệp nhiễm không có dòng ở đây
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references core.tenants,
  object_key    text not null unique,
  filename      text not null check (char_length(filename) between 1 and 255),
  mime_type     text not null check (mime_type ~ '^[[:alnum:]_.+-]+/[[:alnum:]_.+-]+$'),
  size_bytes    bigint not null check (size_bytes > 0),
  sha256        bytea  not null check (octet_length(sha256) = 32),
  scanned_at    timestamptz not null,        -- thời điểm ClamAV trả kết quả sạch
  encrypted     boolean not null default false,
  wrapped_dek   text,                        -- khóa dữ liệu đã bọc bởi OpenBao Transit (F3.7)
  storage_tier  text not null default 'hot' check (storage_tier in ('hot', 'cold')),
  created_by    text not null,               -- sub Keycloak của người tải lên
  created_at    timestamptz not null default now(),
  unique (tenant_id, id),                    -- đích của khóa ngoại kèm thuê ước
  constraint files_encryption_key check (encrypted = (wrapped_dek is not null)),
  -- khóa đối tượng phải nằm dưới tiền tố của đúng thuê ước: tenant/<tenant_id>/<yyyy>/<mm>/<id>
  constraint files_object_key_tenant check (object_key like 'tenant/' || tenant_id || '/%')
);

create index files_tenant_created on core.files (tenant_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Sổ kiểm toán chuỗi băm (F2.12)
--
-- Mỗi dòng mang hash của dòng trước; sửa một dòng thì hash của nó không còn khớp, sửa cả hash thì
-- prev_hash của dòng sau không khớp. Đầu chuỗi (id, hash cuối) nằm trong core.audit_head: khóa dòng
-- này khiến các giao dịch ghi sổ xếp hàng, nên thứ tự id trùng thứ tự chuỗi.
-- ---------------------------------------------------------------------------

create table core.audit_log (
  id           bigint primary key,           -- trigger cấp, liên tiếp từ 1, không do người ghi chọn
  tenant_id    uuid references core.tenants, -- null: sự kiện của nền tảng
  occurred_at  timestamptz not null,
  actor_id     text not null,
  actor_kind   text not null check (actor_kind in ('user', 'service', 'agent', 'system')),
  request_id   text,                         -- X-Request-Id do APISIX gắn
  action       text not null,                -- insert | update | delete | tên sự kiện, vd 'file.rejected'
  entity       text not null,                -- 'office.documents'
  entity_id    text not null,
  diff         jsonb not null,               -- {cột: [giá trị cũ, giá trị mới]}
  prev_hash    bytea not null check (octet_length(prev_hash) = 32),
  hash         bytea not null unique check (octet_length(hash) = 32)
);

create index audit_log_tenant_time on core.audit_log (tenant_id, occurred_at);
create index audit_log_entity on core.audit_log (entity, entity_id);

create table core.audit_head (
  singleton  boolean primary key default true check (singleton),
  last_id    bigint not null,
  last_hash  bytea not null
);

insert into core.audit_head (last_id, last_hash) values (0, decode(repeat('00', 32), 'hex'));

create table core.audit_anchors (           -- hash đầu chuỗi đã neo ra ngoài CSDL
  id           bigint generated always as identity primary key,
  audit_id     bigint not null references core.audit_log,
  hash         bytea not null,
  location     text not null,                -- 's3://cold/anchors/…' hoặc 'git:anchors/…'
  anchored_at  timestamptz not null default now()
);

-- Băm một dòng sổ. Thời điểm lấy theo epoch (micro giây) để kết quả không phụ thuộc múi giờ của phiên;
-- jsonb::text luôn cho cùng một chuỗi với cùng một giá trị, nên tính lại được khi kiểm tra.
create function core.audit_hash(r core.audit_log) returns bytea
language sql stable
as $$
  select sha256(r.prev_hash || convert_to(jsonb_build_array(
    r.id, extract(epoch from r.occurred_at), r.tenant_id, r.actor_id, r.actor_kind,
    r.request_id, r.action, r.entity, r.entity_id, r.diff
  )::text, 'UTF8'))
$$;

create function core.audit_chain() returns trigger
language plpgsql security definer set search_path = pg_catalog, pg_temp
as $$
declare
  head core.audit_head;
begin
  -- Khóa đầu chuỗi đến hết giao dịch. READ COMMITTED: đợi rồi đọc bản mới nhất;
  -- REPEATABLE READ trở lên: lỗi tuần tự hóa thay vì rẽ nhánh chuỗi.
  select * into strict head from core.audit_head for update;
  new.id := head.last_id + 1;
  new.occurred_at := clock_timestamp();
  new.prev_hash := head.last_hash;
  new.hash := core.audit_hash(new);
  update core.audit_head set last_id = new.id, last_hash = new.hash;
  return new;
end
$$;

create trigger audit_chain before insert on core.audit_log
  for each row execute function core.audit_chain();

create function core.audit_append_only() returns trigger
language plpgsql
as $$
begin
  raise exception 'core.audit_log chỉ được ghi thêm, không sửa hay xóa'
    using errcode = 'insufficient_privilege';
end
$$;

create trigger audit_no_change before update or delete on core.audit_log
  for each row execute function core.audit_append_only();
create trigger audit_no_truncate before truncate on core.audit_log
  for each statement execute function core.audit_append_only();

-- Kiểm lại toàn bộ chuỗi. Không có dòng nào trả về nghĩa là chuỗi nguyên vẹn.
--   gap        thiếu dòng ngay trước audit_id
--   prev_hash  prev_hash không bằng hash của dòng trước (dòng trước bị sửa cả hash, hoặc bị xóa)
--   hash       nội dung dòng không còn khớp hash của nó
--   head       core.audit_head không trỏ vào dòng cuối (dòng cuối bị xóa)
create function core.audit_verify()
returns table (audit_id bigint, problem text)
language plpgsql stable
as $$
declare
  r core.audit_log;
  expect_id bigint := 1;
  expect_prev bytea := decode(repeat('00', 32), 'hex');
  head core.audit_head;
begin
  for r in select * from core.audit_log l order by l.id loop
    if r.id <> expect_id then
      audit_id := r.id; problem := 'gap'; return next;
    end if;
    if r.prev_hash <> expect_prev then
      audit_id := r.id; problem := 'prev_hash'; return next;
    end if;
    if core.audit_hash(r) <> r.hash then
      audit_id := r.id; problem := 'hash'; return next;
    end if;
    expect_id := r.id + 1;
    expect_prev := r.hash;
  end loop;

  select * into strict head from core.audit_head;
  if head.last_id <> expect_id - 1 or head.last_hash <> expect_prev then
    audit_id := head.last_id; problem := 'head'; return next;
  end if;
end
$$;

-- Trigger gắn vào bảng nghiệp vụ: mỗi dòng thêm, sửa, xóa thành một dòng sổ.
-- Tham số trigger: các cột khóa ghép thành entity_id (mặc định 'id').
-- Người thực hiện:
--   qua Hasura   — biến phiên hasura.user (vai trò service → 'service', admin → 'system', còn lại 'user')
--   ghi thẳng CSDL — set local moc.actor / moc.actor_kind / moc.request_id trước khi ghi
create function core.audit() returns trigger
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

create trigger audit after insert or update or delete on core.tenants
  for each row execute function core.audit();
create trigger audit after insert or update or delete on core.files
  for each row execute function core.audit();
