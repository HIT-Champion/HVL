# Thêm một ứng dụng mới trên lõi Signet

Signet chia hai tầng. Tầng 1 là lõi không giao diện: định danh (Keycloak), cổng API (APISIX), dữ liệu và quyền
(PostgreSQL + Hasura), tệp và kiểm dịch (`svc-files`), quy trình (`svc-workflow`, Flowable), sổ kiểm toán chuỗi băm.
Tầng 2 là ứng dụng, gọi lõi qua cổng như mọi client khác. Văn phòng điện tử (`apps/office`) là ứng dụng đầu tiên.

Có hai cách cắm thêm một ứng dụng:

- **Một lệnh, không sửa tệp nào của lõi** (mục 1): viết `apps/<thư mục>/app.yaml` rồi
  `python3 scripts/moc.py app install apps/<thư mục>/app.yaml`. Ví dụ: **Bảng tin đơn vị** (`apps/bang-tin`), ứng
  dụng thứ ba, nghe sự kiện của lõi.
- **Làm tay** (mục 3, giữ làm tham chiếu): sửa realm, route, compose, thêm migration và metadata vào lõi — cách đã
  dùng cho **Không gian cá nhân P.A.R.A** (`apps/ca-nhan`), ứng dụng thứ hai. Cách này vẫn cần cho ứng dụng muốn
  thành một phần của lõi (cùng phiên bản, cùng bản cài, có trong mọi bản chạy).

## 1. Một lệnh: `moc app install`

```bash
python3 scripts/moc.py app install apps/bang-tin/app.yaml --dry-run   # in kế hoạch 8 bước (9 khi có workflow)
python3 scripts/moc.py app install apps/bang-tin/app.yaml             # make app-install APP=apps/bang-tin/app.yaml
python3 scripts/moc.py app list                                       # make app-list
python3 scripts/moc.py app remove bang-tin                            # make app-remove APP=bang-tin — GIỮ dữ liệu
```

Chạy trên một bản Signet đang chạy (`make up`), ở thư mục chạy (gốc repo hoặc thư mục `make install`). Chạy lại bao
nhiêu lần cũng được: bước nào đã khớp thì bỏ qua, không tạo client, migration, container trùng. Lỗi giữa chừng thì
lệnh báo đúng bước (`✗ bước 5/8 (Keycloak): …`) và cách chạy lại; chạy lại chỉ làm phần còn thiếu. Thoát 0: xong;
1: manifest sai (kể cả BPMN, form bị `svc-workflow` từ chối), xung đột hay một bước lỗi; 2: không gọi được CSDL,
Keycloak, Docker, `svc-workflow`.

Người dùng thấy ứng dụng đã cài ở trang **Danh mục ứng dụng** của Văn phòng điện tử (`/ung-dung`, mục "Ứng dụng" ở
thanh bên, mọi vai trò): tên, mô tả (`description` của manifest), nút Mở tới `/<đường>/`, phiên bản, lúc cài, cùng hai
ứng dụng có sẵn trong lõi (Văn phòng điện tử, Không gian cá nhân — phiên bản lõi lấy từ `/api/status`). Lãnh đạo, quản
trị đơn vị thấy thêm **băm manifest** (SHA-256 các byte của `app.yaml` lúc cài — so với `sha256sum
apps/<thư mục>/app.yaml` để biết bản đang cài đúng bản đã duyệt; nút chép đủ 64 ký tự) và ứng dụng **đã gỡ**. Trang
đọc khung nhìn `core.app_catalog` (migration `1792281603400`): 9 cột của `core.apps`, không có manifest (image, cổng,
healthcheck, biến môi trường, cổng webhook), không schema; `core.apps` vẫn không vào GraphQL; không vai trò nào ghi.
Trạng thái ghi "Đã cài", không ghi "đang chạy": CSDL không biết container của ứng dụng có khỏe không. Kiểm: office
`apps.test.ts`, db `test_app_catalog.py`, `make demo-cai-ung-dung` (bước 4, 6, 7), e2e `ung-dung.spec.ts`.

### 1.1. Manifest

Cấu trúc đầy đủ: [`scripts/app-manifest.schema.json`](../scripts/app-manifest.schema.json) (JSON Schema 2020-12). Lệnh
kiểm toàn bộ trước bước đầu tiên và in mọi lỗi một lượt. Đọc bằng bộ đọc YAML thư viện chuẩn (`scripts/yaml_nho.py`,
không cần PyYAML trong thư mục cài): không nhận chuỗi nhiều dòng `|` `>`, thẻ `!`, `yes`/`no` không nháy.

| Khóa | Nghĩa | Lõi kiểm thêm |
|---|---|---|
| `name`, `title`, `version`, `description` | Tên ngắn (`app-<tên>` cho service, client; `app_<tên>` cho trigger, vai trò dịch vụ), tên hiển thị, phiên bản `X.Y.Z` | Tên giữ chỗ (`office`, `ca-nhan`, `core`…) bị từ chối |
| `path` | Đường của trang trên cổng: route `/<đường>`, `/<đường>/*` | Không trùng đường của lõi, của ứng dụng đang cài, của trang Văn phòng điện tử (test so với `apps/office/app/pages`); ứng dụng đã gỡ trả lại đường |
| `image` | `{build: .}` — dựng từ thư mục ứng dụng lúc cài (thẻ `moc/app-<tên>:<phiên bản>-<băm thư mục>`), hoặc `{ref: …@sha256:…}` — image dựng sẵn, bắt buộc ghim digest | Thư mục dựng phải nằm trong thư mục ứng dụng, có `Dockerfile` |
| `port`, `healthcheck`, `memory`, `read_only`, `environment` | Cổng của trang trong container; healthcheck dạng exec; giới hạn bộ nhớ (mặc định 256m); rootfs chỉ đọc (mặc định); biến môi trường **không bí mật** | Tên biến giống bí mật (`…SECRET`, `…TOKEN`, `…KEY`…) hay biến lõi đặt bị từ chối; giá trị chép nguyên văn (`$` ghi thành `$$`: compose không thay `${…}` bằng biến trong `.env` của lõi) |
| `database.schema`, `database.migrations` | Schema riêng; thư mục `<số>_<tên>/up.sql`, áp theo thứ tự số | Không phải schema của lõi, của hệ thống; symlink không được trỏ ra ngoài thư mục migration; xem 1.4 |
| `metadata.tables` | Cùng định dạng tệp bảng của `db/metadata`: bảng, quan hệ, `select`/`insert`/`update_permissions` | Bảng chỉ trong schema của ứng dụng; quan hệ chỉ một chiều về `core`, `office`; vai trò chỉ `clerk`, `staff`, `manager`, `director`, `tenant_admin` (và `app_<tên>` khi có `service_account`); vai trò người dùng phải lọc theo đơn vị: `filter` (đọc, sửa) và `check` (thêm, khi không `set`) có `tenant_id: {_eq: X-Hasura-Tenant-Id}` ở gốc hoặc trong `_and` cấp đầu — nằm trong `_or`, `_not` không tính; hoặc `set: {tenant_id: X-Hasura-Tenant-Id}` khi thêm; điều kiện trong quyền (mọi vai trò) không có `_exists`, qua quan hệ sang `core`, `office` chỉ nhận `visible: {_eq: true}` (xem 1.9); bảng phải có ở bước 3 (sau migration); không có `delete_permissions`, `event_triggers` |
| `service_account` | `true`: client bí mật `app-<tên>-svc` cho phần máy chủ (xem 1.5) | — |
| `events` | `kinds` (danh sách trắng của lõi), `webhook: {port, path}`, `retry` | `webhook.port` khác `port` (cổng webhook không có route ra ngoài) |
| `workflow` | `processes`: tệp BPMN `*.bpmn20.xml`; `forms`: `formKey` → tệp JSON Schema — quy trình chạy trên Flowable của lõi (1.10) | `formKey` mở đầu `<tên>.`; tệp có thật, trong thư mục ứng dụng; nội dung BPMN, form do `svc-workflow` kiểm ở bước 1 (danh sách trắng, 1.10) |

Không có bí mật nào trong manifest: header webhook và client secret do lệnh sinh lúc cài.

### 1.2. Lệnh làm gì

