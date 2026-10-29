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

"""Dữ liệu công khai (#424, đề trường mục 3.3): bản chụp có phiên bản trong seed/du-lieu-mo/<mã nguồn>/.

Mỗi nguồn một module scripts/nguon_<mã, gạch nối đổi thành gạch dưới>.py có ``NGUON``, ``TEN`` và
``lay(thu_muc) -> manifest``. Bản cài không bao giờ gọi nguồn lúc chạy: svc-files đọc các manifest.json qua mount chỉ
đọc /srv/du-lieu-mo, trang trạng thái (``GET /api/status``, khóa ``open_data``) báo tuổi dữ liệu và kết quả so băm.
Nguồn ngừng thì bản chụp gần nhất vẫn dùng được; lấy mới là việc ở máy của đội, đổi bản chụp đi qua PR.

    python3 scripts/du_lieu_mo.py lay [MÃ ...]
        Lấy mới từ nguồn (cần Internet). Chỉ thay bản chụp khi lấy xong, mọi tệp khớp manifest và tổng không quá 3 MB;
        lỗi thì giữ bản cũ, thoát 1. (make du-lieu-mo-lay)
    python3 scripts/du_lieu_mo.py kiem [MÃ ...] [--json]
        So SHA-256, cỡ từng tệp với manifest, in tuổi dữ liệu. Thoát 1 khi manifest hỏng, thiếu tệp hay sai băm; quá
        max_age_days chỉ báo cũ. (make du-lieu-mo)
    python3 scripts/du_lieu_mo.py nap [MÃ ...] [--clerk TÊN]
        Nạp các tệp là văn bản (meta có loại, số ký hiệu, cơ quan, ngày ban hành, trích yếu) thành văn bản đến của đơn
        vị mẫu qua API nạp lô (POST /api/imports/incoming: CSV + zip, ClamAV, Action receiveIncoming), như văn thư nạp
        tay; nguồn chỉ có dữ liệu (vd ngay-nghi-le, svc-workflow đọc tại chỗ) thì bỏ qua. Gửi lại không tạo trùng
        (Idempotency-Key theo băm manifest, dòng trùng số ký hiệu báo duplicate). Cần .env và stack đang chạy; make seed
        gọi.

Cũng là nhóm lệnh ``moc du-lieu-mo`` của scripts/moc.py. ``lay``, ``kiem`` chỉ dùng thư viện chuẩn, không đọc .env.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import io
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from types import ModuleType
from typing import Any

SCRIPTS = pathlib.Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
DIR = ROOT / "seed" / "du-lieu-mo"
MANIFEST = "manifest.json"
MAX_BYTES = 3 * 1024 * 1024     # luật dữ liệu ngoài của đội: bản chụp mỗi nguồn nhỏ
TEXT_KEYS = ("source", "name", "publisher", "home_url", "reuse_basis", "fetched_at")
# tên trơn hoặc một tầng thư mục con (câu trích trich/*.txt của ngay-nghi-le); không phần nào bắt đầu bằng "."
FILE_NAME = re.compile(r"(?:[a-z0-9][a-z0-9._-]{0,99}/)?[a-z0-9][a-z0-9._-]{0,99}")
SHA256 = re.compile(r"[0-9a-f]{64}")
CLERK = "vanthu"                # văn thư Khoa CNTT của đơn vị mẫu (seed/users.csv)
# cột của lô văn bản đến (schemas/van-ban-den.json; svc-files imports/parse.py), ``files`` là tên tệp trong zip
COLUMNS = ("type_code", "symbol", "issuer_name", "issued_on", "summary", "urgency", "files")
DOC_KEYS = COLUMNS[:5]          # meta có đủ các khóa này thì tệp là một văn bản để nạp


def sources() -> dict[str, ModuleType]:
    """Mã nguồn → module scripts/nguon_*.py."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    found: dict[str, ModuleType] = {}
    for path in sorted(SCRIPTS.glob("nguon_*.py")):
        mod = importlib.import_module(path.stem)
        if path.stem != "nguon_" + mod.NGUON.replace("-", "_"):
            raise SystemExit(f"{path.name}: NGUON = {mod.NGUON!r} không khớp tên tệp")
        found[mod.NGUON] = mod
    return found


