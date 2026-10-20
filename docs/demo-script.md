# Kịch bản demo — bằng chứng 4 nguyên lý thiết kế

Đề thi (`olp-2026-de-thi.md` §3.2) yêu cầu sản phẩm "được xây dựng dựa trên" 4 nguyên lý, kèm gợi ý bằng chứng
cho từng nguyên lý. Mỗi màn dưới đây:

- chạy bằng **một lệnh** trên hệ thống đang chạy (`make up`, `make seed`), xong trong **dưới một phút**;
- in từng bước kèm dấu ✓, sai bước nào thì dừng và nói rõ bước đó (thoát 1);
- chạy lại bao nhiêu lần cũng được, không sửa dữ liệu mẫu (mỗi lần chỉ thêm dữ liệu riêng của lần chạy, vd một
  tệp sạch chưa gắn văn bản và vài dòng sổ kiểm toán).

Trên máy chủ đã `make install`, chạy `python3 scripts/demo.py <màn>` trong thư mục cài, thay cho `make demo-<màn>`.

Khi trình bày: terminal chạy lệnh một bên, trình duyệt mở giao diện ở bên kia (đường dẫn in ở cuối mỗi màn).

| Nguyên lý | Màn | Lệnh | Tình trạng |
| --- | --- | --- | --- |
| (i) Vòng đời và tốc độ dữ liệu | Nóng → lạnh: hồ sơ đã đóng chuyển sang kho lạnh, vẫn tìm và xác thực được | `make demo-nong-lanh` | Có (F3.8) |
| (ii) Hội tụ IT/OT | Cảm biến nhiệt độ phòng máy → NGSI-LD → dựng nháp báo cáo sự cố | — | Chưa có (F3.10) |
| (iii) Quản trị dữ liệu | Phả hệ: báo cáo ← bảng ← sự kiện; kiểm chất lượng tự động | — | Chưa có (F3.9) |
| (iv) Zero-Trust + GitOps | Kiểm dịch tại cửa ngõ | `make demo-kiem-dich` | Có (F3.1) |
| (iv) Zero-Trust + GitOps | Két bí mật: dịch vụ không giữ bí mật, két tự mở khóa | `make demo-ket-bi-mat` | Có (F3.2) |
| (iv) Zero-Trust + GitOps | Tự phục hồi từ cấu hình trong git | `make demo-tu-phuc-hoi` | Có (F3.3) |

## (i) Nóng → lạnh — `make demo-nong-lanh`

**Điều muốn chứng minh:**

- Dữ liệu có vòng đời: văn bản đang xử lý nằm ở CSDL nghiệp vụ (nóng). Hồ sơ đã đóng thì nộp lưu (NĐ 30/2020, Điều
  28–31): chi tiết chuyển sang kho lạnh rẻ, không sửa được; CSDL nghiệp vụ chỉ giữ bản ghi rút gọn.
- Chuyển đi mà không mất gì: gói có manifest băm từng phần, đọc lại so băm xong mới gỡ khỏi CSDL. Văn bản vẫn tìm
  thấy, quét mã QR vẫn "khớp", phòng đọc vẫn đọc lại được gói.
- Kho lạnh có khóa ghi: trong thời hạn bảo quản không ai xóa được gói, kể cả quản trị kho.

**Lệnh in ra 5 bước:**

1. Chuyên viên (hoặc tổ trưởng) lập hồ sơ `HS-…`, đưa vào tối đa ba văn bản đã xong mà mình đọc được, thuộc phòng
   mình (ưu tiên văn bản đi đã phát hành, có mã QR), đóng hồ sơ — ngày đóng do CSDL đặt. In số dòng liên kết tệp,
   dòng thời gian, giao việc của các văn bản đó trong CSDL.
2. Gọi job nộp lưu của svc-files ngay (bình thường là vòng nền mỗi giờ, cho hồ sơ đóng quá `MOC_ARCHIVE_AFTER_DAYS`
   ngày). In đường dẫn gói `s3://moc-cold/cold/<đơn vị>/case/<hồ sơ>/`, số văn bản, số tệp, số byte, thời gian, băm
   của manifest (`manifest-<băm>.json`).
3. CSDL nghiệp vụ: văn bản ở trạng thái `archived`; liên kết tệp, dòng thời gian về 0; giao việc giữ nguyên (căn
   cứ quyền xem, sổ đăng ký); bản tệp trong bucket nóng đã xóa.
