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

"""Lệnh vận hành Signet trên máy chủ — chỉ dùng thư viện chuẩn, chạy được ngay trong thư mục cài (make install).

    python3 scripts/moc.py audit verify [--anchors TỆP ...] [--json]
        Tính lại toàn bộ sổ kiểm toán bên ngoài CSDL, so với các mốc neo trong bucket lạnh (và trong tệp, nếu
        có), so hash của văn bản đã phát hành. Thoát 0: nguyên vẹn; 1: có dòng bị sửa; 2: không kiểm được, hoặc
        chưa đủ bằng chứng (chưa có mốc neo, mốc quá cũ, bucket không khóa ghi). (make audit)

    python3 scripts/moc.py audit anchor [--to TỆP]
        Neo đầu chuỗi ngay, không đợi vòng neo định kỳ của svc-files. --to: ghi thêm mốc vào một tệp, để chép
        ra ngoài máy chủ (kho git riêng của đơn vị, thư điện tử…) — bản này nằm ngoài tầm cả quản trị máy chủ.

    python3 scripts/moc.py backup create [--keep N]
        Sao lưu mọi CSDL và tệp vào kho restic (MOC_BACKUP_DIR), mã hóa bằng MOC_BACKUP_PASSWORD. --keep N: sau đó
        chỉ giữ N lượt mới nhất. (make backup; chi tiết trong scripts/backup.py)

    python3 scripts/moc.py backup list [--json] | check
        Các lượt trong kho; kiểm cấu trúc kho.

    python3 scripts/moc.py backup restore [LƯỢT] [--yes]
        Dừng Signet, thay mọi CSDL và tệp bằng một lượt (mặc định lượt mới nhất), ghi lần khôi phục vào sổ kiểm
        toán, chạy lại. Hỏi lại trước khi thay, trừ khi có --yes. (make restore)

    python3 scripts/moc.py tenant create --code MÃ --name TÊN --admin TÊN_ĐĂNG_NHẬP [--department "MÃ=Tên" ...]
                                         [--dry-run] [--json] …
        Thêm (hoặc cập nhật) một đơn vị: dòng core.tenants, phòng, Organization trong Keycloak, tài khoản quản trị
        đơn vị với mật khẩu tạm (in một lần). Chạy lại được. Thoát 0: xong; 1: bị từ chối hoặc danh bạ chưa đồng bộ;
        2: không gọi được CSDL, Keycloak. (chi tiết trong scripts/tenants.py)

    python3 scripts/moc.py tenant list [--json] | check [MÃ ...] [--json]
        Các đơn vị kèm số phòng, người dùng, văn bản, Organization; đối chiếu đơn vị, Organization, thành viên và
        danh bạ core.users. check thoát 1 nếu lệch.

    python3 scripts/moc.py realm clients [--dry-run] [--json]
        Thêm vào realm đang chạy client của ứng dụng trên trình duyệt có trong moc-realm.json mà realm chưa có (realm
        chỉ nạp từ tệp ở lần khởi động đầu; vd bản cài cũ chưa có app-ca-nhan). Không sửa client đã có. make seed
        cũng gọi. Thoát 0: xong; 1: bị từ chối; 2: không gọi được Keycloak. (chi tiết trong scripts/realm_clients.py)

Đọc CSDL qua `docker compose exec postgres psql`, đọc bucket qua `docker compose exec svc-files`, gọi Keycloak qua cổng
quản trị nội bộ (127.0.0.1): không mở thêm cổng nào, không cần mật khẩu ngoài .env.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

import backup
import realm_clients
import tenants
from audit_chain import ANCHORS_SQL, DOCUMENTS_SQL, HEAD_SQL, NOW_SQL, ROWS_SQL, Report, check, local_time, to_datetime
from moc_env import ENV, ROOT

COMPOSE = ["docker", "compose", "--profile", "core", "--profile", "app"]


class Unavailable(Exception):
    """Không đọc được CSDL hoặc bucket — không kết luận được gì về sổ."""


class Snapshot:
    """Đọc sổ trong MỘT giao dịch REPEATABLE READ: lúc đọc, đầu chuỗi, bảng mốc, văn bản rồi các dòng sổ (đọc dần,
    sổ có thể rất dài) cùng nhìn một thời điểm — dòng ghi chen giữa các câu không làm báo nhầm."""

    SECTIONS = (("now", NOW_SQL), ("head", HEAD_SQL), ("recorded", ANCHORS_SQL), ("documents", DOCUMENTS_SQL),
                ("rows", ROWS_SQL))

    def __enter__(self) -> Snapshot:
        script = "begin isolation level repeatable read read only;\n"
        script += "".join(f"\\echo @{name}\n{sql.strip()};\n" for name, sql in self.SECTIONS) + "commit;\n"
        self._err = tempfile.TemporaryFile()    # không đọc stderr trong lúc đọc stdout: ghi ra tệp, khỏi kẹt ống
        self._proc = subprocess.Popen(
            [*COMPOSE, "exec", "-T", "postgres", "psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1",
             "-v", "FETCH_COUNT=5000", "-U", ENV.get("POSTGRES_USER", "moc"), "-d", ENV.get("POSTGRES_DB", "moc"),
             "-f", "-"],
            cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._err, text=True, encoding="utf-8")
        assert self._proc.stdin is not None and self._proc.stdout is not None
        self._proc.stdin.write(script)
        self._proc.stdin.close()
        data: dict[str, list[dict[str, Any]]] = {name: [] for name, _ in self.SECTIONS}
        section = None
        for line in self._proc.stdout:
            if line.startswith("@"):
                section = line.strip()[1:]
                if section == "rows":
                    break
            elif line.strip() and section:
                data[section].append(json.loads(line))
        if section != "rows":
            self._fail()
        self.now = data["now"][0]["now"]
        self.head = data["head"][0]
        self.recorded = data["recorded"]
        self.documents = data["documents"]
        return self

    def rows(self) -> Iterator[dict[str, Any]]:
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            if line.strip():
                yield json.loads(line)
        if self._proc.wait() != 0:
            self._fail()

    def _fail(self) -> None:
        self._proc.wait()
        self._err.seek(0)
        raise Unavailable(f"không đọc được CSDL: {self._err.read().decode(errors='replace').strip() or 'psql lỗi'}")

    def __exit__(self, *exc: object) -> None:
        if self._proc.poll() is None:
            self._proc.kill()
        self._proc.wait()
        self._err.close()


def anchors_tool(command: str) -> dict[str, Any]:
    """python -m svc_files.anchors trong container svc-files (có khóa S3 và Hasura của nó)."""
    proc = subprocess.run([*COMPOSE, "exec", "-T", "svc-files", "python", "-m", "svc_files.anchors", command],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    try:
        out = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        raise Unavailable(f"không gọi được svc-files: {proc.stderr.strip() or proc.stdout.strip()}") from None
    if proc.returncode != 0 or "error" in out:
        raise Unavailable(out.get("error") or proc.stderr.strip())
    return out


def read_file_anchors(path: pathlib.Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Unavailable(f"không đọc được tệp mốc {path}: {exc.strerror}") from None
    anchors = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            a = json.loads(line)
            anchors.append({"audit_id": int(a["audit_id"]), "hash": str(a["hash"]).lower(),
                            "anchored_at": a.get("anchored_at"), "source": path.name})
        except (ValueError, KeyError, TypeError):
            raise Unavailable(f"{path}:{n}: dòng không phải mốc neo (cần JSON có audit_id, hash)") from None
    return anchors


def render(report: Report, gaps: list[str], notes: list[str]) -> None:
    print("Sổ kiểm toán — tính lại chuỗi bên ngoài CSDL")
    chain = [p for p in report.problems if p.kind in {"gap", "prev_hash", "hash", "head"}]
    if not chain:
        print(f"  ✓ {report.rows} dòng, chuỗi băm liền mạch; đầu chuỗi #{report.last_id} ({report.last_hash[:12]}…)")
    for source, stats in report.anchors.items():
        mark = "✓" if stats["matched"] == stats["checked"] else "✗"
        print(f"  {mark} {source}: {stats['matched']}/{stats['checked']} mốc neo khớp")
    if report.latest_anchor and not any(p.kind.startswith("anchor") for p in report.problems):
        a = report.latest_anchor
        tail = f", {report.unanchored} dòng sau đó chưa neo" if report.unanchored else ", không còn dòng nào chưa neo"
        print(f"    mốc mới nhất #{a['audit_id']} ({a['source']}, {local_time(a['anchored_at'])}){tail}")
    if report.documents and not any(p.kind == "document" for p in report.problems):
        print(f"  ✓ {report.documents} văn bản có hash: khớp hash ghi trong sổ")
    for note in notes:
        print(f"  · {note}")
    for gap in gaps:
        print(f"  ⚠ {gap}")
    for p in report.problems:
        print(f"  ✗ {p.message}")
    if report.rewritten:
        lo, hi = report.rewritten
        print(f"  ✗ Chuỗi đã bị tính lại sau khi neo: dòng bị sửa nằm trong khoảng #{lo}…#{hi}")
    if not report.ok:
        print(f"Sổ kiểm toán KHÔNG nguyên vẹn: {len(report.problems)} lỗi.")
    elif gaps:
        print("Không thấy dòng nào bị sửa, nhưng chưa đủ bằng chứng (⚠ ở trên).")
    else:
        print("Sổ kiểm toán nguyên vẹn.")


def coverage(report: Report, bucket: dict[str, Any]) -> list[str]:
    """Những gì làm lần kiểm này chưa đủ bằng chứng, dù không thấy dòng nào bị sửa."""
    gaps = []
    if not bucket["locked"] and bucket["anchors"]:
        gaps.append(f"bucket {bucket['bucket']} không bật khóa ghi: mốc trong đó xóa được")
    if report.rows and report.latest_anchor is None:
        gaps.append("chưa có mốc neo nào khớp: không chứng minh được chuỗi chưa bị tính lại."
                    " Neo ngay: python3 scripts/moc.py audit anchor")
    elif report.latest_anchor and report.unanchored:
        interval = float(ENV.get("MOC_AUDIT_ANCHOR_INTERVAL_S") or 600) or 600
        at = to_datetime(report.latest_anchor["anchored_at"])
        age = (datetime.now(timezone.utc) - at).total_seconds() if at else 0
        if age > max(3 * interval, 1800):
            gaps.append(f"mốc mới nhất đã {age / 60:.0f} phút, {report.unanchored} dòng sau đó chưa neo:"
                        " vòng neo của svc-files có chạy không? (docker compose logs svc-files)")
    return gaps


def verify(args: argparse.Namespace) -> int:
    notes: list[str] = []
    gaps: list[str] = []
    try:
        anchors = [a for path in args.anchors for a in read_file_anchors(path)]
        with Snapshot() as snap:
            # Liệt kê bucket SAU lúc đọc CSDL: mọi mốc mà bảng tra cứu đã ghi đều phải thấy trong bucket
            bucket: dict[str, Any] | None = None
            try:
                bucket = anchors_tool("list")
                anchors += [{**a, "source": f"bucket {bucket['bucket']}"} for a in bucket["anchors"]]
            except Unavailable as exc:
                gaps.append(f"không đọc được mốc neo trong bucket lạnh: {exc}")
            report = check(snap.rows(), snap.head, anchors, snap.documents,
                           recorded=snap.recorded if bucket is not None else None, as_of=snap.now)
    except Unavailable as exc:
        print(f"✗ {exc}. Signet có đang chạy không? (make ps)", file=sys.stderr)
        return 2
    if bucket is not None:
        gaps += coverage(report, bucket)
    if report.later:
        notes.append(f"{report.later} mốc neo ghi trong lúc đang kiểm, đối chiếu ở lần sau")
    # Chỉ là lời khai trong CSDL, không miễn lỗi nào: người sửa được CSDL cũng thêm được một dòng như vậy
    for r in report.restores:
        notes.append(f"dòng #{r['id']}: khôi phục từ bản sao lưu lượt {r['run']} lúc {local_time(r['at'])}, chuỗi quay"
                     f" về dòng #{r['audit_id']}. Mốc chép ra ngoài sau lúc sao lưu đó sẽ không khớp: đối chiếu với"
                     " nhật ký vận hành, đúng có lần khôi phục này thì bỏ các mốc đó khỏi tệp mốc")

    if args.json:
        print(json.dumps({
            "ok": report.ok, "complete": not gaps, "rows": report.rows, "last_id": report.last_id,
            "last_hash": report.last_hash, "anchors": report.anchors, "latest_anchor": report.latest_anchor,
            "unanchored": report.unanchored, "rewritten": report.rewritten, "documents": report.documents,
            "gaps": gaps, "notes": notes, "problems": [p.__dict__ for p in report.problems],
        }, ensure_ascii=False))
    else:
        render(report, gaps, notes)
    if not report.ok:
        return 1
    return 2 if gaps else 0


def anchor(args: argparse.Namespace) -> int:
    try:
        result = anchors_tool("now")["anchored"]
    except Unavailable as exc:
        print(f"✗ Không neo được: {exc}", file=sys.stderr)
        return 2
    if result is None:
        print("Sổ kiểm toán còn trống, chưa có gì để neo.")
        return 0
    if result["new"]:
        print(f"✓ Đã neo đầu chuỗi #{result['audit_id']} ({result['hash'][:12]}…) vào {result['location']}")
    else:
        print(f"✓ Đầu chuỗi #{result['audit_id']} ({result['hash'][:12]}…) đã được neo, không có dòng sổ mới")
    if args.to:
        line = {"audit_id": result["audit_id"], "hash": result["hash"],
                "anchored_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "system": ENV.get("MOC_PUBLIC_URL", "")}
        try:
            have = read_file_anchors(args.to) if args.to.exists() else []
        except Unavailable as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 2
        if any((a["audit_id"], a["hash"]) == (line["audit_id"], line["hash"]) for a in have):
            print(f"  mốc này đã có trong {args.to}")
        else:
            # tệp sửa tay có thể thiếu dấu xuống dòng cuối: không để hai mốc dính vào một dòng
            gap = "\n" if args.to.exists() and args.to.read_bytes()[-1:] not in (b"", b"\n") else ""
            with args.to.open("a", encoding="utf-8") as f:
                f.write(gap + json.dumps(line, ensure_ascii=False) + "\n")
            print(f"  đã ghi thêm vào {args.to} — chép tệp này ra ngoài máy chủ để giữ một bản nữa;"
                  f" kiểm bằng: python3 scripts/moc.py audit verify --anchors {args.to}")
    return 0


def positive(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("phải từ 1 trở lên")
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="moc", description="Lệnh vận hành Signet trên máy chủ")
    groups = parser.add_subparsers(dest="group", required=True)
    audit = groups.add_parser("audit", help="sổ kiểm toán chuỗi băm (F2.12)").add_subparsers(dest="cmd", required=True)
    v = audit.add_parser("verify", help="tính lại chuỗi, so mốc neo và hash văn bản")
    v.add_argument("--anchors", type=pathlib.Path, action="append", default=[], metavar="TỆP",
                   help="tệp mốc neo đã chép ra ngoài (mỗi dòng một JSON, do audit anchor --to ghi)")
    v.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    v.set_defaults(run=verify)
    a = audit.add_parser("anchor", help="neo đầu chuỗi ngay")
    a.add_argument("--to", type=pathlib.Path, metavar="TỆP", help="ghi thêm mốc vào tệp này")
    a.set_defaults(run=anchor)

    b = groups.add_parser("backup", help="sao lưu, khôi phục CSDL và tệp (F3.4)").add_subparsers(dest="cmd",
                                                                                                 required=True)
    c = b.add_parser("create", help="sao lưu một lượt")
    c.add_argument("--keep", type=positive, metavar="N", help="sau đó chỉ giữ N lượt mới nhất")
    c.set_defaults(run=backup.cmd_create)
    ls = b.add_parser("list", help="các lượt trong kho")
    ls.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    ls.set_defaults(run=backup.cmd_list)
    b.add_parser("check", help="kiểm cấu trúc kho (restic check)").set_defaults(run=backup.cmd_check)
    r = b.add_parser("restore", help="dừng Signet, thay CSDL và tệp bằng một lượt sao lưu, chạy lại")
    r.add_argument("run_id", nargs="?", metavar="LƯỢT", help="mã lượt trong backup list; mặc định: lượt mới nhất")
    r.add_argument("--yes", action="store_true", help="không hỏi lại")
    r.set_defaults(run=backup.cmd_restore)

    t = groups.add_parser("tenant", help="đơn vị (thuê ước) và Keycloak Organizations (F3.12)").add_subparsers(
        dest="cmd", required=True)
    tc = t.add_parser("create", help="thêm hoặc cập nhật một đơn vị: CSDL, Organization, quản trị đơn vị (chạy lại được)")
    tc.add_argument("--code", required=True, type=tenants.code_arg, metavar="MÃ",
                    help="mã viết trong ký hiệu văn bản, vd KTCK (không dấu cách, '/', '-'; tối đa 20 ký tự)")
    tc.add_argument("--name", required=True, type=tenants.text_arg, metavar="TÊN", help='tên đơn vị, vd "Khoa Cơ khí"')
    tc.add_argument("--parent-name", type=tenants.text_arg, metavar="TÊN", help="cơ quan chủ quản in trên văn bản đi")
    tc.add_argument("--place-name", type=tenants.text_arg, metavar="TÊN", help="địa danh trước ngày tháng, vd Hà Nội")
    tc.add_argument("--head-title", type=tenants.text_arg, metavar="TÊN",
                    help="chức vụ người đứng đầu ở phần ký, vd Trưởng khoa")
    tc.add_argument("--org-ident", type=tenants.org_ident_arg, metavar="MÃ",
                    help="mã định danh 13 ký tự theo QCVN 102 (tùy chọn)")
    tc.add_argument("--department", type=tenants.department_arg, action="append", default=[], metavar="MÃ=TÊN",
                    help='phòng, bộ môn; lặp lại cho nhiều phòng, vd --department "VP=Văn phòng khoa"')
    tc.add_argument("--admin", required=True, type=tenants.username_arg, metavar="TÊN_ĐĂNG_NHẬP",
                    help="tài khoản quản trị đơn vị (tenant_admin); đã có ở đơn vị này thì giữ nguyên")
    tc.add_argument("--admin-name", type=tenants.person_arg, metavar="HỌ_TÊN",
                    help='họ và tên, vd "Ngô Văn Tín" (mặc định: Quản trị <tên đơn vị>)')
    tc.add_argument("--admin-email", type=tenants.email_arg, metavar="EMAIL",
                    help="mặc định <tên đăng nhập>@<alias>.moc.example — thành viên Organization phải có email")
    tc.add_argument("--alias", type=tenants.alias_arg,
                    help="alias Organization (mặc định suy từ mã: ĐT → dt); Keycloak không cho đổi sau khi tạo")
    tc.add_argument("--domain", type=tenants.domain_arg, action="append", default=[], metavar="TÊN_MIỀN",
                    help="tên miền email của đơn vị gắn vào Organization (tùy chọn, lặp lại được)")
    tc.add_argument("--reset-password", action="store_true",
                    help="quản trị đơn vị đã có: đặt lại mật khẩu tạm (vd mất mật khẩu in lần trước)")
    tc.add_argument("--wait", type=int, default=90, metavar="GIÂY",
                    help="đợi svc-workflow chép quản trị đơn vị vào danh bạ tối đa bao lâu (mặc định 90; 0: không đợi)")
    tc.add_argument("--dry-run", action="store_true", help="chỉ in kế hoạch, không thay đổi gì")
    tc.add_argument("--json", action="store_true", help="in kết quả dạng JSON (có mật khẩu tạm nếu vừa đặt)")
    tc.set_defaults(run=tenants.cmd_create)
    tl = t.add_parser("list", help="các đơn vị: phòng, người dùng, văn bản, Organization")
    tl.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    tl.set_defaults(run=tenants.cmd_list)
    tk = t.add_parser("check", help="đối chiếu đơn vị, Organization, thành viên và danh bạ core.users")
    tk.add_argument("codes", nargs="*", metavar="MÃ", help="chỉ kiểm các đơn vị này (mặc định: tất cả)")
    tk.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    tk.set_defaults(run=tenants.cmd_check)

    rm = groups.add_parser("realm", help="realm Keycloak: client của ứng dụng (docs/them-ung-dung.md)").add_subparsers(
        dest="cmd", required=True)
    rc = rm.add_parser("clients", help="thêm client ứng dụng trên trình duyệt còn thiếu so với moc-realm.json")
    rc.add_argument("--dry-run", action="store_true", help="chỉ in client sẽ thêm, không thay đổi gì")
    rc.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    rc.set_defaults(run=realm_clients.cmd_clients)
    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
