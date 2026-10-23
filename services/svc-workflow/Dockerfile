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

# Dựng: docker build -t moc/svc-workflow services/svc-workflow
FROM python:3.13.16-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Thư viện cài từ PyPI theo tệp khóa có băm; không chép thư viện vào repo (PoF #5).
COPY requirements.txt ./
RUN pip install --require-hashes -r requirements.txt

COPY src/ ./src/
# JSON Schema dùng chung với giao diện (schemas/ ở gốc repo; compose đưa vào bằng additional_contexts, dựng tay thì
# docker build --build-context schemas=schemas services/svc-workflow): dựng cùng image để form (biên dịch vào
# app-office lúc dựng) và svc-workflow luôn kiểm theo cùng một bản
COPY --from=schemas . ./schemas/

RUN useradd --system --uid 10001 --no-create-home svc
USER 10001

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]

CMD ["uvicorn", "svc_workflow.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
