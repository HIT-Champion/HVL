# Thư mục giữ chỗ cho phông Be Vietnam Pro

Thư mục này cố ý không có tệp phông (#305). Khi chạy, dịch vụ `keycloak-fonts` của `docker-compose.yml` chép phông
lấy từ gói npm `@fontsource/be-vietnam-pro` (SIL OFL-1.1, dựng trong `platform/keycloak/fonts/`) vào volume
`keycloak_fonts`, và Keycloak gắn volume đó đè lên đúng thư mục này: `be-vietnam-pro.css` (CSS của gói, `styles` trong
`theme.properties` nạp), `files/*.woff2`, `files/*.woff` và `OFL.txt`.

Đừng xóa tệp này: thư mục theme gắn vào Keycloak chỉ đọc, nên điểm gắn của volume phải có sẵn trong repo, bản cài và
gói phát hành.
