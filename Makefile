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
# Signet — điều phối dựng, chạy và phát hành.
# Toàn bộ công cụ sử dụng đều là phần mềm nguồn mở (tiêu chí PoF #4).
# Chạy `make help` để xem danh sách lệnh.
# ---------------------------------------------------------------------------

.DEFAULT_GOAL := help
SHELL := /bin/bash

ENV_FILE := .env
# Profile thêm khai trong .env (MOC_EXTRA_PROFILES=tunnel,…) đi cùng mọi lệnh compose của Makefile, như
# COMPOSE_PROFILES trong bản cài (make install)
EXTRA_PROFILES := $(shell sed -n 's/^MOC_EXTRA_PROFILES=//p' $(ENV_FILE) 2>/dev/null | tail -n 1 | tr ',' ' ')
COMPOSE := $(strip docker compose --profile core --profile app $(foreach p,$(EXTRA_PROFILES),--profile $(p)))
# Log tập trung (F3.14, profile logs; docs/van-hanh.md mục Log tập trung): tệp phủ đổi driver log của 9 dịch vụ sang
# fluentd → Vector. Chỉ nạp khi bật; tắt thì docker compose chỉ đọc docker-compose.yml như cũ. export: lệnh con
# (demo.py, moc.py… gọi docker compose) cũng nạp tệp phủ
# Ứng dụng cài bằng manifest (moc app install, docs/them-ung-dung.md): tệp phủ compose sinh trong .moc-apps/. Có thì
# đi cùng mọi COMPOSE_FILE mà Makefile tự đặt (log tập trung); không đặt thì compose đọc COMPOSE_FILE trong .env
APPS_COMPOSE_FILE := $(wildcard .moc-apps/docker-compose.apps.yml)
APPS_SUFFIX := $(if $(APPS_COMPOSE_FILE),:$(APPS_COMPOSE_FILE))
# Mô hình chạy trên GPU NVIDIA (MOC_AI_DEVICE=gpu, docs/van-hanh.md mục Chạy mô hình bằng GPU): tệp phủ cấp GPU cho
# ollama, đi cùng mọi COMPOSE_FILE mà Makefile đặt. cpu (mặc định) thì compose chỉ đọc docker-compose.yml như cũ
AI_DEVICE := $(shell sed -n 's/^MOC_AI_DEVICE=//p' $(ENV_FILE) 2>/dev/null | tail -n 1 | tr -d ' ')
GPU_SUFFIX := $(if $(filter gpu,$(AI_DEVICE)),:docker-compose.gpu.yml)
BASE_COMPOSE_FILE := docker-compose.yml$(GPU_SUFFIX)$(APPS_SUFFIX)
LOGS_COMPOSE_FILE := docker-compose.yml$(GPU_SUFFIX):platform/logs/docker-compose.logs.yml$(APPS_SUFFIX)
LOGGED_SERVICES := apisix app-office app-ca-nhan svc-files svc-workflow hasura keycloak postgres meilisearch
# Bật lâu dài (logs trong MOC_EXTRA_PROFILES): make up cũng thêm mật khẩu vào .env cũ (logs-env) và đặt giữ log
LOGS_ON := $(filter logs,$(EXTRA_PROFILES))
ifneq ($(LOGS_ON),)
export COMPOSE_FILE := $(LOGS_COMPOSE_FILE)
else ifneq ($(GPU_SUFFIX),)
export COMPOSE_FILE := $(BASE_COMPOSE_FILE)
endif
# Wiki nội bộ (#367, profile wiki; docs/van-hanh.md mục Wiki nội bộ). Bật lâu dài (wiki trong MOC_EXTRA_PROFILES): make
# up cũng thêm bí mật client vào .env cũ (wiki-env) và đồng bộ client Keycloak, quyền theo đơn vị (moc wiki sync)
WIKI_ON := $(filter wiki,$(EXTRA_PROFILES))
# Tự động hóa bằng Node-RED (#366, profile tu-dong; docs/van-hanh.md mục Tự động hóa bằng Node-RED). Bật lâu dài
# (tu-dong trong MOC_EXTRA_PROFILES): make up cũng thêm khóa vào .env cũ (tu-dong-env) và đồng bộ client Keycloak
TU_DONG_ON := $(filter tu-dong,$(EXTRA_PROFILES))
# Nơi cài khi chạy ngoài thư mục mã nguồn (make install)
PREFIX ?= /opt/moc

