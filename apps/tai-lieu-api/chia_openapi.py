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

"""Chia OpenAPI của các dịch vụ (docs/api/openapi/, do make api-docs sinh từ mã) thành hai bộ cho trang Swagger:

  loi.json        API lõi (Tầng 1): tệp, tìm kiếm, hỏi đáp, quy trình của ứng dụng, trạng thái, mốc neo
  van-phong.json  API của Văn phòng điện tử (Tầng 2): chạy trong svc-files sau cờ MOC_OFFICE_ENABLED, chưa tách
                  tiến trình (#324)

Mỗi đường qua cổng thuộc đúng một bộ, một nhóm (GROUPS, theo thứ tự hiện trên trang). Đường của svc-files thuộc lõi đúng
bằng CORE_API của services/svc-files/tests/test_office_flag.py, tức các đường còn lại khi tắt cờ (tests/test_openapi.py
kiểm). Đường nội bộ của svc-workflow (/actions/{name}: Hasura gọi; /ot/notify/{tenant}: broker NGSI-LD gọi) không qua
cổng nên không lên trang. Đường /api/… mới chưa xếp thì báo lỗi: image không dựng được, make test đỏ.

Dockerfile chạy lúc dựng image: python3 chia_openapi.py <thư mục OpenAPI> <thư mục ra>
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

SERVICES = ("svc-files", "svc-workflow")
HTTP_METHODS = ("get", "post", "put", "patch", "delete")
DOCS = "https://github.com/HIT-Champion/Signet/blob/develop/docs/api"
INFO = {
    "loi": (
        "Signet — API lõi (Tầng 1)",
        "Dịch vụ dùng chung mà mọi ứng dụng gọi qua cổng APISIX: tệp qua trạm kiểm dịch, tìm kiếm, hỏi đáp trên văn "
        "bản, quy trình duyệt của ứng dụng cắm bằng manifest, trạng thái hệ thống. Cần token Bearer do Keycloak cấp "
        "(nút **Đăng nhập** ở đầu trang, hoặc **Authorize** rồi dán token), trừ nhóm ghi \"không cần token\". "
        "Đường `/api/workflow/{app}/…` chỉ nhận token của client `app-<tên>` của đúng ứng dụng đó, nên gọi thử ở đây "
        "trả `403`.\n\n"
        "Dữ liệu có cấu trúc đi qua GraphQL `POST /v1/graphql` (Hasura), không có trên trang này: schema theo từng vai "
        f"trò ở [docs/api/graphql]({DOCS}/graphql), cách gọi ở [docs/api/README.md]({DOCS}/README.md).",
    ),
    "van-phong": (
        "Signet — API Văn phòng điện tử (Tầng 2)",
        "Phần máy chủ của Văn phòng điện tử: văn bản, sổ đăng ký, cổng xác thực văn bản đã phát hành, hồ sơ và nộp "
        "lưu, nạp lô văn bản đến. Hiện chạy chung tiến trình với lõi trong `svc-files`, sau cờ `MOC_OFFICE_ENABLED` "
        "(tắt cờ thì các đường này không còn); tách thành dịch vụ riêng là việc #324. Cần token Bearer, trừ cổng xác "
        "thực.\n\n"
        "Thao tác nghiệp vụ (vào sổ, trình, hoàn thành việc) là Hasura Action, gọi bằng GraphQL `POST /v1/graphql`: "
        f"[docs/api/README.md]({DOCS}/README.md) mục 2.",
    ),
}
GROUPS = {
    "/api/files": ("loi", "Tệp"),
    "/api/files/{file_id}": ("loi", "Tệp"),
    "/api/search": ("loi", "Tìm kiếm và hỏi đáp"),
    "/api/documents/ask": ("loi", "Tìm kiếm và hỏi đáp"),
    "/api/workflow/{app}/forms/{form_key}": ("loi", "Quy trình của ứng dụng"),
    "/api/workflow/{app}/processes/{process_key}": ("loi", "Quy trình của ứng dụng"),
    "/api/workflow/{app}/processes": ("loi", "Quy trình của ứng dụng"),
    "/api/workflow/{app}/tasks": ("loi", "Quy trình của ứng dụng"),
    "/api/workflow/{app}/tasks/{task_id}": ("loi", "Quy trình của ứng dụng"),
    "/api/status": ("loi", "Trạng thái và mốc neo (không cần token)"),
    "/api/verify/anchor-key.pem": ("loi", "Trạng thái và mốc neo (không cần token)"),
    "/api/documents/{document_id}/preview": ("van-phong", "Văn bản"),
    "/api/files/{file_id}/read": ("van-phong", "Văn bản"),
    "/api/registers/{direction}/{year}": ("van-phong", "Sổ đăng ký"),
    "/api/registers/{direction}/{year}/pdf": ("van-phong", "Sổ đăng ký"),
    "/api/case-files/{case_file_id}/archive": ("van-phong", "Hồ sơ và nộp lưu"),
    "/api/case-files/{case_file_id}/archive/files/{file_id}": ("van-phong", "Hồ sơ và nộp lưu"),
    "/api/case-files/archive-stats": ("van-phong", "Hồ sơ và nộp lưu"),
    "/api/imports/{kind}": ("van-phong", "Nạp lô văn bản đến"),
    "/api/imports": ("van-phong", "Nạp lô văn bản đến"),
    "/api/imports/{job_id}": ("van-phong", "Nạp lô văn bản đến"),
    "/api/imports/{job_id}/rows": ("van-phong", "Nạp lô văn bản đến"),
    "/api/verify/{code}": ("van-phong", "Cổng xác thực (không cần token)"),
    "/api/verify": ("van-phong", "Cổng xác thực (không cần token)"),
    "/api/verify/ca.pem": ("van-phong", "Cổng xác thực (không cần token)"),
}


def refs(node: Any, schemas: dict[str, Any], found: set[str]) -> None:
    """Thêm vào ``found`` tên mọi kiểu ``#/components/schemas/…`` mà ``node`` nhắc tới, kể cả qua kiểu khác."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            name = ref.rsplit("/", 1)[1]
            if name not in found:
                found.add(name)
                refs(schemas[name], schemas, found)
        for value in node.values():
            refs(value, schemas, found)
    elif isinstance(node, list):
        for value in node:
            refs(value, schemas, found)


