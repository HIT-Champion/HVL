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

-- Ứng dụng cắm vào lõi bằng manifest (`moc app install`, scripts/ung_dung.py, docs/them-ung-dung.md mục 1). Ba bảng của
-- lõi, không bảng nào cho vai trò người dùng đọc:
--   core.apps            ứng dụng đã cài (và đã gỡ: removed_at — gỡ không xóa dữ liệu của ứng dụng)
--   core.app_migrations  migration của ứng dụng đã áp, SHA-256 nội dung: không áp lại, không sửa được im lặng
--   core.app_events      luồng sự kiện ĐÃ LÀM SẠCH mà ứng dụng nghe được qua Hasura Event Triggers
-- và schema moc_app: hàm duy nhất vai trò CSDL của ứng dụng được gọi, cuối mỗi migration (mục cuối tệp).
-- Trạng thái mong muốn (manifest, SQL) nằm trong .moc-apps/ của thư mục chạy; ở đây là trạng thái đã áp, có sổ kiểm
-- toán.

create table core.apps (
  name             text primary key check (name ~ '^[a-z][a-z0-9]*(-[a-z0-9]+)*$'
                                           and char_length(name) between 2 and 30),
  title            text not null check (btrim(title) <> ''),
  path             text not null check (path ~ '^/[a-z][a-z0-9]*(-[a-z0-9]+)*$'),
  schema_name      text not null unique check (schema_name ~ '^[a-z][a-z0-9_]*$' and char_length(schema_name) <= 50
                                                and schema_name not in ('core', 'office', 'personal', 'public',
                                                                        'moc_app')),
  version          text not null,
  manifest         jsonb not null,           -- manifest đã kiểm, như lúc cài (không có bí mật)
  manifest_sha256  text not null check (manifest_sha256 ~ '^[0-9a-f]{64}$'),
  installed_at     timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  removed_at       timestamptz
);

-- Đường chỉ duy nhất giữa các ứng dụng đang cài: ứng dụng đã gỡ trả đường cho ứng dụng khác (schema, dữ liệu vẫn là
-- của nó)
create unique index apps_path_active on core.apps (path) where removed_at is null;

create table core.app_migrations (
  app         text not null references core.apps,
  version     bigint not null check (version >= 0),
  name        text not null check (name ~ '^[a-z0-9_]+$'),
  sha256      text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  applied_at  timestamptz not null default now(),
  primary key (app, version)
);

create trigger audit after insert or update or delete on core.apps
  for each row execute function core.audit('name');
create trigger audit after insert or update or delete on core.app_migrations
  for each row execute function core.audit('app', 'version');

-- ---------------------------------------------------------------------------
-- Sự kiện cho ứng dụng: DANH SÁCH TRẮNG do lõi quy định. Mỗi dòng office.document_events thuộc loại dưới đây, của văn
-- bản KHÔNG hạn chế (F3.7), được chép sang core.app_events với đúng 5 cột: không note, không data (số ký hiệu, mã tra
-- cứu, băm, ý kiến chỉ đạo…), không người làm. Văn bản hạn chế không lộ cả sự tồn tại. Ứng dụng muốn biết thêm thì hỏi
-- GraphQL bằng token của người dùng — Hasura xét quyền như mọi lần đọc khác. Mỗi ứng dụng khai `events` trong manifest
-- có một Hasura Event Trigger trên bảng này (metadata do moc app sinh); Hasura tự gửi lại khi webhook lỗi.
-- Danh sách loại phải trùng EVENT_KINDS trong scripts/ung_dung.py và enum trong scripts/app-manifest.schema.json
-- (test kiểm).
-- Hasura gửi thân sự kiện chuẩn của nó, có session_variables lấy từ biến hasura.user của giao dịch (người làm việc):
-- hàm chép đặt hasura.user = 'null' trong lúc ghi core.app_events (mệnh đề SET của hàm, tự trả lại khi hàm xong), nên
-- ứng dụng nhận session_variables null — không biết ai đã làm.
-- ---------------------------------------------------------------------------

