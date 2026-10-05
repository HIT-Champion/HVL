# Quy trình Git của Mộc

> Áp dụng cho cả đội (**Backend · AI · Frontend**) và người đóng góp bên ngoài.
> Mục tiêu: nhánh `main` lúc nào cũng chạy được, lịch sử commit đọc được, và bản thân repo là bằng
> chứng cho các tiêu chí PoF #1 (dùng repo thật), #3 (phát hành theo phiên bản), #6 (bug tracker,
> changelog).

---

## 0. Tóm tắt một màn hình

```
 issue #12 ─► nhánh feat/12-keycloak-realm ─► commit nhỏ ─► Pull Request ─► CI xanh + 1 review
                                                                                 │
                                                                     squash merge vào main
                                                                                 │
                   cuối mỗi phase: make release VERSION=x.y.z ─► thẻ vX.Y.Z ─► GitHub Release (.tar.gz)
                                                                                 │
                                    đưa lên server: fast-forward nhánh deploy ◄──┘
```

**7 luật vàng:**

1. Không ai push thẳng lên `main`. Mọi thay đổi đi qua Pull Request.
2. Mỗi việc bắt đầu từ một **issue**. Nhánh và commit đều ghi số issue.
3. Commit message theo **Conventional Commits** (mục 3).
4. Mỗi PR cần **CI xanh** và **1 người ở mảng khác** duyệt.
5. Tài liệu của tính năng nằm **trong cùng PR** với mã.
6. Không bao giờ commit bí mật, `.env`, dữ liệu thật, `node_modules/`, trọng số mô hình, CSDL chữ ký ClamAV.
7. Từ **17:00 06/12/2026** không push gì lên repo này nữa — kho mã được chấm 7–9/12.

---

## 1. Mô hình nhánh

Đội dùng **GitHub Flow** (một nhánh chính + nhánh ngắn hạn), không dùng Git Flow cổ điển
(`develop`, `release/*`, `hotfix/*`): với 3 người trong 9 tuần, thêm nhánh chỉ thêm việc merge.

| Nhánh | Vai trò | Ai được ghi | Cách ghi |
|---|---|---|---|
| `main` | Mã mới nhất, **luôn chạy được** | Không ai push trực tiếp | Squash merge từ PR |
| `deploy` | Đúng phiên bản đang chạy trên server; reconciler kéo nhánh này | Backend | Fast-forward từ thẻ phát hành hoặc từ `main` đã qua CI |
| `<loại>/<issue>-<mô-tả>` | Nhánh làm việc, sống **≤ 3 ngày** | Người làm issue | Commit, push thoải mái |
| Thẻ `vX.Y.Z` | Bản phát hành | Backend | `make release` (mục 6) |

---

## 2. Đặt tên nhánh

```
<loại>/<số-issue>-<mô-tả-ngắn>
```

- `<loại>` giống loại commit (mục 3.2): `feat`, `fix`, `docs`, `refactor`, `test`, `build`, `ci`, `chore`.
- Chữ thường, không dấu, nối bằng gạch ngang, tối đa ~5 từ.

| Đúng | Sai |
|---|---|
| `feat/12-keycloak-realm` | `feature-moi` (không loại, không issue) |
| `fix/31-clamav-timeout` | `fix/sửa-lỗi-quét-virus` (có dấu) |
| `docs/40-huong-dan-api` | `hoang-test` (không rõ làm gì) |

---

## 3. Viết commit message

### 3.1. Định dạng

```
<loại>(<phạm vi>): <mô tả ngắn>

<thân — tùy chọn: VÌ SAO thay đổi, không chỉ LÀM GÌ>

<chân — tùy chọn: Closes #12 · Refs #12 · Co-authored-by: … · BREAKING CHANGE: …>
```

- **Dòng đầu ≤ 72 ký tự**, viết tiếng Việt có dấu, bắt đầu bằng động từ, chữ thường, không chấm cuối.
- Thân và chân cách dòng đầu **một dòng trống**; xuống dòng ở khoảng 72 ký tự.
- `Closes #12` (từ khóa tiếng Anh) để GitHub tự đóng issue khi merge vào `main`; `Refs #12` để chỉ liên kết.

### 3.2. Loại commit

| Loại | Dùng khi | Ghi vào CHANGELOG mục |
|---|---|---|
| `feat` | Thêm tính năng người dùng thấy được | Đã thêm |
| `fix` | Sửa lỗi | Đã sửa lỗi (lỗi bảo mật → **Bảo mật**) |
| `perf` | Tăng hiệu năng, không đổi hành vi | Đã sửa đổi |
| `refactor` | Đổi cấu trúc mã, không đổi hành vi | — |
| `docs` | Chỉ sửa tài liệu | — |
| `test` | Thêm hoặc sửa test | — |
| `build` | Dockerfile, `docker-compose.yml`, Makefile, phiên bản gói | Đã sửa đổi (nếu ảnh hưởng người cài) |
| `ci` | `.github/workflows/` | — |
| `chore` | Việc vặt khác: dọn dẹp, phát hành | — |
| `revert` | Hoàn tác một commit trước | — |

