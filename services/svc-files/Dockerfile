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

# Dựng: docker build -t moc/svc-files services/svc-files
FROM python:3.13.16-slim

# OMP_THREAD_LIMIT=1: tesseract (F4.1) chỉ dùng một luồng OpenMP, không chiếm hết CPU của các dịch vụ khác trên máy
# (ocr.py cũng đặt lại biến này cho tiến trình tesseract)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src \
    OMP_THREAD_LIMIT=1

WORKDIR /app

# Dựng PDF văn bản đi bằng WeasyPrint: Pango dàn chữ, HarfBuzz nhúng phông vào PDF. Phông Liberation Serif
# (SIL OFL 1.1) có cùng số đo với Times New Roman mà NĐ 30/2020 quy định, đủ dấu tiếng Việt.
# Đọc văn bản đến (F4.1): Tesseract OCR (Apache-2.0) và dữ liệu tiếng Việt của gói Debian, gọi qua dòng lệnh
# trong tiến trình con có giới hạn (src/svc_files/docread/ocr.py).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-liberation \
      tesseract-ocr tesseract-ocr-vie \
 && rm -rf /var/lib/apt/lists/*

# Thư viện cài từ PyPI theo tệp khóa có băm; không chép thư viện vào repo (PoF #5).
COPY requirements.txt ./
RUN pip install --require-hashes -r requirements.txt

COPY src/ ./src/

RUN useradd --system --uid 10001 --no-create-home svc
USER 10001

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]

CMD ["uvicorn", "svc_files.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
