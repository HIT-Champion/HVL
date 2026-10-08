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
import { BarChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { init, use } from 'echarts/core';
import { SVGRenderer } from 'echarts/renderers';

// Biểu đồ Apache ECharts (dashboard điều hành, F3.11). Chỉ nạp phần dùng đến; vẽ SVG để chữ sắc khi in và chụp.
// Số liệu luôn có bảng đi kèm ở trang gọi: biểu đồ chỉ để nhìn nhanh, aria-label tóm tắt cho trình đọc màn hình.
use([BarChart, GridComponent, LegendComponent, TooltipComponent, SVGRenderer]);
const props = defineProps({
  option: {
    type: Object,
    required: true
  },
  label: {
    type: String,
    required: true
  },
  height: Number
});
const el = ref(null);
let chart = null;
let observer = null;

// Cùng phông chữ với trang
function withFont(option) {
  const fontFamily = el.value ? getComputedStyle(el.value).fontFamily : undefined;
  return {
    textStyle: {
      fontFamily
    },
    ...option
  };
}
onMounted(() => {
  if (!el.value) return;
  chart = init(el.value, undefined, {
    renderer: 'svg'
  });
  chart.setOption(withFont(props.option));
  observer = new ResizeObserver(() => chart?.resize());
  observer.observe(el.value);
});
watch(() => props.option, option => chart?.setOption(withFont(option), true));
onBeforeUnmount(() => {
  observer?.disconnect();
  chart?.dispose();
});
</script>

<template>
  <div ref="el" role="img" :aria-label="label" class="w-full" :style="{ height: `${height ?? 256}px` }" />
</template>
