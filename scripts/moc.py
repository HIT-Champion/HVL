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

    python3 scripts/moc.py audit verify [--anchors TỆP ...] [--key TỆP.pem ...] [--json]
        Tính lại toàn bộ sổ kiểm toán bên ngoài CSDL, so với các mốc neo trong bucket lạnh (và trong tệp, nếu
        có), so hash của văn bản đã phát hành. Mốc trong tệp có chữ ký thì kiểm chữ ký (anchor_sig.py) bằng khóa
        trong --key, anchor-key.pem cạnh tệp mốc, hoặc khóa két đang dùng. Thoát 0: nguyên vẹn; 1: có dòng bị sửa,
        hoặc mốc trong tệp có chữ ký sai, hay không có chữ ký mà đứng sau mốc đã ký; 2: không kiểm được, hoặc chưa đủ
        bằng chứng (chưa có mốc neo, mốc quá cũ, bucket không khóa ghi, chữ ký không có khóa để kiểm). (make audit)

    python3 scripts/moc.py audit anchor [--to TỆP] [--publish THƯ_MỤC]
        Neo đầu chuỗi ngay, không đợi vòng neo định kỳ của svc-files. --to: ghi thêm mốc (kèm chữ ký của két nếu
        két có khóa moc-anchor) vào một tệp, để chép ra ngoài máy chủ — bản này nằm ngoài tầm cả quản trị máy chủ.
        Két có khóa mà mốc không có chữ ký (két không trả lời lúc ký) thì không ghi, thoát 2; lượt sau ghi lại.
        --publish: như --to với THƯ_MỤC/anchors.jsonl trong một bản sao git, chép khóa công khai ra anchor-key.pem,
        commit (tác giả "Signet anchor") và git push nếu có remote — không bao giờ ép (--force). Timer
        platform/systemd/moc-anchor-publish.timer chạy lệnh này định kỳ (docs/van-hanh.md mục Mốc neo công khai).

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

    python3 scripts/moc.py realm theme [--dry-run] [--json]
        Áp theme đăng nhập Signet (loginTheme trong moc-realm.json) cho realm nạp từ trước khi có theme. Chỉ đặt khi
        realm còn dùng theme mặc định; không đổi theme quản trị đã chọn. Thoát 0: xong hoặc không cần đặt; 1: Keycloak
        chưa có thư mục theme (docker compose up -d keycloak) hoặc từ chối; 2: không gọi được Keycloak.

    python3 scripts/moc.py app install apps/<thư mục>/app.yaml [--dry-run] | list [--json] | remove TÊN [--dry-run]
                           | sync [--files] [--json]
        Cắm ứng dụng vào lõi bằng manifest, không sửa tệp lõi nào: client Keycloak, route APISIX, container, schema và
        migration riêng, bảng và quyền Hasura, event trigger nghe sự kiện của lõi. Chạy lại được; lỗi giữa chừng thì
        báo bước nào. Gỡ giữ nguyên dữ liệu. (make app-install APP=…; chi tiết trong scripts/ung_dung.py)

Đọc CSDL qua `docker compose exec postgres psql`, đọc bucket qua `docker compose exec svc-files`, gọi Keycloak qua cổng
quản trị nội bộ (127.0.0.1): không mở thêm cổng nào, không cần mật khẩu ngoài .env.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

import anchor_sig
import backup
import realm_clients
import tenants
import ung_dung
from audit_chain import (ANCHORS_SQL, DOCUMENTS_SQL, HEAD_SQL, NOW_SQL, ROWS_SQL, Problem, Report, check, local_time,
                         to_datetime)
from moc_env import ENV, ROOT

COMPOSE = ["docker", "compose", "--profile", "core", "--profile", "app"]
# Kho mốc công khai (audit anchor --publish): tên tệp trong bản sao git và tác giả cố định của mỗi commit
ANCHORS_FILE = "anchors.jsonl"
KEY_FILE = "anchor-key.pem"
SIGNATURE_RESULTS = ("valid", "invalid", "unsigned", "unsigned_late", "unknown_key")
PUBLISH_AUTHOR = ("Signet anchor", "anchor@signet.invalid")


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
                            "anchored_at": a.get("anchored_at"), "source": path.name, "line": n,
                            # chữ ký (signet-anchor-v1) phủ cả bốn giá trị audit_id, hash, anchored_at, system
                            **{k: a[k] for k in ("v", "system", "key", "sig") if k in a}})
        except (ValueError, KeyError, TypeError):
            raise Unavailable(f"{path}:{n}: dòng không phải mốc neo (cần JSON có audit_id, hash)") from None
    return anchors