def split(specs: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Hai bộ OpenAPI {"loi": …, "van-phong": …} từ OpenAPI của từng dịch vụ; ValueError nếu GROUPS lệch."""
    owner = {path: service for service, spec in specs.items() for path in spec["paths"]}
    loose = sorted(p for p in owner if p.startswith("/api/") and p not in GROUPS)
    gone = sorted(p for p in GROUPS if p not in owner)
    if loose or gone:
        raise ValueError("; ".join([f"{p}: chưa xếp vào bộ nào (GROUPS)" for p in loose]
                                   + [f"{p}: không còn trong OpenAPI của dịch vụ" for p in gone]))
    base = specs["svc-files"]
    out = {}
    for name, (title, text) in INFO.items():
        paths: dict[str, Any] = {}
        tags: list[str] = []
        used: dict[str, Any] = {}
        for path, (doc, tag) in GROUPS.items():
            if doc != name:
                continue
            spec = specs[owner[path]]
            schemas = spec.get("components", {}).get("schemas", {})
            paths[path] = {m: {**op, "tags": [tag]} if m in HTTP_METHODS else op
                           for m, op in spec["paths"][path].items()}
            if tag not in tags:
                tags.append(tag)
            found: set[str] = set()
            refs(paths[path], schemas, found)
            for ref in sorted(found):
                if used.setdefault(ref, schemas[ref]) != schemas[ref]:
                    raise ValueError(f"kiểu {ref}: khác nhau giữa các dịch vụ")
        out[name] = {
            "openapi": base["openapi"],
            "info": {"title": title, "description": text, "version": base["info"]["version"]},
            "tags": [{"name": tag} for tag in tags],
            "paths": paths,
            "components": {"schemas": dict(sorted(used.items())),
                           "securitySchemes": base["components"]["securitySchemes"]},
        }
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("dùng: python3 chia_openapi.py <thư mục OpenAPI của dịch vụ> <thư mục ra>", file=sys.stderr)
        return 2
    src, dest = (pathlib.Path(a) for a in argv)
    specs = {s: json.loads((src / f"{s}.json").read_text(encoding="utf-8")) for s in SERVICES}
    try:
        docs = split(specs)
    except ValueError as exc:
        print(f"chia_openapi: {exc}", file=sys.stderr)
        return 1
    dest.mkdir(parents=True, exist_ok=True)
    for name, doc in docs.items():
        (dest / f"{name}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")),
                                           encoding="utf-8")
        print(f"{name}.json: {len(doc['paths'])} đường, {len(doc['components']['schemas'])} kiểu")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
