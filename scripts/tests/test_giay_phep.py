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

"""Kiểm giấy phép trên SBOM (scripts/license_audit.py, make license-audit, job "Giấy phép (PoF #2)" của CI): biểu thức
SPDX (OR chọn nhánh được nhận, AND đòi mọi phần), chữ tự do, gói chưa rõ giấy phép, copyleft yếu liệt kê riêng, GPL bị
chặn; ngoại lệ phải trùng giấy phép SBOM ghi, khai tay thì phải ghi phiên bản; tệp ngoại lệ thật của repo hợp lệ; image
Syft ghim cùng một digest ở Makefile và ci.yml, make sbom chỉ đọc cây mã nguồn. Không cần Docker, không gọi mạng.
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent
spec = importlib.util.spec_from_file_location("license_audit", SCRIPTS / "license_audit.py")
audit_mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = audit_mod          # dataclass cần tìm thấy mô-đun của chính nó
spec.loader.exec_module(audit_mod)


def component(purl: str, *licenses: dict, where: str = "/apps/office/package-lock.json") -> dict:
    name, _, version = purl.split("/", 1)[1].rpartition("@")
    return {"type": "library", "name": name, "version": version, "purl": purl, "licenses": list(licenses),
            "properties": [{"name": "syft:location:0:path", "value": where}]}


def spdx(id_: str) -> dict:
    return {"license": {"id": id_}}


def expr(text: str) -> dict:
    return {"expression": text}


def named(text: str) -> dict:
    return {"license": {"name": text}}


def sbom(*components: dict) -> dict:
    return {"bomFormat": "CycloneDX", "specVersion": "1.6",
            "metadata": {"component": {"type": "file", "name": "moc", "version": "1.1.0"},
                         "tools": {"components": [{"name": "syft", "version": "1.54.1"}]}},
            "components": [{"type": "file", "name": "/apps/office/package-lock.json"}, *components]}


class ExpressionTest(unittest.TestCase):
    def verdict(self, text: str) -> int:
        return audit_mod.judge(audit_mod.parse(text))[0]

    def test_or_takes_the_accepted_branch_and_takes_all(self) -> None:
        # node-forge: cho chọn BSD-3-Clause hay GPL-2.0, Signet dùng theo BSD-3-Clause
        self.assertEqual(self.verdict("BSD-3-Clause OR GPL-2.0"), audit_mod.PASS)
        self.assertEqual(self.verdict("MIT AND GPL-3.0-only"), audit_mod.FAIL)
        self.assertEqual(self.verdict("(MIT OR GPL-3.0-only) AND Apache-2.0"), audit_mod.PASS)
        self.assertEqual(self.verdict("MIT AND (GPL-3.0-only OR AGPL-3.0-only)"), audit_mod.FAIL)

    def test_operators_and_ids_ignore_case(self) -> None:
        self.assertEqual(self.verdict("mit or apache-2.0"), audit_mod.PASS)
        self.assertEqual(audit_mod.render(audit_mod.parse("apache-2.0 and bsd-3-clause")),
                         "Apache-2.0 AND BSD-3-Clause")

    def test_render_is_order_independent(self) -> None:
        a = audit_mod.render(audit_mod.parse("GPL-2.0-or-later OR (MPL-1.1 OR LGPL-2.1+)"))
        b = audit_mod.render(audit_mod.parse("MPL-1.1 OR LGPL-2.1-or-later OR GPL-2.0+"))
        self.assertEqual(a, b)
        self.assertEqual(a, "GPL-2.0-or-later OR LGPL-2.1-or-later OR MPL-1.1")

    def test_old_gnu_ids_and_with(self) -> None:
        self.assertEqual(audit_mod.normalize_id("GPL-2.0"), "GPL-2.0-only")
        self.assertEqual(audit_mod.normalize_id("lgpl-2.1+"), "LGPL-2.1-or-later")
        # ngoại lệ WITH chỉ thêm quyền: xét theo giấy phép gốc
        self.assertEqual(self.verdict("Apache-2.0 WITH LLVM-exception"), audit_mod.PASS)
        self.assertEqual(self.verdict("GPL-2.0-only WITH Classpath-exception-2.0"), audit_mod.FAIL)

    def test_weak_and_strong_copyleft(self) -> None:
        self.assertEqual(self.verdict("MPL-1.1"), audit_mod.WEAK)
        self.assertEqual(self.verdict("GPL-2.0-or-later OR LGPL-2.1-or-later OR MPL-1.1"), audit_mod.WEAK)
        level, why = audit_mod.judge(audit_mod.parse("AGPL-3.0-only"))
        self.assertEqual(level, audit_mod.FAIL)
        self.assertIn("dịch vụ độc lập", why)
        self.assertIn("ngoài danh sách", audit_mod.judge(audit_mod.parse("SSPL-1.0"))[1])

    def test_malformed_expressions_raise(self) -> None:
        for text in ("MIT OR", "(MIT", "MIT)", "AND MIT", "MIT WITH"):
            with self.subTest(text=text), self.assertRaises(audit_mod.FormatError):
                audit_mod.parse(text)


class SbomLicenseTest(unittest.TestCase):
    def test_entries_ids_expressions_and_free_text(self) -> None:
        self.assertEqual(audit_mod.sbom_license({"licenses": [spdx("MIT")]}), ("MIT", "MIT"))
        self.assertEqual(audit_mod.sbom_license({"licenses": [named("Apache License 2.0")]})[0], "Apache-2.0")
        # nhiều mục giấy phép trên một gói: mọi mục đều áp dụng
        self.assertEqual(audit_mod.sbom_license({"licenses": [spdx("MIT"), expr("BSD-3-Clause OR GPL-2.0")]})[0],
                         "(BSD-3-Clause OR GPL-2.0-only) AND MIT")

    def test_unclear_text_or_nothing_is_unknown(self) -> None:
        self.assertEqual(audit_mod.sbom_license({"licenses": [named("Dual License")]}), (None, "Dual License"))
        self.assertEqual(audit_mod.sbom_license({"licenses": [named("BSD License")]})[0], None)
        self.assertEqual(audit_mod.sbom_license({"licenses": [spdx("MIT"), named("Custom")]})[0], None)
        self.assertEqual(audit_mod.sbom_license({}), (None, ""))

    def test_package_key(self) -> None:
        self.assertEqual(audit_mod.package_key("pkg:pypi/Python_Dateutil@2.9.0.post0"), "pkg:pypi/python-dateutil")
        self.assertEqual(audit_mod.package_key("pkg:npm/%40speed-highlight/core@1.2.24"),
                         "pkg:npm/@speed-highlight/core")
        self.assertEqual(audit_mod.package_key("pkg:npm/@speed-highlight/core"), "pkg:npm/@speed-highlight/core")
        self.assertEqual(audit_mod.package_key("pkg:github/actions/checkout@v7.0.1?x=1"), "pkg:github/actions/checkout")


class AuditTest(unittest.TestCase):
    """Chạy main() trên SBOM và tệp ngoại lệ tạm, như CI chạy make license-audit."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name)

    def run_audit(self, document: dict, waivers: list[dict] | None = None, actions: bool = False) -> tuple[int, str]:
        (self.dir / "sbom.cdx.json").write_text(json.dumps(document), encoding="utf-8")
        (self.dir / "ngoai-le.json").write_text(json.dumps({"ngoai_le": waivers or []}), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS"} | ({"GITHUB_ACTIONS": "true"} if actions
                                                                               else {})
        with unittest.mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            code = audit_mod.main([str(self.dir / "sbom.cdx.json"), "--ngoai-le", str(self.dir / "ngoai-le.json")])
        return code, out.getvalue() + err.getvalue()

    def test_permissive_tree_passes_and_counts_each_package_once(self) -> None:
        code, out = self.run_audit(sbom(
            component("pkg:npm/vue@3.5.0", spdx("MIT")),
            component("pkg:npm/node-forge@1.4.0", expr("BSD-3-Clause OR GPL-2.0")),
            # cùng gói trong hai tệp khóa: Syft ghi hai mục
            component("pkg:pypi/httpx2@2.13.0", spdx("BSD-3-Clause"), where="/services/svc-files/requirements.txt"),
            component("pkg:pypi/httpx2@2.13.0", spdx("BSD-3-Clause"), where="/services/svc-workflow/requirements.txt"),
        ))
        self.assertEqual(code, 0, out)
        self.assertIn("SBOM moc 1.1.0", out)
        self.assertIn("3 gói khác nhau — npm 2, pypi 1", out)
        self.assertIn("Đạt: 3/3 gói", out)

    def test_unknown_and_gpl_fail_with_location(self) -> None:
        code, out = self.run_audit(sbom(
            component("pkg:npm/vue@3.5.0", spdx("MIT")),
            component("pkg:npm/gpl-lib@1.0.0", spdx("GPL-3.0-only")),
            component("pkg:pypi/weasyprint@70.0", where="/services/svc-files/requirements.txt"),
            component("pkg:pypi/python-dateutil@2.9.0.post0", named("Dual License")),
        ))
        self.assertEqual(code, 1)
        self.assertIn("KHÔNG ĐẠT: 3/4 gói", out)
        self.assertIn("pkg:npm/gpl-lib@1.0.0 (apps/office/package-lock.json): GPL-3.0-only là copyleft mạnh", out)
        self.assertIn("pkg:pypi/weasyprint@70.0 (services/svc-files/requirements.txt): chưa rõ giấy phép: SBOM không "
                      "ghi giấy phép; chưa có ngoại lệ", out)
        self.assertIn('SBOM ghi "Dual License", không phải mã SPDX', out)
        self.assertIn("make sbom hỏi PyPI", out)
        self.assertIn("Cách sửa:", out)

    def test_actions_get_error_annotations(self) -> None:
        code, out = self.run_audit(sbom(component("pkg:npm/x@1.0.0", spdx("SSPL-1.0"))), actions=True)
        self.assertEqual(code, 1)
        self.assertIn("::error::Giấy phép không đạt: pkg:npm/x@1.0.0: SSPL-1.0 ngoài danh sách", out)

    def test_weak_copyleft_passes_but_is_listed(self) -> None:
        code, out = self.run_audit(sbom(component("pkg:pypi/pyphen@0.18.1", expr("GPL-2.0+ OR LGPL-2.1+ OR MPL-1.1"))))
        self.assertEqual(code, 0, out)
        self.assertIn("Copyleft yếu, chỉ nhận khi dùng nguyên bản (DEPENDENCIES.md): 1 gói", out)

    def test_policy_waiver_must_match_the_sbom_license(self) -> None:
        waiver = {"goi": "pkg:npm/caniuse-lite", "giay_phep": "CC-BY-4.0", "ly_do": "dữ liệu, chỉ dùng lúc dựng"}
        code, out = self.run_audit(sbom(component("pkg:npm/caniuse-lite@1.0.1", spdx("CC-BY-4.0"))), [waiver])
        self.assertEqual(code, 0, out)
        self.assertIn("Qua nhờ ngoại lệ có lý do", out)
        # gói đổi giấy phép: ngoại lệ cũ không còn che
        code, out = self.run_audit(sbom(component("pkg:npm/caniuse-lite@1.0.2", spdx("CC-BY-SA-4.0"))), [waiver])
        self.assertEqual(code, 1)
        self.assertIn("ngoại lệ ghi CC-BY-4.0 nhưng SBOM ghi CC-BY-SA-4.0", out)

    def test_declared_license_needs_the_version_that_was_read(self) -> None:
        pinned = {"goi": "pkg:pypi/WeasyPrint", "phien_ban": "70.0", "giay_phep": "BSD-3-Clause",
                  "ly_do": "LICENSE trong wheel là BSD ba điều khoản"}
        code, out = self.run_audit(sbom(component("pkg:pypi/weasyprint@70.0")), [pinned])
        self.assertEqual(code, 0, out)
        self.assertIn("pkg:pypi/weasyprint@70.0  BSD-3-Clause  (khai tay: SBOM không rõ giấy phép)", out)
        code, out = self.run_audit(sbom(component("pkg:pypi/weasyprint@71.0")), [pinned])
        self.assertEqual(code, 1)
        self.assertIn("ngoại lệ chỉ cho bản 70.0 — đọc giấy phép của bản 71.0 rồi sửa", out)
        self.assertIn("ngoại lệ pkg:pypi/weasyprint@70.0 không còn gói nào cần tới", out)
        unpinned = {k: v for k, v in pinned.items() if k != "phien_ban"}
        code, out = self.run_audit(sbom(component("pkg:pypi/weasyprint@70.0")), [unpinned])
        self.assertEqual(code, 1)
        self.assertIn('phải ghi "phien_ban"', out)

    def test_unneeded_waiver_only_warns(self) -> None:
        waiver = {"goi": "pkg:npm/vue", "giay_phep": "MIT", "ly_do": "thừa"}
        code, out = self.run_audit(sbom(component("pkg:npm/vue@3.5.0", spdx("MIT"))), [waiver])
        self.assertEqual(code, 0, out)
        self.assertIn("Cảnh báo: ngoại lệ pkg:npm/vue không còn gói nào cần tới", out)
        code, out = self.run_audit(sbom(component("pkg:npm/vue@3.5.0", spdx("MIT"))), [waiver], actions=True)
        self.assertIn("::warning::ngoại lệ pkg:npm/vue không còn gói nào cần tới", out)

    def test_bad_waivers_and_bad_sbom_exit_2(self) -> None:
        good = sbom(component("pkg:npm/vue@3.5.0", spdx("MIT")))
        for waiver, message in (
            ({"goi": "pkg:npm/x", "giay_phep": "MIT", "ly_do": " "}, 'thiếu "ly_do"'),
            ({"goi": "pkg:npm/x@1.0.0", "giay_phep": "MIT", "ly_do": "a"}, "purl không kèm phiên bản"),
            ({"goi": "pkg:npm/x", "giay_phep": "MIT OR", "ly_do": "a"}, "biểu thức giấy phép dở dang"),
            ({"goi": "pkg:npm/x", "giay_phep": "MIT", "ly_do": "a", "phien_ban": []}, '"phien_ban"'),
            ({"goi": "pkg:npm/x", "giay_phep": "MIT", "ly_do": "a", "het_han": "x"}, "khóa lạ"),
        ):
            with self.subTest(message=message):
                code, out = self.run_audit(good, [waiver])
                self.assertEqual(code, 2)
                self.assertIn(message, out)
        code, out = self.run_audit({"spdxVersion": "SPDX-2.3"})
        self.assertEqual(code, 2)
        self.assertIn("không phải SBOM CycloneDX", out)


