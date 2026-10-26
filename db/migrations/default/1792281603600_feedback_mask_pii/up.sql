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

-- #265: góp ý (F4.6) ghi thẳng qua Hasura, lãnh đạo, quản trị đơn vị đọc được nội dung. Form nhắc đừng ghi số CCCD, số
-- điện thoại, nhưng ai lỡ ghi thì số đó nằm nguyên trong bảng. Che bằng luật SQL theo mẫu trước khi lưu — đơn giản
-- hơn bộ che của svc-files (F4.4, svc_files/pii.py): không phân loại CCCD, số điện thoại, số tài khoản, mọi chỗ che
-- đều thành `[đã che]`.

-- Che email và dãy số dài:
--   * dãy số liền từ 9 chữ số (CMND 9, số điện thoại 10, CCCD 12, số tài khoản);
--   * dãy chia nhóm bằng dấu cách, chấm, gạch, từ 9 chữ số, bắt đầu bằng 0 hoặc +84, (+84): số điện thoại, CCCD (mã
--     tỉnh 001–096) viết tách nhóm. Số tiền "100.000.000", năm "2024 2025 2026" không bắt đầu bằng 0 nên giữ.
-- Không che: số dính chữ ("SĐT0912…", "ĐT-0912…"), nhóm số trong mã UUID (mã X-Request-Id người dùng chép từ câu báo
-- lỗi), dãy bắt đầu ngay sau "chữ số + dấu chấm" (phần sau của "10.000.000.000"). Số tiền viết tách bằng dấu cách từ
-- 100 tỉ ("100 000 000 000") bị che phần sau. Nhãn `[đã che]` 8 ký tự, ngắn hơn mọi dãy số bị che; chỉ email rất ngắn
-- (a@b.vn) làm câu dài ra — trigger cắt lại ở 500 ký tự.
-- strict: null vào thì null ra (regexp_instr(null) là null, vòng lặp sẽ không dừng).
create function office.mask_pii(t text) returns text
language plpgsql immutable strict set search_path = pg_catalog, pg_temp
as $$
declare
  num constant text :=
    '(?<![[:alnum:]_])(?<![[:alnum:]_]-)(?<!\d\.)(?:\(?\+\d{2}\)?|\d{3,})(?:[ .-]?\d{2,})*(?![[:alnum:]_])';
  pos int := 1;
  at  int;
  run text;
begin
  t := regexp_replace(t, '(?<![[:alnum:]._%+-])[[:alnum:]._%+-]+@[[:alnum:]-]+(?:\.[[:alnum:]-]+)*\.[[:alpha:]]{2,}',
                      '[đã che]', 'g');
  loop
    at := regexp_instr(t, num, pos);
    exit when at = 0;
    run := regexp_substr(t, num, at);
    if char_length(regexp_replace(run, '\D', '', 'g')) >= 9 and (run ~ '^\+?\d+$' or run ~ '^(0|\(?\+84)') then
      t := overlay(t placing '[đã che]' from at for char_length(run));
      pos := at + char_length('[đã che]');
    else
      -- dãy bị loại: chỉ bước qua nhóm đầu, các nhóm sau xét lại — số điện thoại đứng sau năm, số phòng
      -- ("26/10/2026 0912345678", "Phòng 302 0912 345 678") vẫn được che
      pos := at + char_length(substring(run from '^\(?\+?\d+\)?'));
    end if;
  end loop;
  return t;
end
$$;

comment on function office.mask_pii(text) is 'Che email, dãy số từ 9 chữ số (liền, hoặc tách nhóm và bắt đầu bằng 0, '
  '+84) thành [đã che] — luật theo mẫu cho nội dung góp ý (#265), đơn giản hơn svc_files/pii.py';

-- Như migration 1792281602700_feedback, thêm bước che sau khi gọt khoảng trắng. Chặn gửi dồn giữ nguyên.
create or replace function office.feedback_guard() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
declare
  recent int;
  today  int;
begin
  new.comment := nullif(regexp_replace(new.comment, '^\s+|\s+$', '', 'g'), '');
  -- quá 500 ký tự thì để nguyên cho ràng buộc feedback_comment từ chối (không lưu gì); trong giới hạn thì che, cắt
  -- lại ở 500 khi email ngắn làm câu dài ra
  if char_length(new.comment) <= 500 then
    new.comment := left(office.mask_pii(new.comment), 500);
  end if;
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

-- Góp ý đã gửi trước bản này (bản online có thể đã có số thật). Trigger chỉ chạy khi thêm nên lệnh sửa không ăn vào
-- lượt gửi; bảng không gắn sổ kiểm toán nên không ghi sổ.
update office.feedback
   set comment = left(office.mask_pii(comment), 500)
 where comment is distinct from left(office.mask_pii(comment), 500);
