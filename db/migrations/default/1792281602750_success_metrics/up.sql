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

-- Số đo "sau" theo đặc tả §8 (F4.6), tính từ dữ liệu của hệ thống: thời gian từ khi văn bản đến tới khi được giao
-- xử lý (trung vị, p90), tỷ lệ văn bản xử lý quá hạn, và bảng tổng hợp góp ý. Thời gian tìm lại một văn bản cũ đo bằng
-- cách bấm giờ những lần tìm thật (make do-so-lieu-sau, nút trên trang Số đo), số bước chuyển tay chỉ so sánh định
-- tính — không có trong CSDL. Cách đo và cách đọc số: docs/so-lieu-sau.md.
--
-- Như dashboard điều hành (migration 1792281601200): chỉ có số đếm và số giờ, gom theo đơn vị, không cột nào chứa trích
-- yếu, số ký hiệu hay tên người; văn bản hạn chế không vào phép tính nào; "hôm nay", "tháng" theo giờ Việt Nam. Mỗi
-- khung nhìn có một dòng mỗi tháng và một dòng month null cho mọi tháng: trung vị, p90 không cộng dồn được từ các tháng
-- nên dòng tổng tính lại trên toàn bộ văn bản (grouping sets).
--
-- Cột sample: đơn vị mẫu do make seed nạp (core.tenants.sample_data). Giao diện và lệnh đo ghi rõ số đó tính trên dữ
-- liệu mẫu — kịch bản seed đi hết các bước trong vài giây, không phải nhịp làm việc của người ở đơn vị thật.

alter table core.tenants
  add column sample_data boolean not null default false;   -- đơn vị mẫu do make seed nạp (seed/tenants.sql)

-- Hai đơn vị mẫu của seed/tenants.sql (id cố định) nạp trước migration này: đánh dấu luôn, không đợi make seed chạy lại
update core.tenants set sample_data = true
 where id in ('c300d5bb-028f-44cc-ba10-7b5277a4225d', '318da474-60d6-4a90-aa7f-928b31b8fc59');

-- (a) Từ lúc văn bản đến tới lúc được giao xử lý. Lúc đến: dòng văn bản đến được tạo — văn thư tiếp nhận (sự kiện
-- office.document.received) hoặc liên thông tới (office.document.arrived). Lúc giao: lần đầu lãnh đạo đơn vị giao chủ
-- trì (việc chủ trì gốc, sự kiện office.document.directed), kể cả việc giao rồi hủy để giao lại. Thêm một mốc: lần đầu
-- văn bản tới tay một người xử lý (việc chủ trì có user_id — lãnh đạo giao thẳng cho người, hay lãnh đạo phòng phân
-- công, sự kiện office.document.assigned). Hai mốc đọc từ office.documents.created_at và
-- office.assignments.assigned_at, ghi cùng giao dịch với các sự kiện trên: nộp lưu (F3.8) gỡ dòng thời gian nhưng giữ
-- văn bản và giao việc, nên văn bản đã nộp lưu vẫn được tính. Văn bản đã hủy, văn bản hạn chế không tính. Nhóm theo
-- tháng văn bản đến.
-- waiting: chưa được giao, còn chờ vào sổ hay chờ chỉ đạo. Văn bản lãnh đạo cho lưu không giao (filed) không vào số
-- nào trừ arrived. Số giờ âm (lúc giao nhập tay trước lúc văn bản đến, vd nạp thẳng vào CSDL) tính là 0, không kéo
-- trung vị xuống dưới 0.
create view office.v_time_to_assign as
with docs as (
  select d.tenant_id,
         date_trunc('month', d.created_at at time zone 'Asia/Ho_Chi_Minh')::date as month,
         d.status,
         d.created_at,
         (select min(a.assigned_at) from office.assignments a
           where a.tenant_id = d.tenant_id and a.document_id = d.id
             and a.parent_id is null and a.role = 'lead')                         as lead_at,
         (select min(a.assigned_at) from office.assignments a
           where a.tenant_id = d.tenant_id and a.document_id = d.id
             and a.role = 'lead' and a.user_id is not null)                       as handler_at
    from office.documents d
   where d.direction = 'in' and d.status <> 'cancelled' and not d.restricted
),
hours as (
  -- case chứ không greatest(): greatest bỏ qua null nên văn bản chưa giao sẽ thành 0 giờ
  select tenant_id,
         month,
         status,
         (case when lead_at < created_at then 0
               else extract(epoch from lead_at - created_at) / 3600 end)::float8      as lead_hours,
         (case when handler_at < created_at then 0
               else extract(epoch from handler_at - created_at) / 3600 end)::float8   as handler_hours
    from docs
),
grouped as (
  select tenant_id,
         month,
         count(*)::int                                                       as arrived,
         count(lead_hours)::int                                              as assigned,
         percentile_cont(0.5) within group (order by lead_hours)             as median_hours,
         percentile_cont(0.9) within group (order by lead_hours)             as p90_hours,
         count(handler_hours)::int                                           as handled,
         percentile_cont(0.5) within group (order by handler_hours)          as handled_median_hours,
         percentile_cont(0.9) within group (order by handler_hours)          as handled_p90_hours,
         count(*) filter (where lead_hours is null
                            and status in ('received', 'registered'))::int as waiting
    from hours
   group by grouping sets ((tenant_id, month), (tenant_id))
)
select g.tenant_id, t.sample_data as sample, g.month, g.arrived, g.assigned, g.median_hours, g.p90_hours,
       g.handled, g.handled_median_hours, g.handled_p90_hours, g.waiting
  from grouped g
  join core.tenants t on t.id = g.tenant_id;

