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

-- Văn bản đi (F2.4) và cổng xác thực (F2.13): nội dung dự thảo, thông tin đơn vị in trên văn bản, cấp số đi
-- trong một giao dịch, khung nhìn công khai cho cổng xác thực. Mô tả: docs/mo-hinh-du-lieu.md §2.2, §4.1.

-- ---------------------------------------------------------------------------
-- Thông tin in trên văn bản theo thể thức NĐ 30/2020/NĐ-CP (Phụ lục I): tên cơ quan chủ quản ở dòng trên
-- tên đơn vị, địa danh trước ngày tháng, chức vụ người đứng đầu ở phần ký.
-- ---------------------------------------------------------------------------

alter table core.tenants
  add column parent_name text check (parent_name is null or btrim(parent_name) <> ''),  -- 'Trường Đại học …'
  add column place_name  text check (place_name is null or btrim(place_name) <> ''),    -- 'Hà Nội'
  add column head_title  text check (head_title is null or btrim(head_title) <> '');    -- 'Trưởng khoa'

-- Nội dung văn bản đi do chuyên viên soạn (các đoạn cách nhau một dòng trống); svc-files dựng PDF từ đây
alter table office.documents
  add column body text,
  add constraint documents_body_length check (body is null or char_length(body) <= 20000),
  add constraint documents_body_only_out check (direction = 'out' or body is null);

-- ---------------------------------------------------------------------------
-- Cấp số văn bản đi: khóa văn bản, lấy số kế tiếp của sổ đi năm nay, ghi số, ký hiệu, ngày ban hành và mã
-- tra cứu — một giao dịch, nên không có số bị bỏ trống hay cấp trùng (NĐ 30, Điều 15). Văn bản vẫn ở trạng
-- thái approved: svc-workflow dựng PDF có số rồi mới chuyển sang issued cùng băm của tệp. Gọi lại cho văn bản
-- đã có số thì trả về như cũ, không cấp số thứ hai.
--
-- Ký hiệu (NĐ 30, Phụ lục I): văn bản có tên loại là số/tên loại-đơn vị (05/TB-CNTT); công văn là
-- số/đơn vị-phòng soạn thảo (05/CNTT-ĐT). Số nhỏ hơn 10 viết thêm số 0 ở trước.
--
-- Chỉ vai trò service gọi được (svc-workflow, khi văn thư phát hành); thuê ước và người thực hiện lấy từ
-- hasura_session. Mã tra cứu do svc-workflow sinh ngẫu nhiên (10 ký tự base32) và truyền vào.
-- ---------------------------------------------------------------------------

create function office.number_outgoing(document_id uuid, verify_code text, hasura_session json)
returns setof office.documents
language plpgsql volatile
as $$
declare
  tenant     uuid := (hasura_session ->> 'x-hasura-tenant-id')::uuid;
  actor      text := hasura_session ->> 'x-hasura-user-id';
  -- ngày ban hành và sổ theo năm dương lịch ở Việt Nam
  today      date := (now() at time zone 'Asia/Ho_Chi_Minh')::date;
  doc        office.documents;
  reg        office.registers;
  org_code   text;
  dept_code  text;
  with_type  boolean;
  num        text;
begin
  select * into doc
    from office.documents d
   where d.id = number_outgoing.document_id and d.tenant_id = tenant
     for update;
  if not found then
    raise exception 'không có văn bản %', number_outgoing.document_id
      using errcode = 'invalid_parameter_value';
  end if;
  if doc.direction <> 'out' then
    raise exception 'chỉ văn bản đi mới cấp số đi' using errcode = 'check_violation';
  end if;
  if doc.register_number is not null then
    return next doc;                          -- đã cấp số từ lần gọi trước
    return;
  end if;
  if doc.status <> 'approved' then
    raise exception 'văn bản ở trạng thái % chưa được cấp số', doc.status
      using errcode = 'check_violation';
  end if;

  insert into office.registers (tenant_id, direction, year)
  values (tenant, 'out', extract(year from today)::int)
  on conflict (tenant_id, direction, year) do nothing;

  update office.registers r
     set last_number = r.last_number + 1
   where r.tenant_id = tenant and r.direction = 'out' and r.year = extract(year from today)::int
  returning * into reg;

  select t.code into strict org_code from core.tenants t where t.id = tenant;
  select dt.in_symbol into strict with_type from office.document_types dt where dt.code = doc.type_code;
  select p.code into dept_code from office.departments p where p.id = doc.department_id;
  num := case when reg.last_number < 10 then '0' || reg.last_number else reg.last_number::text end;

  update office.documents d
     set register_id = reg.id,
         register_number = reg.last_number,
         registered_at = now(),
         issued_on = today,
         symbol = num || '/' || case when with_type then doc.type_code || '-' || org_code
                                     else org_code || coalesce('-' || dept_code, '') end,
         verify_code = number_outgoing.verify_code
   where d.id = doc.id
  returning * into doc;

  insert into office.document_events (tenant_id, document_id, kind, actor_id, actor_kind, data)
  values (tenant, doc.id, 'office.document.numbered', actor, 'user',
          jsonb_build_object('register_number', reg.last_number, 'year', reg.year, 'symbol', doc.symbol));

  return next doc;
end
$$;

-- ---------------------------------------------------------------------------
-- Cổng xác thực (F2.13): thông tin công khai của văn bản đã phát hành. svc-files tra đúng một văn bản theo mã
-- tra cứu hoặc theo băm bằng vai trò verifier — vai trò chỉ đọc được khung nhìn này, không có quyền nào khác,
-- và không có trong token của người dùng. Trích yếu chỉ hiện khi văn bản được đánh dấu công khai.
-- ---------------------------------------------------------------------------

create view office.issued_documents as
select d.verify_code,
       d.content_sha256,
       d.symbol,
       d.issued_on,
       d.type_code,
       dt.name   as type_name,
       t.name    as issuer_name,
       t.parent_name,
       case when d.is_public then d.summary end as summary,
       d.status
  from office.documents d
  join core.tenants t on t.id = d.tenant_id
  join office.document_types dt on dt.code = d.type_code
 where d.direction = 'out' and d.status in ('issued', 'archived');
