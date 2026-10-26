# Signet

Lõi nền tảng nguồn mở, tự cài, kèm ứng dụng đầu tiên là Văn phòng điện tử. Trang này giúp xem nhanh hệ thống trong 5
phút và biết tìm từng phần ở đâu. Giới thiệu đầy đủ ở [`README.md`](../README.md).

## Xem nhanh trong 5 phút

Không cần cài gì:

1. **Hệ thống là gì (1 phút):** [`README.md`](../README.md), mục Giới thiệu và sơ đồ ở mục Kiến trúc.
2. **Trạng thái (30 giây):** <https://signet.htechcs.com/trang-thai>, không cần đăng nhập: từng thành phần của lõi
   đang chạy hay gián đoạn.
3. **Dùng thử (2 phút):** <https://signet.htechcs.com>, đăng nhập bằng tài khoản dùng thử ở
   [`README.md`](../README.md#chạy-thử), mục Chạy thử. Tài khoản chuyên viên mà mục đó gợi ý để thử nhanh không cần
   xác thực hai bước; hộp việc có sẵn một công văn khẩn chờ xử lý và một dự thảo bị trả lại chờ sửa.
4. **Xác thực văn bản (1 phút):** <https://signet.htechcs.com/xac-thuc>, không cần đăng nhập: tra mã in cạnh mã QR
   hoặc thả tệp PDF đã phát hành; tệp bị sửa thì báo không khớp.
5. **Kiểm tự động (30 giây):** trang [Actions](https://github.com/HIT-Champion/Signet/actions/workflows/ci.yml).
   Mỗi pull request dựng toàn hệ thống từ mã nguồn rồi chạy smoke, e2e trên trình duyệt thật, các màn demo và cài ra
   ngoài thư mục mã nguồn.

Tự cài thì dùng bốn lệnh ở [`README.md`](../README.md#cài-đặt-từ-mã-nguồn-building-from-source), mục Cài đặt từ mã
nguồn. Sau đó mỗi nguyên lý thiết kế có một màn demo chạy bằng một lệnh, dưới một phút: README, mục Bằng chứng 4 nguyên
lý; kịch bản ở [`demo-script.md`](demo-script.md).

## Tìm gì ở đâu

| Phần | Xem ở đâu | Kiểm tự động |
|---|---|---|
| Mã nguồn, cách làm việc | Repo công khai, xem không cần đăng nhập. [Pull requests](https://github.com/HIT-Champion/Signet/pulls?q=is%3Apr+is%3Amerged): mọi thay đổi vào `develop` qua PR, cần CI xanh và một người khác duyệt. [Issues](https://github.com/HIT-Champion/Signet/issues) có mẫu báo lỗi, đề xuất. Quy trình: [`git_flow.md`](git_flow.md) | Ruleset của `develop`, `main` ([`git_flow.md`](git_flow.md) mục 10) |
| Giấy phép | [`LICENSE`](../LICENSE) (toàn văn Apache-2.0); [`NOTICE`](../NOTICE), mục "Mục đích của giấy phép"; dòng SPDX đầu mỗi tệp mã; [`REUSE.toml`](../REUSE.toml) cho tệp không chèn được (tài liệu, ảnh, phông, JSON) | CI job "Giấy phép": header từng tệp, không bundle mã dự án khác, SBOM và giấy phép mọi gói kể cả gián tiếp (`make license-audit`) |
| Bản phát hành | [Releases](https://github.com/HIT-Champion/Signet/releases): gói `.tar.gz` tự sinh kèm `.sha256`, SBOM CycloneDX `.cdx.json` từ v1.1.0; thẻ SemVer; [`CHANGELOG.md`](../CHANGELOG.md) theo Keep a Changelog | `make release` tạo gói `.tar.gz`; workflow `nang-cap.yml` tập nâng cấp từ bản trước |
| Cài đặt | README, mục Cài đặt từ mã nguồn: mọi tham số trong `.env` (`make env` hay `cp .env.example .env`), không sửa tệp mã; `make install PREFIX=…` cài ra ngoài thư mục mã nguồn; lên máy chủ: [`trien-khai.md`](trien-khai.md) | CI job "Dựng từ mã nguồn"; job `chay-thu` dựng toàn hệ thống, phần `cai-dat` cài ra thư mục khác rồi chạy từ bản cài |
| Thư viện, gói phụ thuộc | [`DEPENDENCIES.md`](../DEPENDENCIES.md): từng thành phần kèm giấy phép. Image thượng nguồn ghim phiên bản và digest trong `docker-compose.yml`, tùy biến bằng cấu hình; không commit `vendor/`, `node_modules/` | CI job "Giấy phép", bước "Không bundle mã nguồn dự án khác"; `make license-audit` |
| Tài liệu, giao tiếp | README ([tiếng Anh](../README.en.md)), [`CONTRIBUTING.md`](../CONTRIBUTING.md), [`SECURITY.md`](../SECURITY.md) (báo lỗ hổng riêng tư đã bật), [`CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md), [`ROADMAP.md`](../ROADMAP.md), tài liệu API [`api/`](api/README.md) | CI job "Tài liệu" |
| Ý tưởng, kiến trúc | [`dac-ta-san-pham.md`](dac-ta-san-pham.md) §1–2: vì sao chọn hướng này, bài toán. [`architecture.md`](architecture.md): mô hình H-P-D-I, §4 ranh giới lõi và ứng dụng, §5 bản ghi quyết định kiến trúc | — |
| Đã làm tới đâu | [`muc-hoan-thien.md`](muc-hoan-thien.md): mức của từng tính năng (Hoàn thiện, Dùng được, Minh họa…), tệp test, bước CI, lệnh demo, hạn chế; [`danh-gia-ai.md`](danh-gia-ai.md); [`so-lieu-sau.md`](so-lieu-sau.md) | `make test` đối số test ghi trong `muc-hoan-thien.md` với mã thật |
| Dễ dùng | Văn phòng điện tử có tiếng Việt và tiếng Anh, dùng được trên điện thoại, đạt tương phản và quét trợ năng theo WCAG 2.2 AA; ảnh ở README, mục Ảnh chụp màn hình | CI job `chay-thu`, phần `e2e` (quét bằng axe-core) |
| Vận hành lâu dài | [`van-hanh.md`](van-hanh.md): thêm đơn vị, sao lưu và khôi phục, két bí mật, mốc neo công khai, GitOps và tự phục hồi, giám sát, log tập trung; [`them-ung-dung.md`](them-ung-dung.md): cắm ứng dụng mới bằng một lệnh; [`tu-chan-doan.md`](tu-chan-doan.md) | CI job `chay-thu`, phần `sao-luu` |
| Trình diễn | [`demo-script.md`](demo-script.md): từng màn, phương án dự phòng, việc trước giờ trình diễn; [`dac-ta-san-pham.md`](dac-ta-san-pham.md) §7: kịch bản 5 phút | Mọi màn `make demo-*` chạy lại trong CI job `chay-thu`, trừ `demo-kiem-dich` (đã có trong `make smoke`) |

Bảng tự kiểm theo các yêu cầu PoF, có ngày và commit đã kiểm: [`du-thi/pof-checklist.md`](du-thi/pof-checklist.md).

## Giới hạn đã biết

Mỗi giới hạn có issue theo dõi. Hạn chế của từng tính năng ở [`muc-hoan-thien.md`](muc-hoan-thien.md), chỗ còn yếu của
kiến trúc ở [`architecture.md`](architecture.md) §6.

- Quy trình (Flowable) mới phục vụ Văn phòng điện tử: `svc-workflow` chỉ nhận các Action viết sẵn của Văn phòng,
  manifest ứng dụng chưa khai được quy trình (#301).
- Phần máy chủ của Văn phòng còn chạy chung tiến trình với phần lõi trong `svc-files`, `svc-workflow`
  ([`architecture.md`](architecture.md) §4.4, hướng tách §4.7; #302).
- Chưa có biểu mẫu low-code: form của Văn phòng viết trong mã, JSON Schema ở `schemas/` chỉ dùng để kiểm dữ liệu
  (#303).
- Hồ sơ đã nộp lưu (Parquet trên kho lạnh) tìm và xác thực được, nhưng chưa phân tích được trên trang Điều hành (#304).
- Phông Be Vietnam Pro (OFL-1.1) có ba bản giống nhau trong repo (#305).
- Không gian cá nhân và Bảng tin mới có tiếng Việt (#306).

Các việc còn mở khác: [Issues](https://github.com/HIT-Champion/Signet/issues).
