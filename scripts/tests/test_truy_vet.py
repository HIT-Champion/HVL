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

"""Truy vết phân tán (#364): Jaeger chỉ ở profile trace, ghim digest, giao diện chỉ trên 127.0.0.1; APISIX lấy mẫu theo
MOC_TRACE_RATIO (mặc định 0: không span nào) và gửi đúng Jaeger; Jaeger bỏ chuỗi truy vấn, không mở gRPC hay tự gửi span
ra ngoài; tỉ lệ sai bị từ chối trước khi APISIX bỏ cả global rule chung với WAF. Kiểm chữ (không có PyYAML, không cần
Docker) — cú pháp jaeger.yaml do bước CI `jaeger validate` kiểm; bộ che span: test_tracing.py của svc-files.
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
COMPOSE = ROOT / "docker-compose.yml"
APISIX = ROOT / "platform" / "apisix"
JAEGER = ROOT / "platform" / "trace" / "jaeger.yaml"


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def service_block(name: str) -> str:
    """Khối của một dịch vụ trong docker-compose.yml: từ dòng `  <name>:` tới dịch vụ kế tiếp."""
    lines = read(COMPOSE).splitlines()
    start = lines.index(f"  {name}:")
    end = start + 1
    while end < len(lines) and not re.match(r"(  )?[A-Za-z#]", lines[end]):
        end += 1
    return "\n".join(lines[start:end])


def section(text: str, key: str) -> str:
    """Mục cấp cao nhất `key:` của một tệp YAML, tới mục cấp cao nhất kế tiếp."""
    start = text.index(f"\n{key}:\n") + 1
    nxt = re.search(r"^[a-z_]+:", text[start + len(key) + 2:], re.M)
    return text[start:start + len(key) + 2 + nxt.start()] if nxt else text[start:]


class JaegerServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.block = service_block("jaeger")

    def test_only_in_trace_profile_with_pinned_image(self) -> None:
        self.assertIn("\n    profiles: [trace]\n", self.block)
        self.assertEqual(read(COMPOSE).count("profiles: [trace]"), 1)
        self.assertRegex(self.block, r"\n {4}image: jaegertracing/jaeger:\d+\.\d+\.\d+@sha256:[0-9a-f]{64}\n")

    def test_locked_down_and_bounded(self) -> None:
        for line in ("read_only: true", "cap_drop: [ALL]", "security_opt: [no-new-privileges:true]"):
            self.assertIn(f"\n    {line}\n", self.block)
        self.assertRegex(self.block, r"\n {4}mem_limit: 256m\b")
        self.assertIn("\n      - ./platform/trace/jaeger.yaml:/etc/jaeger/jaeger.yaml:ro\n", self.block)
        self.assertIn('command: ["--config", "/etc/jaeger/jaeger.yaml"]', self.block)

    def test_ui_only_on_loopback_and_otlp_not_published(self) -> None:
        ports = re.findall(r"^ {6}- (.+)$", self.block[self.block.index("    ports:"):], re.M)
        self.assertEqual(ports, ["127.0.0.1:${MOC_TRACE_PORT:-16686}:16686"])
        self.assertIn("<<: *common", self.block)                    # mạng moc của x-common, như các dịch vụ lõi
        self.assertNotIn("networks:", self.block)

    def test_installed_with_the_release(self) -> None:
        # install.sh chỉ tự đọc bind mount của profile core, app
        self.assertRegex(read(ROOT / "scripts" / "install.sh"), r"\n\s+platform/trace/jaeger\.yaml\)")

    def test_ci_validates_the_config_with_the_pinned_image(self) -> None:
        ci = read(ROOT / ".github" / "workflows" / "ci.yml")
        self.assertIn("sed -n '/^  jaeger:$/,/^    image:/s/^    image: //p' docker-compose.yml", ci)
        self.assertIn('"$image" validate --config /etc/jaeger/jaeger.yaml', ci)
        self.assertRegex(ci, r"for p in [a-z -]*\btrace\b[a-z -]*; do")


class JaegerConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = read(JAEGER)

    def test_receives_otlp_http_only(self) -> None:
        receivers = section(self.text, "receivers")
        self.assertIn("      http:\n        endpoint: 0.0.0.0:4318\n", receivers)
        self.assertNotIn("grpc", receivers)

    def test_query_does_not_trace_itself_nor_open_grpc(self) -> None:
        extensions = section(self.text, "extensions")
        self.assertIn("    enable_tracing: false\n", extensions)
        self.assertIn("    grpc:\n      endpoint: 127.0.0.1:16685\n", extensions)
        self.assertIn("    http:\n      endpoint: 0.0.0.0:16686\n", extensions)

    def test_bounded_in_memory_store(self) -> None:
        extensions = section(self.text, "extensions")
        self.assertRegex(extensions, r"\n {8}memory:\n {10}max_traces: \d+\n")
        self.assertNotIn("badger", extensions)

    def test_query_string_is_dropped_before_storage(self) -> None:
        pipeline = section(self.text, "service")
        self.assertIn("      processors: [attributes/che, batch]\n", pipeline)
        processors = section(self.text, "processors")
        for key in ("http.target", "url.query"):
            self.assertIn(f"      - key: {key}\n        action: delete\n", processors)

    def test_no_metrics_port(self) -> None:
        self.assertIn("    metrics:\n      level: none\n", section(self.text, "service"))


class GatewayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = read(APISIX / "config.yaml")
        self.gateway = read(APISIX / "apisix.yaml")

    def test_plugin_enabled_and_ratio_visible_to_workers(self) -> None:
        plugins = self.config[self.config.index("\nplugins:\n"):self.config.index("\nplugin_attr:")]
        self.assertIn("  - opentelemetry\n", plugins)
        envs = self.config[self.config.index("  envs:\n"):self.config.index("http_configuration_snippet")]
        self.assertIn("    - MOC_TRACE_RATIO\n", envs)

    def test_global_rule_samples_by_ratio_defaulting_to_zero(self) -> None:
        rules = self.gateway[self.gateway.index("\nglobal_rules:\n"):self.gateway.index("\nroutes:\n")]
        self.assertEqual(rules.count("  - id: "), 1)                 # cùng global rule với request-id, WAF
        self.assertIn("      opentelemetry:\n        sampler:\n          name: trace_id_ratio\n"
                      "          options:\n            fraction: ${{MOC_TRACE_RATIO:=0}}\n"
                      "        additional_header_prefix_attributes: [x-request-id]\n", rules)
        self.assertNotIn("name: parent_base", rules)                # cờ của client không bắt APISIX ghi

    def test_spans_go_to_jaeger_in_the_core_network(self) -> None:
        metadata = section(self.gateway, "plugin_metadata")
        self.assertIn("  - id: opentelemetry\n    trace_id_source: random\n", metadata)
        self.assertIn("    collector:\n      address: jaeger:4318\n", metadata)
        self.assertIn("      service.name: apisix\n", metadata)

    def test_ratio_reaches_gateway_and_services_defaulting_to_zero(self) -> None:
        for name in ("apisix", "svc-files", "svc-workflow"):
            self.assertIn("      MOC_TRACE_RATIO: ${MOC_TRACE_RATIO:-0}\n", service_block(name) + "\n", name)
        text = read(ROOT / (".e" + "nv.example"))
        self.assertIn("\nMOC_TRACE_RATIO=0\n", text)
        self.assertIn("\nMOC_TRACE_PORT=16686\n", text)


class RatioCheckTest(unittest.TestCase):
    """Tỉ lệ sai kiểu làm APISIX bỏ cả global rule (mất WAF, mã yêu cầu): entrypoint, `make up` dừng trước."""

    def run_check(self, value: str | None) -> subprocess.CompletedProcess[str]:
        env = {"PATH": "/usr/bin:/bin"}
        if value is not None:
            env["MOC_TRACE_RATIO"] = value
        return subprocess.run(["sh", str(APISIX / "kiem-moi-truong.sh"), "--chi-kiem"], capture_output=True,
                              text=True, env=env)

    def test_accepts_ratios_between_zero_and_one(self) -> None:
        for value in (None, "", "0", "1", "0.1", "0.25", "1.0"):
            with self.subTest(value=value):
                self.assertEqual(self.run_check(value).returncode, 0)

    def test_rejects_anything_else_with_a_clear_message(self) -> None:
        for value in ("1.5", "2", "-0.1", "abc", "0.1 ", ".5", "0.", "1e-1", "01"):
            with self.subTest(value=value):
                run = self.run_check(value)
                self.assertEqual(run.returncode, 64)
                self.assertIn(f"MOC_TRACE_RATIO='{value}'", run.stderr)

    def test_make_up_checks_the_value_compose_will_use(self) -> None:
        make = read(ROOT / "Makefile")
        recipe = make[make.index("\nenv-ready:"):make.index("\ncheck:")]
        self.assertIn("r=$$(get MOC_TRACE_RATIO)", recipe)
        self.assertIn('export MOC_TRACE_RATIO="$$r"', recipe)


if __name__ == "__main__":
    unittest.main()
