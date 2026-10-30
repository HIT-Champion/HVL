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

# Node-RED của Signet (#366, profile tu-dong): image chính thức bản minimal (Node 24, không bộ dựng, không Python),
# thêm openid-client cho đăng nhập Keycloak và settings.js. package-lock.json ghim băm từng gói
FROM nodered/node-red:5.0.8-minimal@sha256:f8705efbf2b9c1a82b26cbda0f909fc9ad1b85946a6d341e3333e9313acc85c4

USER root
WORKDIR /moc
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund --cache /tmp/npm && rm -rf /tmp/npm
COPY settings.js kiem-tra.cjs ./
# Nạp thử settings.js bằng Node của image: openid-client (gói ESM) require được, chiến lược đăng nhập dựng được, khóa
# đã đặt. Sai là dừng dựng image
RUN node kiem-tra.cjs && rm kiem-tra.cjs

USER node-red
WORKDIR /usr/src/node-red
# entrypoint.sh của image chạy node-red --userDir /data, thêm các đối số này
CMD ["--settings", "/moc/settings.js"]
