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
- **Ràng buộc nằm trong CSDL** (`CHECK`, `UNIQUE`) — lớp thứ ba của Poka-yoke, sau form và Action handler. Cả
  ba lớp theo một JSON Schema dùng chung ở `schemas/` ([`schemas/README.md`](../schemas/README.md)).
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
  -- in trên văn bản đi theo thể thức NĐ 30/2020; quản trị đơn vị sửa được
  parent_name text,                          -- cơ quan chủ quản: 'Trường Đại học …'
  place_name  text,                          -- địa danh trước ngày tháng: 'Hà Nội'
  head_title  text,                          -- chức vụ người đứng đầu ở phần ký: 'Trưởng khoa'
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

create table core.file_texts (              -- lớp chữ của PDF để tìm theo nội dung (F2.7, migration 1792281601000)
  file_id       uuid primary key,             -- (tenant_id, file_id) tham chiếu core.files, xóa tệp thì xóa theo
  tenant_id     uuid not null,
  status        text not null check (status in ('ok', 'empty', 'failed')),   -- empty: bản scan, chờ OCR (F4.1)
  pages         int,
  content       text not null default '' check (char_length(content) <= 50000),
  note          text,                         -- lý do khi failed: encrypted, timeout, memory, too large…
  extracted_at  timestamptz not null default now()
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

create table core.notifications (           -- thông báo từng người (F2.5, migration 1792281600600)
  id           bigint generated always as identity primary key,
  tenant_id    uuid not null references core.tenants,
  user_id      text not null,                -- (tenant_id, user_id) → core.users
  kind         text not null,                -- task.assigned | task.overdue | task.escalated | document.*
  key          text not null,                -- chống gửi trùng: unique (tenant_id, user_id, key)
  document_id  uuid,
  data         jsonb not null default '{}',  -- form_key, trích yếu, số ký hiệu… lúc gửi; câu chữ dựng ở giao diện
  created_at   timestamptz not null default now(),
  read_at      timestamptz
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

create table core.audit_anchors (           -- bản tra cứu các lần neo đầu chuỗi ra ngoài CSDL
  id           bigint generated always as identity primary key,
  audit_id     bigint not null references core.audit_log,
  hash         bytea not null,
  location     text not null,                -- 's3://moc-cold/anchors/<audit_id>-<hash>.json'
  anchored_at  timestamptz not null default now(),
  unique (audit_id, location)                -- migration 1792281600700
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

**Neo ra ngoài CSDL và kiểm từ bên ngoài** (F2.12, migration 1792281600700):

- Superuser tắt được trigger, sửa một dòng rồi tính lại hash của mọi dòng phía sau, kể cả `core.audit_head`:
  chuỗi lại liền mạch và `core.audit_verify()` báo nguyên vẹn. Chặn bằng **mốc neo**: `svc-files` định kỳ
  (`MOC_AUDIT_ANCHOR_INTERVAL_S`, mặc định 600 giây, chỉ khi có dòng mới) chép `(last_id, last_hash)` thành đối
  tượng `anchors/<last_id 12 chữ số>-<hash>.json` trên bucket lạnh `moc-cold`. Bucket tạo với S3 Object Lock;
  mỗi đối tượng giữ ở chế độ COMPLIANCE `MOC_AUDIT_ANCHOR_RETENTION_DAYS` ngày (mặc định 3650): không ai xóa,
  ghi đè hay rút ngắn hạn được, kể cả tài khoản quản trị của kho. Ghi lại cùng khóa chỉ tạo thêm phiên bản, bản
  đầu vẫn còn và lúc kiểm mang cờ. Hash nằm ngay trong tên đối tượng, nên lệnh kiểm chỉ cần liệt kê bucket.
- Khóa ghi chỉ có hiệu lực khi đi qua cổng S3: gọi thẳng filer của SeaweedFS thì xóa được cả mốc đang khóa (đã
  thử). Vì vậy SeaweedFS chạy với `-filer.disableHttp` và nằm riêng mạng `storage` với `svc-files`; PostgreSQL
  (superuser chạy được lệnh hệ điều hành qua `COPY … TO PROGRAM`) không tới được kho.
- Vòng neo nhớ mốc vừa ghi trong bộ nhớ, không hỏi `core.audit_anchors`: thêm dòng giả vào bảng đó không làm
  vòng neo dừng.
- `core.audit_anchors` là bản tra cứu trong CSDL (màn xem sổ dùng để báo dòng nào đã neo); khi kiểm không tin
  bảng này.
- **`make audit`** (`scripts/moc.py audit verify`) tính lại cả chuỗi bên ngoài CSDL: PostgreSQL chỉ dựng chuỗi
  JSON của từng dòng bằng `pg_catalog.jsonb_build_array` (cùng biểu thức với `core.audit_hash`), còn băm và nối
  chuỗi tính bằng Python. Ba lớp: chuỗi liền mạch; hash của dòng tại mỗi mốc bằng hash đã neo (viết lại chuỗi
  từ dòng k thì mọi mốc từ k lệch, dòng bị sửa nằm giữa mốc cuối còn khớp và mốc đầu bị lệch); `content_sha256`
  của mọi văn bản bằng giá trị lần cuối ghi vào sổ (đổi hash để một tệp giả "khớp" ở cổng xác thực mà tắt
  trigger thì bị bắt). `audit anchor --to <tệp>` ghi thêm một bản mốc vào tệp để chép ra ngoài máy chủ.
- **Xem sổ:** `director`, `tenant_admin` đọc dòng sổ của đơn vị mình nhưng không đọc cột `diff`; trường tính
  toán `overview` (`core.audit_overview(r)`) giữ tên mọi cột đã đổi, còn giá trị chỉ giữ ở các cột không chứa
  nội dung (trạng thái, số, ngày, cờ, mã người, mã văn bản; năm, số dòng của lần in sổ đăng ký — migration
  1792281600900; mẫu mã độc, cỡ tệp của tệp bị ClamAV chặn — migration 1792281601100, tên tệp vẫn ẩn). Lãnh đạo không đọc được văn bản hạn chế thì sổ
  cũng không lộ trích yếu, nội dung, cả hash của nó (có hash là tra được văn bản ở cổng xác thực). Trường
  `overview` thật ra là `office.audit_overview_seen(r, hasura_session)` (migration 1792281601600, nằm ở `office` vì
  `core` không phụ thuộc `office`): dòng sổ về văn bản hạn chế mà người xem sổ không đọc được (chính văn bản, tệp gắn
  vào, giao việc, lần vào hồ sơ, danh sách được xem) chỉ còn tên trường, mọi giá trị là null — trạng thái, độ khẩn,
  hạn, người ký cũng không lộ. Ai có tên trong danh sách được xem vẫn thấy qua `entity_id` của dòng `document_acl`. Mốc neo mở cho hai vai trò này `audit_id`, `anchored_at`: chuỗi
  chung cho cả nền tảng nên mốc không thuộc riêng đơn vị nào.
- **Lịch sử của một văn bản** (F3.5, tab "Lịch sử" trên trang văn bản): view `office.document_history` (migration
  1792281601500) gồm các dòng sổ về chính văn bản, tệp gắn với nó (`entity_id` "<văn bản>/<tệp>"), các lần giao
  việc, lần đưa vào hồ sơ (bỏ id hồ sơ); cột `document_id`, `id`, `occurred_at`, `actor_id`, `actor_kind`, `action`,
  `entity`, `overview` — không có `diff`, không có hash. Không gồm danh sách được xem văn bản hạn chế
  (`document_acl`): người có tên không được biết ai khác cũng có tên. `staff`, `manager`, `clerk`, `director` đọc khi
  đọc được văn bản (computed field `visible` qua quan hệ `document`), tối đa 500 dòng mỗi lần. Mỗi nhánh của view nối
  bằng `=` trên chỉ mục (`audit_log (entity, split_part(entity_id, '/', 1))` và chỉ mục riêng cho dòng hồ sơ), lọc
  theo một văn bản không quét cả sổ.

Tệp bị ClamAV chặn **không** có dòng trong `core.files`; `svc-files` ghi sự kiện `file.rejected` vào
`core.audit_log` (màn demo kiểm dịch F3.1).

Khôi phục từ bản sao lưu (`moc backup restore`, F3.4) ghi sự kiện `system.restored` của nền tảng (`tenant_id` null,
`entity` = `backup`, `entity_id` = mã lượt) ngay sau đầu chuỗi vừa khôi phục. Bản sao lưu gồm mọi CSDL (`pg_dump
-Fc`) và cả volume SeaweedFS (tệp, bucket lạnh với mốc neo); chỉ mục Meilisearch dựng lại từ CSDL khi `svc-files`
khởi động.

**Lớp chữ của PDF** (`core.file_texts`, F2.7): `svc-files` đọc ở vòng nền các PDF đã gắn vào văn bản, trong tiến
trình con có giới hạn, rồi ghi bằng khóa quản trị; vòng đồng bộ tìm kiếm đưa vào trường `content` của
Meilisearch. Không vai trò người dùng nào đọc được bảng này. Tệp của văn bản hạn chế không được đọc chữ và nội
dung văn bản hạn chế không vào chỉ mục (bản chữ trần sẽ vô hiệu việc mã hóa tệp — F3.7). Trigger giữ điều này ở
CSDL: chữ của tệp gắn vào văn bản hạn chế bị bỏ qua khi ghi, và bị xóa khi văn bản bật hạn chế hoặc khi tệp được
gắn vào văn bản hạn chế. Bảng không gắn sổ kiểm
toán: chữ là dữ liệu dẫn xuất, tính lại được từ tệp mà băm đã nằm trong `core.files` và trong sổ.

**Thông báo** (`core.notifications`): dịch vụ ghi bằng vai trò `service`; mỗi người chỉ đọc thông báo của mình
và chỉ sửa được `read_at`. Thông báo về văn bản hạn chế (F3.7) không mang nội dung: trigger `notifications_restricted`
gọt `summary`, `symbol`, `issuer_name`, `note` khỏi `data` và gắn `restricted: true` ở mọi lần ghi, kể cả dịch vụ ghi
sai; văn bản chuyển sang hạn chế thì thông báo đã gửi về nó cũng bị gọt (`documents_restricted_notifications`). Bảng không gắn sổ kiểm toán: thông báo là bản tin phái sinh từ các bước đã kiểm toán.
Centrifugo chỉ đẩy bản sao tới trình duyệt đang mở (§5), nên mất kết nối không mất thông báo.

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
  body             text check (char_length(body) <= 20000),  -- nội dung văn bản đi; mỗi dòng một đoạn
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
  -- poka-yoke lớp 3 (F2.2), cùng quy tắc với schemas/van-ban-den.json: số ký hiệu 1–50 ký tự, cơ quan ban hành
  -- 1–200 ký tự, một dòng; không khoảng trắng ở đầu hoặc cuối, không ký tự ẩn, dạng Unicode NFC; ngày ban hành
  -- từ 1900, không sau ngày tiếp nhận; hạn không trước ngày ban hành (migration 1792281600800)
  constraint documents_in_symbol  check (direction <> 'in' or (char_length(symbol) between 1 and 50
                                                            and symbol is nfc normalized and symbol !~ '…')),
  constraint documents_in_issuer  check (direction <> 'in' or (char_length(issuer_name) between 1 and 200 and …)),
  constraint documents_in_summary check (direction <> 'in' or (summary is nfc normalized and summary !~ '…')),
  constraint documents_in_dates   check (direction <> 'in' or (issued_on between '1900-01-01'
                                                                             and (created_at at time zone 'Asia/Ho_Chi_Minh')::date
                                                           and (due_on is null or due_on >= issued_on))),
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

Đã làm ở F3.8 (migration `1792281601300_case_files`; tóm tắt, bản đủ có thêm kiểm độ dài, mẫu `archive_key`):

```sql
create table office.case_files (            -- hồ sơ công việc
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references core.tenants,
  department_id    uuid not null,            -- (tenant_id, department_id) → office.departments
  year             int  not null,
  code             text not null,            -- ký hiệu hồ sơ theo danh mục hồ sơ của đơn vị
  title            text not null,
  retention_years  int  check (retention_years is null or retention_years between 1 and 100),  -- null = vĩnh viễn
  status           text not null default 'open' check (status in ('open', 'closed', 'archived')),
  closed_on        date,                     -- trigger đặt khi đóng (ngày giờ Việt Nam)
  archived_at      timestamptz,
  archive_key      text,                     -- cold/<tenant_id>/case/<id>/
  archive_sha256   bytea,                    -- băm của manifest-<băm>.json trong gói lưu trữ
  created_by       text not null,
  created_at       timestamptz not null default now(),
  unique (tenant_id, year, code),
  check ((status = 'open') = (closed_on is null)),
  check ((status = 'archived') = (archive_key is not null and archive_sha256 is not null and archived_at is not null))
);

create table office.case_file_documents (
  tenant_id     uuid not null,
  case_file_id  uuid not null,             -- (tenant_id, case_file_id) → office.case_files
  document_id   uuid not null,             -- (tenant_id, document_id) → office.documents
  added_by      text not null,
  added_at      timestamptz not null default now(),
  primary key (case_file_id, document_id),
  unique (document_id)                     -- mỗi văn bản thuộc một hồ sơ
);
```

Trigger giữ quy tắc ở CSDL, mọi đường ghi đều theo:

- Văn bản vào hồ sơ phải đã xử lý xong (đến `done`, đi `issued`), không phải văn bản hạn chế (tệp của nó mã hóa
  riêng, F3.7), và hồ sơ còn `open` (khóa dòng hồ sơ, không lọt văn bản vào hồ sơ vừa đóng). Gỡ văn bản ra chỉ khi
  hồ sơ còn mở.
- Đóng hồ sơ: phải có ít nhất một văn bản; `closed_on` do trigger đặt (ngày theo giờ Việt Nam), không ai chọn được —
  lùi ngày là ép nộp lưu ngay, đẩy ngày là không bao giờ nộp lưu. Đóng rồi không mở lại; đã `archived` thì không sửa
  được nữa, kể cả bằng khóa quản trị.
- Cả hai bảng có trigger `core.audit`. Sổ hiện ký hiệu hồ sơ, ngày đóng, thời hạn bảo quản, băm gói; tên hồ sơ do
  người dùng đặt nên ẩn như trích yếu.

Quyền Hasura: `staff`, `manager` lập hồ sơ cho phòng mình (`tenant_id`, `department_id`, `created_by` đặt sẵn từ
token), đưa vào văn bản mình đọc được và thuộc phòng mình (văn bản đi của phòng, văn bản đến giao cho phòng hoặc cho
mình), đóng hồ sơ (`status` chỉ được `open` hoặc `closed`); `clerk`, `director` xem hồ sơ cả đơn vị. Không vai trò
người dùng nào đặt được `archived`, `archive_key`, `archive_sha256`, `closed_on`.

**Nộp lưu — nóng sang lạnh (F3.8).** Vòng nền của `svc-files` (`MOC_ARCHIVE_INTERVAL_S`, mặc định mỗi giờ) chọn
hồ sơ `closed` từ `MOC_ARCHIVE_AFTER_DAYS` ngày (mặc định 365); một hồ sơ lỗi không chặn hồ sơ khác (bỏ qua nó
24 giờ):

1. Kiểm băm mọi tệp trong bucket nóng, rồi ghi gói vào bucket lạnh có khóa ghi, dưới `cold/<tenant_id>/case/<id>/`,
   mọi tên theo băm nội dung: `documents-<băm>.parquet`, `assignments-<băm>.parquet`, `events-<băm>.parquet` (DuckDB,
   nén zstd, lược đồ cột cố định), `files/<sha256>` (nguyên byte), `manifest-<băm>.json` liệt kê từng phần kèm
   SHA-256 và số dòng. Khóa COMPLIANCE tới hết thời hạn bảo quản tính từ ngày đóng (vĩnh viễn: 100 năm; đã quá hạn
   thì tới hết ngày mai); manifest không ghi giờ chạy nên lượt chạy lại ra đúng gói cũ. Đọc lại cả gói, so băm, rồi
   mới sang bước 2.
2. Hàm `office.archive_case_file(p jsonb)` (Hasura đưa ra thành mutation, chỉ khóa quản trị gọi được), một giao dịch
   có khóa dòng: kiểm hồ sơ còn `closed` và CSDL còn đúng như gói (đúng văn bản, dòng thời gian, liên kết tệp) — lệch
   thì raise, không đổi gì; rồi `case_files` ghi `archive_key`, `archive_sha256`, `archived_at`, `status =
   'archived'`; văn bản `archived`; xóa `document_events`, `document_files` của các văn bản đó; tệp đổi `storage_tier
   = 'cold'`; sự kiện `case_file.archived` kèm băm vào `core.audit_log`. **Giữ** dòng `documents` rút gọn (vẫn tìm
   thấy, cổng xác thực vẫn trả lời — `office.issued_documents` gồm cả `archived`) và `assignments` (căn cứ quyền xem,
   cột "đơn vị nhận" của sổ đăng ký). Hai lượt cùng lúc: lượt sau đợi khóa, thấy hồ sơ đã `archived`, rollback.
3. Xóa bản nóng của tệp (tệp còn gắn văn bản ngoài hồ sơ thì giữ). Trigger `document_files_hot_only` chặn gắn tệp
   đã sang lạnh vào văn bản nào nữa.

Xem lại hồ sơ đã lưu: `GET /api/case-files/{id}/archive` (§4.3) — svc-files tải manifest theo `archive_sha256`, so
băm, DuckDB đọc bảng văn bản, chỉ trả văn bản người gọi đọc được. Phòng đọc xem tệp có watermark làm cùng F3.7.

**Phả hệ và kiểm chất lượng (F3.9).** Mỗi lượt nộp lưu là một run OpenLineage của job `moc.case_file.archive`, với
4 run con `files`, `tables`, `manifest`, `commit` (facet `parent`). svc-files ghi từng sự kiện vào:

```sql
create table core.lineage_events (
  id bigint generated always as identity primary key,
  tenant_id uuid references core.tenants,     -- null: việc của nền tảng
  run_id uuid not null, parent_run_id uuid,
  job text not null, event_type text not null, event_time timestamptz not null,
  inputs text[] not null default '{}', outputs text[] not null default '{}',   -- "<namespace>/<name>"
  quality_ok boolean,                         -- null: bước không kiểm chất lượng
  event jsonb not null,                       -- sự kiện OpenLineage 2-0-2 nguyên văn
  recorded_at timestamptz not null default now()
);
```

- Tên dataset: bảng `postgres://postgres:5432` + `moc.<schema>.<bảng>`; đối tượng `s3://<bucket>` + key.
- Bảng Parquet được dựng và kiểm trước khi ghi sang lạnh: số dòng bằng số dòng lấy từ CSDL, cột bắt buộc không null
  (`dataQualityAssertions`); trượt thì bước `tables` FAIL, job dừng, không ghi gì sang bucket lạnh.
- Chỉ thêm: trigger chặn sửa, xóa. Không chứa tên hồ sơ, trích yếu, tên tệp (thông báo lỗi chỉ có tên lớp lỗi). Ghi
  phả hệ lỗi không chặn việc nộp lưu.
- `dataQualityAssertions` nằm ở dataset đầu ra của bước `tables` (mở rộng của Mộc) và ở `inputFacets` của bảng đầu
  vào bước `manifest` (đúng đặc tả OpenLineage, Marquez hiển thị được).
- Quyền: `director`, `clerk` đọc của đơn vị mình (§3); không vai trò nào ghi.

Thống kê điều hành (§2.5) tính thời gian xử lý từ dòng thời gian: văn bản đã nộp lưu không còn trong số đó (mặc định
nộp lưu sau một năm, ngoài cửa sổ 12 tháng của dashboard).

### 2.5. Khung nhìn cho báo cáo

Dashboard điều hành (F3.11, migration `1792281601200_dashboard`) đọc bốn view chỉ có số đếm, đã gom theo thuê
ước: không cột nào chứa trích yếu, số ký hiệu hay tên người. Hasura cho `director` đọc, lọc
`tenant_id = X-Hasura-Tenant-Id`; vai trò khác không thấy. "Hôm nay", "tháng" tính theo giờ Việt Nam.

**Văn bản hạn chế không vào phép chia nào.** Lãnh đạo đọc được mọi văn bản khác của đơn vị, nên lấy số chia trừ đi
số văn bản mình thấy là ra trạng thái, độ khẩn, phòng xử lý, thời gian xử lý của văn bản hạn chế — đúng thứ sổ đăng
ký in che đi (F2.8). Chúng chỉ có một con số tổng mỗi chiều (`v_document_counts`, `restricted = true`), như sổ đăng
ký vẫn cho biết có bao nhiêu văn bản. Nhờ vậy mọi số chia trên dashboard tính lại được từ văn bản người xem đọc
được (smoke kiểm đúng điều này).

| View | Cột | Dùng cho |
|---|---|---|
| `office.v_document_counts` | `direction`, `restricted`, `status`, `urgency`, `overdue`, `documents` | Văn bản đến theo trạng thái, văn bản khẩn chưa xong, số quá hạn (văn bản đến chưa xong — chờ vào sổ, chờ chỉ đạo, đang xử lý — mà đã qua `due_on`). Dòng `restricted = true`: số văn bản hạn chế, `status`, `urgency`, `overdue` để null |
| `office.v_overdue_by_department` | `department_id`, `code`, `name`, `in_progress`, `overdue` | Văn bản đến đang xử lý theo phòng chủ trì: việc chủ trì gốc giao cho phòng, hoặc giao cho một người thì tính về phòng của người đó (`core.users`). Phòng chưa có việc vẫn có dòng, số 0. Không xác định được phòng thì vào dòng `department_id` null ("Chưa rõ phòng"), để tổng luôn bằng số văn bản đang xử lý |
| `office.v_processing_time` | `month`, `documents`, `total_hours`, `with_due`, `on_time` | Thời gian từ vào sổ đến khi xong, theo tháng xong. Lúc xong là sự kiện `office.document.processed` (báo xong) hoặc `office.document.filed` (cho lưu) trên dòng thời gian, ghi cùng giao dịch với trạng thái `done`. Trả tổng số giờ để giao diện tự chia, gộp nhiều tháng không lệch; `on_time` đếm trong số `with_due` (văn bản có hạn) |
| `office.v_outgoing_by_month` | `month`, `documents` | Văn bản đi đã phát hành theo tháng ban hành |

Sổ đăng ký văn bản đến / đi (F2.8) không cần view riêng: `svc-files` đọc `office.documents` theo `register`
(chiều, năm) bằng vai trò `service` để sổ liền số kể cả văn bản hạn chế, rồi che nội dung dòng nào người in không
được đọc (hỏi lại Hasura bằng token của họ) — §4.3.

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

**Danh sách người được xem** (F3.7, migration 1792281601600). Có tên vẫn phải có quyền theo vai trò ở bảng trên
(tổ trưởng phòng khác chưa được giao việc thì vẫn không thấy). Văn thư và lãnh đạo đơn vị cấp, gỡ qua hai hàm
`office.grant_document_access(document_id, user_id)`, `office.revoke_document_access(document_id, user_id)` (Hasura
đưa ra thành mutation, truyền phiên của người gọi vào `hasura_session`): hàm kiểm vai trò, người gọi đọc được văn bản, văn bản đang hạn chế,
người được cấp cùng đơn vị và còn hoạt động, không tự gỡ mình; cấp lại người đã có thì giữ người cấp lần đầu. Mỗi lần
cấp, gỡ là một dòng sổ kiểm toán (`office.document_acl`, `entity_id` "<văn bản>/<người>"). `svc-workflow` (vai trò
`service`) tự thêm người phải làm các việc đang mở của quy trình sau mỗi bước, để không ai nhận việc mà không mở được
văn bản. Tệp phải khớp chế độ: văn bản hạn chế chỉ gắn tệp mã hóa, văn bản thường chỉ gắn tệp thường (trigger
`document_files_sealed`); đã có tệp thì không bật, tắt hạn chế được nữa (`documents_restricted_sealed`). Tệp mã hóa đã
gắn vào văn bản chỉ theo quyền đọc văn bản — người tạo dòng tệp (vd lãnh đạo bấm phát hành, svc-files dựng bản phát
hành thay) bị gỡ khỏi danh sách cũng hết tải. Văn bản hạn chế không được công khai trích yếu ở cổng xác thực (ràng
buộc `documents_restricted_private`: không `restricted` và `is_public` cùng lúc).

> **Không đặt tên vai trò là `admin`.** `admin` là vai trò có sẵn của Hasura, bỏ qua mọi quyền kể cả khi nằm
> trong JWT. Chạy thử ở #18: token có `x-hasura-default-role: admin` đọc được dữ liệu của mọi thuê ước.
> Quản trị đơn vị là `tenant_admin`; mapper của realm chỉ đưa 5 vai trò nghiệp vụ vào claim.

Ghi trực tiếp (không qua Action):

| Vai trò | Được làm | Cột đặt sẵn |
|---|---|---|
| `staff` | Thêm dự thảo văn bản đi; sửa khi còn `draft` hoặc `returned` | `tenant_id`, `created_by`, `direction = 'out'`, `status = 'draft'` |
| `staff` | Gắn tệp do chính mình tải lên vào dự thảo của mình (như dòng trên); gỡ khi dự thảo còn ở bước đó | `tenant_id`, `added_by` |
| `staff`, `manager` | Tạo, đóng hồ sơ công việc của phòng mình; đưa vào văn bản đã xong mình đọc được và thuộc phòng mình, gỡ ra khi hồ sơ còn mở (F3.8) | `tenant_id`, `department_id`, `created_by` / `added_by` |
| `tenant_admin` | Phòng ban | `tenant_id` |
| `clerk`, `director` | Cấp, gỡ người được xem văn bản hạn chế, qua hàm `office.grant_document_access`, `office.revoke_document_access` (F3.7) | `tenant_id`, `granted_by` |

Sổ do `svc-workflow` tạo khi cấp số đầu tiên của năm. Danh mục loại văn bản dùng chung cho mọi thuê ước,
chỉ đổi bằng migration.

Không vai trò người dùng nào sửa được `status`, `register_number`, `symbol` của văn bản đi,
`content_sha256`, `verify_code`, `process_id`.

**Không có vai trò ẩn danh.** Cổng xác thực đi qua `svc-files` (§4.3), không cho truy vấn bảng — nếu không,
người ngoài liệt kê được mọi văn bản đã phát hành.

---

## 4. Hasura Actions và API của dịch vụ

Cách gọi, schema GraphQL theo vai trò và OpenAPI xuất từ hệ thống đang chạy: [`docs/api/`](api/README.md).

### 4.1. Actions (do `svc-workflow` xử lý)

| Action | Ai gọi | Làm gì |
|---|---|---|
| `receiveIncoming(data)` | `clerk` | Tiếp nhận văn bản đến (F2.2). Kiểm `data` theo `schemas/van-ban-den.json` — cùng tệp form đã kiểm — rồi tra loại văn bản, tệp do chính người gọi tải lên, văn bản trùng (cùng cơ quan, số ký hiệu, ngày; kể cả văn bản hạn chế văn thư không thấy). Ghi văn bản `received` kèm tệp (tệp đầu là bản chính) bằng vai trò `service`, người tạo là người gọi. Lỗi trả từng trường trong `extensions.fields` (`schemas/README.md`). Văn bản hạn chế phải kèm toàn tệp đã mã hóa, văn bản thường không được kèm tệp mã hóa (`file_ids`: `not_sealed`, `sealed`). Văn thư không có quyền ghi thẳng bảng văn bản lẫn bảng tệp đính kèm |
| `registerIncoming(documentId)` | `clerk` | Gọi hàm `office.register_incoming` (một giao dịch: khóa văn bản, lấy số kế tiếp của sổ năm nay, `received → registered`, ghi sự kiện), rồi khởi chạy `van-ban-den` với `businessKey = documentId`. Flowable lỗi thì vẫn giữ số đã cấp; job đối soát (5 phút) khởi chạy sau |
| `myTasks` (query) | `clerk`, `staff`, `manager`, `director` | Việc giao đích danh cho người gọi và việc chưa ai nhận của nhóm vai trò của họ; khẩn xếp trước. Kiểu trả về có quan hệ `document` sang `office_documents`, nên Hasura áp quyền đọc văn bản như mọi truy vấn khác |
| `submitOutgoing(documentId, signerId)` | `staff` (người soạn) | Kiểm dự thảo có nội dung, nơi nhận; người ký là lãnh đạo đơn vị; phòng có lãnh đạo phòng duyệt. `draft → in_review` thì khởi chạy `van-ban-di`; `returned → in_review` thì hoàn thành việc `vbdi.chinhSua`, quy trình quay về bước duyệt cấp phòng (đổi được người ký) |
| `completeTask(taskId, outcome, data)` | Người được giao task | Kiểm task thuộc về người gọi, văn bản hạn chế thì người gọi phải đọc được nó (403 `restricted`), kiểm `data` theo JSON Schema của `formKey`, hoàn thành task Flowable, cập nhật bảng và ghi `document_events` |

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
| `van-ban-di` | `vbdi.duyetPhong` | `manager` của phòng soạn | `approve` · `return` | `note` (bắt buộc khi `return`) |
| | `vbdi.duyetDonVi` | `director` được chọn làm người ký | `approve` · `return` | `note` (bắt buộc khi `return`) |
| | `vbdi.chinhSua` | Người soạn, khi bị trả lại | — (hoàn thành bằng `submitOutgoing`) | — |
| | `vbdi.phatHanh` | `clerk` | `issue` | `is_public` |

`vbdi.duyetDonVi` với `approve`: `in_review → approved`. Trả lại ở bước nào cũng `→ returned`.

`vbdi.phatHanh` với `outcome = issue` (đã làm):

1. `svc-workflow` sinh `verify_code` (10 ký tự base32, 50 bit ngẫu nhiên) rồi gọi hàm `office.number_outgoing`:
   một giao dịch khóa văn bản, lấy số kế tiếp của sổ đi năm nay, ghi số, ký hiệu, ngày ban hành, mã tra cứu.
   Ký hiệu theo NĐ 30, Phụ lục I: văn bản có tên loại `05/TB-CNTT`, công văn `05/CNTT-ĐT`. Gọi lại thì trả về
   số đã cấp.
2. `svc-workflow` gọi `POST /internal/issue` của `svc-files` bằng token tài khoản dịch vụ (client credentials của
   client `svc-workflow`). `svc-files` đọc văn bản từ CSDL, dựng PDF đúng thể thức (WeasyPrint): số, ngày, mã QR
   dẫn tới `<MOC_PUBLIC_URL>/xac-thuc/<mã>`. PDF vẫn qua ClamAV rồi mới lưu vào `core.files` như mọi tệp.
3. Một mutation: `status = issued`, `content_sha256` = SHA-256 của tệp, gắn tệp với vai trò `issued`, ghi sự kiện.

Giao bản cho nơi nhận nội bộ (F3.12) làm ở Phase 3.

Nhắc hạn (đã làm): mỗi user task có timer không ngắt việc, chu kỳ `R2/${slaDuration}` (`MOC_SLA_DURATION`: thật
`PT24H` — NĐ 30 yêu cầu trình trong ngày; demo `PT1M`). Timer bắn thì Flowable tạo việc giao ra ngoài (external
worker, topic `moc-sla`); `svc-workflow` **tự lấy** việc đó về (không có callback từ Flowable vào, nên Flowable
không cần biết địa chỉ hay khóa của dịch vụ nào; `svc-workflow` dừng thì việc chờ đó, chạy lại thì làm tiếp):

- quá một thời hạn → nhắc người phải làm (`task.overdue`)
- quá hai thời hạn → báo thêm lãnh đạo của họ (`task.escalated`): chuyên viên → lãnh đạo phòng, còn lại → lãnh
  đạo đơn vị; việc của lãnh đạo đơn vị thì chỉ nhắc

Mỗi lần ghi một sự kiện `office.task.overdue` / `office.task.escalated` vào dòng thời gian, `data` có
`sla_task_id`, `notified`. Văn bản đến có `due_on`: vòng nền của `svc-workflow` (5 phút) tìm văn bản đang xử lý
đã qua hạn, báo người xử lý, người giao việc và lãnh đạo đơn vị một lần (`office.document.overdue`).
Văn bản khẩn: biến `urgency` để hộp việc xếp lên đầu.

### 4.3. API REST của `svc-files`

| Đường dẫn (qua APISIX) | Ai gọi | Làm gì |
|---|---|---|
| `POST /api/files` | Người đăng nhập | Quét ClamAV → ghi SeaweedFS → thêm dòng `core.files`; nhiễm thì trả 422 và ghi `file.rejected`. `?restricted=true`: chỉ PDF, mã hóa bằng khóa riêng do két cấp rồi mới ghi, `wrapped_dek` vào CSDL (F3.7) |
| `GET /api/files/{id}` | Người có quyền với văn bản chứa tệp | Kiểm quyền qua Hasura; tệp mã hóa thì giải mã trong bộ nhớ, kiểm băm, đóng dấu tên người xem lên mọi trang, ghi `file.decrypted` vào sổ kiểm toán rồi mới trả |
| `GET /api/search?q=` | Người đăng nhập | Meilisearch tìm trong số ký hiệu, trích yếu, cơ quan ban hành, nội dung văn bản đi và chữ của PDF đính kèm (trừ văn bản hạn chế); lọc thuê ước và quyền phía server; `matched_content` báo kết quả chỉ khớp nội dung |
| `GET /api/documents/{id}/preview` | Người đọc được văn bản đi | PDF đúng thể thức của dự thảo, chưa có số, in chữ "DỰ THẢO" |
| `GET /api/registers/{in\|out}/{year}` | `clerk`, `director` | Sổ đăng ký một năm, cột theo mẫu NĐ 30 Phụ lục IV; dòng văn bản hạn chế người gọi không đọc được chỉ có số, ngày, số ký hiệu |
| `GET /api/registers/{in\|out}/{year}/pdf` | `clerk`, `director` | Như trên, ra PDF A4 ngang để ký nhận, đóng sổ; ghi `register.printed` vào sổ kiểm toán |
| `GET /api/verify/{code}` | Ẩn danh | `{result, document: {symbol, issued_on, type_name, issuer_name, parent_name, summary?, sha256, verify_code, status}}`; `summary` chỉ có khi `is_public` |
| `GET /api/verify?sha256=…` | Ẩn danh | Như trên, tra theo băm do trình duyệt tự tính |
| `GET /api/case-files/{id}/archive` | Người xem được hồ sơ | Phòng đọc hồ sơ đã nộp lưu: đọc lại gói từ bucket lạnh, so băm với CSDL, văn bản người gọi đọc được từ Parquet (số còn lại trong `hidden`); ghi `case_file.read` vào sổ kiểm toán |
| `POST /internal/issue` | Chỉ `svc-workflow` (token tài khoản dịch vụ), không qua APISIX | Dựng, quét, lưu bản phát hành; trả `{file_id, sha256, size_bytes}` |

`GET /api/files/{id}` (đã làm ở #19): svc-files hỏi Hasura `core_files_by_pk` **bằng token của người gọi** —
Hasura trả dòng khi người gọi là người tải lên hoặc đọc được văn bản có gắn tệp — rồi mới lấy `object_key`
bằng vai trò `service`. Không có tệp và không được xem đều trả 404. Tệp luôn trả về dạng `attachment` kèm
`Content-Security-Policy: sandbox`, để tệp HTML/SVG người dùng tải lên không chạy được trên tên miền của Mộc.

`GET /api/search` (đã làm ở #20): Meilisearch tìm với điều kiện `tenant_id` lấy từ token và chỉ trả về id;
svc-files hỏi lại Hasura `office_documents(where: {id: {_in: …}})` bằng token của người gọi, giữ những văn bản
họ được đọc theo đúng thứ tự xếp hạng. Không trả tổng số kết quả. Chỉ mục được đồng bộ mỗi vài giây theo
`office.documents.updated_at`.

`verify_code`: 10 ký tự base32 ngẫu nhiên (50 bit) — không đoán, không liệt kê được. APISIX giới hạn tốc độ
`/api/verify/*` theo IP (`MOC_RATE_VERIFY_PER_MIN`).

`/api/verify` (đã làm): `svc-files` tra khung nhìn `office.issued_documents` bằng vai trò Hasura `verifier`. Vai
trò này chỉ đọc được khung nhìn đó, tối đa một dòng mỗi lần, và không có trong token của người dùng. Khung nhìn
chỉ có văn bản đi đã phát hành; trích yếu bị ẩn khi văn bản không công khai hoặc là văn bản hạn chế.

---

## 5. Định dạng sự kiện

Khuôn chung cho sự kiện gửi ra ngoài hệ thống (webhook, liên thông — Phase 3). `office.document_events` lưu
cùng loại (cột `kind`), người làm (`actor_id`, `actor_kind`) và `data`:

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
| `office.document.submitted` / `resubmitted` | Văn bản đi được trình / trình lại sau khi sửa |
| `office.document.reviewed` | Lãnh đạo phòng đồng ý, chuyển người ký |
| `office.document.approved` / `returned` | Người ký duyệt / trả lại (ở bước nào) |
| `office.document.numbered` | Văn bản đi được cấp số, ký hiệu |
| `office.document.issued` | Văn bản đi được phát hành, kèm băm và mã tra cứu |
| `office.task.overdue` / `office.task.escalated` | Timer của Flowable: quá một / hai thời hạn của bước (§4.2) |
| `office.document.overdue` | Văn bản đến qua hạn giải quyết mà chưa xử lý xong |
| `office.case_file.archived` | Hồ sơ nộp lưu xong |
| `core.file.rejected` | ClamAV chặn tệp |
| `ot.alarm` | Cảm biến vượt ngưỡng, có dự thảo báo cáo sự cố (F3.10). Trong `office.document_events`: `actor_kind` `service` (`svc-workflow`), `data` = mã cảm biến, tên phòng, nhiệt độ, ngưỡng, giờ đo |

**Thông báo realtime** (đã làm): mỗi kết nối Centrifugo tự vào kênh riêng `personal:#<sub>` của người trong
token (Centrifugo tự kiểm token Keycloak qua JWKS); trình duyệt không đăng ký được kênh nào khác. Sau mỗi bước,
`svc-workflow` ghi `core.notifications` rồi đẩy dòng vừa ghi (`id`, `kind`, `document_id`, `data`, `created_at`)
qua HTTP API nội bộ của Centrifugo:

| `kind` | Gửi cho | Khi |
|---|---|---|
| `task.assigned` | Người phải làm việc mới (đích danh, hoặc mọi người trong nhóm ứng viên), trừ người vừa làm bước trước | Sau mỗi bước làm quy trình sinh việc mới; bị trả lại thì kèm ý kiến |
| `task.overdue` / `task.escalated` | Người phải làm / lãnh đạo của họ | Timer quá một / hai thời hạn |
| `document.issued` | Người soạn, người ký | Văn thư phát hành văn bản đi |
| `document.processed` | Lãnh đạo đã chỉ đạo, lãnh đạo phòng đã phân công | Người xử lý báo xong |
| `document.overdue` | Người xử lý, người giao việc, lãnh đạo đơn vị | Văn bản đến qua hạn giải quyết |
| `ot.alarm` | Chuyên viên phụ trách cảm biến | Cảm biến vượt ngưỡng, hệ thống vừa dựng dự thảo báo cáo sự cố (F3.10); `data`: tên phòng, nhiệt độ, ngưỡng, trích yếu |

Dashboard điều hành (F3.11) không dùng kênh realtime: số liệu tính lúc mở trang, có nút làm mới (§2.5).

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
