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

// Độ tương phản màu của giao diện Liền mạch theo WCAG 2.2 AA: chữ ≥ 4.5:1 với nền (1.4.3, tính cả chữ nhỏ), viền ô
// nhập và viền focus ≥ 3:1 với nền kề (1.4.11). Màu đọc thẳng từ app/assets/css/main.css (token @theme, :root và luật
// của khung), nên sửa màu mà trượt chuẩn thì test đỏ. Không kiểm: chữ của nút bị vô hiệu (WCAG miễn) và viền của nút
// có chữ (btn-secondary), vì chữ trong nút đã đủ cho biết đó là nút.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const css = readFileSync(new URL('../app/assets/css/main.css', import.meta.url), 'utf8')
const HEX = '(#[0-9a-fA-F]{6}\\b|#[0-9a-fA-F]{3}\\b)'

// biến CSS khai đúng một lần bằng mã hex: token('color-brand-700'), token('muted')
function token(name: string): string {
  const all = [...css.matchAll(new RegExp(`--${name}:\\s*${HEX}`, 'g'))]
  assert.equal(all.length, 1, `main.css: --${name} phải khai đúng một lần bằng mã hex`)
  return all[0][1]
}

// màu của thuộc tính trong luật đầu tiên có đúng bộ chọn này (tới dấu } đầu tiên)
function decl(selector: string, property: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const start = css.search(new RegExp(`^\\s*${escaped} \\{`, 'm'))
  assert.ok(start >= 0, `main.css: không thấy luật ${selector}`)
  const body = css.slice(start, css.indexOf('}', start))
  const hit = body.match(new RegExp(`(?:^|[\\s;{])${property}:[^;]*?${HEX}`))
  assert.ok(hit, `main.css: ${selector} không có ${property} dạng hex`)
  return hit[1]
}

