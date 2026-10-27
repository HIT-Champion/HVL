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

# Dựng: docker compose build app-tai-lieu-api (profile app), thẻ moc/app-tai-lieu-api:<MOC_VERSION>.
# Bước 1: Swagger UI và bản cho trình duyệt của oidc-client-ts từ npm theo package-lock.json (không chép mã thư viện vào
# repo — PoF #5), cùng image Node, cùng phiên bản oidc-client-ts với apps/nghi-phep. --ignore-scripts: @scarf/scarf mà
# swagger-ui-dist kéo theo chỉ có bước postinstall gửi số liệu sử dụng, không chạy.
FROM node:24.20.0-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --ignore-scripts

# Bước 2: chia OpenAPI của svc-files, svc-workflow (docs/api/openapi/, ngữ cảnh phụ `openapi` trong docker-compose.yml)
# thành bộ lõi và bộ Văn phòng điện tử. Đường /api/… mới chưa xếp bộ thì dựng hỏng ở đây
FROM python:3.13.16-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS chia
WORKDIR /src
COPY chia_openapi.py ./
COPY --from=openapi svc-files.json svc-workflow.json ./in/
RUN python3 chia_openapi.py in out

# Bước 3: chỉ trang tĩnh và máy chủ thư viện chuẩn, chạy không root
FROM python:3.13.16-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f
WORKDIR /app
COPY server.py ./
COPY public/ ./public/
COPY --from=build /src/node_modules/oidc-client-ts/dist/browser/oidc-client-ts.min.js ./public/lib/
COPY --from=build /src/node_modules/swagger-ui-dist/swagger-ui-bundle.js \
     /src/node_modules/swagger-ui-dist/swagger-ui.css /src/node_modules/swagger-ui-dist/LICENSE \
     /src/node_modules/swagger-ui-dist/NOTICE ./public/lib/swagger-ui/
COPY --from=chia /src/out/ ./public/openapi/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --retries=3 CMD \
  ["python3", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8080/tai-lieu-api/healthz', timeout=3)"]
CMD ["python3", "/app/server.py"]