def file_keys(paths: list[pathlib.Path]) -> dict[str, bytes]:
    """Khóa công khai ký mốc neo trong các tệp PEM → {vân tay: khóa}."""
    keys: dict[str, bytes] = {}
    for path in paths:
        try:
            keys.update(anchor_sig.public_keys(path.read_text(encoding="utf-8")))
        except OSError as exc:
            raise Unavailable(f"không đọc được tệp khóa {path}: {exc.strerror}") from None
        except ValueError as exc:
            raise Unavailable(f"{path}: {exc}") from None
    return keys


def check_signatures(files: list[list[dict[str, Any]]], keys: dict[str, bytes],
                     ) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]], list[Problem], list[str]]:
    """Kiểm chữ ký các mốc, từng tệp theo thứ tự dòng → (mốc dùng để đối chiếu chuỗi, số đếm theo tệp, lỗi, chỗ chưa
    đủ bằng chứng). Mốc chữ ký sai, hay không có chữ ký mà đứng sau mốc đã ký (chữ ký bị gỡ), bị loại khỏi phần đối
    chiếu: dòng đó đã bị sửa sau khi ký (hoặc không do két này ký), giá trị của nó không đáng tin để kết luận chuỗi
    đúng hay sai. Mốc chưa ký đứng trước mọi mốc đã ký (ghi trước khi két có khóa) vẫn đối chiếu như trước."""
    kept, problems, gaps = [], [], []
    counts: dict[str, dict[str, int]] = {}
    unknown: dict[tuple[str, str], int] = {}
    checked = [(a, result) for lines in files for a, result in zip(lines, anchor_sig.check_all(lines, keys))]
    for a, result in checked:
        stats = counts.setdefault(a["source"], dict.fromkeys(SIGNATURE_RESULTS, 0))
        stats[result] += 1
        if result == "invalid":
            problems.append(Problem(
                "anchor_signature", a["audit_id"],
                f"mốc #{a['audit_id']} ({a['source']}, dòng {a['line']}): chữ ký không khớp — dòng đã bị sửa sau khi"
                " ký, hoặc không do két của hệ thống này ký"))
            continue
        if result == "unsigned_late":
            problems.append(Problem(
                "anchor_unsigned_late", a["audit_id"],
                f"mốc #{a['audit_id']} ({a['source']}, dòng {a['line']}): không có chữ ký mà đứng sau mốc đã ký — chữ"
                " ký đã bị gỡ khỏi dòng (két có khóa thì moc audit anchor không ghi mốc chưa ký)"))
            continue
        if result == "unknown_key":
            where = (a["source"], str(a.get("key")))
            unknown[where] = unknown.get(where, 0) + 1
        kept.append(a)
    for (source, key), n in unknown.items():
        gaps.append(f"{n} mốc trong {source} ký bằng khóa {key[:23]}… mà không có khóa công khai nào khớp: chưa kiểm"
                    " được chữ ký (thêm --key TỆP.pem)")
    return kept, counts, problems, gaps


