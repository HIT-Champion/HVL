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

"""Xuất tài liệu API vào docs/api/ từ hệ thống đang chạy (make api-docs).

- graphql/<vai trò>.graphql: schema GraphQL mà vai trò đó thấy, lấy qua cổng APISIX bằng token của một tài
  khoản mẫu — đúng những gì một ứng dụng nhận được, không dùng khóa quản trị Hasura
- thao-tac-theo-vai-tro.md: vai trò nào gọi được truy vấn, thao tác ghi nào
- openapi/svc-files.json, openapi/svc-workflow.json: OpenAPI do FastAPI sinh, lấy trong mạng nội bộ

Cần hệ thống đang chạy và đã `make seed`. Chạy với --check thì chỉ so với docs/api/, thoát 1 nếu tài liệu
đã cũ so với mã (CI dùng).
"""

from __future__ import annotations

import difflib
import json
import os
import pathlib
import sys

from moc_env import ROOT, Session, compose

OUT = ROOT / "docs" / "api"
# Header giấy phép của chính tệp này (khối chú thích đầu tiên), dùng lại cho các tệp .graphql sinh ra
LICENSE = pathlib.Path(__file__).read_text(encoding="utf-8").split("\n\n", 1)[0] + "\n"
ROLES = {
    "clerk": "văn thư",
    "staff": "chuyên viên",
    "manager": "lãnh đạo phòng",
    "director": "lãnh đạo đơn vị",
    "tenant_admin": "quản trị đơn vị",
}
SERVICES = {
    "svc-files": "qua cổng APISIX ở /api/files, /api/search",
    "svc-workflow": "nội bộ, không qua cổng: Hasura gọi để chạy Actions, context broker NGSI-LD gọi /ot/notify",
}
BUILTIN_SCALARS = {"String", "Int", "Float", "Boolean", "ID"}

INTROSPECTION = """
query {
  __schema {
    queryType { name } mutationType { name } subscriptionType { name }
    types {
      kind name description
      fields(includeDeprecated: true) {
        name description args { ...InputValue } type { ...TypeRef } isDeprecated deprecationReason
      }
      inputFields { ...InputValue }
      interfaces { ...TypeRef }
      enumValues(includeDeprecated: true) { name description isDeprecated deprecationReason }
      possibleTypes { ...TypeRef }
    }
  }
}
fragment InputValue on __InputValue { name description type { ...TypeRef } defaultValue }
fragment TypeRef on __Type {
  kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name } } } } }
}
"""


def demo_accounts() -> dict[str, str]:
    """Tài khoản mẫu đầu tiên của mỗi vai trò trong seed/users.csv."""
    accounts: dict[str, str] = {}
    for line in (ROOT / "seed" / "users.csv").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            username, _, _, role, *_ = line.split(",")
            accounts.setdefault(role, username)
    missing = set(ROLES) - set(accounts)
    if missing:
        sys.exit(f"seed/users.csv thiếu tài khoản mẫu cho vai trò: {', '.join(sorted(missing))}")
    return accounts


# --- In schema GraphQL dạng SDL từ kết quả introspection ---------------------------------------------------

def type_ref(t: dict) -> str:
    if t["kind"] == "NON_NULL":
        return type_ref(t["ofType"]) + "!"
    if t["kind"] == "LIST":
        return f"[{type_ref(t['ofType'])}]"
    return t["name"]


def description(text: str | None, indent: str = "") -> str:
    if not text:
        return ""
    if "\n" not in text:
        return f"{indent}{json.dumps(text, ensure_ascii=False)}\n"
    lines = text.replace('"""', '\\"""').split("\n")
    return "".join(f"{indent}{line}\n" if line else "\n" for line in ['"""', *lines, '"""'])


def deprecated(item: dict) -> str:
    if not item.get("isDeprecated"):
        return ""
    reason = item.get("deprecationReason")
    return f" @deprecated(reason: {json.dumps(reason, ensure_ascii=False)})" if reason else " @deprecated"