class RepoWaiversTest(unittest.TestCase):
    """.github/license-exceptions.json của repo: đọc được, mỗi mục có lý do, gói khai tay có phiên bản."""

    def test_repo_file_loads_and_every_entry_has_a_reason(self) -> None:
        waivers = audit_mod.load_waivers(audit_mod.WAIVERS)
        self.assertGreater(len(waivers), 0)
        data = json.loads(audit_mod.WAIVERS.read_text(encoding="utf-8"))["ngoai_le"]
        keys = [w["goi"] + "@" + str(w.get("phien_ban")) for w in data]
        self.assertEqual(len(keys), len(set(keys)), "ngoại lệ trùng")
        for waiver in waivers:
            self.assertGreaterEqual(len(waiver.reason), 20, waiver.package)
        # giấy phép nằm sẵn trong danh sách được nhận thì chỉ cần ngoại lệ khi SBOM không rõ: phải ghi phiên bản
        for item in data:
            level, _ = audit_mod.judge(audit_mod.parse(item["giay_phep"]))
            if level != audit_mod.FAIL:
                self.assertIn("phien_ban", item, item["goi"])


class SyftPinTest(unittest.TestCase):
    """Image Syft ghim theo thẻ + digest, cùng một giá trị ở Makefile (make sbom) và ci.yml (job Giấy phép)."""

    PIN = re.compile(r"SYFT_IMAGE \??[:=] ?(\S+)")

    def test_same_digest_in_makefile_and_ci(self) -> None:
        makefile = self.PIN.findall((ROOT / "Makefile").read_text(encoding="utf-8"))
        ci = re.findall(r"^  SYFT_IMAGE: (\S+)$", (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"),
                        re.M)
        self.assertEqual(len(makefile), 1)
        self.assertEqual(makefile, ci)
        self.assertRegex(makefile[0], r"^ghcr\.io/anchore/syft:v\d+\.\d+\.\d+@sha256:[0-9a-f]{64}$")

    def test_ci_license_job_runs_sbom_then_audit(self) -> None:
        text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job = text.split("\n  license:\n", 1)[1].split("\n  build:\n", 1)[0]
        self.assertLess(job.index("run: make sbom\n"), job.index("run: make license-audit\n"))

    @unittest.skipUnless(shutil.which("make") and shutil.which("git"), "cần GNU Make, git")
    def test_make_sbom_reads_the_tree_read_only(self) -> None:
        # make -n chỉ in lệnh, không gọi Docker
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(ROOT / "Makefile", tmp)
            proc = subprocess.run(["make", "-n", "-s", "sbom", "license-audit", "VERSION=1.1.0"], cwd=tmp,
                                  capture_output=True, text=True, env={**os.environ, "MAKEFLAGS": ""})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout
        self.assertIn(f'-v "{tmp}:/src:ro"', out)
        self.assertIn("scan dir:/src --enrich python --source-name moc", out)
        self.assertIn('--source-version "1.1.0"', out)
        self.assertIn("SYFT_JAVASCRIPT_INCLUDE_DEV_DEPENDENCIES=true", out)
        self.assertIn("SYFT_CHECK_FOR_APP_UPDATE=false", out)
        for excluded in ("node_modules", ".venv", "dist", ".git"):
            self.assertRegex(out, rf"--exclude '\./(\*\*/)?{re.escape(excluded)}/\*\*'")
        self.assertIn("> dist/moc-1.1.0.cdx.json.tmp", out)
        self.assertIn("sha256sum moc-1.1.0.cdx.json > moc-1.1.0.cdx.json.sha256", out)
        self.assertIn("python3 scripts/license_audit.py dist/moc-1.1.0.cdx.json", out)


if __name__ == "__main__":
    unittest.main()