def problems(manifest: Any, folder: pathlib.Path, source: str | None = None) -> list[str]:
    """Chỗ sai của một bản chụp: khuôn manifest (HOP-DONG mục 2), tên tệp, có tệp, cỡ, SHA-256, tổng cỡ. Rỗng: đúng."""
    if not isinstance(manifest, dict):
        return ["manifest không phải object JSON"]
    out = [f"thiếu hoặc sai kiểu khóa {k}" for k in TEXT_KEYS if not isinstance(manifest.get(k), str)]
    if source is not None and manifest.get("source") != source:
        out.append(f"source là {manifest.get('source')!r}, thư mục là {source!r}")
    age = manifest.get("max_age_days")
    if isinstance(age, bool) or not isinstance(age, int) or age < 1:       # bool là int: true không phải số ngày
        out.append("max_age_days phải là số nguyên dương")
    if _when(manifest.get("fetched_at")) is None:
        out.append("fetched_at không phải thời điểm ISO 8601 có múi giờ")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        return [*out, "files rỗng"]
    total, seen = 0, set()
    for n, f in enumerate(files, 1):
        name = f.get("file") if isinstance(f, dict) else None
        if not isinstance(name, str) or not FILE_NAME.fullmatch(name) or name == MANIFEST or name in seen:
            out.append(f"tệp {n}: tên {name!r} không hợp lệ hoặc trùng")
            continue
        seen.add(name)
        if not isinstance(f.get("url"), str) or not isinstance(f.get("meta"), dict):
            out.append(f"{name}: thiếu url hoặc meta")
        path = folder / name
        if not path.is_file():
            out.append(f"{name}: không có tệp")
            continue
        data = path.read_bytes()
        total += len(data)
        if not isinstance(f.get("sha256"), str) or not SHA256.fullmatch(f["sha256"]):
            out.append(f"{name}: sha256 không hợp lệ")
        elif hashlib.sha256(data).hexdigest() != f["sha256"]:
            out.append(f"{name}: SHA-256 không khớp manifest")
        if f.get("bytes") != len(data):
            out.append(f"{name}: cỡ {len(data)} byte, manifest ghi {f.get('bytes')}")
    if total > MAX_BYTES:
        out.append(f"tổng {total} byte, quá {MAX_BYTES // (1024 * 1024)} MB")
    return out


def _when(value: Any) -> datetime | None:
    try:
        at = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return at if at.tzinfo is not None else None


def check(folder: pathlib.Path, now: datetime | None = None) -> dict[str, Any]:
    """Trạng thái một bản chụp như khóa ``open_data`` của /api/status: ok, stale (quá max_age_days), broken."""
    now = now or datetime.now(timezone.utc)
    try:
        manifest = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"source": folder.name, "state": "broken", "age_days": None, "problems": [f"{MANIFEST}: {exc}"]}
    bad = problems(manifest, folder, folder.name)
    at = _when(manifest.get("fetched_at")) if isinstance(manifest, dict) else None
    age = (now - at).days if at else None
    if bad:
        state = "broken"
    else:
        state = "stale" if age is not None and age > manifest["max_age_days"] else "ok"
    return {"source": folder.name, "state": state, "age_days": age,
            "max_age_days": manifest.get("max_age_days") if isinstance(manifest, dict) else None,
            "files": len(manifest.get("files") or []) if isinstance(manifest, dict) else 0, "problems": bad}


