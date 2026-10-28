#!/usr/bin/env python3
# Copyright 2026 Signet Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Màn demo bằng chứng các nguyên lý thiết kế (docs/demo-script.md): mỗi màn một lệnh, dưới một phút, chạy trên
hệ thống đang chạy (cần make seed trước). Chỉ dùng thư viện chuẩn, chạy được trong thư mục cài (make install).

    python3 scripts/demo.py nong-lanh
        (i) Vòng đời dữ liệu nóng → lạnh: chuyên viên lập hồ sơ, đóng; svc-files nộp lưu thành gói Parquet + tệp +
        manifest có băm trên bucket lạnh khóa ghi, gỡ chi tiết khỏi CSDL nghiệp vụ; văn bản vẫn tìm thấy, quét QR vẫn
        khớp, phòng đọc đọc lại gói bằng DuckDB, xem tệp PDF có dấu tên người xem; số liệu đã nộp lưu của trang Điều
        hành (DuckDB đếm trên các gói Parquet) tăng đúng bằng hồ sơ vừa nộp lưu, phả hệ ghi lượt đọc. (make
        demo-nong-lanh)
    python3 scripts/demo.py kiem-dich
        (iv) Kiểm dịch tại cửa ngõ: tệp sạch qua, tệp chứa chuỗi kiểm thử EICAR bị ClamAV chặn trước khi chạm
        kho; lần chặn nằm trong sổ kiểm toán chuỗi băm, neo ra ngoài CSDL và kiểm lại được. (make demo-kiem-dich)
    python3 scripts/demo.py han-che
        (iv) Văn bản hạn chế: tệp mã hóa từng tệp bằng khóa từ két OpenBao trước khi vào kho; người nhận việc tự có
        tên trong danh sách được xem, người khác 404; mở ra là bản giải mã trong bộ nhớ có dấu tên người xem, mỗi lần
        mở một dòng sổ kiểm toán; thông báo không mang nội dung. (make demo-han-che)
    python3 scripts/demo.py ket-bi-mat
        (iv) Két bí mật: dịch vụ không nhận bí mật qua biến môi trường mà lấy từ két OpenBao bằng AppRole riêng;
        khởi động lại két thì két tự mở khóa, dịch vụ khởi động lại vẫn lấy được bí mật. (make demo-ket-bi-mat)
    python3 scripts/demo.py tu-phuc-hoi
        (iv) Tự phục hồi: xóa hẳn container svc-files, dừng centrifugo; một lượt reconciler (systemd timer chạy mỗi
        60 giây) dựng lại đúng như compose khai báo, tải tệp lại được. (make demo-tu-phuc-hoi)
    python3 scripts/demo.py it-ot
        (ii) Hội tụ IT/OT: bật context broker NGSI-LD (profile iot); cảm biến nhiệt độ phòng máy chủ giả lập gửi các
        lần đo, vượt ngưỡng thì svc-workflow dựng dự thảo "Báo cáo sự cố" từ mẫu cho chuyên viên phụ trách; chuyên viên
        trình, dự thảo vào luồng văn bản đi; sơ đồ cảm biến kho (/cam-bien) tô màu từng phòng và gắn cờ chất lượng
        (mất tín hiệu, ngoài dải, trùng observedAt, observedAt ở tương lai). (make demo-it-ot)
    python3 scripts/demo.py lien-thong
        Liên thông văn bản trong hệ thống (F3.12, không thuộc 4 nguyên lý): Khoa CNTT phát hành công văn gửi Khoa
        Kinh tế; bên nhận tự có văn bản đến cùng tệp (cùng SHA-256), cùng mã xác thực; vào sổ, lãnh đạo có việc chỉ
        đạo; sổ kiểm toán của cả hai đơn vị ghi lại; văn bản hạn chế không gửi được. (make demo-lien-thong)
    python3 scripts/demo.py doc-van-ban
        Đọc văn bản đến (F4.1, dưới hai phút, không cần mô hình): văn thư tải công văn mẫu, tác tử moc-doc-reader đọc
        lớp chữ (ảnh thì OCR) và gợi ý số ký hiệu, ngày, cơ quan, loại, độ khẩn, trích yếu kèm độ tin cậy; văn thư sửa
        một ô rồi vào sổ; sổ kiểm toán ghi lần đọc (chỉ siêu dữ liệu); tệp hạn chế không bị đọc; bật profile ai thì
        mô hình viết trích yếu cho văn bản không có dòng V/v. (make demo-doc-van-ban)
    python3 scripts/demo.py do-doc-van-ban
        Đo tác tử trên mọi văn bản mẫu seed/van-ban-den (22: 15 PDF có lớp chữ, 7 ảnh/bản scan) so với nhãn
        nhan.json: bảng đúng / sai / trống từng trường, riêng PDF có lớp chữ và bản scan, tỉ lệ số ký hiệu, ngày ban
        hành đúng trên cả kho, thời gian trung bình; thoát 1 khi PDF có lớp chữ dưới ngưỡng, hay cả kho dưới 20 văn
        bản hoặc số ký hiệu, ngày ban hành đúng không quá nửa. (make do-doc-van-ban)
    python3 scripts/demo.py hoi-dap
        Hỏi đáp trên kho văn bản (F4.2, dưới hai phút, không cần mô hình): văn thư nạp kho mẫu seed/hoi-dap; trợ lý
        moc-assistant trả câu trích nguyên văn kèm số ký hiệu và trang; giảng viên Bộ môn KTPM chỉ thấy văn bản mình
        được xem; nội dung văn bản hạn chế không ai hỏi ra; sổ kiểm toán ghi lượt hỏi của tác tử, không có câu hỏi,
        câu trả lời; bật profile ai thì mô hình viết câu trả lời có trích dẫn. (make demo-hoi-dap)
    python3 scripts/demo.py do-hoi-dap
        Đo trợ lý trên mọi câu trong seed/hoi-dap/cau-hoi.json (đúng người hỏi): bảng trạng thái, nguồn top-3, đúng /
        sai, từ khóa, thời gian; recall@3, tỉ lệ từ chối đúng; có mô hình thì đo thêm câu trả lời của mô hình. Thoát 1
        khi có nguồn bị cấm ở bất kỳ câu nào (quyền, văn bản hạn chế), hoặc recall@3 dưới ngưỡng. (make do-hoi-dap)
    python3 scripts/demo.py giao-viec
        Gợi ý giao việc (F4.3, không cần mô hình): văn thư nạp lịch sử giao việc mẫu seed/giao-viec; văn bản mới vào sổ
        thì lãnh đạo khoa có việc chỉ đạo ngay, vài giây sau tác tử moc-assigner gợi ý đơn vị chủ trì và hạn kèm căn
        cứ (các văn bản tương tự đã giao); dùng gợi ý thì view đo tỉ lệ giữ tăng 1; văn bản hạn chế không gợi ý, không
        làm căn cứ; sổ kiểm toán ghi lần gợi ý (không chữ văn bản); tắt svc-files thì văn bản vẫn tới bước chỉ đạo,
        gợi ý ghi failed. (make demo-giao-viec)
    python3 scripts/demo.py do-giao-viec
        Đo tác tử leave-one-out trên lịch sử seed/giao-viec (python -m svc_workflow.advisor evaluate trong
        svc-workflow): top-1/2/3, độ phủ, đúng theo độ tin cậy, sai số hạn, thời gian; thoát 1 khi có căn cứ là văn
        bản hạn chế, hoặc top-1 dưới ngưỡng. (make do-giao-viec)
    python3 scripts/demo.py ky-so
        Ký số văn bản đi (F4.5, CHỈ MINH HỌA — CA nội bộ trong két, không có giá trị pháp lý như chữ ký số công cộng):
        CA gốc mẫu trong két OpenBao; văn thư phát hành, bản PDF ký PAdES bằng khóa của đơn vị nằm trong Transit của
        két; cổng xác thực cho biết ai ký, CA nào cấp; pyHanko trong svc-files báo hợp lệ, báo "đã bị sửa sau khi ký"
        khi thêm một chú thích, báo không khớp khi lật một bit; văn bản hạn chế không được ký; văn bản cũ không chữ
        ký vẫn xác thực như cũ. (make demo-ky-so)
    python3 scripts/demo.py che-pii
        Che thông tin cá nhân (F4.4, không cần mô hình): văn thư tải một lá đơn giả lập có số CCCD, số điện thoại,
        email, số tài khoản; tìm theo số CCCD ra đúng lá đơn, trợ lý trích nguyên văn có đúng số điện thoại (người
        được xem văn bản thấy bản gốc); tệp EICAR tên có số điện thoại bị chặn, sổ kiểm toán giữ tên gốc; nhật ký
        apisix, app-office, svc-files, svc-workflow từ lúc bắt đầu màn không còn giá trị nào ở bất kỳ cách viết nào,
        dòng truy cập không còn chuỗi truy vấn; bật profile ai thì mô hình chỉ thấy nhãn [SĐT-1]. (make demo-che-pii)
    python3 scripts/demo.py do-so-lieu-sau
        Số đo "sau" của đặc tả §8 (F4.6, docs/so-lieu-sau.md) bằng quyền lãnh đạo đơn vị: thời gian từ khi văn bản
        đến tới khi được giao xử lý (trung vị, p90), tỷ lệ xử lý quá hạn, 5 lần tìm lại văn bản đến cũ nhất qua
        /api/search (độ trễ hệ thống), số bước chuyển tay chỉ so sánh định tính; cột "trước" ghi chưa đo. In bảng,
        ghi out/so-lieu-sau.json; thoát 1 khi không đủ 5 văn bản để tìm hoặc một lần tìm không ra văn bản cần tìm
        trong 20 kết quả đầu. (make do-so-lieu-sau)
    python3 scripts/demo.py nap-lo
        Nạp lô văn bản đến qua API (cụm ⑤ Tầng 1): văn thư Khoa Kinh tế gửi 200 văn bản đến một lần (NDJSON + zip tệp
        đính kèm, scripts/nap_lo_mau.py); svc-files xử lý nền, mỗi dòng đi đúng đường tiếp nhận lẻ (ClamAV, Action
        receiveIncoming thay mặt văn thư); lỗi từng dòng đúng bảng dòng sai cố ý, tệp EICAR trong zip bị chặn, mỗi văn
        bản một dòng sổ kiểm toán, dòng có tệp bị Action từ chối được gỡ tệp; gửi lại không nhân đôi văn bản hay tệp;
        lô 5 dòng register=true có số đến trong sổ. (make demo-nap-lo)
    python3 scripts/demo.py log-tap-trung
        Log tập trung (F3.14, profile logs — chưa bật thì màn tự bật bằng make logs-up và để nguyên): văn thư phát hành
        một công văn với X-Request-Id tự đặt; yêu cầu đi qua APISIX → Hasura → svc-workflow → svc-files; tra
        Parseable theo mã đó ra dòng của cả ba dịch vụ, sổ kiểm toán có dòng cùng mã; không đăng nhập thì không đọc
        được kho log; không dòng nào có token, cookie, chuỗi truy vấn; docker logs vẫn đọc được; Vector chạy lại thì
        dòng đầu tiên của dịch vụ đang im ghi sau đó vẫn tới kho. (make demo-log-tap-trung)
    python3 scripts/demo.py cai-ung-dung
        Cắm ứng dụng thứ ba bằng MỘT lệnh (docs/them-ung-dung.md mục 1): `moc app install apps/bang-tin/app.yaml` —
        kế hoạch --dry-run không đổi gì; cài xong mở /bang-tin/ qua APISIX, đăng nhập một lần (client app-bang-tin,
        PKCE S256, không hỏi lại mật khẩu), GraphQL trên bảng của ứng dụng; văn thư vào sổ văn bản đến → ứng dụng nhận
        sự kiện qua Event Trigger, văn bản hạn chế thì không; cài lại không tạo gì mới; gỡ thì route, client, trigger,
        container mất, dữ liệu còn; git status trước và sau giống hệt: không tệp nào của lõi đổi. (make
        demo-cai-ung-dung)
    python3 scripts/demo.py quy-trinh
        Quy trình của ứng dụng chạy trên lõi (#301, docs/them-ung-dung.md mục Đơn nghỉ phép): cài apps/nghi-phep —
        BPMN, form của ứng dụng lên động cơ quy trình của lõi; bản có scriptTask bị từ chối trước khi đổi gì; nhân viên
        gửi đơn qua API chung bằng token app-nghi-phep (dữ liệu sai → 422 đúng mã từng trường); chỉ trưởng phòng cùng
        phòng thấy và duyệt được; token của client khác → 403; hộp việc Văn phòng điện tử không lẫn việc nghỉ phép;
        duyệt → đơn kết thúc với quyết định đồng ý; cài lại không đổi gì; gỡ giữ lịch sử đơn. (make demo-quy-trinh)
    python3 scripts/demo.py canh-bao
        Cảnh báo vận hành (F3.13, #284): Prometheus nối Alertmanager; một cảnh báo giả đẩy vào Alertmanager thành thông
        báo ở chuông của quản trị mọi đơn vị (quantri thấy qua GraphQL), không ai khác nhận; hết cảnh báo thì mỗi quản
        trị thêm đúng một thông báo; gọi svc-workflow bằng token sai → 401; dịch vụ ngoài mạng alerts không tới được
        API của Alertmanager. Thông báo của màn đánh dấu đã đọc ở cuối. (make demo-canh-bao)

Thoát 0 khi màn chạy đúng như kịch bản, 1 khi có bước sai (in rõ bước nào).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import time
import unicodedata
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import nap_lo_mau
from moc_env import (EICAR, ENV, PUBLIC_URL, ROOT, HTTPError, Session, call_json, compose, request, text_pdf,
                     user_token)


class DemoFailed(Exception):
    pass


def say(n: int, text: str) -> None:
    print(f"\n{n}. {text}")


def ok(text: str) -> None:
    print(f"   ✓ {text}")


def psql(query: str) -> str:
    out = compose("exec", "-T", "postgres", "psql", "-X", "-q", "-t", "-A", "-U", ENV.get("POSTGRES_USER", "moc"),
                  "-d", ENV.get("POSTGRES_DB", "moc"), "-c", query)
    return out.decode().strip()


def moc(*args: str) -> tuple[int, str, str]:
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "moc.py"), *args], cwd=ROOT, capture_output=True,
                       text=True)
    return r.returncode, r.stdout, r.stderr


def error_detail(exc: HTTPError) -> dict[str, Any]:
    try:
        detail = json.loads(exc.body).get("detail")
    except (ValueError, AttributeError):
        return {}
    return detail if isinstance(detail, dict) else {"message": detail}


def vault_status() -> dict[str, Any]:
    """`bao status` trong container két; két đang khóa thì lệnh thoát 2 nhưng vẫn in trạng thái."""
    try:
        raw = compose("exec", "-T", "openbao", "bao", "status", "-format=json")
    except subprocess.CalledProcessError as exc:
        raw = exc.stdout or b"{}"
    try:
        return json.loads(raw)
    except ValueError:
        return {"error": raw.decode(errors="replace")[:200]}


def last_audit_id(director: Session) -> int:
    agg = director.gql("{ core_audit_log_aggregate { aggregate { max { id } } } }")["core_audit_log_aggregate"]
    return agg["aggregate"]["max"]["id"] or 0


def kiem_dich() -> None:
    print("Màn (iv) · Kiểm dịch tại cửa ngõ — mọi tệp tải lên qua cổng APISIX đều đi qua ClamAV trước khi vào kho")
    tag = uuid.uuid4().hex[:6].upper()
    clerk, director = Session("vanthu"), Session("truongkhoa")

    say(1, "Văn thư tải lên một công văn bình thường")
    clean = clerk.upload(f"cong-van-{tag}.pdf", text_pdf("Cong van de nghi phoi hop", f"Ma thu {tag}"))
    ok(f"cong-van-{tag}.pdf → 201: ClamAV báo sạch, đã lưu vào kho (SHA-256 {clean['sha256'][:16]}…)")

    say(2, "Văn thư tải lên hoa-don.pdf chứa chuỗi kiểm thử EICAR (chuẩn để thử phần mềm diệt virus, vô hại)")
    name = f"hoa-don-{tag}.pdf"
    before = last_audit_id(director)
    try:
        clerk.upload(name, EICAR)
        raise DemoFailed("tệp EICAR không bị chặn")
    except HTTPError as exc:
        detail = error_detail(exc)
        if exc.status != 422 or detail.get("code") != "infected":
            raise DemoFailed(f"tệp EICAR trả {exc.status} {detail or exc.body[:200]}") from exc
    ok(f"{name} → 422 infected: ClamAV báo {detail.get('signature')} — tệp bị chặn ngay ở cửa ngõ")

    sha = hashlib.sha256(EICAR).hexdigest()
    say(3, "Không có gì của tệp nhiễm lọt vào hệ thống")
    stored = psql(f"select count(*) from core.files where sha256 = '\\x{sha}'")
    if stored != "0":
        raise DemoFailed(f"core.files có {stored} dòng với SHA-256 của tệp EICAR")
    ok(f"core.files: 0 dòng có SHA-256 {sha[:16]}… — tệp không được ghi nhận, svc-files không ghi gì vào kho")

    say(4, "Lần chặn nằm trong sổ kiểm toán chuỗi băm — lãnh đạo khoa đọc sổ của đơn vị, đúng quyền của mình")
    rows = director.gql(
        """query ($h: String!, $after: bigint!) {
             core_audit_log(where: {action: {_eq: "file.rejected"}, entity_id: {_eq: $h}, id: {_gt: $after}},
                            order_by: {id: desc}, limit: 1) { id occurred_at actor_id hash overview }
           }""", {"h": sha, "after": before})["core_audit_log"]
    if not rows:
        raise DemoFailed(f"sổ kiểm toán không có dòng file.rejected của {name}")
    row = rows[0]
    overview = row["overview"]
    clerk_id = clerk.gql('{ core_users(where: {username: {_eq: "vanthu"}}) { id } }')["core_users"][0]["id"]
    if not overview.get("signature") or overview.get("filename") is not None or row["actor_id"] != clerk_id:
        raise DemoFailed(f"dòng #{row['id']} không đúng: người tải {row['actor_id']}, tóm tắt {overview}")
    ok(f"dòng #{row['id']} file.rejected · {row['occurred_at'][:19].replace('T', ' ')} · người tải: vanthu · "
       f"mẫu mã độc {row['overview']['signature']} · tên tệp ẩn (có thể nói lên nội dung) · "
       f"hash dòng {str(row['hash']).removeprefix(chr(92) + 'x')[:16]}…")

    say(5, "Neo đầu chuỗi ra bucket lạnh khóa ghi, rồi tính lại cả chuỗi bên ngoài CSDL")
    code, out, err = moc("audit", "anchor")
    if code != 0 or not out.strip():
        raise DemoFailed(f"không neo được đầu chuỗi:\n{out}{err}")
    print("   " + out.strip().splitlines()[0])
    # Kho lưu giờ ghi mốc theo giây: verify bỏ qua mốc ghi trong 2 giây trước lúc đọc CSDL (đối chiếu ở lần sau),
    # nên đợi qua khoảng đó để mốc vừa neo được đối chiếu ngay lần này
    time.sleep(3)
    code, out, err = moc("audit", "verify", "--json")
    try:
        report = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise DemoFailed(f"moc audit verify không trả kết quả:\n{out}{err}") from exc
    anchored = (report.get("latest_anchor") or {}).get("audit_id") or 0
    if code != 0 or not report["ok"] or not report["complete"] or anchored < row["id"]:
        reasons = [f"{p['kind']} ở dòng #{p['audit_id']}" for p in report["problems"]] + report["gaps"]
        if anchored < row["id"]:
            reasons.append(f"mốc neo mới nhất ở dòng #{anchored}, chưa tới dòng #{row['id']}")
        raise DemoFailed("sổ kiểm toán chưa được xác nhận:\n   - " + "\n   - ".join(reasons or [err.strip()]))
    ok(f"{report['rows']} dòng, chuỗi liền mạch tới #{report['last_id']}, đã neo tới dòng mới nhất — sửa hay xóa "
       f"dòng #{row['id']} đều bị phát hiện")

    print(f"\nXem trên giao diện (lãnh đạo khoa): {PUBLIC_URL}/so-kiem-toan?loai=files — dòng \"Chặn tệp nhiễm mã độc\"")


# Đọc thẳng đối tượng trong kho tệp từ container svc-files (khóa kho lấy từ két như svc-files): 4 byte đầu, cỡ,
# có đầu PDF hay chữ cần tìm không
PEEK = """import os, sys
from svc_files.config import Settings
from svc_files.openbao import with_secrets
from svc_files.storage import s3_client
s = Settings.from_env(with_secrets(os.environ))
c = s3_client(s.s3_endpoint, s.s3_access_key, s.s3_secret_key, s.s3_region)
b = c.get_object(Bucket=s.bucket, Key=sys.argv[1])['Body'].read()
print(b[:4].decode('latin-1'), len(b), b'%PDF' in b, sys.argv[2].encode() in b)
"""

# Chữ trên trang đầu của PDF đưa vào stdin (pypdf có sẵn trong svc-files)
PAGE_TEXT = "import io, sys, pypdf; print(pypdf.PdfReader(io.BytesIO(sys.stdin.buffer.read())).pages[0].extract_text())"


def han_che() -> None:
    print("Màn (iv) · Văn bản hạn chế — tệp mã hóa trong kho, chỉ người có tên mới mở được, mỗi lần mở có dấu tên "
          "và vào sổ")
    tag = uuid.uuid4().hex[:6].upper()
    clerk, director, manager = Session("vanthu"), Session("truongkhoa"), Session("totruongdt")

    say(1, "Văn thư tải lên danh sách nâng lương trước hạn ở chế độ hạn chế")
    marker = f"MATKIN{tag}"
    pdf = clerk.upload(f"nang-luong-{tag}.pdf", text_pdf("Danh sach nang luong truoc han nam 2026", f"Ma thu {marker}"),
                       restricted=True)
    if not pdf.get("encrypted"):
        raise DemoFailed(f"tệp tải lên ở chế độ hạn chế không được mã hóa: {pdf}")
    key, wrapped = psql(f"select object_key, split_part(wrapped_dek, ':', 1) || ':' || split_part(wrapped_dek, ':', 2) "
                        f"from core.files where id = '{pdf['id']}'").split("|")
    head, size, has_pdf, has_marker = compose("exec", "-T", "svc-files", "python", "-c", PEEK, key,
                                              marker).decode().split()
    if (head, has_pdf, has_marker) != ("MOC1", "False", "False") or wrapped != "vault:v1":
        raise DemoFailed(f"đối tượng trong kho chưa phải bản mã: {head} {has_pdf} {has_marker}, khóa {wrapped}")
    ok(f"svc-files xin két OpenBao một khóa AES-256 riêng cho tệp, mã hóa (AES-GCM) rồi mới lưu: trong kho là {size} "
       f"byte bắt đầu bằng MOC1, không có đầu %PDF, không có chữ {marker}")
    ok(f"CSDL chỉ giữ khóa đã bọc bằng khóa của két ({wrapped}:…) — lấy được CSDL và kho tệp cũng không đọc được")

    say(2, "Văn thư tiếp nhận văn bản hạn chế; quy trình giao lãnh đạo khoa cho ý kiến chỉ đạo")
    symbol = f"88/ĐHCN-TCCB{tag}"
    doc_id = clerk.gql("mutation ($d: jsonb!) { receiveIncoming(data: $d) { document_id } }", {"d": {
        "type_code": "CV", "symbol": symbol, "issuer_name": "Trường Đại học Công nghiệp",
        "issued_on": datetime.now(timezone(timedelta(hours=7))).date().isoformat(), "urgency": "normal",  # giờ VN
        "restricted": True, "summary": f"Về việc nâng lương trước hạn năm 2026 (demo {tag})", "file_ids": [pdf["id"]],
    }})["receiveIncoming"]["document_id"]
    number = clerk.gql("mutation ($id: uuid!) { registerIncoming(documentId: $id) { register_number } }",
                       {"id": doc_id})["registerIncoming"]["register_number"]
    names = {u["id"]: u["username"] for u in clerk.gql("{ core_users { id username } }")["core_users"]}
    viewers = clerk.gql("query ($d: uuid!) { office_document_acl(where: {document_id: {_eq: $d}}) { user_id } }",
                        {"d": doc_id})["office_document_acl"]
    if "truongkhoa" not in [names.get(v["user_id"]) for v in viewers]:
        raise DemoFailed(f"lãnh đạo nhận việc mà không có tên trong danh sách được xem: {viewers}")
    ok(f"{symbol} vào sổ, số đến {number}; svc-workflow tự thêm người nhận việc vào danh sách được xem: "
       f"{', '.join(sorted(names.get(v['user_id'], v['user_id']) for v in viewers))}")

    say(3, "Tổ trưởng Tổ Đào tạo không có tên trong danh sách")
    seen = manager.gql("query ($d: uuid!) { office_documents_by_pk(id: $d) { id } }", {"d": doc_id})
    try:
        request("GET", f"{PUBLIC_URL}/api/files/{pdf['id']}", headers=manager.auth)
        raise DemoFailed("tổ trưởng không có tên vẫn tải được tệp")
    except HTTPError as exc:
        if exc.status != 404:
            raise DemoFailed(f"tổ trưởng tải tệp trả {exc.status}") from exc
    if seen["office_documents_by_pk"] is not None:
        raise DemoFailed("tổ trưởng không có tên vẫn đọc được văn bản")
    ok("không đọc được văn bản; mở thẳng đường dẫn tệp → 404, y như tệp không tồn tại")

    say(4, "Lãnh đạo khoa mở tệp: giải mã trong bộ nhớ, đóng dấu tên người xem và giờ xem lên mọi trang")
    _, headers, opened = request("GET", f"{PUBLIC_URL}/api/files/{pdf['id']}", headers=director.auth)
    text = compose("exec", "-T", "svc-files", "python", "-c", PAGE_TEXT, stdin=opened).decode()
    stamp = next((line.strip() for line in text.splitlines() if "VĂN BẢN HẠN CHẾ" in line), None)
    cache = next((v for k, v in headers.items() if k.lower() == "cache-control"), "")
    if not stamp or marker not in text or "no-store" not in cache:
        raise DemoFailed(f"bản mở ra chưa có dấu người xem hoặc cho lưu đệm ({cache}):\n{text[:400]}")
    ok(f"dấu trên trang: \"{stamp}\"")
    sha = hashlib.sha256(opened).hexdigest()
    ok(f"Cache-Control: {cache}; mỗi người, mỗi lần mở là một bản khác (SHA-256 {sha[:12]}… ≠ bản gốc "
       f"{pdf['sha256'][:12]}…) — bản rõ không ghi xuống đĩa")

    say(5, "Thông báo việc mới gửi lãnh đạo khoa không mang nội dung văn bản")
    started, notes = time.time(), []
    while not notes and time.time() - started < 15:
        notes = director.gql("query ($d: uuid!) { core_notifications(where: {document_id: {_eq: $d}}) { kind data } }",
                             {"d": doc_id})["core_notifications"]
        notes or time.sleep(1)
    if not notes or any({"summary", "symbol", "issuer_name"} & set(n["data"]) for n in notes):
        raise DemoFailed(f"thông báo về văn bản hạn chế mang nội dung: {notes}")
    ok(f"{notes[0]['kind']}: {json.dumps(notes[0]['data'], ensure_ascii=False)} — CSDL gọt nội dung cho mọi đường ghi")

    say(6, "Sổ kiểm toán: ai đã mở tệp, lúc nào")
    rows = director.gql("""query ($e: String!) { core_audit_log(where: {action: {_eq: "file.decrypted"},
        entity_id: {_eq: $e}}, order_by: {id: asc}) { id occurred_at actor_id } }""",
                        {"e": pdf["id"]})["core_audit_log"]
    if [names.get(r["actor_id"]) for r in rows] != ["truongkhoa"]:
        raise DemoFailed(f"sổ kiểm toán chưa đúng lần mở: {rows}")
    ok(f"dòng #{rows[0]['id']} file.decrypted · {rows[0]['occurred_at'][:19].replace('T', ' ')} · truongkhoa — "
       f"lần tổ trưởng bị từ chối không giải mã gì nên không có dòng")

    print(f"\nXem trên giao diện (văn thư): {PUBLIC_URL}/van-ban/{doc_id} — khóa ở tệp đính kèm, mục người được xem")


# Bí mật svc-files, svc-workflow cần (tên trong .env) — cùng danh sách platform/openbao/start.sh nạp vào két
SECRETS = {"svc-files": ("SEAWEEDFS_S3_ACCESS_KEY", "SEAWEEDFS_S3_SECRET_KEY", "HASURA_ADMIN_SECRET",
                         "MEILI_MASTER_KEY"),
           "svc-workflow": ("HASURA_ADMIN_SECRET", "MOC_ACTION_SECRET", "FLOWABLE_ADMIN_PASSWORD",
                            "CENTRIFUGO_API_KEY", "MOC_DIRECTORY_CLIENT_SECRET")}


def env_hashes(service: str) -> dict[str, str]:
    """SHA-256 từng biến môi trường của dịch vụ: so với bí mật mà không đưa bí mật ra khỏi container."""
    out = compose("exec", "-T", service, "python", "-c",
                  "import hashlib, json, os\nprint(json.dumps({k: hashlib.sha256(v.encode()).hexdigest()"
                  " for k, v in os.environ.items()}))")
    return json.loads(out)


def restart(service: str, *wait_also: str) -> float:
    started = time.monotonic()
    compose("restart", service)
    compose("up", "-d", "--wait", "--wait-timeout", "120", service, *wait_also)
    return time.monotonic() - started


def ket_bi_mat() -> None:
    print("Màn (iv) · Két bí mật — dịch vụ lấy bí mật từ két OpenBao bằng AppRole riêng, không qua biến môi trường")
    tag = uuid.uuid4().hex[:6].upper()
    clerk = Session("vanthu")

    say(1, "svc-files, svc-workflow không có bí mật nào trong biến môi trường")
    for service, names in SECRETS.items():
        hashed = env_hashes(service)
        wanted = {hashlib.sha256(ENV[n].encode()).hexdigest(): n for n in names}
        leaked = sorted(f"{wanted[h]} (biến {k})" for k, h in hashed.items() if h in wanted)
        if leaked:
            raise DemoFailed(f"{service} còn nhận bí mật qua biến môi trường: {', '.join(leaked)}")
        found = sorted(k for k in hashed if k.startswith("MOC_OPENBAO_"))
        ok(f"{service}: 0/{len(names)} bí mật trong env (so băm giá trị) — chỉ có địa chỉ két: {', '.join(found)}")

    say(2, "Khởi động lại két: static seal tự mở khóa, không ai phải nhập khóa")
    since = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # svc-files, svc-workflow phụ thuộc két (restart: true) nên khởi động lại theo: chờ cả hai sẵn sàng
    took = restart("openbao", "svc-files", "svc-workflow")
    seal = vault_status()
    if seal.get("sealed") is not False or seal.get("type") != "static":
        raise DemoFailed(f"két chưa mở khóa sau khi khởi động lại: {seal}")
    ok(f"openbao khởi động lại, mở khóa và cấp lại AppRole; hai dịch vụ lấy lại bí mật — sẵn sàng sau {took:.0f} "
       f"giây · seal {seal['type']}, sealed={seal['sealed']}")

    say(3, "Khởi động lại svc-files: đăng nhập két bằng AppRole, lấy khóa kho S3, rồi nhận tệp như thường")
    took = restart("svc-files")
    stored = clerk.upload(f"sau-khoi-dong-{tag}.pdf", text_pdf("Kiem tra ket bi mat", f"Ma thu {tag}"))
    ok(f"svc-files sẵn sàng sau {took:.0f} giây; tải tệp → 201, vào kho bằng khóa S3 lấy từ két "
       f"(SHA-256 {stored['sha256'][:16]}…)")

    say(4, "Mỗi dịch vụ chỉ đọc được bí mật của mình")
    cross = compose("exec", "-T", "svc-workflow", "python", "-c",
                    "import os\nfrom svc_workflow.config import ConfigError\n"
                    "from svc_workflow.openbao import with_secrets\n"
                    "try:\n    with_secrets({**os.environ, 'MOC_OPENBAO_SECRET_PATH': 'moc/data/svc-files'},\n"
                    "                 attempts=1)\n"
                    "    print('read')\nexcept ConfigError as exc:\n    print('refused', exc)\n").decode().strip()
    if not cross.startswith("refused") or "403" not in cross:
        raise DemoFailed(f"svc-workflow đọc được bí mật của svc-files: {cross}")
    ok("AppRole svc-workflow đọc moc/data/svc-files → két từ chối (403)")

    say(5, "Két ghi sổ mọi lần truy cập; giá trị bí mật trong sổ đã băm HMAC")
    logs = compose("logs", "--no-log-prefix", "--since", since, "openbao").decode()
    if any(ENV[n] in logs for names in SECRETS.values() for n in names):
        raise DemoFailed("sổ truy cập của két chứa giá trị bí mật")
    reads = []
    for line in logs.splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get("type") != "response":
            continue
        path = (entry.get("request") or {}).get("path")
        role = ((entry.get("auth") or {}).get("metadata") or {}).get("role_name")
        if path in ("auth/approle/login", "moc/data/svc-files", "moc/data/svc-workflow") and role:
            what = "đăng nhập" if path.startswith("auth/") else f"đọc {path}"
            if entry.get("error"):
                # lỗi của két có dạng "1 error occurred:\n\t* permission denied\n": gom về một dòng
                reason = " ".join(str(entry["error"]).replace("1 error occurred:", "").replace("*", " ").split())
                what += f" → bị từ chối ({reason})"
            try:   # sổ ghi giờ UTC, in theo giờ máy
                at = datetime.strptime(entry["time"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                when = at.astimezone().strftime("%H:%M:%S")
            except (KeyError, TypeError, ValueError):
                when = "?"
            reads.append(f"{when} {role} {what}")
    if not any(r.endswith("svc-files đọc moc/data/svc-files") for r in reads):
        raise DemoFailed(f"sổ của két không có lần svc-files đọc bí mật: {reads}")
    if not any("svc-workflow đọc moc/data/svc-files → bị từ chối" in r for r in reads):
        raise DemoFailed(f"sổ của két không ghi lần svc-workflow đọc chéo bị từ chối: {reads}")
    for r in reads[-4:]:
        print(f"   · {r}")
    ok(f"{len(reads)} lần đăng nhập/đọc từ lúc khởi động lại két, kể cả lần đọc chéo bị từ chối; không giá trị bí "
       f"mật nào xuất hiện rõ trong sổ")

    print("\nXem sổ của két: docker compose logs openbao · trạng thái: docker compose exec openbao bao status")


def service_state(service: str) -> str:
    """Trạng thái container của dịch vụ: "không có", "running (healthy)", "exited"…"""
    raw = compose("ps", "-a", "--format", "json", service).decode().strip()
    rows = json.loads(raw) if raw.startswith("[") else [json.loads(line) for line in raw.splitlines() if line]
    if not rows:
        return "không có container"
    row = rows[0]
    return f"{row.get('State')}" + (f" ({row['Health']})" if row.get("Health") else "")


def reconcile_pass() -> tuple[int, str]:
    """Một lượt tự phục hồi (không kéo commit từ git); timer của máy chủ đang chạy một lượt thì đợi nó xong."""
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "reconcile.py"), "--heal-only", "--wait", "300"],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def tu_phuc_hoi() -> None:
    print("Màn (iv) · Tự phục hồi — reconciler đưa hệ thống đang chạy về đúng trạng thái khai trong compose (git)")
    tag = uuid.uuid4().hex[:6].upper()
    clerk = Session("vanthu")

    say(1, "Trước khi phá: một lượt reconciler thấy hệ thống đã khớp khai báo")
    code, out = reconcile_pass()
    if code != 0 or "không có gì phải làm" not in out:
        raise DemoFailed(f"hệ thống chưa khớp khai báo trước khi bắt đầu:\n{out}")
    for line in out.splitlines():
        print(f"   {line}")

    say(2, "Phá: xóa hẳn container svc-files (docker rm -f), dừng centrifugo (docker stop)")
    files_id = compose("ps", "-q", "svc-files").decode().strip()
    realtime_id = compose("ps", "-q", "centrifugo").decode().strip()
    if not files_id or not realtime_id:
        raise DemoFailed("svc-files hoặc centrifugo không chạy")
    subprocess.run(["docker", "rm", "-f", files_id], check=True, capture_output=True)
    subprocess.run(["docker", "stop", realtime_id], check=True, capture_output=True)
    try:
        clerk.upload(f"luc-hong-{tag}.pdf", text_pdf("Thu khi svc-files mat", f"Ma thu {tag}"))
        raise DemoFailed("svc-files đã bị xóa mà vẫn nhận tệp")
    except HTTPError as exc:
        ok(f"svc-files: {service_state('svc-files')} · centrifugo: {service_state('centrifugo')} · tải tệp → "
           f"{exc.status} (cổng không tới được dịch vụ)")

    say(3, "Một lượt reconciler — systemd timer gọi mỗi 60 giây, ở đây gọi ngay cho khỏi chờ")
    started = time.monotonic()
    code, out = reconcile_pass()
    for line in out.splitlines():
        print(f"   {line}")
    if code == 0 and "không có gì phải làm" in out and compose("ps", "-q", "svc-files").decode().strip():
        # máy chủ đã bật timer (platform/systemd/) và lượt của timer chạy trước lượt này
        print("   (timer reconciler của máy chủ đã dựng lại trước lượt gọi tay này)")
    elif code != 0 or "dựng lại svc-files" not in out or "chạy lại centrifugo" not in out:
        raise DemoFailed("reconciler không dựng lại đủ hai dịch vụ")

    say(4, "Hệ thống trở lại: dịch vụ healthy, tải tệp được")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        states = {s: service_state(s) for s in ("svc-files", "centrifugo")}
        if all(v == "running (healthy)" for v in states.values()):
            break
        time.sleep(2)
    else:
        raise DemoFailed(f"sau 2 phút vẫn chưa healthy: {states}")
    healthy = time.monotonic()
    # APISIX hỏi lại DNS mỗi 5 giây (dns_resolver_valid): vừa healthy thì cổng có thể còn trỏ địa chỉ container cũ và
    # trả 502/503 một lúc. Thử lại tối đa 30 giây, in đúng số giây đã chờ
    while True:
        try:
            stored = clerk.upload(f"sau-phuc-hoi-{tag}.pdf", text_pdf("Thu sau khi tu phuc hoi", f"Ma thu {tag}"))
            break
        except HTTPError as exc:
            if exc.status not in (502, 503) or time.monotonic() - healthy > 30:
                raise
            time.sleep(2)
    gateway = time.monotonic() - healthy
    ok(f"svc-files, centrifugo healthy sau {healthy - started:.0f} giây kể từ lượt reconciler; tải tệp → 201"
       + (f" sau {gateway:.0f} giây chờ cổng nhận container mới" if gateway >= 1 else "")
       + f" (SHA-256 {stored['sha256'][:16]}…)")

    print("\nTrên máy chủ thật: platform/systemd/moc-reconcile.timer · nhật ký: journalctl -u moc-reconcile")


CREATE_CASE_FILE = """
mutation ($o: office_case_files_insert_input!) { insert_office_case_files_one(object: $o) { id code } }"""
ADD_TO_CASE_FILE = """
mutation ($o: office_case_file_documents_insert_input!) {
  insert_office_case_file_documents_one(object: $o) { document_id }
}"""
CLOSE_CASE_FILE = """
mutation ($id: uuid!) {
  update_office_case_files(where: {id: {_eq: $id}}, _set: {status: "closed"}) { affected_rows }
}"""

