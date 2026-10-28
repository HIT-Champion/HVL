# `schemas/` — JSON Schema dùng chung cho dữ liệu người dùng nhập

Mỗi tệp `*.json` ở đây mô tả dữ liệu của một form. Ba lớp kiểm theo cùng một tệp, nên một quy tắc chỉ viết một
lần mà form, máy chủ và CSDL không nói khác nhau (poka-yoke, F2.2 trong
[`docs/du-thi/ke-hoach-phat-trien.md`](../docs/du-thi/ke-hoach-phat-trien.md)):

| Lớp | Ở đâu | Kiểm bằng | Chặn được |
|---|---|---|---|
| 1. Form | `apps/office` | Ajv, biên dịch sẵn lúc build (`apps/office/scripts/forms.mjs`) | Người nhập sai: báo ngay dưới từng ô, chưa gửi gì đi |
| 2. Action | `svc-workflow` | `jsonschema` (`services/svc-workflow/src/svc_workflow/schemas.py`) | Gọi thẳng API bỏ qua form, form cũ còn trong bộ nhớ trình duyệt |
| 3. CSDL | PostgreSQL | Ràng buộc `CHECK`, chỉ mục chặn trùng (migration `1792281600800_intake_rules`) | Ghi thẳng bằng quyền quản trị, lỗi ở chính svc-workflow |

| Tệp | Form | Action |
|---|---|---|
| `van-ban-den.json` | Tiếp nhận văn bản đến (`/van-ban-den/tiep-nhan`) | `receiveIncoming(data: jsonb!)` |

Văn thư không có quyền ghi thẳng bảng `office.documents` lẫn `office.document_files`: văn bản đến và tệp kèm theo
chỉ vào CSDL qua Action `receiveIncoming`, nên không đi vòng được lớp 2.

## Quy ước

- **Chuẩn**: JSON Schema 2020-12, chỉ dùng từ khóa cả Ajv lẫn `jsonschema` hiểu giống nhau.
- **`format`**: chỉ `date` (`YYYY-MM-DD`, ngày có thật) và `uuid` (36 ký tự có gạch nối). Hai lớp tự viết hàm
  kiểm cho khớp nhau từng ký tự, không dùng bản có sẵn của thư viện (bản của `jsonschema` nhận cả `20261019`).
- **Độ dài** đếm theo ký tự (code point) như `len()` của Python và `char_length()` của PostgreSQL.
- **Khoảng trắng** viết tường minh trong `pattern`, đúng bằng `\s` của JavaScript, vì `\s` của Python và của
  PostgreSQL mỗi nơi hiểu một khác. Không được có ở đầu hoặc cuối; số ký hiệu, cơ quan ban hành chỉ một dòng.
- **Ký tự ẩn** — ký tự điều khiển, gạch nối mềm, ký tự rộng 0, điều khiển hướng chữ, BOM — không được có ở đâu cả:
  chép từ PDF hay dính, mắt không thấy nhưng làm cùng một số ký hiệu thành hai, lọt qua chặn trùng.
- **`x-moc-nfc`** (ở gốc schema): mọi chuỗi phải ở dạng dựng sẵn (Unicode NFC). "Hưng Yên" gõ bằng bộ gõ và
  "Hưng Yên" chép từ PDF dạng tổ hợp trông như nhau mà khác byte, chặn trùng sẽ không nhận ra.
- **Năm** của ngày phải từ 1900 đến 2099 (`pattern`), chặn gõ nhầm kiểu `0202-10-19`.
- Form tự dọn trước khi kiểm: bỏ khoảng trắng hai đầu và ký tự ẩn, đưa về NFC. Action và CSDL không tự sửa mà từ
  chối, để ứng dụng khác gọi API cũng phải gửi dữ liệu sạch.
- **`x-moc-date`**: từ khóa riêng, so ngày với hôm nay theo giờ Việt Nam (`not-after-today`,
  `not-before-today`). JSON Schema không có khái niệm "hôm nay", nên lớp 1 và lớp 2 tự so; CSDL kiểm điều
  yếu hơn nhưng không phụ thuộc lúc ghi (ngày ban hành không sau ngày tiếp nhận, hạn không trước ngày ban hành).
- **Điều chỉ CSDL biết** (loại văn bản có trong danh mục, tệp do chính người này tải lên, văn bản trùng) không
  nằm trong schema: svc-workflow tra CSDL sau khi dữ liệu qua schema.

## Mã lỗi

Lớp 1 và lớp 2 quy lỗi về `{trường: mã}` giống hệt nhau. Mã là tên từ khóa JSON Schema bị vi phạm (`required`,
`type`, `minLength`, `maxLength`, `format`, `pattern`, `enum`, `not`, `additionalProperties`, `uniqueItems`,
`maxItems`) hoặc từ khóa riêng (`x-moc-nfc`, `x-moc-date`). Một trường sai nhiều điều thì báo điều đứng trước trong danh sách này. svc-workflow thêm `duplicate`
(trùng văn bản đã tiếp nhận) và `unknown` (loại văn bản, tệp không có). Lỗi trả trong `extensions.fields`:

```json
{"errors": [{"message": "Dữ liệu văn bản đến chưa hợp lệ: summary, symbol",
             "extensions": {"code": "invalid", "fields": {"symbol": "not", "summary": "minLength"}}}]}
```

## Ca thử dùng chung

`van-ban-den.cases.json` liệt kê ca hợp lệ và ca sai (kèm mã lỗi mong đợi và lỗi mà PostgreSQL phải báo). Ba
bộ test chạy cùng các ca đó:

