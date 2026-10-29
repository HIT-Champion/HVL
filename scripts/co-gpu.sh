#!/usr/bin/env bash
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

# In "gpu" khi máy chạy được mô hình trên GPU NVIDIA trong Docker (MOC_AI_DEVICE=gpu, docker-compose.gpu.yml):
# nvidia-smi thấy ít nhất một GPU và Docker có runtime nvidia (NVIDIA Container Toolkit, đã chạy nvidia-ctk runtime
# configure). Thiếu một trong hai thì in "cpu". Luôn thoát 0, không cần quyền root, không đổi gì trên máy. make env,
# make install dùng để gợi ý (docs/van-hanh.md mục Chạy mô hình bằng GPU).
set -u
if nvidia-smi -L 2>/dev/null | grep -q '^GPU ' \
  && docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q '"nvidia"'; then
  echo gpu
else
  echo cpu
fi