-- (b) Tỷ lệ văn bản xử lý quá hạn: hạn giải quyết (office.documents.due_on) so với lúc xong — sự kiện processed /
-- filed cuối cùng, văn bản đã nộp lưu thì bản giữ lại (như v_processing_time, migration 1792281602300). Quá hạn là
-- xong sau ngày hạn (theo giờ Việt Nam), hoặc chưa xong mà đã qua ngày hạn (late_open): bỏ những văn bản chưa xong thì
-- tỷ lệ đẹp hơn thật. Văn bản có hạn, chưa xong, chưa tới hạn chưa biết đúng hay trễ: chỉ đếm ở pending, không vào
-- mẫu số (judged). Xong mà không rõ lúc xong (không có sự kiện — vd nhập thẳng vào CSDL) không vào số nào. Văn bản
-- không có hạn giải quyết không vào tỷ lệ. Nhóm theo tháng của ngày hạn.
-- Khác cột on_time của dashboard điều hành (v_processing_time): dashboard chỉ đếm văn bản đã xong, nhóm theo tháng
-- xong; tỷ lệ này đếm cả văn bản chưa xong mà đã qua hạn, nhóm theo tháng của hạn.
create view office.v_overdue_rate as
with docs as (
  select d.tenant_id,
         date_trunc('month', d.due_on::timestamp)::date as month,
         d.due_on,
         d.status in ('done', 'archived') as finished,
         coalesce((select max(e.created_at) from office.document_events e
                    where e.document_id = d.id
                      and e.kind in ('office.document.processed', 'office.document.filed')),
                  (select k.finished_at from office.archived_document_facts k
                    where k.document_id = d.id and k.tenant_id = d.tenant_id)) as finished_at,
         (now() at time zone 'Asia/Ho_Chi_Minh')::date as today
    from office.documents d
   where d.direction = 'in' and d.status <> 'cancelled' and not d.restricted and d.due_on is not null
),
judged as (
  select tenant_id,
         month,
         case when finished then (finished_at at time zone 'Asia/Ho_Chi_Minh')::date > due_on
              when due_on < today then true
         end                                   as late,
         not finished and due_on < today       as late_open,
         not finished and due_on >= today      as pending
    from docs
)
select g.tenant_id, t.sample_data as sample, g.month, g.judged, g.on_time, g.late, g.late_open, g.pending
  from (select tenant_id,
               month,
               count(late)::int                           as judged,
               count(*) filter (where not late)::int      as on_time,
               count(*) filter (where late)::int          as late,
               count(*) filter (where late_open)::int     as late_open,
               count(*) filter (where pending)::int       as pending
          from judged
         group by grouping sets ((tenant_id, month), (tenant_id))) g
  join core.tenants t on t.id = g.tenant_id;

-- Góp ý theo màn hình (migration 1792281602700): số góp ý, tổng điểm (giao diện tự chia ra điểm trung bình, gộp được
-- nhiều màn hình mà không lệch), số góp ý theo từng mức 1–5, số góp ý có viết nội dung, lần gửi gần nhất. Dòng screen
-- null: mọi màn hình. Không có nội dung góp ý, không có người gửi.
create view office.v_feedback_summary as
select g.tenant_id, t.sample_data as sample, g.screen, g.feedback, g.rating_total, g.rating_1, g.rating_2, g.rating_3,
       g.rating_4, g.rating_5, g.with_comment, g.last_at
  from (select tenant_id,
               screen,
               count(*)::int                               as feedback,
               sum(rating)::int                            as rating_total,
               count(*) filter (where rating = 1)::int     as rating_1,
               count(*) filter (where rating = 2)::int     as rating_2,
               count(*) filter (where rating = 3)::int     as rating_3,
               count(*) filter (where rating = 4)::int     as rating_4,
               count(*) filter (where rating = 5)::int     as rating_5,
               count(comment)::int                         as with_comment,
               max(created_at)                             as last_at
          from office.feedback
         group by grouping sets ((tenant_id, screen), (tenant_id))) g
  join core.tenants t on t.id = g.tenant_id;
