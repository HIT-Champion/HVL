# Thêm một ứng dụng mới trên lõi Signet

Signet chia hai tầng. Tầng 1 là lõi không giao diện: định danh (Keycloak), cổng API (APISIX), dữ liệu và quyền
(PostgreSQL + Hasura), tệp và kiểm dịch (`svc-files`), quy trình (`svc-workflow`, Flowable), sổ kiểm toán chuỗi băm.
Tầng 2 là ứng dụng, gọi lõi qua cổng như mọi client khác. Văn phòng điện tử (`apps/office`) là ứng dụng đầu tiên.

Tài liệu này ghi các bước để cắm thêm một ứng dụng, lấy **Không gian cá nhân P.A.R.A** (`apps/ca-nhan`) làm ví dụ đầy
đủ. Ứng dụng này được thêm vào mà **không sửa dòng nào trong `services/`**, không sửa bảng, quyền hay migration nào
của lõi: chỉ thêm cấu hình và một schema riêng (mục 4).

## 1. Ứng dụng nhận gì từ lõi

| Việc | Lõi làm sẵn | Ứng dụng chỉ cần |
|---|---|---|
| Đăng nhập | SSO và TOTP của Keycloak; một phiên cho mọi ứng dụng | Một client công khai, Authorization Code + PKCE |
| Danh tính, đơn vị, vai trò | Token mang claim `https://hasura.io/jwt/claims` (người dùng, đơn vị, phòng, vai trò) | Giữ 5 mapper của client mẫu |
| Cổng | Cửa duy nhất ra ngoài, kiểm JWT ở biên, giới hạn tốc độ, `X-Request-Id` | Một route tới trang tĩnh của ứng dụng |
| Dữ liệu và quyền | GraphQL tự sinh, quyền theo vai trò và đơn vị đến từng dòng | Bảng trong schema riêng, khai quyền trong metadata |
| Tệp | `POST /api/files`: ClamAV quét, sạch mới vào kho; `GET /api/files/{id}`: tải về nếu được xem | Gọi đúng hai đường đó |
| Sổ kiểm toán | Trigger `core.audit()` ghi chuỗi băm, neo ra kho lạnh, `moc audit verify` kiểm lại | Gắn trigger vào bảng của mình |
| Vận hành | Sao lưu và khôi phục cả CSDL, reconciler GitOps dựng lại container theo compose | Một service trong profile `app` |

## 2. Các bước

| # | Tệp | Làm gì |
|---|---|---|
| 1 | `platform/keycloak/realm/moc-realm.json` | Chép client `app-office`, đổi `clientId`, `name`, `baseUrl`; `redirectUris` và `post.logout.redirect.uris` chỉ dưới đường của ứng dụng (`${MOC_PUBLIC_URL}/<đường>/*`). Giữ `publicClient`, `pkce.code.challenge.method: S256`, không bật luồng mật khẩu, tài khoản dịch vụ; giữ nguyên `protocolMappers` |
| 2 | `platform/apisix/apisix.yaml` | Một `upstream` tới `<service>:8080`, một route `uris: ["/<đường>", "/<đường>/*"]`, `methods: [GET, HEAD]`, đặt **trước** route bắt mọi đường của `app-office`. Trang tĩnh không cần token; API của ứng dụng đi qua các route có sẵn (`/v1/graphql`, `/api/files`), đã kiểm token |
| 3 | `docker-compose.yml` | Service `<<: *common`, `build: ./apps/<thư mục>` **trên một dòng** (`make install` thay dòng đó bằng `pull_policy: never`), `image: moc/<service>:${MOC_VERSION:-dev}`, `profiles: [app]`. Reconciler và `make up` tự nhận service mới |
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

## 3. Ví dụ: Không gian cá nhân P.A.R.A

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

## 4. Bằng chứng: lõi không đổi

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

## 5. Giới hạn

- **Không xóa tệp.** Lõi không có API xóa tệp, và nguyên tắc dữ liệu là không xóa: tệp không dùng nữa thì chuyển
  sang Lưu trữ.
- Quản trị đơn vị (`tenant_admin`) không có không gian cá nhân.
- Chỉ xếp được tệp tải lên qua Không gian cá nhân hoặc tệp không mã hóa do chính mình tải lên ở Văn phòng điện tử;
  tệp chuyển sang kho lạnh theo hồ sơ nộp lưu thì chưa kiểm việc tải về từ đây.
- Chưa có hạn mức dung lượng cho mỗi người; cỡ tệp tối đa theo `svc-files`.
- Đường dưới `/ca-nhan/` không có tệp thì trả trang chính (ứng dụng một trang).
- Đặt `MOC_OIDC_AUDIENCE` cho `svc-files` thì client mới cũng phải có mapper audience tương ứng.
- Giao diện chỉ tiếng Việt.