.PHONY: help env env-ready check build up up-ai ai-model down reset restart logs ps seed totp smoke e2e test api-docs audit demo-kiem-dich demo-han-che demo-ket-bi-mat demo-tu-phuc-hoi demo-nong-lanh demo-pha-he demo-it-ot demo-lien-thong \
        demo-doc-van-ban do-doc-van-ban van-ban-mau demo-hoi-dap do-hoi-dap hoi-dap-mau demo-giao-viec do-giao-viec \
        demo-ky-so \
        demo-che-pii do-che-pii \
        demo-nap-lo nap-lo-mau \
        demo-ca-nhan demo-tat-van-phong \
        do-so-lieu-sau \
        logs-env logs-up logs-down logs-tra demo-log-tap-trung alert-env demo-canh-bao \
        wiki-env wiki-up wiki-down demo-wiki \
        tu-dong-env tu-dong-up tu-dong-down demo-tu-dong \
        reconcile \
        backup restore install uninstall license-check license-fix sbom license-audit lint release clean

help: ## Hiển thị danh sách lệnh
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

$(ENV_FILE):
	@echo "Chưa có $(ENV_FILE). Tạo bằng: make env  (hoặc cp .env.example .env rồi sửa)" >&2
	@exit 1

env: ## Sinh .env từ .env.example, thay mọi change_me bằng chuỗi ngẫu nhiên
	@test ! -f $(ENV_FILE) || { echo "Đã có $(ENV_FILE) — xóa đi nếu muốn sinh lại." >&2; exit 1; }
	@# umask trước khi ghi: tệp chứa bí mật không lúc nào đọc được bởi người khác; sinh lỗi thì không để lại tệp dở
	@umask 077 && ./scripts/gen-env.sh .env.example > $(ENV_FILE).tmp && mv $(ENV_FILE).tmp $(ENV_FILE) \
	  || { rm -f $(ENV_FILE).tmp; exit 1; }
	@chmod 600 $(ENV_FILE)
	@echo "Đã tạo $(ENV_FILE). Mật khẩu của các tài khoản mẫu là giá trị MOC_DEMO_PASSWORD trong tệp này."
	@[ "$$(./scripts/co-gpu.sh)" != gpu ] || echo "Máy có GPU NVIDIA và Docker có runtime nvidia: đặt MOC_AI_DEVICE=gpu \
	trong $(ENV_FILE) để Ollama chạy mô hình trên GPU (docs/van-hanh.md, mục Chạy mô hình bằng GPU)."

# .env chép tay từ .env.example mà quên sửa: mật khẩu, khóa (cả khóa quản trị Hasura) ai đọc mã nguồn cũng biết
env-ready: $(ENV_FILE)
	@! grep -qE '^[A-Z0-9_]+=change_me' $(ENV_FILE) || { echo "$(ENV_FILE) còn giá trị mẫu change_me:" \
	  $$(grep -oE '^[A-Z0-9_]+=change_me' $(ENV_FILE) | cut -d= -f1) \
	  "— đổi thành chuỗi ngẫu nhiên, hoặc xóa $(ENV_FILE) rồi make env" >&2; exit 1; }
	@# F3.15: MOC_WAF, MOC_APISIX_WORKERS (#364: MOC_TRACE_RATIO) sai thì APISIX dừng ngay lúc khởi động — kiểm trước
	@# bằng chính script entrypoint của image (cùng nguồn với reconciler GitOps), với giá trị compose sẽ dùng: shell rồi
	@# .env, mặc định
	@json=$$($(COMPOSE) config --format json apisix 2>/dev/null) || exit 0; \
	  get() { printf '%s\n' "$$json" | sed -n "s/^ *\"$$1\": \"\(.*\)\",*\$$/\1/p"; }; \
	  w=$$(get MOC_WAF); n=$$(get MOC_APISIX_WORKERS); r=$$(get MOC_TRACE_RATIO); \
	  if [ -n "$$w" ]; then export MOC_WAF="$$w"; fi; if [ -n "$$n" ]; then export MOC_APISIX_WORKERS="$$n"; fi; \
	  if [ -n "$$r" ]; then export MOC_TRACE_RATIO="$$r"; fi; \
	  sh platform/apisix/kiem-moi-truong.sh --chi-kiem

check: ## Kiểm tra tiền điều kiện của môi trường
	@command -v docker >/dev/null || { echo "Thiếu Docker Engine >= 24.0"; exit 1; }
	@docker compose version >/dev/null || { echo "Thiếu plugin docker compose v2"; exit 1; }
	@test -f $(ENV_FILE) || { echo "Thiếu $(ENV_FILE) — chạy: make env"; exit 1; }
	@$(MAKE) --no-print-directory env-ready
	@$(COMPOSE) config -q && echo "Cú pháp Docker Compose hợp lệ."
	@echo "Môi trường sẵn sàng."

build: $(ENV_FILE) ## Dựng image của các dịch vụ do đội viết
	@$(COMPOSE) build

