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

-- Sổ kiểm toán (F2.12) không lộ danh sách được xem văn bản hạn chế (F3.7) cho lãnh đạo, quản trị đơn vị không đọc
-- được văn bản đó. Dòng sổ của office.document_acl mang entity_id "<văn bản>/<người được cấp>" (trigger core.audit,
-- migration 1792281600200) và actor_id là người cấp / gỡ — hai cột `director`, `tenant_admin` chọn và lọc thẳng được
-- (core_audit_log.yaml). Trường overview đã che giá trị (office.audit_overview_seen, migration 1792281601600) nhưng hai
-- cột thô thì không: core_audit_log(where: {entity: {_eq: "office.document_acl"}}) ra mọi người được cấp và người cấp.
--
-- Hàm dưới thành trường tính toán `visible` của core_audit_log, nằm trong bộ lọc quyền của `director`, `tenant_admin`
-- (không cấp cho vai trò nào chọn — lược đồ GraphQL của hai vai trò không đổi): dòng document_acl của văn bản hạn chế
-- mà người xem không đọc được thì không hiện cả dòng — cùng điều kiện với lúc overview che mọi giá trị. Lọc ở quyền
-- nên mọi đường đều theo: cột thô, where trên entity_id / actor_id (_like, _regex…), aggregate, by_pk. Người đọc được
-- văn bản (người tạo, có tên trong danh sách) thấy như cũ.
--
-- - Không sửa dòng sổ nào (sổ chỉ ghi thêm; hash tính trên cả entity_id, actor_id): dòng cũ và dòng mới cùng được lọc;
--   chuỗi băm, core.audit_verify(), make audit không đổi. Không đổi khóa entity_id của dòng mới: màn Sổ kiểm toán vẫn
--   lọc dòng danh sách được xem theo "<văn bản>/%".
-- - Đổi lại: người không đọc được văn bản không còn biết là có lần cấp / gỡ quyền xem (trước đây thấy dòng với mọi giá
--   trị null), dãy id họ thấy có chỗ hở; quản trị đơn vị không đọc văn bản nào nên không thấy dòng danh sách được xem
--   của văn bản hạn chế nào. prev_hash của dòng kế tiếp vẫn là hash của dòng ẩn — hash không lộ nội dung.
-- - Văn bản không tra được (entity_id hỏng, văn bản đã bị xóa thẳng trong CSDL) thì cũng ẩn: không biết nó có hạn chế
--   không. Dòng không phải document_acl không đổi gì.
-- - Chi phí: PostgreSQL không gộp hàm vào câu truy vấn (EXPLAIN cho thấy một bộ lọc gọi hàm trên từng dòng sau khi
--   quét theo thuê ước), nhưng mỗi lần gọi rẻ: dòng khác document_acl dừng ở phép so entity, dòng document_acl tra một
--   văn bản theo khóa chính.

create function office.audit_log_visible(r core.audit_log, hasura_session json) returns boolean
language sql stable
as $$
  select r.entity <> 'office.document_acl'
      or exists (select 1 from office.documents d
                  where d.tenant_id = r.tenant_id
                    and d.id = case when split_part(r.entity_id, '/', 1)
                                         ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                                    then split_part(r.entity_id, '/', 1)::uuid end
                    and (not d.restricted or coalesce(office.document_visible(d, hasura_session), false)))
$$;
