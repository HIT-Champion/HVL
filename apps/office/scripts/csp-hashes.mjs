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

// Tính băm SHA-256 của các thẻ <script> nội tuyến Nuxt sinh ra (importmap, cấu hình), để chính sách CSP
// chỉ cho chạy đúng các đoạn đó thay vì mở 'unsafe-inline'. Chạy sau `nuxt generate`, ghi ra tệp cấu hình
// nginx: node scripts/csp-hashes.mjs .output/public > .output/csp.conf
import { createHash } from 'node:crypto'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const root = process.argv[2] ?? '.output/public'
const hashes = new Set()

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) walk(path)
    else if (name.endsWith('.html')) scan(readFileSync(path, 'utf8'))
  }
}

function scan(html) {
  for (const m of html.matchAll(/<script(?![^>]*\bsrc=)([^>]*)>([\s\S]*?)<\/script>/g)) {
    const type = /type="([^"]+)"/.exec(m[1])?.[1]
    if (type === 'application/json') continue // khối dữ liệu, trình duyệt không chạy
    hashes.add(`'sha256-${createHash('sha256').update(m[2], 'utf8').digest('base64')}'`)
  }
}

walk(root)
process.stdout.write(`set $csp_scripts "${[...hashes].sort().join(' ')}";\n`)
