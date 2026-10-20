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

"""Bí mật lấy từ két OpenBao (F3.2) lúc khởi động: đăng nhập bằng AppRole, đọc phần bí mật của riêng dịch vụ này.

Không đặt MOC_OPENBAO_ADDR thì dùng nguyên biến môi trường (test, chạy tay). Có thì role_id, secret_id đọc từ tệp
trong volume chỉ dịch vụ này gắn (két ghi lúc khởi động); bí mật trong két đè lên biến cùng tên. Két chưa sẵn sàng
thì thử lại một lúc; két từ chối (thông tin đăng nhập sai, không có quyền) thì dừng ngay — thiếu bí mật thì dịch vụ
không chạy. Token chỉ dùng để đọc một lần rồi thu hồi.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .config import ConfigError

SECRET_PATH = "moc/data/svc-workflow"


def _call(url: str, *, token: str | None = None, body: dict[str, Any] | None = None, timeout_s: float) -> Any:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Vault-Token"] = token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def _credentials(env: Mapping[str, str]) -> tuple[str, str]:
    try:
        return (Path(env.get("MOC_OPENBAO_ROLE_ID_FILE", "/run/openbao/role_id")).read_text().strip(),
                Path(env.get("MOC_OPENBAO_SECRET_ID_FILE", "/run/openbao/secret_id")).read_text().strip())
    except OSError as exc:
        raise ConfigError(f"Không đọc được thông tin đăng nhập két (AppRole): {exc}") from None


def with_secrets(env: Mapping[str, str], *, attempts: int = 30, delay_s: float = 2.0,
                 timeout_s: float = 5.0) -> dict[str, str]:
    """Biến môi trường cộng bí mật của dịch vụ trong két."""
    addr = (env.get("MOC_OPENBAO_ADDR") or "").rstrip("/")
    if not addr:
        return dict(env)
    path = env.get("MOC_OPENBAO_SECRET_PATH", SECRET_PATH).strip("/")
    problem: object = None
    for _ in range(attempts):
        # đọc lại mỗi lần: két khởi động lại thì cấp secret_id mới và hủy cái cũ
        role_id, secret_id = _credentials(env)
        token = None
        try:
            login = _call(f"{addr}/v1/auth/approle/login", body={"role_id": role_id, "secret_id": secret_id},
                          timeout_s=timeout_s)
            token = login["auth"]["client_token"]
            data = _call(f"{addr}/v1/{path}", token=token, timeout_s=timeout_s)["data"]["data"]
            return {**env, **{str(k): str(v) for k, v in data.items()}}
        except urllib.error.HTTPError as exc:
            # 400 với secret_id vừa bị thay (két đang xoay vòng): thử lại bằng tệp mới
            if exc.code == 400 and _credentials(env) != (role_id, secret_id):
                problem = "secret_id vừa được cấp lại"
                continue
            # 400: role_id/secret_id sai; 403: không có quyền đọc; 404: chưa có bí mật — chờ cũng không khá hơn
            if exc.code in (400, 403, 404):
                raise ConfigError(f"Két {addr} từ chối ({exc.code}) khi lấy bí mật {path}") from None
            problem = f"HTTP {exc.code}"        # 503: két đang khóa hoặc đang khởi động
        except (urllib.error.URLError, OSError, KeyError, TypeError, ValueError) as exc:
            problem = exc
        finally:
            if token:
                try:
                    _call(f"{addr}/v1/auth/token/revoke-self", token=token, body={}, timeout_s=timeout_s)
                except (urllib.error.URLError, OSError, ValueError):
                    pass                        # token tự hết hạn sau 1 giờ
        time.sleep(delay_s)
    raise ConfigError(f"Không lấy được bí mật từ két {addr} sau {attempts} lần thử: {problem}")