# Văn bản người lập hồ sơ được đưa vào (cùng quy tắc với quyền Hasura): đã xong, không hạn chế, chưa thuộc hồ sơ nào;
# văn bản đi của phòng mình, văn bản đến giao cho mình (tổ trưởng: giao cho phòng mình). Chọn người có nhiều văn bản
# như thế nhất, để chạy demo nhiều lần sau một lần seed vẫn còn văn bản.
FILEABLE = """
select u.username, d.id from office.documents d join core.users u on u.tenant_id = d.tenant_id
 where u.role in ('staff', 'manager') and u.enabled and not d.restricted
   and not exists (select 1 from office.case_file_documents c where c.document_id = d.id)
   and ((d.direction = 'out' and d.status = 'issued' and d.department_id = u.department_id)
     or (d.direction = 'in' and d.status = 'done' and exists (select 1 from office.assignments a
          where a.document_id = d.id and a.status <> 'cancelled'
            and ((u.role = 'staff' and a.user_id = u.id)
              or (u.role = 'manager' and a.department_id = u.department_id)))))
 order by u.role = 'staff' desc, d.direction = 'out' desc, d.created_at"""


def oltp_detail(ids: list[str]) -> dict[str, int]:
    """Số dòng chi tiết của các văn bản trong CSDL nghiệp vụ (OLTP)."""
    inlist = ", ".join(f"'{i}'" for i in ids)
    row = psql(f"select (select count(*) from office.document_files where document_id in ({inlist})),"
               f" (select count(*) from office.document_events where document_id in ({inlist})),"
               f" (select count(*) from office.assignments where document_id in ({inlist}))")
    files, events, assignments = (int(x) for x in row.split("|"))
    return {"liên kết tệp": files, "dòng thời gian": events, "giao việc": assignments}


ARCHIVE_STATS_RUN = """query { core_lineage_events(where: {job: {_eq: "moc.archive.stats"}}, order_by: {id: desc},
  limit: 1) { inputs } }"""


def archive_stats(session: Session) -> dict[str, Any]:
    """Số liệu đã nộp lưu của trang Điều hành (#304): DuckDB đếm trên các gói Parquet trong bucket lạnh."""
    stats, _ = call_json("GET", f"{PUBLIC_URL}/api/case-files/archive-stats", headers=session.auth)
    return stats


def year_counts(stats: dict[str, Any]) -> Counter:
    counts: Counter = Counter()
    for r in stats["by_year"]:
        counts[(r["year"], "in")] += r["incoming"]
        counts[(r["year"], "out")] += r["outgoing"]
    return counts


def check_archive_stats(director: Session, staff: Session, before: dict[str, Any], docs: dict[str, dict[str, Any]],
                        done: dict[str, Any]) -> None:
    """Màn nóng → lạnh, bước 5: số liệu lạnh tăng đúng bằng hồ sơ vừa nộp lưu (tổng, theo năm ban hành và chiều), chỉ
    lãnh đạo đơn vị đọc được, phả hệ ghi lượt DuckDB đọc các gói."""
    started = time.monotonic()
    after = archive_stats(director)
    elapsed = time.monotonic() - started
    grown = year_counts(after)
    grown.subtract(year_counts(before))
    changed = {k: v for k, v in grown.items() if v}
    expected = dict(Counter((d["year"], d["direction"]) for d in docs.values()))
    if after["case_files"] - before["case_files"] != 1 or after["documents"] - before["documents"] != len(docs) \
            or changed != expected:
        raise DemoFailed(f"số liệu lạnh chưa khớp hồ sơ vừa nộp lưu: trước {before['case_files']} hồ sơ,"
                         f" {before['documents']} văn bản; sau {after['case_files']}, {after['documents']};"
                         f" theo năm tăng {changed}, cần {expected}")
    if any(u["case_file_id"] == done["case_file_id"] for u in after["unreadable"]):
        raise DemoFailed("gói vừa nộp lưu không đọc lại được để phân tích")
    ok(f"lãnh đạo đơn vị: {after['case_files']} hồ sơ, {after['documents']} văn bản đã nộp lưu (đến"
       f" {after['incoming']}, đi {after['outgoing']}) — thêm 1 hồ sơ, {len(docs)} văn bản so với trước bước 2;"
       f" {elapsed:.1f} giây")
    ok("theo năm ban hành: " + "; ".join(f"{r['year'] or '?'}: đến {r['incoming']}, đi {r['outgoing']}"
                                         for r in after["by_year"]))
    try:
        archive_stats(staff)
    except HTTPError as exc:
        if exc.status != 403:
            raise DemoFailed(f"chuyên viên gọi số liệu đã nộp lưu trả {exc.status}") from exc
    else:
        raise DemoFailed("chuyên viên đọc được số liệu đã nộp lưu của cả đơn vị")
    ok("chuyên viên gọi cùng API → 403: như trang Điều hành, chỉ lãnh đạo đơn vị")
    runs = director.gql(ARCHIVE_STATS_RUN)["core_lineage_events"]
    table = f"s3://{after['bucket']}/{done['archive_key']}documents-"
    if not runs or not any(name.startswith(table) for name in runs[0]["inputs"]):
        raise DemoFailed("phả hệ chưa ghi lượt DuckDB đọc gói vừa nộp lưu (job moc.archive.stats)")
    ok(f"phả hệ: run moc.archive.stats đọc {len(runs[0]['inputs'])} bảng Parquet, có bảng văn bản của gói vừa nộp lưu")


def nong_lanh() -> None:
    print("Màn (i) · Vòng đời dữ liệu: nóng → lạnh — hồ sơ đã đóng được nộp lưu thành gói Parquet + tệp + manifest có"
          " băm trên bucket lạnh khóa ghi; CSDL nghiệp vụ chỉ giữ bản ghi rút gọn")
    tag = uuid.uuid4().hex[:6].upper()
    clerk = Session("vanthu")

    say(1, "Chuyên viên lập hồ sơ công việc, đưa văn bản đã xong vào, đóng hồ sơ (NĐ 30/2020, Điều 28–29)")
    # văn bản đi đã phát hành (có mã QR) và văn bản đến đã xử lý xong mà người lập hồ sơ được đưa vào
    by_user: dict[str, list[str]] = {}
    for row in psql(FILEABLE).splitlines():
        username, doc_id = row.split("|")
        by_user.setdefault(username, []).append(doc_id)
    if not by_user:
        raise DemoFailed("không còn văn bản đã xong nào chưa nộp lưu — chạy make seed (hoặc make smoke) để có thêm")
    username = max(by_user, key=lambda u: min(len(by_user[u]), 3))   # bằng nhau thì giữ thứ tự: chuyên viên trước
    ids = by_user[username][:3]
    staff = Session(username)
    docs = {}
    for row in psql("select id, direction, coalesce(symbol, ''), coalesce(verify_code, ''),"
                    " coalesce(extract(year from issued_on)::int::text, ''), summary from"
                    f" office.documents where id in ({', '.join(repr(i) for i in ids)})").splitlines():
        i, direction, symbol, code, year, summary = row.split("|", 5)
        docs[i] = {"direction": direction, "symbol": symbol, "verify_code": code, "summary": summary,
                   "year": int(year) if year else datetime.now().year}   # thiếu ngày ban hành: năm của hồ sơ
    # số liệu đã nộp lưu trước khi nộp lưu hồ sơ này (bước 5 so lại): lãnh đạo đơn vị của người lập hồ sơ
    director = Session(psql("select d.username from core.users d join core.users s on s.tenant_id = d.tenant_id"
                            f" where s.username = '{username}' and d.role = 'director' and d.enabled"
                            " order by d.username limit 1"))
    cold_before = archive_stats(director)
    cf = staff.gql(CREATE_CASE_FILE, {"o": {"year": datetime.now().year, "code": f"HS-{tag}",
                                            "title": f"Hồ sơ thử nộp lưu {tag}", "retention_years": 10}})
    cf = cf["insert_office_case_files_one"]
    for i in ids:
        staff.gql(ADD_TO_CASE_FILE, {"o": {"case_file_id": cf["id"], "document_id": i}})
    staff.gql(CLOSE_CASE_FILE, {"id": cf["id"]})
    for d in docs.values():
        ok(f"{'đi' if d['direction'] == 'out' else 'đến'} {d['symbol']} — {d['summary'][:60]}")
    before = oltp_detail(ids)
    ok(f"{username} lập hồ sơ {cf['code']}, đóng (ngày đóng do CSDL đặt); trong CSDL nghiệp vụ: "
       + ", ".join(f"{v} dòng {k}" for k, v in before.items()))

    say(2, "Nộp lưu (job svc-files; vòng nền chạy mỗi giờ cho hồ sơ đóng quá MOC_ARCHIVE_AFTER_DAYS, ở đây gọi ngay)")
    started = time.monotonic()
    out = compose("exec", "-T", "svc-files", "python", "-m", "svc_files.archive", "now", "--case-file", cf["id"])
    result = json.loads(out.decode().strip().splitlines()[-1])
    if "error" in result:
        raise DemoFailed(f"nộp lưu lỗi: {result['error']}")
    done = result["archived"][0]
    ok(f"gói s3://moc-cold/{done['archive_key']} — {done['documents']} văn bản, {done['files']} tệp,"
       f" {done['bytes']:,} byte, {time.monotonic() - started:.1f} giây".replace(",", "."))
    ok(f"manifest-{done['archive_sha256'][:16]}….json — băm của nó ghi vào case_files.archive_sha256 và sổ kiểm toán;"
       " mọi đối tượng khóa ghi COMPLIANCE 10 năm")

    say(3, "CSDL nghiệp vụ chỉ còn bản ghi rút gọn")
    after = oltp_detail(ids)
    if after["liên kết tệp"] or after["dòng thời gian"] or after["giao việc"] != before["giao việc"]:
        raise DemoFailed(f"CSDL sau nộp lưu chưa đúng: {after}")
    states = psql(f"select string_agg(distinct status, ',') from office.documents where id in"
                  f" ({', '.join(repr(i) for i in ids)})")
    if states != "archived":
        raise DemoFailed(f"văn bản chưa ở trạng thái archived: {states}")
    ok(f"văn bản: trạng thái archived (dòng rút gọn: số, ký hiệu, trích yếu, băm, mã tra cứu);"
       f" liên kết tệp {before['liên kết tệp']} → 0, dòng thời gian {before['dòng thời gian']} → 0;"
       f" giữ {before['giao việc']} dòng giao việc (căn cứ quyền xem, sổ đăng ký)")
    ok("tệp: bản trong bucket nóng đã xóa, core.files chuyển storage_tier = cold")

    say(4, "Vẫn tìm thấy, vẫn xác thực được, đọc lại được từ kho lạnh")
    out_doc = next((d for d in docs.values() if d["verify_code"]), None)
    if out_doc:
        verified, _ = call_json("GET", f"{PUBLIC_URL}/api/verify/{out_doc['verify_code']}")
        if verified.get("result") != "valid" or verified["document"]["status"] != "archived":
            raise DemoFailed(f"cổng xác thực trả {verified}")
        ok(f"quét QR {out_doc['verify_code']} → khớp: {out_doc['symbol']} (trạng thái archived, không đăng nhập)")
    first = next(iter(docs.values()))
    deadline = time.monotonic() + 30
    while True:
        found, _ = call_json("GET", f"{PUBLIC_URL}/api/search?q={quote(first['symbol'])}", headers=clerk.auth)
        hits = found["hits"]
        hit = next((h for h in hits if h.get("status") == "archived"), None)
        if hit or time.monotonic() > deadline:
            break
        time.sleep(2)
    if not hit:
        raise DemoFailed(f"tìm '{first['symbol']}' không ra văn bản đã nộp lưu")
    ok(f"văn thư tìm '{first['symbol']}' → ra văn bản, trạng thái archived")
    room, _ = call_json("GET", f"{PUBLIC_URL}/api/case-files/{cf['id']}/archive", headers=clerk.auth)
    if room["manifest_sha256"] != done["archive_sha256"] or len(room["documents"]) != len(ids):
        raise DemoFailed(f"phòng đọc trả {room}")
    ok(f"phòng đọc: manifest khớp băm trong CSDL; DuckDB đọc documents.parquet ra {len(room['documents'])} văn bản: "
       + ", ".join(d["symbol"] or "?" for d in room["documents"]))
    # phòng đọc xem tệp: đọc từ gói lạnh, so băm với manifest, đóng dấu tên người xem, ghi sổ rồi mới trả
    viewable = [f for f in room["files"] if f["viewable"]]
    if viewable:
        _, got, stamped = request("GET", f"{PUBLIC_URL}/api/case-files/{cf['id']}/archive/files/"
                                  f"{viewable[0]['file_id']}", headers=clerk.auth)
        disposition = next((v for k, v in got.items() if k.lower() == "content-disposition"), "")
        if not stamped.startswith(b"%PDF") or not disposition.startswith("inline;") \
                or hashlib.sha256(stamped).hexdigest() == viewable[0]["sha256"]:
            raise DemoFailed(f"phòng đọc trả tệp chưa đúng: {disposition}")
        seen = psql("select count(*) from core.audit_log where action = 'case_file.file_viewed'"
                    f" and entity_id = '{cf['id']}'")
        if seen != "1":
            raise DemoFailed(f"lần xem tệp trong phòng đọc chưa vào sổ kiểm toán ({seen} dòng)")
        ok(f"phòng đọc xem {viewable[0]['filename']}: bản PDF có dấu tên văn thư và giờ xem (khác byte gốc, chỉ xem);"
           " lần xem vào sổ kiểm toán (case_file.file_viewed)")
    else:
        ok("phòng đọc: các tệp trong gói không phải PDF — chỉ hiện băm, cỡ, không mở")

    say(5, "Phân tích trên dữ liệu lạnh: trang Điều hành đếm văn bản đã nộp lưu bằng DuckDB trên các gói Parquet")
    check_archive_stats(director, staff, cold_before, docs, done)

    say(6, "Gói lưu trữ không sửa, không xóa được — kể cả bằng khóa quản trị kho (S3 Object Lock, COMPLIANCE)")
    try_delete = (
        "import os, sys\n"
        "from svc_files.config import Settings\n"
        "from svc_files.openbao import with_secrets\n"
        "from svc_files.storage import s3_client\n"
        "s = Settings.from_env(with_secrets(os.environ))\n"
        "c = s3_client(s.s3_endpoint, s.s3_access_key, s.s3_secret_key, s.s3_region)\n"
        "key = f'{sys.argv[1]}manifest-{sys.argv[2]}.json'\n"
        "v = c.list_object_versions(Bucket=s.cold_bucket, Prefix=key)['Versions'][0]\n"
        "try:\n"
        "    c.delete_object(Bucket=s.cold_bucket, Key=v['Key'], VersionId=v['VersionId'])\n"
        "    print('deleted')\n"
        "except Exception as exc:\n"
        "    print('refused', type(exc).__name__)\n"
    )
    refused = compose("exec", "-T", "svc-files", "python", "-c", try_delete, done["archive_key"],
                      done["archive_sha256"]).decode().strip()
    if not refused.startswith("refused"):
        raise DemoFailed(f"xóa được manifest trong bucket lạnh: {refused}")
    ok(f"xóa manifest bằng khóa quản trị kho → {refused.split()[-1]}")
    event = psql("select id from core.audit_log where action = 'case_file.archived' and entity_id ="
                 f" '{cf['id']}'")
    ok(f"sổ kiểm toán dòng #{event}: case_file.archived kèm archive_sha256 — lần nộp lưu cũng nằm trong chuỗi băm")


LINEAGE_RUNS = """query { core_lineage_events(where: {job: {_eq: "moc.case_file.archive"}, event_type: {_eq: "COMPLETE"}},
  order_by: {id: desc}, limit: 1) { run_id outputs } }"""
LINEAGE_OF = """query ($run: uuid!) { core_lineage_events(order_by: {id: asc},
  where: {_or: [{run_id: {_eq: $run}}, {parent_run_id: {_eq: $run}}]}) {
  run_id parent_run_id job event_type inputs outputs quality_ok event } }"""
QUALITY_FAILED = """query { core_lineage_events_aggregate(where: {quality_ok: {_eq: false}}) { aggregate { count } } }"""
# Phả hệ báo cáo (F3.9, F3.11): office.report_lineage tính từ catalog PostgreSQL (migration 1792281602900)
REPORT_LINEAGE = "{ office_report_lineage { report consumer source source_kind depth } }"
BOARD_VIEWS = ("office.v_document_counts", "office.v_overdue_by_department", "office.v_processing_time",
               "office.v_outgoing_by_month")


def report_sources(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Cạnh catalog → mỗi khung nhìn báo cáo đọc những gì, gần trước xa sau; đọc qua view lồng thì ghi "qua <view>"."""
    out: dict[str, list[str]] = {}
    for r in sorted(rows, key=lambda r: (r["report"], r["depth"], r["consumer"], r["source"])):
        out.setdefault(r["report"], []).append(r["source"] + (f" (qua {r['consumer']})" if r["depth"] > 1 else ""))
    return out


def short(name: str) -> str:
    """Rút gọn tên dataset để in: bỏ namespace postgres, bỏ tiền tố cold/<tenant>/case/<id>/, băm còn 8 ký tự."""
    name = name.removeprefix("postgres://postgres:5432/")
    if "/case/" in name:
        name = "…/" + name.split("/case/", 1)[1].split("/", 1)[1]
    elif name.startswith("s3://") and "/tenant/" in name:
        name = name.split("/tenant/", 1)[0] + "/tenant/…/" + name.rsplit("/", 1)[1][:8] + "…"
    folder, _, base = name.rpartition("/")
    if "-" in base:                                # documents-<sha256>.parquet, manifest-<sha256>.json
        head, _, tail = base.rpartition("-")
        base = f"{head}-{tail[:8]}…{tail[64:]}" if len(tail) > 64 else base
    elif len(base) == 64:                          # files/<sha256>
        base = f"{base[:8]}…"
    return f"{folder}/{base}" if folder else base


def pha_he() -> None:
    print("Màn (iii) · Quản trị dữ liệu: phả hệ + kiểm chất lượng — mỗi bước nộp lưu là một run OpenLineage; gói lưu trữ"
          " truy ngược được về bảng nghiệp vụ; bảng Parquet nào cũng được kiểm số dòng và null trước khi ghi")
    director = Session("truongkhoa")

    say(1, "Lượt nộp lưu gần nhất (chưa có thì chạy màn (i) trước)")
    runs = director.gql(LINEAGE_RUNS)["core_lineage_events"]
    if not runs:
        nong_lanh()
        runs = director.gql(LINEAGE_RUNS)["core_lineage_events"]
    if not runs:
        raise DemoFailed("nộp lưu xong mà không có sự kiện phả hệ nào trong core.lineage_events")
    run = runs[0]["run_id"]
    events = director.gql(LINEAGE_OF, {"run": run})["core_lineage_events"]
    steps = [e for e in events if e["parent_run_id"] == run]
    names = [e["job"].rsplit(".", 1)[1] for e in steps]
    if names != ["files", "tables", "manifest", "commit"] or any(e["event_type"] != "COMPLETE" for e in steps):
        raise DemoFailed(f"lượt nộp lưu {run} thiếu bước: {[(e['job'], e['event_type']) for e in steps]}")
    ok(f"run {run[:8]}… của job moc.case_file.archive: START → 4 run con (files, tables, manifest, commit) → COMPLETE;"
       " lãnh đạo đọc qua Hasura, chỉ đơn vị mình")
    for e in steps:
        ins = ", ".join(sorted({short(i) for i in e["inputs"]}))
        outs = ", ".join(sorted({short(o) for o in e["outputs"]}))
        print(f"       · {e['job'].rsplit('.', 1)[1]:<8} {ins}\n                  → {outs}")

    say(2, "Truy ngược: gói lưu trữ ← bảng Parquet / tệp ← bảng nghiệp vụ, bucket nóng")
    # bước commit ghi ngược vào chính các bảng nghiệp vụ: bỏ ra, phả hệ của gói dừng ở nguồn
    produced = {o: e for e in steps if not e["job"].endswith(".commit") for o in e["outputs"]}
    manifest = runs[0]["outputs"][0]
    seen: set[str] = set()
    expanded: set[str] = set()      # mỗi bước chỉ in đầu vào một lần

    def trace(name: str, depth: int) -> None:
        print(f"       {'   ' * depth}{'← ' if depth else ''}{short(name)}")
        step = produced.get(name)
        if name in seen or not step:
            return
        seen.add(name)
        if step["run_id"] in expanded:
            print(f"       {'   ' * (depth + 1)}← (cùng bước {step['job'].rsplit('.', 1)[1]}, như trên)")
            return
        expanded.add(step["run_id"])
        for parent in sorted(set(step["inputs"])):
            trace(parent, depth + 1)
    trace(manifest, 0)
    tables = next(e for e in steps if e["job"].endswith(".tables"))
    if not any(i.endswith("moc.office.documents") for i in tables["inputs"]):
        raise DemoFailed("phả hệ không dẫn bảng Parquet về office.documents")
    ok("manifest dẫn về documents/assignments/events.parquet và từng tệp; Parquet dẫn về office.documents,"
       " office.assignments, office.document_events")

    say(3, "Kiểm chất lượng của từng bảng trước khi ghi sang bucket lạnh")
    for out in tables["event"]["outputs"]:
        checks = out["facets"]["dataQualityAssertions"]["assertions"]
        rows = out["outputFacets"]["outputStatistics"]["rowCount"]
        not_null = [a for a in checks if a["assertion"] == "not_null"]
        same = next(a for a in checks if a["assertion"] == "row_count_equals_source")
        if not all(a["success"] for a in checks):
            raise DemoFailed(f"{short(out['name'])}: {checks}")
        ok(f"{short(out['namespace'] + '/' + out['name'])}: {rows} dòng = số dòng trong CSDL"
           f" ({'✓' if same['success'] else '✗'}); {len(not_null)} cột bắt buộc không null ✓")
    failed = director.gql(QUALITY_FAILED)["core_lineage_events_aggregate"]["aggregate"]["count"]
    ok(f"bảng trượt kiểm thì job dừng trước khi ghi gì sang lạnh, sự kiện FAIL nằm lại trong phả hệ — đơn vị này hiện"
       f" có {failed} bước trượt")

    say(4, "Sự kiện theo đặc tả OpenLineage — chuyển được sang Marquez (MOC_OPENLINEAGE_URL)")
    first = events[0]["event"]
    ok(f"{first['schemaURL']} · producer {first['producer'].rsplit('/', 2)[-1]} · namespace job"
       f" '{first['job']['namespace']}'; tên dataset theo quy ước postgres://host:port/db.schema.bảng, s3://bucket/key")

    say(5, "Phả hệ báo cáo: biểu đồ trang Điều hành ← khung nhìn ← bảng, tính từ catalog PostgreSQL lúc hỏi")
    sources = report_sources(director.gql(REPORT_LINEAGE)["office_report_lineage"])
    missing = [v for v in BOARD_VIEWS if v not in sources]
    if missing:
        raise DemoFailed(f"khung nhìn của trang Điều hành không có trong office.report_lineage: {missing}")
    for view in BOARD_VIEWS:
        print(f"       · {view} ← {', '.join(sources[view])}")
    if not {"office.document_events", "office.archived_document_facts"} <= set(sources["office.v_processing_time"]):
        raise DemoFailed(f"thời gian xử lý không dẫn về dòng thời gian: {sources['office.v_processing_time']}")
    ok(f"{len(sources)} khung nhìn báo cáo office.v_*, {sum(map(len, sources.values()))} cạnh — không khai tay: sửa"
       " view là phả hệ đổi theo; lãnh đạo xem đồ thị ở /pha-he (nút \"Nguồn số liệu\" trên từng biểu đồ của"
       " /dieu-hanh)")
    commit = next(e for e in steps if e["job"].endswith(".commit"))
    if any(o.endswith("moc.office.archived_document_facts") for o in commit["outputs"]):
        ok("thời gian xử lý ← office.archived_document_facts ← bước commit của lượt nộp lưu ở bước 1: văn bản đã nộp"
           " lưu vẫn được đếm")


OT_SENSOR = "phong-may-chu"
OT_ROOM = "Phòng máy chủ tầng 3"
OT_PLAN_ROOM = "may-chu"  # mã phòng trên sơ đồ cảm biến kho (apps/office/app/utils/otMap.ts)
OT_STAFF = "chuyenviendt"
OT_SUBSCRIPTION = "urn:ngsi-ld:Subscription:moc-ot-alarm"

OT_DRAFTS = """
query ($sensor: jsonb!) {
  office_documents(where: {direction: {_eq: "out"}, events: {kind: {_eq: "ot.alarm"}, data: {_contains: $sensor}}},
                   order_by: {created_at: desc}) {
    id status type_code urgency summary body created_by events(where: {kind: {_eq: "ot.alarm"}}) { data }
  }
}"""

SUBMIT = "mutation ($d: uuid!, $s: String!) { submitOutgoing(documentId: $d, signerId: $s) { status } }"
# như Session.complete (moc_env.py), gọi tay để gửi kèm X-Request-Id
COMPLETE_TASK = ("mutation ($t: String!, $o: String!, $d: jsonb) { completeTask(taskId: $t, outcome: $o, data: $d) {"
                 " task_id } }")

# Gửi một thông báo giả (token sai) tới svc-workflow, in mã HTTP nhận được hoặc "không tới được"
# Sơ đồ cảm biến kho (Action otSensorMap, trang /cam-bien)
OT_MAP = "{ otSensorMap { status threshold stale_after_min sensors { id room value observed_at flags } } }"

OT_PROBE = """
import sys, urllib.error, urllib.request
req = urllib.request.Request(sys.argv[1], data=b'{"data": []}', method="POST",
                             headers={"Content-Type": "application/json", "X-Moc-OT-Token": "sai"})
try:
    print(urllib.request.urlopen(req, timeout=5).status)
except urllib.error.HTTPError as exc:
    print(exc.code)
except OSError:
    print("không tới được")
"""


def iot(*args: str) -> bytes:
    return compose("--profile", "iot", "--profile", "iot-sim", *args)


def ngsi_tenant(code: str) -> str:
    """Tên tenant NGSI-LD của đơn vị, như svc_workflow.ot.ngsi_tenant: mã có dấu thì "t" + băm."""
    if code.isascii() and code.isalnum() and len(code) <= 20:
        return code
    return "t" + hashlib.sha256(code.encode()).hexdigest()[:16]


def ot_query(threshold: float) -> str:
    """Điều kiện q của subscription, như svc_workflow.ot.query_for."""
    return f"temperature>{int(threshold) if threshold.is_integer() else format(Decimal(repr(threshold)), 'f')}"


def ngsi(path: str, tenant: str) -> tuple[int, Any]:
    """Đọc broker từ trong container của nó (broker không mở cổng ra máy chủ)."""
    out = iot("exec", "-T", "scorpio", "curl", "-s", "-w", "\n%{http_code}", "-H", f"NGSILD-Tenant: {tenant}",
              f"http://localhost:9090/ngsi-ld/v1{path}").decode()
    body, _, code = out.rpartition("\n")
    try:
        return int(code), json.loads(body) if body.strip() else None
    except ValueError:
        return int(code) if code.isdigit() else 0, body


def ot_drafts(staff: Session, sensor: str) -> list[dict[str, Any]]:
    return staff.gql(OT_DRAFTS, {"sensor": {"sensor": sensor}})["office_documents"]


def it_ot() -> None:
    print("Màn (ii) · Hội tụ IT/OT: cảm biến nhiệt độ (OT) → bản sao số NGSI-LD → subscription → dự thảo \"Báo cáo sự"
          " cố\" trong luồng văn bản đi (IT) — hệ thống dựng nháp, con người kiểm tra và trình")
    staff, manager = Session(OT_STAFF), Session("totruongdt")
    unit = psql("select t.code from core.tenants t join core.users u on u.tenant_id = t.id"
                f" where u.username = '{OT_STAFF}'")
    tenant = ngsi_tenant(unit)
    threshold = float(ENV.get("MOC_OT_THRESHOLD") or 35)
    sensor = f"urn:ngsi-ld:TemperatureSensor:{OT_SENSOR}"

    say(1, "Bật context broker NGSI-LD (profile iot: Scorpio + PostGIS); svc-workflow đăng ký subscription")
    if not ENV.get("MOC_NGSI_DB_PASSWORD") or ENV["MOC_NGSI_DB_PASSWORD"].startswith("change_me"):
        raise DemoFailed("chưa đặt MOC_NGSI_DB_PASSWORD trong .env: thêm dòng MOC_NGSI_DB_PASSWORD=<chuỗi ngẫu nhiên>"
                         " (make env mới tự sinh)")
    t0 = time.monotonic()
    iot("up", "-d", "--wait", "--wait-timeout", "300", "scorpio")
    ready = time.monotonic() - t0
    want = ot_query(threshold)
    deadline = time.monotonic() + 60
    while True:
        code, sub = ngsi(f"/subscriptions/{OT_SUBSCRIPTION}", tenant)
        if code == 200 and isinstance(sub, dict) and sub.get("q") == want:
            break
        if time.monotonic() > deadline:
            raise DemoFailed(f"sau 60 giây đơn vị {unit} vẫn chưa có subscription {want} (HTTP {code}: {sub})")
        time.sleep(2)
    uri = sub["notification"]["endpoint"]["uri"]
    ok(f"Scorpio sẵn sàng sau {ready:.0f} giây; đơn vị {unit} (tenant NGSI-LD {tenant}) có subscription \"{want}\" →"
       f" {uri.split('//', 1)[-1]}, kèm token riêng của đơn vị; broker không mở cổng ra ngoài")

    # lần chạy trước dừng giữa chừng còn để dự thảo mở thì trình nốt: cảm biến còn dự thảo mở thì không dựng thêm
    signer = staff.gql('{ core_users(where: {username: {_eq: "truongkhoa"}}) { id } }')["core_users"][0]["id"]
    for old in ot_drafts(staff, sensor):
        if old["status"] == "draft":
            staff.gql(SUBMIT, {"d": old["id"], "s": signer})
            print(f"       (dự thảo còn mở từ lần chạy trước {old['id'][:8]}… đã trình nốt)")
    before = {d["id"] for d in ot_drafts(staff, sensor)}

    readings = [threshold - 11, threshold - 6, threshold - 2, threshold + 2, threshold + 6]
    say(2, f"Cảm biến {OT_ROOM} gửi các lần đo: {' → '.join(f'{r:g}' for r in readings)} °C (ngưỡng {threshold:g} °C)")
    out = iot("run", "--rm", "-T", "ot-sensor", "--tenant", tenant, "--sensor", OT_SENSOR, "--name", OT_ROOM,
              "--room", OT_PLAN_ROOM, "--responsible", OT_STAFF, "--readings", ",".join(f"{r:g}" for r in readings),
              "--interval", "1")
    sent = [json.loads(line) for line in out.decode().splitlines() if line.startswith("{")]
    if len(sent) != len(readings) or any(r.get("status") != 204 for r in sent):
        raise DemoFailed(f"cảm biến chưa gửi đủ: {sent}")
    ok(f"{len(sent)} lần đo vào bản sao số {sensor}; 2 lần cuối vượt ngưỡng")

    say(3, "Vượt ngưỡng → svc-workflow dựng dự thảo \"Báo cáo sự cố\" từ mẫu cho chuyên viên phụ trách")
    deadline = time.monotonic() + 30
    while not [d for d in ot_drafts(staff, sensor) if d["id"] not in before] and time.monotonic() < deadline:
        time.sleep(1)
    time.sleep(2)  # lần vượt ngưỡng thứ hai tới sau: không được dựng dự thảo thứ hai
    drafts = [d for d in ot_drafts(staff, sensor) if d["id"] not in before]
    if len(drafts) != 1:
        raise DemoFailed(f"phải có đúng 1 dự thảo mới cho 2 lần vượt ngưỡng, có {len(drafts)}")
    doc = drafts[0]
    alarm = doc["events"][0]["data"]
    if (doc["status"], doc["type_code"], doc["urgency"]) != ("draft", "BC", "khan") or alarm["temperature"] <= threshold:
        raise DemoFailed(f"dự thảo chưa đúng: {doc['status']}, {doc['type_code']}, {doc['urgency']}, {alarm}")
    print(f"       trích yếu: {doc['summary']}")
    print(f"       nội dung:  {doc['body'].splitlines()[0]}")
    notes = staff.gql("""query ($d: uuid!) { core_notifications(where: {document_id: {_eq: $d}, kind: {_eq: "ot.alarm"}})
        { id } }""", {"d": doc["id"]})["core_notifications"]
    if len(notes) != 1:
        raise DemoFailed(f"chuyên viên phải nhận đúng 1 thông báo ot.alarm, có {len(notes)}")
    ok("đúng 1 dự thảo cho 2 lần vượt ngưỡng (chống trùng): Báo cáo, độ khẩn \"Khẩn\", đứng tên chuyên viên phụ trách;"
       " dòng thời gian có sự kiện ot.alarm; chuyên viên nhận thông báo ngay")

    say(4, "Lịch sử đo nằm trong bản sao số (NGSI-LD temporal API)")
    # broker ghi lịch sử sau khi trả lời lệnh cập nhật (bất đồng bộ): chờ tới khi có đủ các lần vừa gửi, so cả giờ đo
    # (lần chạy trước gửi cùng các giá trị)
    want = {(r["temperature"], r["observedAt"]) for r in sent}
    deadline = time.monotonic() + 30
    while True:
        code, history = ngsi(f"/temporal/entities/{sensor}?attrs=temperature&lastN=50", tenant)
        points = {(v.get("value"), v.get("observedAt")) for v in (history or {}).get("temperature", [])} \
            if code == 200 and isinstance(history, dict) else set()
        if want <= points:
            break
        if time.monotonic() > deadline:
            raise DemoFailed(f"sau 30 giây lịch sử đo vẫn thiếu: HTTP {code}, thiếu {sorted(want - points)}")
        time.sleep(1)
    ok(f"broker giữ lịch sử: đủ {len(want)} lần vừa đo (cả các lần dưới ngưỡng) trong {len(points)} lần gần nhất — dữ liệu"
       " OT ở broker, Signet chỉ nhận sự kiện cần xử lý")

    say(5, "Chuyên viên kiểm tra, trình → dự thảo vào luồng văn bản đi: tổ trưởng có việc duyệt")
    staff.gql(SUBMIT, {"d": doc["id"], "s": signer})
    manager.wait_task(doc["id"], "vbdi.duyetPhong")
    ok("trình lên lãnh đạo khoa; tổ trưởng phòng nhận việc duyệt như mọi văn bản đi — hệ thống không tự trình")

    say(6, "Chỉ broker gọi được svc-workflow: thiết bị không tới được, dịch vụ khác thiếu token đúng → 401")
    url = f"http://svc-workflow:8000/ot/notify/{quote(tenant, safe='')}"
    from_device = iot("run", "--rm", "-T", "--entrypoint", "python", "ot-sensor", "-c", OT_PROBE, url).decode().strip()
    from_inside = compose("exec", "-T", "svc-files", "python", "-c", OT_PROBE, url).decode().strip()
    if (from_device, from_inside) != ("không tới được", "401"):
        raise DemoFailed(f"thông báo giả: từ mạng thiết bị phải không tới được (nhận {from_device}), từ svc-files với"
                         f" token sai phải 401 (nhận {from_inside})")
    ok("mạng thiết bị chỉ thấy broker, không tới được svc-workflow; thông báo giả từ mạng nội bộ (svc-files) với token"
       " sai bị từ chối (401) — token mỗi đơn vị suy từ khóa của svc-workflow, chỉ broker giữ")

    ot_sensor_map(tenant, threshold, readings[-1])


def ot_sensor_map(tenant: str, threshold: float, server_room: float) -> None:
    """Bước 7 của màn it-ot: sơ đồ cảm biến kho, cờ chất lượng tính ở svc-workflow, đọc qua Action có kiểm quyền."""
    stale_min = int(ENV.get("MOC_OT_STALE_MIN") or 10)
    # mã cảm biến = mã phòng, tên phòng, số đo (dưới ngưỡng: không dựng dự thảo), cách giả lỗi của sensor.py, cờ chờ
    rooms = [
        ("kho-1", "Kho bảo quản 1", [threshold - 14, threshold - 13], [], []),
        ("kho-2", "Kho bảo quản 2", [threshold - 13, -127], [], ["out_of_range"]),
        ("kho-3", "Kho bảo quản 3", [threshold - 12, threshold - 11], ["--frozen-clock"], ["duplicate_time"]),
        ("phong-doc", "Phòng đọc", [threshold - 11], ["--late", str(stale_min + 20)], ["stale"]),
        ("xu-ly", "Phòng xử lý tài liệu", [threshold - 10], ["--clock-ahead", "30"], ["future_time"]),
    ]
    say(7, "Sơ đồ cảm biến kho: năm cảm biến gửi số đo — bình thường; -127 °C (ngoài dải); đồng hồ đứng (trùng"
           f" observedAt); số đo cũ {stale_min + 20} phút (mất tín hiệu); đồng hồ nhanh 30 phút (giờ đo ở tương lai)")
    for code, name, values, fault, _ in rooms:
        out = iot("run", "--rm", "-T", "ot-sensor", "--tenant", tenant, "--sensor", code, "--name", name,
                  "--room", code, "--responsible", OT_STAFF, "--readings", ",".join(f"{v:g}" for v in values),
                  "--interval", "1", *fault)
        sent = [json.loads(line) for line in out.decode().splitlines() if line.startswith("{")]
        if len(sent) != len(values) or any(r.get("status") != 204 for r in sent):
            raise DemoFailed(f"cảm biến {code} chưa gửi đủ: {sent}")
    want = {f"urn:ngsi-ld:TemperatureSensor:{code}": flags for code, _, _, _, flags in rooms}
    server = f"urn:ngsi-ld:TemperatureSensor:{OT_SENSOR}"
    clerk = Session("vanthu")
    # lịch sử đo (để xét trùng observedAt) broker ghi bất đồng bộ, sau vài chục giây: chờ tới khi đủ cờ
    deadline = time.monotonic() + 60
    while True:
        board = clerk.gql(OT_MAP)["otSensorMap"]
        got = {s["id"]: s for s in board["sensors"]}
        seen = {sid: got.get(sid, {}).get("flags") for sid in want}
        wrong = {sid: flags for sid, flags in seen.items() if flags != want[sid]}
        if board["status"] == "ready" and not wrong and server in got:
            break
        if time.monotonic() > deadline:
            raise DemoFailed(f"sau 60 giây sơ đồ vẫn chưa đúng cờ (trạng thái {board['status']}): {wrong}")
        time.sleep(1)
    room = got[server]
    if room["room"] != OT_PLAN_ROOM or room["value"] != server_room or {"out_of_range", "duplicate_time"} & set(
            room["flags"]):
        raise DemoFailed(f"phòng máy chủ trên sơ đồ chưa đúng: {room}")
    if got["urn:ngsi-ld:TemperatureSensor:kho-2"]["value"] != -127:
        raise DemoFailed(f"kho 2 phải hiện số -127 kèm cờ ngoài dải: {got['urn:ngsi-ld:TemperatureSensor:kho-2']}")
    ok(f"văn thư thấy {len(got)} cảm biến: phòng máy chủ {server_room:g} °C vượt ngưỡng {board['threshold']:g} °C (đỏ);"
       " kho 1 bình thường; kho 2 \"ngoài dải\", kho 3 \"trùng giờ đo\", phòng đọc \"mất tín hiệu\" (quá"
       f" {board['stale_after_min']} phút), phòng xử lý \"giờ đo ở tương lai\" (mất tín hiệu xét theo lúc broker nhận)"
       " — cờ do svc-workflow tính, không tin số của thiết bị")

    other = Session("vanthukt").gql(OT_MAP)["otSensorMap"]
    if set(want) & {s["id"] for s in other["sensors"]} or server in {s["id"] for s in other["sensors"]}:
        raise DemoFailed(f"văn thư Khoa Kinh tế thấy cảm biến của Khoa CNTT: {other['sensors']}")
    try:
        Session("quantri").gql(OT_MAP)
    except RuntimeError as exc:
        refused = str(exc)
    else:
        raise DemoFailed("quản trị đơn vị gọi được otSensorMap: Action phải chỉ cho các vai trò đọc được văn bản")
    ok(f"văn thư Khoa Kinh tế chỉ thấy cảm biến của đơn vị mình ({len(other['sensors'])}); quản trị đơn vị không có"
       f" Action này ({refused[:80]}) — trình duyệt không gọi thẳng broker, đọc qua APISIX → Hasura → svc-workflow")
    print(f"\nXem trên giao diện (vanthu): {PUBLIC_URL}/cam-bien")


DISPATCH_UNITS = "{ office_dispatch_units(order_by: {name: asc}) { id code name } }"
DRAFT = "mutation ($o: office_documents_insert_input!) { insert_office_documents_one(object: $o) { id } }"
ISSUED = "query ($id: uuid!) { office_documents_by_pk(id: $id) { status symbol verify_code content_sha256 } }"
ARRIVED = """query ($s: uuid!) { office_documents(where: {source_id: {_eq: $s}}) { id status symbol issuer_name
  files { role file_id file { sha256 } } } }"""
INCOMING_NOTE = """query ($d: uuid!) { core_notifications(where: {document_id: {_eq: $d}, kind: {_eq: "document.incoming"}})
  { data } }"""
DISPATCH_OUT = "query ($d: uuid!) { office_dispatches(where: {document_id: {_eq: $d}}) { id status delivered_at } }"
DISPATCH_IN = """query ($d: uuid!) { office_dispatches(where: {incoming_document_id: {_eq: $d}}) {
  id status source_verify_code source_sha256 } }"""
AUDIT_OF = """query ($ids: [String!]!) { core_audit_log(where: {entity_id: {_in: $ids}}, order_by: {id: asc}) {
  id action entity actor_kind } }"""


def hexed(bytea: str | None) -> str:
    return (bytea or "").removeprefix("\\x")


def lien_thong() -> None:
    print("Màn F3.12 · Liên thông văn bản trong hệ thống — Khoa CNTT phát hành công văn gửi Khoa Kinh tế; bên nhận tự có"
          " văn bản đến cùng tệp, cùng mã xác thực, rồi vào sổ, chỉ đạo như mọi văn bản đến")
    tag = uuid.uuid4().hex[:6].upper()
    staff, manager, director, clerk = (Session(u) for u in ("chuyenviendt", "totruongdt", "truongkhoa", "vanthu"))
    kt_clerk, kt_director = Session("vanthukt"), Session("truongkhoakt")

    say(1, "Chuyên viên CNTT soạn công văn, chọn Khoa Kinh tế trong danh sách đơn vị trong hệ thống")
    units = staff.gql(DISPATCH_UNITS)["office_dispatch_units"]
    own = staff.gql("{ core_tenants { id } }")["core_tenants"][0]["id"]
    kt = next((u for u in units if u["code"] == "KT"), None)
    if kt is None:
        raise DemoFailed(f"danh sách đơn vị trong hệ thống không có Khoa Kinh tế (mã KT): {units} — chạy make seed")
    if any(u["id"] == own for u in units):
        raise DemoFailed("danh sách đơn vị nhận có cả đơn vị của người soạn")
    sent = staff.gql(DRAFT, {"o": {
        "type_code": "CV", "recipients": [kt["name"]], "recipient_tenant_ids": [kt["id"]],
        "summary": f"Về việc phối hợp tổ chức hội thảo khoa học liên khoa (demo {tag})",
        "body": "Khoa Công nghệ thông tin đề nghị Khoa Kinh tế cử cán bộ tham gia ban tổ chức hội thảo.\n"
                "Danh sách gửi về Văn phòng khoa trước ngày 15 tháng sau.",
    }})["insert_office_documents_one"]["id"]
    ok(f"danh sách chọn được: {', '.join(u['name'] for u in units)} (không có đơn vị mình); dự thảo gửi {kt['name']}")

    say(2, "Trình → tổ trưởng duyệt → lãnh đạo khoa ký → văn thư CNTT phát hành")
    signer = staff.gql('{ core_users(where: {username: {_eq: "truongkhoa"}}) { id } }')["core_users"][0]["id"]
    staff.gql(SUBMIT, {"d": sent, "s": signer})
    manager.complete(manager.wait_task(sent, "vbdi.duyetPhong"), "approve", {})
    director.complete(director.wait_task(sent, "vbdi.duyetDonVi"), "approve", {})
    clerk.complete(clerk.wait_task(sent, "vbdi.phatHanh"), "issue", {"is_public": False})
    issued_at = time.monotonic()
    src = clerk.gql(ISSUED, {"id": sent})["office_documents_by_pk"]
    if src["status"] != "issued":
        raise DemoFailed(f"công văn chưa phát hành: {src}")
    sha, code = hexed(src["content_sha256"]), src["verify_code"]
    ok(f"{src['symbol']} phát hành: mã xác thực {code[:5]}-{code[5:]}, SHA-256 {sha[:16]}…")

    say(3, "Khoa Kinh tế tự nhận văn bản đến — không ai gửi thư điện tử, không ai tải tệp lên lại")
    # svc-workflow chuyển ngay sau lần phát hành; trượt thì vòng đối soát nền làm lại
    deadline = time.monotonic() + 90
    while not (arrived := kt_clerk.gql(ARRIVED, {"s": sent})["office_documents"]):
        if time.monotonic() > deadline:
            raise DemoFailed("sau 90 giây Khoa Kinh tế chưa có văn bản đến từ công văn vừa phát hành")
        time.sleep(1)
    took = time.monotonic() - issued_at
    doc = arrived[0]
    main = [f for f in doc["files"] if f["role"] == "main"]
    if len(arrived) != 1 or doc["status"] != "received" or len(main) != 1 or doc["symbol"] != src["symbol"]:
        raise DemoFailed(f"văn bản đến chưa đúng: {arrived}")
    _, _, body = request("GET", f"{PUBLIC_URL}/api/files/{main[0]['file_id']}", headers=kt_clerk.auth)
    got = hashlib.sha256(body).hexdigest()
    if got != sha or hexed((main[0]["file"] or {}).get("sha256")) != sha:
        raise DemoFailed(f"tệp bên nhận không trùng bản phát hành: {got} ≠ {sha}")
    ok(f"{took:.0f} giây sau phát hành: văn bản đến {doc['symbol']} của {doc['issuer_name']}, trạng thái received"
       " (chờ vào sổ)")
    ok(f"văn thư KT tải tệp chính về: SHA-256 {got[:16]}… trùng từng byte bản phát hành — bản sao nằm trong kho của Khoa"
       " Kinh tế, đã qua ClamAV")
    deadline = time.monotonic() + 15
    while not (notes := kt_clerk.gql(INCOMING_NOTE, {"d": doc["id"]})["core_notifications"]):
        if time.monotonic() > deadline:
            raise DemoFailed("văn thư Khoa Kinh tế chưa nhận thông báo văn bản đến mới")
        time.sleep(1)
    out = clerk.gql(DISPATCH_OUT, {"d": sent})["office_dispatches"]
    if [r["status"] for r in out] != ["delivered"] or not out[0]["delivered_at"]:
        raise DemoFailed(f"bên gửi chưa thấy đã chuyển: {out}")
    at = datetime.fromisoformat(out[0]["delivered_at"]).astimezone().strftime("%H:%M:%S")
    ok(f"vanthukt nhận thông báo văn bản đến mới (từ {notes[0]['data'].get('from_name')}); bên gửi thấy trạng thái"
       f" delivered lúc {at}, không thấy gì thêm của bên nhận")

    say(4, "Bên nhận kiểm ở cổng xác thực bằng mã của bên gửi (không cần đăng nhập)")
    link = kt_clerk.gql(DISPATCH_IN, {"d": doc["id"]})["office_dispatches"]
    if len(link) != 1 or link[0]["source_verify_code"] != code or hexed(link[0]["source_sha256"]) != sha:
        raise DemoFailed(f"văn bản đến không mang mã xác thực, băm của bên gửi: {link}")
    by_code, _ = call_json("GET", f"{PUBLIC_URL}/api/verify/{code}")
    by_hash, _ = call_json("GET", f"{PUBLIC_URL}/api/verify?sha256={got}")
    if by_code.get("result") != "valid" or by_code["document"]["sha256"] != got or by_hash.get("result") != "valid":
        raise DemoFailed(f"cổng xác thực trả {by_code} / {by_hash}")
    ok(f"mã {code[:5]}-{code[5:]} (giao diện hiện cạnh văn bản đến) → khớp: {by_code['document']['symbol']} do"
       f" {by_code['document']['issuer_name']} phát hành; tra theo SHA-256 của tệp nhận được cũng khớp")

    say(5, "Văn thư KT vào sổ — văn bản vào luồng văn bản đến bình thường của Khoa Kinh tế")
    number = kt_clerk.gql("mutation ($id: uuid!) { registerIncoming(documentId: $id) { register_number } }",
                          {"id": doc["id"]})["registerIncoming"]["register_number"]
    kt_director.wait_task(doc["id"], "vbden.chiDao")
    ok(f"số đến {number} trong sổ đến của Khoa Kinh tế; truongkhoakt có việc cho ý kiến chỉ đạo (vbden.chiDao)")
    if clerk.gql("query ($id: uuid!) { office_documents_by_pk(id: $id) { id } }",
                 {"id": doc["id"]})["office_documents_by_pk"] is not None:
        raise DemoFailed("Khoa CNTT đọc được văn bản đến của Khoa Kinh tế")
    ok("Khoa CNTT không đọc được văn bản đến của Khoa Kinh tế — mỗi đơn vị chỉ thấy phần của mình")

    say(6, "Sổ kiểm toán của cả hai đơn vị ghi lại — mỗi lãnh đạo đọc sổ của đơn vị mình")
    ours = director.gql(AUDIT_OF, {"ids": [link[0]["id"]]})["core_audit_log"]
    theirs = kt_director.gql(AUDIT_OF, {"ids": [doc["id"], main[0]["file_id"]]})["core_audit_log"]
    peek = kt_director.gql(AUDIT_OF, {"ids": [link[0]["id"], sent]})["core_audit_log"]
    if not {("office.dispatches", "insert"), ("office.dispatches", "update")} <= {(r["entity"], r["action"])
                                                                                  for r in ours}:
        raise DemoFailed(f"sổ Khoa CNTT thiếu dòng liên thông: {ours}")
    copied = [r for r in theirs if (r["entity"], r["action"]) == ("core.files", "insert")]
    if not copied or not any((r["entity"], r["action"]) == ("office.documents", "insert") for r in theirs):
        raise DemoFailed(f"sổ Khoa Kinh tế thiếu văn bản đến hoặc bản sao tệp: {theirs}")
    if peek:
        raise DemoFailed(f"lãnh đạo Khoa Kinh tế đọc được sổ của Khoa CNTT: {peek}")
    ok(f"sổ Khoa CNTT: {len(ours)} dòng office.dispatches (tạo trong giao dịch phát hành → delivered),"
       f" từ dòng #{ours[0]['id']}")
    ok(f"sổ Khoa Kinh tế: {len(theirs)} dòng — văn bản đến, vào sổ, bản sao tệp (người thực hiện:"
       f" {copied[0]['actor_kind']}); lãnh đạo Khoa Kinh tế không đọc được dòng nào của Khoa CNTT")

    say(7, "Văn bản hạn chế không gửi được trong hệ thống")
    try:
        staff.gql(DRAFT, {"o": {
            "type_code": "CV", "recipients": [kt["name"]], "recipient_tenant_ids": [kt["id"]], "restricted": True,
            "summary": f"Về việc danh sách nâng lương trước hạn (demo {tag})", "body": "Danh sách kèm theo.",
        }})
        raise DemoFailed("văn bản hạn chế vẫn chọn được đơn vị nhận trong hệ thống")
    except RuntimeError as exc:
        if "documents_restricted_local" not in str(exc):
            raise DemoFailed(f"bị từ chối nhưng không vì ràng buộc documents_restricted_local: {exc}") from exc
    ok("dự thảo hạn chế chọn Khoa Kinh tế → CSDL từ chối (documents_restricted_local); svc-workflow, svc-files cũng"
       " chặn — tệp hạn chế mã hóa theo khóa của đơn vị gửi, không rời đơn vị")

    print(f"\nXem trên giao diện (vanthukt): {PUBLIC_URL}/van-ban/{doc['id']} — chip \"Liên thông\", \"Nhận từ"
          f" {doc['issuer_name']}\"; bên gửi (vanthu): {PUBLIC_URL}/van-ban/{sent}")


# --- F4.1 · Đọc văn bản đến ------------------------------------------------------------------------------------------
# Văn bản mẫu hư cấu đi kèm mã nguồn (sinh lại: make van-ban-mau), nhãn đúng của từng tệp trong nhan.json
SAMPLES_DIR = ROOT / "seed" / "van-ban-den"
READ_FIELDS = ("type_code", "symbol", "issued_on", "issuer_name", "urgency")
FIELD_NAMES = {"type_code": "Loại", "symbol": "Số, ký hiệu", "issued_on": "Ngày ban hành",
               "issuer_name": "Cơ quan ban hành", "urgency": "Độ khẩn", "summary": "Trích yếu"}
SAMPLE_MIME = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
# Ngưỡng theo tỉ lệ (%) trên các PDF có lớp chữ — như services/svc-files/tests/test_docread_samples.py; thêm: không
# trường high nào sai
TEXT_MIN = {"symbol": 90, "issued_on": 90, "type_code": 90, "issuer_name": 80, "summary": 80}
# /readyz của svc-files (trong container, cổng không mở ra máy chủ): "ai": true khi Ollama có mô hình (profile ai)
AI_READY = """import json, urllib.error, urllib.request
try:
    raw = urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=5).read()
