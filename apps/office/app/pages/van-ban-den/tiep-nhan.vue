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

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { schemas, vanBanDen } from 'virtual:moc-forms'
import { ApiError } from '~/composables/useApi'
import type { ReadFieldKey, ReadResult, UploadedFile } from '~/composables/useApi'
import { formErrors } from '~/utils/forms'
import type { FieldErrors } from '~/utils/forms'
import { FIELD_WARNINGS, READ_KEYS, acceptOffer, applySuggestion, openOffer } from '~/utils/suggest'
import type { SuggestMap } from '~/utils/suggest'

// Tiếp nhận văn bản đến (F2.2). Poka-yoke lớp 1: kiểm ngay trên form theo schemas/van-ban-den.json — cùng tệp mà
// svc-workflow kiểm lại khi nhận Action receiveIncoming (lớp 2); CSDL chặn lần cuối bằng ràng buộc CHECK (lớp 3).
// Độ dài tối đa, danh mục độ khẩn cũng đọc từ schema, không viết lại ở đây.
//
// Đọc văn bản đến (F4.1): tệp chính quét sạch, không hạn chế thì tác tử moc-doc-reader (svc-files) tự đọc một lần và
// điền sẵn các ô còn trống, mỗi ô gắn nhãn "Gợi ý". Không bao giờ ghi đè chữ văn thư đã gõ: ô văn thư đã chạm hoặc
// đang có focus chỉ nhận gợi ý; chỉ tệp nguồn của form được điền, đọc tệp khác (phụ lục) chỉ đưa ra gợi ý
// (app/utils/suggest.ts). Văn thư đối chiếu, sửa, bấm lưu mới tạo văn bản (receiveIncoming như cũ). Tệp của văn bản
// hạn chế không bao giờ đọc.

interface ReadState {
  state: 'reading' | 'done' | 'empty' | 'error'
  started: number
  method?: ReadResult['method']
  cached?: boolean
  message?: string
  notes?: string[]   // cảnh báo của lần đọc không gắn với ô nào (chữ ít, mô hình…)
}

interface PendingFile {
  key: number
  name: string
  size: number
  progress: number
  state: 'uploading' | 'clean' | 'infected' | 'error'
  message?: string
  uploaded?: UploadedFile
  read?: ReadState
}

const SCHEMA = schemas.vanBanDen
const FIELDS = SCHEMA.properties ?? {}
const URGENCIES = FIELDS.urgency?.enum as string[]
const maxLength = (field: string) => FIELDS[field]?.maxLength as number | undefined

// Chữ chép từ PDF hay dính ký tự ẩn (rộng 0, gạch nối mềm, điều khiển) và dạng Unicode tổ hợp: mắt không thấy nhưng
// làm hỏng chặn trùng. Form tự dọn trước khi kiểm và gửi; svc-workflow, CSDL không tự sửa mà từ chối.
const oneLine = (s: string) => s.normalize('NFC').replace(/[\t\n\v\f\r\p{Zl}\p{Zp}]+/gu, ' ')
  .replace(/[\p{Cc}\p{Cf}]/gu, '').trim()
const multiLine = (s: string) => s.normalize('NFC').replace(/\r\n?|[\p{Zl}\p{Zp}]/gu, '\n')
  .replace(/[\t\v\f]+/g, ' ').replace(/[^\n\P{Cc}]|\p{Cf}/gu, '').trim()

const { t, te } = useI18n()
const { gql, upload, readFile } = useApi()
const notice = useNotice()
const router = useRouter()
const claims = useAuth().claims

const types = ref<{ code: string; name: string }[]>([])
const files = ref<PendingFile[]>([])
const dragging = ref(false)
const saving = ref(false)
const tried = ref(false)
const duplicate = ref<{ symbol: string; issuer_name: string; issued_on: string } | null>(null)
const serverErrors = ref<FieldErrors>({})   // lỗi svc-workflow trả về (lớp 2), xóa khi người dùng sửa form
let nextKey = 1

// Giá trị ban đầu của hai ô chọn: gợi ý của tác tử coi ô còn giá trị này là chưa chọn
const DEFAULTS = { type_code: 'CV', urgency: 'normal' }

const form = reactive({
  ...DEFAULTS,
  symbol: '',
  issuer_name: '',
  issued_on: '',
  summary: '',
  due_on: '',
  restricted: false,
})

// Gợi ý của tác tử đang áp lên form: ô mang giá trị tác tử điền (nhãn Gợi ý / Đã sửa), gợi ý chưa điền (Dùng), cảnh
// báo gắn với ô (hiện tới khi ô đổi giá trị)
const suggested = ref<SuggestMap>({})
const offers = ref<SuggestMap>({})
const readWarnings = ref<{ code: string; key: ReadFieldKey; at: string }[]>([])
const source = ref<number | null>(null)   // tệp nguồn: tệp có kết quả đọc đang áp lên form
// Ô văn thư đã chạm (gõ, chọn, soạn chữ bằng bộ gõ, bấm Dùng): kết quả đọc về sau không bao giờ tự đổi ô đó, chỉ đưa
// ra gợi ý — xét theo việc chạm, không theo giá trị (ô ngày gõ dở, chữ đang soạn vẫn là '' trong form)
const touched = ref<ReadFieldKey[]>([])
const announce = ref('')                  // vùng aria-live: đang đọc, đọc xong, lỗi
const now = ref(Date.now())
let autoArmed = true                      // còn được tự đọc tệp chính
let readSeq = 0

