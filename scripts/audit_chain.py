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

"""Kiểm sổ kiểm toán chuỗi băm từ bên ngoài CSDL (F2.12) — chỉ dùng thư viện chuẩn.

Dùng chung cho lệnh ``moc audit verify`` (scripts/moc.py) và test CSDL (db/tests/test_audit.py). Không gọi
core.audit_verify(): superuser sửa được cả hàm đó. PostgreSQL chỉ dựng chuỗi JSON của từng dòng bằng hàm có sẵn
(pg_catalog.jsonb_build_array, cùng biểu thức với core.audit_hash); băm và so chuỗi tính ở đây.

Ba lớp kiểm:

1. Chuỗi: id liên tiếp từ 1, prev_hash bằng hash dòng trước, hash bằng sha256(prev_hash ‖ nội dung dòng), đầu
   chuỗi trỏ vào dòng cuối. Sửa một dòng (kể cả tắt trigger) thì lớp này chỉ ra đúng dòng đó.
2. Mốc neo: hash của dòng tại mỗi mốc phải bằng hash đã neo ra ngoài CSDL. Sửa một dòng rồi tính lại cả chuỗi
   phía sau thì lớp 1 không thấy gì, nhưng mọi mốc từ dòng đó trở đi lệch: dòng bị sửa nằm giữa mốc cuối cùng
   còn khớp và mốc đầu tiên bị lệch.
3. Văn bản có hash (văn bản đi đã phát hành): content_sha256 trong office.documents phải bằng giá trị lần
   cuối ghi vào sổ. Đổi hash trong CSDL (để một tệp giả "khớp" ở cổng xác thực) mà tắt trigger thì lớp này thấy.

Mọi câu SELECT dưới đây phải đọc trong cùng một giao dịch REPEATABLE READ (scripts/moc.py làm vậy): đọc đầu chuỗi
và các dòng ở hai lúc khác nhau thì dòng mới ghi chen giữa trông như "đầu chuỗi trỏ sai".
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

GENESIS = "00" * 32

# Mỗi lệnh trả một cột JSON mỗi dòng
ROWS_SQL = """
select json_build_object(
  'id', l.id, 'prev', encode(l.prev_hash, 'hex'), 'hash', encode(l.hash, 'hex'),
  'payload', pg_catalog.jsonb_build_array(l.id, extract(epoch from l.occurred_at), l.tenant_id, l.actor_id,
             l.actor_kind, l.request_id, l.action, l.entity, l.entity_id, l.diff)::text
)::text
from core.audit_log l order by l.id
"""

HEAD_SQL = "select json_build_object('id', last_id, 'hash', encode(last_hash, 'hex'))::text from core.audit_head"

# Bảng tra cứu các lần neo: mỗi dòng phải có mốc tương ứng ngoài CSDL
ANCHORS_SQL = """
select json_build_object('audit_id', audit_id, 'hash', encode(hash, 'hex'), 'location', location,
                         'anchored_at', anchored_at)::text
from core.audit_anchors order by audit_id
"""

# Lần khôi phục từ bản sao lưu (moc backup restore, F3.4) thành một dòng sổ của nền tảng (tenant_id null), nối tiếp
# chuỗi vừa khôi phục: sổ cho thấy các dòng ghi sau lúc sao lưu không còn là vì khôi phục, không phải vì bị xóa lén.
# Biến psql: actor, run, diff (JSON).
RESTORED_SQL = """
insert into core.audit_log (tenant_id, actor_id, actor_kind, action, entity, entity_id, diff)
values (null, :'actor', 'system', 'system.restored', 'backup', :'run', :'diff'::jsonb)
returning id;
"""

# Lúc đọc (đầu giao dịch): mốc neo sau lúc này chưa thể có dòng của nó trong lần đọc
NOW_SQL = "select json_build_object('now', extract(epoch from now()))::text"

DOCUMENTS_SQL = """
select json_build_object('id', d.id, 'symbol', d.symbol, 'summary', d.summary,
                         'sha256', encode(d.content_sha256, 'hex'))::text