def render(report: Report, gaps: list[str], notes: list[str], signatures: dict[str, dict[str, int]]) -> None:
    print("Sổ kiểm toán — tính lại chuỗi bên ngoài CSDL")
    chain = [p for p in report.problems if p.kind in {"gap", "prev_hash", "hash", "head"}]
    if not chain:
        print(f"  ✓ {report.rows} dòng, chuỗi băm liền mạch; đầu chuỗi #{report.last_id} ({report.last_hash[:12]}…)")
    for source, stats in report.anchors.items():
        mark = "✓" if stats["matched"] == stats["checked"] else "✗"
        print(f"  {mark} {source}: {stats['matched']}/{stats['checked']} mốc neo khớp")
    for source, sig in signatures.items():
        expected = sig["valid"] + sig["invalid"] + sig["unsigned_late"]
        if expected:
            mark = "✓" if sig["valid"] == expected else "✗"
            print(f"  {mark} {source}: {sig['valid']}/{expected} chữ ký mốc neo hợp lệ")
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
        files = [read_file_anchors(path) for path in args.anchors]
        anchors = [a for lines in files for a in lines]
        # khóa kiểm chữ ký: --key, anchor-key.pem cạnh tệp mốc (bố cục của --publish), khóa két đang dùng khi cần
        keys = file_keys([*args.key, *(p.parent / KEY_FILE for p in args.anchors if (p.parent / KEY_FILE).is_file())])
        if any(a.get("sig") and a.get("key") not in keys for a in anchors):
            try:
                current = anchors_tool("key")["key"]
                if current:
                    keys.update(anchor_sig.public_keys(current["pem"]))
            except (Unavailable, KeyError, TypeError, ValueError) as exc:
                notes.append(f"không đọc được khóa ký mốc neo trong két: {exc}")
        anchors, signatures, bad_signatures, unchecked = check_signatures(files, keys)
        gaps += unchecked
        for path, lines in zip(args.anchors, files):
            if any(a.get("sig") for a in lines):
                continue
            if (path.parent / KEY_FILE).is_file():
                # --publish chỉ ghi anchor-key.pem khi tệp đã có mốc có chữ ký
                bad_signatures.append(Problem(
                    "anchor_unsigned_all", lines[-1]["audit_id"] if lines else None,
                    f"cạnh {path.name} có {KEY_FILE} mà tệp không còn mốc nào có chữ ký — chữ ký đã bị gỡ khỏi"
                    " mọi dòng (hoặc các dòng đã bị xóa)"))
            elif args.key:
                gaps.append(f"{path.name} không có mốc nào có chữ ký: --key chưa kiểm được chữ ký nào")
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
    report.problems += bad_signatures
    if bucket is not None:
        gaps += coverage(report, bucket)
    if report.later:
        notes.append(f"{report.later} mốc neo ghi trong lúc đang kiểm, đối chiếu ở lần sau")
    for source, stats in signatures.items():
        if stats["unsigned"]:
            notes.append(f"{stats['unsigned']} mốc trong {source} không có chữ ký (ghi khi két chưa có khóa ký mốc"
                         " neo): chỉ đối chiếu giá trị")
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
            "signatures": signatures, "gaps": gaps, "notes": notes,
            "problems": [p.__dict__ for p in report.problems],
        }, ensure_ascii=False))
    else:
        render(report, gaps, notes, signatures)
    if not report.ok:
        return 1
    return 2 if gaps else 0


def append_line(path: pathlib.Path, line: dict[str, Any]) -> bool:
    """Ghi thêm một mốc vào tệp JSON lines; mốc (audit_id, hash) đã có thì thôi → có ghi hay không."""
    have = read_file_anchors(path) if path.exists() else []
    if any((a["audit_id"], a["hash"]) == (line["audit_id"], line["hash"]) for a in have):
        return False
    # tệp sửa tay có thể thiếu dấu xuống dòng cuối: không để hai mốc dính vào một dòng
    gap = "\n" if path.exists() and path.read_bytes()[-1:] not in (b"", b"\n") else ""
    with path.open("a", encoding="utf-8") as f:
        f.write(gap + json.dumps(line, ensure_ascii=False) + "\n")
    return True


