# Copyright 2026 Mộc Team
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

"""scripts/tenants.py và lệnh `moc tenant`: alias, tham số dòng lệnh, kế hoạch --dry-run, chạy lại không tạo trùng, kiểm
Organization. Keycloak giả (đúng các đường Admin REST mà tenants.Keycloak gọi) và CSDL giả: không cần Docker, không đọc
.env. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib
import io
import json
import pathlib
import sys
import types
import unittest
import urllib.parse
import uuid
from collections import defaultdict
from typing import Any
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8180/admin/realms/moc"
CNTT, KT = "c300d5bb-028f-44cc-ba10-7b5277a4225d", "318da474-60d6-4a90-aa7f-928b31b8fc59"

tenants: Any = None
moc: Any = None
_saved: dict[str, Any] = {}


class FakeHTTPError(Exception):
    def __init__(self, status: int, body: str = "", url: str = ""):
        super().__init__(f"HTTP {status} {url}: {body}")
        self.status = status
        self.body = body


def setUpModule() -> None:
    """moc_env thật đọc .env lúc nạp (thiếu thì thoát): thay bằng bản giả chỉ có những gì moc.py, backup.py cần."""
    global tenants, moc
    for name in ("moc_env", "moc", "backup", "tenants"):
        _saved[name] = sys.modules.pop(name, None)
    stub = types.ModuleType("moc_env")
    stub.ENV = {}
    stub.ROOT = SCRIPTS.parent
    stub.REALM = "moc"
    stub.KEYCLOAK_ADMIN_URL = "http://127.0.0.1:8180"
    stub.PUBLIC_URL = "http://localhost:8080"
    stub.HTTPError = FakeHTTPError

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("test không được gọi mạng")

    stub.call_json = no_network
    sys.modules["moc_env"] = stub
    sys.path.insert(0, str(SCRIPTS))
    tenants = importlib.import_module("tenants")
    moc = importlib.import_module("moc")


def tearDownModule() -> None:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
    sys.path.remove(str(SCRIPTS))


class FakeKeycloak:
    """Keycloak 26 giả, đủ các đường Admin REST của tenants.Keycloak; ghi lại mọi lần gọi."""

    def __init__(self, organizations_enabled: bool = True):
        self.realm = {"realm": "moc", "enabled": True, "organizationsEnabled": organizations_enabled,
                      "attributes": {"frontendUrl": ""}, "oauth2DeviceCodeLifespan": 600}
        self.orgs: dict[str, dict[str, Any]] = {}
        self.members: dict[str, list[str]] = defaultdict(list)
        self.users: dict[str, dict[str, Any]] = {}
        self.passwords: dict[str, str] = {}
        self.calls: list[tuple[str, str, Any]] = []

    def add_user(self, username: str, tenant: str | None = None, role: str | None = "staff",
                 email: str | None = "") -> str:
        uid = str(uuid.uuid4())
        attrs: dict[str, list[str]] = {}
        if tenant:
            attrs["tenant_id"] = [tenant]
        if role:
            attrs["moc_role"] = [role]
        self.users[uid] = {"id": uid, "username": username, "enabled": True,
                           "email": f"{username}@x.moc.example" if email == "" else email, "attributes": attrs}
        return uid

    def add_org(self, alias: str, name: str, tenant: str | None = None, members: tuple[str, ...] = ()) -> str:
        oid = str(uuid.uuid4())
        self.orgs[oid] = {"id": oid, "alias": alias, "name": name, "enabled": True, "description": "",
                          "attributes": {"tenant_id": [tenant]} if tenant else {}, "domains": []}
        self.members[oid] = list(members)
        return oid

    def writes(self) -> list[tuple[str, str]]:
        return [(m, p) for m, p, _ in self.calls if m != "GET"]

    @staticmethod
    def _page(items: list[Any], q: dict[str, str]) -> list[Any]:
        start = int(q.get("first", 0))
        return items[start:start + int(q.get("max", 10))]

    def __call__(self, method: str, url: str, body: Any = None, *, headers: dict[str, str] | None = None,
                 form: Any = None) -> tuple[Any, dict[str, str]]:
        assert url.startswith(BASE), url
        assert headers and headers["Authorization"] == "Bearer tok"
        parts = urllib.parse.urlsplit(url)
        path, q = parts.path[len("/admin/realms/moc"):], dict(urllib.parse.parse_qsl(parts.query))
        self.calls.append((method, path, copy.deepcopy(body)))
        seg = [s for s in path.split("/") if s]
        if not seg and method == "GET":
            return copy.deepcopy(self.realm), {}
        if not seg and method == "PUT":
            self.realm = copy.deepcopy(body)
            return None, {}
        if seg[0] == "organizations":
            if not self.realm.get("organizationsEnabled"):
                raise FakeHTTPError(404, json.dumps({"errorMessage": "Organizations not enabled for this realm."}))
            if len(seg) == 1 and method == "GET":
                full = q.get("briefRepresentation") == "false"
                items = [copy.deepcopy(o) if full else {k: v for k, v in o.items() if k != "attributes"}
                         for o in self.orgs.values()]
                return self._page(items, q), {}
            if len(seg) == 1 and method == "POST":
                if any(o["alias"] == body["alias"] or o["name"] == body["name"] for o in self.orgs.values()):
                    raise FakeHTTPError(409, json.dumps({"errorMessage": "duplicate"}))
                oid = str(uuid.uuid4())
                self.orgs[oid] = {**copy.deepcopy(body), "id": oid}
                return None, {"Location": f"{BASE}/organizations/{oid}"}
            oid = seg[1]
            if len(seg) == 2 and method == "PUT":
                assert body["alias"] == self.orgs[oid]["alias"], "Keycloak không cho đổi alias"
                assert "attributes" in body, "PUT thiếu attributes sẽ không còn tenant_id"
                self.orgs[oid] = {**copy.deepcopy(body), "id": oid}
                return None, {}
            if seg[2:] == ["members"] and method == "GET":
                items = [{"id": u, "username": self.users[u]["username"], "email": self.users[u].get("email"),
                          "membershipType": "UNMANAGED"} for u in self.members[oid]]
                return self._page(items, q), {}
            if seg[2:] == ["members"] and method == "POST":
                if body in self.members[oid]:
                    raise FakeHTTPError(409, json.dumps({"errorMessage": "User is already a member of the organization."}))
                self.members[oid].append(body)
                return None, {"Location": f"{BASE}/organizations/{oid}/members/{body}"}
        if seg[0] == "users":
            if len(seg) == 1 and method == "GET":
                found = list(self.users.values())
                if "username" in q:
                    found = [u for u in found if u["username"] == q["username"]]
                if "email" in q:
                    found = [u for u in found if u.get("email") == q["email"]]
                return self._page(copy.deepcopy(found), q), {}
            if len(seg) == 1 and method == "POST":
                if any(u["username"] == body["username"] for u in self.users.values()):
                    raise FakeHTTPError(409, json.dumps({"errorMessage": "User exists with same username"}))
                uid = str(uuid.uuid4())
                rep = copy.deepcopy(body)
                creds = rep.pop("credentials", [])
                self.users[uid] = {**rep, "id": uid}
                if creds:
                    self.passwords[uid] = creds[0]["value"]
                return None, {"Location": f"{BASE}/users/{uid}"}
            if seg[2:] == ["reset-password"] and method == "PUT":
                self.passwords[seg[1]] = body["value"]
                return None, {}
        raise AssertionError(f"chưa giả lập: {method} {url}")


class FakeDB:
    """CSDL giả: nhận đúng các câu SQL của tenants.py; danh bạ core.users chép từ Keycloak giả như svc-workflow."""

    def __init__(self, kc: FakeKeycloak | None = None, sync: bool = True):
        self.tenants: dict[str, dict[str, Any]] = {}
        self.departments: dict[str, dict[str, str]] = defaultdict(dict)
        self.core_users: list[dict[str, Any]] = []
        self.kc, self.auto_sync = kc, sync
        self.writes = 0
        self.variables: list[dict[str, str]] = []

    def add_tenant(self, code: str, name: str, tid: str | None = None, departments: dict[str, str] | None = None) -> str:
        tid = tid or str(uuid.uuid4())
        self.tenants[code] = {"id": tid, "code": code, "name": name, "org_ident": None, "parent_name": None,
                              "place_name": None, "head_title": None}
        self.departments[code].update(departments or {})
        return tid

    def sync(self) -> None:
        known = {t["id"] for t in self.tenants.values()}
        self.core_users = [
            {"id": u["id"], "tenant_id": tenants.user_tenant(u), "username": u["username"],
             "enabled": u.get("enabled", True)}
            for u in (self.kc.users.values() if self.kc else [])
            if tenants.user_tenant(u) in known and tenants.first(u["attributes"], "moc_role") in tenants.ROLES]

    def _state(self, code: str, org_ident: str) -> dict[str, Any]:
        t = self.tenants.get(code)
        owner = next((c for c, x in self.tenants.items() if org_ident and x["org_ident"] == org_ident and c != code), None)
        return {"tenant": dict(t) if t else None, "org_ident_owner": owner,
                "departments": [{"code": c, "name": n} for c, n in sorted(self.departments[code].items())]}

    def _list(self) -> list[dict[str, Any]]:
        return [{"id": t["id"], "code": c, "name": t["name"], "departments": sorted(self.departments[c]),
                 "users": sum(1 for u in self.core_users if u["tenant_id"] == t["id"] and u["enabled"]),
                 "documents": 0} for c, t in self.tenants.items()]

    def query(self, sql: str, **v: str) -> Any:
        self.variables.append(v)
        if sql is tenants.STATE_SQL:
            return self._state(v["code"], v["org_ident"])
        if sql is tenants.WRITE_SQL:
            self.writes += 1
            assert v["actor"].startswith("os:")
            t = self.tenants.setdefault(v["code"], {"id": v["id"], "code": v["code"], "org_ident": None,
                                                    "parent_name": None, "place_name": None, "head_title": None})
            t["name"] = v["name"]
            for k in ("org_ident", "parent_name", "place_name", "head_title"):
                if v[k]:
                    t[k] = v[k]
            for d in json.loads(v["departments"]):
                self.departments[v["code"]][d["code"]] = d["name"]
            return self._state(v["code"], v["org_ident"])
        if sql is tenants.SYNCED_SQL:
            if self.auto_sync:
                self.sync()
            return {"synced": any(r["id"] == v["user_id"] and r["tenant_id"] == v["tenant_id"] and r["enabled"]
                                  for r in self.core_users)}
        if sql is tenants.TENANTS_SQL:
            return self._list()
        if sql is tenants.CHECK_SQL:
            return {"tenants": self._list(), "users": list(self.core_users)}
        raise AssertionError("câu SQL lạ")


def seeded(organized: bool = True) -> tuple[FakeKeycloak, FakeDB]:
    """Như sau make seed: CNTT (3 tài khoản), KT (1 tài khoản); organized: mỗi đơn vị đã có Organization."""
    kc = FakeKeycloak()
    db = FakeDB(kc)
    db.add_tenant("CNTT", "Khoa Công nghệ thông tin", CNTT, {"VP": "Văn phòng khoa", "ĐT": "Tổ Đào tạo"})
    db.add_tenant("KT", "Khoa Kinh tế", KT, {"VP": "Văn phòng khoa"})
    a = kc.add_user("vanthu", CNTT, "clerk")
    b = kc.add_user("chuyenviendt", CNTT, "staff")
    q = kc.add_user("quantri", CNTT, "tenant_admin")
    k = kc.add_user("vanthukt", KT, "clerk")
    kc.add_user("service-account-svc-workflow", None, None, email=None)
    if organized:
        kc.add_org("cntt", "Khoa Công nghệ thông tin", CNTT, (a, b, q))
        kc.add_org("kt", "Khoa Kinh tế", KT, (k,))
    db.sync()
    return kc, db


def run_moc(kc: FakeKeycloak, db: FakeDB, *argv: str) -> tuple[int, str, str]:
    client = tenants.Keycloak("http://127.0.0.1:8180", "moc", "tok", call=kc, http_error=FakeHTTPError)
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(tenants, "connect", return_value=client), \
            mock.patch.object(tenants, "database", return_value=db), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = moc.main(list(argv))
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


CREATE = ("tenant", "create", "--code", "KTCK", "--name", "Khoa Cơ khí", "--department", "VP=Văn phòng khoa",
          "--department", "ĐT=Tổ Đào tạo", "--admin", "quantrick", "--admin-name", "Lê Văn Cường")


class AliasTest(unittest.TestCase):
    def test_alias_from_code(self) -> None:
        cases = {"CNTT": "cntt", "KT": "kt", "KTCK": "ktck", "ĐT": "dt", "đhbk": "dhbk", "ẮÂÊÔƠƯ": "aaeoou",
                 "K.CNTT": "k-cntt", "Khoa_Cơ": "khoa-co", "VP2": "vp2"}
        for code, alias in cases.items():
            with self.subTest(code=code):
                self.assertEqual(tenants.alias_for(code), alias)
                self.assertRegex(tenants.alias_for(code), tenants.ALIAS)

    def test_alias_without_latin_letters_is_hashed(self) -> None:
        alias = tenants.alias_for("東京")
        self.assertEqual(alias, "t" + hashlib.sha256("東京".encode()).hexdigest()[:16])
        self.assertRegex(alias, tenants.ALIAS)

    def test_ngsi_tenant_like_svc_workflow(self) -> None:
        self.assertEqual(tenants.ngsi_tenant("CNTT"), "CNTT")
        self.assertEqual(tenants.ngsi_tenant("ĐT"), "t" + hashlib.sha256("ĐT".encode()).hexdigest()[:16])

    def test_temporary_password_meets_realm_policy(self) -> None:
        seen = {tenants.generate_password() for _ in range(50)}
        self.assertEqual(len(seen), 50)
        for p in seen:
            self.assertGreaterEqual(len(p), 10)       # passwordPolicy length(10)
            self.assertRegex(p, r"^[A-Za-z2-9]{4}(-[A-Za-z2-9]{4}){3}$")


class ArgumentsTest(unittest.TestCase):
    def test_department(self) -> None:
        self.assertEqual(tenants.department_arg("VP=Văn phòng  khoa"), ("VP", "Văn phòng khoa"))
        self.assertEqual(tenants.department_arg(" ĐT = Tổ Đào tạo "), ("ĐT", "Tổ Đào tạo"))
        for bad in ("VP", "VP=", "V P=Văn phòng", "A/B=Phòng", "A-B=Phòng", "=Phòng", "X" * 21 + "=Phòng"):
            with self.subTest(bad=bad), self.assertRaises(tenants.argparse.ArgumentTypeError):
                tenants.department_arg(bad)

    def test_bad_code_rejected_before_anything_runs(self) -> None:
        kc, db = seeded()
        code, out, err = run_moc(kc, db, "tenant", "create", "--code", "K T", "--name", "X", "--admin", "abc")
        self.assertEqual(code, 2)
        self.assertIn("--code", err)
        self.assertEqual(kc.calls, [])
        self.assertEqual(db.variables, [])

    def test_admin_required(self) -> None:
        kc, db = seeded()
        code, _, err = run_moc(kc, db, "tenant", "create", "--code", "KTCK", "--name", "Khoa Cơ khí")
        self.assertEqual(code, 2)
        self.assertIn("--admin", err)

    def test_username_and_person_name(self) -> None:
        self.assertEqual(tenants.username_arg(" QuanTri.CK "), "quantri.ck")
        for bad in ("ab", "quản trị", "-abc"):
            with self.subTest(bad=bad), self.assertRaises(tenants.argparse.ArgumentTypeError):
                tenants.username_arg(bad)
        self.assertEqual(tenants.split_name(tenants.person_arg("Ngô  Văn Tín")), ("Ngô Văn", "Tín"))
        with self.assertRaises(tenants.argparse.ArgumentTypeError):
            tenants.person_arg("Tín")

    def test_duplicate_department_refused(self) -> None:
        kc, db = seeded()
        code, out, _ = run_moc(kc, db, *CREATE, "--department", "VP=Văn phòng", "--json")
        self.assertEqual(code, 1)
        self.assertIn("VP", json.loads(out)["error"])
        self.assertEqual(kc.writes(), [])


class CreateTest(unittest.TestCase):
    def test_dry_run_plans_without_writing(self) -> None:
        kc, db = seeded(organized=False)
        kc.realm["organizationsEnabled"] = False
        code, out, _ = run_moc(kc, db, *CREATE, "--dry-run", "--json")
        self.assertEqual(code, 0)
        plan = json.loads(out)
        self.assertTrue(plan["dry_run"])
        self.assertEqual((plan["tenant"]["status"], plan["tenant"]["id"]), ("created", None))
        self.assertEqual([(d["code"], d["status"]) for d in plan["departments"]], [("VP", "created"), ("ĐT", "created")])
        self.assertTrue(plan["realm"]["enable"])
        self.assertEqual((plan["organization"]["alias"], plan["organization"]["status"]), ("ktck", "created"))
        self.assertEqual(plan["organization"]["added"], ["quantrick"])
        self.assertEqual(plan["admin"]["status"], "created")
        self.assertEqual(plan["admin"]["email"], "quantrick@ktck.moc.example")
        self.assertIsNone(plan["admin"]["temporary_password"])
        self.assertEqual(kc.writes(), [])
        self.assertEqual(db.writes, 0)

    def test_create_then_rerun_keeps_everything(self) -> None:
        kc, db = seeded()
        kc.realm["organizationsEnabled"] = False      # realm nạp từ tệp trước F3.12
        code, out, _ = run_moc(kc, db, *CREATE, "--json")
        self.assertEqual(code, 0, out)
        first = json.loads(out)
        tid = first["tenant"]["id"]
        self.assertEqual(db.tenants["KTCK"]["id"], tid)
        self.assertEqual(db.departments["KTCK"], {"VP": "Văn phòng khoa", "ĐT": "Tổ Đào tạo"})

        # realm: bật Organizations bằng bản đầy đủ vừa đọc, không chỉ một trường
        put = [b for m, p, b in kc.calls if (m, p) == ("PUT", "")]
        self.assertEqual(len(put), 1)
        self.assertTrue(put[0]["organizationsEnabled"])
        self.assertEqual(put[0]["oauth2DeviceCodeLifespan"], 600)

        org = next(o for o in kc.orgs.values() if o["alias"] == "ktck")
        self.assertEqual(org["attributes"], {"tenant_id": [tid]})
        self.assertEqual(org["name"], "Khoa Cơ khí")

        admin = next(u for u in kc.users.values() if u["username"] == "quantrick")
        self.assertEqual(admin["attributes"], {"tenant_id": [tid], "moc_role": ["tenant_admin"]})  # không có phòng
        self.assertEqual((admin["firstName"], admin["lastName"]), ("Lê Văn", "Cường"))
        self.assertEqual(admin["requiredActions"], ["UPDATE_PASSWORD", "CONFIGURE_TOTP"])
        posted = next(b for m, p, b in kc.calls if (m, p) == ("POST", "/users"))
        self.assertEqual(posted["credentials"][0]["temporary"], True)
        self.assertNotIn("otp", [c["type"] for c in posted["credentials"]])   # không cài sẵn TOTP như tài khoản mẫu
        self.assertEqual(kc.members[org["id"]], [admin["id"]])
        password = first["admin"]["temporary_password"]
        self.assertEqual(kc.passwords[admin["id"]], password)
        self.assertNotIn(password, json.dumps(db.variables, ensure_ascii=False))   # không đi vào CSDL
        self.assertTrue(first["directory"]["synced"])
        self.assertTrue(first["ok"])

        writes_before = len(kc.writes())
        code, out, _ = run_moc(kc, db, *CREATE, "--json")
        self.assertEqual(code, 0, out)
        again = json.loads(out)
        self.assertEqual(again["tenant"]["id"], tid)
        self.assertEqual([again[k]["status"] for k in ("tenant", "organization", "admin")], ["kept"] * 3)
        self.assertEqual({d["status"] for d in again["departments"]}, {"kept"})
        self.assertIsNone(again["admin"]["temporary_password"])
        self.assertEqual(again["organization"]["added"], [])
        self.assertEqual(len(kc.writes()), writes_before)                  # Keycloak: không ghi gì thêm
        self.assertEqual(sum(o["alias"] == "ktck" for o in kc.orgs.values()), 1)
        self.assertEqual(sum(u["username"] == "quantrick" for u in kc.users.values()), 1)

    def test_human_output(self) -> None:
        kc, db = seeded()
        code, out, _ = run_moc(kc, db, *CREATE)
        self.assertEqual(code, 0, out)
        password = next(iter(kc.passwords.values()))
        self.assertEqual(out.count(password), 1)
        for text in ("Organization ktck", "tenant_admin", "đổi mật khẩu và cài TOTP", "Tự có, không phải làm thêm",
                     "Dùng chung có chủ ý", "files_object_key_tenant", "S3 Object Lock", "AAD", "Meilisearch"):
            self.assertIn(text, out)

    def test_existing_tenant_gets_missing_members_and_new_department(self) -> None:
        kc, db = seeded()
        late = kc.add_user("giangvien", CNTT, "staff")    # tạo sau trong trang quản trị Keycloak
        db.sync()
        code, out, _ = run_moc(kc, db, "tenant", "create", "--code", "CNTT", "--name", "Khoa Công nghệ thông tin",
                               "--department", "HTTT=Bộ môn Hệ thống thông tin", "--admin", "quantri", "--json")
        self.assertEqual(code, 0, out)
        r = json.loads(out)
        self.assertEqual((r["tenant"]["id"], r["tenant"]["status"]), (CNTT, "kept"))
        self.assertEqual(r["organization"]["status"], "kept")
        self.assertEqual(r["organization"]["added"], ["giangvien"])
        self.assertEqual(r["admin"]["status"], "kept")
        self.assertIsNone(r["admin"]["temporary_password"])
        self.assertEqual({d["code"]: d["status"] for d in r["departments"]},
                         {"HTTT": "created", "VP": "existing", "ĐT": "existing"})
        cntt = next(o for o in kc.orgs.values() if o["alias"] == "cntt")
        self.assertIn(late, kc.members[cntt["id"]])

    def test_reset_password_of_existing_admin(self) -> None:
        kc, db = seeded()
        code, out, _ = run_moc(kc, db, "tenant", "create", "--code", "CNTT", "--name", "Khoa Công nghệ thông tin",
                               "--admin", "quantri", "--reset-password", "--json")
        self.assertEqual(code, 0, out)
        r = json.loads(out)
        self.assertEqual(r["admin"]["status"], "reset")
        self.assertEqual(kc.passwords[r["admin"]["id"]], r["admin"]["temporary_password"])

    def test_refuses_account_of_another_tenant(self) -> None:
        kc, db = seeded()
        code, out, _ = run_moc(kc, db, "tenant", "create", "--code", "KTCK", "--name", "Khoa Cơ khí",
                               "--admin", "vanthukt", "--json")
        self.assertEqual(code, 1)
        self.assertIn("đơn vị khác", json.loads(out)["error"])
        self.assertEqual((kc.writes(), db.writes), ([], 0))     # kiểm trước, chưa ghi gì

    def test_refuses_existing_tenant_account_with_other_role(self) -> None:
        kc, db = seeded()
        code, out, _ = run_moc(kc, db, "tenant", "create", "--code", "CNTT", "--name", "Khoa Công nghệ thông tin",
                               "--admin", "vanthu", "--json")
        self.assertEqual(code, 1)
        self.assertIn("clerk", json.loads(out)["error"])
        self.assertEqual(db.writes, 0)

    def test_alias_clash_then_explicit_alias(self) -> None:
        kc, db = seeded()
        other = db.add_tenant("DT", "Trung tâm Đào tạo")
        kc.add_org("dt", "Trung tâm Đào tạo", other)
        args = ("tenant", "create", "--code", "ĐT", "--name", "Phòng Đào tạo", "--admin", "quantridt", "--json")
        code, out, _ = run_moc(kc, db, *args)
        self.assertEqual(code, 1)
        self.assertIn("--alias", json.loads(out)["error"])
        self.assertEqual((kc.writes(), db.writes), ([], 0))
        code, out, _ = run_moc(kc, db, *args, "--alias", "phong-dt")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["organization"]["alias"], "phong-dt")

    def test_same_tenant_name_gets_code_suffix(self) -> None:
        kc, db = seeded()
        code, out, _ = run_moc(kc, db, "tenant", "create", "--code", "KT2", "--name", "Khoa Kinh tế",
                               "--admin", "quantrikt2", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["organization"]["name"], "Khoa Kinh tế (KT2)")

    def test_directory_timeout(self) -> None:
        kc, db = seeded()
        db.auto_sync = False                                 # svc-workflow không chạy
        client = tenants.Keycloak("http://127.0.0.1:8180", "moc", "tok", call=kc, http_error=FakeHTTPError)
        clock = iter(range(0, 1000, 2))
        spec = tenants.Spec(code="KTCK", name="Khoa Cơ khí", admin="quantrick")
        r = tenants.create(spec, client, db, wait_s=10, sleep=lambda s: None, clock=lambda: next(clock))
        self.assertFalse(r["ok"])
        self.assertFalse(r["directory"]["synced"])

    def test_keycloak_down_is_unavailable(self) -> None:
        kc, db = seeded()

        def refused(*args: Any, **kwargs: Any) -> Any:
            raise ConnectionRefusedError("connection refused")

        client = tenants.Keycloak("http://127.0.0.1:8180", "moc", "tok", call=refused, http_error=FakeHTTPError)
        with mock.patch.object(tenants, "connect", return_value=client), \
                mock.patch.object(tenants, "database", return_value=db), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            code = moc.main([*CREATE, "--json"])
        self.assertEqual(code, 2)
        self.assertIn("Keycloak", json.loads(out.getvalue())["error"])


class StaleOrganizationTest(unittest.TestCase):
    def test_clash_with_organization_left_from_before_is_refused_before_writing(self) -> None:
        kc, db = seeded()
        kc.add_org("ktck", "Xưởng cũ", tenant=KT)      # tạo từ trước khi realm tắt Organizations
        kc.realm["organizationsEnabled"] = False
        code, out, _ = run_moc(kc, db, *CREATE, "--json")
        self.assertEqual(code, 1, out)
        self.assertIn("alias ktck", json.loads(out)["error"])
        self.assertEqual(db.writes, 0)                  # chưa ghi gì vào CSDL
        self.assertNotIn("KTCK", db.tenants)


class OrganizeTest(unittest.TestCase):
    def test_seed_organizations_idempotent(self) -> None:
        kc, db = seeded(organized=False)
        kc.realm["organizationsEnabled"] = False
        client = tenants.Keycloak("http://127.0.0.1:8180", "moc", "tok", call=kc, http_error=FakeHTTPError)
        rows = [{"id": t["id"], "code": c, "name": t["name"]} for c, t in db.tenants.items()]
        enabled, done = tenants.organize(client, rows)
        self.assertTrue(enabled)
        self.assertEqual([(d["alias"], d["status"], d["members"]) for d in done], [("cntt", "created", 3),
                                                                                    ("kt", "created", 1)])
        writes = len(kc.writes())
        enabled, done = tenants.organize(client, rows)
        self.assertFalse(enabled)
        self.assertEqual([(d["status"], d["added"]) for d in done], [("kept", []), ("kept", [])])
        self.assertEqual(len(kc.writes()), writes)
        report = tenants.consistency(db._list(), list(kc.orgs.values()),
                                     {o: [{"id": u} for u in m] for o, m in kc.members.items()},
                                     list(kc.users.values()), db.core_users)
        self.assertTrue(report.ok, report.problems)


class CheckTest(unittest.TestCase):
    def check(self, kc: FakeKeycloak, db: FakeDB, *codes: str) -> tuple[int, dict[str, Any]]:
        code, out, _ = run_moc(kc, db, "tenant", "check", *codes, "--json")
        return code, json.loads(out)

    def test_seed_consistent(self) -> None:
        code, r = self.check(*seeded(), "CNTT", "KT")
        self.assertEqual(code, 0, r)
        self.assertEqual([(t["code"], t["organization"], t["members"], t["accounts"]) for t in r["tenants"]],
                         [("CNTT", "cntt", 3, 3), ("KT", "kt", 1, 1)])

    def test_account_missing_from_organization(self) -> None:
        kc, db = seeded()
        kc.add_user("moi", CNTT, "staff")
        db.sync()
        code, r = self.check(kc, db)
        self.assertEqual(code, 1)
        self.assertTrue(any("moi" in p and "chưa là thành viên" in p for p in r["problems"]), r["problems"])
        self.assertEqual({t["code"]: t["ok"] for t in r["tenants"]}, {"CNTT": False, "KT": True})

    def test_account_in_two_organizations(self) -> None:
        kc, db = seeded()
        vanthu = next(u for u, x in kc.users.items() if x["username"] == "vanthu")
        kt = next(o for o, x in kc.orgs.items() if x["alias"] == "kt")
        kc.members[kt].append(vanthu)
        code, r = self.check(kc, db)
        self.assertEqual(code, 1)
        self.assertEqual(sum("vanthu" in p for p in r["problems"]), 1)
        self.assertEqual({t["code"]: t["ok"] for t in r["tenants"]}, {"CNTT": False, "KT": False})

    def test_member_without_tenant_attribute(self) -> None:
        kc, db = seeded()
        stray = kc.add_user("khach", None, None)
        kc.members[next(o for o, x in kc.orgs.items() if x["alias"] == "kt")].append(stray)
        code, r = self.check(kc, db, "KT")
        self.assertEqual(code, 1)
        self.assertTrue(any("khach" in p and "tenant_id" in p for p in r["problems"]), r["problems"])

    def test_missing_and_duplicate_organization(self) -> None:
        kc, db = seeded()
        kt = next(o for o, x in kc.orgs.items() if x["alias"] == "kt")
        del kc.orgs[kt]
        kc.add_org("cntt-2", "Bản sao", CNTT)
        code, r = self.check(kc, db)
        self.assertEqual(code, 1)
        self.assertTrue(any(p.startswith("KT: chưa có Organization") for p in r["problems"]), r["problems"])
        self.assertTrue(any(p.startswith("CNTT: 2 Organization") for p in r["problems"]), r["problems"])

    def test_directory_lag(self) -> None:
        kc, db = seeded()
        kc.add_user("moi", KT, "staff")
        kc.members[next(o for o, x in kc.orgs.items() if x["alias"] == "kt")].append(
            next(u for u, x in kc.users.items() if x["username"] == "moi"))
        code, r = self.check(kc, db, "KT")                       # chưa db.sync(): danh bạ chưa có
        self.assertEqual(code, 1)
        self.assertTrue(any("core.users" in p for p in r["problems"]), r["problems"])
        db.sync()
        self.assertEqual(self.check(kc, db, "KT")[0], 0)

    def test_filter_ignores_other_tenants(self) -> None:
        kc, db = seeded()
        kc.add_user("moi", KT, "staff")                          # lỗi của KT
        db.sync()
        self.assertEqual(self.check(kc, db, "CNTT")[0], 0)
        code, r = self.check(kc, db, "XYZ")
        self.assertEqual(code, 1)
        self.assertIn("không có đơn vị mã XYZ", r["problems"][0])

    def test_realm_without_organizations(self) -> None:
        kc, db = seeded(organized=False)
        kc.realm["organizationsEnabled"] = False
        code, r = self.check(kc, db)
        self.assertEqual(code, 1)
        self.assertIn("chưa bật Organizations", r["problems"][0])


class ListTest(unittest.TestCase):
    def test_list(self) -> None:
        kc, db = seeded()
        code, out, _ = run_moc(kc, db, "tenant", "list", "--json")
        self.assertEqual(code, 0)
        rows = {t["code"]: t for t in json.loads(out)["tenants"]}
        self.assertEqual(rows["CNTT"]["organizations"][0]["alias"], "cntt")
        self.assertEqual(rows["CNTT"]["organizations"][0]["members"], 3)
        self.assertEqual(rows["KT"]["departments"], ["VP"])
        code, out, _ = run_moc(kc, db, "tenant", "list")
        self.assertEqual(code, 0)
        self.assertIn("Organization: cntt, 3 thành viên", out)


if __name__ == "__main__":
    unittest.main()
