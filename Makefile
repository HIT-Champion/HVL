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
# Nơi cài khi chạy ngoài thư mục mã nguồn (make install)
PREFIX ?= /opt/moc

.PHONY: help env env-ready check build up up-ai ai-model down reset restart logs ps seed totp smoke e2e test api-docs audit demo-kiem-dich demo-han-che demo-ket-bi-mat demo-tu-phuc-hoi demo-nong-lanh demo-pha-he demo-it-ot demo-lien-thong \
        demo-doc-van-ban do-doc-van-ban van-ban-mau demo-hoi-dap do-hoi-dap hoi-dap-mau demo-giao-viec do-giao-viec \
        demo-ky-so \
        demo-che-pii do-che-pii \
        do-so-lieu-sau \
        reconcile \
        backup restore install uninstall license-check license-fix lint release clean

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

# .env chép tay từ .env.example mà quên sửa: mật khẩu, khóa (cả khóa quản trị Hasura) ai đọc mã nguồn cũng biết
env-ready: $(ENV_FILE)
	@! grep -qE '^[A-Z0-9_]+=change_me' $(ENV_FILE) || { echo "$(ENV_FILE) còn giá trị mẫu change_me:" \
	  $$(grep -oE '^[A-Z0-9_]+=change_me' $(ENV_FILE) | cut -d= -f1) \
	  "— đổi thành chuỗi ngẫu nhiên, hoặc xóa $(ENV_FILE) rồi make env" >&2; exit 1; }

check: ## Kiểm tra tiền điều kiện của môi trường
	@command -v docker >/dev/null || { echo "Thiếu Docker Engine >= 24.0"; exit 1; }
	@docker compose version >/dev/null || { echo "Thiếu plugin docker compose v2"; exit 1; }
	@test -f $(ENV_FILE) || { echo "Thiếu $(ENV_FILE) — chạy: make env"; exit 1; }
	@$(MAKE) --no-print-directory env-ready
	@$(COMPOSE) config -q && echo "Cú pháp Docker Compose hợp lệ."
	@echo "Môi trường sẵn sàng."

build: $(ENV_FILE) ## Dựng image của các dịch vụ do đội viết
	@$(COMPOSE) build

up: env-ready ## Khởi động lõi (Tầng 1) và Văn phòng điện tử (Tầng 2)
	@$(COMPOSE) up -d --build --wait --wait-timeout 600
	@echo "Signet đang chạy ở $$(grep '^MOC_PUBLIC_URL=' $(ENV_FILE) | cut -d= -f2). Nạp dữ liệu mẫu: make seed"

up-ai: $(ENV_FILE) ## Bật mô hình ngôn ngữ cục bộ (Ollama, profile ai): tác tử đọc văn bản viết trích yếu, trợ lý hỏi đáp tìm theo nghĩa và viết câu trả lời — cần make ai-model trước
	@$(COMPOSE) --profile ai up -d --wait ollama

ai-model: $(ENV_FILE) ## Tải mô hình sinh MOC_AI_MODEL (mặc định qwen3:1.7b) và mô hình nhúng MOC_AI_EMBED_MODEL (mặc định qwen3-embedding:0.6b) vào volume ollama_models — chạy một lần, cần Internet
	@$(COMPOSE) --profile ai-pull run --rm ollama-pull

down: ## Dừng toàn bộ dịch vụ (giữ dữ liệu)
	@$(COMPOSE) --profile iot --profile iot-sim --profile ai --profile ai-pull down

reset: ## Dừng và XÓA toàn bộ dữ liệu (CSDL, tệp, chỉ mục)
	@read -p "Xóa toàn bộ dữ liệu của Signet trên máy này? [y/N] " a && [ "$$a" = y ]
	@$(COMPOSE) --profile iot --profile iot-sim --profile ai --profile ai-pull down -v

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

PLAYWRIGHT_IMAGE := mcr.microsoft.com/playwright:v1.63.0-noble@sha256:eff16c30e6f3f4af0a03fa4b706120d5e9b0891c344a27d64559aff5900a4a27

e2e: $(ENV_FILE) ## Kiểm thử trên trình duyệt thật (Playwright): văn bản đến, văn bản đi, ký số, thông báo, sổ kiểm toán, sổ đăng ký, kiểm dịch, văn bản hạn chế, đọc văn bản đến
	@docker run --rm --network host --ipc host --env-file $(ENV_FILE) -u "$$(id -u):$$(id -g)" \
	  -e HOME=/tmp -e npm_config_cache=/tmp/.npm -v "$(CURDIR)/tests/e2e:/e2e" -w /e2e \
	  -v "$(CURDIR)/seed/van-ban-den:/mau:ro" -e MOC_SAMPLES_DIR=/mau $(PLAYWRIGHT_IMAGE) \
	  sh -c 'npm ci --no-audit --no-fund --ignore-scripts >/dev/null && npx playwright test'

test: ## Chạy test đơn vị của các dịch vụ, lệnh vận hành và phần kiểm form (không cần Docker; cần uv, Node 24, npm ci trong apps/office)
	@cd services/svc-files && uv run --no-project --with-requirements requirements-dev.txt python -m pytest -q
	@cd services/svc-workflow && uv run --no-project --with-requirements requirements-dev.txt python -m pytest -q
	@python3 -m unittest discover -s scripts/tests
	@cd apps/office && npm test

audit: $(ENV_FILE) ## Kiểm sổ kiểm toán: tính lại chuỗi băm ngoài CSDL, so mốc neo trong bucket lạnh, hash văn bản
	@python3 scripts/moc.py audit verify

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

do-che-pii: ## Đo bộ che thông tin cá nhân, không cần Docker: số chỗ bị che trên kho mẫu seed/ (phải 0), 15 đột biến mã của pii.py (phải bị test bắt hết); thoát 1 khi che nhầm hoặc có đột biến sống sót
	@cd services/svc-files && uv run --no-project --with-requirements requirements-dev.txt python -m pytest -q -s \
	  tests/test_pii_corpus.py tests/test_pii_mutation.py

reconcile: $(ENV_FILE) ## Một lượt reconciler GitOps + tự phục hồi (systemd timer gọi mỗi 60 giây, xem platform/systemd/)
	@python3 scripts/reconcile.py

backup: $(ENV_FILE) ## Sao lưu mọi CSDL và tệp vào kho restic mã hóa (MOC_BACKUP_DIR, mặc định ./backups)
	@python3 scripts/moc.py backup create

restore: $(ENV_FILE) ## Khôi phục lượt sao lưu mới nhất (hỏi lại trước khi thay dữ liệu); các lượt: python3 scripts/moc.py backup list
	@python3 scripts/moc.py backup restore

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

lint: license-check ## Chạy toàn bộ kiểm tra tĩnh
	@$(COMPOSE) config -q && echo "Docker Compose hợp lệ."

release: ## Tạo bản phát hành .tar.gz — dùng: make release VERSION=0.1.0
	@test -n "$(VERSION)" || { echo "Thiếu tham số: make release VERSION=0.1.0"; exit 1; }
	@./scripts/release.sh $(VERSION)

clean: ## Xóa tệp tạm và gói phát hành cục bộ
	@rm -rf dist/
	@echo "Đã dọn dẹp."