up: env-ready alert-env $(if $(LOGS_ON),logs-env) $(if $(WIKI_ON),wiki-env) $(if $(TU_DONG_ON),tu-dong-env) ## Khởi động lõi (Tầng 1) và Văn phòng điện tử (Tầng 2)
	$(if $(wildcard .moc-apps/apps),@python3 scripts/moc.py app sync --files)
	@$(COMPOSE) up -d --build --wait --wait-timeout 600
	$(if $(LOGS_ON),@python3 scripts/log_tap_trung.py init)
	$(if $(WIKI_ON),@python3 scripts/moc.py wiki sync)
	$(if $(TU_DONG_ON),@python3 scripts/moc.py tu-dong sync)
	$(if $(wildcard .moc-apps/apps),@python3 scripts/moc.py app sync)
	@echo "Signet đang chạy ở $$(grep '^MOC_PUBLIC_URL=' $(ENV_FILE) | cut -d= -f2). Nạp dữ liệu mẫu: make seed"

up-ai: $(ENV_FILE) ## Bật mô hình ngôn ngữ cục bộ (Ollama, profile ai): tác tử đọc văn bản viết trích yếu, trợ lý hỏi đáp tìm theo nghĩa và viết câu trả lời — cần make ai-model trước
	@$(COMPOSE) --profile ai up -d --wait ollama

ai-model: $(ENV_FILE) ## Tải mô hình sinh MOC_AI_MODEL (mặc định qwen3:1.7b) và mô hình nhúng MOC_AI_EMBED_MODEL (mặc định qwen3-embedding:0.6b) vào volume ollama_models — chạy một lần, cần Internet
	@$(COMPOSE) --profile ai-pull run --rm ollama-pull

down: ## Dừng toàn bộ dịch vụ (giữ dữ liệu)
	@$(COMPOSE) --profile iot --profile iot-sim --profile tu-dong \
	  --profile ai --profile ai-pull --profile logs --profile wiki down

reset: ## Dừng và XÓA toàn bộ dữ liệu (CSDL, tệp, chỉ mục)
	@read -p "Xóa toàn bộ dữ liệu của Signet trên máy này? [y/N] " a && [ "$$a" = y ]
	@$(COMPOSE) --profile iot --profile iot-sim --profile tu-dong \
	  --profile ai --profile ai-pull --profile logs --profile wiki down -v

restart: down up ## Khởi động lại toàn bộ hệ thống

logs: ## Theo dõi nhật ký của mọi dịch vụ
	@$(COMPOSE) logs -f --tail=100

alert-env: $(ENV_FILE)
	@# .env sinh trước #284 thiếu token Alertmanager → svc-workflow: sinh như make env, không in giá trị. Dòng có mà
	@# rỗng là đã chọn tắt cảnh báo ra chuông: giữ nguyên
	@grep -q '^MOC_ALERT_TOKEN=' $(ENV_FILE) || { umask 077 \
	  && printf '\n# Cảnh báo ra chuông (#284), make up thêm\nMOC_ALERT_TOKEN=change_me\n' \
	  | ./scripts/gen-env.sh /dev/stdin >> $(ENV_FILE) && echo "Đã thêm MOC_ALERT_TOKEN (ngẫu nhiên) vào $(ENV_FILE)."; }

logs-env: $(ENV_FILE)
	@# .env sinh trước F3.14 thiếu mật khẩu: sinh đúng như make env (scripts/gen-env.sh), không in giá trị
	@grep -q '^MOC_LOGS_PASSWORD=' $(ENV_FILE) || { umask 077 \
	  && printf '\n# Log tập trung (F3.14), make up / make logs-up thêm\nMOC_LOGS_PASSWORD=change_me\n' \
	  | ./scripts/gen-env.sh /dev/stdin >> $(ENV_FILE) && echo "Đã thêm MOC_LOGS_PASSWORD (ngẫu nhiên) vào $(ENV_FILE)."; }
	@sed -n 's/^MOC_LOGS_PASSWORD=//p' $(ENV_FILE) | tail -n 1 | grep -q . || { echo "MOC_LOGS_PASSWORD trong" \
	  "$(ENV_FILE) rỗng: Parseable không khởi động với mật khẩu rỗng — đặt một chuỗi ngẫu nhiên" >&2; exit 1; }

logs-up: env-ready logs-env ## Bật log tập trung (F3.14): Vector + Parseable; 9 dịch vụ (LOGGED_SERVICES) gửi log qua driver fluentd (tạo lại 9 container: CSDL, Hasura, Keycloak, tìm kiếm gián đoạn vài giây). Giữ qua make up: thêm logs vào MOC_EXTRA_PROFILES
	@COMPOSE_FILE=$(LOGS_COMPOSE_FILE) $(COMPOSE) --profile logs up -d --wait vector parseable $(LOGGED_SERVICES)
	@python3 scripts/log_tap_trung.py init
	@echo " $(EXTRA_PROFILES) " | grep -q ' logs ' || echo "Lưu ý: make up lần sau trả 9 dịch vụ về json-file" \
	  "(Vector, Parseable vẫn chạy mà không nhận gì) — bật lâu dài thì thêm logs vào MOC_EXTRA_PROFILES trong $(ENV_FILE)"