create table core.app_events (
  id           bigint primary key,           -- = office.document_events.id: khóa chống trùng cho ứng dụng
  tenant_id    uuid not null references core.tenants,
  document_id  uuid not null,
  kind         text not null check (kind in ('office.document.received', 'office.document.registered',
                                             'office.document.issued')),
  occurred_at  timestamptz not null
);

create index app_events_occurred on core.app_events (occurred_at);

create function core.app_events_publish() returns trigger
language plpgsql security definer set search_path = pg_catalog, pg_temp set "hasura.user" = 'null'
as $$
begin
  if new.kind = any (array['office.document.received', 'office.document.registered', 'office.document.issued'])
     and exists (select 1 from office.documents d
                  where d.id = new.document_id and d.tenant_id = new.tenant_id and not d.restricted) then
    insert into core.app_events (id, tenant_id, document_id, kind, occurred_at)
    values (new.id, new.tenant_id, new.document_id, new.kind, new.created_at);
  end if;
  return null;
end
$$;

create trigger app_events after insert on office.document_events
  for each row execute function core.app_events_publish();

-- ---------------------------------------------------------------------------
-- Migration của ứng dụng chạy trên một phiên mà session user là VAI TRÒ CSDL RIÊNG của ứng dụng, moc_appdb_<schema>
-- (moc app tạo: NOLOGIN ngoài lúc chạy migration, không SUPERUSER, CREATEROLE, CREATEDB, BYPASSRLS, không thành viên
-- vai trò nào; làm chủ schema của mình, không quyền gì trên core, office, personal). RESET ROLE, SQL động không leo lên
-- được vai trò nào khác; đọc, ghi, tham chiếu lõi thì PostgreSQL báo "permission denied".
-- Cuối mỗi migration, CÙNG giao dịch, phiên đó gọi moc_app.migration_done(): kiểm những gì schema đang có rồi mới ghi
-- core.app_migrations; kiểm không qua thì cả migration hủy. Vì sao phải kiểm: Hasura nối CSDL bằng `moc` (superuser) và
-- đọc, ghi bảng của ứng dụng bằng vai trò đó. View đọc bảng bằng quyền của CHỦ view (vai trò ứng dụng), nhưng hàm gọi
-- trong view, default, check, trigger, chỉ mục chạy bằng quyền của NGƯỜI GỌI (Hasura). Nên:
--   - hàm, thủ tục trong schema ứng dụng bị đặt SECURITY DEFINER: luôn chạy bằng vai trò ứng dụng;
--   - biểu thức lưu trong schema chỉ được đọc bảng trong chính schema đó, gọi hàm trong schema hoặc hàm của PostgreSQL
--     không đọc gì (IMMUTABLE, ai cũng gọi được) và vài hàm thời gian, sinh số (danh sách dưới) — không view hệ thống
--     (pg_stat_activity cho superuser thấy câu lệnh của phiên khác), không query_to_xml, set_config, nextval (serial:
--     dùng generated … as identity);
--   - không view security_invoker, không CAST trên kiểu của ứng dụng, không đối tượng nào của vai trò nằm ngoài schema.
-- ---------------------------------------------------------------------------

create schema moc_app;
revoke all on schema moc_app from public;

create function moc_app.migration_done(p_app text, p_version bigint, p_name text, p_sha text) returns json
language plpgsql security definer set search_path = pg_catalog, pg_temp
as $$
declare
  v_schema text;
  v_ns     oid;
  v_role   oid;
  v_bad    text;
  r        record;
