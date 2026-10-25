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

"""Kiểm chính gói nguồn sẽ phát hành (dist/signet-X.Y.Z.tar.gz), không phải cây git: scripts/release.sh (make release,
ở máy) gọi ngay sau khi đóng gói, .github/workflows/release.yml gọi trước khi tạo Release.

- Toàn vẹn: tệp .sha256 cạnh gói có đúng một dòng ghi tên gói (`sha256sum -c` chạy được) và băm khớp.
- Cấu trúc (đọc header tar, chưa giải nén): mọi mục nằm dưới thư mục gốc signet-X.Y.Z/, chỉ tệp thường và thư mục (không
  symlink, hardlink, thiết bị), không đường tuyệt đối hay "..", tổng dung lượng giải nén có trần. Đạt mới giải nén vào
  thư mục tạm.
- Tệp không được phát hành: tệp môi trường thật (chỉ tệp mẫu *.example), khóa riêng (theo tên, và theo nội dung PEM nên
  .pem chỉ có chứng thư công khai vẫn qua), tệp đăng nhập, tài liệu nội bộ của đội (*.local*, COMMIT.md, publics/), phụ
  thuộc và bộ đệm (node_modules, __pycache__, .venv), dữ liệu chạy và CSDL như .gitignore, tệp lớn bất thường. Loại một
  tệp đang theo dõi khỏi gói: dòng "<đường dẫn> export-ignore" trong .gitattributes (git archive tôn trọng).
- Giấy phép: LICENSE (Apache-2.0) và NOTICE; scripts/license-header.sh check của checkout đang chạy, trên thư mục giải
  nén; mọi tệp có SPDX-License-Identifier và dòng bản quyền trong tệp, hoặc được REUSE.toml của gói khai (như reuse
  lint, bỏ qua LICENSE*, LICENSES/, REUSE.toml); giấy phép khai có toàn văn trong LICENSES/.
- Phiên bản: dòng cuối tệp VERSION của gói là vX.Y.Z — git archive điền (.gitattributes: VERSION export-subst),
  scripts/install.sh đọc khi cài từ gói.

  python3 scripts/kiem_goi.py dist/signet-1.2.0.tar.gz [--version 1.2.0]

Thoát 0 khi đạt, 1 khi gói có lỗi (liệt kê hết), 2 khi gọi sai. Chỉ dùng thư viện chuẩn (Python ≥ 3.11).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import posixpath
import re
import subprocess
import sys
import tarfile
import tempfile
import tomllib

SCRIPTS = pathlib.Path(__file__).resolve().parent
LICENSE_HEADER = SCRIPTS / "license-header.sh"

PACKAGE = re.compile(r"signet-(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\.tar\.gz")
# Tệp lớn nhất của cây lúc viết (10/2026) là văn bản mẫu scan 0,44 MB (seed/van-ban-den): trần gấp ~11 lần, còn chỗ cho
# mẫu scan thêm, vẫn bắt được bản dump CSDL, video, trọng số mô hình lỡ commit. Đổi trần thì đổi ở đây, qua PR
MAX_FILE = 5 * 1024 * 1024
# Gói giải nén lúc viết 11,3 MiB (657 tệp): quá trần là gói phình bất thường, không giải nén (phòng đầy đĩa runner)
MAX_TOTAL = 100 * 1024 * 1024

# Tên tệp môi trường ghép từ hai mảnh để công cụ quét chuỗi bí mật không bắt nhầm chính dòng này
ENV = ".e" + "nv"
KEY_NAME = re.compile(r"id_(?:rsa|dsa|ecdsa|ed25519)(?:_sk)?")
KEY_SUFFIXES = (".key", ".p12", ".pfx", ".jks", ".keystore", ".ppk")
CREDENTIALS = frozenset({".netrc", ".pgpass", ".git-credentials"})
LOCAL = re.compile(r".+\.local(?:\..+)?")
DB_SUFFIXES = (".sqlite", ".sqlite3", ".db", ".dump", ".rdb")
# Thư mục dữ liệu chạy ở gốc, như .gitignore (/data/, /volumes/, /storage/, /backups/, /.moc-apps/)
ROOT_DATA = frozenset({"data", "volumes", "storage", "backups", ".moc-apps"})
# Khối PEM khóa riêng: PKCS#8, RSA, EC, DSA, OpenSSH, ENCRYPTED, PGP … BLOCK
PRIVATE_KEY = re.compile(rb"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----")
# Khối REUSE-Ignore: công cụ reuse bỏ qua hai dòng này, không đọc nhầm thành khai giấy phép của chính tệp này
# REUSE-IgnoreStart
LICENSE_ID = re.compile(r"SPDX-License-Identifier:")
COPYRIGHT = re.compile(r"SPDX-FileCopyrightText:|Copyright|©")
# REUSE-IgnoreEnd


def forbidden(rel: str) -> tuple[str, str] | None:
    """(chỗ cần báo, lý do) khi tệp `rel` (đường dẫn trong gói, bỏ thư mục gốc) không được phát hành, không thì None.
    Lỗi theo thư mục báo một lần cho cả thư mục."""
    *dirs, name = rel.split("/")
    low = name.lower()
    for i, part in enumerate(dirs):
        where = "/".join(dirs[:i + 1]) + "/"
        if part == "publics":
            return where, "bản lưu tài liệu của BTC, không phân phối lại"
        if part in ("node_modules", "__pycache__", ".venv"):
            return where, "thư mục phụ thuộc hay bộ đệm, không phải mã nguồn"
        if i == 0 and part in ROOT_DATA:
            return where, "dữ liệu chạy của hệ thống (.gitignore), có thể có dữ liệu thật và bí mật"
    is_env = low in (ENV, ENV + "rc") or low.startswith(ENV + ".") or low.endswith(ENV)
    if is_env and not low.endswith(".example"):
        return rel, "tệp môi trường thật, có bí mật — chỉ phát hành tệp mẫu *.example"
    if KEY_NAME.fullmatch(low) or low.endswith(KEY_SUFFIXES):
        return rel, "khóa riêng hay kho khóa"
    if low in CREDENTIALS:
        return rel, "tệp thông tin đăng nhập"
    if name == "COMMIT.md" or LOCAL.fullmatch(name):
        return rel, "tài liệu nội bộ của đội (*.local*, COMMIT.md), không đưa ra ngoài"
    if low.endswith((".pyc", ".pyo")):
        return rel, "mã Python đã biên dịch, không phải mã nguồn"
    if (not dirs and name == ".moc-restoring") or low.endswith(DB_SUFFIXES):
        return rel, "tệp CSDL hay dữ liệu chạy (.gitignore)"
    return None


def reuse_glob(pattern: str) -> re.Pattern[str]:
    """Mẫu `path` của REUSE.toml: `*` khớp mọi ký tự trừ `/`, `**` khớp cả `/`, `\\*` là dấu sao thật."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("\\*", i):
            out.append(re.escape("*"))
            i += 2
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out))


