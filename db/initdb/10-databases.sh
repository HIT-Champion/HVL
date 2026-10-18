#!/bin/sh
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

# Tạo CSDL riêng cho Keycloak và Flowable, mỗi CSDL một tài khoản riêng (không dùng tài khoản chủ).
# Image postgres chỉ chạy thư mục này ở lần khởi động đầu tiên, khi volume dữ liệu còn trống.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v kc_pw="$KEYCLOAK_DB_PASSWORD" -v fl_pw="$FLOWABLE_DB_PASSWORD" <<'SQL'
create role keycloak login password :'kc_pw';
create database keycloak owner keycloak;
create role flowable login password :'fl_pw';
create database flowable owner flowable;
SQL