4. Vẫn dùng được:
   - quét mã tra cứu của văn bản đi ở cổng xác thực, không đăng nhập → "khớp", trạng thái `archived`;
   - văn thư tìm theo số ký hiệu → ra văn bản đã nộp lưu;
   - phòng đọc `GET /api/case-files/{id}/archive`: manifest khớp băm trong CSDL, DuckDB đọc `documents.parquet` ra
     đúng các văn bản.
5. Thử xóa manifest bằng khóa quản trị của kho → bị từ chối (S3 Object Lock, chế độ COMPLIANCE). Dòng
   `case_file.archived` nằm trong sổ kiểm toán chuỗi băm.

**Trên giao diện:**

- *Bất kỳ ai*: mở trang xác thực, nhập mã tra cứu của văn bản vừa nộp lưu → vẫn "Văn bản khớp".
- *Lãnh đạo khoa*: **Sổ kiểm toán** → tab **Văn bản**, dòng "Nộp lưu hồ sơ" kèm ký hiệu hồ sơ, băm gói, số văn bản,
  số tệp; tên hồ sơ không hiện.
- Chưa có màn lập hồ sơ: bước 1 đi qua GraphQL với đúng quyền của chuyên viên.

**Nếu giám khảo hỏi:**

- *"Lạnh là ở đâu?"* Bucket `moc-cold` của SeaweedFS, có khóa ghi, chung với mốc neo sổ kiểm toán. Triển khai thật
  thì trỏ `MOC_COLD_BUCKET` sang ổ rẻ hơn hoặc kho S3 khác. Parquet là định dạng cột mở: công cụ nào cũng đọc được,
  không cần Mộc.
- *"Sao không dùng Kestra?"* Một job mỗi giờ không đáng thêm một máy chủ Java khoảng 1 GB RAM. Job là vòng nền trong
  svc-files, như vòng neo sổ kiểm toán. DuckDB nhúng trong svc-files, không chạy máy chủ riêng.
- *"Hỏng giữa chừng thì sao?"* Thứ tự là kiểm băm tệp nóng → ghi gói → đọc lại so băm → một giao dịch CSDL → xóa
  bản nóng. Giao dịch kiểm CSDL còn đúng như gói (khóa dòng), lệch thì không đổi gì. Hỏng trước giao dịch thì CSDL
  chưa đổi gì, lượt sau làm lại và không ghi lại phần đã có. Hỏng sau giao dịch thì chỉ thừa bản nóng, không mất gì.
- *"Văn bản hạn chế?"* Không vào hồ sơ nộp lưu: tệp của nó sẽ mã hóa riêng (F3.7). Nộp lưu bản mã hóa cần thêm bước
  giữ khóa.

## (iv) Kiểm dịch tại cửa ngõ — `make demo-kiem-dich`

**Điều muốn chứng minh:**

- Không tệp nào chạm kho mà chưa qua ClamAV.
- Tệp nhiễm bị chặn ngay ở cửa ngõ, không được lưu. Thứ duy nhất còn lại là dòng sổ kiểm toán ghi lần chặn.
- Sổ kiểm toán là chuỗi băm, neo ra ngoài CSDL: ai sửa hay xóa dòng đó, kể cả quản trị, đều bị phát hiện.

**Lệnh in ra 5 bước:**

1. Văn thư tải lên một công văn bình thường qua cổng APISIX → `201`, ClamAV báo sạch, tệp vào kho.
2. Văn thư tải lên `hoa-don-….pdf` chứa **chuỗi kiểm thử EICAR**. Đây là chuỗi chuẩn để thử phần mềm diệt virus,
   không phải mã độc thật. Kết quả: `422 infected`, ClamAV báo `Eicar-Test-Signature`.
3. `core.files` không có dòng nào mang SHA-256 của tệp đó: tệp bị chặn trên luồng, trước khi ghi vào kho.
4. Lãnh đạo khoa đọc sổ kiểm toán của đơn vị, đúng quyền của mình, và thấy dòng `file.rejected`:
   - thấy giờ, người tải, mẫu mã độc, cỡ tệp;
   - không thấy tên tệp, vì tên do người dùng đặt có thể nói lên nội dung.
5. `moc audit anchor` neo đầu chuỗi ra bucket lạnh khóa ghi (object lock). `moc audit verify` tính lại cả chuỗi bên
   ngoài CSDL: chuỗi liền mạch tới dòng vừa ghi. Từ đó, sửa hay xóa dòng này đều bị phát hiện.

**Trên giao diện:**

