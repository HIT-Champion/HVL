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

-- Góp ý trong Văn phòng điện tử (F4.6, đặc tả §8): người đã đăng nhập chấm mức hài lòng 1–5, viết vài dòng (không bắt
-- buộc); giao diện tự gắn màn hình đang dùng. Mô tả: docs/so-lieu-sau.md, docs/mo-hinh-du-lieu.md §2.5.
--
-- Chỉ thu đúng những gì cần để đọc góp ý:
-- - Không họ tên, vai trò, phòng, trình duyệt, địa chỉ IP. user_id (sub) chỉ để người gửi xem lại góp ý của mình
--   (trường `mine`) và để chặn gửi dồn; lãnh đạo, quản trị đơn vị đọc danh sách nhưng không có cột này.
-- - Màn hình là khuôn đường dẫn, không phải đường dẫn thật: đoạn có số hay id thay bằng `:id`, không chuỗi truy vấn
--   (ràng buộc feedback_screen) — /tim-kiem?q=<số CCCD> hay /van-ban/<id> không lọt vào bảng.
-- - Không gắn sổ kiểm toán: sổ ghi người thực hiện từng dòng, lãnh đạo đọc sổ của đơn vị (trường overview) sẽ biết ai
--   góp ý gì. Góp ý không phải hồ sơ nghiệp vụ; không vai trò nào sửa, xóa qua GraphQL.
--
-- Chống gửi dồn ở CSDL, mọi đường ghi đều theo (cả mutation gửi nhiều dòng một lúc): mỗi người trong một đơn vị tối đa
-- 3 góp ý mỗi 10 phút và 20 góp ý mỗi 24 giờ (trigger feedback_guard). Giờ gửi do CSDL đặt.

create table office.feedback (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references core.tenants,
  user_id     text not null check (btrim(user_id) <> ''),   -- sub Keycloak; Hasura đặt từ token
  rating      int  not null constraint feedback_rating check (rating between 1 and 5),
  comment     text constraint feedback_comment check (comment is null or char_length(comment) between 1 and 500),
  -- khuôn đường dẫn của màn hình: '/', '/van-ban-den/tiep-nhan', '/van-ban/:id'… — chỉ chữ thường và gạch nối
  screen      text not null constraint feedback_screen
              check (char_length(screen) <= 80 and screen ~ '^(/|(/([a-z]+(-[a-z]+)*|:id)){1,6})$'),
  created_at  timestamptz not null default now()
);

create index feedback_sender on office.feedback (tenant_id, user_id, created_at desc);
create index feedback_tenant_created on office.feedback (tenant_id, created_at desc);

-- Trước khi thêm: gọt khoảng trắng hai đầu của nội dung, kể cả xuống dòng, tab (chỉ còn khoảng trắng thì null), giờ
-- gửi là giờ của CSDL, rồi đếm góp ý của người gửi trong 10 phút, 24 giờ qua. Khóa tư vấn theo (đơn vị, người) xếp
-- hàng các lần gửi song song của cùng một người, để hai yêu cầu cùng lúc không cùng đếm thiếu. Dòng gửi trước đó trong
-- cùng câu lệnh (mutation nhiều dòng) cũng được đếm: lệnh SQL trong trigger BEFORE ROW thấy các dòng câu lệnh đã thêm
-- trước nó. Lỗi raise không có trường constraint như ràng buộc check: Hasura trả mã permission-error, câu "Check
-- constraint violation. feedback_rate: …", nên tên đặt trong câu lỗi và giao diện (app/utils/errors.ts) tìm tên trong
-- câu — như documents_recipient_units.
create function office.feedback_guard() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
declare
  recent int;
  today  int;
begin
  new.comment := nullif(regexp_replace(new.comment, '^\s+|\s+$', '', 'g'), '');
  new.created_at := now();
  perform pg_advisory_xact_lock(hashtextextended('office.feedback:' || new.tenant_id || ':' || new.user_id, 0));
  select count(*) filter (where f.created_at > now() - interval '10 minutes'), count(*)
    into recent, today
    from office.feedback f
   where f.tenant_id = new.tenant_id and f.user_id = new.user_id and f.created_at > now() - interval '24 hours';
  if recent >= 3 or today >= 20 then
    raise exception 'feedback_rate: gửi quá nhiều góp ý — tối đa 3 góp ý mỗi 10 phút, 20 góp ý mỗi 24 giờ'
      using errcode = 'check_violation';
  end if;
  return new;
end
$$;

create trigger feedback_guard before insert on office.feedback
  for each row execute function office.feedback_guard();

-- Trường `mine` của office_feedback: góp ý này có phải của người đang xem không. Người gửi lọc góp ý của mình mà
-- không ai, kể cả lãnh đạo, đọc được cột user_id.
create function office.feedback_mine(f office.feedback, hasura_session json) returns boolean
language sql stable
as $$
  select coalesce(f.user_id = hasura_session ->> 'x-hasura-user-id', false)
$$;

comment on table office.feedback is 'Góp ý của người dùng Văn phòng điện tử (F4.6): mức hài lòng 1–5, vài dòng, khuôn '
  'đường dẫn màn hình; không họ tên, vai trò, IP';
