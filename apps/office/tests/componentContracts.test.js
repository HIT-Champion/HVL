// Copyright 2026 Signet Team
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parse, compileScript } from '@vue/compiler-sfc';

test('JavaScript SFCs expose the runtime props consumed by charts, source links and processing forms', () => {
  const contracts = {
    EChart: ['option', 'label', 'height'],
    ChartChecks: ['chart', 'checks', 'failed'],
    SourceLink: ['chart'],
    QualityFlag: ['status', 'detail', 'empty'],
    TaskPanel: ['brief', 'taskId', 'formKey', 'documentId', 'documentDue', 'restricted', 'users', 'departments', 'myDepartment', 'myId'],
  };
  for (const [name, props] of Object.entries(contracts)) {
    const file = new URL(`../app/components/${name}.vue`, import.meta.url);
    const { descriptor } = parse(readFileSync(file, 'utf8'), { filename: name + '.vue' });
    const script = compileScript(descriptor, { id: name });
    for (const prop of props) assert.equal(script.bindings[prop], 'props', `${name}.${prop} must be a Vue prop, not an undeclared attribute`);
  }
});