- *Lãnh đạo khoa*: vào **Sổ kiểm toán** → tab **Tệp**, có dòng "Chặn tệp nhiễm mã độc" kèm mẫu mã độc và cỡ tệp.
- *Văn thư*: tải tệp EICAR ở **Tiếp nhận văn bản**, tệp hiện đỏ "Tệp nhiễm mã độc (…) — đã bị chặn, không lưu".

**Nếu giám khảo hỏi:**

- *"Chặn ở gateway hay ở dịch vụ?"* Ở `svc-files`, sau APISIX. Mọi đường tải tệp lên đều đi qua đây, không có
  đường nào ghi thẳng vào SeaweedFS. Tệp được quét trên luồng trước khi ghi vào kho. ClamAV không trả lời thì
  từ chối tệp (`503`), không cho qua.
- *"Mã độc mới, chưa có mẫu thì sao?"* ClamAV chỉ bắt được mẫu đã biết. Mẫu tự cập nhật nhiều lần mỗi ngày
  (freshclam chạy sẵn trong image `clamav/clamav`). Lớp sau là: tệp không bao giờ được thực thi trên máy chủ,
  PDF chỉ được đọc trong tiến trình con có giới hạn bộ nhớ, CPU và thời gian (F2.7).

## (iv) Két bí mật — `make demo-ket-bi-mat`

**Điều muốn chứng minh:**

- Dịch vụ của đội không nhận bí mật qua biến môi trường (`docker inspect` hay `/proc/<pid>/environ` không lộ gì);
  bí mật nằm trong két OpenBao, mỗi dịch vụ đăng nhập bằng danh tính riêng (AppRole) và chỉ đọc được phần của mình.
- Két tự mở khóa khi khởi động lại (static seal), nên máy chủ khởi động lại hay dịch vụ bị dựng lại (F3.3) không cần
  người nhập khóa.
- Mọi lần đăng nhập, đọc bí mật đều vào sổ của két; giá trị bí mật trong sổ đã băm.

**Lệnh in ra 5 bước:**

1. Băm giá trị từng biến môi trường trong container `svc-files`, `svc-workflow`, so với băm của các bí mật trong
   `.env`: không khớp cái nào. Env chỉ có địa chỉ két (`MOC_OPENBAO_ADDR`, `MOC_OPENBAO_SECRET_PATH`).
2. `docker compose restart openbao`: két khởi động lại, tự mở khóa, nạp lại bí mật và cấp secret_id mới cho từng dịch
   vụ (hủy cái cũ) trong vài giây; `svc-files`, `svc-workflow` khởi động lại theo và lấy lại bí mật. `bao status`:
   seal `static`, `sealed=false`.
3. `docker compose restart svc-files`: dịch vụ đăng nhập két bằng secret_id mới, lấy khóa kho S3, rồi văn thư tải một
   tệp lên → `201`. Khóa kho không đi qua đâu ngoài két.
4. Trong container `svc-workflow`, thử đọc phần bí mật của `svc-files` bằng AppRole của `svc-workflow` → két từ chối
   `403`.
5. Đọc sổ của két (`docker compose logs openbao`) từ lúc khởi động lại: thấy `svc-files` đăng nhập rồi đọc
   `moc/data/svc-files`, và lần `svc-workflow` đọc chéo bị từ chối ở bước 4; không giá trị bí mật nào xuất hiện rõ
   trong sổ.

**Nếu giám khảo hỏi:**

- *"Bí mật vẫn nằm trong `.env` mà?"* Đúng. `.env` vẫn là nguồn: container `openbao` nhận chúng và nạp vào két mỗi
  lần khởi động. Cái được: dịch vụ của đội không giữ bí mật trong biến môi trường, mỗi dịch vụ chỉ đọc được phần của
  mình, mọi lần đọc có sổ. Phần mềm thượng nguồn (Hasura, SeaweedFS, Meilisearch, Centrifugo) vẫn đọc bí mật của
  chúng từ biến môi trường.
- *"Khóa mở két để đâu?"* `MOC_OPENBAO_SEAL_KEY` trong `.env`, khóa phục hồi và token khởi động trong volume của két,
  `role_id`/`secret_id` của dịch vụ trong volume riêng của dịch vụ đó. Ai có quyền Docker trên máy chủ vẫn đọc được
  két. Static seal đổi an toàn lấy khả năng tự phục hồi; bản thật nên dùng KMS hoặc HSM (seal `pkcs11`, `awskms`…).