def input_value(v: dict) -> str:
    default = f" = {v['defaultValue']}" if v.get("defaultValue") is not None else ""
    return f"{v['name']}: {type_ref(v['type'])}{default}"


def arguments(args: list[dict], indent: str) -> str:
    if not args:
        return ""
    if not any(a.get("description") for a in args):
        return "(" + ", ".join(input_value(a) for a in args) + ")"
    inner = indent + "  "
    return "(\n" + "".join(description(a.get("description"), inner) + inner + input_value(a) + "\n"
                           for a in args) + indent + ")"


def print_type(t: dict) -> str:
    head = description(t.get("description"))
    kind, name = t["kind"], t["name"]
    if kind == "SCALAR":
        return f"{head}scalar {name}"
    if kind == "UNION":
        return f"{head}union {name} = " + " | ".join(p["name"] for p in t["possibleTypes"])
    if kind == "ENUM":
        body = "".join(description(v.get("description"), "  ") + f"  {v['name']}{deprecated(v)}\n"
                       for v in t["enumValues"])
        return f"{head}enum {name} {{\n{body}}}"
    if kind == "INPUT_OBJECT":
        body = "".join(description(f.get("description"), "  ") + f"  {input_value(f)}\n" for f in t["inputFields"])
        return f"{head}input {name} {{\n{body}}}"
    keyword = "interface" if kind == "INTERFACE" else "type"
    implements = " implements " + " & ".join(i["name"] for i in t["interfaces"]) if t.get("interfaces") else ""
    body = "".join(
        description(f.get("description"), "  ")
        + f"  {f['name']}{arguments(f['args'], '  ')}: {type_ref(f['type'])}{deprecated(f)}\n"
        for f in t["fields"]
    )
    return f"{head}{keyword} {name}{implements} {{\n{body}}}"


def print_schema(schema: dict) -> str:
    roots = [(op, (schema.get(f"{op}Type") or {}).get("name")) for op in ("query", "mutation", "subscription")]
    parts = ["schema {\n" + "".join(f"  {op}: {name}\n" for op, name in roots if name) + "}"]
    types = sorted((t for t in schema["types"] if not t["name"].startswith("__") and t["name"] not in BUILTIN_SCALARS),
                   key=lambda t: t["name"])
    parts += [print_type(t) for t in types]
    return "\n\n".join(parts) + "\n"


def root_fields(schema: dict, op: str) -> list[str]:
    name = (schema.get(f"{op}Type") or {}).get("name")
    for t in schema["types"]:
        if t["name"] == name:
            return [f["name"] for f in t["fields"]]
    return []


# --- Các tệp tài liệu -------------------------------------------------------------------------------------

def graphql_file(role: str, schema: dict) -> str:
    return (
        LICENSE
        + "#\n"
        + f"# Schema GraphQL mà vai trò `{role}` ({ROLES[role]}) thấy qua cổng APISIX: POST /v1/graphql.\n"
        + "# Tệp sinh tự động bằng `make api-docs` từ hệ thống đang chạy, không sửa tay; CI báo lỗi khi tệp cũ.\n"
        + "# subscription_root có trong schema của Hasura nhưng cổng chưa mở WebSocket, nên chưa gọi được qua cổng.\n"
        + "\n"
        + print_schema(schema)
    )