// Hết phiên giữa chừng: quay lại sau khi đăng nhập vẫn còn phần đã nhập và tệp đã quét. Văn bản hạn chế thì không
// giữ (trích yếu không nằm lại trong trình duyệt)
interface Kept {
  form: typeof form
  files: { name: string; size: number; uploaded: UploadedFile }[]
  read?: { suggested: SuggestMap; offers: SuggestMap; touched?: ReadFieldKey[]; source?: string | null }
}
const draft = useFormDraft<Kept>(
  () => (claims.value ? `${claims.value.userId}:tiep-nhan` : null),
  () => (form.restricted ? null : {
    form: { ...form },
    files: files.value.filter((f) => f.state === 'clean' && f.uploaded)
      .map((f) => ({ name: f.name, size: f.size, uploaded: f.uploaded! })),
    read: {
      suggested: suggested.value, offers: offers.value, touched: touched.value,
      source: files.value.find((f) => f.key === source.value)?.uploaded?.id ?? null,   // key đổi khi khôi phục, id thì không
    },
  }),
  (kept) => {
    Object.assign(form, kept.form)
    files.value = kept.files.map((f) => ({ key: nextKey++, name: f.name, size: f.size, progress: 100, state: 'clean' as const, uploaded: f.uploaded }))
    suggested.value = kept.read?.suggested ?? {}
    offers.value = kept.read?.offers ?? {}
    touched.value = (kept.read?.touched ?? []).filter((k) => READ_KEYS.includes(k))
    source.value = files.value.find((f) => kept.read?.source && f.uploaded?.id === kept.read.source)?.key ?? null
    // tệp đã tải trước khi hết phiên: không tự đọc lại (form đã có phần đã nhập); cần thì văn thư bấm Đọc văn bản
    if (kept.files.length) autoArmed = false
  },
)

// Tải danh mục loại văn bản; lỗi thì báo ngay trên trang kèm nút Thử lại (gọi lại hàm này). Bản dở chỉ khôi phục
// một lần: bấm Thử lại không đè lên phần văn thư đã nhập sau đó
const initialFailure = ref('')
let restored = false
async function loadInitial() {
  initialFailure.value = ''
  if (claims.value?.role !== 'clerk') return router.replace('/van-ban-den')
  if (!restored) {
    restored = true
    if (draft.resume()) notice.info(t('compose.restored'))
  }
  try {
    const data = await gql<{ office_document_types: { code: string; name: string }[] }>(
      '{ office_document_types(order_by: {name: asc}) { code name } }',
    )
    types.value = data.office_document_types
  } catch (e) {
    initialFailure.value = errorText(t, e)
  }
}
onMounted(loadInitial)

const uploading = computed(() => files.value.some((f) => f.state === 'uploading'))
const cleanFiles = computed(() => files.value.filter((f) => f.state === 'clean'))

// Dữ liệu gửi đi, đúng hình schema mô tả: chuỗi đã dọn, ô bắt buộc để trống thì thiếu trường
const payload = computed(() => ({
  type_code: form.type_code,
  symbol: oneLine(form.symbol) || undefined,
  issuer_name: oneLine(form.issuer_name) || undefined,
  issued_on: form.issued_on || undefined,
  summary: multiLine(form.summary) || undefined,
  urgency: form.urgency,
  due_on: form.due_on || null,
  restricted: form.restricted,
  file_ids: cleanFiles.value.map((f) => f.uploaded!.id),
}))

// Lỗi form tự thấy thì chặn bấm lưu; lỗi svc-workflow trả về chỉ để hiện (sửa bất cứ gì là xóa, gửi lại được):
// form cũ trong trình duyệt có thể lệch schema mới, chặn theo lỗi đó thì nút lưu không còn tác dụng
const clientErrors = computed<FieldErrors>(() => {
  const e = formErrors(vanBanDen, SCHEMA, payload.value, today())
  if (duplicate.value && !e.symbol) e.symbol = 'duplicate'
  return e
})
const errors = computed<FieldErrors>(() => ({ ...serverErrors.value, ...clientErrors.value }))
watch(payload, () => { serverErrors.value = {} }, { deep: true })