logs-down: env-ready ## Tắt log tập trung: 9 dịch vụ về json-file (tạo lại container), dừng Vector, Parseable; giữ log đã lưu (volume parseable_data — make reset mới xóa)
	@! echo " $(EXTRA_PROFILES) " | grep -q ' logs ' || { echo "Bỏ logs khỏi MOC_EXTRA_PROFILES trong $(ENV_FILE)" \
	  "trước, không thì make up lần sau lại bật" >&2; exit 1; }
	@COMPOSE_FILE=$(BASE_COMPOSE_FILE) $(COMPOSE) up -d --wait --no-deps $(LOGGED_SERVICES)
	@COMPOSE_FILE=$(BASE_COMPOSE_FILE) $(COMPOSE) --profile logs rm -sf vector parseable

logs-tra: $(ENV_FILE) ## Tra log tập trung theo mã yêu cầu (header X-Request-Id, câu "đã ghi nhật ký với mã …"): make logs-tra ID=<mã> [PHUT=60]
	@python3 scripts/log_tap_trung.py tra "$(ID)" --phut "$(or $(PHUT),60)"

demo-log-tap-trung: $(ENV_FILE) ## Màn log tập trung (F3.14): một mã X-Request-Id tự đặt đi qua APISIX → svc-workflow → svc-files; Parseable trả dòng của cả ba cùng mã, sổ kiểm toán cùng mã; không lộ token; docker logs vẫn đọc được
	@python3 scripts/demo.py log-tap-trung

wiki-env: $(ENV_FILE)
	@# .env sinh trước #367 thiếu bí mật client: sinh đúng như make env (scripts/gen-env.sh), không in giá trị
	@grep -q '^MOC_WIKI_CLIENT_SECRET=' $(ENV_FILE) || { umask 077 \
	  && printf '\n# Wiki nội bộ (#367), make up / make wiki-up thêm\nMOC_WIKI_CLIENT_SECRET=change_me\n' \
	  | ./scripts/gen-env.sh /dev/stdin >> $(ENV_FILE) \
	  && echo "Đã thêm MOC_WIKI_CLIENT_SECRET (ngẫu nhiên) vào $(ENV_FILE)."; }

wiki-up: env-ready wiki-env ## Bật wiki nội bộ (#367, DokuWiki ở /wiki/): đăng nhập Keycloak, mỗi đơn vị một không gian riêng; tạo client Keycloak wiki, ghi quyền theo đơn vị (chạy lại sau khi thêm đơn vị). Giữ qua make up: thêm wiki vào MOC_EXTRA_PROFILES
	@$(COMPOSE) --profile wiki up -d --build --wait wiki
	@python3 scripts/moc.py wiki sync
	@echo " $(EXTRA_PROFILES) " | grep -q ' wiki ' || echo "Lưu ý: make down tắt wiki, make up sau đó không bật" \
	  "lại — bật lâu dài thì thêm wiki vào MOC_EXTRA_PROFILES trong $(ENV_FILE)"

wiki-down: env-ready ## Tắt wiki nội bộ: dừng, xóa container; giữ trang, tệp đã lưu (volume wiki_data — make reset mới xóa)
	@! echo " $(EXTRA_PROFILES) " | grep -q ' wiki ' || { echo "Bỏ wiki khỏi MOC_EXTRA_PROFILES trong $(ENV_FILE)" \
	  "trước, không thì make up lần sau lại bật" >&2; exit 1; }
	@$(COMPOSE) --profile wiki rm -sf wiki

tu-dong-env: $(ENV_FILE)
	@# .env sinh trước #366 thiếu khóa mã hóa thông tin đăng nhập của flow: sinh như make env, không in giá trị
	@grep -q '^MOC_TU_DONG_SECRET=' $(ENV_FILE) || { umask 077 \
	  && printf '\n# Tự động hóa Node-RED (#366), make up / make tu-dong-up thêm\nMOC_TU_DONG_SECRET=change_me\n' \
	  | ./scripts/gen-env.sh /dev/stdin >> $(ENV_FILE) \
	  && echo "Đã thêm MOC_TU_DONG_SECRET (ngẫu nhiên) vào $(ENV_FILE)."; }

tu-dong-up: env-ready tu-dong-env ## Bật tự động hóa Node-RED (#366, trình soạn ở /tu-dong/): đăng nhập Keycloak, chỉ vai trò operator; tạo client Keycloak tu-dong. Cấp vai trò: python3 scripts/moc.py tu-dong operator add <tên>. Giữ qua make up: thêm tu-dong vào MOC_EXTRA_PROFILES
	@$(COMPOSE) --profile tu-dong up -d --build --wait tu-dong
	@python3 scripts/moc.py tu-dong sync
	@echo " $(EXTRA_PROFILES) " | grep -q ' tu-dong ' || echo "Lưu ý: make down tắt Node-RED, make up sau đó không" \
	  "bật lại — bật lâu dài thì thêm tu-dong vào MOC_EXTRA_PROFILES trong $(ENV_FILE)"

