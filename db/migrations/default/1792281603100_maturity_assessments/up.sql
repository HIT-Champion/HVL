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

-- Tự chẩn đoán mức trưởng thành H-P-D-I (trang /tu-chan-doan, docs/tu-chan-doan.md): lãnh đạo đơn vị trả lời bộ câu
-- của giao diện (apps/office/app/data/tu-chan-doan.json); mỗi lần lưu là một dòng, để đơn vị so các lần với nhau.
--
-- - framework: phiên bản bộ câu. CSDL không giữ nội dung câu hỏi nhưng biết bộ mã câu của từng phiên bản: hpdi-1 là
--   12 câu h1–h3, p1–p3, d1–d3, i1–i3 (test office đối chiếu với tệp JSON). Đổi bộ câu thì thêm phiên bản mới bằng
--   migration (ràng buộc maturity_framework và trigger), để lịch sử không trộn hai bộ.
-- - answers: mã câu → mức 1–5, vd {"h1": 3, "p2": 4}: đủ mọi mã câu của phiên bản, không thừa câu nào.
-- - h, p, d, i: điểm mỗi không gian do CSDL tính từ answers (trung bình, làm tròn 2 chữ số) — người gửi không chọn
--   được điểm; giao diện tính cùng cách (app/utils/hpdi.ts) để hiện trước khi lưu.
-- - Thuê ước, người lưu Hasura đặt từ token; giờ lưu do CSDL đặt. Mỗi lần lưu là một dòng sổ kiểm toán (core.audit()
--   như mọi bảng nghiệp vụ). Không vai trò nào sửa, xóa qua GraphQL: lịch sử để xem tiến bộ, không để viết lại.
-- - Chặn lưu dồn như góp ý (feedback_rate, migration 1792281602700): mỗi đơn vị tối đa 5 lần lưu mỗi giờ, 20 lần mỗi
--   24 giờ — đủ cho lãnh đạo đánh giá lại, không để vòng lặp hay mutation nhiều dòng làm phình bảng và sổ kiểm toán.
-- - Lỗi raise không có trường constraint như ràng buộc check: Hasura trả câu "Check constraint violation.
--   maturity_answers: …", nên tên đặt ở đầu câu lỗi — như feedback_rate (migration 1792281602700).

create table office.maturity_assessments (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references core.tenants,
  created_by  text not null check (btrim(created_by) <> ''),    -- sub Keycloak; Hasura đặt từ token
  framework   text not null constraint maturity_framework check (framework in ('hpdi-1')),
  answers     jsonb not null,                                    -- trigger maturity_assessments_guard kiểm
  h           numeric(3,2) not null,                             -- trigger tính từ answers
  p           numeric(3,2) not null,
  d           numeric(3,2) not null,
  i           numeric(3,2) not null,
  note        text constraint maturity_note check (note is null or char_length(note) between 1 and 300),
  created_at  timestamptz not null default now(),
  constraint maturity_scores check (h between 1 and 5 and p between 1 and 5 and d between 1 and 5 and i between 1 and 5)
);

create index maturity_assessments_tenant_created on office.maturity_assessments (tenant_id, created_at desc);

-- Trước khi thêm: kiểm answers (đối tượng; đúng bộ mã câu của phiên bản; giá trị số nguyên 1–5), tính h, p, d, i, gọt
-- khoảng trắng hai đầu của ghi chú (chỉ còn khoảng trắng thì null), đặt giờ lưu, rồi đếm số lần lưu của đơn vị trong
-- 1 giờ, 24 giờ qua. Khóa tư vấn theo đơn vị xếp hàng các lần lưu song song (hai yêu cầu cùng lúc không cùng đếm
-- thiếu); dòng thêm trước đó trong cùng câu lệnh (mutation nhiều dòng) cũng được đếm — như feedback_guard. Sửa dòng
-- (chỉ quyền quản trị làm được) cũng qua đây, không đếm lưu dồn: điểm luôn khớp answers.
create function office.maturity_assessments_guard() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
declare
  codes  text[];
  total  int;
  bad    int;
  recent int;
  today  int;
begin
  codes := case new.framework
             when 'hpdi-1' then '{h1,h2,h3,p1,p2,p3,d1,d2,d3,i1,i2,i3}'::text[]
           end;
  if codes is null then
    raise exception 'maturity_framework: phiên bản bộ câu không có trong CSDL (đang có: hpdi-1)'
      using errcode = 'check_violation';
  end if;
  if jsonb_typeof(new.answers) is distinct from 'object' then
    raise exception 'maturity_answers: answers phải là đối tượng mã câu → mức' using errcode = 'check_violation';
  end if;
  select count(*),
         count(*) filter (where not (a.key = any (codes) and jsonb_typeof(a.value) = 'number'
                                     and a.value::text ~ '^[1-5]$'))
    into total, bad
    from jsonb_each(new.answers) as a;
  -- khóa của đối tượng jsonb không trùng: không mã lạ và đủ số mã là đúng bộ mã câu
  if bad > 0 or total <> cardinality(codes) then
    raise exception 'maturity_answers: cần đủ % câu của bộ % (%), mỗi câu một mức là số nguyên 1–5',
      cardinality(codes), new.framework, array_to_string(codes, ', ') using errcode = 'check_violation';
  end if;
  select round(avg(a.value::text::int) filter (where left(a.key, 1) = 'h'), 2),
         round(avg(a.value::text::int) filter (where left(a.key, 1) = 'p'), 2),
         round(avg(a.value::text::int) filter (where left(a.key, 1) = 'd'), 2),
         round(avg(a.value::text::int) filter (where left(a.key, 1) = 'i'), 2)
    into new.h, new.p, new.d, new.i
    from jsonb_each(new.answers) as a;
  new.note := nullif(regexp_replace(new.note, '^\s+|\s+$', '', 'g'), '');
  if tg_op = 'INSERT' then
    new.created_at := now();
    perform pg_advisory_xact_lock(hashtextextended('office.maturity_assessments:' || new.tenant_id, 0));
    select count(*) filter (where m.created_at > now() - interval '1 hour'), count(*)
      into recent, today
      from office.maturity_assessments m
     where m.tenant_id = new.tenant_id and m.created_at > now() - interval '24 hours';
    if recent >= 5 or today >= 20 then
      raise exception 'maturity_rate: lưu quá nhiều lần — mỗi đơn vị tối đa 5 lần mỗi giờ, 20 lần mỗi 24 giờ'
        using errcode = 'check_violation';
    end if;
  end if;
  return new;
end
$$;

create trigger maturity_assessments_guard before insert or update on office.maturity_assessments
  for each row execute function office.maturity_assessments_guard();

-- Sổ kiểm toán chuỗi băm của lõi: mỗi lần lưu một dòng, người làm lấy từ phiên Hasura
create trigger audit after insert or update or delete on office.maturity_assessments
  for each row execute function core.audit();

comment on table office.maturity_assessments is 'Tự chẩn đoán mức trưởng thành H-P-D-I của đơn vị: câu trả lời theo '
  'mã câu, điểm bốn không gian do CSDL tính, ghi chú; mỗi lần lưu một dòng';
