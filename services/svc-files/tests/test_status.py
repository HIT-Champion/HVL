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

"""Trạng thái hệ thống công khai (GET /api/status, status.py): chỉ ra chữ cố định đã làm sạch — không tên máy, URL nội
bộ, địa chỉ IP, thông báo lỗi —; lưu đệm và gom một lượt cho mọi người gọi cùng lúc; lần dò treo bị cắt theo hạn, không
mở thêm lần dò mới cho thành phần đang treo; tính trạng thái chung; Hasura đọc giờ sao lưu gần nhất."""

import asyncio
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx2
import pytest
from conftest import FakeHasura, FakeMeili, FakeScanner, FakeStore, FakeVault
from fastapi.testclient import TestClient

from svc_files.app import create_app
from svc_files.config import ConfigError, Settings
from svc_files.hasura import HasuraClient, HasuraError
from svc_files.status import Component, StatusBoard, default_board, public_model, public_version

BACKUP_AT = datetime(2026, 10, 23, 1, 30, tzinfo=UTC)
JWKS = {"keys": [{"kid": "k1", "kty": "RSA", "alg": "RS256", "use": "sig", "n": "AQAB", "e": "AQAB"}]}

# Dấu hiệu lộ thông tin nội bộ: URL, tên máy kèm cổng hay tên miền, địa chỉ IP, đường dẫn realm, tên lớp lỗi,
# vết ngăn xếp
LEAKS = [
    re.compile(r"https?://"),
    re.compile(r"\b(?:apisix|keycloak|hasura|svc-workflow|svc-files|seaweedfs|openbao|ollama|meilisearch|clamav|"
               r"postgres|flowable)(?::\d+|\.\w)"),
    re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"),
    re.compile(r"realms|Traceback|Error|Exception|bi-mat|\.local\b"),
]


def leaks(text: str) -> list[str]:
    return [m.group(0) for pattern in LEAKS for m in pattern.finditer(text)]


def run(coro):
    return asyncio.run(coro)


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def ok_after(calls: list[str], name: str, state: str = "ok", delay: float = 0.0):
    async def check() -> str:
        calls.append(name)
        if delay:
            await asyncio.sleep(delay)
        return state
    return check


# --- StatusBoard -------------------------------------------------------------------------------------------------


def test_cache_shared_by_concurrent_callers_and_expires():
    calls: list[str] = []
    clock = Clock()
    board = StatusBoard([Component("csdl", "loi", "CSDL", "PostgreSQL", ok_after(calls, "csdl", delay=0.05))],
                        ttl_s=10, timeout_s=1, clock=clock)

    async def burst() -> list[dict]:
        return await asyncio.gather(*(board.report() for _ in range(50)))

    reports = run(burst())
    assert calls == ["csdl"] and board.rounds == 1          # 50 người gọi cùng lúc: một lượt dò
    assert all(r["components"] == reports[0]["components"] for r in reports)
    clock.t += 9.9
    run(board.report())
    assert board.rounds == 1                                # còn trong hạn lưu đệm
    clock.t += 0.2
    out = run(board.report())
    assert board.rounds == 2 and calls == ["csdl", "csdl"]
    assert out["uptime_s"] == 10


def test_hung_probe_is_cut_by_timeout_and_not_restarted_while_pending():
    calls: list[str] = []
    clock = Clock()
    board = StatusBoard([
        Component("luu-tru", "du-lieu", "Lưu trữ tệp", "SeaweedFS", ok_after(calls, "luu-tru", delay=0.6)),
        Component("csdl", "loi", "CSDL", "PostgreSQL", ok_after(calls, "csdl")),
    ], ttl_s=1, timeout_s=0.1, clock=clock)

    async def two_rounds() -> tuple[dict, dict, float]:
        start = time.monotonic()
        first = await board.report()
        elapsed = time.monotonic() - start
        clock.t += 2                                        # hết hạn lưu đệm, lần dò kho cũ vẫn treo
        second = await board.report()
        return first, second, elapsed

    first, second, elapsed = run(two_rounds())
    states = {c["id"]: c["status"] for c in first["components"]}
    assert states == {"luu-tru": "down", "csdl": "ok"} and first["status"] == "down"
    assert elapsed < 0.5                                    # không chờ hết lần dò treo
    assert calls.count("luu-tru") == 1 and calls.count("csdl") == 2   # lượt hai chờ tiếp lần cũ, không mở lần mới
    assert {c["id"]: c["status"] for c in second["components"]}["luu-tru"] == "down"


