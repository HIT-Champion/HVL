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


"""Văn phòng điện tử tắt (MOC_OFFICE_ENABLED=false) thì svc-files không nạp mô-đun nào của Văn phòng, cả lúc import
svc_files.app lẫn lúc create_app (#489, docs/architecture.md §4.7). Chạy trong tiến trình riêng: các test khác đã nạp
Văn phòng vào tiến trình pytest. Nhóm của mô-đun lấy từ scripts/ranh_gioi_loi.py, một bảng cho cả repo."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

SERVICE = pathlib.Path(__file__).resolve().parents[1]
ROOT = SERVICE.parents[1]
PKG = "svc_files"
# Không có kết nối nào: create_app chỉ dựng máy khách, vòng nền chỉ chạy khi app khởi động (ở đây không khởi động)
OFF = {
    "MOC_OIDC_ISSUER": "http://keycloak/realms/moc", "MOC_OIDC_JWKS_URL": "http://unused/jwks",
    "SEAWEEDFS_S3_ACCESS_KEY": "test", "SEAWEEDFS_S3_SECRET_KEY": "test", "HASURA_ADMIN_SECRET": "test",
    "MEILISEARCH_API_KEY": "test", "MOC_SEARCH_SYNC_INTERVAL_S": "0", "MOC_ASK_ENABLED": "false",
    "MOC_ASK_SYNC_INTERVAL_S": "0", "MOC_AUDIT_ANCHOR_INTERVAL_S": "0", "MOC_TEXT_INTERVAL_S": "0", "MOC_AI_URL": "",
    "MOC_IMPORT_INTERVAL_S": "0", "MOC_OFFICE_ENABLED": "false",
}
CHILD = r'''
import importlib, importlib.util, json, pathlib, sys
root, pkg, env = pathlib.Path(sys.argv[1]), sys.argv[2], json.loads(sys.argv[3])
spec = importlib.util.spec_from_file_location("ranh_gioi_loi", root / "scripts" / "ranh_gioi_loi.py")
rg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rg)


def office_loaded():
    def group(name):
        rel = name.replace(".", "/")
        return rg.nhom_cua(rel + ".py") or rg.nhom_cua(rel + "/__init__.py") or rg.THU_MUC.get(rel + "/")
    return sorted(m for m in sys.modules if m.startswith(pkg + ".") and group(m) == rg.VP)


app = importlib.import_module(pkg + ".app")
config = importlib.import_module(pkg + ".config")
seen = {"import": office_loaded()}
app.create_app(config.Settings.from_env(env))
seen["create_app"] = office_loaded()
importlib.import_module(pkg + ".office.api")
seen["control"] = office_loaded()
print(json.dumps(seen))
'''


def test_office_off_loads_no_office_module() -> None:
    env = {**os.environ, "PYTHONPATH": str(SERVICE / "src")}
    done = subprocess.run([sys.executable, "-c", CHILD, str(ROOT), PKG, json.dumps(OFF)], cwd=SERVICE, env=env,
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
    seen = json.loads(done.stdout.strip().splitlines()[-1])
    assert seen["import"] == [], "import svc_files.app nạp mô-đun Văn phòng ở đầu tệp"
    assert seen["create_app"] == [], "create_app nạp mô-đun Văn phòng khi MOC_OFFICE_ENABLED=false"
    # đối chứng: bảng nhóm vẫn nhận ra mô-đun Văn phòng, nên hai danh sách rỗng ở trên không phải vì bảng hỏng
    assert f"{PKG}.office.api" in seen["control"]
