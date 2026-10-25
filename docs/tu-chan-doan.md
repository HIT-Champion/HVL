# Tự chẩn đoán mức trưởng thành H-P-D-I (F4.7)

Bài giới thiệu chủ đề OLP 2026 (VFOSSA, bài 761) xếp **ban lãnh đạo** vào nhóm tác nhân đầu tiên của DX-Lab: dùng
khung đo lường để chẩn đoán thực trạng tổ chức. Trang **Tự chẩn đoán** `/tu-chan-doan` của Văn phòng điện tử là
khung đó ở dạng làm được ngay: lãnh đạo trả lời 12 câu theo bốn không gian [H] Con người, [P] Quy trình, [D] Dữ liệu,
[I] Trí tuệ, xem radar, chỗ lệch nền, không gian nên làm trước và bước tiếp theo trỏ vào đúng phân hệ của Signet.
Điểm khác với một bảng hỏi thuần: cạnh mỗi không gian là **bằng chứng đo được** — số Signet tính từ chính dữ liệu của
đơn vị — để lãnh đạo đối chiếu điều mình tự khai với điều hệ thống thấy. Mức hoàn thiện ở
[`muc-hoan-thien.md`](muc-hoan-thien.md).

> **Không phải bộ chỉ số chính thức.** Câu hỏi do đội Signet tự viết. Trang không tính điểm DTI, không quy đổi sang
> bất kỳ thang nào của cơ quan nhà nước. Tỷ trọng H-P-D-I và hình dạng (mục 3) chỉ là ước lượng theo công thức của
> giáo trình DX-OS, lấy mức tự đánh giá thay cho điểm DTI, để định hướng. Bộ câu chưa thử với đơn vị thật nào (mục 6).

## 1. Dùng thế nào

| Ai | Làm được |
|---|---|
| Lãnh đạo đơn vị (`director`) | Trả lời, xem kết quả, bước tiếp theo; thấy bằng chứng đo được của đơn vị; lưu kết quả kèm ghi chú; xem lịch sử các lần lưu của đơn vị, radar chồng lần lưu trước; "Điền theo lần lưu gần nhất" để đánh giá lại nhanh |
| Lãnh đạo phòng (`manager`) | Trả lời, xem kết quả, bước tiếp theo trên trình duyệt của mình; không lưu, không có bằng chứng (các khung nhìn số đo chỉ lãnh đạo đơn vị đọc); trang chỉ lãnh đạo đơn vị mở được hiện tên, không có liên kết |
| Vai trò khác | Không có mục trên thanh bên; mở thẳng đường dẫn thì trang báo không có quyền |

