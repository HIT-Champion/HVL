# Kế hoạch 4 tuần cho vòng cấp trường

> Viết ngày 10/09/2026. Giả định: vòng cấp trường diễn ra khoảng **10/10/2026**, chấm theo tinh
> thần thể lệ OLP (repo + trình diễn), đội 3 người, mỗi người 10–15 giờ mỗi tuần, máy dev 16 GB.
> Nếu ngày hoặc tiêu chí khác, sửa mục 1 trước rồi mới sửa lịch.
>
> Nguyên tắc duy nhất của bản này: **một luồng chạy thật xuyên bốn trục, cài được trên máy sạch,
> repo sạch PoF**. Mọi thứ không phục vụ ba điều đó hoãn sau vòng trường.
>
> **Sửa đổi 10/09 (chiều), sau đợt bằng chứng 2 trong `du-bao-de-thi-2026.md` mục 2.2–2.3:** luồng
> demo là **DX-Ticket theo hộp cát Alpha của giáo trình** (khách hàng gửi yêu cầu bảo hành, khiếu nại,
> tư vấn), seed từ chính CSV của hộp cát. An toàn xưởng (`dac-ta-dx-safety.md`) lùi thành gói lĩnh
> vực thứ hai sau vòng trường. Mọi cơ chế lõi (máy trạng thái, Poka-yoke, ngoại lệ, tác tử, H%) giữ
> nguyên; chỉ đổi tên thực thể: `incidents` → `tickets`, `areas/equipment` → `customers`, sự kiện
> "Nghiêm trọng → dừng máy" → "Khiếu nại → cảnh báo Telegram", ngoại lệ "vận hành khi sự cố mở" →
> "cấp voucher / đền bù vượt thẩm quyền" (đúng cổng phê duyệt của bài 8.5).

---

## 1. Mục tiêu và tiêu chí thắng

Sau 4 tuần, ban giám khảo cấp trường phải thấy được trong 7 phút:

1. Khách hàng gửi yêu cầu từ điện thoại (số điện thoại 10 số, loại yêu cầu, ảnh lỗi), bị chặn khi
   sai định dạng; hệ thống tự tìm hoặc tạo khách theo số điện thoại. *(H, P)*
2. Nhân viên bấm Nhận, bị chặn khi Đóng mà thiếu Hướng xử lý; khiếu nại mới bắn cảnh báo Telegram. *(P)*
3. Tác tử đọc lịch sử khách, trích dẫn chính sách bảo hành trong `[R]`, đề xuất ưu tiên và soạn
   email, **dừng chờ duyệt** vì đề xuất cấp voucher. *(I)*
4. Đề xuất voucher đó đi vào bàn phê duyệt ngoại lệ: chấm rủi ro, dẫn tiền lệ, quản lý duyệt có điều
   kiện; khách nhận email CSAT khi đóng. *(P, I)*
5. Dashboard đổi số ngay sau thao tác, radar H% có đường lịch sử. *(D)*
6. Trang Releases có `v0.2.0` với `.tar.gz` + `.sha256`; README có build from source đã chạy trên máy
   sạch; `DEPENDENCIES.md` sinh tự động. *(PoF)*

Không cần cho vòng trường: Nextcloud, Nextcloud Talk, gói `dx-ticket`, xuất JSON-LD, hai thử
nghiệm phòng sốc (XML hóa đơn, NGSI-LD), thử Frappe. Tất cả chuyển sang tháng 10–11 trong
`du-bao-de-thi-2026.md` mục 5.

---

## 2. Quyết định chốt ngay để không mất tuần đầu

| Quyết định | Chốt | Lý do |
|---|---|---|
| QĐ-004 nền [P] | **Appsmith CE**, không thử Frappe | Apache-2.0, image chính thức sạch, form công khai và RLS theo claim OIDC làm được; không còn thời gian so sánh |
| QĐ-005 kênh cảnh báo | **Telegram bot qua Node-RED** cho vòng trường; ghi rõ là dịch vụ ngoài, tùy chọn | Cài trong một giờ; Talk cần Nextcloud, hoãn |
| Kho tài liệu `[R]` | Thư mục `resources/` trong repo, mount vào container tác tử | Đủ để RAG chạy; Nextcloud thay vào sau, cấu trúc P.A.R.A giữ nguyên |
| Dashboard | **Apache Superset** nếu dựng xong trong tuần 3; dự phòng là biểu đồ ngay trong Appsmith | Không để dashboard chặn demo |
| Ngoại lệ | Chỉ làm **một loại**: Vận hành khi sự cố mở | Đủ kể câu chuyện; ba loại còn lại sau |
| Đồng hồ H% | Một view SQL tính ba hệ số + radar trên Superset | Không làm bảng hỏi DTI, lấy DTI_X = 1 |
| LLM | Ollama + Qwen2.5-7B, embedding bge-m3, pgvector | Máy 16 GB chạy được; không dùng API ngoài trong demo |