tu-dong-down: env-ready ## Tắt tự động hóa Node-RED: dừng, xóa container; giữ flow đã lưu (volume tu_dong_data — make reset mới xóa)
	@! echo " $(EXTRA_PROFILES) " | grep -q ' tu-dong ' || { echo "Bỏ tu-dong khỏi MOC_EXTRA_PROFILES trong" \
	  "$(ENV_FILE) trước, không thì make up lần sau lại bật" >&2; exit 1; }
	@$(COMPOSE) --profile tu-dong rm -sf tu-dong

demo-tu-dong: $(ENV_FILE) ## Màn tự động hóa (#366, cần make tu-dong-up): chưa đăng nhập, không có vai trò operator thì không vào được trình soạn; người vận hành đăng nhập Keycloak, triển khai flow qua cổng (WAF bật); không node exec, không cài node từ npm; robot của đơn vị, hai flow mẫu (Hỏa tốc báo lãnh đạo, văn bản sắp hạn)
	@python3 scripts/demo_tu_dong.py

demo-wiki: $(ENV_FILE) ## Màn wiki nội bộ (#367, cần make wiki-up): người phòng CNTT viết trang trong không gian đơn vị mình; văn thư phòng KT và khách chưa đăng nhập không đọc được; tài khoản đến từ Keycloak, không mật khẩu riêng
	@python3 scripts/demo_wiki.py

ps: ## Liệt kê trạng thái các dịch vụ
	@$(COMPOSE) ps

seed: $(ENV_FILE) ## Nạp dữ liệu mẫu: 2 đơn vị, phòng ban, tài khoản, văn bản
	@python3 scripts/seed.py

totp: $(ENV_FILE) ## Mã TOTP của tài khoản mẫu văn thư, lãnh đạo; khóa để thêm vào ứng dụng xác thực
	@python3 scripts/totp.py

smoke: $(ENV_FILE) ## Kiểm tra nhanh luồng chính qua cổng APISIX
	@python3 scripts/smoke.py

PLAYWRIGHT_IMAGE := mcr.microsoft.com/playwright:v1.63.0-noble@sha256:eff16c30e6f3f4af0a03fa4b706120d5e9b0891c344a27d64559aff5900a4a27

e2e: $(ENV_FILE) ## Kiểm thử trên trình duyệt thật (Playwright): văn bản đến, văn bản đi, ký số, thông báo, sổ kiểm toán, sổ đăng ký, kiểm dịch, văn bản hạn chế, đọc văn bản đến
	@docker run --rm --network host --ipc host --env-file $(ENV_FILE) -u "$$(id -u):$$(id -g)" -e CI \
	  -e HOME=/tmp -e npm_config_cache=/tmp/.npm -v "$(CURDIR)/tests/e2e:/e2e" -w /e2e \
	  -v "$(CURDIR)/seed/van-ban-den:/mau:ro" -e MOC_SAMPLES_DIR=/mau $(PLAYWRIGHT_IMAGE) \
	  sh -c 'npm ci --no-audit --no-fund --ignore-scripts >/dev/null && npx playwright test'

