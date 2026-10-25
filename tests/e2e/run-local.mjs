// Copyright 2026 Signet Team
// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from 'node:fs';
import { parseEnv } from 'node:util';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const root = new URL('../../', import.meta.url);
const env = { ...parseEnv(readFileSync(new URL('.env', root), 'utf8')), ...process.env };
if (process.platform === 'win32' && !env.MOC_E2E_CHANNEL) env.MOC_E2E_CHANNEL = 'msedge';
const child = spawn(process.execPath, [fileURLToPath(new URL('node_modules/@playwright/test/cli.js', import.meta.url)), 'test', ...process.argv.slice(2)], { cwd: fileURLToPath(new URL('.', import.meta.url)), env, stdio: 'inherit' });
child.on('error', error => { console.error(error.message); process.exitCode = 1; });
child.on('exit', code => { process.exitCode = code ?? 1; });
