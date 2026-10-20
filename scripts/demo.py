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
    python3 scripts/demo.py ket-bi-mat
        (iv) Két bí mật: dịch vụ không nhận bí mật qua biến môi trường mà lấy từ két OpenBao bằng AppRole riêng;
        khởi động lại két thì két tự mở khóa, dịch vụ khởi động lại vẫn lấy được bí mật. (make demo-ket-bi-mat)
    python3 scripts/demo.py tu-phuc-hoi
        (iv) Tự phục hồi: xóa hẳn container svc-files, dừng centrifugo; một lượt reconciler (systemd timer chạy mỗi
        60 giây) dựng lại đúng như compose khai báo, tải tệp lại được. (make demo-tu-phuc-hoi)

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
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from moc_env import EICAR, ENV, PUBLIC_URL, ROOT, HTTPError, Session, call_json, compose, text_pdf


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


DEMOS = {"nong-lanh": nong_lanh, "kiem-dich": kiem_dich, "ket-bi-mat": ket_bi_mat, "tu-phuc-hoi": tu_phuc_hoi}


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