def replace(target: pathlib.Path, staged: pathlib.Path, manifest: dict[str, Any]) -> None:
    """Đưa bản vừa lấy (đã kiểm) vào ``target``: từng tệp os.replace, manifest ghi sau cùng, rồi xóa tệp cũ không còn
    trong manifest mới. README và tệp khác của thư mục giữ nguyên."""
    target.mkdir(parents=True, exist_ok=True)
    old = set()
    try:
        old = {f["file"] for f in json.loads((target / MANIFEST).read_text(encoding="utf-8"))["files"]
               if FILE_NAME.fullmatch(str(f.get("file")))}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    new = {f["file"] for f in manifest["files"]}
    for name in sorted(new):
        dest = target / name
        dest.parent.mkdir(exist_ok=True)
        moi = dest.with_name(f".{dest.name}.moi")
        shutil.copyfile(staged / name, moi)
        os.replace(moi, dest)
    (target / f".{MANIFEST}.moi").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                              encoding="utf-8")
    os.replace(target / f".{MANIFEST}.moi", target / MANIFEST)
    for name in sorted(old - new):
        (target / name).unlink(missing_ok=True)


def cmd_lay(args: argparse.Namespace) -> int:
    mods = sources()
    chosen = args.nguon or sorted(mods)
    if unknown := [c for c in chosen if c not in mods]:
        print(f"Không có nguồn {', '.join(unknown)}; có: {', '.join(sorted(mods))}", file=sys.stderr)
        return 2
    rc = 0
    for code in chosen:
        with tempfile.TemporaryDirectory(prefix=f"du-lieu-mo-{code}-") as tmp:
            staged = pathlib.Path(tmp)
            try:
                manifest = mods[code].lay(staged)
                if bad := problems(manifest, staged, code):
                    raise ValueError("; ".join(bad))
            except Exception as exc:  # noqa: BLE001 — nguồn nào lỗi cũng giữ bản cũ, báo rồi sang nguồn sau
                print(f"{code}: không lấy được, giữ bản chụp cũ — {type(exc).__name__}: {exc}", file=sys.stderr)
                rc = 1
                continue
            replace(DIR / code, staged, manifest)
        size = sum(f["bytes"] for f in manifest["files"])
        print(f"{code}: {len(manifest['files'])} tệp, {size // 1024} KB → {(DIR / code).relative_to(ROOT)}")
    return rc


def cmd_kiem(args: argparse.Namespace) -> int:
    folders = [DIR / c for c in args.nguon] if args.nguon else sorted(p.parent for p in DIR.glob(f"*/{MANIFEST}"))
    results = [check(f) for f in folders]
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        if not results:
            print(f"Chưa có bản chụp nào trong {DIR.relative_to(ROOT)}")
        for r in results:
            age = "?" if r["age_days"] is None else r["age_days"]
            print(f"{r['source']}: {r['state']} · {r.get('files', 0)} tệp · lấy cách đây {age} ngày"
                  f" (tối đa {r.get('max_age_days')})")
            for p in r["problems"]:
                print(f"  - {p}")
    return 1 if any(r["state"] == "broken" for r in results) else 0


