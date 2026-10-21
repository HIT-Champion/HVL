// Copyright 2026 Mộc Team
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

import { useI18n } from 'vue-i18n'

// Hiện một dòng sổ kiểm toán cho người đọc: ai làm, nhãn thao tác, các cột đã đổi. Dùng chung cho trang Sổ kiểm toán
// (F2.12) và tab Lịch sử của văn bản (F3.5). Dòng chỉ có `overview`: cột chứa nội dung (trích yếu, tên tệp, ý kiến…)
// có tên mà không có giá trị — gom lại một dòng "trường khác đã đổi".

export interface AuditRow {
  action: string
  actor_id: string
  actor_kind: string
  // trigger ghi {cột: [cũ, mới]}; sự kiện dịch vụ tự ghi (vd file.rejected) thì {trường: giá trị}
  overview: Record<string, unknown>
}

// cột không cần hiện: khóa, mốc thời gian tự đặt, id liên kết
const HIDDEN = new Set(['id', 'tenant_id', 'created_at', 'updated_at', 'created_by', 'object_key', 'document_id',
  'file_id', 'case_file_id'])

// units: tên đơn vị khác trong hệ thống (liên thông, F3.12) — không có thì hiện id
export function useAuditFormat(names: { value: Map<string, string> }, departments: { value: Map<string, string> },
  units?: { value: Map<string, string> }) {
  const { t, te } = useI18n()

  function label(map: string, key: string) {
    return te(`${map}.${key}`) ? t(`${map}.${key}`) : key
  }

  // Trạm quét chặn tệp vì không mở được để quét (có mật khẩu, nén quá sâu — mẫu Heuristics.Encrypted.*,
  // Heuristics.Limits.Exceeded.* của ClamAV, svc-files/clamav.py) khác với chặn vì nhiễm mã độc: cùng sự kiện
  // file.rejected, nhãn theo mẫu
  function action(row: AuditRow) {
    const sig = row.overview.signature
    if (row.action === 'file.rejected' && typeof sig === 'string'
      && (sig.startsWith('Heuristics.Encrypted.') || sig.startsWith('Heuristics.Limits.Exceeded'))) {
      return label('audit.action', 'file.unscannable')
    }
    return label('audit.action', row.action)
  }

  // Dịch vụ ghi thay người dùng (vai trò service) thì actor_id vẫn là người đó; tài khoản dịch vụ, việc tự chạy và
  // ghi thẳng CSDL thì là "Hệ thống"; tác tử (F4.1, vd moc-doc-reader đọc văn bản đến) có tên riêng
  function who(row: AuditRow) {
    if (row.actor_kind === 'agent') return t('audit.agent', { name: label('audit.agents', row.actor_id) })
    const name = names.value.get(row.actor_id)
    if (row.actor_kind === 'service') return name ? t('audit.service', { name }) : t('event.system')
    if (row.actor_kind === 'system') return t('event.system')
    return name ?? row.actor_id
  }

  function show(col: string, value: unknown): string {
    if (value === null || value === undefined || value === '') return '—'
    if (typeof value === 'boolean') return value ? t('audit.yes') : t('audit.no')
    if (typeof value === 'string' && value.startsWith('\\x')) return `${value.slice(2, 12)}…`
    // trạng thái văn bản; sự kiện đọc văn bản (intake.suggested) có trạng thái riêng: ok, empty, unreadable; trợ lý
    // hỏi đáp (assistant.answered, F4.2): answered, passages_only, no_evidence
    if (col === 'status') {
      if (te(`status.${value}`)) return t(`status.${value}`)
      return te(`audit.readStatus.${value}`) ? t(`audit.readStatus.${value}`) : label('assist.status', String(value))
    }
    if (col === 'urgency') return label('urgency', String(value))
    if (col === 'direction' || col === 'role') return label(`audit.${col}`, String(value))
    if (col === 'user_id' || col === 'signer_id') return names.value.get(String(value)) ?? String(value)
    if (col === 'department_id') return departments.value.get(String(value)) ?? String(value)
    if (col === 'to_tenant_id') return units?.value.get(String(value)) ?? String(value)
    if (col === 'registered_at' || col === 'archived_at' || col === 'delivered_at') return fmtDateTime(String(value))
    if (col === 'due_on' || col === 'issued_on' || col === 'closed_on') return fmtDate(String(value))
    // băm gói nộp lưu: sự kiện case_file.archived ghi dạng hex, không có tiền tố \x
    if (col === 'archive_sha256') return `${String(value).replace(/^\\x/, '').slice(0, 10)}…`
    if (col === 'size_bytes' && typeof value === 'number') return fmtSize(value)
    // đọc văn bản đến (F4.1): trường đọc được ghi thành chuỗi "symbol,issued_on,…" (diff không chứa mảng)
    if (col === 'found') {
      return String(value).split(',').map((k) => k.trim()).filter(Boolean)
        .map((k) => label('receive.read.field', k)).join(', ') || '—'
    }
    if (col === 'duration_ms' && Number.isFinite(Number(value))) {
      return t('audit.seconds', { n: fmtNumber(Math.round(Number(value) / 100) / 10) })
    }
    if (col === 'method') return label('receive.read.method', String(value))
    if (col === 'summary_source') return label('audit.summarySource', String(value))
    if (col === 'reason') return label('receive.read.reason', String(value))
    // trợ lý hỏi đáp (F4.2): chế độ hỏi, nguồn câu trả lời; cảnh báo ghi thành chuỗi "model_timeout,…"
    if (col === 'mode') return label('audit.askMode', String(value))
    if (col === 'answer_source') return label('audit.answerSource', String(value))
    if (col === 'warnings') {
      return String(value).split(',').map((k) => k.trim()).filter(Boolean)
        .map((k) => label('assist.warning', k)).join('; ') || '—'
    }
    return String(value)
  }

  // Các thay đổi để hiện: cột có giá trị trước, cột nội dung (giá trị ẩn) gom lại một dòng
  function changes(row: AuditRow) {
    const shown: { col: string; text: string }[] = []
    const hidden: string[] = []
    for (const [col, value] of Object.entries(row.overview)) {
      if (HIDDEN.has(col)) continue
      // sự kiện đọc văn bản, trợ lý hỏi đáp chỉ ghi siêu dữ liệu: null là không có (không dùng mô hình, không lỗi),
      // không phải trường nội dung bị ẩn
      if (value === null && (row.action === 'intake.suggested' || row.action === 'assistant.answered')) continue
      if (value === null) {
        hidden.push(label('audit.col', col))
        continue
      }
      if (!Array.isArray(value)) {
        shown.push({ col: label('audit.col', col), text: show(col, value) })
        continue
      }
      const [before, after] = value
      if (row.action === 'insert' && (after === null || after === false)) continue
      const text = row.action === 'insert' ? show(col, after)
        : row.action === 'delete' ? show(col, before)
          : `${show(col, before)} → ${show(col, after)}`
      shown.push({ col: label('audit.col', col), text })
    }
    return { shown, hidden }
  }

  return { label, action, who, show, changes }
}
