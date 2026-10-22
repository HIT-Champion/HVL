# Bảng tự chấm 50 điểm PoF

Dùng bảng này để tự chấm kho mã nguồn trước ngày BTC chấm (**7–9/12/2026**). Phần PoF được chấm
**trên repo, không có mặt đội thi để giải thích** — nên mọi bằng chứng phải nhìn thấy được ngay
từ trang chủ kho mã nguồn.

**Cách dùng:** mỗi tiêu chí ghi rõ *bằng chứng trong repo* và *lệnh tự kiểm tra*. Đánh dấu ✅ chỉ
khi đã chạy lệnh kiểm tra và thấy kết quả sạch.

---

## Tiêu chí 1 — Hệ thống quản lý mã nguồn trên Internet (5đ)

| Trạng thái | Yêu cầu | Bằng chứng | Mức trừ nếu thiếu |
|---|---|---|---|
| ☐ | Kho mã nguồn công khai trên Internet | URL GitHub/GitLab công khai | — |
| ☐ | Có web viewer duyệt mã trực tiếp trên trình duyệt | GitHub/GitLab có sẵn | −3 |
| ☐ | Truy cập mở, không cần đăng nhập | Mở repo ở chế độ ẩn danh để kiểm chứng | −3 |
| ☐ | **Repo được sử dụng thực tế** | Lịch sử commit trải đều nhiều tháng, nhiều tác giả, không phải một cú push duy nhất | **−5** |

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
| ☐ | Giấy phép được OSI phê duyệt | `LICENSE` — Apache-2.0 | điều kiện loại trừ |
| ☐ | Ghi giấy phép trong **từng tệp mã** | Header Apache-2.0 đầu mỗi tệp | −5 |
| ☐ | Không xung đột giấy phép giữa các thành phần | `DEPENDENCIES.md`, mục kiểm tra tương thích | −5 |
| ☐ | Có thông báo về **mục đích** của giấy phép | `NOTICE`, mục "Mục đích của giấy phép" | −5 |
| ☐ | Có **bản sao toàn văn** giấy phép | `LICENSE` (11 KB, toàn văn Apache-2.0) | −5 |

```bash
make license-check     # kiểm tra header trong từng tệp mã
head -3 LICENSE        # xác nhận là toàn văn, không phải link
```

---

## Tiêu chí 3 — Có ít nhất một bản phát hành (5đ)

| Trạng thái | Yêu cầu | Bằng chứng | Mức trừ nếu thiếu |
|---|---|---|---|
| ☐ | Có ≥ 1 release **trước thời điểm nộp bài** | Trang Releases của repo | −5 |
| ☐ | Phát hành **theo phiên bản** (SemVer) | Thẻ `v0.1.0`, `v0.2.0`… | −3 |
| ☐ | Dùng **định dạng mở** cho gói phát hành | `.tar.gz` — **tuyệt đối không** `.zip`, `.rar`, `.arj` | −3 |

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
| ☐ | Có hướng dẫn dịch từ mã nguồn | README, mục "Cài đặt từ mã nguồn" | −5 |
| ☐ | **Không** cấu hình bằng cách sửa tay tệp header | Mọi tham số nằm trong `.env` | −5 |
| ☐ | Cấu hình được **trước khi** dịch | `cp .env.example .env` rồi mới `make build` | −5 |
| ☐ | Dịch bằng **công cụ nguồn mở** | Docker, Compose, Make, Git — đều là PMNM | −5 |
| ☐ | Chạy được **ngoài thư mục mã nguồn** | `make install PREFIX=/opt/moc` (README, mục "Cài ra ngoài thư mục mã nguồn"); CI chạy smoke từ bản cài | −5 |

**Bài kiểm tra thực tế bắt buộc làm trước ngày chấm** — giả lập đúng thao tác của giám khảo:

```bash
cd /tmp && rm -rf pof-test && mkdir pof-test && cd pof-test
git clone <URL-repo> && cd HVL
cp .env.example .env
make check && make build && make up
# Hệ thống phải chạy được mà không cần sửa bất kỳ tệp mã nào.

# Chạy ngoài thư mục mã nguồn: cài, xóa hẳn mã nguồn, chạy từ PREFIX
make down && make install PREFIX=/tmp/pof-test/opt-moc
cd /tmp/pof-test && rm -rf HVL && cd opt-moc
docker compose up -d --wait && python3 scripts/seed.py && python3 scripts/smoke.py
```

---

## Tiêu chí 5 — Sử dụng thư viện và gói đính kèm (10đ)

| Trạng thái | Yêu cầu | Bằng chứng | Mức trừ nếu thiếu |
|---|---|---|---|
| ☐ | Có tài liệu làm rõ thư viện/gói sử dụng | `DEPENDENCIES.md` | — |
| ☐ | Ưu tiên thư viện sẵn có của hệ thống | Dùng image chính thức, không tự đóng gói lại | −5 |
| ☐ | **Không** phát hành kèm gói của dự án phụ thuộc | Không commit `vendor/`, `node_modules/`, `third_party/` | −5 |
| ☐ | **Không** chỉnh sửa mã nguồn gói đính kèm | Không fork-sửa upstream; tùy biến ở lớp config/plugin | −5 |

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
| ☐ | Có hệ thống ghi nhận lỗi (bug tracker) | GitHub Issues **đã bật** + mẫu báo lỗi + **có issue thật** | −5 |
| ☐ | Có lịch sử thay đổi (changelog) | `CHANGELOG.md` theo Keep a Changelog | −5 |
| ☐ | Có README và hướng dẫn | `README.md` | −5 |

> ⚠️ Bật Issues nhưng để trống trông như chưa dùng bao giờ. Trong quá trình phát triển, hãy mở
> issue thật cho các đầu việc và đóng chúng qua commit — vừa là bằng chứng bug tracker hoạt động,
> vừa củng cố tiêu chí 1 (*"repo được sử dụng thực tế"*).

---

## Rà soát cuối cùng — đầu tháng 12/2026

- [ ] Clone repo vào máy sạch, chạy đủ chuỗi `clone → cp .env → make up` thành công
- [ ] Mở repo bằng trình duyệt ẩn danh, xác nhận truy cập được không cần đăng nhập
- [ ] Trang Releases có ≥ 1 bản phát hành kèm gói `.tar.gz` tự sinh và `.sha256`
- [ ] `make license-check` sạch trên toàn bộ cây mã nguồn
- [ ] `DEPENDENCIES.md` đã điền đủ, không còn dòng *chưa chốt*
- [ ] `CHANGELOG.md` có mục cho mọi phiên bản đã phát hành
- [ ] Issues có lịch sử thật: issue đã mở và đã đóng
- [ ] Không có tệp nào chứa mật khẩu thật hoặc khóa API (`git log -p | grep -i 'api[_-]key'`)
