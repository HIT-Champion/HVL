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

"""Log tập trung (F3.14, profile logs): Vector, Parseable chỉ chạy khi bật profile, chỉ nghe 127.0.0.1, không gắn
docker.sock, mật khẩu rỗng thì Parseable không mở cổng; tệp phủ chỉ đổi driver log của 9 dịch vụ (5 dịch vụ tự che PII;
Hasura, Keycloak, PostgreSQL, Meilisearch có luật riêng trong Vector); Makefile
chỉ nạp tệp phủ khi MOC_EXTRA_PROFILES có logs; scripts/log_tap_trung.py không ghép chuỗi lạ vào SQL, không in mật
khẩu. Kiểm chữ (không có PyYAML, không cần Docker) và một Parseable giả trên 127.0.0.1.
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import base64
import contextlib
import importlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import log_tap_trung as lt  # noqa: E402

from test_duong_ham import service_block  # noqa: E402

LOGS = ROOT / "platform" / "logs"
OVERRIDE = LOGS / "docker-compose.logs.yml"
LOGGED = ["apisix", "app-office", "app-ca-nhan", "svc-files", "svc-workflow", "hasura", "keycloak", "postgres",
          "meilisearch"]
# Không tự che thông tin cá nhân trong nhật ký: Vector có luật riêng, vector.test.yaml có ca
UNREDACTED = ("hasura", "keycloak", "postgres", "meilisearch")
SECRET_PATHS = ("docker.sock", "/var/lib/docker", "/var/run/docker")


def without_comments(text: str) -> str:
    """Bỏ chú thích YAML (cả dòng và cuối dòng sau " #"): chỉ kiểm phần cấu hình thật."""
    return "\n".join(re.sub(r"(^|\s)#.*$", "", line) for line in text.splitlines())


def list_items(block: str, key: str) -> list[str]:
    """Phần tử của danh sách ``key:`` (dạng "- …" ở các dòng ngay sau) trong khối một dịch vụ."""
    lines = without_comments(block).splitlines()
    start = next(i for i, x in enumerate(lines) if x.strip() == f"{key}:")
    items = []
    for line in lines[start + 1:]:
        if not line.lstrip().startswith("- "):
            break
        items.append(line.strip()[2:].strip())
    return items


class ComposeTest(unittest.TestCase):
    def test_vector_and_parseable_only_in_logs_profile_on_their_own_network(self) -> None:
        for name in ("vector", "parseable"):
            block = service_block(name)
            self.assertIn("profiles: [logs]", block, name)
            self.assertIn("networks: [logs]", block, name)          # không vào mạng moc: không tới dịch vụ khác
            self.assertNotIn("<<: *common", block, name)
            self.assertRegex(block, r"image: [^\s@]+:[^\s@]+@sha256:[0-9a-f]{64}\n", name)
            ports = list_items(block, "ports")
            self.assertTrue(ports and all(p.startswith("127.0.0.1:") for p in ports), (name, ports))
            self.assertIn("driver: json-file", block, name)         # log của chính nó không gửi vào mình

    def test_parseable_refuses_to_start_without_a_password(self) -> None:
        block = service_block("parseable")
        self.assertIn("P_USERNAME: moc", block)
        self.assertIn("P_PASSWORD: ${MOC_LOGS_PASSWORD:-}", block)
        # mật khẩu rỗng → P_ADDR rỗng → Parseable thoát, không bao giờ mở cổng nhận đăng nhập rỗng
        self.assertIn("P_ADDR: ${MOC_LOGS_PASSWORD:+0.0.0.0:8000}", block)
        self.assertIn('P_CHECK_UPDATE: "false"', block)
        self.assertIn('P_SEND_ANONYMOUS_USAGE_DATA: "false"', block)
        self.assertNotRegex(block.lower(), r"\badmin\b")

    def test_vector_runs_unprivileged_and_reads_its_password_from_a_secret(self) -> None:
        block = service_block("vector")
        for line in ('user: "65534:65534"', "cap_drop: [ALL]", "no-new-privileges:true", "secrets: [moc_logs_password]",
                     "./platform/logs/vector.yaml:/etc/vector/vector.yaml:ro"):
            self.assertIn(line, block)
        # rootfs chỉ đọc thì compose không chép được secret nguồn environment vào container: Vector không khởi động
        self.assertNotIn("read_only: true", without_comments(block))
        text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertRegex(text, r"\nsecrets:\n(?:  #.*\n)*  moc_logs_password:\n    environment: MOC_LOGS_PASSWORD\n")
        self.assertRegex(text, r"\n  logs:\n    driver: bridge\n")

    def test_no_docker_socket_anywhere(self) -> None:
        for path in (ROOT / "docker-compose.yml", OVERRIDE):
            text = without_comments(path.read_text(encoding="utf-8"))
            for bad in SECRET_PATHS:
                self.assertNotIn(bad, text, f"{path.name}: {bad}")

    def test_override_only_switches_the_logged_services_to_fluentd(self) -> None:
        text = OVERRIDE.read_text(encoding="utf-8")
        services = re.findall(r"^  ([a-z-]+): \{logging: \*fluentd\}$", text, re.M)
        self.assertEqual(services, LOGGED)
        tail = text.split("\nservices:\n", 1)[1].splitlines()
        self.assertEqual(len([x for x in tail if x.strip()]), len(LOGGED))     # không đổi gì khác của dịch vụ
        anchor = text.split("x-fluentd: &fluentd\n", 1)[1].split("\n\n", 1)[0]
        self.assertIn("driver: fluentd", anchor)
        self.assertIn("fluentd-address: 127.0.0.1:${MOC_LOGS_FLUENT_PORT:-24224}", anchor)
        self.assertIn('fluentd-async: "true"', anchor)
        self.assertIn('fluentd-request-ack: "true"', anchor)        # không ack thì mất dòng ở kết nối chết (#226)
        self.assertIn("labels: com.docker.compose.service", anchor)
        self.assertIn("cache-max-size: 10m", anchor)                 # docker logs vẫn đọc được như trước
        # driver gửi kèm biến môi trường (có bí mật) của container nếu khai các tùy chọn này
        for option in ("env:", "env-regex", "labels-regex"):
            self.assertNotIn(option, anchor)

    def test_services_without_rules_are_not_collected(self) -> None:
        text = OVERRIDE.read_text(encoding="utf-8")
        for name in ("openbao", "flowable", "seaweedfs"):
            self.assertNotRegex(text, rf"^  {name}:", name)

    @unittest.skipUnless(shutil.which("git") and (ROOT / ".git").exists(), "cần git và bản checkout")
    def test_config_dir_is_not_gitignored(self) -> None:
        # .gitignore bỏ mọi thư mục logs/: thiếu dòng !/platform/logs/ thì cấu hình không vào commit, bản phát hành
        files = [str(p.relative_to(ROOT)) for p in sorted(LOGS.rglob("*")) if p.is_file()]
        # --no-index: xét theo .gitignore cả khi tệp đã nằm trong chỉ mục (git không báo bỏ qua tệp đã theo dõi)
        cmd = ["git", "-C", str(ROOT), "check-ignore", "--no-index", *files]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout)


class VectorConfigTest(unittest.TestCase):
    def test_password_comes_from_the_secret_not_the_environment(self) -> None:
        text = (LOGS / "vector.yaml").read_text(encoding="utf-8")
        # Vector ≥ 0.57 không thay biến môi trường: ${MOC_…} sẽ đi nguyên chuỗi (${1} là nhóm của replace trong VRL)
        self.assertNotRegex(without_comments(text), r"\$\{?[A-Z_]")
        self.assertIn('password: "SECRET[tep.moc_logs_password]"', text)
        self.assertIn(f"X-P-Stream: {lt.STREAM} ", text)
        self.assertIn(f"user: {lt.USER}\n", text)
        self.assertIn("uri: http://parseable:8000/api/v1/ingest", text)

    @staticmethod
    def transform(name: str) -> str:
        """Khối một transform trong vector.yaml (không chú thích): từ dòng `  <name>:` tới khóa cùng cấp kế tiếp."""
        lines = without_comments((LOGS / "vector.yaml").read_text(encoding="utf-8")).splitlines()
        start = lines.index(f"  {name}:")
        end = next(i for i in range(start + 1, len(lines)) if re.match(r"( {2})?\S", lines[i]))
        return "\n".join(lines[start:end])

    def test_redaction_drops_a_line_it_cannot_process(self) -> None:
        # vector test không gây được lỗi lúc chạy với cấu hình thật: kiểm tĩnh. Lỗi ở bước che mà không bỏ dòng thì
        # Vector gửi nguyên văn chưa che; reroute_dropped thì dòng lỗi đi sang cổng ra khác
        block = self.transform("moc")
        self.assertIn("type: remap", block)
        self.assertRegex(block, r"\n    drop_on_error: true\s*\n")
        self.assertNotIn("reroute_dropped", block)
        # dòng tiếp của PostgreSQL bị abort: drop_on_abort mặc định true, đặt false thì dòng chưa che đi tiếp
        self.assertIn("abort", block)
        self.assertNotIn("drop_on_abort", block)

    def test_services_that_do_not_redact_have_their_own_rules_and_cases(self) -> None:
        block = self.transform("moc")
        cases = (LOGS / "vector.test.yaml").read_text(encoding="utf-8")
        for name in UNREDACTED:
            self.assertIn(f'service == "{name}"', block, name)
            self.assertIn(f"'\"com.docker.compose.service\"': {name}\n", cases, name)

    def test_meilisearch_writes_json_lines(self) -> None:
        # luật của Vector che theo khóa (query_parameters, error); bản chữ tách lời lỗi nhiều dòng thành nhiều dòng log
        block = service_block("meilisearch")
        self.assertIn("      MEILI_EXPERIMENTAL_LOGS_MODE: json\n", block)

    def test_partial_lines_are_joined_per_container_and_partial_id(self) -> None:
        block = self.transform("ghep")
        self.assertIn("type: reduce", block)
        keys = re.search(r"\n    group_by: \[([^\]]*)\]", block)
        self.assertIsNotNone(keys, block)
        self.assertEqual({k.strip() for k in keys.group(1).split(",")}, {"container_id", "partial_id"})

    def test_fake_password_for_validate_is_obviously_fake(self) -> None:
        fake = (LOGS / "kiem-tra" / "mat-khau-gia.txt").read_text(encoding="utf-8").strip()
        self.assertTrue(fake.startswith("khong-phai-mat-khau"), fake)


class EnvExampleTest(unittest.TestCase):
    def test_make_env_generates_the_password(self) -> None:
        text = (ROOT / (".e" + "nv.example")).read_text(encoding="utf-8")
        self.assertRegex(text, r"\nMOC_LOGS_PASSWORD=change_me\n")       # gen-env.sh thay bằng chuỗi ngẫu nhiên
        self.assertRegex(text, r"\nMOC_LOGS_RETENTION_DAYS=7\n")
        self.assertRegex(text, r"\nMOC_LOGS_PORT=8400\n")


@unittest.skipUnless(shutil.which("make"), "cần GNU Make")
class MakefileTest(unittest.TestCase):
    """Tệp phủ chỉ nạp khi MOC_EXTRA_PROFILES có logs (make chạy trong thư mục tạm, không gọi Docker)."""

    def compose_file(self, env: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(ROOT / "Makefile", tmp)
            (pathlib.Path(tmp) / ("." + "env")).write_text(env, encoding="utf-8")
            (pathlib.Path(tmp) / "in.mk").write_text("in-bien:\n\t@echo \"[$$COMPOSE_FILE]\"\n", encoding="utf-8")
            proc = subprocess.run(["make", "-s", "-f", "Makefile", "-f", "in.mk", "in-bien"], cwd=tmp,
                                  capture_output=True, text=True,
                                  env={k: v for k, v in {**os.environ, "MAKEFLAGS": ""}.items() if k != "COMPOSE_FILE"})
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return proc.stdout.strip()

    def test_override_only_when_logs_profile_is_on(self) -> None:
        self.assertEqual(self.compose_file("MOC_EXTRA_PROFILES=\n"), "[]")
        self.assertEqual(self.compose_file("MOC_EXTRA_PROFILES=tunnel\n"), "[]")
        self.assertEqual(self.compose_file("MOC_EXTRA_PROFILES=tunnel,logs\n"),
                         "[docker-compose.yml:platform/logs/docker-compose.logs.yml]")

    def run_up(self, env: str) -> tuple[str, str, str]:
        """make up với docker giả và log_tap_trung.py giả: trả (.env sau khi chạy, lệnh docker, lệnh init)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = pathlib.Path(tmp)
            (d / "scripts").mkdir()
            (d / "bin").mkdir()
            shutil.copy(ROOT / "Makefile", d)
            shutil.copy(ROOT / "scripts" / "gen-env.sh", d / "scripts")
            (d / "platform" / "apisix").mkdir(parents=True)  # make up kiểm MOC_WAF bằng script này (F3.15)
            shutil.copy(ROOT / "platform" / "apisix" / "kiem-moi-truong.sh", d / "platform" / "apisix")
            (d / "scripts" / "log_tap_trung.py").write_text(
                "import sys\nopen('init.log', 'a').write(' '.join(sys.argv[1:]) + '\\n')\n", encoding="utf-8")
            docker = d / "bin" / "docker"
            docker.write_text('#!/bin/sh\necho "$*" >> docker.log\n', encoding="utf-8")
            docker.chmod(0o755)
            dot_env = d / ("." + "env")
            dot_env.write_text(env, encoding="utf-8")
            run_env = {k: v for k, v in os.environ.items()
                       if k not in ("COMPOSE_FILE", "MAKEFLAGS", "MAKELEVEL", "MOC_LOGS_PASSWORD")}
            run_env["PATH"] = f"{d / 'bin'}:{run_env['PATH']}"
            proc = subprocess.run(["make", "-s", "up"], cwd=d, env=run_env, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            read = lambda name: (d / name).read_text(encoding="utf-8") if (d / name).exists() else ""  # noqa: E731
            return dot_env.read_text(encoding="utf-8"), read("docker.log"), read("init.log")

    def test_make_up_with_logs_profile_fills_an_old_env_and_sets_retention(self) -> None:
        # .env sinh trước F3.14 (thiếu MOC_LOGS_PASSWORD) rồi thêm logs vào MOC_EXTRA_PROFILES: make up không lỗi
        env, docker, init = self.run_up("MOC_PUBLIC_URL=https://x\nMOC_EXTRA_PROFILES=logs\n")
        self.assertRegex(env, r"\nMOC_LOGS_PASSWORD=[0-9a-f]{48}\n")
        self.assertIn("--profile logs up -d --build --wait", docker)
        self.assertEqual(init, "init\n")                     # luồng moc có thời gian giữ log ngay từ lần đầu
        again, _, _ = self.run_up(env)
        self.assertEqual(again.count("MOC_LOGS_PASSWORD="), 1)

    def test_make_up_without_logs_profile_is_unchanged(self) -> None:
        env, docker, init = self.run_up("MOC_PUBLIC_URL=https://x\nMOC_EXTRA_PROFILES=\n")
        self.assertNotIn("MOC_LOGS_PASSWORD", env)
        # bỏ lệnh chỉ đọc `config` mà env-ready gọi để kiểm MOC_WAF (F3.15)
        ups = [line for line in docker.splitlines() if " config " not in line]
        self.assertEqual(ups, ["compose --profile core --profile app up -d --build --wait --wait-timeout 600"])
        self.assertEqual(init, "")

    def test_logged_services_match_the_override(self) -> None:
        text = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn(f"LOGGED_SERVICES := {' '.join(LOGGED)}\n", text)
        self.assertIn("--profile ai-pull --profile logs down\n", text)
        self.assertIn("--profile ai-pull --profile logs down -v\n", text)


class PureFunctionTest(unittest.TestCase):
    def test_request_id_whitelist(self) -> None:
        for good in ("demo-log-ab12", "goi-y:g1", "0f3c" * 8, "3f2a8c1e-0b6d-4c1e-9a7f-2d5e6b8c9a01", "a" * 128):
            self.assertTrue(lt.valid_request_id(good), good)
        for bad in ("", "a' or '1'='1", "a b", "a" * 129, "x;drop", "x\n", "ố"):
            self.assertFalse(lt.valid_request_id(bad), bad)

    def test_query_body(self) -> None:
        body = lt.query_body("demo-log-ab12", 30)
        self.assertEqual(body, {"query": "select * from moc where request_id = 'demo-log-ab12' order by p_timestamp",
                                "startTime": "30m", "endTime": "now"})
        with self.assertRaises(ValueError):
            lt.query_body("x' or '1'='1", 30)
        with self.assertRaises(ValueError):
            lt.query_body("ok", 0)

    def test_service_body(self) -> None:
        self.assertEqual(lt.service_body("postgres", 10),
                         {"query": "select * from moc where service = 'postgres' order by p_timestamp",
                          "startTime": "10m", "endTime": "now"})
        for bad in ("", "Postgres", "pg' or '1'='1", "a b", "-x", "a" * 65):
            with self.assertRaises(ValueError, msg=bad):
                lt.service_body(bad, 10)
        with self.assertRaises(ValueError):
            lt.service_body("keycloak", 0)

    def test_retention(self) -> None:
        self.assertEqual(lt.retention_body(7), [{"description": "Giữ log tập trung 7 ngày (MOC_LOGS_RETENTION_DAYS)",
                                                 "action": "delete", "duration": "7d"}])
        self.assertEqual(lt.retention_days("7"), 7)
        for bad in ("0", "-1", "7d", "", "36501"):
            with self.assertRaises(ValueError):
                lt.retention_days(bad)

    def test_auth_header(self) -> None:
        self.assertEqual(base64.b64decode(lt.auth_header("moc", "p").split()[1]), b"moc:p")

    def test_table_keeps_lines_short(self) -> None:
        (line,) = lt.table([{"p_timestamp": "2026-10-23T03:00:00.123456", "service": "svc-files", "event": "x",
                             "message": "a\n  b " + "c" * 500}])
        self.assertTrue(line.startswith("2026-10-23T03:00:00.123  svc-files"))
        self.assertIn(" a b ccc", line)
        self.assertLessEqual(len(line), 23 + 2 + 12 + 2 + 28 + 2 + 120)


class FakeParseable(BaseHTTPRequestHandler):
    """Parseable giả: basic auth moc/dung, luồng, giữ log, truy vấn — đủ cho init và tra."""

    state: dict = {}

    def log_message(self, *args) -> None:  # noqa: D401 — im lặng trong test
        pass

    def _send(self, status: int, body) -> None:
        raw = (body if isinstance(body, str) else json.dumps(body)).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _handle(self) -> None:
        st = self.state
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length)) if length else None
        st["calls"].append((self.command, self.path, body))
        if self.path == "/api/v1/readiness":
            return self._send(200, "")
        auth = self.headers.get("Authorization")
        if auth is None:
            return self._send(401, "")
        if auth != lt.auth_header("moc", "dung"):
            return self._send(403, "")
        if (self.command, self.path) == ("GET", "/api/v1/logstream"):
            return self._send(200, [{"name": n} for n in st["streams"]])
        if (self.command, self.path) == ("PUT", "/api/v1/logstream/moc"):
            st["streams"].append("moc")
            return self._send(200, "Log stream created")
        if self.path == "/api/v1/logstream/moc/retention":
            if self.command == "PUT":
                st["retention"] = body
                return self._send(200, "set retention configuration for log stream moc")
            return self._send(200, st["retention"])
        if (self.command, self.path) == ("POST", "/api/v1/query"):
            if not st["rows"]:
                return self._send(400, 'Schema error: No field named request_id.')
            return self._send(200, st["rows"])
        return self._send(404, "")

    do_GET = do_PUT = do_POST = _handle