begin
  select a.schema_name into v_schema from core.apps a where a.name = p_app and a.removed_at is null;
  if v_schema is null then
    raise exception 'moc_app: ứng dụng % chưa ghi trong core.apps', p_app;
  end if;
  if session_user::text <> 'moc_appdb_' || v_schema then
    raise exception 'moc_app: migration của % phải chạy bằng vai trò moc_appdb_%', p_app, v_schema;
  end if;
  select oid into v_ns from pg_namespace where nspname = v_schema;
  select oid into v_role from pg_roles where rolname = session_user;

  -- đối tượng của vai trò ứng dụng nằm ngoài schema (kể cả large object, quyền mặc định toàn cục); bảng tạm thì bỏ qua
  select string_agg(pg_describe_object(s.classid, s.objid, s.objsubid), ', ') into v_bad
    from pg_shdepend s
   where s.refclassid = 'pg_authid'::regclass and s.refobjid = v_role and s.deptype = 'o'
     and s.dbid = (select oid from pg_database where datname = current_database())
     and not (s.classid = 'pg_namespace'::regclass and s.objid = v_ns)
     and coalesce((pg_identify_object(s.classid, s.objid, 0)).schema, '-') <> v_schema
     and coalesce((pg_identify_object(s.classid, s.objid, 0)).schema, '-') !~ '^pg_(toast_)?temp(_|$)';
  if v_bad is not null then
    raise exception 'moc_app: % tạo đối tượng ngoài schema %: %', p_app, v_schema, v_bad;
  end if;

  -- đối tượng trong schema không thuộc vai trò ứng dụng (vd còn lại từ cách cài cũ, chủ là superuser)
  select string_agg(x, ', ') into v_bad from (
    select c.oid::regclass::text as x from pg_class c where c.relnamespace = v_ns and c.relowner <> v_role
    union all
    select p.oid::regprocedure::text from pg_proc p where p.pronamespace = v_ns and p.proowner <> v_role) o;
  if v_bad is not null then
    raise exception 'moc_app: trong schema % có đối tượng không thuộc moc_appdb_%: %', v_schema, v_schema, v_bad;
  end if;

  -- Biểu thức lưu trong schema (view, rule, default, check, chỉ mục, trigger, policy, domain, toán tử, aggregate):
  -- bảng nó đọc phải trong schema; hàm nó gọi phải trong schema (thành SECURITY DEFINER ở dưới) hoặc là hàm của
  -- PostgreSQL không đọc gì. pg_depend không ghi phụ thuộc vào đối tượng có sẵn của PostgreSQL (pinned) nên đọc thẳng
  -- cây biểu thức: :funcid/:aggfnoid/:winfnoid là hàm, :relid là bảng trong FROM, :seqid là sequence của cột identity.
  -- Toán tử có sẵn (:opno) là phép tính thuần; toán tử của ứng dụng thì kiểm hàm của nó (dòng operator).
  with exprs(what, tree) as (
    select format('view/rule %s', c.oid::regclass), w.ev_action::text || coalesce(w.ev_qual::text, '')
      from pg_rewrite w join pg_class c on c.oid = w.ev_class where c.relnamespace = v_ns
    union all
    select format('default %s.%s', c.oid::regclass, a.attname), d.adbin::text
      from pg_attrdef d join pg_class c on c.oid = d.adrelid
      join pg_attribute a on a.attrelid = d.adrelid and a.attnum = d.adnum
     where c.relnamespace = v_ns
    union all
    select format('ràng buộc %s', k.conname), k.conbin::text
      from pg_constraint k where k.connamespace = v_ns and k.conbin is not null
    union all
    select format('chỉ mục %s', i.indexrelid::regclass), coalesce(i.indexprs::text, '') || coalesce(i.indpred::text, '')
      from pg_index i join pg_class c on c.oid = i.indrelid where c.relnamespace = v_ns
    union all
    select format('trigger %s', t.tgname), coalesce(t.tgqual::text, '') || format(' :funcid %s ', t.tgfoid)
      from pg_trigger t join pg_class c on c.oid = t.tgrelid where c.relnamespace = v_ns and not t.tgisinternal
    union all
    select format('policy %s', p.polname), coalesce(p.polqual::text, '') || coalesce(p.polwithcheck::text, '')
      from pg_policy p join pg_class c on c.oid = p.polrelid where c.relnamespace = v_ns
    union all
    select format('thống kê %s', x.stxname), coalesce(x.stxexprs::text, '')
      from pg_statistic_ext x where x.stxnamespace = v_ns
    union all
    select format('kiểu %s', t.oid::regtype), coalesce(t.typdefaultbin::text, '')
      from pg_type t where t.typnamespace = v_ns
    union all
    select format('toán tử %s', o.oid::regoperator), format(' :funcid %s ', o.oprcode::oid)
      from pg_operator o where o.oprnamespace = v_ns
    union all
    select format('aggregate %s', g.aggfnoid::regprocedure),
           format(' :funcid %s :funcid %s :funcid %s :funcid %s :funcid %s :funcid %s :funcid %s :funcid %s ',
                  g.aggtransfn::oid, g.aggfinalfn::oid, g.aggcombinefn::oid, g.aggserialfn::oid,
                  g.aggdeserialfn::oid, g.aggmtransfn::oid, g.aggminvtransfn::oid, g.aggmfinalfn::oid)
      from pg_aggregate g join pg_proc p on p.oid = g.aggfnoid where p.pronamespace = v_ns
    union all
    select format('range %s', g.rngtypid::regtype),
           format(' :funcid %s :funcid %s ', g.rngsubdiff::oid, g.rngcanonical::oid)
      from pg_range g join pg_type t on t.oid = g.rngtypid where t.typnamespace = v_ns
  ), refs as (
    select e.what, m[1] as kind, m[2]::oid as ref
      from exprs e cross join lateral regexp_matches(e.tree, ':(funcid|aggfnoid|winfnoid|relid|seqid) ([0-9]+)', 'g') m
  )
  select string_agg(distinct format('%s → %s', f.what,
                                    case when f.kind in ('relid', 'seqid') then f.ref::regclass::text
                                         else f.ref::regprocedure::text end), '; ')
    into v_bad
    from refs f
   where f.ref <> 0 and case
     when f.kind in ('relid', 'seqid') then
       (select c.relnamespace from pg_class c where c.oid = f.ref) is distinct from v_ns
     else not exists (
       select 1 from pg_proc p
        where p.oid = f.ref
          and (p.pronamespace = v_ns
               or (p.pronamespace = 'pg_catalog'::regnamespace
                   and has_function_privilege('public', p.oid, 'EXECUTE')
                   and p.proname !~ '^(pg_|lo_|dblink)|_to_xml|^ts_(stat|rewrite)$|^(set_config|current_setting)$'
                   and (p.provolatile = 'i'
                        or p.proname = any (array['now', 'statement_timestamp', 'transaction_timestamp',
                                                  'clock_timestamp', 'timeofday', 'gen_random_uuid', 'random',
                                                  'to_char', 'to_date', 'to_timestamp', 'date_trunc', 'date_part',
                                                  'extract', 'age', 'timezone', 'date'])))))
   end;
  if v_bad is not null then
    raise exception 'moc_app: % dùng bảng ngoài schema % hoặc hàm không được phép (biểu thức này chạy bằng quyền của '
                    'Hasura khi được đọc, ghi; cột tự tăng: dùng generated … as identity, không serial): %',
                    p_app, v_schema, v_bad;
  end if;

  select string_agg(c.oid::regclass::text, ', ') into v_bad
    from pg_class c
   where c.relnamespace = v_ns and c.relkind in ('v', 'm')
     and exists (select 1 from unnest(coalesce(c.reloptions, '{}')) o where o ~* '^security_invoker=(t|on|y|1)');
  if v_bad is not null then
    raise exception 'moc_app: view security_invoker đọc bằng quyền của người gọi (Hasura): %', v_bad;
  end if;

  select string_agg(format('%s → %s', c.castsource::regtype, c.casttarget::regtype), ', ') into v_bad
    from pg_cast c join pg_type t on t.oid in (c.castsource, c.casttarget)
   where t.typnamespace = v_ns;
  if v_bad is not null then
    raise exception 'moc_app: không tạo CAST trên kiểu của ứng dụng: %', v_bad;
  end if;

  for r in select p.oid::regprocedure as f from pg_proc p
            where p.pronamespace = v_ns and p.prokind in ('f', 'p') and not p.prosecdef loop
    execute format('alter routine %s security definer', r.f);
  end loop;

  insert into core.app_migrations (app, version, name, sha256) values (p_app, p_version, p_name, p_sha);
  return json_build_object('ok', true);
end
$$;

revoke all on function moc_app.migration_done(text, bigint, text, text) from public;
