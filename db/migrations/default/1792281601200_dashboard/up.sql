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

-- Dashboard điều hành (F3.11): bốn khung nhìn chỉ có số đếm, đã gom theo thuê ước — không cột nào chứa trích
-- yếu, số ký hiệu hay tên người. Hasura cho lãnh đạo đơn vị đọc, lọc tenant_id = X-Hasura-Tenant-Id, nên số
-- liệu theo đúng SSO và thuê ước mà không cần dịch vụ riêng.
--
-- Văn bản hạn chế KHÔNG vào các phép chia (trạng thái, độ khẩn, quá hạn, phòng, thời gian): lãnh đạo đọc được mọi
-- văn bản khác của đơn vị, nên lấy số chia trừ đi số văn bản mình thấy là ra trạng thái, phòng xử lý, thời gian
-- của văn bản hạn chế — đúng thứ sổ đăng ký in che đi (F2.8). Chỉ còn một con số tổng theo chiều đến / đi
-- (v_document_counts, restricted = true), như sổ đăng ký vẫn cho biết có bao nhiêu văn bản.
--
-- "Hôm nay", "tháng" tính theo giờ Việt Nam, như sổ đăng ký.

-- Văn bản theo chiều, trạng thái, độ khẩn. overdue: văn bản đến chưa xử lý xong (chờ vào sổ, chờ chỉ đạo, đang xử
-- lý) mà đã qua hạn giải quyết. Văn bản hạn chế gom một dòng mỗi chiều, status / urgency / overdue để null.
create view office.v_document_counts as
select d.tenant_id,
       d.direction,
       d.restricted,
       case when not d.restricted then d.status end  as status,
       case when not d.restricted then d.urgency end as urgency,
       case when not d.restricted then
         coalesce(d.direction = 'in' and d.status in ('received', 'registered', 'in_progress')
                  and d.due_on < (now() at time zone 'Asia/Ho_Chi_Minh')::date, false)
       end as overdue,
       count(*)::int as documents
  from office.documents d
 group by 1, 2, 3, 4, 5, 6;

-- Văn bản đến đang xử lý theo phòng chủ trì: việc chủ trì gốc giao cho phòng, hoặc cho một người thì lấy phòng
-- của người đó. Phòng chưa có việc vẫn có dòng, số 0 — để biểu đồ đủ mọi phòng. Không xác định được phòng (người
-- được giao chưa gắn phòng trong danh bạ, hay không có việc chủ trì) thì vào dòng department_id null, để tổng các
-- dòng luôn bằng số văn bản đến đang xử lý (không kể văn bản hạn chế).
create view office.v_overdue_by_department as
with lead as (
  select d.tenant_id,
         p.id as department_id,
         coalesce(d.due_on < (now() at time zone 'Asia/Ho_Chi_Minh')::date, false) as overdue
    from office.documents d
    left join office.assignments a on a.document_id = d.id and a.parent_id is null and a.role = 'lead'
                                  and a.status <> 'cancelled'
    left join core.users u on u.id = a.user_id and u.tenant_id = a.tenant_id
    left join office.departments p on p.tenant_id = d.tenant_id and p.id = coalesce(a.department_id, u.department_id)
   where d.direction = 'in' and d.status = 'in_progress' and not d.restricted
)
select p.tenant_id,
       p.id   as department_id,
       p.code,
       p.name,
       count(l.department_id)::int                         as in_progress,
       count(l.department_id) filter (where l.overdue)::int as overdue
  from office.departments p
  left join lead l on l.tenant_id = p.tenant_id and l.department_id = p.id
 group by p.tenant_id, p.id, p.code, p.name
union all
select tenant_id, null, null, null, count(*)::int, count(*) filter (where overdue)::int
  from lead
 where department_id is null
 group by tenant_id;

-- Thời gian từ vào sổ đến khi xong (người được giao báo xong, hoặc lãnh đạo cho lưu không xử lý), theo tháng
-- xong. Lúc xong lấy từ dòng thời gian (office.document_events), ghi cùng giao dịch với trạng thái done; văn bản
-- không có sự kiện đó (vd nhập thẳng vào CSDL) không được tính. Trả tổng số giờ, không trả trung bình đã làm tròn:
-- giao diện tự chia, gộp được nhiều tháng mà không lệch. on_time chỉ đếm trong số văn bản có hạn (with_due).
create view office.v_processing_time as
with finished as (
  select d.tenant_id,
         d.registered_at,
         d.due_on,
         (select max(e.created_at) from office.document_events e
           where e.document_id = d.id
             and e.kind in ('office.document.processed', 'office.document.filed')) as finished_at
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

-- Văn bản đi đã phát hành theo tháng ban hành.
create view office.v_outgoing_by_month as
select tenant_id,
       date_trunc('month', issued_on::timestamp)::date as month,
       count(*)::int as documents
  from office.documents
 where direction = 'out' and status in ('issued', 'archived') and not restricted
 group by 1, 2;
