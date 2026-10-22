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

-- Danh bạ người dùng (đồng bộ từ Keycloak) và cấp số đến trong một giao dịch.
-- Mô tả: docs/mo-hinh-du-lieu.md §1 (core.users) và §4.1 (registerIncoming).

-- ---------------------------------------------------------------------------
-- Danh bạ: bản sao chỉ đọc của người dùng Keycloak, để giao diện chọn người được giao việc và hiện
-- tên trên dòng thời gian. Keycloak là nguồn sự thật; svc-workflow đồng bộ định kỳ, không ai sửa tay.
-- ---------------------------------------------------------------------------

create table core.users (
  id             text primary key,             -- sub của Keycloak
  tenant_id      uuid not null references core.tenants,
  department_id  uuid,                          -- office.departments; không đặt khóa ngoại: core không phụ thuộc office
  username       text not null,
  full_name      text not null check (btrim(full_name) <> ''),
  email          text,
  role           text not null check (role in ('clerk', 'staff', 'manager', 'director', 'tenant_admin')),
  enabled        boolean not null default true,
  unique (tenant_id, id)
);

create index users_tenant_department on core.users (tenant_id, department_id) where enabled;

create trigger audit after insert or update or delete on core.users
  for each row execute function core.audit();

-- ---------------------------------------------------------------------------
-- Vào sổ văn bản đến: khóa văn bản, lấy số kế tiếp của sổ năm nay, ghi số và trạng thái, thêm sự kiện —
-- tất cả trong một giao dịch, nên không có số bị bỏ trống hay cấp trùng (NĐ 30, Điều 22). Gọi lại cho văn
-- bản đã vào sổ thì trả về văn bản như cũ, không cấp số thứ hai.
--
-- Chỉ vai trò service gọi được (svc-workflow xử lý Action registerIncoming); hasura_session do Hasura
-- truyền vào, nên thuê ước và người thực hiện lấy từ phiên chứ không từ tham số.
-- ---------------------------------------------------------------------------

create function office.register_incoming(document_id uuid, hasura_session json)
returns setof office.documents
language plpgsql volatile
as $$
declare
  tenant  uuid := (hasura_session ->> 'x-hasura-tenant-id')::uuid;
  actor   text := hasura_session ->> 'x-hasura-user-id';
  -- sổ đăng ký theo năm dương lịch ở Việt Nam
  yr      int  := extract(year from now() at time zone 'Asia/Ho_Chi_Minh')::int;
  doc     office.documents;
  reg     office.registers;
begin
  select * into doc
    from office.documents d
   where d.id = register_incoming.document_id and d.tenant_id = tenant
     for update;
  if not found then
    raise exception 'không có văn bản %', register_incoming.document_id
      using errcode = 'invalid_parameter_value';
  end if;
  if doc.direction <> 'in' then
    raise exception 'chỉ văn bản đến mới vào sổ đến' using errcode = 'check_violation';
  end if;
  if doc.status <> 'received' then
    if doc.registered_at is not null then
      return next doc;                        -- đã vào sổ từ lần gọi trước
      return;
    end if;
    raise exception 'văn bản ở trạng thái % không vào sổ được', doc.status
      using errcode = 'check_violation';
  end if;

  insert into office.registers (tenant_id, direction, year)
  values (tenant, 'in', yr)
  on conflict (tenant_id, direction, year) do nothing;

  update office.registers r
     set last_number = r.last_number + 1
   where r.tenant_id = tenant and r.direction = 'in' and r.year = yr
  returning * into reg;

  update office.documents d
     set status = 'registered',
         register_id = reg.id,
         register_number = reg.last_number,
         registered_at = now()
   where d.id = doc.id
  returning * into doc;

  insert into office.document_events (tenant_id, document_id, kind, actor_id, actor_kind, data)
  values (tenant, doc.id, 'office.document.registered', actor, 'user',
          jsonb_build_object('register_number', reg.last_number, 'year', yr));

  return next doc;
end
$$;