| # | Bước | Ghi vào đâu |
|---|---|---|
| 1 | Kiểm manifest | — |
| 2 | Image: có rồi thì thôi; không thì `docker build` (hoặc `docker pull` ảnh ghim digest) | Docker |
| 3 | CSDL: ghi `core.apps` (không đổi gì thì không ghi), tạo vai trò `moc_appdb_<schema>` và schema của nó, áp migration còn thiếu bằng vai trò đó (1.4), kiểm bảng khai trong manifest đã có | `core.apps`, `core.app_migrations` (sổ kiểm toán chuỗi băm ghi cả hai) |
| 4 | Bí mật còn thiếu: header webhook, client secret (giữ cái đã có) | `.moc-apps/<tên>.env` (0600) |
| 5 | Keycloak: client công khai `app-<tên>` chép từ `app-office` (PKCE S256, 5 mapper, chuyển hướng và đăng xuất chỉ dưới `/<đường>/*` — đổi `path` thì sửa theo); client dịch vụ `app-<tên>-svc` | Keycloak qua cổng quản trị nội bộ (như `moc tenant`) |
| 6 | Tệp chạy dựng từ tệp lõi + bản ghi các ứng dụng đã cài | `.moc-apps/` (dưới đây), `COMPOSE_FILE` trong `.env` |
| 7 | `docker compose up -d --no-deps apisix hasura app-<tên>`: compose chỉ tạo lại dịch vụ có cấu hình đổi; tệp route `.moc-apps/apisix.yaml` vừa đổi thì khởi động lại `apisix` và chờ cổng trả lời (#299) | Docker |
| 8 | Hasura: `hasura-cli metadata apply` thư mục metadata trộn trong container, kiểm bảng được track, trigger có mặt, không có gì không nhất quán; lỗi thì trả tệp chạy và metadata về như trước lần cài này | Metadata Hasura |

Manifest khai `workflow` thì lệnh có 9 bước: ở bước 1, `svc-workflow` kiểm gói quy trình trước mọi thay đổi (BPMN
độc, form sai bị từ chối khi chưa dựng image, chưa tạo schema, client nào); bước "quy trình" đứng ngay sau Keycloak
(bước 6) triển khai gói lên Flowable, các bước sau lùi một số. Chi tiết: 1.10.

Mọi thứ của ứng dụng nằm trong `.moc-apps/` của thư mục chạy (`.gitignore` bỏ qua), tệp của lõi không đổi một byte:

- `apisix.yaml`: [`platform/apisix/apisix.yaml`](../platform/apisix/apisix.yaml) chép **nguyên văn** (kể cả
  `global_rules`, plugin, khối lõi thêm sau này — vd tường lửa WAF), chèn upstream ngay sau `upstreams:` và route
  `GET`/`HEAD` ngay **trước** route bắt mọi đường `app-office`. Ứng dụng khai `events` có thêm route hook
  `POST /su-kien/<tên>` chỉ ở cổng hook 9081 (1.3). Không còn ứng dụng nào thì tệp giống hệt tệp lõi.
  APISIX gắn từng tệp và mỗi giây so `mtime`: lệnh ghi đè **tại chỗ** (cùng inode); lúc đang ghi tệp thiếu dấu
  `#END` nên APISIX giữ cấu hình cũ. APISIX có tự nạp lại tệp mới, nhưng lệnh không dựa vào đó: tệp này đổi thì sau
  bước 7 lệnh khởi động lại `apisix` và chờ cổng trả 200 (tối đa 90 giây), vì nạp lại nóng có lúc làm hỏng bộ nhớ
  của WAF (#299, [`platform/apisix/README.md`](../platform/apisix/README.md) mục WAF, "Hạn chế"). Trong vài giây đó
  cổng không trả lời, mọi trang của Signet cũng vậy; chạy lại lệnh mà không đổi gì thì không khởi động lại.
- `hasura-metadata/`: `db/metadata` chép nguyên văn, thêm một tệp mỗi bảng của ứng dụng (một dòng `!include` cuối
  `tables.yaml`) và khóa `event_triggers` cuối `core_app_events.yaml`. Image `cli-migrations` của Hasura áp lại thư
  mục này mỗi lần khởi động, nên phần của ứng dụng sống qua khởi động lại (thêm qua Metadata API thì mất).
- `docker-compose.apps.yml`: tệp phủ — bind mount của `apisix`, `hasura` trỏ sang hai mục trên (compose gộp
  `volumes` theo đường trong container), `env_file` bí mật header cho `hasura`, service `app-<tên>` (profile `app`,
  chỉ mạng `apps` — tới được APISIX, không tới được dịch vụ lõi nào khác —, không mở cổng, rootfs chỉ đọc,
  `cap_drop: ALL`, `no-new-privileges`, giới hạn bộ nhớ và 1 CPU).
  `make up`, reconciler và mọi lệnh `docker compose` nhận tệp này qua `COMPOSE_FILE` trong `.env`.
- `apps/<tên>.json`: bản ghi đã kiểm (manifest, SQL migration, image) — trạng thái mong muốn.

`moc app sync [--files]` dựng lại các tệp trên từ bản ghi (lõi vừa đổi, tệp bị sửa tay); `make up` gọi trước và sau
khi khởi động, `make install` gọi sau khi chép lõi mới vào thư mục cài.

### 1.3. Sự kiện của lõi

Lõi phát một luồng sự kiện **đã làm sạch** cho ứng dụng: bảng `core.app_events` (migration `1792281603200`) nhận một
dòng cho mỗi `office.document_events` thuộc **danh sách trắng** — `office.document.received`, `.registered`,
`.issued` — của văn bản **không hạn chế** (F3.7: văn bản hạn chế không lộ cả sự tồn tại), đúng 5 cột `id`,
`tenant_id`, `document_id`, `kind`, `occurred_at`: không ghi chú, không số ký hiệu, không người làm.

Mỗi ứng dụng khai `events` có một Hasura Event Trigger `app_<tên>` trên bảng đó: Hasura gọi
`http://apisix:9081/su-kien/<tên>`, kèm header `X-Moc-Hook-Secret` lấy từ biến môi trường của Hasura
(`value_from_env`, giá trị trong `.moc-apps/hasura.env`, không nằm trong metadata). Hasura chỉ ở mạng `moc`, container
ứng dụng chỉ ở `apps`, nên không tới thẳng nhau: 9081 là cổng hook của APISIX — có trong `node_listen`, không publish
ra máy chủ; route hook có `vars: [["server_port", "==", "9081"]]` nên cổng công khai 9080 không khớp (404), đúng một
đường `POST`, `proxy-rewrite` về đúng `http://app-<tên>:<port><path>` của manifest. APISIX không gỡ, không thêm header:
ứng dụng vẫn tự kiểm `X-Moc-Hook-Secret`. Như mọi yêu cầu qua cổng, thân sự kiện đi qua WAF (5 cột, không chữ tự
do). Thân là **thân sự kiện chuẩn** của Hasura, không biến đổi:
`{id, created_at, trigger: {name}, table: {schema: core, name: app_events}, event: {op: INSERT, data: {old: null,
new: {5 cột}}, session_variables: null}, delivery_info}`. `session_variables` là `null` vì hàm chép của lõi xóa người
làm (`hasura.user`) trong lúc ghi `core.app_events`. Mọi loại trong danh sách trắng đều tới mọi ứng dụng nghe sự kiện;
ứng dụng tự bỏ loại không khai — lõi đặt `MOC_APP_EVENT_KINDS` (các `events.kinds`, cách nhau dấu phẩy) cho container.
Webhook lỗi hoặc trả khác 2xx thì Hasura gửi lại theo `retry` (mặc định 5 lần, cách 10 giây): giao **ít nhất một lần**,
ứng dụng chống trùng bằng `event.data.new.id`. Muốn biết thêm (số ký hiệu, trích yếu) thì hỏi GraphQL bằng token của
người dùng — Hasura xét quyền như mọi lần đọc khác.

Đã đo trên Hasura v2.51 thật (bộ thử tích hợp của việc này, chưa có trong CI): giá trị header bí mật không có trong
`hdb_catalog.event_invocation_logs` và không có trong nhật ký container Hasura (`docker logs`) sau các lần giao. Không
dùng `request_transform`: khi trigger có biến đổi, Hasura v2.51 ghi cả yêu cầu gốc, kèm header bí mật, vào nhật ký
container.

### 1.4. Migration và mô hình tin cậy

**Cài một ứng dụng nghĩa là quản trị viên tin mã của ứng dụng đó**, như cài một gói phần mềm: container của ứng dụng
chạy mã của nó trên máy của lõi, mã không bị kiểm. Mạng thì đã tách: container chỉ ở mạng `apps`, tới lõi duy nhất qua
APISIX. Các kiểm dưới đây thu hẹp những gì SQL và manifest của ứng dụng làm được với CSDL và Hasura; chúng không biến
một ứng dụng không đáng tin thành an toàn.

**Vai trò CSDL riêng.** Mỗi ứng dụng có một vai trò PostgreSQL `moc_appdb_<schema>`: không superuser, không
`CREATEDB`, `CREATEROLE`, `BYPASSRLS`, `REPLICATION`, không là thành viên vai trò nào, không mật khẩu, `NOLOGIN` trừ lúc
chạy migration. Nó làm chủ schema của ứng dụng, quyền duy nhất ngoài đó là gọi `moc_app.migration_done` — không quyền
gì trên `core`, `office`, `personal`. Migration chạy bằng `psql -U moc_appdb_<schema>` (socket Unix trong container
`postgres`): **session user là vai trò của ứng dụng**, không phải `SET ROLE` từ superuser, nên `RESET ROLE`, `SET
SESSION AUTHORIZATION` trong SQL động không thoát ra được. SQL gửi dạng base64, giải mã rồi `EXECUTE` trong một giao
dịch (`psql` không diễn giải lệnh `\` nào; `COMMIT` trong đó bị từ chối). Không `REASSIGN OWNED`: đối tượng của ứng
dụng thuộc vai trò của ứng dụng mãi.

**Kiểm trước khi `COMMIT`** (`moc_app.migration_done`, migration `1792281603200`), sai thì cả giao dịch hủy, bước 3 báo
lỗi, không còn lại gì:

- vai trò của ứng dụng không làm chủ gì ngoài schema của nó (cả large object, quyền mặc định toàn cục); trong schema
  không có đối tượng của ai khác;
- biểu thức lưu trong schema — view, rule, `DEFAULT`, `CHECK`, chỉ mục, trigger, policy, domain, toán tử, aggregate —
  chỉ đọc bảng trong schema, chỉ gọi hàm trong schema hoặc hàm có sẵn của PostgreSQL không đọc dữ liệu (đọc thẳng cây
  biểu thức: `pg_depend` không ghi phụ thuộc vào đối tượng có sẵn). Cột tự tăng dùng `generated … as identity`;
- không view `security_invoker`, không `CAST` trên kiểu của ứng dụng;
- hàm, thủ tục của ứng dụng thành `SECURITY DEFINER`: Hasura (nối bằng superuser) gọi tới thì chạy bằng quyền của vai
  trò ứng dụng, không bằng quyền của Hasura.

Đọc hay ghi bảng của lõi, tạo bảng, schema, vai trò chỗ khác, gắn trigger vào bảng của lõi, `ALTER DEFAULT
PRIVILEGES`, `GRANT` cho vai trò khác, `COPY … PROGRAM`, `lo_import`: PostgreSQL chặn hoặc kiểm trên từ chối
(`db/tests/test_app_registry.py`, 32 ca SQL; chạy trên PostgreSQL thật khi `MOC_IT=1`). Migration đã áp mà nội dung đổi:
lệnh từ chối — viết migration mới. Bảng ứng dụng không gắn được trigger `core.audit()` của lõi (vai trò không thấy
`core`); sổ kiểm toán ghi `core.apps`, `core.app_migrations`.

**Ranh giới thật** — cái đã có, cái chưa có:

| Đã có | Chưa có |
|---|---|
| Vai trò CSDL riêng như trên; ứng dụng không có mật khẩu CSDL nào | Các ứng dụng chung một mạng `apps`: tới được nhau, tới cổng hook 9081 (webhook của ứng dụng khác vẫn đòi bí mật header của nó), cổng trạng thái 7085 và chỉ số 9091 của APISIX — không có chính sách mạng riêng cho từng ứng dụng |
| Container chỉ ở mạng `apps` (`internal`, không ra Internet), nơi chỉ có APISIX của lõi: không tới được PostgreSQL, Hasura, Keycloak, svc-files hay dịch vụ lõi nào khác; mọi lời gọi vào lõi qua cổng — kiểm token, giới hạn tốc độ, WAF như trình duyệt (`scripts/tests/test_mang_ung_dung.py`, bước 5 của `make demo-cai-ung-dung`) | Trong cổng, ứng dụng là một client như trình duyệt: gọi được mọi route công khai mà token của nó cho phép |
| Không có khóa quản trị Hasura: giá trị `environment` chép nguyên văn, không nội suy `${…}` từ `.env` của lõi | Mã trong container không bị kiểm: nó làm được mọi thứ một tiến trình ở mạng `apps` làm được |
| Người dùng chỉ đọc bảng ứng dụng theo quyền Hasura khai trong manifest, có lọc đơn vị (1.1); điều kiện trong quyền không đọc được dữ liệu lõi (1.9) | Đúng sai của quyền đó (ngoài các điều lõi kiểm) là việc của người viết manifest — lõi không biết một cột nhạy cảm hay không |
| Phần máy chủ chỉ có vai trò `app_<tên>` (1.5) | `app_<tên>` thêm dòng với `check: {}` thì lõi tin phần máy chủ ghi đúng `tenant_id` |

**Gỡ không xóa dữ liệu**: schema, bảng, các dòng, vai trò CSDL còn nguyên; `core.apps.removed_at` ghi lúc gỡ, đường
của ứng dụng được trả lại. Cài lại thì dữ liệu cũ hiện lại, migration không áp lại.

### 1.5. Danh tính dịch vụ

`service_account: true`: client bí mật `app-<tên>-svc`, chỉ bật client credentials (không luồng trình duyệt, không
luồng mật khẩu), token sống 5 phút, mang claim Hasura cố định: vai trò `app_<tên>` (gạch nối thành gạch dưới), không
đơn vị, người làm `app:<tên>` (sổ kiểm toán ghi tên này). Vai trò `app_<tên>` chỉ có quyền ứng dụng khai cho nó trên
bảng của chính nó — không đọc văn bản, không đọc gì của lõi. Container nhận `MOC_CLIENT_ID`, `MOC_CLIENT_SECRET`,
`MOC_HOOK_SECRET` qua `env_file`; `MOC_KEYCLOAK_INTERNAL_URL`, `MOC_GRAPHQL_INTERNAL_URL` là `http://apisix:9080`,
`http://apisix:9080/v1/graphql` — container chỉ tới được APISIX, nên lấy token ở route `dang-nhap` (giới hạn
`MOC_RATE_LOGIN_PER_MIN` theo IP của container, chung cho mọi lần lấy token của ứng dụng đó) và gọi GraphQL ở route
`graphql` (kiểm token ở biên, `MOC_RATE_API_PER_MIN` mỗi token), cùng WAF như trình duyệt. Mất tệp bí mật thì lần
cài sau sinh bí mật mới và dựng lại client dịch vụ.

### 1.6. Vị trí trong GitOps

Ứng dụng cài bằng manifest là **trạng thái vận hành của từng bản chạy**, như đơn vị hay tài khoản — không phải cấu
hình lõi trong git: bản ghi và bí mật nằm trong `.moc-apps/`, phần đã áp nằm trong CSDL (`core.apps`). Mã của ứng
dụng (`apps/<thư mục>/`) vẫn ở trong git như mọi mã khác; cài hay không là quyết định của từng bản chạy.
Reconciler (`scripts/reconcile.py`) **không** cài, gỡ hay kéo mã ứng dụng nào: mỗi lượt chỉ dựng lại tệp chạy khi
lõi vừa đổi (GitOps áp commit mới) hoặc tệp bị sửa, rồi áp lại phần còn thiếu; container ứng dụng mất thì dựng lại
như mọi dịch vụ khác (tệp phủ nằm trong `COMPOSE_FILE`).

### 1.7. Ví dụ: Bảng tin đơn vị

`apps/bang-tin`: văn bản vừa vào sổ, vừa phát hành trong đơn vị, cập nhật theo sự kiện của lõi. Mở ở
`${MOC_PUBLIC_URL}/bang-tin/`; đã đăng nhập Văn phòng điện tử thì vào thẳng (client `app-bang-tin`, PKCE S256,
`response_mode=fragment`: mã cấp quyền không tới máy chủ nào). Mỗi người chỉ thấy tin của văn bản mình được xem —
quyền đọc `bang_tin.tin` lọc theo `document.visible`, đúng quy tắc `office.document_visible` của lõi.

| Phần | Ở bang-tin |
|---|---|
| Manifest | [`apps/bang-tin/app.yaml`](../apps/bang-tin/app.yaml): `/bang-tin`, cổng 8080 (trang), 8081 (webhook), 96 MiB, `service_account`, nghe `registered`, `issued` |
| Image | Python thư viện chuẩn trên `python:3.13.16-slim` ghim digest (cùng image `svc-files`), không root (10001), bản dựng cho trình duyệt của `oidc-client-ts` lấy từ npm lúc dựng |
| Máy chủ | [`server.py`](../apps/bang-tin/server.py): trang tĩnh, CSP `script-src 'self'`, nhật ký không ghi chuỗi truy vấn; `POST /su-kien` so header bí mật thời gian hằng, đọc thân chuẩn của Hasura (`event.data.new`), bỏ loại không nghe (200), ghi tin bằng token dịch vụ (`insert_bang_tin_tin`), trùng `event_id` là đã ghi, lỗi → 503 để Hasura gửi lại |
| CSDL | `migrations/0001_tin`, chạy bằng vai trò `moc_appdb_bang_tin`: `bang_tin.tin` (`event_id` khóa chính = `core.app_events.id`; không khóa ngoại tới `core`, `office` — vai trò không thấy hai schema đó, và nộp lưu gỡ văn bản khỏi CSDL nghiệp vụ; không trigger `core.audit()` — sự kiện gốc đã ở sổ kiểm toán qua `office.document_events`) |
| Quyền | clerk, staff, manager, director đọc 4 cột, lọc đơn vị và `document.visible`; quan hệ `document` một chiều về `office.documents`; chỉ `app_bang_tin` thêm dòng; không ai sửa, xóa |

```
office.document_events ──trigger──► core.app_events ──Event Trigger──► APISIX :9081 /su-kien/bang-tin
 (lõi ghi khi vào sổ, phát hành)    (danh sách trắng,     (header bí mật,      │ (cổng hook, không publish)
                                     không hạn chế)        thử lại)            ▼
                                                                   app-bang-tin:8081/su-kien  (mạng apps)
                                                                               │ token client credentials qua
                                                                               ▼ APISIX :9080 (app-bang-tin-svc)
trình duyệt ── /bang-tin/ ──► APISIX ──► app-bang-tin:8080       APISIX :9080 /v1/graphql ──► Hasura ── bang_tin.tin
            ── /v1/graphql (token người dùng) ──► Hasura ── bang_tin_tin { document { symbol summary } }
```

Kiểm: `apps/bang-tin/tests` (`node --test` 5, `unittest` 15, trong `make test`); `scripts/tests/test_ung_dung.py`
47, `test_mang_ung_dung.py` 8 (mạng `apps`, cổng hook), `test_yaml_nho.py` 6; `db/tests/test_app_registry.py` 13
hàm (44 ca, PostgreSQL và Hasura thật khi `MOC_IT=1`, job CI `db` có đặt); `make demo-cai-ung-dung` trên hệ thống đang
chạy (bước CI ở phần `luong-chinh` của job `chay-thu`).

### 1.8. Bằng chứng: lõi không đổi

`make demo-cai-ung-dung` (cần `make seed`): `--dry-run` không đổi gì; cài; mở `/bang-tin/` qua APISIX; đăng nhập Văn
phòng điện tử rồi vào Bảng tin không hỏi lại mật khẩu; câu GraphQL của trang chạy trên bảng của ứng dụng; Danh mục ứng
dụng của chuyên viên có Bảng tin, chuyên viên không đọc được băm manifest; văn thư vào sổ một văn bản đến thường và một
văn bản hạn chế → lãnh đạo khoa thấy tin của văn bản thường, văn bản hạn chế không có trong luồng sự kiện; từ trong
container `app-bang-tin` chỉ mở được kết nối tới `apisix:9080` (Keycloak, Hasura, PostgreSQL, svc-files: không),
`POST /su-kien/bang-tin` ở cổng công khai trả 404; cài lại không tạo gì mới (cùng container, `.moc-apps/` không đổi
một byte; băm manifest lãnh đạo khoa thấy = `sha256sum apps/bang-tin/app.yaml`, lúc cài, lúc cập nhật không đổi); gỡ →
route, client, trigger, container mất, dữ liệu còn, tệp chạy APISIX giống hệt tệp lõi, Danh mục ứng dụng: chuyên viên
không còn thấy Bảng tin, lãnh đạo khoa thấy "Đã gỡ"; cuối cùng `git status` trước và sau giống hệt và
`git diff --stat` trống.

### 1.9. Giới hạn và rủi ro

Rủi ro (xem cả bảng ranh giới ở 1.4):

- **Tin mã của ứng dụng.** Mã trong container không bị kiểm. Container chỉ ở mạng `apps` nên chỉ tới được APISIX:
  mọi lời gọi vào lõi qua cùng kiểm token, giới hạn tốc độ, WAF như trình duyệt; dịch vụ lõi tin "đã ở trong mạng
  nội bộ" (mạng `moc`) không thấy ứng dụng. Các ứng dụng vẫn chung một mạng `apps` (tới được nhau, tới cổng hook 9081
  — webhook của ứng dụng khác đòi bí mật header của nó), không có chính sách mạng riêng từng ứng dụng. Chưa có cách
  cài ứng dụng không đáng tin.
- **Quyền thêm của `app_<tên>` có thể là `check: {}`** (như bang-tin): lõi tin phần máy chủ ghi đúng `tenant_id` của
  sự kiện. Phần máy chủ ghi sai đơn vị thì người dùng đơn vị đó thấy dòng sai.
- **Quyền đọc của người dùng là do manifest khai.** Hasura chạy điều kiện trong quyền bằng quyền admin: `_exists`,
  `<quan hệ>_aggregate` hay điều kiện đi qua quan hệ sang `office.documents` đọc được văn bản của mọi đơn vị, kể cả
  văn bản hạn chế — quyền của bảng đích không áp. Nên lõi kiểm cả cây điều kiện của mọi vai trò: có lọc đơn vị (1.1),
  không `_exists`; qua quan hệ sang `core`, `office`, hay quan hệ khóa ngoại một cột (lõi không biết bảng đích) chỉ
  nhận đúng `visible: {_eq: true}` — luật đọc văn bản của lõi, chạy theo phiên người xem; qua quan hệ sang bảng của
  chính ứng dụng thì kiểm tiếp. Ngoài các điều đó, cột nào nhạy cảm, ai đọc dòng nào là việc của người viết manifest.
- **Mọi ứng dụng nghe sự kiện nhận mọi loại trong danh sách trắng**, không chỉ loại mình khai (Hasura không lọc trigger
  theo giá trị cột): 5 cột đã làm sạch của mọi văn bản không hạn chế trong mọi đơn vị.
- **Văn bản bật hạn chế sau khi đã phát sự kiện**: dòng đã gửi không thu hồi được (người dùng vẫn không đọc được tin
  đó vì quyền lọc theo `document.visible`).
- **Tệp chạy là bản chép**: lõi đổi `platform/apisix/apisix.yaml` hay `db/metadata` mà chưa chạy `moc app sync`
  (`make up`, reconciler, `make install` gọi sẵn) thì `.moc-apps/` vẫn chạy bản cũ của tệp lõi.
- **Băm thư mục ứng dụng gồm mọi tệp** (cả README, tests): sửa một tệp không thuộc image cũng dựng image mới.
- **Kiểm migration đọc cây biểu thức** của PostgreSQL 16 (`:funcid`, `:relid`…): đổi bản PostgreSQL lớn thì chạy lại
  `db/tests/test_app_registry.py` trước.

Giới hạn:

- Một ứng dụng một container, một trang dưới một đường; không có route API riêng qua APISIX — API của ứng dụng là
  GraphQL trên bảng của nó và các đường có sẵn của lõi (`/v1/graphql`, `/api/files`, `/api/workflow/<tên>/…` khi
  khai `workflow` — 1.10).
- Không có Action, remote schema, cron trigger cho ứng dụng; không quan hệ từ bảng của lõi sang bảng ứng dụng.
- Danh sách sự kiện cố định ở lõi (3 loại văn bản); thêm loại là sửa migration của lõi. Không phải trục streaming:
  không đọc lại từ một vị trí, không nhóm người nghe, không bảo đảm thứ tự; mỗi ứng dụng một webhook.
- Migration chỉ đi lên; gỡ không xóa schema, vai trò CSDL. Đổi schema của ứng dụng đã cài: không được. Hàm của ứng dụng
  luôn là `SECURITY DEFINER` của vai trò ứng dụng; bảng ứng dụng không gắn được trigger sổ kiểm toán của lõi.
- `.moc-apps/` chứa bí mật và bản ghi, không vào `moc backup`: chép cùng `.env` khi chuyển máy (CSDL có `core.apps`
  và dữ liệu nhưng không có SQL migration, bí mật). `moc backup` ghi tên vai trò `moc_appdb_*` vào manifest và tạo lại
  chúng trước khi khôi phục sang máy mới.
- Bước 7 tạo lại `apisix`, `hasura` ở lần cài đầu (bind mount mới) và khi bí mật header đổi: cổng gián đoạn vài
  giây, Hasura khoảng 15 giây.
- Chưa có giao diện quản trị: cài, gỡ chỉ bằng dòng lệnh; trang Danh mục ứng dụng (`/ung-dung`) chỉ để xem, không
  dò sức khỏe container của ứng dụng. Không gian cá nhân (`apps/ca-nhan`) chưa chuyển sang manifest: vẫn là
  một phần của lõi, cắm theo cách làm tay (mục 3).
- Với Keycloak, Hasura, APISIX thật, lệnh chỉ được kiểm bằng màn `make demo-cai-ung-dung` (bước CI ở phần
  `luong-chinh` của job `chay-thu`); test trong `scripts/tests` không gọi dịch vụ thật.

### 1.10. Quy trình của ứng dụng (`workflow`, #301)

Ứng dụng mang quy trình nghiệp vụ của riêng nó (BPMN) và form (JSON Schema) mà không cần máy chủ nghiệp vụ, không cần
bảng: lõi triển khai quy trình lên chính Flowable của `svc-workflow`, kiểm dữ liệu form, giao việc theo đơn vị và
phòng, rồi mở một API chung cho trang của ứng dụng. Ứng dụng mẫu: Đơn nghỉ phép (`apps/nghi-phep`, mục 7).

```yaml
workflow:
  processes: [workflow/don-nghi-phep.bpmn20.xml]      # đường tương đối với app.yaml
  forms:
    nghi-phep.don: forms/don.json                      # formKey → JSON Schema 2020-12
    nghi-phep.duyet: forms/duyet.json
```

**Cài, cài lại, gỡ.** `moc app install` gói các tệp khai (nội dung lưu cả trong bản ghi `.moc-apps/apps/<tên>.json`,
nên `moc app sync` và hoàn tác dựng lại được gói dù thư mục nguồn đổi) thành zip, đưa qua stdin cho lệnh chạy trong
container `svc-workflow`:

```bash
docker compose exec -T svc-workflow python -m svc_workflow.apps.deploy check|install <tên>   # stdin: zip base64
docker compose exec -T svc-workflow python -m svc_workflow.apps.deploy remove <tên>
```

Lệnh lấy thông tin đăng nhập Flowable đúng như lúc dịch vụ khởi động (`Settings.from_env(with_secrets(…))`: mật khẩu
`rest-admin` trong két OpenBao, đọc bằng AppRole của `svc-workflow`), không qua dòng lệnh hay biến môi trường của người
chạy. Gói hợp lệ thành **một** deployment tên `app/<tên>@<12 ký tự đầu SHA-256 nội dung>`, tài nguyên đặt tên theo
khóa: `<processKey>.bpmn20.xml`, `<formKey>.json` và mục lục `moc-app.json`. Deployment mới nhất của ứng dụng đã cùng
tên thì không triển khai lại — cài lại không đổi gì không thêm phiên bản định nghĩa quy trình nào. Gói khác thì thành
phiên bản mới: đơn bắt đầu sau đó theo bản mới; đơn đang chạy đi tiếp theo BPMN cũ, việc của nó kiểm theo form của
chính deployment cũ. Bước Hasura lỗi thì hoàn tác cả quy trình: cài lại gói của lần cài trước, chưa có thì tạm dừng.

`moc app remove` (và manifest bỏ mục `workflow`) **tạm dừng** (suspend) mọi định nghĩa quy trình có khóa `<tên>.…`
cùng các phiên đang chạy — không xóa deployment: lịch sử đơn (`act_hi_*`), biến, đơn đang dở còn nguyên trong Flowable,
như schema CSDL của ứng dụng gỡ không bị xóa. API coi ứng dụng là đã gỡ (`404 app_not_installed`) khi không định nghĩa
nào của deployment mới nhất còn chạy. Cài lại thì bật lại, đơn đang dở làm tiếp.

**Kiểm BPMN theo danh sách trắng** (`svc_workflow/apps/bpmn.py`). BPMN của ứng dụng chạy trong cùng động cơ với quy
trình Văn phòng điện tử và bằng quyền của động cơ: `scriptTask` chạy mã, `serviceTask` gọi lớp Java hay bean, listener
chạy khi qua một bước, biểu thức `${…}` (JUEL) gọi được phương thức của mọi đối tượng trong ngữ cảnh (đọc, sửa quy
trình của đơn vị khác). Flowable còn tính biểu thức ở tên việc, `documentation`, `formKey`, hạn, người được giao. Nên
chỉ nhận đúng những gì một quy trình duyệt cần; mọi thứ khác bị từ chối, lời báo tiếng Việt kèm tệp, dòng, phần tử:

| Phần | Nhận | Không nhận |
|---|---|---|
| Phần tử | `definitions`, `process` (đúng một mỗi tệp), `startEvent` (đúng một), `endEvent`, `userTask`, `exclusiveGateway`, `parallelGateway`, `sequenceFlow`, `conditionExpression`, `documentation`; sơ đồ BPMN DI (`bpmndi`, `dc`, `di` theo namespace, tiền tố gì cũng được) | `scriptTask`, `serviceTask`, `sendTask`, `receiveTask`, `businessRuleTask`, `callActivity`, `subProcess`, `boundaryEvent`, timer, message, signal, `extensionElements`, listener, mọi phần tử của namespace khác |
| Thuộc tính | Chỉ các thuộc tính liệt kê cho từng phần tử, giá trị theo mẫu hẹp (id, số, chữ không có `${`/`#{`) | `flowable:class`, `expression`, `delegateExpression`, `resultVariable`, `skipExpression`… và mọi thuộc tính `activiti:` |
| Điều kiện | `${bien == 'chuoi'}`, `!=`, nối bằng `&&` hoặc `||`; biến là trường **bắt buộc** của một form trong manifest | Gọi hàm, thuộc tính, ngoặc, số, `#{…}` |
| Ai làm việc | `flowable:candidateGroups` chỉ `t:${tenantId}:<vai trò>` hoặc `t:${tenantId}:d:${departmentId}:<vai trò>` (vai trò của realm: `clerk`, `staff`, `manager`, `director`, `tenant_admin`), cách nhau bằng dấu phẩy; `flowable:assignee` chỉ `${initiator}` | Nhóm, người cố định hay tính bằng biểu thức khác |
| Form, hạn | `flowable:formKey` bắt buộc ở sự kiện bắt đầu và mọi `userTask`, dạng `<tên>.<khóa>`, có trong `workflow.forms`; `flowable:dueDate` chỉ khoảng ISO 8601 viết sẵn (`P3D`, `PT24H`); `flowable:initiator` chỉ `initiator` | — |
| Tệp | UTF-8, tối đa 512 KB | `<!DOCTYPE`, `<!ENTITY` (thực thể ngoài đọc được tệp của máy chủ, thực thể lồng làm nổ bộ nhớ), chỉ thị xử lý `<?…?>` |

Process id (= `processKey`) phải dạng `<tên>.<khóa>`: ứng dụng không chạm được quy trình Văn phòng điện tử hay của ứng
dụng khác. Process id tối đa 22 ký tự: Flowable đặt id định nghĩa `<khóa>:<phiên bản>:<uuid>`, chuỗi đó quá 64 ký tự
thì id chỉ còn uuid, lõi không còn biết việc thuộc ứng dụng nào (22 ký tự vừa tới phiên bản 9999). Gói còn bị từ chối
khi hai tệp cùng process id, khi có tệp không khai.

**Kiểm form** (`svc_workflow/apps/forms.py`). Lúc cài, form phải là JSON Schema 2020-12 hợp lệ, `type: object`,
`additionalProperties: false` (mọi biến ghi vào quy trình đều được khai); tên trường dạng camelCase (là tên biến
Flowable), không trùng biến hệ thống `tenantId`, `departmentId`, `initiator`; mỗi trường một giá trị đơn (chuỗi, số,
đúng/sai — biến Flowable không chứa đối tượng, mảng); `format` chỉ `date`, `uuid`; `$ref` chỉ trỏ trong chính tệp, dạng
JSON Pointer (`#/…`), tới đúng một schema, không vòng; `x-moc-range` là các cặp hai trường `format: date`; tối đa 256
KB; không dùng `patternProperties`, `propertyNames` (mẫu chạy trên mọi khóa gửi lên, kể cả khóa thừa). `pattern` chạy
bằng `re` của Python, quay lui, ngay trong vòng sự kiện của svc-workflow: mẫu quay lui bùng nổ (ReDoS, vd `^(a+)+$`) với
vài chục ký tự làm đứng cả dịch vụ, kể cả Action của Văn phòng điện tử. Nên lúc cài không nhận mẫu lặp lồng trong lặp
(trừ lặp đúng n lần như `(,[0-9]{3})*`), có `|` hay tham chiếu ngược (`\1`) trong phần lặp, dài quá 512 ký tự. Phần lặp
nối nhau vẫn tốn thời gian đa thức, và jsonschema kiểm bằng `re.search`: mẫu không neo `^` thử lại ở mọi vị trí, `a+$`
đã tốn bình phương độ dài chuỗi. Lõi ước lượng số bước quay lui: tích (cận trên − cận dưới + 1) của các phần lặp không
cố định và số nhánh của mỗi `|`, nhân độ dài chuỗi L cho mỗi phần lặp không chặn trên (`+`, `*`, `{n,}`) và thêm L nếu
không neo `^`; quá 10^7 bước (khoảng 30 ms) thì không nhận, mọi `pattern` của một form cộng lại quá 3·10^7 bước cũng
không nhận, mẫu ở `$defs` tính một lần cho mỗi chỗ `$ref` trỏ tới (#323). Khi số bước tăng theo L, `pattern` phải có
`maxLength` ngay cạnh (cùng một schema) làm L; lúc nhận dữ liệu, chuỗi dài quá `maxLength` đó không chạy `pattern` (chỉ
báo `maxLength`). Mẫu không có chỗ quay lui (lớp ký tự cấm, `^20[0-9]{2}-`) hay neo `^` với phần lặp có chặn
(`^[A-Z]{2,5}$`, `^[^@\s]{1,64}@[^@\s]{1,63}\.[a-z]{2,10}$`) không cần `maxLength`; `^\S.*$` cần. Lúc nhận dữ liệu, giá
trị mảng hay đối tượng báo `type` ngay mà không chạy schema (không ghi được thành biến); còn lại lõi kiểm bằng đúng
`schemas.FormSchema` của form tiếp nhận văn bản đến (mã lỗi như [`schemas/README.md`](../schemas/README.md)) cộng
`x-moc-range` (trường sau trước trường trước → mã `x-moc-range` ở trường sau; kiểm sau cùng, bỏ qua khi một trong hai
trường đã có lỗi). Chỉ trường đã khai, có mặt và khác `null` được ghi thành biến, giữ kiểu (chuỗi, long, double,
boolean).

**API** (route APISIX `svc-workflow`: `/api/workflow/*`, `GET`/`POST`, cùng kiểm token, giới hạn tốc độ như
`/api/files`; bảng đủ ở [`docs/api/README.md`](api/README.md)):

| Yêu cầu | Trả |
|---|---|
| `GET /api/workflow/<tên>/forms/<formKey>` | `200`: JSON Schema của form, đúng tệp manifest khai (bản mới nhất) |
| `POST /api/workflow/<tên>/processes/<processKey>` `{"data": {…}}` | `201 {"id"}`; kiểm theo form của sự kiện bắt đầu; lõi tự đặt `tenantId`, `departmentId` (rỗng nếu người gửi không thuộc phòng nào), `initiator` từ token |
| `GET /api/workflow/<tên>/processes` | Đơn người này đã gửi, mới nhất trước: `[{id, processKey, startedAt, endedAt, data}]` — `data` gồm dữ liệu đơn và dữ liệu các bước đã xong (vd `quyetDinh`, `ghiChu`) |
| `GET /api/workflow/<tên>/tasks` | Việc của ứng dụng giao cho người này (`assignee`) hoặc cho một nhóm của người này, cùng đơn vị, cũ nhất trước: `[{id, name, formKey, processKey, processId, createdAt, dueAt, data}]` |
| `POST /api/workflow/<tên>/tasks/<taskId>` `{"data": {…}}` | `204`: kiểm theo form của việc, nhận việc rồi hoàn thành |

Thân yêu cầu tối đa 64 KB, lớn hơn → `413 too_large` (#323). Lỗi kiểm dữ liệu: `422 {"errors": {trường: mã}}` (gửi tên
biến hệ thống → `additionalProperties`). Lỗi khác dạng `{"detail": {"code", "message"}}` như `svc-files`: `401` thiếu,
sai, hết hạn token; `403` token không phải của client `app-<tên>` (`azp` — token của Văn phòng điện tử, `moc-cli` hay
của ứng dụng khác không dùng được) hoặc tài khoản chưa gán đơn vị; `404` ứng dụng chưa cài hoặc đã gỡ, form, quy trình,
việc không có hoặc không thuộc ứng dụng, đơn vị, người này (không nói việc của người khác có tồn tại); `409` việc vừa có
người khác nhận; `503` chưa gọi được Flowable hoặc Keycloak. APISIX kiểm chữ ký, hạn của token ở biên; `svc-workflow`
kiểm lại theo JWKS của realm (`iss` là URL công khai của realm như `x-oidc` trong `docker-compose.yml`), thêm `azp`.

Nhóm của người dùng lấy từ claim của token: `t:<đơn vị>:<vai trò>` và, khi có phòng, `t:<đơn vị>:d:<phòng>:<vai trò>`
— bao trùm nhóm Văn phòng điện tử dùng. Hộp việc Văn phòng điện tử chỉ nhận việc của quy trình `van-ban-den`,
`van-ban-di` (form của ứng dụng có khai trường tên `documentId` cũng không lẫn vào), và không hoàn thành được việc của
ứng dụng; API của ứng dụng chỉ thấy việc có khóa quy trình `<tên>.…`.

Kiểm không cần hệ thống chạy: svc-workflow `test_app_forms.py` (gồm mọi ca của `apps/*/forms/*.cases.json`, dùng chung
với form trên trình duyệt), `test_app_bpmn.py` (các ca BPMN độc), `test_app_deploy.py` (gói, triển khai, cài lại, gỡ,
lệnh trong container với Flowable giả), `test_app_api.py` (token RSA thật, Flowable giả), `test_app_core.py` (hộp việc
Văn phòng không lẫn việc ứng dụng; các lệnh REST mới); scripts `test_ung_dung_quy_trinh.py`. Trên hệ thống thật:
`make demo-quy-trinh` (mục 7).

Giới hạn:

- Chỉ quy trình duyệt: không timer, không nhắc hạn (hạn chỉ hiện ở `dueAt`), không bước tự động, không gửi thư hay gọi
  API ra ngoài, không quy trình con. Điều kiện chỉ so chuỗi bằng, khác.
- Form không có tệp đính kèm, không trường nhiều giá trị.
- Đơn vị tách bằng biến `tenantId` và nhóm ứng viên `t:<đơn vị>:…` như quy trình Văn phòng điện tử, không dùng tenant
  của Flowable.
- "Đơn của tôi" đọc lịch sử theo các `processKey` trong bản cài mới nhất; mỗi truy vấn tối đa 500 dòng, chưa phân trang.
- Gỡ không xóa gì khỏi Flowable; chưa có lệnh dọn lịch sử quy trình của ứng dụng đã gỡ.
- API không trả tên người gửi đơn (chỉ dữ liệu form); không hủy được đơn đã gửi.

## 2. Ứng dụng nhận gì từ lõi

| Việc | Lõi làm sẵn | Ứng dụng chỉ cần |
|---|---|---|
| Đăng nhập | SSO và TOTP của Keycloak; một phiên cho mọi ứng dụng | Một client công khai, Authorization Code + PKCE |
| Danh tính, đơn vị, vai trò | Token mang claim `https://hasura.io/jwt/claims` (người dùng, đơn vị, phòng, vai trò) | Giữ 5 mapper của client mẫu |
| Cổng | Cửa duy nhất ra ngoài, kiểm JWT ở biên, giới hạn tốc độ, `X-Request-Id` | Một route tới trang tĩnh của ứng dụng |
| Dữ liệu và quyền | GraphQL tự sinh, quyền theo vai trò và đơn vị đến từng dòng | Bảng trong schema riêng, khai quyền trong metadata |
| Tệp | `POST /api/files`: ClamAV quét, sạch mới vào kho; `GET /api/files/{id}`: tải về nếu được xem | Gọi đúng hai đường đó |
| Sổ kiểm toán | Trigger `core.audit()` ghi chuỗi băm, neo ra kho lạnh, `moc audit verify` kiểm lại | Gắn trigger vào bảng của mình (cách làm tay; ứng dụng cài bằng manifest thì không — 1.4) |
| Quy trình | Flowable của `svc-workflow`: triển khai BPMN đã kiểm, kiểm form, giao việc theo đơn vị, phòng, vai trò, API `/api/workflow/<tên>/…` (1.10) | BPMN và form JSON Schema khai ở `workflow` của manifest |
| Vận hành | Sao lưu và khôi phục cả CSDL, reconciler GitOps dựng lại container theo compose | Một service trong profile `app` |

## 3. Làm tay (tham chiếu)

Cách đã dùng cho Không gian cá nhân: ứng dụng thành một phần của lõi — sửa cấu hình lõi, thêm migration và
metadata vào `db/`. Cách một lệnh ở mục 1 làm đúng các việc này nhưng ghi ra `.moc-apps/` thay vì sửa tệp lõi.


| # | Tệp | Làm gì |
|---|---|---|
| 1 | `platform/keycloak/realm/moc-realm.json` | Chép client `app-office`, đổi `clientId`, `name`, `baseUrl`; `redirectUris` và `post.logout.redirect.uris` chỉ dưới đường của ứng dụng (`${MOC_PUBLIC_URL}/<đường>/*`). Giữ `publicClient`, `pkce.code.challenge.method: S256`, không bật luồng mật khẩu, tài khoản dịch vụ; giữ nguyên `protocolMappers` |
| 2 | `platform/apisix/apisix.yaml` | Một `upstream` tới `<service>:8080`, một route `uris: ["/<đường>", "/<đường>/*"]`, `methods: [GET, HEAD]`, đặt **trước** route bắt mọi đường của `app-office`. Trang tĩnh không cần token; API của ứng dụng đi qua các route có sẵn (`/v1/graphql`, `/api/files`), đã kiểm token |
| 3 | `docker-compose.yml` | Service `<<: *common`, `build: ./apps/<thư mục>` **trên một dòng** (`make install` thay dòng đó bằng `pull_policy: never`), `image: moc/<service>:${MOC_VERSION:-dev}`, `profiles: [app]`, `networks: [apps]` (ghi đè mạng `moc` của `x-common`: container chỉ tới được APISIX; `test_mang_ung_dung.py` liệt kê đúng các service ở mạng này, thêm service mới vào đó). Reconciler và `make up` tự nhận service mới |
| 4 | `apps/<thư mục>/` | Image ghim theo digest, chạy không quyền root, có `HEALTHCHECK`; CSP chặn mã nội tuyến; nhật ký truy cập không ghi chuỗi truy vấn (khối `log_format moc_khong_truy_van`, [`platform/apisix/README.md`](../platform/apisix/README.md)) |
| 5 | `db/migrations/default/<phiên bản>_<tên>/` | `create schema <tên>`; mọi bảng có `tenant_id`; khóa ngoại kèm thuê ước tới bảng của `core`; ràng buộc trong CSDL; trigger `core.audit('<cột khóa>')`. Không sửa gì trong `core`, `office` ([`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §0) |
| 6 | `db/metadata/databases/default/tables/<schema>_<bảng>.yaml`, một dòng `!include` trong `tables.yaml` | Quyền theo vai trò: `set` thuê ước, chủ từ phiên; `filter` theo `X-Hasura-Tenant-Id` và `X-Hasura-User-Id`; chỉ cấp cột cần sửa; không cấp `delete`. Quan hệ chỉ một chiều, từ bảng của ứng dụng về `core` — không thêm quan hệ vào metadata của lõi |
| 7 | Bản cài đang chạy | Realm chỉ nạp từ tệp ở lần khởi động đầu: `python3 scripts/moc.py realm clients` thêm client ứng dụng còn thiếu (`--dry-run` để xem trước; `make seed` cũng gọi). Migration và metadata Hasura tự áp khi khởi động lại |
| 8 | Kiểm thử, tài liệu | Test đơn vị trong `apps/<thư mục>/tests` (thêm vào `make test`), test quyền trong `db/tests/`, màn demo đi qua cổng, kịch bản `tests/e2e/`; sinh lại `docs/api/` (`make api-docs`: schema GraphQL theo vai trò đổi); phạm vi commit mới trong `scripts/check_pr.py` và [`git_flow.md`](git_flow.md) §3.3; `DEPENDENCIES.md`, `CHANGELOG.md` |

Gọi lõi từ ứng dụng trên trình duyệt (cùng gốc với cổng, nên không cần CORS):

```js
// token: access token của client ứng dụng (oidc-client-ts, PKCE)
await fetch('/v1/graphql', { method: 'POST', headers: { Authorization: `Bearer ${token}`,
  'Content-Type': 'application/json' }, body: JSON.stringify({ query, variables }) })
const form = new FormData(); form.append('file', file)            // ClamAV quét trước khi lưu
const stored = await (await fetch('/api/files', { method: 'POST', headers: { Authorization: `Bearer ${token}` },
  body: form })).json()                                              // 201 {id, filename, sha256, …}; 422 infected
await fetch(`/api/files/${stored.id}`, { headers: { Authorization: `Bearer ${token}` } })   // 404 nếu không được xem
```

## 4. Ví dụ làm tay: Không gian cá nhân P.A.R.A

Mỗi người một chỗ cất tệp của riêng mình, xếp theo bốn thư mục của phương pháp P.A.R.A: **Dự án** (việc đang làm,
có hạn), **Lĩnh vực** (trách nhiệm lâu dài), **Tài nguyên** (tư liệu tham khảo), **Lưu trữ** (đã xong, giữ lại). Mở
ở `${MOC_PUBLIC_URL}/ca-nhan/`; đã đăng nhập Văn phòng điện tử thì vào thẳng, không nhập lại mật khẩu. Tải tệp lên
vào thư mục đang mở, chuyển tệp giữa các thư mục, tải về. Clerk, staff, manager, director đều có không gian;
`tenant_admin` thì không (vai trò này không đọc `core.files`).

| Bước | Ở ca-nhan |
|---|---|
| 1 | Client `app-ca-nhan`: `baseUrl` `/ca-nhan/`, chuyển hướng `${MOC_PUBLIC_URL}/ca-nhan/*`, cùng 5 mapper với `app-office` |
| 2 | Upstream và route `app-ca-nhan`: `/ca-nhan`, `/ca-nhan/*`, chỉ `GET`, `HEAD`, không plugin |
| 3 | Service `app-ca-nhan` trong profile `app` |
| 4 | `apps/ca-nhan/`: trang tĩnh JavaScript thuần (không bước biên dịch), phục vụ bằng `nginx-unprivileged` cùng image với app-office; thư viện duy nhất là bản dựng cho trình duyệt của `oidc-client-ts` (cùng phiên bản app-office dùng), lấy từ npm lúc dựng image |
| 5 | Migration `1792281602500_personal_space`: schema `personal`, bảng `personal.items` (`file_id`, `tenant_id`, `owner_id`, `para`, mốc thời gian); trigger `items_guard`; `core.audit('file_id')` |
| 6 | `personal_items.yaml`: clerk, staff, manager, director thêm (`file_id`, `para`), đọc, đổi `para` mục của mình; không ai xóa; quan hệ `file` về `core.files` |
| 7 | `moc realm clients` thêm `app-ca-nhan` vào bản cài dựng trước khi có ứng dụng |
| 8 | `apps/ca-nhan/tests` (13 test, `node --test`), `db/tests/test_ca_nhan.py` (11 test), `make demo-ca-nhan`, `tests/e2e/ca-nhan.spec.ts`, phạm vi commit `ca-nhan` |

Một lần tải lên đi qua những gì lõi đã có:

```
trình duyệt ── POST /api/files ──► APISIX (kiểm JWT) ──► svc-files ── ClamAV ── SeaweedFS
                                                              └── core.files (created_by = sub)
            ── insert_personal_items_one ──► APISIX ──► Hasura (set tenant_id, owner_id từ token)
                                                              └── personal.items ── items_guard ── core.audit()
```

`items_guard` chỉ cho xếp tệp chính người dùng tải lên, cùng đơn vị, không mã hóa (tệp mã hóa thuộc văn bản hạn
chế, đi theo quyền đọc văn bản — F3.7), kể cả khi ghi thẳng CSDL. Tên tệp và mọi chữ trên trang gán bằng
`textContent`; CSP `script-src 'self'`; token giữ trong `sessionStorage` của tab. Người khác cùng đơn vị không thấy
mục, tải về nhận `404`, không xếp được tệp của người khác vào không gian của mình. Sổ kiểm toán ghi mỗi lần xếp,
chuyển; `overview` chỉ giữ `file_id`, lãnh đạo xem sổ không thấy tên thư mục.

Kích thước (đếm dòng, gồm header giấy phép): mã giao diện `public/*.js` 566 dòng, `index.html` 91, `style.css` 117;
nginx và Dockerfile 122; migration 96, metadata 71.

Kiểm trên hệ thống đang chạy: `make demo-ca-nhan` — trang và CSP; đăng nhập Văn phòng điện tử rồi vào Không gian cá
nhân không hỏi lại mật khẩu, token `azp` `app-ca-nhan` mang đủ claim Hasura, PKCE bắt buộc, `redirect_uri` ngoài
`/ca-nhan/` bị từ chối; tải lên, xếp vào Dự án, chuyển sang Lưu trữ, tải về đúng từng byte; tệp EICAR bị chặn;
người khác không với tới; hai dòng sổ kiểm toán.

## 5. Bằng chứng: lõi không đổi khi thêm Không gian cá nhân

Lệnh, chạy ở gốc repo trên nhánh của thay đổi này:

```bash
git diff --stat origin/develop...HEAD -- services/
```

Không in dòng nào. Bản vá được dựng trên commit `34286d7` (develop `1d89f55` cộng các bản vá chưa gộp lúc đó);
`git diff --stat 34286d7 -- services/` cũng không in dòng nào. Cùng lệnh với `apps/office/`, các migration có từ
trước, `db/metadata/databases/default/tables/core_*.yaml`, `office_*.yaml`, `actions.*` cũng trống.

Ngoài `apps/ca-nhan/`, thay đổi chỉ là cấu hình (realm, route, service compose), phần thêm của CSDL (một migration
mới, một tệp metadata mới, một dòng `!include`), công cụ vận hành (`scripts/realm_clients.py`, hai hàm
`clients`, `create_client` của `tenants.Keycloak`, lệnh `moc realm clients`, `make seed` gọi lệnh đó, màn
`scripts/demo_ca_nhan.py`), test và tài liệu.

## 6. Giới hạn của Không gian cá nhân

- **Không xóa tệp.** Lõi không có API xóa tệp, và nguyên tắc dữ liệu là không xóa: tệp không dùng nữa thì chuyển
  sang Lưu trữ.
- Quản trị đơn vị (`tenant_admin`) không có không gian cá nhân.
- Chỉ xếp được tệp tải lên qua Không gian cá nhân hoặc tệp không mã hóa do chính mình tải lên ở Văn phòng điện tử;
  tệp chuyển sang kho lạnh theo hồ sơ nộp lưu thì chưa kiểm việc tải về từ đây.
- Chưa có hạn mức dung lượng cho mỗi người; cỡ tệp tối đa theo `svc-files`.
- Đường dưới `/ca-nhan/` không có tệp thì trả trang chính (ứng dụng một trang).
- Đặt `MOC_OIDC_AUDIENCE` cho `svc-files` thì client mới cũng phải có mapper audience tương ứng.
- Giao diện chỉ tiếng Việt.

## 7. Ứng dụng mẫu có quy trình riêng: Đơn nghỉ phép

`apps/nghi-phep` (#301) là ứng dụng thứ tư, dựng để cho thấy một ứng dụng mang quy trình nghiệp vụ của riêng nó mà
không có máy chủ nghiệp vụ, không có bảng nào: nhân viên gửi đơn nghỉ phép, trưởng phòng **của chính phòng người gửi**
duyệt hoặc từ chối kèm ghi chú, người gửi theo dõi kết quả. Mục này chỉ tả ứng dụng; cách lõi nhận mục `workflow` của
manifest, kiểm BPMN và mở API chung là phần lõi của #301 trong tài liệu này. Ứng dụng chỉ chạy khi lõi đã có phần đó.

| Phần | Ở nghi-phep |
|---|---|
| Manifest | [`apps/nghi-phep/app.yaml`](../apps/nghi-phep/app.yaml): `/nghi-phep`, cổng 8080, 64 MiB; `database` chỉ vì manifest bắt buộc (schema trống `nghi_phep`, không migration); `workflow`: một quy trình, hai form |
| Quy trình | [`workflow/don-nghi-phep.bpmn20.xml`](../apps/nghi-phep/workflow/don-nghi-phep.bpmn20.xml), id `nghi-phep.don`: gửi đơn → "Trưởng phòng duyệt" (nhóm `t:${tenantId}:d:${departmentId}:manager`, như bước duyệt cấp phòng của văn bản đi) → cổng rẽ theo `quyetDinh` → "Đã duyệt" / "Bị từ chối". Chỉ sự kiện, việc người làm, cổng rẽ; có sơ đồ BPMN DI |
| Form | `forms/don.json` (loại nghỉ, từ ngày, đến ngày, lý do) và `forms/duyet.json` (quyết định, ghi chú): JSON Schema, kiểm ở trình duyệt bằng `public/schema-form.js` và ở lõi khi nhận |
| Image | Python thư viện chuẩn trên `python:3.13.16-slim` ghim digest (như Bảng tin), không root (10001), chỉ trang tĩnh; bản dựng cho trình duyệt của `oidc-client-ts` lấy từ npm lúc dựng |
| Trang | Đăng nhập Authorization Code + PKCE (client `app-nghi-phep`, `response_mode=fragment`). Ba phần: Gửi đơn; Đơn của tôi (trạng thái, nội dung, quyết định); Việc cần duyệt (chỉ hiện khi có việc, tự làm mới mỗi 30 giây). Lỗi `422` của lõi hiện dưới đúng ô |

Trang gọi `/api/workflow/nghi-phep/…` bằng token của người dùng: lấy form, gửi đơn, xem đơn của mình, xem và làm việc
duyệt của mình. Ai thấy việc nào, dữ liệu có hợp form không, đơn lưu ở đâu là việc của lõi; trang không quyết định
điều gì trong số đó. Chi tiết trang, bảng API: [`apps/nghi-phep/README.md`](../apps/nghi-phep/README.md).

Kiểm không cần hệ thống chạy (trong `make test`): `apps/nghi-phep/tests` — `node --test` (form dựng từ schema; đường
API, đọc câu trả lời, trạng thái đơn; khóa trong app.yaml, BPMN, form khớp nhau; tỉ lệ tương phản màu) và `unittest`
(máy chủ trang trên cổng ngẫu nhiên; BPMN chỉ dùng phần tử được phép, mọi nút tới được kết thúc);
`scripts/tests/test_nghi_phep.py` cho phần thuần của kịch bản dưới đây.

Kiểm trên hệ thống đang chạy: `make demo-quy-trinh` (cần `make seed`), bước CI "Quy trình của ứng dụng qua lõi (make
demo-quy-trinh)" ở phần `luong-chinh` của job `chay-thu`, ngay sau bước của Bảng tin. Kịch bản dùng ba tài khoản mẫu
cùng đơn vị Khoa CNTT: chuyên viên `giangvienktpm` và trưởng bộ môn `truongbmktpm` cùng Bộ môn KTPM, tổ trưởng
`totruongdt` ở phòng Đào tạo — để cùng một quy trình cho thấy việc duyệt tới đúng phòng và không tới phòng khác:

1. Bản sao của ứng dụng với BPMN có thêm một `scriptTask` bị từ chối lúc cài, không đổi gì trên hệ thống.
2. Cài; trang `/nghi-phep/` qua APISIX có CSP, `config.json` mang client `app-nghi-phep`.
3. Chuyên viên đăng nhập Văn phòng điện tử rồi vào ứng dụng không hỏi lại mật khẩu; form lõi trả về khớp
   `forms/*.json`.
4. Đơn sai (đến ngày trước từ ngày, loại nghỉ ngoài danh sách) → `422` đúng mã ở đúng ô; đơn đúng → `201`, nằm ở
   "Đơn của tôi" với trạng thái chờ duyệt.
5. Trưởng bộ môn cùng phòng thấy việc duyệt; tổ trưởng phòng khác và chính người gửi không thấy, không làm được.
6. Token của `app-office`, `moc-cli` bị từ chối (`403`); hộp việc của Văn phòng điện tử không lẫn việc nghỉ phép.
7. Quyết định ngoài danh sách → `422`; "Đồng ý" → `204`, quy trình kết thúc với `quyetDinh = dong-y`.
8. Cài lại không đổi gì (cùng container, cùng trạng thái trong `.moc-apps/`, không thêm phiên bản quy trình).
9. Gỡ: trang, container, client mất; API của ứng dụng thôi trả `200`; lịch sử đơn còn trong động cơ quy trình.
10. `git status` trước và sau giống hệt.

Giới hạn của ứng dụng mẫu: việc duyệt chỉ có nội dung đơn, không có tên người gửi (API chung không trả); giao diện
chỉ tiếng Việt; một bước duyệt, không ủy quyền, không hủy đơn đã gửi.