// Mã lỗi (chung với svc-workflow) → câu cho người nhập; số giới hạn lấy từ schema
function message(field: string, code: string): string {
  const rule = FIELDS[field] ?? {}
  if (code === 'minLength' || code === 'maxLength') {
    return Number(rule.minLength) > 1
      ? t('validation.between', { min: rule.minLength, max: rule.maxLength })
      : t('validation.max', { max: rule.maxLength })
  }
  if (code === 'x-moc-date') return t(rule['x-moc-date'] === 'not-after-today' ? 'validation.dateFuture' : 'validation.dueBefore')
  if (code === 'x-moc-nfc') return t('validation.nfc')
  if (code === 'pattern' && rule.format === 'date') return t('validation.year')
  return t(`validation.${code}`)
}

const show = (field: string) => (tried.value && errors.value[field] ? message(field, errors.value[field]!) : undefined)
const summaryLength = computed(() => [...multiLine(form.summary)].length)   // theo ký tự, như schema đếm

// Văn bản hạn chế (F3.7): tệp tải lên ở chế độ hạn chế — chỉ PDF, svc-files mã hóa trước khi lưu. Đã có tệp thì không
// đổi chế độ được nữa (tệp đã lưu theo chế độ cũ; svc-workflow và CSDL cũng chặn), phải gỡ tệp trước.
function addFiles(list: FileList | null) {
  for (const file of Array.from(list ?? [])) {
    const item = reactive<PendingFile>({ key: nextKey++, name: file.name, size: file.size, progress: 0, state: 'uploading' })
    files.value.push(item)
    if (form.restricted && file.type !== 'application/pdf') {
      item.state = 'error'
      item.message = t('receive.pdfOnly')
      continue
    }
    upload(file, (p) => { item.progress = p }, form.restricted)
      .then((res) => { item.state = 'clean'; item.uploaded = res })
      .catch((e) => {
        if (e?.code === 'infected') {
          item.state = 'infected'
          item.message = t('receive.infected', { sig: e.message })
        } else {
          item.state = 'error'
          item.message = errorText(t, e)
        }
      })
  }
}

function onDrop(e: DragEvent) {
  dragging.value = false
  addFiles(e.dataTransfer?.files ?? null)
}

function removeFile(key: number) {
  files.value = files.value.filter((f) => f.key !== key)
  // gỡ tệp nguồn: bỏ gợi ý của nó — ô tác tử điền mà văn thư chưa chạm trở về như cũ; chữ văn thư gõ, ô văn thư đã
  // chạm (kể cả gợi ý đã bấm Dùng) giữ nguyên
  if (key === source.value) {
    const out = applySuggestion(form, DEFAULTS, suggested.value, null, { touched: touched.value })
    Object.assign(form, out.values)
    suggested.value = out.suggested
    offers.value = {}
    readWarnings.value = []
    source.value = null
    autoArmed = true
  }
  if (!files.value.length) autoArmed = true
}

// ---- Đọc văn bản đến (F4.1) ----

const reading = computed(() => files.value.some((f) => f.read?.state === 'reading'))
const hasSuggestions = computed(() => READ_KEYS.some((k) => suggested.value[k]))

// Chỉ tệp đã quét sạch, không mã hóa, form không ở chế độ hạn chế; svc-files cũng từ chối tệp mã hóa (409)
const readable = (f: PendingFile) => f.state === 'clean' && !!f.uploaded && !f.uploaded.encrypted && !form.restricted

// Tệp chính (tệp đầu tiên không bị chặn — tệp đầu là bản chính) quét sạch: tự đọc một lần, khi form chưa có kết quả
// đọc nào và không có lượt đọc khác đang chạy
const mainFile = computed(() => files.value.find((f) => f.state !== 'infected' && f.state !== 'error'))
watch(() => [mainFile.value?.key, mainFile.value?.state, reading.value, source.value], () => {
  const f = mainFile.value
  if (!autoArmed || !f || f.read || !readable(f) || reading.value || source.value !== null) return
  autoArmed = false
  readDocument(f, false)
})

// Đồng hồ giây trên dòng tệp đang đọc
let ticker: ReturnType<typeof setInterval> | undefined
watch(reading, (on) => {
  clearInterval(ticker)
  if (!on) return
  now.value = Date.now()
  ticker = setInterval(() => { now.value = Date.now() }, 1000)
})
onBeforeUnmount(() => clearInterval(ticker))
const elapsed = (f: PendingFile) => Math.max(0, Math.floor((now.value - (f.read?.started ?? now.value)) / 1000))

// Báo cho trình đọc màn hình (aria-live): xóa rồi mới đặt, để câu trùng lần trước vẫn được đọc
function say(message: string) {
  announce.value = ''
  nextTick(() => { announce.value = message })
}

// Đã có kết quả (đọc được hoặc không ra gì) thì "Đọc lại" bỏ qua gợi ý đã lưu (force); lần đầu, lỗi thì "Đọc văn bản"
const readAgain = (f: PendingFile) => f.read?.state === 'done' || f.read?.state === 'empty'

