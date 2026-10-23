# Chính sách bảo mật

Signet giữ văn bản hành chính, tài khoản người dùng và khóa ký của đơn vị, nên một lỗ hổng có thể làm lộ dữ liệu của
người khác. Nếu bạn tìm thấy lỗ hổng, xin báo **riêng** cho nhóm duy trì theo hướng dẫn dưới đây — đừng mở issue,
pull request hay thảo luận công khai về nó.

## Phiên bản được hỗ trợ

| Phiên bản | Nhận bản vá bảo mật |
|---|---|
| Bản phát hành mới nhất (hiện là 1.0.x, nhánh `main`) | ✅ |
| `develop` (chưa phát hành) | ✅ — bản vá gộp vào đây, bản đã phát hành nhận qua [bản vá nóng](docs/git_flow.md#6-phát-hành) |
| Các bản cũ hơn (0.1.0) | ❌ — hãy nâng lên bản mới nhất |

Danh sách bản phát hành: [trang Releases](https://github.com/HIT-Champion/HVL/releases); thay đổi của từng bản:
[`CHANGELOG.md`](CHANGELOG.md).

## Cách báo lỗ hổng

Dùng tính năng báo lỗ hổng riêng tư của GitHub (*private vulnerability reporting*):

1. Mở tab **Security** của kho → **Report a vulnerability**, hoặc vào thẳng
   <https://github.com/HIT-Champion/HVL/security/advisories/new>.
2. Điền mẫu báo cáo. Chỉ bạn và nhóm duy trì đọc được; mọi trao đổi tiếp theo diễn ra ngay trong báo cáo đó.

Không thấy nút **Report a vulnerability** nghĩa là tính năng chưa được bật — người quản trị kho bật trong Settings →
Code security ([`docs/git_flow.md`](docs/git_flow.md) mục 10). Khi đó hãy mở một issue chỉ ghi "Cần kênh riêng để báo
lỗ hổng bảo mật", **không** mô tả lỗ hổng, không đính kèm gì; nhóm duy trì sẽ bật tính năng hoặc mời bạn vào một bản
nháp security advisory riêng.

Dự án không nhận báo lỗ hổng qua email cá nhân hay mạng xã hội của thành viên.

## Nên gửi kèm

- Thành phần bị ảnh hưởng (dịch vụ, endpoint, tệp) và phiên bản: tên bản phát hành, hoặc `git describe --tags`.
- Các bước tái hiện ngắn nhất, kèm cấu hình khác mặc định nếu có. Đừng gửi tệp `.env`, mật khẩu hay khóa thật.
- Tác động: ai làm được gì mà lẽ ra không được — đọc văn bản của đơn vị khác, vượt quyền, sửa sổ kiểm toán mà không bị
  phát hiện…
- Bản vá hay cách giảm thiểu bạn đề xuất, nếu có.
- Bạn có muốn được ghi tên khi công bố hay không.

## Thời gian phản hồi

Signet do một đội sinh viên duy trì; các mốc dưới đây là mục tiêu của đội, không phải cam kết hợp đồng.

| Bước | Mục tiêu |
|---|---|
| Xác nhận đã nhận báo cáo | trong 3 ngày làm việc |
| Đánh giá ban đầu: có phải lỗ hổng không, mức độ, kế hoạch sửa | trong 7 ngày |
| Phát hành bản vá | mức nghiêm trọng và cao: trong 30 ngày; mức thấp hơn: bản phát hành kế tiếp |

Quá các mốc trên mà chưa có phản hồi, hãy nhắc lại ngay trong báo cáo.

## Phạm vi

Trong phạm vi:

- Mã và cấu hình của đội trong kho này: `services/`, `apps/`, `scripts/`, `db/`, `platform/`, `docker-compose.yml` —
  kể cả cấu hình làm phần mềm thượng nguồn lộ ra lỗ hổng (route cổng API mở quá rộng, quyền Hasura sai, két bí mật cấp
  quyền thừa…).
- Bản chạy thử trực tuyến do đội vận hành. Chỉ dùng tài khoản mẫu hoặc tài khoản của chính bạn và dừng ngay khi đã
  chứng minh được lỗ hổng: không quét tự động cường độ cao, không tấn công từ chối dịch vụ, không đọc, sửa, xóa dữ liệu
  của người khác, không giữ quyền truy cập lâu hơn mức cần để chứng minh. Dữ liệu trên bản chạy thử là dữ liệu mẫu giả
  lập.
- Gói phát hành và quy trình dựng: các lệnh `make`, workflow trong `.github/workflows/`, SBOM đính kèm bản phát hành.

Ngoài phạm vi:

- Lỗ hổng của chính phần mềm thượng nguồn (Keycloak, APISIX, Hasura, Flowable, PostgreSQL…): Signet dùng chúng nguyên
  bản ([`DEPENDENCIES.md`](DEPENDENCIES.md)), hãy báo cho dự án đó. Phiên bản Signet đang ghim có lỗ hổng đã công bố
  thì vẫn báo ở đây để đội nâng bản.
- Chữ ký số trên văn bản đi không có giá trị pháp lý: tính năng chỉ minh họa, CA nội bộ — đây là thiết kế, không phải
  lỗ hổng. Giả mạo được chữ ký hay qua mặt được bước kiểm chữ ký thì vẫn trong phạm vi.
- Bản cài do đơn vị khác tự vận hành: báo cho đơn vị đó; lỗ hổng nằm trong mã thì báo ở đây.
- Lừa đảo, tấn công vật lý vào máy của thành viên; kết quả quét tự động chưa chỉ ra được tác động.

## Công bố

- Đừng công bố (issue, bài viết, mạng xã hội, hội thảo) trước khi bản vá được phát hành, hoặc trước ngày hai bên đã
  thống nhất.
- Sau khi phát hành bản vá, nhóm duy trì đăng GitHub Security Advisory (xin mã CVE khi phù hợp) và ghi vào
  `CHANGELOG.md` mục "Đã sửa lỗi", kèm tên người báo nếu người đó đồng ý.
- Dự án chưa có chương trình thưởng tiền cho báo cáo lỗ hổng.

## Chuỗi cung ứng phần mềm

- Từ bản sau 1.0.0, mỗi bản phát hành kèm danh mục thành phần SBOM CycloneDX `moc-X.Y.Z.cdx.json` (và `.sha256`), sinh
  bằng `make sbom`: gói npm, Python, action CI của đúng cây mã nguồn được gắn thẻ, kèm giấy phép. Đối chiếu với cơ sở
  dữ liệu lỗ hổng không cần dựng hệ thống: `osv-scanner scan source -L moc-X.Y.Z.cdx.json`. Lỗ hổng đội chấp nhận tạm,
  có lý do và hạn xem lại, nằm trong `apps/office/osv-scanner.toml`.
- CI chạy trên mọi pull request: quét bí mật trong toàn bộ lịch sử commit (gitleaks), lỗ hổng đã biết trong các tệp
  khóa phụ thuộc (OSV-Scanner), giấy phép của mọi gói kể cả gói gián tiếp (`make license-audit`).
- Image bên thứ ba và action ghim theo digest, SHA commit; thư viện cài theo băm trong tệp khóa
  ([`DEPENDENCIES.md`](DEPENDENCIES.md)).
