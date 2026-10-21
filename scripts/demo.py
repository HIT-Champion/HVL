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

Thoát 0 khi màn chạy đúng như kịch bản, 1 khi có bước sai (in rõ bước nào).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import quote

from moc_env import EICAR, ENV, PUBLIC_URL, ROOT, HTTPError, Session, call_json, compose, request, text_pdf


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


DEMOS = {"nong-lanh": nong_lanh, "kiem-dich": kiem_dich, "han-che": han_che, "ket-bi-mat": ket_bi_mat,
         "tu-phuc-hoi": tu_phuc_hoi, "pha-he": pha_he, "it-ot": it_ot, "lien-thong": lien_thong}


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
