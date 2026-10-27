#!/bin/sh
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

# Lệnh của image moc/keycloak-fonts (#305): chép phông của theme đăng nhập từ image (/fonts, dựng từ gói npm) vào volume
# keycloak_fonts gắn ở /theme-fonts; keycloak gắn cùng volume, chỉ đọc, vào thư mục phông của theme. Compose chạy dịch
# vụ này trước keycloak mỗi lần `docker compose up`, nên bản phông của image mới thay bản cũ trong volume. Mỗi tệp chép
# ra tên tạm rồi đổi tên: Keycloak đang chạy không đọc phải tệp chép dở. Tệp của bản cũ không còn trong image thì xóa.
set -eu
SRC=/fonts
DST=/theme-fonts

# volume tạo từ trước khi image chạy user node thì thư mục gốc của nó thuộc root
if [ ! -w "$DST" ]; then
  echo "keycloak-fonts: không ghi được vào $DST; xóa volume keycloak_fonts rồi chạy lại để tạo volume mới" >&2
  exit 1
fi
cd "$SRC"
for f in $(find . -type f); do
  mkdir -p "$DST/${f%/*}"
  cp "$f" "$DST/$f.tmp"
  mv -f "$DST/$f.tmp" "$DST/$f"
done
cd "$DST"
for f in $(find . -type f); do
  [ -e "$SRC/$f" ] || rm -f "$f"
done
echo "keycloak-fonts: $(find . -type f | wc -l) tệp phông trong volume keycloak_fonts"
