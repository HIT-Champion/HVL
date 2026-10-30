# Giới thiệu trợ lý

<!-- Nguồn của đường gioi_thieu (assist/route.py, guide.py). Neo {#…} cố định: guide.INTRO_SECTIONS trỏ tới. Mỗi câu
     phải đúng với mã đang chạy và docs/danh-gia-ai.md; đổi mô hình mặc định thì sửa mục mo-hinh. -->

## Trợ lý là ai {#gioi-thieu}

Tôi là trợ lý hỏi đáp của Signet. Tôi trả lời câu hỏi bằng nội dung các văn bản bạn được xem trong Văn phòng điện tử,
kèm số ký hiệu và trang của đoạn được trích. Tôi cũng trả lời câu hỏi về cách dùng Signet theo hướng dẫn sử dụng.

## Trợ lý làm được gì {#lam-duoc-gi}

Tôi tìm trong các văn bản bạn được xem và trích nguyên văn đoạn trả lời câu hỏi, ví dụ "Điều kiện xét học bổng khuyến
khích học tập là gì?". Tôi trả lời câu hỏi về cách dùng Signet theo hướng dẫn sử dụng, ví dụ "Nộp đơn nghỉ phép ở
đâu?". Tôi đếm việc trong Hộp việc của bạn và số văn bản bạn được xem, ví dụ "Việc nào của tôi sắp quá hạn?", "Có bao
nhiêu văn bản đến trong tháng này?"; số đếm thẳng trong dữ liệu, không qua mô hình ngôn ngữ. Tôi hiểu câu hỏi nối tiếp
câu ngay trước, ví dụ "Còn khoa Kinh tế thì sao?". Tôi không tìm trong văn bản hạn chế. Tôi không trả lời câu ngoài
văn bản và cách dùng Signet, như thời tiết, tin tức hay viết hộ.

## Cách hỏi {#cach-hoi}

Hỏi mỗi câu một ý, dùng từ có trong văn bản như tên quy chế, số ký hiệu, năm ban hành. Chọn văn bản đến, văn bản đi
hoặc năm để thu hẹp phạm vi tìm. Nút Hỏi về văn bản này trên trang văn bản chỉ hỏi trong văn bản đó. Mỗi ý của câu trả
lời có số [n] trỏ tới nguồn; hãy mở văn bản nguồn để đối chiếu trước khi dùng.

## Mô hình và giới hạn {#mo-hinh}

Câu trích nguyên văn được chọn bằng quy tắc, không cần mô hình ngôn ngữ. Khi đơn vị bật mô hình, Qwen3-1.7B (giấy phép
Apache-2.0) chạy trong Ollama trên máy chủ của đơn vị viết câu trả lời ngắn từ tối đa 4 đoạn đã tìm. Máy chủ kiểm từng
câu và từng con số của câu trả lời với các đoạn đó; câu trả lời không đạt thì bị bỏ, chỉ còn câu trích. Tìm theo nghĩa
dùng mô hình nhúng Qwen3-Embedding-0.6B (Apache-2.0). Số điện thoại, số căn cước, email, số tài khoản được che trước
khi tới mô hình. Câu hỏi chỉ giữ trên trang; sổ kiểm toán ghi một dòng cho mỗi lượt hỏi, không có chữ câu hỏi. Signet
là phần mềm nguồn mở, giấy phép Apache-2.0. Tôi có thể sai, nên hãy đọc đoạn nguồn trước khi dùng câu trả lời.

## Cảm ơn {#cam-on}

Rất vui được giúp bạn. Bạn có thể hỏi tiếp về nội dung văn bản hoặc cách dùng Signet.

## Ngoài phạm vi {#ngoai-pham-vi}

Câu này nằm ngoài phạm vi của tôi. Tôi trả lời câu hỏi về nội dung các văn bản bạn được xem, về cách dùng Signet, về
việc của bạn và số văn bản. Bạn có thể hỏi, ví dụ: "Điều kiện xét học bổng là gì?", "Nộp đơn nghỉ phép ở đâu?", "Việc
nào của tôi sắp quá hạn?", "Bạn làm được gì?".