def reuse_annotations(path: pathlib.Path) -> tuple[list[re.Pattern[str]], set[str]]:
    """Mẫu đường dẫn của các khối [[annotations]] có cả bản quyền và giấy phép, cùng các mã giấy phép được khai."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    globs: list[re.Pattern[str]] = []
    ids: set[str] = set()
    for block in data.get("annotations", []):
        expression = block.get("SPDX-License-Identifier")
        if not expression or not block.get("SPDX-FileCopyrightText"):
            continue
        ids.update(t for t in re.findall(r"[A-Za-z0-9.+-]+", expression) if t not in ("AND", "OR", "WITH"))
        paths = block.get("path", [])
        globs.extend(reuse_glob(p) for p in ([paths] if isinstance(paths, str) else paths))
    return globs, ids


def check_checksum(package: pathlib.Path) -> list[str]:
    sums = package.with_name(package.name + ".sha256")
    if not sums.is_file():
        return [f"thiếu {sums.name} cạnh gói"]
    lines = [line for line in sums.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    m = re.fullmatch(r"([0-9a-f]{64}) [ *](.+)", lines[0]) if len(lines) == 1 else None
    if not m:
        return [f"{sums.name} phải có đúng một dòng '<sha256>  {package.name}' (như sha256sum in ra)"]
    if m[2] != package.name:
        return [f"{sums.name} ghi tệp '{m[2]}', không phải {package.name} — sha256sum -c sẽ không thấy gói"]
    digest = hashlib.sha256()
    with package.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    if digest.hexdigest() != m[1]:
        return [f"băm SHA-256 của {package.name} không khớp {sums.name}"]
    return []


def check_members(members: list[tarfile.TarInfo], root: str) -> list[str]:
    """Cấu trúc gói từ header tar, trước khi giải nén."""
    errors: list[str] = []
    tops = sorted({m.name.split("/", 1)[0] for m in members})
    if tops != [root]:
        shown = ", ".join(f"{t}/" for t in tops) or "không có gì"
        errors.append(f"gói phải có đúng một thư mục gốc {root}/ (gói có: {shown})")
    total = 0
    for m in members:
        if m.name.startswith("/") or ".." in m.name.split("/"):
            errors.append(f"{m.name}: đường dẫn thoát ra ngoài thư mục giải nén")
        elif not (m.isfile() or m.isdir()):
            errors.append(f"{m.name}: không phải tệp thường hay thư mục (symlink, hardlink, thiết bị)")
        total += m.size if m.isfile() else 0
    if total > MAX_TOTAL:
        errors.append(f"gói giải nén {total / 2**20:.0f} MiB, vượt trần {MAX_TOTAL // 2**20} MiB — không giải nén")
    return errors


def check_files(root: pathlib.Path, files: dict[str, int]) -> tuple[list[str], set[str]]:
    """Tệp không được phát hành và tệp quá lớn; `files` là đường dẫn trong gói → kích thước. Trả cả tập tệp đã bị
    chặn: kiểm giấy phép bỏ qua chúng, mỗi tệp chỉ báo một lỗi."""
    errors: list[str] = []
    reported: set[str] = set()
    flagged: set[str] = set()
    for rel, size in files.items():
        hit = forbidden(rel)
        if hit:
            flagged.add(rel)
            if hit[0] not in reported:
                reported.add(hit[0])
                errors.append(f"{hit[0]}: {hit[1]}")
        if size > MAX_FILE:
            flagged.add(rel)
            errors.append(f"{rel}: {size / 2**20:.1f} MiB, vượt trần {MAX_FILE // 2**20} MiB cho một tệp")
        elif not hit and PRIVATE_KEY.search((root / rel).read_bytes()):
            flagged.add(rel)
            errors.append(f"{rel}: có khối khóa riêng PEM (PRIVATE KEY)")
    return errors, flagged


def check_licenses(root: pathlib.Path, files: dict[str, int], flagged: set[str]) -> list[str]:
    errors: list[str] = []
    license_file = root / "LICENSE"
    if not license_file.is_file():
        errors.append("thiếu LICENSE (toàn văn giấy phép)")
    elif not all(s in license_file.read_text(encoding="utf-8", errors="replace")
                 for s in ("Apache License", "Version 2.0")):
        errors.append("LICENSE không phải Apache License, Version 2.0")
    notice = root / "NOTICE"
    if not notice.is_file() or not notice.read_text(encoding="utf-8", errors="replace").strip():
        errors.append("thiếu NOTICE (thông báo bản quyền và mục đích giấy phép) hoặc NOTICE rỗng")

    proc = subprocess.run(["bash", str(LICENSE_HEADER), "check", str(root)], capture_output=True, text=True,
                          check=False)
    if proc.returncode != 0:
        missing = [line.split(":", 1)[1].strip() for line in proc.stdout.splitlines() if "THIẾU header" in line]
        errors.extend(f"{rel}: thiếu header giấy phép Apache-2.0 (scripts/license-header.sh)" for rel in missing
                      if rel not in flagged)
        flagged = flagged | set(missing)
        if not missing:
            errors.append(f"scripts/license-header.sh check lỗi: {(proc.stdout + proc.stderr).strip()}")

    if not (root / "REUSE.toml").is_file():
        return errors + ["thiếu REUSE.toml (khai giấy phép cho tệp không mang được header)"]
    try:
        globs, ids = reuse_annotations(root / "REUSE.toml")
    except (tomllib.TOMLDecodeError, AttributeError, TypeError) as e:
        return errors + [f"REUSE.toml không đọc được: {e}"]
    for spdx in sorted(ids | {"Apache-2.0"}):
        if not (root / "LICENSES" / f"{spdx}.txt").is_file():
            errors.append(f"LICENSES/{spdx}.txt: thiếu toàn văn giấy phép {spdx} (REUSE)")
    for rel in files:
        if rel in flagged:
            continue
        name = posixpath.basename(rel)
        if rel.startswith("LICENSES/") or rel == "REUSE.toml" or re.match(r"(LICEN[CS]E|COPYING)([-.]|$)", name):
            continue
        if rel.endswith(".license") or f"{rel}.license" in files:
            continue
        text = (root / rel).read_bytes().decode("utf-8", errors="replace")
        if LICENSE_ID.search(text) and COPYRIGHT.search(text):
            continue
        if not any(g.fullmatch(rel) for g in globs):
            errors.append(f"{rel}: không có SPDX-License-Identifier và bản quyền trong tệp, REUSE.toml cũng không khai")
    return errors


def check_version(root: pathlib.Path, version: str) -> list[str]:
    path = root / "VERSION"
    if not path.is_file():
        return ["thiếu VERSION (install.sh lấy phiên bản từ đây khi cài từ gói)"]
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.startswith("#")]
    if len(lines) != 1:
        return [f"VERSION phải có đúng một dòng phiên bản ngoài chú thích (có {len(lines)})"]
    if lines[0].startswith("$Format:"):
        return ["VERSION chưa được git archive điền thẻ — .gitattributes thiếu dòng 'VERSION export-subst'?"]
    if lines[0] != f"v{version}":
        return [f"VERSION ghi '{lines[0]}', gói là v{version} — gói không đóng từ thẻ v{version}?"]
    return []


def check(package: pathlib.Path, version: str) -> tuple[list[str], str]:
    """Mọi lỗi của gói (rỗng là đạt) và một dòng tóm tắt."""
    root_name = f"signet-{version}"
    errors = check_checksum(package)
    try:
        with tarfile.open(package, "r:gz") as tar:
            members = tar.getmembers()
            structure = check_members(members, root_name)
            if structure:
                return errors + structure, ""
            with tempfile.TemporaryDirectory(prefix="kiem-goi-") as tmp:
                tar.extractall(tmp, filter="data")
                root = pathlib.Path(tmp) / root_name
                files = {m.name[len(root_name) + 1:]: m.size for m in members if m.isfile()}
                found, flagged = check_files(root, files)
                errors += found + check_licenses(root, files, flagged)
                errors += check_version(root, version)
    except (tarfile.TarError, OSError, EOFError) as e:
        return errors + [f"không đọc được gói .tar.gz: {e}"], ""
    total = sum(files.values())
    return errors, f"{len(files)} tệp, {total / 2**20:.1f} MiB giải nén, thư mục gốc {root_name}/, VERSION v{version}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kiểm gói nguồn signet-X.Y.Z.tar.gz trước khi phát hành.")
    parser.add_argument("package", type=pathlib.Path, help="gói, vd. dist/signet-1.2.0.tar.gz (.sha256 nằm cạnh)")
    parser.add_argument("--version", help="phiên bản phải trùng tên gói, không có tiền tố v")
    args = parser.parse_args(argv)
    m = PACKAGE.fullmatch(args.package.name)
    if not m:
        parser.error(f"tên gói phải là signet-X.Y.Z.tar.gz (đang là {args.package.name})")
    if args.version is not None and args.version != m[1]:
        parser.error(f"--version {args.version} khác phiên bản trong tên gói ({m[1]})")
    if not args.package.is_file():
        parser.error(f"không có tệp {args.package}")

    errors, summary = check(args.package, m[1])
    if not errors:
        print(f"Gói {args.package.name} đạt: {summary}; .sha256 khớp; không có tệp cấm; giấy phép đủ.")
        return 0
    annotate = bool(os.environ.get("GITHUB_ACTIONS"))
    print(f"Gói {args.package.name} KHÔNG được phát hành — {len(errors)} lỗi:")
    for error in errors:
        print(f"::error::{args.package.name}: {error}" if annotate else f"  - {error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