---

## 3. Lịch tuần

### Tuần 1 (10–17/09): hạ tầng chạy, repo sống

| Việc | Ai | Xong khi |
|---|---|---|
| Cài plugin `docker compose`; `make up-h` chạy Postgres + Keycloak; `make up-p` thêm Appsmith + Node-RED; ghim tag image | A | `make ps` xanh; số RAM ghi vào `architecture.md` |
| `db/schema.sql`: `customers` (7 cột như hộp cát), `tickets` (17 cột bài 6.8), `people`, `kb_scenarios`, `exceptions`, `events`; hàm chuyển trạng thái; trigger cấm `UPDATE status` trực tiếp; `make seed` nạp CSV Alpha (7 khách, 14 ticket) rồi sinh thêm 80 ticket 90 ngày | B | `make seed` thoát 0; `make seed FROM=<csv>` nạp được tệp cùng cấu trúc; `UPDATE tickets SET status` bị từ chối |
| Keycloak realm `dxlab`, 5 vai, 14 tài khoản demo, client cho Appsmith và Superset; script import realm | C | Đăng nhập Appsmith bằng Keycloak được |
| Merge nhánh docs; mở 10 issue theo bảng này; commit mỗi ngày từ cả 3 tài khoản | A | `git shortlog -sn` có 3 người |
| **`v0.1.0`** ngay khi `make up-p` chạy: `make release VERSION=0.1.0`, tải `.tar.gz` + `.sha256` lên Releases | A | Trang Releases có gói do đội sinh |

### Tuần 2 (18–24/09): luồng [P] chạy tay từ đầu đến cuối

| Việc | Ai | Xong khi |
|---|---|---|
| Form công khai Appsmith cho khách: SĐT `^[0-9]{10}$`, email, dropdown loại yêu cầu, ảnh lỗi từ camera, nội dung ≥ 20 ký tự; tìm/tạo khách theo SĐT | B | Gửi sai SĐT bị chặn ở cả form lẫn backend |
| Màn hình hàng đợi "Chờ xử lý" và ticket của tôi; nút Bắt đầu xử lý / Kết thúc xử lý chỉ hiện đúng tiền điều kiện; Kết thúc bắt buộc Hướng xử lý; RLS `Trạng_Thái='Chờ xử lý' OR Nhân_Sự_Phụ_Trách = tôi` | B | Nhân viên A không thấy ticket đang xử lý của B |
| Node-RED: sự kiện (a) ticket mới → tìm/tạo khách + email xác nhận + đánh thức tác tử; (b) Đang xử lý và loại Khiếu nại → Telegram "🚨 CẢNH BÁO KHIẾU NẠI MỚI"; (c) Đóng → email CSAT; (d) quét ticket quá 15 phút chưa Đang xử lý; cột `Log_Email` chống trùng | A | Bốn luồng trong `config/node-red/flows.json`, không có `localhost` |
| Màn hình ngoại lệ: đề xuất voucher/đền bù từ tác tử hoặc nhân viên → chờ duyệt → duyệt có điều kiện / từ chối / thu hồi; trigger chặn xin lại trùng | C | Kịch bản mục 1 điểm 4 chạy tay được |
| `seed/`: CSV Alpha + 80 ticket 90 ngày, 9 ngoại lệ, 12% sự kiện `blocked`; `resources/` có chính sách bảo hành, đền bù, kịch bản xử lý 25 tình huống dạng Markdown | C | Dashboard tuần 3 có dữ liệu; RAG có tài liệu |
| CI: thêm kiểm tra không tệp > 2 MB, không `.env`, không `localhost` trong mã | A | CI fail khi cố tình vi phạm |

**Cổng kiểm tra cuối tuần 2:** một người ngoài đội làm được điểm 1, 2, 4 của mục 1 mà không cần
hướng dẫn miệng. Nếu chưa, tuần 3 ưu tiên sửa luồng, dashboard lùi.

### Tuần 3 (25/09–01/10): [D] và [I]

| Việc | Ai | Xong khi |
|---|---|---|
| Superset: kết nối Postgres, KPI đúng giáo trình (tổng ticket, CSAT trung bình, thời gian xử lý trung bình; tồn đọng, cơ cấu loại yêu cầu, cảnh báo độ trễ, tải theo nhân sự, bảng quá hạn) + ngoại lệ theo loại + tỷ lệ bị chặn; nhúng vào cổng | C | Số đổi trong 1 phút sau thao tác |
| View `hpdi_monthly` tính `P_supp`, `D_supp`, `I_supp` từ `events`; radar 4 trục có lịch sử tuần | C | Radar có đường thay đổi sau khi thêm sự cố |
| Dịch vụ `i-agent` theo 9 bước bài 8.5: nạp chính sách bảo hành/đền bù và `kb_scenarios` vào pgvector; ticket mới → đọc lịch sử khách, chấm rủi ro, đề xuất ưu tiên, soạn email nháp, **tạo đề xuất voucher vào bàn ngoại lệ thay vì tự cấp**; in `[CHƯA CÓ TIỀN LỆ]` khi không khớp; ghi `events` với `actor = agent:ticket-v1` | B | Hai kịch bản mục 1 điểm 3 và 4 chạy với LLM cục bộ dưới 20 giây |
| `scripts/deps-audit.sh`: đọc `docker-compose.yml`, kéo nhãn image, sinh `DEPENDENCIES.md`; nối vào CI với allowlist SPDX | A | `DEPENDENCIES.md` không còn dòng "chưa chốt" |
| Viết `docs/build-from-source.md`; chạy thử trên máy sạch (VM hoặc máy bạn) và ghi thời gian | A | Người khác cài xong dưới 30 phút |

