# Bảng tự chấm 50 điểm PoF

Dùng bảng này để tự chấm kho mã nguồn trước ngày BTC chấm (**7–9/12/2026**). Phần PoF được chấm
**trên repo, không có mặt đội thi để giải thích** — nên mọi bằng chứng phải nhìn thấy được ngay
từ trang chủ kho mã nguồn.

**Cách dùng:** mỗi tiêu chí ghi rõ *bằng chứng trong repo* và *lệnh tự kiểm tra*. Đánh dấu ✅ chỉ
khi đã chạy lệnh kiểm tra và thấy kết quả sạch.

**Lần kiểm gần nhất:** 26/10/2026, trên `develop` 62bff8d. Ô ✅ đã kiểm bằng lệnh, CI hay trang GitHub ghi ở cột
Bằng chứng; CI của commit đó xanh cả 14 job:
<https://github.com/HIT-Champion/Signet/actions/runs/40315747559>. Ô ☐ chưa đạt, ghi lý do và issue. Số commit, PR,
issue là số lúc kiểm. Mục "Rà soát cuối cùng" làm lại trên bản phát hành cuối, trước 17:00 06/12/2026.

---

## Tiêu chí 1 — Hệ thống quản lý mã nguồn trên Internet (5đ)

| Trạng thái | Yêu cầu | Bằng chứng | Mức trừ nếu thiếu |
|---|---|---|---|
| ✅ | Kho mã nguồn công khai trên Internet | <https://github.com/HIT-Champion/Signet>, `gh repo view` báo `PUBLIC` | — |
| ✅ | Có web viewer duyệt mã trực tiếp trên trình duyệt | GitHub: duyệt mã, lịch sử, blame trên trình duyệt | −3 |
| ✅ | Truy cập mở, không cần đăng nhập | Trang repo, Releases, Issues và `LICENSE` trả 200 khi tải không đăng nhập, không cookie | −3 |
| ✅ | **Repo được sử dụng thực tế** | Đề trừ điểm khi "có repo nhưng thực tế không dùng". Đã kiểm: 118 PR đã gộp, PR nào cũng có lượt duyệt; 137 issue, 117 đã đóng; 334 commit trên `develop` của 3 tác giả (`git shortlog -sn`, gộp tên theo `.mailmap`) | **−5** |

> ⚠️ Mức trừ −5 nặng nhất của tiêu chí này là *"có hệ thống quản lý mã nguồn nhưng trên thực tế
> không được sử dụng"*. Đây là lý do phải commit đều **từ tháng 9**, không dồn toàn bộ vào tháng 12.

```bash
git log --pretty='%h %ad %an %s' --date=short | tail -20   # lịch sử có trải đều không
git shortlog -sn                                            # đóng góp có nhiều người không
```

---

## Tiêu chí 2 — Cấp phép PMNM theo giấy phép OSI-approved (10đ)

| Trạng thái | Yêu cầu | Bằng chứng | Mức trừ nếu thiếu |
|---|---|---|---|
| ✅ | Giấy phép được OSI phê duyệt | `LICENSE` — Apache-2.0; GitHub nhận đúng Apache-2.0 (`gh api repos/HIT-Champion/Signet/license`) | điều kiện loại trừ |
| ✅ | Ghi giấy phép trong **từng tệp mã** | Header Apache-2.0 đầu mỗi tệp; tệp không chèn được header (JSON, ảnh, PDF, tài liệu) khai trong `REUSE.toml`. `./scripts/license-header.sh check` sạch; `reuse lint` (5.0.2): 753/753 tệp có bản quyền và giấy phép, đạt REUSE 3.3 | −5 |
| ✅ | Không xung đột giấy phép giữa các thành phần | `DEPENDENCIES.md`, mục kiểm tra tương thích; `make license-audit` kiểm mọi gói kể cả gói gián tiếp trong SBOM, ngoại lệ có lý do ở `.github/license-exceptions.json`; CI chạy trên mọi PR, xanh ở job "Giấy phép" của 62bff8d | −5 |
| ✅ | Có thông báo về **mục đích** của giấy phép | `NOTICE`, mục "Mục đích của giấy phép" | −5 |
| ✅ | Có **bản sao toàn văn** giấy phép | `LICENSE` (11 KB, toàn văn Apache-2.0) | −5 |