@contextlib.contextmanager
def fake_parseable(**state):
    FakeParseable.state = {"calls": [], "streams": [], "retention": [], "rows": [], **state}
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeParseable)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", FakeParseable.state
    finally:
        server.shutdown()
        server.server_close()


class ClientTest(unittest.TestCase):
    def test_init_creates_the_stream_once_and_sets_retention(self) -> None:
        with fake_parseable() as (url, st):
            api = lt.Parseable(url, "dung")
            api.wait_ready(timeout_s=5)
            self.assertTrue(api.ensure_stream())
            self.assertFalse(api.ensure_stream())           # chạy lại make logs-up: không tạo lần nữa
            got = api.set_retention(7)
        self.assertEqual(got, lt.retention_body(7))
        self.assertEqual([c for c in st["calls"] if c[0] == "PUT"],
                         [("PUT", "/api/v1/logstream/moc", None),
                          ("PUT", "/api/v1/logstream/moc/retention", lt.retention_body(7))])

    def test_find_sends_the_whitelisted_query(self) -> None:
        rows = [{"p_timestamp": "2026-10-23T03:00:00.1", "service": "apisix", "request_id": "r-1", "message": "m"}]
        with fake_parseable(rows=rows) as (url, st):
            self.assertEqual(lt.Parseable(url, "dung").find("r-1", 15), rows)
            with self.assertRaises(ValueError):
                lt.Parseable(url, "dung").find("r-1' or 1=1 --", 15)
        self.assertEqual(st["calls"], [("POST", "/api/v1/query", lt.query_body("r-1", 15))])

    def test_recent_sends_the_service_query(self) -> None:
        rows = [{"p_timestamp": "2026-10-25T17:18:55.1", "service": "postgres", "message": "m"}]
        with fake_parseable(rows=rows) as (url, st):
            self.assertEqual(lt.Parseable(url, "dung").recent("postgres", 10), rows)
        self.assertEqual(st["calls"], [("POST", "/api/v1/query", lt.service_body("postgres", 10))])

    def test_no_rows_with_request_id_yet_is_empty_not_an_error(self) -> None:
        with fake_parseable() as (url, _):
            self.assertEqual(lt.Parseable(url, "dung").find("r-1"), [])

    def test_wrong_password_fails_without_echoing_it(self) -> None:
        with fake_parseable() as (url, _):
            with self.assertRaises(lt.ParseableError) as err:
                lt.Parseable(url, "mat-khau-sai-123").streams()
        self.assertEqual(err.exception.status, 403)
        self.assertNotIn("mat-khau-sai-123", str(err.exception))

    def test_tra_rejects_a_bad_id_before_reading_env(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as exit_:
            lt.main(["tra", "x' or '1'='1"])
        self.assertEqual(exit_.exception.code, 2)
        self.assertIn("make logs-tra ID=", err.getvalue())


class DemoHelpersTest(unittest.TestCase):
    """Hàm thuần của make demo-log-tap-trung; moc_env thay bằng bản giả (như test_che_pii): không mạng, không Docker."""

    demo = None
    saved: dict = {}

    @classmethod
    def setUpClass(cls) -> None:
        for name in ("moc_env", "demo"):
            cls.saved[name] = sys.modules.pop(name, None)
        stub = types.ModuleType("moc_env")

        def no_network(*args, **kwargs):
            raise AssertionError("test không được gọi mạng, Docker")

        stub.ENV, stub.ROOT, stub.PUBLIC_URL, stub.EICAR = {}, ROOT, "http://localhost:8080", b""
        stub.HTTPError = type("HTTPError", (Exception,), {})
        stub.Session = type("Session", (), {"__init__": no_network})
        for name in ("call_json", "compose", "request", "text_pdf", "user_token"):
            setattr(stub, name, no_network)
        sys.modules["moc_env"] = stub
        cls.demo = importlib.import_module("demo")

    @classmethod
    def tearDownClass(cls) -> None:
        for name, module in cls.saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def test_registered(self) -> None:
        self.assertIs(self.demo.DEMOS["log-tap-trung"], self.demo.log_tap_trung)
        self.assertEqual(self.demo.LOG_TRACED, ("apisix", "svc-workflow", "hasura", "svc-files"))
        self.assertEqual(list(self.demo.LOG_COLLECTED), LOGGED)

    def test_complete_task_matches_session_complete(self) -> None:
        # màn gọi tay completeTask để gửi kèm X-Request-Id: phải đúng mutation của Session.complete (moc_env.py)
        text = (ROOT / "scripts" / "moc_env.py").read_text(encoding="utf-8")
        self.assertIn(" ".join(self.demo.COMPLETE_TASK.split()), " ".join(text.split()))

    def test_leaks(self) -> None:
        clean = [{"service": "apisix", "message": 'x "GET /api/search HTTP/1.1" 200 "demo-log-1"'},
                 {"service": "svc-files", "event": "office.document.rendered", "request_id": "demo-log-1"}]
        self.assertEqual(self.demo.traced_services(clean), {"apisix", "svc-files"})
        self.assertEqual(self.demo.log_leaks(clean, ["tok-cua-van-thu-123", "", "ngan"]), [])
        dirty = [{"service": "apisix", "message": "GET /tim-kiem?q=abc"},
                 {"service": "svc-workflow", "message": "Authorization: Bearer eyJabc"},
                 {"service": "svc-files", "message": "lọt tok-cua-van-thu-123"},
                 {"service": "app-office", "message": "ngan"}]                   # bí mật dưới 8 ký tự: bỏ qua
        found = self.demo.log_leaks(dirty, ["tok-cua-van-thu-123", "ngan"])
        self.assertEqual(found, ["apisix: ?q=", "svc-workflow: Bearer ey", "svc-workflow: eyJ",
                                 "svc-files: giá trị bí mật"])
        self.assertNotIn("tok-cua-van-thu-123", " ".join(found))           # không in giá trị bí mật


    def test_logged_since(self) -> None:
        rows = [{"p_timestamp": "2026-10-25T17:18:52.9"}, {"p_timestamp": "2026-10-25T17:18:53"},
                {"p_timestamp": "2026-10-25T17:18:54.123456"}, {"p_timestamp": "2026-10-25T17:18:55.1+00:00"},
                {"p_timestamp": ""}, {}]
        self.assertEqual(self.demo.logged_since(rows, "2026-10-25T17:18:53Z"), rows[1:4])

    def test_postgres_entry(self) -> None:
        # dòng cùng lô có cùng p_timestamp: Parseable trả CONTEXT, STATEMENT trước dòng ERROR (lần chạy CI đầu tiên)
        pre = "2026-10-26 00:49:35.888 +07"
        rows = [{"service": "postgres", "message": f"{pre} [91] CONTEXT:  PL/pgSQL function inline_code_block"},
                {"service": "postgres", "message": f"{pre} [84] ERROR:  khac"},
                {"service": "postgres", "message": f"{pre} [91] STATEMENT:  do [REDACTED]"},
                {"service": "postgres", "message": f"{pre} [91] ERROR:  demo-log-ab12: lỗi thử"},
                {"service": "keycloak", "message": f"{pre} [91] ERROR:  không phải postgres"},
                {"service": "postgres", "message": f"{pre} [84] STATEMENT:  select 1"},
                {"service": "postgres", "message": "2026-10-26 00:52:00.001 +07 [91] STATEMENT:  pid dùng lại"}]
        self.assertEqual(self.demo.postgres_entry(rows, "demo-log-ab12"), [rows[3], rows[0], rows[2]])
        self.assertEqual(self.demo.postgres_entry(rows, "demo-log-cd34"), [])
        self.assertEqual(self.demo.postgres_entry(rows[4:], "không phải"), [])


if __name__ == "__main__":
    unittest.main()
