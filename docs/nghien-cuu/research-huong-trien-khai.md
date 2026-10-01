# Nghiên cứu hướng triển khai DX-Lab OLP 2026

Ngày đối chiếu: 09/09/2026. Đây là đề xuất kỹ thuật của đội, chưa phải quyết định chốt domain hoặc diễn giải được BTC xác nhận.

## 1. Hướng đề xuất

**Xây dựng một DX-Lab có thể cài lại, mô phỏng quy trình CSKH hậu mãi/bảo hành thiết bị cho SME. Tận dụng phần mềm nguồn mở có sẵn, bổ sung cấu hình nghiệp vụ và mã tích hợp cần thiết.**

Ưu tiên thử **Frappe Framework + Frappe Helpdesk** làm nền nghiệp vụ, **Node-RED** nối luồng sự kiện. Sau khi chứng minh được luồng ticket, hoàn thiện H/D/I bằng các thành phần phù hợp. Dùng một repo dự thi làm điểm vào cho toàn bộ mã, cấu hình, hướng dẫn và bản phát hành.

Không cần tạo riêng một sản phẩm lớn từ đầu chỉ để repo dự thi build lại sản phẩm đó. Nếu cần module riêng, tạo một app mở rộng nhỏ, có source công khai và giấy phép phù hợp. Tách repo khi có nhu cầu bảo trì/tái sử dụng thực tế.

Đây là hướng chuẩn bị trước đề chính thức. Theo lịch BTC đã công bố, tháng 11/2026 mới có đề; khi đó phải đối chiếu lại domain, chức năng và cách nộp bài [1].

## 2. Kết luận có căn cứ và giới hạn

| Câu hỏi | Kết luận từ tài liệu |
|---|---|
| Có được tận dụng phần mềm có sẵn? | Có. Bài chủ đề yêu cầu chủ động nghiên cứu, tìm và lắp ghép nền tảng nguồn mở; đề cập low-code, workflow, API, BI và LLM [2]. |
| Có thể dùng nhiều phần mềm cho một không gian? | Phù hợp với định hướng lắp ghép. Bài chủ đề liệt kê nhiều nhóm chức năng trong mỗi không gian; không quy định mỗi trục đúng một phần mềm [2]. |
| Có phải không cần code? | Không có căn cứ để cam kết zero-code. Cấu hình có thể giải quyết nhiều phần; kiểm tra nghiệp vụ, tích hợp và đóng gói có thể cần mã riêng. Thể lệ không nêu số dòng code tối thiểu [1]. |
| Kéo Docker image về chạy có đủ? | Chứng minh được triển khai. Chưa tự chứng minh tiêu chí “cài đặt, biên dịch được từ mã nguồn” [1]. |
| Repo A lấy source repo B để build image có làm được? | Có về kỹ thuật. `frappe_docker` chính thức nhận danh sách app qua `apps.json` rồi xây dựng image chứa các app đó [6]. |
| Repo A như vậy chắc chắn đạt PoF không? | Chưa thể xác nhận. Nguồn đã đối chiếu chưa giải thích cụ thể phạm vi build/bundling của bài điều phối nhiều dịch vụ [1][2]. |
| Dùng bộ công cụ trong giáo trình nguyên xi được không? | Phải kiểm tra từng thành phần. Giáo trình minh họa cả Google Workspace/AppSheet và n8n; xuất hiện trong giáo trình không đồng nghĩa được cấp phép OSI [3][9]. |

Thể lệ có 50 điểm PoF và 50 điểm sản phẩm. Trong phần sản phẩm, tính nguyên gốc, hoàn thiện và thân thiện là những tiêu chí riêng. Vì vậy, chỉ dựng thành công các container chưa chứng minh đủ giá trị bài thi [1].

## 3. Chọn domain khi không có thời gian khảo sát doanh nghiệp

Giáo trình dùng DX-Ticket làm bài thực hành xuyên suốt; mục 6.2 mô tả khách hàng, ticket, phân công, trạng thái và đánh giá sau xử lý. Mục 9.2 khuyên bắt đầu từ bán hàng/CSKH, thay vì nghỉ phép, văn phòng phẩm hoặc đặt phòng họp [3][4].

