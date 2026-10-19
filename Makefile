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

# ---------------------------------------------------------------------------
# Mộc — điều phối dựng, chạy và phát hành.
# Toàn bộ công cụ sử dụng đều là phần mềm nguồn mở (tiêu chí PoF #4).
# Chạy `make help` để xem danh sách lệnh.
# ---------------------------------------------------------------------------

.DEFAULT_GOAL := help
SHELL := /bin/bash

COMPOSE := docker compose --profile core --profile app
ENV_FILE := .env
# Nơi cài khi chạy ngoài thư mục mã nguồn (make install)
PREFIX ?= /opt/moc

.PHONY: help env check build up down reset restart logs ps seed totp smoke e2e test \
        install uninstall license-check license-fix lint release clean

help: ## Hiển thị danh sách lệnh
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

$(ENV_FILE):
	@echo "Chưa có $(ENV_FILE). Tạo bằng: make env  (hoặc cp .env.example .env rồi sửa)" >&2
	@exit 1

env: ## Sinh .env từ .env.example, thay mọi change_me bằng chuỗi ngẫu nhiên
	@test ! -f $(ENV_FILE) || { echo "Đã có $(ENV_FILE) — xóa đi nếu muốn sinh lại." >&2; exit 1; }
	@./scripts/gen-env.sh .env.example > $(ENV_FILE)
	@chmod 600 $(ENV_FILE)
	@echo "Đã tạo $(ENV_FILE). Mật khẩu của các tài khoản mẫu là giá trị MOC_DEMO_PASSWORD trong tệp này."

check: ## Kiểm tra tiền điều kiện của môi trường
	@command -v docker >/dev/null || { echo "Thiếu Docker Engine >= 24.0"; exit 1; }
	@docker compose version >/dev/null || { echo "Thiếu plugin docker compose v2"; exit 1; }
	@test -f $(ENV_FILE) || { echo "Thiếu $(ENV_FILE) — chạy: make env"; exit 1; }
	@$(COMPOSE) config -q && echo "Cú pháp Docker Compose hợp lệ."
	@echo "Môi trường sẵn sàng."

build: $(ENV_FILE) ## Dựng image của các dịch vụ do đội viết
	@$(COMPOSE) build

up: $(ENV_FILE) ## Khởi động lõi (Tầng 1) và Văn phòng điện tử (Tầng 2)
	@$(COMPOSE) up -d --build --wait --wait-timeout 600
	@echo "Mộc đang chạy ở $$(grep '^MOC_PUBLIC_URL=' $(ENV_FILE) | cut -d= -f2). Nạp dữ liệu mẫu: make seed"

down: ## Dừng toàn bộ dịch vụ (giữ dữ liệu)
	@$(COMPOSE) down

reset: ## Dừng và XÓA toàn bộ dữ liệu (CSDL, tệp, chỉ mục)
	@read -p "Xóa toàn bộ dữ liệu của Mộc trên máy này? [y/N] " a && [ "$$a" = y ]
	@$(COMPOSE) down -v

restart: down up ## Khởi động lại toàn bộ hệ thống

logs: ## Theo dõi nhật ký của mọi dịch vụ
	@$(COMPOSE) logs -f --tail=100

ps: ## Liệt kê trạng thái các dịch vụ
	@$(COMPOSE) ps

seed: $(ENV_FILE) ## Nạp dữ liệu mẫu: 2 đơn vị, phòng ban, tài khoản, văn bản
	@python3 scripts/seed.py

totp: $(ENV_FILE) ## Mã TOTP của tài khoản mẫu văn thư, lãnh đạo; khóa để thêm vào ứng dụng xác thực
	@python3 scripts/totp.py

smoke: $(ENV_FILE) ## Kiểm tra nhanh luồng chính qua cổng APISIX
	@python3 scripts/smoke.py

PLAYWRIGHT_IMAGE := mcr.microsoft.com/playwright:v1.63.0-noble

e2e: $(ENV_FILE) ## Kiểm thử trên trình duyệt thật (Playwright): luồng văn bản đến qua giao diện
	@docker run --rm --network host --ipc host --env-file $(ENV_FILE) -u "$$(id -u):$$(id -g)" \
	  -e HOME=/tmp -e npm_config_cache=/tmp/.npm -v "$(CURDIR)/tests/e2e:/e2e" -w /e2e $(PLAYWRIGHT_IMAGE) \
	  sh -c 'npm ci --no-audit --no-fund --ignore-scripts >/dev/null && npx playwright test'

test: ## Chạy test đơn vị của các dịch vụ (không cần Docker)
	@cd services/svc-files && uv run --no-project --with-requirements requirements-dev.txt python -m pytest -q
	@cd services/svc-workflow && uv run --no-project --with-requirements requirements-dev.txt python -m pytest -q

install: $(ENV_FILE) ## Cài ra ngoài thư mục mã nguồn, chạy từ đó — dùng: make install PREFIX=/opt/moc
	@MOC_VERSION="$(MOC_VERSION)" ./scripts/install.sh install "$(PREFIX)"

uninstall: ## Gỡ bản cài, giữ .env và dữ liệu — dùng: make uninstall PREFIX=/opt/moc
	@./scripts/install.sh uninstall "$(PREFIX)"

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