def test_slow_probe_finishing_later_is_reused_by_next_round():
    calls: list[str] = []
    clock = Clock()
    board = StatusBoard([Component("luu-tru", "du-lieu", "Lưu trữ tệp", "SeaweedFS",
                                   ok_after(calls, "luu-tru", delay=0.15))], ttl_s=1, timeout_s=0.1, clock=clock)

    async def rounds() -> tuple[str, str]:
        first = (await board.report())["components"][0]["status"]
        clock.t += 2
        second = (await board.report())["components"][0]["status"]   # lần dò cũ xong trong hạn của lượt này
        return first, second

    assert run(rounds()) == ("down", "ok")
    assert calls == ["luu-tru"]


@pytest.mark.parametrize(("states", "overall"), [
    ({"a": "ok", "b": "ok", "c": "off"}, "ok"),             # tắt theo cấu hình không tính
    ({"a": "ok", "b": "down", "c": "ok"}, "degraded"),      # b không thiết yếu
    ({"a": "degraded", "b": "ok", "c": "ok"}, "degraded"),
    ({"a": "down", "b": "ok", "c": "ok"}, "down"),
    ({"a": "ok", "b": "ok", "c": "bogus"}, "down"),         # trạng thái lạ coi như gián đoạn
])
def test_overall_status(states, overall):
    async def fixed(state: str) -> str:
        return state

    board = StatusBoard([
        Component("a", "loi", "A", "X", lambda: fixed(states["a"])),
        Component("b", "du-lieu", "B", "Y", lambda: fixed(states["b"]), critical=False),
        Component("c", "loi", "C", "Z", lambda: fixed(states["c"])),
    ])
    assert run(board.report())["status"] == overall


def test_errors_stay_in_log_not_in_report(log_records):
    async def boom() -> str:
        raise RuntimeError("Không gọi được http://hasura:8080/healthz (10.0.3.7) với khóa bi-mat")

    async def no_backup() -> datetime | None:
        raise HasuraError("Hasura trả lỗi ở http://hasura:8080/v1/graphql")

    board = StatusBoard([Component("csdl", "loi", "CSDL", "PostgreSQL · Hasura", boom)], last_backup=no_backup)
    out = run(board.report())
    assert out["status"] == "down" and out["last_backup_at"] is None
    assert leaks(json.dumps(out, ensure_ascii=False)) == []
    events = [r for r in log_records if r.get("event") == "core.status.changed"]
    assert {e["component"] for e in events} == {"csdl", "sao-luu"}
    assert "hasura:8080" in next(e["reason"] for e in events if e["component"] == "csdl")


def test_log_only_when_state_changes(log_records):
    state = {"now": "down"}
    clock = Clock()

    async def check() -> str:
        return state["now"]

    board = StatusBoard([Component("tim-kiem", "du-lieu", "Tìm kiếm", "Meilisearch", check)], ttl_s=1, clock=clock)
    for now in ("down", "down", "ok", "ok", "down"):
        state["now"] = now
        clock.t += 2
        run(board.report())
    events = [r["state"] for r in log_records if r.get("event") == "core.status.changed"]
    assert events == ["down", "ok", "down"]


@pytest.mark.parametrize(("raw", "expected"), [
    ("qwen3:1.7b", "qwen3:1.7b"),
    ("registry.noi-bo.local:5000/team/qwen3:4b", "qwen3:4b"),     # bỏ tên máy của registry riêng
    ("hf.co/Qwen/Qwen3-1.7B-GGUF:Q4_K_M", "Qwen3-1.7B-GGUF:Q4_K_M"),
    ("mô hình lạ", None),
    ("", None),
    (None, None),
])
def test_public_model(raw, expected):
    assert public_model(raw) == expected