except urllib.error.HTTPError as exc:
    raw = exc.read()
print(json.dumps(json.loads(raw).get('ai')))
"""
RECEIVED_BEFORE = """query ($s: String!, $d: date!) { office_documents(where: {direction: {_eq: "in"}, symbol: {_eq: $s},
  issued_on: {_eq: $d}}, order_by: {created_at: asc}) { id status issuer_name register_number } }"""
READ_AUDIT = """query ($f: String!) { core_audit_log(where: {action: {_eq: "intake.suggested"}, entity_id: {_eq: $f}},
  order_by: {id: asc}) { id occurred_at entity actor_id actor_kind overview } }"""


def sample_labels() -> list[dict[str, Any]]:
    path = SAMPLES_DIR / "nhan.json"
    if not path.is_file():
        raise DemoFailed(f"không có {path.relative_to(ROOT)} — văn bản mẫu đi kèm mã nguồn (sinh lại: make van-ban-mau)")
    return json.loads(path.read_text(encoding="utf-8"))["samples"]


def upload_sample(clerk: Session, name: str) -> dict[str, Any]:
    path = SAMPLES_DIR / name
    return clerk.upload(name, path.read_bytes(), SAMPLE_MIME.get(path.suffix.lower(), "application/octet-stream"))


def read_file(clerk: Session, file_id: str, *, force: bool = False) -> dict[str, Any]:
    """POST /api/files/{id}/read qua APISIX: tác tử moc-doc-reader đọc tệp, trả gợi ý — không ghi gì vào văn bản.
    Hết lượt OCR (503 busy) thì đợi như Retry-After rồi gọi lại, tối đa ba lần."""
    url = f"{PUBLIC_URL}/api/files/{file_id}/read" + ("?force=true" if force else "")
    attempts = 0
    while True:
        try:
            _, _, raw = request("POST", url, data=b"", headers=clerk.auth, timeout=90)
            return json.loads(raw)
        except HTTPError as exc:
            attempts += 1
            if exc.status != 503 or error_detail(exc).get("code") != "busy" or attempts == 3:
                raise
            time.sleep(10)


def expected(field: str, labels: dict[str, Any]) -> str | None:
    """Nhãn của trường; "normal" (không có dấu độ khẩn) coi như không có gì để gợi ý."""
    want = labels.get(field)
    return None if field == "urgency" and want == "normal" else want


def same_value(field: str, got: str, want: str | None) -> bool:
    """So như tests/test_docread_samples.py: số ký hiệu bỏ khoảng trắng, không phân biệt hoa thường; cơ quan gộp
    khoảng trắng; trích yếu trùng ≥ 60% từ của nhãn; còn lại bằng nhau."""
    if want is None:
        return False
    if field == "symbol":
        return "".join(got.split()).casefold() == "".join(want.split()).casefold()
    if field == "issuer_name":
        return " ".join(got.split()).casefold() == " ".join(want.split()).casefold()
    if field == "summary":
        words = set(re.findall(r"\w+", want.casefold()))
        return len(words & set(re.findall(r"\w+", got.casefold()))) >= 0.6 * max(len(words), 1)
    return got == want


def misses(fields: dict[str, Any], labels: dict[str, Any]) -> list[str]:
    """Các ô gợi ý khác nhãn hoặc bỏ trống trong khi nhãn có giá trị."""
    out = []
    for name in (*READ_FIELDS, "summary"):
        got, want = fields.get(name), expected(name, labels)
        if got is None:
            if want is not None:
                out.append(f"{name}: trống, nhãn {want!r}")
        elif not same_value(name, str(got["value"]), want):
            out.append(f"{name}: {got['value']!r} ≠ nhãn {want!r}")
    return out


def show_fields(result: dict[str, Any], labels: dict[str, Any]) -> tuple[int, list[str]]:
    """In bảng gợi ý so với nhãn; trả (số trường đúng trên 6, các trường high sai)."""
    fields = result.get("fields") or {}
    right, wrong_high = 0, []
    print(f"   {'trường':<17} {'tin cậy':<8} {'nguồn':<6} nhãn  gợi ý")
    for name in (*READ_FIELDS, "summary"):
        got, want = fields.get(name), expected(name, labels)
        if got is None:
            mark = "✓" if want is None else "·"
            right += want is None
            print(f"   {FIELD_NAMES[name]:<17} {'—':<8} {'—':<6} {mark:<5} (không gợi ý)")
            continue
        good = same_value(name, str(got["value"]), want)
        right += good
        if got["confidence"] == "high" and not good:
            wrong_high.append(f"{name} = {got['value']!r}, nhãn {want!r}")
        value = str(got["value"])
        value = value if len(value) <= 70 else value[:69] + "…"
        print(f"   {FIELD_NAMES[name]:<17} {got['confidence']:<8} {got['source']:<6} {'✓' if good else '✗':<5} {value}")
    if result.get("warnings"):
        print(f"   cảnh báo: {', '.join(result['warnings'])}")
    return right, wrong_high


def ai_ready() -> bool:
    try:
        return json.loads(compose("exec", "-T", "svc-files", "python", "-c", AI_READY)) is True
    except (subprocess.CalledProcessError, ValueError):
        return False


def doc_van_ban() -> None:
    print("Màn F4.1 · Đọc văn bản đến — tác tử moc-doc-reader đọc tệp văn thư vừa tải lên, gợi ý các ô tiếp nhận kèm độ"
          " tin cậy; văn thư kiểm, sửa, quyết. Gợi ý không tự ghi vào văn bản; văn bản hạn chế không bị đọc")
    tag = uuid.uuid4().hex[:6].upper()
    labels = {s["file"]: s for s in sample_labels()}
    clerk, director = Session("vanthu"), Session("truongkhoa")

    say(1, "Văn thư tải công văn 01-cong-van.pdf (PDF có lớp chữ, hai dòng đầu, V/v hai dòng) và bấm Đọc văn bản")
    letter = labels["01-cong-van.pdf"]
    file = upload_sample(clerk, letter["file"])
    first = read_file(clerk, file["id"])
    if first.get("method") != "text" or first.get("cached") or first.get("status") != "ok":
        raise DemoFailed(f"đọc PDF có lớp chữ chưa đúng: {first}")
    right, wrong = show_fields(first, letter["fields"])
    missing = [f for f in ("symbol", "issued_on", "type_code") if f not in first["fields"]]
    if wrong or missing:
        raise DemoFailed("gợi ý chưa đúng: " + "; ".join(wrong + [f"thiếu {f}" for f in missing]))
    ok(f"đọc lớp chữ {first['pages']} trang trong {first['duration_ms']} ms: {right}/6 ô khớp nhãn, không ô high nào"
       " sai; ô medium, low là ô văn thư cần kiểm kỹ")
    again = read_file(clerk, file["id"])
    if not again.get("cached") or again.get("fields") != first["fields"]:
        raise DemoFailed(f"bấm lại không trả gợi ý đã lưu: cached={again.get('cached')}")
    ok("bấm lại: trả ngay gợi ý đã lưu (cached), không đọc lại tệp, không ghi thêm dòng sổ kiểm toán")

    say(2, "Tải ảnh chụp của chính công văn đó (11-cong-van-anh-300dpi.jpg): không có lớp chữ, tác tử OCR bằng Tesseract")
    photo = labels["11-cong-van-anh-300dpi.jpg"]
    image = upload_sample(clerk, photo["file"])
    started = time.monotonic()
    try:
        scanned = read_file(clerk, image["id"])
    except HTTPError as exc:
        detail = error_detail(exc)
        hint = " — image svc-files chưa có tesseract-ocr-vie?" if detail.get("code") == "ocr_unavailable" else ""
        raise DemoFailed(f"đọc ảnh trả {exc.status} {detail or exc.body[:200]}{hint}") from exc
    took = time.monotonic() - started
    if scanned.get("method") != "ocr" or scanned.get("status") != "ok":
        raise DemoFailed(f"đọc ảnh chưa đúng: method {scanned.get('method')}, status {scanned.get('status')}")
    right, wrong = show_fields(scanned, photo["fields"])
    ok(f"OCR trang 1 trong {took:.1f} giây: {right}/6 ô khớp nhãn"
       + (f" — {len(wrong)} ô high sai: {'; '.join(wrong)}" if wrong else "; chữ OCR nhầm thì độ tin cậy hạ xuống"))

    say(3, "Văn thư kiểm gợi ý, sửa ô Cơ quan ban hành (medium) cho đủ tên trường, rồi lưu và vào sổ")
    values = {k: v["value"] for k, v in first["fields"].items()}
    data = {k: values.get(k) or letter["fields"][k] for k in ("type_code", "symbol", "issued_on", "summary")}
    data.update(urgency=values.get("urgency", "normal"), file_ids=[file["id"]],
                issuer_name=f"{values.get('issuer_name') or letter['fields']['issuer_name']}, Trường Đại học Mẫu")
    before = clerk.gql(RECEIVED_BEFORE, {"s": data["symbol"], "d": data["issued_on"]})["office_documents"]
    if before:
        doc_id, number = before[0]["id"], before[0]["register_number"]
        print(f"   – {data['symbol']} đã được tiếp nhận ở lần chạy trước — bỏ qua bước tiếp nhận (chặn trùng)")
    else:
        doc_id = clerk.gql("mutation ($d: jsonb!) { receiveIncoming(data: $d) { document_id } }",
                           {"d": data})["receiveIncoming"]["document_id"]
        number = None
        ok(f"Cơ quan ban hành: “{values.get('issuer_name')}” → “{data['issuer_name']}”; các ô khác giữ gợi ý — "
           "receiveIncoming kiểm lại theo schemas/van-ban-den.json như khi gõ tay")
    if number is None:
        number = clerk.gql("mutation ($id: uuid!) { registerIncoming(documentId: $id) { register_number } }",
                           {"id": doc_id})["registerIncoming"]["register_number"]
        ok(f"{data['symbol']} vào sổ, số đến {number} — từ đây là luồng văn bản đến bình thường")
    else:
        ok(f"{data['symbol']} đã vào sổ ở lần chạy trước, số đến {number}")

    say(4, "Lãnh đạo khoa đọc sổ kiểm toán: lần đọc do tác tử thực hiện, sổ chỉ có siêu dữ liệu")
    rows = director.gql(READ_AUDIT, {"f": file["id"]})["core_audit_log"]
    if len(rows) != 1:
        raise DemoFailed(f"tệp {file['id']} có {len(rows)} dòng intake.suggested (cần đúng 1: lần bấm lại không ghi)")
    row = rows[0]
    overview = row["overview"] or {}
    shown = json.dumps(overview, ensure_ascii=False)
    leaked = [f for f in ("symbol", "issuer_name", "summary") if f in values and str(values[f]) in shown]
    if (row["actor_id"], row["actor_kind"], row["entity"]) != ("moc-doc-reader", "agent", "core.files") or leaked:
        raise DemoFailed(f"dòng #{row['id']} chưa đúng: {row['actor_id']}/{row['actor_kind']}, lộ {leaked}: {shown}")
    ok(f"dòng #{row['id']} intake.suggested · {row['occurred_at'][:19].replace('T', ' ')} · người thực hiện"
       f" moc-doc-reader ({row['actor_kind']}) · method {overview.get('method')}, tìm được {overview.get('found')},"
       f" {overview.get('duration_ms')} ms")
    ok("không có số ký hiệu, cơ quan, trích yếu hay chữ nào của văn bản trong sổ — chỉ biết ai nhờ đọc, đọc ra những ô nào")

    say(5, "Tệp của văn bản hạn chế (mã hóa khi tải lên): tác tử không đọc")
    sealed = clerk.upload(f"han-che-{tag}.pdf", text_pdf("CONG HOA XA HOI CHU NGHIA VIET NAM", f"So: 77/QD-MAU{tag}",
                                                       "Danh sach nang luong truoc han nam 2026"), restricted=True)
    try:
        read_file(clerk, sealed["id"])
        raise DemoFailed("tệp của văn bản hạn chế vẫn đọc được")
    except HTTPError as exc:
        detail = error_detail(exc)
        if exc.status != 409 or detail.get("code") != "restricted":
            raise DemoFailed(f"tệp hạn chế trả {exc.status} {detail or exc.body[:200]}") from exc
    kept = psql(f"select count(*) from office.intake_suggestions where file_id = '{sealed['id']}'")
    if kept != "0":
        raise DemoFailed(f"office.intake_suggestions có {kept} dòng cho tệp hạn chế")
    ok(f"409 restricted: {detail.get('message')} — kiểm trước khi đọc byte, không tới OCR, không tới mô hình")
    ok("office.intake_suggestions: 0 dòng cho tệp này; CSDL cũng chặn lưu gợi ý của tệp mã hóa (trigger)")

    say(6, "Trích yếu bằng mô hình ngôn ngữ chạy tại chỗ (tùy chọn: profile ai, không ra Internet)")
    if not ai_ready():
        print("   – chưa bật mô hình — trích yếu theo quy tắc (make ai-model, xem docs)")
    else:
        invite = labels["06-giay-moi.pdf"]
        drafted = read_file(clerk, upload_sample(clerk, invite["file"])["id"])
        summary = drafted["fields"].get("summary") or {}
        if drafted.get("summary_source") != "model" or summary.get("source") != "model":
            raise DemoFailed(f"mô hình sẵn sàng mà trích yếu không do mô hình viết: cảnh báo {drafted.get('warnings')}")
        ok(f"giấy mời không có dòng V/v: {drafted.get('model')} viết trích yếu “{summary['value']}” (medium — văn thư"
           " kiểm); số, ngày, cơ quan vẫn do quy tắc")

    print(f"\nXem trên giao diện (vanthu): {PUBLIC_URL}/van-ban-den/tiep-nhan — tải tệp, các ô có nhãn \"Gợi ý\"; văn bản"
          f" vừa vào sổ: {PUBLIC_URL}/van-ban/{doc_id}; sổ kiểm toán (truongkhoa): {PUBLIC_URL}/so-kiem-toan?loai=files")


def score_reads(results: list[tuple[str, dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    """Mỗi trường: đúng / sai (điền mà khác — tệ hơn bỏ trống) / trống, riêng ô high; trích yếu: có / trùng ≥ 60% từ."""
    table = {f: {"đúng": 0, "sai": 0, "trống": 0, "high": 0, "high_sai": 0} for f in READ_FIELDS}
    table["summary"] = {"có": 0, "khớp": 0, "high": 0, "high_sai": 0}
    wrong: list[str] = []
    for name, labels, fields in results:
        for f in READ_FIELDS:
            got, want = fields.get(f), expected(f, labels)
            if got is None:
                table[f]["đúng" if want is None else "trống"] += 1
                continue
            good = same_value(f, str(got["value"]), want)
            table[f]["đúng" if good else "sai"] += 1
            if got["confidence"] == "high":
                table[f]["high"] += 1
                if not good:
                    table[f]["high_sai"] += 1
                    wrong.append(f"{name}: {f} = {got['value']!r} (high), nhãn {want!r}")
        got = fields.get("summary")
        if got is not None:
            good = same_value("summary", str(got["value"]), labels["summary"])
            table["summary"]["có"] += 1
            table["summary"]["khớp"] += good
            if got["confidence"] == "high":
                table["summary"]["high"] += 1
                if not good:
                    table["summary"]["high_sai"] += 1
                    wrong.append(f"{name}: summary = {got['value']!r} (high), nhãn {labels['summary']!r}")
    return {"n": len(results), "table": table, "wrong": wrong}


def accuracy_table(title: str, measured: dict[str, Any]) -> str:
    n, t = measured["n"], measured["table"]
    rows = [f"### {title} — {n} tệp", "| trường | đúng | sai | trống | high (sai) |", "|---|---|---|---|---|"]
    rows += [f"| {f} | {t[f]['đúng']}/{n} | {t[f]['sai']} | {t[f]['trống']} | {t[f]['high']} ({t[f]['high_sai']}) |"
             for f in READ_FIELDS]
    s = t["summary"]
    rows.append(f"| summary | có {s['có']}/{n}, trùng ≥ 60% từ {s['khớp']}/{n} | | | {s['high']} ({s['high_sai']}) |")
    return "\n".join(rows)


def do_doc_van_ban() -> None:
    print("Đo F4.1 · Tác tử đọc từng văn bản mẫu trong seed/van-ban-den qua APISIX như văn thư (force=true), so với nhãn"
          " nhan.json")
    clerk = Session("vanthu")
    results: dict[str, list] = {"text": [], "scan": []}
    took: dict[str, list[float]] = {"text": [], "scan": []}
    server: dict[str, list[int]] = {"text": [], "scan": []}
    models: set[str] = set()
    print()
    for sample in sample_labels():
        name, kind = sample["file"], sample["kind"]
        file = upload_sample(clerk, name)
        started = time.monotonic()
        try:
            got = read_file(clerk, file["id"], force=True)
        except HTTPError as exc:
            detail = error_detail(exc)
            got = {"method": "lỗi", "fields": {}, "warnings": [f"{exc.status} {detail.get('code')}"
                                                              f" {detail.get('reason') or ''}".strip()]}
        took[kind].append(time.monotonic() - started)
        if isinstance(got.get("duration_ms"), int):
            server[kind].append(got["duration_ms"])
        if got.get("model"):
            models.add(got["model"])
        fields = got.get("fields") or {}
        results[kind].append((name, sample["fields"], fields))
        wrong = misses(fields, sample["fields"])
        note = f" · cảnh báo {', '.join(got['warnings'])}" if got.get("warnings") else ""
        print(f"   {name:<30} {got.get('method', '?'):<4} {took[kind][-1]:5.1f} s  {6 - len(wrong)}/6 ô khớp{note}")
        for miss in wrong:
            print(f"      ✗ {miss[:110]}")

    for kind, title in (("text", "PDF có lớp chữ"), ("scan", "Ảnh, bản scan (OCR)")):
        if results[kind]:
            print("\n" + accuracy_table(title, score_reads(results[kind])))
            inside = f" (svc-files tự đo {sum(server[kind]) / len(server[kind]):.0f} ms)" if server[kind] else ""
            print(f"\nTrung bình {sum(took[kind]) / len(took[kind]):.1f} giây/tệp từ lúc gọi tới lúc có gợi ý{inside}")
    print(f"Trích yếu bằng mô hình: {', '.join(sorted(models)) if models else 'không (chưa bật profile ai)'}")

    every = score_reads(results["text"] + results["scan"])
    whole = every["table"]
    print(f"\nCả kho {every['n']} văn bản (\"Hoàn thành khi\" của Phase 4: trên 20 công văn mẫu): số ký hiệu đúng"
          f" {whole['symbol']['đúng']}/{every['n']}, ngày ban hành đúng {whole['issued_on']['đúng']}/{every['n']}")

    measured = score_reads(results["text"])
    t, n = measured["table"], measured["n"]
    right = {f: t[f]["có"] if f == "summary" else t[f]["đúng"] for f in TEXT_MIN}
    below = [f"PDF có lớp chữ: {FIELD_NAMES[f].lower()} {right[f]}/{n} < {minimum} %"
             for f, minimum in TEXT_MIN.items() if 100 * right[f] < minimum * n]
    if not n:
        below.append("nhan.json không có PDF có lớp chữ")
    # "Hoàn thành khi" của Phase 4: trên 20 công văn mẫu, số ký hiệu và ngày ban hành đúng ở phần lớn văn bản
    if every["n"] < 20:
        below.append(f"cả kho chỉ có {every['n']} văn bản, cần ít nhất 20")
    below += [f"cả kho: {FIELD_NAMES[f].lower()} đúng {whole[f]['đúng']}/{every['n']}, chưa quá nửa"
              for f in ("symbol", "issued_on") if 2 * whole[f]["đúng"] <= every["n"]]
    if below or measured["wrong"]:
        raise DemoFailed("Dưới ngưỡng: " + "; ".join(below + measured["wrong"]))
    print(f"\n✓ {n} PDF có lớp chữ đạt ngưỡng: số ký hiệu, ngày ban hành, loại ≥ 90 %; cơ quan ban hành, trích yếu"
          f" ≥ 80 %; không ô high nào sai · cả kho {every['n']} văn bản: số ký hiệu, ngày ban hành đúng quá nửa")


# --- F4.2 · Hỏi đáp trên kho văn bản ---------------------------------------------------------------------------------
# Kho văn bản mẫu hư cấu đi kèm mã nguồn (sinh lại: make hoi-dap-mau); câu hỏi kèm đáp án trong cau-hoi.json
ASK_DIR = ROOT / "seed" / "hoi-dap"
ASK_URL = f"{PUBLIC_URL}/api/documents/ask"
TOP = 3
# Trạng thái không trả lời: câu âm, câu bị cấm đúng khi rơi vào một trong hai
REFUSED = ("no_evidence", "passages_only")
# Ngưỡng của make do-hoi-dap: recall@3 trên các câu dương — chốt lại sau lần đo đầu trên bản cài (số đo ghi ở
# services/svc-files/README.md). Câu quyền, câu hạn chế có nguồn bị cấm thì luôn là lỗi
RECALL_MIN = 0.8
# Trưởng đơn vị phân công người xử lý sau khi lãnh đạo khoa giao (seed/users.csv); tên đơn vị trong ý kiến chỉ đạo
MANAGERS = {"ĐT": "totruongdt", "KTPM": "truongbmktpm"}
UNIT_NAMES = {"ĐT": "Tổ Đào tạo", "KTPM": "Bộ môn Kỹ thuật phần mềm", "HTTT": "Bộ môn Hệ thống thông tin",
              "VP": "Văn phòng khoa"}
ASK_DOCUMENT = """query ($s: String!) { office_documents(where: {direction: {_eq: "in"}, symbol: {_eq: $s}}) {
  id restricted files { role file_id } } }"""
ASK_AUDIT = """query ($e: String!) { core_audit_log(where: {action: {_eq: "assistant.answered"}, entity_id: {_eq: $e}},
  order_by: {id: asc}) { id occurred_at entity actor_id actor_kind overview } }"""
# /readyz của svc-files: "assist" cho biết chỉ mục, tìm theo nghĩa, mô hình đang dùng — in kèm số đo
ASSIST_INFO = """import json, urllib.error, urllib.request
try:
    raw = urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=5).read()
except urllib.error.HTTPError as exc:
    raw = exc.read()
