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

"""core.file_texts — lớp chữ của PDF để tìm theo nội dung (F2.7, migration 1792281601000)."""

import pytest

from conftest import SQLError, incoming, insert_file, received, sql


def test_no_user_role_reads_pdf_texts(world):
    file_id = insert_file(world.service_a, world.clerk_a)
    sql(f"insert into core.file_texts (file_id, tenant_id, status, pages, content) "
        f"values ('{file_id}', '{world.tenant_a}', 'ok', 1, 'Danh sách nâng lương')")
    for user in (world.clerk_a, world.director_a, world.manager_a1, world.staff_a1, world.admin_a):
        assert "errors" in user.raw("{ core_file_texts { content } }")
        assert "errors" in user.raw("{ core_files { id text { content } } }")      # cả qua quan hệ của tệp


def test_texts_follow_their_file(world):
    file_id = insert_file(world.service_a, world.clerk_a)
    sql(f"insert into core.file_texts (file_id, tenant_id, status) values ('{file_id}', '{world.tenant_a}', 'empty')")
    with pytest.raises(SQLError, match="foreign key"):     # chữ phải cùng thuê ước với tệp
        sql(f"insert into core.file_texts (file_id, tenant_id, status) "
            f"values ('{insert_file(world.service_a, world.clerk_a)}', '{world.tenant_b}', 'empty')")
    sql(f"delete from core.files where id = '{file_id}'")
    assert sql(f"select count(*) from core.file_texts where file_id = '{file_id}'") == [["0"]]


@pytest.mark.parametrize(("status", "content"), [
    ("ok", ""),                     # ok mà không có chữ
    ("empty", "có chữ"),            # empty mà có chữ
    ("failed", "có chữ"),
    ("ok", "a" * 50_001),           # quá giới hạn
    ("scan", ""),                   # trạng thái lạ
])
def test_status_and_content_agree(world, status, content):
    file_id = insert_file(world.service_a, world.clerk_a)
    with pytest.raises(SQLError, match="violates check constraint"):
        sql(f"insert into core.file_texts (file_id, tenant_id, status, content) "
            f"values ('{file_id}', '{world.tenant_a}', '{status}', '{content}')")


def _attach(world, doc_id: str, file_id: str, role: str = "main") -> None:
    sql(f"insert into office.document_files (tenant_id, document_id, file_id, role, added_by) "
        f"values ('{world.tenant_a}', '{doc_id}', '{file_id}', '{role}', '{world.clerk_a.sub}')")


def _text(world, file_id: str) -> None:
    sql(f"insert into core.file_texts (file_id, tenant_id, status, pages, content) "
        f"values ('{file_id}', '{world.tenant_a}', 'ok', 1, 'Danh sách nâng lương trước hạn')")


def _count(file_id: str) -> str:
    return sql(f"select count(*) from core.file_texts where file_id = '{file_id}'")[0][0]


def test_texts_of_restricted_documents_are_never_stored(world):
    doc = received(world.clerk_a, incoming(world.tag, 301, restricted=True))
    file_id = insert_file(world.service_a, world.clerk_a, encrypted=True)
    _attach(world, doc["id"], file_id)
    _text(world, file_id)                            # bỏ qua, không báo lỗi: svc-files không kẹt ở tệp này
    assert _count(file_id) == "0"


def test_encrypted_files_never_get_texts_even_before_attaching(world):
    file_id = insert_file(world.service_a, world.clerk_a, encrypted=True)
    _text(world, file_id)
    assert _count(file_id) == "0"


# Văn bản hạn chế có từ trước F3.7 có thể mang tệp rõ. Nay trigger document_files_sealed và
# documents_restricted_sealed (migration 1792281601600) chặn hai đường dưới; tắt chúng trong cùng giao dịch để
# kiểm phần dọn lớp chữ của F2.7 vẫn đúng cho dữ liệu cũ.
def _legacy(statement: str, trigger: str, table: str) -> None:
    sql(f"alter table {table} disable trigger {trigger}; {statement}; alter table {table} enable trigger {trigger}")


def test_restricting_a_document_drops_texts_already_read(world):
    doc = received(world.clerk_a, incoming(world.tag, 302))
    file_id = insert_file(world.service_a, world.clerk_a)
    _attach(world, doc["id"], file_id)
    _text(world, file_id)
    assert _count(file_id) == "1"
    sql(f"update office.documents set summary = summary || ' (sửa)' where id = '{doc['id']}'")
    assert _count(file_id) == "1"                    # sửa trường khác: giữ nguyên
    with pytest.raises(SQLError, match="documents_restricted_sealed"):   # tệp rõ không tự mã hóa lại được
        sql(f"update office.documents set restricted = true where id = '{doc['id']}'")
    assert _count(file_id) == "1"
    _legacy(f"update office.documents set restricted = true where id = '{doc['id']}'",
            "documents_restricted_sealed", "office.documents")
    assert _count(file_id) == "0"


def test_attaching_a_read_file_to_a_restricted_document_drops_its_text(world):
    open_doc = received(world.clerk_a, incoming(world.tag, 303))
    secret = received(world.clerk_a, incoming(world.tag, 304, restricted=True))
    file_id = insert_file(world.service_a, world.clerk_a)
    _attach(world, open_doc["id"], file_id)
    _text(world, file_id)
    with pytest.raises(SQLError, match="document_files_sealed"):
        _attach(world, secret["id"], file_id, role="attachment")
    assert _count(file_id) == "1"
    _legacy(f"insert into office.document_files (tenant_id, document_id, file_id, role, added_by) values "
            f"('{world.tenant_a}', '{secret['id']}', '{file_id}', 'attachment', '{world.clerk_a.sub}')",
            "document_files_sealed", "office.document_files")
    assert _count(file_id) == "0"
