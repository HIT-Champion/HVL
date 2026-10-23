# Quy trình Git của Signet

> Áp dụng cho cả đội (**Backend · AI · Frontend**) và người đóng góp bên ngoài.
> Mục tiêu: `main` chỉ chứa các bản đã phát hành, `develop` lúc nào cũng chạy được, lịch sử commit đọc
> được, và bản thân repo là bằng chứng cho các tiêu chí PoF #1 (dùng repo thật), #3 (phát hành theo
> phiên bản), #6 (bug tracker, changelog).

---

## 0. Tóm tắt một màn hình

```
 issue #12 ─► nhánh feat/12-keycloak-realm (tách từ develop) ─► commit nhỏ ─► PR vào develop
                                                                                 │
                                                    CI xanh + 1 review ─► squash merge vào develop
                                                                                 │
 cuối mỗi phase: PR develop → main "chore(release): vX.Y.Z" ─► merge commit ─► thẻ vX.Y.Z trên main
                                                                                 │
                  GitHub Release (.tar.gz) ◄── Actions ◄─────────────────────────┤
                                                                                 │
                                  đưa lên server: nhánh deploy theo thẻ ◄────────┘

 lỗi gấp sau phát hành: hotfix/X.Y.Z từ main ─► PR vào main ─► thẻ ─► PR main → develop (gộp ngược)
```

**7 luật vàng:**

1. Không ai push thẳng lên `develop` hay `main`. Mọi thay đổi đi qua Pull Request; **`main` chỉ nhận
   PR phát hành** (mục 6).
2. Mỗi việc bắt đầu từ một **issue**. Nhánh và commit đều ghi số issue.
3. Commit message theo **Conventional Commits** (mục 3).
4. Mỗi PR cần **CI xanh** và **1 người ở mảng khác** duyệt.
5. Tài liệu của tính năng nằm **trong cùng PR** với mã.
6. Không bao giờ commit bí mật, `.env`, dữ liệu thật, `node_modules/`, trọng số mô hình, CSDL chữ ký ClamAV.
7. Từ **17:00 06/12/2026** không push gì lên repo này nữa — kho mã được chấm 7–9/12.

---

## 1. Mô hình nhánh

Đội dùng **Git Flow** rút gọn: tính năng gộp vào `develop`, `main` chỉ nhận bản phát hành. Người tải
mã từ `main` hay từ trang Release luôn nhận một phiên bản đã chốt, có ghi chép thay đổi; phần đang làm
dở nằm ở `develop`. So với Git Flow đầy đủ, đội bỏ nhánh `release/*`: với 3 người, việc chốt bản phát
hành (chuyển mục CHANGELOG) làm bằng một PR vào `develop`, rồi PR thẳng `develop` → `main`.

| Nhánh | Vai trò | Ai được ghi | Cách ghi |
|---|---|---|---|
| `develop` | **Nhánh mặc định**: mã mới nhất, **luôn chạy được** | Không ai push trực tiếp | Squash merge từ PR |
| `main` | Chỉ các bản đã phát hành; mỗi commit gộp trên `main` mang một thẻ | Không ai push trực tiếp | Merge commit từ PR phát hành (mục 6) |
| `deploy` | Đúng phiên bản đang chạy trên server; reconciler kéo nhánh này | Backend | Theo thẻ phát hành (mục 7) |
| `<loại>/<issue>-<mô-tả>` | Nhánh làm việc tách từ `develop`, sống **≤ 3 ngày** | Người làm issue | Commit, push thoải mái |
| `hotfix/X.Y.Z` | Sửa gấp một lỗi của bản đã phát hành, tách từ `main` | Người sửa | PR vào `main`, rồi gộp ngược vào `develop` |
| Thẻ `vX.Y.Z` | Bản phát hành, gắn trên `main` | Backend | `make release` (mục 6); không sửa, không xóa được |

---

## 2. Đặt tên nhánh

