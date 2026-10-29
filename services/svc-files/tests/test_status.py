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
import hashlib
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
from svc_files.status import Component, StatusBoard, default_board, public_model, public_version, render_metrics

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
    device: str | None = None


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
        "MOC_IMPORT_INTERVAL_S": "0",     # vòng nền nạp lô tắt (không tạo thư mục spool)
        "MOC_VERSION": "1.0.0", "MOC_STATUS_TIMEOUT_S": "0.5",
        "MOC_OPEN_DATA_DIR": "",          # không đọc /srv/du-lieu-mo của máy chạy test
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
    assert set(body) == {"status", "checked_at", "version", "uptime_s", "last_backup_at", "ai", "layers", "components",
                         "open_data"}
    assert body["open_data"] == []
    assert body["status"] == "ok" and body["version"] == "1.0.0" and isinstance(body["uptime_s"], int)
    assert datetime.fromisoformat(body["last_backup_at"]) == BACKUP_AT
    assert [x["id"] for x in body["components"]] == EXPECTED
    assert {x["id"]: x["status"] for x in body["components"]} == {**dict.fromkeys(EXPECTED, "ok"), "tro-ly-ai": "off"}
    assert [x["id"] for x in body["layers"]] == ["nguoi-dung", "loi", "quy-trinh", "du-lieu", "tri-tue"]
    assert {x["layer"] for x in body["components"]} == {x["id"] for x in body["layers"]}
    labels = {x["id"]: x["label"] for x in body["components"]}
    assert labels["dang-nhap"] == "Đăng nhập một lần" and labels["quet-ma-doc"] == "Quét mã độc"
    assert body["ai"] == {"enabled": False, "model": None, "semantic": False, "device": None}
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
    assert body["ai"] == {"enabled": True, "model": "qwen3:1.7b", "semantic": True, "device": None}
    assert {x["id"]: x["status"] for x in body["components"]}["tro-ly-ai"] == "ok"
    parts["ai"].chat_available = False                              # chỉ còn tìm theo nghĩa
    board.ttl_s = 0
    body = run(board.report())
    assert body["ai"] == {"enabled": False, "model": None, "semantic": True, "device": None}
    assert {x["id"]: x["status"] for x in body["components"]}["tro-ly-ai"] == "degraded"
    parts["ai"].chat_available, parts["ai"].device = True, "gpu"     # MOC_AI_DEVICE=gpu, Ollama báo mô hình trên GPU
    body = run(board.report())
    assert body["ai"] == {"enabled": True, "model": "qwen3:1.7b", "semantic": True, "device": "gpu"}
    run(board.aclose())


def test_api_status_external_answer_api(parts, verifier):
    """#430: viết câu trả lời qua API ngoài — trợ lý bật được cả khi không có Ollama; phần mềm ghi rõ "API ngoài",
    không lộ URL của API."""
    def board_for(**extra: str):
        settings = status_settings(MOC_ASK_ENABLED="true", MOC_ASK_SYNC_INTERVAL_S="5", MOC_ASK_API="openai",
                                   MOC_ASK_API_URL="https://mo-hinh.example/v1", MOC_ASK_MODEL="mo-hinh-ngoai",
                                   **extra)
        return default_board(settings, scanner=parts["scanner"], store=parts["store"], hasura=parts["hasura"],
                             meili=parts["meili"], vault=parts["vault"], ai=parts["ai"],
                             transport=httpx2.MockTransport(parts["net"]))

    parts["ai"] = StubAi(chat_available=True, embed_available=False, chat_model="mo-hinh-ngoai")
    board = board_for()
    body = run(board.report())
    ai = next(x for x in body["components"] if x["id"] == "tro-ly-ai")
    assert ai["status"] == "ok" and ai["software"] == "API ngoài"
    assert body["ai"] == {"enabled": True, "model": "mo-hinh-ngoai", "semantic": False, "device": None}
    assert "mo-hinh.example" not in json.dumps(body)
    run(board.aclose())
    board = board_for(MOC_AI_URL="http://ollama:11434")
    ai = next(x for x in run(board.report())["components"] if x["id"] == "tro-ly-ai")
    assert ai["software"] == "Ollama, API ngoài"
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
        spec = c.get("/openapi.json").json()
    op = spec["paths"]["/api/status"]["get"]
    assert "security" not in op and "429" in op["responses"]
    assert "open_data" in spec["components"]["schemas"]["StatusOut"]["properties"]


# --- nguồn dữ liệu công khai (#424) -------------------------------------------------------------------------------


def open_data_source(root, *, sha: str | None = None) -> dict:
    pdf = b"%PDF-1.7 thong tu\n"
    folder = root / "cong-bao-gddt"
    folder.mkdir()
    (folder / "tt.pdf").write_bytes(pdf)
    manifest = {"source": "cong-bao-gddt", "name": "Văn bản Bộ GD&ĐT trên Công báo", "publisher": "Văn phòng Chính phủ",
                "home_url": "https://congbao.chinhphu.vn/", "reuse_basis": "Khoản 2 Điều 15 Luật SHTT", "licence": None,
                "fetched_at": "2026-10-30T02:10:00+07:00", "max_age_days": 400,
                "files": [{"file": "tt.pdf", "url": "https://congbao.chinhphu.vn/tt.pdf", "bytes": len(pdf),
                           "sha256": sha or hashlib.sha256(pdf).hexdigest(), "fetched_at": None,
                           "meta": {"symbol": "26/2026/TT-BGDĐT"}}]}
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    return manifest