```bash
make license-check     # kiểm tra header trong từng tệp mã
uvx --from reuse==5.0.2 reuse lint   # mọi tệp có thông tin bản quyền, giấy phép (chuẩn REUSE)
make sbom && make license-audit      # giấy phép của mọi gói npm, Python, action CI (cần Docker, mạng tới PyPI)
head -3 LICENSE        # xác nhận là toàn văn, không phải link
```

---

## Tiêu chí 3 — Có ít nhất một bản phát hành (5đ)

| Trạng thái | Yêu cầu | Bằng chứng | Mức trừ nếu thiếu |
|---|---|---|---|
| ✅ | Có ≥ 1 release **trước thời điểm nộp bài** | Trang Releases của repo: 3 bản v0.1.0, v1.0.0, v1.1.0 | −5 |
| ✅ | Phát hành **theo phiên bản** (SemVer) | Thẻ `v0.1.0`, `v1.0.0`, `v1.1.0`; `CHANGELOG.md` theo SemVer 2.0.0 | −3 |
| ✅ | Dùng **định dạng mở** cho gói phát hành | `.tar.gz` — **tuyệt đối không** `.zip`, `.rar`, `.arj`. Mỗi bản kèm gói `.tar.gz` tự sinh và `.sha256`, không tải lên gói nén nào khác; v1.1.0 thêm SBOM `.cdx.json` | −3 |

> ⚠️ GitHub **tự động** đính kèm cả `Source code (zip)` và `Source code (tar.gz)` vào mỗi release.
> Không xóa được phần tự động này, nên phải **chủ động tải lên gói `.tar.gz` do mình sinh ra**
> (kèm `.sha256`) và ghi rõ trong phần mô tả release rằng đây mới là gói phát hành chính thức.

```bash
make release VERSION=0.1.0
git push origin main --tags
```

---

## Tiêu chí 4 — Cài đặt, dịch từ mã nguồn (10đ)

| Trạng thái | Yêu cầu | Bằng chứng | Mức trừ nếu thiếu |
|---|---|---|---|
| ✅ | Có hướng dẫn dịch từ mã nguồn | README, mục "Cài đặt từ mã nguồn"; `README.en.md`, mục "Building from source" | −5 |
| ✅ | **Không** cấu hình bằng cách sửa tay tệp header | Mọi tham số nằm trong `.env`. CI job "Dựng từ mã nguồn", bước "Cấu hình được trước khi dựng, không sửa tệp mã" chỉ chạy `cp .env.example .env`; job `chay-thu` dựng toàn hệ thống từ `.env` do `make env` sinh | −5 |
| ✅ | Cấu hình được **trước khi** dịch | `make env` (hay `cp .env.example .env`) rồi mới `make up` (README, bước 2 và 3) | −5 |
| ✅ | Dịch bằng **công cụ nguồn mở** | Docker Engine, Docker Compose, GNU Make, Git, Python 3 — đều là PMNM (README, mục "Yêu cầu hệ thống") | −5 |
| ✅ | Chạy được **ngoài thư mục mã nguồn** | `make install PREFIX=/opt/moc` (README, mục "Cài ra ngoài thư mục mã nguồn"); CI job `chay-thu`, phần `cai-dat`, bước "Cài ra ngoài thư mục mã nguồn và chạy từ đó" xanh trên 62bff8d | −5 |

**Bài kiểm tra thực tế bắt buộc làm trước ngày chấm** — giả lập đúng thao tác của giám khảo:

```bash
cd /tmp && rm -rf pof-test && mkdir pof-test && cd pof-test
git clone <URL-repo> && cd Signet
cp .env.example .env
make check && make build && make up
# Hệ thống phải chạy được mà không cần sửa bất kỳ tệp mã nào.

# Chạy ngoài thư mục mã nguồn: cài, xóa hẳn mã nguồn, chạy từ PREFIX
make down && make install PREFIX=/tmp/pof-test/opt-moc
cd /tmp/pof-test && rm -rf Signet && cd opt-moc
docker compose up -d --wait && python3 scripts/seed.py && python3 scripts/smoke.py
```

---

## Tiêu chí 5 — Sử dụng thư viện và gói đính kèm (10đ)

