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


-- Phả hệ của báo cáo tổng hợp (F3.9, F3.11): khung nhìn báo cáo nào đọc bảng nào, tính thẳng từ catalog PostgreSQL
-- lúc truy vấn — không khai tay cạnh nào, sửa view là phả hệ đổi theo. Biểu đồ nào của trang Điều hành đọc view nào
-- thì khai ở một chỗ trong office (apps/office/app/utils/lineage.ts), có test đối chiếu với truy vấn thật của trang.
--
-- - Báo cáo: mọi view (cả materialized view) trong schema office tên bắt đầu bằng v_ — quy ước sẵn có của các khung
--   nhìn số liệu (dashboard 1200, số đo 2750, độ chính xác gợi ý). View báo cáo mới theo quy ước là tự có phả hệ.
-- - Cạnh trực tiếp: luật _RETURN của view ghi trong pg_depend mọi quan hệ mà truy vấn của nó đọc, kể cả trong truy vấn
--   con, CTE, subquery vô hướng (vd office.document_events trong v_processing_time). Không dùng
--   information_schema.view_table_usage: khung nhìn đó chỉ hiện bảng do vai trò hiện tại sở hữu.
-- - View đọc view: đi tiếp đệ quy tới tận bảng; depth 1 là báo cáo đọc trực tiếp, consumer là view đọc ở cạnh đó.
-- - Chỉ có tên đối tượng và cạnh, giống nhau cho mọi đơn vị: không số dòng (reltuples cộng mọi đơn vị; đếm theo đơn vị
--   trên bảng giao việc, dòng thời gian thì lộ dấu vết văn bản hạn chế mà migration 1200 đã che), không định nghĩa SQL.
--   Hasura cho lãnh đạo đơn vị đọc, như dashboard.
-- - Giới hạn: view gọi một hàm SQL đọc bảng thì catalog không ghi cạnh tới bảng đó (hiện không view v_ nào làm vậy);
--   phả hệ mức bảng, chưa mức cột.
create view office.report_lineage as
with recursive
  reads as (            -- view, materialized view → quan hệ nó đọc trực tiếp
    select distinct r.ev_class as consumer, d.refobjid as source
      from pg_catalog.pg_rewrite r
      join pg_catalog.pg_depend d on d.classid = 'pg_catalog.pg_rewrite'::regclass and d.objid = r.oid
                                  and d.refclassid = 'pg_catalog.pg_class'::regclass and d.refobjid <> r.ev_class
      join pg_catalog.pg_class s on s.oid = d.refobjid and s.relkind in ('r', 'p', 'v', 'm', 'f')
     where r.rulename = '_RETURN'
  ),
  reports as (
    select c.oid
      from pg_catalog.pg_class c
      join pg_catalog.pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'office' and c.relname like 'v\_%' and c.relkind in ('v', 'm')
  ),
  walk (report, consumer, source, depth, path) as (
    select p.oid, d.consumer, d.source, 1, array[p.oid]
      from reports p
      join reads d on d.consumer = p.oid
    union all
    select w.report, d.consumer, d.source, w.depth + 1, w.path || d.consumer
      from walk w
      join reads d on d.consumer = w.source
     where d.consumer <> all (w.path)  -- view không đọc vòng được nhau, chặn cho chắc
  )
select rn.nspname || '.' || rc.relname as report,
       cn.nspname || '.' || cc.relname as consumer,
       sn.nspname || '.' || sc.relname as source,
       case sc.relkind when 'r' then 'table' when 'p' then 'partitioned_table' when 'v' then 'view'
                       when 'm' then 'materialized_view' when 'f' then 'foreign_table' end as source_kind,
       min(w.depth) as depth
  from walk w
  join pg_catalog.pg_class rc on rc.oid = w.report
  join pg_catalog.pg_namespace rn on rn.oid = rc.relnamespace
  join pg_catalog.pg_class cc on cc.oid = w.consumer
  join pg_catalog.pg_namespace cn on cn.oid = cc.relnamespace
  join pg_catalog.pg_class sc on sc.oid = w.source
  join pg_catalog.pg_namespace sn on sn.oid = sc.relnamespace
 group by 1, 2, 3, 4;