def test_api_status_lists_open_data_sources(tmp_path, parts, verifier):
    manifest = open_data_source(tmp_path)
    with status_client(status_settings(MOC_OPEN_DATA_DIR=str(tmp_path)), parts, verifier) as c:
        body = c.get("/api/status").json()
    [src] = body["open_data"]
    assert src["source"] == "cong-bao-gddt" and src["state"] == "ok" and src["max_age_days"] == 400
    assert isinstance(src["age_days"], int) and src["age_days"] >= 0
    assert datetime.fromisoformat(src["fetched_at"]) == datetime.fromisoformat(manifest["fetched_at"])
    assert src["files"] == [{**manifest["files"][0]}]
    assert body["status"] == "ok"


def test_api_status_broken_source_does_not_change_overall(tmp_path, parts, verifier):
    open_data_source(tmp_path, sha="0" * 64)
    with status_client(status_settings(MOC_OPEN_DATA_DIR=str(tmp_path)), parts, verifier) as c:
        body = c.get("/api/status").json()
    assert [s["state"] for s in body["open_data"]] == ["broken"] and body["status"] == "ok"


def test_open_data_failure_or_hang_gives_empty_list(log_records):
    def boom() -> list:
        raise OSError("ổ đĩa lỗi")

    def hang() -> list:
        time.sleep(0.3)
        return [{"source": "x"}]

    for read in (boom, hang):
        board = StatusBoard([Component("a", "loi", "A", "X", ok_after([], "a"))], open_data=read, timeout_s=0.05)
        report = run(board.report())
        assert report["open_data"] == [] and report["status"] == "ok"
    assert any(r.get("component") == "du-lieu-mo" and r["state"] == "down" for r in log_records)


def test_open_data_dir_default():
    assert Settings.open_data_dir == "/srv/du-lieu-mo"


# --- GET /metrics cho Prometheus (#274) ----------------------------------------------------------------------------

METRIC = re.compile(r'^moc_component_up\{component="([a-z-]+)",critical="(true|false)"\} ([01])$')


def component_up(text: str) -> dict[str, tuple[str, str]]:
    """Mỗi dòng số liệu của /metrics → {thành phần: (critical, giá trị)}; dòng lạ thì test đỏ."""
    rows = [line for line in text.splitlines() if not line.startswith("#")]
    assert all(METRIC.match(line) for line in rows), rows
    found = {m[1]: (m[2], m[3]) for m in map(METRIC.match, rows)}
    assert len(found) == len(rows)                                  # mỗi thành phần đúng một dòng
    return found


def test_metrics_lists_every_component_not_off(parts, verifier):
    with status_client(status_settings(), parts, verifier) as c:
        r = c.get("/metrics")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert r.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
    assert "# TYPE moc_component_up gauge" in r.text.splitlines()
    up = component_up(r.text)
    assert list(up) == [x for x in EXPECTED if x != "tro-ly-ai"]   # trợ lý AI tắt theo cấu hình: không có dòng
    assert {k: v for k, (_, v) in up.items()} == dict.fromkeys(up, "1")
    assert {k for k, (crit, _) in up.items() if crit == "false"} == {"ket-khoa", "tim-kiem"}
    assert leaks(r.text) == []


def test_metrics_zero_only_when_down(parts, verifier):
    parts["net"].gateway = 503                                      # suy giảm vẫn là trả lời được
    parts["meili"].down = True
    parts["scanner"].down = True
    with status_client(status_settings(), parts, verifier) as c:
        up = component_up(c.get("/metrics").text)
    assert {k for k, (_, v) in up.items() if v == "0"} == {"tim-kiem", "quet-ma-doc"}
    assert up["cong-api"] == ("true", "1") and up["tim-kiem"] == ("false", "0")


def test_metrics_share_the_status_cache_and_stay_out_of_openapi(parts, verifier):
    with status_client(status_settings(), parts, verifier) as c:
        c.get("/api/status")
        c.get("/metrics")
        c.get("/metrics")
        assert c.app.state.status_board.rounds == 1
        assert "/metrics" not in c.get("/openapi.json").json()["paths"]


def test_metrics_escape_label_values():
    report = {"components": [{"id": 'a"b\\c\nd', "status": "degraded"}, {"id": "x", "status": "off"}]}
    # thoát \ " và xuống dòng theo định dạng chữ của Prometheus; không khai critical thì coi là bắt buộc
    expected = 'moc_component_up{component="a\\"b\\\\c\\nd",critical="true"} 1'
    assert render_metrics(report, {}).splitlines()[2:] == [expected]


@pytest.mark.parametrize(("env", "message"), [
    ({"MOC_STATUS_CACHE_S": "0"}, "MOC_STATUS_CACHE_S"),
    ({"MOC_STATUS_TIMEOUT_S": "30"}, "MOC_STATUS_TIMEOUT_S"),
    ({"MOC_WORKFLOW_URL": "svc-workflow:8000"}, "MOC_WORKFLOW_URL"),
    ({"MOC_OPEN_DATA_DIR": "seed/du-lieu-mo"}, "MOC_OPEN_DATA_DIR"),
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