print(json.dumps(json.loads(raw).get('assist')))
"""
_SESSIONS: dict[str, Session] = {}


def who(username: str) -> Session:
    """Một phiên cho mỗi tài khoản suốt lượt chạy: mỗi lần đăng nhập văn thư, lãnh đạo tốn một mã TOTP."""
    if username not in _SESSIONS:
        _SESSIONS[username] = Session(username)
    return _SESSIONS[username]


def ask_samples() -> dict[str, Any]:
    path = ASK_DIR / "cau-hoi.json"
    if not path.is_file():
        raise DemoFailed(f"không có {path.relative_to(ROOT)} — kho mẫu đi kèm mã nguồn (sinh lại: make hoi-dap-mau)")
    return json.loads(path.read_text(encoding="utf-8"))


def flat(text: str | None) -> str:
    """So chữ: NFC, gộp mọi khoảng trắng, không phân biệt hoa thường."""
    return " ".join(unicodedata.normalize("NFC", text or "").split()).casefold()


def same_symbol(got: str | None, want: str | None) -> bool:
    return bool(want) and "".join((got or "").split()).casefold() == "".join(want.split()).casefold()


def source_label(src: dict[str, Any]) -> str:
    """Nhãn trích dẫn như giao diện: "88/CTSV · tr. 1", "… · tài liệu kèm theo, tr. 2", "… · trích yếu"."""
    name = src.get("symbol") or (src.get("summary") or "?")[:40]
    if src.get("kind") != "page" or src.get("page") is None:
        return f"{name} · trích yếu"
    part = "tài liệu kèm theo, " if src.get("file_role") == "attachment" else ""
    return f"{name} · {part}tr. {src['page']}"


def matches(src: dict[str, Any], want: dict[str, Any]) -> bool:
    """Nguồn khớp một đáp án: cùng số ký hiệu (văn bản đi lấy số lúc phát hành, không biết trước: trích yếu chứa
    chuỗi cho trước) và cùng trang; đoạn "trích yếu" không có trang nên không khớp đáp án có trang."""
    if "symbol" in want:
        same = same_symbol(src.get("symbol"), want["symbol"])
    else:
        same = bool(want.get("summary_contains")) and flat(want["summary_contains"]) in flat(src.get("summary"))
    return same and ("page" not in want or (src.get("kind") == "page" and src.get("page") == want["page"]))


def hit_rank(sources: list[dict[str, Any]], expect: Any) -> int | None:
    """Thứ hạng (từ 1) của nguồn đầu tiên khớp một đáp án; None khi không có (câu âm: luôn None)."""
    if not isinstance(expect, list):
        return None
    return next((i for i, src in enumerate(sources, 1) if any(matches(src, w) for w in expect)), None)


def forbidden(sources: list[dict[str, Any]], symbols: list[str]) -> list[str]:
    """Nhãn các nguồn mang số ký hiệu bị cấm (câu quyền, văn bản hạn chế)."""
    return [source_label(s) for s in sources if any(same_symbol(s.get("symbol"), x) for x in symbols)]


def keywords_in(text: str | None, keywords: list[str]) -> bool:
    """Câu trả lời có đủ mọi từ khóa — so sau casefold và gộp khoảng trắng."""
    body = flat(text)
    return bool(keywords) and all(flat(k) in body for k in keywords)


def answer_text(result: dict[str, Any]) -> str:
    return (result.get("answer") or {}).get("text") or ""


def restricted_symbols(data: dict[str, Any]) -> list[str]:
    """Số ký hiệu văn bản hạn chế của kho mẫu: không câu hỏi nào, của bất kỳ ai, được có nguồn này."""
    return [d["symbol"] for d in data["documents"] if d.get("restricted")]


def score(question: dict[str, Any], result: dict[str, Any], seconds: float, *, restricted: list[str]) -> dict:
    """Chấm một lượt extract theo đáp án: câu dương đúng khi nguồn đáp án nằm trong 3 nguồn đầu; câu âm đúng khi
    trợ lý không trả lời — no_evidence, hoặc passages_only (chỉ đưa đoạn liên quan trong văn bản được xem, không câu
    trích nào đủ khớp: ngưỡng điểm tìm kiếm quyết định, không phải chuyện quyền); nguồn bị cấm (danh sách của câu +
    văn bản hạn chế) ghi riêng, luôn là lỗi."""
    expect = question["expect"]
    sources = result.get("sources") or []
    positive = isinstance(expect, list)
    rank = hit_rank(sources, expect)
    status = result.get("status") or "?"
    return {"id": question["id"], "user": question["user"], "question": question["question"], "positive": positive,
            "status": status, "top": [source_label(s) for s in sources[:TOP]], "rank": rank,
            "correct": (rank is not None and rank <= TOP) if positive else status in REFUSED,
            "keywords": keywords_in(answer_text(result), question.get("keywords", [])) if positive else None,
            "forbidden": forbidden(sources, [*question.get("forbid", []), *restricted]),
            "guarded": bool(question.get("forbid")), "seconds": seconds, "server_ms": result.get("duration_ms"),
            "semantic": bool(result.get("semantic")), "warnings": list(result.get("warnings") or []), "model": None}


def score_model(question: dict[str, Any], result: dict[str, Any], seconds: float, *, restricted: list[str]) -> dict:
    """Chấm lượt generate: câu trả lời do mô hình viết và qua kiểm (answer.source = model), chứa từ khóa, có [n] trỏ
    tới nguồn đáp án."""
    answer = result.get("answer") or {}
    sources = result.get("sources") or []
    by_model = answer.get("source") == "model"
    expect = question["expect"]
    cited = [s for s in sources if s.get("cited")]
    return {"by_model": by_model, "name": answer.get("model"), "status": result.get("status") or "?",
            "keywords": by_model and keywords_in(answer.get("text"), question.get("keywords", [])),
            "cites": by_model and isinstance(expect, list) and any(matches(s, w) for s in cited for w in expect),
            "forbidden": forbidden(sources, [*question.get("forbid", []), *restricted]),
            "warnings": list(result.get("warnings") or []), "seconds": seconds}


def percentile(values: list[float], p: float) -> float | None:
    """Phân vị p (0–100), cách lấy hạng gần nhất: p50 của [1, 2, 3, 4] là 2, p95 là 4."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(1, -(-len(ordered) * p // 100)) - 1]


def summarize(rows: list[dict]) -> dict[str, Any]:
    pos = [r for r in rows if r["positive"]]
    neg = [r for r in rows if not r["positive"]]
    gen = [r for r in rows if r["model"]]
    gen_pos = [r for r in gen if r["positive"]]
    violations = [f"{r['id']} ({r['user']}): {', '.join(r['forbidden'])}" for r in rows if r["forbidden"]]
    violations += [f"{r['id']} ({r['user']}, generate): {', '.join(r['model']['forbidden'])}"
                   for r in gen if r["model"]["forbidden"]]
    server = [r["server_ms"] for r in rows if isinstance(r["server_ms"], int)]
    out: dict[str, Any] = {
        "positives": len(pos), "recall": sum(r["correct"] for r in pos), "keywords": sum(bool(r["keywords"]) for r in pos),
        "negatives": len(neg), "refused": sum(r["correct"] for r in neg),
        "no_evidence": sum(r["status"] == "no_evidence" for r in neg), "guarded": sum(r["guarded"] for r in rows),
        "violations": violations, "semantic": sum(r["semantic"] for r in rows), "asked": len(rows),
        "p50": percentile([r["seconds"] for r in rows], 50), "p95": percentile([r["seconds"] for r in rows], 95),
        "server_p50": percentile(server, 50), "server_p95": percentile(server, 95), "model": None}
    if gen:
        out["model"] = {
            "asked": len(gen), "by_model": sum(r["model"]["by_model"] for r in gen), "positives": len(gen_pos),
            "keywords": sum(bool(r["model"]["keywords"]) for r in gen_pos),
            "cites": sum(bool(r["model"]["cites"]) for r in gen_pos),
            "negatives": len(gen) - len(gen_pos),
            "neg_answered": sum(r["model"]["by_model"] for r in gen if not r["positive"]),
            "names": sorted({r["model"]["name"] for r in gen if r["model"]["name"]}),
            "p50": percentile([r["model"]["seconds"] for r in gen], 50),
            "p95": percentile([r["model"]["seconds"] for r in gen], 95)}
    return out


def verdict(summary: dict[str, Any]) -> list[str]:
    """Lý do thoát 1 (rỗng: đạt): mọi nguồn bị cấm; recall@3 câu dương dưới RECALL_MIN."""
    problems = [f"nguồn bị cấm — {v}" for v in summary["violations"]]
    if summary["positives"] and summary["recall"] < RECALL_MIN * summary["positives"]:
        problems.append(f"recall@3 {summary['recall']}/{summary['positives']} dưới ngưỡng {RECALL_MIN:.0%}")
    return problems


def result_table(rows: list[dict]) -> str:
    """Bảng markdown từng câu: trạng thái, nguồn top-3, đúng / sai, từ khóa, thời gian (thêm cột mô hình nếu có)."""
    with_model = any(r["model"] for r in rows)
    head = "| câu | người hỏi | trạng thái | nguồn top-3 | đúng | từ khóa | thời gian |"
    line = "|---|---|---|---|---|---|---|"
    if with_model:
        head += " mô hình | từ khóa | trích đúng | thời gian |"
        line += "---|---|---|---|"
    out = [head, line]
    mark = {True: "✓", False: "✗", None: "—"}
    for r in rows:
        question = r["question"] if len(r["question"]) <= 48 else r["question"][:47] + "…"
        right = "✗ CẤM: " + ", ".join(r["forbidden"]) if r["forbidden"] else (
            mark[r["correct"]] + (f" #{r['rank']}" if r["rank"] else ""))
        cells = [f"{r['id']} {question}", r["user"], r["status"], "; ".join(r["top"]) or "—", right,
                 mark[r["keywords"]], f"{r['seconds']:.1f} s"]
        if with_model:
            m = r["model"]
            cells += (["—"] * 4 if m is None else [
                ("viết" if m["by_model"] else ", ".join(m["warnings"]) or m["status"]),
                mark[m["keywords"] if r["positive"] else None], mark[m["cites"] if r["positive"] else None],
                f"{m['seconds']:.1f} s"])
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def ask(session: Session, question: str, *, mode: str = "extract", ask_id: str | None = None) -> tuple[dict, float]:
    """POST /api/documents/ask qua APISIX bằng token người hỏi → (kết quả, số giây). Token hết hạn giữa lượt đo dài
    thì đăng nhập lại một lần; hết lượt sinh (503 busy) thì đợi như Retry-After rồi gọi lại, tối đa ba lần."""
    body: dict[str, Any] = {"question": question, "mode": mode}
    if ask_id:
        body["ask_id"] = ask_id
    attempts = 0
    while True:
        started = time.monotonic()
        try:
            _, _, raw = request("POST", ASK_URL, data=json.dumps(body).encode(), timeout=25 if mode == "extract" else 70,
                                headers={**session.auth, "Content-Type": "application/json"})
            return json.loads(raw), time.monotonic() - started
        except HTTPError as exc:
            attempts += 1
            if exc.status == 401 and attempts == 1:
                session.token = user_token(session.username)
                continue
            if exc.status != 503 or error_detail(exc).get("code") != "busy" or attempts >= 3:
                raise
            time.sleep(10)


def show_answer(result: dict[str, Any]) -> None:
    """In câu trả lời và danh sách nguồn như trang Hỏi đáp."""
    for line in answer_text(result).splitlines() or ["(không có câu trả lời)"]:
        print(f"     {line}")
    for src in result.get("sources") or []:
        cited = "" if src.get("cited") else " (liên quan, không trích)"
        print(f"     [{src['n']}] {source_label(src)} · {src.get('issuer_name') or '?'}{cited}")


def refusal(result: dict[str, Any]) -> str:
    """Kết quả của câu lẽ ra không có câu trả lời, in như giao diện: không tìm thấy gì; chỉ có đoạn liên quan mà không
    câu nào đủ khớp; hoặc câu trích từ văn bản khác mà người hỏi được xem."""
    labels = ", ".join(source_label(s) for s in result.get("sources") or [])
    if result.get("status") == "no_evidence":
        return "no_evidence: “Không tìm thấy văn bản nào bạn được xem có nội dung này”"
    if result.get("status") == "passages_only":
        return f"passages_only: “Chưa trích được câu trả lời ngắn” — đoạn liên quan trong văn bản được xem: {labels}"
    return f"{result.get('status')}: câu trích từ văn bản khác mà người hỏi được xem: {labels}"


def load_corpus(data: dict[str, Any]) -> tuple[dict[str, dict], int]:
    """Nạp kho mẫu như văn thư: tải lên (văn bản hạn chế ở chế độ hạn chế, trước tiên — đọc chữ theo thứ tự tải
    lên), tiếp nhận, vào sổ; lãnh đạo khoa giao đơn vị chủ trì, trưởng đơn vị phân công theo "assign". Văn bản đã có
    (cùng số ký hiệu) thì bỏ qua → (văn bản theo số ký hiệu, số văn bản mới)."""
    from seed_documents import DEPT, today

    clerk, director = who("vanthu"), who("truongkhoa")
    loaded: dict[str, dict] = {}
    created = 0
    for d in sorted(data["documents"], key=lambda d: not d["restricted"]):
        found = clerk.gql(ASK_DOCUMENT, {"s": d["symbol"]})["office_documents"]
        if found:
            loaded[d["symbol"]] = found[0]
            continue
        file = clerk.upload(d["file"], (ASK_DIR / d["file"]).read_bytes(), restricted=d["restricted"])
        doc_id = clerk.gql("mutation ($d: jsonb!) { receiveIncoming(data: $d) { document_id } }", {"d": {
            "type_code": d["type_code"], "symbol": d["symbol"], "issuer_name": d["issuer_name"],
            "issued_on": d["issued_on"], "summary": d["summary"], "urgency": "normal", "restricted": d["restricted"],
            "file_ids": [file["id"]]}})["receiveIncoming"]["document_id"]
        clerk.gql("mutation ($id: uuid!) { registerIncoming(documentId: $id) { register_number } }", {"id": doc_id})
        assign = d.get("assign")
        if assign:
            director.complete(director.wait_task(doc_id, "vbden.chiDao"), "direct", {
                "instruction": f"Giao {UNIT_NAMES[assign['lead']]} chủ trì nghiên cứu, triển khai.",
                "lead_department_id": DEPT[assign["lead"]], "supports": [],
                "due_on": (today() + timedelta(days=14)).isoformat()})
            if assign.get("handler"):
                manager = who(MANAGERS[assign["lead"]])
                user_id = manager.gql("query ($u: String!) { core_users(where: {username: {_eq: $u}}) { id } }",
                                      {"u": assign["handler"]})["core_users"][0]["id"]
                manager.complete(manager.wait_task(doc_id, "vbden.phanCong"), "assign",
                                 {"user_id": user_id, "note": "Đề nghị nghiên cứu, thực hiện."})
        loaded[d["symbol"]] = {"id": doc_id, "restricted": d["restricted"],
                               "files": [{"role": "main", "file_id": file["id"]}]}
        created += 1
    return loaded, created


def wait_indexed(data: dict[str, Any], timeout_s: float) -> float:
    """Đợi vòng nền svc-files đọc chữ từng trang rồi đưa đoạn vào chỉ mục: hỏi thử câu đầu của mỗi văn bản mẫu (đúng
    người hỏi) tới khi một trang của văn bản đó có trong nguồn → số giây đã đợi. Nguồn "trích yếu" không tính: trích
    yếu vào chỉ mục ngay lúc tiếp nhận, trước khi chữ các trang được đọc (bản cài mới thì trả lời lúc đó còn thiếu)."""
    probes: dict[str, dict] = {}
    for q in data["questions"]:
        for want in q["expect"] if isinstance(q["expect"], list) else []:
            if any(d["symbol"] == want.get("symbol") for d in data["documents"]):
                probes.setdefault(want["symbol"], q)
    started = time.monotonic()
    while probes:
        for symbol, q in list(probes.items()):
            try:
                sources = ask(who(q["user"]), q["question"])[0].get("sources") or []
            except HTTPError as exc:        # Meilisearch, Hasura vừa khởi động: đợi tiếp; tắt trợ lý thì dừng
                if exc.status != 503 or error_detail(exc).get("code") == "assistant_disabled":
                    raise
                sources = []
            if any(same_symbol(s.get("symbol"), symbol) and s.get("kind") == "page" for s in sources):
                del probes[symbol]
        if not probes:
            break
        if time.monotonic() - started > timeout_s:
            raise DemoFailed(f"sau {timeout_s:.0f} giây chỉ mục đoạn chưa có {', '.join(probes)} — vòng nền svc-files"
                             " (đọc chữ MOC_TEXT_INTERVAL_S, chỉ mục MOC_ASK_SYNC_INTERVAL_S) có chạy không?")
        time.sleep(3)
    return time.monotonic() - started


def hoi_dap() -> None:
    print("Màn F4.2 · Hỏi đáp trên kho văn bản — trợ lý moc-assistant chỉ tìm trong các văn bản người hỏi được xem, trả"
          " câu trích nguyên văn kèm số ký hiệu và trang; văn bản hạn chế không bao giờ vào chỉ mục")
    data = ask_samples()
    qs = {q["id"]: q for q in data["questions"]}
    sealed = restricted_symbols(data)

    say(1, "Văn thư nạp kho mẫu seed/hoi-dap: tải lên, tiếp nhận, vào sổ; lãnh đạo khoa giao việc như cau-hoi.json")
    loaded, created = load_corpus(data)
    pages = sum(d["pages"] for d in data["documents"] if not d["restricted"])
    again = "" if created == len(loaded) else ", còn lại đã nạp ở lần chạy trước"
    ok(f"{len(loaded)} văn bản ({created} mới{again}): {len(loaded) - len(sealed)} văn bản {pages} trang + {len(sealed)}"
       f" văn bản hạn chế ({', '.join(sealed)}, tệp mã hóa)")
    took = wait_indexed(data, 90)
    ok(f"svc-files đã đọc chữ từng trang và đưa đoạn vào chỉ mục (đợi {took:.0f} giây) — không cần mô hình nào")

    q = qs["q01"]
    say(2, f"{q['user']} hỏi: “{q['question']}”")
    first, _ = ask(who(q["user"]), q["question"])
    show_answer(first)
    rank = hit_rank(first.get("sources") or [], q["expect"])
    want = q["expect"][0]
    if first.get("status") != "answered" or rank is None or rank > TOP or not keywords_in(answer_text(first),
                                                                                          q["keywords"]):
        raise DemoFailed(f"chưa trả đúng câu trích của {want['symbol']} tr. {want['page']} (có “{q['keywords'][0]}”):"
                         f" trạng thái {first.get('status')},"
                         f" nguồn {[source_label(s) for s in first.get('sources') or []]}")
    search = "từ khóa và theo nghĩa" if first.get("semantic") else "từ khóa"
    ok(f"nguồn [{rank}] {want['symbol']} · tr. {want['page']} ✓ khớp đáp án trong cau-hoi.json; câu trích có"
       f" “{q['keywords'][0]}”; tìm theo {search}, svc-files trả lời trong {first.get('duration_ms')} ms")

    q, guarded = qs["q14"], qs["q19"]
    say(3, f"Cùng một câu, hai người hỏi: “{q['question']}” — trợ lý chỉ tìm trong văn bản người hỏi được xem")
    got, _ = ask(who(q["user"]), q["question"])
    rank = hit_rank(got.get("sources") or [], q["expect"])
    if rank is None or rank > TOP or not keywords_in(answer_text(got), q["keywords"]):
        raise DemoFailed(f"{q['user']} chưa được câu trích của {q['expect'][0]['symbol']}: {got.get('status')}, nguồn"
                         f" {[source_label(s) for s in got.get('sources') or []]}")
    ok(f"{q['user']} → [{rank}] {source_label(got['sources'][rank - 1])}: câu trích có “{q['keywords'][0]}”")
    denied, _ = ask(who(guarded["user"]), guarded["question"])
    leaked = forbidden(denied.get("sources") or [], [*guarded["forbid"], *sealed])
    if leaked:
        raise DemoFailed(f"{guarded['user']} hỏi ra văn bản không được xem: {leaked}")
    ok(f"{guarded['user']} (Bộ môn KTPM) → {refusal(denied)} — {' và '.join(guarded['forbid'])} giao Tổ Đào tạo,"
       " giảng viên KTPM không được xem; câu trả lời không để lộ các văn bản đó có tồn tại")
    q = qs["q10"]
    allowed, _ = ask(who(q["user"]), q["question"])
    rank = hit_rank(allowed.get("sources") or [], q["expect"])
    if rank is None or rank > TOP or not keywords_in(answer_text(allowed), q["keywords"]):
        raise DemoFailed(f"giảng viên KTPM không hỏi được văn bản giao cho mình: {allowed.get('status')}, nguồn"
                         f" {[source_label(s) for s in allowed.get('sources') or []]}")
    ok(f"“{q['question']}” → {answer_text(allowed).splitlines()[0]} — {q['expect'][0]['symbol']} giao Bộ môn KTPM,"
       f" giảng viên được phân công xử lý")

    q = qs["q18"]
    say(4, f"Văn bản hạn chế {', '.join(sealed)}: hỏi đúng cụm từ riêng của nó, bằng người tạo (vanthu) và lãnh đạo"
           " khoa (có tên trong danh sách được xem)")
    for name in ("vanthu", "truongkhoa"):
        got, _ = ask(who(name), q["question"])
        if forbidden(got.get("sources") or [], sealed):
            raise DemoFailed(f"{name} hỏi nội dung văn bản hạn chế → {got.get('status')}, nguồn"
                             f" {[source_label(s) for s in got.get('sources') or []]}")
        ok(f"{name} → {refusal(got)}")
    file_ids = [f["file_id"] for symbol in sealed for f in loaded[symbol]["files"]]
    texts = psql("select count(*) from core.file_texts where file_id in (%s)" % ", ".join(f"'{f}'" for f in file_ids))
    if texts != "0":
        raise DemoFailed(f"core.file_texts có {texts} dòng của tệp văn bản hạn chế")
    ok("core.file_texts: 0 dòng của tệp này — chữ của văn bản hạn chế không được đọc, không vào chỉ mục, không tới"
       " mô hình, kể cả với người được xem văn bản")

    say(5, "Lãnh đạo khoa đọc sổ kiểm toán: mỗi lượt hỏi một dòng của tác tử moc-assistant, không có câu hỏi, câu"
           " trả lời")
    rows = who("truongkhoa").gql(ASK_AUDIT, {"e": first["ask_id"]})["core_audit_log"]
    if len(rows) != 1:
        raise DemoFailed(f"lượt hỏi {first['ask_id']} có {len(rows)} dòng assistant.answered (cần đúng 1)")
    row = rows[0]
    overview = row["overview"] or {}
    if (row["actor_id"], row["actor_kind"], row["entity"]) != ("moc-assistant", "agent", "ai.questions") \
            or any(overview.get(k) is None for k in ("mode", "hits", "cited")):
        raise DemoFailed(f"dòng #{row['id']} chưa đúng: {row['actor_id']}/{row['actor_kind']}/{row['entity']}, tóm tắt"
                         f" {overview}")
    diff = psql(f"select diff::text from core.audit_log where id = {int(row['id'])}").casefold()
    words = [w for w in re.findall(r"\w+", qs["q01"]["question"]) if len(w) >= 3 and not w.isdigit()]
    leaked = [w for w in words if w.casefold() in diff] + [s for s in ("15/QĐ-ĐHM", "tín chỉ") if s.casefold() in diff]
    if leaked:
        raise DemoFailed(f"diff của dòng #{row['id']} có chữ của câu hỏi, câu trả lời: {leaked}")
    ok(f"dòng #{row['id']} assistant.answered · {row['occurred_at'][:19].replace('T', ' ')} · người thực hiện"
       f" moc-assistant ({row['actor_kind']}) · mode {overview.get('mode')}, {overview.get('hits')} nguồn, trích"
       f" {overview.get('cited')}, {overview.get('duration_ms')} ms")
    ok("psql: diff của dòng không có từ nào của câu hỏi, không có câu trích, số ký hiệu — chỉ biết ai hỏi, lúc nào,"
       " được mấy nguồn")

    q = qs["q02"]
    say(6, f"Câu trả lời do mô hình ngôn ngữ chạy tại chỗ viết (tùy chọn: profile ai) — {q['user']} hỏi"
           f" “{q['question']}”")
    base, _ = ask(who(q["user"]), q["question"])
    if not base.get("ai_available"):
        quote = answer_text(base).splitlines()[0] if answer_text(base) else "—"
        print(f"   – chưa bật mô hình — trả lời bằng câu trích: {quote} (make ai-model && make up-ai)")
    else:
        got, took = ask(who(q["user"]), q["question"], mode="generate", ask_id=base["ask_id"])
        show_answer(got)
        answer = got.get("answer") or {}
        if answer.get("source") == "model":
            ok(f"{answer.get('model')} viết câu trả lời trong {took:.0f} giây; svc-files gắn [n] cho từng câu theo"
               " bằng chứng (số, độ phủ) — giao diện ghi rõ “Do mô hình ngôn ngữ viết — đối chiếu nguồn”")
        else:
            print(f"   – mô hình không qua kiểm ({', '.join(got.get('warnings') or []) or got.get('status')}) — giữ câu"
                  " trích nguyên văn, như giao diện hiện")
        both = who("truongkhoa").gql(ASK_AUDIT, {"e": base["ask_id"]})["core_audit_log"]
        modes = [(r["overview"] or {}).get("mode") for r in both]
        if modes != ["extract", "generate"]:
            raise DemoFailed(f"lượt hỏi hai pha chưa đủ hai dòng sổ cùng mã: {modes}")
        ok("sổ kiểm toán: hai dòng cùng mã lượt hỏi (extract rồi generate)")

    print(f"\nXem trên giao diện (vanthu): {PUBLIC_URL}/hoi-dap — hỏi “{qs['q14']['question']}”; sổ kiểm toán"
          f" (truongkhoa): {PUBLIC_URL}/so-kiem-toan")


def failure(exc: Exception) -> str:
    """Trạng thái ghi vào bảng đo khi một lượt hỏi lỗi (HTTP, quá giờ) — lượt đo vẫn chạy tiếp các câu sau."""
    if isinstance(exc, HTTPError):
        return f"lỗi {exc.status} {error_detail(exc).get('code') or ''}".strip()
    return f"lỗi {type(exc).__name__}"


def do_hoi_dap() -> None:
    print("Đo F4.2 · Trợ lý hỏi đáp trên mọi câu trong seed/hoi-dap/cau-hoi.json, đúng người hỏi, qua APISIX")
    data = ask_samples()
    sealed = restricted_symbols(data)
    loaded, created = load_corpus(data)
    took = wait_indexed(data, 120)
    print(f"   kho mẫu: {len(loaded)} văn bản ({created} mới), chỉ mục sẵn sàng sau {took:.0f} giây")
    try:
        info = json.loads(compose("exec", "-T", "svc-files", "python", "-c", ASSIST_INFO))
    except (subprocess.CalledProcessError, ValueError):
        info = None
    print(f"   svc-files /readyz assist: {json.dumps(info, ensure_ascii=False)}\n")
    rows = []
    for q in data["questions"]:
        session = who(q["user"])
        try:
            got, seconds = ask(session, q["question"])
        except (HTTPError, OSError) as exc:
            got, seconds = {"status": failure(exc)}, 0.0
        row = score(q, got, seconds, restricted=sealed)
        if got.get("ai_available") and got.get("status") not in (None, "no_evidence"):
            try:
                gen, gen_seconds = ask(session, q["question"], mode="generate", ask_id=got.get("ask_id"))
            except (HTTPError, OSError) as exc:
                gen, gen_seconds = {"status": failure(exc)}, 0.0
            row["model"] = score_model(q, gen, gen_seconds, restricted=sealed)
        rows.append(row)
        print(f"   {q['id']} {q['user']:<14} {row['status']:<14} {'✓' if row['correct'] else '✗'}"
              f" {seconds:4.1f} s  {'; '.join(row['top']) or '—'}")

    s = summarize(rows)
    print("\n" + result_table(rows))
    print(f"\nrecall@3 (câu dương): {s['recall']}/{s['positives']} · câu trích có từ khóa:"
          f" {s['keywords']}/{s['positives']} · từ chối đúng (câu âm, câu bị cấm không được trả lời):"
          f" {s['refused']}/{s['negatives']}, trong đó no_evidence {s['no_evidence']}")
    print(f"an toàn: {len(s['violations'])} lượt có nguồn bị cấm ({s['guarded']} câu có danh sách cấm, văn bản hạn chế"
          f" {', '.join(sealed)} cấm ở mọi câu) · tìm theo nghĩa {s['semantic']}/{s['asked']} lượt")
    print(f"thời gian extract: p50 {s['p50']:.1f} s, p95 {s['p95']:.1f} s"
          + (f" (svc-files tự đo p50 {s['server_p50']} ms, p95 {s['server_p95']} ms)" if s["server_p50"] is not None
             else ""))
    m = s["model"]
    if m is None:
        print("mô hình sinh: không (chưa bật profile ai — make ai-model && make up-ai rồi chạy lại)")
    else:
        print(f"mô hình sinh {', '.join(m['names']) or '?'}: qua kiểm {m['by_model']}/{m['asked']} · chứa từ khóa"
              f" {m['keywords']}/{m['positives']} · trích đúng nguồn {m['cites']}/{m['positives']}"
              f" · p50 {m['p50']:.1f} s, p95 {m['p95']:.1f} s · mô hình trả lời câu âm"
              f" {m['neg_answered']}/{m['negatives']}")
    problems = verdict(s)
    if problems:
        raise DemoFailed("; ".join(problems))
    print(f"\n✓ không nguồn bị cấm nào; recall@3 {s['recall']}/{s['positives']} ≥ {RECALL_MIN:.0%}")


# --- F4.3 · Gợi ý giao việc -----------------------------------------------------------------------------------------
# Lịch sử giao việc hư cấu (số ký hiệu đuôi -GVM) làm căn cứ cho tác tử moc-assigner, các ca có nhãn, một mồi hạn chế
GV_PATH = ROOT / "seed" / "giao-viec" / "lich-su.json"
# Ngưỡng của make do-giao-viec: top-1 leave-one-out trên lịch sử (none tính là sai) — chốt lại sau lần đo đầu trên bản
# cài, ghi số đo vào services/svc-workflow/README.md. Căn cứ là văn bản hạn chế thì luôn là lỗi
MIN_TOP1 = 0.6
GV_DOCUMENT = """query ($s: String!) { office_documents(where: {direction: {_eq: "in"}, symbol: {_eq: $s}}) {
  id status restricted } }"""
SUGGESTION = """query ($id: uuid!) { office_assignment_suggestions_by_pk(document_id: $id) {
    status reason department_id confidence share due_days due_on evidence candidates semantic duration_ms created_at }
  office_documents_by_pk(id: $id) { registered_at } }"""
ACCURACY = """{ office_v_assignment_suggestion_accuracy { status confidence suggested decided kept_unit due_compared
  kept_due } }"""
# Căn cứ trỏ tới văn bản hạn chế, trên mọi dòng gợi ý đã lưu (trigger CSDL chặn lúc ghi, gỡ khi bật hạn chế sau)
SEALED_EVIDENCE = """select count(*) from office.assignment_suggestions s
  cross join lateral jsonb_array_elements(s.evidence) e
  join office.documents d on d.tenant_id = s.tenant_id and d.id = (e->>'document_id')::uuid
 where d.restricted"""
# Vào sổ → có dòng gợi ý, trên dòng thật (seed, lịch sử, các lần chạy demo, smoke)
SUGGEST_LATENCY = """select count(*), percentile_disc(0.5) within group (order by x),
       percentile_disc(0.95) within group (order by x)
  from (select extract(epoch from s.created_at - d.registered_at)::numeric(10, 1) as x
          from office.assignment_suggestions s
          join office.documents d on d.tenant_id = s.tenant_id and d.id = s.document_id
         where d.registered_at is not null) t"""
# Khóa diff của dòng sổ assignment.suggested (hợp đồng F4.3 §6): chỉ giá trị vô hướng, không chữ văn bản
SUGGEST_DIFF_KEYS = {"outcome", "outcome_reason", "department_id", "due_days", "confidence", "evidence", "candidates",
                     "semantic", "duration_ms"}
CONFIDENCE = {"high": "cao", "medium": "vừa", "low": "thấp"}
_TOKEN_AT: dict[str, float] = {}


def gv(username: str) -> Session:
    """who() kèm làm mới token: token Keycloak sống 5 phút, lần nạp lịch sử đầu tiên cộng các bước đợi có thể lâu hơn
    (mỗi lần làm mới tốn một mã TOTP của văn thư, lãnh đạo)."""
    session = who(username)
    now = time.monotonic()
    if now - _TOKEN_AT.setdefault(username, now) > 240:
        session.token = user_token(username)
        _TOKEN_AT[username] = now
    return session


def gv_samples() -> dict[str, Any]:
    if not GV_PATH.is_file():
        raise DemoFailed(f"không có {GV_PATH.relative_to(ROOT)} — lịch sử giao việc mẫu đi kèm mã nguồn")
    return json.loads(GV_PATH.read_text(encoding="utf-8"))


def unit_code(department_id: str | None) -> str:
    """Mã đơn vị của seed (ĐT, KTPM…) theo id phòng; phòng lạ thì 8 ký tự đầu của id."""
    from seed_documents import DEPT

    if not department_id:
        return "—"
    return next((code for code, dept in DEPT.items() if dept == department_id), department_id[:8])


def unit_name(department_id: str | None) -> str:
    code = unit_code(department_id)
    return UNIT_NAMES.get(code, code)


def receive_bare(d: dict[str, Any], symbol: str, *, restricted: bool = False) -> str:
    """Văn thư tiếp nhận văn bản không kèm tệp (svc-files đưa trích yếu vào chỉ mục thành đoạn meta) rồi vào sổ → id."""
    from seed_documents import today

    clerk = gv("vanthu")
    doc_id = clerk.gql("mutation ($d: jsonb!) { receiveIncoming(data: $d) { document_id } }", {"d": {
        "type_code": d["type_code"], "symbol": symbol, "issuer_name": d["issuer_name"],
        "issued_on": (today() - timedelta(days=3)).isoformat(), "summary": d["summary"], "urgency": "normal",
        "restricted": restricted, "file_ids": []}})["receiveIncoming"]["document_id"]
    clerk.gql("mutation ($id: uuid!) { registerIncoming(documentId: $id) { register_number } }", {"id": doc_id})
    return doc_id


def direct(doc_id: str, *, due_on: str, department_id: str | None = None, user_id: str | None = None,
           task: str | None = None) -> None:
    """Lãnh đạo khoa giao một phòng chủ trì hoặc giao thẳng một người, không phòng phối hợp."""
    director = gv("truongkhoa")
    task = task or director.wait_task(doc_id, "vbden.chiDao")
    if department_id:
        lead: dict[str, Any] = {"lead_department_id": department_id}
        instruction = f"Giao {unit_name(department_id)} chủ trì thực hiện, báo cáo đúng hạn."
    else:
        lead, instruction = {"lead_user_id": user_id}, "Giao đồng chí chủ trì thực hiện, báo cáo đúng hạn."
    director.complete(task, "direct", {"instruction": instruction, **lead, "supports": [], "due_on": due_on})


def file_away(doc_id: str, task: str | None = None) -> None:
    """Lãnh đạo khoa lưu văn bản, không giao xử lý."""
    director = gv("truongkhoa")
    director.complete(task or director.wait_task(doc_id, "vbden.chiDao"), "file", {"note": "Lưu để biết."})


def load_history(data: dict[str, Any]) -> tuple[dict[str, str], int]:
    """Nạp lịch sử như văn thư và lãnh đạo khoa: mồi hạn chế trước, rồi history, people — tiếp nhận không kèm tệp, vào
    sổ, giao đơn vị chủ trì (lead) hoặc giao thẳng một người (lead_user), hạn = hôm nay + due_in. Văn bản đã có (cùng
    số ký hiệu) thì bỏ qua; lần chạy trước dừng giữa chừng thì làm nốt bước còn thiếu → (id theo số ký hiệu, số mới)."""
    from seed_documents import DEPT, today

    users: dict[str, str] = {}
    ids: dict[str, str] = {}
    created = 0
    for d in [data["bait"], *data["history"], *data["people"]]:
        found = gv("vanthu").gql(GV_DOCUMENT, {"s": d["symbol"]})["office_documents"]
        if found:
            doc_id, status = found[0]["id"], found[0]["status"]
            if status == "received":
                gv("vanthu").gql("mutation ($id: uuid!) { registerIncoming(documentId: $id) { register_number } }",
                                 {"id": doc_id})
        else:
            doc_id, status = receive_bare(d, d["symbol"], restricted=bool(d.get("restricted"))), "registered"
            created += 1
        if status in ("received", "registered"):
            due_on = (today() + timedelta(days=d["due_in"])).isoformat()
            if d.get("lead_user"):
                if d["lead_user"] not in users:
                    users[d["lead_user"]] = gv("truongkhoa").gql(
                        "query ($u: String!) { core_users(where: {username: {_eq: $u}}) { id } }",
                        {"u": d["lead_user"]})["core_users"][0]["id"]
                direct(doc_id, due_on=due_on, user_id=users[d["lead_user"]])
            else:
                direct(doc_id, due_on=due_on, department_id=DEPT[d["lead"]])
        ids[d["symbol"]] = doc_id
    return ids, created


def wait_history_indexed(data: dict[str, Any], timeout_s: float, *, settle: bool) -> float:
    """Đợi vòng nền svc-files đưa trích yếu văn bản lịch sử nạp sau cùng vào chỉ mục đoạn (MOC_ASK_SYNC_INTERVAL_S):
    lãnh đạo khoa hỏi trợ lý đúng trích yếu đó tới khi văn bản có trong nguồn → số giây đã đợi. settle: vừa nạp văn
    bản mới — đoạn có thể vào chỉ mục lúc văn bản còn "registered", tác tử chỉ lấy căn cứ đã giao (in_progress…) nên
    đợi thêm hai vòng đồng bộ để trạng thái trong chỉ mục theo kịp."""
    last = (data["people"] or data["history"])[-1]
    started = time.monotonic()
    while True:
        try:
            sources = ask(gv("truongkhoa"), last["summary"])[0].get("sources") or []
        except HTTPError as exc:            # Meilisearch, Hasura vừa khởi động: đợi tiếp; tắt trợ lý thì dừng
            if exc.status != 503 or error_detail(exc).get("code") == "assistant_disabled":
                raise
            sources = []
        if any(same_symbol(s.get("symbol"), last["symbol"]) for s in sources):
            if settle:
                time.sleep(2 * float(ENV.get("MOC_ASK_SYNC_INTERVAL_S") or 5) + 1)
            return time.monotonic() - started
        if time.monotonic() - started > timeout_s:
            raise DemoFailed(f"sau {timeout_s:.0f} giây chỉ mục đoạn chưa có {last['symbol']} — vòng nền svc-files"
                             " (MOC_ASK_SYNC_INTERVAL_S) có chạy không, trợ lý có bật (MOC_ASK_ENABLED) không?")
        time.sleep(3)


def wait_suggestion(doc_id: str, timeout_s: float) -> tuple[dict | None, dict | None]:
    """Dòng gợi ý của văn bản (lãnh đạo khoa đọc, hỏi lại mỗi giây) tới khi có hoặc hết giờ → (dòng, văn bản)."""
    deadline = time.monotonic() + timeout_s
    while True:
        got = gv("truongkhoa").gql(SUGGESTION, {"id": doc_id})
        row = got["office_assignment_suggestions_by_pk"]
        if row or time.monotonic() >= deadline:
            return row, got["office_documents_by_pk"]
        time.sleep(1)


def wait_suggestions(docs: dict[str, str], timeout_s: float) -> dict[str, dict | None]:
    """Như wait_suggestion cho nhiều văn bản một lúc → dòng gợi ý theo khóa (None: hết giờ vẫn chưa có)."""
    rows: dict[str, dict | None] = dict.fromkeys(docs)
    deadline = time.monotonic() + timeout_s
    while True:
        for key, doc_id in docs.items():
            if rows[key] is None:
                rows[key] = wait_suggestion(doc_id, 0)[0]
        if all(rows.values()) or time.monotonic() >= deadline:
            return rows
        time.sleep(1)


def lag(row: dict[str, Any], doc: dict[str, Any] | None) -> str:
    """created_at của dòng gợi ý − registered_at của văn bản, như "2.4 giây"."""
    try:
        start = datetime.fromisoformat(((doc or {}).get("registered_at") or "").replace("Z", "+00:00"))
        end = datetime.fromisoformat((row.get("created_at") or "").replace("Z", "+00:00"))
    except ValueError:
        return "?"
    return f"{(end - start).total_seconds():.1f} giây"


def evidence_labels(row: dict[str, Any]) -> list[str]:
    """Căn cứ in như giao diện: số ký hiệu (đơn vị đã giao, điểm, số ngày) — lãnh đạo khoa đọc số ký hiệu."""
    evidence = row.get("evidence") or []
    if not evidence:
        return []
    symbols = {d["id"]: d["symbol"] for d in gv("truongkhoa").gql(
        "query ($ids: [uuid!]!) { office_documents(where: {id: {_in: $ids}}) { id symbol } }",
        {"ids": [e["document_id"] for e in evidence]})["office_documents"]}
    return [f"{symbols.get(e['document_id'], '?')} ({unit_code(e.get('department_id'))}, {e.get('score', 0):.2f}"
            + (f", {e['days']} ngày)" if e.get("days") else ")") for e in evidence]


def accuracy() -> dict[str, int]:
    """Tổng các cột đếm của view office.v_assignment_suggestion_accuracy trong đơn vị (lãnh đạo khoa đọc)."""
    rows = gv("truongkhoa").gql(ACCURACY)["office_v_assignment_suggestion_accuracy"]
    return {k: sum(r[k] for r in rows) for k in ("suggested", "decided", "kept_unit", "due_compared", "kept_due")}


