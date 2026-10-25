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


-- Kiểm chất lượng số liệu báo cáo (F3.9, F3.11): bộ luật tính trong CSDL lúc truy vấn trên các khung nhìn mà trang
-- Điều hành vẽ, mỗi dòng một kết quả PASSED / WARNING / FAILED kèm số liệu. Trang Điều hành hiện cờ cạnh từng biểu đồ,
-- trang Phả hệ hiện từng luật. Ngưỡng của mọi luật là 0: lệch một văn bản là có cờ.
--
-- Chọn luật theo chỗ ràng buộc schema KHÔNG chặn được (trạng thái văn bản đến, một chủ trì gốc, ngày ban hành của văn
-- bản đi đã phát hành thì ràng buộc đã giữ — kiểm lại là thừa):
-- - status_total: mọi văn bản đến của đơn vị có mặt trên trang — Σ cột của biểu đồ trạng thái (đúng 6 trạng thái trang
--   vẽ, IN_STATUSES của pages/dieu-hanh.vue) cộng văn bản đến hạn chế (trang ghi một con số riêng) bằng số văn bản đến
--   đếm thẳng trên office.documents. Lệch là FAILED, detail ghi trạng thái có dữ liệu mà biểu đồ không vẽ. Hôm nay đúng
--   theo cấu trúc; luật chặn hồi quy: view bị thêm điều kiện lọc, quy trình có trạng thái mới mà biểu đồ chưa vẽ.
-- - department_total: Σ "đang xử lý" của biểu đồ theo phòng bằng cột "Đang xử lý" của biểu đồ trạng thái (hai biểu đồ
--   cùng trang phải nói cùng một số; lệch: FAILED). Khớp nhưng có văn bản ở dòng "chưa rõ phòng" (giao cho người chưa
--   có trong danh bạ hay chưa gắn phòng, đang xử lý mà chưa có việc chủ trì): WARNING, issues là số văn bản đó.
-- - processing_coverage: biểu đồ thời gian xử lý bỏ qua văn bản không có mốc xong (sự kiện processed / filed, hay bản
--   giữ lại lúc nộp lưu) — vd nhập thẳng CSDL. Số văn bản đến đã xong (done / archived, đã vào sổ, không hạn chế) nhiều
--   hơn số biểu đồ tính được: WARNING (trung bình chỉ tính trên một phần); ít hơn, hay có tháng tổng giờ âm (xong trước
--   khi vào sổ — detail ghi tháng): FAILED. Tính trên mọi tháng, không chỉ 12 tháng trang vẽ.
-- - unique_keys: khóa mà trang dùng để ghép số là duy nhất, không rỗng — trang lấy dòng theo tháng (find), theo phòng
--   (:key), trùng thì lặng lẽ lấy dòng đầu, rỗng thì rơi khỏi biểu đồ. Một dòng cho mỗi khung nhìn của trang; tháng
--   rỗng tính là lỗi, phòng rỗng được một dòng ("chưa rõ phòng"). Hôm nay đúng theo GROUP BY; luật chặn hồi quy.
-- - no_personal_columns: theo catalog, cho mọi view office.v_* (cả của trang Số đo): cột xuất ra mang tên thông tin cá
--   nhân (email, số điện thoại, CCCD/CMND, hộ chiếu, ngày sinh, địa chỉ, họ tên, tên đăng nhập) là FAILED; view — hay
--   view lồng mà nó đọc qua (office.report_lineage) — đọc cột như vậy của bảng khác (pg_depend của luật view ghi từng
--   cột) mà không xuất ra là WARNING: gộp, lọc theo cột cá nhân cũng cần xem lại. Theo tên cột: cột đặt tên lạ thì
--   không bắt được; khóa người dùng (user_id, created_by — sub ẩn danh của Keycloak) không tính.
--
-- Cách tính: một dòng core.tenants nhân lateral với các luật của đúng đơn vị đó; mỗi khung nhìn đọc một lần (CTE dùng
-- nhiều lần thì vật lý hóa, có tham số là đơn vị), nên Hasura lọc tenant_id = X-Hasura-Tenant-Id thì chỉ tính cho một
-- đơn vị. Phần catalog giống nhau cho mọi đơn vị. Không lộ gì mới cho lãnh đạo: số nào cũng suy được từ số đã có trên
-- trang (tổng văn bản đến = Σ biểu đồ trạng thái + dòng hạn chế), tên cột là catalog chung. Tên không bắt đầu bằng v_
-- nên không thành một báo cáo trong office.report_lineage.
create view office.report_checks as
select t.id as tenant_id, c.rule, c.report, c.status, c.expected, c.actual, c.issues, c.detail
  from core.tenants t
 cross join lateral (
  with counts as (
    select * from office.v_document_counts v where v.tenant_id = t.id
  ),
  departments as (
    select * from office.v_overdue_by_department v where v.tenant_id = t.id
  ),
  processing as (
    select * from office.v_processing_time v where v.tenant_id = t.id
  ),
  outgoing as (
    select * from office.v_outgoing_by_month v where v.tenant_id = t.id
  ),
  base as (             -- đếm thẳng trên bảng, để đối chiếu với khung nhìn
    select count(*) filter (where d.direction = 'in') as incoming,
           count(*) filter (where d.direction = 'in' and d.status in ('done', 'archived')
                              and d.registered_at is not null and not d.restricted) as finished
      from office.documents d
     where d.tenant_id = t.id
  ),
  shown as (            -- văn bản đến có mặt trên trang: 6 cột của biểu đồ trạng thái + dòng văn bản hạn chế
    select coalesce(sum(documents) filter (where restricted or status in ('received', 'registered', 'in_progress',
                                                                           'done', 'archived', 'cancelled')),
                    0)::bigint as n,
           array_agg(distinct status order by status)
             filter (where not restricted and status not in ('received', 'registered', 'in_progress', 'done',
                                                             'archived', 'cancelled')) as off_chart
      from counts
     where direction = 'in'
  )
  select 'status_total'::text as rule, 'office.v_document_counts'::text as report,
         case when s.n = b.incoming then 'PASSED' else 'FAILED' end::text as status,
         b.incoming as expected, s.n as actual, abs(b.incoming - s.n) as issues, s.off_chart as detail
    from base b, shown s
  union all
  select 'department_total', 'office.v_overdue_by_department',
         case when p.listed <> s.working then 'FAILED' when p.unknown > 0 then 'WARNING' else 'PASSED' end,
         s.working, p.listed, p.unknown, null
    from (select coalesce(sum(documents), 0)::bigint as working
            from counts
           where direction = 'in' and not restricted and status = 'in_progress') s,
         (select coalesce(sum(in_progress), 0)::bigint as listed,
                 coalesce(sum(in_progress) filter (where department_id is null), 0)::bigint as unknown
            from departments) p
  union all
  select 'processing_coverage', 'office.v_processing_time',
         case when p.timed > b.finished or p.negative is not null then 'FAILED'
              when p.timed < b.finished then 'WARNING' else 'PASSED' end,
         b.finished, p.timed, abs(b.finished - p.timed), p.negative
    from base b,
         (select coalesce(sum(documents), 0)::bigint as timed,
                 array_agg(to_char(month, 'YYYY-MM') order by month) filter (where total_hours < 0) as negative
            from processing) p
  union all
  select 'unique_keys', k.report, case when k.keys = k.total then 'PASSED' else 'FAILED' end,
         k.total, k.keys, k.total - k.keys, null
    from (select 'office.v_document_counts' as report, count(*) as total,
                 count(distinct (direction, restricted, status, urgency, overdue)) as keys
            from counts
          union all
          select 'office.v_overdue_by_department', count(*), count(distinct coalesce(department_id::text, '-'))
            from departments
          union all
          select 'office.v_processing_time', count(*), count(distinct month) from processing
          union all
          select 'office.v_outgoing_by_month', count(*), count(distinct month) from outgoing) k
 ) c
