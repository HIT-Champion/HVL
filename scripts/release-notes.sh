#!/usr/bin/env bash
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
# ---------------------------------------------------------------------------
# In ghi chú phát hành của một phiên bản: phần dưới tiêu đề "## [X.Y.Z]" của
# CHANGELOG.md tới tiêu đề "## [" kế tiếp. release.sh gọi trước khi gắn thẻ
# (thiếu mục thì không gắn), .github/workflows/release.yml gọi để lấy nội dung
# trang Release.
#
# Bỏ qua khối chú thích HTML <!-- … -->: mẫu cho bản kế tiếp nằm trong đó và
# tiêu đề của mẫu không được khớp một phiên bản thật. Mục chỉ có tiêu đề nhóm
# (### Đã thêm …) mà không có dòng thay đổi nào thì coi như chưa có.
#
#   ./scripts/release-notes.sh 0.2.0 [CHANGELOG.md]
# ---------------------------------------------------------------------------
set -euo pipefail

VERSION="${1:?Sử dụng: release-notes.sh <phiên-bản> [CHANGELOG.md]}"
CHANGELOG="${2:-CHANGELOG.md}"

notes="$(awk -v head="## [$VERSION]" '
  /<!--/                     { c = 1 }
  c                          { if (/-->/) c = 0; next }
  index($0, head) == 1       { p = 1; next }
  p && /^## \[/              { exit }
  p                          { print }
' "$CHANGELOG")"

if ! grep -qE '^[[:space:]]*[-*] ' <<<"$notes"; then
  echo "Lỗi: $CHANGELOG chưa có mục '## [$VERSION]' với ít nhất một dòng thay đổi." >&2
  echo "Chuyển các dòng của mục [Chưa phát hành] sang mục [$VERSION] rồi commit, trước khi gắn thẻ." >&2
  exit 1
fi
# bỏ dòng trống đầu và cuối
sed -e '/./,$!d' <<<"$notes" | sed -e ':a' -e '/^\n*$/{$d;N;ba' -e '}'