def summary_words(text: str) -> list[str]:
    """Từ của trích yếu đủ dài để đối chiếu với diff sổ kiểm toán (bỏ số, từ hai chữ)."""
    return [w for w in re.findall(r"\w+", text) if len(w) >= 3 and not w.isdigit()]


def audit_problems(rows: list[list[str]], docs: dict[str, str], texts: dict[str, list[str]]) -> list[str]:
    """Dòng sổ assignment.suggested (entity_id, actor_id, actor_kind, diff) của các văn bản đã gợi ý: mỗi văn bản đúng
    một dòng của moc-assigner (agent), khóa diff ⊆ SUGGEST_DIFF_KEYS, diff không chứa chữ nào của trích yếu, số ký
    hiệu."""
    problems = []
    seen = Counter(r[0] for r in rows)
    problems += [f"{key}: {seen[doc_id]} dòng (cần 1)" for key, doc_id in docs.items() if seen[doc_id] != 1]
    for entity_id, actor_id, actor_kind, diff in rows:
        if (actor_id, actor_kind) != ("moc-assigner", "agent"):
            problems.append(f"{entity_id}: người thực hiện {actor_id}/{actor_kind}")
        try:
            keys = set(json.loads(diff))
        except ValueError:
            keys = {"?"}
        if keys - SUGGEST_DIFF_KEYS:
            problems.append(f"{entity_id}: khóa lạ {sorted(keys - SUGGEST_DIFF_KEYS)}")
        bare = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "", diff.casefold())
        leaked = [w for w in texts.get(entity_id, []) if w.casefold() in bare]
        if leaked:
            problems.append(f"{entity_id}: diff có chữ của văn bản {leaked}")
    return problems


def giao_viec() -> None:
    from seed_documents import DEPT, today

    print("Màn F4.3 · Gợi ý giao việc — tác tử moc-assigner chạy song song với bước chỉ đạo, tìm các văn bản tương tự"
          " đã giao, gợi ý đơn vị chủ trì và hạn kèm căn cứ; lãnh đạo khoa quyết định")
    data = gv_samples()
    tag = uuid.uuid4().hex[:6].upper()
    bait = data["bait"]

    say(1, "Văn thư nạp lịch sử giao việc seed/giao-viec (không kèm tệp), lãnh đạo khoa giao như lich-su.json")
    ids, created = load_history(data)
    again = "" if created == len(ids) else ", còn lại đã nạp ở lần chạy trước"
    ok(f"{len(ids)} văn bản ({created} mới{again}): {len(data['history'])} giao đơn vị, {len(data['people'])} giao"
       f" thẳng một người, mồi hạn chế {bait['symbol']} — trích yếu gần như trùng cụm học bổng của Tổ Đào tạo nhưng"
       f" giao {UNIT_NAMES[bait['lead']]}")

    say(2, "Đợi svc-files đưa trích yếu vào chỉ mục đoạn (chỉ mục chung với trợ lý hỏi đáp F4.2)")
    took = wait_history_indexed(data, 120, settle=created > 0)
    ok(f"trợ lý tìm ra {(data['people'] or data['history'])[-1]['symbol']} theo trích yếu (đợi {took:.0f} giây)")

    case = next(c for c in data["cases"] if c["key"] == "hoc-bong")
    say(3, f"Văn thư vào sổ “{case['summary']}” — lãnh đạo khoa có việc chỉ đạo ngay, gợi ý tới sau vài giây")
    started = time.monotonic()
    doc_id = receive_bare(case, f"{case['symbol']}-{tag}")
    try:
        task = gv("truongkhoa").wait_task(doc_id, "vbden.chiDao", 5)
    except RuntimeError as exc:
        raise DemoFailed(f"vào sổ xong 5 giây chưa có việc chỉ đạo — nhánh gợi ý chắn bước chỉ đạo? {exc}") from exc
    to_task = time.monotonic() - started
    row, doc = wait_suggestion(doc_id, 30)
    waited = time.monotonic() - started
    if not row or row["status"] != "suggested":
        raise DemoFailed(f"sau {waited:.0f} giây {case['symbol']}-{tag} chưa có gợi ý: {row} — svc-workflow có chạy"
                         " vòng nền MOC_SUGGEST_POLL_INTERVAL_S, svc-files có trả văn bản tương tự không?")
    ok(f"việc chỉ đạo có sau {to_task:.1f} giây (nhánh gợi ý chạy song song, không chắn); dòng gợi ý có sau"
       f" {waited:.1f} giây (vào sổ → dòng gợi ý: {lag(row, doc)})")
    due = (f"hạn đề xuất {row['due_on']} ({row['due_days']} ngày, như các văn bản tương tự)" if row["due_on"]
           else "theo hạn ghi trên văn bản")
    ok(f"đơn vị chủ trì: {unit_name(row['department_id'])} · độ tin cậy {CONFIDENCE.get(row['confidence'])} (tỉ phần"
       f" phiếu {row['share']:.0%}) · {due}")
    search = "từ khóa và theo nghĩa" if row["semantic"] else "từ khóa"
    ok(f"căn cứ: {'; '.join(evidence_labels(row))} — trong {row['candidates']} văn bản tương tự (tìm theo {search},"
       f" {row['duration_ms']} ms)")
    if unit_code(row["department_id"]) != case["expect"]["lead"]:
        print(f"   · khác nhãn {case['expect']['lead']} của lich-su.json — số đo ở make do-giao-viec")

    say(4, "Căn cứ chỉ là văn bản không hạn chế: psql trên mọi dòng office.assignment_suggestions")
    bait_id = str(uuid.UUID(ids[bait["symbol"]]))
    sealed = psql(SEALED_EVIDENCE)
    baited = psql("select count(*) from office.assignment_suggestions"
                  f" where evidence @> '[{{\"document_id\": \"{bait_id}\"}}]'::jsonb")
    if (sealed, baited) != ("0", "0"):
        raise DemoFailed(f"có căn cứ là văn bản hạn chế: {sealed} căn cứ hạn chế, {baited} dòng lấy mồi"
                         f" {bait['symbol']}")
    ok(f"{psql('select count(*) from office.assignment_suggestions')} dòng gợi ý, 0 căn cứ là văn bản hạn chế; mồi"
       f" {bait['symbol']} không là căn cứ của dòng nào — văn bản hạn chế không vào chỉ mục, trigger CSDL chặn thêm")

    say(5, "Lãnh đạo khoa bấm “Dùng gợi ý” (đơn vị + hạn) rồi giao — view đo tỉ lệ giữ gợi ý tăng đúng 1")
    before = accuracy()
    direct(doc_id, task=task, department_id=row["department_id"],
           due_on=row["due_on"] or (today() + timedelta(days=10)).isoformat())
    after = accuracy()
    delta = {k: after[k] - before[k] for k in after}
    want = {"decided": 1, "kept_unit": 1, **({"kept_due": 1} if row["due_on"] else {})}
    if any(delta[k] != v for k, v in want.items()):
        raise DemoFailed(f"view office.v_assignment_suggestion_accuracy chưa đếm đúng lần giữ gợi ý: {delta}")
    ok(f"decided +1, kept_unit +1{', kept_due +1' if row['due_on'] else ''} (so trước/sau: seed, lịch sử cũng có gợi"
       f" ý) — tổng trong đơn vị: giữ đơn vị {after['kept_unit']}/{after['decided']}, giữ hạn"
       f" {after['kept_due']}/{after['due_compared']}")

    say(6, "Các ca có nhãn còn lại — văn thư vào sổ thêm văn bản hạn chế R trước các ca (kiểm ở bước 8)")
    sealed_id = receive_bare(bait, f"{bait['symbol']}-{tag}", restricted=True)
    others = [c for c in data["cases"] if c["key"] != "hoc-bong"]
    docs = {c["key"]: receive_bare(c, f"{c['symbol']}-{tag}") for c in others}
    rows = wait_suggestions(docs, 30)
    last_row = time.monotonic()
    print("\n   | ca | văn bản | kỳ vọng | gợi ý | tin cậy | hạn | căn cứ |\n   |---|---|---|---|---|---|---|")
    for c in others:
        r = rows[c["key"]] or {"status": "chưa có", "reason": None}
        want_unit = c["expect"].get("lead") or c["expect"].get("status")
        got = unit_code(r.get("department_id")) if r["status"] == "suggested" else f"{r['status']}/{r.get('reason')}"
        hit = got == want_unit or (want_unit == "none" and r["status"] == "none")
        print(f"   | {c['key']} | {c['symbol']}-{tag} | {want_unit} | {'✓' if hit else '·'} {got} |"
              f" {CONFIDENCE.get(r.get('confidence'), '—')} | {r.get('due_days') or '—'} |"
              f" {len(r.get('evidence') or [])} |")
    missed = [c["key"] for c in others if c["expect"].get("lead") and (rows[c["key"]] or {}).get("department_id")
              != DEPT[c["expect"]["lead"]]]
    if missed:
        print(f"   · lệch nhãn: {', '.join(missed)} — chỉ cảnh báo, số đánh giá ở make do-giao-viec")
    for c in others:
        if c["expect"].get("lead"):
            r = rows[c["key"]] or {}
            direct(docs[c["key"]], department_id=DEPT[c["expect"]["lead"]],
                   due_on=r.get("due_on") or (today() + timedelta(days=10)).isoformat())
    ok("lãnh đạo khoa giao các ca theo nhãn — thành lịch sử cho lần sau, tác tử tốt dần khi có thêm dữ liệu")

    unrelated = next(c for c in others if c["expect"].get("status") == "none")
    say(7, f"Ca không liên quan “{unrelated['summary']}” → không gợi ý")
    r = rows[unrelated["key"]]
    if not r or r["status"] != "none":
        raise DemoFailed(f"ca không liên quan lẽ ra không có gợi ý: {r}")
    ok(f"none/{r['reason']} — không đủ văn bản tương tự (ngưỡng MOC_SUGGEST_MIN_SCORE) thì tác tử không đoán bừa,"
       " giao diện chỉ hiện một dòng mờ")
    file_away(docs[unrelated["key"]])

    say(8, f"Văn bản hạn chế R {bait['symbol']}-{tag} (trích yếu như cụm học bổng): không gợi ý, không dòng sổ")
    time.sleep(max(0.0, 3 - (time.monotonic() - last_row)))
    found = psql(f"select (select count(*) from office.assignment_suggestions where document_id = '{sealed_id}'),"
                 f" (select count(*) from core.audit_log where action = 'assignment.suggested'"
                 f" and entity_id = '{sealed_id}')")
    if found != "0|0":
        raise DemoFailed(f"văn bản hạn chế có dòng gợi ý | dòng sổ: {found}")
    ok("psql: 0 dòng gợi ý, 0 dòng sổ assignment.suggested — tác tử bỏ qua văn bản hạn chế, trigger CSDL chặn thêm")
    file_away(sealed_id)

    say(9, "psql: mỗi gợi ý một dòng sổ của tác tử, không có chữ văn bản")
    checked = {"hoc-bong": doc_id, **docs}
    texts = {doc_id: [*summary_words(case["summary"]), f"{case['symbol']}-{tag}"]}
    texts.update({docs[c["key"]]: [*summary_words(c["summary"]), f"{c['symbol']}-{tag}"] for c in others})
    audit = [line.split("|", 3) for line in psql(
        "select entity_id, actor_id, actor_kind, diff::text from core.audit_log where action = 'assignment.suggested'"
        f" and entity_id in ({', '.join(repr(str(uuid.UUID(d))) for d in checked.values())}) order by id").splitlines()]
    problems = audit_problems(audit, checked, texts)
    if problems:
        raise DemoFailed("dòng sổ assignment.suggested chưa đúng: " + "; ".join(problems))
    ok(f"{len(audit)} dòng assignment.suggested · người thực hiện moc-assigner (agent) · khóa diff thuộc"
       f" {{{', '.join(sorted(SUGGEST_DIFF_KEYS))}}}")
    ok("diff::text không có từ nào của trích yếu, không số ký hiệu — chỉ đơn vị, độ tin cậy, số đếm; căn cứ nằm ở"
       " bảng gợi ý, chỉ lãnh đạo khoa đọc")

    say(10, "svc-files tạm dừng: văn bản vẫn tới bước chỉ đạo ngay, tác tử ghi failed rồi thôi (không thử lại)")
    stopped, probe_task = False, None
    try:
        stopped = True
        compose("stop", "svc-files")
        started = time.monotonic()
        probe = receive_bare({"type_code": "CV", "issuer_name": "Phòng Công tác sinh viên",
                              "summary": f"Về việc thử gợi ý giao việc khi svc-files tạm dừng (thử {tag})"},
                             f"309/CTSV-GVM-{tag}")
        try:
            probe_task = gv("truongkhoa").wait_task(probe, "vbden.chiDao", 5)
        except RuntimeError as exc:
            raise DemoFailed(f"svc-files tắt, vào sổ xong 5 giây chưa có việc chỉ đạo: {exc}") from exc
        to_task = time.monotonic() - started
        r, _ = wait_suggestion(probe, 20)
        if not r or r["status"] != "failed":
            raise DemoFailed(f"svc-files tắt mà sau 20 giây dòng gợi ý chưa là failed: {r}")
        ok(f"svc-files dừng; việc chỉ đạo có sau {to_task:.1f} giây; gợi ý failed/{r['reason']} sau"
           f" {time.monotonic() - started:.1f} giây — lãnh đạo giao như thường lệ")
    finally:
        if stopped:
            took = restart("svc-files")
            print(f"   ✓ svc-files chạy lại, sẵn sàng sau {took:.0f} giây")
    if probe_task:
        file_away(probe, probe_task)

    print(f"\nXem trên giao diện (truongkhoa): {PUBLIC_URL}/van-ban/{doc_id} — tab Lịch sử có dòng “Tác tử gợi ý giao"
          " việc”; văn bản đến mới vào sổ có khối “Gợi ý giao việc” ở đầu form chỉ đạo")


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Số đo leave-one-out trên các dòng evaluate (hợp đồng F4.3 §5.2) có đáp án actual.department_id: độ phủ; top-1
    (none, failed là sai), top-2, top-3 (theo ranking); đúng theo độ tin cậy; sai số hạn (MAE, lệch ≤ 1 ngày); p50/p95
    duration_ms; gốc so sánh "luôn đoán đơn vị đông nhất"."""
    labelled = [r for r in rows if (r.get("actual") or {}).get("department_id")]
    total = len(labelled)

    def right(r: dict[str, Any], k: int) -> bool:
        actual = r["actual"]["department_id"]
        top1 = r.get("status") == "suggested" and r.get("department_id") == actual
        return top1 or (k > 1 and actual in (r.get("ranking") or [])[:k])

    suggested = [r for r in labelled if r.get("status") == "suggested"]
    by_confidence = {c: {"n": sum(r.get("confidence") == c for r in suggested),
                         "correct": sum(r.get("confidence") == c and right(r, 1) for r in suggested)}
                     for c in ("high", "medium", "low")}
    errors = [abs(r["due_days"] - r["actual"]["days"]) for r in suggested
              if isinstance(r.get("due_days"), int) and isinstance(r["actual"].get("days"), int)]
    ms = [r["duration_ms"] for r in rows if isinstance(r.get("duration_ms"), int)]
    units = Counter(r["actual"]["department_id"] for r in labelled)
    return {
        "rows": len(rows), "total": total, "suggested": len(suggested),
        "coverage": len(suggested) / total if total else 0.0,
        "top1": sum(right(r, 1) for r in labelled), "top2": sum(right(r, 2) for r in labelled),
        "top3": sum(right(r, 3) for r in labelled),
        "top1_rate": sum(right(r, 1) for r in labelled) / total if total else 0.0,
        "by_confidence": by_confidence,
        "outcomes": dict(Counter(f"{r.get('status')}/{r.get('reason')}" for r in labelled
                                 if r.get("status") != "suggested")),
        "due_compared": len(errors), "due_mae": sum(errors) / len(errors) if errors else None,
        "due_within1": sum(e <= 1 for e in errors),
        "p50_ms": percentile(ms, 50), "p95_ms": percentile(ms, 95),
        "semantic": sum(bool(r.get("semantic")) for r in rows),
        "units": len(units), "majority": max(units.values()) / total if total else 0.0,
    }


def gv_verdict(m: dict[str, Any], leaks: list[str]) -> list[str]:
    """Lý do thoát 1 (rỗng: đạt): mọi căn cứ là văn bản hạn chế; top-1 dưới MIN_TOP1; không đo được dòng nào."""
    problems = [f"căn cứ là văn bản hạn chế — {leak}" for leak in leaks]
    if not m["total"]:
        problems.append("evaluate không trả dòng nào có đáp án")
    elif m["top1_rate"] < MIN_TOP1:
        problems.append(f"top-1 {m['top1']}/{m['total']} ({m['top1_rate']:.0%}) dưới ngưỡng {MIN_TOP1:.0%}")
    return problems


def gv_tenant() -> str:
    return gv("truongkhoa").gql("{ core_tenants { id } }")["core_tenants"][0]["id"]


def run_evaluate(tenant: str, documents: list[str]) -> list[dict[str, Any]]:
    """Leave-one-out trong container svc-workflow: mỗi văn bản được gợi ý như vừa vào sổ (svc-files đã loại chính nó),
    so với đơn vị và hạn đã giao thật; không ghi CSDL, sổ, không in chữ văn bản (hợp đồng F4.3 §5.2)."""
    body = json.dumps({"tenant_id": tenant, "documents": documents}).encode()
    try:
        out = compose("exec", "-T", "svc-workflow", "python", "-m", "svc_workflow.advisor", "evaluate", stdin=body)
    except subprocess.CalledProcessError as exc:
        tail = (exc.stderr or b"").decode(errors="replace").strip().splitlines()[-5:]
        raise DemoFailed(f"evaluate trong svc-workflow lỗi (mã {exc.returncode}): {' | '.join(tail)}") from exc
    text = out.decode().strip()
    for candidate in (text, (text.splitlines() or [""])[-1]):
        try:
            return json.loads(candidate)["rows"]
        except (ValueError, KeyError, TypeError):
            continue
    raise DemoFailed(f"evaluate không trả JSON {{\"rows\": …}}: {text[-300:]}")


def restricted_among(ids: list[str]) -> set[str]:
    """Các id là văn bản hạn chế (psql, không lọc quyền)."""
    if not ids:
        return set()
    try:
        listed = ", ".join(f"'{uuid.UUID(i)}'" for i in ids)
    except (ValueError, TypeError, AttributeError) as exc:
        raise DemoFailed(f"căn cứ trong kết quả evaluate không phải id văn bản: {exc}") from exc
    return set(psql(f"select id from office.documents where restricted and id in ({listed})").split())


def evidence_ids(row: dict[str, Any]) -> list[str]:
    return [e["document_id"] if isinstance(e, dict) else e for e in row.get("evidence") or []]


def evidence_leaks(rows: list[dict[str, Any]], symbols: dict[str, str], bait_id: str) -> list[str]:
    """Căn cứ của các dòng evaluate trỏ tới văn bản hạn chế (cả mồi) → nhãn "văn bản → căn cứ"."""
    sealed = restricted_among(sorted({e for r in rows for e in evidence_ids(r)})) | {bait_id}
    return [f"{symbols.get(r.get('document_id'), r.get('document_id'))} → {e}" for r in rows for e in evidence_ids(r)
            if e in sealed]


def stored_leaks() -> int:
    return int(psql(SEALED_EVIDENCE) or 0)


def valid_units() -> int:
    """Số đơn vị có lãnh đạo phòng đang bật — đơn vị duy nhất tác tử được gợi ý (svc-workflow từ chối giao nơi khác)."""
    rows = gv("truongkhoa").gql("""{ core_users(where: {role: {_eq: "manager"}, enabled: {_eq: true},
        department_id: {_is_null: false}}) { department_id } }""")["core_users"]
    return len({r["department_id"] for r in rows})


def suggestion_latency() -> tuple[int, float | None, float | None]:
    """(số dòng, p50, p95) giây từ lúc vào sổ tới lúc có dòng gợi ý, trên mọi dòng thật trong CSDL."""
    n, p50, p95 = (psql(SUGGEST_LATENCY).split("|") + ["", "", ""])[:3]
    return int(n or 0), float(p50) if p50 else None, float(p95) if p95 else None


def gv_table(rows: list[dict[str, Any]], symbols: dict[str, str]) -> str:
    """Bảng markdown từng văn bản: đơn vị đã giao, gợi ý, tin cậy, xếp hạng, hạn gợi ý / thật, số căn cứ, thời gian."""
    out = ["| văn bản | đã giao | gợi ý | tin cậy | xếp hạng | hạn gợi ý / thật | căn cứ | ms |",
           "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        actual = r.get("actual") or {}
        if r.get("status") == "suggested":
            got = ("✓ " if r.get("department_id") == actual.get("department_id") else "✗ ") + unit_code(
                r.get("department_id"))
        else:
            got = f"✗ {r.get('status')}/{r.get('reason')}"
        due = f"{r.get('due_days') or '—'} / {actual.get('days') or '—'}"
        name = symbols.get(r.get("document_id"), r.get("document_id"))
        ranking = ", ".join(unit_code(u) for u in r.get("ranking") or []) or "—"
        out.append(f"| {name} | {unit_code(actual.get('department_id'))} | {got} |"
                   f" {CONFIDENCE.get(r.get('confidence'), '—')} | {ranking} | {due} | {len(evidence_ids(r))} |"
                   f" {r.get('duration_ms', '—')} |")
    return "\n".join(out)


def do_giao_viec() -> None:
    print("Đo F4.3 · Tác tử gợi ý giao việc, leave-one-out trên lịch sử seed/giao-viec: mỗi văn bản được gợi ý như vừa"
          " vào sổ, các văn bản còn lại làm căn cứ, so với đơn vị chủ trì và hạn đã giao thật")
    data = gv_samples()
    ids, created = load_history(data)
    took = wait_history_indexed(data, 120, settle=created > 0)
    print(f"   lịch sử: {len(ids)} văn bản ({created} mới), chỉ mục sẵn sàng sau {took:.0f} giây")
    measured = {ids[d["symbol"]]: d["symbol"] for d in [*data["history"], *data["people"]]}
    rows = run_evaluate(gv_tenant(), list(measured))
    units = valid_units()
    m = metrics(rows)
    print("\n" + gv_table(rows, measured))
    print(f"\ntop-1: {m['top1']}/{m['total']} ({m['top1_rate']:.0%}; none, failed tính là sai) · độ phủ"
          f" {m['suggested']}/{m['total']} ({m['coverage']:.0%}) · gốc so sánh “luôn đoán đơn vị đông nhất”:"
          f" {m['majority']:.0%}")
    print(f"top-2: {m['top2']}/{m['total']}, top-3: {m['top3']}/{m['total']} — vô nghĩa khi số đơn vị hợp lệ ≤ k: hiện"
          f" có {units} đơn vị có lãnh đạo phòng, đáp án thuộc {m['units']} đơn vị")
    print("đúng theo độ tin cậy: " + ", ".join(f"{CONFIDENCE[c]} {v['correct']}/{v['n']}"
                                               for c, v in m["by_confidence"].items())
          + (" · không gợi ý: " + ", ".join(f"{k} {v}" for k, v in sorted(m["outcomes"].items()))
             if m["outcomes"] else ""))
    if m["due_compared"]:
        print(f"hạn: so được {m['due_compared']} văn bản, sai số tuyệt đối trung bình {m['due_mae']:.1f} ngày, lệch"
              f" ≤ 1 ngày {m['due_within1']}/{m['due_compared']}")
    print(f"thời gian một lần gợi ý (svc-files + bỏ phiếu): p50 {m['p50_ms']} ms, p95 {m['p95_ms']} ms · tìm theo"
          f" nghĩa {m['semantic']}/{m['rows']}")
    n, p50, p95 = suggestion_latency()
    if n:
        print(f"dòng thật (vào sổ → có dòng gợi ý): p50 {p50} s, p95 {p95} s trên {n} văn bản")
    leaks = evidence_leaks(rows, measured, str(uuid.UUID(ids[data["bait"]["symbol"]])))
    stored = stored_leaks()
    if stored:
        leaks.append(f"{stored} căn cứ hạn chế trong office.assignment_suggestions")
    print(f"an toàn: {len(leaks)} căn cứ là văn bản hạn chế (kết quả đo + bảng gợi ý; mồi {data['bait']['symbol']}"
          " tính là hạn chế)")
    problems = gv_verdict(m, leaks)
    if problems:
        raise DemoFailed("; ".join(problems))
    print(f"\n✓ không căn cứ nào là văn bản hạn chế; top-1 {m['top1']}/{m['total']} ≥ {MIN_TOP1:.0%}")


# --- F4.5 · Ký số văn bản đi (PKI nội bộ trong két, chỉ minh họa) -----------------------------------------------------
# Chứng thư PEM ở stdin, đọc trong svc-files (cryptography có sẵn): CN, O, hạn, cỡ khóa, có tự ký không
CA_INFO = """import sys
from cryptography import x509
from cryptography.x509.oid import NameOID
c = x509.load_pem_x509_certificate(sys.stdin.buffer.read())
for oid in (NameOID.COMMON_NAME, NameOID.ORGANIZATION_NAME):
    print(c.subject.get_attributes_for_oid(oid)[0].value)
print(c.not_valid_after_utc.date().isoformat())
print(c.public_key().key_size, c.subject == c.issuer)
"""
SIGNED_DOC = """query ($id: uuid!) { office_documents_by_pk(id: $id) { status symbol verify_code content_sha256
  files(where: {role: {_eq: "issued"}}) { file_id } } }"""
# Dòng chữ ký của bản phát hành — bảng core.file_signatures không vai trò nào đọc được, chỉ psql
SIGNATURE_ROW = """select s.key_name, s.key_version, s.serial, s.not_after::date from core.file_signatures s
  join office.document_files df on df.file_id = s.file_id and df.role = 'issued' where df.document_id = '{doc}'"""
RESTRICTED_SIGNED = """select count(*) from core.file_signatures s join office.document_files df on df.file_id = s.file_id
  join office.documents d on d.id = df.document_id where d.restricted"""
# Văn bản phát hành không có chữ ký (trước khi bật ký số, ký số tắt hay ký lỗi), còn ở kho nóng, không hạn chế — mới nhất
UNSIGNED_ISSUED = """select d.verify_code, d.symbol from office.documents d
  join office.document_files df on df.document_id = d.id and df.role = 'issued'
  left join core.file_signatures s on s.file_id = df.file_id
 where d.direction = 'out' and d.status = 'issued' and not d.restricted and s.file_id is null
 order by d.issued_on desc, d.symbol desc limit 1"""


def pem_fingerprint(pem: str) -> str:
    """Vân tay SHA-256 của chứng thư đầu tiên trong PEM (băm phần DER, tức base64 giữa hai dòng BEGIN/END), dạng
    AB:CD:… như trình duyệt, trình đọc PDF hiện — để đối chiếu khi nhập CA vào trình đọc PDF."""
    lines = [line.strip() for line in pem.strip().splitlines()]
    start = lines.index("-----BEGIN CERTIFICATE-----") + 1
    der = base64.b64decode("".join(lines[start:lines.index("-----END CERTIFICATE-----", start)]))
    digest = hashlib.sha256(der).hexdigest().upper()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


def local_time(iso: str) -> str:
    """Giờ ISO 8601 (có "Z" hay độ lệch) → giờ máy chạy demo, dạng 14:05:09 23/10/2026."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().strftime("%H:%M:%S %d/%m/%Y")


def issue_outgoing(staff: Session, manager: Session, director: Session, clerk: Session, draft: dict[str, Any], *,
                   public: bool, request_id: str | None = None) -> tuple[str, float]:
    """Chuyên viên soạn → trình → tổ trưởng duyệt → lãnh đạo khoa ký duyệt → văn thư phát hành → (id văn bản, số giây
    của riêng bước phát hành: cấp số, dựng PDF, ký, quét, lưu). ``request_id``: bước phát hành gửi kèm X-Request-Id
    tự đặt (màn log tập trung), APISIX phải trả lại đúng mã đó."""
    doc_id = staff.gql(DRAFT, {"o": draft})["insert_office_documents_one"]["id"]
    signer = staff.gql('{ core_users(where: {username: {_eq: "truongkhoa"}}) { id } }')["core_users"][0]["id"]
    staff.gql(SUBMIT, {"d": doc_id, "s": signer})
    manager.complete(manager.wait_task(doc_id, "vbdi.duyetPhong"), "approve", {})
    director.complete(director.wait_task(doc_id, "vbdi.duyetDonVi"), "approve", {})
    task = clerk.wait_task(doc_id, "vbdi.phatHanh")
    started = time.monotonic()
    if request_id is None:
        clerk.complete(task, "issue", {"is_public": public})
        return doc_id, time.monotonic() - started
    variables = {"t": task, "o": "issue", "d": {"is_public": public}}
    data, headers = call_json("POST", f"{PUBLIC_URL}/v1/graphql", {"query": COMPLETE_TASK, "variables": variables},
                              headers={**clerk.auth, "X-Request-Id": request_id})
    if data.get("errors"):
        raise RuntimeError(f"{clerk.username}: {data['errors'][0].get('message')}")
    echoed = {k.lower(): v for k, v in headers.items()}.get("x-request-id")
    if echoed != request_id:
        raise DemoFailed(f"APISIX trả X-Request-Id {echoed!r}, không phải mã đã gửi {request_id!r} (plugin request-id)")
    return doc_id, time.monotonic() - started


def cli_lines(lines: list[str]) -> None:
    for line in lines:
        print(f"   │ {line}")


def ky_so() -> None:
    # nạp trong hàm: test của các màn khác thay moc_env bằng bản giả không có các tên này
    from moc_env import INCREMENTAL_EDIT, byte_range_end, flip_in_signed_stream, signature_cli, vault_ca_pem

    print("Màn F4.5 · Ký số văn bản đi — CHỈ MINH HỌA: CA nội bộ trong két OpenBao, không có giá trị pháp lý như chữ ký"
          " số công cộng. Bản phát hành ký PAdES bằng khóa của đơn vị nằm trong két; ai cũng kiểm được người ký và biết"
          " tệp có bị sửa sau khi ký không")
    tag = uuid.uuid4().hex[:6].upper()
    staff, manager, director, clerk = (Session(u) for u in ("chuyenviendt", "totruongdt", "truongkhoa", "vanthu"))

    say(1, "CA nội bộ trong két OpenBao — chứng thư mẫu, không thuộc danh sách tin cậy công cộng nào")
    pem = vault_ca_pem()
    if pem is None:
        raise DemoFailed("két chưa có CA nội bộ (pki/ca/pem): két khởi tạo trước F4.5 nên ký số tự tắt, mọi thứ khác"
                         " vẫn chạy như cũ — xem docs/van-hanh.md mục Két bí mật")
    info = compose("exec", "-T", "svc-files", "python", "-c", CA_INFO, stdin=pem.encode()).decode().strip()
    cn, org, expires, size = info.splitlines()
    bits, self_signed = size.split()
    if "MẪU" not in cn or "chỉ minh họa" not in cn or self_signed != "True":
        raise DemoFailed(f"CA của két không phải CA gốc mẫu, chỉ minh họa: {cn} / {org}")
    ok(f"CN \"{cn}\" · O \"{org}\" · CA gốc tự ký, RSA {bits} bit, hạn tới {expires}")
    ok(f"vân tay SHA-256 {pem_fingerprint(pem)}")
    ok("đọc pki/ca/pem không cần token: chỉ là chứng thư công khai; khóa riêng của CA sinh ngay trong két (internal)")

    say(2, "Chuyên viên soạn công văn → tổ trưởng duyệt → lãnh đạo khoa ký duyệt → văn thư phát hành (công khai)")
    tenant = staff.gql("{ core_tenants { id } }")["core_tenants"][0]["id"]
    first = psql(f"select count(*) from core.file_signatures where tenant_id = '{tenant}'") == "0"
    doc_id, took = issue_outgoing(staff, manager, director, clerk, {
        "type_code": "CV", "recipients": ["Phòng Đào tạo"],
        "summary": f"Về việc báo cáo kết quả tự đánh giá chương trình đào tạo ngành Kỹ thuật phần mềm (demo {tag})",
        "body": "Khoa Công nghệ thông tin báo cáo kết quả tự đánh giá chương trình đào tạo ngành Kỹ thuật phần mềm.\n"
                "Đề nghị Phòng Đào tạo tổng hợp, báo cáo Ban Giám hiệu.",
    }, public=True)
    doc = clerk.gql(SIGNED_DOC, {"id": doc_id})["office_documents_by_pk"]
    if doc["status"] != "issued" or not doc["files"]:
        raise DemoFailed(f"công văn chưa phát hành: {doc}")
    ok(f"{doc['symbol']} phát hành trong {took:.1f} giây: cấp số → dựng PDF → ký bằng khóa của đơn vị trong két → tự"
       " kiểm chữ ký → băm SHA-256 → ClamAV → lưu")
    if first:
        ok("lần ký đầu của đơn vị: két sinh khóa RSA-3072 trong Transit, CA nội bộ cấp chứng thư cho khóa đó — các lần"
           " sau dùng lại")

    say(3, "Bản phát hành mang chữ ký PAdES; cổng xác thực (không đăng nhập) cho biết ai ký, CA nào cấp")
    _, _, pdf = request("GET", f"{PUBLIC_URL}/api/files/{doc['files'][0]['file_id']}", headers=clerk.auth)
    sha = hashlib.sha256(pdf).hexdigest()
    if hexed(doc["content_sha256"]) != sha:
        raise DemoFailed(f"băm tệp tải về {sha} khác content_sha256 {doc['content_sha256']}")
    if b"/ByteRange" not in pdf or b"/ETSI.CAdES.detached" not in pdf or byte_range_end(pdf) != len(pdf):
        raise DemoFailed("bản phát hành không có chữ ký PAdES phủ toàn bộ tệp (/ByteRange, /ETSI.CAdES.detached) — xem"
                         " nhật ký svc-files: office.document.sign_failed, office.signing.disabled")
    ok(f"SHA-256 {sha[:16]}… = content_sha256 trong CSDL: băm, mã QR, sổ kiểm toán đều theo bản ĐÃ ký; tệp có"
       " /ByteRange, /SubFilter /ETSI.CAdES.detached, chữ ký phủ tới byte cuối")
    found, _ = call_json("GET", f"{PUBLIC_URL}/api/verify/{doc['verify_code']}")
    sig = (found.get("document") or {}).get("signature") or {}
    if found.get("result") != "valid" or sig.get("level") != "PAdES-B-B" or sig.get("illustrative") is not True:
        raise DemoFailed(f"cổng xác thực chưa trả khối chữ ký: {found}")
    ok(f"/api/verify/{doc['verify_code']} → signature: chuẩn {sig['level']} · ký bởi \"{sig['signer']}\" · CA"
       f" \"{sig['ca']}\"")
    ok(f"số sê-ri chứng thư {sig['serial']} · ký lúc {local_time(sig['signed_at'])} (giờ tự ghi trong chữ ký, không có"
       " dấu thời gian tin cậy) · illustrative: true")
    row = psql(SIGNATURE_ROW.format(doc=doc_id)).split("|")
    if len(row) != 4 or row[0] != f"moc-ky-so-{tenant}" or row[2] != sig["serial"]:
        raise DemoFailed(f"core.file_signatures không khớp cổng xác thực: {row}")
    ok(f"psql core.file_signatures: khóa Transit {row[0]} phiên bản {row[1]}, chứng thư hạn tới {row[3]} — CSDL chỉ giữ"
       " vân tay chứng thư, chứng thư nằm trong PDF")

    say(4, "Kiểm bằng pyHanko trong svc-files (python -m svc_files.signing verify) — chỉ tin CA của két")
    code, lines = signature_cli(pdf)
    cli_lines(lines)
    if code != 0 or not lines or not lines[0].startswith("Chữ ký hợp lệ"):
        raise DemoFailed(f"CLI không xác nhận chữ ký của bản phát hành (thoát {code})")
    ok("thoát 0: băm phần đã ký khớp, chữ ký RSA đúng, chuỗi chứng thư về CA nội bộ, chữ ký chứng nhận không cho sửa")

    say(5, "Sửa sau khi ký: thêm một chú thích vào bản phát hành, ghi nối sau phần đã ký như trình đọc PDF lưu ghi chú")
    edited = compose("exec", "-T", "svc-files", "python", "-c", INCREMENTAL_EDIT, stdin=pdf)
    end = byte_range_end(edited)
    if not edited.startswith(pdf) or end != len(pdf):
        raise DemoFailed(f"lớp sửa không ghi nối sau bản đã ký (cuối /ByteRange {end}, bản ký {len(pdf)} byte)")
    code, lines = signature_cli(edited)
    if code != 1 or not lines or not lines[0].startswith("Văn bản đã bị sửa sau khi ký"):
        cli_lines(lines)
        raise DemoFailed(f"CLI chưa báo sửa sau khi ký (thoát {code})")
    ok(f"CLI thoát 1: {lines[0]}")
    whole, _ = call_json("GET", f"{PUBLIC_URL}/api/verify?sha256={hashlib.sha256(edited).hexdigest()}")
    part, _ = call_json("GET", f"{PUBLIC_URL}/api/verify?sha256={hashlib.sha256(edited[:end]).hexdigest()}")
    if whole.get("result") != "not_found" or part.get("result") != "valid" \
            or (part.get("document") or {}).get("symbol") != doc["symbol"]:
        raise DemoFailed(f"cổng xác thực: cả tệp {whole.get('result')}, phần đã ký {part.get('result')}")
    ok(f"cổng xác thực: băm cả tệp → không khớp; băm phần đầu tệp tới cuối /ByteRange ({end} byte) → đúng"
       f" {doc['symbol']} — phần đã ký còn nguyên, {len(edited) - end} byte thêm vào không do đơn vị ký")

    say(6, "Lật một bit trong phần đã ký (dữ liệu một stream của tệp)")
    flipped = flip_in_signed_stream(pdf)
    code, lines = signature_cli(flipped)
    if code != 1 or not lines or not lines[0].startswith("Chữ ký không khớp nội dung"):
        cli_lines(lines)
        raise DemoFailed(f"CLI chưa báo chữ ký không khớp nội dung (thoát {code})")
    found, _ = call_json("GET", f"{PUBLIC_URL}/api/verify?sha256={hashlib.sha256(flipped).hexdigest()}")
    if found.get("result") != "not_found":
        raise DemoFailed(f"tệp đã lật một bit vẫn khớp ở cổng xác thực: {found}")
    ok(f"CLI thoát 1: {lines[0]} — cổng xác thực: không khớp")

    say(7, "Văn bản hạn chế không được ký")
    secret_id, _ = issue_outgoing(staff, manager, director, clerk, {
        "type_code": "CV", "recipients": ["Phòng Tổ chức cán bộ"], "restricted": True,
        "summary": f"Về việc danh sách đề nghị nâng lương trước hạn năm 2026 (demo {tag})",
        "body": "Khoa Công nghệ thông tin gửi danh sách đề nghị nâng lương trước hạn năm 2026 (kèm theo).",
    }, public=False)
    secret = clerk.gql(SIGNED_DOC, {"id": secret_id})["office_documents_by_pk"]
    if secret["status"] != "issued" or not secret["files"]:
        raise DemoFailed(f"văn bản hạn chế chưa phát hành: {secret}")
    file_id = secret["files"][0]["file_id"]
    state = (psql(f"select wrapped_dek is not null from core.files where id = '{file_id}'"),
             psql(f"select count(*) from core.file_signatures where file_id = '{file_id}'"), psql(RESTRICTED_SIGNED))
    if state != ("t", "0", "0"):
        raise DemoFailed(f"văn bản hạn chế: mã hóa {state[0]}, chữ ký của nó {state[1]}, chữ ký gắn văn bản hạn chế"
                         f" {state[2]}")
    check, _ = call_json("GET", f"{PUBLIC_URL}/api/verify/{secret['verify_code']}")
    if check.get("result") != "valid" or (check.get("document") or {}).get("signature") is not None:
        raise DemoFailed(f"cổng xác thực trả về văn bản hạn chế chưa đúng: {check}")
    ok(f"{secret['symbol']} (hạn chế) phát hành: tệp mã hóa trong kho, không có chữ ký — mỗi lần mở là một bản viết lại"
       " có dấu tên người xem nên chữ ký sẽ hỏng ngay; tra mã ở cổng xác thực → khớp, signature: null")
    ok("psql: 0 chữ ký gắn với văn bản hạn chế trên cả hệ thống")

    say(8, "Văn bản phát hành không có chữ ký số (trước khi bật ký số) vẫn xác thực như cũ")
    old = psql(UNSIGNED_ISSUED)
    if not old:
        print("   – bỏ qua: chưa có văn bản phát hành nào không có chữ ký (két có PKI nội bộ ngay từ khi cài)")
    else:
        code_old, symbol_old = old.split("|")
        found, _ = call_json("GET", f"{PUBLIC_URL}/api/verify/{code_old}")
        if found.get("result") != "valid" or (found.get("document") or {}).get("signature") is not None:
            raise DemoFailed(f"văn bản cũ {symbol_old} không còn xác thực như cũ: {found}")
        ok(f"{symbol_old}: tra mã → khớp, signature: null — không ký lại văn bản cũ (băm, mã QR, sổ kiểm toán đã cố"
           " định); trang xác thực ghi không có chữ ký số")

    print(f"\nXem trên giao diện (người ngoài, không đăng nhập): {PUBLIC_URL}/xac-thuc/{doc['verify_code']} — khối \"Chữ"
          f" ký số (minh họa)\"; bản PDF (văn thư): {PUBLIC_URL}/van-ban/{doc_id} — trình đọc PDF báo chữ ký chưa tin"
          " cậy cho tới khi nhập CA nội bộ (docs/demo-script.md)")