### 3.3. Phạm vi

| Phạm vi | Bao gồm | Mảng chính |
|---|---|---|
| `gateway` | APISIX: route, plugin | Backend |
| `auth` | Keycloak: realm, vai trò, mapper, trang đăng nhập | Frontend · Backend |
| `db` | Schema, migration, metadata Hasura, ràng buộc, sổ kiểm toán | AI |
| `workflow` | Flowable, `svc-workflow`, `processes/*.bpmn` | Backend |
| `files` | `svc-files`, SeaweedFS, ClamAV, tìm kiếm | AI |
| `realtime` | Centrifugo | Backend |
| `office` | `apps/office` — giao diện web | Frontend |
| `ai` | `svc-ai`: RAG, OCR, tác tử | AI |
| `data` | Kestra, nóng → lạnh, lineage | AI |
| `ops` | Compose, reconciler, sao lưu, giám sát, OpenBao | Backend |
| `cli` | Lệnh `dxos` | Backend |
| `ci` | CI/CD | Backend |
| `deps` | Nâng hoặc ghim phiên bản, `DEPENDENCIES.md` | Ai cũng được |
| `docs` | Tài liệu chung | Ai cũng được |
| `release` | Phát hành | Backend |

Thay đổi chạm nhiều phạm vi → chọn phạm vi chính, hoặc bỏ trống: `feat: …`.

### 3.4. Ví dụ

**Tốt:**

```
feat(workflow): thêm bước giám đốc duyệt khi số tiền vượt ngưỡng

Ngưỡng đọc từ biến DXOS_APPROVAL_THRESHOLD thay vì ghi cứng trong BPMN,
để mỗi tổ chức tự đặt theo quy chế của mình.

Closes #27
```

```
fix(files): chặn tệp khi ClamAV không phản hồi thay vì cho qua

Trước đây hết thời gian chờ thì tệp vẫn được lưu, trái nguyên tắc
zero-trust. Giờ coi như tệp không an toàn và trả lỗi 503.

Closes #41
```

```
docs(readme): bổ sung phát biểu bài toán và bảng chức năng
```

**Chưa tốt:**

| Commit | Vấn đề | Nên viết |
|---|---|---|
| `update` | Không nói gì | `fix(office): sửa nút Duyệt bị ẩn trên màn hình nhỏ` |
| `fix bug` | Lỗi nào, ở đâu? | `fix(auth): sửa vòng lặp chuyển hướng khi token hết hạn` |
| `WIP` | Không dùng cho commit đã merge | Gộp lại khi squash merge (mục 5) |
| `feat: làm xong phase 1` | Quá to, không review được | Tách thành nhiều PR nhỏ |

### 3.5. Mẫu commit cho trình soạn thảo

Lưu khối dưới đây thành tệp `~/.gitmessage-moc`, rồi chạy
`git config commit.template ~/.gitmessage-moc` trong thư mục repo. Khi gõ `git commit` (không `-m`),
trình soạn thảo mở sẵn mẫu; các dòng bắt đầu bằng `#` tự bị bỏ.

```
# <loại>(<phạm vi>): <mô tả ngắn, ≤ 72 ký tự, không chấm cuối>
#
# Loại:    feat fix perf refactor docs test build ci chore revert
# Phạm vi: gateway auth db workflow files realtime office ai data ops cli ci deps docs release
#
# Thân (tùy chọn): VÌ SAO thay đổi. Xuống dòng ở 72 ký tự.
#
# Chân (tùy chọn):
# Closes #<số-issue>            tự đóng issue khi merge vào main
# Refs #<số-issue>              chỉ liên kết
# Co-authored-by: Tên <email>   khi làm cặp
# BREAKING CHANGE: <mô tả>      khi phá vỡ API hoặc cấu hình cũ
```

---

## 4. Commit thế nào cho đúng

### 4.1. Cấu hình Git một lần cho mỗi người

```bash
git config --global user.name  "Họ Tên Thật"
git config --global user.email "email-đã-xác-minh-trên-GitHub"   # để commit được tính cho đúng người
git config --global pull.rebase true
git config --global rebase.autoStash true
git config --global core.autocrlf input   # luôn lưu LF, kể cả trên Windows
```

### 4.2. Trước mỗi commit