| Phương án | Mức phù hợp với điều kiện đội | Quyết định đề xuất |
|---|---|---|
| CSKH hậu mãi/bảo hành thiết bị | Có bài mẫu DX-Ticket; thể hiện được nhiều vai trò, SLA, ngoại lệ và tra cứu chính sách | Ưu tiên |
| Bán hàng - kho - mua hàng | Có giá trị nhưng mở rộng nhanh sang tồn kho, giá, hóa đơn và kế toán | Để sau |
| Nghỉ phép/đặt phòng | Dễ mô phỏng, nhưng khó chứng minh tác động và chiều sâu H/P/D/I bằng CSKH | Không ưu tiên |

Đối tượng sử dụng trong kịch bản là CSKH, kỹ thuật viên và quản lý của một SME giả lập. Người dùng trực tiếp của sản phẩm DX-Lab còn có đội sinh viên/giảng viên muốn dựng môi trường để thực hành. Phân biệt hai nhóm này giúp thiết kế cả giao diện nghiệp vụ lẫn hướng dẫn cài lab.

Luồng đầu tiên:

```text
Khách gửi yêu cầu
  -> CSKH xác minh khách hàng và thiết bị
  -> Hệ thống kiểm tra dữ liệu, phân tuyến, theo dõi SLA
  -> Kỹ thuật viên chẩn đoán và cập nhật kết quả
  -> Quản lý duyệt ngoại lệ/chi phí nếu phát sinh
  -> CSKH bàn giao, đóng phiếu, lấy đánh giá
  -> Dashboard cập nhật; AI sử dụng chính sách và lịch sử được phép đọc
```

Phạm vi đầu tiên chỉ gồm khách hàng, thiết bị, ticket, nhiệm vụ xử lý, chính sách, phê duyệt và đánh giá. Chưa mở rộng sang kế toán, thanh toán hoặc quản lý kho linh kiện đầy đủ.

Không cần anh đi khảo sát để xây dựng sandbox này. Đội tự viết **chính sách giả lập có phiên bản**, công khai giả định và tạo dữ liệu tổng hợp. Nếu tham khảo chính sách công khai thì ghi nguồn; không tự nhận đã xác thực quy trình của doanh nghiệp thật. Nếu đề chính thức bắt buộc dữ liệu thực tế, phương án dữ liệu phải được điều chỉnh.

## 4. Bộ công cụ và lý do chọn

### Nền nghiệp vụ ưu tiên thử trước

**Frappe Framework (MIT) + Frappe Helpdesk (AGPLv3).** Helpdesk đã có cổng khách hàng/nhân viên, SLA, luật phân công và kho bài hướng dẫn. Frappe cung cấp cơ chế app mở rộng, DocType, API và xuất custom fields thành fixtures để đưa vào Git [5][7].

Điều này giảm phần phải tự làm như đăng nhập, CRUD, giao diện ticket và quản lý người dùng. Các trường thiết bị/bảo hành, ràng buộc chuyển trạng thái và phê duyệt ngoại lệ vẫn là phần cần thiết kế. Khả năng hiển thị custom fields trên đúng màn hình Helpdesk, và phối hợp workflow riêng với trạng thái ticket, cần thử trực tiếp trước khi chốt.

**Node-RED (Apache-2.0)** làm lớp tích hợp khi cần nối dịch vụ: nhận sự kiện, gọi API, chuyển thông báo, đồng bộ dữ liệu và gọi luồng AI. Upstream có hướng dẫn build bằng `npm ci` và `grunt build` [8]. Luật nghiệp vụ cốt lõi phải được kiểm tra ở backend nghiệp vụ, không chỉ nằm trong giao diện hoặc Node-RED.

**Phương án dự phòng:** nếu Helpdesk hạn chế tùy biến quá nhiều, thử dựng module DX-Ticket nhỏ bằng cơ chế low-code của Frappe. Zammad cũng là ứng viên ticket AGPLv3, nhưng Compose tham chiếu có thêm PostgreSQL, Redis, Memcached và Elasticsearch; cần đánh giá thêm chi phí vận hành và phần tùy biến [16]. Không có kết quả benchmark để kết luận nền nào nhẹ hơn.

### Kiến trúc đích để hoàn thiện H/P/D/I

Đây là danh sách ứng viên có vai trò cụ thể, chưa phải tổ hợp đã chạy và tương thích hoàn toàn.

