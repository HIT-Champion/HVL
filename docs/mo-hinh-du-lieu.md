# Mô hình dữ liệu, Hasura Actions và định dạng sự kiện

> **Bản nháp** cho việc 0.3 / issue #6 — lập ngày 15/10/2026, Backend rà và cùng chốt trong PR.
> Phạm vi sản phẩm: [`dac-ta-san-pham.md`](dac-ta-san-pham.md). Nguồn sự thật giữa Flowable và PostgreSQL:
> [`ke-hoach-phat-trien.md`](du-thi/ke-hoach-phat-trien.md) §2.1.
> Sau khi chốt, `db/migrations/` (#18) và `db/metadata/actions.*` (#15) làm theo tài liệu này; đổi mô hình
> thì sửa tài liệu trong cùng PR.

---

## 0. Nguyên tắc

- **Hai schema, đúng ranh giới 3 tầng.** `core` là dữ liệu dùng chung của lõi (thuê ước, tệp, sổ kiểm toán)
  — ứng dụng nào cũng dùng. `office` là dữ liệu riêng của ứng dụng Văn phòng điện tử. Ứng dụng khác cắm vào
  lõi thì có schema riêng của nó, không sửa `core` — vd `personal` của Không gian cá nhân (§2.6).
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
  sample_data boolean not null default false, -- đơn vị mẫu do make seed nạp; số đo F4.6 ghi rõ (§2.5)
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
  extracted_at  timestamptz not null default now(),
  page_starts   int[]                         -- vị trí đầu mỗi trang trong content (F4.2, migration 1792281602000)
);

create table core.file_signatures (         -- chữ ký số PAdES của bản phát hành (F4.5, migration 1792281602200)
  file_id       uuid primary key,             -- (tenant_id, file_id) tham chiếu core.files, xóa tệp thì xóa theo
  tenant_id     uuid not null,                -- preset từ phiên
  level         text not null default 'PAdES-B-B' check (level in ('PAdES-B-B')),
  signed_at     timestamptz not null,         -- giờ ký tự khai trong chữ ký (không có dấu thời gian tin cậy)
  signer_name   text not null,                -- CN chứng thư lá: "<đơn vị>, <cơ quan chủ quản>", 1–64 ký tự
  ca_name       text not null,                -- CN của CA nội bộ, 1–64 ký tự
  serial        text not null,                -- số sê-ri chứng thư, hex thường 2–64 ký tự
  cert_sha256   bytea not null,               -- vân tay chứng thư lá (32 byte); chứng thư nằm sẵn trong PDF
  not_after     timestamptz not null,         -- hạn chứng thư lá
  key_name      text not null,                -- khóa transit 'moc-ky-so-<tenant_id>'
  key_version   int  not null check (key_version > 0),
  created_at    timestamptz not null default now()
);