```bash
make license-fix      # tự chèn header Apache-2.0 vào tệp mã mới
make license-check    # PoF #2 — CI cũng chạy bước này
make check            # môi trường + cú pháp Compose
git diff --staged     # đọc lại đúng những gì sắp commit
```

Có test cho phần mình sửa thì chạy test trước khi commit.

`make license-check` in **CẢNH BÁO loại tệp chưa hỗ trợ** → bổ sung loại tệp đó vào
`scripts/license-header.sh` trong cùng PR, đừng bỏ qua. Sửa tệp `.bpmn` bằng trình vẽ quy trình
xong thì chạy lại `make license-fix`, vì trình vẽ có thể xóa chú thích header.

### 4.3. Nguyên tắc

- **Một commit = một thay đổi logic.** Không trộn sửa định dạng với sửa logic.
- Sau mỗi commit, mã vẫn dựng được.
- **Push nhánh ít nhất mỗi ngày** khi đang làm — vừa sao lưu, vừa để cả đội thấy tiến độ.
- Làm cặp thì thêm `Co-authored-by: Tên <email>` vào chân commit để cả hai cùng được ghi nhận.
- Thêm phần mềm thượng nguồn mới → cùng PR phải cập nhật `DEPENDENCIES.md`.
- Thêm tham số cấu hình → cùng PR phải cập nhật `.env.example`.

### 4.4. Không bao giờ commit

| Thứ | Lý do |
|---|---|
| `.env`, khóa, mật khẩu, token | Lộ bí mật — repo công khai |
| `node_modules/`, `.venv/`, `dist/` | Vi phạm PoF #5 (bundle) — CI chặn `node_modules`, `vendor`, `third_party` |
| `data/`, `volumes/`, bản dump CSDL thật | Dữ liệu cá nhân của đơn vị chạy thử |
| Trọng số mô hình AI, CSDL chữ ký ClamAV | Tải lúc chạy, không đóng gói vào repo hay release |
| Tệp nhị phân lớn (video, ảnh demo nặng) | Làm phình repo; để ở nơi khác và dẫn link |

---

## 5. Pull Request

### 5.1. Các bước

```bash
git switch main && git pull                      # 1. lấy main mới nhất
git switch -c feat/12-keycloak-realm             # 2. tạo nhánh từ issue #12
# ... sửa, commit nhỏ ...
git fetch origin && git rebase origin/main       # 3. cập nhật theo main trước khi mở PR
git push -u origin feat/12-keycloak-realm        # 4. đẩy nhánh
gh pr create --fill                              # 5. mở PR (hoặc mở trên giao diện GitHub)
```

### 5.2. Yêu cầu với PR

- **Tiêu đề PR = commit message dòng đầu**, theo mục 3 — vì khi squash merge, tiêu đề PR trở thành
  commit duy nhất trên `main`.
- Mô tả điền theo mẫu `.github/pull_request_template.md` và có dòng `Closes #<issue>`.
- Gắn **nhãn mảng** (`backend` / `ai` / `frontend`) và **milestone** của phase hiện tại.
- PR nhỏ: lý tưởng dưới ~400 dòng thay đổi. To hơn thì tách.
- Còn dở dang nhưng muốn xin ý kiến sớm → mở **Draft PR**.

### 5.3. Review

| PR của | Người review | Lý do |
|---|---|---|
| Backend (@Vanvuong2005827) | AI (@HoangTechCS-AIE) | AI dùng trực tiếp API và dữ liệu do Backend dựng |
| AI (@HoangTechCS-AIE) | Frontend (@nguyenlehoainam) | Frontend hiển thị dữ liệu, tìm kiếm, trợ lý do AI làm |
| Frontend (@nguyenlehoainam) | Backend (@Vanvuong2005827) | Backend nắm Keycloak, gateway, luồng gọi API |

- Review **trong vòng 24 giờ**. Không kịp thì nhắn người khác review thay.
- Người review chạy thử theo mục "Cách kiểm chứng" trong mô tả PR, không chỉ đọc mã.
- Góp ý nhỏ, không chặn → ghi "nit:" và vẫn duyệt.

### 5.4. Merge

- Điều kiện: **CI xanh** (3 job: Giấy phép, Dựng từ mã nguồn, Tài liệu) + **1 duyệt**.
- Cách merge: **Squash and merge** — mọi commit nhỏ của nhánh gộp thành một commit sạch trên `main`.
- Người mở PR tự merge sau khi được duyệt, rồi **xóa nhánh**.

---

## 6. Phát hành

Lịch theo kế hoạch: `v0.1.0` 25/10 · `v0.2.0` 08/11 · `v0.5.0` 20/11 · `v0.9.0` 25/11 · `v1.0.0` 03/12.