@pytest.mark.parametrize(("raw", "expected"), [
    ("1.0.0", "1.0.0"),
    ("1.0.0-3-g67f3e82-dirty", "1.0.0-3-g67f3e82-dirty"),
    ("dev", "dev"),
    ("http://may-chu:8080", "dev"),
    ("x" * 80, "dev"),
    ("", "dev"),
])
def test_public_version(raw, expected):
    assert public_version(raw) == expected


# --- GET /api/status qua create_app, lần dò thật nối với client giả ----------------------------------------------


@dataclass
class StubAi:
    chat_available: bool = False
    embed_available: bool = False
    chat_model: str | None = "qwen3:1.7b"


class Network:
    """Thay mạng nội bộ cho các lần dò HTTP: APISIX, Keycloak, svc-workflow."""

    def __init__(self) -> None:
        self.gateway = 200
        self.workflow: tuple[int, dict] = (200, {"status": "ok", "checks": {"hasura": True, "flowable": True}})
        self.fail: Exception | None = None
        self.seen: list[str] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.seen.append(f"{request.method} {request.url}")
        if self.fail is not None:
            raise self.fail
        if request.url.path == "/status/ready":
            return httpx2.Response(self.gateway, json={"status": "ok" if self.gateway == 200 else "error"})
        if request.url.path.endswith("/certs"):
            return httpx2.Response(200, json=JWKS)
        if request.url.path == "/readyz":
            return httpx2.Response(self.workflow[0], json=self.workflow[1])
        return httpx2.Response(404)


def status_settings(**extra: str) -> Settings:
    return Settings.from_env({
        "MOC_OIDC_ISSUER": "https://moc.example/realms/moc",
        "MOC_OIDC_JWKS_URL": "http://keycloak:8080/realms/moc/protocol/openid-connect/certs",
        "SEAWEEDFS_S3_ACCESS_KEY": "test", "SEAWEEDFS_S3_SECRET_KEY": "test",
        "HASURA_ADMIN_SECRET": "bi-mat", "MEILISEARCH_API_KEY": "test",
        "MOC_SEARCH_SYNC_INTERVAL_S": "0", "MOC_ASK_ENABLED": "false", "MOC_ASK_SYNC_INTERVAL_S": "0",
        "MOC_AUDIT_ANCHOR_INTERVAL_S": "0", "MOC_TEXT_INTERVAL_S": "0", "MOC_AI_URL": "",
        "MOC_VERSION": "1.0.0", "MOC_STATUS_TIMEOUT_S": "0.5",
        **extra,
    })


@pytest.fixture
def parts():
    return {"scanner": FakeScanner(), "store": FakeStore(), "hasura": FakeHasura(backup_at=BACKUP_AT),
            "meili": FakeMeili(), "vault": FakeVault(), "ai": StubAi(), "net": Network()}


def status_client(settings: Settings, parts: dict, verifier) -> TestClient:
    board = default_board(settings, scanner=parts["scanner"], store=parts["store"], hasura=parts["hasura"],
                          meili=parts["meili"], vault=parts["vault"], ai=parts["ai"],
                          transport=httpx2.MockTransport(parts["net"]))
    app = create_app(settings, scanner=parts["scanner"], store=parts["store"], verifier=verifier,
                     hasura=parts["hasura"], meili=parts["meili"], vault=parts["vault"], status_board=board)
    return TestClient(app)


EXPECTED = ["cong-api", "dang-nhap", "csdl", "ket-khoa", "quet-ma-doc", "quy-trinh", "luu-tru", "tim-kiem", "tro-ly-ai"]


