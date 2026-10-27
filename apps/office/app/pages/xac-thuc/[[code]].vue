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

// Cổng xác thực văn bản (F2.13), công khai. Tra bằng mã in cạnh mã QR (quét QR là mở thẳng trang này), hoặc
// thả tệp PDF: trình duyệt tự tính SHA-256 (Web Crypto) và chỉ gửi mã băm đi tra — tệp không rời khỏi máy.
// Có mã rồi thì thả tệp để so: khớp từng byte với bản đã phát hành mới báo "khớp".
// Bản phát hành từ F4.5 có chữ ký số PAdES bằng PKI nội bộ trong két (chỉ minh họa, không có giá trị pháp lý): trang
// hiện chuẩn, người ký, CA, số sê-ri, giờ ký tự khai — lấy từ CSDL, svc-files đã tự kiểm chữ ký lúc ký; kiểm đầy đủ
// phần mật mã thì dùng pyHanko trong svc-files. Văn bản cũ hoặc hạn chế không có chữ ký số (signature: null).
// Khối chữ ký có liên kết tải chứng thư CA (/api/verify/ca.pem) kèm vân tay SHA-256; cuối trang là khóa công khai ký
// mốc neo sổ kiểm toán (/api/verify/anchor-key.pem) kèm vân tay — người ngoài tự kiểm mốc neo đã công bố bằng OpenSSL.
// Vân tay do trình duyệt tính trên đúng tệp vừa tải (utils/pemFingerprint.ts); két chưa có CA, chưa có khóa thì 404:
// không hiện vân tay, khối mốc neo ẩn.

definePageMeta({ layout: 'public' })

interface VerifiedSignature {
  level: string
  signer: string
  ca: string
  serial: string
  signed_at: string
  illustrative: boolean
}

interface Verified {
  symbol: string
  issued_on: string
  type_name: string
  issuer_name: string
  parent_name: string | null
  summary: string | null
  sha256: string
  verify_code: string
  status: string
  signature: VerifiedSignature | null
}

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const code = ref(String(route.params.code ?? ''))
const result = ref<'valid' | 'not_found' | null>(null)
const found = ref<Verified | null>(null)
const match = ref<boolean | null>(null)
const fileName = ref('')
const checking = ref(false)
const failure = ref('')
const dragging = ref(false)

const CA_URL = '/api/verify/ca.pem'
const ANCHOR_KEY_URL = '/api/verify/anchor-key.pem'
const caFingerprint = ref<string | null>(null)
const anchorKey = ref<{ fingerprint: string | null } | null>(null)

// tệp PEM công khai → có hay không, kèm vân tay (null khi trình duyệt không tính được); lỗi mạng coi như chưa có
async function publicPem(url: string, style: 'ca' | 'anchor'): Promise<{ fingerprint: string | null } | null> {
  try {
    const res = await fetch(url, { cache: 'no-store' })
    return res.ok ? { fingerprint: await pemFingerprint(await res.text(), style) } : null
  } catch {
    return null
  }
}

// chỉ tải CA khi có văn bản ký số để xem: mỗi lần tải tính vào giới hạn tra cứu theo IP
watch(() => found.value?.signature, async (signature) => {
  if (!signature || caFingerprint.value !== null) return
  caFingerprint.value = (await publicPem(CA_URL, 'ca'))?.fingerprint ?? null
})

const readableCode = computed(() => (found.value ? `${found.value.verify_code.slice(0, 5)}-${found.value.verify_code.slice(5)}` : ''))

async function call(url: string): Promise<{ result: 'valid' | 'not_found'; document: Verified | null }> {
  const res = await fetch(url, { cache: 'no-store' })
  if (res.status === 429) throw new Error(t('verify.rateLimited'))
  if (!res.ok) throw new Error(t('error.generic', { msg: `HTTP ${res.status}` }))
  return res.json()
}

async function run(job: () => Promise<void>) {
  checking.value = true
  failure.value = ''
  try {
    await job()
  } catch (e) {
    failure.value = e instanceof Error ? e.message : String(e)
  } finally {
    checking.value = false
  }
}

function lookup(value: string) {
  return run(async () => {
    const body = await call(`/api/verify/${encodeURIComponent(value)}`)
    result.value = body.result
    found.value = body.document
    match.value = null
    fileName.value = ''
  })
}

function submitCode() {
  const value = code.value.trim()
  if (!value) return
  router.replace(`/xac-thuc/${encodeURIComponent(value)}`)
  lookup(value)
}

async function digest(file: File): Promise<string> {
  const hash = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
  return Array.from(new Uint8Array(hash), (b) => b.toString(16).padStart(2, '0')).join('')
}

