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

"""Lấy bí mật từ két (F3.2): đăng nhập AppRole, đọc kv-v2, thử lại khi két chưa sẵn sàng — với két giả qua HTTP."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from svc_files.config import ConfigError, Settings
from svc_files.openbao import with_secrets

ROLE_ID, SECRET_ID, TOKEN = "role-1", "secret-1", "tok-1"
SECRETS = {"SEAWEEDFS_S3_ACCESS_KEY": "ak", "SEAWEEDFS_S3_SECRET_KEY": "sk", "HASURA_ADMIN_SECRET": "ha",
           "MEILISEARCH_API_KEY": "mk"}


class FakeBao:
    """Két giả: login đúng role_id/secret_id thì cấp token; đọc moc/data/svc-files bằng token đó thì trả bí mật.
    `fail_first` lần đầu trả 503 (két đang khóa)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail_first = 0
        self.login_status = 200
        self.revoked: list[str | None] = []
        self.on_bad_secret = None      # gọi khi login sai secret_id (giả lập két vừa cấp secret_id mới)

    def handle(self, method: str, path: str, token: str | None, body: dict | None) -> tuple[int, dict | None]:
        self.calls.append((method, path))
        if self.fail_first:
            self.fail_first -= 1
            return 503, {"errors": ["Vault is sealed"]}
        if method == "POST" and path == "/v1/auth/approle/login":
            if self.login_status != 200:
                return self.login_status, {"errors": ["permission denied"]}
            if body != {"role_id": ROLE_ID, "secret_id": SECRET_ID}:
                if self.on_bad_secret:
                    self.on_bad_secret()
                return 400, {"errors": ["invalid role or secret ID"]}
            return 200, {"auth": {"client_token": TOKEN, "lease_duration": 3600}}
        if method == "GET" and path == "/v1/moc/data/svc-files":
            if token != TOKEN:
                return 403, {"errors": ["permission denied"]}
            return 200, {"data": {"data": SECRETS, "metadata": {"version": 1}}}
        if method == "POST" and path == "/v1/auth/token/revoke-self":
            self.revoked.append(token)
            return 204, None
        return 404, {"errors": []}


@pytest.fixture
def bao() -> Iterator[tuple[FakeBao, str]]:
    fake = FakeBao()

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, method: str) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length)) if length else None
            status, payload = fake.handle(method, self.path, self.headers.get("X-Vault-Token"), body)
            data = json.dumps(payload).encode() if payload is not None else b""
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            self._reply("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._reply("POST")

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield fake, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def role_files(tmp_path) -> dict[str, str]:
    (tmp_path / "role_id").write_text(ROLE_ID + "\n")
    (tmp_path / "secret_id").write_text(SECRET_ID + "\n")
    return {"MOC_OPENBAO_ROLE_ID_FILE": str(tmp_path / "role_id"),
            "MOC_OPENBAO_SECRET_ID_FILE": str(tmp_path / "secret_id")}


def test_without_vault_env_is_unchanged():
    env = {"HASURA_ADMIN_SECRET": "tu-env", "X": "1"}
    assert with_secrets(env) == env


def test_secrets_from_vault_complete_settings(bao, role_files):
    fake, addr = bao
    env = {"MOC_OPENBAO_ADDR": addr + "/", "MOC_OIDC_ISSUER": "http://kc/realms/moc",
           "MOC_OIDC_JWKS_URL": "http://kc/certs", "HASURA_ADMIN_SECRET": "cu", **role_files}
    merged = with_secrets(env, delay_s=0)
    # bí mật trong két đè lên biến cùng tên; biến khác giữ nguyên
    assert merged["HASURA_ADMIN_SECRET"] == "ha" and merged["MOC_OIDC_ISSUER"] == "http://kc/realms/moc"
    settings = Settings.from_env(merged)
    assert (settings.s3_access_key, settings.s3_secret_key) == ("ak", "sk")
    # token chỉ dùng một lần rồi thu hồi
    assert fake.calls == [("POST", "/v1/auth/approle/login"), ("GET", "/v1/moc/data/svc-files"),
                          ("POST", "/v1/auth/token/revoke-self")]
    assert fake.revoked == [TOKEN]


def test_retries_while_vault_is_sealed(bao, role_files):
    fake, addr = bao
    fake.fail_first = 2
    merged = with_secrets({"MOC_OPENBAO_ADDR": addr, **role_files}, delay_s=0)
    assert merged["MEILISEARCH_API_KEY"] == "mk"
    assert len(fake.calls) == 5


def test_rereads_rotated_secret_id(bao, tmp_path, role_files):
    """Dịch vụ đọc secret_id cũ đúng lúc két khởi động lại cấp cái mới: thử lại bằng tệp mới, không dừng."""
    fake, addr = bao
    (tmp_path / "secret_id").write_text("cu-da-huy")
    fake.on_bad_secret = lambda: (tmp_path / "secret_id").write_text(SECRET_ID)
    merged = with_secrets({"MOC_OPENBAO_ADDR": addr, **role_files}, delay_s=0)
    assert merged["HASURA_ADMIN_SECRET"] == "ha"
    assert [c[1] for c in fake.calls[:2]] == ["/v1/auth/approle/login"] * 2


@pytest.mark.parametrize("status", [400, 403])
def test_refusal_stops_at_once(bao, role_files, status):
    fake, addr = bao
    fake.login_status = status
    with pytest.raises(ConfigError, match=f"từ chối \\({status}\\)"):
        with_secrets({"MOC_OPENBAO_ADDR": addr, **role_files}, delay_s=0)
    assert len(fake.calls) == 1


def test_wrong_secret_id_is_refused(bao, tmp_path, role_files):
    fake, addr = bao
    (tmp_path / "secret_id").write_text("cu-da-huy")
    with pytest.raises(ConfigError, match="400"):
        with_secrets({"MOC_OPENBAO_ADDR": addr, **role_files}, delay_s=0)


def test_other_service_path_is_refused(bao, role_files):
    _, addr = bao
    with pytest.raises(ConfigError, match="404"):
        with_secrets({"MOC_OPENBAO_ADDR": addr, "MOC_OPENBAO_SECRET_PATH": "moc/data/svc-workflow", **role_files},
                     delay_s=0)


def test_missing_role_files(tmp_path):
    with pytest.raises(ConfigError, match="AppRole"):
        with_secrets({"MOC_OPENBAO_ADDR": "http://127.0.0.1:9",
                      "MOC_OPENBAO_ROLE_ID_FILE": str(tmp_path / "khong-co")})


def test_gives_up_when_vault_unreachable(role_files):
    with pytest.raises(ConfigError, match="sau 3 lần thử"):
        with_secrets({"MOC_OPENBAO_ADDR": "http://127.0.0.1:9", **role_files}, attempts=3, delay_s=0,
                     timeout_s=0.5)
