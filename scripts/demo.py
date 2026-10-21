#!/usr/bin/env python3
# Copyright 2026 Mộc Team
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
        khớp, phòng đọc đọc lại gói bằng DuckDB. (make demo-nong-lanh)
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
        trình, dự thảo vào luồng văn bản đi. (make demo-it-ot)
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
        Đo tác tử trên 14 văn bản mẫu seed/van-ban-den so với nhãn nhan.json: bảng đúng / sai / trống từng trường,
        riêng PDF có lớp chữ và bản scan, thời gian trung bình; thoát 1 khi PDF có lớp chữ dưới ngưỡng.
        (make do-doc-van-ban)
    python3 scripts/demo.py hoi-dap
        Hỏi đáp trên kho văn bản (F4.2, dưới hai phút, không cần mô hình): văn thư nạp kho mẫu seed/hoi-dap; trợ lý
        moc-assistant trả câu trích nguyên văn kèm số ký hiệu và trang; giảng viên Bộ môn KTPM chỉ thấy văn bản mình
        được xem; nội dung văn bản hạn chế không ai hỏi ra; sổ kiểm toán ghi lượt hỏi của tác tử, không có câu hỏi,
        câu trả lời; bật profile ai thì mô hình viết câu trả lời có trích dẫn. (make demo-hoi-dap)
    python3 scripts/demo.py do-hoi-dap
        Đo trợ lý trên mọi câu trong seed/hoi-dap/cau-hoi.json (đúng người hỏi): bảng trạng thái, nguồn top-3, đúng /
        sai, từ khóa, thời gian; recall@3, tỉ lệ từ chối đúng; có mô hình thì đo thêm câu trả lời của mô hình. Thoát 1
        khi có nguồn bị cấm ở bất kỳ câu nào (quyền, văn bản hạn chế), hoặc recall@3 dưới ngưỡng. (make do-hoi-dap)

Thoát 0 khi màn chạy đúng như kịch bản, 1 khi có bước sai (in rõ bước nào).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import quote

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


# Bí mật svc-files, svc-workflow cần (tên trong .env) — cùng danh sách openbao/start.sh nạp vào két
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
        # máy chủ đã bật timer (ops/systemd/) và lượt của timer chạy trước lượt này
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
    stored = clerk.upload(f"sau-phuc-hoi-{tag}.pdf", text_pdf("Thu sau khi tu phuc hoi", f"Ma thu {tag}"))
    ok(f"svc-files, centrifugo healthy sau {time.monotonic() - started:.0f} giây kể từ lượt reconciler; tải tệp → "
       f"201 (SHA-256 {stored['sha256'][:16]}…)")

    print("\nTrên máy chủ thật: ops/systemd/moc-reconcile.timer · nhật ký: journalctl -u moc-reconcile")


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
    for row in psql("select id, direction, coalesce(symbol, ''), coalesce(verify_code, ''), summary from"
                    f" office.documents where id in ({', '.join(repr(i) for i in ids)})").splitlines():
        i, direction, symbol, code, summary = row.split("|", 4)
        docs[i] = {"direction": direction, "symbol": symbol, "verify_code": code, "summary": summary}
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

    say(5, "Gói lưu trữ không sửa, không xóa được — kể cả bằng khóa quản trị kho (S3 Object Lock, COMPLIANCE)")
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


OT_SENSOR = "phong-may-chu"
OT_ROOM = "Phòng máy chủ tầng 3"
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

# Gửi một thông báo giả (token sai) tới svc-workflow, in mã HTTP nhận được hoặc "không tới được"
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
              "--responsible", OT_STAFF, "--readings", ",".join(f"{r:g}" for r in readings), "--interval", "1")
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
       " OT ở broker, Mộc chỉ nhận sự kiện cần xử lý")

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
# Ngưỡng trên 10 PDF có lớp chữ — như services/svc-files/tests/test_docread_samples.py; thêm: không trường high nào sai
TEXT_MIN = {"symbol": 9, "issued_on": 9, "type_code": 9, "issuer_name": 8, "summary": 8}
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

    measured = score_reads(results["text"])
    t = measured["table"]
    below = [f"{f} {t[f]['có'] if f == 'summary' else t[f]['đúng']}/{measured['n']} < {minimum}"
             for f, minimum in TEXT_MIN.items() if (t[f]["có"] if f == "summary" else t[f]["đúng"]) < minimum]
    if len(results["text"]) != 10:
        below.append(f"có {len(results['text'])} PDF có lớp chữ, cần 10")
    if below or measured["wrong"]:
        raise DemoFailed("PDF có lớp chữ dưới ngưỡng: " + "; ".join(below + measured["wrong"]))
    print("\n✓ PDF có lớp chữ đạt ngưỡng: số ký hiệu, ngày ban hành, loại ≥ 9/10; cơ quan ban hành, trích yếu ≥ 8/10;"
          " không ô high nào sai")


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
    người hỏi) tới khi văn bản đó có trong nguồn → số giây đã đợi."""
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
            if any(same_symbol(s.get("symbol"), symbol) for s in sources):
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


DEMOS = {"nong-lanh": nong_lanh, "kiem-dich": kiem_dich, "han-che": han_che, "ket-bi-mat": ket_bi_mat,
         "tu-phuc-hoi": tu_phuc_hoi, "pha-he": pha_he, "it-ot": it_ot, "lien-thong": lien_thong,
         "doc-van-ban": doc_van_ban, "do-doc-van-ban": do_doc_van_ban, "hoi-dap": hoi_dap, "do-hoi-dap": do_hoi_dap}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="demo", description="Màn demo bằng chứng nguyên lý thiết kế của Mộc")
    parser.add_argument("man", choices=sorted(DEMOS), help="màn cần chạy")
    args = parser.parse_args(argv)
    started = time.monotonic()
    try:
        DEMOS[args.man]()
    except DemoFailed as exc:
        print(f"\n✗ {exc}", file=sys.stderr)
        return 1
    except (HTTPError, RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        print(f"\n✗ Không chạy được màn demo: {exc}. Mộc có đang chạy và đã make seed chưa?", file=sys.stderr)
        return 1
    print(f"\nXong trong {time.monotonic() - started:.0f} giây.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
