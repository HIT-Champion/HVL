---
version: 1
slug: "apps-office-app-pages-index-vue"
primary_target: "apps/office/app/pages/index.vue"
related_targets: ["apps/office/app/layouts/default.vue", "apps/office/app/components/TaskQueueItem.vue", "apps/office/app/assets/css/main.css"]
---

# Signet — Butter workspace

Mode: Operate. Primary audience: daily document-processing staff. Existing roles, API contracts and permissions remain authoritative. The user explicitly selected **butter** after rerolling three interactive proposals on 23/10/2026. This replaces the rejected wine masthead and the earlier three-pane workbench.

THESIS: Staff see actual tasks needing attention first and remaining work below, with one direct document link per item.

OWN-WORLD: Butter navigation, warm white surroundings, white work surfaces and olive actions. Gentle 8px controls and 12px panels. Lora is identity only; clear sans-serif type carries all work. Tokens belong to root DESIGN.md.

STORY: Enter assigned work; find urgent or overdue items; optionally filter by document type, deadline state or text; open the real processing page. Metadata, full files and business actions stay in document detail. No duplicate preview or invented history.

FIRST VIEWPORT: A 244px sidebar track with 16px inset, a light utility row and one work axis. Main heading/compose, scoped search and native filters, attention surface, remaining list. Sidebar retracts to a 92px track (76px visible panel), preserving icon names and remembering preference. Below 900px it becomes a focus-trapped drawer with inert background; phone content stacks deadlines beneath task titles.

FORM: seed:69aa3c2a0b521ac9, surface/operate reroll1. The three dealt compositions were4/2/5; Butter was candidate5 and selected directly in chat. The user's pinned left sidebar, bright vintage palette, mild rounding and motion supersede the old unapproved visual system. Code-led chosen reference: `.impeccable/mocks/decision/butter-attention.html`; screenshots in `.impeccable/review-v3/reroll-1/`.

FINISH: Compare live source and screenshots honestly. A chosen direction is not acceptance of the final implementation. Sidebar transitions260ms, task feedback140–180ms, reduced motion removes spatial effects. Real task urgency or overdue due_on determines attention; each task appears once. Local only; no push.

## Preserved functions and adaptations

- `myTasks`, notifications, deadline rollover, retry/empty recovery and direct document routes remain live.
- Category filtering joins the pre-existing all/today/overdue/urgent filter; no business state is invented.
- The drawer threshold expands from the prototype's640px to900px to preserve usable tablet navigation.
- Existing notification, language, logout and verification controls remain available; their presence is a functional adaptation to the prototype.
- The Butter system extends to forms, tables, cases and charts; their own information architecture is preserved.