test: ## Chạy test đơn vị của các dịch vụ, lệnh vận hành và phần kiểm form (không cần Docker; cần uv, Node 24, npm ci trong apps/office)
	@cd services/svc-files && uv run --no-project --with-requirements requirements-dev.txt python -m pytest -q
	@cd services/svc-workflow && uv run --no-project --with-requirements requirements-dev.txt python -m pytest -q
	@python3 -m unittest discover -s scripts/tests
	@cd apps/office && npm test
	@cd apps/ca-nhan && npm test
	@cd apps/bang-tin && node --test tests/*.test.js
	@python3 -m unittest discover -s apps/bang-tin/tests
	@cd apps/nghi-phep && node --test tests/*.test.js
	@python3 -m unittest discover -s apps/nghi-phep/tests
	@python3 -m unittest discover -s apps/tai-lieu-api/tests

audit: $(ENV_FILE) ## Kiểm sổ kiểm toán: tính lại chuỗi băm ngoài CSDL, so mốc neo trong bucket lạnh, hash văn bản
	@python3 scripts/moc.py audit verify

demo-canh-bao: $(ENV_FILE) ## Màn cảnh báo vận hành (F3.13): cảnh báo giả qua Alertmanager thành thông báo ở chuông của quản trị mọi đơn vị, hết cảnh báo thêm một thông báo, token sai bị từ chối (docs/demo-script.md)
	@python3 scripts/demo.py canh-bao

demo-kiem-dich: $(ENV_FILE) ## Màn demo (iv) kiểm dịch: tệp EICAR bị chặn ở cửa ngõ, lần chặn vào sổ kiểm toán (docs/demo-script.md)
	@python3 scripts/demo.py kiem-dich

demo-han-che: $(ENV_FILE) ## Màn demo (iv) văn bản hạn chế: tệp mã hóa trong kho, chỉ người có tên mở được, có dấu tên người xem (docs/demo-script.md)
	@python3 scripts/demo.py han-che

demo-ket-bi-mat: $(ENV_FILE) ## Màn demo (iv) két bí mật: dịch vụ lấy bí mật từ OpenBao, két tự mở khóa khi khởi động lại (docs/demo-script.md)
	@python3 scripts/demo.py ket-bi-mat

demo-tu-phuc-hoi: $(ENV_FILE) ## Màn demo (iv) tự phục hồi: xóa container, reconciler dựng lại theo khai báo (docs/demo-script.md)
	@python3 scripts/demo.py tu-phuc-hoi

demo-nong-lanh: $(ENV_FILE) ## Màn demo (i) nóng → lạnh: lập hồ sơ, nộp lưu thành gói Parquet + tệp + manifest có băm trên bucket lạnh (docs/demo-script.md)
	@python3 scripts/demo.py nong-lanh

demo-pha-he: $(ENV_FILE) ## Màn demo (iii) phả hệ + chất lượng: lượt nộp lưu truy ngược về bảng nghiệp vụ, bảng nào cũng được kiểm (docs/demo-script.md)
	@python3 scripts/demo.py pha-he

demo-it-ot: $(ENV_FILE) ## Màn demo (ii) IT/OT: bật broker NGSI-LD, cảm biến vượt ngưỡng → dự thảo "Báo cáo sự cố" vào luồng văn bản đi (docs/demo-script.md)
	@python3 scripts/demo.py it-ot

demo-lien-thong: $(ENV_FILE) ## Màn liên thông (F3.12): CNTT phát hành → Khoa Kinh tế tự nhận văn bản đến cùng băm, mã xác thực, vào sổ, chỉ đạo (docs/demo-script.md)
	@python3 scripts/demo.py lien-thong

demo-doc-van-ban: $(ENV_FILE) ## Màn đọc văn bản đến (F4.1): văn thư tải công văn, tác tử đọc (lớp chữ PDF / OCR) gợi ý số, ngày, cơ quan, loại, trích yếu; vào sổ; văn bản hạn chế không đọc (docs/demo-script.md)
	@python3 scripts/demo.py doc-van-ban

do-doc-van-ban: $(ENV_FILE) ## Đo tác tử đọc văn bản trên 22 mẫu seed/van-ban-den: bảng đúng/sai/trống từng trường, thời gian (thoát 1 khi PDF có chữ dưới ngưỡng, cả kho dưới 20 văn bản, số ký hiệu hay ngày ban hành đúng không quá nửa)
	@python3 scripts/demo.py do-doc-van-ban

van-ban-mau: $(ENV_FILE) ## Sinh lại văn bản đến mẫu seed/van-ban-den (PDF, ảnh scan, nhãn) và TSV Tesseract cho test, trong container svc-files (cần make up)
	@python3 scripts/van_ban_mau.py --mode container

demo-hoi-dap: $(ENV_FILE) ## Màn hỏi đáp trên kho văn bản (F4.2): trợ lý trả câu trích kèm số ký hiệu, trang; chỉ trong văn bản người hỏi được xem; văn bản hạn chế không vào chỉ mục; sổ kiểm toán không có câu hỏi (docs/demo-script.md)
	@python3 scripts/demo.py hoi-dap

do-hoi-dap: $(ENV_FILE) ## Đo trợ lý hỏi đáp trên bộ câu hỏi seed/hoi-dap/cau-hoi.json: recall@3, từ chối đúng, thời gian; có profile ai thì đo cả câu trả lời của mô hình (thoát 1 khi có nguồn bị cấm hoặc recall@3 dưới ngưỡng)
	@python3 scripts/demo.py do-hoi-dap

hoi-dap-mau: $(ENV_FILE) ## Sinh lại kho văn bản mẫu nhiều trang seed/hoi-dap (PDF, cau-hoi.json) trong container svc-files (cần make up)
	@python3 scripts/hoi_dap_mau.py --mode container

demo-giao-viec: $(ENV_FILE) ## Màn gợi ý giao việc (F4.3): văn bản mới vào sổ, tác tử gợi ý đơn vị chủ trì và hạn kèm căn cứ; văn bản hạn chế không gợi ý, không làm căn cứ; svc-files tắt vẫn chỉ đạo được (docs/demo-script.md)
	@python3 scripts/demo.py giao-viec

do-giao-viec: $(ENV_FILE) ## Đo tác tử gợi ý giao việc leave-one-out trên lịch sử seed/giao-viec: top-1/2/3, độ phủ, sai số hạn, thời gian (thoát 1 khi căn cứ là văn bản hạn chế hoặc top-1 dưới ngưỡng)
	@python3 scripts/demo.py do-giao-viec

do-so-lieu-sau: $(ENV_FILE) ## Số đo "sau" của đặc tả §8 (F4.6) trên hệ thống đang chạy: thời gian từ văn bản đến tới khi giao xử lý (trung vị, p90), tỷ lệ quá hạn, 5 lần tìm lại văn bản cũ qua API (độ trễ hệ thống); in bảng, ghi out/so-lieu-sau.json (thoát 1 khi không đo được)
	@python3 scripts/demo.py do-so-lieu-sau

demo-ky-so: $(ENV_FILE) ## Màn ký số (F4.5, chỉ minh họa): văn bản đi ký PAdES bằng khóa của đơn vị trong két, CA nội bộ; cổng xác thực báo người ký; pyHanko phát hiện sửa sau khi ký, lật một bit; văn bản hạn chế không ký (docs/demo-script.md)
	@python3 scripts/demo.py ky-so

demo-che-pii: $(ENV_FILE) ## Màn che thông tin cá nhân (F4.4): đơn giả lập có CCCD, số điện thoại, email, STK — tìm và trích nguyên văn vẫn có số thật; nhật ký apisix, app-office, svc-files, svc-workflow không còn giá trị nào, không còn chuỗi truy vấn; mô hình chỉ thấy nhãn (docs/demo-script.md)
	@python3 scripts/demo.py che-pii

do-che-pii: ## Đo bộ che thông tin cá nhân, không cần Docker: số chỗ bị che trên kho mẫu seed/ (phải 0), 18 đột biến mã của pii.py (phải bị test bắt hết); thoát 1 khi che nhầm hoặc có đột biến sống sót
	@cd services/svc-files && uv run --no-project --with-requirements requirements-dev.txt python -m pytest -q -s \
	  tests/test_pii_corpus.py tests/test_pii_mutation.py

demo-nap-lo: $(ENV_FILE) ## Màn nạp lô văn bản đến (cụm ⑤): 200 dòng + zip qua API, EICAR bị chặn, gửi lại không trùng
	@python3 scripts/demo.py nap-lo

nap-lo-mau: ## Sinh lại seed/nap-lo/van-ban-den.csv: 200 văn bản đến mẫu, có dòng sai cố ý (không cần Docker)
	@python3 scripts/nap_lo_mau.py

demo-ca-nhan: $(ENV_FILE) ## Ứng dụng thứ hai trên lõi (docs/them-ung-dung.md): Không gian cá nhân P.A.R.A — client Keycloak riêng, SSO với Văn phòng điện tử; tải lên qua ClamAV, xếp, chuyển, tải về; người khác không với tới; sổ kiểm toán của lõi
	@python3 scripts/demo_ca_nhan.py

demo-tat-van-phong: $(ENV_FILE) ## Tắt phần Văn phòng điện tử (MOC_OFFICE_ENABLED=false) trong svc-files, svc-workflow: route, Action của Văn phòng không còn; phần lõi của make smoke và make demo-ca-nhan vẫn đạt; xong thì bật lại (#302)
	@python3 scripts/demo_tat_van_phong.py

.PHONY: app-install app-list app-remove demo-cai-ung-dung demo-quy-trinh

app-install: env-ready ## Cắm ứng dụng bằng manifest, không sửa lõi: make app-install APP=apps/bang-tin/app.yaml [DRY=1]
	@test -n "$(APP)" || { echo "Thiếu tham số: make app-install APP=apps/<thư mục>/app.yaml" >&2; exit 1; }
	@python3 scripts/moc.py app install "$(APP)" $(if $(DRY),--dry-run)

app-list: $(ENV_FILE) ## Ứng dụng đã cài bằng manifest: đường, image, migration đã áp, sự kiện nghe
	@python3 scripts/moc.py app list

app-remove: env-ready ## Gỡ ứng dụng cài bằng manifest, GIỮ dữ liệu: make app-remove APP=bang-tin [DRY=1]
	@test -n "$(APP)" || { echo "Thiếu tham số: make app-remove APP=<tên>" >&2; exit 1; }
	@python3 scripts/moc.py app remove "$(APP)" $(if $(DRY),--dry-run)

demo-cai-ung-dung: $(ENV_FILE) ## Cắm Bảng tin bằng một lệnh: cài, SSO, sự kiện, cài lại, gỡ giữ dữ liệu; lõi không đổi
	@python3 scripts/demo.py cai-ung-dung

demo-quy-trinh: $(ENV_FILE) ## Quy trình ứng dụng qua lõi (Đơn nghỉ phép): BPMN độc bị từ chối, 422, duyệt theo phòng
	@python3 scripts/demo.py quy-trinh

reconcile: $(ENV_FILE) ## Một lượt reconciler GitOps + tự phục hồi (systemd timer gọi mỗi 60 giây, xem platform/systemd/)
	@python3 scripts/reconcile.py

backup: $(ENV_FILE) ## Sao lưu mọi CSDL và tệp vào kho restic mã hóa (MOC_BACKUP_DIR, mặc định ./backups)
	@python3 scripts/moc.py backup create

restore: $(ENV_FILE) ## Khôi phục lượt sao lưu mới nhất (hỏi lại trước khi thay dữ liệu); các lượt: python3 scripts/moc.py backup list
	@python3 scripts/moc.py backup restore

.PHONY: copyright
copyright: ## Sinh COPYRIGHT.txt (bảng phần mềm thượng nguồn) từ các bảng thành phần của DEPENDENCIES.md
	@python3 scripts/copyright_txt.py

api-docs: $(ENV_FILE) ## Xuất tài liệu API vào docs/api/ từ hệ thống đang chạy: schema GraphQL theo vai trò, OpenAPI
	@python3 scripts/api_docs.py

install: env-ready ## Cài ra ngoài thư mục mã nguồn, chạy từ đó — dùng: make install PREFIX=/opt/moc
	@MOC_VERSION="$(MOC_VERSION)" ./scripts/install.sh install "$(PREFIX)"

uninstall: ## Gỡ bản cài, giữ .env và dữ liệu — dùng: make uninstall PREFIX=/opt/moc
	@./scripts/install.sh uninstall "$(PREFIX)"

license-check: ## Kiểm tra header giấy phép trong từng tệp mã (tiêu chí PoF #2)
	@./scripts/license-header.sh check

license-fix: ## Tự chèn header giấy phép vào các tệp còn thiếu
	@./scripts/license-header.sh fix

# Syft (Anchore) đọc tệp khóa npm (kể cả gói chỉ dùng lúc dựng), requirements*.txt và action trong .github/workflows/;
# requirements.txt không ghi giấy phép nên --enrich python hỏi PyPI giấy phép của từng gói Python (cần mạng). Không đọc
# Dockerfile, docker-compose.yml: image thượng nguồn và giấy phép của chúng ghi ở DEPENDENCIES.md. CI ghi đè bằng biến
# môi trường cùng tên trong .github/workflows/ci.yml — đổi phiên bản thì đổi cả hai (test scripts kiểm hai chỗ trùng)
SYFT_IMAGE ?= ghcr.io/anchore/syft:v1.54.1@sha256:3eb5379ba7b409c3f4069b686110527af0c47df993fa5c10d13e7cf34f49b1aa
SBOM_VERSION = $(or $(VERSION),$(shell git describe --tags --always 2>/dev/null | sed 's/^v//'),dev)
SBOM = dist/signet-$(SBOM_VERSION).cdx.json

sbom: ## Danh mục thành phần SBOM CycloneDX của cây mã nguồn (Syft): dist/signet-<phiên bản>.cdx.json kèm .sha256 — dùng: make sbom [VERSION=1.1.0]; cần Docker, mạng tới PyPI
	@mkdir -p dist
	@docker run --rm -e SYFT_CHECK_FOR_APP_UPDATE=false -e SYFT_JAVASCRIPT_INCLUDE_DEV_DEPENDENCIES=true \
	  -v "$(CURDIR):/src:ro" $(SYFT_IMAGE) scan dir:/src --enrich python --source-name moc \
	  --source-version "$(SBOM_VERSION)" --exclude './**/node_modules/**' --exclude './**/.venv/**' \
	  --exclude './dist/**' --exclude './.git/**' -o cyclonedx-json > $(SBOM).tmp || { rm -f $(SBOM).tmp; exit 1; }
	@mv $(SBOM).tmp $(SBOM)
	@cd dist && sha256sum $(notdir $(SBOM)) > $(notdir $(SBOM)).sha256
	@echo "Đã tạo $(SBOM) và $(notdir $(SBOM)).sha256. Kiểm giấy phép: make license-audit"

license-audit: ## Kiểm giấy phép mọi gói (kể cả gián tiếp) trong SBOM của make sbom theo DEPENDENCIES.md; ngoại lệ có lý do ở .github/license-exceptions.json
	@test -f $(SBOM) || { echo "Chưa có $(SBOM) — chạy make sbom trước (cùng VERSION nếu có)." >&2; exit 1; }
	@python3 scripts/license_audit.py $(SBOM)

lint: license-check ## Chạy toàn bộ kiểm tra tĩnh
	@$(COMPOSE) config -q && echo "Docker Compose hợp lệ."

release: ## Tạo bản phát hành .tar.gz — dùng: make release VERSION=0.1.0
	@test -n "$(VERSION)" || { echo "Thiếu tham số: make release VERSION=0.1.0"; exit 1; }
	@./scripts/release.sh $(VERSION)

clean: ## Xóa tệp tạm và gói phát hành cục bộ
	@rm -rf dist/
	@echo "Đã dọn dẹp."