| Không gian | Đề xuất | Bằng chứng cần trình diễn |
|---|---|---|
| H | Keycloak; Nextcloud Files + Collectives, xem xét Talk cho trao đổi nội bộ | Định danh tập trung, vai trò CSKH/kỹ thuật/quản lý; hồ sơ theo P.A.R.A; chính sách có phiên bản; thông báo gắn với ticket |
| P | Frappe + Helpdesk và Node-RED | Form low-code, chặn dữ liệu sai ở backend, chuyển trạng thái đúng quyền, phân công và phê duyệt |
| D | CSDL nghiệp vụ do Frappe hỗ trợ; PostgreSQL làm dữ liệu phân tích; Apache Superset làm BI | ID thống nhất, lịch sử sự kiện, dữ liệu đồng bộ, dashboard SLA/backlog/thời gian xử lý |
| I | Langflow + PostgreSQL/pgvector; cân nhắc Ollama để chạy model cục bộ | Sự kiện kích hoạt RAG, trích nguồn chính sách, ghi gợi ý nội bộ; xin phê duyệt trước hành động vượt quyền |

Keycloak và Superset dùng Apache-2.0; Nextcloud/Collectives dùng AGPL; Langflow và Ollama runtime dùng MIT [11][12][13][14]. **Giấy phép runtime AI không phải giấy phép model.** Phải chọn và kiểm tra riêng model sinh văn bản, embedding, plugin và phụ thuộc của phiên bản sẽ dùng.

Nextcloud có app OIDC chính thức. SSO giữa toàn bộ sản phẩm, ánh xạ vai trò và đăng xuất/thu hồi quyền vẫn cần thử theo từng phiên bản; không suy ra “có Keycloak là mọi app tự có SSO” [12]. Talk và các app bổ sung cũng phải kiểm tra phiên bản/giấy phép trước khi đưa vào danh mục phát hành.

Một số bẫy đã phát hiện:

- **n8n:** LICENSE hiện tại dùng Sustainable Use License ngoài phần enterprise, có giới hạn mục đích sử dụng/phân phối. Không chọn làm thành phần nguồn mở OSI của bài; ưu tiên Node-RED [9].
- **Flowise:** LICENSE hiện tại tách phần enterprise và một số tệp sang giấy phép thương mại; không ghi chung cả repo là Apache-2.0 [10]. Langflow là ứng viên thay thế cần thử.
- **Metabase:** có bản OSS AGPL và phần enterprise thương mại. Đây vẫn có thể là lựa chọn hợp lệ nếu dùng đúng bản, nhưng phải xác minh tính năng cần dùng có ở OSS. Đề xuất Superset để khảo sát trước [15].
- **MariaDB/PostgreSQL:** ví dụ triển khai Helpdesk/Frappe đang dùng MariaDB. Không ép mọi app vào PostgreSQL chỉ vì skeleton đã có PostgreSQL [6].
- **RAM/build:** chưa đo tài nguyên của bộ này. Không cam kết toàn bộ dịch vụ cộng LLM cục bộ chạy tốt trên 8 GB. Bộ nhớ lúc build cũng có thể cao hơn lúc chạy.

Phần D phải có ánh xạ dữ liệu liên kết vì bài chủ đề nhắc rõ LOD [2]. Đề xuất dùng ID/URI ổn định, từ điển dữ liệu và một bản xuất JSON-LD liên kết khách hàng - thiết bị - ticket - chính sách. Dữ liệu công khai của demo là dữ liệu tổng hợp. Chỉ thêm kho RDF/SPARQL nếu yêu cầu hoặc truy vấn cần tới; đây là lựa chọn triển khai, không phải định dạng BTC đã bắt buộc.

“Nguồn sự thật duy nhất” không có nghĩa tất cả app phải dùng một database vật lý. Xác định nơi sở hữu từng thực thể: Frappe sở hữu ticket; kho tài liệu sở hữu chính sách; bảng phân tích/vector là bản dẫn xuất có ID, phiên bản nguồn và thời điểm cập nhật. Không cho sửa độc lập cùng một ticket ở hai nơi.

## 5. Repo dự thi và cách build

Mô hình khuyến nghị:

```text
Source upstream công khai, ghim phiên bản/commit
                  +
Repo DX-Lab: cấu hình + module/adapter + workflow + dữ liệu + tài liệu
                  |
         Quy trình build có hướng dẫn và log
                  |
           Các Docker image có truy xuất nguồn
                  |
         Docker Compose dựng hệ thống demo
```

