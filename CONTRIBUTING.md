# Hướng dẫn đóng góp cho Signet

Cảm ơn bạn đã quan tâm tới Signet. Dự án hoan nghênh mọi đóng góp: báo lỗi, đề xuất tính năng,
cải thiện tài liệu, bổ sung dịch vụ cho lõi nền tảng hoặc ứng dụng chạy trên lõi.

Tệp này tóm tắt những điều bắt buộc. Quy trình Git chi tiết (nhánh, commit, pull request, phát
hành) nằm ở [`docs/git_flow.md`](docs/git_flow.md).

## Người duy trì dự án

Mỗi pull request được một người duy trì xem xét. Có câu hỏi về mảng nào, hãy nhắc (@) người phụ
trách mảng đó trong issue hoặc pull request:

| Mảng | Người duy trì |
|---|---|
| Backend — cổng API, quy trình, triển khai | [@Vanvuong2005827](https://github.com/Vanvuong2005827) |
| AI và dữ liệu | [@HoangTechCS-AIE](https://github.com/HoangTechCS-AIE) |
| Frontend — giao diện web | [@nguyenlehoainam](https://github.com/nguyenlehoainam) |

## Nguyên tắc kiến trúc bắt buộc

Trước khi viết dòng mã đầu tiên, hãy nắm ba ràng buộc không được vi phạm:

1. **Không fork-và-sửa phần mềm thượng nguồn.** Signet *điều phối* các dự án nguồn mở ở dạng
   nguyên bản. Mọi tùy biến phải nằm ở lớp cấu hình, plugin, hoặc adapter của riêng Signet.
   Nếu cần vá upstream, hãy gửi patch lên chính dự án đó rồi ghim phiên bản.
2. **Không bundle mã nguồn của dự án khác vào kho này.** Phụ thuộc được khai báo qua image
   Docker có ghim thẻ phiên bản, hoặc qua trình quản lý gói — không sao chép cây mã vào repo.
3. **Không nhảy cóc trục.** Tính năng thuộc trục [I] chỉ được nhận nếu dữ liệu nó tiêu thụ đã do
   [D] chuẩn hóa và sự kiện nó lắng nghe đã do [P] sinh ra.

Muốn thêm một **ứng dụng mới** (Tầng 2) trên lõi, làm theo
[`docs/them-ung-dung.md`](docs/them-ung-dung.md): client Keycloak, route APISIX, service compose, schema riêng
và quyền Hasura — không sửa mã của lõi (`services/`), ví dụ đầy đủ là Không gian cá nhân `apps/ca-nhan/`.

## Quy trình đóng góp

```bash
# 1. Mở issue mô tả lỗi hoặc đề xuất, chờ người duy trì phản hồi trước khi bắt tay làm
#    (sửa lỗi chính tả, tài liệu nhỏ thì bỏ qua bước này)

# 2. Fork repo trên GitHub, rồi tải bản fork về máy
git clone https://github.com/<tài-khoản-của-bạn>/HVL.git
cd HVL
git remote add upstream https://github.com/HIT-Champion/HVL.git

# 3. Tạo nhánh từ develop mới nhất của repo gốc (nhánh mặc định; main chỉ chứa bản đã phát hành)
git fetch upstream
git switch -c feat/<số-issue>-<mô-tả-ngắn> upstream/develop   # hoặc fix/, docs/, refactor/, test/

# 4. Cấu hình môi trường
cp .env.example .env

# 5. Sửa mã, rồi kiểm tra trước khi commit
make license-fix      # tự chèn header giấy phép vào tệp mã mới
make license-check    # bảo đảm mọi tệp mã có header giấy phép
make check            # kiểm tra môi trường + cú pháp Compose

# 6. Commit theo quy ước bên dưới, đẩy lên bản fork,
#    rồi mở pull request vào nhánh develop của HIT-Champion/HVL
git push -u origin feat/<số-issue>-<mô-tả-ngắn>
```

Pull request cần **CI xanh** và được **một người duy trì duyệt**, sau đó được gộp vào `develop` bằng
*Squash and merge*. `main` chỉ nhận bản phát hành do người duy trì gộp từ `develop`. Thành viên đội tạo
nhánh thẳng trên repo, không cần fork — xem [`docs/git_flow.md`](docs/git_flow.md).

## Quy ước commit

Theo [Conventional Commits](https://www.conventionalcommits.org/). Commit, tiêu đề và mô tả PR viết **tiếng Anh**
(từ 23/10/2026, commit cũ giữ tiếng Việt — xem [`docs/git_flow.md`](docs/git_flow.md) mục 3.1):

```
<loại>(<phạm vi>): <mô tả ngắn, ≤ 72 ký tự>

feat(workflow): add a director approval step above the amount threshold
fix(files): block files when ClamAV times out instead of storing them
docs(readme): add the problem statement and the feature table
ci: pin the checkout action version
```

- **Loại**: `feat`, `fix`, `perf`, `refactor`, `docs`, `test`, `build`, `ci`, `chore`, `revert`.
- **Phạm vi** theo thành phần: `gateway`, `auth`, `db`, `workflow`, `files`, `realtime`, `office`,
  `ca-nhan`, `ai`, `data`, `ops`, `cli`, `scripts`, `e2e`, `ci`, `deps`, `docs`, `release`.
- Chân commit ghi `Closes #<số-issue>` để tự đóng issue khi gộp vào `develop`.
- CI kiểm tiêu đề pull request theo đúng quy ước này, vì khi squash nó thành dòng đầu của commit.

Bảng giải thích từng loại, phạm vi và ví dụ: [`docs/git_flow.md`](docs/git_flow.md) mục 3.

## Yêu cầu với mã nguồn

- **Mọi tệp mã mới phải có header giấy phép Apache-2.0** ở đầu tệp. Chạy `make license-fix` để
  tự chèn. CI sẽ chặn pull request nếu thiếu (đây là tiêu chí chấm điểm bắt buộc của dự án).
  Script hỗ trợ cả tệp `.vue`, `.html`, `.xml`, `.bpmn` (chú thích `<!-- -->`) và `.css`, `.scss`
  (chú thích `/* */`). Gặp loại tệp chưa hỗ trợ, script sẽ in **CẢNH BÁO** — khi đó bổ sung loại
  tệp vào `scripts/license-header.sh`, đừng bỏ qua.
- Trình vẽ BPMN có thể xóa chú thích khi lưu lại tệp `.bpmn`. Sau khi sửa quy trình bằng trình vẽ,
  chạy lại `make license-fix`.
- Không hard-code cấu hình. Tham số mới phải được khai báo trong `.env.example` kèm chú thích.
- Mã phải chạy được khi hệ thống được cài **ngoài** thư mục mã nguồn.
- Cập nhật `CHANGELOG.md` mục `[Chưa phát hành]` cho mọi thay đổi hướng người dùng.
- Nếu thêm một phần mềm thượng nguồn mới, phải bổ sung dòng tương ứng vào `DEPENDENCIES.md`
  kèm giấy phép và kiểm tra tính tương thích với Apache-2.0.
- Thêm hay nâng gói npm, Python thì chạy `make sbom && make license-audit` (cần Docker và mạng): CI kiểm giấy phép của
  mọi gói, kể cả gói gián tiếp. Gói ngoài chính sách hay chưa rõ giấy phép cần ngoại lệ ghi lý do trong
  `.github/license-exceptions.json`.

## Báo lỗi

**Lỗ hổng bảo mật thì không mở issue**: báo riêng tư theo [`SECURITY.md`](SECURITY.md).

Lỗi khác: mở issue theo mẫu có sẵn tại `.github/ISSUE_TEMPLATE/`. Một báo lỗi hữu ích cần có: bước tái
hiện, kết quả mong đợi, kết quả thực tế, phiên bản Signet (`git describe --tags`), và nhật ký
liên quan (`make logs`).

## Giấy phép của phần đóng góp

Khi gửi pull request, bạn đồng ý rằng phần đóng góp của mình được phát hành theo
**Apache License 2.0**, cùng giấy phép với dự án.