function onFile(file: File | undefined) {
  if (!file) return
  if (!window.crypto?.subtle) {
    failure.value = t('verify.noCrypto')
    return
  }
  run(async () => {
    const hash = await digest(file)
    fileName.value = file.name
    if (found.value) {
      match.value = hash === found.value.sha256
      return
    }
    const body = await call(`/api/verify?sha256=${hash}`)
    result.value = body.result
    found.value = body.document
    match.value = body.result === 'valid' ? true : null
  })
}

function onDrop(e: DragEvent) {
  dragging.value = false
  onFile(e.dataTransfer?.files?.[0])
}

onMounted(async () => {
  if (code.value) lookup(code.value)
  anchorKey.value = await publicPem(ANCHOR_KEY_URL, 'anchor')
})
</script>

<template>
  <div>
    <PageHeader :title="t('verify.title')" :subtitle="t('verify.subtitle')" />

    <div class="moc-stack">
      <form class="moc-block flex flex-wrap items-end gap-3" @submit.prevent="submitCode">
        <div class="min-w-48 flex-1">
          <label class="label" for="verify-code">{{ t('verify.code') }}</label>
          <input
            id="verify-code" v-model="code" class="input font-mono tracking-wider uppercase" maxlength="40"
            autocomplete="off" :placeholder="t('verify.codeHint')"
          >
        </div>
        <button type="submit" class="btn-primary" :disabled="checking || !code.trim()">{{ t('verify.lookup') }}</button>
      </form>

      <p v-if="checking" class="moc-loading">{{ t('verify.checking') }}</p>
      <p v-if="failure" class="moc-state">{{ failure }}</p>

      <!-- kết quả: một khối; chữ ký số, kết quả so tệp là các phần trong khối, ngăn bằng đường kẻ -->
      <section v-if="result === 'valid' && found" class="moc-block overflow-hidden !p-0" data-testid="verify-valid">
        <div class="flex items-center gap-3 border-b border-emerald-100 bg-emerald-50 px-6 py-3.5 text-emerald-900">
          <svg
            class="h-6 w-6 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"
            aria-hidden="true"
          >
            <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span class="font-semibold">{{ t('verify.valid') }}</span>
        </div>
        <dl class="moc-facts px-6 py-5">
          <div><dt>{{ t('verify.symbol') }}</dt><dd>{{ found.symbol }}</dd></div>
          <div><dt>{{ t('verify.issuedOn') }}</dt><dd class="tabular-nums">{{ fmtDate(found.issued_on) }}</dd></div>
          <div><dt>{{ t('verify.type') }}</dt><dd>{{ found.type_name }}</dd></div>
          <div>
            <dt>{{ t('verify.issuer') }}</dt>
            <dd>{{ found.issuer_name }}</dd>
            <dd v-if="found.parent_name">{{ found.parent_name }}</dd>
          </div>
          <div class="is-wide">
            <dt>{{ t('verify.summary') }}</dt>
            <dd :class="found.summary ? '' : '!font-normal !text-stone-500'">
              {{ found.summary ?? t('verify.summaryHidden') }}
            </dd>
          </div>
          <div><dt>{{ t('verify.code') }}</dt><dd class="font-mono tracking-wider">{{ readableCode }}</dd></div>
          <div class="is-wide">
            <dt>{{ t('verify.sha256') }}</dt>
            <dd class="font-mono text-[13px] break-all">{{ found.sha256 }}</dd>
          </div>
        </dl>
        <!-- chữ ký số PAdES (F4.5, chỉ minh họa): luôn kèm câu nói rõ không có giá trị pháp lý -->
        <div v-if="found.signature" class="border-t border-stone-100 px-6 py-5" data-testid="verify-signature">
          <h2 class="moc-block-title flex items-center gap-2">
            <svg
              class="h-4 w-4 shrink-0 text-stone-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"
              stroke-width="1.8" aria-hidden="true"
            >
              <path
                stroke-linecap="round" stroke-linejoin="round"
                d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6
                  18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zM19.5 7.125L16.862 4.487"
              />
            </svg>
            {{ t('verify.signature.title') }}
          </h2>
          <dl class="moc-facts mt-3">
            <div><dt>{{ t('verify.signature.level') }}</dt><dd>{{ found.signature.level }}</dd></div>
            <div>
              <dt>{{ t('verify.signature.signedAt') }}</dt>
              <dd class="tabular-nums">{{ fmtDateTime(found.signature.signed_at) }}</dd>
            </div>
            <div><dt>{{ t('verify.signature.signer') }}</dt><dd>{{ found.signature.signer }}</dd></div>
            <div><dt>{{ t('verify.signature.ca') }}</dt><dd>{{ found.signature.ca }}</dd></div>
            <div class="is-wide">
              <dt>{{ t('verify.signature.serial') }}</dt>
              <dd class="font-mono text-[13px] break-all">{{ found.signature.serial }}</dd>
            </div>
          </dl>
          <p class="moc-note mt-4 text-[13px]">{{ t('verify.signature.illustrative') }}</p>
          <div class="mt-3 text-[13px] text-stone-600" data-testid="verify-ca">
            <a :href="CA_URL" download="signet-ca.pem"
               class="font-medium text-brand-700 underline underline-offset-2"
            >{{ t('verify.signature.caDownload') }}</a>
            <span v-if="caFingerprint" class="mt-1 block">{{ t('verify.signature.caFingerprint') }}:
              <span class="font-mono break-all text-stone-700">{{ caFingerprint }}</span></span>
          </div>
        </div>
        <p v-else class="border-t border-stone-100 px-6 py-4 text-[13px] text-stone-500" data-testid="verify-unsigned">
          {{ t('verify.signature.none') }}
        </p>
        <!-- so tệp: nền nhạt theo kết quả, không chữ nhỏ trên nền đậm -->
        <div
          v-if="match !== null" data-testid="verify-match"
          class="mx-6 mb-6 flex items-start gap-3 rounded-lg border px-4 py-3 text-sm font-semibold"
          :class="match ? 'border-emerald-200 bg-emerald-50 text-emerald-900' : 'border-red-200 bg-red-50 text-red-800'"
        >
          <svg
            class="mt-0.5 h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"
          >
            <path v-if="match" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            <path v-else d="M12 9v4m0 4h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" />
          </svg>
          <span class="min-w-0">
            {{ match ? t('verify.match') : t('verify.mismatch') }}
            <span v-if="fileName" class="block text-[13px] font-normal wrap-anywhere">{{ fileName }}</span>
          </span>
        </div>
      </section>

      <section
        v-else-if="result === 'not_found'" data-testid="verify-not-found"
        class="rounded-xl border border-amber-200 bg-amber-50 px-6 py-5 text-amber-900"
      >
        <div class="font-semibold">{{ t('verify.notFound') }}</div>
        <p class="mt-1 text-sm">{{ t('verify.notFoundHint') }}</p>
        <p v-if="fileName" class="mt-1 text-[13px] wrap-anywhere">{{ fileName }}</p>
      </section>

      <!-- thả tệp: tra theo băm, hoặc so với văn bản vừa tra; ô chọn tệp ẩn nên viền sáng lên khi có tiêu điểm -->
      <label
        class="flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed px-6 py-10
          text-center text-sm text-stone-600 focus-within:outline-2 focus-within:outline-offset-2
          focus-within:outline-brand-700"
        :class="dragging ? 'border-brand-600 bg-brand-50' : 'border-stone-300 bg-white hover:bg-stone-50'"
        @dragover.prevent="dragging = true" @dragleave="dragging = false" @drop.prevent="onDrop"
      >
        <input
          id="verify-file" type="file" accept="application/pdf,.pdf" class="sr-only"
          @change="onFile(($event.target as HTMLInputElement).files?.[0])"
        >
        <svg
          class="h-8 w-8 text-brand-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6"
          aria-hidden="true"
        >
          <path
            stroke-linecap="round" stroke-linejoin="round"
            d="M12 16V4m0 0l-4 4m4-4l4 4M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2"
          />
        </svg>
        <span class="font-medium text-stone-800">{{ found ? t('verify.compare') : t('verify.file') }}</span>
        <span class="max-w-prose text-[13px] text-stone-500">{{ t('verify.fileHint') }}</span>
      </label>

      <!-- mốc neo sổ kiểm toán: khóa công khai để người ngoài tự kiểm mốc đã công bố; két chưa có khóa thì ẩn -->
      <section v-if="anchorKey" class="moc-block text-[13px] text-stone-600" data-testid="verify-anchor-key">
        <h2 class="moc-block-title">{{ t('verify.anchors.title') }}</h2>
        <p class="mt-1">{{ t('verify.anchors.text') }}</p>
        <a :href="ANCHOR_KEY_URL" download="signet-anchor-key.pem"
           class="mt-2 inline-block font-medium text-brand-700 underline underline-offset-2">
          {{ t('verify.anchors.download') }}
        </a>
        <p v-if="anchorKey.fingerprint" class="mt-1">{{ t('verify.anchors.fingerprint') }}:
          <span class="font-mono break-all text-stone-700">{{ anchorKey.fingerprint }}</span></p>
      </section>
    </div>
  </div>
</template>