Upstream `frappe_docker` là bằng chứng kỹ thuật cho cách làm này: `apps.json` có URL/nhánh của app; quy trình build lấy Frappe và app để tạo image [6]. Đây không phải bằng chứng BTC đã chấp nhận mọi cách tách repo hay bundling.

Đề xuất hai đường chạy, với tên lệnh chỉ là thiết kế, **chưa có trong repo hiện tại**:

| Đường chạy | Mục đích | Yêu cầu |
|---|---|---|
| `make demo` | Dựng nhanh để dùng thử | Pull image đã ghim digest; nạp cấu hình/dữ liệu mẫu đúng phiên bản |
| `make build-source` | Chứng minh khả năng dựng sản phẩm từ source | Lấy source đã ghim, kiểm tra revision, chạy build tương ứng, đóng image và chạy cùng kịch bản kiểm chứng |

`docker pull` tải image đã build. `docker build` chỉ có `FROM <image-app>` rồi chép cấu hình cũng chưa chứng minh đã build app đó từ source. Với Python/JavaScript, build từ source có thể gồm cài package từ source, xử lý phụ thuộc và build frontend/assets; không nhất thiết tạo binary native.

Phạm vi build cần được lập bảng cho từng thành phần: đội tự viết gì, app upstream nào được build, phụ thuộc hệ thống nào dùng bản phân phối sẵn. Không tự suy ra BTC yêu cầu biên dịch lại cả hệ điều hành và mọi thư viện; cũng không suy ra image upstream là đủ cho toàn bộ sản phẩm.

Repo nên chứa:

- Manifest nguồn: URL, phiên bản/commit, giấy phép; lock image bằng digest và lưu thông tin build. Không chỉ dùng `latest`, `stable` hay tên nhánh di động.
- Compose, cấu hình mẫu, healthcheck và kịch bản khởi tạo có thể chạy lại.
- App mở rộng nếu cần, workflow xuất từ Node-RED, fixtures, mapping dữ liệu, dashboard và luồng AI xuất ra tệp.
- Chính sách giả lập, dữ liệu tổng hợp, bộ ca kiểm chứng có kết quả mong đợi, kịch bản demo.
- Hướng dẫn build/cài/backup/restore, danh mục phụ thuộc, thông báo giấy phép, changelog, issue tracker và release thực tế.

Không đưa cây mã upstream hoặc các thư mục dependency vào release repo một cách tùy tiện. Việc tải source vào vùng build riêng giúp quản lý nguồn, nhưng **không tự bảo đảm miễn trừ bundling**, nhất là khi phát hành image chứa các app. Phải mô tả trung thực thành phần trong image và giữ nghĩa vụ giấy phép tương ứng.

Nếu đội tự viết app ở repo B, repo dự thi A có thể tham chiếu/build B về kỹ thuật. B phải công khai, có giấy phép, ghim phiên bản và liên kết rõ trong release A. Việc tách repo không thay thế yêu cầu công khai toàn bộ kết quả; phải làm rõ với BTC cách chấm nhiều repo. App mở rộng liên kết với thành phần AGPL cần đánh giá giấy phép theo cách tích hợp thực tế, không tự áp Apache-2.0 cho mọi tệp có nguồn gốc khác nhau.

## 6. Phần đóng góp riêng cần tập trung

1. **Quy trình mẫu tái sử dụng:** vai trò, trạng thái, chính sách bảo hành, SLA và đường duyệt ngoại lệ được cấu hình rồi xuất vào Git.
2. **Tích hợp có kiểm soát:** chung ID, sự kiện không tạo bản ghi trùng khi gửi lại, có retry và nhật ký để tìm lỗi.
3. **Dữ liệu có nghĩa:** từ điển dữ liệu/JSON-LD và dashboard trả lời được “phiếu nào sắp quá hạn, đang mắc ở ai, vì sao”.
4. **AI nằm trong luồng xử lý:** đọc ticket mới, tìm điều khoản có phiên bản, tự ghi gợi ý nội bộ với trích dẫn; chuyển người khi thiếu bằng chứng hoặc phát sinh ngoại lệ.
5. **Lab cài lại được:** từ môi trường sạch đến cùng quy trình/dữ liệu bằng các bước đã kiểm chứng, kèm tài liệu thực hành cho người khác.

