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

"""Tường lửa ứng dụng web ở cổng (F3.15): image APISIX kèm coraza-proxy-wasm ghim digest và băm, WAF bật toàn cục ở pha
rewrite và thấy thân yêu cầu, chặn mặc định, mỗi loại trừ có lý do trong README và hẹp đúng trường chữ tự do mà giao
diện gửi, JSON lồng sâu bị chặn trước WAF, MOC_WAF sai giá trị thì container dừng ngay lúc khởi động và `make up`,
reconciler GitOps từ chối trước. Kiểm chữ (không có PyYAML, không cần Docker) — chặn thật trên stack: khối "Tường lửa
ứng dụng web" của smoke.py.
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
APISIX = ROOT / "platform" / "apisix"
spec = importlib.util.spec_from_file_location("reconcile_waf", ROOT / "scripts" / "reconcile.py")
reconcile: Any = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reconcile)


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def service_block(name: str) -> str:
    """Khối của một dịch vụ trong docker-compose.yml: từ dòng `  <name>:` tới dịch vụ kế tiếp."""
    lines = read(ROOT / "docker-compose.yml").splitlines()
    start = lines.index(f"  {name}:")
    end = start + 1
    while end < len(lines) and not re.match(r"(  )?[A-Za-z#]", lines[end]):
        end += 1
    return "\n".join(lines[start:end])


def global_rule() -> str:
    """Khối global_rules của apisix.yaml (tới routes:)."""
    text = read(APISIX / "apisix.yaml")
    return text[text.index("\nglobal_rules:\n"):text.index("\nroutes:\n")]


class ImageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dockerfile = read(APISIX / "Dockerfile")

    def test_both_images_pinned_by_digest(self) -> None:
        self.assertRegex(self.dockerfile, r"ghcr\.io/corazawaf/coraza-proxy-wasm:\d+\.\d+\.\d+@sha256:[0-9a-f]{64} ")
        self.assertRegex(self.dockerfile, r"\nFROM apache/apisix:3\.18\.0-debian@sha256:[0-9a-f]{64}\n")

    def test_wasm_checked_against_release_hash_and_loaded_from_same_path(self) -> None:
        copied = re.search(r"COPY --from=coraza /plugin\.wasm (\S+)\n", self.dockerfile).group(1)
        checked = re.search(r'echo "([0-9a-f]{64})  (\S+)"\s*\\\n\s*\| sha256sum -c -', self.dockerfile)
        self.assertIsNotNone(checked, "thiếu bước sha256sum -c cho tệp .wasm")
        self.assertEqual("/usr/local/apisix/" + checked.group(2), copied)   # WORKDIR của image APISIX
        self.assertIn(f"file: {copied}\n", read(APISIX / "config.yaml"))

    def test_compose_builds_team_image_on_one_line(self) -> None:
        block = service_block("apisix")
        # make install thay đúng dòng `build:` bằng pull_policy: never (scripts/install.sh)
        self.assertRegex(block, r"\n {4}build: \./platform/apisix\n {4}image: moc/apisix:\$\{MOC_VERSION:-dev\}\n")
        self.assertNotIn("apache/apisix", block)
        self.assertIn("MOC_WAF: ${MOC_WAF:-On}", block)
        self.assertIn("MOC_APISIX_WORKERS: ${MOC_APISIX_WORKERS:-4}", block)

    def test_env_example_documents_switch(self) -> None:
        text = read(ROOT / (".e" + "nv.example"))
        self.assertIn("\nMOC_WAF=On\n", text)
        self.assertIn("\nMOC_APISIX_WORKERS=4\n", text)

    def test_entrypoint_rejects_bad_switch_before_apisix_starts(self) -> None:
        # MOC_WAF sai thì Coraza không nạp được và APISIX trả 503 mọi yêu cầu: script dừng trước, báo rõ
        self.assertIn("COPY --chmod=0755 kiem-moi-truong.sh /usr/local/bin/moc-kiem-moi-truong\n", self.dockerfile)
        self.assertIn('ENTRYPOINT ["/usr/local/bin/moc-kiem-moi-truong"]\nCMD ["docker-start"]\n', self.dockerfile)
        script = read(APISIX / "kiem-moi-truong.sh")
        self.assertIn('\nexec /docker-entrypoint.sh "$@"\n', script)     # entrypoint gốc của image APISIX
        dry = script.replace('exec /docker-entrypoint.sh "$@"', "echo CHAY")
        for value, code in (("On", 0), ("on", 0), ("DetectionOnly", 0), ("Off", 0), ("Bogus", 64), ("", 64),
                            ("On ", 64)):
            with self.subTest(MOC_WAF=value):
                run = subprocess.run(["sh", "-s"], input=dry, capture_output=True, text=True,
                                     env={"PATH": "/usr/bin:/bin", "MOC_WAF": value})
                self.assertEqual(run.returncode, code, run.stderr)
                self.assertEqual("CHAY" in run.stdout, code == 0)
                if code:
                    self.assertIn("MOC_WAF", run.stderr)
        run = subprocess.run(["sh", "-s"], input=dry, capture_output=True, text=True,
                             env={"PATH": "/usr/bin:/bin", "MOC_APISIX_WORKERS": "bốn"})
        self.assertEqual(run.returncode, 64)
        # --chi-kiem (make up, reconciler GitOps gọi trên máy chủ): chỉ kiểm, không chạy APISIX
        for value, code in (("On", 0), ("Bogus", 64)):
            run = subprocess.run(["sh", str(APISIX / "kiem-moi-truong.sh"), "--chi-kiem"], capture_output=True,
                                 text=True, env={"PATH": "/usr/bin:/bin", "MOC_WAF": value})
            self.assertEqual(run.returncode, code, run.stderr)
        # `make up` (qua env-ready) từ chối trước bằng chính script này, với giá trị compose sẽ dùng (shell rồi .env,
        # mặc định On): `up --wait` không thấy container khởi động lại liên tục là lỗi
        make = read(ROOT / "Makefile")
        recipe = make[make.index("\nenv-ready:"):make.index("\ncheck:")]
        self.assertIn("$(COMPOSE) config --format json apisix", recipe)
        self.assertIn("sh platform/apisix/kiem-moi-truong.sh --chi-kiem", recipe)


class ReconcileGatewayEnvTest(unittest.TestCase):
    """Reconciler GitOps (scripts/reconcile.py) gọi thẳng `docker compose up --wait`, không qua `make up`: MOC_WAF sai
    phải bị từ chối trước khi dừng Signet, bằng cùng script, và không đánh dấu commit là áp lỗi (lỗi ở .env)."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.src = pathlib.Path(tmp.name)
        (self.src / "platform" / "apisix").mkdir(parents=True)
        (self.src / "scripts").mkdir()
        (self.src / "scripts" / "install.sh").write_text("", encoding="utf-8")
        shutil.copy(APISIX / "kiem-moi-truong.sh", self.src / "platform" / "apisix" / "kiem-moi-truong.sh")
        self.calls: list[list[str]] = []
        self.environment: dict[str, Any] = {}
        real = reconcile._run

        def fake(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
            self.calls.append(cmd)
            if cmd[:2] == ["docker", "compose"]:
                if cmd[-4:] != ["config", "--format", "json", "apisix"]:
                    return subprocess.CompletedProcess(cmd, 0, "", "")      # build, down, up: chỉ ghi lại
                self.assertEqual(kw.get("cwd"), self.src)                   # compose của commit sắp áp
                out = {"services": {"apisix": {"environment": self.environment}}}
                return subprocess.CompletedProcess(cmd, 0, json.dumps(out), "")
            return real(cmd, **kw)                                          # script kiểm: chạy thật

        saved = {n: getattr(reconcile, n) for n in ("_run", "checkout")}
        self.addCleanup(lambda: [setattr(reconcile, n, v) for n, v in saved.items()])
        reconcile._run = fake
        reconcile.checkout = lambda git, src, commit: {"PATH": os.environ.get("PATH", os.defpath)}

    def test_values_compose_will_use_go_through_the_entrypoint_check(self) -> None:
        env = {"PATH": os.environ.get("PATH", os.defpath)}
        for values, error in (({"MOC_WAF": "On", "MOC_APISIX_WORKERS": "4"}, None),
                              ({"MOC_WAF": "detectiononly", "MOC_APISIX_WORKERS": "auto"}, None),
                              ({}, None),
                              ({"MOC_WAF": "Bogus", "MOC_APISIX_WORKERS": "4"}, "MOC_WAF='Bogus'"),
                              ({"MOC_WAF": "On ", "MOC_APISIX_WORKERS": "4"}, "MOC_WAF='On '"),
                              ({"MOC_WAF": "On", "MOC_APISIX_WORKERS": "0"}, "MOC_APISIX_WORKERS='0'")):
            with self.subTest(values):
                self.environment = values
                if error is None:
                    reconcile.check_gateway_env(self.src, env)
                else:
                    with self.assertRaisesRegex(reconcile.ConfigError, re.escape(error)):
                        reconcile.check_gateway_env(self.src, env)

    def test_commit_without_waf_is_not_checked(self) -> None:
        (self.src / "platform" / "apisix" / "kiem-moi-truong.sh").unlink()
        reconcile.check_gateway_env(self.src, {})
        self.assertEqual(self.calls, [])

    def test_bad_switch_does_not_stop_moc_nor_mark_commit_failed(self) -> None:
        self.environment = {"MOC_WAF": "bat"}
        with self.assertRaises(reconcile.ConfigError):
            reconcile.apply(["git"], self.src, "c0ffee", "beef00")
        stopped = [c for c in self.calls if c[:2] == ["docker", "compose"] and {"build", "down", "up"} & set(c)]
        self.assertEqual(stopped, [], "MOC_WAF sai: không được dựng, dừng hay chạy lại Signet")
        self.environment = {"MOC_WAF": "On"}
        reconcile.apply(["git"], self.src, "c0ffee", "beef00")
        self.assertTrue(any("down" in c for c in self.calls))
        # gitops: ConfigError được bắt trước nhánh ghi state["failed"]
        code = inspect.getsource(reconcile.gitops)
        self.assertLess(code.index("except ConfigError"), code.index('state["failed"] = target'))


class GatewayConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = read(APISIX / "config.yaml")

    def test_wasm_plugin_runs_in_rewrite_before_token_check_after_request_id(self) -> None:
        block = self.config[self.config.index("\nwasm:\n"):]
        self.assertIn("- name: coraza-waf\n", block)
        self.assertIn("http_request_phase: rewrite\n", block)
        priority = int(re.search(r"priority: (\d+)", block).group(1))
        self.assertLess(priority, 12015)        # request-id chạy trước: phản hồi 403 vẫn có X-Request-Id
        self.assertLess(priority, 10000)        # serverless-pre-function (chặn JSON lồng sâu) chạy trước

    def test_request_body_reaches_waf(self) -> None:
        # apisix/wasm.lua chỉ đưa thân cho plugin wasm khi biến này khác rỗng; thiếu thì CRS quyết chặn sau upstream
        snippet = re.search(r"http_server_location_configuration_snippet: \|\n((?:    .*\n)+)", self.config).group(1)
        self.assertIn("set $wasm_process_req_body on;", snippet)

    def test_switch_and_workers_from_env(self) -> None:
        self.assertIn("worker_processes: ${{MOC_APISIX_WORKERS:=4}}", self.config)
        envs = self.config[self.config.index("  envs:\n"):self.config.index("http_configuration_snippet")]
        self.assertIn("    - MOC_WAF\n", envs)
        plugins = self.config[self.config.index("\nplugins:\n"):self.config.index("\nplugin_attr:")]
        self.assertIn("  - serverless-pre-function\n", plugins)

    def test_body_limit_matches_client_max_body_size(self) -> None:
        mib = int(re.search(r"client_max_body_size: (\d+)m", self.config).group(1))
        rule = global_rule()
        self.assertIn(f"SecRequestBodyLimit {mib * 1024 * 1024}\n", rule)
        self.assertIn(f"SecRequestBodyInMemoryLimit {mib * 1024 * 1024}\n", rule)


class RulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = global_rule()
        self.directives = self.rule[self.rule.index("coraza-waf:"):]

    def test_global_and_blocking_by_default(self) -> None:
        self.assertIn("coraza-waf:", self.rule)
        self.assertIn("- SecRuleEngine ${{MOC_WAF:=On}}\n", self.directives)
        self.assertIn("tx.blocking_paranoia_level=1", self.directives)
        self.assertIn("tx.inbound_anomaly_score_threshold=5", self.directives)
        self.assertIn("- Include @owasp_crs/*.conf\n", self.directives)
        # thiết lập trước bộ luật, loại trừ toàn cục sau (SecRuleRemoveById chỉ gỡ luật đã nạp)
        order = [self.directives.index(d) for d in ("Include @recommended-conf", "SecRuleEngine",
                                                     "Include @crs-setup-conf", "id:900000", "id:10010",
                                                     "Include @owasp_crs/*.conf", "SecRuleRemoveById")]
        self.assertEqual(order, sorted(order))
        self.assertIn("- SecResponseBodyAccess Off\n", self.directives)

    def test_every_exclusion_has_reason_and_is_documented(self) -> None:
        readme = read(APISIX / "README.md")
        ids = re.findall(r'"id:(10\d\d\d),', self.directives)
        self.assertEqual(ids, ["10010", "10020", "10030", "10031", "10032", "10033", "10040", "10060",
                               "10061"])
        removed = re.findall(r"SecRuleRemoveById (\d+)", self.directives)
        self.assertEqual(removed, ["920350"])
        for rule_id in ids + removed:
            self.assertTrue(f"\n| {rule_id} |" in readme, f"platform/apisix/README.md thiếu dòng của luật {rule_id}")
        # chỉ thị loại trừ (dòng `- >-` của 10010–10040, SecRuleRemoveById) có chú thích lý do ngay trên
        lines = self.directives.splitlines()
        for i, line in enumerate(lines):
            starts = line.strip() == "- >-" and re.search(r'"id:100[1-4]\d,', lines[i + 1])
            if starts or "SecRuleRemoveById" in line:
                self.assertTrue(lines[i - 1].strip().startswith("#"), f"loại trừ không có chú thích lý do: {line}")

    def test_exclusions_scoped_to_path_and_target(self) -> None:
        # loại trừ trên đường cụ thể, gỡ luật trên đúng tham số — không tắt cả nhóm luật cho mọi đầu vào
        scoped = re.findall(r'SecRule REQUEST_FILENAME "@(?:beginsWith|rx|streq) [^"]+" "id:(\d+),phase:1,pass,nolog,',
                            self.directives)
        self.assertEqual(scoped, ["10010", "10020", "10030", "10031", "10032", "10033", "10040"])
        self.assertNotIn("ctl:ruleEngine=Off", self.directives)
        self.assertNotIn("ctl:ruleRemoveByTag", self.directives)
        self.assertNotIn("ctl:ruleRemoveById", self.directives)
        for target in re.findall(r"ctl:ruleRemoveTarget(?:ById|ByTag)=[^;]+;([^,\"\n]+)", self.directives):
            self.assertRegex(target, r"^(?:ARGS:[a-z_.-]+|FILES|MULTIPART_PART_HEADERS:[a-z]+)$")

    def exclusion(self, rule_id: str) -> str:
        start = self.directives.index(f'"id:{rule_id},')
        return self.directives[start:self.directives.index('"\n', start)]

    def test_free_text_exclusion_only_on_fields_the_apps_send(self) -> None:
        # Loại trừ 5, 6: chỉ dải id 932… (lệnh hệ điều hành), 933… (PHP), 931100 (URL http://<IP> ở đầu chữ) và
        # 931120 (câu mở đầu "File"/"http", kết thúc "?"), chỉ trên khóa biến của các ô chữ tự do. Mỗi khóa phải còn
        # được giao diện gửi (đổi tên biến thì loại trừ thành vô dụng, chặn nhầm quay lại); SQLi, XSS, duyệt thư mục,
        # Log4Shell không bao giờ được gỡ ở đây
        office = ROOT / "apps" / "office" / "app"
        sent = {
            "json.variables.o.body": (office / "pages/van-ban-di/soan.vue", r"\{ o: \{ \.\.\.fields",
                                      r"body: form\.body"),
            "json.variables.o.summary": (office / "pages/van-ban-di/soan.vue", r"\{ o: \{ \.\.\.fields",
                                         r"summary: form\.summary"),
            "json.variables.set.body": (office / "pages/van-ban-di/soan.vue", r"_set: \$set", r"set: fields"),
            "json.variables.set.summary": (office / "pages/van-ban-di/soan.vue", r"_set: \$set", r"set: fields"),
            "json.variables.d.summary": (office / "pages/van-ban-den/tiep-nhan.vue", r"receiveIncoming\(data: \$d\)",
                                         r"summary: multiLine\(form\.summary\)"),
            "json.variables.d.instruction": (office / "components/TaskPanel.vue", r"data: \$d",
                                             r"instruction: direct\.instruction"),
            "json.variables.d.note": (office / "components/TaskPanel.vue", r"data: \$d", r"\bnote: "),
            "json.variables.d.result_note": (office / "components/TaskPanel.vue", r"data: \$d", r"result_note: "),
            "json.variables.c": (office / "components/FeedbackButton.vue", r"comment: \$c", r"\bc: comment\.value"),
            "json.question": (office / "composables/useApi.ts", r"'/api/documents/ask'", r"\n  question: string\n"),
        }
        rule = self.exclusion("10031") + ",\n" + self.exclusion("10032")
        keys = set(re.findall(r";ARGS:([a-z_.]+)", rule))
        self.assertEqual(keys, set(sent))
        for key, (path, *evidence) in sent.items():
            code = read(path)
            for pattern in evidence:
                self.assertRegex(code, pattern, f"{key}: {path.name} không còn gửi trường này")
            for ids in ("932000-932999", "933000-933999", "931100", "931120"):
                self.assertIn(f"ctl:ruleRemoveTargetById={ids};ARGS:{key},", rule + ",")
        removed = set(re.findall(r"ruleRemoveTargetById=([\d-]+);", rule))
        self.assertEqual(removed, {"932000-932999", "933000-933999", "931100", "931120"})

    def test_java_and_node_rules_never_removed_by_tag(self) -> None:
        # Nhãn attack-rce gồm cả 934… (Node.js) và 944… (Java, Log4Shell): gỡ theo nhãn thì mất luôn chúng. Chỉ gỡ
        # theo dải id; gỡ theo nhãn chỉ có OWASP_CRS trên mật khẩu (loại trừ 1)
        self.assertEqual(set(re.findall(r"ruleRemoveTargetByTag=([A-Za-z_-]+);", self.directives)), {"OWASP_CRS"})
        for low, high in re.findall(r"ruleRemoveTargetById=(\d+)-(\d+);", self.directives):
            self.assertIn((low, high), {("932000", "932999"), ("933000", "933999")})

    def test_search_box_only_loses_url_and_php_file_rules(self) -> None:
        # Loại trừ 7: ô Tìm kiếm nhận đường dẫn http://<IP>/… (931100), câu "File …?" (931120), dòng "03 file (PDF)"
        # (933160) — chỉ gỡ đúng ba luật đó trên q; chèn lệnh, SQLi, XSS… vẫn soi
        rule = self.exclusion("10033")
        self.assertEqual(re.findall(r"ctl:([^,\"]+)", rule), [f"ruleRemoveTargetById={i};ARGS:q"
                                                             for i in ("931100", "931120", "933160")])
        office = ROOT / "apps" / "office" / "app"
        self.assertIn("/api/search?${qs}", read(office / "composables/useApi.ts"))
        self.assertIn("query: { q: q.value.trim()", read(office / "pages/tim-kiem.vue"))

    def test_upload_name_exclusion_only_on_upload_routes(self) -> None:
        rule = self.exclusion("10040")
        path = re.search(r'"@rx (\S+)"', self.directives[self.directives.index('"id:10040,') - 120:]).group(1)
        for uri, hit in (("/api/files", True), ("/api/imports/incoming", True), ("/api/files/x/read", False),
                         ("/v1/graphql", False), ("/api/search", False), ("/api/imports", False)):
            self.assertEqual(bool(re.search(path, uri)), hit, uri)
        self.assertIn("ctl:ruleRemoveTargetById=920120;FILES,", rule)
        self.assertNotIn("FILES_NAMES", rule)                    # tên trường do ứng dụng đặt: vẫn soi
        self.assertEqual(set(re.findall(r"ruleRemoveTargetById=(\d+);", rule)), {"920120", "922130"})
        self.assertEqual(set(re.findall(r"MULTIPART_PART_HEADERS:([a-z]+)", rule)), {"file", "data", "archive"})

    def test_argument_limit_rules_block(self) -> None:
        # GHSA-6r3q-mjv7-xr8m: tham số thứ 1000 trở đi không được soi — chặn hẳn
        self.assertRegex(self.directives, r'SecRule &ARGS_GET "@ge 1000" "id:10060,phase:1,deny,status:403')
        self.assertRegex(self.directives, r'SecRule &ARGS_POST "@ge 1000" "id:10061,phase:2,deny,status:403')

    def test_deep_json_guard_before_waf(self) -> None:
        # GHSA-6gcq-wc29-5xf2: Coraza 3.3.3 đọc JSON đệ quy không giới hạn — thân lồng sâu bị chặn trước
        guard = self.rule[self.rule.index("serverless-pre-function:"):self.rule.index("coraza-waf:")]
        self.assertIn("phase: rewrite", guard)
        self.assertIn('require("cjson.safe").new()', guard)
        depth = int(re.search(r"decode_max_depth\((\d+)\)", guard).group(1))
        self.assertLessEqual(depth, 64)
        self.assertIn('return 400, {error = "invalid_json"}', guard)
        self.assertIn('t:find("^application/json")', guard)
        self.assertIn('ngx.req.get_headers(0)["content-type"]', guard)   # mọi giá trị, không chỉ giá trị đầu


class SmokeTest(unittest.TestCase):
    def test_smoke_checks_waf_unless_switched_off(self) -> None:
        smoke = read(ROOT / "scripts" / "smoke.py")
        self.assertIn('print("Tường lửa ứng dụng web")', smoke)
        self.assertIn('if ENV.get("MOC_WAF", "On") == "On":\n        check_waf(clerk, director, staff, tag)', smoke)
        self.assertLess(smoke.index("check_waf(clerk, director, staff, tag)"), smoke.index('print("Trạm kiểm dịch")'))
        # chữ hành chính thật phải qua (vòng sửa: chặn nhầm tên tệp có ' ; =, nội dung có đề mục La Mã)
        block = smoke[smoke.index("def check_waf("):smoke.index("\ndef main(")]
        named = re.search(r"name = f\"[^\"]*'[^\"]*;[^\"]*=[^\"]*\.pdf\"", block)
        self.assertTrue(named, "smoke thiếu tên tệp có ' ; =")
        roman = '("I. ' in block and "\\nII. " in block and "\\nIII. " in block
        self.assertTrue(roman, "smoke thiếu nội dung có đề mục I./II./III.")
        self.assertIn("insert_office_documents_one", block)
        # phần đại diện của lượt dò chặn nhầm: mỗi luật đã gỡ trên chữ tự do, ô Tìm kiếm có một mẫu chữ thật
        for rule_id in ("933210", "931120", "931100", "933160"):
            self.assertIn(f"({rule_id})", block)
        self.assertIn("update_office_documents_by_pk", block)
        self.assertIn('"/api/search?" + urllib.parse.urlencode({"q": text})', block)


if __name__ == "__main__":
    unittest.main()