```
<loại>/<số-issue>-<mô-tả-ngắn>
```

- `<loại>` giống loại commit (mục 3.2): `feat`, `fix`, `docs`, `refactor`, `test`, `build`, `ci`, `chore`.
- Chữ thường, không dấu, nối bằng gạch ngang, tối đa ~5 từ.
- Nhánh sửa gấp bản đã phát hành: `hotfix/<phiên-bản-mới>`, ví dụ `hotfix/1.1.1`.
- CI (job "Quy trình nhánh và tiêu đề PR") từ chối PR vào `develop` từ nhánh không có `<loại>/`, có chữ
  hoa hay có dấu; thiếu số issue thì chỉ nhắc.

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

- **Dòng đầu ≤ 72 ký tự**, viết **tiếng Anh**, bắt đầu bằng động từ ở thể mệnh lệnh (`add`, `fix`, `move`…),
  chữ thường, không chấm cuối. Thân commit cũng viết tiếng Anh.
- Thân và chân cách dòng đầu **một dòng trống**; xuống dòng ở khoảng 72 ký tự.
- `Closes #12` (từ khóa tiếng Anh) để GitHub tự đóng issue khi merge vào nhánh mặc định `develop`;
  `Refs #12` để chỉ liên kết.

Từ 23/10/2026 (sau `v1.0.0`), commit, tiêu đề và mô tả PR viết tiếng Anh: lịch sử Git là thứ người ngoài đội —
cộng đồng nguồn mở, người muốn đóng góp — đọc đầu tiên, và mô tả PR thành thân commit khi *Squash and merge*.
Commit trước mốc này giữ nguyên tiếng Việt, không viết lại lịch sử. Issue viết tiếng Việt, tiêu đề kèm bản tiếng
Anh trong ngoặc; tài liệu, `CHANGELOG.md` và giao diện vẫn tiếng Việt vì người dùng là cơ quan, trường học Việt Nam.

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
| `cli` | Lệnh `scripts/moc.py` | Backend |
| `scripts` | Các kịch bản khác trong `scripts/`: seed, smoke, demo, phát hành | Ai cũng được |
| `e2e` | Kiểm thử trình duyệt Playwright, `tests/e2e/` | Frontend |
| `ci` | CI/CD | Backend |
| `deps` | Nâng hoặc ghim phiên bản, `DEPENDENCIES.md` | Ai cũng được |
| `docs` | Tài liệu chung | Ai cũng được |
| `release` | Phát hành | Backend |

Thay đổi chạm nhiều phạm vi → chọn phạm vi chính, hoặc bỏ trống: `feat: …`. CI kiểm tiêu đề PR theo
đúng hai bảng trên (`scripts/check_pr.py`): thêm loại hay phạm vi thì sửa cả hai nơi.

### 3.4. Ví dụ

**Tốt:**

```
feat(workflow): add a director approval step above the amount threshold

Read the threshold from DXOS_APPROVAL_THRESHOLD instead of hard-coding
it in the BPMN, so that each organization sets it by its own rules.

Closes #27
```

```
fix(files): block files when ClamAV times out instead of storing them

A scan that timed out still stored the file, against the zero-trust
principle. Treat such a file as unsafe and return 503.

Closes #41
```

```
docs(readme): add the problem statement and the feature table
```

**Chưa tốt:**

| Commit | Vấn đề | Nên viết |
|---|---|---|
| `update` | Không nói gì | `fix(office): show the Approve button on small screens` |
| `fix bug` | Lỗi nào, ở đâu? | `fix(auth): stop the redirect loop when the token expires` |
| `WIP` | Không dùng cho commit đã merge | Gộp lại khi squash merge (mục 5) |
| `feat: finish phase 1` | Quá to, không review được | Tách thành nhiều PR nhỏ |

### 3.5. Mẫu commit cho trình soạn thảo

