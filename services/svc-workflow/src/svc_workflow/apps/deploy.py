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

"""Triển khai quy trình của một ứng dụng lên Flowable của lõi — ``moc app install | remove`` gọi trong container:

    docker compose exec -T svc-workflow python -m svc_workflow.apps.deploy check|install <tên>  < gói (zip, base64)
    docker compose exec -T svc-workflow python -m svc_workflow.apps.deploy remove <tên>

- ``check``: kiểm gói (bundle.py), cho biết đã triển khai đúng bản này chưa; không đổi gì (``--dry-run``);
- ``install``: kiểm gói, rồi triển khai thành MỘT deployment nếu deployment mới nhất của ứng dụng không phải đúng bản
  này (cài lại không đổi thì bỏ qua; cài lại bản cũ sau bản mới thì bản cũ thành mới nhất); bật lại định nghĩa đã tạm
  dừng (ứng dụng từng bị gỡ: đơn đang dở chạy tiếp);
- ``remove``: tạm dừng (suspend) mọi định nghĩa quy trình của ứng dụng cùng các phiên đang chạy — không bắt đầu được
  đơn mới, việc đang mở không làm tiếp được; lịch sử, biến, đơn đang dở giữ nguyên trong Flowable (gỡ không xóa dữ
  liệu, như schema CSDL của ứng dụng).

Thông tin đăng nhập Flowable lấy đúng như lúc dịch vụ khởi động: ``Settings.from_env(with_secrets(os.environ))`` —
mật khẩu rest-admin trong két OpenBao (AppRole của svc-workflow, tệp role_id/secret_id gắn ở /run/openbao), không
đi qua dòng lệnh hay biến môi trường của người chạy.

Giao tiếp với ``scripts/ung_dung.py``: in đúng một dòng JSON ra stdout. Thoát 0 kèm ``{"ok": true, …}`` hoặc
``{"ok": false, "errors": [...]}`` (gói bị từ chối — lỗi viết cho người cài đọc); thoát 2 khi không gọi được két
hoặc Flowable (lý do ra stderr).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import json
import os
import sys
from typing import Any

from ..config import ConfigError, Settings
from ..flowable import FlowableClient, FlowableError
from ..openbao import with_secrets
from .bpmn import NAME
from .bundle import Bundle, BundleError, check_bundle, deployment_prefix

ACTIONS = ("check", "install", "remove")


def summary(bundle: Bundle) -> dict[str, Any]:
    return {"deployment": bundle.name, "processes": sorted(bundle.processes), "forms": sorted(bundle.forms)}


async def latest(flowable: FlowableClient, app: str) -> dict[str, Any] | None:
    rows = await flowable.deployments(f"{deployment_prefix(app)}%", size=1)
    return next((r for r in rows if str(r.get("name", "")).startswith(deployment_prefix(app))), None)


async def app_definitions(flowable: FlowableClient, app: str, *, suspended: bool) -> list[dict[str, Any]]:
    rows = await flowable.definitions(keyLike=f"{app}.%", suspended=str(suspended).lower())
    # LIKE của CSDL: lọc lại đúng tiền tố, đúng trạng thái
    return [r for r in rows if str(r.get("key", "")).startswith(f"{app}.") and bool(r.get("suspended")) == suspended]


async def check(flowable: FlowableClient | None, bundle: Bundle) -> dict[str, Any]:
    current: bool | None = None
    if flowable is not None:
        try:
            row = await latest(flowable, bundle.app)
            current = bool(row and row.get("name") == bundle.name)
        except FlowableError:
            current = None
    return {"ok": True, **summary(bundle), "current": current}


async def install(flowable: FlowableClient, bundle: Bundle) -> dict[str, Any]:
    row = await latest(flowable, bundle.app)
    deployed = not (row and row.get("name") == bundle.name)
    if deployed:
        await flowable.deploy_zip(bundle.name, f"{bundle.app}.zip", bundle.zip())
    activated = 0
    for d in await app_definitions(flowable, bundle.app, suspended=True):
        await flowable.set_definition_state(d["id"], "activate")
        activated += 1
    return {"ok": True, **summary(bundle), "deployed": deployed, "activated": activated}


async def remove(flowable: FlowableClient, app: str) -> dict[str, Any]:
    suspended = 0
    for d in await app_definitions(flowable, app, suspended=False):
        await flowable.set_definition_state(d["id"], "suspend")
        suspended += 1
    return {"ok": True, "suspended": suspended}


def _client() -> FlowableClient:
    settings = Settings.from_env(with_secrets(os.environ))
    return FlowableClient(settings.flowable_url, settings.flowable_user, settings.flowable_password)


async def run(action: str, app: str, bundle: Bundle | None, client: FlowableClient | None) -> dict[str, Any]:
    if client is None:
        assert action == "check" and bundle is not None
        return await check(None, bundle)
    try:
        if action == "check":
            assert bundle is not None
            return await check(client, bundle)
        if action == "install":
            assert bundle is not None
            return await install(client, bundle)
        return await remove(client, app)
    finally:
        await client.aclose()


def main(argv: list[str] | None = None, *, stdin: Any = None, client: Any = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m svc_workflow.apps.deploy",
                                     description="Triển khai quy trình của ứng dụng lên Flowable của lõi")
    parser.add_argument("action", choices=ACTIONS)
    parser.add_argument("name", help="tên ứng dụng (name của manifest)")
    args = parser.parse_args(argv)
    if not NAME.fullmatch(args.name):
        print(json.dumps({"ok": False, "errors": [f"tên ứng dụng {args.name!r} không hợp lệ"]}, ensure_ascii=False))
        return 0
    bundle = None
    if args.action != "remove":
        try:
            data = base64.b64decode((stdin or sys.stdin).read().strip(), validate=True)
            bundle = check_bundle(args.name, data)
        except (binascii.Error, ValueError):
            print(json.dumps({"ok": False, "errors": ["stdin phải là gói zip mã hóa base64"]}, ensure_ascii=False))
            return 0
        except BundleError as exc:
            print(json.dumps({"ok": False, "errors": exc.errors}, ensure_ascii=False))
            return 0
    try:
        client = client or _client()
    except ConfigError as exc:
        if args.action != "check":
            print(f"Không lấy được cấu hình Flowable: {exc}", file=sys.stderr)
            return 2
        client = None                             # dry-run: gói vẫn kiểm được, chỉ không biết đã triển khai chưa
    try:
        result = asyncio.run(run(args.action, args.name, bundle, client))
    except FlowableError as exc:
        print(f"Không gọi được Flowable: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