def matrix_file(schemas: dict[str, dict], accounts: dict[str, str]) -> str:
    roles = list(ROLES)
    ops = {op: {role: root_fields(schemas[role], op) for role in roles} for op in ("query", "mutation")}
    lines = [
        "# Truy vấn và thao tác ghi theo vai trò",
        "",
        "> Tệp sinh tự động bằng `make api-docs` từ hệ thống đang chạy, không sửa tay. Cách gọi API: [README](README.md).",
        "",
        "Mỗi vai trò thấy một schema GraphQL riêng ở `POST /v1/graphql`, lấy qua cổng APISIX bằng token của tài khoản",
        "mẫu trong bảng dưới. Trường không có trong schema của vai trò thì gọi sẽ bị Hasura báo lỗi `validation-failed`.",
        "Ngoài ra Hasura còn lọc theo dòng (cùng đơn vị, cùng phòng, văn bản hạn chế) và theo cột; quy tắc ở",
        "[`db/README.md`](../../db/README.md#vai-trò).",
        "",
        "| Vai trò | Tài khoản mẫu | Truy vấn | Thao tác ghi | Schema |",
        "|---|---|--:|--:|---|",
    ]
    for role in roles:
        lines.append(f"| `{role}` ({ROLES[role]}) | `{accounts[role]}` | {len(ops['query'][role])} "
                     f"| {len(ops['mutation'][role])} | [`graphql/{role}.graphql`](graphql/{role}.graphql) |")
    for op, title in (("query", "Truy vấn (`query`)"), ("mutation", "Thao tác ghi (`mutation`)")):
        names = sorted({name for fields in ops[op].values() for name in fields})
        lines += ["", f"## {title}", "", "| Trường | " + " | ".join(f"`{r}`" for r in roles) + " |",
                  "|---|" + ":-:|" * len(roles)]
        for name in names:
            marks = " | ".join("✓" if name in ops[op][role] else "" for role in roles)
            lines.append(f"| `{name}` | {marks} |")
    lines += ["", "`subscription` có trong schema của Hasura nhưng chưa gọi được qua cổng (chưa mở WebSocket), nên không liệt kê.", ""]
    return "\n".join(lines)


def openapi_file(service: str) -> str:
    raw = compose("exec", "-T", service, "python", "-c",
                  "import sys, urllib.request; "
                  "sys.stdout.buffer.write(urllib.request.urlopen('http://127.0.0.1:8000/openapi.json', timeout=30).read())")
    return json.dumps(json.loads(raw), indent=2, ensure_ascii=False) + "\n"


def build() -> dict[str, str]:
    accounts = demo_accounts()
    schemas = {role: Session(accounts[role]).gql(INTROSPECTION)["__schema"] for role in ROLES}
    files = {f"graphql/{role}.graphql": graphql_file(role, schemas[role]) for role in ROLES}
    files["thao-tac-theo-vai-tro.md"] = matrix_file(schemas, accounts)
    files.update({f"openapi/{service}.json": openapi_file(service) for service in SERVICES})
    return files


def main() -> None:
    check = "--check" in sys.argv[1:]
    files = build()
    # Tệp sinh ra từ lần trước nhưng nay không còn (đổi tên vai trò, bỏ dịch vụ)
    leftover = sorted(str(p.relative_to(OUT)) for pattern in ("graphql/*.graphql", "openapi/*.json")
                      for p in OUT.glob(pattern) if str(p.relative_to(OUT)) not in files)
    changed = []
    for rel, content in files.items():
        path = OUT / rel
        old = path.read_text(encoding="utf-8") if path.exists() else ""
        if old == content:
            continue
        changed.append(rel)
        if check:
            diff = list(difflib.unified_diff(old.splitlines(), content.splitlines(), f"docs/api/{rel} (trong git)",
                                             f"docs/api/{rel} (hệ thống đang chạy)", lineterm="", n=1))
            print("\n".join(diff[:30]) + ("\n…" if len(diff) > 30 else ""))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    for rel in leftover:
        if not check:
            (OUT / rel).unlink()

    stale = changed + leftover
    if check:
        if stale:
            print(f"\n✗ Tài liệu API đã cũ so với mã: {', '.join(stale)}")
            if os.environ.get("GITHUB_ACTIONS") == "true":
                print("  Trên CI: tải artifact docs-api-<lần chạy> của job \"Chạy thử: luong-chinh\" "
                      "(gh run download), chép vào docs/api/ rồi commit.")
            sys.exit("  Chạy `make up && make seed && make api-docs` rồi commit thư mục docs/api/.")
        print(f"✓ Tài liệu API trong docs/api/ khớp hệ thống đang chạy ({len(files)} tệp)")
    elif stale:
        print(f"Đã cập nhật docs/api/: {', '.join(stale)}")
    else:
        print(f"docs/api/ đã khớp hệ thống đang chạy, không đổi tệp nào ({len(files)} tệp)")


if __name__ == "__main__":
    main()
