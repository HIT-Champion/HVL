#!/usr/bin/env bash
#
# Copyright 2026 DX-Lab Team
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
#
# ---------------------------------------------------------------------------
# Kiểm tra và chèn header giấy phép Apache-2.0 vào mọi tệp mã nguồn.
#
# Tiêu chí chấm điểm PoF #2 trừ 5 điểm nếu "giấy phép không được ghi trong từng
# tệp mã" và trừ tiếp 5 điểm nếu "mã nguồn không có thông báo về mục đích của
# giấy phép". Script này bảo đảm cả hai điều kiện.
#
#   ./scripts/license-header.sh check   # liệt kê tệp thiếu header, thoát 1 nếu có
#   ./scripts/license-header.sh fix     # tự chèn header vào các tệp thiếu
# ---------------------------------------------------------------------------

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

COPYRIGHT_HOLDER="${DXLAB_COPYRIGHT_HOLDER:-DX-Lab Team}"
COPYRIGHT_YEAR="${DXLAB_COPYRIGHT_YEAR:-2026}"

# Dấu hiệu nhận biết header đã tồn tại
MARKER="SPDX-License-Identifier: Apache-2.0"

# Sinh phần thân header (chưa có ký tự chú thích)
header_body() {
  cat <<EOF
Copyright ${COPYRIGHT_YEAR} ${COPYRIGHT_HOLDER}

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

${MARKER}
EOF
}

# Ký tự mở đầu dòng chú thích theo phần mở rộng tệp
comment_prefix_for() {
  case "$1" in
    *.sh|*.bash|*.py|*.yml|*.yaml|*.toml|*.cfg|*.conf|Makefile|Dockerfile|*.mk) echo "#" ;;
    *.js|*.ts|*.jsx|*.tsx|*.go|*.java|*.c|*.h|*.cpp|*.rs|*.kt)                  echo "//" ;;
    *.sql)                                                                       echo "--" ;;
    *) echo "" ;;
  esac
}

# Liệt kê tệp mã nguồn do dự án viết (Git theo dõi, bỏ qua tài liệu và dữ liệu)
source_files() {
  git ls-files -z 2>/dev/null | tr '\0' '\n' | while read -r f; do
    [ -f "$f" ] || continue
    case "$f" in
      *.md|*.txt|LICENSE|NOTICE|*.json|*.lock|*.png|*.jpg|*.pdf|*.svg|.gitignore|.editorconfig|.env.example)
        continue ;;
    esac
    [ -n "$(comment_prefix_for "$f")" ] && echo "$f"
  done
}

has_header() { head -n 25 "$1" | grep -qF "$MARKER"; }

insert_header() {
  local file="$1" prefix="$2" tmp first_line=""
  tmp="$(mktemp)"

  # Giữ nguyên dòng shebang hoặc chỉ thị đầu tệp nếu có
  if head -n 1 "$file" | grep -qE '^(#!|<\?|// *@|# *-\*-)'; then
    first_line="$(head -n 1 "$file")"
    printf '%s\n' "$first_line" > "$tmp"
  fi

  header_body | while IFS= read -r line; do
    if [ -z "$line" ]; then printf '%s\n' "$prefix"; else printf '%s %s\n' "$prefix" "$line"; fi
  done >> "$tmp"
  printf '\n' >> "$tmp"

  if [ -n "$first_line" ]; then tail -n +2 "$file" >> "$tmp"; else cat "$file" >> "$tmp"; fi

  cat "$tmp" > "$file"
  rm -f "$tmp"
}

missing=0
mode="${1:-check}"

while IFS= read -r file; do
  [ -n "$file" ] || continue
  if has_header "$file"; then continue; fi
  missing=$((missing + 1))
  prefix="$(comment_prefix_for "$file")"
  if [ "$mode" = "fix" ]; then
    insert_header "$file" "$prefix"
    echo "  đã chèn header: $file"
  else
    echo "  THIẾU header giấy phép: $file"
  fi
done < <(source_files)

if [ "$mode" = "fix" ]; then
  echo "Hoàn tất: đã xử lý $missing tệp."
  exit 0
fi

if [ "$missing" -gt 0 ]; then
  echo ""
  echo "Có $missing tệp thiếu header giấy phép Apache-2.0."
  echo "Chạy 'make license-fix' để tự chèn."
  exit 1
fi

echo "Tất cả tệp mã nguồn đều có header giấy phép Apache-2.0."
