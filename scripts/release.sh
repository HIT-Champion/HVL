#!/usr/bin/env bash
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

# ---------------------------------------------------------------------------
# Tạo gói phát hành DX-Lab ở định dạng MỞ (.tar.gz).
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

if ! grep -q "## \[$VERSION\]" CHANGELOG.md; then
  echo "Lỗi: CHANGELOG.md chưa có mục '## [$VERSION]'." >&2
  echo "Mỗi bản phát hành phải có ghi chép thay đổi (tiêu chí PoF #6)." >&2
  exit 1
fi

TAG="v$VERSION"
DIST="dist"
mkdir -p "$DIST"

echo "==> Gắn thẻ phiên bản $TAG"
git tag -a "$TAG" -m "DX-Lab $VERSION"

echo "==> Sinh gói nguồn $DIST/dx-lab-$VERSION.tar.gz"
git archive --format=tar.gz \
            --prefix="dx-lab-$VERSION/" \
            -o "$DIST/dx-lab-$VERSION.tar.gz" \
            "$TAG"

echo "==> Sinh tổng kiểm tra SHA-256"
( cd "$DIST" && sha256sum "dx-lab-$VERSION.tar.gz" > "dx-lab-$VERSION.tar.gz.sha256" )

echo ""
echo "Đã tạo bản phát hành $TAG:"
ls -lh "$DIST/dx-lab-$VERSION.tar.gz"*
echo ""
echo "Bước tiếp theo:  git push origin main --tags"
