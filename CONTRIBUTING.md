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
git clone https://github.com/<tài-khoản-của-bạn>/Signet.git
cd Signet
git remote add upstream https://github.com/HIT-Champion/Signet.git

# 3. Tạo nhánh từ develop mới nhất của repo gốc (nhánh mặc định; main chỉ chứa bản đã phát hành)
git fetch upstream
git switch -c feat/<số-issue>-<mô-tả-ngắn> upstream/develop   # hoặc fix/, docs/, refactor/, test/

# 4. Cấu hình môi trường: sinh .env từ .env.example, mọi change_me thay bằng chuỗi ngẫu nhiên
make env

# 5. Sửa mã, rồi kiểm tra trước khi commit
make license-fix      # tự chèn header giấy phép vào tệp mã mới
make license-check    # bảo đảm mọi tệp mã có header giấy phép
make check            # kiểm tra môi trường + cú pháp Compose

# 6. Commit theo quy ước bên dưới, đẩy lên bản fork,
#    rồi mở pull request vào nhánh develop của HIT-Champion/Signet
git push -u origin feat/<số-issue>-<mô-tả-ngắn>
```

Pull request cần **CI xanh** và được **một người duy trì duyệt**, sau đó được gộp vào `develop` bằng
*Squash and merge*. `main` chỉ nhận bản phát hành do người duy trì gộp từ `develop`, hay từ `hotfix/X.Y.Z` khi
sửa gấp bản đã phát hành. Thành viên đội tạo nhánh thẳng trên repo, không cần fork — xem
[`docs/git_flow.md`](docs/git_flow.md).

## Quy ước commit

Theo [Conventional Commits](https://www.conventionalcommits.org/). Commit, tiêu đề và mô tả PR viết **tiếng Anh**
(từ 23/10/2026, commit cũ giữ tiếng Việt — xem [`docs/git_flow.md`](docs/git_flow.md) mục 3.1):

```
<loại>(<phạm vi>): <mô tả ngắn; cả dòng ≤ 72 ký tự>

