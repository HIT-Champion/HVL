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

import { readdir, readFile } from 'node:fs/promises';
import { resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc';

const root = fileURLToPath(new URL('../', import.meta.url));
let checked = 0;

function checkModule(source, file) {
  const result = spawnSync(process.execPath, ['--input-type=module', '--check'], {
    input: source,
    encoding: 'utf8',
  });
  if (result.status !== 0) throw new Error(`${file}: ${result.stderr || result.error?.message}`);
}

async function check(file) {
  if (file.endsWith('.d.ts')) return;
  if (file.endsWith('.ts')) throw new Error(`Dùng JavaScript cho FE: ${file}`);
  if (/\.(js|mjs)$/.test(file)) {
    const result = spawnSync(process.execPath, ['--check', file], { encoding: 'utf8' });
    if (result.status !== 0) throw new Error(result.stderr || result.error?.message);
    checked++;
  }
  if (!file.endsWith('.vue')) return;
  const source = await readFile(file, 'utf8');
  const { descriptor, errors } = parse(source, { filename: file });
  if (errors.length) throw new Error(`${file}: ${errors.join('\n')}`);
  if (descriptor.script?.lang === 'ts' || descriptor.scriptSetup?.lang === 'ts') {
    throw new Error(`Dùng <script setup> JavaScript: ${file}`);
  }
  const id = relative(root, file);
  const script = descriptor.script || descriptor.scriptSetup ? compileScript(descriptor, { id }) : null;
  if (script) checkModule(script.content, file);
  if (descriptor.template) {
    const result = compileTemplate({
      source: descriptor.template.content,
      filename: file,
      id,
      compilerOptions: { bindingMetadata: script?.bindings },
    });
    if (result.errors.length) throw new Error(`${file}: ${result.errors.join('\n')}`);
    checkModule(result.code, file);
  }
  checked++;
}

async function walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const file = resolve(dir, entry.name);
    if (entry.isDirectory()) await walk(file);
    else await check(file);
  }
}

for (const dir of ['app', 'dev', 'scripts', 'server']) await walk(resolve(root, dir));
await check(resolve(root, 'nuxt.config.js'));
console.log(`OK: ${checked} tệp JavaScript/Vue hợp lệ.`);
