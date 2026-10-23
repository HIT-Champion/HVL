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

"""make totp — mã TOTP của các tài khoản mẫu văn thư, lãnh đạo, quản trị (make seed cài sẵn khóa chung
MOC_DEMO_TOTP_SECRET). In mã hiện tại, và khóa để thêm một lần vào ứng dụng xác thực trên điện thoại.

Keycloak lấy chính chuỗi khóa làm khóa HMAC (RFC 6238, HMAC-SHA1, 6 số, 30 giây); ứng dụng xác thực nhận
khóa ở dạng base32 của chuỗi đó.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import sys
import time
import urllib.parse

from moc_env import ENV, ROOT
from seed import MFA_ROLES

PERIOD = 30
DIGITS = 6


def totp(secret: str, at: float | None = None) -> str:
    counter = int((time.time() if at is None else at) // PERIOD)
    mac = hmac.new(secret.encode(), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    return str((struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF) % 10 ** DIGITS).zfill(DIGITS)


def main() -> None:
    secret = ENV.get("MOC_DEMO_TOTP_SECRET", "")
    if not secret:
        sys.exit("Chưa có MOC_DEMO_TOTP_SECRET trong .env — thêm một chuỗi ngẫu nhiên rồi chạy lại make seed")
    key = base64.b32encode(secret.encode()).decode().rstrip("=")
    label = urllib.parse.quote("Signet:tài khoản mẫu")
    uri = f"otpauth://totp/{label}?secret={key}&issuer={urllib.parse.quote('Signet')}&digits={DIGITS}&period={PERIOD}"
    users = [line.split(",")[0] for line in (ROOT / "seed" / "users.csv").read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.startswith("#") and line.split(",")[3] in MFA_ROLES]
    print(f"Mã hiện tại: {totp(secret)}  (còn {PERIOD - int(time.time()) % PERIOD} giây)")
    print(f"Dùng cho: {', '.join(users)}")
    print(f"Thêm một lần vào ứng dụng xác thực (FreeOTP, Aegis, Google Authenticator) bằng khóa: {key}")
    print(f"hoặc liên kết: {uri}")


if __name__ == "__main__":
    main()
