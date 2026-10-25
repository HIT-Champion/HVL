// Copyright 2026 Signet Team
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// SPDX-License-Identifier: Apache-2.0

// Cờ kiểm chất lượng số liệu (F3.9, F3.11) trên trang Điều hành và trang Phả hệ: Đạt / Cảnh báo / Trượt.
// - Số liệu báo cáo: office.report_checks tính bộ luật trong CSDL lúc truy vấn (migration 1792281603300), mỗi dòng một
//   luật trên một khung nhìn kèm số. Cờ của một biểu đồ là cờ nặng nhất trong các luật của các khung nhìn mà biểu đồ
//   dùng (BOARD_CHARTS của utils/lineage.ts).
// - Nộp lưu: assertion mà svc-files đã ghi trong sự kiện OpenLineage (facet dataQualityAssertions, svc_files.lineage) —
//   lấy nguyên văn từ core.lineage_events, không tính lại.
// Chỉ import kiểu: tệp chạy được thẳng bằng node --test.





// Các luật của office.report_checks, theo thứ tự hiện trên trang; db/tests/test_report_checks.py đối chiếu với CSDL
export const REPORT_RULES = ['status_total', 'department_total', 'processing_coverage', 'unique_keys',
'no_personal_columns'];

// Một dòng office.report_checks; ý nghĩa expected / actual / issues / detail theo từng luật (migration, locales)










const SEVERITY = { PASSED: 0, WARNING: 1, FAILED: 2 };
// Luật có detail đáng hiện: trạng thái biểu đồ không vẽ, tháng có tổng giờ âm, tên cột cá nhân
const DETAILED = ['status_total', 'processing_coverage', 'no_personal_columns'];

/** Cờ nặng nhất của một tập cờ; không có cờ nào: null. */
export function worstCheck(statuses) {
  let worst = null;
  for (const s of statuses) if (s && (!worst || SEVERITY[s] > SEVERITY[worst])) worst = s;
  return worst;
}

function ruleOrder(rule) {
  const i = REPORT_RULES.indexOf(rule);
  return i < 0 ? REPORT_RULES.length : i;
}

/** Các luật trên những khung nhìn đã cho: nặng trước, rồi theo thứ tự REPORT_RULES, rồi theo tên khung nhìn. */
export function checksFor(checks, views) {
  return checks.filter((c) => views.includes(c.report)).sort((a, b) => SEVERITY[b.status] - SEVERITY[a.status] ||
  ruleOrder(a.rule) - ruleOrder(b.rule) || a.report.localeCompare(b.report));
}

/** Cờ của một biểu đồ trang Điều hành: nặng nhất trong các luật của các khung nhìn biểu đồ dùng. */
export function chartCheck(checks, chart) {
  return worstCheck(checksFor(checks, chart.views).map((c) => c.status));
}

/** Câu số liệu của một luật: [khóa i18n, tham số] — câu chính, và câu detail khi có. */
export function checkMessages(c) {
  const params = { expected: c.expected, actual: c.actual, issues: c.issues, detail: (c.detail ?? []).join(', ') };
  const lines = [[`quality.rules.${c.rule}.figures`, params]];
  if (c.detail?.length && DETAILED.includes(c.rule)) lines.push([`quality.rules.${c.rule}.detail`, params]);
  return lines;
}

// --- Nộp lưu -------------------------------------------------------------------------------------------------













/** Bảng của một đối tượng Parquet trong gói: cold/<đơn vị>/case/<hồ sơ>/documents-<sha256>.parquet → documents. */
export function parquetTable(name) {
  const m = /([^/]+?)(?:-[0-9a-f]{64})?\.parquet$/.exec(name);
  return m ? m[1] : name;
}

function assertionKey(a) {
  return `${a.dataset}|${a.assertion}|${a.column ?? ''}`;
}

// Gộp trùng theo bảng + assertion + cột; cùng một mục mà nơi đạt nơi trượt thì giữ trượt
function merge(list) {
  const seen = new Map();
  for (const a of list) {
    const prev = seen.get(assertionKey(a));
    if (!prev || prev.success && !a.success) seen.set(assertionKey(a), a);
  }
  return [...seen.values()];
}

/** Assertion có trong một sự kiện, nguyên văn: facet của dataset (bước tables ghi ở đầu ra) và inputFacets của đầu vào
 * (bước manifest mang lại đúng các mục đó). Sự kiện không kèm nguyên văn: rỗng. */
export function eventAssertions(e) {
  const event = e.event ?? {};
  const list = [];
  const take = (d, facets) => {
    for (const a of facets?.dataQualityAssertions?.assertions ?? []) {
      list.push({ dataset: parquetTable(d.name ?? ''), assertion: a.assertion ?? '?',
        ...(a.column ? { column: a.column } : {}), success: a.success === true });
    }
  };
  for (const d of event.outputs ?? []) take(d, d.facets);
  for (const d of event.inputs ?? []) {
    take(d, d.facets);
    take(d, d.inputFacets);
  }
  return merge(list);
}

/** Cờ của một bước nộp lưu: Trượt khi có assertion trượt, Đạt khi mọi assertion đạt; bước không kiểm gì (chép tệp,
 * ghi lại CSDL): null. Sự kiện không kèm nguyên văn thì theo cột quality_ok. */
export function stepCheck(e) {
  const list = eventAssertions(e);
  if (list.length) return list.some((a) => !a.success) ? 'FAILED' : 'PASSED';
  return e.quality_ok === true ? 'PASSED' : e.quality_ok === false ? 'FAILED' : null;
}

/** Kết quả kiểm của một lượt nộp lưu (các sự kiện của run cha và các bước con): assertion gộp trùng giữa các bước.
 * Lượt không ghi assertion nào là Cảnh báo — không có gì bảo chứng số dòng, cột bắt buộc của gói (vd ghi phả hệ của
 * bước tables lỗi: svc-files chỉ cảnh báo trong nhật ký, nộp lưu vẫn chạy tiếp). */
export function runCheck(events) {
  const assertions = merge(events.flatMap(eventAssertions));
  const status = !assertions.length ? 'WARNING' : assertions.some((a) => !a.success) ? 'FAILED' : 'PASSED';
  return { status, assertions };
}

/** Assertion theo từng bảng của gói, giữ thứ tự xuất hiện: số mục, số mục trượt và các mục trượt. */
export function assertionsByTable(list) {
  const tables = new Map();
  for (const a of list) {
    const row = tables.get(a.dataset) ?? { dataset: a.dataset, total: 0, failed: [] };
    row.total++;
    if (!a.success) row.failed.push(a);
    tables.set(a.dataset, row);
  }
  return [...tables.values()];
}
