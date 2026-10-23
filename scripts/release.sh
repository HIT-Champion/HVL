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
# Tạo gói phát hành Signet ở định dạng MỞ (.tar.gz).
#
# Tiêu chí chấm điểm PoF #3 trừ 3 điểm nếu "sử dụng các định dạng không phải là
# mở cho bản phát hành (vd., zip, .rar, .arj)" và trừ 3 điểm nếu "dự án không
# thực hiện phát hành theo phiên bản". Script này dùng .tar.gz và bắt buộc
# phiên bản theo Semantic Versioning.
#
#   ./scripts/release.sh 0.1.0
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

VERSION="${1:-}"
if [ -z "$VERSION" ]; then
  echo "Sử dụng: ./scripts/release.sh <phiên-bản>    (ví dụ: 0.1.0)" >&2
  exit 1
fi

if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$'; then
  echo "Lỗi: '$VERSION' không đúng Semantic Versioning (MAJOR.MINOR.PATCH)." >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "Lỗi: cây làm việc chưa sạch. Hãy commit hết trước khi phát hành." >&2
  exit 1
fi

# Mỗi bản phát hành phải có ghi chép thay đổi (tiêu chí PoF #6) — kiểm trước khi gắn thẻ: thẻ đã đẩy thì không gắn lại
if ! ./scripts/release-notes.sh "$VERSION" > /dev/null; then
  exit 1
fi

TAG="v$VERSION"
DIST="dist"

# Phiên bản đã phát hành thì không gắn lại: người dùng đã tải gói và .sha256 của nó, thay gói cùng tên là phá cách kiểm
if git remote get-url origin > /dev/null 2>&1; then
  if ! remote_tag="$(git ls-remote --tags origin "refs/tags/$TAG")"; then
    echo "Lỗi: không hỏi được origin để biết thẻ $TAG đã có chưa — kiểm mạng rồi chạy lại." >&2
    exit 1
  fi
  if [ -n "$remote_tag" ]; then
    echo "Lỗi: thẻ $TAG đã có trên origin (đã phát hành). Phát hành phiên bản mới; sửa ghi chú thì sửa trên trang" \
         "Release." >&2
    exit 1
  fi
fi
# chưa có trên origin mà có ở máy: thường là lần trước gắn thẻ rồi dừng giữa chừng — chưa ai tải, gỡ thẻ là đủ
if git rev-parse -q --verify "refs/tags/$TAG" > /dev/null; then
  echo "Lỗi: thẻ $TAG đã có ở máy này nhưng chưa đẩy lên origin (lần trước dừng giữa chừng?). Xem lại rồi gỡ:" \
       "git tag -d $TAG, chạy lại." >&2
  exit 1
fi

mkdir -p "$DIST"

echo "==> Gắn thẻ phiên bản $TAG"
git tag -a "$TAG" -m "Signet $VERSION"

echo "==> Sinh gói nguồn $DIST/moc-$VERSION.tar.gz"
git archive --format=tar.gz \
            --prefix="moc-$VERSION/" \
            -o "$DIST/moc-$VERSION.tar.gz" \
            "$TAG"

echo "==> Sinh tổng kiểm tra SHA-256"
( cd "$DIST" && sha256sum "moc-$VERSION.tar.gz" > "moc-$VERSION.tar.gz.sha256" )

echo ""
echo "Đã tạo bản phát hành $TAG:"
ls -lh "$DIST/moc-$VERSION.tar.gz"*
echo ""
echo "Bước tiếp theo:  git push origin $TAG    # chỉ thẻ này; GitHub Actions tạo Release kèm .tar.gz, SBOM, .sha256"
