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


# F3.13, #284 — chạy Alertmanager với token gọi svc-workflow. Cấu hình Alertmanager không đọc được biến môi trường:
# chép MOC_ALERT_TOKEN vào tệp trên tmpfs (chỉ người dùng của container đọc được) cho credentials_file của
# alertmanager.yml. Chưa có token (bản cài cũ) thì chạy cấu hình không gửi, ghi một dòng nhật ký.
set -eu

config=/etc/alertmanager/alertmanager.yml
if [ -n "${MOC_ALERT_TOKEN:-}" ]; then
  (umask 077 && printf '%s' "$MOC_ALERT_TOKEN" > /tmp/moc-alert-token)
else
  echo '{"event":"alertmanager.no_token","message":"Chưa có MOC_ALERT_TOKEN: cảnh báo không gửi tới svc-workflow"}'
  config=/etc/alertmanager/alertmanager-khong-gui.yml
fi
unset MOC_ALERT_TOKEN

# một bản, không chạy cụm (cổng 9094); nhật ký gửi, lệnh tắt cảnh báo nằm trên tmpfs: khởi động lại thì mất, lần gửi
# lại sau đó không thành thông báo thứ hai (svc-workflow chống trùng)
exec /bin/alertmanager --config.file="$config" --storage.path=/alertmanager --cluster.listen-address= \
  --web.listen-address=:9093 --log.format=json
