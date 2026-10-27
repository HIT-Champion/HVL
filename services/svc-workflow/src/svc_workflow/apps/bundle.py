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

"""Gói quy trình của một ứng dụng: zip do ``moc app install`` dựng từ mục ``workflow`` của manifest.

Trong zip: ``moc-workflow.json`` (``{"app", "processes": [đường BPMN], "forms": {formKey: đường JSON}}``) và đúng
các tệp nó kể, ở đường tương đối với thư mục ứng dụng. Kiểm hết (bpmn.py, forms.py) rồi dựng lại thành tài nguyên
của MỘT deployment Flowable, tên cố định theo khóa: ``<processKey>.bpmn20.xml``, ``<formKey>.json`` và ``moc-app.json``
(mục lục: form bắt đầu của từng quy trình, các form). API lúc chạy đọc form, mục lục từ đúng deployment của định nghĩa
quy trình — không cần thư mục gắn vào container hay bảng mới. Tên deployment ``app/<tên>@<12 ký tự băm nội dung>``.
"""

from __future__ import annotations

import hashlib
import io
import json
import posixpath
import zipfile
from dataclasses import dataclass, field
from typing import Any

from . import bpmn
from .forms import AppForm, check_form

MANIFEST = "moc-workflow.json"
INDEX = "moc-app.json"
MAX_ENTRIES = 64
MAX_TOTAL_BYTES = 8 * 1024 * 1024
FORMAT = 1


def deployment_prefix(app: str) -> str:
    return f"app/{app}@"


def process_resource(key: str) -> str:
    return f"{key}.bpmn20.xml"


def form_resource(form_key: str) -> str:
    return f"{form_key}.json"


class BundleError(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class Bundle:
    app: str
    processes: dict[str, bpmn.Process]
    forms: dict[str, AppForm]
    resources: dict[str, bytes] = field(default_factory=dict)

    @property
    def index(self) -> dict[str, Any]:
        processes = {k: {"startForm": p.start_form, "name": p.name} for k, p in sorted(self.processes.items())}
        return {"format": FORMAT, "app": self.app, "processes": processes, "forms": sorted(self.forms)}

    @property
    def digest(self) -> str:
        h = hashlib.sha256()
        for name in sorted(self.resources):
            data = self.resources[name]
            h.update(f"{name}\0{len(data)}\0".encode())
            h.update(data)
        return h.hexdigest()

    @property
    def name(self) -> str:
        return f"{deployment_prefix(self.app)}{self.digest[:12]}"

    def zip(self) -> bytes:
        """Zip dựng lại được y hệt (thứ tự, mốc thời gian cố định): cùng nội dung thì cùng byte."""
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in sorted(self.resources):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, self.resources[name])
        return out.getvalue()


def _safe(name: str) -> bool:
    return (bool(name) and not name.startswith("/") and "\\" not in name and "\0" not in name
            and posixpath.normpath(name) == name and not name.startswith(".."))


def _read(data: bytes) -> dict[str, bytes]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, ValueError) as exc:
        raise BundleError([f"gói quy trình không phải zip ({exc})"]) from None
    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > MAX_ENTRIES:
        raise BundleError([f"gói quy trình có {len(infos)} tệp, tối đa {MAX_ENTRIES}"])
    files: dict[str, bytes] = {}
    total = 0
    for info in infos:
        if not _safe(info.filename):
            raise BundleError([f"tên tệp {info.filename!r} trong gói không hợp lệ"])
        with zf.open(info) as f:                 # đọc có trần: không tin kích thước khai trong zip
            content = f.read(MAX_TOTAL_BYTES - total + 1)
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            raise BundleError([f"gói quy trình lớn quá {MAX_TOTAL_BYTES // 1024 // 1024} MB"])
        files[info.filename] = content
    return files


