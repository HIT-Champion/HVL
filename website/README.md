# website — trang tài liệu

Trang tài liệu của Signet, dựng bằng Docusaurus 3.10 (#308). Thư mục này không chứa nội dung: trang đọc thẳng `docs/`
và README của các thành phần trong kho (danh sách `INCLUDE` trong [`docusaurus.config.js`](docusaurus.config.js)), bỏ
`docs/du-thi/nghien-cuu/`. GitHub và trang tài liệu hiện cùng một tệp, sửa một chỗ.

## Dựng thử trên máy

Cần Node.js 24.

```bash
cd website
npm ci --ignore-scripts
npm run build    # ra build/; liên kết hỏng làm lệnh dừng
npm run serve    # xem ở http://localhost:3000/Signet/
```

`npm start` chạy máy chủ phát triển: sửa tệp `.md` là trang cập nhật ngay.

## Viết tài liệu cho trang

- Tệp `.md` đọc như CommonMark (`markdown.format: 'detect'`), nên cứ viết như cho GitHub, dấu `<`, `{` không làm hỏng
  bước dựng. Không cần front matter: tiêu đề trang là dòng `# ` đầu tiên, tên trên mục lục đặt trong
  [`sidebars.js`](sidebars.js).
- Thêm trang: đặt tệp trong `docs/` rồi thêm một dòng vào `sidebars.js`. Thêm README của thành phần mới: thêm mẫu vào
  `INCLUDE`.
- Liên kết tương đối tới tệp mã, thư mục vẫn viết như cho GitHub;
  [`src/remark/lien-ket-kho.js`](src/remark/lien-ket-kho.js) đổi chúng thành liên kết GitHub. Liên kết tới tệp `.md`
  hay ảnh không tồn tại làm bước dựng dừng.

## Đăng lên GitHub Pages

Workflow [`trang-tai-lieu.yml`](../.github/workflows/trang-tai-lieu.yml) dựng trang trên mọi PR. Push lên `develop` thì
đăng lên <https://hit-champion.github.io/Signet/>, với điều kiện repo đã bật Pages (Settings → Pages → Source: GitHub
Actions). Chưa bật thì workflow vẫn dựng, chỉ bỏ qua bước đăng.

Phụ thuộc, giấy phép và lỗ hổng chấp nhận tạm: [`DEPENDENCIES.md`](../DEPENDENCIES.md) mục Trang tài liệu,
[`osv-scanner.toml`](osv-scanner.toml).
