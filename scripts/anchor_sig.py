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

"""Kiểm chữ ký mốc neo sổ kiểm toán (signet-anchor-v1) — chỉ dùng thư viện chuẩn, chạy được ở bất kỳ máy nào.

svc-files nhờ két ký mỗi mốc neo bằng khóa Ed25519 ``moc-anchor`` (services/svc-files/src/svc_files/anchors.py tả
thông điệp ký); ``moc audit anchor --to/--publish`` chép mốc kèm chữ ký ra một tệp JSON lines. Tệp này dựng lại thông
điệp từ một dòng và kiểm chữ ký theo RFC 8032 (Ed25519 thuần), viết bằng Python thuần thay vì gọi thư viện mật mã:

- ``moc audit verify --anchors`` chạy trên máy chủ chỉ có python3, không cài thêm gói nào (như mọi lệnh trong scripts/);
- người ngoài tải mã nguồn Signet về là kiểm được cả tệp mốc trên máy mình, không cần Docker, không cần hệ thống đang
  chạy, không tin container nào của máy chủ:

      python3 scripts/anchor_sig.py anchors.jsonl anchor-key.pem

  Thoát 0: mọi dòng có chữ ký đều hợp lệ; 1: có dòng chữ ký sai, hoặc dòng chưa ký đứng sau một dòng đã ký; 2: không
  đọc được tệp, hoặc có dòng ký bằng khóa không có trong tệp khóa. Dòng chưa ký đứng trước mọi dòng đã ký (mốc ghi
  trước khi két có khóa) chỉ được đếm.

Chỉ kiểm, không ký: không có khóa riêng nào ở đây, nên mã không cần chạy trong thời gian hằng (khóa công khai, thông
điệp, chữ ký đều công khai). Kiểm từng dòng một bằng OpenSSL 3 cũng được — docs/van-hanh.md mục "Mốc neo công khai".
Test so với vectơ của RFC 8032 §7.1 và một chữ ký két ra (scripts/tests/test_moc_neo.py).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import pathlib
import re
import sys
from collections.abc import Iterable
from typing import Any

MESSAGE = "signet-anchor-v1"
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
HASH = re.compile(r"^[0-9a-f]{64}$")
SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")    # DER SubjectPublicKeyInfo của Ed25519 (RFC 8410)
PEM_BLOCK = re.compile(r"-----BEGIN PUBLIC KEY-----(.*?)-----END PUBLIC KEY-----", re.S)

# --- Ed25519, chỉ phần kiểm (RFC 8032 §5.1, §6) -------------------------------------------------------------------

_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)
Point = tuple[int, int, int, int]       # tọa độ mở rộng (X, Y, Z, T), x = X/Z, y = Y/Z, xy = T/Z


def _add(p: Point, q: Point) -> Point:
    a = (p[1] - p[0]) * (q[1] - q[0]) % _P
    b = (p[1] + p[0]) * (q[1] + q[0]) % _P
    c = 2 * p[3] * q[3] * _D % _P
    d = 2 * p[2] * q[2] % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return e * f % _P, g * h % _P, f * g % _P, e * h % _P


def _mul(s: int, p: Point) -> Point:
    q: Point = (0, 1, 1, 0)                 # điểm trung hòa
    while s > 0:
        if s & 1:
            q = _add(q, p)
        p = _add(p, p)
        s >>= 1
    return q


def _equal(p: Point, q: Point) -> bool:
    return (p[0] * q[2] - q[0] * p[2]) % _P == 0 and (p[1] * q[2] - q[1] * p[2]) % _P == 0


def _recover_x(y: int, sign: int) -> int | None:
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P != 0:
        return None
    return _P - x if (x & 1) != sign else x


def _decompress(s: bytes) -> Point | None:
    y = int.from_bytes(s, "little")
    sign, y = y >> 255, y & ((1 << 255) - 1)
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _P)


_GY = 4 * pow(5, _P - 2, _P) % _P
_GX = _recover_x(_GY, 0)
assert _GX is not None
_G: Point = (_GX, _GY, 1, _GX * _GY % _P)


def ed25519_verify(public: bytes, message: bytes, signature: bytes) -> bool:
    """Chữ ký Ed25519 (64 byte) của message có khớp khóa công khai (32 byte) không — RFC 8032 §5.1.7."""
    if len(public) != 32 or len(signature) != 64:
        return False
    a, r = _decompress(public), _decompress(signature[:32])
    s = int.from_bytes(signature[32:], "little")
    if a is None or r is None or s >= _L:
        return False
    h = int.from_bytes(hashlib.sha512(signature[:32] + public + message).digest(), "little") % _L
    return _equal(_mul(s, _G), _add(r, _mul(h, a)))


# --- khóa công khai, thông điệp ----------------------------------------------------------------------------------

def fingerprint(raw: bytes) -> str:
    """``sha256:<hex>`` của DER SubjectPublicKeyInfo — như ``openssl pkey -pubin -outform DER | sha256sum``."""
    return "sha256:" + hashlib.sha256(SPKI_PREFIX + raw).hexdigest()


def public_keys(text: str) -> dict[str, bytes]:
    """Mọi khóa Ed25519 trong một tệp PEM (một hoặc nhiều khối PUBLIC KEY) → {vân tay: 32 byte}. Khối không phải khóa
    Ed25519 thì ValueError."""
    keys = {}
    for body in PEM_BLOCK.findall(text):
        try:
            der = base64.b64decode("".join(body.split()), validate=True)
        except binascii.Error:
            raise ValueError("khối PEM không phải base64") from None
        if len(der) != len(SPKI_PREFIX) + 32 or not der.startswith(SPKI_PREFIX):
            raise ValueError("không phải khóa công khai Ed25519")
        raw = der[len(SPKI_PREFIX):]
        keys[fingerprint(raw)] = raw
    if not keys:
        raise ValueError("không có khối -----BEGIN PUBLIC KEY-----")
    return keys


def message(audit_id: int, hash_hex: str, anchored_at: str, system: str) -> bytes:
    """Thông điệp két ký cho một mốc: năm dòng, dòng nào cũng kết thúc bằng \\n. Trường sai dạng: ValueError."""
    if (type(audit_id) is not int or audit_id < 1 or not HASH.match(hash_hex) or not STAMP.match(anchored_at)
            or not system or any(ch in system for ch in "\r\n")):
        raise ValueError("mốc neo không đúng dạng signet-anchor-v1")
    return "".join(f"{line}\n" for line in (MESSAGE, str(audit_id), hash_hex, anchored_at, system)).encode()


def check(anchor: dict[str, Any], keys: dict[str, bytes]) -> str:
    """Một dòng mốc (dạng ``moc audit anchor --to`` ghi) → ``valid`` | ``invalid`` (chữ ký sai, hoặc dòng có chữ ký
    mà không dựng được thông điệp) | ``unsigned`` (dòng không có chữ ký) | ``unknown_key`` (không có khóa nào khớp vân
    tay của dòng)."""
    if not anchor.get("sig"):
        return "unsigned"
    raw = keys.get(str(anchor.get("key") or ""))
    if raw is None:
        return "unknown_key"
    try:
        if anchor.get("v") != MESSAGE:
            return "invalid"
        text = message(anchor["audit_id"], anchor["hash"], anchor["anchored_at"], anchor["system"])
        sig = base64.b64decode(str(anchor["sig"]), validate=True)
    except (KeyError, TypeError, ValueError, binascii.Error):
        return "invalid"
    return "valid" if ed25519_verify(raw, text, sig) else "invalid"


def check_all(anchors: Iterable[dict[str, Any]], keys: dict[str, bytes]) -> list[str]:
    """Các dòng của một tệp mốc, theo thứ tự trong tệp → kết quả từng dòng như check(), thêm ``unsigned_late``: dòng
    không có chữ ký đứng sau một dòng có chữ ký. Két có khóa rồi thì ``moc audit anchor`` không ghi mốc chưa ký nữa,
    nên dòng như vậy là chữ ký đã bị gỡ khỏi dòng: lỗi như chữ ký sai. Dòng chưa ký đứng trước mọi dòng có chữ ký là
    mốc ghi khi két chưa có khóa (gỡ chữ ký của mọi dòng từ đầu tệp thì chỉ lịch sử git của kho công khai cho thấy)."""
    results, signed = [], False
    for anchor in anchors:
        result = check(anchor, keys)
        results.append("unsigned_late" if result == "unsigned" and signed else result)
        signed = signed or result != "unsigned"
    return results


def _lines(path: pathlib.Path) -> Iterable[tuple[int, dict[str, Any]]]:
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip() and not line.lstrip().startswith("#"):
            yield n, json.loads(line)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 2:
        print("Dùng: python3 anchor_sig.py TỆP_MỐC TỆP_KHÓA.pem [TỆP_KHÓA.pem ...]", file=sys.stderr)
        return 2
    try:
        keys: dict[str, bytes] = {}
        for name in args[1:]:
            keys.update(public_keys(pathlib.Path(name).read_text(encoding="utf-8")))
        lines = list(_lines(pathlib.Path(args[0])))
    except (OSError, ValueError) as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2
    labels = {"valid": "chữ ký hợp lệ", "invalid": "CHỮ KÝ SAI", "unsigned": "chưa ký",
              "unsigned_late": "CHƯA KÝ SAU DÒNG ĐÃ KÝ", "unknown_key": "ký bằng khóa không có trong tệp khóa"}
    counts = dict.fromkeys(labels, 0)
    for (n, anchor), result in zip(lines, check_all((anchor for _, anchor in lines), keys)):
        counts[result] += 1
        mark = "✓" if result == "valid" else "✗" if result in ("invalid", "unsigned_late") else "·"
        print(f"  {mark} dòng {n}: mốc #{anchor.get('audit_id')} {str(anchor.get('hash'))[:16]}"
              f" {anchor.get('anchored_at') or ''} — {labels[result]}")
    print(", ".join(f"{labels[k]}: {v}" for k, v in counts.items()))
    return 1 if counts["invalid"] or counts["unsigned_late"] else 2 if counts["unknown_key"] else 0


if __name__ == "__main__":
    sys.exit(main())