// độ sáng tương đối và tỉ lệ tương phản theo định nghĩa của WCAG 2.x
function luminance(hex: string): number {
  const full = hex.length === 4 ? hex.replace(/[0-9a-f]/gi, (c) => c + c) : hex
  const [r, g, b] = [1, 3, 5].map((i) => {
    const v = parseInt(full.slice(i, i + 2), 16) / 255
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
function ratio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

const stone = (n: number) => token(`color-stone-${n}`)
const brand = (n: number) => token(`color-brand-${n}`)
const amber = (n: number) => token(`color-amber-${n}`)
const ground = token('ground')
const surface = token('surface')
const sidebar = decl('.sg-sidebar', 'background')

test('công thức tỉ lệ khớp ví dụ của WCAG', () => {
  assert.equal(ratio('#000000', '#ffffff').toFixed(2), '21.00')
  assert.equal(ratio('#777777', '#ffffff').toFixed(2), '4.48')
  assert.equal(ratio('#fff', '#ffffff'), 1)
})

test('chữ đạt 4.5:1 trên nền nó nằm', () => {
  const pairs: [string, string, string][] = [
    ['chữ chính trên nền trang', token('text'), ground],
    ['chữ chính trên thẻ trắng', token('text'), surface],
    ['chữ phụ --muted (cả thẻ lọc chưa chọn) trên nền trang', token('muted'), ground],
    ['chữ phụ --muted trên thẻ trắng', token('muted'), surface],
    ['chữ phụ --muted trên nền giấy', token('muted'), token('paper')],
    ['chữ phụ --muted trên nền chọn', token('muted'), token('active')],
    ['thẻ lọc đang chọn trên nền trang', decl('.moc-tabs button[aria-selected=true]', 'color'), ground],
    ['nút chính: chữ trắng trên lục bảo', '#ffffff', brand(700)],
    ['nút chính khi rê chuột', '#ffffff', brand(800)],
    ['nút phụ: chữ trên nền trắng', stone(800), surface],
    ['nút phụ khi rê chuột', stone(800), stone(50)],
    ['nút mờ (btn-ghost) trên nền trang', stone(600), ground],
    ['nút mờ khi rê chuột', stone(600), stone(100)],
    ['nhãn ô nhập trên nền trang', stone(700), ground],
    ['chữ gợi ý trong ô nhập', decl('input::placeholder, textarea::placeholder', 'color'), surface],
    ['text-stone-500 trên nền trang', stone(500), ground],
    ['text-stone-500 trên thẻ trắng', stone(500), surface],
    ['text-stone-400 trên nền trang', stone(400), ground],
    ['text-stone-400 trên thẻ trắng', stone(400), surface],
    ['text-stone-400 trên nền stone-50', stone(400), stone(50)],
    ['text-stone-400 trên nền stone-100', stone(400), stone(100)],
    ['liên kết lục bảo trên thẻ trắng', brand(700), surface],
    ['liên kết lục bảo trên nền trang', brand(700), ground],
    ['nhãn trạng thái stone', stone(700), stone(100)],
    ['nhãn trạng thái đã hủy', stone(600), stone(200)],
    ['nhãn lục bảo nhạt', brand(800), brand(50)],
    ['nhãn lục bảo', brand(800), brand(100)],
    ['nhãn vàng đậm', amber(900), amber(100)],
    ['nhãn vàng', amber(800), amber(100)],
    ['mục menu trên thanh bên', decl('.sg-nav-link', 'color'), sidebar],
    ['mục menu khi rê chuột', decl('.sg-nav-link', 'color'), decl('.sg-nav-link:hover::before', 'background')],
    ['mục menu đang mở', decl('.sg-nav-link.is-active', 'color'), decl('.sg-nav-link.is-active::before', 'background')],
    ['vai trò dưới tên trên thanh bên', decl('.sg-account-name small', 'color'), sidebar],
    ['báo lỗi chung (.moc-state)', decl('.moc-state', 'color'), decl('.moc-state', 'background')],
    ['ghi chú cảnh báo (.moc-note)', decl('.moc-note', 'color'), decl('.moc-note', 'background')],
    ['ghi chú thường (.moc-aside) trên nền giấy', token('muted'), token('paper')],
  ]
  for (const [what, fg, bg] of pairs) {
    const r = ratio(fg, bg)
    assert.ok(r >= 4.5, `${what}: ${fg} trên ${bg} chỉ ${r.toFixed(2)}:1, cần ≥ 4.5:1`)
  }
})

test('viền ô nhập, viền focus và gạch thẻ lọc đạt 3:1 với nền kề', () => {
  const focus = decl(':focus-visible', 'outline')
  const pairs: [string, string, string][] = [
    ['viền focus trên nền trang', focus, ground],
    ['viền focus trên thẻ trắng', focus, surface],
    // thanh bên lục bảo đậm: viền focus chung (lục bảo) chìm vào nền, nên thanh bên có viền focus riêng
    ['viền focus trên thanh bên', decl('.sg-sidebar :focus-visible', 'outline-color'), sidebar],
    ['viền focus trên mục đang mở (nền trắng)', decl('.sg-nav-link.is-active:focus-visible', 'outline-color'),
      decl('.sg-nav-link.is-active::before', 'background')],
    ['viền ô nhập trên nền trắng của ô', decl('@utility input', 'border-color'), surface],
    ['viền ô nhập với nền trang', decl('@utility input', 'border-color'), ground],
    ['viền ô nhập đang focus', decl('&:focus', 'border-color'), surface],
    ['gạch dưới thẻ lọc đang chọn', decl('.moc-tabs button[aria-selected=true]', 'border-color'), ground],
  ]
  for (const [what, fg, bg] of pairs) {
    const r = ratio(fg, bg)
    assert.ok(r >= 3, `${what}: ${fg} với ${bg} chỉ ${r.toFixed(2)}:1, cần ≥ 3:1`)
  }
})