# --- F4.4 · Che thông tin cá nhân ----------------------------------------------------------------------------------
# Giá trị giả lập: hợp lệ về định dạng nên có thể trùng số thật — số ví dụ phổ biến, CCCD đuôi 0000xx, email
# @example.com (RFC 2606). Cùng bộ với services/svc-files/tests/test_pii.py; scripts/tests/test_che_pii.py dùng lại
PII_DEMO = {"cccd": "001205000017", "phone": "0912 345 678", "landline": "(024) 3000 0000",
            "email": "nguyenvanb@example.com", "account": "0011 0041 23456"}
PII_QUESTION = "Số điện thoại liên hệ của người làm đơn đề nghị cấp bản sao bằng tốt nghiệp là gì?"
# Lá đơn tiếp nhận một lần cho mỗi đơn vị (chạy lại thì dùng lại, như màn đọc văn bản đến): bản sao trùng nhau không
# chen nhau trong nguồn của trợ lý. Trích yếu, số ký hiệu, cơ quan không có thông tin cá nhân
PII_SYMBOL = "01/ĐN-GL"
PII_ISSUER = "Người làm đơn (giả lập)"
PII_SUMMARY = "Về việc đề nghị cấp bản sao bằng tốt nghiệp"
# Tệp EICAR tên có số điện thoại: nhật ký core.file.rejected của svc-files ghi tên đã che, sổ kiểm toán giữ tên gốc
PII_FILE = "don-0912345678.txt"
PII_FILE_MASKED = "don-[SĐT].txt"
# Nhật ký đi qua bộ che (lọt là đỏ màn) và nhật ký ngoài phạm vi F4.4 (Hasura, Meilisearch, Keycloak, PostgreSQL không
# qua bộ lọc nào: lọt chỉ cảnh báo)
PII_LOGGED = ("apisix", "app-office", "svc-files", "svc-workflow")
PII_UNFILTERED = ("hasura", "meilisearch", "keycloak", "postgres")
# Dòng truy cập phải có, không chuỗi truy vấn: (dịch vụ, nhãn, đường dẫn chấp nhận). APISIX và nginx của giao diện
# lấy đường dẫn từ $request_uri cắt ở dấu ? đầu tiên (không phải $uri: try_files của ứng dụng một trang đổi $uri thành
# /index.html), nên /tim-kiem?q=… được ghi là GET /tim-kiem
PII_ACCESS = (("apisix", "/api/search", ("/api/search",)), ("apisix", "/tim-kiem", ("/tim-kiem",)),
              ("svc-files", "/api/search", ("/api/search",)), ("app-office", "/tim-kiem", ("/tim-kiem",)))
QUERY_MARKS = ("/api/search?q", "/tim-kiem?q")
# Nhãn đã che, như svc_files.pii.LABEL_RE (test so hai mẫu)
MASK_LABEL_RE = re.compile(r"\[(?:CCCD|CMND|SĐT|EMAIL|STK)(?:-\d{1,3})?\]")
# Cách chia nhóm thường gặp theo số chữ số (ngoài cách viết của chính giá trị)
PII_SPLITS = {10: ((4, 3, 3), (3, 3, 4)), 11: ((3, 4, 4), (4, 3, 4)), 12: ((3, 3, 3, 3), (4, 4, 4)), 13: ((4, 4, 5),)}
PII_DOCUMENT = """query ($s: String!) { office_documents(where: {direction: {_eq: "in"}, symbol: {_eq: $s},
  status: {_neq: "cancelled"}}, order_by: {created_at: asc}) { id register_number } }"""


def pii_letter(tag: str) -> list[str]:
    """Các dòng của lá đơn giả lập (một trang; chữ ASCII vì text_pdf chỉ có Helvetica): đủ năm giá trị của PII_DEMO và
    vài số không được che — năm sinh, ngày cấp, số bản sao, mã hồ sơ."""
    v = PII_DEMO
    return ["CONG HOA XA HOI CHU NGHIA VIET NAM", "Doc lap - Tu do - Hanh phuc",
            "DON DE NGHI CAP BAN SAO BANG TOT NGHIEP", "Kinh gui: Phong Dao tao, Truong Dai hoc Mau",
            f"Toi la Nguyen Van B, sinh nam 2005, so CCCD {v['cccd']} cap ngay 05/3/2021.",
            f"So dien thoai lien he cua nguoi lam don de nghi: {v['phone']}.",
            f"Dien thoai co quan: {v['landline']}. Email: {v['email']}.",
            "Toi de nghi cap 02 ban sao bang tot nghiep.",
            f"Le phi chuyen vao so tai khoan {v['account']}.",
            f"Ma ho so: {tag}",
            "Van ban gia lap de chay thu Signet, khong phai van ban that."]


def _split(digits: str, sizes: tuple[int, ...]) -> list[str]:
    out, at = [], 0
    for size in sizes:
        out.append(digits[at:at + size])
        at += size
    return out


def spellings(values: dict[str, str]) -> list[str]:
    """Mọi cách viết của các giá trị giả lập mà một dòng nhật ký có thể mang: như đã viết; số liền; theo nhóm (của
    chính giá trị và cách chia thường gặp) với dấu cách, chấm, gạch; điện thoại thêm +84, (+84), 0084, 84 thay số 0
    đầu; email chữ thường; mỗi cách viết thêm dạng mã hóa URL (%20, %40, %2B…) và dấu cách thành "+"."""
    out: dict[str, None] = {}
    for value in values.values():
        forms = [value]
        if "@" in value:
            forms.append(value.lower())
        else:
            digits = "".join(re.findall(r"\d", value))
            groups = re.findall(r"\d+", value)
            forms.append(digits)
            splits = [groups, *(_split(digits, sizes) for sizes in PII_SPLITS.get(len(digits), ()))]
            forms += [sep.join(g) for g in splits if len(g) > 1 for sep in " .-"]
            if digits[:1] == "0" and len(digits) in (10, 11):        # điện thoại: mã nước thay số 0 đầu
                national = [groups[0][1:], *groups[1:]] if len(groups[0]) > 1 else groups[1:]
                for cc in ("+84", "(+84)", "0084", "84"):
                    forms += [cc + digits[1:], f"{cc} {digits[1:]}", f"{cc} {' '.join(national)}"]
        for form in list(forms):
            forms.append(quote(form, safe=""))
            if " " in form:
                forms.append(form.replace(" ", "+"))
        for form in forms:
            out.setdefault(form, None)
    return list(out)


def leaks(text: str, forms: list[str]) -> list[str]:
    """Các cách viết có trong ``text`` (không phân biệt hoa thường). Cách viết mở đầu / kết thúc bằng chữ số thì không
    tính khi dính liền chữ số khác: đó là một phần của số dài hơn (mốc thời gian, mã toàn số), không phải giá trị này."""
    low = text.casefold()
    found = []
    for form in forms:
        f = form.casefold()
        pattern = (r"(?<!\d)" if f[:1].isdigit() else "") + re.escape(f) + (r"(?!\d)" if f[-1:].isdigit() else "")
        if re.search(pattern, low):
            found.append(form)
    return found


def access_lines(text: str, *paths: str) -> list[str]:
    """Các dòng nhật ký truy cập của một trong ``paths``: đường dẫn đứng ngay sau phương thức HTTP, tiếp theo là chuỗi
    truy vấn, khoảng trắng hoặc dấu nháy — "GET /api/search HTTP/1.1" (APISIX, nginx), "GET /api/search?… HTTP/1.1"
    (uvicorn); không nhận /api/search-khac."""
    pattern = re.compile(r"\b(?:GET|HEAD|POST|PUT|PATCH|DELETE|OPTIONS) (?:%s)(?=[?\s\"]|$)"
                         % "|".join(map(re.escape, paths)))
    return [line for line in text.splitlines() if pattern.search(line)]


def log_problems(logs: dict[str, str], forms: list[str]) -> list[str]:
    """Lý do màn đỏ ở bước đọc nhật ký (rỗng: đạt): giá trị nào lọt ở dịch vụ nào; dòng còn ?q=; thiếu dòng truy cập
    phải có; svc-files không ghi tên tệp đã che."""
    problems = []
    for service in PII_LOGGED:
        text = logs.get(service, "")
        found = leaks(text, forms)
        if found:
            problems.append(f"{service}: lọt {', '.join(found[:6])}" + (f" (+{len(found) - 6})" if len(found) > 6 else ""))
        queried = [line for line in text.splitlines() if any(mark in line for mark in QUERY_MARKS)]
        if queried:
            problems.append(f"{service}: {len(queried)} dòng còn chuỗi truy vấn, vd {queried[0].strip()[:160]}")
    for service, label, paths in PII_ACCESS:
        if not access_lines(logs.get(service, ""), *paths):
            problems.append(f"{service}: không có dòng truy cập {label} — nhật ký truy cập bị tắt, hay đọc sai dịch vụ?")
    if PII_FILE_MASKED not in logs.get("svc-files", "") and "don-[S\\u0110T].txt" not in logs.get("svc-files", ""):
        problems.append(f"svc-files: không có dòng core.file.rejected ghi {PII_FILE_MASKED}")
    return problems