def unsigned_refused(paths: list[pathlib.Path]) -> str | None:
    """Lý do không ghi một mốc chưa ký vào các tệp mốc này; None: két chưa có khóa, ghi như cũ.

    Két đã có khóa mà mốc không có chữ ký là két không trả lời lúc ký. Người kiểm không phân biệt được dòng như vậy
    với một dòng bị gỡ chữ ký (anchor_sig.check_all coi dòng chưa ký sau dòng đã ký là lỗi), nên không ghi; lượt sau
    két ký lại đúng mốc đó (cùng mốc, cùng thời điểm ghi bucket, cùng chữ ký) hoặc mốc mới hơn."""
    for path in paths:
        if path.exists() and any(a.get("sig") for a in read_file_anchors(path)):
            return f"{path} đã có mốc có chữ ký"
        if (path.parent / KEY_FILE).exists():
            return f"cạnh {path.name} đã có khóa ký mốc {path.parent / KEY_FILE}"
    try:
        key = anchors_tool("key")["key"]
    except (Unavailable, KeyError, TypeError) as exc:
        return f"không hỏi được két đã có khóa ký mốc chưa ({exc})"
    return "két đã có khóa ký mốc moc-anchor nhưng không ký được mốc này" if key else None


def git(directory: pathlib.Path, *args: str, author: bool = False) -> subprocess.CompletedProcess[str]:
    """git trong bản sao mốc công khai; không hỏi gì trên terminal (chạy từ timer). author: tác giả cố định."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if author:
        env |= {"GIT_AUTHOR_NAME": PUBLISH_AUTHOR[0], "GIT_AUTHOR_EMAIL": PUBLISH_AUTHOR[1],
                "GIT_COMMITTER_NAME": PUBLISH_AUTHOR[0], "GIT_COMMITTER_EMAIL": PUBLISH_AUTHOR[1]}
    return subprocess.run(["git", "-C", str(directory), *args], capture_output=True, text=True, encoding="utf-8",
                          env=env)


def publish(directory: pathlib.Path, line: dict[str, Any]) -> int:
    """Ghi mốc vào THƯ_MỤC/anchors.jsonl, khóa công khai vào anchor-key.pem, commit, push nếu có remote.

    Chỉ thêm commit, không bao giờ viết lại lịch sử: không --force, không amend; nhánh công khai cấm đẩy ép (docs/
    van-hanh.md mục Mốc neo công khai) nên bản sao ở máy chủ có bị sửa cũng không xóa được mốc đã công bố. Push hỏng
    (mất mạng) thì commit vẫn nằm lại, lần chạy sau đẩy tiếp."""
    if git(directory, "rev-parse", "--is-inside-work-tree").stdout.strip() != "true":
        print(f"✗ {directory} không phải một bản sao git (git init hoặc git clone kho mốc công khai trước)",
              file=sys.stderr)
        return 2
    path = directory / ANCHORS_FILE
    try:
        added = append_line(path, line)
        signed = any(a.get("sig") for a in read_file_anchors(path))
    except Unavailable as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2
    files = [ANCHORS_FILE]
    try:
        key = anchors_tool("key")["key"]
    except (Unavailable, KeyError, TypeError) as exc:
        key = None
        print(f"  không đọc được khóa công khai trong két ({exc}): giữ nguyên {KEY_FILE}", file=sys.stderr)
    pem = directory / KEY_FILE
    # khóa chỉ đi cùng mốc có chữ ký: audit verify coi anchor-key.pem cạnh một tệp không có dòng ký nào là chữ ký bị gỡ
    if key and signed and (not pem.exists() or pem.read_text(encoding="utf-8") != key["pem"]):
        # khóa đổi (két dựng lại): ghi đè, lịch sử git vẫn giữ khóa cũ cho các mốc ký trước đó
        pem.write_text(key["pem"], encoding="utf-8")
    if pem.exists():
        files.append(KEY_FILE)
    out = git(directory, "add", "--", *files)
    if out.returncode != 0:
        print(f"✗ git add: {out.stderr.strip()}", file=sys.stderr)
        return 2
    if git(directory, "diff", "--cached", "--quiet", "--", *files).returncode == 1:
        message = f"Anchor #{line['audit_id']} {line['hash'][:16]}"
        out = git(directory, "commit", "--quiet", "-m", message, "--", *files, author=True)
        if out.returncode != 0:
            print(f"✗ git commit: {out.stderr.strip() or out.stdout.strip()}", file=sys.stderr)
            return 2
        print(f"  đã commit \"{message}\" vào {directory}")
    elif not added:
        print(f"  mốc này đã có trong {path}, không có gì mới để commit")
    remotes = git(directory, "remote").stdout.split()
    if not remotes:
        print(f"  {directory} chưa có remote: chỉ commit tại chỗ, chưa công bố ra ngoài")
        return 0
    remote = "origin" if "origin" in remotes else remotes[0]
    out = git(directory, "push", "--porcelain", remote, "HEAD")
    if out.returncode != 0:
        print(f"✗ git push {remote}: {out.stderr.strip() or out.stdout.strip()} — commit vẫn ở {directory},"
              " lần chạy sau đẩy tiếp", file=sys.stderr)
        return 2
    print(f"  đã đẩy lên {remote}")
    return 0


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
    signed = result.get("signed")
    if signed:
        # đúng các trường két đã ký (anchor_sig.py dựng lại thông điệp từ chúng)
        line = {"v": anchor_sig.MESSAGE, "audit_id": result["audit_id"], "hash": result["hash"],
                "anchored_at": signed["anchored_at"], "system": signed["system"], "key": signed["key"],
                "sig": signed["sig"]}
        print(f"  két đã ký mốc bằng khóa {signed['key'][:23]}…")
    else:
        line = {"audit_id": result["audit_id"], "hash": result["hash"],
                "anchored_at": result.get("anchored_at") or datetime.now().astimezone().isoformat(timespec="seconds"),
                "system": ENV.get("MOC_PUBLIC_URL", "")}
        if args.to or args.publish:
            targets = [p for p in (args.to, args.publish and args.publish / ANCHORS_FILE) if p]
            try:
                refused = unsigned_refused(targets)
            except Unavailable as exc:
                print(f"✗ {exc}", file=sys.stderr)
                return 2
            if refused:
                print(f"✗ Không ghi mốc chưa ký ra tệp: {refused}. Dòng chưa ký sau dòng đã ký bị coi là chữ ký bị"
                      " gỡ; lượt sau thử lại (docs/van-hanh.md mục Mốc neo công khai)", file=sys.stderr)
                return 2
            print("  mốc không có chữ ký: két chưa có khóa moc-anchor (docs/van-hanh.md mục Két bí mật)")
    if args.to:
        try:
            added = append_line(args.to, line)
        except Unavailable as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 2
        if added:
            print(f"  đã ghi thêm vào {args.to} — chép tệp này ra ngoài máy chủ để giữ một bản nữa;"
                  f" kiểm bằng: python3 scripts/moc.py audit verify --anchors {args.to}")
        else:
            print(f"  mốc này đã có trong {args.to}")
    if args.publish:
        return publish(args.publish, line)
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
    v.add_argument("--key", type=pathlib.Path, action="append", default=[], metavar="TỆP.pem",
                   help="khóa công khai kiểm chữ ký mốc trong tệp (anchor-key.pem); mặc định: tệp cạnh tệp mốc,"
                        " khóa két")
    v.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    v.set_defaults(run=verify)
    a = audit.add_parser("anchor", help="neo đầu chuỗi ngay")
    a.add_argument("--to", type=pathlib.Path, metavar="TỆP", help="ghi thêm mốc vào tệp này")
    a.add_argument("--publish", type=pathlib.Path, metavar="THƯ_MỤC",
                   help="ghi mốc vào anchors.jsonl của bản sao git này, commit, push nếu có remote (không bao giờ ép)")
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

    rm = groups.add_parser("realm", help="realm Keycloak: client của ứng dụng (docs/them-ung-dung.md), theme đăng nhập"
                           ).add_subparsers(dest="cmd", required=True)
    rc = rm.add_parser("clients", help="thêm client ứng dụng trên trình duyệt còn thiếu so với moc-realm.json")
    rc.add_argument("--dry-run", action="store_true", help="chỉ in client sẽ thêm, không thay đổi gì")
    rc.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    rc.set_defaults(run=realm_clients.cmd_clients)
    rt = rm.add_parser("theme", help="áp theme đăng nhập Signet (loginTheme của moc-realm.json) cho realm đã nạp")
    rt.add_argument("--dry-run", action="store_true", help="chỉ in việc sẽ làm, không thay đổi gì")
    rt.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    rt.set_defaults(run=realm_clients.cmd_theme)

    ung_dung.add_parser(groups)
    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
