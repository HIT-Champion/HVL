<!--
  Copyright 2026 Signet Team

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.

  SPDX-License-Identifier: Apache-2.0
-->

<script setup>
definePageMeta({ layout: false });
const summary = ref('Về việc cử sinh viên tham gia cuộc thi Olympic Tin học');
const urgency = ref('normal');
const status = ref('received');
const notice = useNotice();

function save() {
  if (!summary.value.trim()) {
    notice.error('Anh nhập trích yếu trước nhé.');
    return;
  }
  notice.ok('Đã thử thông báo thành công. Đây là dữ liệu mẫu, chưa lưu lên hệ thống.');
}
</script>

<template>
  <main class="mx-auto max-w-5xl px-4 py-8 md:px-8 md:py-12">
    <p class="mb-3 text-sm font-medium text-brand-800">Khu phát triển FE · Dữ liệu mẫu</p>
    <PageHeader
      title="Signet — Base giao diện"
      subtitle="Nuxt · JavaScript · Tailwind. Thử component tại đây trước khi nối vào màn hình nghiệp vụ."
    />

    <div class="grid items-start gap-6 md:grid-cols-2">
      <section class="card space-y-5 p-5 md:p-6" aria-labelledby="form-title">
        <h2 id="form-title" class="text-lg font-semibold">Thử biểu mẫu</h2>
        <div>
          <label class="label" for="summary">Trích yếu</label>
          <textarea id="summary" v-model="summary" class="input" rows="3" />
        </div>
        <div>
          <label class="label" for="urgency">Độ khẩn</label>
          <select id="urgency" v-model="urgency" class="input">
            <option value="normal">Bình thường</option>
            <option value="khan">Khẩn</option>
            <option value="thuong_khan">Thượng khẩn</option>
            <option value="hoa_toc">Hỏa tốc</option>
          </select>
        </div>
        <div>
          <label class="label" for="status">Trạng thái</label>
          <select id="status" v-model="status" class="input">
            <option value="received">Đã tiếp nhận</option>
            <option value="registered">Đã vào sổ</option>
            <option value="in_progress">Đang xử lý</option>
            <option value="done">Hoàn thành</option>
          </select>
        </div>
        <div class="flex flex-wrap gap-3">
          <button class="btn-primary" @click="save">Thử thông báo</button>
          <button class="btn-secondary" @click="summary = ''">Xóa nội dung</button>
          <button class="btn-secondary" disabled>Đang xử lý</button>
        </div>
      </section>

      <section class="space-y-5" aria-labelledby="preview-title">
        <h2 id="preview-title" class="text-lg font-semibold">Xem trước văn bản</h2>
        <article class="card space-y-4 p-5 md:p-6">
          <div class="flex flex-wrap items-center gap-2">
            <StatusChip :status="status" />
            <UrgencyChip :urgency="urgency" />
          </div>
          <h3 class="break-words text-lg font-medium">{{ summary || 'Chưa nhập trích yếu' }}</h3>
          <dl class="space-y-3 text-sm">
            <div class="flex flex-wrap justify-between gap-2">
              <dt class="text-stone-500">Số ký hiệu mẫu</dt>
              <dd>01/CV-DEMO</dd>
            </div>
            <div class="flex flex-wrap justify-between gap-2">
              <dt class="text-stone-500">Đơn vị mẫu</dt>
              <dd>Khoa Công nghệ thông tin</dd>
            </div>
          </dl>
        </article>
        <p class="text-sm leading-relaxed text-stone-600">
          Trang này chỉ có khi chạy dev và không gọi backend. Sửa style chung trong
          app/assets/css/main.css; sửa component trong app/components.
          Các trang nghiệp vụ vẫn yêu cầu đăng nhập SSO.
        </p>
      </section>
    </div>
  </main>
</template>