async function readDocument(item: PendingFile, force: boolean) {
  if (!readable(item) || reading.value) return
  const seq = ++readSeq
  const started = Date.now()
  item.read = { state: 'reading', started }
  say(t('receive.read.started', { name: item.name }))
  // tệp đã bị gỡ, hoặc có lượt đọc mới hơn: bỏ kết quả
  const stale = () => seq !== readSeq || !files.value.includes(item)
  let res: ReadResult
  try {
    res = await readFile(item.uploaded!.id, force)
  } catch (e) {
    if (stale()) return
    const message = readError(e)
    item.read = { state: 'error', started, message }
    say(message)
    return
  }
  if (stale()) return
  // Chỉ tệp nguồn (hoặc khi form chưa theo tệp nào) mới được điền ô; tệp khác (phụ lục…) chỉ đưa ra gợi ý, để giá trị
  // đọc từ bản chính không bị mất hay bị thay. Ô văn thư đã chạm, ô đang có focus lúc kết quả về: chỉ đưa ra.
  const primary = source.value === null || source.value === item.key
  const focus = FIELD_IDS[document.activeElement?.id ?? '']
  const out = applySuggestion(form, DEFAULTS, suggested.value, res, {
    types: types.value.map((ty) => ty.code), urgencies: URGENCIES,
    touched: focus ? [...touched.value, focus] : touched.value, offerOnly: !primary,
  })
  Object.assign(form, out.values)
  suggested.value = out.suggested
  offers.value = out.offers
  const warnings = Array.isArray(res.warnings) ? res.warnings : []
  if (primary) {
    source.value = item.key
    readWarnings.value = warnings.flatMap((code) => {
      const key = FIELD_WARNINGS[code]
      return key ? [{ code, key, at: form[key] }] : []
    })
  }
  const method = t(`receive.read.method.${res.method === 'ocr' ? 'ocr' : 'text'}`)
  const offered = Object.keys(out.offers).length
  const main = files.value.find((f) => f.key === source.value)?.name ?? ''
  const message = res.status === 'empty' ? t('receive.read.empty')
    : !primary ? (offered ? t('receive.read.doneOther', { method, name: main, n: offered }, offered)
      : t('receive.read.doneOtherNone', { method, name: main }))
      : out.filled.length ? t('receive.read.done', { method, n: out.filled.length }, out.filled.length)
        : t('receive.read.doneNone', { method })
  item.read = {
    state: res.status === 'empty' ? 'empty' : 'done', started, method: res.method, cached: res.cached, message,
    notes: warnings.filter((code) => !FIELD_WARNINGS[code] && te(`receive.read.warning.${code}`))
      .map((code) => t(`receive.read.warning.${code}`)),
  }
  say(message)
  // tra trùng lỗi thì thôi: svc-workflow vẫn chặn trùng khi lưu
  if (out.filled.length) checkDuplicate().catch(() => {})
}

// Mã lỗi của svc-files → câu cho văn thư (không dùng utils/errors.ts: mã riêng của chức năng đọc)
function readError(e: unknown): string {
  if (!(e instanceof ApiError)) return t('receive.read.error.generic', { msg: e instanceof Error ? e.message : String(e) })
  if (e.code === 'unreadable') {
    const reason = te(`receive.read.reason.${e.reason}`) ? `receive.read.reason.${e.reason}` : 'receive.read.reason.unknown'
    return t('receive.read.error.unreadable', { reason: t(reason) })
  }
  if (e.code && te(`receive.read.error.${e.code}`)) return t(`receive.read.error.${e.code}`)
  return errorText(t, e)   // mạng, hết phiên, giới hạn tốc độ của cổng; còn lại là thông điệp máy chủ
}

// Văn thư chạm vào ô (gõ, chọn, bắt đầu soạn chữ bằng bộ gõ): từ đây kết quả đọc không tự đổi ô đó
function touch(key: ReadFieldKey) {
  if (!touched.value.includes(key)) touched.value = [...touched.value, key]
}
// Ô ngày: gõ dở thì giá trị vẫn '' và chưa có sự kiện input — phím gõ chữ số, xóa cũng tính là chạm (Tab thì không)
function touchDate(e: KeyboardEvent) {
  if (e.key.length === 1 || e.key === 'Backspace' || e.key === 'Delete') touch('issued_on')
}
// id của ô trên trang → khóa trường (ô đang có focus lúc kết quả về)
const FIELD_IDS: Record<string, ReadFieldKey> = { type: 'type_code', urgency: 'urgency', symbol: 'symbol',
  issued_on: 'issued_on', issuer: 'issuer_name', summary: 'summary' }

// Văn thư bấm "Dùng" ở một gợi ý chưa điền: đó là quyết định của văn thư, lần đọc sau không tự đổi ô này nữa
function takeOffer(key: ReadFieldKey) {
  const out = acceptOffer(suggested.value, offers.value, key)
  if (!out) return
  touch(key)
  form[key] = out.value
  suggested.value = out.suggested
  offers.value = out.offers
  checkDuplicate().catch(() => {})
}

