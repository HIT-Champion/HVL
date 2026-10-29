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

"""Bộ định tuyến tất định của trợ lý hỏi đáp (F4.2, #423): chọn đường trả lời trước khi tìm văn bản.

Mô hình không chọn đường: thêm một lượt gọi vài giây trên CPU trước mọi câu, sai khó đoán, khó test. Ở đây là mẫu chữ
so trên câu hỏi đã bỏ dấu, viết thường; mỗi mẫu một mã lý do (``kw:<mẫu>``) trả về cho người hỏi và ghi sổ kiểm toán.
Không khớp mẫu nào thì về ``van_ban``, tìm trong kho như trước: tệ nhất là hành vi cũ.

- ``gioi_thieu``: câu về chính trợ lý (làm được gì, là ai, dùng mô hình nào), câu chào, cảm ơn → tệp Giới thiệu trợ lý.
- ``huong_dan``: hỏi cách dùng Signet ("ở đâu", "làm thế nào để" + việc trên phần mềm) → hướng dẫn sử dụng.
- ``ngoai_pham_vi``: thời tiết, giá vàng, viết mã… → câu cố định, không tìm, không gọi mô hình.
- ``viec_cua_toi`` (#441): việc của chính người hỏi ("việc nào của tôi sắp quá hạn", "tôi được giao gì") → đếm trong
  Hộp việc bằng token người hỏi (data.py), không tìm, không gọi mô hình.
- ``dem_van_ban`` (#441): "bao nhiêu", "số lượng", "thống kê" + văn bản hay tên loại → đếm văn bản người hỏi được xem.
- ``van_ban``: mặc định.

Câu có từ chỉ văn bản ("quyết định", "quy chế", "học bổng"…) không bao giờ thành ``gioi_thieu`` hay ``ngoai_pham_vi``:
"Em cần làm gì để được học bổng?" là câu hỏi về văn bản dù có "làm gì".

Câu nối tiếp (``follow_up``): có ``previous`` (câu hỏi lượt trước, máy chủ không lưu), câu mới ngắn (≤ 6 term) và có
dấu hiệu nối tiếp ("còn … thì sao", "thế còn", "nó", "văn bản đó") thì ghép với câu trước thành một câu độc lập, đọc
được, để tìm và hiện cho người hỏi ("Đã hiểu là: …"). Ghép bằng quy tắc, không gọi mô hình.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..vntext import fold
from . import data, vi

ROUTES = ("van_ban", "gioi_thieu", "huong_dan", "ngoai_pham_vi", "viec_cua_toi", "dem_van_ban")
DATA_ROUTES = ("viec_cua_toi", "dem_van_ban")
# đường không tìm đoạn, không gọi mô hình: trả lời ngay, cả ở lượt generate (không chờ lượt sinh)
DIRECT_ROUTES = ("gioi_thieu", "ngoai_pham_vi", *DATA_ROUTES)
DEFAULT_REASON = "mac-dinh"
FOLLOW_UP_MAX_TERMS = 6
MAX_REWRITTEN = 500         # như MAX_QUESTION của answer.py: dài hơn thì không ghép


@dataclass(frozen=True)
class Route:
    name: str               # một trong ROUTES
    reason: str             # kw:<mẫu> · mac-dinh
    lang: str = "vi"        # ngôn ngữ của mẫu đã khớp (vi · en): chọn bản Giới thiệu trợ lý, câu cố định


def folded(text: str) -> str:
    """Câu hỏi đem so mẫu: bỏ dấu, chữ thường, mỗi dấu câu thành dấu cách, gộp khoảng trắng."""
    return " ".join(re.sub(r"[^\w]+", " ", fold(vi.normalize(text)).lower()).split())


# Lời mở đầu không mang nghĩa: bỏ trước khi so các mẫu neo đầu câu
_LEAD_RE = re.compile(r"^(?:(?:xin )?cho (?:toi |minh |em |tui )?hoi(?: chut)?|xin hoi|toi muon hoi|hoi chut|a|oi)\s+")

# Từ chỉ văn bản, nội dung văn bản: có thì câu là câu hỏi về văn bản
DOC_WORDS_RE = re.compile(
    r"\b(?:van ban|cong van|quyet dinh|thong bao|quy che|quy dinh|ke hoach|nghi dinh|thong tu|chi thi|bao cao|"
    r"giay moi|to trinh|so ky hieu|hoc bong|hoc phi|hoc phan|sinh vien|giang vien|dieu \d+|khoan \d+)\b")

# Ngôi thứ hai: người hỏi gọi trợ lý
_YOU = r"(?:ban|em|tro ly(?: nay| ao| hoi dap| ai)?|signet|he thong nay|may)"

_INTRO: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("xin-chao", "vi", re.compile(rf"^(?:xin chao|chao)(?: {_YOU})?(?: a| nhe)?$")),
    ("cam-on", "vi", re.compile(rf"^cam on(?: {_YOU})?(?: nhieu| nhe| a)*$")),
    ("lam-duoc-gi", "vi", re.compile(
        rf"^{_YOU} (?:co the |biet |lam duoc |giup duoc |ho tro duoc )?(?:lam|giup|ho tro)(?: duoc)?"
        r"(?: (?:cho )?(?:toi|minh|em|tui))?(?: duoc)? (?:nhung )?(?:gi|viec gi|nhung gi|nhung viec gi)$")),
    ("la-ai", "vi", re.compile(rf"^{_YOU} (?:la ai|ten (?:la )?gi|la gi)$")),
    ("dung-mo-hinh", "vi", re.compile(
        rf"^{_YOU} (?:dung|chay(?: bang)?|la) (?:mo hinh|model|llm|ai|tri tue nhan tao)(?: nao| gi)?(?: vay)?$|"
        rf"^(?:mo hinh|model)(?: ai)? (?:cua )?{_YOU}(?: la)? (?:gi|nao)$")),
    ("hoi-the-nao", "vi", re.compile(
        rf"^(?:toi |minh |em )?(?:nen |phai )?(?:hoi|dung) {_YOU} (?:nhu )?(?:the nao|ra sao|sao)$|"
        rf"^(?:toi |minh |em )?nen hoi {_YOU}(?: nhung)? (?:gi|cau gi|the nao)$")),
    ("hello", "en", re.compile(r"^(?:hello|hi|hey)(?: there| assistant)?$")),
    ("thanks", "en", re.compile(r"^(?:thanks|thank you)(?: very much| so much)?$")),
    ("what-can-you-do", "en", re.compile(
        r"^(?:what can you do(?: for me)?|what do you do|how can you help(?: me)?|what are you able to do)$")),
    ("who-are-you", "en", re.compile(r"^(?:who|what) are you$")),
    ("which-model", "en", re.compile(
        r"^(?:which|what) (?:model|llm|ai)(?: model)? (?:do you use|are you(?: using)?)$")),
)

_OUT_OF_SCOPE: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("thoi-tiet", "vi", re.compile(
        r"\bthoi tiet\b(?:\s+\w+){0,4}\s+(?:hom nay|ngay mai|bay gio|tuan nay|cuoi tuan)\b|\bdu bao thoi tiet\b")),
    ("gia-ca", "vi", re.compile(r"\b(?:gia vang|ty gia|gia xang|gia bitcoin|chung khoan|co phieu|xo so|xsmb)\b")),
    ("the-thao", "vi", re.compile(r"\b(?:bong da|ket qua tran|ngoai hang anh|world cup)\b")),
    ("viet-ho", "vi", re.compile(
        r"\b(?:viet|sang tac|lam) (?:giup |ho |cho )?(?:toi |minh |em )?(?:mot )?"
        r"(?:bai tho|bai van|bai hat|cau chuyen|truyen ngan|code|doan code|ma nguon)\b|"
        r"\b(?:ke (?:chuyen|truyen) cuoi|truyen cuoi|cau do vui)\b|\bgiai (?:giup )?(?:bai tap|phuong trinh)\b")),
    ("weather", "en", re.compile(r"\bweather\b")),
    ("write-for-me", "en", re.compile(r"\b(?:write|tell) (?:me )?(?:a )?(?:poem|story|joke|song|code)\b")),
)

# Hỏi cách làm: dấu hiệu hỏi + (từ chỉ phần mềm hoặc tên chức năng). "Hướng dẫn" một mình là loại văn bản (HD, NĐ 30):
# chỉ là câu hỏi cách làm khi theo sau là "cách", "tôi", "sử dụng"…
_HOW_RE = re.compile(
    r"\b(?:o dau|cho nao|lam (?:the nao|sao|cach nao)|the nao de|lam sao de|bang cach nao|cach nao de|cach de|"
    r"huong dan (?:cach|toi|minh|em|su dung|lam)|cac buoc|nut nao|muc nao|trang nao|bam (?:vao )?dau|vao dau de)\b")
# Câu nhắc tới một văn bản cụ thể (số ký hiệu "12/HD-ĐHM", "88/CTSV", ngày "15/11/2026", "số 45") là câu về văn bản,
# kể cả khi có "ở đâu", "làm thế nào"
_DOC_REF_RE = re.compile(r"\d+[a-z]?/[a-z0-9]|\bso \d+")
# Số ký hiệu (chữ sau "/": "12/HD", "88/CTSV"), không phải ngày: câu đếm "tháng 9/2026" vẫn là câu đếm
_SYMBOL_RE = re.compile(r"\d+[a-z]?/[a-z]")
# huong_dan mà kho hướng dẫn không có mục nào khớp: tìm trong kho văn bản như van_ban (answer.py)
NO_GUIDE_REASON = "khong-khop-huong-dan"
_APP_RE = re.compile(r"\b(?:signet|phan mem|tren he thong|ung dung|giao dien|menu|thanh ben|hop viec|nut)\b")
_FEATURES_RE = re.compile(
    r"\b(?:nghi phep|don nghi|van ban di|van ban den|ky so|chu ky so|trinh ky|phat hanh van ban|vao so|"
    r"tiep nhan van ban|so dang ky|giao viec|phan cong|chuyen xu ly|du thao|ho so cong viec|nop luu|tim kiem|"
    r"hoi dap|dang nhap|dang xuat|mat khau|xac thuc hai buoc|ma xac thuc|totp|lich han|bang tin|"
    r"khong gian ca nhan|so kiem toan|gop y|doi ngon ngu|tieng anh|xac thuc van ban|so do cam bien)\b")

# Việc của chính người hỏi. Ngôi thứ nhất so trên chữ có dấu, viết thường: bỏ dấu thì "tôi" trùng "tới", "tối"
_ME = r"(?:tôi|mình|tui)"
_TASK = r"(?:việc|công việc|nhiệm vụ)"
_MY_TASKS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("viec-cua-toi", "vi", re.compile(rf"\b{_TASK}(?: \w+){{0,4}} của {_ME}\b")),
    ("toi-co-viec", "vi", re.compile(
        rf"\b{_ME} (?:có|còn|đang có|phải xử lý|cần xử lý)(?: \w+){{0,2}} {_TASK}\b")),
    ("duoc-giao", "vi", re.compile(
        rf"\b{_ME} (?:được|đang được) (?:giao|phân công)\b|\b(?:giao|phân công) cho {_ME}\b")),
    ("hop-viec", "vi", re.compile(r"\bhộp việc\b.*\b(?:bao nhiêu|mấy|quá hạn|đến hạn|hết hạn)\b")),
    ("my-tasks", "en", re.compile(r"\bmy (?:tasks?|work items?|assignments?|inbox)\b|\bassigned to me\b")),
)
# Đếm văn bản: từ hỏi số lượng rồi (trong hai từ) văn bản hay tên loại. Hai từ giữa không là giới từ hay đơn vị:
# "bao nhiêu năm theo thông tư", "mấy giờ thì văn bản…" hỏi nội dung, không hỏi số văn bản
_NOT_BETWEEN = ("theo trong của tại ở là cho từ về như thì "
                "ngày năm tháng giờ phút lần trang điều khoản người tiền").split()


def _between(words: list[str]) -> str:
    return rf"(?: (?!(?:{'|'.join(words)})\b)\w+){{0,2}}"


_COUNT: tuple[tuple[str, str, re.Pattern[str]], ...] = (                # chữ đã bỏ dấu
    ("dem-van-ban", "vi", re.compile(
        rf"\b(?:bao nhieu|so luong|tong so|tong cong|thong ke){_between([fold(w) for w in _NOT_BETWEEN])} "
        rf"(?:{data.NOUNS})\b|^so (?:luong )?(?:{data.NOUNS})\b")),
    ("how-many", "en", re.compile(
        r"\b(?:how many|number of|count)(?: \w+){0,2} (?:documents?|letters|decisions|notices|circulars)\b")),
)
# "đếm", "mấy" so trên chữ có dấu: bỏ dấu thì trùng "đêm", "máy" ("Đêm qua có văn bản nào…", "Máy chủ lưu văn bản…")
_COUNT_MARKED: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("dem-van-ban", "vi", re.compile(
        rf"\b(?:đếm|mấy){_between(_NOT_BETWEEN)} (?:văn bản|{'|'.join(t[2] for t in data.TYPES)})\b")),
)


def _data_route(question: str, text: str, marked: str) -> Route | None:
    """``viec_cua_toi``, ``dem_van_ban``; None khi không khớp. ``text``: câu đã bỏ dấu (``folded``); ``marked``: bỏ
    dấu, còn dấu câu. Câu đếm có mốc thời gian chưa đọc được thì không nhận (data.UNSUPPORTED_RE)."""
    lower = " ".join(re.sub(r"[^\w]+", " ", vi.normalize(question).lower()).split())
    if not DOC_WORDS_RE.search(text):
        for code, lang, pattern in _MY_TASKS:
            if pattern.search(text if lang == "en" else lower):
                return Route("viec_cua_toi", f"kw:{code}", lang)
    for patterns, against in ((_COUNT, text), (_COUNT_MARKED, lower)):
        for code, lang, pattern in patterns:
            if pattern.search(against) and not data.UNSUPPORTED_RE.search(marked):
                return Route("dem_van_ban", f"kw:{code}", lang)
    return None


def route(question: str, *, scoped: bool = False) -> Route:
    """Đường của một câu hỏi (đã ghép nếu là câu nối tiếp). ``scoped``: đang hỏi trong một văn bản ("Hỏi về văn bản
    này") — khi đó câu "ở đâu", "thế nào" là về văn bản đó, không thành ``huong_dan`` hay đường dữ liệu."""
    text = _LEAD_RE.sub("", folded(question))
    if not DOC_WORDS_RE.search(text):
        for code, lang, pattern in _INTRO:
            if pattern.search(text):
                return Route("gioi_thieu", f"kw:{code}", lang)
        for code, lang, pattern in _OUT_OF_SCOPE:
            if pattern.search(text):
                return Route("ngoai_pham_vi", f"kw:{code}", lang)
    marked = fold(vi.normalize(question)).lower()          # giữ "/" của số ký hiệu
    if not scoped and not _DOC_REF_RE.search(marked):
        how = _HOW_RE.search(text)
        if how and (_APP_RE.search(text) or _FEATURES_RE.search(text)):
            return Route("huong_dan", "kw:" + how.group(0).replace(" ", "-"))
    if not scoped and not _SYMBOL_RE.search(marked):
        found = _data_route(question, text, marked)
        if found is not None:
            return found
    return Route("van_ban", DEFAULT_REASON)


# --- câu nối tiếp ------------------------------------------------------------------------------------------------

# "còn khoa Kinh tế thì sao?", "thế còn năm 2025?", "vậy còn sinh viên năm nhất": phần sau "còn" thay vào câu trước
_CON_LEAD_RE = re.compile(r"^(?:(?:the|vay|the thi|vay thi) )?con (?:ve |doi voi )?", re.IGNORECASE)
_CON_TAIL_RE = re.compile(r"(?: (?:thi sao|thi the nao|thi nhu the nao|thi sao a|thi))$", re.IGNORECASE)
# "thì sao" đứng cuối mới là câu nối tiếp khi không mở đầu bằng "thế còn", "vậy còn": "còn bao nhiêu ngày" thì không
_CON_STRONG_RE = re.compile(r"^(?:the|vay) con ", re.IGNORECASE)
# Đại từ trỏ về câu trước: so trên chữ có dấu (bỏ dấu thì "nó" trùng "nợ", "đó" trùng "do")
_PRONOUN_RE = re.compile(
    r"\b(?:nó|văn bản (?:đó|này|trên|vừa rồi)|quyết định (?:đó|này|trên)|công văn (?:đó|này|trên)|"
    r"thông báo (?:đó|này|trên)|điều (?:đó|này)|cái (?:đó|này)|van ban (?:nay|tren))\b", re.IGNORECASE)
_EN_ABOUT_RE = re.compile(r"^(?:what|how) about ", re.IGNORECASE)
_EN_PRONOUN_RE = re.compile(r"\b(?:it|that document|this document)\b", re.IGNORECASE)
_TRAIL_RE = re.compile(r"[\s?.!…,;:]+$")


def _strip_trail(text: str) -> str:
    return _TRAIL_RE.sub("", text)


# động từ hay đứng sau cụm danh từ của câu hỏi: cụm bị thay dừng trước chúng ("… đại học quy định gì …")
_PHRASE_END = {("quy", "định"), ("ban", "hành"), ("áp", "dụng"), ("hướng", "dẫn")}


def _splice(previous: str, rest: str) -> str:
    """Thay cụm danh từ của câu trước bằng ``rest`` (phần sau "còn") khi term đầu của ``rest`` có trong câu trước.

    "Điều kiện xét học bổng khoa CNTT là gì?" + "khoa Kinh tế" → "Điều kiện xét học bổng khoa Kinh tế là gì". Không
    neo được (term đầu là từ dừng, hoặc câu trước không có) thì nối ``rest`` vào cuối câu trước: neo ở term giữa cụm
    làm nát câu ("Kỳ thi …" + "hạn nộp đề thi" → "Kỳ hạn nộp đề thi …")."""
    prev = _strip_trail(previous)
    rest_tokens = list(vi.TOKEN_RE.finditer(rest))
    prev_tokens = list(vi.TOKEN_RE.finditer(prev))
    # so chữ thường giữ dấu, không qua term_key: bỏ dấu thì "tự" và "từ" thành một
    prev_words = [None if m.group(0).lower() in vi.STOPWORDS else m.group(0).lower() for m in prev_tokens]
    first = rest_tokens[0].group(0).lower() if rest_tokens else ""
    if first and first not in vi.STOPWORDS and first in prev_words:
        j = prev_words.index(first)
        words = [m.group(0).lower() for m in prev_tokens] + [""]
        end = j + 1             # cụm danh từ: các token liền sau không phải từ dừng, chưa tới động từ
        while (end < len(prev_tokens) and words[end] not in vi.STOPWORDS
               and (words[end], words[end + 1]) not in _PHRASE_END):
            end += 1
        return vi.normalize(prev[: prev_tokens[j].start()] + rest + prev[prev_tokens[end - 1].end():])
    return vi.normalize(f"{prev}, {rest}")


def follow_up(question: str, previous: str | None) -> str | None:
    """Câu độc lập ghép từ câu nối tiếp và câu trước, hoặc None khi ``question`` không phải câu nối tiếp.

    ``question``, ``previous`` đã chuẩn hóa (``vi.normalize``). Câu ghép dài quá ``MAX_REWRITTEN`` thì không ghép."""
    if not previous or not vi.terms(previous) or len(vi.terms(question)) > FOLLOW_UP_MAX_TERMS:
        return None
    q = _strip_trail(question)
    out: str | None = None
    flat = fold(q)
    lead = _CON_LEAD_RE.match(flat)
    tail = _CON_TAIL_RE.search(flat)
    if lead and (tail or _CON_STRONG_RE.match(flat)):
        rest = q[lead.end(): tail.start() if tail else len(q)].strip(" ,")
        if vi.terms(rest):
            out = _splice(previous, rest)
    elif _EN_ABOUT_RE.match(q):
        rest = q[_EN_ABOUT_RE.match(q).end():].strip(" ,")    # type: ignore[union-attr]
        if vi.terms(rest):
            out = _splice(previous, rest)
    else:
        pronoun = _PRONOUN_RE.search(q) or _EN_PRONOUN_RE.search(q)
        if pronoun:
            subject = vi.keyword_query(previous)
            out = vi.normalize(q[: pronoun.start()] + subject + q[pronoun.end():])
    if out is None or len(out) > MAX_REWRITTEN or vi.normalize(out).casefold() == q.casefold():
        return None
    return out
