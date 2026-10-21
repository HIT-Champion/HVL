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

create or replace view office.issued_documents as
select d.verify_code,
       d.content_sha256,
       d.symbol,
       d.issued_on,
       d.type_code,
       dt.name   as type_name,
       t.name    as issuer_name,
       t.parent_name,
       case when d.is_public then d.summary end as summary,
       d.status
  from office.documents d
  join core.tenants t on t.id = d.tenant_id
  join office.document_types dt on dt.code = d.type_code
 where d.direction = 'out' and d.status in ('issued', 'archived');
alter table office.documents drop constraint documents_restricted_private;

drop function office.audit_overview_seen(core.audit_log, json);
drop trigger documents_restricted_notifications on office.documents;
drop function office.documents_restricted_notifications();
drop trigger notifications_restricted on core.notifications;
drop function office.notifications_restricted();
drop function office.notification_redacted(jsonb);

drop function office.revoke_document_access(uuid, text, json);
drop function office.grant_document_access(uuid, text, json);
drop function office.document_acl_target(uuid, json);

create or replace function core.file_texts_skip_restricted() returns trigger
language plpgsql as $$
begin
  if exists (select 1 from office.document_files f
               join office.documents d on d.tenant_id = f.tenant_id and d.id = f.document_id
              where f.file_id = new.file_id and d.restricted) then
    return null;
  end if;
  return new;
end $$;

drop trigger documents_restricted_sealed on office.documents;
drop function office.documents_restricted_sealed();
drop trigger document_files_sealed on office.document_files;
drop function office.document_files_sealed();