def test_api_status_all_ok_without_token(parts, verifier):
    with status_client(status_settings(), parts, verifier) as c:
        r = c.get("/api/status")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    body = r.json()
    assert set(body) == {"status", "checked_at", "version", "uptime_s", "last_backup_at", "ai", "layers", "components"}
    assert body["status"] == "ok" and body["version"] == "1.0.0" and isinstance(body["uptime_s"], int)
    assert datetime.fromisoformat(body["last_backup_at"]) == BACKUP_AT
    assert [x["id"] for x in body["components"]] == EXPECTED
    assert {x["id"]: x["status"] for x in body["components"]} == {**dict.fromkeys(EXPECTED, "ok"), "tro-ly-ai": "off"}
    assert [x["id"] for x in body["layers"]] == ["nguoi-dung", "loi", "quy-trinh", "du-lieu", "tri-tue"]
    assert {x["layer"] for x in body["components"]} == {x["id"] for x in body["layers"]}
    labels = {x["id"]: x["label"] for x in body["components"]}
    assert labels["dang-nhap"] == "Đăng nhập một lần" and labels["quet-ma-doc"] == "Quét mã độc"
    assert body["ai"] == {"enabled": False, "model": None, "semantic": False}
    assert set(body["components"][0]) == {"id", "layer", "label", "software", "status"}
    assert leaks(r.text) == []
    # dò đúng nơi: máy chủ trạng thái của APISIX, JWKS của realm, /readyz của svc-workflow
    assert sorted(parts["net"].seen) == ["GET http://apisix:7085/status/ready",
                                 "GET http://keycloak:8080/realms/moc/protocol/openid-connect/certs",
                                 "GET http://svc-workflow:8000/readyz"]


def test_api_status_everything_down_leaks_nothing(parts, verifier):
    class LeakyStore(FakeStore):
        def ping(self) -> bool:
            raise RuntimeError("Không kết nối được http://seaweedfs:8333 (172.18.0.5)")

    class LeakyHasura(FakeHasura):
        async def ping(self) -> bool:
            raise HasuraError("Không gọi được Hasura: http://hasura:8080/healthz")

    parts.update(store=LeakyStore(), hasura=LeakyHasura(down=True), scanner=FakeScanner(down=True))
    parts["meili"].down = parts["vault"].down = True
    parts["net"].fail = httpx2.ConnectError("[Errno -2] Name or service not known: apisix:7085, keycloak:8080")
    with status_client(status_settings(), parts, verifier) as c:
        r = c.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "down" and body["last_backup_at"] is None
    states = {x["id"]: x["status"] for x in body["components"]}
    assert states == {**dict.fromkeys(EXPECTED, "down"), "tro-ly-ai": "off"}
    assert leaks(r.text) == []


def test_api_status_partial_states(parts, verifier):
    parts["net"].gateway = 503                                      # còn worker chưa nạp xong route
    parts["net"].workflow = (503, {"status": "unavailable", "checks": {"hasura": False, "flowable": True}})
    parts["meili"].down = True
    with status_client(status_settings(), parts, verifier) as c:
        body = c.get("/api/status").json()
    states = {x["id"]: x["status"] for x in body["components"]}
    assert states["cong-api"] == "degraded" and states["quy-trinh"] == "degraded" and states["tim-kiem"] == "down"
    assert body["status"] == "degraded"


def test_api_status_workflow_without_flowable_is_down(parts, verifier):
    parts["net"].workflow = (503, {"status": "unavailable", "checks": {"hasura": True, "flowable": False}})
    with status_client(status_settings(), parts, verifier) as c:
        body = c.get("/api/status").json()
    assert {x["id"]: x["status"] for x in body["components"]}["quy-trinh"] == "down" and body["status"] == "down"