from office.documents d where d.content_sha256 is not null order by d.created_at
"""


@dataclass
class Problem:
    kind: str  # gap | prev_hash | hash | head | anchor | anchor_missing | anchor_tampered | anchor_unbacked | document
    audit_id: int | None
    message: str


@dataclass
class Report:
    rows: int = 0
    last_id: int = 0
    last_hash: str = GENESIS
    problems: list[Problem] = field(default_factory=list)
    anchors: dict[str, dict[str, int]] = field(default_factory=dict)   # nguồn → {checked, matched}
    latest_anchor: dict[str, Any] | None = None     # mốc khớp mới nhất
    rewritten: tuple[int, int] | None = None        # khoảng dòng bị viết lại, suy từ mốc
    documents: int = 0
    later: int = 0                                  # mốc neo sau lúc đọc CSDL, bỏ qua lần này
    restores: list[dict[str, Any]] = field(default_factory=list)   # dòng system.restored (moc backup restore)

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def unanchored(self) -> int:
        """Số dòng sau mốc khớp mới nhất — phần chuỗi chưa có bản ngoài CSDL."""
        return self.last_id - (self.latest_anchor["audit_id"] if self.latest_anchor else 0)


def _strip_bytea(value: Any) -> str | None:
    return value[2:] if isinstance(value, str) and value.startswith("\\x") else value


def to_datetime(value: Any) -> datetime | None:
    """Từ epoch (giây) hoặc chuỗi ISO 8601 có múi giờ; không đọc được thì None."""
    try:
        if isinstance(value, int | float) or (isinstance(value, str) and value.replace(".", "", 1).isdigit()):
            return datetime.fromtimestamp(float(value), timezone.utc)
        at = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return at if at.tzinfo else at.astimezone()


def local_time(value: Any) -> str:
    """Giờ máy chủ, dd/mm/yyyy hh:mm:ss."""
    at = to_datetime(value)
    return at.astimezone().strftime("%d/%m/%Y %H:%M:%S") if at else str(value)


def _where(payload: list[Any]) -> str:
    """Mô tả ngắn của một dòng sổ để chỉ cho người đọc."""
    _id, at, _tenant, actor, _kind, _req, action, entity, entity_id, _diff = payload
    return f"{entity} {entity_id} ({action}, {actor}, {local_time(at)})"


def check(rows: Iterable[dict[str, Any]], head: dict[str, Any], anchors: Iterable[dict[str, Any]] = (),
          documents: Iterable[dict[str, Any]] = (), *, recorded: Iterable[dict[str, Any]] | None = None,
          as_of: float | str | None = None) -> Report:
    """rows: theo ROWS_SQL, đúng thứ tự id; head: HEAD_SQL; anchors: mốc ngoài CSDL {audit_id, hash, source,
    anchored_at?, overwritten?, deleted?}; documents: DOCUMENTS_SQL; recorded: ANCHORS_SQL — mỗi dòng phải có mốc
    trong `anchors`; as_of: NOW_SQL — mốc neo sau lúc này (trừ 2 giây cho độ phân giải giờ của kho) chưa đối chiếu
    được với lần đọc này, bỏ qua."""
    report = Report()
    anchors = list(anchors)
    outside = {(int(a["audit_id"]), a["hash"]) for a in anchors}
    start = to_datetime(as_of) if as_of is not None else None
    if start is not None:
        cutoff = start - timedelta(seconds=2)
        fresh = [a for a in anchors if (to_datetime(a.get("anchored_at")) or cutoff) > cutoff]
        report.later = len(fresh)
        anchors = [a for a in anchors if a not in fresh]
    anchors.sort(key=lambda a: int(a["audit_id"]))
    wanted = {int(a["audit_id"]) for a in anchors}
    seen: dict[int, str] = {}               # id → hash, chỉ giữ dòng có mốc
    doc_hash: dict[str, tuple[int, str | None]] = {}
    expect_id, expect_prev = 1, GENESIS

    for row in rows:
        rid, prev, stored, text = int(row["id"]), row["prev"], row["hash"], row["payload"]
        payload = json.loads(text)
        report.rows += 1
        if rid != expect_id:
            report.problems.append(Problem(
                "gap", rid, f"thiếu dòng #{expect_id}…#{rid - 1} ngay trước #{rid} (đã bị xóa)"))
        if prev != expect_prev:
            report.problems.append(Problem(
                "prev_hash", rid, f"#{rid} không nối vào dòng trước: dòng trước bị sửa cả hash, hoặc bị xóa"))
        if hashlib.sha256(bytes.fromhex(prev) + text.encode()).hexdigest() != stored:
            report.problems.append(Problem(
                "hash", rid, f"#{rid} {_where(payload)}: nội dung không khớp hash của chính nó — dòng này đã bị sửa"))
        if rid in wanted:
            seen[rid] = stored
        action, entity, entity_id, diff = payload[6], payload[7], payload[8], payload[9]
        if action == "system.restored" and isinstance(diff, dict):
            report.restores.append({"id": rid, "run": entity_id, "audit_id": diff.get("audit_id"), "at": payload[1]})
        # chỉ dòng do trigger core.audit() ghi: diff là {cột: [cũ, mới]}; sự kiện dịch vụ tự ghi thì bỏ qua
        change = diff.get("content_sha256") if isinstance(diff, dict) else None
        if (entity == "office.documents" and action in {"insert", "update", "delete"}
                and isinstance(change, list) and len(change) == 2):
            doc_hash[entity_id] = (rid, _strip_bytea(change[1]))
        expect_id, expect_prev = rid + 1, stored

    report.last_id, report.last_hash = expect_id - 1, expect_prev
    if int(head["id"]) != report.last_id or head["hash"] != report.last_hash:
        report.problems.append(Problem(
            "head", int(head["id"]),
            f"đầu chuỗi trỏ vào #{head['id']} nhưng dòng cuối là #{report.last_id}: các dòng cuối đã bị xóa"))

    _check_anchors(report, anchors, seen)

    for r in recorded or ():
        if (int(r["audit_id"]), r["hash"]) not in outside:
            report.problems.append(Problem(
                "anchor_unbacked", int(r["audit_id"]),
                f"CSDL ghi đã neo dòng #{r['audit_id']} vào {r['location']} nhưng ngoài CSDL không có mốc này — mốc"
                " bị xóa khỏi kho, hoặc dòng tra cứu bị thêm giả"))

    for doc in documents:
        report.documents += 1
        name = doc.get("symbol") or (doc.get("summary") or "")[:60] or doc["id"]
        logged = doc_hash.get(doc["id"])
        if logged is None:
            report.problems.append(Problem(
                "document", None, f"văn bản {name} ({doc['id']}): hash không có trong sổ — được ghi khi tắt trigger"))
        elif logged[1] != doc["sha256"]:
            report.problems.append(Problem(
                "document", logged[0],
                f"văn bản {name} ({doc['id']}): hash trong CSDL khác hash ghi trong sổ ở dòng #{logged[0]}"))
    return report


def _check_anchors(report: Report, anchors: list[dict[str, Any]], seen: dict[int, str]) -> None:
    last_good = 0
    for a in anchors:
        aid, source = int(a["audit_id"]), a.get("source", "?")
        stats = report.anchors.setdefault(source, {"checked": 0, "matched": 0})
        stats["checked"] += 1
        at = f", neo lúc {local_time(a['anchored_at'])}" if a.get("anchored_at") else ""
        label = f"mốc #{aid} ({source}{at})"
        if a.get("overwritten") or a.get("deleted"):
            report.problems.append(Problem(
                "anchor_tampered", aid, f"{label} đã bị ghi đè hoặc xóa sau khi neo — kho vẫn giữ bản gốc"))
        if aid > report.last_id or aid not in seen:
            report.problems.append(Problem(
                "anchor_missing", aid, f"{label}: dòng #{aid} không còn trong CSDL — chuỗi đã bị cắt"))
            continue
        if seen[aid] != a["hash"]:
            report.problems.append(Problem("anchor", aid, f"{label}: khác hash hiện tại của dòng #{aid}"))
            if report.rewritten is None:
                report.rewritten = (last_good + 1, aid)
            continue
        stats["matched"] += 1
        if report.rewritten is None:
            last_good = aid
        if report.latest_anchor is None or aid >= report.latest_anchor["audit_id"]:
            report.latest_anchor = {"audit_id": aid, "anchored_at": a.get("anchored_at"), "source": source}
