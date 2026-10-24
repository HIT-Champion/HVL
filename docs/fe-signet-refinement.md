# Signet — nhận diện và tinh chỉnh UI ngày 24/10/2026

Người dùng yêu cầu sans, tăng độ rõ chữ/màu, thu vùng đọc và giữ mật độ thoáng vừa để đọc từng công việc.
Đã hỏi hai vòng: hướng logo/mật độ, rồi chọn giữa ba SVG; người dùng chọn Liền mạch.

## Kết quả

- Logo Liền mạch dùng trong sidebar, trạng thái thu gọn, favicon, xác thực công khai và SSO.
- Xuất SVG đầy đủ đã outline chữ, biểu tượng riêng và các bản một màu; không phụ thuộc font máy nhận.
- Be Vietnam Pro400/500/600/700 được tự phục vụ, có giấy phép OFL-1.1 và attribution.
- Butter đậm hơn ở sidebar, nền nội dung trung tính, chữ mực đậm, attention trắng ấm/viền ochre.
- Hộp việc tối đa1080px, rút phần đầu trang, nhóm24px; giữ title→nguồn→hạn→mở việc.
- Control mobile phân bổ lại chiều rộng, màn rất hẹp xếp loại văn bản riêng hàng.
- Không đổi dữ liệu, API, logic nghiệp vụ hay code BE/AI.

## Dùng skill

Taste app screens giữ hướng Butter đã được chọn, không bốc lại một thiết kế khác.
Impeccable layout/typeset dùng một lượt đánh giá độc lập, sau đó sửa nguồn và đối chiếu render.
Các token/design sidecar/surface brief được cập nhật theo source; không coi lint pass là nghiệm thu thẩm mỹ.

## Bằng chứng local

Compiler JS/Vue qua; 3 E2E responsive/sidebar/retry qua sau logo. 25 route/viewport qua trước logo;
7 capture inbox/ask sau logo qua. SSO và public header đã kiểm font, logo và không có biểu tượng lặp.
Taste đo0 FAIL/0 WARN sau sửa tương phản nhãn vai trò; chỉ cho phép palette-cream theo yêu cầu vintage.
Impeccable detector không có findings. REUSE kiểm bản quyền/giấy phép qua.

Ảnh, log và board tương tác tại `.cache/signet-refinement/` (không commit); Taste tại
`apps/office/.taste-skill/signet-refinement-final/`. Chạy ứng dụng: http://localhost:8080.