Lưu khối dưới đây thành tệp `~/.gitmessage-moc`, rồi chạy
`git config commit.template ~/.gitmessage-moc` trong thư mục repo. Khi gõ `git commit` (không `-m`),
trình soạn thảo mở sẵn mẫu; các dòng bắt đầu bằng `#` tự bị bỏ.

```
# <loại>(<phạm vi>): <mô tả ngắn bằng tiếng Anh, ≤ 72 ký tự, không chấm cuối>
#
# Loại:    feat fix perf refactor docs test build ci chore revert
# Phạm vi: gateway auth db workflow files realtime office ai data ops cli scripts e2e ci deps docs release
#
# Thân (tùy chọn, tiếng Anh): VÌ SAO thay đổi. Xuống dòng ở 72 ký tự.
#
# Chân (tùy chọn):
# Closes #<số-issue>            tự đóng issue khi merge vào develop
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
git switch develop && git pull                   # 1. lấy develop mới nhất
git switch -c feat/12-keycloak-realm             # 2. tạo nhánh từ issue #12
# ... sửa, commit nhỏ ...
git fetch origin && git rebase origin/develop    # 3. cập nhật theo develop trước khi mở PR
git push -u origin feat/12-keycloak-realm        # 4. đẩy nhánh
gh pr create --base develop --fill               # 5. mở PR vào develop (nhánh mặc định của repo)
```

### 5.2. Yêu cầu với PR

- **Tiêu đề PR = commit message dòng đầu**, theo mục 3 — vì khi squash merge, tiêu đề PR trở thành
  commit duy nhất trên `develop`. CI kiểm tiêu đề mỗi lần mở hay sửa PR.
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

