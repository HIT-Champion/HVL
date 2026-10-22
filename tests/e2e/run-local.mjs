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

import { readFileSync } from 'node:fs';
import { parseEnv } from 'node:util';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const env = { ...parseEnv(readFileSync(new URL('../../.env', import.meta.url), 'utf8')), ...process.env };
if (process.platform === 'win32' && !env.MOC_E2E_CHANNEL) env.MOC_E2E_CHANNEL = 'msedge';
const result = spawnSync(process.execPath, [
  fileURLToPath(new URL('node_modules/@playwright/test/cli.js', import.meta.url)),
  'test', ...process.argv.slice(2),
], { cwd: fileURLToPath(new URL('./', import.meta.url)), env, stdio: 'inherit' });
if (result.error) console.error(result.error.message);
process.exitCode = result.status ?? 1;
