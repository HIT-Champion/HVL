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

"""Tài liệu trỏ bằng chứng vào CI phải trỏ đúng chỗ (#271). Khi phần chạy thử tách thành sáu phần của job `chay-thu`,
job `stack` chỉ còn bước gom kết quả, nhưng tài liệu hội đồng vẫn ghi "CI job `stack`, bước …". Test đọc mọi tệp .md
và kiểm:
  * job `x` (x dạng id: chữ thường, gạch nối) là job có thật trong một workflow của .github/workflows/;
  * job "Tên" là tên job hiện trên trang Actions, hoặc phần đầu của tên tới trước " (";
  * phần `x` (dòng đó hay dòng trước có nhắc CI, `chay-thu`) là một phần của ma trận; "phần `x` của job …" thì job đó
    đúng là job chạy ma trận;
  * job `J`[, phần `P`], bước "S" [và "S2"]: S là bước của job J, chạy ở phần P. Viết tắt tên bước tới trước " — "
    hay " (" vẫn được.
Bỏ qua CHANGELOG và ghi chép nghiên cứu có ngày (docs/du-thi/nghien-cuu/): chúng ghi lại điều đúng ở lúc viết.
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import os
import pathlib
import re
import unittest
from typing import NamedTuple

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
SKIP_DIRS = {".git", "node_modules", ".nuxt", ".output", "dist", "build", ".venv", "venv", "__pycache__",
             ".pytest_cache", "test-results", "playwright-report"}
HISTORY = ("CHANGELOG.md", "docs/du-thi/nghien-cuu/")

ID = r"[a-z0-9]+(?:-[a-z0-9]+)*"                  # id job, tên phần; không bắt tên job OpenLineage `moc.case_file.…`
JOB = re.compile(rf"\bjob\s+`({ID})`", re.I)
JOB_NAME = re.compile(r'\bjob\s+"([^"]+)"', re.I)
PART = re.compile(rf"phần\s+`({ID})`")
PART_OF = re.compile(rf'phần\s+`({ID})`\s+của\s+job\s+(?:`({ID})`|"([^"]+)")')
STEP = re.compile(rf'\bjob\s+`({ID})`(?:,?\s+phần\s+`({ID})`)?,?\s+bước\s+"([^"]+)"'
                  rf'(?:\s+và\s+(?:phần\s+`({ID})`,?\s+bước\s+)?"([^"]+)")?', re.I)
MENTIONS_CI = re.compile(r"\bCI\b|`chay-thu`")


class Workflows(NamedTuple):
    steps: dict[str, dict[str, set[str] | None]]     # job → bước → các phần chạy bước đó (None: mọi phần)
    names: dict[str, str]                             # tên hiện trên trang Actions → job
    parts: dict[str, str]                             # phần của ma trận `phan` → job chạy ma trận đó


def workflows() -> Workflows:
    """Đọc .github/workflows/*.yml theo thụt lề như test_quy_trinh.py, không cần thư viện YAML: job thụt 2 dưới jobs:,
    name của job thụt 4, bước "- name:" thụt 6, if của bước thụt 8."""
    ci = Workflows({}, {}, {})
    for path in sorted(WORKFLOWS.glob("*.yml")):
        job = step = ""
        title = {}                                    # job → name chưa thay ${{ matrix.phan }}
        in_jobs = False
        for line in path.read_text(encoding="utf-8").split("\n"):
            if re.match(r"^jobs:\s*$", line):
                in_jobs = True
            elif in_jobs and (m := re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)):
                job, step = m.group(1), ""
                ci.steps.setdefault(job, {})
            elif job and (m := re.match(r"^    name: (.+)$", line)):
                title[job] = m.group(1).strip().strip('"')
            elif job and (m := re.match(r"^        phan: \[(.*)\]\s*$", line)):
                ci.parts.update({p.strip(): job for p in m.group(1).split(",")})
            elif job and (m := re.match(r"^      - name: (.+)$", line)):
                step = m.group(1).strip().strip('"')
                ci.steps[job][step] = None
            elif step and (m := re.match(r"^        if: (.+)$", line)):
                ci.steps[job][step] = set(re.findall(r"matrix\.phan == '([^']*)'", m.group(1))) or None
            elif re.match(r"^      - ", line):
                step = ""                             # bước không tên (uses:): if của nó không thuộc bước trước
        for job, name in title.items():
            own = [p for p, j in ci.parts.items() if j == job]
            for expanded in ([name.replace("${{ matrix.phan }}", p) for p in own] if "${{" in name else [name]):
                ci.names[expanded] = job
    return ci


def docs() -> list[tuple[str, str]]:
    """(đường dẫn từ gốc repo, nội dung) của mọi tệp .md, trừ tệp ghi lịch sử."""
    out = []
    for folder, dirs, files in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            rel = pathlib.Path(folder, name).relative_to(ROOT).as_posix()
            if name.endswith(".md") and not rel.startswith(HISTORY):
                out.append((rel, pathlib.Path(folder, name).read_text(encoding="utf-8")))
    return out


def matches(cited: str, name: str, seps: tuple[str, ...]) -> bool:
    """Tên trong tài liệu (gộp khoảng trắng) là tên thật, hoặc phần đầu của tên thật tới trước một dấu tách."""
    cited = " ".join(cited.split())
    return cited == name or any(name.startswith(cited + sep) for sep in seps)


def problems(text: str, ci: Workflows) -> list[tuple[int, str]]:
    """Các chỗ trỏ sai trong một tài liệu: (số dòng, lời báo)."""
    found = []
    line_of = lambda at: text.count("\n", 0, at) + 1         # noqa: E731
    for m in JOB.finditer(text):
        if m.group(1) not in ci.steps:
            found.append((line_of(m.start()), f"job `{m.group(1)}` không có trong .github/workflows/"))
    for m in JOB_NAME.finditer(text):
        if not any(matches(m.group(1), name, (" (",)) for name in ci.names):
            found.append((line_of(m.start()), f'không job nào tên "{" ".join(m.group(1).split())}"'))
    lines = text.split("\n")
    for m in PART.finditer(text):                     # "phần" cuối dòng, tên phần ở đầu dòng sau vẫn bắt được
        no = line_of(m.start())
        if m.group(1) not in ci.parts and MENTIONS_CI.search(lines[no - 1] + " " + (lines[no - 2] if no > 1 else "")):
            found.append((no, f"phần `{m.group(1)}` không có trong ma trận chạy thử ({', '.join(sorted(ci.parts))})"))
    for m in PART_OF.finditer(text):
        part, job, name = m.groups()
        owner = job or next((j for n, j in ci.names.items() if matches(name, n, (" (",))), None)
        if part in ci.parts and owner and owner != ci.parts[part]:
            found.append((line_of(m.start()), f"phần `{part}` thuộc job `{ci.parts[part]}`, không phải `{owner}`"))
    for m in STEP.finditer(text):
        job, part, first, part2, second = m.groups()
        if job not in ci.steps:
            continue                                  # đã báo ở JOB
        for part, name in ((part, first), (part2 or part, second)):
            if not name:
                continue
            name = " ".join(name.split())
            real = [s for s in ci.steps[job] if matches(name, s, (" — ", " ("))]
            if not real:
                found.append((line_of(m.start()), f'job `{job}` không có bước "{name}"'))
            elif part and not any(ci.steps[job][s] is None or part in ci.steps[job][s] for s in real):
                found.append((line_of(m.start()), f'bước "{name}" của job `{job}` không chạy ở phần `{part}`'))
    return found


class WorkflowsTest(unittest.TestCase):
    def test_reads_jobs_names_steps_and_parts(self) -> None:
        ci = workflows()
        # job của ci.yml và của các workflow khác (pr.yml, release.yml, ban-online.yml, nang-cap.yml)
        for job in ("build", "chay-thu", "stack", "unit", "db", "docs", "license", "security", "flow", "release",
                    "kiem", "nang-cap"):
            self.assertIn(job, ci.steps)
        self.assertEqual(set(ci.parts), {"luong-chinh", "e2e", "ai", "sao-luu", "cai-dat", "https"})
        self.assertEqual(set(ci.parts.values()), {"chay-thu"})
        self.assertEqual(ci.names["Chạy thử: ai"], "chay-thu")
        self.assertEqual(ci.names["Chạy thử toàn hệ thống (PoF #4)"], "stack")
        self.assertEqual(ci.names["Quy trình nhánh và tiêu đề PR"], "flow")
        self.assertEqual(ci.steps["chay-thu"]["Đo chất lượng hỏi đáp (make do-hoi-dap)"], {"ai"})
        self.assertEqual(len(ci.steps["stack"]), 1)                # job stack chỉ gom kết quả của sáu phần


class ProblemsTest(unittest.TestCase):
    """problems() trên đoạn tài liệu viết tay: bắt đúng chỗ sai, không bắt chỗ đúng."""

    ci = Workflows(
        steps={"chay-thu": {"Đo chất lượng hỏi đáp (make do-hoi-dap)": {"ai"}, "Giám sát — luật cảnh báo": None},
               "stack": {"Cả sáu phần chạy thử đều đạt": None}},
        names={"Chạy thử: ai": "chay-thu", "Chạy thử: e2e": "chay-thu", "Chạy thử toàn hệ thống (PoF #4)": "stack"},
        parts={"ai": "chay-thu", "e2e": "chay-thu"},
    )

    def check(self, text: str) -> list[str]:
        return [msg for _, msg in problems(text, self.ci)]

    def test_correct_citations_pass(self) -> None:
        self.assertEqual(self.check('CI job `chay-thu`, phần `ai`, bước "Đo chất lượng hỏi đáp (make do-hoi-dap)"'), [])
        self.assertEqual(self.check('job `chay-thu`, bước "Đo chất lượng hỏi đáp" và\n"Giám sát"'), [])
        self.assertEqual(self.check('Job "Chạy thử toàn hệ thống" gom các phần; CI (phần `ai` của job "Chạy thử: ai")'),
                         [])

    def test_step_cited_under_the_wrong_job_or_part(self) -> None:
        wrong = ['bước "Đo chất lượng hỏi đáp" của job `chay-thu` không chạy ở phần `e2e`']
        self.assertEqual(self.check('CI job `stack`, bước "Đo chất lượng hỏi đáp (make do-hoi-dap)"'),
                         ['job `stack` không có bước "Đo chất lượng hỏi đáp (make do-hoi-dap)"'])
        self.assertEqual(self.check('job `chay-thu`, phần `e2e`, bước "Đo chất lượng\n  hỏi đáp"'), wrong)
        # bước thứ hai sau "và phần …" xét theo phần của chính nó
        two = 'job `chay-thu`, phần `e2e`, bước "Giám sát" và phần `{}`, bước "Đo chất lượng hỏi đáp"'
        self.assertEqual(self.check(two.format("e2e")), wrong)
        self.assertEqual(self.check(two.format("ai")), [])

    def test_part_cited_under_the_wrong_job(self) -> None:
        self.assertEqual(self.check('CI chạy lệnh này\n(phần `ai` của job "Chạy thử toàn hệ thống")'),
                         ["phần `ai` thuộc job `chay-thu`, không phải `stack`"])

    def test_unknown_job_name_and_part(self) -> None:
        self.assertEqual(self.check("bước CI của job `luong-chinh`"),
                         ["job `luong-chinh` không có trong .github/workflows/"])
        self.assertEqual(self.check('job "Chạy thử tích hợp"'), ['không job nào tên "Chạy thử tích hợp"'])
        self.assertEqual(self.check("CI chạy lệnh này\n(phần `sao-luu` của job `chay-thu`)"),
                         ["phần `sao-luu` không có trong ma trận chạy thử (ai, e2e)"])
        self.assertEqual(self.check("CI job `chay-thu`, phần\n`sao-luu`, bước"),
                         ["phần `sao-luu` không có trong ma trận chạy thử (ai, e2e)"])

    def test_names_that_only_look_like_ci_are_skipped(self) -> None:
        self.assertEqual(self.check("tên job `moc.case_file.archive` của OpenLineage"), [])
        self.assertEqual(self.check("nginx cắt dòng nhật ký: mất phần `request-id`"), [])


class DocsTest(unittest.TestCase):
    def test_docs_cite_real_jobs_parts_and_steps(self) -> None:
        ci = workflows()
        found, cited = [], 0
        for rel, text in docs():
            cited += len(JOB.findall(text)) + len(JOB_NAME.findall(text))
            found += [f"{rel}:{no}: {msg}" for no, msg in problems(text, ci)]
        self.assertEqual(found, [])
        # cận dưới: bộ đọc tài liệu hỏng (không thấy tệp, regex sai) thì đỏ thay vì qua mà không kiểm gì
        self.assertGreaterEqual(cited, 20, f"chỉ thấy {cited} chỗ nhắc job")


if __name__ == "__main__":
    unittest.main()