// Giá trị gợi ý để hiện: tên loại văn bản, nhãn độ khẩn, ngày kiểu Việt Nam
function shown(key: ReadFieldKey, value: string): string {
  if (key === 'type_code') return types.value.find((ty) => ty.code === value)?.name ?? value
  if (key === 'urgency') return te(`urgency.${value}`) ? t(`urgency.${value}`) : value
  if (key === 'issued_on') return fmtDate(value)
  return value
}

// Dưới mỗi ô: cảnh báo của lần đọc (tới khi ô đổi giá trị) và gợi ý chưa điền
const notes = computed(() => Object.fromEntries(READ_KEYS.map((key) => {
  const offer = openOffer(offers.value, form, key)
  return [key, {
    warnings: readWarnings.value.filter((w) => w.key === key && form[key] === w.at)
      .map((w) => t(`receive.read.warning.${w.code}`)),
    offer: offer ? shown(key, offer.value) : '',
  }]
})) as Record<ReadFieldKey, { warnings: string[]; offer: string }>)

// Ô nhập trỏ tới nhãn gợi ý, gợi ý chưa điền để trình đọc màn hình đọc kèm
const describedBy = (key: ReadFieldKey) => [show(key) && `${key}-error`,
  suggested.value[key] && `${key}-suggest`, notes.value[key].offer && `${key}-offer`]
  .filter(Boolean).join(' ') || undefined

// Chặn trùng: cùng cơ quan ban hành, số ký hiệu, ngày ban hành (NĐ 30) — báo ngay khi rời ô, chưa cho lưu. Chỉ tra
// được văn bản người này thấy; svc-workflow tra lại trên mọi văn bản của đơn vị, CSDL có chỉ mục chặn trùng.
async function checkDuplicate() {
  duplicate.value = null
  const { symbol, issuer_name: issuer, issued_on: day } = payload.value
  if (!symbol || !issuer || !day) return
  const data = await gql<{ office_documents: { symbol: string; issuer_name: string; issued_on: string }[] }>(`
    query ($s: String!, $i: String!, $d: date!) {
      office_documents(where: {direction: {_eq: "in"}, status: {_neq: "cancelled"}, symbol: {_eq: $s},
                               issuer_name: {_ilike: $i}, issued_on: {_eq: $d}}, limit: 1) { symbol issuer_name issued_on }
    }`, { s: symbol, i: issuer.replace(/[\\%_]/g, '\\$&'), d: day })
  duplicate.value = data.office_documents[0] ?? null
}

async function save(register: boolean) {
  tried.value = true
  if (Object.keys(clientErrors.value).length) {
    await focusInvalidField()
    return
  }
  if (uploading.value) return
  saving.value = true
  let id: string
  try {
    const data = await gql<{ receiveIncoming: { document_id: string } }>(
      'mutation ($d: jsonb!) { receiveIncoming(data: $d) { document_id } }', { d: payload.value },
    )
    id = data.receiveIncoming.document_id
    draft.clear()
  } catch (e) {
    if (e instanceof ApiError && e.fields) {
      serverErrors.value = e.fields
      await focusInvalidField()
    }
    notice.error(errorText(t, e))
    saving.value = false
    return
  }
  // Đã tiếp nhận: vào sổ lỗi thì vẫn sang trang văn bản (vào sổ lại ở đó), không ở lại form — lưu lần nữa sẽ trùng
  try {
    if (register) {
      const reg = await gql<{ registerIncoming: { register_number: number } }>(
        'mutation ($id: uuid!) { registerIncoming(documentId: $id) { register_number } }', { id },
      )
      notice.ok(t('receive.registered', { n: reg.registerIncoming.register_number }))
    } else {
      notice.ok(t('receive.saved'))
    }
  } catch (e) {
    notice.error(errorText(t, e))
  } finally {
    saving.value = false
  }
  await router.push(`/van-ban/${id}`)
}
</script>

