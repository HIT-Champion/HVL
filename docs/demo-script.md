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