| Trạng thái | Yêu cầu | Bằng chứng | Mức trừ nếu thiếu |
|---|---|---|---|
| ✅ | Có tài liệu làm rõ thư viện/gói sử dụng | `DEPENDENCIES.md`; danh mục đầy đủ từng gói (kể cả gián tiếp) kèm giấy phép: SBOM CycloneDX `signet-X.Y.Z.cdx.json` đính kèm bản phát hành từ sau v1.0.0 (`make sbom`); v1.1.0 có `signet-1.1.0.cdx.json` | — |
| ✅ | Ưu tiên thư viện sẵn có của hệ thống | Dùng image chính thức, không tự đóng gói lại: image thượng nguồn trong `docker-compose.yml` ghim phiên bản và digest. Image đội tự dựng là mã của đội (dịch vụ, ứng dụng) và APISIX: image `apache/apisix` chính thức thêm tệp `plugin.wasm` chép từ image chính thức của coraza-proxy-wasm 0.6.0, kiểm SHA-256 | −5 |
| ☐ | **Không** phát hành kèm gói của dự án phụ thuộc | Không commit `vendor/`, `node_modules/`, `third_party/` (CI job "Giấy phép" kiểm). Chưa đánh dấu lúc kiểm 26/10 trên 62bff8d: phông Be Vietnam Pro (OFL-1.1) có 3 bản TTF trong repo. #305 bỏ các tệp này, lấy từ gói npm `@fontsource/be-vietnam-pro` lúc dựng; kiểm lại sau khi gộp | −5 |
| ✅ | **Không** chỉnh sửa mã nguồn gói đính kèm | Không fork-sửa upstream; tùy biến ở lớp config/plugin. Repo không có tệp `.patch`, Dockerfile không vá mã thượng nguồn; tùy biến bằng route APISIX, metadata Hasura, realm và theme Keycloak | −5 |

> ⚠️ Đây là tiêu chí **xung khắc nhất** với bản chất "lắp ghép open-core" của Signet. Nguyên tắc
> an toàn: `docker-compose.yml` kéo image thượng nguồn **nguyên bản có ghim thẻ phiên bản**; mọi
> tùy biến nằm ở `.env`, tệp cấu hình riêng, hoặc adapter do đội tự viết.

```bash
git ls-files | grep -E '(vendor|third_party|node_modules)/' && echo "VI PHẠM" || echo "Sạch"
```

---

## Tiêu chí 6 — Tài liệu và giao tiếp (10đ)

| Trạng thái | Yêu cầu | Bằng chứng | Mức trừ nếu thiếu |
|---|---|---|---|
| ✅ | Có hệ thống ghi nhận lỗi (bug tracker) | GitHub Issues **đã bật** + mẫu báo lỗi + **có issue thật**: mẫu `bug_report.yml`, `feature_request.yml`; 137 issue, 117 đã đóng | −5 |
| ✅ | Có lịch sử thay đổi (changelog) | `CHANGELOG.md` theo Keep a Changelog, có mục cho v0.1.0, v1.0.0, v1.1.0 và mục "Chưa phát hành" (CI job "Tài liệu" kiểm) | −5 |
| ✅ | Có README và hướng dẫn | `README.md`, bản tiếng Anh `README.en.md`; xem nhanh và bản đồ tài liệu ở `docs/README.md` | −5 |

> ⚠️ Bật Issues nhưng để trống trông như chưa dùng bao giờ. Trong quá trình phát triển, hãy mở
> issue thật cho các đầu việc và đóng chúng qua commit — vừa là bằng chứng bug tracker hoạt động,
> vừa củng cố tiêu chí 1 (*"repo được sử dụng thực tế"*).

---

## Rà soát cuối cùng — đầu tháng 12/2026

Làm trên bản phát hành cuối, trước 17:00 06/12/2026. Lần kiểm ở các bảng trên không thay cho mục này.

- [ ] Clone repo vào máy sạch, chạy đủ chuỗi `clone → cp .env → make up` thành công
- [ ] Mở repo bằng trình duyệt ẩn danh, xác nhận truy cập được không cần đăng nhập
- [ ] Trang Releases có ≥ 1 bản phát hành kèm gói `.tar.gz` tự sinh, SBOM `.cdx.json` và `.sha256` của cả hai
- [ ] `make license-check` sạch trên toàn bộ cây mã nguồn; `make sbom && make license-audit` đạt
- [ ] `SECURITY.md` có trên trang chủ repo; *Private vulnerability reporting* đã bật (`docs/git_flow.md` mục 10)
- [ ] `DEPENDENCIES.md` đã điền đủ, không còn dòng *chưa chốt*
- [ ] `CHANGELOG.md` có mục cho mọi phiên bản đã phát hành
- [ ] Issues có lịch sử thật: issue đã mở và đã đóng
- [ ] Không có tệp nào chứa mật khẩu thật hoặc khóa API (`git log -p | grep -i 'api[_-]key'`)
