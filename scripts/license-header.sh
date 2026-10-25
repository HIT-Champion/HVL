#!/usr/bin/env bash
#
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
#   ./scripts/license-header.sh check <thư mục>   # kiểm thư mục khác, vd. gói .tar.gz đã giải nén
#                                                 # (scripts/kiem_goi.py)
# ---------------------------------------------------------------------------

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${2:-$REPO_ROOT}"

COPYRIGHT_HOLDER="${MOC_COPYRIGHT_HOLDER:-Signet Team}"
COPYRIGHT_YEAR="${MOC_COPYRIGHT_YEAR:-2026}"

# Dấu hiệu nhận biết header đã tồn tại. Khối REUSE-Ignore: công cụ reuse bỏ qua dòng này, không đọc nhầm thành
# khai giấy phép của chính tệp này.
# REUSE-IgnoreStart
MARKER="SPDX-License-Identifier: Apache-2.0"
# REUSE-IgnoreEnd

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

# Kiểu chú thích theo loại tệp:
#   "line <tiền tố>"  — chú thích từng dòng: #, //, --
#   "html"            — khối <!-- ... -->  (Vue, HTML, XML, BPMN)
#   "css"             — khối /* ... */     (CSS, SCSS, Less)
#   ""                — loại tệp chưa hỗ trợ
comment_style_for() {
  case "$1" in
    *.sh|*.bash|*.py|*.yml|*.yaml|*.toml|*.cfg|*.conf|*.conf.template|*.ini|*.graphql|*.gql|Makefile|*/Makefile|Dockerfile|*/Dockerfile|*.Dockerfile|*.mk|*.env.example)
      echo "line #" ;;
    *.js|*.mjs|*.cjs|*.ts|*.mts|*.cts|*.jsx|*.tsx|*.go|*.java|*.c|*.h|*.cpp|*.rs|*.kt)
      echo "line //" ;;
    *.sql|*.lua)
      echo "line --" ;;
    *.vue|*.html|*.htm|*.xml|*.bpmn|*.dmn)
      echo "html" ;;
    *.css|*.scss|*.less)
      echo "css" ;;
    # Tệp phiên bản ở gốc: header dạng #, dòng cuối git archive điền thẻ (scripts/kiem_goi.py kiểm)
    VERSION)
      echo "line #" ;;
    *) echo "" ;;
  esac
}

# Tệp không phải mã nguồn: tài liệu, dữ liệu, hình ảnh, phông chữ, cấu hình công cụ — giấy phép của chúng khai trong
# REUSE.toml. Mẫu bắt đầu bằng * để khớp cả tệp nằm trong thư mục con (vd. services/x/.dockerignore).
# Định dạng JSON không có cú pháp chú thích nên không thể mang header.
is_non_source() {
  case "$1" in
    *.md|*.txt|LICENSE|NOTICE|*.json|*.lock|*.csv|*.tsv|*.png|*.jpg|*.jpeg|*.gif|*.webp|*.ico|*.pdf|*.svg|\
    *.woff|*.woff2|*.ttf|*.otf|*.gitkeep|*.gitignore|*.gitattributes|*.dockerignore|*.editorconfig|\
    *.nvmrc|*.python-version)
      return 0 ;;
  esac
  return 1
}

# Tệp cần xét: trong repo là tệp Git theo dõi. Thư mục không có .git (gói .tar.gz đã giải nén) thì mọi tệp trong đó —
# git ls-files ở đó không ra tệp nào và lượt kiểm sẽ qua mà không xét gì.
list_files() {
  if [ -e .git ]; then
    git ls-files -z 2>/dev/null | tr '\0' '\n'
  else
    find . -type f | sed 's#^\./##' | LC_ALL=C sort
  fi
}

# Liệt kê tệp mã nguồn do dự án viết (bỏ qua tài liệu và dữ liệu).
# Tệp có loại chưa hỗ trợ được ghi vào $UNSUPPORTED để cảnh báo thay vì bỏ qua im lặng.
UNSUPPORTED="$(mktemp)"
trap 'rm -f "$UNSUPPORTED"' EXIT

source_files() {
  list_files | while read -r f; do
    [ -f "$f" ] || continue
    is_non_source "$f" && continue
    if [ -n "$(comment_style_for "$f")" ]; then
      echo "$f"
    else
      echo "$f" >> "$UNSUPPORTED"
    fi
  done
}

has_header() { head -n 25 "$1" | grep -qF "$MARKER"; }

# In header đã bọc chú thích theo kiểu của tệp
render_header() {
  local style="$1" kind prefix
  read -r kind prefix <<< "$style"
  case "$kind" in
    line)
      header_body | while IFS= read -r line; do
        if [ -z "$line" ]; then printf '%s\n' "$prefix"; else printf '%s %s\n' "$prefix" "$line"; fi
      done ;;
    html)
      printf '%s\n' "<!--"
      header_body | while IFS= read -r line; do
        if [ -z "$line" ]; then printf '\n'; else printf '  %s\n' "$line"; fi
      done
      printf '%s\n' "-->" ;;
    css)
      printf '%s\n' "/*"
      header_body | while IFS= read -r line; do
        if [ -z "$line" ]; then printf '%s\n' " *"; else printf ' * %s\n' "$line"; fi
      done
      printf '%s\n' " */" ;;
  esac
}

insert_header() {
  local file="$1" style="$2" tmp first_line=""
  tmp="$(mktemp)"

  # Giữ nguyên dòng phải đứng đầu tệp: shebang, khai báo XML, DOCTYPE, chỉ thị biên dịch
  if head -n 1 "$file" | grep -qiE '^(#!|<\?|<!doctype|// *@|# *-\*-)'; then
    first_line="$(head -n 1 "$file")"
    printf '%s\n' "$first_line" > "$tmp"
  fi

  render_header "$style" >> "$tmp"
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
  if [ "$mode" = "fix" ]; then
    insert_header "$file" "$(comment_style_for "$file")"
    echo "  đã chèn header: $file"
  else
    echo "  THIẾU header giấy phép: $file"
  fi
done < <(source_files)

# Cảnh báo tệp có loại chưa hỗ trợ: cần thêm kiểu chú thích vào comment_style_for,
# hoặc khai báo là không phải mã nguồn trong is_non_source
if [ -s "$UNSUPPORTED" ]; then
  echo ""
  echo "CẢNH BÁO — loại tệp chưa được script hỗ trợ, không kiểm tra được header:"
  while IFS= read -r f; do
    if [ -n "${GITHUB_ACTIONS:-}" ]; then
      echo "::warning file=$f::Loại tệp chưa được scripts/license-header.sh hỗ trợ"
    else
      echo "  ? $f"
    fi
  done < "$UNSUPPORTED"
fi

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