**Cổng kiểm tra cuối tuần 3:** chạy trọn 6 điểm của mục 1 một lần, quay màn hình làm video dự phòng.

### Tuần 4 (02–09/10): đóng băng, luyện, hồ sơ

| Việc | Ai | Xong khi |
|---|---|---|
| Đóng băng tính năng từ 02/10; chỉ sửa lỗi có issue | cả đội | Không có commit `feat:` sau 02/10 |
| `docs/demo-script.md` 7 phút theo mục 1; luyện 3 lần, đo giờ; một người đóng vai giám khảo hỏi 5 câu khó | cả đội | Lần thứ 3 dưới 7 phút |
| Slide 8 trang: bài toán, H-P-D-I, kiến trúc, luồng, điểm nguyên gốc (ngoại lệ, H%), giấy phép, lộ trình tới tháng 12, đội | C | |
| README: ảnh chụp, kiến trúc, build from source, tài khoản demo; CHANGELOG cho `0.2.0`; NOTICE, header kiểm lại | A | `make lint` sạch; bảng `pof-checklist.md` tích hết mục làm được |
| **`v0.2.0`** trước 07/10 | A | Releases có 2 bản |
| Ghi lại vào `nghien-cuu-chu-de-2026.md` mục 6.4 những gì hoãn và ngày làm | B | |

---

## 4. Phân vai

| | A: hạ tầng và PoF | B: nghiệp vụ [P] và schema | C: định danh, [D], [I], trình bày |
|---|---|---|---|
| Sở hữu | Compose, Node-RED, CI, release, build from source, `DEPENDENCIES.md` | Schema, trigger, Appsmith, `i-agent` | Keycloak, Superset, H%, seed, slide |
| Nếu vắng một tuần | B nhận CI và release | A nhận Appsmith | B nhận Superset, A nhận slide |

Đồng bộ 15 phút mỗi ngày làm việc; mỗi việc là một issue; nhánh `feat/<trục>-<việc>`; PR nhỏ, một
người review; `main` luôn dựng được.

---

## 5. Rủi ro của 4 tuần này và cách cắt

| Rủi ro | Dấu hiệu | Cắt gì |
|---|---|---|
| Appsmith và Keycloak không bắt tay OIDC | Hết ngày 3 tuần 1 chưa đăng nhập được | Dùng đăng nhập nội bộ Appsmith cho vòng trường, giữ Keycloak cho SSO của Superset; ghi vào rủi ro |
| LLM cục bộ chậm trên máy demo | > 30 giây một lần gọi | Giảm xuống Qwen2.5-3B; nếu vẫn chậm, ghi sẵn kết quả tác tử vào seed và bật lại lúc hỏi đáp |
| Superset ngốn RAM, dựng không kịp | Hết tuần 3 chưa nhúng được | Biểu đồ trong Appsmith từ view SQL; radar vẽ bằng biểu đồ radar của Appsmith |
| Giám khảo hỏi "khác gì hộp cát Google của giáo trình?" | | Trả lời bằng ba thứ hộp cát không có: bàn ngoại lệ có tiền lệ, đồng hồ H% đo từ sự kiện, toàn bộ chạy cục bộ không một dịch vụ Google; và một thứ hộp cát có mà đội làm tốt hơn: nạp đúng CSV của hộp cát |
| Mỗi người ít giờ hơn dự kiến | Cuối tuần 2 chưa qua cổng kiểm tra | Bỏ ngoại lệ (điểm 4) và radar lịch sử; giữ 1, 2, 3, 5, 6 |

---

## 6. Sau vòng trường

Nếu qua vòng trường, quay lại lịch tháng 10–11 trong `du-bao-de-thi-2026.md` mục 5: gói
`safety` làm gói lĩnh vực thứ hai, Nextcloud thay `resources/`, thử nghiệm NGSI-LD trước rồi XML hóa
đơn, ba loại ngoại lệ còn lại, bảng hỏi DTI. Nếu không qua, repo vẫn là một dự án nguồn mở hoàn chỉnh để nộp thẳng cho OLP nếu trường
cho phép đăng ký tự do.
