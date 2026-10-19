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

-- Dữ liệu mẫu: hai đơn vị và phòng ban. id cố định vì tài khoản mẫu trong Keycloak (seed/users.csv) trỏ tới.
-- Chạy lại nhiều lần được. KHÔNG dùng trên hệ thống thật.
begin;
set local moc.actor = 'seed';

-- parent_name, place_name, head_title in trên văn bản đi (thể thức NĐ 30/2020)
insert into core.tenants (id, code, name, parent_name, place_name, head_title) values
  ('c300d5bb-028f-44cc-ba10-7b5277a4225d', 'CNTT', 'Khoa Công nghệ thông tin', 'Trường Đại học Công nghiệp', 'Hà Nội', 'Trưởng khoa'),
  ('318da474-60d6-4a90-aa7f-928b31b8fc59', 'KT',   'Khoa Kinh tế',             'Trường Đại học Công nghiệp', 'Hà Nội', 'Trưởng khoa')
on conflict (id) do update set code = excluded.code, name = excluded.name, parent_name = excluded.parent_name,
  place_name = excluded.place_name, head_title = excluded.head_title;

insert into office.departments (id, tenant_id, code, name) values
  ('ecd87efb-e9a1-4113-a46a-f599a9d15574', 'c300d5bb-028f-44cc-ba10-7b5277a4225d', 'VP',   'Văn phòng khoa'),
  ('5cc372aa-304d-4574-896c-4f3e781a2ce7', 'c300d5bb-028f-44cc-ba10-7b5277a4225d', 'ĐT',   'Tổ Đào tạo'),
  ('7ee31261-b14c-4c42-8e1b-9a7e99935412', 'c300d5bb-028f-44cc-ba10-7b5277a4225d', 'KTPM', 'Bộ môn Kỹ thuật phần mềm'),
  ('8dec217d-fa1e-4fb3-9505-5f6033ba340e', 'c300d5bb-028f-44cc-ba10-7b5277a4225d', 'HTTT', 'Bộ môn Hệ thống thông tin'),
  ('0647d361-8734-427d-be0e-deb9530dce81', '318da474-60d6-4a90-aa7f-928b31b8fc59', 'VP',   'Văn phòng khoa'),
  ('30fe7d0a-75a0-49c8-a595-5545a80434c2', '318da474-60d6-4a90-aa7f-928b31b8fc59', 'ĐT',   'Tổ Đào tạo')
on conflict (id) do update set code = excluded.code, name = excluded.name;

commit;
