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

Thực thể ``urn:ngsi-ld:TemperatureSensor:<mã>`` được tạo nếu chưa có (tên phòng, người phụ trách, mã phòng trên sơ
đồ kho nếu có ``--room``), rồi mỗi lần đo cập nhật ``temperature`` (°C, ``observedAt`` = giờ gửi). Broker tự ghi lịch
sử từng lần đo và báo svc-workflow khi vượt ngưỡng. Mỗi lần đo in một dòng JSON. Gửi JSON thường không kèm
``@context`` như thiết bị đơn giản: broker hiểu theo ngữ cảnh lõi NGSI-LD.

Giả lỗi dữ liệu để thấy cờ chất lượng trên trang Sơ đồ cảm biến: ``--late 30`` lùi ``observedAt`` 30 phút (thiết bị
mất tín hiệu từ nửa giờ trước), ``--frozen-clock`` cho mọi lần đo cùng ``observedAt`` của lần đầu (đồng hồ thiết bị
đứng), số đo ngoài dải như ``--readings 22,-127`` (-127 °C: mã "mất kết nối" của thư viện DallasTemperature).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

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
    p.add_argument("--room", help="mã phòng trên sơ đồ kho (trang Sơ đồ cảm biến), vd kho-1, may-chu")
    p.add_argument("--late", type=float, default=0.0, help="lùi observedAt chừng ấy phút: giả thiết bị mất tín hiệu")
    p.add_argument("--frozen-clock", action="store_true",
                   help="mọi lần đo mang observedAt của lần đầu: giả đồng hồ thiết bị đứng")
    args = p.parse_args(argv)
    if args.room is not None and not re.fullmatch(r"[a-z0-9-]{1,40}", args.room):
        p.error("--room: 1–40 ký tự a-z, 0-9, dấu gạch ngang")
    base = os.environ.get("MOC_NGSI_URL", "http://scorpio:9090").rstrip("/") + "/ngsi-ld/v1"
    entity_id = f"urn:ngsi-ld:TemperatureSensor:{args.sensor}"
    try:
        readings = [float(x) for x in args.readings.split(",")]
    except ValueError:
        p.error("--readings: các số cách nhau bằng dấu phẩy")

    about = {"name": prop(args.name), "responsible": prop(args.responsible)}
    if args.room is not None:
        about["room"] = prop(args.room)
    status = call(base, "POST", "/entities", args.tenant, {"id": entity_id, "type": "TemperatureSensor", **about})
    if status == 409:  # đã có: cập nhật tên phòng, người phụ trách, mã phòng
        status = call(base, "PATCH", f"/entities/{entity_id}/attrs", args.tenant, about)
    if status not in (201, 204):
        print(json.dumps({"error": f"broker trả HTTP {status} khi tạo cảm biến"}, ensure_ascii=False))
        return 1
    first = ""
    for i, value in enumerate(readings):
        if i:
            time.sleep(args.interval)
        at = (datetime.now(UTC) - timedelta(minutes=args.late)).isoformat(timespec="seconds").replace("+00:00", "Z")
        if args.frozen_clock:
            at = first = first or at
        status = call(base, "PATCH", f"/entities/{entity_id}/attrs", args.tenant,
                      {"temperature": prop(value, unitCode="CEL", observedAt=at)})
        print(json.dumps({"sensor": entity_id, "temperature": value, "observedAt": at, "status": status}), flush=True)
        if status != 204:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