feat(workflow): add a director approval step above the amount threshold
fix(files): block files when ClamAV times out instead of storing them
docs(readme): add the problem statement and the feature table
ci: pin the checkout action version
```

- **Loại**: `feat`, `fix`, `perf`, `refactor`, `docs`, `test`, `build`, `ci`, `chore`, `revert`.
- **Phạm vi** theo thành phần: `gateway`, `auth`, `db`, `workflow`, `files`, `realtime`, `office`,
  `ca-nhan`, `bang-tin`, `ai`, `data`, `ops`, `cli`, `scripts`, `e2e`, `ci`, `deps`, `docs`, `release`.
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
- Tệp chữ xuống dòng bằng LF (`.editorconfig`, `.gitattributes`). Clone trên Windows vẫn ra LF. Bản clone có từ trước
  #244 thì chạy một lần `git rm -rq --cached . && git reset --hard` để checkout lại ra LF (lệnh bỏ mọi thay đổi chưa
  commit).
- Cập nhật `CHANGELOG.md` mục `[Chưa phát hành]` cho mọi thay đổi hướng người dùng: mỗi thay đổi một dòng (tối đa
  120 ký tự) trong nhóm Đã thêm, Đã sửa đổi, Đã sửa lỗi hay Bảo mật, nói thay đổi gì, kèm số issue hoặc PR. Chi
  tiết cài đặt, số test để ở PR và tài liệu.
- Nếu thêm một phần mềm thượng nguồn mới, phải bổ sung dòng tương ứng vào `DEPENDENCIES.md`
  kèm giấy phép và kiểm tra tính tương thích với Apache-2.0.
- Thêm hay nâng gói npm, Python thì chạy `make sbom && make license-audit` (cần Docker và mạng): CI kiểm giấy phép của
  mọi gói, kể cả gói gián tiếp. Gói ngoài chính sách hay chưa rõ giấy phép cần ngoại lệ ghi lý do trong
  `.github/license-exceptions.json`.

## Dịch giao diện

Phần song ngữ Việt / Anh hiện có:

- **Văn phòng điện tử** (`apps/office`): mọi câu trên giao diện. Ngôn ngữ chọn bằng nút trên thanh trên; trang công
  khai cũng có nút này.
- **Không gian cá nhân** (`apps/ca-nhan`) và **Bảng tin** (`apps/bang-tin`): mọi câu trên giao diện. Nút đổi ngôn
  ngữ ở thanh trên; lựa chọn lưu chung với Văn phòng điện tử.
- **Trang đăng nhập**: theme Keycloak `signet`, câu nằm ở `platform/keycloak/themes/signet/login/messages/`
  (`messages_vi.properties`, `messages_en.properties`).

Ứng dụng mẫu Nghỉ phép (`apps/nghi-phep`) chỉ có tiếng Việt. PDF phát hành và sổ in theo thể thức văn bản tiếng Việt.

Trong Văn phòng điện tử:

- Câu nằm trong `apps/office/app/locales/vi.json` và `en.json`. Hai tệp cùng cây khóa, cùng tham số `{x}`. Thêm câu
  mới thì thêm khóa ở **cả hai** tệp và gọi `t('nhom.khoa')` trong template hoặc script. Không viết chữ thẳng trong
  template, kể cả `placeholder`, `title`, `aria-label`.
- Dữ liệu song ngữ viết trong mã, như bộ câu tự chẩn đoán (`app/utils/hpdi.ts`), dùng dạng `{ vi: '…', en: '…' }`.
- Kiểm bằng `cd apps/office && npm test` (Node 24, `node --test`):
  - `tests/answer.test.ts`: hai tệp cùng khóa, cùng tham số;
  - `tests/i18n.test.ts`: mọi khóa `t('…')` có thật; phần viết thẳng của khóa ghép `` t(`a.${x}`) `` có trong
    `vi.json`; template và script không có chữ tiếng Việt viết cứng, trừ trường `vi:`.

  Ngoài ra, e2e `tests/e2e/tieng-anh.spec.ts` chạy luồng chính bằng tiếng Anh.
- Thêm ngôn ngữ thứ ba hiện phải sửa mã:
  - `app/plugins/i18n.ts`: danh sách bản dịch; ngôn ngữ đã chọn lưu ở `localStorage`, khóa `moc.locale`;
  - nút đổi ngôn ngữ ở `app/layouts/default.vue` và `app/layouts/public.vue`, hiện là công tắc giữa hai ngôn ngữ;
  - các chỗ chọn định dạng số, ngày theo `locale.value === 'vi'`;
  - hàm `hpdiText` của `app/utils/hpdi.ts`;
  - test so cặp `vi` và `en` ở `tests/answer.test.ts`.

Trong Không gian cá nhân và Bảng tin (JavaScript thuần, mỗi ứng dụng một bảng riêng vì image dựng từ thư mục ứng dụng):

- Câu nằm trong `public/i18n.js` của ứng dụng, đối tượng `MESSAGES` có hai bảng `vi`, `en` cùng khóa, cùng tham số
  `{x}`. Mã gọi `t('khoa')`. Chữ tĩnh của `index.html` để sẵn bản tiếng Việt và mang `data-i18n="khoa"` (chữ của phần
  tử) hoặc `data-i18n-<thuộc tính>="khoa"` (vd `data-i18n-aria-label`); `localize()` gán lại theo ngôn ngữ đã chọn.
- Kiểm bằng `node --test tests/*.test.js` trong thư mục ứng dụng: `tests/i18n.test.js` bắt chữ tiếng Việt viết cứng
  trong `public/*.js`, chữ tĩnh của `index.html` không có khóa hay lệch bảng, khóa thiếu ở một trong hai bảng.
  e2e `tests/e2e/tieng-anh.spec.ts` mở cả hai ứng dụng bằng tiếng Anh.

Tài liệu tiếng Anh: `README.en.md`. Bản tiếng Anh của hướng dẫn vận hành đang chờ người đóng góp (issue #59).

## Báo lỗi

**Lỗ hổng bảo mật thì không mở issue**: báo riêng tư theo [`SECURITY.md`](SECURITY.md).

Lỗi khác: mở issue theo mẫu có sẵn tại `.github/ISSUE_TEMPLATE/`. Một báo lỗi hữu ích cần có: bước tái
hiện, kết quả mong đợi, kết quả thực tế, phiên bản Signet (`git describe --tags`), và nhật ký
liên quan (`make logs`).

## Giấy phép của phần đóng góp

Khi gửi pull request, bạn đồng ý rằng phần đóng góp của mình được phát hành theo
**Apache License 2.0**, cùng giấy phép với dự án.