def check_bundle(app: str, data: bytes) -> Bundle:
    """zip → Bundle đã kiểm; sai thì BundleError liệt kê mọi lỗi tìm được."""
    if not bpmn.NAME.fullmatch(app):
        raise BundleError([f"tên ứng dụng {app!r} không hợp lệ"])
    files = _read(data)
    try:
        manifest = json.loads(files.pop(MANIFEST).decode("utf-8"))
    except KeyError:
        raise BundleError([f"gói thiếu {MANIFEST}"]) from None
    except (UnicodeDecodeError, ValueError) as exc:
        raise BundleError([f"{MANIFEST} không đọc được ({exc})"]) from None
    if not isinstance(manifest, dict) or manifest.get("app") != app:
        raise BundleError([f"{MANIFEST}: app phải là {app}"])
    paths, form_paths = manifest.get("processes"), manifest.get("forms")
    if not (isinstance(paths, list) and paths and all(isinstance(p, str) for p in paths)):
        raise BundleError(["workflow.processes: cần danh sách tệp *.bpmn20.xml"])
    if not (isinstance(form_paths, dict) and all(isinstance(p, str) for p in form_paths.values())):
        raise BundleError(["workflow.forms: cần ánh xạ formKey → tệp .json"])

    errors: list[str] = []
    key = bpmn.key_pattern(app)
    forms: dict[str, AppForm] = {}
    resources: dict[str, bytes] = {}
    for form_key, path in sorted(form_paths.items()):
        where = f"workflow.forms.{form_key} ({path})"
        if not key.fullmatch(form_key):
            errors.append(f"{where}: formKey phải dạng {app}.<tên> (chữ thường, số, gạch nối)")
            continue
        if path not in files:
            errors.append(f"{where}: không có tệp trong gói")
            continue
        form, problems = check_form(where, files[path])
        errors += problems
        if form is not None:
            forms[form_key] = form
            resources[form_resource(form_key)] = files[path]
    fields = {f for form in forms.values() for f in form.fields}
    required = {f for form in forms.values() for f in form.required}
    processes: dict[str, bpmn.Process] = {}
    for path in paths:
        if path not in files:
            errors.append(f"workflow.processes: {path} không có trong gói")
            continue
        if not path.endswith(".bpmn20.xml"):
            errors.append(f"workflow.processes: {path} phải có đuôi .bpmn20.xml")
            continue
        # chưa kiểm được form nào thì vẫn kiểm BPMN theo tên khai, để một lần chạy báo đủ lỗi
        proc, problems = bpmn.check(app, path, files[path], set(form_paths), fields)
        errors += problems
        if proc is None:
            continue
        if proc.key in processes:
            errors.append(f"{path}: process id {proc.key} trùng với một tệp khác")
            continue
        loose = sorted(proc.condition_variables - required)
        if loose:
            errors.append(f"{path}: biến {', '.join(loose)} dùng trong điều kiện rẽ nhánh phải là trường bắt buộc "
                          "(required) của form — thiếu biến thì Flowable dừng ở cổng")
        processes[proc.key] = proc
        resources[process_resource(proc.key)] = files[path]
    stray = sorted(set(files) - set(paths) - set(form_paths.values()))
    if stray:
        errors.append(f"gói có tệp không khai trong workflow: {', '.join(stray)}")
    if errors:
        raise BundleError(errors)
    bundle = Bundle(app, processes, forms, resources)
    bundle.resources[INDEX] = (json.dumps(bundle.index, ensure_ascii=False, sort_keys=True) + "\n").encode()
    return bundle


def make_zip(app: str, processes: dict[str, bytes], forms: dict[str, tuple[str, bytes]]) -> bytes:
    """Gói như ``moc app install`` dựng (dùng cho test và chạy tay): processes {đường: nội dung}, forms {formKey:
    (đường, nội dung)}."""
    manifest = {"app": app, "processes": sorted(processes), "forms": {k: p for k, (p, _) in sorted(forms.items())}}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, sort_keys=True))
        for path, content in sorted(processes.items()):
            zf.writestr(path, content)
        for path, content in sorted(dict(forms.values()).items()):
            zf.writestr(path, content)
    return out.getvalue()