def log_events(text: str, event: str) -> list[dict[str, Any]]:
    """Các dòng nhật ký JSON có ``event`` cho trước, theo thứ tự (bỏ dòng không phải JSON: dòng truy cập…)."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and record.get("event") == event:
            out.append(record)
    return out


def utc_mark() -> str:
    """Mốc cho docker compose logs --since: giờ UTC, lùi một giây (mốc tính theo giây, không bỏ sót dòng nào)."""
    return (datetime.now(timezone.utc) - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def service_logs(since: str, *services: str) -> dict[str, str]:
    """docker compose logs từ mốc ``since`` của từng dịch vụ, không tiền tố tên, không màu → {dịch vụ: chữ}."""
    return {s: compose("logs", "--since", since, "--no-log-prefix", "--no-color", s).decode(errors="replace")
            for s in services}


# APISIX ghi nhật ký truy cập có đệm (nginx.conf của APISIX: access_log … buffer=16384 flush=3): dòng ra sau yêu cầu tới
# 3 giây. Đọc sớm thì thiếu dòng truy cập (màn đỏ sai), tệ hơn là dòng còn giá trị chưa ra (màn xanh sai)
LOG_FLUSH_S = 4.0


def settled_logs(since: str, last_request: float, timeout_s: float = 15.0) -> dict[str, str]:
    """Nhật ký của PII_LOGGED từ mốc ``since``, đọc khi đệm đã xả: đợi tới ``last_request`` (time.monotonic() sau yêu
    cầu cuối của màn) + LOG_FLUSH_S, rồi đọc lại tới khi có đủ dòng truy cập của PII_ACCESS hoặc hết ``timeout_s`` —
    hết giờ thì trả lần đọc cuối để log_problems báo thiếu."""
    time.sleep(max(0.0, last_request + LOG_FLUSH_S - time.monotonic()))
    deadline = time.monotonic() + timeout_s
    while True:
        logs = service_logs(since, *PII_LOGGED)
        if all(access_lines(logs.get(s, ""), *paths) for s, _, paths in PII_ACCESS) or time.monotonic() >= deadline:
            return logs
        time.sleep(1)


def wait_pii_answer(clerk: Session, doc_id: str, timeout_s: float) -> dict[str, Any]:
    """Hỏi PII_QUESTION (extract) tới khi trang của lá đơn có trong nguồn — vòng nền svc-files đã đưa đoạn vào chỉ mục.
    Nguồn "trích yếu" của lá đơn có trước (vào chỉ mục lúc tiếp nhận) nhưng không có số điện thoại: chưa tính."""
    started = time.monotonic()
    while True:
        try:
            got, _ = ask(clerk, PII_QUESTION)
        except HTTPError as exc:            # Meilisearch, Hasura vừa khởi động: đợi tiếp; tắt trợ lý thì dừng
            if exc.status != 503 or error_detail(exc).get("code") == "assistant_disabled":
                raise
            got = {}
        if any(s.get("document_id") == doc_id and s.get("kind") == "page" for s in got.get("sources") or []):
            return got
        if time.monotonic() - started > timeout_s:
            raise DemoFailed(f"sau {timeout_s:.0f} giây trợ lý chưa có lá đơn {PII_SYMBOL} trong nguồn — vòng nền svc-files"
                             " (MOC_ASK_SYNC_INTERVAL_S) có chạy không?")
        time.sleep(3)


def che_pii() -> None:
    print("Màn F4.4 · Che thông tin cá nhân — người được xem văn bản thấy bản gốc; mô hình ngôn ngữ và nhật ký chỉ thấy"
          " nhãn [SĐT], [CCCD]…; nhật ký truy cập không còn chuỗi truy vấn")
    from seed_documents import today

    tag = uuid.uuid4().hex[:6].upper()
    clerk = who("vanthu")
    forms = spellings(PII_DEMO)
    cccd, phone = PII_DEMO["cccd"], PII_DEMO["phone"]

    since = utc_mark()
    say(1, f"Mốc nhật ký {since} (UTC) — bước 6 đọc mọi dòng nhật ký từ mốc này")
    ok(f"giá trị giả lập, đúng định dạng nhưng không của ai: CCCD {cccd}, di động {phone}, máy bàn"
       f" {PII_DEMO['landline']}, email {PII_DEMO['email']}, số tài khoản {PII_DEMO['account']}")

    say(2, "Văn thư tải lên “Đơn đề nghị cấp bản sao bằng tốt nghiệp” (hư cấu) có đủ năm giá trị, tiếp nhận với trích"
           " yếu không có thông tin cá nhân, vào sổ")
    found = clerk.gql(PII_DOCUMENT, {"s": PII_SYMBOL})["office_documents"]
    if found:
        doc_id, number = found[0]["id"], found[0]["register_number"]
        print(f"   – {PII_SYMBOL} đã được tiếp nhận ở lần chạy trước — dùng lại, không tải thêm bản nào (chặn trùng)")
    else:
        file = clerk.upload(f"don-de-nghi-{tag}.pdf", text_pdf(*pii_letter(tag)))
        doc_id = clerk.gql("mutation ($d: jsonb!) { receiveIncoming(data: $d) { document_id } }", {"d": {
            "type_code": "CV", "symbol": PII_SYMBOL, "issuer_name": PII_ISSUER,
            "issued_on": (today() - timedelta(days=1)).isoformat(), "summary": PII_SUMMARY, "urgency": "normal",
            "file_ids": [file["id"]]}})["receiveIncoming"]["document_id"]
        number = None
        ok(f"don-de-nghi-{tag}.pdf: PDF một trang có lớp chữ, chân trang “Van ban gia lap de chay thu Signet…”")
    if number is None:
        number = clerk.gql("mutation ($id: uuid!) { registerIncoming(documentId: $id) { register_number } }",
                           {"id": doc_id})["registerIncoming"]["register_number"]
    ok(f"{PII_SYMBOL} trong sổ, số đến {number}; trích yếu “{PII_SUMMARY}”")

    say(3, f"Văn thư gõ số CCCD {cccd} vào ô Tìm kiếm — chỉ mục tìm kiếm giữ bản gốc")
    started = time.monotonic()
    while True:
        hits = call_json("GET", f"{PUBLIC_URL}/api/search?q={quote(cccd)}", headers=clerk.auth)[0]["hits"]
        hit = next((h for h in hits if h["id"] == doc_id), None)
        if hit and hit.get("matched_content"):
            break
        if time.monotonic() - started > 60:
            raise DemoFailed(f"sau 60 giây tìm {cccd} chưa ra {PII_SYMBOL} (khớp nội dung tệp): {hits[:3]} — vòng nền"
                             " svc-files đọc chữ PDF (MOC_TEXT_INTERVAL_S) có chạy không?")
        time.sleep(2)
    ok(f"ra đúng lá đơn {PII_SYMBOL}, khớp trong nội dung tệp PDF (sau {time.monotonic() - started:.0f} giây)")
    request("GET", f"{PUBLIC_URL}/tim-kiem?q={quote(cccd)}", timeout=15)
    ok("mở /tim-kiem?q=… như khi tải lại trang Tìm kiếm — APISIX và nginx của giao diện có dòng truy cập để kiểm ở bước 6")

    say(4, f"Văn thư hỏi trợ lý: “{PII_QUESTION}”")
    base = wait_pii_answer(clerk, doc_id, 90)
    show_answer(base)
    cited = [s for s in base.get("sources") or [] if s.get("cited") and s.get("document_id") == doc_id]
    if base.get("status") != "answered" or phone not in answer_text(base) or not cited:
        raise DemoFailed(f"chưa trích được câu có số điện thoại của lá đơn: trạng thái {base.get('status')}, nguồn"
                         f" {[source_label(s) for s in base.get('sources') or []]}")
    ok(f"câu trích nguyên văn có đúng số {phone}, nguồn [{cited[0]['n']}] {source_label(cited[0])} — người được xem văn"
       " bản thấy bản gốc: chỉ mục, câu trích, nguồn không che")

    say(5, f"Văn thư tải tệp EICAR tên {PII_FILE} — ClamAV chặn; tên tệp mang số điện thoại")
    before = int(psql("select coalesce(max(id), 0) from core.audit_log") or 0)
    try:
        clerk.upload(PII_FILE, EICAR, "text/plain")
        raise DemoFailed("tệp EICAR không bị chặn")
    except HTTPError as exc:
        detail = error_detail(exc)
        if exc.status != 422 or detail.get("code") != "infected":
            raise DemoFailed(f"tệp EICAR trả {exc.status} {detail or exc.body[:200]}") from exc
    last_request = time.monotonic()
    ok(f"{PII_FILE} → 422 infected ({detail.get('signature')})")
    kept = psql("select diff->>'filename' from core.audit_log where id > %d and action = 'file.rejected'"
                " order by id desc limit 1" % before)
    if kept != PII_FILE:
        raise DemoFailed(f"dòng sổ file.rejected mới nhất ghi tên {kept!r}, cần tên gốc {PII_FILE}")
    ok(f"psql: dòng sổ file.rejected giữ tên gốc {kept} — sổ kiểm toán có phân quyền và chuỗi băm, không che (che làm"
       " sai băm, mất giá trị chứng cứ)")

    say(6, f"Đọc nhật ký từ mốc ở bước 1: docker compose logs {' '.join(PII_LOGGED)}")
    logs = settled_logs(since, last_request)
    problems = log_problems(logs, forms)
    if problems:
        raise DemoFailed("nhật ký chưa sạch:\n   - " + "\n   - ".join(problems))
    total = sum(len(text.splitlines()) for text in logs.values())
    ok(f"{total} dòng của {len(PII_LOGGED)} dịch vụ: không có giá trị nào ở {len(forms)} cách viết (liền, theo nhóm,"
       " chấm, gạch, +84, %20, %40…)")
    ok("svc-workflow chỉ được quét để chắc không lọt từ chỗ khác: màn không đưa giá trị nào qua nó — bộ lọc nhật ký của"
       " svc-workflow do test đơn vị kiểm (tests/test_pii_logging.py)")
    for service, label, paths in PII_ACCESS:
        line = " ".join(access_lines(logs[service], *paths)[-1].split())
        ok(f"{service} ({label}): {line if len(line) <= 100 else line[:99] + '…'}")
    ok(f"svc-files: core.file.rejected ghi {PII_FILE_MASKED}; sổ kiểm toán ở bước 5 vẫn giữ tên gốc")
    warned = []
    for service in PII_UNFILTERED:
        try:
            found_here = leaks(service_logs(since, service)[service], forms)
        except subprocess.CalledProcessError:
            print(f"   – {service}: không đọc được nhật ký")
            continue
        if found_here:
            warned.append(service)
            print(f"   – cảnh báo {service}: có {', '.join(found_here[:4])} — nhật ký này không qua bộ che (ngoài phạm"
                  " vi F4.4, xem README svc-files)")
    if not warned:
        ok(f"{', '.join(PII_UNFILTERED)} (không qua bộ che, lọt chỉ cảnh báo): không thấy giá trị nào")

    say(7, "Chữ gửi mô hình ngôn ngữ chạy tại chỗ (tùy chọn: profile ai) — che trước khi rời svc-files")
    if base.get("ai_available"):
        mark = utc_mark()
        got, took = ask(clerk, PII_QUESTION, mode="generate", ask_id=base["ask_id"])
        answer = got.get("answer") or {}
        warnings = list(got.get("warnings") or [])
        if answer.get("source") == "model":
            show_answer(got)
            leaked = leaks(answer.get("text") or "", forms)
            if leaked:
                raise DemoFailed(f"câu trả lời của mô hình có giá trị gốc: {leaked}")
            labels = list(dict.fromkeys(MASK_LABEL_RE.findall(answer.get("text") or "")))
            ok(f"{answer.get('model')} viết trong {took:.0f} giây, không có giá trị gốc nào"
               + (f"; ghi {', '.join(labels)} — mô hình chưa từng thấy số thật, số thật ở câu trích bước 4" if labels
                  else ""))
            if not any(label.startswith("[SĐT") for label in labels):
                print("   – câu trả lời không nhắc nhãn [SĐT-1] (mô hình diễn đạt khác) — vẫn không có số gốc")
        else:
            print(f"   – mô hình không qua kiểm ({', '.join(warnings) or got.get('status')}) — giữ câu trích nguyên văn")
        time.sleep(1)
        text = service_logs(mark, "svc-files")["svc-files"]
        leaked = leaks(text, forms)
        if leaked:
            raise DemoFailed(f"nhật ký svc-files của lượt generate có {leaked}")
        if answer.get("source") == "model" or {"model_rejected", "model_declined"} & set(warnings):
            asked = [e for e in log_events(text, "office.assist.asked") if e.get("mode") == "generate"]
            masked = asked[-1].get("masked") if asked else None
            if not isinstance(masked, int) or masked < 2:
                raise DemoFailed(f"nhật ký office.assist.asked của lượt generate ghi masked = {masked!r} (cần ≥ 2)")
            if log_events(text, "office.assist.pii_at_egress"):
                raise DemoFailed("có office.assist.pii_at_egress: lối ra Ollama còn phải che — chỗ dựng ngữ cảnh đã quên"
                                 " che")
            ok(f"nhật ký office.assist.asked của lượt này: masked = {masked} chỗ đã che trong câu hỏi và các đoạn gửi mô"
               " hình; không có office.assist.pii_at_egress — ngữ cảnh đã che trước khi tới lối ra")
    else:
        print("   – chưa bật mô hình (make ai-model && make up-ai) — bản che mà lối ra Ollama sẽ gửi đi:")
        masked_text = compose("exec", "-T", "svc-files", "python", "-m", "svc_files.pii", "mask",
                              stdin="\n".join(pii_letter(tag)).encode()).decode()
        for line in masked_text.strip().splitlines():
            print(f"     {line}")
        leaked = leaks(masked_text, forms)
        labels = MASK_LABEL_RE.findall(masked_text)
        if leaked or len(labels) != len(PII_DEMO):
            raise DemoFailed(f"bản che còn {leaked or 'đủ giá trị'}, có {len(labels)} nhãn (cần {len(PII_DEMO)})")
        ok(f"python -m svc_files.pii mask trong container svc-files: {len(labels)} nhãn {', '.join(labels)}, không còn"
           " giá trị gốc; năm sinh, ngày cấp, số bản sao giữ nguyên. Trợ lý đánh số nhãn theo lượt hỏi ([SĐT-1]…)")

    print(f"\nXem trên giao diện (vanthu): {PUBLIC_URL}/tim-kiem — gõ {cccd}; {PUBLIC_URL}/hoi-dap — hỏi “{PII_QUESTION}”"
          f" (bật mô hình: câu trả lời ghi [SĐT-1], dòng nhắc số thật ở câu trích nguyên văn); lá đơn:"
          f" {PUBLIC_URL}/van-ban/{doc_id}")


# --- F4.6 · Số đo "sau" (đặc tả §8) ----------------------------------------------------------------------------------
# Bốn chỉ số của docs/dac-ta-san-pham.md §8 trên hệ thống đang chạy, đọc bằng quyền lãnh đạo đơn vị qua APISIX như
# trang Số đo: (a), (b) từ khung nhìn office.v_time_to_assign, office.v_overdue_rate (migration 1792281602750) — chỉ
# số đếm, số giờ, văn bản hạn chế không tính; (c) bấm giờ 5 lần tìm lại văn bản đến cũ nhất qua /api/search, lần lượt,
# không lượt khởi động: độ trễ hệ thống, không gồm thời gian người gõ, đọc; (d) chỉ so sánh định tính. Cột "trước"
# luôn là "chưa đo" — chưa có đơn vị chạy thử. Cách đo, cách đọc: docs/so-lieu-sau.md.
SL_ACCOUNT = "truongkhoa"              # lãnh đạo Khoa CNTT của seed (seed/users.csv)
SL_RUNS = 5
SL_POOL = 25                           # số văn bản đến cũ nhất để chọn ra 5 số ký hiệu khác nhau
SL_LIMIT = 20                          # văn bản cần tìm phải nằm trong 20 kết quả đầu
SL_BEFORE = "chưa đo"
SL_JSON = ROOT / "out" / "so-lieu-sau.json"
SL_QUERY = """{
  core_tenants { code name }
  office_v_time_to_assign { sample month arrived assigned median_hours p90_hours handled handled_median_hours
    handled_p90_hours waiting }
  office_v_overdue_rate { sample month judged on_time late late_open pending }
  office_v_feedback_summary(where: {screen: {_is_null: true}}) { sample feedback rating_total with_comment }
  office_documents(where: {direction: {_eq: "in"}, restricted: {_eq: false}, status: {_neq: "cancelled"},
    symbol: {_is_null: false}}, order_by: [{created_at: asc}, {id: asc}], limit: %d) { id symbol }
}""" % SL_POOL
SL_NAMES = {
    "time_to_assign": "Thời gian từ khi văn bản đến tới khi được giao xử lý",
    "overdue_rate": "Tỷ lệ văn bản xử lý quá hạn",
    "search": "Thời gian tìm lại một văn bản cũ",
    "handoffs": "Số bước chuyển tay (in, ký, mang đi, nhắn tin nhắc)",
}
SL_HOW = {
    "time_to_assign": "office.v_time_to_assign: lúc tiếp nhận (hoặc liên thông tới) → lần đầu giao chủ trì",
    "overdue_rate": "office.v_overdue_rate: hạn giải quyết so với lúc xong; chưa xong mà qua hạn tính là trễ",
    "search": f"{SL_RUNS} lần GET /api/search theo số ký hiệu của văn bản đến cũ nhất, lần lượt",
    "handoffs": "so quy trình giấy với quy trình trên hệ thống",
}


def sl_targets(docs: list[dict[str, Any]], n: int = SL_RUNS) -> list[dict[str, str]]:
    """Văn bản cần tìm lại: theo thứ tự đã xếp (cũ nhất trước), mỗi số ký hiệu một lần — như pickSearchTargets của
    trang Số đo (apps/office/app/utils/metrics.ts)."""
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for d in docs:
        symbol = (d.get("symbol") or "").strip()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        out.append({"document_id": d["id"], "symbol": symbol})
        if len(out) == n:
            break
    return out


def sl_rank(hits: list[dict[str, Any]], doc_id: str) -> int | None:
    """Vị trí của văn bản cần tìm trong kết quả, 1 là đầu; None: không thấy."""
    return next((i for i, h in enumerate(hits, 1) if h.get("id") == doc_id), None)


def sl_median(values: list[float]) -> float | None:
    s = sorted(values)
    if not s:
        return None
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def sl_number(x: float) -> str:
    """Một chữ số thập phân, dấu phẩy, bỏ ",0": 19,2 · 4 · 0,5."""
    text = f"{round(x, 1):.1f}"
    return (text[:-2] if text.endswith(".0") else text).replace(".", ",")


def sl_hours(hours: float | None) -> str:
    """Như fmtDuration của trang Số đo: dưới 1 phút ra giây, dưới 1 giờ ra phút, dưới 2 ngày ra giờ, còn lại ra ngày.
    Dữ liệu mẫu đi hết các bước trong vài giây nên phải hiện được giây."""
    if hours is None or hours != hours or hours in (float("inf"), float("-inf")):
        return "—"
    h = max(0.0, float(hours))
    if h < 1 / 60:
        return f"{round(h * 3600)} giây"
    if h < 1:
        return f"{sl_number(h * 60)} phút"
    if h < 48:
        return f"{sl_number(h)} giờ"
    return f"{sl_number(h / 24)} ngày"


def _sl_split(rows: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """(dòng mọi tháng, các tháng cũ trước), bỏ cột sample (ghi một lần ở tenant)."""
    clean = [{k: v for k, v in r.items() if k != "sample"} for r in rows]
    total = next((r for r in clean if r.get("month") is None), None)
    return total, sorted((r for r in clean if r.get("month") is not None), key=lambda r: r["month"])


def sl_report(data: dict[str, Any], runs: list[dict[str, Any]], *, measured_at: str) -> dict[str, Any]:
    """Kết quả một lần đo, đúng khuôn của out/so-lieu-sau.json (docs/so-lieu-sau.md)."""
    views = data.get("office_v_time_to_assign", []), data.get("office_v_overdue_rate", []), \
        data.get("office_v_feedback_summary", [])
    tenant = (data.get("core_tenants") or [{}])[0]
    assign_all, assign_months = _sl_split(views[0])
    overdue_all, overdue_months = _sl_split(views[1])
    feedback = views[2][0] if views[2] else None
    ms = [r["ms"] for r in runs]
    return {
        "measured_at": measured_at,
        "account": SL_ACCOUNT,
        "tenant": {"code": tenant.get("code"), "name": tenant.get("name"),
                   "sample": any(r.get("sample") for rows in views for r in rows)},
        "before": SL_BEFORE,
        "time_to_assign": {"all": assign_all, "months": assign_months},
        "overdue_rate": {"all": overdue_all, "months": overdue_months,
                         "late_pct": (100 * overdue_all["late"] / overdue_all["judged"]
                                      if overdue_all and overdue_all["judged"] else None)},
        "search": {"kind": "độ trễ hệ thống", "endpoint": "/api/search", "limit": SL_LIMIT, "runs": runs,
                   "median_ms": sl_median(ms), "max_ms": max(ms) if ms else None,
                   "found": sum(r["rank"] is not None for r in runs)},
        "handoffs": {"kind": "định tính", "value": None, "doc": "docs/so-lieu-sau.md"},
        "feedback": {"count": feedback["feedback"] if feedback else 0,
                     "average": feedback["rating_total"] / feedback["feedback"]
                     if feedback and feedback["feedback"] else None,
                     "with_comment": feedback["with_comment"] if feedback else 0},
    }


def sl_after(report: dict[str, Any]) -> dict[str, str]:
    """Cột "sau" của bảng: chưa có dòng nào thì "chưa có dữ liệu" (không phải 0)."""
    assign, overdue, search = report["time_to_assign"]["all"], report["overdue_rate"], report["search"]
    after = {"handoffs": "so sánh định tính — docs/so-lieu-sau.md"}
    if assign and assign["assigned"]:
        after["time_to_assign"] = (f"trung vị {sl_hours(assign['median_hours'])}, p90 {sl_hours(assign['p90_hours'])}"
                                   f" ({assign['assigned']} văn bản đã giao, {assign['waiting']} còn chờ)")
    else:
        after["time_to_assign"] = "chưa có dữ liệu"
    if overdue["late_pct"] is not None:
        a = overdue["all"]
        after["overdue_rate"] = (f"{sl_number(overdue['late_pct'])} % ({a['late']}/{a['judged']} văn bản; trong đó"
                                 f" {a['late_open']} chưa xong đã qua hạn; {a['pending']} chưa tới hạn chưa tính)")
    else:
        after["overdue_rate"] = "chưa có dữ liệu"
    if search["runs"]:
        after["search"] = (f"trung vị {sl_number(search['median_ms'])} ms, chậm nhất {sl_number(search['max_ms'])} ms"
                           f" ({len(search['runs'])} lần, tìm thấy {search['found']}/{len(search['runs'])}) — độ trễ"
                           " hệ thống qua APISIX, không gồm thời gian người gõ, đọc")
    else:
        after["search"] = "chưa đo được"
    return after


def sl_table(report: dict[str, Any]) -> str:
    """Bảng markdown đúng 4 dòng của đặc tả §8: Chỉ số | Trước | Sau | Cách đo."""
    after = sl_after(report)
    out = ["| Chỉ số | Trước | Sau | Cách đo |", "|---|---|---|---|"]
    for key, name in SL_NAMES.items():
        out.append(f"| {name} | {report['before']} | {after[key]} | {SL_HOW[key]} |")
    return "\n".join(out)


def sl_problems(report: dict[str, Any]) -> list[str]:
    """Lý do thoát 1 (rỗng: đạt). Thiếu dữ liệu cho (a), (b) không phải lỗi: chỉ in "chưa có dữ liệu"."""
    runs = report["search"]["runs"]
    problems = []
    if len(runs) < SL_RUNS:
        problems.append(f"chỉ có {len(runs)} văn bản đến có số ký hiệu để tìm lại, cần {SL_RUNS} (đã make seed chưa?)")
    problems += [f"tìm “{r['symbol']}” không thấy văn bản {r['document_id']} trong {SL_LIMIT} kết quả đầu"
                 for r in runs if r["rank"] is None]
    return problems


def do_so_lieu_sau() -> None:
    print(f"Số đo \"sau\" theo đặc tả §8 (F4.6) trên hệ thống đang chạy, đọc bằng quyền lãnh đạo đơn vị ({SL_ACCOUNT})"
          " qua cổng APISIX; cột \"trước\" chưa đo — chưa có đơn vị chạy thử")
    leader = who(SL_ACCOUNT)
    data = leader.gql(SL_QUERY)
    runs = []
    for target in sl_targets(data["office_documents"]):
        url = f"{PUBLIC_URL}/api/search?q={quote(target['symbol'], safe='')}&limit={SL_LIMIT}"
        started = time.perf_counter()
        body, _ = call_json("GET", url, headers=leader.auth)
        ms = (time.perf_counter() - started) * 1000
        runs.append({**target, "ms": round(ms, 1), "rank": sl_rank((body or {}).get("hits") or [],
                                                                   target["document_id"])})
    report = sl_report(data, runs, measured_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    tenant = report["tenant"]
    print(f"   đơn vị: {tenant['name']} ({tenant['code']})")
    print("\n" + sl_table(report))
    for r in runs:
        print(f"   tìm “{r['symbol']}”: {sl_number(r['ms'])} ms, "
              + (f"thứ {r['rank']} trong kết quả" if r["rank"] else f"không thấy trong {SL_LIMIT} kết quả đầu"))
    if report["feedback"]["count"]:
        print(f"   góp ý: {report['feedback']['count']}, điểm trung bình {sl_number(report['feedback']['average'])}/5")
    if tenant["sample"]:
        print("\nDữ liệu mẫu (make seed): kịch bản mẫu đi hết các bước trong vài giây, không phải nhịp làm việc thật —"
              " các số trên không phải số đo \"sau\" của một đơn vị.")
    SL_JSON.parent.mkdir(parents=True, exist_ok=True)
    SL_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nĐã ghi {SL_JSON.relative_to(ROOT)}")
    problems = sl_problems(report)
    if problems:
        raise DemoFailed("; ".join(problems))
    print(f"\n✓ đo đủ {SL_RUNS} lần tìm, văn bản cần tìm đều nằm trong {SL_LIMIT} kết quả đầu")


# --- Nạp lô văn bản đến (cụm ⑤ Tầng 1) -----------------------------------------------------------------------------

IMPORTS_URL = f"{PUBLIC_URL}/api/imports"
IMPORT_AUDIT = """query ($id: String!) {
  core_audit_log(where: {entity: {_eq: "core.import_jobs"}, entity_id: {_eq: $id}}, order_by: {id: asc}) {
    id action actor_kind overview } }"""
VN = timezone(timedelta(hours=7))


def send_batch(session: Session, data: bytes, name: str, *, archive: bytes | None = None, key: str | None = None,
               query: str = "") -> tuple[int, dict[str, str], dict[str, Any]]:
    """POST /api/imports/incoming → (mã HTTP, tiêu đề chữ thường, thân JSON)."""
    parts = [("data", name, "text/csv" if name.endswith(".csv") else "application/x-ndjson", data)]
    if archive is not None:
        parts.append(("archive", "tep.zip", "application/zip", archive))
    body, content_type = nap_lo_mau.multipart(parts)
    headers = {**session.auth, "Content-Type": content_type, **({"Idempotency-Key": key} if key else {})}
    status, got, raw = request("POST", f"{IMPORTS_URL}/incoming{query}", data=body, headers=headers, timeout=120)
    return status, {k.lower(): v for k, v in got.items()}, json.loads(raw)


def wait_batch(session: Session, job_id: str, timeout_s: float = 180) -> dict[str, Any]:
    """Hỏi trạng thái lô mỗi giây tới khi done."""
    deadline = time.monotonic() + timeout_s
    while True:
        job, _ = call_json("GET", f"{IMPORTS_URL}/{job_id}", headers=session.auth)
        if job["status"] == "done":
            return job
        if time.monotonic() > deadline:
            raise DemoFailed(f"sau {timeout_s:.0f} giây lô {job_id} chưa xong: {job}")
        time.sleep(1)


def batch_rows(session: Session, job_id: str, status: str) -> list[dict[str, Any]]:
    """Mọi dòng có trạng thái ``status`` của lô (đi hết các trang next_after)."""
    out: list[dict[str, Any]] = []
    after = 0
    while True:
        page, _ = call_json("GET", f"{IMPORTS_URL}/{job_id}/rows?status={status}&limit=500&after={after}",
                            headers=session.auth)
        out += page["rows"]
        if page["next_after"] is None:
            return out
        after = page["next_after"]


def tally(job: dict[str, Any]) -> str:
    return f"đạt {job['ok']} · trùng {job['duplicate']} · lỗi {job['failed']}"


def row_problems(rows: list[dict[str, Any]]) -> list[str]:
    """Dòng lỗi / trùng lệch bảng BAD của scripts/nap_lo_mau.py (rỗng: đúng từng dòng, đúng mã, đúng lỗi theo
    trường)."""
    got = {r["line"]: r for r in rows}
    problems = [f"dòng {n} không có trong bảng dòng sai: {r['status']} {r['code']} {r['message']}"
                for n, r in sorted(got.items()) if n not in nap_lo_mau.BAD]
    for n, (code, fields) in sorted(nap_lo_mau.BAD.items()):
        row = got.get(n)
        if row is None:
            problems.append(f"dòng {n} mong đợi {code} mà không lỗi")
            continue
        have = "duplicate" if row["status"] == "duplicate" else row["code"]
        if have != code or (fields is not None and row["fields"] != fields):
            problems.append(f"dòng {n}: mong đợi {code} {fields or ''}, nhận {have} {row['fields'] or ''}")
    return problems


def nap_lo() -> None:
    print("Màn cụm ⑤ · Nạp lô văn bản đến qua API — 200 văn bản đến trong một lần gửi; mỗi dòng đi đúng đường tiếp nhận"
          " lẻ: ClamAV, Action receiveIncoming thay mặt văn thư, sổ kiểm toán")
    tag = uuid.uuid4().hex[:6].upper()
    clerk, director, other = Session("vanthukt"), Session("truongkhoakt"), Session("vanthu")
    rows = nap_lo_mau.rows(tag)
    data = nap_lo_mau.ndjson(rows)
    archive = nap_lo_mau.archive(rows, eicar=EICAR, pdf=lambda name: text_pdf("Van ban den mau", f"{name} {tag}"))
    want, key, name = nap_lo_mau.expected(), f"demo-nap-lo-{tag}", f"van-ban-den-{tag}.ndjson"
    attached = sum(1 for r in rows if r.get("files"))

    say(1, f"Văn thư Khoa Kinh tế gửi {len(rows)} văn bản đến (NDJSON) kèm zip {attached} tệp đính kèm, có"
           " Idempotency-Key")
    status, headers, job = send_batch(clerk, data, name, archive=archive, key=key)
    if status != 202 or headers.get("location") != f"/api/imports/{job['id']}" or job["total"] != len(rows):
        raise DemoFailed(f"tạo lô trả {status} {headers.get('location')} {job}")
    ok(f"202 Accepted sau một lần gửi ({len(data) // 1024} KB dữ liệu, zip {len(archive) // 1024} KB): lô"
       f" {job['id'][:8]}…, {job['total']} dòng, {job['failed']} dòng hỏng ngay lúc đọc (JSON sai, tệp không có trong"
       f" zip), {job['pending']} dòng chờ vòng nền; Location {headers['location'][:22]}…")

    say(2, "Sai vai trò, sai đơn vị")
    try:
        send_batch(director, data, name)
        raise DemoFailed("lãnh đạo khoa tạo được lô nạp")
    except HTTPError as exc:
        if exc.status != 403 or error_detail(exc).get("code") != "forbidden":
            raise DemoFailed(f"lãnh đạo khoa gửi lô: {exc.status} {error_detail(exc)}") from exc
    try:
        call_json("GET", f"{IMPORTS_URL}/{job['id']}", headers=other.auth)
        raise DemoFailed("văn thư Khoa CNTT đọc được lô của Khoa Kinh tế")
    except HTTPError as exc:
        if exc.status != 404:
            raise DemoFailed(f"văn thư Khoa CNTT đọc lô: {exc.status} {error_detail(exc)}") from exc
    ok("truongkhoakt gửi lô → 403 forbidden (chỉ văn thư nạp lô); vanthu (Khoa CNTT) đọc lô → 404, như lô không có")

    say(3, "svc-files xử lý nền theo mẻ — văn thư hỏi trạng thái tới khi xong")
    started = time.monotonic()
    done = wait_batch(clerk, job["id"])
    took = time.monotonic() - started
    if Counter({k: done[k] for k in want}) != want:
        raise DemoFailed(f"lô xong với {tally(done)}, mong đợi {dict(want)}")
    bad = batch_rows(clerk, job["id"], "failed") + batch_rows(clerk, job["id"], "duplicate")
    if problems := row_problems(bad):
        raise DemoFailed("kết quả từng dòng lệch bảng dòng sai cố ý:\n   - " + "\n   - ".join(problems))
    ok(f"xong sau {took:.0f} giây: {tally(done)} — đúng từng dòng với bảng dòng sai cố ý của scripts/nap_lo_mau.py")
    print("   dòng | kết quả   | mã                 | lý do")
    for r in sorted(bad, key=lambda x: x["line"]):
        print(f"   {r['line']:>4} | {r['status']:<9} | {r['code'] or '':<18} | {(r['message'] or '')[:64]}")

    say(4, "Tệp EICAR trong zip bị chặn như tải lên lẻ; mỗi văn bản một dòng sổ kiểm toán")
    infected = next(r for r in bad if r["line"] == nap_lo_mau.INFECTED)
    sha = hashlib.sha256(EICAR).hexdigest()
    stored = psql(f"select count(*) from core.files where sha256 = '\\x{sha}'")
    rejected = psql("select count(*) from core.audit_log where action = 'file.rejected'"
                    f" and request_id = '{job['id']}:{nap_lo_mau.INFECTED}'")
    if "Eicar" not in (infected["message"] or "") or stored != "0" or rejected != "1":
        raise DemoFailed(f"dòng EICAR: {infected['message']}; core.files {stored} dòng; file.rejected {rejected} dòng")
    ok(f"dòng {infected['line']}: {infected['message']}; core.files 0 dòng có SHA-256 {sha[:16]}…; sổ có file.rejected"
       f" mang request_id {job['id'][:8]}…:{infected['line']}")
    # dòng có tệp mà Action từ chối (ngày không có thật, loại lạ…): tệp đã quét, vào kho rồi được gỡ lại
    rejected = [n for n, (code, _) in sorted(nap_lo_mau.BAD.items()) if code == "invalid" and rows[n - 1].get("files")]
    per_row = sum(len(rows[n - 1]["files"]) for n in rejected)
    requests = ", ".join(f"'{job['id']}:{n}'" for n in rejected)
    trail = "select count(*) from core.audit_log where entity = 'core.files' and request_id in ({}) and {}"
    inserted = psql(trail.format(requests, "action = 'insert'"))
    dropped = psql(trail.format(requests, "action = 'delete' and actor_id = 'svc-files:import'"))
    if not rejected or inserted != str(per_row) or dropped != str(per_row):
        raise DemoFailed(f"dòng bị Action từ chối {rejected}: sổ có {inserted} insert, {dropped} delete core.files,"
                         f" mong đợi {per_row}")
    ok(f"dòng {', '.join(map(str, rejected))} có tệp mà Action từ chối: {per_row} tệp đã qua trạm quét, vào kho rồi"
       f" được gỡ lại (sổ: {inserted} insert, {dropped} delete core.files bởi svc-files:import) — không để lại tệp mồ"
       " côi")
    pattern = f"%-{tag}/%"
    docs = psql(f"select count(*) from office.documents where direction = 'in' and symbol like '{pattern}'")
    logged = psql("select count(*) || '/' || count(distinct a.entity_id) from core.audit_log a join office.documents d"
                  " on a.entity = 'office.documents' and a.action = 'insert' and a.entity_id = d.id::text"
                  f" where d.direction = 'in' and d.symbol like '{pattern}'")
    if docs != str(want["ok"]) or logged != f"{want['ok']}/{want['ok']}":
        raise DemoFailed(f"{docs} văn bản đến mang tag {tag}, dòng sổ insert (tổng/văn bản) {logged}")
    ok(f"{docs} văn bản đến mới, mỗi văn bản đúng một dòng sổ insert office.documents — như tiếp nhận từng văn bản")
    events = director.gql(IMPORT_AUDIT, {"id": job["id"]})["core_audit_log"]
    if [(e["action"], e["actor_kind"]) for e in events] != [("import.created", "user"), ("import.finished", "service")]:
        raise DemoFailed(f"sổ kiểm toán của lô: {events}")
    overview = events[1]["overview"] or {}
    if overview.get("ok") != want["ok"] or overview.get("filename") is not None:
        raise DemoFailed(f"tóm tắt dòng import.finished: {overview}")
    ok(f"truongkhoakt đọc sổ: import.created (văn thư) → import.finished (svc-files) #{events[1]['id']}: đạt"
       f" {overview['ok']}, trùng {overview.get('duplicate')}, lỗi {overview.get('failed')} — tên tệp không lên"
       " tóm tắt")

    say(5, "Gửi lại đúng tệp, không kèm khóa — lô mới, không văn bản nào nhân đôi")
    files_sql = ("select count(*) from core.files where created_by::text ="
                 " (select id::text from core.users where username = 'vanthukt')")
    files_before = psql(files_sql)
    status, _, again = send_batch(clerk, data, name, archive=archive)
    if status != 202 or again["id"] == job["id"]:
        raise DemoFailed(f"gửi lại trả {status} {again}")
    redo = wait_batch(clerk, again["id"])
    if (redo["ok"], redo["duplicate"], redo["failed"]) != (0, want["ok"] + want["duplicate"], want["failed"]):
        raise DemoFailed(f"lô gửi lại: {tally(redo)}")
    docs_after, files_after = psql(f"select count(*) from office.documents where direction = 'in' and symbol like"
                                   f" '{pattern}'"), psql(files_sql)
    if docs_after != docs or files_after != files_before:
        raise DemoFailed(f"gửi lại làm đổi số văn bản ({docs} → {docs_after}) hoặc số tệp ({files_before} →"
                         f" {files_after})")
    ok(f"lô {again['id'][:8]}…: {tally(redo)}; vẫn {docs} văn bản, {files_after} tệp của vanthukt — dòng trùng tra"
       " trước khi đưa tệp vào kho, dòng bị từ chối gỡ tệp vừa lưu")

    say(6, "Gửi lại với Idempotency-Key của bước 1")
    status, headers, same = send_batch(clerk, data, name, archive=archive, key=key)
    if status != 200 or same["id"] != job["id"]:
        raise DemoFailed(f"gửi lại cùng khóa trả {status} {same.get('id')}")
    ok(f"200 OK, đúng lô {same['id'][:8]}… ({tally(same)}) — không tạo lô mới")

    say(7, "Lô CSV 5 dòng register=true: tiếp nhận rồi vào sổ, có số đến")
    five = [{k: v for k, v in r.items() if k != "files"} for r in nap_lo_mau.rows(f"{tag}S")[:5]]
    status, _, small = send_batch(clerk, nap_lo_mau.csv_text(five, broken=None).encode(), f"vao-so-{tag}.csv",
                                  query="?register=true")
    if status != 202 or small["register"] is not True:
        raise DemoFailed(f"lô vào sổ trả {status} {small}")
    small = wait_batch(clerk, small["id"])
    numbers = [r["register_number"] for r in batch_rows(clerk, small["id"], "ok")]
    if small["ok"] != 5 or len(numbers) != 5 or None in numbers:
        raise DemoFailed(f"lô vào sổ: {tally(small)}, số đến {numbers}")
    book, _ = call_json("GET", f"{PUBLIC_URL}/api/registers/in/{datetime.now(VN).year}", headers=clerk.auth)
    listed = {e["number"] for e in book["entries"]}
    if not set(numbers) <= listed or book["missing"]:
        raise DemoFailed(f"sổ đến thiếu số {sorted(set(numbers) - listed)} hoặc báo thiếu dòng {book['missing']}")
    ok(f"đạt 5, số đến {', '.join(map(str, sorted(numbers)))}; sổ đến năm {book['year']} có đủ các số đó, không thiếu"
       " dòng nào")

    print(f"\nLô: GET {IMPORTS_URL}/{job['id']} (giao diện \"Nhập lô\" ở bản sau); văn bản đến số ký hiệu có"
          f" \"-{tag}/\" trong danh sách văn bản đến của vanthukt")


# --- F3.14 · Log tập trung (make demo-log-tap-trung) ------------------------------------------------------------
# Dịch vụ log tập trung thu (LOGGED_SERVICES của Makefile, tệp phủ platform/logs/docker-compose.logs.yml)
LOG_COLLECTED = ("apisix", "app-office", "app-ca-nhan", "svc-files", "svc-workflow", "hasura", "keycloak", "postgres")
# Một yêu cầu phát hành đi qua: APISIX (dòng truy cập, mã ở cuối dòng), svc-workflow (office.action.done), Hasura
# (svc-workflow, svc-files gửi mã kèm lời gọi GraphQL: hasura.http-log), svc-files (office.document.rendered…)
LOG_TRACED = ("apisix", "svc-workflow", "hasura", "svc-files")
# Không dòng nào trong kho log được có: token (Bearer, JWT), chuỗi truy vấn của ô tìm kiếm hay của lần đăng nhập
LOG_FORBIDDEN = ("Bearer ey", "eyJ", "?q=", "?code=", "?state=")
LOGS_WAIT_S = 60.0


def traced_services(rows: list[dict[str, Any]]) -> set[str]:
    return {str(r["service"]) for r in rows if r.get("service")}


def logged_since(rows: list[dict[str, Any]], since: str) -> list[dict[str, Any]]:
    """Dòng Parseable nhận từ mốc ``since`` (utc_mark()) trở đi. p_timestamp là giờ UTC, không ghi múi giờ."""
    start = datetime.strptime(since, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    out = []
    for row in rows:
        try:
            at = datetime.fromisoformat(str(row.get("p_timestamp") or ""))
        except ValueError:
            continue
        if (at if at.tzinfo else at.replace(tzinfo=timezone.utc)) >= start:
            out.append(row)
    return out


def postgres_entry(rows: list[dict[str, Any]], marker: str) -> list[dict[str, Any]]:
    """Các dòng PostgreSQL của mục lỗi có ``marker`` trong lời báo: dòng ERROR rồi các dòng cùng tiền tố "%m [%p] "
    (CONTEXT, STATEMENT…). Không dựa vào thứ tự: các dòng tới Parseable cùng lô có cùng p_timestamp, order by xếp tùy
    ý. Không có dòng ERROR mang dấu thì []."""
    rows = [r for r in rows if r.get("service") == "postgres"]
    for row in rows:
        found = re.match(r"(.* \[\d+\] )ERROR:  .*" + re.escape(marker), str(row.get("message") or ""))
        if found:
            return [row] + [r for r in rows if r is not row and str(r.get("message") or "").startswith(found.group(1))]
    return []


def log_leaks(rows: list[dict[str, Any]], secrets: list[str]) -> list[str]:
    """Dòng log nào mang dấu hiệu cấm hay chính giá trị bí mật (token của phiên, mật khẩu…) → "dịch vụ: dấu hiệu".
    Bí mật ngắn dưới 8 ký tự bỏ qua (khớp nhầm); không in giá trị bí mật ra."""
    found = []
    for row in rows:
        text = json.dumps(row, ensure_ascii=False)
        marks = [m for m in LOG_FORBIDDEN if m in text]
        marks += ["giá trị bí mật" for s in secrets if s and len(s) >= 8 and s in text][:1]
        found += [f"{row.get('service') or '?'}: {m}" for m in marks]
    return found


def log_driver(service: str) -> str:
    """Driver log của container đang chạy của dịch vụ (fluentd khi log tập trung đang thu nó); không chạy thì ""."""
    cid = compose("ps", "-q", service).decode().split()
    if not cid:
        return ""
    out = subprocess.run(["docker", "inspect", "-f", "{{.HostConfig.LogConfig.Type}}", cid[0]], capture_output=True,
                         text=True, check=True)
    return out.stdout.strip()


def log_tap_trung() -> None:
    # nạp trong hàm: test của các màn khác thay moc_env bằng bản giả không có các tên này
    import log_tap_trung as lt
    from moc_env import load_env

    print("Màn F3.14 · Log tập trung — một mã X-Request-Id đi qua APISIX → svc-workflow → Hasura, svc-files; Vector"
          " thu log, che lần hai (Hasura, Keycloak, PostgreSQL không tự che: luật riêng), gửi Parseable; tra theo mã ra"
          " dòng của cả bốn; câu SQL lỗi, lần đăng nhập sai vào kho đã che")

    say(1, f"Log tập trung (profile logs): Vector, Parseable chạy; {len(LOG_COLLECTED)} dịch vụ gửi log qua driver"
           " fluentd của Docker")
    turned_on = False
    try:
        request("GET", f"{lt.base_url(ENV)}/api/v1/liveness", timeout=5)
        running = True
    except (HTTPError, OSError):
        running = False
    drivers = {s: log_driver(s) for s in LOG_COLLECTED}
    if not running or any(d != "fluentd" for d in drivers.values()):
        if not (ROOT / "Makefile").is_file():
            raise DemoFailed("log tập trung chưa bật và đây là bản cài (không có Makefile): thêm logs vào"
                             " MOC_EXTRA_PROFILES rồi cài lại (make install) — docs/van-hanh.md mục Log tập trung")
        print(f"   chưa bật: make logs-up (tạo lại {len(LOG_COLLECTED)} container, giữ nguyên dữ liệu; CSDL, Hasura,"
              " Keycloak gián đoạn vài giây)")
        subprocess.run(["make", "--no-print-directory", "logs-up"], cwd=ROOT, check=True)
        turned_on = True
        drivers = {s: log_driver(s) for s in LOG_COLLECTED}
    if any(d != "fluentd" for d in drivers.values()):
        raise DemoFailed(f"dịch vụ chưa gửi log qua fluentd: {drivers}")
    env = load_env()        # make logs-up có thể vừa thêm MOC_LOGS_PASSWORD vào .env
    api = lt.client(env)
    ok(f"Parseable ở {api.base_url} (chỉ 127.0.0.1); driver log: " + ", ".join(f"{s} {d}" for s, d in drivers.items()))

    say(2, "Văn thư phát hành một công văn, yêu cầu phát hành mang X-Request-Id tự đặt")
    rid = f"demo-log-{uuid.uuid4().hex[:12]}"
    mark = utc_mark()
    tag = uuid.uuid4().hex[:6].upper()
    staff, manager, director, clerk = (Session(u) for u in ("chuyenviendt", "totruongdt", "truongkhoa", "vanthu"))
    doc_id, took = issue_outgoing(staff, manager, director, clerk, {
        "type_code": "CV", "recipients": ["Phòng Đào tạo"],
        "summary": f"Về việc tổng hợp nhật ký hệ thống theo mã yêu cầu (demo {tag})",
        "body": "Khoa Công nghệ thông tin gửi Phòng Đào tạo kết quả thử log tập trung.",
    }, public=False, request_id=rid)
    sent = time.monotonic()
    ok(f"X-Request-Id {rid}: APISIX giữ mã client gửi và trả lại ở header; phát hành xong trong {took:.1f} giây")

    say(3, f"Tra Parseable theo mã (make logs-tra ID={rid}) — đợi Vector gửi, tối đa {LOGS_WAIT_S:.0f} giây")
    deadline = time.monotonic() + LOGS_WAIT_S
    rows: list[dict[str, Any]] = []
    while True:
        try:
            rows = api.find(rid, 15)
        except lt.ParseableError as exc:
            raise DemoFailed(str(exc)) from exc
        missing = [s for s in LOG_TRACED if s not in traced_services(rows)]
        if not missing or time.monotonic() > deadline:
            break
        time.sleep(2)
    cli_lines(lt.table(rows, 70))
    if missing:
        raise DemoFailed(f"sau {LOGS_WAIT_S:.0f} giây Parseable chưa có dòng của {', '.join(missing)} mang mã {rid} —"
                         " xem: docker compose --profile logs logs vector")
    ok(f"{len(rows)} dòng của {', '.join(sorted(traced_services(rows)))} cùng mã, sau {time.monotonic() - sent:.0f}"
       " giây kể từ yêu cầu")

    say(4, "Sổ kiểm toán ghi cùng mã: svc-workflow, svc-files gửi mã sang Hasura (core.audit_log.request_id)")
    audit = [line.split("|") for line in psql(
        f"select action, count(*) from core.audit_log where request_id = '{rid}' group by action order by action"
    ).splitlines() if line]
    if not audit:
        raise DemoFailed(f"core.audit_log không có dòng nào mang request_id {rid} (văn bản {doc_id})")
    ok("psql core.audit_log: " + ", ".join(f"{a} ×{n}" for a, n in audit))

    say(5, "PostgreSQL, Keycloak không tự che: một câu SQL lỗi có giá trị giả, một lần đăng nhập bằng tên không có")
    since = utc_mark()
    fake = f"Nguyen Van A {uuid.uuid4().hex[:8]}"           # giá trị trong câu lệnh lỗi: kho log không được có
    try:
        psql(f"do $$ declare ghi_chu text := '{fake}'; begin raise exception '{rid}: lỗi thử log tập trung'; end $$")
        raise DemoFailed("câu SQL thử không lỗi")
    except subprocess.CalledProcessError:
        pass
    user = f"{rid}-{uuid.uuid4().hex[:6]}"                  # Keycloak ghi tên gõ vào ở LOGIN_ERROR: kho không được có
    try:
        call_json("POST", f"{PUBLIC_URL}/realms/moc/protocol/openid-connect/token",
                  form={"grant_type": "password", "client_id": "moc-cli", "username": user,
                        "password": uuid.uuid4().hex, "scope": "openid"})
        raise DemoFailed(f"Keycloak cho đăng nhập bằng tên không có {user}")
    except HTTPError as exc:
        if exc.status not in (400, 401):
            raise
    deadline = time.monotonic() + LOGS_WAIT_S
    while True:
        try:
            pg = logged_since(api.recent("postgres", 10), since)
            kc = logged_since(api.recent("keycloak", 10), since)
        except lt.ParseableError as exc:
            raise DemoFailed(str(exc)) from exc
        entry = postgres_entry(pg, rid)
        statement = [r for r in entry if " STATEMENT:  " in str(r.get("message"))]
        failed = [r for r in kc if "LOGIN_ERROR" in str(r.get("message") or "")]
        if (statement and failed) or time.monotonic() > deadline:
            break
        time.sleep(2)
    cli_lines(lt.table(entry + failed, 70))
    if not entry:
        raise DemoFailed(f"sau {LOGS_WAIT_S:.0f} giây Parseable chưa có dòng ERROR của postgres mang {rid}")
    if not statement or not all(str(r.get("message")).endswith(" STATEMENT:  do [REDACTED]") for r in statement):
        raise DemoFailed("dòng STATEMENT của câu lỗi không có hoặc không bị che")
    if not failed:
        raise DemoFailed(f"sau {LOGS_WAIT_S:.0f} giây Parseable chưa có dòng LOGIN_ERROR của keycloak")
    for service, value, rows_ in (("postgres", fake, pg), ("keycloak", user, kc)):
        if any(value in json.dumps(r, ensure_ascii=False) for r in rows_):
            raise DemoFailed(f"kho log có nguyên văn giá trị {service} phải che")
    ok(f"postgres: {len(entry)} dòng của mục lỗi (ERROR giữ lời báo, câu lệnh chỉ còn từ đầu); keycloak: LOGIN_ERROR"
       " không còn tên gõ vào")

    say(6, "Kho log cần đăng nhập; dòng trong kho không có token, cookie, chuỗi truy vấn")
    for who_, auth in (("không đăng nhập", None), ("sai mật khẩu", lt.auth_header(lt.USER, uuid.uuid4().hex))):
        try:
            request("GET", f"{api.base_url}/api/v1/logstream", headers={"Authorization": auth} if auth else None,
                    timeout=10)
            raise DemoFailed(f"Parseable cho đọc danh sách luồng khi {who_}")
        except HTTPError as exc:
            if exc.status not in (401, 403):
                raise
            ok(f"{who_}: HTTP {exc.status}")
    leaked = log_leaks(rows + pg + kc, [clerk.token, env.get("MOC_LOGS_PASSWORD", ""),
                                        env.get("HASURA_ADMIN_SECRET", ""), env.get("MOC_ACTION_SECRET", "")])
    if leaked:
        raise DemoFailed(f"kho log có dấu hiệu cấm: {', '.join(leaked[:6])}")
    ok(f"không dòng nào chứa {', '.join(LOG_FORBIDDEN)}, token phiên của văn thư hay khóa của hệ thống")

    say(7, "docker logs vẫn đọc được (dual logging của Docker): bản cục bộ cũng có mã")
    time.sleep(max(0.0, sent + LOG_FLUSH_S - time.monotonic()))
    local = service_logs(mark, "apisix", "svc-workflow")
    without = [s for s, text in local.items() if rid not in text]
    if without:
        raise DemoFailed(f"docker compose logs của {', '.join(without)} không có mã {rid}")
    ok("docker compose logs apisix, svc-workflow: có dòng mang mã")

    say(8, "Vector chạy lại (cập nhật, sự cố): dòng đầu tiên một dịch vụ đang im ghi sau đó vẫn tới kho")
    began = time.monotonic()
    compose("--profile", "logs", "restart", "vector")
    # Kết nối cũ của driver fluentd tới Vector đã chết. Gọi qua APISIX mỗi 2 giây, cùng một mã: mã có trong kho là
    # Vector đã nhận lại
    probe = f"{rid}-v"
    deadline = time.monotonic() + LOGS_WAIT_S
    while True:
        request("GET", f"{PUBLIC_URL}/", headers={"X-Request-Id": probe}, timeout=10)
        try:
            back = api.find(probe, 5)
        except lt.ParseableError as exc:
            raise DemoFailed(str(exc)) from exc
        if back or time.monotonic() > deadline:
            break
        time.sleep(2)
    if not back:
        raise DemoFailed(f"sau {LOGS_WAIT_S:.0f} giây Vector chạy lại vẫn chưa gửi dòng nào của apisix mang {probe}")
    up = time.monotonic() - began
    # postgres im từ bước 5: dòng ERROR này là lần ghi đầu tiên của nó sau khi Vector chạy lại
    marker = f"{rid}-sau-khoi-dong-lai"
    try:
        psql(f"do $$ begin raise exception '{marker}'; end $$")
        raise DemoFailed("câu SQL thử không lỗi")
    except subprocess.CalledProcessError:
        pass
    asked = time.monotonic()
    deadline = asked + LOGS_WAIT_S
    while True:
        try:
            entry = postgres_entry(api.recent("postgres", 10), marker)
        except lt.ParseableError as exc:
            raise DemoFailed(str(exc)) from exc
        if entry or time.monotonic() > deadline:
            break
        time.sleep(2)
    if not entry:
        raise DemoFailed(f"sau {LOGS_WAIT_S:.0f} giây Parseable chưa có dòng ERROR của postgres ghi sau khi Vector chạy"
                         " lại: driver fluentd gửi vào kết nối đã chết mà không biết")
    ok(f"Vector nhận lại sau {up:.0f} giây; dòng ERROR đầu tiên của postgres sau đó tới kho sau"
       f" {time.monotonic() - asked:.0f} giây")

    print(f"\n   Giao diện: {api.base_url} — tài khoản {lt.USER}, mật khẩu là MOC_LOGS_PASSWORD trong .env; giữ"
          f" {env.get('MOC_LOGS_RETENTION_DAYS') or '7'} ngày")
    if turned_on:
        print(f"   Màn này đã bật log tập trung và để nguyên. Tắt: make logs-down (tạo lại {len(LOG_COLLECTED)}"
              " container)")
    else:
        print("   Tắt: bỏ logs khỏi MOC_EXTRA_PROFILES (nếu có) rồi make logs-down")

# --- F3.13 · Cảnh báo vận hành ra chuông (make demo-canh-bao) ---------------------------------------------------------

ALERT_BELL = """query Alerts {
  core_notifications(where: {kind: {_eq: "ops.alert"}}, order_by: {id: desc}, limit: 20) { id data }
}"""
# Alertmanager gom 30 giây trước lần gửi đầu của một nhóm, gửi phần đổi (hết cảnh báo) mỗi phút (alertmanager.yml)
ALERT_WAIT_S = 120
# Gọi API của Alertmanager từ một container chỉ ở mạng moc (svc-files): tới được thì in "reached"
ALERTMANAGER_PROBE = """
import urllib.error, urllib.request
try:
    urllib.request.urlopen("http://alertmanager:9093/-/ready", timeout=5)
    print("reached")
except urllib.error.HTTPError:
    print("reached")
except OSError as exc:
    print(type(exc).__name__)
"""


def in_alertmanager(url: str, body: Any, *headers: str) -> bytes:
    """POST JSON bằng wget trong container alertmanager: Alertmanager, svc-workflow không mở cổng ra ngoài."""
    args = ["exec", "-T", "alertmanager", "wget", "-q", "-O", "-", "--header", "Content-Type: application/json"]
    for header in headers:
        args += ["--header", header]
    return compose(*args, "--post-data", json.dumps(body), url)


def alert_rows(component: str, status: str) -> list[dict[str, str]]:
    """Người nhận thông báo ops.alert của thành phần giả, theo vai trò và đơn vị (đọc thẳng CSDL)."""
    out = psql("select u.role, n.tenant_id from core.notifications n join core.users u on u.tenant_id = n.tenant_id"
               f" and u.id = n.user_id where n.kind = 'ops.alert' and n.data->>'component' = '{component}'"
               f" and n.data->>'status' = '{status}'")
    return [dict(zip(("role", "tenant"), line.split("|"))) for line in out.splitlines() if line]


def canh_bao() -> None:
    print("Màn F3.13 · Cảnh báo vận hành — Prometheus tính luật, Alertmanager gom rồi gọi svc-workflow: mỗi cảnh báo"
          " thành thông báo ở chuông của quản trị mọi đơn vị (kèm email, webhook… nếu đã bật kênh); hết sự cố có thông"
          " báo hết cảnh báo; gọi svc-workflow bằng token sai bị từ chối")

    say(1, "Prometheus gửi cảnh báo đang bật cho Alertmanager; Alertmanager có token gọi svc-workflow")
    try:
        raw = compose("exec", "-T", "prometheus", "wget", "-q", "-O", "-", "http://localhost:9090/api/v1/alertmanagers")
        urls = [a.get("url", "") for a in json.loads(raw)["data"]["activeAlertmanagers"]]
    except (subprocess.CalledProcessError, ValueError, KeyError) as exc:
        raise DemoFailed(f"không hỏi được Prometheus: {exc}") from exc
    if not any("alertmanager:9093" in u for u in urls):
        raise DemoFailed(f"Prometheus chưa nối Alertmanager: {urls}")
    try:
        compose("exec", "-T", "alertmanager", "test", "-s", "/tmp/moc-alert-token")
    except subprocess.CalledProcessError as exc:
        raise DemoFailed("Alertmanager chạy cấu hình không gửi: .env chưa có MOC_ALERT_TOKEN — make up (tự thêm), bản"
                         " cài thì make install lại (docs/van-hanh.md mục Cảnh báo)") from exc
    ok(f"Prometheus → {', '.join(urls)}; Alertmanager có token (tệp trên tmpfs, không in ra)")

    say(2, "Giả một sự cố: đẩy cảnh báo ComponentDown của một thành phần giả vào Alertmanager")
    component = f"demo-{uuid.uuid4().hex[:6]}"
    starts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    alert = {"labels": {"alertname": "DemoCanhBao", "severity": "warning", "component": component},
             "annotations": {"summary": f"Thành phần {component} gián đoạn (màn demo, không phải sự cố thật)"},
             "startsAt": starts}
    tenants = set(psql("select distinct tenant_id from core.users where role = 'tenant_admin' and enabled").split())
    in_alertmanager("http://localhost:9093/api/v2/alerts", [alert])
    admin = Session("quantri")
    started = time.monotonic()
    # svc-workflow ghi lần lượt từng đơn vị: chờ tới khi chuông của quantri có và mọi đơn vị đã có dòng
    while True:
        rows = [r for r in admin.gql(ALERT_BELL)["core_notifications"]
                if r["data"].get("component") == component and r["data"].get("status") == "firing"]
        got = alert_rows(component, "firing")
        if rows and {r["tenant"] for r in got} >= tenants:
            break
        if time.monotonic() - started > ALERT_WAIT_S:
            raise DemoFailed(f"sau {ALERT_WAIT_S} giây chuông của quantri {'có' if rows else 'chưa có'} cảnh báo"
                             f" {component}, {len({r['tenant'] for r in got})}/{len(tenants)} đơn vị có thông báo")
        time.sleep(3)
    ok(f"sau {time.monotonic() - started:.0f} giây chuông của quantri (quản trị đơn vị): «Cảnh báo vận hành:"
       f" {rows[0]['data']['message']}»")
    if {r["role"] for r in got} != {"tenant_admin"} or {r["tenant"] for r in got} != tenants:
        raise DemoFailed(f"cảnh báo phải tới quản trị của mọi đơn vị ({len(tenants)}), không ai khác: {got}")
    ok(f"{len(got)} thông báo cho quản trị của {len(tenants)} đơn vị; văn thư, lãnh đạo, chuyên viên không nhận")

    say(3, "Hết sự cố: Alertmanager gửi «đã hết», mỗi quản trị thêm một thông báo; gửi lại không thêm dòng")
    alert["endsAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    in_alertmanager("http://localhost:9093/api/v2/alerts", [alert])
    started = time.monotonic()
    while len(alert_rows(component, "resolved")) < len(got):
        if time.monotonic() - started > ALERT_WAIT_S:
            raise DemoFailed(f"sau {ALERT_WAIT_S} giây chưa có thông báo hết cảnh báo {component}")
        time.sleep(3)
    if len(alert_rows(component, "firing")) != len(got):
        raise DemoFailed("cảnh báo đang bật bị ghi thêm lần nữa")
    ok(f"sau {time.monotonic() - started:.0f} giây: «Hết cảnh báo: {alert['annotations']['summary']}»; mỗi quản trị"
       " đúng một thông báo bật, một thông báo hết")

    say(4, "Gọi thẳng svc-workflow POST /ops/alerts bằng token sai (từ trong mạng nội bộ)")
    try:
        in_alertmanager("http://svc-workflow:8000/ops/alerts", {"alerts": [alert]}, "Authorization: Bearer sai-token")
    except subprocess.CalledProcessError as exc:
        if b"401" not in (exc.stderr or b""):
            raise DemoFailed(f"svc-workflow trả lỗi khác 401: {exc.stderr!r}") from exc
    else:
        raise DemoFailed("svc-workflow nhận cảnh báo với token sai")
    ok("401 — gọi thẳng svc-workflow mà không có token thì không ghi được thông báo")

    say(5, "API của Alertmanager (đẩy cảnh báo, tạo silence, không đăng nhập) chỉ ở mạng alerts: svc-files không tới")
    reached = compose("exec", "-T", "svc-files", "python", "-c", ALERTMANAGER_PROBE).decode().strip()
    if reached == "reached":
        raise DemoFailed("svc-files (mạng moc) gọi được API của Alertmanager: alertmanager phải chỉ ở mạng alerts")
    ok(f"svc-files → alertmanager:9093: {reached}; chỉ Prometheus, svc-workflow chung mạng với Alertmanager")
    # thông báo giả của màn: đánh dấu đã đọc để chuông của quản trị không đếm (email, SMS… đã gửi nếu kênh đang bật)
    psql(f"update core.notifications set read_at = now() where kind = 'ops.alert' and read_at is null"
         f" and data->>'component' = '{component}'")


# ------------------------------------------------------------------------------------------- cắm ứng dụng bằng manifest

APP_MANIFEST = "apps/bang-tin/app.yaml"
APP_NAME, APP_PATH = "bang-tin", "/bang-tin/"
APP_CALLBACK = f"{PUBLIC_URL}/bang-tin/dang-nhap"


def need_sources(screen: str, *rels: str) -> None:
    """Màn cắm ứng dụng đọc gói ứng dụng mẫu trong apps/ của thư mục mã nguồn; bản cài (make install) không chép apps/,
    vì gói ứng dụng nằm ngoài lõi. Kiểm trước khi gỡ hay đổi gì: thiếu tệp mà vẫn chạy thì màn gỡ ứng dụng đang cài
    rồi mới dừng."""
    missing = [rel for rel in rels if not (ROOT / rel).exists()]
    if missing:
        raise DemoFailed(f"không có {', '.join(missing)}: bản cài không chép apps/ (gói ứng dụng nằm ngoài lõi). Chạy "
                         f"make demo-{screen} trong thư mục mã nguồn; chưa gỡ hay đổi gì")


def app_query() -> str:
    """Đúng câu GraphQL trang Bảng tin gửi (apps/bang-tin/public/tin.js)."""
    js = (ROOT / "apps" / "bang-tin" / "public" / "tin.js").read_text(encoding="utf-8")
    found = re.search(r"export const QUERY_TIN = `([^`]*)`", js)
    if not found:
        raise DemoFailed("apps/bang-tin/public/tin.js không còn QUERY_TIN")
    return found.group(1)


def catalog_queries() -> tuple[str, str]:
    """Đúng hai câu GraphQL trang Danh mục ứng dụng (/ung-dung) gửi (apps/office/app/utils/apps.ts): mọi vai trò;
    lãnh đạo, quản trị đơn vị (thêm băm manifest, ứng dụng đã gỡ)."""
    ts = (ROOT / "apps" / "office" / "app" / "utils" / "apps.ts").read_text(encoding="utf-8")
    found = [re.search(rf"export const {name} = `([^`]*)`", ts) for name in ("APPS_QUERY", "APPS_QUERY_LEADER")]
    if not (found[0] and found[1]):
        raise DemoFailed("apps/office/app/utils/apps.ts không còn APPS_QUERY, APPS_QUERY_LEADER")
    return found[0].group(1), found[1].group(1)


def catalog_row(session: Session, query: str) -> dict[str, Any] | None:
    return next((a for a in session.gql(query)["core_app_catalog"] if a["name"] == APP_NAME), None)


def moc_app(*args: str) -> str:
    """`moc app …` đúng như người vận hành gõ; lỗi thì in đúng thông báo của lệnh (bước nào)."""
    code, out, err = moc("app", *args)
    if code != 0:
        raise DemoFailed(f"moc app {' '.join(args)} thoát {code}: {(err or out).strip()[-600:]}")
    return out


def git_state() -> str | None:
    """Tệp nào của cây mã nguồn đang khác commit (kể cả tệp mới không bị .gitignore); không phải bản git → None."""
    r = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=all"], capture_output=True,
                       text=True)
    return r.stdout if r.returncode == 0 else None


def state_digest() -> str:
    """Băm mọi tệp trong .moc-apps/ (không in nội dung: có bí mật)."""
    base = ROOT / ".moc-apps"
    h = hashlib.sha256()
    for path in sorted(p for p in base.rglob("*") if p.is_file()) if base.is_dir() else []:
        h.update(str(path.relative_to(base)).encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def app_container(name: str = APP_NAME) -> list[str]:
    """Container của service app-<tên> trong project compose của thư mục này (tên project tùy nơi cài); gỡ rồi thì
    tệp phủ không còn service đó, compose báo lỗi — coi như không có container."""
    import ung_dung
    proc = subprocess.run([*ung_dung.COMPOSE, "ps", "-q", f"app-{name}"], cwd=ROOT,
                          env=ung_dung.System(ROOT).env(), capture_output=True, text=True)
    return proc.stdout.split() if proc.returncode == 0 else []


# Chạy trong container ứng dụng: in các host:cổng mở được kết nối TCP (tên không phân giải được cũng là không tới được)
NET_PROBE = """import socket, sys
for target in sys.argv[1:]:
    host, port = target.rsplit(":", 1)
    try:
        socket.create_connection((host, int(port)), timeout=3).close()
    except OSError:
        continue
    print(target)