Mỗi câu có 5 mức, mô tả điều **quan sát được** trong đơn vị (ví dụ "Mở bảng điều hành là có số, tính từ chính dữ liệu
vận hành tại thời điểm xem"), không phải cảm nhận. Câu đã chọn được giữ trong thẻ trình duyệt (`sessionStorage`) tới
khi rời trang, như form soạn văn bản — hết phiên đăng nhập giữa chừng không mất bài.

Bộ câu nằm ở [`apps/office/app/data/tu-chan-doan.json`](../apps/office/app/data/tu-chan-doan.json), có JSON Schema
cùng thư mục; mỗi câu có tiêu đề, câu hỏi, đúng 5 mức, một câu "bước tiếp theo", 1–3 liên kết, cả tiếng Việt và tiếng
Anh. Sửa câu chữ thì sửa tệp này; đổi ý nghĩa câu thì đổi cả `id` của bộ câu (đang là `hpdi-1`) để lịch sử không trộn
hai bộ khác nhau.

## 2. Nguồn khung tham chiếu

| Nguồn | Lấy gì | Không lấy gì |
|---|---|---|
| VFOSSA, [Giới thiệu mô hình DX-OS và chủ đề cuộc thi Phần mềm nguồn mở OLP 2026](https://vfossa.vn/tin-tuc/gioi-thieu-mo-hinh-dx-os-va-chu-de-cuoc-thi-phan-mem-nguon-mo-olp-2026-761.html) (09/06/2026; tóm tắt ở [`du-thi/olp-2026-brief.md`](du-thi/olp-2026-brief.md) §1.2–1.3, §2.3) | Định nghĩa bốn không gian (H: môi trường làm việc số tích hợp — SSO, P.A.R.A, cổng nội bộ; P: luồng việc tự động, Poka-yoke; D: nguồn sự thật duy nhất, dashboard thời gian thực; I: tác tử tự hành); nguyên lý **tiến hóa tuyến tính bắt buộc** và **human-in-the-loop**; nhóm tác nhân lãnh đạo | — |
| Giáo trình [DX-OS, chương 2](https://opendigitransform.gitbook.io/dx-os/phan-i-tu-duy-chien-luoc/chuong-2-mo-hinh-hpdi-va-phuong-phap-danh-gia-nang-luc-so-dti) của TS. Tạ Tuấn Anh, giấy phép [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (đọc ngày 25/10/2026) | Mục 2.1: năm nấc vai trò của con người (từ "người thực thi" tới "kiến trúc sư") — gợi ý cho câu H3; mục 2.4.2: công thức tỷ trọng `X% = DTI_X / max × X_supp × 30%`, `H% = 100 − (P + D + I)`; mục 2.4.3: bốn nguyên mẫu trên radar tỷ trọng (Mũi giáo phân mảnh, Cánh diều lệch tâm, Ảo giác công nghệ, Kim cương toàn vẹn) và rủi ro "rác vào, rác ra" của Ảo giác công nghệ — cơ sở của tỷ trọng, hình dạng, cảnh báo GIGO (mục 3); mục 2.6: hỏi "mất bao lâu để có con số" — gợi ý cho câu D1 | Không chép câu hỏi Mini-DTI (mục 2.6); không có điểm DTI đầy đủ và hệ số thực chứng: tỷ trọng dùng mức tự đánh giá thay cho `DTI_X / max` và `X_supp = 1` (mục 3); không đặt tên mức theo 5 cấp DTI — mục 2.2 nói rõ 5 cấp DTI và 5 nấc HPDI là hai thước đo khác nhau; không lấy mã, ngưỡng của bài dự thi nào khác |

Mục 2.2 của giáo trình ghi khung DTI doanh nghiệp kế thừa Quyết định 1567/QĐ-BKHCN; đội chưa đọc văn bản gốc của
quyết định này và trang không dùng gì từ đó.

## 3. Cách chấm

Phép tính ở [`apps/office/app/utils/hpdi.ts`](../apps/office/app/utils/hpdi.ts), không có chữ hiển thị; test ở
`apps/office/tests/hpdi.test.ts`.

- **Điểm không gian** = trung bình mức các câu của không gian đó, làm tròn 2 chữ số (1,00–5,00). Khi lưu, CSDL tính
  lại từ câu trả lời theo đúng cách này (mục 5) — người gửi không chọn được điểm. Trang hiện điểm với 1 chữ số thập
  phân (2,67 hiện là 2,7); so lệch nền và chọn không gian nên làm trước dùng điểm 2 chữ số.
- **Lệch nền**: theo nguyên lý tiến hóa tuyến tính H → P → D → I, cặp liền kề mà không gian sau cao hơn không gian
  ngay trước **từ 1 mức trở lên** (vd [I] 4, [D] 2). Trang cảnh báo: không gian sau dựng trên nền chưa vững dễ thành
  "rác vào, rác ra".
- **Nên làm trước**: xét các không gian từ [H] tới không gian đứng trước chỗ lệch nền đầu tiên (không có lệch nền thì
  xét cả bốn), chọn điểm thấp nhất; bằng nhau lấy không gian đứng trước; cả bốn đạt 5 thì không có. Ví dụ H 3, P 2,
  D 4, I 1: [D] vượt [P] nên chỉ xét [H], [P] → làm [P] trước, dù [I] thấp nhất. Không gian nên làm trước là [I]
  (không lệch nền, [I] thấp nhất) thì trang nói ba không gian trước đã cao hơn, không nhắc "không gian sau".
- **Bước tiếp theo** của mỗi không gian: câu có mức thấp nhất (dưới 5) của không gian đó, bằng nhau lấy câu đứng
  trước; hiện câu "bước tiếp theo" của câu hỏi và liên kết tới trang Signet tương ứng. Mọi liên kết là trang có thật:
  test đối chiếu từng liên kết với `app/pages/` của Văn phòng điện tử, hoặc với route `/ca-nhan` của APISIX (Không
  gian cá nhân P.A.R.A).
- Liên kết **theo vai trò người xem**: liên kết tới trang chỉ một số vai trò mở được khai `roles` trong tệp JSON (vd
  Điều hành, Số đo: `director`; Tiếp nhận văn bản: `clerk`). Người xem không thuộc các vai trò đó thì trang hiện tên
  trang và vai trò làm việc đó ("Điều hành (trang của Lãnh đạo đơn vị)"), không có liên kết. Test chạy đúng điều
  kiện vai trò của từng mục menu trong `layouts/default.vue` (và `hasSpace` của Không gian cá nhân) để đối chiếu:
  `roles` khai đúng như menu, lãnh đạo phòng không được dẫn tới Điều hành, Số đo, Sổ đăng ký, Sổ kiểm toán, và không
  ai được dẫn tới trang Tiếp nhận văn bản (trang chuyển vai trò khác văn thư về Văn bản đến).

- **Tỷ trọng** (giáo trình mục 2.4.2): `P% = (mức P − 1) / 4 × 30 %`, `D%`, `I%` như vậy (mức 1 → 0 %, mức 5 →
  30 %); `H% = 100 % − (P% + D% + I%)` là phần việc còn lại trên vai con người. Giáo trình nhân thêm hệ số thực chứng
  (phần mềm có liên thông thật không); trang lấy bằng 1 vì mỗi mức của bộ câu đã tả việc quan sát được, không tả phần
  mềm sở hữu, còn bằng chứng đo được (mục 4) đặt cạnh để đối chiếu chứ không nhân vào. Điểm không gian [H] của bộ câu
  (không gian làm việc số) không vào công thức: H% của giáo trình là phần dư, không phải mức của không gian [H]. Đủ
  mức 5 ra đúng Kim cương của giáo trình: [H] 10 %, ba trục kia 30 %.
- **Hình dạng** (giáo trình mục 2.4.3): xét theo thứ tự, luật đầu tiên khớp. Ngưỡng có số lấy từ giáo trình; chỗ
  giáo trình chỉ tả bằng lời ("co cụm sát tâm", "triệt tiêu", "vươn dài") thì đội lấy một phần ba trục (10 %).

  | Hình dạng | Luật | Giáo trình tả |
  |---|---|---|
  | Kim cương toàn vẹn | [P], [D], [I] đều từ 22,5 % (mức 4) | "[P], [D], [I] mở rộng đối xứng, đạt đỉnh 30 % mỗi trục", [H] 10 % |
  | Ảo giác công nghệ | [D] hoặc [I] từ 10 %, vượt [P], và [P] dưới 20 % | "Trục [I] hoặc [D] vươn dài … đi kèm sự suy giảm của trục [P]"; rủi ro GIGO |
  | Cánh diều lệch tâm | [P] từ 20 %, [D] và [I] dưới 10 % | "[P] … (20 % – 30 %). Trục [D] và [I] vẫn ở trạng thái triệt tiêu" |
  | Mũi giáo phân mảnh | [H] từ 80 % | "[H] (chiếm 80 % – 90 %)" |
  | Đang chuyển tiếp | không khớp luật nào | giáo trình chỉ tả bốn nguyên mẫu "phổ biến" |

- **Rác vào, rác ra (GIGO)**: [I] cao hơn [D] từ 1 mức (lệch nền D → I), hoặc hình dạng Ảo giác công nghệ. Trang
  khuyên tạm dừng mở rộng [I] (gợi ý của tác tử, hỏi đáp AI), chuẩn hóa [P], [D] trước, và dẫn tới mục "Kiểm chất
  lượng số liệu" của trang Phả hệ số liệu (`/pha-he#chat-luong`) — cờ Đạt / Cảnh báo / Trượt của các báo cáo, chỉ lãnh
  đạo đơn vị xem được; lãnh đạo phòng thấy tên trang và vai trò.

Ngưỡng 1 mức, quy tắc "nên làm trước", cách quy mức sang tỷ trọng, hệ số thực chứng bằng 1 và ngưỡng một phần ba trục
là lựa chọn của đội để diễn đạt nguyên lý của bài 761 và giáo trình, không có trong tài liệu của Ban tổ chức.

## 4. Bằng chứng đo được

Chỉ dùng số **đã có** trong Signet, đọc bằng token của lãnh đạo đơn vị qua Hasura (lọc theo đơn vị, như dashboard).
Không có view mới. Chỉ số nào chưa có dữ liệu (không có dòng, mẫu số 0) thì **không hiện** — không ghi 0 %. Số chỉ đặt
cạnh câu tự đánh giá; trang không quy số đo ra mức.

| Không gian | Chỉ số | Nguồn |
|---|---|---|
| [H] | Điểm hài lòng trung bình của người dùng, số góp ý | `office_v_feedback_summary`, dòng mọi màn hình (F4.6) |
| [P] | Văn bản đến đang quá hạn | `office_v_document_counts` (F3.11), không kể văn bản hạn chế, đã hủy |
| [P] | Tỷ lệ quá hạn trong số văn bản đã rõ đúng hay trễ hạn | `office_v_overdue_rate`, dòng mọi tháng (F4.6) |
| [P] | Trung vị thời gian từ khi văn bản đến tới khi được giao | `office_v_time_to_assign`, dòng mọi tháng (F4.6) |
| [D] | Văn bản trên hệ thống, không tính văn bản đã hủy (đến, đi; cả văn bản hạn chế) | `office_v_document_counts` |
| [D] | Văn bản đã lưu trữ (nộp lưu) | `office_v_document_counts`, trạng thái `archived` |
| [D] | Hồ sơ đã nộp lưu / tổng số hồ sơ | `office_case_files` (F3.8), chỉ cột `status` |
| [I] | Trường gợi ý đọc văn bản đến được văn thư giữ nguyên | `office_v_intake_accuracy` (F4.1) |
| [I] | Gợi ý giao việc giữ đúng phòng chủ trì | `office_v_assignment_suggestion_accuracy` (F4.3), văn bản đã giao |

Văn bản hạn chế không lộ trạng thái trong view (cột `status` rỗng) nên vào tổng số văn bản, kể cả khi đã hủy. Hồ sơ
đếm ở giao diện từ cột `status` của từng hồ sơ: lãnh đạo đơn vị không có quyền aggregate trên `office_case_files`
(bảng của F3.8), thêm quyền đó là đổi quyền của tính năng khác nên chưa làm.

**Không hiện** vì lãnh đạo không có nguồn đọc được: tỷ lệ văn bản đi được ký số (`core.file_signatures` không vai
trò người dùng nào đọc, `office.issued_documents` chỉ cổng xác thực đọc), số người dùng đăng nhập một lần, mức dùng
Không gian cá nhân (mỗi người chỉ thấy mục của mình). Thêm các số này cần view số đếm mới và quyết định quyền — chưa
làm. Trên đơn vị mẫu của `make seed`, trang ghi rõ số tính trên dữ liệu mẫu (cột `sample`, như trang Số đo).

## 5. Lưu lịch sử

Migration `1792281603100_maturity_assessments`, metadata `office_maturity_assessments.yaml`; mô hình dữ liệu ở
[`mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md) §2.7.

- Mỗi lần lưu một dòng `office.maturity_assessments`: phiên bản bộ câu (`framework`), câu trả lời (`answers`, mã câu →
  mức), điểm `h`, `p`, `d`, `i`, ghi chú tối đa 300 ký tự, giờ lưu. Thuê ước và người lưu Hasura đặt từ token.
- Trigger `maturity_assessments_guard` biết bộ mã câu của từng phiên bản: `hpdi-1` là 12 câu h1–h3, p1–p3, d1–d3,
  i1–i3 (test office đối chiếu với tệp JSON). Trigger kiểm `answers` có đủ đúng các mã đó, không thừa, mỗi mức là số
  nguyên 1–5 (sai thì lỗi `maturity_answers: …`); phiên bản lạ bị chặn (`maturity_framework`). Rồi tính bốn điểm,
  gọt ghi chú, đặt giờ lưu. Đổi bộ câu thì thêm phiên bản mới bằng migration.
- Chặn lưu dồn như góp ý: mỗi đơn vị tối đa 5 lần lưu mỗi giờ, 20 lần mỗi 24 giờ (lỗi `maturity_rate: …`, trang dịch
  thành câu tiếng Việt). Khóa tư vấn theo đơn vị xếp hàng các lần lưu song song; mutation nhiều dòng cũng bị đếm.
- Chỉ lãnh đạo đơn vị thêm và đọc, trong đơn vị mình; không đọc cột `created_by` — lịch sử là của đơn vị, ai lưu thì
  xem ở Sổ kiểm toán. Không vai trò nào sửa, xóa. Mỗi lần lưu là một dòng sổ kiểm toán chuỗi băm (`core.audit()`).

## 6. Giới hạn

- Bộ câu tự viết, chưa thử với đơn vị thật nào, chưa kiểm độ tin cậy (hai người cùng đơn vị có chọn giống nhau không).
  12 câu là ít so với bộ chỉ số DTI; đây là công cụ mở đầu cuộc trao đổi của ban lãnh đạo, không phải đánh giá.
- Một người trả lời cho cả đơn vị. Giáo trình (mục 2.2) khuyên khảo sát chéo ba tầng (lãnh đạo, quản lý cấp trung,
  nhân viên); trang chưa gom câu trả lời của nhiều người.
- Bằng chứng đo được chỉ phủ phần việc văn bản mà Signet quản lý; đơn vị dùng phần mềm khác cho việc khác thì số không
  phản ánh phần đó. Trên bản demo, số tính trên dữ liệu mẫu (vài giây mỗi bước, không phải nhịp làm việc thật).
- Lãnh đạo phòng không lưu được và không thấy bằng chứng của đơn vị.
- Tỷ trọng và hình dạng dựng trên mức tự đánh giá, không trên điểm DTI và hệ số thực chứng như giáo trình: hai đơn vị
  cùng hình dạng chưa chắc cùng thực trạng. Chỉ để gợi chuyện, không dùng để xếp hạng.
- Mỗi đơn vị lưu tối đa 5 lần mỗi giờ: đủ cho một buổi đánh giá lại, nhưng chạy e2e quá 5 lần trong một giờ trên cùng
  CSDL sẽ đỏ ở bước lưu.

## 7. Kiểm

```bash
cd apps/office && npm test                               # tests/hpdi.test.ts: bộ câu, liên kết, chấm điểm, hình dạng
db/tests/stack.sh up && cd db/tests && MOC_IT=1 .venv/bin/python -m pytest test_maturity.py   # quyền, trigger, sổ
make e2e                                                 # tests/e2e/tu-chan-doan.spec.ts, cần hệ thống đang chạy
```