- *"Ai cấu hình két?"* Lần đầu, `openbao/start.sh` cấu hình bằng token root rồi thu hồi nó ngay. Các lần sau chỉ
  dùng token khởi động: không đọc thẳng được bí mật, không sửa được policy, nhưng cấp được secret_id cho hai dịch vụ
  — nên volume của két phải được giữ như chính két.
- *"Két dùng làm gì nữa?"* Khóa transit `moc-files` để mã hóa tệp của văn bản hạn chế (F3.7): `svc-files` chỉ xin
  được khóa dữ liệu mới và mở khóa đã bọc, không bao giờ cầm khóa gốc.

## (iv) Tự phục hồi — `make demo-tu-phuc-hoi`

**Điều muốn chứng minh:**

- Trạng thái mong muốn nằm trong git (`docker-compose.yml`, cấu hình cổng, policy két…); một reconciler đều đặn
  so trạng thái đang chạy với khai báo và tự sửa phần lệch, không cần người.
- Dịch vụ chết hay bị xóa hẳn thì được dựng lại; cấu hình bị sửa tay trên máy chủ thì bị đưa về đúng commit.

**Lệnh in ra 4 bước (dưới một phút):**

1. Một lượt `scripts/reconcile.py`: "đã khớp trạng thái khai báo, không có gì phải làm".
2. Phá: `docker rm -f` container `svc-files` (mất hẳn, không phải chỉ dừng), `docker stop` container `centrifugo`.
   Văn thư tải tệp → cổng trả lỗi vì không tới được dịch vụ.
3. Một lượt reconciler (trên máy chủ là systemd timer mỗi 60 giây, ở đây gọi ngay): in "dựng lại svc-files (không
   còn container)", "chạy lại centrifugo (đã dừng: …)".
4. Hai dịch vụ về `running (healthy)` (svc-files lấy lại bí mật từ két F3.2), văn thư tải tệp → `201`.

**Phần GitOps** (chạy trong CI, bước "GitOps"; trên máy chủ xem README mục "GitOps và tự phục hồi"):

- Đẩy một commit lên nhánh `deploy` của repo → lượt reconciler kế tiếp in "áp commit … (nhánh deploy: cũ → mới)",
  tệp `VERSION` của bản cài mang commit mới, smoke vẫn qua.
- Sửa tay `docker-compose.yml` trong thư mục cài → lượt kế tiếp in "tệp đã cài bị sửa tay, đưa về commit …" và
  tệp trở lại đúng như trong git.

**Đối chiếu bốn nguyên tắc OpenGitOps 1.0:**

| Nguyên tắc | Ở Mộc |
| --- | --- |
| Khai báo (declarative) | Toàn bộ hệ thống khai trong `docker-compose.yml` + cấu hình từng thành phần (realm Keycloak, metadata Hasura, cổng APISIX, cấu hình két); không bước dựng tay nào ngoài `.env` |
| Có phiên bản, bất biến (versioned and immutable) | Trạng thái mong muốn là một commit git; image dựng theo commit (`MOC_VERSION` = `git describe`), tệp `VERSION` của bản cài ghi commit; lùi phiên bản = đẩy commit cũ lên `deploy` |
| Tự kéo về (pulled automatically) | Reconciler trên máy chủ tự `git fetch`; không ai đẩy vào máy chủ, CI không cần quyền vào máy chủ |
| Liên tục đối chiếu (continuously reconciled) | systemd timer mỗi 60 giây: so commit, so băm tệp đã cài, so container đang chạy với khai báo; lệch thì sửa |

**Nếu giám khảo hỏi:**

- *"Sao không dùng Argo CD hay Flux?"* Hai công cụ đó chạy trên Kubernetes; Mộc nhắm máy chủ đơn vị chạy Docker
  Compose. Reconciler là một script thư viện chuẩn Python, đọc được trong vài phút.
- *"Docker có `restart: unless-stopped` rồi mà?"* Chính sách đó chỉ chạy lại container còn tồn tại và không chạy lại
  container bị `docker stop`. Container bị xóa hẳn, hay cấu hình lệch khỏi git, thì chỉ reconciler đưa về được.
- *"Áp commit có làm gián đoạn không?"* Có, khoảng một phút: reconciler dựng image trước, rồi dừng Mộc, cài lại đúng
  commit và chạy lại. Commit áp lỗi thì reconciler đợi commit kế tiếp chứ không thử lại liên tục.
- *"`.env` thì sao?"* Không nằm trong git (chứa bí mật), reconciler không đụng tới; đổi `.env` vẫn là việc của
  người vận hành.
