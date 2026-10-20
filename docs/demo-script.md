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
| (i) Vòng đời và tốc độ dữ liệu | Nóng → lạnh: hồ sơ đã đóng chuyển sang kho lạnh, vẫn tìm và xác thực được | — | Chưa có (F3.8) |
| (ii) Hội tụ IT/OT | Cảm biến nhiệt độ phòng máy → NGSI-LD → dựng nháp báo cáo sự cố | — | Chưa có (F3.10) |
| (iii) Quản trị dữ liệu | Phả hệ: báo cáo ← bảng ← sự kiện; kiểm chất lượng tự động | — | Chưa có (F3.9) |
| (iv) Zero-Trust + GitOps | Kiểm dịch tại cửa ngõ | `make demo-kiem-dich` | Có (F3.1) |
| (iv) Zero-Trust + GitOps | Két bí mật: dịch vụ không giữ bí mật, két tự mở khóa | `make demo-ket-bi-mat` | Có (F3.2) |
| (iv) Zero-Trust + GitOps | Tự phục hồi từ cấu hình trong git | — | Chưa có (F3.3) |

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