create table core.users (                   -- danh bạ, đồng bộ từ Keycloak (migration 1792281600400)
  id             text primary key,             -- sub của Keycloak
  tenant_id      uuid not null references core.tenants,
  department_id  uuid,                          -- không đặt khóa ngoại: core không phụ thuộc office
  username       text not null,
  full_name      text not null,                 -- "firstName lastName" của Keycloak: họ đệm + tên
  email          text,
  phone          text,                          -- số nhận SMS, E.164 (+84…): phone_number của Keycloak (#365)
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
  channels     text[] not null default '{}', -- kênh ngoài cần gửi: email, webhook (migration 1792281602600)
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

- Trigger `core.audit()` gắn vào mọi bảng nghiệp vụ (trừ `office.document_events` và `office.feedback` — góp ý
  không gắn sổ để lãnh đạo đọc sổ không biết ai góp ý gì, §2.5), ghi các cột đã đổi. Hàng đợi của lô nạp
  (`core.import_jobs`, `core.import_rows`) cũng không gắn: mỗi mẻ đổi `run_after` và từng dòng, gắn trigger thì
  lô vài trăm dòng làm sổ phình mà không thêm gì — thay vào đó `svc-files` ghi `import.created` lúc tạo lô, trigger
  `import_jobs_finished` ghi `import.finished` đúng một lần khi lô chuyển sang `done`; mỗi văn bản tạo ra vẫn có
  dòng sổ của nó.
- Trigger `before insert` trên `core.audit_log` khóa dòng đầu chuỗi `core.audit_head (last_id, last_hash)`,
  cấp `id = last_id + 1`, đặt `occurred_at`, `prev_hash`, `hash` — người ghi không chọn được các cột này.
  Khóa dòng thay cho `pg_advisory_xact_lock`: ở `READ COMMITTED` giao dịch sau đợi rồi đọc đầu chuỗi mới;
  ở mức cô lập cao hơn thì lỗi tuần tự hóa chứ không rẽ nhánh chuỗi.
- `hash = sha256(prev_hash ‖ jsonb_build_array(id, epoch(occurred_at), tenant_id, actor_id, actor_kind,
  request_id, action, entity, entity_id, diff)::text)`. Thời điểm lấy theo epoch để không phụ thuộc múi giờ
  của phiên; `jsonb::text` cho cùng một chuỗi với cùng một giá trị, nên tính lại được khi kiểm tra.
- Người thực hiện: đọc `current_setting('hasura.user', true)` (Hasura đặt biến này trong mỗi giao dịch);
  dịch vụ ghi thẳng vào CSDL thì `set local moc.actor = '…'` trước khi ghi. `actor_kind` theo vai trò Hasura của
  phiên: `service` → `service`, `agent` → `agent` (tác tử đọc văn bản đến, F4.1, migration 1792281601900; trợ lý
  hỏi đáp, F4.2; tác tử gợi ý giao việc, F4.3), `admin` → `system`, vai trò người dùng → `user`.
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
  trigger thì bị bắt). `audit anchor --to <tệp>` ghi thêm một bản mốc vào tệp để chép ra ngoài máy chủ, kèm chữ ký
  Ed25519 của két (khóa `moc-anchor`); `--publish` đẩy mốc lên một kho git công khai cấm đẩy ép, người ngoài kiểm chữ
  ký bằng OpenSSL (`docs/van-hanh.md` mục Mốc neo công khai). Mốc trong tệp có chữ ký sai, hay không có chữ ký mà
  đứng sau mốc đã ký, thì `audit verify` báo lỗi.
- **Xem sổ:** `director`, `tenant_admin` đọc dòng sổ của đơn vị mình nhưng không đọc cột `diff`; trường tính
  toán `overview` (`core.audit_overview(r)`) giữ tên mọi cột đã đổi, còn giá trị chỉ giữ ở các cột không chứa
  nội dung (trạng thái, số, ngày, cờ, mã người, mã văn bản; năm, số dòng của lần in sổ đăng ký — migration
  1792281600900; mẫu mã độc, cỡ tệp của tệp bị ClamAV chặn — migration 1792281601100, tên tệp vẫn ẩn; đơn vị nhận,
  văn bản đến, văn bản gửi, số lần thử, lúc giao của lần gửi liên thông — migration 1792281601800, băm và mã tra cứu
  chụp từ văn bản gửi, lỗi giao vẫn ẩn; cách đọc, số trang, tên các trường tìm thấy, nguồn trích yếu, tên mô hình,
  thời gian, lý do của lượt đọc văn bản đến `intake.suggested` — migration 1792281601900, các khóa này chỉ hiện ở
  dòng sự kiện đó; mã lượt hỏi, chế độ, nguồn câu trả lời, số đoạn, số nguồn được trích, có tìm theo nghĩa không, tên
  mô hình sinh và mô hình nhúng, thời gian, mã cảnh báo của câu trả lời `assistant.answered` — migration
  1792281602000, cũng chỉ ở dòng sự kiện đó; id các văn bản nguồn vẫn ẩn; kết quả, lý do không gợi ý, số ngày đề xuất,
  độ tin cậy, số căn cứ, số văn bản tương tự, có tìm theo nghĩa không, thời gian của gợi ý giao việc
  `assignment.suggested` — migration 1792281602100, chỉ ở dòng sự kiện đó; loại lô, định dạng, có vào sổ không, số
  dòng, số đạt / trùng / lỗi của lô nạp `import.created`, `import.finished` — migration 1792281602800, tên tệp vẫn
  ẩn). Lãnh đạo không đọc được văn bản hạn chế
  thì sổ cũng không lộ trích yếu, nội dung, cả hash của nó (có hash là tra được văn bản ở cổng xác thực). Trường
  `overview` thật ra là `office.audit_overview_seen(r, hasura_session)` (migration 1792281601600, nằm ở `office` vì
  `core` không phụ thuộc `office`): dòng sổ về văn bản hạn chế mà người xem sổ không đọc được (chính văn bản, tệp gắn
  vào, giao việc, lần vào hồ sơ, danh sách được xem) chỉ còn tên trường, mọi giá trị là null — trạng thái, độ khẩn,
  hạn, người ký cũng không lộ. Dòng danh sách được xem (`office.document_acl`) mang người được cấp ở `entity_id`
  ("<văn bản>/<người>") và người cấp ở `actor_id` — hai cột thô mà overview không che được — nên với văn bản hạn chế
  người xem không đọc được thì không hiện cả dòng: bộ lọc quyền của hai vai trò có thêm trường tính toán `visible`
  (`office.audit_log_visible(r, hasura_session)`, migration 1792281602400; không cấp cho vai trò nào chọn, lược đồ
  GraphQL không đổi). Lọc kiểu gì (`where` trên `entity_id`, `actor_id`, aggregate, `by_pk`) cũng không ra dòng đó;
  văn bản không tra được thì cũng ẩn. Người đọc được văn bản (người tạo, có tên trong danh sách) thấy như cũ. Không
  dòng sổ nào bị sửa, chuỗi băm không đổi; đổi lại, người không đọc được văn bản không còn biết có lần cấp, gỡ quyền
  xem, dãy `id` họ thấy có chỗ hở. Mốc neo mở cho hai vai trò này `audit_id`, `anchored_at`: chuỗi
  chung cho cả nền tảng nên mốc không thuộc riêng đơn vị nào.
- **Lịch sử của một văn bản** (F3.5, tab "Lịch sử" trên trang văn bản): view `office.document_history` (migration
  1792281601500) gồm các dòng sổ về chính văn bản, tệp gắn với nó (`entity_id` "<văn bản>/<tệp>"), các lần giao
  việc, lần đưa vào hồ sơ (bỏ id hồ sơ), lần gửi liên thông của văn bản đi (`office.dispatches`, migration
  1792281601800 — dòng sổ thuộc đơn vị gửi nên chỉ hiện ở văn bản đi; văn bản đến bên nhận có lịch sử riêng trong sổ
  của đơn vị nhận); cột `document_id`, `id`, `occurred_at`, `actor_id`, `actor_kind`, `action`,
  `entity`, `overview` — không có `diff`, không có hash. Dòng `assignment.suggested` của tác tử gợi ý giao việc (F4.3)
  mang `entity` `office.documents`, `entity_id` = id văn bản nên tự hiện ở đây. Không gồm danh sách được xem văn bản
  hạn chế (`document_acl`): người có tên không được biết ai khác cũng có tên. `staff`, `manager`, `clerk`, `director`
  đọc khi đọc được văn bản (computed field `visible` qua quan hệ `document`), tối đa 500 dòng mỗi lần. Mỗi nhánh của
  view nối bằng `=` trên chỉ mục (`audit_log (entity, split_part(entity_id, '/', 1))` và chỉ mục riêng cho dòng hồ sơ),
  lọc theo một văn bản không quét cả sổ.

Tệp bị ClamAV chặn **không** có dòng trong `core.files`; `svc-files` ghi sự kiện `file.rejected` vào
`core.audit_log` (màn demo kiểm dịch F3.1).

Khôi phục từ bản sao lưu (`moc backup restore`, F3.4) ghi sự kiện `system.restored` của nền tảng (`tenant_id` null,
`entity` = `backup`, `entity_id` = mã lượt) ngay sau đầu chuỗi vừa khôi phục. Bản sao lưu gồm mọi CSDL (`pg_dump
-Fc`) và cả volume SeaweedFS (tệp, bucket lạnh với mốc neo); chỉ mục Meilisearch dựng lại từ CSDL khi `svc-files`
khởi động. Lượt sao lưu trọn vẹn (`moc backup create`) ghi sự kiện `system.backed_up` cùng dạng, sau lúc dump nên
không nằm trong chính lượt đó; trang trạng thái hệ thống (`GET /api/status`) lấy giờ sao lưu gần nhất từ dòng này
hoặc từ `backed_up_at` của `system.restored`.

**Lớp chữ của PDF** (`core.file_texts`, F2.7): `svc-files` đọc ở vòng nền các PDF đã gắn vào văn bản, trong tiến
trình con có giới hạn, rồi ghi bằng khóa quản trị; vòng đồng bộ tìm kiếm đưa vào trường `content` của
Meilisearch. Không vai trò người dùng nào đọc được bảng này. Tệp của văn bản hạn chế không được đọc chữ và nội
dung văn bản hạn chế không vào chỉ mục (bản chữ trần sẽ vô hiệu việc mã hóa tệp — F3.7). Trigger giữ điều này ở
CSDL: chữ của tệp gắn vào văn bản hạn chế bị bỏ qua khi ghi, và bị xóa khi văn bản bật hạn chế hoặc khi tệp được
gắn vào văn bản hạn chế. Bảng không gắn sổ kiểm
toán: chữ là dữ liệu dẫn xuất, tính lại được từ tệp mà băm đã nằm trong `core.files` và trong sổ.

`page_starts` (F4.2, migration 1792281602000): vị trí ký tự đầu của từng trang trong `content`, để trợ lý hỏi đáp
trích dẫn đúng số trang. Trang trống mang cùng vị trí với trang sau; trang bắt đầu sau điểm cắt 50 000 ký tự không có
trong mảng. Ràng buộc `file_texts_page_starts`: chỉ có khi `status = 'ok'`, 1–200 phần tử, phần tử đầu là 0, phần tử
cuối không vượt độ dài `content`, mảng một chiều không có null. `null` khi bản scan, tệp lỗi, hoặc dòng đọc trước F4.2
(`svc-files` coi cả nội dung là một "trang" không số). Migration xóa mọi dòng `ok` cũ để vòng nền đọc lại một lần, lần
này có ranh giới trang. Hàng đợi đọc chữ gồm bản chính, tài liệu kèm theo và bản phát hành (`issued`) của văn bản đi.

**Chữ ký số của bản phát hành** (`core.file_signatures`, F4.5, migration 1792281602200 — **chỉ minh họa**, không có giá
trị pháp lý như chữ ký số công cộng). `svc-files` ký PDF văn bản đi lúc phát hành bằng khóa transit của đơn vị, chứng
thư do CA nội bộ trong két cấp (§4.3; quyết định kiến trúc: `docs/architecture.md` QĐ-007), rồi lưu tệp đã ký và một
dòng ở đây.

- Một dòng mỗi tệp đã ký, ghi **trong cùng mutation** với dòng `core.files` của bản phát hành (Hasura chạy hai trường
  gốc trong một giao dịch): không có tệp đã ký mà thiếu dòng chữ ký, hay ngược lại. Khóa ngoại `(tenant_id, file_id)` →
  `core.files (tenant_id, id)` `on delete cascade`: không gắn được chữ ký vào tệp của đơn vị khác.
- Không lưu chứng thư (đã nằm trong PDF), chỉ lưu vân tay `cert_sha256`. Không thêm cột vào `core.files` (bảng chung
  cho mọi tệp).
- Ràng buộc mang tên mặc định của PostgreSQL (`file_signatures_<cột>_check`): `level` chỉ `PAdES-B-B`; `serial` khớp
  `^[0-9a-f]{2,64}$` (hex thường, không dấu hai chấm); `cert_sha256` đúng 32 byte; `key_name` khớp
  `^moc-ky-so-[0-9a-f-]{36}$`; `signer_name`, `ca_name` 1–64 ký tự.
- Trigger `core.audit('file_id')`: sổ kiểm toán có dòng `insert` với `entity = 'core.file_signatures'`, `entity_id` =
  id tệp. `overview` của dòng này chỉ giữ giá trị `file_id`; các cột khác còn tên, giá trị null (bản tối thiểu chưa
  thêm nhánh riêng vào `core.audit_overview`).
- Không ký văn bản hạn chế (mỗi lần mở đều viết lại PDF để đóng tên người xem, chữ ký hỏng ngay) và không ký lại văn
  bản đã phát hành trước F4.5 (băm, QR và sổ kiểm toán đã cố định): chúng không có dòng ở đây.
- Không vai trò nào đọc bảng này; cổng xác thực đọc năm cột chữ ký qua view `office.issued_documents` (§2.5).

**Gợi ý đọc văn bản đến** (`office.intake_suggestions`, F4.1, migration 1792281601900). Văn thư tải công văn lên màn
tiếp nhận, bấm đọc (`POST /api/files/{id}/read`, §4.3); tác tử `moc-doc-reader` trong `svc-files` đọc lớp chữ PDF,
không có thì nhận dạng chữ (Tesseract), rồi gợi ý sáu trường của form tiếp nhận. Văn thư đối chiếu, sửa rồi mới lưu —
văn bản vẫn chỉ vào qua Action `receiveIncoming`; gợi ý không bao giờ tự thành văn bản.

```sql
create table office.intake_suggestions (    -- một dòng mỗi tệp: bản gợi ý của lần đọc gần nhất
  file_id         uuid primary key,          -- (tenant_id, file_id) tham chiếu core.files, xóa tệp thì xóa theo
  tenant_id       uuid not null,             -- preset từ phiên
  requested_by    text not null,             -- sub văn thư bấm đọc
  agent_id        text not null,             -- preset X-Hasura-User-Id của phiên agent (moc-doc-reader)
  status          text not null check (status in ('ok', 'empty')),
  method          text not null check (method in ('text', 'ocr')),
  pages           int  not null check (pages between 0 and 200),
  fields          jsonb not null default '{}',   -- {trường: {value, confidence, source}}, khóa ⊂ type_code, symbol,
                                                 -- issued_on, issuer_name, summary, urgency; tối đa 16 KB
  warnings        jsonb not null default '[]',   -- mã cảnh báo: future_date, low_text, model_timeout…
  summary_source  text not null default 'none' check (summary_source in ('rule', 'model', 'none')),
  model           text,                          -- tên mô hình đã viết trích yếu, null nếu không dùng
  duration_ms     int  not null check (duration_ms >= 0),
  read_at         timestamptz not null default now()   -- trigger đặt lại mỗi lần ghi
);
```

- Lần bấm đọc sau trả ngay bản đã lưu (không đọc lại tệp, không ghi sổ); văn thư chọn đọc lại thì ghi đè cả dòng
  (upsert theo `file_id`).
- Ràng buộc mang tên mặc định của PostgreSQL (`intake_suggestions_<cột>_check`): thông điệp lỗi nêu đúng cột sai.
- **Văn bản hạn chế không bao giờ có gợi ý**: bản gợi ý (số ký hiệu, trích yếu) là chữ trần, lưu ra sẽ vô hiệu việc
  mã hóa tệp (F3.7). `svc-files` từ chối tệp mã hóa trước khi đọc byte; trigger `intake_suggestions_guard` chặn thêm
  ở CSDL — ghi gợi ý cho tệp mã hóa hoặc tệp đang gắn vào văn bản hạn chế bị từ chối (`intake_suggestions_sealed`,
  `check_violation`) — và xóa gợi ý khi văn bản bật hạn chế hoặc khi tệp đã đọc được gắn vào văn bản hạn chế (dữ liệu
  có từ trước F3.7), như `core.file_texts`.
- Bảng không gắn trigger sổ kiểm toán (gợi ý là dữ liệu dẫn xuất có nội dung văn bản). Mỗi lần đọc thật, tác tử ghi
  dòng sổ `intake.suggested` chỉ có siêu dữ liệu (§5) **trong cùng yêu cầu GraphQL** với gợi ý: Hasura chạy một
  mutation nhiều trường trong một giao dịch, ghi sổ lỗi thì gợi ý cũng không được lưu.
- Không vai trò người dùng nào đọc, ghi bảng này; giao diện nhận gợi ý qua API của `svc-files`. Lãnh đạo, quản trị
  đơn vị xem số đo qua view `office.v_intake_accuracy` (§2.5).

**Gợi ý giao việc** (`office.assignment_suggestions`, F4.3, migration 1792281602100). Văn bản đến vừa vào sổ thì nhánh
BPMN song song `goiYGiaoViec` (§4.2) giao việc cho tác tử `moc-assigner` trong `svc-workflow`: tìm các văn bản đến tương
tự đã giao (`svc-files`, §4.3), mỗi căn cứ bỏ phiếu cho đơn vị chủ trì gốc của nó, lưu đơn vị thắng, hạn đề xuất, độ
tin cậy và căn cứ. Lãnh đạo thấy gợi ý ở đầu form chỉ đạo; "Dùng gợi ý" chỉ điền form, lãnh đạo vẫn bấm "Giao xử lý".
Quyết định kiến trúc: `docs/architecture.md` QĐ-005.

```sql
create table office.assignment_suggestions (   -- một dòng mỗi văn bản đến, kể cả khi không gợi ý được
  document_id   uuid primary key,              -- (tenant_id, document_id) tham chiếu office.documents, xóa theo
  tenant_id     uuid not null,                 -- preset từ phiên
  agent_id      text not null,                 -- preset X-Hasura-User-Id của phiên agent (moc-assigner)
  process_id    text,                          -- phiên Flowable đã giao việc gợi ý
  status        text not null check (status in ('suggested', 'none', 'failed')),
  reason        text,             -- none: no_similar | no_history | no_valid_unit | low_confidence;
                                  -- failed: timeout | unavailable
  department_id uuid,             -- đơn vị chủ trì gợi ý, (tenant_id, department_id) tham chiếu office.departments
  confidence    text check (confidence in ('high', 'medium', 'low')),
  share         real check (share > 0 and share <= 1),   -- tỉ phần phiếu của đơn vị thắng
  due_days      int  check (due_days between 1 and 365), -- null: văn bản đã ghi hạn, hoặc căn cứ không có hạn
  due_on        date,                          -- ngày vào sổ + due_days, đẩy qua thứ Bảy, Chủ nhật
  evidence      jsonb not null default '[]',   -- [{document_id, score, department_id, days}], ≤ 5 phần tử, ≤ 2 KB
  candidates    int  not null default 0,       -- số văn bản svc-files trả về (0–100)
  semantic      boolean not null default false, -- có tìm theo nghĩa (mô hình nhúng)
  duration_ms   int  not null check (duration_ms >= 0),
  created_at    timestamptz not null default now()
);
```

- Ràng buộc `assignment_suggestions_shape`: `suggested` phải có đơn vị, độ tin cậy, tỉ phần và không có lý do; `none`,
  `failed` phải có lý do đúng loại, không có đơn vị, độ tin cậy, tỉ phần, hạn, căn cứ. `assignment_suggestions_due`:
  `due_days` và `due_on` cùng có hoặc cùng không. Ràng buộc của từng cột mang tên mặc định
  (`assignment_suggestions_<cột>_check`).
- **Căn cứ chỉ có id và số**, không có trích yếu hay số ký hiệu. Giao diện đọc số ký hiệu, trích yếu của căn cứ bằng
  **token người xem** (`office_documents where id in …, restricted = false`), nên gợi ý không cho ai thấy văn bản mình
  không được đọc.
- **Văn bản hạn chế không bao giờ có gợi ý, không bao giờ làm căn cứ.** `svc-files` không tìm cho văn bản hạn chế và bỏ
  văn bản hạn chế khỏi kết quả; trigger `assignment_suggestions_guard` chặn thêm ở CSDL: văn bản đích hạn chế hoặc là
  văn bản đi, hay một căn cứ là văn bản hạn chế → `assignment_suggestions_sealed` (`check_violation`). Trigger khóa
  `for share` văn bản đích và các căn cứ, nên bật hạn chế chạy song song phải đợi lần ghi xong (rồi dọn), hoặc lần ghi
  đợi lần bật hạn chế xong (rồi bị chặn). Văn bản bật hạn chế sau đó (trigger
  `documents_drop_restricted_assignment_suggestions`): xóa gợi ý của chính nó, gỡ nó khỏi căn cứ của các gợi ý khác;
  đơn vị, độ tin cậy, hạn của các gợi ý đó giữ nguyên.
- Bảng không gắn trigger sổ kiểm toán. Cùng giao dịch với dòng gợi ý (một mutation nhiều trường), tác tử ghi dòng sổ
  `assignment.suggested` chỉ có số và mã (§5); dòng sổ gắn vào văn bản nên hiện ở tab Lịch sử. Không ghi
  `office.document_events`: dòng thời gian là việc của người.
- Chỉ `director` đọc (§3); không ai sửa, xóa. Lãnh đạo, quản trị đơn vị xem số đo giữ / đổi gợi ý qua view
  `office.v_assignment_suggestion_accuracy` (§2.5).

**Thông báo** (`core.notifications`): dịch vụ ghi bằng vai trò `service`; mỗi người chỉ đọc thông báo của mình
và chỉ sửa được `read_at`. Thông báo về văn bản hạn chế (F3.7) không mang nội dung: trigger `notifications_restricted`
gọt `summary`, `symbol`, `issuer_name`, `note` khỏi `data` và gắn `restricted: true` ở mọi lần ghi, kể cả dịch vụ ghi
sai; văn bản chuyển sang hạn chế thì thông báo đã gửi về nó cũng bị gọt (`documents_restricted_notifications`). Bảng không gắn sổ kiểm toán: thông báo là bản tin phái sinh từ các bước đã kiểm toán.
Kênh ngoài (email, webhook; migration 1792281602600): svc-workflow khai ở cột `channels` lúc ghi; trigger
`notifications_deliveries` tạo trong cùng giao dịch một dòng `core.notification_deliveries` cho mỗi kênh (hộp thư đi:
`status` `pending` → `sent` | `failed` | `skipped`, `attempts`, `last_error` chỉ tên lỗi và mã, `next_attempt_at`,
`sent_at`; unique `(notification_id, channel)`). Bảng này gắn sổ kiểm toán — lần gửi ra ngoài hệ thống phải truy được
— và không có địa chỉ email, URL hay nội dung: người nhận đọc từ `core.users` lúc gửi. Chỉ `service` của đơn vị đọc và
ghi kết quả; người dùng không đọc (mô tả: `services/svc-workflow/README.md`).
SMS, Zalo (#365, migration 1792281603700) chỉ gửi cho người tự bật: `core.notification_subscriptions` một dòng mỗi
(người, kênh `sms` | `zalo`) — `enabled`, với Zalo thêm `zalo_chat_id` (đã liên kết) hoặc mã liên kết 8 ký tự còn
hạn (`link_code`, `link_expires_at`, chỉ mục duy nhất). Ràng buộc: Zalo bật thì phải có chat_id; SMS không có chat_id
hay mã. Trigger xếp hàng chỉ thêm dòng `sms`, `zalo` khi người nhận còn bật kênh, tài khoản còn hoạt động và — với
SMS — `core.users.phone` có số. Bảng gắn sổ kiểm toán; chỉ `service` đọc, ghi (qua Action `myChannels`,
`setMyChannel`), người dùng không đọc thẳng; `phone` của `core.users` cũng chỉ `service` đọc.
Centrifugo chỉ đẩy bản sao tới trình duyệt đang mở (§5), nên mất kết nối không mất thông báo.

**Lô nạp khối lớn** (cụm ⑤, migration 1792281602800; mô tả: `services/svc-files/README.md`, mục Nạp lô văn bản
đến). Hàng đợi bền trong CSDL như hộp thư đi. `core.import_jobs` một dòng mỗi lô: `kind` (hiện chỉ `incoming` — văn
bản đến; thêm loại là migration mở rộng check cùng một handler trong `svc-files`), người tạo (`created_by`, sub trong
token), phòng lúc tạo, `status` `queued` → `running` → `done`, tên và định dạng tệp (`ndjson` | `csv`), băm tệp dữ
liệu và zip, `options` (`{"register": bool}`), `idempotency_key` (unique theo đơn vị và người tạo: gửi lại cùng khóa
trả lô cũ), `total`, `run_after` (vòng nền làm lô đến giờ, sớm nhất trước; lỗi tạm thì lùi lại), `ok` / `duplicate` /
`failed` chụp lúc đóng lô (`import_jobs_closed`: lô `done` thì tổng khớp), `note`. `core.import_rows` một dòng mỗi
dòng của tệp, khóa `(job_id, line)` — `line` là số dòng người gửi thấy (NDJSON: dòng vật lý; CSV: hàng như Excel);
`data` chỉ giữ khi `pending`, xong thì xóa; `files` (tên trong zip, tối đa 20); `attempts` 0–20 (khóa lạc quan của
vòng nền); `claimed_until` (vòng nền giữ dòng tới lúc này: nhận dòng là cập nhật có điều kiện, hai vòng không cùng làm
một dòng; quá hạn thì nhận lại được); `claim_id` (mã lượt giữ: lưu tiến độ, ghi kết quả đều kèm mã này, vòng đã mất
dòng không ghi đè được); `result` (id tệp đã lưu khi còn chờ, id văn bản, số đến); `code` chỉ khi
`failed`, `message`, `fields` (lỗi theo trường). Dòng không thành văn bản thì svc-files gỡ tệp đã lưu cho dòng (khóa
quản trị, chỉ tệp chưa gắn văn bản của người tạo lô).
Khóa ngoại `(job_id, tenant_id)` kèm thuê ước, xóa lô thì xóa dòng. Chỉ `service` của đơn vị đọc, ghi;
không vai trò người dùng nào có quyền — API `/api/imports` (§4.3) kiểm token, chỉ cho người tạo xem lô của mình.

**Ứng dụng cắm bằng manifest** (migration 1792281603200; `moc app install`, [`them-ung-dung.md`](them-ung-dung.md)
mục 1). `core.apps` một dòng mỗi ứng dụng đã cài: `name` (khóa), `title`, `path` (unique giữa các ứng dụng chưa gỡ),
`schema_name` (unique; không được là `core`, `office`, `personal`, `public`, `moc_app`), `version`, `manifest` (jsonb,
như lúc cài, không bí mật),
`manifest_sha256`, `installed_at`, `updated_at`, `removed_at` (gỡ không xóa dòng, không xóa dữ liệu của ứng dụng).
`core.app_migrations` khóa `(app, version)`: `name`, `sha256` nội dung — áp rồi thì không áp lại, nội dung đổi thì lệnh
từ chối. Cả hai gắn `core.audit()`, không vai trò nào đọc qua GraphQL (lệnh đọc bằng `psql`). `core.app_events` là
luồng sự kiện **đã làm sạch** cho ứng dụng: `id` (= `office.document_events.id`, khóa chống trùng cho người nghe),
`tenant_id`, `document_id`, `kind`, `occurred_at` — trigger `app_events_publish` (security definer) chép mỗi dòng
`office.document_events` có `kind` trong danh sách trắng (`office.document.received`, `.registered`, `.issued`) về văn
bản không hạn chế; không `data`, không người làm (hàm chép đặt `hasura.user` = `null` trong lúc ghi, nên
`session_variables` của sự kiện Hasura là `null`). Hasura Event Trigger của từng ứng dụng nằm trên bảng này (§5).
Schema `moc_app` chỉ có hàm `moc_app.migration_done` (security definer): vai trò CSDL `moc_appdb_<schema>` của từng
ứng dụng gọi nó cuối mỗi migration để kiểm đối tượng vừa tạo rồi ghi `core.app_migrations`
([`them-ung-dung.md`](them-ung-dung.md) mục 1.4).

**Danh mục ứng dụng** (migration 1792281603400; trang `/ung-dung` của Văn phòng điện tử). View `core.app_catalog` là
cửa đọc duy nhất của `core.apps` qua GraphQL, đúng 9 cột: `name`, `title`, `description` (= `manifest ->>
'description'`, gọt khoảng trắng, trống thì `null`), `path`, `version`, `installed_at`, `updated_at`, `removed_at`,
`manifest_sha256` (SHA-256 các byte của `app.yaml` lúc cài). Không có `manifest` (image, cổng, healthcheck, biến môi
trường, cổng webhook), `schema_name`. Dữ liệu toàn hệ thống, không cột đơn vị: `clerk`, `staff`, `manager` đọc 7 cột
đầu của ứng dụng chưa gỡ (`removed_at is null`); `director`, `tenant_admin` đọc cả 9 cột, mọi dòng; không vai trò nào
ghi, `service` không đọc. Ứng dụng có sẵn trong lõi (Văn phòng điện tử, Không gian cá nhân) không cài bằng manifest
nên không có ở đây — trang khai chúng trong `apps/office/app/utils/apps.ts` (test đối chiếu tên, đường giữ chỗ, route,
image).

**Cách ly giữa các đơn vị** (F3.12). Một đơn vị là một dòng `core.tenants`; thêm bằng `python3 scripts/moc.py tenant
create` (dòng đơn vị, phòng, Organization trong Keycloak, quản trị đơn vị — `van-hanh.md`, mục Thêm đơn vị). Ranh
giới giữa các đơn vị nằm ở nhiều lớp, lớp sau không tin lớp trước:

- *Danh tính*: đơn vị của một người là thuộc tính `tenant_id` của tài khoản Keycloak, đi vào JWT
  (`x-hasura-tenant-id`); người dùng không tự khai được. Organization của Keycloak (alias suy từ mã, thuộc tính
  `tenant_id`) gom tài khoản theo đơn vị để quản trị; `tenant check` kiểm mỗi tài khoản thuộc đúng một Organization,
  khớp `tenant_id`.
- *Quyền Hasura*: mọi bảng nghiệp vụ lọc theo `X-Hasura-Tenant-Id`; dịch vụ ghi bằng vai trò `service` kèm thuê ước
  lấy từ token đã kiểm, không từ tham số.
- *Ràng buộc CSDL*: khóa ngoại kèm thuê ước (`unique (tenant_id, id)`): giao việc, gắn tệp, phòng chủ trì không trỏ
  được sang đơn vị khác; `files_object_key_tenant` buộc khóa đối tượng của tệp nằm dưới `tenant/<tenant_id>/`.
- *Tìm kiếm*: chỉ mục Meilisearch chung, điều kiện `tenant_id` lấy từ token luôn đứng đầu bộ lọc.
- *Mã hóa*: tệp văn bản hạn chế mã hóa AES-GCM với AAD = id đơn vị ‖ id tệp — bản mã chép sang dòng `core.files` của
  đơn vị khác thì không giải mã được.
- *IoT*: mỗi đơn vị một tenant NGSI-LD trong broker (`NGSILD-Tenant`), token thông báo riêng từng đơn vị.

Không có bucket (hay khóa transit, CSDL) riêng cho từng đơn vị, có chủ ý: `svc-files` là dịch vụ duy nhất chạm kho tệp,
giữ một khóa S3 đọc được mọi bucket, nên tách bucket không thêm ranh giới nào mà nhân số bucket phải tạo, khóa ghi
(Object Lock ở bucket lạnh đặt theo bucket), sao lưu và giám sát theo số đơn vị. Ranh giới thật là thuê ước lấy từ token
cộng ràng buộc trong CSDL và AAD của bản mã ở trên. Một bucket nóng (tiền tố `tenant/<id>/`), một bucket lạnh khóa
ghi (gói nộp lưu dưới `cold/<id>/`, mốc neo sổ kiểm toán chung cả nền tảng vì chuỗi băm là một), một khóa transit
`moc-files` (mỗi tệp một khóa dữ liệu riêng). Riêng khóa **ký số** văn bản đi (F4.5, minh họa) là của từng đơn vị —
khóa transit `moc-ky-so-<tenant_id>`, `svc-files` tự tạo ở lần phát hành đầu — vì chứng thư phải cho biết đơn vị nào
phát hành; đây là danh tính chứ không phải ranh giới cách ly. Đơn vị cần tách vật lý (cơ quan khác, yêu cầu pháp lý)
thì chạy một bản cài Signet riêng.

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
  recipient_tenant_ids uuid[] not null default '{}',    -- đơn vị nhận trong hệ thống (F3.12, migration 1792281601800)
  body             text check (char_length(body) <= 20000),  -- nội dung văn bản đi; mỗi dòng một đoạn
  reply_to_id      uuid references office.documents,    -- trả lời văn bản đến nào
  content_sha256   bytea unique check (content_sha256 is null or octet_length(content_sha256) = 32),
  verify_code      text unique check (verify_code is null or verify_code ~ '^[A-Z2-7]{10}$'),

  -- liên kết
  source_id        uuid references office.documents,    -- văn bản đi của đơn vị khác sinh ra văn bản đến này (F3.12)
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
lớp quyền phía trên có lỗi. Riêng `source_id` (F3.12) được trỏ sang thuê ước khác; `office.dispatches` nối hai thuê
ước bằng hai khóa ngoại, mỗi khóa kèm thuê ước của văn bản nó trỏ tới (bên dưới). Văn bản đến chỉ vào được
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

Văn bản đến liên thông trong hệ thống bắt đầu ở `received` như văn bản văn thư tiếp nhận, do `office.deliver_dispatch`
tạo (§4.2).

**Liên thông trong hệ thống** (F3.12, migration `1792281601800_dispatches`). Văn bản đi chọn đơn vị nhận là đơn vị
khác dùng Signet; văn thư phát hành thì mỗi đơn vị nhận có một văn bản đến `received` (`source_id` trỏ về văn bản
đi) kèm bản sao tệp phát hành — luồng và cách giữ đúng một lần ở §4.2.

```sql
alter table office.documents
  add column recipient_tenant_ids uuid[] not null default '{}',   -- đơn vị nhận trong hệ thống
  add constraint documents_recipient_units_out   check (direction = 'out' or recipient_tenant_ids = '{}'),
  add constraint documents_recipient_units_other check (not (tenant_id = any (recipient_tenant_ids))),
  add constraint documents_restricted_local      check (not (restricted and recipient_tenant_ids <> '{}'));
-- mỗi văn bản gửi sinh nhiều nhất một văn bản đến ở mỗi đơn vị, kể cả khi bản đó đã hủy
create unique index documents_source_once on office.documents (tenant_id, source_id) where source_id is not null;

create view office.dispatch_units as select id, code, name, parent_name from core.tenants;

create table office.dispatches (            -- hộp thư đi: một dòng cho mỗi (văn bản gửi, đơn vị nhận)
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references core.tenants,   -- đơn vị gửi
  document_id           uuid not null,                           -- (tenant_id, document_id) → văn bản đi
  to_tenant_id          uuid not null references core.tenants,   -- đơn vị nhận
  status                text not null default 'pending',         -- pending | delivered | duplicate | failed
  file_id               uuid not null default gen_random_uuid(), -- id bản sao tệp ở đơn vị nhận, định trước
  incoming_document_id  uuid unique,                             -- (to_tenant_id, incoming_document_id) → văn bản đến
  source_verify_code    text not null,                           -- chụp lúc phát hành
  source_sha256         bytea not null,
  attempts              int not null default 0,                  -- số lần giao lỗi
  last_error            text,
  next_attempt_at       timestamptz not null default now(),
  notified_at           timestamptz,                             -- đã báo văn thư bên nhận
  delivered_at          timestamptz,
  created_at            timestamptz not null default now(),
  constraint dispatches_once unique (document_id, to_tenant_id),
  constraint dispatches_not_self check (to_tenant_id <> tenant_id),
  constraint dispatches_linked check ((status in ('delivered', 'duplicate')) = (incoming_document_id is not null))
);
```

- `recipient_tenant_ids`: trigger `documents_recipient_units` bỏ trùng, xếp theo id, kiểm mọi id là đơn vị có trong
  `core.tenants`, và khóa danh sách khi văn bản đã trình (khác `draft`, `returned`) — đơn vị nhận là một phần văn bản
  người ký đã duyệt. Lỗi bắt đầu bằng `documents_recipient_units:`. Không gửi cho chính mình
  (`documents_recipient_units_other`); văn bản đến không có đơn vị nhận (`documents_recipient_units_out`).
- **Văn bản hạn chế chỉ ở trong đơn vị** (`documents_restricted_local`, F3.7): tệp của nó mã hóa gắn với đơn vị và
  tệp (AAD), bản sao ở đơn vị khác không giải mã được; danh sách người được xem (`document_acl`) là người của đơn vị
  gửi, sang đơn vị nhận không còn nghĩa, và đơn vị nhận không biết phải hạn chế với ai. Muốn liên thông thì văn bản
  không đặt hạn chế (chọn trước khi tải tệp), hoặc gửi theo đường khác.
- `office.dispatch_units`: người dùng chỉ đọc được dòng `core.tenants` của đơn vị mình (§3), nên danh sách để chọn đi
  qua view chỉ có mã, tên, cơ quan chủ quản.
- `source_verify_code`, `source_sha256` chụp lúc phát hành vì `verify_code`, `content_sha256` là `unique` trên
  `office.documents`, văn bản đến không mang được; bên nhận so băm tệp chính với `source_sha256`, tra mã ở cổng xác
  thực của bên gửi.
- `core.audit` gắn vào `office.dispatches`; `tenant_id` của dòng là đơn vị gửi.
- Trigger `documents_dispatch_pending`: văn bản còn dòng `pending` thì chưa chuyển sang `archived` được (nộp lưu gỡ
  dòng thời gian, tệp của văn bản, §2.4) — raise `serialization_failure`, job nộp lưu thử lại ở lượt sau.

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
   'archived'`; văn bản `archived`; ghi `office.archived_document_facts` (lúc xong, tệp bản chính — §2.5, migration
   1792281602300) rồi mới xóa `document_events`, `document_files` của các văn bản đó; tệp đổi `storage_tier
   = 'cold'`; sự kiện `case_file.archived` kèm băm vào `core.audit_log`. **Giữ** dòng `documents` rút gọn (vẫn tìm
   thấy, cổng xác thực vẫn trả lời — `office.issued_documents` gồm cả `archived`) và `assignments` (căn cứ quyền xem,
   cột "đơn vị nhận" của sổ đăng ký). Hai lượt cùng lúc: lượt sau đợi khóa, thấy hồ sơ đã `archived`, rollback.
3. Xóa bản nóng của tệp (tệp còn gắn văn bản ngoài hồ sơ thì giữ). Trigger `document_files_hot_only` chặn gắn tệp
   đã sang lạnh vào văn bản nào nữa.

Xem lại hồ sơ đã lưu: `GET /api/case-files/{id}/archive` (§4.3) — svc-files tải manifest theo `archive_sha256`, so
băm, DuckDB đọc bảng văn bản, chỉ trả văn bản người gọi đọc được. Xem tệp: `GET …/archive/files/{file_id}` — chỉ PDF
của văn bản người gọi đọc được, so băm với manifest, đóng dấu người xem bằng đúng đường của F3.7, ghi
`case_file.file_viewed` rồi mới trả. Lãnh đạo phòng nộp lưu ngay hồ sơ đã đóng của phòng:
`POST /api/case-files/{id}/archive` (cùng các bước trên, ghi `case_file.archive_requested` khi giành được lượt).

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
- `dataQualityAssertions` nằm ở dataset đầu ra của bước `tables` (mở rộng của Signet) và ở `inputFacets` của bảng đầu
  vào bước `manifest` (đúng đặc tả OpenLineage, Marquez hiển thị được).
- Quyền: `director`, `clerk` đọc của đơn vị mình (§3); không vai trò nào ghi.

Thống kê điều hành và số đo đọc văn bản đến (§2.5) tính từ dòng thời gian, liên kết tệp mà nộp lưu gỡ đi: văn bản
đã nộp lưu vẫn được đếm như trước nhờ bản giữ lại `office.archived_document_facts` (migration 1792281602300, §2.5).

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
| `office.v_processing_time` | `month`, `documents`, `total_hours`, `with_due`, `on_time` | Thời gian từ vào sổ đến khi xong, theo tháng xong. Lúc xong là sự kiện `office.document.processed` (báo xong) hoặc `office.document.filed` (cho lưu) trên dòng thời gian, ghi cùng giao dịch với trạng thái `done` (văn bản đã nộp lưu: bản giữ lại, xem dưới). Trả tổng số giờ để giao diện tự chia, gộp nhiều tháng không lệch; `on_time` đếm trong số `with_due` (văn bản có hạn) |
| `office.v_outgoing_by_month` | `month`, `documents` | Văn bản đi đã phát hành theo tháng ban hành |

**Số đo đọc văn bản đến** (F4.1, migration 1792281601900): `office.v_intake_accuracy` đối chiếu gợi ý đã lưu với
văn bản văn thư đã lưu từ tệp đó (tệp là bản chính của văn bản đến chưa hủy), cho biết văn thư giữ nguyên bao nhiêu
gợi ý trên dữ liệu thật. Văn bản hạn chế không vào phép đếm. `director`, `tenant_admin` đọc, lọc thuê ước, có
aggregate; vai trò khác không thấy.

**Văn bản đã nộp lưu vẫn trong số liệu** (migration 1792281602300). Nộp lưu (§2.4) xóa dòng thời gian và liên kết tệp
mà `v_processing_time` (lúc xong) và `v_intake_accuracy` (tệp bản chính) đọc. `office.archive_case_file` chép trước
hai thứ ấy vào bảng dưới, trong cùng giao dịch; hai view lấy từ dòng sống như cũ và chỉ dùng bản giữ lại khi dòng sống
không còn — văn bản chưa nộp lưu tính y như trước. Văn bản nộp lưu trước migration được điền lại từ sổ kiểm toán:
lúc xong là lần cuối trạng thái chuyển sang `done` (cùng giao dịch với sự kiện, lệch vài mili giây), bản chính là dòng
`document_files` vai trò `main` bị xóa lúc nộp lưu. Dữ liệu dẫn xuất: không gắn sổ kiểm toán, không đưa vào Hasura
(không vai trò nào đọc, ghi).

```sql
create table office.archived_document_facts (   -- một dòng mỗi văn bản nộp lưu
  document_id    uuid primary key,              -- (tenant_id, document_id) → office.documents
  tenant_id      uuid not null,
  finished_at    timestamptz,                   -- sự kiện processed / filed cuối cùng; null: không có
  main_file_ids  uuid[] not null default '{}'   -- tệp bản chính lúc nộp lưu
);
```

| View | Cột | Dùng cho |
|---|---|---|
| `office.v_intake_accuracy` | `field`, `confidence`, `suggested`, `kept` | Theo trường và độ tin cậy: số gợi ý, số gợi ý văn thư giữ nguyên. Số ký hiệu so không phân biệt hoa thường, bỏ khoảng trắng; cơ quan ban hành so không phân biệt hoa thường, gộp khoảng trắng; ngày so dạng `YYYY-MM-DD`; trường khác so đúng từng ký tự |

**Số đo gợi ý giao việc** (F4.3, migration 1792281602100): `office.v_assignment_suggestion_accuracy` đối chiếu gợi ý
với việc chủ trì gốc lãnh đạo thật sự giao (`assignments` vai trò `lead`, không có `parent_id`, chưa hủy). Chỉ tính
quyết định **sau** lúc gợi ý — giao trước đó thì gợi ý không góp phần. Giao cho một người thì tính về phòng của người
đó (`core.users`), như `v_overdue_by_department`. Không cần ghi thêm gì lúc chỉ đạo: hành vi giữ hay đổi đã là phản
hồi. Văn bản bật hạn chế thì gợi ý của nó bị xóa, ra khỏi phép đếm. `director`, `tenant_admin` đọc, lọc thuê ước, có
aggregate.

| View | Cột | Dùng cho |
|---|---|---|
| `office.v_assignment_suggestion_accuracy` | `tenant_id`, `status`, `confidence`, `suggested`, `decided`, `kept_unit`, `due_compared`, `kept_due`, `due_abs_error_days` | Theo kết quả (`suggested`, `none`, `failed`) và độ tin cậy: số gợi ý; số văn bản đã giao chủ trì sau lúc gợi ý; số giữ đúng đơn vị gợi ý; số có cả hạn gợi ý và hạn đã giao; số giữ đúng hạn; tổng số ngày lệch hạn (chia cho `due_compared` ra sai số trung bình) |

**Góp ý và số đo "sau"** (F4.6, migration 1792281602700, 1792281602750; cách đo, cách đọc:
[`so-lieu-sau.md`](so-lieu-sau.md)). Người đã đăng nhập gửi góp ý: mức hài lòng 1–5, vài dòng, khuôn đường dẫn màn
hình. Bảng không có họ tên, vai trò, phòng, trình duyệt, IP; không gắn sổ kiểm toán (sổ ghi người thực hiện từng dòng,
lãnh đạo đọc sổ của đơn vị sẽ biết ai góp ý gì); không vai trò nào sửa, xóa.

```sql
create table office.feedback (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references core.tenants,
  user_id     text not null,                 -- sub Keycloak, Hasura đặt từ token; không vai trò nào đọc cột này
  rating      int  not null,                 -- feedback_rating: 1–5
  comment     text,                          -- feedback_comment: null hoặc 1–500 ký tự, đã gọt khoảng trắng
  screen      text not null,                 -- feedback_screen: khuôn đường dẫn, vd '/van-ban/:id', ≤ 80 ký tự
  created_at  timestamptz not null default now()   -- trigger đặt, người gửi không chọn
);
```

- `feedback_screen`: chỉ chữ thường, gạch nối và `:id`, tối đa 6 đoạn, không chuỗi truy vấn — id văn bản hay
  `?q=<số CCCD>` không lọt vào bảng.
- Trigger `before insert` `office.feedback_guard()`: gọt khoảng trắng hai đầu của `comment` (chỉ còn khoảng trắng thì
  null), che bằng `office.mask_pii` khi nội dung trong 500 ký tự (cắt lại ở 500 nếu email ngắn làm câu dài ra; quá 500
  thì để nguyên cho `feedback_comment` từ chối), đặt `created_at = now()`, khóa tư vấn theo (đơn vị, người gửi) rồi đếm:
  quá 3 góp ý trong 10 phút hay 20 trong 24 giờ thì lỗi `check_violation` có câu `feedback_rate: …`. Lỗi raise không có
  tên ràng buộc đi kèm: Hasura trả mã `permission-error`, câu `Check constraint violation. feedback_rate: …`, nên giao
  diện tìm tên trong câu. Đếm cả dòng thêm trước đó trong cùng câu lệnh (mutation nhiều dòng) và các lần gửi song song.
- Hàm `office.mask_pii(text)` (immutable, strict; migration 1792281603600, #265): thay email, dãy số liền từ 9 chữ số
  và dãy chia nhóm bằng dấu cách, chấm, gạch từ 9 chữ số bắt đầu bằng 0, +84 hay (+84) bằng `[đã che]`. Không che số
  dính chữ, nhóm số trong mã UUID, phần sau của "chữ số + dấu chấm" (số tiền "10.000.000.000" giữ nguyên). Migration
  che luôn các góp ý đã có; số gốc không lưu ở đâu nên `down.sql` không mở lại được.
- Hàm `office.feedback_mine(feedback, hasura_session)` → trường `mine`: góp ý này của người đang xem. Người gửi lọc góp
  ý của mình mà không ai đọc được `user_id`.
- Quyền: `clerk`, `staff`, `manager`, `director`, `tenant_admin` thêm được (chỉ `rating`, `comment`, `screen`; Hasura
  đặt `tenant_id`, `user_id` từ token). `clerk`, `staff`, `manager` chỉ đọc góp ý của mình; `director`,
  `tenant_admin` đọc mọi góp ý của đơn vị (không có `user_id`), có aggregate. `service`, `agent` không có quyền nào.

Ba view số đo "sau" theo đặc tả §8 (migration 1792281602750). Như dashboard: chỉ số đếm và số giờ, văn bản hạn chế,
văn bản đã hủy không tính, tháng theo giờ Việt Nam. Mỗi view có một dòng mỗi tháng (mỗi màn hình) và một dòng `month`
(`screen`) null cho tất cả — trung vị, p90 không cộng từ các tháng được nên dòng tổng tính lại (grouping sets). Cột
`sample` lấy từ `core.tenants.sample_data`.

| View | Cột | Dùng cho |
|---|---|---|
| `office.v_time_to_assign` | `tenant_id`, `sample`, `month`, `arrived`, `assigned`, `median_hours`, `p90_hours`, `handled`, `handled_median_hours`, `handled_p90_hours`, `waiting` | (a) Từ lúc văn bản đến (`documents.created_at`) tới lần đầu giao chủ trì gốc (`assignments.assigned_at`), và tới lần đầu văn bản tới tay một người (`handled_*`); `percentile_cont`, giờ âm tính 0; `waiting`: chưa giao, còn chờ vào sổ hay chỉ đạo. Theo tháng văn bản đến. Chỉ `director` đọc |
| `office.v_overdue_rate` | `tenant_id`, `sample`, `month`, `judged`, `on_time`, `late`, `late_open`, `pending` | (b) Hạn giải quyết so với lúc xong (sự kiện `processed` / `filed` cuối cùng, hay bản giữ lại khi đã nộp lưu); chưa xong mà qua hạn tính là quá hạn (`late_open`), chưa tới hạn chỉ đếm ở `pending`. Theo tháng của hạn. Chỉ `director` đọc |
| `office.v_feedback_summary` | `tenant_id`, `sample`, `screen`, `feedback`, `rating_total`, `rating_1`…`rating_5`, `with_comment`, `last_at` | Góp ý theo màn hình: số góp ý, tổng điểm (giao diện tự chia ra điểm trung bình), số theo từng mức, số có nội dung, lần gửi gần nhất. Không có nội dung, người gửi. `director`, `tenant_admin` đọc |

**Khung nhìn của cổng xác thực** (`office.issued_documents`, F2.13): một dòng mỗi văn bản đi đã phát hành hoặc đã nộp
lưu; chỉ vai trò `verifier` đọc, mỗi lần một dòng (§3, §4.3). F4.5 (migration 1792281602200) thêm năm cột chữ ký ở cuối.

| View | Cột | Dùng cho |
|---|---|---|
| `office.issued_documents` | `verify_code`, `content_sha256`, `symbol`, `issued_on`, `type_code`, `type_name`, `issuer_name`, `parent_name`, `summary` (chỉ văn bản công khai, không hạn chế), `status`; F4.5: `signature_level`, `signed_at`, `signer_name`, `signer_ca`, `certificate_serial` | Cổng xác thực tra theo mã hoặc băm. Năm cột chữ ký lấy từ `core.file_signatures` của tệp cùng đơn vị có `sha256` bằng `content_sha256`, không qua `office.document_files`: nộp lưu (F3.8) xóa dòng gắn tệp nhưng giữ tệp (kho lạnh) và chữ ký, nên văn bản đã nộp lưu vẫn hiện chữ ký. Tệp khác cùng nội dung (tải lên lại, bản liên thông ở đơn vị nhận) không có dòng chữ ký; `limit 1` giữ một dòng mỗi văn bản; chỉ mục `files_tenant_sha256` cho lần tra. Null khi bản phát hành không ký (trước F4.5, văn bản hạn chế, két chưa có PKI, ký lỗi) |

Sổ đăng ký văn bản đến / đi (F2.8) không cần view riêng: `svc-files` đọc `office.documents` theo `register`
(chiều, năm) bằng vai trò `service` để sổ liền số kể cả văn bản hạn chế, rồi che nội dung dòng nào người in không
được đọc (hỏi lại Hasura bằng token của họ) — §4.3.

**Phả hệ của báo cáo** (F3.9, F3.11, migration 1792281602900). `office.report_lineage` tính thẳng từ catalog
PostgreSQL lúc truy vấn khung nhìn báo cáo nào đọc bảng, view nào — không khai tay cạnh nào, tạo, sửa, xóa view là phả
hệ đổi theo. Báo cáo là mọi view (cả materialized view) trong schema `office` tên bắt đầu `v_` (hiện 9). Cạnh lấy từ
`pg_depend` của luật `_RETURN`: mọi quan hệ trong truy vấn của view, kể cả truy vấn con, CTE, subquery vô hướng; view
đọc view thì đi tiếp đệ quy tới tận bảng. Không dùng `information_schema.view_table_usage` (chỉ hiện bảng vai trò hiện
tại sở hữu). Chỉ có tên và cạnh, giống nhau cho mọi đơn vị: không `tenant_id`, không số dòng (`reltuples` là số của mọi
đơn vị cộng lại; đếm theo đơn vị trên bảng giao việc, dòng thời gian thì lộ dấu vết văn bản hạn chế), không định nghĩa
SQL. Hasura cho `director` đọc, `filter: {}` (như dashboard; vai trò khác không thấy).

| View | Cột | Dùng cho |
|---|---|---|
| `office.report_lineage` | `report` (view báo cáo gốc), `consumer` (view đọc ở cạnh này), `source`, `source_kind` (`table`, `view`, `materialized_view`, `partitioned_table`, `foreign_table`), `depth` (1: báo cáo đọc trực tiếp) | Trang Phả hệ số liệu (`/pha-he`) của lãnh đạo: biểu đồ → khung nhìn → bảng; bước 5 của `make demo-pha-he`. Tên dạng `schema.tên` |

Biểu đồ nào của trang Điều hành đọc khung nhìn nào thì khai một chỗ ở `apps/office/app/utils/lineage.ts`
(`BOARD_CHARTS`); `apps/office/tests/lineage.test.ts` đối chiếu khai báo đó với truy vấn và mã thật của
`pages/dieu-hanh.vue`, `db/tests/test_report_lineage.py` kiểm mọi khung nhìn đã khai có trong phả hệ. Trang Phả hệ nối
thêm lượt nộp lưu gần nhất từ `core.lineage_events` (§2.4): tên dataset `postgres://postgres:5432` +
`moc.<schema>.<bảng>` trùng tên catalog, nên bảng nguồn của báo cáo cũng là đầu vào của bước `tables`; bước `commit`
khai cả `office.archived_document_facts` mà `v_processing_time` đọc. Giới hạn: view gọi một hàm SQL đọc bảng thì
catalog không ghi cạnh tới bảng đó (hiện không view `v_` nào gọi hàm tự viết — test chặn); phả hệ mức bảng, chưa mức
cột.

**Kiểm chất lượng số liệu báo cáo** (F3.9, F3.11, migration 1792281603300). `office.report_checks` tính lúc truy vấn
một bộ luật trên các khung nhìn mà trang Điều hành vẽ; trang Điều hành hiện cờ nặng nhất cạnh từng biểu đồ, trang Phả hệ
hiện từng luật. Ngưỡng của mọi luật là 0. Luật chọn theo chỗ ràng buộc schema không chặn được:

| Luật | Khung nhìn | PASSED / WARNING / FAILED |
|---|---|---|
| `status_total` | `v_document_counts` | Σ 6 cột của biểu đồ trạng thái (đúng `IN_STATUSES` của trang) + văn bản đến hạn chế = số văn bản đến đếm trên `office.documents` / — / lệch (`detail`: trạng thái biểu đồ không vẽ) |
| `department_total` | `v_overdue_by_department` | Σ "đang xử lý" theo phòng = cột "Đang xử lý" của biểu đồ trạng thái, không văn bản nào ở dòng "chưa rõ phòng" / khớp nhưng có (`issues`) / lệch |
| `processing_coverage` | `v_processing_time` | văn bản đến đã xong (done, archived; không hạn chế) đều có mốc xong / thiếu mốc (`issues` văn bản không vào trung bình) / tính thừa, hay có tháng tổng giờ âm (`detail`) |
| `unique_keys` | cả bốn | khóa trang dùng để ghép số (tháng, phòng, bộ chiều của `v_document_counts`) không trùng, không rỗng / — / trùng hoặc rỗng |
| `no_personal_columns` | mọi `office.v_*` | không cột nào mang tên thông tin cá nhân / view (hay view lồng nó đọc qua) đọc cột như vậy (`pg_depend` mức cột) / xuất ra |

Cột: `tenant_id`, `rule`, `report`, `status`, `expected`, `actual`, `issues`, `detail` (`text[]`). Một dòng
`core.tenants` nhân lateral với các luật của đúng đơn vị đó (mỗi khung nhìn đọc một lần), nên lọc
`tenant_id = X-Hasura-Tenant-Id` chỉ tính cho một đơn vị; phần catalog giống nhau cho mọi đơn vị. Hasura cho `director`
đọc với bộ lọc đó, như dashboard. `status_total` và `unique_keys` hôm nay đúng theo cấu trúc (ràng buộc, GROUP BY): là
luật chặn hồi quy khi sửa view, `db/tests/test_report_checks.py` giả lập bằng cách thay tạm view. Tên cột cá nhân theo
mẫu tên (email, phone, cccd, cmnd, birth, address, full_name, username…): cột đặt tên lạ không bắt được; khóa người dùng
(`user_id`, `created_by`) không tính.

### 2.6. Schema `personal` — Không gian cá nhân P.A.R.A (ứng dụng thứ hai)

Không thuộc Văn phòng điện tử: đây là schema của ứng dụng thứ hai `apps/ca-nhan` (migration
`1792281602500_personal_space`), đặt ở mục này để không đánh số lại §3–§6. Cách một ứng dụng cắm vào lõi:
[`them-ung-dung.md`](them-ung-dung.md). Ứng dụng không có bảng tệp riêng: tệp vẫn là dòng `core.files` do `svc-files`
thêm sau khi ClamAV quét sạch; bảng dưới chỉ ghi tệp nào của ai nằm ở thư mục nào.

| Bảng | Cột | Ràng buộc, ghi chú |
|---|---|---|
| `personal.items` | `file_id` (khóa chính), `tenant_id`, `owner_id` (`sub`), `para`, `created_at`, `updated_at` | `para` ∈ `projects`, `areas`, `resources`, `archives` (`items_para`) — Dự án, Lĩnh vực, Tài nguyên, Lưu trữ. Khóa ngoại `(tenant_id, file_id)` → `core.files (tenant_id, id)`, xóa tệp thì mục xóa theo. Trigger `items_guard`: chỉ xếp được tệp có `created_by` là chính chủ, cùng đơn vị, không mã hóa (tệp mã hóa thuộc văn bản hạn chế, đi theo quyền đọc văn bản — F3.7); thêm rồi thì không đổi tệp, chủ, đơn vị; mốc thời gian do CSDL đặt. Sổ kiểm toán: `core.audit('file_id')` |

Quyền: `clerk`, `staff`, `manager`, `director` thêm (chỉ `file_id`, `para`; `tenant_id`, `owner_id` đặt sẵn từ
token), đọc và chuyển thư mục (chỉ cột `para`) mục của chính mình trong đơn vị mình; không ai xóa (§0). Quan hệ
`file` đọc `core.files` theo đúng quyền của vai trò ở `core_files.yaml` — người tải lên thấy tệp của mình; không thêm
quan hệ ngược vào metadata của lõi. `tenant_admin` không đọc `core.files` nên không có không gian cá nhân. `overview`
của sổ chỉ giữ giá trị `file_id`: lãnh đạo xem sổ thấy ai xếp, chuyển tệp nào, không thấy tên thư mục.

### 2.7. Tự chẩn đoán H-P-D-I

Migration `1792281603100_maturity_assessments`, trang `/tu-chan-doan`, cách dùng và cách chấm:
[`tu-chan-doan.md`](tu-chan-doan.md). Mỗi lần lãnh đạo đơn vị lưu bài tự chẩn đoán là một dòng; CSDL không giữ nội
dung câu hỏi (nằm ở `apps/office/app/data/tu-chan-doan.json`), chỉ mã câu và mức — nhưng biết bộ mã câu của từng
phiên bản để đối chiếu.

| Bảng | Cột | Ràng buộc, ghi chú |
|---|---|---|
| `office.maturity_assessments` | `id`, `tenant_id`, `created_by` (`sub`), `framework`, `answers` (jsonb), `h`, `p`, `d`, `i` (numeric(3,2)), `note`, `created_at` | `framework` là phiên bản CSDL biết, hiện chỉ `hpdi-1` (`maturity_framework`); `note` null hoặc 1–300 ký tự (`maturity_note`); bốn điểm trong 1–5 (`maturity_scores`). Trigger `before insert or update` `maturity_assessments_guard`: `answers` là đối tượng có đủ đúng các mã câu của phiên bản (`hpdi-1`: h1–h3, p1–p3, d1–d3, i1–i3), không thừa, mỗi mức số nguyên 1–5 (sai thì lỗi `check_violation` câu `maturity_answers: …`); tính `h`, `p`, `d`, `i` = trung bình mức các câu của không gian, làm tròn 2 chữ số — người gửi không chọn được điểm; gọt khoảng trắng của `note`; khi thêm: đặt `created_at`, chặn lưu dồn — mỗi đơn vị tối đa 5 lần mỗi giờ, 20 lần mỗi 24 giờ (khóa tư vấn theo đơn vị, lỗi `maturity_rate: …`). Sổ kiểm toán: `core.audit()` |

Quyền: chỉ `director` thêm (cột `framework`, `answers`, `note`; `tenant_id`, `created_by` đặt sẵn từ token) và đọc
dòng của đơn vị mình (mọi cột trừ `tenant_id`, `created_by`; có aggregate). Không vai trò nào sửa, xóa; `manager`,
`clerk`, `staff`, `tenant_admin`, `service`, `agent` không có bảng này. `overview` của sổ không giữ giá trị cột nào
của bảng này (`core.audit_overview` không đổi): lãnh đạo đọc sổ thấy ai lưu, lúc nào.

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
(`platform/keycloak/realm/moc-realm.json`): chỉ quản trị viên xem và sửa được, người dùng không tự đổi đơn vị hay vai trò
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
cấp, gỡ là một dòng sổ kiểm toán (`office.document_acl`, `entity_id` "<văn bản>/<người>"); lãnh đạo, quản trị đơn vị
không đọc được văn bản thì không thấy dòng đó (§1, migration 1792281602400). `svc-workflow` (vai trò
`service`) tự thêm người phải làm các việc đang mở của quy trình sau mỗi bước, để không ai nhận việc mà không mở được
văn bản. Tệp phải khớp chế độ: văn bản hạn chế chỉ gắn tệp mã hóa, văn bản thường chỉ gắn tệp thường (trigger
`document_files_sealed`); đã có tệp thì không bật, tắt hạn chế được nữa (`documents_restricted_sealed`). Tệp mã hóa đã
gắn vào văn bản chỉ theo quyền đọc văn bản — người tạo dòng tệp (vd lãnh đạo bấm phát hành, svc-files dựng bản phát
hành thay) bị gỡ khỏi danh sách cũng hết tải. Văn bản hạn chế không được công khai trích yếu ở cổng xác thực (ràng
buộc `documents_restricted_private`: không `restricted` và `is_public` cùng lúc).

**Liên thông trong hệ thống** (F3.12, migration 1792281601800). Một dòng `office.dispatches` có hai bên, mỗi bên đọc
theo văn bản của mình: `clerk`, `staff`, `manager`, `director` của đơn vị gửi thấy dòng khi đọc được văn bản đi
(`tenant_id = X-Hasura-Tenant-Id` và `document.visible`); của đơn vị nhận thấy khi văn bản đến đã có và họ đọc được nó
(`to_tenant_id = X-Hasura-Tenant-Id` và `incoming.visible`) — dòng còn chờ giao thì bên nhận chưa thấy. Cột cho người
dùng: id, hai đơn vị, hai văn bản, trạng thái, mã tra cứu và băm chụp lúc phát hành, số lần thử, lỗi, lúc tạo, lúc
giao; `file_id`, `next_attempt_at`, `notified_at` chỉ `service` đọc. Quan hệ sang văn bản của bên kia (`document`,
`incoming`, `source`) trả null, vì quyền đọc văn bản lọc theo thuê ước: bên gửi không thấy tiến độ xử lý của bên nhận,
bên nhận không đọc văn bản gốc — chỉ có tên đơn vị kia qua `to_unit` (bên gửi) / `from_unit` (bên nhận). Quan hệ trỏ
về chính đơn vị mình trả null (`from_unit` ở bên gửi, `to_unit` ở bên nhận). `office.dispatch_units` cho bốn vai trò
người dùng và `service` đọc mọi đơn vị trừ đơn vị trong phiên (`id <> X-Hasura-Tenant-Id`). Không vai trò nào thêm,
xóa dòng `dispatches`; `service` (phiên bên gửi hoặc bên nhận) chỉ sửa `attempts`, `last_error`, `next_attempt_at`,
`notified_at`; trạng thái chỉ đổi trong hàm `office.deliver_dispatch` (mutation chỉ cho `service`).

**Tác tử đọc văn bản đến** (F4.1, migration 1792281601900). Vai trò Hasura `agent` không có trong token người dùng:
`svc-files` gọi bằng khóa quản trị kèm `X-Hasura-Role: agent`, `X-Hasura-Tenant-Id` (đơn vị của văn thư bấm đọc),
`X-Hasura-User-Id` = danh tính tác tử (`MOC_AGENT_ID`, mặc định `moc-doc-reader`). Quyền:

| Bảng | Được làm | Cột đặt sẵn |
|---|---|---|
| `office.intake_suggestions` | Thêm, đọc, sửa (upsert) gợi ý của đơn vị trong phiên; không xóa | `tenant_id`, `agent_id` |
| `office.assignment_suggestions` | Thêm gợi ý giao việc (F4.3); chỉ đọc được cột `document_id` (văn bản đã có gợi ý chưa); không sửa, xóa | `tenant_id`, `agent_id` |
| `core.audit_log` | Chỉ thêm dòng `action = intake.suggested`, `entity = core.files`; `action = assistant.answered`, `entity = ai.questions` (F4.2); hoặc `action = assignment.suggested`, `entity = office.documents` (F4.3) (cột `request_id`, `entity_id`, `diff`) | `tenant_id`, `actor_id`, `actor_kind = agent` |

Ngoài các bảng này `agent` không có quyền nào: không đọc, ghi văn bản, không đọc `core.files`, không đọc sổ. Tệp có
được đọc hay không do `svc-files` hỏi Hasura bằng **token của văn thư** trước khi đọc byte; khóa ngoại kèm thuê ước
chặn lưu gợi ý cho tệp của đơn vị khác.

**Trợ lý hỏi đáp** (F4.2, migration 1792281602000). Tác tử thứ hai dùng chung vai trò `agent`, khác danh tính:
`X-Hasura-User-Id` = `MOC_ASSISTANT_ID` (mặc định `moc-assistant`), `X-Hasura-Tenant-Id` = đơn vị của người hỏi. Vai
trò không thêm quyền nào: tác tử chỉ ghi một dòng sổ `assistant.answered` cho mỗi lượt hỏi (§5), ghi xong mới trả lời.
Trợ lý không đọc văn bản bằng vai trò của mình. Quyền được giữ ở hai lớp, cả hai đứng trước mô hình và trước người
dùng:

1. **Lọc trước** trong chỉ mục đoạn Meilisearch `chunks`: mỗi đoạn mang `tenant_id`, `direction`, `department_id`,
   `created_by`, giao việc chưa hủy (`assignee_departments`, `assignee_users`); điều kiện tìm dựng theo vai trò đúng như
   `office.document_visible` (`clerk`, `director`: mọi văn bản của đơn vị; `manager`: phòng mình soạn hoặc giao cho
   phòng mình; `staff`: mình tạo, giao cho mình, văn bản đi của phòng mình; vai trò khác: 403). Văn bản hạn chế không
   bao giờ vào chỉ mục.
2. **Hậu kiểm** bằng Hasura với **token người hỏi** (như tìm kiếm F2.7): đoạn của văn bản Hasura không trả về, hoặc
   trả về mà `restricted`, bị bỏ trước khi tới mô hình và người dùng.

Lớp 1 quyết độ phủ, lớp 2 quyết an toàn: chỉ mục chậm vài giây sau khi văn bản bật hạn chế hay giao việc bị hủy cũng
không lộ đoạn nào, lượt đồng bộ sau tự sửa. Vòng chỉ mục nền đọc văn bản, chữ của tệp bằng khóa quản trị (như F2.7).

**Tác tử gợi ý giao việc** (F4.3, migration 1792281602100). Tác tử thứ ba dùng chung vai trò `agent`, nằm trong
`svc-workflow`: `X-Hasura-User-Id` = `MOC_ASSIGNER_ID` (mặc định `moc-assigner`), `X-Hasura-Tenant-Id` = đơn vị của
văn bản. Bằng vai trò này tác tử chỉ hỏi văn bản đã có gợi ý chưa và lưu gợi ý cùng dòng sổ `assignment.suggested`
(bảng trên). Phần đọc dùng vai trò `service` sẵn có của `svc-workflow`: văn bản đích, lịch sử giao việc của các văn bản
tương tự (chỉ văn bản đến không hạn chế), danh sách phòng có lãnh đạo phòng đang hoạt động. Tìm văn bản tương tự là
việc của `svc-files` (`POST /internal/similar-documents`, §4.3): phạm vi vai trò `service` của thuê ước, chỉ văn bản đến
đã giao (`in_progress`, `done`, `archived`), hậu kiểm bỏ văn bản hạn chế, chỉ trả id và điểm.

Quyền đọc gợi ý:

| Vai trò | Đọc `office.assignment_suggestions` |
|---|---|
| `director` | Mọi cột, gợi ý của văn bản mình đọc được (`tenant_id = X-Hasura-Tenant-Id` và `document.visible`); quan hệ `document`, `department` |
| `clerk`, `staff`, `manager`, `tenant_admin` | Không có bảng này: gợi ý thuộc bước chỉ đạo của lãnh đạo đơn vị. Dòng sổ `assignment.suggested` (không có căn cứ) vẫn hiện ở tab Lịch sử cho người đọc được văn bản |
| `agent` | Chỉ cột `document_id` của đơn vị trong phiên |

Căn cứ chỉ có id: giao diện hỏi lại `office_documents(where: {id: {_in: …}, restricted: {_eq: false}})` bằng token
người xem rồi mới hiện số ký hiệu, trích yếu — căn cứ người xem không đọc được thì không hiện.

> **Không đặt tên vai trò là `admin`.** `admin` là vai trò có sẵn của Hasura, bỏ qua mọi quyền kể cả khi nằm
> trong JWT. Chạy thử ở #18: token có `x-hasura-default-role: admin` đọc được dữ liệu của mọi thuê ước.
> Quản trị đơn vị là `tenant_admin`; mapper của realm chỉ đưa 5 vai trò nghiệp vụ vào claim.

Ghi trực tiếp (không qua Action):

| Vai trò | Được làm | Cột đặt sẵn |
|---|---|---|
| `staff` | Thêm dự thảo văn bản đi (kể cả đơn vị nhận trong hệ thống, `recipient_tenant_ids` — F3.12); sửa khi còn `draft` hoặc `returned` | `tenant_id`, `created_by`, `direction = 'out'`, `status = 'draft'` |
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

**Chữ ký số** (F4.5, migration 1792281602200, chỉ minh họa):

| Vai trò | `core.file_signatures` | `office.issued_documents` |
|---|---|---|
| `service` | Chỉ thêm, cột `file_id`, `level`, `signed_at`, `signer_name`, `ca_name`, `serial`, `cert_sha256`, `not_after`, `key_name`, `key_version`; `tenant_id` đặt sẵn từ phiên. Không đọc, sửa, xóa: `svc-files` ghi bằng `insert_core_file_signatures { affected_rows }` cùng mutation với `insert_core_files_one` (`returning` cần quyền đọc nên không dùng) | — |
| `verifier` | Không có | Thêm năm cột chữ ký vào các cột đã có; `limit: 1` giữ nguyên |
| Vai trò người dùng, `agent` | Không có | Không có |

Khóa ngoại `(tenant_id, file_id)` → `core.files` chặn phiên của đơn vị này gắn chữ ký vào tệp của đơn vị khác. Sổ kiểm
toán ghi dòng `core.file_signatures` như mọi bảng; `director`, `tenant_admin` thấy dòng đó ở màn Sổ kiểm toán với tên
các cột, giá trị chỉ có ở `file_id` (bản tối thiểu chưa thêm nhánh vào `core.audit_overview`).

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
| `otSensorMap` (query) | `clerk`, `staff`, `manager`, `director` — các vai trò đọc được dự thảo "Báo cáo sự cố" | Sơ đồ cảm biến OT (F3.10): đọc context broker NGSI-LD ở tenant của đơn vị trong biến phiên (thực thể `TemperatureSensor`, lịch sử 10 lần đo gần nhất), trả số đo mới nhất, mã phòng (`room`), ngưỡng và cờ chất lượng — `stale` (quá `MOC_OT_STALE_MIN` phút không có số đo), `out_of_range` (không phải số hoặc ngoài −55…125 °C), `duplicate_time` (số đo mới nhất trùng `observedAt` với lần đo khác), `future_time` (`observedAt` muộn hơn giờ máy chủ quá 2 phút; khi đó `stale` xét theo lúc broker nhận số đo). Chỉ đọc, không ghi CSDL; chưa bật broker thì `status` = `off` / `unavailable`, không lỗi |

Mọi Action **idempotent** theo `(documentId, trạng thái hiện tại)` hoặc `taskId`: gọi lại sau lỗi mạng không
cấp số hai lần. `completeTask` chạy theo thứ tự: kiểm quyền và dữ liệu → nhận việc trong Flowable (người khác
đã nhận thì 409) → ghi PostgreSQL trong một giao dịch, sự kiện mang `task_id` và biến sẽ gửi Flowable (`flow`)
→ hoàn thành việc trong Flowable. Gọi lại khi đã có sự kiện mang `task_id` thì bỏ qua bước ghi, hoàn thành việc
bằng đúng `flow` đã ghi (lần bấm lại chọn khác cũng không đổi nhánh); CSDL từ chối thì trả việc về nhóm.

Hai lần gọi chen nhau (bấm lại khi phát hành lâu, bấm đúp) không ghi hai lần:
- Trong `svc-workflow`, các lần gọi cùng một việc, cùng một văn bản (vào sổ, trình, đối soát) chạy lần lượt.
- Chỉ mục duy nhất `document_events_task_once` trên `(data->>'task_id')`: mỗi việc chỉ có một sự kiện, lần ghi thứ
  hai bị chặn cả giao dịch (cả phân công đi kèm); `svc-workflow` đọc lại sự kiện đã ghi và hoàn thành nốt việc
  theo `flow` của nó (không thấy sự kiện của văn bản này thì báo lỗi 409).
  Sự kiện nhắc hạn mang `sla_task_id`, không thuộc chỉ mục.
- `process_id` chỉ gắn khi văn bản chưa có (`update … where process_id is null`): lần gọi thua theo quy trình đã
  gắn và hủy quy trình nó vừa khởi chạy. Hủy không được (Flowable không trả lời) thì quy trình thừa còn lại, nhật ký
  ghi `office.process.duplicate_left` để dọn tay; ghi `process_id` lỗi sau khi đã khởi chạy thì nhật ký ghi
  `office.process.unlinked`.

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

**Liên thông trong hệ thống** (F3.12, migration 1792281601800; bảng ở §2.2). Văn bản đi có `recipient_tenant_ids`:

1. Cùng giao dịch với bước 3, trigger `documents_dispatch` (sau khi `status` chuyển sang `issued`) thêm một dòng
   `office.dispatches` `pending` cho mỗi đơn vị nhận (`on conflict on constraint dispatches_once do nothing`), chụp mã
   tra cứu và băm. Phát hành lỗi thì không có dòng nào; phát hành xong thì dòng đã nằm trong CSDL (hộp thư đi), không
   phụ thuộc dịch vụ còn chạy hay không. `submitOutgoing` kiểm lại đơn vị nhận trước khi trình.
2. `svc-workflow` giao từng dòng ngay sau khi phát hành; vòng nền đối soát giao lại dòng `pending` đến hạn
   (`next_attempt_at`) và báo dòng đã giao mà chưa báo (`notified_at` null). Các lần gọi cùng một dòng chạy lần lượt.
   Giao một dòng:
   1. `svc-files` `POST /internal/dispatch-file` (§4.3) chép tệp phát hành sang đơn vị nhận với id = `file_id`.
   2. Hàm `office.deliver_dispatch(dispatch_id)` — Hasura đưa ra thành mutation `office_deliver_dispatch`, chỉ vai trò
      `service`, gọi trong phiên của **đơn vị nhận** (thuê ước, người thực hiện lấy từ `hasura_session`):
      - khóa dòng (`for update`); dòng không gửi tới đơn vị trong phiên thì báo như không có; đã khác `pending` thì trả
        nguyên dòng;
      - văn bản gửi không còn `issued` / `archived`, hoặc là văn bản hạn chế → `failed`;
      - đơn vị nhận đã có văn bản đến trùng (cùng khóa của `documents_in_dedup`, chưa hủy — vd đã tiếp nhận tay từ bản
        giấy) → `duplicate`, nối `incoming_document_id`, sự kiện `office.document.dispatch_duplicate` ở văn bản gửi;
      - không thì trong một khối `begin … exception`: văn bản đến `received` (loại, số ký hiệu, ngày ban hành, độ khẩn
        của văn bản gửi; `issuer_name` = tên đơn vị gửi; trích yếu làm sạch bằng `office.clean_text` — trích yếu văn
        bản đi không theo các ràng buộc `documents_in_*` của F2.2; `source_id`; `created_by` = người thực hiện), tệp
        `main` = `file_id`, sự kiện `office.document.arrived` (văn bản đến) và `office.document.dispatched` (văn bản
        gửi), `delivered`, `delivered_at`. Vi phạm ràng buộc (`check_violation`, `unique_violation`) → khối quay lui,
        `failed` kèm `last_error` — lỗi cố định, không giao lại. Chưa có tệp ở đơn vị nhận (khóa ngoại) → lỗi, dòng
        vẫn `pending`.
   3. Báo văn thư đơn vị nhận (không có văn thư thì lãnh đạo đơn vị): thông báo `document.incoming` (§5), rồi đặt
      `notified_at`.
3. Lỗi ở bước chép tệp hay giao (dịch vụ, kho, ClamAV không sẵn sàng; khóa ngoại) → `attempts + 1`, `last_error`,
   `next_attempt_at = now + min(30 giây · 2^n, 1 giờ)`.

**Đúng một lần.** Một dòng cho mỗi (văn bản, đơn vị) (`dispatches_once`). Nhiều nhất một văn bản đến cho mỗi dòng:
khóa dòng và trạng thái trong hàm, chốt cuối là chỉ mục `documents_source_once` (văn bản đến đã hủy vẫn giữ chỗ). Tệp
chép một lần: `file_id` định trước từ lúc tạo dòng, `svc-files` chép lại thì trùng khóa chính. Nhiều nhất một thông báo
cho mỗi người: khóa `doc:<văn bản đến>:document.incoming` của `core.notifications`. Hai sổ kiểm toán cùng ghi trong
giao dịch giao: `core.audit()` lấy `tenant_id` từ chính dòng ghi — dòng `dispatches` vào sổ bên gửi, văn bản đến và tệp
vào sổ bên nhận; người thực hiện là tài khoản dịch vụ (`actor_kind` `service`).

**Rủi ro đã biết** (ghi lại, chưa làm):
- `office.dispatch_units` cho mọi người dùng thấy tên mọi đơn vị trên cùng hệ thống — ổn cho các khoa, phòng của một
  trường; bản nhiều tổ chức (SaaS) cần cờ kiểu `dispatch_open` trên `core.tenants` để đơn vị chọn có hiện trong danh
  sách hay không.
- Hàm đánh dấu `duplicate` hoặc `failed` sau khi `svc-files` đã chép tệp: bản sao (dòng `core.files` và đối tượng
  trong kho) mồ côi ở đơn vị nhận.
- Chưa có nút gửi lại dòng `failed` (việc Could: Action `retryDispatch` đưa dòng về `pending`).
- Bên gửi không thấy tiến độ xử lý của bên nhận — cố ý cách ly; chỉ biết đã giao và lúc nào.
- Nhiều bản sao `svc-workflow` cùng giao một dòng: dựa vào khóa dòng của hàm và `file_id` định trước (`svc-files` thua
  khóa chính thì chỉ xóa đối tượng của mình khi khác khóa của dòng đã có).
- Dòng còn `pending` chặn nộp lưu văn bản gửi; job nộp lưu bỏ qua hồ sơ đó 24 giờ rồi thử lại.

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

**Gợi ý giao việc** (F4.3, QĐ-005 trong `docs/architecture.md`). Trong `van-ban-den`, `vaoSo` dẫn tới cổng song song
`tachGoiY` tách hai nhánh, không nối lại:

- `chiDao` như cũ (cả timer nhắc hạn `hanChiDao`): lúc vào sổ lãnh đạo đã có việc, thông báo đi ngay.
- Service task `goiYGiaoViec` (external worker, topic `moc-goi-y`, không vào hộp việc của ai) → end `daGoiY`. Timer
  ngắt `boGoiY` (`PT10M`, hằng) → end `khongGoiY`: lưới an toàn khi không ai nhận việc (`MOC_SUGGEST_POLL_INTERVAL_S=0`,
  `svc-workflow` dừng). Không có terminate end event: nhánh gợi ý lỗi hay quá giờ không chặn chỉ đạo.

`svc-workflow` tự lấy việc `moc-goi-y` về (vòng nền mỗi 2 giây, như `moc-sla`). Mỗi việc: bỏ qua nếu tắt gợi ý, lãnh
đạo đã chỉ đạo xong, văn bản hạn chế hay là văn bản đi, hoặc đã có gợi ý; gọi `svc-files` tìm văn bản tương tự (hạn
`MOC_SUGGEST_TIMEOUT_S`); đọc lịch sử giao việc chủ trì gốc của chúng, bỏ phiếu, chỉ giữ phòng có lãnh đạo phòng đang
hoạt động (chỉ đạo cho phòng không có lãnh đạo phòng bị từ chối `no_manager`); lưu gợi ý và dòng sổ trong một giao dịch
bằng vai trò `agent` (§3) rồi hoàn thành việc. `svc-files` không trả lời → dòng `failed`, không thử lại: lãnh đạo giao
như thường lệ. Chỉ gợi ý đơn vị chủ trì và hạn; người xử lý vẫn do lãnh đạo phòng phân công (`vbden.phanCong`).
Thuật toán, ngưỡng, số đo: README của `svc-workflow`.

### 4.3. API REST của `svc-files`

| Đường dẫn (qua APISIX) | Ai gọi | Làm gì |
|---|---|---|
| `POST /api/files` | Người đăng nhập | Quét ClamAV → ghi SeaweedFS → thêm dòng `core.files`; nhiễm thì trả 422 và ghi `file.rejected`. `?restricted=true`: chỉ PDF, mã hóa bằng khóa riêng do két cấp rồi mới ghi, `wrapped_dek` vào CSDL (F3.7) |
| `GET /api/files/{id}` | Người có quyền với văn bản chứa tệp | Kiểm quyền qua Hasura; tệp mã hóa thì giải mã trong bộ nhớ, kiểm băm, đóng dấu tên người xem lên mọi trang, ghi `file.decrypted` vào sổ kiểm toán rồi mới trả |
| `GET /api/search?q=` | Người đăng nhập | Meilisearch tìm trong số ký hiệu, trích yếu, cơ quan ban hành, nội dung văn bản đi và chữ của PDF đính kèm (trừ văn bản hạn chế); lọc thuê ước và quyền phía server; `matched_content` báo kết quả chỉ khớp nội dung |
| `GET /api/documents/{id}/preview` | Người đọc được văn bản đi | PDF đúng thể thức của dự thảo, chưa có số, in chữ "DỰ THẢO" |
| `GET /api/registers/{in\|out}/{year}` | `clerk`, `director` | Sổ đăng ký một năm, cột theo mẫu NĐ 30 Phụ lục IV; dòng văn bản hạn chế người gọi không đọc được chỉ có số, ngày, số ký hiệu |
| `GET /api/registers/{in\|out}/{year}/pdf` | `clerk`, `director` | Như trên, ra PDF A4 ngang để ký nhận, đóng sổ; ghi `register.printed` vào sổ kiểm toán |
| `GET /api/verify/{code}` | Ẩn danh | `{result, document: {symbol, issued_on, type_name, issuer_name, parent_name, summary?, sha256, verify_code, status, signature}}`; `summary` chỉ có khi `is_public`; `signature` (F4.5, chỉ minh họa) luôn có mặt: `{level, signer, ca, serial, signed_at, illustrative: true}`, hoặc `null` khi bản phát hành không ký |
| `GET /api/verify?sha256=…` | Ẩn danh | Như trên, tra theo băm do trình duyệt tự tính |
| `GET /api/case-files/{id}/archive` | Người xem được hồ sơ | Phòng đọc hồ sơ đã nộp lưu: đọc lại gói từ bucket lạnh, so băm với CSDL, văn bản người gọi đọc được từ Parquet (số còn lại trong `hidden`); ghi `case_file.read` vào sổ kiểm toán |
| `GET /api/case-files/{id}/archive/files/{file_id}` | Người xem được hồ sơ, đọc được văn bản gắn tệp | Phòng đọc xem tệp: chỉ PDF; so băm với manifest (lệch → 502, không trả byte), bản có dấu tên người xem, giờ xem (`inline`, `no-store`); ghi `case_file.file_viewed` trước khi trả |
| `POST /api/case-files/{id}/archive` | `manager`, hồ sơ của phòng mình | Nộp lưu ngay hồ sơ đã đóng: các bước của job nộp lưu; giành được lượt (chung khóa với vòng nền) rồi mới ghi `case_file.archive_requested`; 409 `not_closed`, `already_archived`, `archive_failed`, `archive_conflict`; 503 `busy` |
| `POST /api/files/{id}/read` | `clerk`, tệp do chính mình tải lên | Đọc văn bản đến (F4.1): gợi ý số ký hiệu, ngày ban hành, cơ quan ban hành, loại, độ khẩn, trích yếu kèm độ tin cậy; `?force=true` đọc lại. Tệp mã hóa → 409 `restricted`, không đọc byte. Lưu gợi ý và ghi sổ `intake.suggested` trong một giao dịch bằng vai trò `agent` (§3); không ghi được sổ thì không trả gợi ý (503). Chi tiết lỗi: README của `svc-files` |
| `POST /api/documents/ask` | `clerk`, `staff`, `manager`, `director` | Trợ lý hỏi đáp (F4.2): `{question, mode: extract\|generate, direction?, year?, type_code?, ask_id?}` → câu trích nguyên văn (luôn có, không cần mô hình) hoặc câu trả lời do mô hình viết, mỗi ý có `[n]`; `sources` (số ký hiệu, trang, đoạn trích) chỉ gồm văn bản người hỏi đọc được, lọc trước trong chỉ mục và hậu kiểm bằng token người hỏi (§3). `no_evidence` giống hệt dù văn bản không tồn tại hay bị cấm. Mỗi lượt một dòng sổ `assistant.answered` bằng vai trò `agent`, không ghi được sổ thì không trả lời (503). Đi qua route `/api/documents/*` sẵn có của APISIX. Chi tiết lỗi: README của `svc-files` |
| `POST /api/imports/incoming` | `clerk` | Nạp lô văn bản đến (cụm ⑤): multipart `data` (NDJSON hoặc CSV, cùng trường với `receiveIncoming`, thêm `files`: tên tệp trong zip) + `archive` (zip) tùy chọn, `?register=true` vào sổ từng văn bản, `Idempotency-Key` tùy chọn. Kiểm cả tệp (tệp dữ liệu qua ClamAV), ghi lô + dòng + `import.created` trong một mutation, trả 202. Vòng nền đưa từng dòng qua đúng `ingest()` và Action `receiveIncoming` (tùy chọn `registerIncoming`) với phiên của văn thư tạo lô; lỗi một dòng không hỏng dòng khác. Chi tiết lỗi: README của `svc-files` |
| `GET /api/imports/{id}` | Người tạo lô | Trạng thái, số dòng đã nhận, còn chờ, đạt, trùng, lỗi; người khác (kể cả cùng đơn vị) → 404 |
| `GET /api/imports/{id}/rows` | Người tạo lô | Kết quả từng dòng: số dòng, mã, lý do, lỗi theo trường, id văn bản, số đến; không trả lại dữ liệu đã gửi |
| `GET /api/imports` | Người đăng nhập | Các lô của chính người gọi, mới trước |
| `POST /internal/issue` | Chỉ `svc-workflow` (token tài khoản dịch vụ), không qua APISIX | Dựng, ký số (F4.5, chỉ minh họa — xem dưới), quét, lưu bản phát hành; trả `{file_id, sha256, size_bytes}`, `sha256` là băm của bản đã ký. 503 `signing_unavailable` khi két không trả lời (không lưu gì, văn thư bấm lại) |
| `POST /internal/similar-documents` | Chỉ tài khoản dịch vụ trong `MOC_SERVICE_CLIENTS` (`svc-workflow`), không qua APISIX, không có trong `/openapi.json` | Gợi ý giao việc (F4.3): `{tenant_id, document_id, limit}` (`limit` 1–30, mặc định 15) → `{document_id, hits: [{document_id, score}], terms, semantic, duration_ms}` — văn bản đến khác đã giao (`in_progress`, `done`, `archived`) tương tự theo trích yếu, điểm giảm dần, đã hậu kiểm bỏ văn bản hạn chế; dùng lại phần truy xuất của trợ lý hỏi đáp (phạm vi vai trò `service` của thuê ước). Không trả chữ nào (`terms` chỉ là số từ của câu tìm), nhật ký không ghi trích yếu. 404 `not_found`; 409 `not_incoming`, `restricted` (không tìm gì thêm); 503 `assistant_disabled` (`MOC_ASK_ENABLED=false`), `search_unavailable`, `database_unavailable` |
| `POST /internal/dispatch-file` | Chỉ `svc-workflow` (như trên) | Liên thông (F3.12): `{dispatch_id, actor_id}`. svc-files tự đọc dòng `office.dispatches`, tệp `issued` và văn bản gửi bằng khóa quản trị (bên gọi không chỉ định được tệp), quét ClamAV, lưu bản sao vào `core.files` của đơn vị nhận với id = `dispatches.file_id`. 201 / 200 (đã có) `{file_id, sha256, size_bytes}`; 409 `not_pending`, `not_issued`, `restricted`, `cold`, `integrity` (SHA-256 đọc ra khác `core.files.sha256` hay `content_sha256`); 503 khi kho, ClamAV, CSDL không sẵn sàng |

`GET /api/files/{id}` (đã làm ở #19): svc-files hỏi Hasura `core_files_by_pk` **bằng token của người gọi** —
Hasura trả dòng khi người gọi là người tải lên hoặc đọc được văn bản có gắn tệp — rồi mới lấy `object_key`
bằng vai trò `service`. Không có tệp và không được xem đều trả 404. Tệp luôn trả về dạng `attachment` kèm
`Content-Security-Policy: sandbox`, để tệp HTML/SVG người dùng tải lên không chạy được trên tên miền của Signet.

`GET /api/search` (đã làm ở #20): Meilisearch tìm với điều kiện `tenant_id` lấy từ token và chỉ trả về id;
svc-files hỏi lại Hasura `office_documents(where: {id: {_in: …}})` bằng token của người gọi, giữ những văn bản
họ được đọc theo đúng thứ tự xếp hạng. Không trả tổng số kết quả. Chỉ mục được đồng bộ mỗi vài giây theo
`office.documents.updated_at`.

`verify_code`: 10 ký tự base32 ngẫu nhiên (50 bit) — không đoán, không liệt kê được. APISIX giới hạn tốc độ
`/api/verify/*` theo IP (`MOC_RATE_VERIFY_PER_MIN`).

`/api/verify` (đã làm): `svc-files` tra khung nhìn `office.issued_documents` bằng vai trò Hasura `verifier`. Vai
trò này chỉ đọc được khung nhìn đó, tối đa một dòng mỗi lần, và không có trong token của người dùng. Khung nhìn
chỉ có văn bản đi đã phát hành; trích yếu bị ẩn khi văn bản không công khai hoặc là văn bản hạn chế. Từ F4.5 câu trả
lời có thêm `document.signature` lấy từ năm cột chữ ký của khung nhìn (§2.5) — CSDL ghi lại chữ ký `svc-files` đã tự
kiểm lúc ký; trình duyệt vẫn chỉ băm cả tệp như trước, tệp không rời máy người dùng.

**Ký số khi phát hành** (F4.5, **chỉ minh họa**, không có giá trị pháp lý như chữ ký số công cộng; quyết định kiến trúc
`docs/architecture.md` QĐ-007). Trong `/internal/issue`, `svc-files` ký **sau khi dựng PDF, trước khi băm**: dựng →
ký → tự kiểm chữ ký → SHA-256 → ClamAV → lưu → `core.files` cùng `core.file_signatures` trong một mutation (§1). Băm
trả cho `svc-workflow`, `content_sha256`, sự kiện `issued`, sổ kiểm toán, bản liên thông và cổng xác thực đều theo bản
đã ký; `svc-workflow` không đổi. QR mã hóa URL theo mã tra cứu cấp lúc cấp số, nên QR không đổi.

- Chữ ký PAdES B-B (`ETSI.CAdES.detached`, SHA-256), chữ ký chứng nhận không cho sửa thêm (`NO_CHANGES`), ô ký ẩn
  `MocKySo`; không dấu thời gian tin cậy, không thông tin kiểm dài hạn: giờ ký là giờ tự khai.
- Khóa ký: khóa transit `moc-ky-so-<tenant_id>` (rsa-3072, PKCS#1 v1.5) trong két OpenBao, `svc-files` tạo ở lần phát
  hành đầu của đơn vị. Chứng thư: CSR do chính Transit ký → `pki/sign/moc-van-thu` (CN "<đơn vị>, <cơ quan chủ
  quản>", tối đa 64 ký tự) → gắn vào phiên bản khóa (`set-certificate`). Khóa riêng không ra khỏi két; mỗi lần ký là
  một lần gọi `transit/sign`, két ghi sổ.
- Không ký: văn bản hạn chế (mỗi lần mở đều viết lại PDF để đóng tên người xem); `MOC_SIGN_ENABLED=false` (không gọi
  Transit, PKI); két chưa có PKI (két khởi tạo trước F4.5 — `van-hanh.md` mục Két bí mật), két từ chối, ký hoặc tự kiểm lỗi —
  các trường hợp này vẫn phát hành (201), không có dòng chữ ký, ghi nhật ký (§5); két chưa có PKI thì dò lại sau 5 phút.
  Két không trả lời (mạng, 5xx, hết giờ): 503 `signing_unavailable`, không lưu gì.
- Văn bản phát hành trước F4.5 không ký lại (băm, QR, sổ kiểm toán đã cố định): cổng trả `signature: null`.
- Kiểm đầy đủ phần mật mã (chỉ tin đúng CA của két) trong container `svc-files`: `python -m svc_files.signing verify`
  đọc PDF từ stdin, mã thoát 0 hợp lệ, 1 sửa sau khi ký / không khớp / CA lạ / không có chữ ký, 2 không đọc được.

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

Ứng dụng cắm bằng manifest không nhận khuôn trên: Hasura Event Trigger `app_<tên>` trên `core.app_events` (§1) gọi
webhook của ứng dụng với thân sự kiện chuẩn của Hasura (không biến đổi): `event.op` = `INSERT`, `event.data.new` =
`{"id", "tenant_id", "document_id", "kind", "occurred_at"}`, `event.session_variables` = `null`; mọi loại trong danh
sách trắng, ứng dụng tự bỏ loại không khai (`MOC_APP_EVENT_KINDS`). Header `X-Moc-Hook-Secret`; giao ít nhất một lần,
chống trùng bằng `event.data.new.id`.

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
| `office.document.dispatched` | Văn bản đi đã giao tới một đơn vị trong hệ thống (F3.12, ở văn bản đi). `data`: `dispatch_id`, `to_tenant_id`, `to_name` |
| `office.document.dispatch_duplicate` | Đơn vị nhận đã có văn bản đến trùng: nối vào văn bản đó, không thêm bản thứ hai (ở văn bản đi). `data` như trên |
| `office.document.arrived` | Văn bản đến do liên thông tạo (ở văn bản đến bên nhận). `data`: `dispatch_id`, `from_tenant_id`, `from_name`, `verify_code` (mã tra cứu của bên gửi) |
| `core.file.rejected` | ClamAV chặn tệp |
| `core.intake.suggested` | Tác tử đọc xong một tệp văn bản đến, có gợi ý (F4.1). Chỉ ở sổ kiểm toán, khuôn bên dưới |
| `core.assistant.answered` | Trợ lý hỏi đáp trả lời một câu hỏi (F4.2). Chỉ ở sổ kiểm toán, khuôn bên dưới |
| `core.assignment.suggested` | Tác tử gợi ý giao việc xong một văn bản đến, có gợi ý hay không (F4.3). Ở sổ kiểm toán và tab Lịch sử của văn bản, khuôn bên dưới |
| `ot.alarm` | Cảm biến vượt ngưỡng, có dự thảo báo cáo sự cố (F3.10). Trong `office.document_events`: `actor_kind` `service` (`svc-workflow`), `data` = mã cảm biến, tên phòng, nhiệt độ, ngưỡng, giờ đo (`observed_at`; đồng hồ thiết bị chạy nhanh quá 2 phút thì là giờ máy chủ nhận, giờ thiết bị gửi ở `device_observed_at`) |

Ba sự kiện liên thông do chính hàm `office.deliver_dispatch` ghi (`actor_kind` `service`), cùng giao dịch với văn bản
đến; không bao giờ mang `task_id` — chỉ mục `document_events_task_once` là chỉ mục duy nhất cho cả bảng.

**Nhật ký ký số của `svc-files`** (F4.5, chỉ minh họa). Ký số không thêm loại sự kiện vào `office.document_events`:
`office.document.issued` giữ nguyên, băm trong đó là băm bản đã ký. `svc-files` ghi các dòng sau vào nhật ký JSON của
mình (`docker compose logs svc-files`; hai dòng `office.document.*` kèm `request_id` của lượt phát hành, các dòng
`office.signing.*` của bộ ký thì không); chữ ký thành công còn có dòng
`core.file_signatures` trong sổ kiểm toán (§1). Không dòng nào chứa trích yếu hay PDF.

| `event` | Khi | Trường |
|---|---|---|
| `office.document.signed` | Ký và tự kiểm xong một bản phát hành | `tenant_id`, `document_id`, `file_id`, `key_name`, `key_version`, `serial`, `duration_ms` |
| `office.document.sign_failed` | Ký lỗi: két từ chối, pyHanko lỗi, tự kiểm không đạt (phát hành không ký), hoặc két không trả lời (503) | `document_id`, `error` |
| `office.signing.ready` | Bộ ký dò két thấy có CA (lúc khởi động, hoặc lần dò lại sau khi tắt) | `ca`, `serial` |
| `office.signing.disabled` | Bộ ký tự tắt: két chưa có PKI (`reason` `no_pki`, một lần mỗi lượt dò) hoặc két từ chối quyền (`forbidden`); dò lại sau `retry_s` giây | `reason`, `retry_s` |
| `office.signing.unavailable` | Lần dò lúc khởi động không tới được két (lần phát hành sau dò lại) | `error` |
| `office.signing.key_created` | Lần phát hành đầu của đơn vị: két tạo khóa ký `moc-ky-so-<đơn vị>` | `key_name` |
| `office.signing.certificate_issued` | CA nội bộ cấp chứng thư cho khóa ký của đơn vị | `key_name`, `key_version`, `serial`, `not_after` |

Dòng `office.document.rendered` sẵn có thêm trường `signed` (bản phát hành có chữ ký hay không).

**Lượt đọc văn bản đến** (F4.1): mỗi lần tác tử đọc thật một tệp (không tính lần trả bản đã lưu), `svc-files` ghi
một dòng `core.audit_log` bằng vai trò `agent`: `action` `intake.suggested`, `entity` `core.files`, `entity_id` = id
tệp, `actor_id` `moc-doc-reader`, `actor_kind` `agent`. `diff` chỉ có giá trị vô hướng, **không mang nội dung**: không
số ký hiệu, trích yếu, tên tệp, chữ nhận dạng được.

```json
{
  "user_id": "<sub văn thư bấm đọc>", "file_id": "2b0c…", "status": "ok", "method": "ocr", "pages": 1,
  "found": "symbol,issued_on,issuer_name,type_code,summary", "summary_source": "rule", "model": null,
  "duration_ms": 8123, "reason": null
}
```

`status`: `ok` | `empty` | `unreadable`; `method`: `text` | `ocr`; `found`: tên các trường tìm thấy, cách nhau dấu
phẩy; `summary_source`: `rule` | `model` | `none`; `model`: tên mô hình đã dùng hoặc null; `reason`: lý do khi
`unreadable`. Lãnh đạo xem sổ thấy đủ các khóa này qua `overview` (§1).

**Câu trả lời của trợ lý hỏi đáp** (F4.2): mỗi lượt hỏi (`extract`, rồi `generate` nếu có mô hình), `svc-files` ghi
một dòng `core.audit_log` bằng vai trò `agent` **trước khi trả lời**: `action` `assistant.answered`, `entity`
`ai.questions`, `entity_id` = `ask_id` (lượt `generate` gửi lại `ask_id` của lượt `extract`, hai dòng cùng
`entity_id`), `actor_id` `moc-assistant`, `actor_kind` `agent`. Câu hỏi, câu trả lời không lưu ở đâu cả; `diff` chỉ
có giá trị vô hướng, **không** câu hỏi, câu trả lời, số ký hiệu, đoạn trích.

```json
{
  "user_id": "<sub người hỏi>", "ask_id": "5d1e…", "mode": "generate", "status": "answered",
  "answer_source": "model", "hits": 5, "cited": 2, "documents": "<id>,<id>", "semantic": true,
  "model": "qwen3:1.7b", "embed_model": "qwen3-embedding:0.6b", "duration_ms": 18230, "warnings": ""
}
```

`mode`: `extract` | `generate`; `status`: `answered` | `passages_only` | `no_evidence`; `answer_source`: `extract` |
`model` | `none`; `hits`: số đoạn sau hậu kiểm; `cited`: số nguồn được trích; `documents`: id các văn bản nguồn,
cách nhau dấu phẩy; `semantic`: lượt này có tìm theo nghĩa; `model`, `embed_model`: tên mô hình hoặc null; `warnings`:
mã cảnh báo cách nhau dấu phẩy (`embed_unavailable`, `model_unavailable`, `model_timeout`, `model_rejected`,
`model_declined`), rỗng nếu không có. Lãnh đạo xem sổ thấy mọi khóa qua `overview` (§1) trừ `documents`: id văn bản
nguồn chỉ vai trò `service` đọc được.

**Gợi ý giao việc** (F4.3): mỗi văn bản đến tác tử xét xong (có gợi ý, không gợi ý được, hay `svc-files` không trả
lời), `svc-workflow` ghi một dòng `core.audit_log` bằng vai trò `agent`, **cùng giao dịch** với dòng
`office.assignment_suggestions`: `action` `assignment.suggested`, `entity` `office.documents`, `entity_id` = id văn
bản, `request_id` `goi-y:<id việc Flowable>`, `actor_id` `moc-assigner`, `actor_kind` `agent` (hai cột cuối đặt sẵn từ
phiên). Các trường hợp bỏ qua (tắt gợi ý hay trợ lý hỏi đáp, đã chỉ đạo xong, văn bản hạn chế, đã có gợi ý) không ghi
gì. `diff` chỉ có giá trị vô hướng, **không** trích yếu, số ký hiệu hay id văn bản căn cứ (`evidence` là số đếm):

```json
{
  "outcome": "suggested", "outcome_reason": null, "department_id": "5cc3…", "due_days": 10,
  "confidence": "high", "evidence": 4, "candidates": 12, "semantic": false, "duration_ms": 183
}
```

`outcome`: `suggested` | `none` | `failed`; `outcome_reason`: lý do khi không gợi ý (`no_similar`, `no_history`,
`no_valid_unit`, `low_confidence`, `timeout`, `unavailable`), null khi có gợi ý; `department_id`: đơn vị gợi ý hoặc
null; `due_days`: số ngày đề xuất hoặc null; `evidence`: số căn cứ; `candidates`: số văn bản `svc-files` trả về;
`semantic`: có tìm theo nghĩa. Khóa là `outcome`, `outcome_reason` (không phải `status`, `reason`) để giao diện không
lẫn với nhãn của F4.1, F4.2. Dòng gắn vào văn bản nên hiện ở tab Lịch sử cho người đọc được văn bản; lãnh đạo xem sổ
thấy mọi khóa qua `overview` (§1).

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
| `document.incoming` | Văn thư đơn vị nhận (không có văn thư thì lãnh đạo đơn vị) | Có văn bản đến liên thông mới (F3.12); `data`: tóm tắt văn bản đến như các thông báo khác, kèm `from_name`; khóa `doc:<văn bản đến>:document.incoming` |

Dashboard điều hành (F3.11) không dùng kênh realtime: số liệu tính lúc mở trang, có nút làm mới (§2.5).

---

## 6. Việc cần chốt khi rà PR

1. Danh sách loại văn bản ban đầu và cách sinh ký hiệu (công văn: `số/viết tắt đơn vị-viết tắt phòng`;
   loại khác: `số/tên loại-viết tắt đơn vị`) — đối chiếu phụ lục NĐ 30.
2. ~~Văn bản đi gửi nhiều đơn vị trong hệ thống~~ — F3.12 làm đúng như đã chọn: một văn bản đến cho mỗi đơn vị
   nhận (`source_id` trỏ về văn bản đi), qua hộp thư đi `office.dispatches` (§2.2, §4.2).
3. `completeTask` dùng chung hay tách Action theo từng task — bản nháp chọn dùng chung, kiểm theo `formKey`.
4. ~~Phạm vi Phase 1~~ — #18 làm toàn bộ §1 và §2.1–2.3, cùng trigger sổ kiểm toán. Còn `case_files`,
   `case_file_documents` và các view ở §2.5 (Phase 2–3).
5. Danh mục loại văn bản: #18 nạp 27 loại có tên viết tắt (NĐ 30, Phụ lục III) và `CV` (công văn); chưa có
   thư công. Backend đối chiếu khi rà.
