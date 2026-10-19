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

"""Dữ liệu của từng loại việc (formKey trong BPMN) — lớp kiểm thứ hai của poka-yoke (F2.2).

Giao diện kiểm trước, svc-workflow kiểm lại ở đây, CSDL chặn lần cuối bằng ràng buộc CHECK. Trường lạ bị
từ chối (extra="forbid") để client không lén gửi thêm cột.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class _Form(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChiDao(_Form):
    """vbden.chiDao, outcome = direct: giao một phòng chủ trì, hoặc giao thẳng một người."""

    instruction: Annotated[Text, Field(max_length=2000)]
    lead_department_id: uuid.UUID | None = None
    lead_user_id: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    supports: Annotated[list[uuid.UUID], Field(max_length=20)] = []
    due_on: date | None = None

    @model_validator(mode="after")
    def _one_lead(self) -> ChiDao:
        if (self.lead_department_id is None) == (self.lead_user_id is None):
            raise ValueError("chọn đúng một nơi chủ trì: một phòng hoặc một người")
        if self.lead_department_id in self.supports:
            raise ValueError("phòng chủ trì không đồng thời là phòng phối hợp")
        if len(set(self.supports)) != len(self.supports):
            raise ValueError("phòng phối hợp bị lặp")
        return self


class Note(_Form):
    """vbden.chiDao, outcome = file (lưu, không xử lý); vbden.phanCong, outcome = self."""

    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None


class PhanCong(_Form):
    """vbden.phanCong, outcome = assign: lãnh đạo phòng giao cho một người trong phòng."""

    user_id: Annotated[str, Field(min_length=1, max_length=64)]
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None


class XuLy(_Form):
    """vbden.xuLy, outcome = done: người xử lý báo kết quả."""

    result_note: Annotated[Text, Field(max_length=4000)]


class TraLai(_Form):
    """vbdi.duyetPhong, vbdi.duyetDonVi, outcome = return: trả dự thảo về người soạn, phải nói rõ sửa gì."""

    note: Annotated[Text, Field(max_length=2000)]


class PhatHanh(_Form):
    """vbdi.phatHanh, outcome = issue: văn thư cấp số, phát hành; is_public cho cổng xác thực hiện trích yếu."""

    is_public: bool = False


# formKey → outcome → kiểu dữ liệu. vbdi.chinhSua không có ở đây: người soạn sửa xong thì trình lại bằng
# Action submitOutgoing, không hoàn thành việc bằng completeTask.
FORMS: dict[str, dict[str, type[_Form]]] = {
    "vbden.chiDao": {"direct": ChiDao, "file": Note},
    "vbden.phanCong": {"assign": PhanCong, "self": Note},
    "vbden.xuLy": {"done": XuLy},
    "vbdi.duyetPhong": {"approve": Note, "return": TraLai},
    "vbdi.duyetDonVi": {"approve": Note, "return": TraLai},
    "vbdi.phatHanh": {"issue": PhatHanh},
}
