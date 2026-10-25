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

# Dựng: moc app install apps/bang-tin/app.yaml dựng image này (docker build) với thẻ moc/app-bang-tin:<phiên bản>-<băm>.
# Bước 1: bản dựng sẵn cho trình duyệt của oidc-client-ts từ npm theo package-lock.json (không chép vào repo — PoF #5),
# cùng image Node, cùng phiên bản thư viện với apps/ca-nhan.
FROM node:24.20.0-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --ignore-scripts

# Bước 2: Python thư viện chuẩn (cùng image ghim digest với svc-files, svc-workflow), không cài gói nào, không root.
# compose của ứng dụng đặt hệ tệp gốc chỉ đọc, chỉ /tmp ghi được
FROM python:3.13.16-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f
WORKDIR /app
COPY server.py ./
COPY public/ ./public/
COPY --from=build /src/node_modules/oidc-client-ts/dist/browser/oidc-client-ts.min.js ./public/lib/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001:10001
EXPOSE 8080 8081
HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
  CMD ["python3", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8080/bang-tin/healthz', timeout=3)"]
CMD ["python3", "/app/server.py"]