def test_api_status_ai_on_shows_public_model_name(parts, verifier):
    settings = status_settings(MOC_AI_URL="http://ollama:11434", MOC_ASK_ENABLED="true", MOC_ASK_SYNC_INTERVAL_S="5",
                               MOC_AI_MODEL="registry.noi-bo.local:5000/team/qwen3:1.7b")
    parts["ai"] = StubAi(chat_available=True, embed_available=True,
                         chat_model="registry.noi-bo.local:5000/team/qwen3:1.7b")
    board = default_board(settings, scanner=parts["scanner"], store=parts["store"], hasura=parts["hasura"],
                          meili=parts["meili"], vault=parts["vault"], ai=parts["ai"],
                          transport=httpx2.MockTransport(parts["net"]))
    body = run(board.report())
    assert body["ai"] == {"enabled": True, "model": "qwen3:1.7b", "semantic": True}
    assert {x["id"]: x["status"] for x in body["components"]}["tro-ly-ai"] == "ok"
    parts["ai"].chat_available = False                              # chỉ còn tìm theo nghĩa
    board.ttl_s = 0
    body = run(board.report())
    assert body["ai"] == {"enabled": False, "model": None, "semantic": True}
    assert {x["id"]: x["status"] for x in body["components"]}["tro-ly-ai"] == "degraded"
    run(board.aclose())


def test_api_status_no_vault_or_workflow_url_is_off(parts, verifier):
    parts["vault"] = None
    board = default_board(status_settings(MOC_WORKFLOW_URL=""), scanner=parts["scanner"], store=parts["store"],
                          hasura=parts["hasura"], meili=parts["meili"], vault=None, ai=parts["ai"],
                          transport=httpx2.MockTransport(parts["net"]))
    states = {x["id"]: x["status"] for x in run(board.report())["components"]}
    assert states["ket-khoa"] == "off" and states["quy-trinh"] == "off"
    run(board.aclose())


def test_openapi_documents_public_status(parts, verifier):
    with status_client(status_settings(), parts, verifier) as c:
        op = c.get("/openapi.json").json()["paths"]["/api/status"]["get"]
    assert "security" not in op and "429" in op["responses"]


@pytest.mark.parametrize(("env", "message"), [
    ({"MOC_STATUS_CACHE_S": "0"}, "MOC_STATUS_CACHE_S"),
    ({"MOC_STATUS_TIMEOUT_S": "30"}, "MOC_STATUS_TIMEOUT_S"),
    ({"MOC_WORKFLOW_URL": "svc-workflow:8000"}, "MOC_WORKFLOW_URL"),
])
def test_status_config_checked(env, message):
    with pytest.raises(ConfigError, match=message):
        status_settings(**env)


# --- Hasura: lượt sao lưu gần nhất -------------------------------------------------------------------------------


def hasura_replying(data: dict, seen: list[dict]) -> HasuraClient:
    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append({"headers": dict(request.headers), "body": json.loads(request.content)})
        return httpx2.Response(200, json={"data": data})
    return HasuraClient("http://hasura:8080", "bi-mat", transport=httpx2.MockTransport(handler))


def test_last_backup_takes_latest_of_backup_rows_and_restored_runs():
    seen: list[dict] = []
    client = hasura_replying({
        "backed_up": [{"occurred_at": "2026-10-22T08:00:00.123+00:00"}],
        # CSDL vừa khôi phục từ lượt 15:00 giờ Việt Nam: dòng system.backed_up của lượt đó không có trong bản dump
        "restored": [{"backed_up_at": "2026-10-23T15:00:00+07:00"}],
    }, seen)
    assert run(client.last_backup()) == datetime(2026, 10, 23, 8, 0, tzinfo=UTC)
    assert seen[0]["headers"]["x-hasura-admin-secret"] == "bi-mat"
    query = seen[0]["body"]["query"]
    assert '"system.backed_up"' in query and '"system.restored"' in query and "_is_null: true" in query


@pytest.mark.parametrize("data", [
    {"backed_up": [], "restored": []},
    {"backed_up": [{"occurred_at": None}], "restored": [{"backed_up_at": "không phải giờ"}]},
    {"backed_up": [{"occurred_at": "2026-10-22T08:00:00"}], "restored": [{"backed_up_at": None}]},   # thiếu múi giờ
])
def test_last_backup_none_when_unknown(data):
    assert run(hasura_replying(data, []).last_backup()) is None