| Lớp | Test | Lệnh |
|---|---|---|
| 1 | `apps/office/tests/forms.test.ts` — đúng mã kiểm Vite đưa vào bundle | `make test` (Node 24, `npm ci` trong `apps/office`) |
| 2 | `services/svc-workflow/tests/test_intake.py` | `make test` |
| 3 | `db/tests/test_intake.py` — chèn thẳng bằng quyền quản trị | `db/tests/stack.sh up`, rồi pytest (`db/README.md`) |

`make smoke` kiểm lại cả ba lớp trên hệ thống đang chạy, `make e2e` kiểm form chặn trên trình duyệt thật.

## Sửa một quy tắc

1. Sửa schema, thêm ca vào tệp `*.cases.json`.
2. Quy tắc mà CSDL kiểm được thì thêm migration mới (không sửa migration cũ) và ghi tên ràng buộc vào ca thử.
3. `make test`, rồi chạy test CSDL. Form đọc độ dài tối đa, danh mục từ schema nên không phải sửa giao diện.
4. Schema được dựng vào cả image `app-office` (thành mã kiểm form) lẫn `svc-workflow` (compose đưa vào bằng
   `additional_contexts`), nên `make up` dựng lại cả hai — hai lớp luôn cùng một bản. Ở thư mục cài
   (`make install`) không sửa schema tại chỗ: sửa trong mã nguồn rồi cài lại.

## Form dựng từ schema (#303)

Ứng dụng cài thêm khai form bằng một tệp JSON Schema trong gói của mình (`apps/<ứng dụng>/forms/*.json`), không
viết mã giao diện. Trang gọi `mountForm()` của `apps/nghi-phep/public/schema-form.js` (JS thuần, không thư viện):
module dựng ô, nhãn, gợi ý, câu báo lỗi tiếng Việt/tiếng Anh, kiểm bằng đúng tệp đó trước khi gửi. svc-workflow kiểm
lại khi nhận qua API của ứng dụng (`/api/workflow/…`, #301; luật form lúc cài: `docs/them-ung-dung.md` mục 1.10).
Bộ kiểm của module đi từng từ khóa vì CSP không cho
`unsafe-eval`; nó hiểu các từ khóa ở trên cùng `const`, `minimum`, `maximum`, `minItems`, `allOf`. Từ khóa khác, giá
trị từ khóa sai dạng, `$ref` vòng hay gợi ý hiển thị sai (thiếu trường trong `x-moc-order`, `x-moc-range` không phải
hai trường ngày) thì báo lỗi ngay lúc nạp.

Gợi ý hiển thị, bên kiểm bỏ qua; chữ là chuỗi hoặc `{vi, en}`:

- `x-moc-title` (gốc): tên form.
- `x-moc-order` (gốc): thứ tự ô; không có thì theo `properties`.
- `x-moc-ui` (từng trường): `widget` — `text`, `textarea`, `date`, `number`, `select`, `radio`, `checkbox`,
  `checkboxes`, không ghi thì suy từ kiểu; `label`, `help`, `note`, `rows`; `options` — nhãn cho từng giá trị của
  `enum`; `errors` — câu báo riêng theo mã; `hidden`.

Thêm một từ khóa kiểm riêng: **`x-moc-range`** ở gốc, vd `[["tuNgay", "denNgay"]]` — hai trường `format: date`,
trường sau không được trước trường trước. Mã `x-moc-range` gắn vào trường sau, chỉ xét khi cả hai trường đã hợp lệ,
đứng cuối thứ tự ưu tiên. Phía máy chủ, `svc_workflow/apps/forms.py` (`AppForm`) kiểm bằng `FormSchema` rồi mới
xét `x-moc-range`, cùng luật đó; từ khóa không thêm vào `schemas.py` nên form của Văn phòng điện tử không đổi. Lúc
cài, svc-workflow từ chối form có `x-moc-range` không phải cặp hai trường `format: date` khác nhau.

| Tệp | Form |
|---|---|
| `apps/nghi-phep/forms/don.json` | Đơn xin nghỉ (formKey `nghi-phep.don`) |
| `apps/nghi-phep/forms/duyet.json` | Duyệt đơn xin nghỉ (formKey `nghi-phep.duyet`) |

Mỗi form có tệp ca thử `*.cases.json` cùng cách viết với `van-ban-den.cases.json`.
`apps/nghi-phep/tests/schema-form.test.js` (`make test`) chạy cả ca của `schemas/` lẫn ca của form ứng dụng: trên ca
của `schemas/`, bộ kiểm trên trình duyệt cho đúng mã như Ajv và svc-workflow. Phía máy chủ,
`services/svc-workflow/tests/test_app_forms.py` chạy mọi ca của `apps/*/forms/*.cases.json` qua đúng bộ kiểm của API
(`AppForm`: `FormSchema` + `x-moc-range`) và kiểm form cạnh tệp ca thử qua được luật lúc cài.

Luật lúc cài kiểm chính tệp form, không phải dữ liệu, nên có bộ ca riêng:
`services/svc-workflow/tests/app_form_rules.cases.json`. `check_form` và bản chép trên trình duyệt
`apps/office/app/utils/formRules.ts` (cho trình dựng form, #303) cho cùng mã luật trên mọi ca, trừ hai luật chỉ máy chủ
kiểm (`pattern` dễ quay lui bùng nổ, meta-schema). Chi tiết ở [`docs/them-ung-dung.md`](../docs/them-ung-dung.md) mục
1.10.