- Điều kiện: **CI xanh** (8 job: 7 job của workflow CI — Giấy phép, Dựng từ mã nguồn, Tài liệu, Test đơn vị dịch vụ,
  Schema và quyền trên CSDL thật, Chạy thử toàn hệ thống, Quét bí mật và lỗ hổng phụ thuộc — và job "Quy trình nhánh và
  tiêu đề PR" của workflow PR) + **1 duyệt**. Ruleset của repo chặn nút merge tới khi đủ. Job "Chạy thử toàn hệ thống"
  gom ba phần chạy song song trên ba máy (`Chạy thử: luong-chinh`, `ai-sao-luu`, `cai-dat`; phần nào cũng tự dựng và nạp
  mẫu), mất khoảng 12 phút; PR chỉ đổi tài liệu (`*.md`, ảnh trong `docs/`, trừ `docs/api/`) không dựng hệ thống, job
  này đạt ngay. Lỗi thì tải `stack-logs-<phần>` ở trang lượt chạy để xem nhật ký từng dịch vụ và vết Playwright.
- Cách merge vào `develop`: **Squash and merge** — mọi commit nhỏ của nhánh gộp thành một commit sạch.
  Riêng PR gộp ngược sau bản vá nóng (mục 6) dùng **Create a merge commit**.
- Cách merge vào `main` (PR phát hành, mục 6): **Create a merge commit**, giữ nguyên các commit của
  `develop`.
- Người mở PR tự merge sau khi được duyệt; nhánh làm việc tự xóa sau khi gộp.

---

## 6. Phát hành

Lịch: `v0.1.0` 18/10 · `v1.0.0` 23/10, bản cho vòng trường (cả hai đã phát hành) · `v1.1.0` 03/12, bản nộp chấm
(mục 8). Các lệnh dưới đây lấy `1.1.0` làm ví dụ.

Đây là lúc duy nhất `main` nhận thay đổi.

```bash
# 1. Chốt ghi chép thay đổi trên develop: PR (nhánh chore/<issue>-chot-1-1-0) chuyển các dòng của mục
#    "[Chưa phát hành]" trong CHANGELOG.md sang "## [1.1.0] - 2026-12-03", viết 3–8 dòng tóm tắt ngay dưới
#    tiêu đề đó (trang Release hiện phần này, phần còn lại gập lại), để lại tiêu đề
#    "## [Chưa phát hành]" trống (CI đòi có mục này)
#    tiêu đề PR: chore(release): chốt ghi chép thay đổi v1.1.0  → review → squash merge vào develop

# 2. PR phát hành develop → main, tiêu đề đúng "chore(release): v1.1.0"
gh pr create --base main --head develop --title "chore(release): v1.1.0" --body "Phát hành v1.1.0"
#    CI kiểm: nguồn là develop, CHANGELOG có mục [1.1.0] có dòng thay đổi, thẻ v1.1.0 chưa có
#    → review → Create a merge commit

# 3. Gắn thẻ trên main mới nhất, cây làm việc sạch:
git switch main && git pull
make release VERSION=1.1.0       # tạo thẻ v1.1.0 + gói .tar.gz + .sha256 trong dist/ để kiểm tra

# 4. Đẩy thẻ — GitHub Actions kiểm thẻ nằm trên main, chưa có Release, rồi tạo Release kèm .tar.gz, .sha256
git push origin v1.1.0
```

**Bản vá nóng** — lỗi của bản đã phát hành cần sửa ngay, không chờ phase sau:

```bash
git fetch origin && git switch -c hotfix/1.1.1 origin/main
# sửa, commit "fix(…): …"; thêm mục "## [1.1.1] - <ngày>" ngay dưới "## [Chưa phát hành]" của CHANGELOG.md,
# ghi dòng sửa vào đó
git push -u origin hotfix/1.1.1
gh pr create --base main --title "chore(release): v1.1.1" --body "Sửa gấp …"   # → review → merge commit
git switch main && git pull && make release VERSION=1.1.1 && git push origin v1.1.1
# gộp ngược vào develop qua một nhánh riêng (không sửa thẳng develop hay main được):
git switch -c chore/gop-nguoc-1-1-1 origin/develop && git merge --no-ff origin/main
#    CHANGELOG.md xung đột ở đầu tệp thì giữ cả mục [Chưa phát hành] của develop lẫn mục [1.1.1]
git push -u origin chore/gop-nguoc-1-1-1
gh pr create --base develop --title "chore(release): gộp ngược v1.1.1 vào develop" --body ""
#    → review → Create a merge commit (không squash: giữ quan hệ cha con để lần phát hành sau không xung đột)
```

- Phiên bản theo **Semantic Versioning**: số giữa tăng khi có tính năng mới, số cuối cho bản vá nóng, số đầu chỉ
  tăng khi bản cài cũ không nâng cấp tại chỗ được.
- `release.yml` dựng trang Release bằng `scripts/release_body.py`: dòng đầu ghi **tệp chính thức là
  `moc-X.Y.Z.tar.gz`** (GitHub luôn tự gắn thêm "Source code (zip)" mà PoF #3 trừ điểm định dạng không mở), rồi
  phần tóm tắt, toàn bộ ghi chép thay đổi gập lại.
- Không xóa hay gắn lại thẻ đã đẩy — ruleset thẻ `v*` chặn hẳn, `release.yml` và `release.sh` cũng từ
  chối phát hành lại. Phát hành nhầm thì ra bản vá `vX.Y.Z+1`.

---

## 7. Đưa lên server (nhánh `deploy`)

Reconciler trên server kéo nhánh `deploy` mỗi 60 giây. Chỉ Backend (@Vanvuong2005827) đẩy nhánh này.

```bash
git fetch origin
git switch deploy && git pull --ff-only
git merge --ff-only v1.1.0          # thẻ phát hành trên main
git push origin deploy
```

Máy chủ bật kiểm chữ ký (`MOC_GITOPS_ALLOWED_SIGNERS`, `van-hanh.md` mục GitOps) thì đầu nhánh phải là commit do người
trong danh sách ký bằng khóa SSH — thay dòng `--ff-only` bằng:

```bash
git merge --no-ff -S -m "deploy: v1.1.0" v1.1.0   # -S: ký bằng user.signingkey (gpg.format=ssh)
git verify-commit HEAD                            # thấy Good "git" signature trước khi đẩy
```

- **Chỉ fast-forward** (bật kiểm chữ ký: chỉ commit gộp có ký như trên), không commit thẳng lên `deploy`.
- Lỗi trên server → bản vá nóng (mục 6), rồi đưa `deploy` lên thẻ mới.
- Tạo nhánh lần đầu: `git push origin v1.1.0^{commit}:refs/heads/deploy` (bật kiểm chữ ký thì máy chủ chỉ
  áp từ lần gộp có ký đầu tiên).

---

## 8. Các mốc đóng băng

| Từ | Quy tắc |
|---|---|
| **26/11** | Đóng băng tính năng: chỉ nhận PR `fix`, `docs`, `test`, `chore(release)` |
| **03/12** | Phát hành `v1.1.0`, bản nộp chấm. Sau đó mỗi PR sửa lỗi gộp vào `develop` đi kèm một bản vá `v1.1.x` trước 17:00 06/12: lúc chấm, `develop` (nhánh mặc định, giám khảo clone) và `main` cùng nội dung |
| **05/12 → 10/12** | Không đẩy `deploy` trừ khi cả đội đồng ý (sự cố chặn demo) |
| **17:00 06/12** | **Không push bất cứ gì lên repo này** — kể cả nhánh mới. Slide, video làm ở repo riêng |

---

## 9. Xử lý tình huống thường gặp

| Tình huống | Cách xử lý |
|---|---|
| Nhánh bị tụt so với `develop` | `git fetch origin && git rebase origin/develop`, sửa xung đột, `git push --force-with-lease` |
| Lỡ mở PR vào `main` | Bấm **Edit** cạnh tiêu đề PR, đổi nhánh đích sang `develop` — CI chặn PR không phải phát hành vào `main` |
| Xung đột ở tệp khóa (`package-lock.json`…) | Lấy bản của `develop`, chạy lại trình cài gói để sinh lại tệp khóa, commit |
| Viết sai commit message, **chưa push** | `git commit --amend` |
| Viết sai commit message, đã push **nhánh của mình** | `git commit --amend` rồi `git push --force-with-lease` (không bao giờ làm trên `develop`, `main`) |
| Lỡ commit bí mật | **Đổi bí mật đó ngay** (coi như đã lộ), báo cả đội, rồi mới gỡ khỏi mã |
| PR đã merge gây lỗi | Mở PR `revert` vào `develop`: `git revert <sha>` — không sửa lịch sử `develop`, `main`. Lỗi đã nằm trong bản phát hành → bản vá nóng (mục 6) |
| Muốn bỏ hết thay đổi chưa commit | `git restore .` (kiểm tra kỹ trước — không lấy lại được) |

---

## 10. Thiết lập GitHub một lần (người quản trị repo)

- **Nhánh mặc định là `develop`** (Settings → General → Default branch, hay
  `gh repo edit --default-branch develop`): PR mới tự trỏ vào `develop`, và nhánh mặc định không bao giờ bị tự
  xóa sau khi gộp PR phát hành. Không để `main` làm mặc định: GitHub chỉ đọc `Closes #N` trong PR nhắm vào nhánh
  mặc định, PR vào nhánh khác không nối, không đóng được issue. Giám khảo clone nhánh mặc định: ruleset giữ
  `develop` luôn xanh CI, và lúc chấm `develop` cùng nội dung với `main` (mục 8).
- **Ruleset** (Settings → Rules → Rulesets), khai sẵn trong `.github/rulesets/`, tạo bằng
  `gh api -X POST repos/HIT-Champion/HVL/rulesets --input .github/rulesets/<tệp>.json`:
  - `develop.json` — nhánh `develop`: bắt buộc PR, 1 duyệt, 8 job CI xanh (mục 5.4); chỉ squash hoặc
    merge commit; cấm force push, cấm xóa;
  - `main.json` — nhánh `main`: như trên nhưng chỉ merge commit; job "Quy trình nhánh và tiêu đề PR"
    chỉ cho PR phát hành vào;
  - `tags.json` — thẻ `v*`: không ai sửa hay xóa được, kể cả quản trị;
  - `tag-creation.json` — thẻ `v*`: chỉ quản trị repo được tạo.
- **Bảo vệ nhánh `deploy`**: cấm force push; chỉ Backend được push.
- **Merge** (Settings → General → Pull Requests):
  - bật *Allow merge commits* và *Allow squash merging*, tắt *Allow rebase merging*;
  - nội dung commit mặc định của cả hai lấy tiêu đề + mô tả PR;
  - bật *Automatically delete head branches*;
  - bằng lệnh: `gh repo edit --enable-merge-commit --enable-squash-merge --enable-rebase-merge=false
    --delete-branch-on-merge`, rồi `gh api -X PATCH repos/HIT-Champion/HVL -f merge_commit_title=PR_TITLE
    -f merge_commit_message=PR_BODY -f squash_merge_commit_title=PR_TITLE -f squash_merge_commit_message=PR_BODY`.
- **Code security** (Settings → Code security): bật *Secret scanning* và *Push protection* (miễn phí với repo
  công khai), chặn từ lúc push thay vì đợi job gitleaks của CI.
- **Issues**:
  - bật Issues;
  - tạo nhãn `backend`, `ai`, `frontend`, `bug`, `feature`, `docs`, `good first issue`;
  - tạo milestone `Phase 0` … `Phase 5` theo kế hoạch.

---

## 11. Quy trình qua các giai đoạn

| Giai đoạn | Cách làm thực tế |
|---|---|
| Đến `v1.0.0` (23/10/2026) | Mã được gộp **tại máy** rồi đẩy lên theo đợt, không qua pull request, không có review trên GitHub. Một đợt đẩy nhiều commit sát nhau thì CI tự hủy các lượt đang chờ (*Cancelled*), mỗi đợt chỉ lượt cuối chạy đủ; các lượt *Cancelled* này cùng nhiều lượt chạy khác của giai đoạn này đã bị xóa khỏi trang Actions ngày 23/10/2026. Thẻ `v0.1.0` từng bị gắn lại; mỗi lần như vậy workflow Release chạy lại và thay gói `.tar.gz` cùng `.sha256` đã đăng. Commit chuyển sang Git Flow và bản phát hành `v1.0.0` cũng đẩy thẳng lên `develop`, `main`, trước khi bật ruleset. |
| Sau `v1.0.0` | Git Flow như các mục trên: mọi thay đổi qua PR vào `develop`, CI và một người duyệt là bắt buộc (ruleset); `main` chỉ nhận PR phát hành; thẻ `v*` không sửa, không xóa được. |

Vì sao đổi: gộp tại máy không để lại dấu vết review nào trên GitHub; commit không nối được với issue
(không có `Closes #`); `main` có lúc đỏ CI mà không có gì chặn; và gắn lại thẻ làm hỏng tổng kiểm của
người đã tải bản phát hành. Các luật ở mục 1, 5, 6 và ruleset ở mục 10 chặn đúng những chỗ đó.

---

## Phụ lục — Lệnh hay dùng

```bash
git status                              # đang ở đâu, đã sửa gì
git log --oneline --graph -20           # lịch sử gần đây
git diff / git diff --staged            # xem thay đổi chưa / đã stage
git add -p                              # chọn từng đoạn để commit
git switch -c <nhánh>                   # tạo và chuyển nhánh
git fetch origin && git rebase origin/develop
git push --force-with-lease             # đẩy lại nhánh của mình sau rebase/amend
gh pr create --base develop --fill / gh pr checks / gh pr merge --squash --delete-branch
```