Luật xác định như ngày hết hạn, trường bắt buộc và quyền duyệt dùng kiểm tra thông thường. AI hữu ích ở việc hiểu mô tả tự do, tìm chính sách liên quan và giải thích đề xuất. Backend kiểm tra quyền/hành động; nội dung ticket và kết quả LLM không được tự cấp thêm quyền. Khách hàng, CSKH, kỹ thuật viên và quản lý vẫn cung cấp thông tin, thực hiện công việc vật lý, xác nhận kết quả và duyệt ngoại lệ.

## 7. Trình tự thực hiện và điều kiện đi tiếp

| Bước | Công việc | Đạt khi |
|---|---|---|
| 1. Đặc tả sandbox | Viết một luồng, vai trò, dữ liệu và chính sách giả lập; khoảng 20 ca gồm ca đúng/sai/ngoại lệ | Mỗi ca có đầu vào và kết quả mong đợi; không cần tự đoán quy tắc lúc demo |
| 2. Thử nền nghiệp vụ | Dựng Helpdesk; thêm trường thiết bị; thử trạng thái/duyệt, API và xuất cấu hình; build source một phiên bản phù hợp | Cài lại tái tạo được luồng; gọi API trực tiếp vẫn chặn được thao tác sai quyền |
| 3. Nối H/P | Định danh, hồ sơ/chính sách, phân quyền; sự kiện phân công và thông báo | Một ticket đi hết luồng, truy ra ai làm gì; sự kiện lặp không sinh việc trùng |
| 4. Làm D | Chuẩn hóa ID, đồng bộ, JSON-LD, dashboard | Tổng số và trạng thái khớp dữ liệu nguồn; biết độ trễ cập nhật; đối soát lại được |
| 5. Làm I | Chọn model; RAG chính sách; xử lý sự kiện và phê duyệt | Có nguồn trích dẫn; thiếu dữ kiện thì chuyển người; không tự duyệt chi phí/ngoại lệ |
| 6. Đóng gói | Kiểm chứng build, cài sạch, khởi động lại, backup/restore; công khai nguồn và release | Người khác dựng theo hướng dẫn; đo được RAM/CPU/thời gian; có bằng chứng cho từng tiêu chí |

Tháng 9 ưu tiên bước 1-2 để giảm rủi ro chọn sai nền. Tháng 10 hoàn thiện một lát cắt H/P/D/I chạy xuyên suốt và tài liệu tái lập. Tháng 11 đối chiếu đề chính thức rồi điều chỉnh. Đây là thứ tự ưu tiên, không phải cam kết thời lượng khi chưa biết nhân lực và máy chạy.

Đo trên cùng bộ ca tổng hợp: số lần nhập lại dữ liệu, số bước chuyển giao thủ công, tỷ lệ chặn dữ liệu sai, độ trễ đồng bộ, tỷ lệ trích dẫn đúng và số hành động vượt quyền bị chặn. Phân biệt dữ liệu thời gian được seed với thời gian thực sự đo khi chạy. Không dùng sandbox để tuyên bố ROI hay mức tiết kiệm đã được chứng minh ở doanh nghiệp.

## 8. Những giả định trong dự án hiện tại cần cập nhật khi triển khai

- `Makefile` gọi `docker compose build`, nhưng Compose hiện chỉ có PostgreSQL dùng `image:` và chưa có `build:`. Hiện chưa có bằng chứng build app từ source.
- `docs/architecture.md` đang cấm fork tuyệt đối. Ưu tiên không sửa upstream là hợp lý về bảo trì; không nên trình bày đó là lệnh cấm mọi fork do BTC quy định.
- Quyết định dùng chung PostgreSQL cho tất cả app cần xét lại nếu chọn Frappe/Helpdesk.
- Apache-2.0 của repo không tự giải quyết giấy phép của các thành phần, app mở rộng, model hoặc image.
- Mốc 8 GB RAM, cài dưới một giờ và số dịch vụ là mục tiêu đội tự đặt, chưa phải yêu cầu BTC hay kết quả đo.

## 9. Câu hỏi cần BTC xác nhận trước khi chốt cách nộp

Chưa có câu trả lời rõ trong các nguồn đã đối chiếu; chưa gửi câu hỏi ra ngoài:

> Với DX-Lab chủ yếu gồm cấu hình low-code, workflow, adapter và nhiều dịch vụ nguồn mở, đội dự kiến nộp một repo điều phối công khai, ghim source upstream, có quy trình build app từ source và image để chạy nhanh. Tiêu chí Building From Source được đánh giá trên những thành phần nào? Image chứa các app/phụ thuộc và source được tải lúc build được xét theo tiêu chí bundling ra sao? Nếu module của đội nằm ở repo công khai riêng, liên kết và ghim trong release repo chính, BTC chấm phần mã đó theo cách nào?

