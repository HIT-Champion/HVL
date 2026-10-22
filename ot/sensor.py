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

"""Cảm biến nhiệt độ giả lập (F3.10): gửi các lần đo vào context broker NGSI-LD như một thiết bị OT.

Chạy trong mạng iot của Signet (dịch vụ ``ot-sensor``, profile iot), chỉ thư viện chuẩn:

    docker compose --profile iot --profile iot-sim run --rm ot-sensor --tenant CNTT --responsible chuyenviendt \\
        --name "Phòng máy chủ tầng 3" --readings 24,29,33,37,41

Thực thể ``urn:ngsi-ld:TemperatureSensor:<mã>`` được tạo nếu chưa có (tên phòng, người phụ trách), rồi mỗi lần đo
cập nhật ``temperature`` (°C, ``observedAt`` = giờ gửi). Broker tự ghi lịch sử từng lần đo và báo svc-workflow khi
vượt ngưỡng. Mỗi lần đo in một dòng JSON. Gửi JSON thường không kèm ``@context`` như thiết bị đơn giản: broker hiểu
theo ngữ cảnh lõi NGSI-LD.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

def call(base: str, method: str, path: str, tenant: str, body: dict | None = None) -> int:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{base}{path}", data=data, method=method, headers={
        "NGSILD-Tenant": tenant, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as exc:
        return exc.code


def prop(value: object, **extra: object) -> dict:
    return {"type": "Property", "value": value, **extra}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Cảm biến nhiệt độ giả lập gửi NGSI-LD")
    p.add_argument("--tenant", required=True, help="mã đơn vị (tenant NGSI-LD), vd CNTT")
    p.add_argument("--sensor", default="phong-may-chu", help="mã cảm biến, phần cuối của id thực thể")
    p.add_argument("--name", default="Phòng máy chủ", help="tên phòng đặt cảm biến")
    p.add_argument("--responsible", required=True, help="tên đăng nhập của chuyên viên phụ trách")
    p.add_argument("--readings", required=True, help="các lần đo, °C, cách nhau bằng dấu phẩy: 24,29,33,37,41")
    p.add_argument("--interval", type=float, default=2.0, help="giây giữa hai lần đo")
    args = p.parse_args(argv)
    base = os.environ.get("MOC_NGSI_URL", "http://scorpio:9090").rstrip("/") + "/ngsi-ld/v1"
    entity_id = f"urn:ngsi-ld:TemperatureSensor:{args.sensor}"
    try:
        readings = [float(x) for x in args.readings.split(",")]
    except ValueError:
        p.error("--readings: các số cách nhau bằng dấu phẩy")

    entity = {"id": entity_id, "type": "TemperatureSensor", "name": prop(args.name),
              "responsible": prop(args.responsible)}
    status = call(base, "POST", "/entities", args.tenant, entity)
    if status == 409:  # đã có: cập nhật tên phòng, người phụ trách
        status = call(base, "PATCH", f"/entities/{entity_id}/attrs", args.tenant,
                      {"name": prop(args.name), "responsible": prop(args.responsible)})
    if status not in (201, 204):
        print(json.dumps({"error": f"broker trả HTTP {status} khi tạo cảm biến"}, ensure_ascii=False))
        return 1
    for i, value in enumerate(readings):
        if i:
            time.sleep(args.interval)
        at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        status = call(base, "PATCH", f"/entities/{entity_id}/attrs", args.tenant,
                      {"temperature": prop(value, unitCode="CEL", observedAt=at)})
        print(json.dumps({"sensor": entity_id, "temperature": value, "observedAt": at, "status": status}), flush=True)
        if status != 204:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
