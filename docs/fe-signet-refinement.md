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


## Edge navigation and motion — 24 October 2026

User requested flush sidebar edges, hover instead of a collapse button, and more smooth component motion. The focal interaction is a 320ms masked navigation reveal from a fixed 76px rail to a 244px overlay. The workspace does not move. Focus within expands it; pointer departure has a 140ms tolerance. No-hover devices use the existing accessible touch drawer, now flush to viewport edges. The stored collapse preference is no longer consumed.

Supporting feedback covers actual route changes, task-list filtering/reordering, notification popovers, transient notices, button presses, navigation icons and field focus. No animation dependency, scroll reveals or perpetual decorative motion was added. Reduced motion removes transitions and spatial effects.

Validation: 51 JavaScript/Vue files compile; all 3 responsive/recovery E2E cases pass, including rapid repeated hover, keyboard opening, stable main position, edge geometry, reduced motion, notification Escape and mobile focus return. Dedicated live captures verified 1440px rail/open navigation, notification popover and 390/320px mobile drawer without overflow or browser errors. Artifacts are local under `.cache/signet-refinement/sidebar-rail.png`, `sidebar-expanded.png`, `motion-notifications.png` and `edge-mobile-*.png`. This pass changes only FE, tests and design documentation; no push.


## Authentication and complete route consistency review — 24 October 2026

The sign-in screenshot exposed inherited Keycloak field framing and an earlier cached theme. Authentication now uses Be Vietnam Pro, the Liền mạch mark on Butter, neutral #f4f5f1, olive #555b3f actions, 12px panels and 8px controls. The new `signet.css` resource replaces `moc.css`. Upstream Keycloak templates, password toggling, invalid-credential validation, locale selection and OTP remain intact. A desktop inherited sizing issue found during screenshot review was corrected: the sign-in card now spans 480px instead of shrinking to284px.

Source review found two remaining serif overrides (document composition and document body); both now use the shared sans. Callback/loading/retry now has explicit bilingual copy and the same branded recovery composition. A custom bilingual404/error surface replaces the default Nuxt page and provides home/verification recovery. Q&A warnings now use the same SVG stroke language instead of Unicode warning symbols; excerpt boundaries are1px.

Coverage includes every production page route: inbox, incoming list/intake, outgoing list/compose, document detail, Q&A, cases, search, board, register, audit, public verification and authentication callback, plus the404 fallback. The live matrix covers29 work-route/viewport combinations across staff, clerk and director;13 authentication/public combinations cover Vietnamese/English sign-in,320/390/768/1440 widths, invalid credentials, OTP, public input/invalid result and callback error. Empty-filter recovery and drawer focus return were also exercised. This verifies the route families and sampled states, not every possible business record or administrative role.

Validation:52 JS/Vue files compile; all3 existing responsive/recovery E2E tests pass on the rebuilt production app, including real Keycloak login and OTP. Live captures have no horizontal document overflow, browser page errors or remaining visible serif UI. Local evidence: `.cache/signet-consistency/routes/measurements.json`, `auth-public.json`, screenshots and contact sheets. Screenshots were inspected; numerical checks alone were not treated as design acceptance.

The authentication theme must be mounted into Keycloak as described in `apps/office/README.md`; app-office rebuilding alone cannot deploy the separate authentication surface. No BE/AI source, root compose, realm policy or credentials were changed.
