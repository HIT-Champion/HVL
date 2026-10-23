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

"""Gợi ý đơn vị chủ trì và hạn cho văn bản đến (F4.3): bỏ phiếu theo văn bản tương tự đã giao — hàm thuần, không I/O.

Đầu vào là các văn bản đến tương tự (svc-files tìm theo trích yếu, điểm ``_rankingScore`` 0..1) và đơn vị chủ trì
lúc trước của chúng. Mỗi văn bản đủ điểm là một căn cứ, bỏ phiếu cho đơn vị đã chủ trì nó với trọng số bằng điểm
(kNN có trọng số). Chỉ đơn vị có lãnh đạo phòng đang bật mới được gợi ý — đúng điều kiện chỉ đạo không báo
``no_manager``. Độ tin cậy theo số căn cứ ủng hộ và tỉ phần phiếu; hạn theo trung vị số ngày các căn cứ ủng hộ đã có.

Không cần mô hình: giải thích được ("vì 3 văn bản tương tự đã giao Tổ Đào tạo"), tốt dần khi có thêm dữ liệu.
Căn cứ chỉ mang id, điểm, đơn vị, số ngày — không có chữ của văn bản nào.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Literal

VN = timezone(timedelta(hours=7))  # Việt Nam không đổi giờ mùa hè; không phụ thuộc tzdata của image
TOP_K = 5  # số căn cứ tối đa được bỏ phiếu và lưu (CSDL chặn mảng căn cứ > 5 phần tử)
MAX_DAYS = 365

# độ tin cậy: (số căn cứ ủng hộ tối thiểu, tỉ phần phiếu tối thiểu), xét từ cao xuống thấp
CONFIDENCE: tuple[tuple[Literal["high", "medium", "low"], int, float], ...] = (
    ("high", 3, 0.7),
    ("medium", 2, 0.5),
    ("low", 1, 0.4),
)


@dataclass(frozen=True)
class Hit:
    """Văn bản tương tự svc-files tìm được, điểm giảm dần."""

    document_id: str
    score: float


@dataclass(frozen=True)
class Past:
    """Văn bản đã giao: đơn vị chủ trì (phòng, hoặc phòng của người được giao thẳng) và số ngày được cho."""

    document_id: str
    department_id: str | None
    days: int | None


@dataclass(frozen=True)
class Evidence:
    document_id: str
    score: float
    department_id: str
    days: int | None


@dataclass(frozen=True)
class Suggestion:
    status: Literal["suggested", "none"]
    reason: str | None
    department_id: str | None
    confidence: Literal["high", "medium", "low"] | None
    share: float | None
    due_days: int | None
    due_on: date | None
    evidence: tuple[Evidence, ...]
    ranking: tuple[str, ...]
    candidates: int


def vn_date(ts: str) -> date:
    """ISO timestamptz → ngày theo giờ Việt Nam (vào sổ 00:30 sáng giờ VN là 17:30 UTC hôm trước)."""
    moment = datetime.fromisoformat(ts)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(VN).date()


def past_days(registered_at: str, due_on: str | None) -> int | None:
    """Số ngày từ lúc vào sổ (giờ VN) tới hạn; None nếu thiếu, sai dạng, hoặc ngoài 1..365 (hạn lùi, nhập nhầm năm)."""
    if not registered_at or not due_on:
        return None
    try:
        days = (date.fromisoformat(due_on) - vn_date(registered_at)).days
    except (TypeError, ValueError):
        return None
    return days if 1 <= days <= MAX_DAYS else None


def next_workday(d: date) -> date:
    """Thứ Bảy, Chủ nhật → thứ Hai. Chưa xét ngày lễ (chưa có lịch nghỉ)."""
    return d + timedelta(days=7 - d.weekday()) if d.weekday() >= 5 else d


def lead_unit(lead: dict | None, user_departments: dict[str, str]) -> str | None:
    """Đơn vị chủ trì của một lần giao: phòng được giao, hoặc phòng của người được giao thẳng."""
    if not lead:
        return None
    if lead.get("department_id"):
        return str(lead["department_id"])
    return user_departments.get(lead.get("user_id") or "")


def _rank(weight: dict[str, float], best: dict[str, float]) -> list[str]:
    # trọng số giảm dần; hòa thì điểm đơn lẻ cao nhất; vẫn hòa thì id nhỏ hơn — kết quả không phụ thuộc thứ tự vào
    return sorted(weight, key=lambda u: (-weight[u], -best[u], u))


def _none(reason: str, candidates: int, ranking: tuple[str, ...] = ()) -> Suggestion:
    return Suggestion("none", reason, None, None, None, None, None, (), ranking, candidates)


def suggest(hits: list[Hit], history: dict[str, Past], units: set[str], *, min_score: float,
            registered_on: date, doc_due: date | None, today: date) -> Suggestion:
    """Bỏ phiếu đơn vị chủ trì và hạn cho văn bản vào sổ ngày ``registered_on``.

    hits: văn bản tương tự (đã loại chính nó, đã loại văn bản hạn chế); history: id → lần giao chủ trì đầu tiên;
    units: đơn vị có lãnh đạo phòng đang bật; doc_due: hạn ghi trên văn bản — có thì không gợi ý hạn.
    """
    candidates = len(hits)
    # điểm 0 không nói gì về độ giống; mỗi văn bản một phiếu (giữ điểm cao nhất nếu bị trả trùng)
    kept: dict[str, float] = {}
    for hit in hits:
        if hit.score >= min_score and hit.score > 0 and hit.score > kept.get(hit.document_id, -1.0):
            kept[hit.document_id] = hit.score
    if not kept:
        return _none("no_similar", candidates)
    basis = {d: s for d, s in kept.items() if d in history and history[d].department_id is not None}
    if not basis:
        return _none("no_history", candidates)
    valid = {d: s for d, s in basis.items() if history[d].department_id in units}
    if not valid:
        return _none("no_valid_unit", candidates)

    top = sorted(valid.items(), key=lambda item: (-item[1], item[0]))[:TOP_K]
    evidence = tuple(Evidence(d, s, str(history[d].department_id), history[d].days) for d, s in top)
    weight: dict[str, float] = {}
    best: dict[str, float] = {}
    for e in evidence:
        weight[e.department_id] = weight.get(e.department_id, 0.0) + e.score
        best[e.department_id] = max(best.get(e.department_id, 0.0), e.score)
    ranking = tuple(_rank(weight, best))
    winner = ranking[0]
    # làm tròn trước khi so ngưỡng: 0.7 không thành 0.6999… vì cộng số thực
    share = round(weight[winner] / sum(weight.values()), 3)
    backing = [e for e in evidence if e.department_id == winner]
    confidence = next((name for name, n, s in CONFIDENCE if len(backing) >= n and share >= s), None)
    if confidence is None:
        return _none("low_confidence", candidates, ranking)

    due_days: int | None = None
    due_on: date | None = None
    days = [e.days for e in backing if e.days is not None]
    if doc_due is None and days:
        due_days = statistics.median_low(days)
        # hạn rơi vào cuối tuần thì sang thứ Hai; vào sổ đã lâu thì hạn sớm nhất là ngày mai (vẫn là ngày làm việc)
        due_on = next_workday(max(registered_on + timedelta(days=due_days), today + timedelta(days=1)))
    return Suggestion("suggested", None, winner, confidence, share, due_days, due_on, evidence, ranking, candidates)
