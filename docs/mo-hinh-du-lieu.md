# Mô hình dữ liệu, Hasura Actions và định dạng sự kiện

> **Bản nháp** cho việc 0.3 / issue #6 — lập ngày 15/10/2026, Backend rà và cùng chốt trong PR.
> Phạm vi sản phẩm: [`dac-ta-san-pham.md`](dac-ta-san-pham.md). Nguồn sự thật giữa Flowable và PostgreSQL:
> [`ke-hoach-phat-trien.md`](ke-hoach-phat-trien.md) §2.1.
> Sau khi chốt, `db/migrations/` (#18) và `db/metadata/actions.*` (#15) làm theo tài liệu này; đổi mô hình
> thì sửa tài liệu trong cùng PR.

---

## 0. Nguyên tắc

- **Hai schema, đúng ranh giới 3 tầng.** `core` là dữ liệu dùng chung của lõi (thuê ước, tệp, sổ kiểm toán)
  — ứng dụng nào cũng dùng. `office` là dữ liệu riêng của ứng dụng Văn phòng điện tử. Ứng dụng khác cắm vào
  lõi thì có schema riêng của nó, không sửa `core`.
- **Mọi bảng nghiệp vụ có `tenant_id`**; quyền Hasura luôn lọc theo `X-Hasura-Tenant-Id`.
- **Keycloak là nguồn sự thật về người dùng.** Bảng nghiệp vụ chỉ lưu `sub` (kiểu `text`); phòng ban của
  người dùng đi trong JWT (`department_id`). `core.users` là **bản sao chỉ đọc** do `svc-workflow` đồng bộ
  từ Keycloak mỗi 15 giây, chỉ để chọn người được giao việc và hiện tên — không ai sửa qua GraphQL.
- **Không xóa.** Văn bản bị hủy thì đổi trạng thái `cancelled`. Không vai trò nào có quyền `delete`
  trên bảng nghiệp vụ. Ngoại lệ duy nhất là job nộp lưu (§2.4), và chỉ xóa sau khi đã ghi gói lưu trữ
  có băm sang kho lạnh.
- **Chỉ `svc-workflow` ghi cột `status`** (vai trò Hasura `service`). Người dùng đổi trạng thái qua Actions.
- **Ràng buộc nằm trong CSDL** (`CHECK`, `UNIQUE`) — lớp thứ ba của Poka-yoke, sau form và Action handler.
- Thời gian: `timestamptz`; ngày theo nghĩa hành chính (ngày ban hành, hạn giải quyết): `date`.

---

## 1. Schema `core` — dùng chung

```sql
create schema core;

create table core.tenants (                 -- cơ quan, đơn vị dùng hệ thống
  id          uuid primary key default gen_random_uuid(),
  code        text not null unique,          -- viết tắt dùng trong ký hiệu văn bản, vd 'KCNTT'
  name        text not null,
  org_ident   text unique,                   -- mã định danh 13 ký tự theo QCVN 102 (tùy chọn)
  created_at  timestamptz not null default now()
);

create table core.files (                   -- tệp đã qua kiểm dịch; tệp nhiễm không có dòng ở đây
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references core.tenants,
  object_key    text not null unique,        -- tenant/<tenant_id>/<yyyy>/<mm>/<uuid>
  filename      text not null,
  mime_type     text not null,
  size_bytes    bigint not null check (size_bytes > 0),
  sha256        bytea  not null check (octet_length(sha256) = 32),
  scanned_at    timestamptz not null,        -- thời điểm ClamAV trả kết quả sạch
  encrypted     boolean not null default false,
  wrapped_dek   text,                        -- khóa dữ liệu đã bọc bởi OpenBao Transit (F3.7)
  storage_tier  text not null default 'hot' check (storage_tier in ('hot', 'cold')),
  created_by    text not null,               -- sub Keycloak hoặc tên tài khoản dịch vụ
  created_at    timestamptz not null default now(),
  check (encrypted = (wrapped_dek is not null))
);

create table core.users (                   -- danh bạ, đồng bộ từ Keycloak (migration 1792281600400)
  id             text primary key,             -- sub của Keycloak
  tenant_id      uuid not null references core.tenants,
  department_id  uuid,                          -- không đặt khóa ngoại: core không phụ thuộc office
  username       text not null,
  full_name      text not null,                 -- "firstName lastName" của Keycloak: họ đệm + tên
  email          text,
  role           text not null check (role in ('clerk', 'staff', 'manager', 'director', 'tenant_admin')),
  enabled        boolean not null default true  -- bị xóa hoặc khóa trong Keycloak: false, không xóa dòng
);

create table core.audit_log (               -- sổ kiểm toán chuỗi băm (F2.12)
  id           bigint primary key,           -- trigger cấp, liên tiếp theo thứ tự chuỗi
  tenant_id    uuid,                         -- null: sự kiện của nền tảng
  occurred_at  timestamptz not null default clock_timestamp(),
  actor_id     text not null,
  actor_kind   text not null check (actor_kind in ('user', 'service', 'agent', 'system')),
  request_id   text,                         -- X-Request-Id do APISIX gắn
  action       text not null,                -- insert | update | tên sự kiện, vd 'file.rejected'
  entity       text not null,                -- 'office.documents'
  entity_id    text not null,
  diff         jsonb not null,               -- {cột: [giá trị cũ, giá trị mới]}
  prev_hash    bytea not null,
  hash         bytea not null unique
);

create table core.audit_anchors (           -- hash đầu chuỗi đã neo ra ngoài CSDL
  id           bigint generated always as identity primary key,
  audit_id     bigint not null references core.audit_log,
  hash         bytea not null,
  location     text not null,                -- 's3://cold/anchors/…' hoặc 'git:anchors/…'
  anchored_at  timestamptz not null default now()
);
```

**Chuỗi băm** (cài ở #18 — `db/migrations/`, cách dùng ở `db/README.md`):

- Trigger `core.audit()` gắn vào mọi bảng nghiệp vụ (trừ `office.document_events`), ghi các cột đã đổi.
- Trigger `before insert` trên `core.audit_log` khóa dòng đầu chuỗi `core.audit_head (last_id, last_hash)`,
  cấp `id = last_id + 1`, đặt `occurred_at`, `prev_hash`, `hash` — người ghi không chọn được các cột này.
  Khóa dòng thay cho `pg_advisory_xact_lock`: ở `READ COMMITTED` giao dịch sau đợi rồi đọc đầu chuỗi mới;
  ở mức cô lập cao hơn thì lỗi tuần tự hóa chứ không rẽ nhánh chuỗi.
- `hash = sha256(prev_hash ‖ jsonb_build_array(id, epoch(occurred_at), tenant_id, actor_id, actor_kind,
  request_id, action, entity, entity_id, diff)::text)`. Thời điểm lấy theo epoch để không phụ thuộc múi giờ
  của phiên; `jsonb::text` cho cùng một chuỗi với cùng một giá trị, nên tính lại được khi kiểm tra.
- Người thực hiện: đọc `current_setting('hasura.user', true)` (Hasura đặt biến này trong mỗi giao dịch);
  dịch vụ ghi thẳng vào CSDL thì `set local moc.actor = '…'` trước khi ghi.
- `core.audit_log` chỉ được ghi thêm (trigger chặn sửa, xóa, `truncate`). `core.audit_verify()` tính lại
  chuỗi, trả về dòng sai và loại lỗi (`hash`, `prev_hash`, `gap`, `head`).

Tệp bị ClamAV chặn **không** có dòng trong `core.files`; `svc-files` ghi sự kiện `file.rejected` vào
`core.audit_log` (màn demo kiểm dịch F3.1).

---

## 2. Schema `office` — ứng dụng Văn phòng điện tử

### 2.1. Danh mục

```sql
create schema office;

create table office.departments (           -- phòng, bộ môn trong một đơn vị
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references core.tenants,
  code       text not null,                  -- viết tắt dùng trong ký hiệu, vd 'ĐT'
  name       text not null,
  unique (tenant_id, code)
);

create table office.document_types (        -- tên loại văn bản theo NĐ 30
  code       text primary key,               -- 'CV', 'QĐ', 'TB', 'TTr', 'KH', 'BC', 'GM', 'BB', 'HD'
  name       text not null,                  -- 'Công văn', 'Quyết định', …
  in_symbol  boolean not null                -- công văn: false — ký hiệu không có tên loại
);

create table office.registers (             -- sổ đăng ký văn bản, mỗi năm một sổ
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references core.tenants,
  direction    text not null check (direction in ('in', 'out')),
  year         int  not null check (year between 2000 and 2100),
  last_number  int  not null default 0 check (last_number >= 0),
  unique (tenant_id, direction, year)
);
```

**Cấp số** (NĐ 30, Điều 15 và 22 — liên tiếp từ 01 trong năm, duy nhất): trong cùng giao dịch với việc
ghi văn bản,

```sql
update office.registers set last_number = last_number + 1
 where tenant_id = $1 and direction = $2 and year = $3
returning last_number;
```

Dòng sổ bị khóa đến hết giao dịch, nên hai văn thư bấm cùng lúc không nhận trùng số; giao dịch lỗi thì
số cũng không bị tiêu. Sổ của năm mới được tạo khi cấp số đầu tiên của năm đó.

Không có sổ riêng cho văn bản mật vì sản phẩm không quản lý bí mật nhà nước
([`dac-ta-san-pham.md`](dac-ta-san-pham.md) §4.4).

### 2.2. Văn bản

```sql
create table office.documents (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references core.tenants,
  direction        text not null check (direction in ('in', 'out')),
  status           text not null,
  type_code        text not null references office.document_types,

  -- thông tin trên văn bản
  symbol           text,                     -- số, ký hiệu như in trên văn bản: '123/ĐHCN-ĐT'
  issuer_name      text,                     -- cơ quan ban hành
  issued_on        date,                     -- ngày ban hành
  summary          text not null check (char_length(summary) between 10 and 500),  -- trích yếu
  urgency          text not null default 'normal'
                   check (urgency in ('normal', 'khan', 'thuong_khan', 'hoa_toc')),
  restricted       boolean not null default false,   -- hạn chế truy cập (F3.7), KHÔNG phải văn bản mật
  is_public        boolean not null default false,   -- cổng xác thực được hiện trích yếu

  -- đăng ký
  register_id      uuid references office.registers,
  register_number  int  check (register_number > 0),
  registered_at    timestamptz,
  due_on           date,                     -- hạn giải quyết chung của văn bản đến

  -- văn bản đi
  department_id    uuid references office.departments,  -- đơn vị soạn thảo
  signer_id        text,                     -- người ký (sub)
  recipients       text[] not null default '{}',        -- nơi nhận, như in trên văn bản
  reply_to_id      uuid references office.documents,    -- trả lời văn bản đến nào
  content_sha256   bytea unique check (content_sha256 is null or octet_length(content_sha256) = 32),
  verify_code      text unique check (verify_code is null or verify_code ~ '^[A-Z2-7]{10}$'),

  -- liên kết
  source_id        uuid references office.documents,    -- văn bản đi nội bộ sinh ra văn bản đến này (F3.12)
  process_id       text unique,              -- processInstanceId của Flowable
  created_by       text not null,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),

  check (
       (direction = 'in'  and status in ('received', 'registered', 'in_progress', 'done', 'archived', 'cancelled'))
    or (direction = 'out' and status in ('draft', 'in_review', 'returned', 'approved', 'issued', 'archived', 'cancelled'))
  ),
  -- văn bản đến phải đủ thông tin nhận diện
  check (direction <> 'in' or (symbol is not null and issuer_name is not null and issued_on is not null)),
  -- đã vào sổ thì phải có số
  check (registered_at is null or (register_id is not null and register_number is not null)),
  check (direction <> 'in' or status in ('received', 'cancelled') or registered_at is not null),
  -- văn bản đi đã phát hành phải có đủ số, ký hiệu, ngày, băm, mã tra cứu
  check (direction <> 'out' or status not in ('issued', 'archived')
         or (symbol is not null and register_number is not null and issued_on is not null
             and content_sha256 is not null and verify_code is not null and signer_id is not null)),
  check (due_on is null or registered_at is null or due_on >= registered_at::date),
  unique (register_id, register_number)
);

-- chặn vào sổ trùng: cùng cơ quan ban hành, cùng số ký hiệu, cùng ngày
create unique index documents_in_dedup on office.documents
  (tenant_id, lower(issuer_name), symbol, issued_on)
  where direction = 'in' and status <> 'cancelled';

create table office.document_files (
  tenant_id    uuid not null references core.tenants,  -- khóa ngoại kèm tenant_id: văn bản và tệp cùng thuê ước
  document_id  uuid not null references office.documents,
  file_id      uuid not null references core.files,
  role         text not null check (role in ('main', 'attachment', 'draft', 'issued')),
  version      int  not null default 1 check (version > 0),
  added_by     text not null,
  added_at     timestamptz not null default now(),
  primary key (document_id, file_id)
);

create table office.document_acl (          -- ai được xem văn bản hạn chế (F3.7)
  tenant_id    uuid not null references core.tenants,
  document_id  uuid not null references office.documents,
  user_id      text not null,
  granted_by   text not null,
  granted_at   timestamptz not null default now(),
  primary key (document_id, user_id)
);
```

**Khóa ngoại kèm thuê ước.** Bản trong `db/migrations/` viết mọi khóa ngoại giữa các bảng nghiệp vụ (phòng,
sổ, văn bản trả lời, tệp, giao việc) kèm `tenant_id`, vd `foreign key (tenant_id, department_id) references
office.departments (tenant_id, id)`. Nhờ vậy CSDL tự chặn việc trỏ sang dữ liệu của thuê ước khác, kể cả khi
lớp quyền phía trên có lỗi. Riêng `source_id` (F3.12) được trỏ sang thuê ước khác. Văn bản đến chỉ vào được
sổ đến (khóa ngoại kèm `direction`). Các ràng buộc `check` đều có tên (vd `documents_in_identity`), để giao
diện dịch lỗi thành câu tiếng Việt.

Vòng đời trạng thái:

```
Văn bản đến:  received ──registerIncoming──► registered ──chỉ đạo──► in_progress ──xử lý xong──► done ──nộp lưu──► archived
                 └──────────────► cancelled (vào nhầm, trùng)

Văn bản đi:   draft ──submitOutgoing──► in_review ──duyệt đủ cấp──► approved ──văn thư phát hành──► issued ──nộp lưu──► archived
                 ▲                          │
                 └──── returned ◄──trả lại──┘
```

### 2.3. Giao việc và dòng thời gian

```sql
create table office.assignments (           -- ý kiến chỉ đạo và giao việc (NĐ 30, Điều 23)
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references core.tenants,
  document_id    uuid not null references office.documents,
  parent_id      uuid references office.assignments,  -- phòng được giao → phân công tiếp cho người
  department_id  uuid references office.departments,
  user_id        text,
  role           text not null check (role in ('lead', 'support', 'info')),  -- chủ trì / phối hợp / để biết
  instruction    text,                       -- ý kiến chỉ đạo
  due_on         date,
  status         text not null default 'open' check (status in ('open', 'done', 'cancelled')),
  result_note    text,
  assigned_by    text not null,
  assigned_at    timestamptz not null default now(),
  completed_at   timestamptz,
  check (department_id is not null or user_id is not null),
  check ((status = 'done') = (completed_at is not null)),
  check (status <> 'done' or role = 'info' or result_note is not null)
);

-- mỗi văn bản chỉ có một đầu mối chủ trì ở cấp giao đầu tiên
create unique index assignments_one_lead on office.assignments (document_id)
  where role = 'lead' and parent_id is null and status <> 'cancelled';

create table office.document_events (       -- dòng thời gian hiển thị cho người dùng (F2.6)
  id           bigint generated always as identity primary key,
  tenant_id    uuid not null references core.tenants,
  document_id  uuid not null references office.documents,
  kind         text not null,                -- xem danh sách sự kiện ở §5
  actor_id     text not null,
  actor_kind   text not null check (actor_kind in ('user', 'service', 'agent')),
  note         text,
  data         jsonb not null default '{}',
  created_at   timestamptz not null default now()
);
```

`core.audit_log` là bằng chứng kiểm toán, ghi mọi thay đổi dòng. `office.document_events` là dòng thời gian
để hiển thị, chỉ ghi sự kiện nghiệp vụ. Hai bảng không thay thế nhau.

### 2.4. Hồ sơ và lưu trữ

```sql
create table office.case_files (            -- hồ sơ công việc
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references core.tenants,
  department_id    uuid not null references office.departments,
  year             int  not null,
  code             text not null,            -- ký hiệu hồ sơ theo danh mục hồ sơ của đơn vị
  title            text not null,
  retention_years  int  check (retention_years is null or retention_years > 0),  -- null = vĩnh viễn
  status           text not null default 'open' check (status in ('open', 'closed', 'archived')),
  closed_on        date,
  archived_at      timestamptz,
  archive_key      text,                     -- cold/<tenant_id>/case/<id>/
  archive_sha256   bytea,                    -- băm của manifest.json trong gói lưu trữ
  unique (tenant_id, year, code),
  check ((status = 'open') = (closed_on is null)),
  check (status <> 'archived' or (archive_key is not null and archive_sha256 is not null))
);

create table office.case_file_documents (
  case_file_id  uuid not null references office.case_files,
  document_id   uuid not null references office.documents,
  primary key (case_file_id, document_id)
);
```

**Nộp lưu — nóng sang lạnh (F3.8).** Job định kỳ chọn hồ sơ `closed` quá `DXOS_ARCHIVE_AFTER_DAYS`:

1. Ghi gói vào `cold/<tenant_id>/case/<id>/`: `metadata.parquet` (văn bản, giao việc, dòng thời gian),
   `files/<sha256>.pdf`, `manifest.json` liệt kê từng tệp kèm SHA-256.
2. Ghi `archive_key`, `archive_sha256`, `status = 'archived'` vào `case_files`; đổi `storage_tier = 'cold'`
   của các tệp.
3. Xóa khỏi OLTP các dòng `assignments`, `document_events`, `document_files` của hồ sơ đó. **Giữ** dòng
   `documents` rút gọn (trạng thái `archived`) để vẫn tìm thấy và cổng xác thực vẫn trả lời được.
4. Sự kiện `case_file.archived` kèm `archive_sha256` vào `core.audit_log`.

Xem lại hồ sơ đã lưu: `svc-files` đọc Parquet bằng DuckDB, hiển thị trong phòng đọc ảo.

### 2.5. Khung nhìn cho báo cáo

Hasura theo dõi các view sau, cùng quy tắc lọc thuê ước như bảng gốc:

| View | Dùng cho |
|---|---|
| `office.v_register_in`, `office.v_register_out` | Sổ đăng ký văn bản đến / đi theo năm, xuất PDF (F2.8) |
| `office.v_overdue_by_department` | Dashboard: việc quá hạn theo phòng (F3.11) |
| `office.v_processing_time` | Dashboard: thời gian từ vào sổ đến hoàn thành |

---

## 3. Quyền (Hasura)

JWT do Keycloak cấp, mapper đưa vào claim `https://hasura.io/jwt/claims`:

| Claim | Nguồn |
|---|---|
| `x-hasura-user-id` | `sub` |
| `x-hasura-tenant-id` | thuộc tính người dùng `tenant_id` |
| `x-hasura-department-id` | thuộc tính người dùng `department_id` |
| `x-hasura-allowed-roles`, `x-hasura-default-role` | thuộc tính người dùng `moc_role` (một vai trò mỗi người) |

Ba thuộc tính `tenant_id`, `department_id`, `moc_role` khai trong user profile của realm
(`auth/realm/moc-realm.json`): chỉ quản trị viên xem và sửa được, người dùng không tự đổi đơn vị hay vai trò
của mình. Dùng một thuộc tính cho cả hai claim vai trò để không bao giờ lệch nhau; giá trị bị giới hạn trong 5
vai trò nghiệp vụ, nên không gán được vai trò `admin` của Hasura.

Quyền đọc `office.documents` (các bảng con lọc theo văn bản cha):

| Vai trò | Thấy văn bản nào |
|---|---|
| `clerk`, `director` | Mọi văn bản của thuê ước |
| `manager` | Văn bản do phòng mình soạn, hoặc có việc giao cho phòng mình |
| `staff` | Văn bản mình tạo, có việc giao cho mình, hoặc văn bản đi của phòng mình |
| `tenant_admin` | Không đọc nội dung văn bản; chỉ quản lý phòng ban, xem sổ và danh mục |

Điều kiện chung cho mọi vai trò: `tenant_id = X-Hasura-Tenant-Id`, và với văn bản `restricted = true`
thì người xem phải là người tạo hoặc có trong `office.document_acl`. Quy tắc viết một lần trong hàm SQL
`office.document_visible`; Hasura gắn thành trường `visible`, các bảng con lọc theo `document.visible`.

> **Không đặt tên vai trò là `admin`.** `admin` là vai trò có sẵn của Hasura, bỏ qua mọi quyền kể cả khi nằm
> trong JWT. Chạy thử ở #18: token có `x-hasura-default-role: admin` đọc được dữ liệu của mọi thuê ước.
> Quản trị đơn vị là `tenant_admin`; mapper của realm chỉ đưa 5 vai trò nghiệp vụ vào claim.

Ghi trực tiếp (không qua Action):

| Vai trò | Được làm | Cột đặt sẵn |
|---|---|---|
| `clerk` | Thêm văn bản đến ở trạng thái `received`; sửa thông tin khi còn `received` | `tenant_id`, `created_by`, `direction = 'in'`, `status = 'received'` |
| `staff` | Thêm dự thảo văn bản đi; sửa khi còn `draft` hoặc `returned` | `tenant_id`, `created_by`, `direction = 'out'`, `status = 'draft'` |
| `clerk`, `staff` | Gắn tệp do chính mình tải lên vào văn bản mình còn được sửa (như hai dòng trên); gỡ khi văn bản còn ở bước đó | `tenant_id`, `added_by` |
| `staff`, `manager` | Tạo, đóng hồ sơ công việc của phòng mình; đưa văn bản vào hồ sơ *(Phase 3)* | `tenant_id`, `department_id` |
| `tenant_admin` | Phòng ban | `tenant_id` |

Sổ do `svc-workflow` tạo khi cấp số đầu tiên của năm. Danh mục loại văn bản dùng chung cho mọi thuê ước,
chỉ đổi bằng migration.

Không vai trò người dùng nào sửa được `status`, `register_number`, `symbol` của văn bản đi,
`content_sha256`, `verify_code`, `process_id`.

**Không có vai trò ẩn danh.** Cổng xác thực đi qua `svc-files` (§4.3), không cho truy vấn bảng — nếu không,
người ngoài liệt kê được mọi văn bản đã phát hành.

---

## 4. Hasura Actions và API của dịch vụ

### 4.1. Actions (do `svc-workflow` xử lý)

| Action | Ai gọi | Làm gì |
|---|---|---|
| `registerIncoming(documentId)` | `clerk` | Gọi hàm `office.register_incoming` (một giao dịch: khóa văn bản, lấy số kế tiếp của sổ năm nay, `received → registered`, ghi sự kiện), rồi khởi chạy `van-ban-den` với `businessKey = documentId`. Flowable lỗi thì vẫn giữ số đã cấp; job đối soát (5 phút) khởi chạy sau |
| `myTasks` (query) | `clerk`, `staff`, `manager`, `director` | Việc giao đích danh cho người gọi và việc chưa ai nhận của nhóm vai trò của họ; khẩn xếp trước. Kiểu trả về có quan hệ `document` sang `office_documents`, nên Hasura áp quyền đọc văn bản như mọi truy vấn khác |
| `submitOutgoing(documentId, signerId)` | `staff` | Kiểm dự thảo đủ trường, `draft/returned → in_review`, khởi chạy hoặc tiếp tục `van-ban-di` |
| `completeTask(taskId, outcome, data)` | Người được giao task | Kiểm task thuộc về người gọi, kiểm `data` theo JSON Schema của `formKey`, hoàn thành task Flowable, cập nhật bảng và ghi `document_events` |

Mọi Action **idempotent** theo `(documentId, trạng thái hiện tại)` hoặc `taskId`: gọi lại sau lỗi mạng không
cấp số hai lần. `completeTask` chạy theo thứ tự: kiểm quyền và dữ liệu → nhận việc trong Flowable (người khác
đã nhận thì 409) → ghi PostgreSQL trong một giao dịch, sự kiện mang `task_id` → hoàn thành việc trong Flowable.
Gọi lại khi đã có sự kiện mang `task_id` thì bỏ qua bước ghi; CSDL từ chối thì trả việc về nhóm.

Hasura gửi kèm tiêu đề `X-Moc-Action-Secret`; `svc-workflow` từ chối yêu cầu không mang đúng giá trị.

Nhóm ứng viên trong Flowable (Flowable không biết người dùng Keycloak; `svc-workflow` ánh xạ từ token):
`t:<tenant>:director`, `t:<tenant>:d:<department>:manager`, `t:<tenant>:clerk`; việc đích danh giao theo `sub`.

### 4.2. Task trong BPMN

| Quy trình | Task (`formKey`) | Ai làm | `outcome` | `data` |
|---|---|---|---|---|
| `van-ban-den` | `vbden.chiDao` | `director` | `direct` · `file` (chỉ lưu) | `direct`: `instruction`, đúng một trong `lead_department_id` / `lead_user_id`, `supports[]` (phòng), `due_on`; `file`: `note` |
| | `vbden.phanCong` | `manager` của phòng chủ trì | `assign` · `self` | `user_id`, `note` |
| | `vbden.xuLy` | Người được giao | `done` | `result_note` (`reply_document_id` khi có văn bản đi — Phase 2) |
| `van-ban-di` | `vbdi.duyetPhong` | `manager` của phòng soạn | `approve` · `return` | `note` |
| | `vbdi.duyetDonVi` | `director` (người ký) | `approve` · `return` | `note` |
| | `vbdi.phatHanh` | `clerk` | `issue` | `is_public` |

`vbdi.phatHanh` với `outcome = issue`: `svc-workflow` cấp số đi → gọi `svc-files` dựng PDF từ mẫu, chèn số,
ký hiệu, ngày, mã QR → tính SHA-256 → sinh `verify_code` → `status = issued` → giao bản cho nơi nhận nội bộ
(F3.12).

Timer: mỗi user task có timer `DXOS_SLA_DURATION` (thật `PT24H` — NĐ 30 yêu cầu trình trong ngày; demo
`PT1M`) → nhắc → leo thang lên lãnh đạo đơn vị. Văn bản đến có `due_on` → timer theo hạn giải quyết.
Văn bản khẩn: biến `urgency` để hộp việc xếp lên đầu.

### 4.3. API REST của `svc-files`

| Đường dẫn (qua APISIX) | Ai gọi | Làm gì |
|---|---|---|
| `POST /api/files` | Người đăng nhập | Quét ClamAV → ghi SeaweedFS → thêm dòng `core.files`; nhiễm thì trả 422 và ghi `file.rejected` |
| `GET /api/files/{id}` | Người có quyền với văn bản chứa tệp | Kiểm quyền qua Hasura; tệp mã hóa thì giải mã trong bộ nhớ, thêm watermark |
| `GET /api/search?q=` | Người đăng nhập | Meilisearch, lọc thuê ước và quyền phía server |
| `GET /api/verify/{code}` | Ẩn danh | `{result, symbol, issued_on, issuer, summary?, sha256}`; `summary` chỉ có khi `is_public` |
| `GET /api/verify?sha256=…` | Ẩn danh | Như trên, tra theo băm do trình duyệt tự tính |

`GET /api/files/{id}` (đã làm ở #19): svc-files hỏi Hasura `core_files_by_pk` **bằng token của người gọi** —
Hasura trả dòng khi người gọi là người tải lên hoặc đọc được văn bản có gắn tệp — rồi mới lấy `object_key`
bằng vai trò `service`. Không có tệp và không được xem đều trả 404. Tệp luôn trả về dạng `attachment` kèm
`Content-Security-Policy: sandbox`, để tệp HTML/SVG người dùng tải lên không chạy được trên tên miền của Mộc.

`GET /api/search` (đã làm ở #20): Meilisearch tìm với điều kiện `tenant_id` lấy từ token và chỉ trả về id;
svc-files hỏi lại Hasura `office_documents(where: {id: {_in: …}})` bằng token của người gọi, giữ những văn bản
họ được đọc theo đúng thứ tự xếp hạng. Không trả tổng số kết quả. Chỉ mục được đồng bộ mỗi vài giây theo
`office.documents.updated_at`.

`verify_code`: 10 ký tự base32 ngẫu nhiên (50 bit) — không đoán, không liệt kê được. APISIX giới hạn tốc độ
`/api/verify/*` theo IP.

---

## 5. Định dạng sự kiện

Một khuôn chung cho thông báo realtime (Centrifugo), callback và `office.document_events`:

```json
{
  "id": "01JA4Z3K8Q8N6R2V5W7X9Y0B1C",
  "type": "office.document.assigned",
  "tenant_id": "6f1c…",
  "occurred_at": "2026-10-20T09:15:00+07:00",
  "actor": { "id": "a1b2…", "kind": "user" },
  "subject": { "kind": "document", "id": "3c4d…" },
  "request_id": "f00d…",
  "data": { "assignment_id": "…", "due_on": "2026-10-23" }
}
```

`id` là ULID. `request_id` lấy từ `X-Request-Id` để nối sự kiện với log.

| `type` | Phát khi |
|---|---|
| `office.document.received` | Văn thư thêm văn bản đến |
| `office.document.registered` | Vào sổ, có số đến |
| `office.document.directed` | Lãnh đạo ghi ý kiến chỉ đạo |
| `office.document.assigned` | Có việc giao cho một người hoặc phòng |
| `office.document.processed` | Người được giao báo xong |
| `office.document.filed` | Lãnh đạo cho lưu, không xử lý |
| `office.document.submitted` / `approved` / `returned` | Văn bản đi được trình / duyệt / trả lại |
| `office.document.issued` | Văn bản đi được phát hành |
| `office.task.due_soon` / `office.task.overdue` / `office.task.escalated` | Timer của Flowable |
| `office.case_file.archived` | Hồ sơ nộp lưu xong |
| `core.file.rejected` | ClamAV chặn tệp |
| `ot.alarm` | Cảm biến vượt ngưỡng (F3.10) |

Kênh Centrifugo: kênh giới hạn theo người dùng (`…#<sub>`) cho hộp việc của từng người; kênh
`dashboard:<tenant_id>` cho dashboard. Callback từ Flowable gọi `POST /internal/flowable/events` của
`svc-workflow` (chỉ trong mạng nội bộ, không qua APISIX).

---

## 6. Việc cần chốt khi rà PR

1. Danh sách loại văn bản ban đầu và cách sinh ký hiệu (công văn: `số/viết tắt đơn vị-viết tắt phòng`;
   loại khác: `số/tên loại-viết tắt đơn vị`) — đối chiếu phụ lục NĐ 30.
2. Văn bản đi gửi nhiều đơn vị trong hệ thống: một văn bản đến cho mỗi đơn vị nhận (`source_id` trỏ về
   văn bản đi) — đã chọn; Backend xác nhận.
3. `completeTask` dùng chung hay tách Action theo từng task — bản nháp chọn dùng chung, kiểm theo `formKey`.
4. ~~Phạm vi Phase 1~~ — #18 làm toàn bộ §1 và §2.1–2.3, cùng trigger sổ kiểm toán. Còn `case_files`,
   `case_file_documents` và các view ở §2.5 (Phase 2–3).
5. Danh mục loại văn bản: #18 nạp 27 loại có tên viết tắt (NĐ 30, Phụ lục III) và `CV` (công văn); chưa có
   thư công. Backend đối chiếu khi rà.
