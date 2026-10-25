// Copyright 2026 Signet Team
// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from 'node:fs';

// Source-contract checks compare semantics across Windows line endings and the
// JavaScript compiler's optional end-of-line semicolons. Runtime behavior has its own tests.
export function readSource(file, options) {
  const value = readFileSync(file, options);
  if (typeof value !== 'string') return value;
  const text = value.replaceAll('\r\n', '\n');
  return /\.(vue|js)$/.test(String(file)) ? text.replace(/;(?=\n|$)/g, '') : text;
}
