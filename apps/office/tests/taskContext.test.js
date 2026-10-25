// Copyright 2026 Signet Team
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {documentBackTarget,processingBrief} from '../app/utils/taskContext.js';
test('task return destination accepts only a known inbox context and otherwise stays in document registers',()=>{
 assert.equal(documentBackTarget('inbox','in'),'/');
 for(const from of ['https://example.com','//example.com','/admin',undefined,['inbox']]) assert.equal(documentBackTarget(from,'in'),'/van-ban-den');
 assert.equal(documentBackTarget(undefined,'out'),'/van-ban-di');
});
test('staff brief combines own and parent instructions without duplicates and uses the assignment deadline',()=>{
 const assignments=[{id:'dept',instruction:'Review the attached proposal',due_on:'2026-11-01'},
 {id:'own',parent_id:'dept',user_id:'staff',status:'open',instruction:'Send the review to the head',due_on:'2026-10-30',assigned_by:'manager'},
 {id:'other',user_id:'other',status:'open',instruction:'Other task'},
 {id:'done',user_id:'staff',status:'done',instruction:'Old task'}];
 assert.deepEqual(processingBrief(assignments,'staff'),{instructions:['Review the attached proposal','Send the review to the head'],dueOn:'2026-10-30',assignedBy:'manager'});
 assignments[1].instruction=assignments[0].instruction;assignments[1].due_on=null;
 assert.deepEqual(processingBrief(assignments,'staff').instructions,['Review the attached proposal']);
 assert.equal(processingBrief(assignments,'staff').dueOn,'2026-11-01');
 assert.equal(processingBrief(assignments,undefined),null);
 assert.equal(processingBrief(assignments,'not-assigned'),null);
});
