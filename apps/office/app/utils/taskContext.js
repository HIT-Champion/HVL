// Copyright 2026 Signet Team
// SPDX-License-Identifier: Apache-2.0

export function documentBackTarget(from, direction) {
  return from === 'inbox' ? '/' : direction === 'out' ? '/van-ban-di' : '/van-ban-den';
}

// Use only assignments already returned under the viewer's backend permissions.
export function processingBrief(assignments, userId, documentDue = null) {
  if (!userId) return null;
  const mine = assignments.filter(a => a.user_id === userId && a.status !== 'done').at(-1);
  if (!mine) return null;
  const parent = assignments.find(a => a.id === mine.parent_id);
  return {
    instructions: [...new Set([parent?.instruction, mine.instruction].filter(text => text?.trim()))],
    dueOn: mine.due_on || parent?.due_on || documentDue,
    assignedBy: mine.assigned_by || null,
  };
}