Điểm này không cản việc đặc tả domain hoặc thử nền nghiệp vụ. Nó ảnh hưởng đến cách hoàn thiện build/release và kết luận tuân thủ cuối cùng.

## 10. Nguồn và mức kiểm chứng

Đã đối chiếu trang thể lệ/chủ đề trực tiếp, tải 82 trang Markdown theo mục lục GitBook và đọc sâu các phần liên quan đến chọn quy trình, DX-Ticket, dữ liệu và AI. Không khẳng định đã đọc từng dòng của toàn bộ giáo trình. Đã kiểm tra README, giấy phép, tài liệu build/API và một số cấu hình upstream; **chưa build hay chạy thử tổ hợp được đề xuất**. Các nhánh `main/master/develop` trong nguồn tham khảo có thể thay đổi; lúc triển khai phải chọn release/commit tương thích rồi kiểm tra lại.

[1]: https://vfossa.vn/tin-tuc/the-le-olp-phan-mem-nguon-mo-nam-2026-760.html
[2]: https://vfossa.vn/tin-tuc/gioi-thieu-mo-hinh-dx-os-va-chu-de-cuoc-thi-phan-mem-nguon-mo-olp-2026-761.html
[3]: https://opendigitransform.gitbook.io/dx-os/phan-ii-xay-dung-he-dieu-hanh/chuong-6-p-process-chuan-hoa-khong-gian-nghiep-vu-so-and-tu-dong-hoa-quy-trinh/6.2.-dac-ta-tang-luu-tru-backend-thiet-lap-mo-hinh-du-lieu-quan-he
[4]: https://opendigitransform.gitbook.io/dx-os/phan-iii-trien-khai-van-hanh/chuong-9-chien-luoc-trien-khai-thuc-te-va-quan-tri-su-thay-doi/9.2.-chien-luoc-trien-khai-he-thong-tap-trung-vao-quy-trinh-trong-yeu
[5]: https://github.com/frappe/helpdesk
[6]: https://github.com/frappe/frappe_docker/blob/main/docs/02-setup/02-build-setup.md
[7]: https://docs.frappe.io/framework/user/en/guides/app-development/how-to-create-custom-fields-during-app-installation
[8]: https://nodered.org/docs/getting-started/development
[9]: https://github.com/n8n-io/n8n/blob/master/LICENSE.md
[10]: https://github.com/FlowiseAI/Flowise/blob/main/LICENSE.md
[11]: https://github.com/keycloak/keycloak
[12]: https://github.com/nextcloud/user_oidc
[13]: https://github.com/apache/superset/blob/master/LICENSE.txt
[14]: https://github.com/langflow-ai/langflow/blob/main/LICENSE
[15]: https://github.com/metabase/metabase/blob/master/LICENSE.txt
[16]: https://github.com/zammad/zammad-docker-compose/blob/master/docker-compose.yml

Nguồn kỹ thuật bổ sung:

- [Frappe Framework LICENSE](https://github.com/frappe/frappe/blob/version-15/LICENSE), [Helpdesk LICENSE](https://github.com/frappe/helpdesk/blob/main/LICENSE), [Node-RED LICENSE](https://github.com/node-red/node-red/blob/master/LICENSE).
- [Frappe REST API](https://docs.frappe.io/framework/user/en/api/rest), [Frappe custom apps](https://github.com/frappe/frappe_docker/blob/main/docs/09-concepts/01-custom-app.md), [Containerfile build app](https://github.com/frappe/frappe_docker/blob/main/images/custom/Containerfile).
- [Nextcloud Server](https://github.com/nextcloud/server), [Collectives](https://github.com/nextcloud/collectives), [Superset](https://github.com/apache/superset).
- [Langflow development](https://github.com/langflow-ai/langflow/blob/main/DEVELOPMENT.md), [pgvector](https://github.com/pgvector/pgvector), [Ollama LICENSE](https://github.com/ollama/ollama/blob/main/LICENSE).
- [Docker build context](https://docs.docker.com/build/building/context/), [mục lục GitBook](https://opendigitransform.gitbook.io/dx-os/llms.txt).