```bash
# 1. PR chuyển các mục "[Chưa phát hành]" trong CHANGELOG.md sang "## [0.1.0] - 2026-10-25"
#    tiêu đề PR: chore(release): v0.1.0  → review → squash merge

# 2. Trên main mới nhất, cây làm việc sạch:
git switch main && git pull
make release VERSION=0.1.0       # tạo thẻ v0.1.0 + gói .tar.gz + .sha256 trong dist/ để kiểm tra

# 3. Đẩy thẻ — GitHub Actions tự tạo GitHub Release kèm .tar.gz và .sha256
git push origin v0.1.0
```

- Phiên bản theo **Semantic Versioning**; trước `v1.0.0` tăng số giữa cho mỗi phase.
- Ghi chú phát hành ghi rõ: **tệp chính thức là `.tar.gz`** (GitHub luôn tự gắn thêm "Source code (zip)").
- Không xóa hay gắn lại thẻ đã đẩy. Phát hành nhầm thì ra bản vá `vX.Y.Z+1`.

---

## 7. Đưa lên server (nhánh `deploy`)

Reconciler trên server kéo nhánh `deploy` mỗi 60 giây. Chỉ Backend (@Vanvuong2005827) đẩy nhánh này.

```bash
git fetch origin
git switch deploy && git pull --ff-only
git merge --ff-only v0.1.0          # hoặc origin/main, nếu commit đó đã qua CI
git push origin deploy
```

- **Chỉ fast-forward**, không commit thẳng lên `deploy`.
- Lỗi trên server → sửa bằng PR vào `main` như bình thường, rồi đẩy lại `deploy`.
- Tạo nhánh lần đầu: `git push origin main:deploy`.

---

## 8. Các mốc đóng băng

| Từ | Quy tắc |
|---|---|
| **26/11** | Đóng băng tính năng: chỉ nhận PR `fix`, `docs`, `test`, `chore(release)` |
| **03/12** | Phát hành `v1.0.0` |
| **05/12 → 10/12** | Không đẩy `deploy` trừ khi cả đội đồng ý (sự cố chặn demo) |
| **17:00 06/12** | **Không push bất cứ gì lên repo này** — kể cả nhánh mới. Slide, video làm ở repo riêng |

---

## 9. Xử lý tình huống thường gặp

| Tình huống | Cách xử lý |
|---|---|
| Nhánh bị tụt so với `main` | `git fetch origin && git rebase origin/main`, sửa xung đột, `git push --force-with-lease` |
| Xung đột ở tệp khóa (`package-lock.json`…) | Lấy bản của `main`, chạy lại trình cài gói để sinh lại tệp khóa, commit |
| Viết sai commit message, **chưa push** | `git commit --amend` |
| Viết sai commit message, đã push **nhánh của mình** | `git commit --amend` rồi `git push --force-with-lease` (không bao giờ làm trên `main`) |
| Lỡ commit bí mật | **Đổi bí mật đó ngay** (coi như đã lộ), báo cả đội, rồi mới gỡ khỏi mã |
| PR đã merge gây lỗi | Mở PR `revert`: `git revert <sha>` — không sửa lịch sử `main` |
| Muốn bỏ hết thay đổi chưa commit | `git restore .` (kiểm tra kỹ trước — không lấy lại được) |

---

## 10. Thiết lập GitHub một lần (người quản trị repo)

- **Bảo vệ nhánh `main`**:
  - bắt buộc qua PR, 1 duyệt;
  - bắt buộc 3 job CI xanh;
  - cấm force push và cấm xóa nhánh.
- **Bảo vệ nhánh `deploy`**: cấm force push; chỉ Backend được push.
- **Merge**:
  - chỉ bật *Squash merging*, nội dung commit mặc định lấy tiêu đề + mô tả PR;
  - bật *Automatically delete head branches*.
- **Issues**:
  - bật Issues;
  - tạo nhãn `backend`, `ai`, `frontend`, `bug`, `feature`, `docs`, `good first issue`;
  - tạo milestone `Phase 0` … `Phase 5` theo kế hoạch.

---

## Phụ lục — Lệnh hay dùng

```bash
git status                              # đang ở đâu, đã sửa gì
git log --oneline --graph -20           # lịch sử gần đây
git diff / git diff --staged            # xem thay đổi chưa / đã stage
git add -p                              # chọn từng đoạn để commit
git switch -c <nhánh>                   # tạo và chuyển nhánh
git fetch origin && git rebase origin/main
git push --force-with-lease             # đẩy lại nhánh của mình sau rebase/amend
gh pr create --fill / gh pr checks / gh pr merge --squash --delete-branch
```
