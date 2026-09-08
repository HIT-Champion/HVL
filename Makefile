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
# DX-Lab — điều phối dựng, chạy và phát hành.
# Toàn bộ công cụ sử dụng đều là phần mềm nguồn mở (tiêu chí PoF #4).
# Chạy `make help` để xem danh sách lệnh.
# ---------------------------------------------------------------------------

.DEFAULT_GOAL := help
SHELL := /bin/bash

COMPOSE := docker compose
ENV_FILE := .env

.PHONY: help check build up up-h up-p up-d down restart logs ps seed \
        license-check license-fix lint release clean

help: ## Hiển thị danh sách lệnh
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

$(ENV_FILE):
	@echo "Chưa có $(ENV_FILE). Tạo từ mẫu: cp .env.example .env" >&2
	@exit 1

check: ## Kiểm tra tiền điều kiện của môi trường
	@command -v docker >/dev/null || { echo "Thiếu Docker Engine >= 24.0"; exit 1; }
	@$(COMPOSE) version >/dev/null || { echo "Thiếu plugin docker compose v2"; exit 1; }
	@test -f $(ENV_FILE) || { echo "Thiếu $(ENV_FILE) — chạy: cp .env.example .env"; exit 1; }
	@$(COMPOSE) config -q && echo "Cú pháp Docker Compose hợp lệ."
	@echo "Môi trường sẵn sàng."

build: $(ENV_FILE) ## Dựng toàn bộ image từ mã nguồn
	@$(COMPOSE) --profile all build

up: $(ENV_FILE) ## Khởi động đủ 4 trục H-P-D-I
	@$(COMPOSE) --profile all up -d
	@echo "DX-Lab đang chạy. Xem nhật ký: make logs"

up-h: $(ENV_FILE) ## Khởi động riêng trục [H] — Nhân sự
	@$(COMPOSE) --profile h up -d

up-p: $(ENV_FILE) ## Khởi động trục [H] + [P] — thêm Quy trình
	@$(COMPOSE) --profile h --profile p up -d

up-d: $(ENV_FILE) ## Khởi động trục [H] + [P] + [D] — thêm Dữ liệu
	@$(COMPOSE) --profile h --profile p --profile d up -d

down: ## Dừng toàn bộ dịch vụ
	@$(COMPOSE) --profile all down

restart: down up ## Khởi động lại toàn bộ hệ thống

logs: ## Theo dõi nhật ký của mọi dịch vụ
	@$(COMPOSE) --profile all logs -f --tail=100

ps: ## Liệt kê trạng thái các dịch vụ
	@$(COMPOSE) --profile all ps

seed: $(ENV_FILE) ## Nạp dữ liệu mẫu để chạy thử
	@test -d seed || { echo "Chưa có thư mục seed/ — sẽ bổ sung ở giai đoạn 1."; exit 0; }
	@bash seed/load.sh

license-check: ## Kiểm tra header giấy phép trong từng tệp mã (tiêu chí PoF #2)
	@./scripts/license-header.sh check

license-fix: ## Tự chèn header giấy phép vào các tệp còn thiếu
	@./scripts/license-header.sh fix

lint: license-check ## Chạy toàn bộ kiểm tra tĩnh
	@$(COMPOSE) config -q && echo "Docker Compose hợp lệ."

release: ## Tạo bản phát hành .tar.gz — dùng: make release VERSION=0.1.0
	@test -n "$(VERSION)" || { echo "Thiếu tham số: make release VERSION=0.1.0"; exit 1; }
	@./scripts/release.sh $(VERSION)

clean: ## Xóa tệp tạm và gói phát hành cục bộ
	@rm -rf dist/
	@echo "Đã dọn dẹp."
