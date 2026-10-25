# Quy trình FE Signet

<!-- Copyright 2026 Signet Team -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

## Bộ thư viện thống nhất

| Thành phần | Dùng cho | Quy tắc |
|---|---|---|
| Nuxt 4 + Vue | SPA JavaScript, route, component, composable, trạng thái | Dùng auto-import chuẩn; không thêm framework hoặc store thứ hai |
| Tailwind 4 + CSS chung | Layout, token Butter/olive, chữ, focus, motion | Tái dùng token/component có sẵn; không cài thêm bộ UI kit |
| vue-i18n | Tiếng Việt/Anh | Nhãn, lỗi và trạng thái đều có khóa ở cả hai bản ngôn ngữ |
| oidc-client-ts | SSO/PKCE, access token | Chỉ qua useAuth; không tự lưu thêm bản token ở component |
| ECharts core | Biểu đồ cần thiết | Import module dùng thật, tải theo route; hủy chart/ResizeObserver khi rời trang |
| Ajv (devDependency) | Biên dịch schema thành validator lúc build | Không đưa engine/eval vào trình duyệt; không sao chép luật BE để tự mở quyền |

Bốn runtime dependencies hiện có đều được sử dụng. Đợt cải thiện này không thêm package. Các font WOFF2 là tài sản
tĩnh tự phục vụ, kèm giấy phép/manifest; không có request đến Google Fonts khi người dùng chạy ứng dụng.

## Tổ chức mã

- `app/pages`: ghép dữ liệu, quyền hiển thị theo claim, trạng thái tải/lỗi/rỗng và thao tác của một màn.
- `app/components`: UI có runtime props/emits rõ ràng. Khi chuyển TypeScript sang JavaScript, không để mất khai báo props.
- `app/composables/useApi.js`: giao tiếp qua gateway và chuẩn hóa lỗi. Không báo lưu thành công từ HTTP lỗi/JSON thiếu data.
- `app/composables/useAuth.js`: chủ sở hữu duy nhất của phiên SSO. Không gọi dịch vụ AI hoặc DB trực tiếp từ FE.
- `app/utils`: hàm thuần cho chuyển đổi, hiển thị và kiểm tra; có test khi chứa quyết định nghiệp vụ/edge case.
- `app/assets/css/main.css`: token, control, shell, motion và breakpoint chung. Theme đăng nhập/cá nhân giữ cùng font và nhận diện.

Dùng `ref` cho trạng thái ngắn trong component; `useState` cho trạng thái cần giữ qua route như bộ lọc Hộp việc.
Không thêm thư viện chỉ để thay vài dòng Vue/CSS hoặc API trình duyệt đã có.

## Vòng làm việc

1. Ghi màn, người dùng, công việc chính và API hiện có. Giữ brief Butter/sans/sidebar đã chốt.
2. Đọc Taste app-screen và Impeccable theo phạm vi; đối chiếu ảnh thật, không lấy detector xanh làm kết luận thiết kế.
3. Sửa FE, có đủ trạng thái thực tế: dữ liệu, rỗng, tải, lỗi/thử lại, thiếu quyền, đang gửi và reduced motion.
4. Chạy `node apps/office/scripts/check.mjs` và unit tests liên quan. Test hành vi/hợp đồng từng gây lỗi.
5. Dựng lại image FE, xác nhận container dùng bản mới; chạy E2E qua SSO/gateway thật với WAF bật.
6. Xem ảnh ở 1440/768/390, đo font/contrast/target/overflow, kiểm tra bàn phím; sửa lỗi nhìn thấy dù test vẫn xanh.
7. Kiểm tra dependency diff, giấy phép và Git. Không sửa nguồn BE/AI để làm cho test FE xanh.

Nếu lỗi nằm ở BE/AI, lưu báo cáo có baseline, bước tái hiện, trạng thái thật và điều cần xác nhận. Không tự sửa
source, tái tạo dữ liệu hoặc tạo workaround trái với quyết định của người dùng.

## Giữ ngữ cảnh khi làm dài

Checkpoint nội bộ ở `.cache/goal-continuation.md` ghi baseline bất biến, thay đổi đang làm, handle tiến trình,
đường dẫn bằng chứng, kết quả đã xác minh và việc còn thiếu. Dùng log/artifact cục bộ thay vì đổ toàn bộ output vào chat.
Khi tiếp tục, đọc Git/runtime/test hiện tại; không coi bản tóm tắt là bằng chứng hoàn tất. Không lưu bí mật vào tài liệu commit.