def documents(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Các tệp là văn bản: meta có đủ ``DOC_KEYS`` dạng chuỗi. Nguồn chỉ có dữ liệu thì rỗng."""
    return [f for f in manifest["files"] if all(isinstance(f["meta"].get(k), str) for k in DOC_KEYS)]


def batch(manifest: dict[str, Any], folder: pathlib.Path) -> tuple[bytes, bytes, str]:
    """Bản chụp → (CSV văn bản đến, zip tệp đính kèm, Idempotency-Key). Mỗi văn bản (``documents``) một dòng, tệp là
    bản chính."""
    docs = documents(manifest)
    buf = io.StringIO()
    out = csv.writer(buf, lineterminator="\n")
    out.writerow(COLUMNS)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in docs:
            m = f["meta"]
            out.writerow([m["type_code"], m["symbol"], m["issuer_name"], m["issued_on"], m["summary"], "normal",
                          f["file"]])
            info = zipfile.ZipInfo(f["file"], date_time=(2026, 1, 1, 0, 0, 0))
            zf.writestr(info, (folder / f["file"]).read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
    data = buf.getvalue().encode()
    digest = hashlib.sha256(json.dumps(docs, sort_keys=True).encode()).hexdigest()[:24]
    return data, archive.getvalue(), f"du-lieu-mo-{manifest['source']}-{digest}"


def nap(codes: list[str] | None = None, clerk_name: str = CLERK) -> int:
    """Nạp các bản chụp qua API nạp lô; thoát 0 khi mọi dòng đạt hoặc trùng (đã nạp lần trước)."""
    import nap_lo_mau
    from moc_env import PUBLIC_URL, HTTPError, Session, call_json, request   # cần .env

    folders = [DIR / c for c in codes] if codes else sorted(p.parent for p in DIR.glob(f"*/{MANIFEST}"))
    clerk = Session(clerk_name)
    rc = 0
    for folder in folders:
        state = check(folder)
        if state["state"] == "broken":
            print(f"  {folder.name}: bản chụp hỏng, không nạp — {'; '.join(state['problems'])}", file=sys.stderr)
            rc = 1
            continue
        manifest = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
        if not documents(manifest):
            print(f"  Nguồn công khai {folder.name}: không có văn bản để nạp, dùng tại chỗ")
            continue
        data, archive, key = batch(manifest, folder)
        body, content_type = nap_lo_mau.multipart([("data", f"{folder.name}.csv", "text/csv", data),
                                                   ("archive", f"{folder.name}.zip", "application/zip", archive)])
        headers = {**clerk.auth, "Content-Type": content_type, "Idempotency-Key": key}
        try:
            _, _, raw = request("POST", f"{PUBLIC_URL}/api/imports/incoming", data=body, headers=headers, timeout=120)
        except HTTPError as exc:
            print(f"  {folder.name}: API nạp lô trả {exc}", file=sys.stderr)
            rc = 1
            continue
        job = json.loads(raw)
        deadline = time.monotonic() + 300
        while job["status"] != "done" and time.monotonic() < deadline:
            time.sleep(2)
            job, _ = call_json("GET", f"{PUBLIC_URL}/api/imports/{job['id']}", headers=clerk.auth)
        if job["status"] != "done":
            print(f"  {folder.name}: lô {job['id']} chưa xong sau 5 phút", file=sys.stderr)
            rc = 1
            continue
        print(f"  Nguồn công khai {folder.name}: {job['ok']} văn bản mới, {job['duplicate']} đã có,"
              f" {job['failed']} lỗi")
        if job["failed"]:
            rc = 1
    return rc


def cmd_nap(args: argparse.Namespace) -> int:
    return nap(args.nguon or None, args.clerk)


def add_parser(groups: Any) -> None:
    d = groups.add_parser("du-lieu-mo", help="dữ liệu công khai: bản chụp seed/du-lieu-mo (#424)").add_subparsers(
        dest="cmd", required=True)
    lay = d.add_parser("lay", help="lấy mới từ nguồn, chỉ thay bản chụp khi lấy xong và băm khớp")
    lay.add_argument("nguon", nargs="*", metavar="MÃ", help="mã nguồn (mặc định: mọi nguồn)")
    lay.set_defaults(run=cmd_lay)
    kiem = d.add_parser("kiem", help="so SHA-256 với manifest, in tuổi dữ liệu")
    kiem.add_argument("nguon", nargs="*", metavar="MÃ", help="mã nguồn (mặc định: mọi bản chụp)")
    kiem.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    kiem.set_defaults(run=cmd_kiem)
    nap_ = d.add_parser("nap", help="nạp bản chụp thành văn bản đến qua API nạp lô (cần stack đang chạy)")
    nap_.add_argument("nguon", nargs="*", metavar="MÃ", help="mã nguồn (mặc định: mọi bản chụp)")
    nap_.add_argument("--clerk", default=CLERK, metavar="TÊN", help=f"văn thư nạp lô (mặc định {CLERK})")
    nap_.set_defaults(run=cmd_nap)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="du_lieu_mo", description="Dữ liệu công khai: bản chụp seed/du-lieu-mo")
    add_parser(parser.add_subparsers(dest="group", required=True))
    args = parser.parse_args(["du-lieu-mo", *(sys.argv[1:] if argv is None else argv)])
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
