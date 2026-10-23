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

-- Poka-yoke lớp 3 cho tiếp nhận văn bản đến (F2.2): cùng quy tắc với schemas/van-ban-den.json. Form (lớp 1) và
-- Action receiveIncoming (lớp 2) kiểm theo tệp đó; ở đây CSDL chặn lần cuối, kể cả khi ghi thẳng bằng quyền quản
-- trị. Cả ba lớp chạy chung bộ ca thử schemas/van-ban-den.cases.json (db/tests/test_intake.py cho lớp này).
--
-- Đã có từ trước: documents_in_identity (đủ số ký hiệu, cơ quan, ngày), documents_summary_check (10–500 ký tự),
-- documents_urgency_check, khóa ngoại loại văn bản, chỉ mục chặn trùng documents_in_dedup.
--
-- Tập ký tự viết tường minh, không dùng \s hay [[:space:]] của PostgreSQL (theo locale của máy chủ, có nơi coi
-- U+00A0 là khoảng trắng, có nơi không): khoảng trắng đúng bằng \s của JavaScript; ký tự điều khiển, gạch nối
-- mềm, ký tự rộng 0, điều khiển hướng chữ, BOM không được có ở đâu cả (U+0000 thì kiểu text vốn không chứa được).
-- Chuỗi phải ở dạng dựng sẵn (NFC): "Hưng Yên" gõ và "Hưng Yên" chép từ PDF dạng tổ hợp là một, chặn trùng mới đúng.
-- Hạn tính theo "hôm nay" chỉ kiểm được ở lớp 1, 2; ở đây kiểm điều yếu hơn mà không phụ thuộc lúc ghi: ngày ban
-- hành từ năm 1900 và không sau ngày tiếp nhận (created_at), hạn không trước ngày ban hành.

-- 1. Văn bản đến đã có: sửa những lỗi sửa được mà không đổi nghĩa (form làm đúng như vậy trước khi gửi) — đưa về
--    NFC; tab, và xuống dòng ở số ký hiệu, cơ quan ban hành, thành dấu cách; bỏ ký tự vô hình, khoảng trắng hai đầu.
--    Sổ kiểm toán ghi người sửa là migration này.
create function pg_temp.moc_clean(t text, one_line boolean) returns text language sql immutable as $$
  select regexp_replace(regexp_replace(
           case when one_line then regexp_replace(normalize(t, nfc), '[\t\n\v\f\r\u2028\u2029]+', ' ', 'g')
                else regexp_replace(regexp_replace(normalize(t, nfc), '[\t\v\f]+', ' ', 'g'),
                                    '[\u2028\u2029]', E'\n', 'g') end,
           '[\u0001-\u0009\u000b\u000c\u000e-\u001f\u007f-\u009f\u00ad\u115f\u1160\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\u3164\ufeff\uffa0\u2028\u2029]', '', 'g'),
         '^[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+|[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+$', '', 'g')
$$;

set local moc.actor = 'migration:1792281600800_intake_rules';
set local moc.actor_kind = 'system';
update office.documents
   set symbol = pg_temp.moc_clean(symbol, true),
       issuer_name = pg_temp.moc_clean(issuer_name, true),
       summary = pg_temp.moc_clean(summary, false)
 where direction = 'in'
   and (symbol is distinct from pg_temp.moc_clean(symbol, true)
        or issuer_name is distinct from pg_temp.moc_clean(issuer_name, true)
        or summary is distinct from pg_temp.moc_clean(summary, false));

-- 2. Ràng buộc mới
alter table office.documents
  add constraint documents_in_symbol check (direction <> 'in' or (char_length(symbol) between 1 and 50
    and symbol is nfc normalized
    and symbol !~ '[\u0001-\u0009\u000b\u000c\u000e-\u001f\u007f-\u009f\u00ad\u115f\u1160\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\u3164\ufeff\uffa0\n\r\u2028\u2029]|^[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]|[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]$'))
    not valid,
  add constraint documents_in_issuer check (direction <> 'in' or (char_length(issuer_name) between 1 and 200
    and issuer_name is nfc normalized
    and issuer_name !~ '[\u0001-\u0009\u000b\u000c\u000e-\u001f\u007f-\u009f\u00ad\u115f\u1160\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\u3164\ufeff\uffa0\n\r\u2028\u2029]|^[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]|[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]$'))
    not valid,
  add constraint documents_in_summary check (direction <> 'in' or (summary is nfc normalized
    and summary !~ '[\u0001-\u0009\u000b\u000c\u000e-\u001f\u007f-\u009f\u00ad\u115f\u1160\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\u3164\ufeff\uffa0\u2028\u2029]|^[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]|[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]$'))
    not valid,
  add constraint documents_in_dates check (direction <> 'in'
    or (issued_on between '1900-01-01' and (created_at at time zone 'Asia/Ho_Chi_Minh')::date
        and (due_on is null or due_on >= issued_on)))
    not valid;

-- 3. Kiểm lại dữ liệu cũ. Còn dòng sai (vd. số ký hiệu dài quá 50 ký tự — bước 1 không tự cắt được) thì migration
--    vẫn chạy, ràng buộc vẫn chặn mọi lần ghi mới, nhưng chính dòng đó không sửa được gì (kể cả vào sổ, đổi trạng
--    thái) cho tới khi sửa nội dung: cảnh báo trong nhật ký Hasura liệt kê mã văn bản (db/README.md).
do $$
declare
  c text;
  rule text;
  bad text;
begin
  foreach c in array array['documents_in_symbol', 'documents_in_issuer', 'documents_in_summary', 'documents_in_dates']
  loop
    begin
      execute format('alter table office.documents validate constraint %I', c);
    exception when check_violation then
      select regexp_replace(pg_get_constraintdef(oid), '^CHECK |\s+NOT VALID$', '', 'g') into rule
        from pg_constraint where conrelid = 'office.documents'::regclass and conname = c;
      execute format('select string_agg(id::text, '', '') from (select id from office.documents where not %s '
                     'limit 20) t', rule) into bad;
      raise warning 'Văn bản đến cũ vi phạm % (sửa rồi chạy: alter table office.documents validate constraint %): %',
        c, c, bad;
    end;
  end loop;
end $$;

drop function pg_temp.moc_clean(text, boolean);