union all
select t.id, p.rule, p.report, p.status, p.expected, p.actual, p.issues, p.detail
  from core.tenants t
 cross join (
  with personal (pattern) as (
    values ('(^|_)(e_?mail|phone|mobile|tel|fax|sdt|so_dien_thoai|dien_thoai|cccd|cmnd|cmt|citizen_id|national_id'
            '|id_number|passport|ho_chieu|birth|birthday|birthdate|dob|ngay_sinh|address|dia_chi|full_name|fullname'
            '|ho_ten|username|user_name)(_|$)')
  ),
  views as (
    select c.oid, n.nspname || '.' || c.relname as report
      from pg_catalog.pg_class c
      join pg_catalog.pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'office' and c.relname like 'v\_%' and c.relkind in ('v', 'm')
  ),
  layers as (           -- chính view báo cáo và mọi view nó đọc qua
    select v.report, v.oid as layer from views v
    union
    select l.report, c.oid
      from office.report_lineage l
      join pg_catalog.pg_namespace n on n.nspname = split_part(l.consumer, '.', 1)
      join pg_catalog.pg_class c on c.relnamespace = n.oid and c.relname = split_part(l.consumer, '.', 2)
  ),
  exposed as (          -- cột xuất ra
    select v.report, array_agg(v.report || '.' || a.attname order by a.attname) as cols
      from views v
      join pg_catalog.pg_attribute a on a.attrelid = v.oid and a.attnum > 0 and not a.attisdropped
      join personal x on a.attname ~* x.pattern
     group by 1
  ),
  read as (             -- cột của quan hệ khác mà luật view đọc tới
    select l.report, array_agg(distinct sn.nspname || '.' || sc.relname || '.' || a.attname) as cols
      from layers l
      join pg_catalog.pg_rewrite r on r.ev_class = l.layer and r.rulename = '_RETURN'
      join pg_catalog.pg_depend d on d.classid = 'pg_catalog.pg_rewrite'::regclass and d.objid = r.oid
                                  and d.refclassid = 'pg_catalog.pg_class'::regclass and d.refobjsubid > 0
                                  and d.refobjid <> l.layer
      join pg_catalog.pg_attribute a on a.attrelid = d.refobjid and a.attnum = d.refobjsubid
      join pg_catalog.pg_class sc on sc.oid = a.attrelid
      join pg_catalog.pg_namespace sn on sn.oid = sc.relnamespace
      join personal x on a.attname ~* x.pattern
     group by 1
  )
  select 'no_personal_columns'::text as rule, v.report,
         case when e.cols is not null then 'FAILED' when r.cols is not null then 'WARNING' else 'PASSED' end::text
           as status,
         0::bigint as expected, coalesce(cardinality(e.cols), 0)::bigint as actual,
         coalesce(cardinality(r.cols), 0)::bigint as issues, e.cols || r.cols as detail
    from views v
    left join exposed e on e.report = v.report
    left join read r on r.report = v.report
 ) p;