"""


def app_reach(*targets: str) -> list[str]:
    """host:cổng mà container app-bang-tin tới được (mạng apps: chỉ APISIX)."""
    import ung_dung
    proc = subprocess.run([*ung_dung.COMPOSE, "exec", "-T", f"app-{APP_NAME}", "python3", "-c", NET_PROBE, *targets],
                          cwd=ROOT, env=ung_dung.System(ROOT).env(), capture_output=True, text=True)
    if proc.returncode != 0:
        raise DemoFailed(f"không chạy được thử mạng trong app-{APP_NAME}: {proc.stderr.strip()[-300:]}")
    return proc.stdout.split()


def app_clients(name: str = APP_NAME) -> list[str]:
    import tenants
    return sorted(c["clientId"] for c in tenants.connect().clients()
                  if c.get("clientId") in (f"app-{name}", f"app-{name}-svc"))


def app_metadata() -> tuple[bool, bool]:
    """(bảng bang_tin.tin còn được track, trigger app_bang_tin còn) theo metadata Hasura đang chạy."""
    import ung_dung
    md = ung_dung.System(ROOT).metadata({"type": "export_metadata", "version": 2, "args": {}})["metadata"]
    tables = [t for src in md.get("sources", []) for t in src.get("tables", [])]
    tracked = any(t["table"] == {"schema": "bang_tin", "name": "tin"} for t in tables)
    trigger = any(e["name"] == "app_bang_tin" for t in tables for e in t.get("event_triggers", []))
    return tracked, trigger


def sso_fragment(browser: Any, client_id: str, redirect_uri: str) -> tuple[str, str]:
    """Như oidc-client-ts của trang (apps/bang-tin/public/auth.js): code + PKCE S256, response_mode=fragment — mã cấp
    quyền nằm sau dấu #, không tới máy chủ nào. Phiên SSO phải đủ: Keycloak hỏi mật khẩu là lỗi."""
    import urllib.parse

    verifier = base64.urlsafe_b64encode(uuid.uuid4().bytes + uuid.uuid4().bytes).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = uuid.uuid4().hex
    query = urllib.parse.urlencode({"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code",
                                    "response_mode": "fragment", "scope": "openid profile", "state": state,
                                    "code_challenge": challenge, "code_challenge_method": "S256"})
    resp = browser.opener.open(f"{PUBLIC_URL}/realms/{ENV.get('MOC_REALM', 'moc')}/protocol/openid-connect/auth?"
                               f"{query}", timeout=30)
    url = urllib.parse.urlsplit(resp.geturl())
    params = urllib.parse.parse_qs(url.fragment)
    if url.path != urllib.parse.urlsplit(redirect_uri).path or "code" not in params:
        raise DemoFailed(f"{client_id}: Keycloak không chuyển về {redirect_uri}#code=… (dừng ở {url.path}) — SSO "
                         "hỏng hoặc client chưa có")
    if params.get("state") != [state]:
        raise DemoFailed(f"{client_id}: state trả về không khớp")
    return params["code"][0], verifier


def cai_ung_dung() -> None:
    from demo_ca_nhan import OWNER, Browser, as_session, claims_of, exchange

    print("Cắm ứng dụng thứ ba bằng một lệnh — Bảng tin đơn vị (apps/bang-tin): không sửa tệp nào của lõi")
    need_sources("cai-ung-dung", APP_MANIFEST, "apps/bang-tin/public/tin.js", "apps/office/app/utils/apps.ts")
    listed = json.loads(moc_app("list", "--json"))["apps"]
    if any(a["name"] == APP_NAME and (a["installed"] or a["removing"]) for a in listed):
        moc_app("remove", APP_NAME)
        print("   (gỡ bản cài từ lần chạy trước, dữ liệu giữ)")
    git_before = git_state()
    query = app_query()

    say(1, f"moc app install {APP_MANIFEST} --dry-run — kế hoạch từng bước, chưa đổi gì")
    before = state_digest()
    out = moc_app("install", APP_MANIFEST, "--dry-run")
    print("\n".join(f"   {ln}" for ln in out.strip().splitlines()))
    if "8/8 Hasura" not in out or state_digest() != before or app_container():
        raise DemoFailed("--dry-run phải in đủ 8 bước và không đổi .moc-apps/, không tạo container")
    ok("8 bước, .moc-apps/ không đổi, chưa có container")

    say(2, f"moc app install {APP_MANIFEST} — một lệnh, không sửa tệp nào của lõi")
    started = time.monotonic()
    out = moc_app("install", APP_MANIFEST)
    print("\n".join(f"   {ln}" for ln in out.strip().splitlines()))
    tracked, trigger = app_metadata()
    if not (app_container() and tracked and trigger and app_clients() == [f"app-{APP_NAME}", f"app-{APP_NAME}-svc"]):
        raise DemoFailed(f"sau khi cài: container {app_container()}, bảng {tracked}, trigger {trigger}, client "
                         f"{app_clients()}")
    ok(f"xong sau {time.monotonic() - started:.0f} giây: container app-{APP_NAME}, client app-{APP_NAME} + "
       f"app-{APP_NAME}-svc, bảng bang_tin.tin, trigger app_bang_tin")

    say(3, f"Mở {PUBLIC_URL}{APP_PATH} — route APISIX của ứng dụng (thêm vào tệp chạy, tệp lõi không đổi)")
    status, headers, body = request("GET", f"{PUBLIC_URL}{APP_PATH}")
    csp = next((v for k, v in headers.items() if k.lower() == "content-security-policy"), "")
    if status != 200 or "Bảng tin đơn vị" not in body.decode() or "script-src 'self'" not in csp:
        raise DemoFailed(f"{APP_PATH} trả {status}, CSP {csp!r}")
    config = json.loads(request("GET", f"{PUBLIC_URL}{APP_PATH}config.json")[2])
    if config != {"realm": ENV.get("MOC_REALM", "moc"), "clientId": f"app-{APP_NAME}"}:
        raise DemoFailed(f"config.json: {config}")
    ok(f"200, {len(body)} byte, CSP script-src 'self'; config.json: client app-{APP_NAME}")

    say(4, f"{OWNER} đăng nhập Văn phòng điện tử rồi mở Bảng tin: client riêng, PKCE S256, không hỏi lại mật khẩu")
    browser = Browser()
    code, verifier, _ = browser.authorize("app-office", f"{PUBLIC_URL}/", OWNER)
    exchange("app-office", f"{PUBLIC_URL}/", code, verifier)
    code, verifier = sso_fragment(browser, f"app-{APP_NAME}", APP_CALLBACK)
    token = exchange(f"app-{APP_NAME}", APP_CALLBACK, code, verifier)["access_token"]
    claims = claims_of(token)
    hasura = claims.get("https://hasura.io/jwt/claims", {})
    if claims.get("azp") != f"app-{APP_NAME}" or not hasura.get("x-hasura-tenant-id"):
        raise DemoFailed(f"token của app-{APP_NAME} thiếu claim Hasura: azp {claims.get('azp')}")
    reader = as_session(OWNER, token)
    reader.gql(query)
    ok(f"token azp app-{APP_NAME}, vai trò {hasura.get('x-hasura-default-role')}, đơn vị của người dùng; câu GraphQL "
       "của trang chạy được trên bang_tin.tin")
    # Trang Danh mục ứng dụng của Văn phòng điện tử (core.app_catalog): chuyên viên thấy ứng dụng vừa cài để mở, không
    # đọc được băm manifest, ứng dụng đã gỡ
    catalog_q, catalog_leader_q = catalog_queries()
    version = re.search(r"^version: (\S+)$", (ROOT / APP_MANIFEST).read_text(encoding="utf-8"), re.M)
    entry = catalog_row(gv(OWNER), catalog_q)
    if not entry or entry["path"] != APP_PATH.rstrip("/") or entry["version"] != (version and version.group(1)):
        raise DemoFailed(f"Danh mục ứng dụng của {OWNER} không có {APP_NAME} đúng đường, phiên bản: {entry}")
    try:
        gv(OWNER).gql(catalog_leader_q)
    except RuntimeError:     # Hasura: field 'manifest_sha256' not found — vai trò không được đọc cột
        pass
    else:
        raise DemoFailed(f"{OWNER} (chuyên viên) đọc được băm manifest, ứng dụng đã gỡ trong Danh mục ứng dụng")
    ok(f"Danh mục ứng dụng (/ung-dung) của {OWNER}: \"{entry['title']}\" {entry['version']} ở {entry['path']}/; "
       "băm manifest, ứng dụng đã gỡ: chỉ lãnh đạo, quản trị đơn vị")

    say(5, "Văn thư vào sổ một văn bản đến thường và một văn bản hạn chế → lõi phát sự kiện, ứng dụng nhận qua webhook")
    tag = uuid.uuid4().hex[:6].upper()
    d = {"type_code": "CV", "issuer_name": "UBND tỉnh Hưng Yên", "summary": f"Về việc thử bảng tin đơn vị ({tag})"}
    sent = time.monotonic()
    normal = receive_bare(d, f"{tag}/BT-VP")
    secret = receive_bare({**d, "summary": f"Văn bản hạn chế thử bảng tin ({tag})"}, f"{tag}/BT-HC", restricted=True)
    director = gv("truongkhoa")
    seen: list[dict[str, Any]] = []
    while time.monotonic() - sent < 60 and not seen:
        seen = [t for t in director.gql(query)["bang_tin_tin"] if t["document_id"] == normal]
        time.sleep(0 if seen else 1)
    if not seen or seen[0]["kind"] != "office.document.registered" or not seen[0].get("document"):
        raise DemoFailed(f"sau 60 giây lãnh đạo khoa chưa thấy tin của văn bản {tag}/BT-VP: {seen}")
    ok(f"lãnh đạo khoa thấy tin \"{seen[0]['document']['symbol']} — Văn bản đến đã vào sổ\" sau "
       f"{time.monotonic() - sent:.1f} giây (Event Trigger → APISIX cổng hook 9081 → app-{APP_NAME}:8081 → token, "
       "GraphQL qua APISIX bằng danh tính dịch vụ)")
    leaked = psql(f"select (select count(*) from core.app_events where document_id = '{secret}') + "
                  f"(select count(*) from bang_tin.tin where document_id = '{secret}')")
    if leaked != "0":
        raise DemoFailed(f"văn bản hạn chế lọt vào luồng sự kiện của ứng dụng ({leaked} dòng)")
    ok("văn bản hạn chế: không có trong core.app_events, ứng dụng không biết nó tồn tại")
    if any(t["document_id"] == normal for t in reader.gql(query)["bang_tin_tin"]):
        raise DemoFailed(f"{OWNER} thấy tin của văn bản chưa được giao cho mình")
    ok(f"{OWNER} (chưa được giao văn bản đó) không thấy tin: Bảng tin theo đúng quyền xem văn bản của lõi")
    reach = app_reach("apisix:9080", "keycloak:8080", "hasura:8080", "postgres:5432", "svc-files:8000")
    if reach != ["apisix:9080"]:
        raise DemoFailed(f"container app-{APP_NAME} (mạng apps) phải chỉ tới được apisix:9080, đang tới được: {reach}")
    try:
        request("POST", f"{PUBLIC_URL}/su-kien/{APP_NAME}", data=b"{}", headers={"Content-Type": "application/json"})
        public_hook = 200
    except HTTPError as exc:
        public_hook = exc.status
    if public_hook != 404:
        raise DemoFailed(f"POST /su-kien/{APP_NAME} ở cổng công khai phải 404 (route hook chỉ ở cổng 9081): "
                         f"{public_hook}")
    ok(f"app-{APP_NAME} chỉ tới được APISIX (Keycloak, Hasura, PostgreSQL, svc-files: không); route hook chỉ ở cổng "
       "nội bộ 9081, cổng công khai trả 404")

    say(6, f"Chạy lại moc app install {APP_MANIFEST}: không tạo gì mới")
    container, digest = app_container(), state_digest()
    migrations = psql(f"select count(*) from core.app_migrations where app = '{APP_NAME}'")
    entry = catalog_row(gv("truongkhoa"), catalog_leader_q)
    out = moc_app("install", APP_MANIFEST)
    if (app_container() != container or state_digest() != digest
            or psql(f"select count(*) from core.app_migrations where app = '{APP_NAME}'") != migrations
            or "client đã có" not in out or "không có migration mới" not in out):
        raise DemoFailed("cài lại phải giữ nguyên container, .moc-apps/, migration, client:\n" + out)
    ok("cùng container, .moc-apps/ không đổi một byte, không migration mới, client đã có")
    sha = hashlib.sha256((ROOT / APP_MANIFEST).read_bytes()).hexdigest()
    if not entry or entry["manifest_sha256"] != sha or catalog_row(gv("truongkhoa"), catalog_leader_q) != entry:
        raise DemoFailed(f"Danh mục ứng dụng của lãnh đạo: băm manifest phải là SHA-256 của {APP_MANIFEST} ({sha}), "
                         f"cài lại không đổi dòng nào: {entry}")
    ok(f"Danh mục ứng dụng của lãnh đạo khoa: băm manifest {sha[:12]}… = sha256sum {APP_MANIFEST}; cài lại không đổi "
       "lúc cài, lúc cập nhật")

    say(7, f"moc app remove {APP_NAME}: route, client, trigger, container mất; dữ liệu còn")
    rows = psql(f"select count(*) from bang_tin.tin where document_id = '{normal}'")
    print("\n".join(f"   {ln}" for ln in moc_app("remove", APP_NAME).strip().splitlines()))
    _, _, body = request("GET", f"{PUBLIC_URL}{APP_PATH}")
    tracked, trigger = app_metadata()
    problems = [what for what, bad in (("route", "Bảng tin đơn vị" in body.decode(errors="replace")),
                                        ("container", bool(app_container())), ("client", bool(app_clients())),
                                        ("trigger", trigger), ("bảng còn track", tracked)) if bad]
    if problems:
        raise DemoFailed(f"sau khi gỡ còn: {', '.join(problems)}")
    if psql(f"select count(*) from bang_tin.tin where document_id = '{normal}'") != rows or rows == "0":
        raise DemoFailed("gỡ ứng dụng không được xóa dữ liệu")
    if (ROOT / ".moc-apps" / "apisix.yaml").read_bytes() != (ROOT / "platform" / "apisix" / "apisix.yaml").read_bytes():
        raise DemoFailed(".moc-apps/apisix.yaml phải giống hệt tệp lõi khi không còn ứng dụng")
    ok(f"/bang-tin/ không còn là Bảng tin; không container, client, trigger; bang_tin.tin còn {rows} dòng của "
       "văn bản thử; tệp chạy APISIX giống hệt tệp lõi")
    gone, entry = catalog_row(gv(OWNER), catalog_q), catalog_row(gv("truongkhoa"), catalog_leader_q)
    if gone or not entry or not entry["removed_at"]:
        raise DemoFailed(f"Danh mục ứng dụng sau khi gỡ: {OWNER} vẫn thấy {gone}; lãnh đạo thấy {entry}")
    ok(f"Danh mục ứng dụng: {OWNER} không còn thấy {APP_NAME}; lãnh đạo khoa thấy \"Đã gỡ\" lúc {entry['removed_at']}")

    say(8, "Tệp của lõi không đổi: git status trước và sau giống hệt (trạng thái ứng dụng ở .moc-apps/, ngoài git)")
    git_after = git_state()
    if git_before is None:
        ok("không phải thư mục git (bản cài) — bỏ qua so sánh")
        return
    if git_after != git_before:
        raise DemoFailed("cây mã nguồn đổi trong lúc cài/gỡ:\n" + git_after)
    stat = subprocess.run(["git", "-C", str(ROOT), "diff", "--stat"], capture_output=True, text=True).stdout.strip()
    print(f"   git diff --stat: {stat or '(trống)'}")
    ok("không tệp nào được theo dõi trong git đổi; không tệp mới ngoài .gitignore")


# ------------------------------------------------------------------------------- quy trình của ứng dụng qua lõi (#301)

QT_MANIFEST = "apps/nghi-phep/app.yaml"
QT_NAME, QT_PATH = "nghi-phep", "/nghi-phep/"
QT_CLIENT = f"app-{QT_NAME}"
QT_CALLBACK = f"{PUBLIC_URL}/nghi-phep/dang-nhap"
QT_API = f"{PUBLIC_URL}/api/workflow/nghi-phep"
QT_PROCESS, QT_FORM_DON, QT_FORM_DUYET = "nghi-phep.don", "nghi-phep.don", "nghi-phep.duyet"
# seed/users.csv, Khoa CNTT: giảng viên và trưởng Bộ môn KTPM cùng phòng; tổ trưởng Đào tạo là trưởng phòng khác của
# cùng đơn vị (scripts/tests/test_nghi_phep.py kiểm theo tệp seed)
QT_STAFF, QT_MANAGER, QT_OTHER = "giangvienktpm", "truongbmktpm", "totruongdt"
# Dữ liệu sai và mã lỗi lõi phải trả, trùng ca thử dùng chung apps/nghi-phep/forms/*.cases.json (test kiểm)
QT_BAD_RANGE = {"denNgay": "x-moc-range"}
QT_WRONG_TYPE, QT_BAD_TYPE = "nghi-mat", {"loai": "enum"}
QT_WRONG_DECISION, QT_BAD_DECISION = "Đồng ý", {"quyetDinh": "enum"}


def leave_request(today: Any, tag: str) -> dict[str, str]:
    """Đơn hợp lệ theo forms/don.json: phép năm từ một tuần sau, ba ngày; lý do ở dạng NFC như form dọn."""
    start = today + timedelta(days=7)
    return {"loai": "phep-nam", "tuNgay": start.isoformat(), "denNgay": (start + timedelta(days=2)).isoformat(),
            "lyDo": unicodedata.normalize("NFC", f"Về quê dự đám cưới em gái ({tag})")}


def bad_range(req: dict[str, str]) -> dict[str, str]:
    """Cùng đơn, đến ngày trước từ ngày: lõi phải trả 422 {"denNgay": "x-moc-range"}."""
    return {**req, "tuNgay": req["denNgay"], "denNgay": req["tuNgay"]}


def poison_bpmn(xml: str) -> str:
    """BPMN của ứng dụng chèn thêm một scriptTask chạy lệnh trên máy chủ ngay sau lúc gửi đơn — lõi phải từ chối khi
    cài, trước khi đổi gì."""
    flow = 'sourceRef="guiDon" targetRef="duyet"/>'
    if xml.count(flow) != 1:
        raise ValueError("BPMN của nghi-phep không còn luồng guiDon → duyet")
    script = ('sourceRef="guiDon" targetRef="chayMa"/>\n'
              '    <scriptTask id="chayMa" name="Chạy lệnh trên máy chủ" scriptFormat="groovy">'
              '<script>"id".execute()</script></scriptTask>\n'
              '    <sequenceFlow id="f0" sourceRef="chayMa" targetRef="duyet"/>')
    return xml.replace(flow, script)


def poison_copy(target: pathlib.Path) -> pathlib.Path:
    """Chép apps/nghi-phep sang thư mục tạm (ngoài cây mã nguồn), thay BPMN bằng bản độc → đường tới app.yaml."""
    import shutil
    src = ROOT / "apps" / QT_NAME
    shutil.copytree(src, target, ignore=shutil.ignore_patterns("node_modules", "tests"))
    bpmn = target / "workflow" / "don-nghi-phep.bpmn20.xml"
    bpmn.write_text(poison_bpmn(bpmn.read_text(encoding="utf-8")), encoding="utf-8")
    return target / "app.yaml"


def qt_call(token: str, method: str, path: str, data: Any = None) -> tuple[int, Any]:
    """API quy trình chung của lõi, gọi như trang (apps/nghi-phep/public/don.js) → (mã HTTP, thân JSON hoặc None)."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    body = None
    if data is not None:
        body = json.dumps({"data": data}, ensure_ascii=False).encode()
        headers["Content-Type"] = "application/json"
    try:
        status, _, raw = request(method, f"{QT_API}{path}", data=body, headers=headers)
    except HTTPError as exc:
        status, raw = exc.status, exc.body.encode()
    try:
        return status, json.loads(raw) if raw else None
    except ValueError:
        return status, None


def qt_ok(token: str, method: str, path: str, data: Any = None, *, want: int = 200) -> Any:
    status, body = qt_call(token, method, path, data)
    if status != want:
        raise DemoFailed(f"{method} /api/workflow/{QT_NAME}{path} trả {status} (cần {want}): {json.dumps(body)[:300]}")
    return body


def qt_list(token: str, path: str) -> list[dict[str, Any]]:
    """GET một danh sách của API chung (/processes, /tasks): phải là mảng các đối tượng."""
    body = qt_ok(token, "GET", path)
    if not isinstance(body, list) or not all(isinstance(x, dict) for x in body):
        raise DemoFailed(f"GET /api/workflow/{QT_NAME}{path} phải trả một mảng: {json.dumps(body)[:300]}")
    return body


def qt_login(username: str, browser: Any = None) -> str:
    """Đăng nhập như trang (apps/nghi-phep/public/auth.js): code + PKCE S256, response_mode=fragment, client
    app-nghi-phep. Phiên SSO có sẵn thì Keycloak chuyển thẳng về; chưa có thì gõ mật khẩu, rồi mã TOTP nếu Keycloak hỏi
    (trưởng phòng — mã tính từ MOC_DEMO_TOTP_SECRET như make seed cài) → access token."""
    import html
    import urllib.parse

    from demo_ca_nhan import Browser, exchange
    from moc_env import _otp_counter, totp_at

    browser = browser or Browser()
    verifier = base64.urlsafe_b64encode(uuid.uuid4().bytes + uuid.uuid4().bytes).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = uuid.uuid4().hex
    query = urllib.parse.urlencode({"client_id": QT_CLIENT, "redirect_uri": QT_CALLBACK, "response_type": "code",
                                    "response_mode": "fragment", "scope": "openid profile", "state": state,
                                    "code_challenge": challenge, "code_challenge_method": "S256"})
    resp = browser.opener.open(f"{PUBLIC_URL}/realms/{ENV.get('MOC_REALM', 'moc')}/protocol/openid-connect/auth?"
                               f"{query}", timeout=30)
    otp_sent = 0
    for _ in range(6):
        url = urllib.parse.urlsplit(resp.geturl())
        if url.path == urllib.parse.urlsplit(QT_CALLBACK).path:
            break
        page = resp.read().decode(errors="replace")
        form = re.search(r'<form[^>]*\saction="([^"]+)"', page)
        if form is None:
            raise DemoFailed(f"{username}: Keycloak không chuyển về {QT_CALLBACK}, cũng không hỏi đăng nhập "
                             f"({url.path})")
        if 'name="otp"' in page:
            if not ENV.get("MOC_DEMO_TOTP_SECRET") or otp_sent >= 3:
                raise DemoFailed(f"{username}: Keycloak không nhận mã TOTP (MOC_DEMO_TOTP_SECRET khác khóa make seed "
                                 "đã cài?)")
            if otp_sent:
                time.sleep(1.5)        # hai lần sai sát nhau thì Keycloak coi là dò mật khẩu
            fields = {"otp": totp_at(ENV["MOC_DEMO_TOTP_SECRET"], _otp_counter(username))}
            otp_sent += 1
        elif 'name="password"' in page:
            fields = {"username": username, "password": ENV["MOC_DEMO_PASSWORD"]}
        else:
            raise DemoFailed(f"{username}: trang Keycloak lạ ở {url.path} (cần đổi mật khẩu, cài TOTP?)")
        resp = browser.opener.open(urllib.parse.urljoin(resp.geturl(), html.unescape(form.group(1))), timeout=30,
                                   data=urllib.parse.urlencode(fields).encode())
    params = urllib.parse.parse_qs(urllib.parse.urlsplit(resp.geturl()).fragment)
    if "code" not in params or params.get("state") != [state]:
        raise DemoFailed(f"{username}: {QT_CLIENT} không nhận được mã cấp quyền đúng state sau khi đăng nhập")
    return exchange(QT_CLIENT, QT_CALLBACK, params["code"][0], verifier)["access_token"]


def task_of(tasks: Any, process_id: str) -> dict[str, Any] | None:
    """Việc của một đơn trong danh sách /tasks."""
    return next((t for t in tasks or [] if t.get("processId") == process_id), None)


def flowable_sql(query: str) -> str:
    """Một câu trên CSDL của Flowable (docker-compose.yml: jdbc:postgresql://postgres:5432/flowable)."""
    out = compose("exec", "-T", "postgres", "psql", "-X", "-q", "-t", "-A", "-U", ENV.get("POSTGRES_USER", "moc"),
                  "-d", "flowable", "-c", query)
    return out.decode().strip()


def qt_versions() -> int:
    """Số phiên bản định nghĩa quy trình nghi-phep.don lõi đã triển khai lên Flowable."""
    return int(flowable_sql(f"select count(*) from act_re_procdef where key_ = '{QT_PROCESS}'") or 0)


def qt_history() -> int:
    """Số đơn (phiên quy trình, cả đã kết thúc) của nghi-phep.don trong lịch sử Flowable."""
    return int(flowable_sql(f"select count(*) from act_hi_procinst where proc_def_id_ like '{QT_PROCESS}:%'") or 0)


def quy_trinh() -> None:
    import tempfile

    from demo_ca_nhan import Browser, claims_of, exchange

    print("Quy trình của ứng dụng chạy trên lõi — Đơn nghỉ phép (apps/nghi-phep): ứng dụng mang BPMN và form, lõi "
          "triển khai, kiểm form, giao việc theo phòng; không sửa tệp nào của lõi")
    need_sources("quy-trinh", QT_MANIFEST, f"apps/{QT_NAME}/forms")
    listed = json.loads(moc_app("list", "--json"))["apps"]
    if any(a["name"] == QT_NAME and (a["installed"] or a["removing"]) for a in listed):
        moc_app("remove", QT_NAME)
        print("   (gỡ bản cài từ lần chạy trước)")
    git_before = git_state()
    tag = uuid.uuid4().hex[:6].upper()

    say(1, "Cài một bản có BPMN độc (scriptTask chạy lệnh trên máy chủ): lõi từ chối, không đổi gì")
    digest, versions = state_digest(), qt_versions()
    with tempfile.TemporaryDirectory(prefix="moc-nghi-phep-doc-") as tmp:
        code, out, err = moc("app", "install", str(poison_copy(pathlib.Path(tmp) / QT_NAME)))
    said = (err or out).strip()
    if code != 1 or "scriptTask" not in said:
        raise DemoFailed(f"BPMN có scriptTask phải bị từ chối (thoát 1, lời báo nêu scriptTask): thoát {code}\n{said}")
    if state_digest() != digest or app_container(QT_NAME) or app_clients(QT_NAME) or qt_versions() != versions:
        raise DemoFailed("bị từ chối nhưng đã đổi .moc-apps/, tạo container, client hoặc triển khai quy trình")
    print("\n".join(f"   {ln}" for ln in said.splitlines()[-4:]))
    ok("thoát 1, lời báo nêu scriptTask; .moc-apps/ không đổi, không container, client, không quy trình mới")

    say(2, f"moc app install {QT_MANIFEST} — một lệnh: trang, client, BPMN và form lên động cơ quy trình của lõi")
    started = time.monotonic()
    out = moc_app("install", QT_MANIFEST)
    print("\n".join(f"   {ln}" for ln in out.strip().splitlines()))
    if not app_container(QT_NAME) or app_clients(QT_NAME) != [QT_CLIENT] or qt_versions() < 1:
        raise DemoFailed(f"sau khi cài: container {app_container(QT_NAME)}, client {app_clients(QT_NAME)}, quy trình "
                         f"{QT_PROCESS} trên Flowable: {qt_versions()} phiên bản")
    status, headers, body = request("GET", f"{PUBLIC_URL}{QT_PATH}")
    csp = next((v for k, v in headers.items() if k.lower() == "content-security-policy"), "")
    config = json.loads(request("GET", f"{PUBLIC_URL}{QT_PATH}config.json")[2])
    if status != 200 or "Đơn nghỉ phép" not in body.decode() or "script-src 'self'" not in csp \
            or config.get("clientId") != QT_CLIENT:
        raise DemoFailed(f"{QT_PATH} trả {status}, CSP {csp!r}, config {config}")
    ok(f"xong sau {time.monotonic() - started:.0f} giây: container app-{QT_NAME}, client {QT_CLIENT} (không client "
       f"dịch vụ), {QT_PROCESS} trên Flowable; {QT_PATH} 200, CSP script-src 'self'")

    say(3, f"{QT_STAFF} đăng nhập Văn phòng điện tử rồi mở Đơn nghỉ phép (SSO, PKCE) — form lấy từ lõi")
    browser = Browser()
    code, verifier, _ = browser.authorize("app-office", f"{PUBLIC_URL}/", QT_STAFF)
    office_token = exchange("app-office", f"{PUBLIC_URL}/", code, verifier)["access_token"]
    staff = qt_login(QT_STAFF, browser)
    if claims_of(staff).get("azp") != QT_CLIENT:
        raise DemoFailed(f"token của trang Đơn nghỉ phép có azp {claims_of(staff).get('azp')}")
    for key, name in ((QT_FORM_DON, "don"), (QT_FORM_DUYET, "duyet")):
        served = qt_ok(staff, "GET", f"/forms/{key}")
        mine = json.loads((ROOT / "apps" / QT_NAME / "forms" / f"{name}.json").read_text(encoding="utf-8"))
        if not isinstance(served, dict) or served.get("properties") != mine["properties"]:
            raise DemoFailed(f"GET /forms/{key} không trả đúng forms/{name}.json của ứng dụng")
    ok(f"token azp {QT_CLIENT}, không hỏi lại mật khẩu; GET /forms/{QT_FORM_DON}, /forms/{QT_FORM_DUYET} trả đúng "
       "JSON Schema trong forms/ của ứng dụng")

    say(4, "Nhân viên gửi đơn: dữ liệu sai → 422 đúng mã từng trường; dữ liệu đúng → quy trình chạy")
    today = datetime.now(timezone(timedelta(hours=7))).date()
    req = leave_request(today, tag)
    for wrong, want, what in ((bad_range(req), QT_BAD_RANGE, "đến ngày trước từ ngày"),
                              ({**req, "loai": QT_WRONG_TYPE}, QT_BAD_TYPE, "loại nghỉ không có trong danh sách")):
        status, body = qt_call(staff, "POST", f"/processes/{QT_PROCESS}", wrong)
        if status != 422 or (body or {}).get("errors") != want:
            raise DemoFailed(f"{what}: cần 422 {{\"errors\": {json.dumps(want)}}}, nhận {status} {body}")
        ok(f"{what}: 422 {json.dumps(want)}")
    pid = (qt_ok(staff, "POST", f"/processes/{QT_PROCESS}", req, want=201) or {}).get("id")
    mine = next((p for p in qt_list(staff, "/processes") if p.get("id") == pid), None) if pid else None
    if not mine or mine.get("endedAt") or mine.get("processKey") != QT_PROCESS:
        raise DemoFailed(f"đơn vừa gửi ({pid}) phải có trong \"Đơn của tôi\", đang chờ duyệt: {mine}")
    ok(f"201, đơn {pid}: {req['tuNgay']} → {req['denNgay']}, \"Đơn của tôi\" ghi đang chờ duyệt")

    say(5, f"Ai thấy việc: trưởng phòng cùng phòng ({QT_MANAGER}) thấy; phòng khác ({QT_OTHER}), người gửi không")
    manager = qt_login(QT_MANAGER)
    task = None
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and task is None:
        task = task_of(qt_list(manager, "/tasks"), pid)
        time.sleep(0 if task else 1)
    if not task or task.get("formKey") != QT_FORM_DUYET or (task.get("data") or {}).get("tuNgay") != req["tuNgay"]:
        raise DemoFailed(f"{QT_MANAGER} không thấy việc duyệt đơn {pid} (formKey {QT_FORM_DUYET}, kèm dữ liệu đơn)")
    ok(f"{QT_MANAGER}: việc \"{task.get('name')}\" ({QT_FORM_DUYET}) kèm dữ liệu đơn")
    other = qt_login(QT_OTHER)
    for who_, token in ((QT_OTHER, other), (QT_STAFF, staff)):
        if task_of(qt_list(token, "/tasks"), pid):
            raise DemoFailed(f"{who_} thấy việc duyệt đơn của {QT_STAFF}")
        status, _ = qt_call(token, "POST", f"/tasks/{task['id']}", {"quyetDinh": "dong-y"})
        if status not in (403, 404):
            raise DemoFailed(f"{who_} duyệt được đơn của {QT_STAFF}: {status}")
    ok(f"{QT_OTHER} (phòng khác), {QT_STAFF} (người gửi) không thấy việc; tự duyệt → 403/404")

    say(6, "Ranh giới: token của client khác bị cổng từ chối; hộp việc Văn phòng điện tử không lẫn việc nghỉ phép")
    office_mgr = who(QT_MANAGER)
    for client, token in (("app-office", office_token), ("moc-cli", office_mgr.token)):
        status, _ = qt_call(token, "GET", "/processes")
        if status != 403:
            raise DemoFailed(f"token azp {client} gọi /api/workflow/{QT_NAME}/processes phải 403, nhận {status}")
    inbox = office_mgr.gql("{ myTasks { id form_key } }")["myTasks"]
    leaked = [t for t in inbox if t["id"] == task["id"] or str(t["form_key"]).startswith(f"{QT_NAME}.")]
    if leaked:
        raise DemoFailed(f"hộp việc Văn phòng điện tử của {QT_MANAGER} có việc của ứng dụng: {leaked}")
    ok(f"azp app-office, moc-cli → 403; myTasks của {QT_MANAGER} ({len(inbox)} việc) không có việc nghỉ phép")

    say(7, f"{QT_MANAGER} duyệt: dữ liệu sai → 422; đồng ý → đơn của {QT_STAFF} kết thúc với quyết định đồng ý")
    status, body = qt_call(manager, "POST", f"/tasks/{task['id']}", {"quyetDinh": QT_WRONG_DECISION})
    if status != 422 or (body or {}).get("errors") != QT_BAD_DECISION:
        raise DemoFailed(f"quyết định viết khác mã: cần 422 {json.dumps(QT_BAD_DECISION)}, nhận {status} {body}")
    note = unicodedata.normalize("NFC", f"Nhớ bàn giao việc đang làm ({tag})")
    qt_ok(manager, "POST", f"/tasks/{task['id']}", {"quyetDinh": "dong-y", "ghiChu": note}, want=204)
    done = None
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not done:
        done = next((p for p in qt_list(staff, "/processes") if p.get("id") == pid and p.get("endedAt")), None)
        time.sleep(0 if done else 1)
    if not done or (done.get("data") or {}).get("quyetDinh") != "dong-y":
        raise DemoFailed(f"đơn {pid} phải kết thúc với quyetDinh dong-y: {done}")
    if task_of(qt_list(manager, "/tasks"), pid):
        raise DemoFailed(f"việc duyệt đơn {pid} vẫn còn trong danh sách của {QT_MANAGER}")
    ok(f"422 {json.dumps(QT_BAD_DECISION)}; rồi 204 — \"Đơn của tôi\": kết thúc lúc {done['endedAt']}, quyết định "
       "dong-y; việc không còn")

    say(8, f"Chạy lại moc app install {QT_MANIFEST}: không đổi gì")
    container, digest, versions = app_container(QT_NAME), state_digest(), qt_versions()
    out = moc_app("install", QT_MANIFEST)
    if app_container(QT_NAME) != container or state_digest() != digest or qt_versions() != versions \
            or "client đã có" not in out:
        raise DemoFailed("cài lại phải giữ nguyên container, .moc-apps/, client và số phiên bản quy trình:\n" + out)
    ok(f"cùng container, .moc-apps/ không đổi một byte, client đã có, {QT_PROCESS} vẫn {versions} phiên bản")

    say(9, f"moc app remove {QT_NAME}: trang, client, container mất; lịch sử đơn còn")
    history = qt_history()
    print("\n".join(f"   {ln}" for ln in moc_app("remove", QT_NAME).strip().splitlines()))
    _, _, body = request("GET", f"{PUBLIC_URL}{QT_PATH}")
    status, _ = qt_call(staff, "GET", "/processes")
    problems = [what for what, bad in (("trang", "Đơn nghỉ phép" in body.decode(errors="replace")),
                                        ("container", bool(app_container(QT_NAME))),
                                        ("client", bool(app_clients(QT_NAME))), ("API", status == 200)) if bad]
    if problems:
        raise DemoFailed(f"sau khi gỡ còn: {', '.join(problems)}")
    if qt_history() != history or history < 1:
        raise DemoFailed(f"gỡ ứng dụng không được xóa lịch sử đơn ({history} → {qt_history()})")
    ok(f"{QT_PATH} không còn là Đơn nghỉ phép, API trả {status}; không container, client; lịch sử Flowable còn "
       f"{history} đơn")

    say(10, "Tệp của lõi không đổi: git status trước và sau giống hệt")
    git_after = git_state()
    if git_before is None:
        ok("không phải thư mục git (bản cài) — bỏ qua so sánh")
        return
    if git_after != git_before:
        raise DemoFailed("cây mã nguồn đổi trong lúc cài/gỡ:\n" + git_after)
    ok("không tệp nào được theo dõi trong git đổi; không tệp mới ngoài .gitignore")


DEMOS = {"nong-lanh": nong_lanh, "kiem-dich": kiem_dich, "han-che": han_che, "ket-bi-mat": ket_bi_mat,
         "tu-phuc-hoi": tu_phuc_hoi, "pha-he": pha_he, "it-ot": it_ot, "lien-thong": lien_thong,
         "doc-van-ban": doc_van_ban, "do-doc-van-ban": do_doc_van_ban, "hoi-dap": hoi_dap, "do-hoi-dap": do_hoi_dap,
         "giao-viec": giao_viec, "do-giao-viec": do_giao_viec, "ky-so": ky_so, "che-pii": che_pii,
         "do-so-lieu-sau": do_so_lieu_sau, "nap-lo": nap_lo, "log-tap-trung": log_tap_trung,
         "cai-ung-dung": cai_ung_dung, "quy-trinh": quy_trinh, "canh-bao": canh_bao}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="demo", description="Màn demo bằng chứng nguyên lý thiết kế của Signet")
    parser.add_argument("man", choices=sorted(DEMOS), help="màn cần chạy")
    args = parser.parse_args(argv)
    started = time.monotonic()
    try:
        DEMOS[args.man]()
    except DemoFailed as exc:
        print(f"\n✗ {exc}", file=sys.stderr)
        return 1
    except (HTTPError, RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        print(f"\n✗ Không chạy được màn demo: {exc}. Signet có đang chạy và đã make seed chưa?", file=sys.stderr)
        return 1
    print(f"\nXong trong {time.monotonic() - started:.0f} giây.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
