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

# Dựng: docker build -t moc/app-office apps/office
# Bước 1: dựng trang tĩnh bằng Nuxt (thư viện cài từ npm theo package-lock.json, không chép vào repo — PoF #5)
FROM node:24.20.0-slim AS build
WORKDIR /app
ENV NUXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --ignore-scripts
COPY . .
RUN npx nuxt prepare && npx nuxt generate && node scripts/csp-hashes.mjs .output/public > .output/csp.conf

# Bước 2: chỉ giữ tệp tĩnh, phục vụ bằng nginx không chạy quyền root
FROM nginxinc/nginx-unprivileged:1.30.6-alpine
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY nginx/security-headers.conf /etc/nginx/security-headers.conf
COPY --from=build /app/.output/public /usr/share/nginx/html
COPY --from=build /app/.output/csp.conf /etc/nginx/csp.conf
ENV MOC_REALM=moc
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1:8080/config.json || exit 1
