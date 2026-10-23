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

"""Kiểm giấy phép của mọi gói, kể cả gói gián tiếp, trong SBOM CycloneDX do `make sbom` sinh (Syft đọc tệp khóa npm,
requirements.txt, workflow) theo chính sách của DEPENDENCIES.md, mục "Kiểm tra tương thích giấy phép". Job
"Giấy phép (PoF #2)" của CI chạy ngay sau `make sbom`.

- Qua: giấy phép trong ALLOWED. Biểu thức SPDX: OR qua khi một nhánh qua (gói cho chọn giấy phép thì Signet chọn giấy
  phép được nhận, như node-forge theo BSD-3-Clause), AND phải qua mọi phần. Gói ghi nhiều mục giấy phép tính là AND.
- Qua nhưng liệt kê riêng: copyleft yếu (WEAK_COPYLEFT) — chỉ nhận cho thư viện dùng nguyên bản, không sửa.
- Không qua: GPL, AGPL (chỉ nhận ở dạng dịch vụ độc lập, tức image trong docker-compose.yml — không nằm trong SBOM của
  cây mã nguồn), mọi giấy phép khác, và giấy phép chưa rõ: SBOM không ghi, hay ghi chữ tự do không phải mã SPDX.
- Ngoại lệ có lý do trong .github/license-exceptions.json, mỗi mục một gói:
  * gói mang giấy phép ngoài danh sách (CC-BY-4.0 của caniuse-lite…): `giay_phep` phải trùng giấy phép SBOM ghi — gói
    đổi giấy phép thì ngoại lệ hết tác dụng;
  * gói SBOM không rõ giấy phép (PyPI chỉ khai bằng classifier, action GitHub…): `giay_phep` là giấy phép đội đã đọc
    trong gói, bắt buộc kèm `phien_ban` — nâng bản thì đọc lại.
  Ngoại lệ không còn gói nào cần tới thì chỉ cảnh báo.

  python3 scripts/license_audit.py dist/moc-1.1.0.cdx.json [--ngoai-le .github/license-exceptions.json]

Thoát 0 khi đạt, 1 khi có gói không đạt, 2 khi SBOM hay tệp ngoại lệ sai định dạng. Chỉ dùng thư viện chuẩn.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import os
import pathlib
import re
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
WAIVERS = ROOT / ".github" / "license-exceptions.json"

# DEPENDENCIES.md, "Kiểm tra tương thích giấy phép": giấy phép dễ dãi được OSI phê duyệt, và PSF-2.0 của chính Python
ALLOWED = frozenset({"Apache-2.0", "MIT", "MIT-0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD", "BlueOak-1.0.0",
                     "PostgreSQL", "MPL-2.0", "PSF-2.0"})
# Copyleft yếu: nhận cho thư viện, phông dùng nguyên bản, không sửa (Pyphen theo MPL-1.1, Pango, phông Liberation)
WEAK_COPYLEFT = frozenset({"MPL-1.1", "LGPL-2.1-only", "LGPL-2.1-or-later", "OFL-1.1"})
# Copyleft mạnh: chỉ nhận ở dạng dịch vụ độc lập giao tiếp qua mạng, không bao giờ là thư viện của Signet
STRONG_COPYLEFT = re.compile(r"A?GPL-")
KNOWN = {name.lower(): name for name in ALLOWED | WEAK_COPYLEFT}
# Chữ tự do Syft lấy từ trường license của PyPI: chỉ những cách viết không thể hiểu khác ("BSD License" thì không rõ
# hai hay ba điều khoản, "Dual License" không nói giấy phép nào — để chưa rõ)
FREE_TEXT = {"apache 2.0": "Apache-2.0", "apache license 2.0": "Apache-2.0",
             "apache license, version 2.0": "Apache-2.0", "mit license": "MIT", "the mit license": "MIT",
             "isc license": "ISC"}
GNU_ID = re.compile(r"((?:A|L)?GPL-\d\.\d)(\+|-only|-or-later)?", re.I)

PASS, WEAK, FAIL = 0, 1, 2


class FormatError(ValueError):
    """SBOM, tệp ngoại lệ hay biểu thức giấy phép sai định dạng."""


# --- Biểu thức SPDX ---------------------------------------------------------------------------------------------------

def normalize_id(token: str) -> str:
    """Mã SPDX về dạng chuẩn: đúng hoa thường của danh sách; mã GNU cũ (GPL-2.0, LGPL-2.1+) về -only / -or-later;
    hậu tố + của giấy phép khác (dùng được bản đó trở lên) bỏ đi."""
    gnu = GNU_ID.fullmatch(token)
    if gnu:
        later = (gnu[2] or "").lower() in ("+", "-or-later")
        return f"{gnu[1].upper()}{'-or-later' if later else '-only'}"
    token = token.removesuffix("+")
    return KNOWN.get(token.lower(), token)


def parse(text: str) -> tuple:
    """Biểu thức SPDX → cây ("OR" | "AND", [con]) hay ("ID", mã, ngoại lệ WITH | None). Toán tử không phân biệt hoa
    thường (npm hay viết "MIT or Apache-2.0")."""
    tokens = re.findall(r"\(|\)|[^\s()]+", text)
    pos = 0

    def peek() -> str | None:
        return tokens[pos].upper() if pos < len(tokens) else None

    def take() -> str:
        nonlocal pos
        if pos >= len(tokens):
            raise FormatError(f"biểu thức giấy phép dở dang: {text!r}")
        pos += 1
        return tokens[pos - 1]

    def node(op: str) -> tuple:
        lower = "AND" if op == "OR" else None
        parts = [node(lower) if lower else atom()]
        while peek() == op:
            take()
            parts.append(node(lower) if lower else atom())
        flat = [c for p in parts for c in (p[1] if p[0] == op else [p])]
        return flat[0] if len(flat) == 1 else (op, flat)

    def atom() -> tuple:
        token = take()
        if token == "(":
            inner = node("OR")
            if take() != ")":
                raise FormatError(f"thiếu dấu đóng ngoặc: {text!r}")
            return inner
        if token == ")" or token.upper() in ("AND", "OR", "WITH"):
            raise FormatError(f"biểu thức giấy phép sai ở {token!r}: {text!r}")
        if peek() == "WITH":
            take()
            return ("ID", normalize_id(token), take())
        return ("ID", normalize_id(token), None)

    tree = node("OR")
    if pos != len(tokens):
        raise FormatError(f"biểu thức giấy phép thừa {tokens[pos]!r}: {text!r}")
    return tree


def render(tree: tuple, top: bool = True) -> str:
    """Cây → chuỗi chuẩn (toán hạng sắp xếp) để so hai cách viết cùng một giấy phép."""
    if tree[0] == "ID":
        return tree[1] + (f" WITH {tree[2]}" if tree[2] else "")
    text = f" {tree[0]} ".join(sorted(render(c, False) for c in tree[1]))
    return text if top else f"({text})"


def judge(tree: tuple) -> tuple[int, str]:
    """(mức, lý do) theo chính sách: OR lấy nhánh tốt nhất, AND lấy phần tệ nhất. WITH chỉ thêm quyền nên xét mã gốc."""
    if tree[0] == "ID":
        name = tree[1]
        if name in ALLOWED:
            return PASS, ""
        if name in WEAK_COPYLEFT:
            return WEAK, ""
        if STRONG_COPYLEFT.match(name):
            return FAIL, f"{name} là copyleft mạnh, chỉ nhận ở dạng dịch vụ độc lập, không làm thư viện"
        return FAIL, f"{name} ngoài danh sách giấy phép được nhận"
    results = [judge(c) for c in tree[1]]
    pick = min if tree[0] == "OR" else max
    return pick(results, key=lambda r: r[0])


# --- SBOM và ngoại lệ -------------------------------------------------------------------------------------------------

def package_key(purl: str) -> str:
    """pkg:pypi/Foo_Bar@1.0?x=y → pkg:pypi/foo-bar: bỏ phiên bản, qualifier; @ của namespace npm giải mã; tên PyPI
    theo PEP 503."""
    base = urllib.parse.unquote(purl.split("?", 1)[0].split("#", 1)[0])
    head, _, last = base.rpartition("/")
    base = f"{head}/{last.split('@', 1)[0]}" if head else base
    kind, _, name = base.partition("/")
    kind = kind.lower()
    if kind == "pkg:pypi":
        name = re.sub(r"[-_.]+", "-", name).lower()
    return f"{kind}/{name}"


def sbom_license(component: dict) -> tuple[str | None, str]:
    """(biểu thức chuẩn, hay None khi chưa rõ; chữ gốc trong SBOM để in)."""
    parts, raw, unknown = [], [], False
    for entry in component.get("licenses") or []:
        lic = entry.get("license") or {}
        text = entry.get("expression") or lic.get("id")
        if text:
            parts.append(text)
            raw.append(text)
            continue
        name = (lic.get("name") or "").strip()
        raw.append(name)
        alias = FREE_TEXT.get(" ".join(name.lower().split()))
        if alias:
            parts.append(alias)
        else:
            unknown = True
    if unknown or not parts:
        return None, " · ".join(raw)
    try:
        tree = parse(" AND ".join(f"({p})" for p in parts))
    except FormatError:
        return None, " · ".join(raw)
    return render(tree), " · ".join(raw)


@dataclasses.dataclass
class Waiver:
    package: str
    versions: frozenset[str] | None
    license: str
    reason: str
    used: bool = False


@dataclasses.dataclass
class Package:
    purl: str
    version: str
    locations: set[str]
    license: str | None
    raw: str
    level: int = FAIL
    problem: str = ""
    waiver: Waiver | None = None


def load_waivers(path: pathlib.Path) -> list[Waiver]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FormatError(f"không đọc được {path}: {exc}") from exc
    items = data.get("ngoai_le") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise FormatError(f"{path}: thiếu danh sách \"ngoai_le\"")
    result = []
    for i, item in enumerate(items, 1):
        where = f"{path}, ngoại lệ thứ {i}"
        if not isinstance(item, dict):
            raise FormatError(f"{where}: phải là một đối tượng")
        for key in ("goi", "giay_phep", "ly_do"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise FormatError(f"{where}: thiếu \"{key}\" (mọi ngoại lệ phải ghi gói, giấy phép và lý do)")
        if not item["goi"].startswith("pkg:") or "@" in item["goi"].rpartition("/")[2]:
            raise FormatError(f"{where}: \"goi\" là purl không kèm phiên bản, vd. pkg:npm/caniuse-lite")
        versions = item.get("phien_ban")
        if isinstance(versions, str):
            versions = [versions]
        if versions is not None and (not isinstance(versions, list) or not versions
                                     or not all(isinstance(v, str) and v for v in versions)):
            raise FormatError(f"{where}: \"phien_ban\" là một chuỗi hay danh sách chuỗi")
        unknown_keys = set(item) - {"goi", "phien_ban", "giay_phep", "ly_do"}
        if unknown_keys:
            raise FormatError(f"{where}: khóa lạ {sorted(unknown_keys)}")
        try:
            license_ = render(parse(item["giay_phep"]))
        except FormatError as exc:
            raise FormatError(f"{where}: {exc}") from exc
        result.append(Waiver(package_key(item["goi"]), frozenset(versions) if versions else None, license_,
                             item["ly_do"].strip()))
    return result


def collect(sbom: dict) -> list[Package]:
    """Gói trong SBOM, mỗi purl một lần (Syft ghi mỗi tệp khóa một mục), kèm mọi tệp khóa nơi gặp. Mục kiểu "file"
    (chính tệp khóa) bỏ qua."""
    if not isinstance(sbom, dict) or sbom.get("bomFormat") != "CycloneDX":
        raise FormatError("không phải SBOM CycloneDX JSON (thiếu \"bomFormat\": \"CycloneDX\")")
    packages: dict[str, Package] = {}
    stack = list(sbom.get("components") or [])
    while stack:
        comp = stack.pop(0)
        stack.extend(comp.get("components") or [])
        if comp.get("type") == "file":
            continue
        version = str(comp.get("version") or "")
        purl = comp.get("purl") or f"{comp.get('name', '?')}@{version}"
        locations = {p["value"].lstrip("/") for p in comp.get("properties") or []
                     if re.fullmatch(r"syft:location:\d+:path", str(p.get("name")))}
        license_, raw = sbom_license(comp)
        seen = packages.get(purl)
        if seen is None:
            packages[purl] = Package(purl, version, locations, license_, raw)
            continue
        seen.locations |= locations
        if seen.license != license_:
            # cùng purl mà hai tệp khóa ghi khác: tính cả hai, thiếu một bên là chưa rõ
            seen.license = render(parse(f"({seen.license}) AND ({license_})")) if seen.license and license_ else None
            seen.raw = f"{seen.raw} · {raw}" if raw and raw != seen.raw else seen.raw
    return list(packages.values())


def audit(packages: list[Package], waivers: list[Waiver]) -> None:
    """Đặt mức, lý do, ngoại lệ đã dùng cho từng gói (sửa tại chỗ)."""
    by_key: dict[str, list[Waiver]] = collections.defaultdict(list)
    for waiver in waivers:
        by_key[waiver.package].append(waiver)
    for pkg in packages:
        candidates = by_key.get(package_key(pkg.purl), []) if pkg.purl.startswith("pkg:") else []
        match = next((w for w in candidates if w.versions is None or pkg.version in w.versions), None)
        if pkg.license is not None:
            pkg.level, pkg.problem = judge(parse(pkg.license))
            if pkg.level != FAIL:
                continue
            if match is not None and match.license == pkg.license:
                pkg.level, pkg.problem, pkg.waiver, match.used = PASS, "", match, True
                continue
            if match is not None:
                pkg.problem = (f"ngoại lệ ghi {match.license} nhưng SBOM ghi {pkg.license} — đọc lại giấy phép của gói "
                               "rồi sửa ngoại lệ")
        else:
            pkg.problem = "chưa rõ giấy phép: " + (f"SBOM ghi \"{pkg.raw}\", không phải mã SPDX" if pkg.raw
                                                   else "SBOM không ghi giấy phép")
            if match is not None and match.versions is None:
                pkg.problem += "; ngoại lệ cho gói chưa rõ giấy phép phải ghi \"phien_ban\" (bản đã đọc giấy phép)"
            elif match is not None:
                level, _ = judge(parse(match.license))
                pkg.level, pkg.problem, pkg.waiver, match.used = (WEAK if level == WEAK else PASS), "", match, True
                continue
        if match is None and candidates:
            versions = sorted(v for w in candidates for v in w.versions or ())
            pkg.problem += f"; ngoại lệ chỉ cho bản {', '.join(versions)} — đọc giấy phép của bản {pkg.version} rồi sửa"
        elif match is None:
            pkg.problem += "; chưa có ngoại lệ"


# --- Báo cáo ----------------------------------------------------------------------------------------------------------

def ecosystem(purl: str) -> str:
    return purl.split("/", 1)[0].removeprefix("pkg:") if purl.startswith("pkg:") else "khác"


def effective(pkg: Package) -> str:
    if pkg.level == FAIL:
        return "(không đạt)"
    return pkg.license if pkg.license is not None else pkg.waiver.license


def report(packages: list[Package], waivers: list[Waiver], waivers_path: str, source: str,
           annotate: bool) -> tuple[str, int]:
    """(văn bản báo cáo, mã thoát). `annotate`: thêm dòng ::error::/::warning:: cho trang Actions."""
    out: list[str] = []
    kinds = collections.Counter(ecosystem(p.purl) for p in packages)
    out.append(f"{source}: {len(packages)} gói khác nhau — "
               + ", ".join(f"{k} {n}" for k, n in sorted(kinds.items(), key=lambda kv: (-kv[1], kv[0]))))
    out.append("Giấy phép (số gói):")
    for name, count in sorted(collections.Counter(effective(p) for p in packages).items(),
                              key=lambda kv: (-kv[1], kv[0])):
        out.append(f"  {count:5}  {name}")
    weak = [p for p in packages if p.level == WEAK]
    if weak:
        out.append(f"Copyleft yếu, chỉ nhận khi dùng nguyên bản (DEPENDENCIES.md): {len(weak)} gói")
        out.extend(f"  {p.purl}  {effective(p)}" for p in sorted(weak, key=lambda p: p.purl))
    excepted = [p for p in packages if p.waiver is not None]
    if excepted:
        out.append(f"Qua nhờ ngoại lệ có lý do ({waivers_path}): {len(excepted)} gói")
        out.extend(f"  {p.purl}  {p.waiver.license}" + ("  (khai tay: SBOM không rõ giấy phép)" if p.license is None
                                                            else "")
                   for p in sorted(excepted, key=lambda p: p.purl))
    for waiver in waivers:
        if not waiver.used:
            versions = f"@{','.join(sorted(waiver.versions))}" if waiver.versions else ""
            text = f"ngoại lệ {waiver.package}{versions} không còn gói nào cần tới — gỡ khỏi {waivers_path}"
            out.append(f"::warning::{text}" if annotate else f"Cảnh báo: {text}")
    failed = sorted((p for p in packages if p.level == FAIL), key=lambda p: p.purl)
    if not failed:
        out.append(f"Đạt: {len(packages)}/{len(packages)} gói có giấy phép được nhận.")
        return "\n".join(out) + "\n", 0
    out.append(f"KHÔNG ĐẠT: {len(failed)}/{len(packages)} gói có giấy phép chưa rõ hoặc không được nhận:")
    for p in failed:
        where = f" ({', '.join(sorted(p.locations))})" if p.locations else ""
        out.append(f"  - {p.purl}{where}: {p.problem}")
        if annotate:
            out.append(f"::error::Giấy phép không đạt: {p.purl}: {p.problem}")
    if any(p.license is None and not p.raw and ecosystem(p.purl) == "pypi" for p in failed):
        out.append("Gói Python: requirements.txt không ghi giấy phép, make sbom hỏi PyPI (syft --enrich python) — "
                   "không có mạng thì SBOM thiếu giấy phép của mọi gói Python.")
    out.append(f"Cách sửa: thay gói; hoặc đọc giấy phép trong chính gói rồi thêm ngoại lệ có lý do vào {waivers_path} "
               "(gói SBOM không rõ giấy phép cần cả \"phien_ban\"). Chính sách: DEPENDENCIES.md, mục \"Kiểm tra tương "
               "thích giấy phép\".")
    return "\n".join(out) + "\n", 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kiểm giấy phép mọi gói trong SBOM CycloneDX (make sbom).")
    parser.add_argument("sbom", type=pathlib.Path, help="tệp SBOM CycloneDX JSON, vd. dist/moc-1.1.0.cdx.json")
    parser.add_argument("--ngoai-le", type=pathlib.Path, default=WAIVERS, help="tệp ngoại lệ có lý do")
    args = parser.parse_args(argv)
    try:
        sbom = json.loads(args.sbom.read_text(encoding="utf-8"))
        waivers = load_waivers(args.ngoai_le)
        packages = collect(sbom)
        audit(packages, waivers)
    except (OSError, ValueError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2
    meta = sbom.get("metadata") or {}
    root = meta.get("component") or {}
    tools = (meta.get("tools") or {}).get("components") or []
    made_by = ", ".join(f"{t.get('name')} {t.get('version')}" for t in tools if isinstance(t, dict))
    source = f"SBOM {root.get('name', '?')} {root.get('version', '')}".rstrip() + f" ({args.sbom}"
    source += f", {made_by})" if made_by else ")"
    shown = args.ngoai_le.resolve()
    shown = shown.relative_to(ROOT) if shown.is_relative_to(ROOT) else args.ngoai_le
    text, code = report(packages, waivers, str(shown), source, annotate=bool(os.environ.get("GITHUB_ACTIONS")))
    sys.stdout.write(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