<template>
  <div>
    <PageHeader :title="t('receive.title')" :subtitle="t('receive.subtitle')" />

    <!-- không tải được danh mục loại văn bản: báo ngay trên trang, thử lại tại chỗ -->
    <div v-if="initialFailure" class="moc-state mb-6" role="alert">
      <span>{{ initialFailure }}</span>
      <button type="button" class="btn-secondary" @click="loadInitial">{{ t('app.retry') }}</button>
    </div>
    <!-- trình đọc màn hình: đang đọc, đọc xong (điền mấy ô), lỗi -->
    <p class="sr-only" aria-live="polite" data-testid="read-live">{{ announce }}</p>

    <form class="grid gap-6 lg:grid-cols-5" novalidate @submit.prevent="save(true)">
      <!-- tệp -->
      <section class="card p-5 lg:col-span-2">
        <h2 class="mb-3 text-sm font-semibold text-stone-800">{{ t('receive.file') }}</h2>
        <label
          class="relative flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2
                 border-dashed px-4 py-10 text-center text-sm transition focus-within:outline focus-within:outline-2
                 focus-within:outline-offset-2 focus-within:outline-brand-700"
          :class="dragging ? 'border-brand-600 bg-brand-50' : 'border-stone-300 hover:border-brand-500 hover:bg-stone-50'"
          @dragover.prevent="dragging = true" @dragleave="dragging = false" @drop.prevent="onDrop"
        >
          <svg class="h-8 w-8 text-brand-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M12 16V4m0 0l-4 4m4-4l4 4M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" /></svg>
          <span class="text-stone-600">{{ form.restricted ? t('receive.dropRestricted') : t('receive.drop') }}</span>
          <input id="incoming-files" type="file" class="sr-only" multiple :aria-invalid="!!show('file_ids')"
            :aria-describedby="show('file_ids') ? 'file_ids-error' : undefined"
            :accept="form.restricted ? 'application/pdf' : 'application/pdf,image/*'"
            @change="addFiles(($event.target as HTMLInputElement).files)"
          >
        </label>

        <ul class="mt-4 space-y-2">
          <li v-for="f in files" :key="f.key" class="rounded-md border border-stone-200 p-3 text-sm">
            <div class="flex items-center gap-2">
              <span class="min-w-0 flex-1 truncate font-medium">{{ f.name }}</span>
              <span class="text-xs text-stone-500">{{ fmtSize(f.size) }}</span>
              <button type="button" class="text-stone-400 hover:text-red-600" :aria-label="t('app.cancel')" @click="removeFile(f.key)">✕</button>
            </div>
            <div v-if="f.state === 'uploading'" class="mt-2">
              <div class="h-1.5 overflow-hidden rounded bg-stone-200"><div class="h-full bg-brand-600 transition-all" :style="{ width: f.progress + '%' }" /></div>
              <div class="mt-1 text-xs text-stone-500">{{ t('receive.scanning') }}</div>
            </div>
            <template v-else-if="f.state === 'clean'">
              <div class="mt-1 flex items-center gap-1 text-xs text-emerald-700">
                <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m5.6-4.4A11.9 11.9 0 0112 3a11.9 11.9 0 01-8.6 3.6A12 12 0 003 9c0 5.6 3.8 10.3 9 11.6 5.2-1.3 9-6 9-11.6 0-1-.1-2-.4-3z" /></svg>
                {{ f.uploaded?.encrypted ? t('receive.cleanSealed') : t('receive.clean') }}
              </div>

              <!-- đọc văn bản (F4.1): tệp của văn bản hạn chế không bao giờ đọc -->
              <p v-if="f.uploaded?.encrypted || form.restricted" class="mt-2 text-xs text-stone-500">{{ t('receive.read.restricted') }}</p>
              <div v-else class="mt-2 border-t border-stone-100 pt-2 text-xs" data-testid="read-state">
                <div v-if="f.read?.state === 'reading'" class="flex flex-wrap items-center gap-x-2 gap-y-1 text-stone-700">
                  <svg class="h-4 w-4 animate-spin text-brand-700 motion-reduce:animate-none" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" /><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" /></svg>
                  <span class="font-medium tabular-nums">{{ t('receive.read.reading', { s: elapsed(f) }) }}</span>
                  <span class="text-stone-500">{{ t('receive.read.readingHint') }}</span>
                </div>
                <div v-else class="flex flex-wrap items-center justify-between gap-2">
                  <span
                    v-if="f.read"
                    class="min-w-0 flex-1"
                    :class="f.read.state === 'error' ? 'font-medium text-red-700' : f.read.state === 'empty' ? 'text-amber-800' : 'text-stone-700'"
                  >
                    {{ f.read.message }}
                    <span v-if="f.read.cached" class="text-stone-500">({{ t('receive.read.cached') }})</span>
                  </span>
                  <span v-else class="flex-1" />
                  <button
                    type="button" class="btn-secondary !px-2.5 !py-1 !text-xs"
                    :disabled="reading || saving"
                    :aria-label="t('receive.read.forFile', { action: readAgain(f) ? t('receive.read.reread') : t('receive.read.button'), name: f.name })"
                    @click="readDocument(f, readAgain(f))"
                  >
                    <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6M7 3h7l5 5v11a2 2 0 01-2 2H7a2 2 0 01-2-2V5a2 2 0 012-2z" /></svg>
                    {{ readAgain(f) ? t('receive.read.reread') : t('receive.read.button') }}
                  </button>
                </div>
                <ul v-if="f.read?.notes?.length" class="mt-1 space-y-0.5 text-stone-500">
                  <li v-for="n in f.read.notes" :key="n">{{ n }}</li>
                </ul>
              </div>
            </template>
            <div v-else class="mt-1 text-xs font-medium text-red-600">{{ f.message }}</div>
          </li>
        </ul>
        <p v-if="show('file_ids')" id="file_ids-error" class="field-error">{{ show('file_ids') }}</p>
      </section>

      <!-- thông tin văn bản -->
      <section class="card space-y-4 p-5 lg:col-span-3">
        <div class="grid gap-4 sm:grid-cols-2">
          <div>
            <div class="mb-1 flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
              <label class="label !mb-0" for="type">{{ t('receive.type') }}</label>
              <SuggestTag id="type_code-suggest" data-testid="suggest-type_code" :suggestion="suggested.type_code" :value="form.type_code" :display="shown('type_code', suggested.type_code?.value ?? '')" />
            </div>
            <select id="type" v-model="form.type_code" class="input" :aria-invalid="!!show('type_code')" :aria-describedby="describedBy('type_code')" @change="touch('type_code')">
              <option v-for="ty in types" :key="ty.code" :value="ty.code">{{ ty.name }}</option>
            </select>
            <p v-if="show('type_code')" id="type_code-error" class="field-error">{{ show('type_code') }}</p>
            <p v-for="w in notes.type_code.warnings" :key="w" class="mt-1 text-xs text-amber-800">{{ w }}</p>
            <p v-if="notes.type_code.offer" id="type_code-offer" class="mt-1 text-xs text-stone-600">
              {{ t('receive.read.offer', { value: notes.type_code.offer }) }}
              <button type="button" class="ml-1 font-medium text-brand-700 underline underline-offset-2" :aria-label="t('receive.read.useFor', { value: notes.type_code.offer })" @click="takeOffer('type_code')">{{ t('receive.read.use') }}</button>
            </p>
          </div>
          <div>
            <div class="mb-1 flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
              <label class="label !mb-0" for="urgency">{{ t('receive.urgency') }}</label>
              <SuggestTag id="urgency-suggest" data-testid="suggest-urgency" :suggestion="suggested.urgency" :value="form.urgency" :display="shown('urgency', suggested.urgency?.value ?? '')" />
            </div>
            <select id="urgency" v-model="form.urgency" class="input" :aria-describedby="describedBy('urgency')" @change="touch('urgency')">
              <option v-for="u in URGENCIES" :key="u" :value="u">{{ t(`urgency.${u}`) }}</option>
            </select>
            <p v-if="notes.urgency.offer" id="urgency-offer" class="mt-1 text-xs text-stone-600">
              {{ t('receive.read.offer', { value: notes.urgency.offer }) }}
              <button type="button" class="ml-1 font-medium text-brand-700 underline underline-offset-2" :aria-label="t('receive.read.useFor', { value: notes.urgency.offer })" @click="takeOffer('urgency')">{{ t('receive.read.use') }}</button>
            </p>
          </div>
          <div>
            <div class="mb-1 flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
              <label class="label !mb-0" for="symbol">{{ t('receive.symbol') }}</label>
              <SuggestTag id="symbol-suggest" data-testid="suggest-symbol" :suggestion="suggested.symbol" :value="form.symbol" />
            </div>
            <input id="symbol" v-model="form.symbol" class="input" :placeholder="t('receive.symbolHint')" :aria-invalid="!!show('symbol')" :aria-describedby="describedBy('symbol')" @input="touch('symbol')" @compositionstart="touch('symbol')" @blur="checkDuplicate">
            <p v-if="show('symbol')" id="symbol-error" class="field-error">{{ show('symbol') }}</p>
            <p v-for="w in notes.symbol.warnings" :key="w" class="mt-1 text-xs text-amber-800">{{ w }}</p>
            <p v-if="notes.symbol.offer" id="symbol-offer" class="mt-1 text-xs text-stone-600">
              {{ t('receive.read.offer', { value: notes.symbol.offer }) }}
              <button type="button" class="ml-1 font-medium text-brand-700 underline underline-offset-2" :aria-label="t('receive.read.useFor', { value: notes.symbol.offer })" @click="takeOffer('symbol')">{{ t('receive.read.use') }}</button>
            </p>
          </div>
          <div>
            <div class="mb-1 flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
              <label class="label !mb-0" for="issued_on">{{ t('receive.issuedOn') }}</label>
              <SuggestTag id="issued_on-suggest" data-testid="suggest-issued_on" :suggestion="suggested.issued_on" :value="form.issued_on" :display="shown('issued_on', suggested.issued_on?.value ?? '')" />
            </div>
            <input id="issued_on" v-model="form.issued_on" type="date" class="input" :max="today()" :aria-invalid="!!show('issued_on')" :aria-describedby="describedBy('issued_on')" @input="touch('issued_on')" @keydown="touchDate" @change="touch('issued_on'); checkDuplicate()">
            <p v-if="show('issued_on')" id="issued_on-error" class="field-error">{{ show('issued_on') }}</p>
            <p v-for="w in notes.issued_on.warnings" :key="w" class="mt-1 text-xs text-amber-800">{{ w }}</p>
            <p v-if="notes.issued_on.offer" id="issued_on-offer" class="mt-1 text-xs text-stone-600">
              {{ t('receive.read.offer', { value: notes.issued_on.offer }) }}
              <button type="button" class="ml-1 font-medium text-brand-700 underline underline-offset-2" :aria-label="t('receive.read.useFor', { value: notes.issued_on.offer })" @click="takeOffer('issued_on')">{{ t('receive.read.use') }}</button>
            </p>
          </div>
        </div>
        <div>
          <div class="mb-1 flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
            <label class="label !mb-0" for="issuer">{{ t('receive.issuer') }}</label>
            <SuggestTag id="issuer_name-suggest" data-testid="suggest-issuer_name" :suggestion="suggested.issuer_name" :value="form.issuer_name" />
          </div>
          <input id="issuer" v-model="form.issuer_name" class="input" :aria-invalid="!!show('issuer_name')" :aria-describedby="describedBy('issuer_name')" @input="touch('issuer_name')" @compositionstart="touch('issuer_name')" @blur="checkDuplicate">
          <p v-if="show('issuer_name')" id="issuer_name-error" class="field-error">{{ show('issuer_name') }}</p>
          <p v-if="notes.issuer_name.offer" id="issuer_name-offer" class="mt-1 text-xs text-stone-600">
            {{ t('receive.read.offer', { value: notes.issuer_name.offer }) }}
            <button type="button" class="ml-1 font-medium text-brand-700 underline underline-offset-2" :aria-label="t('receive.read.useFor', { value: notes.issuer_name.offer })" @click="takeOffer('issuer_name')">{{ t('receive.read.use') }}</button>
          </p>
        </div>
        <div>
          <div class="mb-1 flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
            <label class="label !mb-0" for="summary">{{ t('receive.summary') }} <span class="font-normal text-stone-400">({{ t('receive.summaryHint') }})</span></label>
            <SuggestTag id="summary-suggest" data-testid="suggest-summary" :suggestion="suggested.summary" :value="form.summary" />
          </div>
          <textarea id="summary" v-model="form.summary" rows="3" class="input" :aria-invalid="!!show('summary')" :aria-describedby="describedBy('summary')" @input="touch('summary')" @compositionstart="touch('summary')" />
          <div class="mt-1 flex justify-between text-xs">
            <span id="summary-error" class="field-error !mt-0">{{ show('summary') }}</span>
            <span class="text-stone-400 tabular-nums">{{ summaryLength }}/{{ maxLength('summary') }}</span>
          </div>
          <p v-if="notes.summary.offer" id="summary-offer" class="mt-1 text-xs text-stone-600">
            {{ t('receive.read.offer', { value: notes.summary.offer }) }}
            <button type="button" class="ml-1 font-medium text-brand-700 underline underline-offset-2" :aria-label="t('receive.read.useFor', { value: notes.summary.offer })" @click="takeOffer('summary')">{{ t('receive.read.use') }}</button>
          </p>
        </div>
        <div class="grid gap-4 sm:grid-cols-2">
          <div>
            <label class="label" for="due_on">{{ t('receive.dueOn') }} <span class="font-normal text-stone-400">({{ t('app.optional') }})</span></label>
            <input
              id="due_on" v-model="form.due_on" type="date" class="input" :min="today()"
              :aria-invalid="!!show('due_on')"
              :aria-describedby="show('due_on') ? 'due_on-error' : undefined"
            >
            <p v-if="show('due_on')" id="due_on-error" class="field-error">{{ show('due_on') }}</p>
          </div>
          <label class="flex items-start gap-3 rounded-md border border-stone-200 p-3 text-sm" :class="{ 'opacity-60': files.length }">
            <input v-model="form.restricted" type="checkbox" class="mt-0.5 h-4 w-4 accent-brand-700" :disabled="files.length > 0" data-testid="restricted">
            <span>
              <span class="font-medium">{{ t('receive.restricted') }}</span><br>
              <span class="text-xs text-stone-500">{{ files.length ? t('receive.restrictedLocked') : t('receive.restrictedHint') }}</span>
            </span>
          </label>
        </div>

        <p v-if="duplicate" class="rounded-md bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-200" role="alert">
          {{ t('receive.duplicate', { symbol: duplicate.symbol, issuer: duplicate.issuer_name, date: fmtDate(duplicate.issued_on) }) }}
        </p>

        <p v-if="hasSuggestions" class="flex items-start gap-2 rounded-md bg-sky-50 p-3 text-sm text-sky-900 ring-1 ring-sky-200" data-testid="suggest-note">
          <svg class="mt-0.5 h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8h.01M11 12h1v4h1m-1 5a9 9 0 110-18 9 9 0 010 18z" /></svg>
          <span>{{ t('receive.read.confirmNote') }}</span>
        </p>

        <div class="flex flex-wrap justify-end gap-2 border-t border-stone-100 pt-4">
          <button type="button" class="btn-secondary" :disabled="saving || uploading" @click="save(false)">{{ t('receive.save') }}</button>
          <button type="submit" class="btn-primary" :disabled="saving || uploading">{{ t('receive.saveAndRegister') }}</button>
        </div>
      </section>
    </form>
  </div>
</template>
